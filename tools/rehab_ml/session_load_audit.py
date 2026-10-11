"""Bounded continuous ASGI/JPEG load with the unchanged owned YOLO worker.

TEST empty images are engineering inputs, not human movement evidence.
No port, camera, production database, candidate model or client is opened.
The workload and budgets are recorded before any requests are issued.
"""
from __future__ import annotations

import asyncio
from collections import Counter
from contextlib import asynccontextmanager, closing
import hashlib
from io import BytesIO
import json
import sqlite3
import time
from uuid import uuid4

from .common import ROOT, file_hash, paths, write_json

WORKLOAD = dict(version='rehab-session-load-1.1', frames=160, requested_send_hz=80,
                pause_resume_pairs=6, pause_s=.04, between_pairs_s=.12,
                finish_after_sent=100, concurrent_finish_requests=4,
                query_period_s=.04, deadline_s=45, cold_warmup_frames=1,
                image_size=[320, 240], inference_provider='original_owned_yolo',
                transport='in_process_ASGI_HTTP_not_socket_network',
                fixture='TEST_empty_jpeg_and_manual_plan_no_human_reference',
                feedback_after_finish='explicit_null_pain_and_fatigue_then_identical_retry')


def fact(item):
    """Exclude mutable derived report/diagnostic state, not visual facts."""
    keys = ('canonical_commit', 'snapshot', 'accepted_count', 'processed_count',
            'accepted_last_seq', 'processed_last_seq', 'persisted_evidence_seq',
            'terminal_epoch', 'dropped_intervals', 'plan_contribution')
    return {key: item[key] for key in keys}


def reconcile(item, audit):
    """Check exact durable frames; a sequence high-water mark is not coverage."""
    frames = audit['frames']
    seqs = [row['seq'] for row in frames]
    processed = [row['seq'] for row in frames if row['status'] == 'processed']
    counts = dict(Counter(row['status'] for row in frames))
    exclusions = {(row['seq'], row['reason']) for row in frames
                  if row['status'] in ('dropped', 'unprocessed', 'failed')}
    intervals = {(seq, row['reason']) for row in item['dropped_intervals']
                 for seq in range(row['from_seq'], row['to_seq']+1)}
    return dict(status_counts=counts, checks=dict(
        unique_frame_sequences=len(seqs) == len(set(seqs)),
        accepted_count_matches_rows=item['accepted_count'] == len(frames),
        processed_count_matches_rows=item['processed_count'] == len(processed),
        accepted_boundary_matches_rows=item['accepted_last_seq'] == max(seqs, default=-1),
        processed_boundary_matches_rows=item['processed_last_seq'] == max(processed, default=-1),
        persisted_boundary_matches_rows=item['persisted_evidence_seq'] == max(processed, default=-1),
        no_pending_after_terminal=counts.get('accepted', 0) == 0,
        known_statuses=set(counts) <= {'processed', 'dropped', 'unprocessed', 'failed'},
        exclusions_explicit=exclusions == intervals,
        one_finalize=sum(row['kind'] == 'finalize' for row in audit['audit']) == 1,
        one_contribution=sum(row['kind'] == 'plan_contribution' for row in audit['audit']) == 1))


