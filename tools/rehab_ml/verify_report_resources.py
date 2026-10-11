"""Durable report deferral / owned preemption audit, isolated TEST facts only."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.rehab_ml.common import ROOT, file_hash, paths, write_json


def native_audit(root):
    import multiprocessing as mp
    from multiprocessing.shared_memory import SharedMemory
    from app.domain import digest
    from app.rehab_v2.resources import ComputeLease
    from mobile_rehab.rehab_v2.report_worker import report_process
    from mobile_rehab.rehab_v2.service import SessionService
    from test_isolation import wait_until
    from test_report_isolation import hanging_report
    from test_sessions import frozen_plan, request
    from test_protocols import Replay

    owner = 'TEST-report-admission-owner'
    database = root/'TEST-sessions.sqlite3'
    service = SessionService(database, frozen_plan, internal_replay=True)
    service.report_executor.report_timeout_s = 2.
    result = {}

    def immutable(sid):
        item = service.repository.get(owner, sid)
        return digest(dict(snapshot=item['snapshot'], receipt=item['canonical_commit'],
                           contribution=service.repository.plan_contribution(owner, sid)))

    def finish(sid, key):
        return service.finish(owner, sid, dict(idempotency_key=key,
            expected_revision=service.get(owner, sid)['revision']))

    try:
        with ComputeLease('formal'):
            sid = service.create(owner, request('TEST-first'))['session_id']
            replay = Replay()
            for angle, count in ((0., 30), (70., 10), (0., 10)):
                for _ in range(count):
                    replay.feed(angle, 1)
                    service.submit_evidence(owner, sid, 'TEST-frame-'+str(replay.seq), replay.frame)
            receipt = finish(sid, 'TEST-first-finish')
            before = immutable(sid)
            wait_until(lambda: service.diagnostics(owner, sid)['counters']['report_deferred'] > 0)
            deferred = service.rebuild_report(owner, sid)
            if deferred.get('state') != 'deferred' or service.report_executor.process is not None:
                raise RuntimeError('report_not_deferred_before_native_spawn')
            if immutable(sid) != before or service.commit(owner, sid)['receipt'] != receipt:
                raise RuntimeError('report_deferral_changed_committed_fact')
            result['formal_deferral'] = dict(response=deferred, child_absent=True,
                completed_reps=receipt['completed_reps'], immutable_sha256=before)

        service.report_wake.set()
        wait_until(lambda: service.get(owner, sid)['derived_report_state'] == 'ready')
        if immutable(sid) != before:
            raise RuntimeError('default_native_report_changed_fact')
        result['default_report_after_release'] = dict(pid=service.report_executor.process.pid,
            ready=True, immutable_sha256=immutable(sid), contract=service.report_executor.contract)

        # The deliberately hanging child is real, but its hang is a TEST
        # target. It is not evidence of a real model/report deadlock.
        service.report_executor.target = hanging_report
        service.report_executor.report_timeout_s = 30.
        service.report_executor.close()
        from mobile_rehab.rehab_v2.report_worker import IsolatedReportWorker
        service.report_executor = IsolatedReportWorker(target=hanging_report, report_timeout_s=30.,
                                                        release_timeout_s=.5)
        second = service.create(owner, request('TEST-second'))['session_id']
        finish(second, 'TEST-second-finish')
        second_before = immutable(second)
        wait_until(lambda: service.report_executor.last_request is not None
                   and service.report_executor.last_request['session_id'] == second)
        child = service.report_executor.process
        pid, memory_name = child.pid, service.report_executor.memory.name
        started = time.perf_counter()
        third = service.create(owner, request('TEST-third'))['session_id']
        create_ms = 1000*(time.perf_counter()-started)
        wait_until(lambda: service.diagnostics(owner, second)['counters']['report_preempted'] == 1)
        if service.get(owner, second)['derived_report_state'] != 'pending':
            raise RuntimeError('preempted_report_not_durable_pending')
        if pid in {process.pid for process in mp.active_children()}:
            raise RuntimeError('owned_report_child_exit_not_confirmed')
        try:
            retained = SharedMemory(name=memory_name)
        except FileNotFoundError:
            pass
        else:
            retained.close()
            raise RuntimeError('owned_report_shared_memory_not_unlinked')
        if immutable(second) != second_before:
            raise RuntimeError('report_preemption_changed_fact')
        result['same_host_preemption'] = dict(owned_pid=pid, owned_exit_confirmed=True,
            shared_memory_unlinked=True, formal_create_ms=create_ms,
            state='pending', immutable_sha256=second_before,
            release=service.report_executor.last_release,
            scope='internal_TEST_create_with_native_hanging_report_not_network_or_pressure')
        service.report_executor.target = report_process
        service.report_executor.report_timeout_s = 2.
        finish(third, 'TEST-third-finish')
        wait_until(lambda: service.get(owner, second)['derived_report_state'] == 'ready')
        wait_until(lambda: service.get(owner, third)['derived_report_state'] == 'ready')
        if immutable(second) != second_before:
            raise RuntimeError('preempted_report_rebuild_changed_fact')

        # A durable failed report is found on restart. Resource busy moves it
        # to pending, so it does not depend on the one-time include_failed scan.
        service.repository.report_state(owner, second, 'failed', error='TEST-restart-failure')
        service.close()
        with ComputeLease('heavy'):
            service = SessionService(database, frozen_plan, internal_replay=True)
            wait_until(lambda: service.get(owner, second)['derived_report_state'] == 'pending')
            if (owner, second) not in service.repository.report_work():
                raise RuntimeError('deferred_report_not_in_durable_work_after_restart')
            if service.report_executor.process is not None or immutable(second) != second_before:
                raise RuntimeError('restart_deferral_spawned_or_changed_fact')
            result['restart_during_heavy'] = dict(state='pending', durable_work_present=True,
                child_absent=True, immutable_sha256=immutable(second))
        service.report_wake.set()
        wait_until(lambda: service.get(owner, second)['derived_report_state'] == 'ready')
        if immutable(second) != second_before:
            raise RuntimeError('restart_rebuild_changed_fact')
        result['restart_after_release'] = dict(state='ready', immutable_sha256=immutable(second))
        return result
    finally:
        service.close(graceful=False)


def main():
    root = paths()['run']/('report-resource-audit-'+uuid4().hex[:8])
    root.mkdir()
    sys.path.insert(0, str(ROOT/'tests/rehab_backend'))
    from app.rehab_v2.resources import ComputeLease
    summary = dict(run_id=root.name, clinical_accuracy=None, human_media_processed=False,
        product_enabled=False, source_kind='SYNTHETIC', usage_context='TEST',
        scope='v2_report_admission_not_full_product_or_device_pressure',
        implementation_sha256={name: file_hash(ROOT/name) for name in (
            'rehab_codex_single_camera_v2_1/app/rehab_v2/resources.py',
            'rehab_codex_single_camera_v2_1/app/rehab_v2/telemetry.py',
            'mobile_rehab/rehab_v2/report_worker.py', 'mobile_rehab/rehab_v2/service.py',
            'mobile_rehab/rehab_v2/owned_worker.py',
            'tests/rehab_backend/test_resources.py', 'tests/rehab_backend/test_report_resources.py',
            'tests/rehab_backend/test_report_isolation.py',
            'tools/rehab_ml/verify_resources.py', 'tools/rehab_ml/verify_report_resources.py')})
    try:
        # Refuse rather than stop somebody else's instrumented work.
        with ComputeLease('heavy'):
            pass
        arguments = ['-X', 'utf8', '-B', '-m', 'unittest',
                     'test_resources', 'test_report_resources', 'test_report_isolation', '-v']
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
            PYTHONPATH=os.pathsep.join((str(ROOT), str(ROOT/'rehab_codex_single_camera_v2_1'),
                                       str(ROOT/'tests/rehab_backend'))))
        started = time.perf_counter()
        completed = subprocess.run([sys.executable, *arguments], cwd=ROOT, env=environment,
            capture_output=True, text=True, encoding='utf-8', timeout=100.)
        log = root/'tests.txt'
        log.write_text(completed.stdout+completed.stderr, encoding='utf-8')
        summary['tests'] = dict(arguments=arguments, exit_code=completed.returncode,
            elapsed_s=time.perf_counter()-started, log=str(log), log_sha256=file_hash(log),
            tail=(completed.stdout+completed.stderr)[-700:])
        if completed.returncode != 0:
            raise RuntimeError('report_resource_regression_failed')
        summary['native'] = native_audit(root)
        summary['passed'] = True
    except Exception as error:
        summary.update(passed=False, failure_type=type(error).__name__, failure=str(error))
    write_json(root/'verification.json', summary)
    report = write_json(ROOT/'reports/rehab_backend/report_resource_verification.json', summary)
    print(json.dumps(dict(path=report, run_id=root.name, passed=summary['passed'],
                          failure=summary.get('failure')), ensure_ascii=False))
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
