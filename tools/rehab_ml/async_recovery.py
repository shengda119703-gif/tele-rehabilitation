"""Exact-owned host kills at three asynchronous finish persistence windows.

TEST replay proves engineering invariants, not camera/clinical accuracy. Public
finish/queries use the original ASGI routes. No socket, patient store, model
child or camera is opened. Every child handle is retained through actual exit.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'rehab_codex_single_camera_v2_1'))
from tools.rehab_ml.common import file_hash, paths, write_json

CASES = ('accepted_before_commit', 'uncommitted_finalize', 'committed_before_http_reply')
OWNER = 'TEST-async-crash-owner'
CREATE = dict(idempotency_key='TEST-create', consent=True)
FINISH = dict(idempotency_key='TEST-finish', expected_revision=0, reason='user_stopped')
WORKLOAD = dict(version='rehab-async-recovery-1', cases=list(CASES), deadline_s=30,
    kill_wait_s=5, fixture='TEST_internal_geometry_one_confirmed_and_one_half_rep',
    pending_input='one_TEST_internal_accepted_evidence_row_not_native_inflight_inference',
    transport='original_in_process_ASGI_routes_not_socket_network',
    native_pose_or_report_child=False, real_human_reference=False)
SOURCES = ('tools/rehab_ml/async_recovery.py', 'mobile_rehab/rehab_v2/api.py',
    'mobile_rehab/rehab_v2/service.py', 'rehab_codex_single_camera_v2_1/app/rehab_v2/sessions.py',
    'rehab_codex_single_camera_v2_1/app/rehab_v2/rounds.py',
    'rehab_codex_single_camera_v2_1/app/rehab_v2/engine.py',
    'rehab_codex_single_camera_v2_1/app/rehab_v2/progress.py',
    'rehab_codex_single_camera_v2_1/app/storage.py')


def frozen_plan(owner, request):
    return dict(plan_id='TEST-crash-plan', plan_revision=1, entry_key='shoulder_abduction:left',
        reference=dict(owner=owner, fixture=True, record_origin='manual'),
        plan=dict(exercise_id='shoulder_abduction', side='left', submode='training',
                  target_reps=2, target_sets=1, target_angle_deg=60.))


def test_host(database, *, inference=None):
    from fastapi import FastAPI, HTTPException
    from mobile_rehab.rehab_v2 import api
    from mobile_rehab.rehab_v2.service import SessionService
    app = FastAPI()
    def owner(req):
        uid = req.cookies.get('TEST-auth')
        if uid not in (OWNER, 'TEST-other-owner'):
            raise HTTPException(401)
        return uid
    async def small_json(req):
        return json.loads(await req.body())
    # Constructor injection is confined to this TEST process, not a public
    # keypoint endpoint or a change to the product's installed/default service.
    original = api.SessionService
    def isolated(*args, **kwargs):
        return SessionService(*args, **kwargs, internal_replay=True, inference_provider=inference)
    try:
        api.SessionService = isolated
        service = api.install_rehab_v2(app, database, owner, small_json, frozen_plan)
    finally:
        api.SessionService = original
    # A pending report remains durable. Disable only this TEST consumer before
    # finalization so a native report child cannot outlive a forced host kill.
    service.report_stop.set()
    service.report_worker.join(2.)
    if service.report_worker.is_alive():
        service.close(graceful=False)
        raise RuntimeError('TEST_report_consumer_exit_unconfirmed')
    return app, service


def read_database(database):
    with closing(sqlite3.connect(database.as_uri()+'?mode=ro', uri=True, timeout=1.)) as conn:
        conn.execute('BEGIN')
        rows = conn.execute('SELECT payload FROM rehab_v2_sessions').fetchall()
        if len(rows) != 1:
            raise RuntimeError('one_isolated_session_required')
        item = json.loads(rows[0][0])
        sid = item['session_id']
        return dict(item=item, repetitions=[json.loads(row[0]) for row in conn.execute(
            'SELECT payload FROM rehab_v2_repetitions WHERE session_id=? ORDER BY rep_index', (sid,))],
            frames=[dict(seq=row[0], status=row[1], reason=row[2]) for row in conn.execute(
                'SELECT seq,status,reason FROM rehab_v2_frames WHERE session_id=? ORDER BY seq', (sid,))],
            operations=[dict(key=row[0], receipt=json.loads(row[1])) for row in conn.execute(
                "SELECT operation_key,receipt FROM rehab_v2_operations WHERE session_id=? AND operation='finish'", (sid,))],
            contributions=[json.loads(row[0]) for row in conn.execute(
                'SELECT payload FROM rehab_v2_plan_contributions WHERE session_id=?', (sid,))],
            audit=[row[0] for row in conn.execute('SELECT kind FROM rehab_v2_audit WHERE session_id=?', (sid,))],
            feedback_rows=conn.execute('SELECT COUNT(*) FROM rehab_v2_feedback WHERE session_id=?', (sid,)).fetchone()[0])


def validate_child_target(database, barrier, case):
    database, barrier = Path(database).resolve(), Path(barrier).resolve()
    if (case not in CASES or database.exists() or not database.is_relative_to(paths()['run'])
            or database.name != 'TEST-host.sqlite3' or barrier.parent != database.parent
            or barrier.name != 'TEST-barrier.json' or barrier.exists()):
        raise ValueError('new_isolated_TEST_database_and_barrier_required')
    return database, barrier


async def child_probe(database, barrier, case):
    import httpx
    from app.domain import digest
    from app.rehab_v2.evidence import EvidenceFrame, MetricEvidence
    release = threading.Event()
    http_accepted = threading.Event()
    app, service = test_host(database)
    proof = dict(case=case, pid=os.getpid(), workload=WORKLOAD,
                 python_executable=sys.executable, base_executable=sys._base_executable)
    def emit(window, **extra):
        proof.update(window=window, **extra,
            no_native_pose_child=service.inference_worker.process is None,
            no_native_report_child=service.report_executor.process is None,
            report_consumer_exited=not service.report_worker.is_alive())
        write_json(barrier, proof)
    original_finish = service._finish
    def held_finish(*args):
        if not http_accepted.wait(60.):
            raise RuntimeError('TEST_HTTP_acceptance_gate_expired')
        if case == 'accepted_before_commit' and not release.wait(60.):
            raise RuntimeError('TEST_precommit_gate_expired')
        return original_finish(*args)
    service._finish = held_finish
    if case == 'uncommitted_finalize':
        original_save = service.repository._save
        def held_save(conn, item):
            original_save(conn, item)
            if item['persistence_state'] == 'finalized':
                # Writes exist on the writer connection; the transaction has
                # not returned/committed. Parent reads the prior durable view.
                emit('inside_uncommitted_final_transaction',
                     writer_transaction_open=conn.in_transaction,
                     transaction_receipt=item['canonical_commit'])
                if not release.wait(60.):
                    raise RuntimeError('TEST_transaction_gate_expired')
        service.repository._save = held_save
    if case == 'committed_before_http_reply':
        original_request = service.request_finish
        def lost_reply(*args):
            result = original_request(*args)
            http_accepted.set()
            deadline = time.monotonic()+20.
            while time.monotonic() < deadline:
                receipt = service.commit(OWNER, proof['session_id'])['receipt']
                if receipt:
                    emit('committed_without_HTTP_finish_response', canonical=receipt)
                    if not release.wait(60.):
                        raise RuntimeError('TEST_lost_reply_gate_expired')
                    return result
                time.sleep(.005)
            raise RuntimeError('TEST_final_commit_not_observed')
        service.request_finish = lost_reply
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                base_url='http://TEST-owned', cookies={'TEST-auth': OWNER}) as client:
            response = await client.post('/api/rehab/v2/sessions', json=CREATE)
            response.raise_for_status()
            item = response.json()
            sid = item['session_id']
            endpoint = '/api/rehab/v2/sessions/'+sid
            proof['session_id'] = sid
            runtime = service.runtimes[sid]
            seq, stamp = 0, 0.
            for value, count in ((0., 30), (70., 10), (0., 10), (70., 6)):
                for _ in range(count):
                    seq, stamp = seq+1, stamp+.05
                    metric = MetricEvidence(value, 'degree', True, None, 'observed', stamp, stamp, 0.,
                                            tuple(runtime.engine.spec['required_joints']))
                    frame = EvidenceFrame(seq, stamp, item['source_epoch'], 'TEST-one', 'coco17-v1',
                        'TEST-not-a-pose-model', (640, 480), {'raise_deg': metric}, 'VALID')
                    service.submit_evidence(OWNER, sid, 'TEST-replay-'+str(seq), frame)
            before = service.get(OWNER, sid)
            if before['snapshot']['completed'] != 1 or before['snapshot']['current'] is None:
                raise RuntimeError('TEST_confirmed_rep_and_half_required')
            proof['checkpoint'] = before['snapshot']
            # The replay host deliberately refuses camera frames. Stage one
            # accepted-but-unprocessed TEST evidence row through its original
            # repository, without weakening that public input boundary. This
            # is a persistence fixture, not proof of live native inference.
            service.repository.accept_frame(OWNER, sid, 'TEST-pending', seq+1,
                digest(dict(fixture='TEST_pending_internal_evidence', seq=seq+1)))
            proof['pending_seq'] = seq+1
            response = await client.post(endpoint+'/finish', json=FINISH)
            proof['finish_http_response'] = dict(status=response.status_code, payload=response.json())
            if response.status_code != 202 or response.json().get('status') != 'finishing':
                raise RuntimeError('durable_HTTP_202_required')
            http_accepted.set()
            if case == 'accepted_before_commit':
                emit('HTTP_202_before_finalization')
            await asyncio.to_thread(release.wait, 60.)
            raise RuntimeError('TEST_parent_did_not_kill_host')
    finally:
        release.set()
        service.close(graceful=False)


async def recover_http(database, before):
    import httpx
    from app.domain import digest
    app, service = test_host(database)
    sid = before['item']['session_id']
    endpoint = '/api/rehab/v2/sessions/'+sid
    checks = {}
    details = {}
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                base_url='http://TEST-owned', cookies={'TEST-auth': OWNER}) as client:
            response = await client.get(endpoint)
            response.raise_for_status()
            item = response.json()
            canonical = item['canonical_commit']
            checks['restart_ended_finalized'] = item['run_state'] == 'ended' and item['persistence_state'] == 'finalized'
            was_final = before['item']['persistence_state'] == 'finalized'
            checks['end_reason_policy'] = item['end_reason'] == ('user_stopped' if was_final else 'interrupted')
            checks['exact_prior_commit_or_new_recovery_commit'] = (canonical == before['item']['canonical_commit'] if was_final
                else bool(canonical and canonical['status'] == 'finalized'))
            checks['confirmed_rep_survives_without_half_resume'] = item['snapshot']['completed'] == 1 and item['snapshot']['current'] is None
            checks['one_confirmed_and_one_unassessable'] = (
                sum(row['completion_status'] == 'COMPLETE' for row in item['snapshot']['repetitions']) == 1 and
                sum(row['completion_status'] == 'UNASSESSABLE' for row in item['snapshot']['repetitions']) == 1)
            checks['confirmed_rep_unchanged'] = item['snapshot']['repetitions'][0] == before['repetitions'][0]
            checks['visual_digest_matches_snapshot'] = canonical['visual_snapshot_digest'] == digest(item['snapshot'])
            checks['missing_feedback_not_zero'] = item['feedback_status'] == 'missing' and item['feedback_revision'] == 0 and not item.get('latest_feedback')
            retry = await client.post(endpoint+'/finish', json=FINISH)
            alias = await client.post(endpoint+'/finish', json=dict(FINISH, idempotency_key='TEST-alias', expected_revision=999))
            checks['same_and_new_key_return_original_commit'] = retry.status_code == alias.status_code == 200 and retry.json() == alias.json() == canonical
            checks['same_key_changed_payload_conflicts'] = (await client.post(endpoint+'/finish', json=dict(FINISH, reason='completed'))).status_code == 409
            checks['finalized_cannot_resume'] = (await client.post(endpoint+'/resume', json=dict(idempotency_key='TEST-resume', expected_revision=item['revision']))).status_code == 409
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                    base_url='http://TEST-owned', cookies={'TEST-auth': 'TEST-other-owner'}) as foreign:
                checks['foreign_owner_cannot_read'] = (await foreign.get(endpoint)).status_code == 404
            checks['create_retry_returns_same_session'] = (await client.post('/api/rehab/v2/sessions', json=CREATE)).json()['session_id'] == sid
            feedback = dict(idempotency_key='TEST-feedback', expected_revision=0,
                            feedback=dict(pain=None, fatigue=None, reason='completed'))
            response = await client.post(endpoint+'/feedback', json=feedback)
            again = await client.post(endpoint+'/feedback', json=feedback)
            checks['null_feedback_retry_once'] = response.status_code == again.status_code == 200 and response.json() == again.json() and response.json()['pain'] is None and response.json()['fatigue'] is None
            checks['commit_immutable_after_retries_feedback'] = (await client.get(endpoint+'/commit')).json()['receipt'] == canonical
            details.update(item_before_feedback=item, feedback=response.json(), recovered_sessions=service.recovered)
    finally:
        service.close(graceful=False)
    saved = read_database(database)
    checks['one_fact_one_contribution'] = len(saved['contributions']) == 1
    checks['materialized_repetitions_match_snapshot'] = saved['repetitions'] == saved['item']['snapshot']['repetitions']
    checks['one_feedback_row'] = saved['feedback_rows'] == 1
    checks['all_finish_receipts_canonical'] = len(saved['operations']) == 2 and all(row['receipt'] == saved['item']['canonical_commit'] for row in saved['operations'])
    pending = [row for row in saved['frames'] if row['seq'] == max(row['seq'] for row in saved['frames'])]
    checks['pending_frame_explicitly_unprocessed'] = len(pending) == 1 and pending[0]['status'] == 'unprocessed' and pending[0]['reason'] == ('finish_boundary_timeout' if was_final else 'process_restart')
    checks['no_accepted_frame_left'] = all(row['status'] != 'accepted' for row in saved['frames'])
    checks['one_terminal_transition'] = saved['audit'].count('finalize')+saved['audit'].count('restart_recovery') == 1
    # A second independent owner/Storage lifecycle must not re-terminalize.
    second_app, second = test_host(database)
    try:
        checks['second_restart_no_recovery'] = second.recovered == []
        checks['second_restart_same_fact'] = second.repository.get(OWNER, sid)['canonical_commit'] == saved['item']['canonical_commit']
    finally:
        second.close(graceful=False)
    checks['second_restart_database_unchanged'] = read_database(database) == saved
    details['database_after_recovery'] = saved
    return checks, details


def audit_async_recovery():
    run = paths()['run']/('async-recovery-'+uuid4().hex[:8])
    run.mkdir()
    hashes = {name: file_hash(ROOT/name) for name in SOURCES}
    result = dict(run_id=run.name, predeclared=WORKLOAD, source_sha256=hashes,
                  cases=[], clinical_accuracy=None)
    write_json(run/'predeclared.json', result)
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    executable = sys.executable
    if sys.platform == 'win32' and os.path.normcase(sys.executable) != os.path.normcase(sys._base_executable):
        # Match the installed CPython multiprocessing launcher: bypass the
        # venv redirector but preserve venv initialization. Popen now owns the
        # actual interpreter, not a redirector with a different child PID.
        executable = sys._base_executable
        environment['__PYVENV_LAUNCHER__'] = sys.executable
    for case in CASES:
        folder = run/case
        folder.mkdir()
        database, barrier = folder/'TEST-host.sqlite3', folder/'TEST-barrier.json'
        record = dict(case=case, checks={}, database=str(database))
        result['cases'].append(record)
        process = None
        started = time.monotonic()
        try:
            with (folder/'child.txt').open('w', encoding='utf-8') as log:
                process = subprocess.Popen([executable, '-X', 'utf8', '-B', str(Path(__file__).resolve()),
                    '--probe-child', '--database', str(database), '--barrier', str(barrier), '--case', case],
                    cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT)
                deadline = time.monotonic()+WORKLOAD['deadline_s']
                while not barrier.exists():
                    if process.poll() is not None:
                        raise RuntimeError('owned_host_exited_before_barrier')
                    if time.monotonic() >= deadline:
                        raise TimeoutError('owned_host_barrier_deadline')
                    time.sleep(.005)
                proof = json.loads(barrier.read_text(encoding='utf-8'))
                if process.poll() is not None or proof['pid'] != process.pid:
                    raise RuntimeError('owned_host_handle_not_live_at_barrier:'+str((process.pid, proof['pid'], process.poll())))
                if case == 'uncommitted_finalize' and not proof.get('writer_transaction_open'):
                    raise RuntimeError('TEST_uncommitted_writer_transaction_not_open')
                before = read_database(database)
                record['before_kill'] = before
                record['barrier_proof'] = proof
                record['checks']['exact_owned_process_live'] = True
                record['checks']['no_native_child_at_barrier'] = all(proof[key] for key in
                    ('no_native_pose_child', 'no_native_report_child', 'report_consumer_exited'))
                should_final = case == 'committed_before_http_reply'
                record['checks']['independent_database_matches_window'] = (before['item']['persistence_state'] == ('finalized' if should_final else 'draft') and
                    before['item']['run_state'] == ('ended' if should_final else 'finishing') and
                    len(before['contributions']) == (1 if should_final else 0))
                record['checks']['finish_HTTP_response_boundary'] = ('finish_http_response' not in proof if should_final
                    else proof.get('finish_http_response', {}).get('status') == 202)
                record['checks']['pending_operation_or_canonical'] = len(before['operations']) == 1 and before['operations'][0]['receipt']['status'] == ('finalized' if should_final else 'finishing')
                record['checks']['checkpoint_has_confirmed_rep'] = before['item']['snapshot']['completed'] == 1
                process.kill()  # Only this still-owned Popen handle, never a stored PID.
                process.wait(WORKLOAD['kill_wait_s'])
                record['exit_code'] = process.returncode
                record['checks']['actual_forced_exit_confirmed'] = process.returncode is not None and process.returncode != 0
            checks, details = asyncio.run(recover_http(database, before))
            record['checks'].update(checks)
            write_json(folder/'details.json', details)
            record['details'] = dict(path=str(folder/'details.json'), sha256=file_hash(folder/'details.json'))
        except Exception as error:
            record['error'] = dict(type=type(error).__name__, message=str(error))
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                process.wait(WORKLOAD['kill_wait_s'])
            record['actual_exit_confirmed'] = process is not None and process.poll() is not None
            record['elapsed_s'] = time.monotonic()-started
            if (folder/'child.txt').exists():
                record['log'] = dict(path=str(folder/'child.txt'), sha256=file_hash(folder/'child.txt'))
            record['passed'] = not record.get('error') and record['actual_exit_confirmed'] and all(record['checks'].values())
            write_json(run/'summary.json', result)
    result['source_unchanged'] = hashes == {name: file_hash(ROOT/name) for name in SOURCES}
    result['passed'] = len(result['cases']) == len(CASES) and result['source_unchanged'] and all(row['passed'] for row in result['cases'])
    write_json(run/'summary.json', result)
    result['raw_summary'] = dict(path=str(run/'summary.json'), sha256=file_hash(run/'summary.json'))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe-child', action='store_true')
    parser.add_argument('--database', type=Path)
    parser.add_argument('--barrier', type=Path)
    parser.add_argument('--case', choices=CASES)
    args = parser.parse_args(argv)
    if args.probe_child:
        if not args.database or not args.barrier or not args.case:
            parser.error('child database, barrier and case required')
        database, barrier = validate_child_target(args.database, args.barrier, args.case)
        asyncio.run(child_probe(database, barrier, args.case))
        return 1  # A normally returning probe is not evidence of a forced crash.
    if args.database or args.barrier or args.case:
        parser.error('audit creates its own new TEST outputs')
    result = audit_async_recovery()
    compact = {key: value for key, value in result.items() if key != 'cases'}
    compact['cases'] = [{key: value for key, value in row.items()
                        if key not in ('before_kill', 'barrier_proof')} for row in result['cases']]
    print(json.dumps(compact, ensure_ascii=False, allow_nan=False))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