async def exercise(app, service, encoded, details):
    import httpx
    from app.rehab_v2.telemetry import percentiles

    owner = 'TEST-load-owner'
    timings = {key: [] for key in ('frame', 'state', 'diagnostics', 'pause', 'resume', 'finish', 'feedback')}
    responses, samples = [], []
    details.update(http_timings_ms=timings, frame_responses=responses, diagnostics_samples=samples)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                base_url='http://test-owned',
                                cookies={'test-load-auth': 'TEST-owned'}) as client:
        async def call(method, path, stage=None, **kwargs):
            start = time.perf_counter()
            response = await client.request(method, path, **kwargs)
            if stage:
                timings[stage].append(1000*(time.perf_counter()-start))
            return response

        create_payload = dict(idempotency_key='TEST-load-create', consent=True)
        created = await call('POST', '/api/rehab/v2/sessions', json=create_payload)
        created.raise_for_status()
        sid = created.json()['session_id']
        endpoint = '/api/rehab/v2/sessions/'+sid
        details['session_id'] = sid
        duplicate = await call('POST', '/api/rehab/v2/sessions', json=create_payload)
        duplicate.raise_for_status()
        async def frame(seq):
            response = await call('POST', endpoint+'/frames', 'frame', content=encoded,
                headers={'content-type': 'image/jpeg', 'x-rehab-event-id': 'TEST-frame-'+str(seq),
                         'x-rehab-seq': str(seq)})
            responses.append(dict(seq=seq, status=response.status_code, payload=response.json()))
            if response.status_code != 200 and not (
                    response.status_code == 409 and response.json().get('detail') == 'session_not_accepting_frames'):
                response.raise_for_status()
            return response

        await frame(1)
        deadline = time.monotonic()+WORKLOAD['deadline_s']
        while True:
            state = await call('GET', endpoint, 'state')
            state.raise_for_status()
            if state.json()['processed_count'] == 1:
                break
            if state.json()['persistence_state'] == 'finalized' or time.monotonic() >= deadline:
                raise RuntimeError('cold_frame_not_processed')
            await asyncio.sleep(.01)
        cold = await call('GET', endpoint+'/diagnostics')
        cold.raise_for_status()
        details['cold_diagnostics'] = cold.json()
        warm_http_offsets = {key: len(values) for key, values in timings.items()}

        sent_boundary, stop_observer = asyncio.Event(), asyncio.Event()
        async def producer():
            start = time.monotonic()
            for index in range(WORKLOAD['frames']):
                # Fixed target schedule without waiting for model results.
                # Catch-up requests remain bounded by the declared frame count.
                await asyncio.sleep(max(0., start+index/WORKLOAD['requested_send_hz']-time.monotonic()))
                await frame(index+2)
                if index+1 == WORKLOAD['finish_after_sent']:
                    sent_boundary.set()
            return dict(elapsed_s=time.monotonic()-start, attempted=WORKLOAD['frames'])

        async def observer():
            while not stop_observer.is_set():
                state = await call('GET', endpoint, 'state')
                state.raise_for_status()
                response = await call('GET', endpoint+'/diagnostics', 'diagnostics')
                response.raise_for_status()
                samples.append(response.json())
                await asyncio.sleep(WORKLOAD['query_period_s'])

        async def controls():
            revision = 0
            for index in range(WORKLOAD['pause_resume_pairs']):
                for operation in ('pause', 'resume'):
                    response = await call('POST', endpoint+'/'+operation, operation,
                        json=dict(idempotency_key='TEST-'+operation+str(index), expected_revision=revision))
                    response.raise_for_status()
                    revision = response.json()['revision']
                    await asyncio.sleep(WORKLOAD['pause_s'] if operation == 'pause' else WORKLOAD['between_pairs_s'])
            return revision

        tasks = [asyncio.create_task(producer()), asyncio.create_task(observer()), asyncio.create_task(controls())]
        try:
            revision = await asyncio.wait_for(tasks[2], WORKLOAD['deadline_s'])
            # Await the producer OR gate: an early producer failure is not a
            # perpetual wait for an event that will never be emitted.
            gate = asyncio.create_task(sent_boundary.wait())
            try:
                done, _ = await asyncio.wait([gate, tasks[0]], timeout=WORKLOAD['deadline_s'],
                                             return_when=asyncio.FIRST_COMPLETED)
                if tasks[0] in done:
                    tasks[0].result()
                if not sent_boundary.is_set():
                    raise RuntimeError('finish_ingress_boundary_not_reached')
            finally:
                gate.cancel()
                await asyncio.gather(gate, return_exceptions=True)
            before = await call('GET', endpoint+'/diagnostics')
            before.raise_for_status()
            details['at_finish'] = before.json()
            details['producer_done_at_finish'] = tasks[0].done()
            payload = dict(idempotency_key='TEST-finish', expected_revision=revision, reason='user_stopped')
            finished = await asyncio.gather(*(call('POST', endpoint+'/finish', 'finish', json=payload)
                                             for _ in range(WORKLOAD['concurrent_finish_requests'])))
            for response in finished:
                response.raise_for_status()
            receipts = [response.json() for response in finished]
            details['finish_response_statuses'] = [response.status_code for response in finished]
            deadline = time.monotonic()+WORKLOAD['deadline_s']
            while True:
                queried = await call('GET', endpoint+'/commit')
                queried.raise_for_status()
                canonical = queried.json().get('receipt')
                if canonical is not None:
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError('accepted_finish_did_not_commit')
                await asyncio.sleep(.01)
            frozen = service.get(owner, sid)
            first_fact, first_audit = fact(frozen), service.repository.audit_view(owner, sid)
            details['producer'] = await asyncio.wait_for(tasks[0], WORKLOAD['deadline_s'])
            stop_observer.set()
            await asyncio.wait_for(tasks[1], WORKLOAD['deadline_s'])
            retry = await call('POST', endpoint+'/finish', json=payload)
            changed_key = await call('POST', endpoint+'/finish', json=dict(payload, idempotency_key='TEST-new-finish'))
            conflict = await call('POST', endpoint+'/finish', json=dict(payload, reason='completed'))
            commit = await call('GET', endpoint+'/commit')
            for response in (retry, changed_key, commit):
                response.raise_for_status()
            feedback_payload = dict(idempotency_key='TEST-feedback', expected_revision=0,
                                    feedback=dict(pain=None, fatigue=None))
            feedback = await call('POST', endpoint+'/feedback', 'feedback', json=feedback_payload)
            feedback_retry = await call('POST', endpoint+'/feedback', 'feedback', json=feedback_payload)
            feedback.raise_for_status()
            feedback_retry.raise_for_status()
            # Confirm all owned work has settled before testing immutable facts.
            deadline = time.monotonic()+WORKLOAD['deadline_s']
            while service.frames.unfinished_tasks:
                if time.monotonic() >= deadline:
                    raise RuntimeError('owned_frame_drain_did_not_settle')
                await asyncio.sleep(.01)
            final = service.get(owner, sid)
            audit = service.repository.audit_view(owner, sid)
            diagnostics = service.diagnostics(owner, sid)
            checks = reconcile(final, audit)
            checks['checks'].update(
                create_retry_same_session=duplicate.json()['session_id'] == sid,
                concurrent_finish_same_receipt=all(row == canonical if row.get('status') == 'finalized' else
                    response.status_code == 202 and row == dict(status='finishing', session_id=sid,
                        accepted_last_seq=frozen['accepted_last_seq']) for row, response in zip(receipts, finished)),
                same_key_retry_same_receipt=retry.json() == canonical,
                new_key_retry_same_receipt=changed_key.json() == canonical,
                changed_payload_conflict=conflict.status_code == 409 and conflict.json().get('detail') == 'idempotency_payload_conflict',
                commit_query_same_receipt=commit.json()['receipt'] == canonical,
                visual_fact_frozen=fact(final) == first_fact,
                frame_audit_frozen=audit['frames'] == first_audit['frames'],
                no_people_no_confirmed_reps=final['snapshot']['completed'] == 0,
                overloaded=diagnostics['counters']['latest_replaced'] > 0,
                queue_capacity_preserved=diagnostics['max_retained_queue_depth'] <= 1,
                no_worker_failure=not diagnostics['consumers']['frame_failure'],
                no_input_failure=diagnostics['counters']['input_failed'] == 0,
                all_frame_responses_expected=all(row['status'] in (200, 409) for row in responses),
                all_declared_frames_attempted=len(responses) == WORKLOAD['frames']+1,
                http_accepted_sequences_match_disk=sorted(row['seq'] for row in responses if row['status'] == 200)
                                                   == [row['seq'] for row in audit['frames']],
                all_pause_resume_persisted=all(sum(row['kind'] == key for row in audit['audit']) ==
                                               WORKLOAD['pause_resume_pairs'] for key in ('pause', 'resume')),
                feedback_retry_once=feedback.json() == feedback_retry.json() and final['feedback_revision'] == 1,
                unknown_feedback_not_filled=feedback.json()['pain'] is None and feedback.json()['fatigue'] is None)
            runtime = service.runtimes[sid]
            with runtime.telemetry.lock:
                stages = {key: list(runtime.telemetry.samples[key]) for key in
                          ('decode_ms', 'inference_ms', 'pose_roundtrip_ms', 'pose_result_age_ms', 'result_age_ms')}
            details.update(final_fact=fact(final), frame_audit=audit, final_diagnostics=diagnostics,
                           finish_receipts=receipts, reconciliation=checks, raw_stage_samples_ms=stages)
            return dict(http={key: percentiles(values) for key, values in timings.items()},
                        frame_status_codes=dict(Counter(str(row['status']) for row in responses)),
                        reconciliation=checks, final_commit=canonical, diagnostics=diagnostics,
                        at_finish=details['at_finish']['backlog'],
                        producer_done_at_finish=details['producer_done_at_finish'],
                        producer=details['producer'], clinical_accuracy=None,
                        load_http={key: percentiles(values[warm_http_offsets[key]:]) for key, values in timings.items()},
                        cold_first={key: values[0] if values else None for key, values in stages.items()},
                        warm_stages={key: percentiles(values[1:]) for key, values in stages.items()})
        finally:
            stop_observer.set()
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


