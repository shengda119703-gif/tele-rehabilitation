"""Real loopback HTTP loss/reconnect and a second owned server lifecycle.

Only fresh TEST stores and an OS-selected 127.0.0.1 port are used. The original
host, authentication, v2 routes, YOLO and report process remain unchanged.
Response gates are confined to this audit child, never installed in product.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import struct
import subprocess
import sys
import threading
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'rehab_codex_single_camera_v2_1'))
from tools.rehab_ml.common import file_hash, paths, read_json, write_json

BASE = '/api/rehab/v2/sessions'
WORKLOAD = dict(version='rehab-socket-recovery-1', host='127.0.0.1', port='OS_selected',
    stages=['create_reply_loss', 'finish_reply_loss', 'forced_host_exit_and_actual_server_restart'],
    deadline_s=45, host_exit_s=5, child_exit_s=2, socket_timeout_s=5,
    transport='actual_TCP_HTTP_uvicorn_not_ASGITransport', inference='original_owned_YOLO',
    fixture='TEST_legacy_assessment_for_plan_and_white_JPEG_not_human_reference',
    phone_or_LAN_or_TLS=False, clinical_accuracy=None)
SOURCES = ('tools/rehab_ml/socket_recovery_audit.py', 'mobile_rehab/server.py',
    'mobile_rehab/rehab_v2/api.py', 'mobile_rehab/rehab_v2/service.py',
    'mobile_rehab/rehab_v2/owned_worker.py', 'mobile_rehab/rehab_v2/host_lifetime.py',
    'mobile_rehab/rehab_v2/pose_worker.py', 'mobile_rehab/rehab_v2/report_worker.py',
    'rehab_codex_single_camera_v2_1/app/rehab_v2/sessions.py',
    'rehab_codex_single_camera_v2_1/app/storage.py',
    'rehab_codex_single_camera_v2_1/assets/models/yolo11n-pose.pt')


def validated_run(run, index):
    run = Path(run).resolve()
    if (index not in (0, 1) or not run.is_relative_to(paths()['run'])
            or not re.fullmatch(r'socket-recovery-[0-9a-f]{8}', run.name)
            or not (run/'predeclared.json').is_file()
            or (run/f'TEST-ready-{index}.json').exists()):
        raise ValueError('fresh_declared_socket_TEST_run_required')
    return run


def until(function, description, *, process=None, budget=None):
    deadline = time.monotonic()+(WORKLOAD['deadline_s'] if budget is None else budget)
    while True:
        if process is not None and process.poll() is not None:
            raise RuntimeError('owned_host_exited_before_'+description)
        result = function()
        if result:
            return result
        if time.monotonic() >= deadline:
            raise RuntimeError('deadline_'+description)
        time.sleep(.01)


def server_child(run, index):
    import uvicorn
    from mobile_rehab.server import create_app
    run = validated_run(run, index)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if os.name == 'nt':
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    listener.bind((WORKLOAD['host'], 0))  # Reserve before opening any store.
    listener.listen(128)
    app = create_app(run/'TEST-server-data', pair_key='TEST-socket-key',
                     runner=lambda item: None, rehab_v2=True)
    service = app.state.rehab_v2
    if index == 0:
        original_create, original_finish = service.create, service.request_finish

        def response_gate(name, value):
            write_json(run/f'TEST-{name}-gate.json', dict(pid=os.getpid(), value=value))
            until(lambda: (run/f'TEST-{name}-release.json').is_file(), name+'_release')

        def create(owner, request):
            result = original_create(owner, request)
            if request.get('idempotency_key') == 'TEST-loss-create' and not (run/'TEST-create-gate.json').exists():
                response_gate('create', dict(session_id=result['session_id']))
            return result

        def finish(owner, sid, request):
            result = original_finish(owner, sid, request)
            if request.get('idempotency_key') == 'TEST-loss-finish' and not (run/'TEST-finish-gate.json').exists():
                canonical = until(lambda: service.commit(owner, sid)['receipt'], 'durable_finish')
                response_gate('finish', canonical)
            return result
        service.create, service.request_finish = create, finish
    server = uvicorn.Server(uvicorn.Config(app, host=WORKLOAD['host'], port=0,
        access_log=False, log_level='warning', timeout_graceful_shutdown=5))
    app.state.shutdown = lambda: setattr(server, 'should_exit', True)
    monitor_stop = threading.Event()

    def inspect():
        def child(worker):
            process = worker.process
            return dict(pid=process.pid, alive=process.is_alive(), warm=worker.warm) if process is not None else None
        return dict(host_pid=os.getpid(), pose=child(service.inference_worker),
                    report=child(service.report_executor))

    def monitor():
        while not monitor_stop.wait(.01):
            if server.started and not (run/f'TEST-ready-{index}.json').exists():
                write_json(run/f'TEST-ready-{index}.json', dict(pid=os.getpid(),
                    port=listener.getsockname()[1], host=WORKLOAD['host'], actual_server_started=True))
            if (run/f'TEST-inspect-{index}.json').is_file() and not (run/f'TEST-workers-{index}.json').exists():
                write_json(run/f'TEST-workers-{index}.json', inspect())
            if (run/f'TEST-stop-{index}.json').is_file():
                server.should_exit = True
    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    try:
        server.run(sockets=[listener])
    finally:
        monitor_stop.set()
        thread.join(1.)
        listener.close()
        write_json(run/f'TEST-shutdown-{index}.json', dict(pid=os.getpid(),
            resources_released=service.resources_released,
            pose_retained=service.inference_worker.process is not None,
            report_retained=service.report_executor.process is not None,
            consumers_alive=[service.worker.is_alive(), service.finish_worker.is_alive(), service.report_worker.is_alive()]))


class OwnedHost:
    def __init__(self, run, index):
        self.run, self.index, self.handles = run, index, []
        self.log = run/f'TEST-server-{index}.txt'
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', __PYVENV_LAUNCHER__=sys.executable)
        self.output = self.log.open('w', encoding='utf-8')
        try:
            self.process = subprocess.Popen([sys._base_executable, '-X', 'utf8', '-B', __file__,
                '--child-run', str(run), '--child-index', str(index)], cwd=ROOT, env=environment,
                stdout=self.output, stderr=subprocess.STDOUT,
                creationflags=0x08000000 if os.name == 'nt' else 0)
        except BaseException:
            self.output.close()
            raise

    def ready(self):
        name = self.run/f'TEST-ready-{self.index}.json'
        result = until(lambda: read_json(name) if name.exists() else None, 'server_ready', process=self.process)
        if result['pid'] != self.process.pid or result['host'] != '127.0.0.1' or not result['actual_server_started']:
            raise RuntimeError('actual_owned_server_identity_required')
        return result

    def capture_workers(self):
        from tools.rehab_ml.native_parent_audit import ExactChildHandle
        write_json(self.run/f'TEST-inspect-{self.index}.json', dict(inspect=True))
        name = self.run/f'TEST-workers-{self.index}.json'
        result = until(lambda: read_json(name) if name.exists() else None, 'owned_workers', process=self.process)
        if result['host_pid'] != self.process.pid or self.process.poll() is not None:
            raise RuntimeError('live_exact_host_required_before_child_capture')
        for role in ('pose', 'report'):
            value = result[role]
            if value and value['alive']:
                self.handles.append(ExactChildHandle(value['pid']))
        return result

    def close(self, *, forced=False):
        cleanup_required = False
        if self.process.poll() is None:
            if forced:
                self.process.kill()
            else:
                write_json(self.run/f'TEST-stop-{self.index}.json', dict(stop=True))
            try:
                self.process.wait(WORKLOAD['host_exit_s'])
            except subprocess.TimeoutExpired:
                cleanup_required = True
                self.process.kill()
                self.process.wait(WORKLOAD['host_exit_s'])
        native_exits = []
        for handle in self.handles:
            exited = handle.exited(WORKLOAD['child_exit_s'])
            native_exits.append(exited)
            if not exited:
                cleanup_required = True
                handle.cleanup()
            handle.close()
        self.handles.clear()
        self.output.close()
        return dict(actual_host_exit_confirmed=self.process.poll() is not None,
            host_exit_code=self.process.returncode, forced_requested=forced,
            fallback_cleanup_required=cleanup_required, captured_native_exits=native_exits,
            log=dict(path=str(self.log), sha256=file_hash(self.log)))


def abort_after_gate(host, cookie, endpoint, payload, gate):
    """Transmit on a real socket, prove the durable gate, then RST without recv."""
    body = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    request = (f'POST {endpoint} HTTP/1.1\r\nHost: 127.0.0.1:{host.port}\r\n'
        'X-Rehab-Client: mobile-v1\r\nContent-Type: application/json\r\n'
        f'Cookie: rehab_device={cookie}\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n').encode('ascii')+body
    with socket.create_connection(('127.0.0.1', host.port), timeout=WORKLOAD['socket_timeout_s']) as connection:
        connection.sendall(request)
        marker = host.run/f'TEST-{gate}-gate.json'
        proof = until(lambda: read_json(marker) if marker.exists() else None, gate+'_committed_gate', process=host.process)
        if proof['pid'] != host.process.pid:
            raise RuntimeError('response_gate_not_owned_host')
        # Windows linger is two unsigned shorts; POSIX uses two ints.
        connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER,
                              struct.pack('HH' if os.name == 'nt' else 'ii', 1, 0))
    write_json(host.run/f'TEST-{gate}-release.json', dict(response_not_read=True, socket_closed=True))
    return proof['value']


def seed_plan(run, uid):
    """Same original-schema TEST fixture as host integration tests, not truth."""
    from app.storage import Storage
    from app.assessment import build_body_profile
    from app.automatic_plans import generate_proposal, create_automatic_plan
    from mobile_rehab.core import exercise_spec
    if not re.fullmatch('[a-f0-9]{32}', uid):
        raise ValueError('authenticated_isolated_uid_required')
    spec, now = exercise_spec('shoulder_abduction'), datetime.now(timezone.utc)
    store = Storage(run/'TEST-server-data'/'jobs'/uid/'assessments.sqlite3')
    try:
        store.save_session(dict(id='TEST-live-assessment', scene_id='rehab', participant_id=uid,
            source_kind='LIVE_CAMERA', usage_context='SELF_USE', submode='assessment', exercise_id='shoulder_abduction',
            side='left', status='FINISHED', start_utc=(now-timedelta(minutes=1)).isoformat(), end_utc=now.isoformat(),
            measurement_contract=spec['measurement_contract'],
            summary=dict(primary_metric=spec['metric'], valid_ratio=.9, completed=3,
                         motion_range=dict(min_deg=5., max_deg=65., range_deg=60.))))
        sessions = store.list_sessions()
        profile = build_body_profile(sessions, uid, 'LIVE_CAMERA', 'SELF_USE')
        plan = create_automatic_plan(generate_proposal(profile, sessions), dict(
            general_activity_ok=True, standing_support_ok=True, companion_present=False))
        return store.save_training_plan(plan, expected_revision=0)
    finally:
        store.close()


def facts(database):
    from tools.rehab_ml.session_load_audit import fact
    with closing(sqlite3.connect(database.as_uri()+'?mode=ro', uri=True)) as conn:
        conn.execute('BEGIN')
        result = {}
        for sid, payload in conn.execute('SELECT id,payload FROM rehab_v2_sessions'):
            item = json.loads(payload)
            contributions = conn.execute('SELECT payload FROM rehab_v2_plan_contributions WHERE session_id=?', (sid,)).fetchall()
            item['plan_contribution'] = json.loads(contributions[0][0]) if contributions else None
            result[sid] = dict(fact=fact(item), contributions=len(contributions),
                feedback_rows=conn.execute('SELECT COUNT(*) FROM rehab_v2_feedback WHERE session_id=?', (sid,)).fetchone()[0])
        return result


def audit(*, publish=False):
    if os.name != 'nt':
        raise RuntimeError('Windows_exact_child_lifecycle_audit_required')
    import httpx
    from PIL import Image
    from tools.rehab_ml.session_load_audit import fact
    run = paths()['run']/('socket-recovery-'+uuid4().hex[:8])
    run.mkdir()
    hashes = {name:file_hash(ROOT/name) for name in SOURCES}
    write_json(run/'predeclared.json', dict(workload=WORKLOAD, source_sha256=hashes))
    result = dict(run_id=run.name, workload=WORKLOAD, source_sha256=hashes, checks={}, hosts=[],
                  clinical_accuracy=None, passed=False)
    hosts, clients = [], []
    try:
        first = OwnedHost(run, 0); hosts.append(first)
        ready = first.ready(); first.port = ready['port']
        client = httpx.Client(base_url=f'http://127.0.0.1:{first.port}', timeout=5., trust_env=False,
                             headers={'X-Rehab-Client':'mobile-v1'}); clients.append(client)
        def call(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json()
        result['checks']['unauthenticated_denied'] = client.get(BASE).status_code == 401
        call('POST', '/api/pair', json=dict(code='TEST-socket-key'))
        cookie = client.cookies.get('rehab_device'); uid = cookie.split('.')[0]
        plan = seed_plan(run, uid)
        create = dict(idempotency_key='TEST-loss-create', consent=True, plan_id=plan['id'],
            expected_plan_revision=plan['revision'], entry_key=plan['items'][0]['key'], view='frontal')
        lost = abort_after_gate(first, cookie, BASE, create, 'create')
        item = call('POST', BASE, json=create); sid = item['session_id']; endpoint = BASE+'/'+sid
        result['checks']['lost_create_retry_same_session'] = sid == lost['session_id']
        result['checks']['changed_create_payload_conflict'] = client.post(BASE, json=dict(create, consent=False)).status_code == 409
        revision = 0
        for operation in ('pause', 'resume'):
            revision = call('POST', endpoint+'/'+operation,
                json=dict(idempotency_key='TEST-'+operation, expected_revision=revision))['revision']
        image = BytesIO(); Image.new('RGB', (320,240), 'white').save(image, format='JPEG'); encoded = image.getvalue()
        call('POST', endpoint+'/frames', content=encoded,
            headers={'content-type':'image/jpeg', 'x-rehab-event-id':'TEST-frame1', 'x-rehab-seq':'1'})
        state = until(lambda: (row if (row:=call('GET', endpoint))['processed_count'] == 1 else None), 'original_YOLO_frame')
        diagnostics = call('GET', endpoint+'/diagnostics')
        result['checks']['real_JPEG_processed_no_people_count'] = state['snapshot']['completed'] == 0 and state['observation_state'] == 'missing'
        result['checks']['original_native_inference_stage_recorded'] = diagnostics['stages']['inference_ms']['total_samples'] == 1
        finish = dict(idempotency_key='TEST-loss-finish', expected_revision=revision, reason='user_stopped')
        canonical = abort_after_gate(first, cookie, endpoint+'/finish', finish, 'finish')
        result['checks']['lost_finish_query_retry_alias_same_commit'] = (
            call('GET', endpoint+'/commit')['receipt'] == canonical
            == call('POST', endpoint+'/finish', json=finish)
            == call('POST', endpoint+'/finish', json=dict(finish, idempotency_key='TEST-alias')))
        result['checks']['changed_finish_payload_conflict'] = client.post(endpoint+'/finish', json=dict(finish, reason='completed')).status_code == 409
        result['checks']['late_frame_rejected'] = client.post(endpoint+'/frames', content=encoded,
            headers={'content-type':'image/jpeg','x-rehab-event-id':'TEST-late','x-rehab-seq':'2'}).status_code == 409
        feedback = dict(idempotency_key='TEST-feedback', expected_revision=0, feedback=dict(pain=None, fatigue=None))
        feedback_value = call('POST', endpoint+'/feedback', json=feedback)
        result['checks']['null_feedback_once'] = (feedback_value['pain'] is None and feedback_value['fatigue'] is None
            and feedback_value == call('POST', endpoint+'/feedback', json=feedback))
        until(lambda: call('GET', endpoint)['derived_report_state'] == 'ready', 'original_report_ready')
        before = fact(call('GET', endpoint))
        result['checks']['plan_not_completed_by_empty_video'] = call('GET', '/api/rehab/v2/plans/'+plan['id'])['progress']['completed'] == 0
        draft = call('POST', BASE, json=dict(idempotency_key='TEST-draft', consent=True, submode='assessment',
            exercise_id='shoulder_abduction', side='left', view='frontal'))
        draft_endpoint = BASE+'/'+draft['session_id']
        call('POST', draft_endpoint+'/frames', content=encoded,
            headers={'content-type':'image/jpeg','x-rehab-event-id':'TEST-draft-frame','x-rehab-seq':'1'})
        until(lambda: call('GET', draft_endpoint)['processed_count'] == 1, 'draft_frame_checkpoint')
        original = facts(run/'TEST-server-data'/'rehab-v2.sqlite3')
        result['checks']['two_rows_only_one_final_before_crash'] = (len(original) == 2
            and original[sid]['contributions'] == 1 and original[draft['session_id']]['contributions'] == 0)
        proof = first.capture_workers()
        result['checks']['actual_pose_and_report_children_live'] = all(proof[role] and proof[role]['alive'] for role in ('pose','report'))
        stopped = first.close(forced=True); result['hosts'].append(stopped)
        result['checks']['forced_host_and_children_exit_without_fallback'] = (stopped['actual_host_exit_confirmed']
            and not stopped['fallback_cleanup_required'] and len(stopped['captured_native_exits']) == 2
            and all(stopped['captured_native_exits']))
        second = OwnedHost(run, 1); hosts.append(second)
        ready = second.ready(); second.port = ready['port']
        restarted = httpx.Client(base_url=f'http://127.0.0.1:{second.port}', timeout=5., trust_env=False,
            headers={'X-Rehab-Client':'mobile-v1'}, cookies={'rehab_device':cookie}); clients.append(restarted)
        client = restarted
        final = call('GET', draft_endpoint)
        recovered = final['canonical_commit']
        result['checks']['second_actual_server_recovered_interrupted'] = (ready['pid'] != proof['host_pid']
            and final['persistence_state'] == 'finalized' and final['end_reason'] == 'interrupted'
            and recovered is not None and final['snapshot']['completed'] == 0)
        result['checks']['prior_visual_fact_immutable_across_server_restart'] = fact(call('GET', endpoint)) == before
        result['checks']['original_finish_retries_still_canonical'] = call('POST', endpoint+'/finish', json=finish) == canonical
        result['checks']['finalized_cannot_resume'] = client.post(draft_endpoint+'/resume',
            json=dict(idempotency_key='TEST-no-reopen', expected_revision=final['revision'])).status_code == 409
        result['checks']['feedback_null_and_revision_survive_restart'] = (
            (row:=call('GET', endpoint))['latest_feedback']['pain'] is None and row['feedback_revision'] == 1)
        result['checks']['history_two_unique_finalized_rows'] = set(row['session_id'] for row in call('GET', BASE)['items']) == {sid,draft['session_id']}
        other = httpx.Client(base_url=client.base_url, timeout=5., trust_env=False, headers={'X-Rehab-Client':'mobile-v1'}); clients.append(other)
        other.post('/api/pair', json=dict(code='TEST-socket-key')).raise_for_status()
        result['checks']['other_paired_owner_cannot_read_known_session'] = other.get(endpoint).status_code == 404 and other.get(BASE).json()['items'] == []
        after = facts(run/'TEST-server-data'/'rehab-v2.sqlite3')
        result['checks']['one_contribution_each_and_feedback_once_SQL'] = (len(after) == 2
            and all(row['contributions'] == 1 for row in after.values())
            and after[sid]['feedback_rows'] == 1 and after[draft['session_id']]['feedback_rows'] == 0
            and after[sid]['fact'] == before)
        second.capture_workers()
        stopped = second.close(); result['hosts'].append(stopped)
        shutdown = read_json(run/'TEST-shutdown-1.json')
        result['checks']['restarted_host_graceful_actual_release'] = (stopped['actual_host_exit_confirmed']
            and stopped['host_exit_code'] == 0 and not stopped['fallback_cleanup_required']
            and all(stopped['captured_native_exits']) and shutdown['resources_released']
            and not shutdown['pose_retained'] and not shutdown['report_retained'] and not any(shutdown['consumers_alive']))
    except Exception as error:
        result['error'] = dict(type=type(error).__name__, message=str(error))
    finally:
        for client in clients:
            client.close()
        for host in reversed(hosts):
            if host.process.poll() is None or host.handles:
                try:
                    result['hosts'].append(host.close())
                except Exception as error:
                    result.setdefault('cleanup_errors', []).append(type(error).__name__+':'+str(error))
    result['source_unchanged'] = hashes == {name:file_hash(ROOT/name) for name in SOURCES}
    result['passed'] = (len(result['checks']) == 22 and all(result['checks'].values())
        and len(result['hosts']) == 2 and not result.get('error') and not result.get('cleanup_errors')
        and result['source_unchanged'])
    raw = run/'summary.json'; write_json(raw, result)
    public = dict(result, raw_summary=dict(path=str(raw), sha256=file_hash(raw)))
    if publish:
        write_json(ROOT/'reports/rehab_backend/socket_recovery.json', public)
    return public


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--child-run', type=Path)
    parser.add_argument('--child-index', type=int, choices=(0,1))
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    if args.child_run:
        server_child(args.child_run, args.child_index)
        return 0
    result = audit(publish=args.publish)
    print(json.dumps(result, allow_nan=False))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
