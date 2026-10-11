"""Cold original-YOLO controls: response acceptance is not final fact commit.

Fixed empty JPEG inputs test engineering behavior, never human accuracy.
No camera, socket listener, patient database or candidate model is used.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import closing
from io import BytesIO
import json
import sqlite3
import time
from uuid import uuid4

from .common import ROOT, file_hash, paths, write_json
from .session_load_audit import fact, reconcile

WORKLOAD = dict(version='rehab-session-cold-1', image_size=[320, 240], frames=1,
                pause_resume_pairs=1, concurrent_finish_requests=4, deadline_s=45,
                inference_provider='original_owned_yolo', wait_for_warm_result=False,
                transport='in_process_ASGI_HTTP_not_socket_network',
                fixture='TEST_empty_jpeg_and_manual_plan_no_human_reference')


async def exercise(app, service, encoded, details):
    import httpx
    from app.rehab_v2.telemetry import percentiles

    owner = 'TEST-cold-owner'
    timings = {key: [] for key in ('pause', 'resume', 'finish', 'state', 'commit')}
    details['http_timings_ms'] = timings
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                base_url='http://test-owned',
                                cookies={'test-cold-auth': 'TEST-owned'}) as client:
        async def call(method, path, stage=None, **kwargs):
            started = time.perf_counter()
            response = await client.request(method, path, **kwargs)
            if stage:
                timings[stage].append(1000*(time.perf_counter()-started))
            return response

        created = await call('POST', '/api/rehab/v2/sessions',
                             json=dict(idempotency_key='TEST-create', consent=True))
        created.raise_for_status()
        sid = created.json()['session_id']
        endpoint = '/api/rehab/v2/sessions/'+sid
        details['session_id'] = sid
        response = await call('POST', endpoint+'/frames', content=encoded,
            headers={'content-type': 'image/jpeg', 'x-rehab-event-id': 'TEST-frame', 'x-rehab-seq': '1'})
        response.raise_for_status()
        deadline = time.monotonic()+WORKLOAD['deadline_s']
        # A durable state row or lock file alone does not prove live work.
        # Inspect the actual owned process and submitted first native ticket.
        while True:
            worker = service.inference_worker
            item = service.get(owner, sid)
            request = worker.last_request
            if (request and request['session_id'] == sid and request['seq'] == 1
                    and worker.process is not None and worker.process.is_alive()
                    and not worker.warm and service.inflight and service.inflight['seq'] == 1
                    and item['processed_count'] == 0):
                details['cold_live_ticket'] = dict(request)
                break
            if time.monotonic() >= deadline or item['persistence_state'] == 'finalized':
                raise RuntimeError('first_cold_native_ticket_not_observed_live')
            await asyncio.sleep(.005)
        revision = 0
        for operation in ('pause', 'resume'):
            response = await call('POST', endpoint+'/'+operation, operation,
                json=dict(idempotency_key='TEST-'+operation, expected_revision=revision))
            response.raise_for_status()
            revision = response.json()['revision']
        details['cold_at_finish'] = dict(
            process_alive=worker.process is not None and worker.process.is_alive(),
            warm=worker.warm, inflight=bool(service.inflight and service.inflight['sid'] == sid),
            processed_count=service.get(owner, sid)['processed_count'])
        payload = dict(idempotency_key='TEST-finish', expected_revision=revision, reason='user_stopped')
        started = time.perf_counter()
        responses = await asyncio.gather(*(call('POST', endpoint+'/finish', 'finish', json=payload)
                                          for _ in range(WORKLOAD['concurrent_finish_requests'])))
        for response in responses:
            response.raise_for_status()
        details['finish_responses'] = [dict(http_status=row.status_code, payload=row.json()) for row in responses]
        # Both the pre-fix blocking protocol and the asynchronous protocol are
        # audited; never treat a 202 acceptance as a finalized receipt.
        deadline = time.monotonic()+WORKLOAD['deadline_s']
        while True:
            response = await call('GET', endpoint+'/commit', 'commit')
            response.raise_for_status()
            if response.json().get('receipt') is not None:
                commit = response.json()['receipt']
                break
            if time.monotonic() >= deadline:
                raise RuntimeError('durable_finish_commit_not_observed')
            await asyncio.sleep(.01)
        details['finish_to_commit_observed_ms'] = 1000*(time.perf_counter()-started)
        initial = fact(service.get(owner, sid))
        initial_audit = service.repository.audit_view(owner, sid)
        late_frame = await call('POST', endpoint+'/frames', content=encoded,
            headers={'content-type': 'image/jpeg', 'x-rehab-event-id': 'TEST-late', 'x-rehab-seq': '2'})
        retry = await call('POST', endpoint+'/finish', json=payload)
        changed_key = await call('POST', endpoint+'/finish', json=dict(payload, idempotency_key='TEST-alias'))
        conflict = await call('POST', endpoint+'/finish', json=dict(payload, reason='completed'))
        feedback_payload = dict(idempotency_key='TEST-feedback', expected_revision=0,
                                feedback=dict(pain=None, fatigue=None))
        feedback = await call('POST', endpoint+'/feedback', json=feedback_payload)
        duplicate = await call('POST', endpoint+'/feedback', json=feedback_payload)
        for response in (retry, changed_key, feedback, duplicate):
            response.raise_for_status()
        deadline = time.monotonic()+WORKLOAD['deadline_s']
        while service.frames.unfinished_tasks:
            if time.monotonic() >= deadline:
                raise RuntimeError('owned_native_frame_not_settled')
            await asyncio.sleep(.01)
        final = service.get(owner, sid)
        audit = service.repository.audit_view(owner, sid)
        checked = reconcile(final, audit)
        checked['checks'].update(
            controls_observed_during_cold_native_work=(details['cold_at_finish'] == dict(
                process_alive=True, warm=False, inflight=True, processed_count=0)),
            all_finish_responses_one_operation=all(
                row['payload'] == commit if row['payload'].get('status') == 'finalized' else
                row['http_status'] == 202 and row['payload'] == dict(
                    status='finishing', session_id=sid, accepted_last_seq=1)
                for row in details['finish_responses']),
            one_freeze_boundary=sum(row['kind'] == 'freeze_boundary' for row in audit['audit']) == 1,
            same_and_new_key_recover_canonical=retry.json() == changed_key.json() == commit,
            changed_payload_conflict=conflict.status_code == 409 and conflict.json()['detail'] == 'idempotency_payload_conflict',
            late_frame_rejected=late_frame.status_code == 409 and late_frame.json()['detail'] == 'session_not_accepting_frames',
            visual_fact_immutable=fact(final) == initial,
            frame_rows_immutable=audit['frames'] == initial_audit['frames'],
            no_people_no_confirmed_reps=final['snapshot']['completed'] == 0,
            null_feedback_not_zero=feedback.json()['pain'] is None and feedback.json()['fatigue'] is None,
            feedback_retry_once=feedback.json() == duplicate.json() and final['feedback_revision'] == 1)
        details.update(final_fact=fact(final), frame_audit=audit, final_state=final)
        return dict(http={key: percentiles(values) for key, values in timings.items()},
                    reconciliation=checked, final_commit=commit,
                    finish_to_commit_observed_ms=details['finish_to_commit_observed_ms'])


def benchmark_session_cold():
    import yaml
    from fastapi import FastAPI, HTTPException
    from PIL import Image
    from mobile_rehab.rehab_v2.api import install_rehab_v2
    from .inventory import doctor

    run = paths()['run']/('session-cold-'+uuid4().hex[:8])
    run.mkdir()
    sources = ('tools/rehab_ml/session_cold_audit.py', 'tools/rehab_ml/session_load_audit.py',
               'mobile_rehab/rehab_v2/api.py', 'mobile_rehab/rehab_v2/service.py',
               'mobile_rehab/rehab_v2/pose_worker.py', 'mobile_rehab/rehab_v2/owned_worker.py',
               'rehab_codex_single_camera_v2_1/app/rehab_v2/sessions.py',
               'configs/rehab_ml/backend.yaml',
               'rehab_codex_single_camera_v2_1/assets/models/yolo11n-pose.pt')
    hashes = {path: file_hash(ROOT/path) for path in sources}
    budgets = yaml.safe_load((ROOT/'configs/rehab_ml/backend.yaml').read_text(encoding='utf-8'))['performance_predeclared']
    declared = dict(workload=WORKLOAD, budgets=budgets, source_sha256=hashes, environment=doctor())
    write_json(run/'predeclared.json', declared)
    app = FastAPI()
    def owner(request):
        if request.cookies.get('test-cold-auth') != 'TEST-owned':
            raise HTTPException(401, 'authentication_required')
        return 'TEST-cold-owner'
    async def small_json(request):
        body = await request.body()
        if len(body) > 4096:
            raise HTTPException(413)
        return json.loads(body)
    def plan(owner, payload):
        return dict(plan_id='TEST-cold-plan', plan_revision=1, entry_key='shoulder_abduction:left',
            reference=dict(record_origin='manual', fixture=True),
            plan=dict(exercise_id='shoulder_abduction', side='left', target_reps=1, target_sets=1, submode='training'))
    details, result, service = {}, {}, None
    database = run/'isolated.sqlite3'
    try:
        service = install_rehab_v2(app, database, owner, small_json, plan)
        buffer = BytesIO()
        Image.new('RGB', WORKLOAD['image_size'], 'white').save(buffer, format='JPEG')
        result = asyncio.run(exercise(app, service, buffer.getvalue(), details))
    except Exception as error:
        result['error'] = dict(type=type(error).__name__, message=str(error))
    finally:
        if service is not None:
            try:
                service.close()
            except Exception as error:
                result['shutdown_error'] = dict(type=type(error).__name__, message=str(error))
            result['shutdown'] = dict(resources_released=service.resources_released,
                pose_process_retained=service.inference_worker.process is not None,
                consumers_alive=any(thread.is_alive() for thread in (service.worker, service.report_worker)
                                    + ((service.finish_worker,) if hasattr(service, 'finish_worker') else ())))
    if 'final_commit' in result:
        with closing(sqlite3.connect(database.as_uri()+'?mode=ro', uri=True)) as conn:
            saved = json.loads(conn.execute('SELECT payload FROM rehab_v2_sessions').fetchone()[0])
            counts = [conn.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in
                      ('rehab_v2_sessions', 'rehab_v2_plan_contributions')]
        result['reconciliation']['checks']['independent_reopen_same_fact'] = (
            saved['canonical_commit'] == result['final_commit'] and saved['snapshot'] == details['final_fact']['snapshot']
            and counts == [1, 1])
    result.update(run_id=run.name, predeclared=declared, clinical_accuracy=None,
                  source_unchanged=hashes == {path: file_hash(ROOT/path) for path in sources},
                  exclusions=['phone', 'camera', 'socket_network', 'human_accuracy', 'long_duration_soak'])
    checks = result.get('reconciliation', {}).get('checks', {})
    result['engineering_invariants_passed'] = bool(checks) and all(checks.values()) and result['source_unchanged']
    result['control_budget'] = {key: dict(p95_ms=result.get('http', {}).get(key, {}).get('p95_ms'),
        budget_ms=budgets['control_response_p95_ms']) for key in ('pause', 'resume', 'finish')}
    result['control_budget_met'] = all(row['p95_ms'] is not None and row['p95_ms'] <= row['budget_ms']
                                     for row in result['control_budget'].values())
    shutdown = result.get('shutdown', {})
    result['passed'] = (result['engineering_invariants_passed'] and result['control_budget_met'] and
                        shutdown.get('resources_released') and not shutdown.get('pose_process_retained') and
                        not shutdown.get('consumers_alive') and 'error' not in result and 'shutdown_error' not in result)
    write_json(run/'details.json', details)
    result['raw_details'] = dict(path=str(run/'details.json'), sha256=file_hash(run/'details.json'))
    write_json(run/'summary.json', result)
    result['raw_summary'] = dict(path=str(run/'summary.json'), sha256=file_hash(run/'summary.json'))
    write_json(ROOT/'reports/rehab_backend/session_cold.json', result)
    return result


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    result = benchmark_session_cold()
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