def benchmark_session_load():
    import yaml
    from fastapi import FastAPI, HTTPException, Request
    from PIL import Image
    from mobile_rehab.rehab_v2.api import install_rehab_v2
    from .inventory import doctor

    run = paths()['run']/('session-load-'+uuid4().hex[:8])
    run.mkdir()
    source_paths = ['tools/rehab_ml/session_load_audit.py', 'tools/rehab_ml/cli.py',
                    'mobile_rehab/rehab_v2/api.py', 'mobile_rehab/rehab_v2/service.py',
                    'mobile_rehab/rehab_v2/pose_worker.py', 'mobile_rehab/rehab_v2/owned_worker.py',
                    'rehab_codex_single_camera_v2_1/app/rehab_v2/sessions.py',
                    'configs/rehab_ml/backend.yaml',
                    'rehab_codex_single_camera_v2_1/assets/models/yolo11n-pose.pt']
    sources = {path: file_hash(ROOT/path) for path in source_paths}
    budgets = yaml.safe_load((ROOT/'configs/rehab_ml/backend.yaml').read_text(encoding='utf-8'))['performance_predeclared']
    declared = dict(workload=WORKLOAD, budgets=budgets, source_sha256=sources, environment=doctor())
    write_json(run/'predeclared.json', declared)
    details, result, service = {}, {}, None
    try:
        def plan(owner, request):
            return dict(plan_id='TEST-load-plan', plan_revision=1, entry_key='shoulder_abduction:left',
                        reference=dict(record_origin='manual', fixture=True),
                        plan=dict(exercise_id='shoulder_abduction', side='left', target_reps=1,
                                  target_sets=1, submode='training'))
        @asynccontextmanager
        async def lifespan(app):
            try:
                yield
            finally:
                app.state.rehab_v2.close()
        app = FastAPI(lifespan=lifespan)
        def owner(request: Request):
            if request.cookies.get('test-load-auth') != 'TEST-owned':
                raise HTTPException(401, 'authentication_required')
            return 'TEST-load-owner'
        async def small_json(request):
            body = await request.body()
            if len(body) > 4096:
                raise HTTPException(413)
            return json.loads(body)
        buffer = BytesIO()
        Image.new('RGB', WORKLOAD['image_size'], 'white').save(buffer, format='JPEG')
        encoded = buffer.getvalue()
        details['jpeg_sha256'] = hashlib.sha256(encoded).hexdigest()
        database = run/'isolated.sqlite3'
        service = install_rehab_v2(app, database, owner, small_json, plan)
        async def run_http():
            async with app.router.lifespan_context(app):
                return await exercise(app, service, encoded, details)
        result = asyncio.run(run_http())
        # A fresh read-only connection proves the fact is on disk, not solely
        # in the owning storage thread's object or the response cache.
        with closing(sqlite3.connect(database.as_uri()+'?mode=ro', uri=True)) as connection:
            counts = {table: connection.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]
                      for table in ('rehab_v2_sessions', 'rehab_v2_plan_contributions')}
            persisted = json.loads(connection.execute('SELECT payload FROM rehab_v2_sessions').fetchone()[0])
            contribution = json.loads(connection.execute('SELECT payload FROM rehab_v2_plan_contributions').fetchone()[0])
        result['reconciliation']['checks']['independent_reopen_same_visual_fact'] = (
            persisted['snapshot'] == details['final_fact']['snapshot'] and
            persisted['canonical_commit'] == result['final_commit'] and
            contribution == details['final_fact']['plan_contribution'] and all(value == 1 for value in counts.values()))
        result['disk_row_counts'] = counts
    except Exception as error:
        result['error'] = dict(type=type(error).__name__, message=str(error))
    finally:
        if service is not None and not service.resources_released:
            service.close()
        result['shutdown'] = None if service is None else dict(
            resources_released=service.resources_released,
            pose_process_retained=service.inference_worker.process is not None,
            frame_consumer_alive=service.worker.is_alive(), report_consumer_alive=service.report_worker.is_alive(),
            finish_consumer_alive=service.finish_worker.is_alive())
    sources_after = {path: file_hash(ROOT/path) for path in source_paths}
    result.update(run_id=run.name, predeclared=declared, clinical_accuracy=None,
                  source_sha256_after=sources_after, source_unchanged=sources == sources_after,
                  exclusions=['phone', 'camera', 'socket_network', 'target_motion_accuracy',
                              'multiple_active_sessions', 'long_duration_soak', 'candidate_tcn_runtime'],
                  memory_sampling='periodic_RSS_observations_not_peak_measurement')
    checks = result.get('reconciliation', {}).get('checks', {})
    shutdown = result['shutdown']
    result['engineering_invariants_passed'] = bool(checks) and all(checks.values()) and result['source_unchanged'] and bool(
        shutdown and shutdown['resources_released'] and not any(shutdown[key] for key in
        ('pose_process_retained', 'frame_consumer_alive', 'report_consumer_alive', 'finish_consumer_alive')))
    result['control_budget'] = {key: dict(p95_ms=result.get('http', {}).get(key, {}).get('p95_ms'),
        budget_ms=budgets['control_response_p95_ms']) for key in ('pause', 'resume', 'finish')}
    result['control_budget_met'] = all(row['p95_ms'] is not None and row['p95_ms'] <= row['budget_ms']
                                     for row in result['control_budget'].values())
    result['passed'] = result['engineering_invariants_passed'] and result['control_budget_met'] and 'error' not in result
    detail_path = run/'details.json'
    write_json(detail_path, details)
    result['raw_details'] = dict(path=str(detail_path), sha256=file_hash(detail_path))
    output = run/'summary.json'
    write_json(output, result)
    result['raw_summary'] = dict(path=str(output), sha256=file_hash(output))
    write_json(ROOT/'reports/rehab_backend/session_load.json', result)
    return result
