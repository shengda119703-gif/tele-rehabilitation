"""OS report admission, durable deferral and same-host owned preemption.

Only isolated TEST facts/SQLite and disposable children; no user services,
camera, media, trained weights or normal patient databases.
"""
from concurrent.futures import ThreadPoolExecutor
from multiprocessing.shared_memory import SharedMemory
import multiprocessing as mp
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import test_report_isolation as helpers
from test_isolation import wait_until
from test_sessions import request
from app.rehab_v2.resources import ComputeLease, ResourceBusy, ResourceUnavailable
from app.rehab_v2.sessions import SessionError
from app.rehab_v2.reporting import build_report
from mobile_rehab.rehab_v2.report_worker import ReportWorkerError, report_process
from tools.rehab_ml.common import paths


class ReportAdmissionTransportTests(unittest.TestCase):
    setUp = helpers.ReportTransportTests.setUp
    tearDown = helpers.ReportTransportTests.tearDown
    assert_released = helpers.ReportTransportTests.assert_released

    def test_formal_or_heavy_defers_before_serialization_or_spawn(self):
        for role in ('formal', 'heavy'):
            with self.subTest(role=role), ComputeLease(role):
                with self.assertRaisesRegex(ReportWorkerError, ResourceBusy.code):
                    self.worker.build(helpers.facts())
                self.assertIsNone(self.worker.process)
                self.assertIsNone(self.worker.memory)
                self.assertIsNone(self.worker.compute_lease)
                self.assertIsNone(self.worker.last_request)
        report, _ = self.worker.build(helpers.facts())
        self.assertEqual(report['completed_reps'], 1)

    def test_real_child_rechecks_after_formal_wins_spawn_race_and_is_reused(self):
        self.worker.target = report_process
        entered, release = threading.Event(), threading.Event()
        actual_start = self.worker._start
        def start_then_gate():
            actual_start()
            entered.set()
            if not release.wait(5.):
                raise AssertionError('TEST startup gate not released')
        with patch.object(self.worker, '_start', side_effect=start_then_gate):
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(self.worker.build, helpers.facts())
                self.assertTrue(entered.wait(5.))
                pid = self.worker.process.pid
                with ComputeLease('formal'):
                    release.set()
                    with self.assertRaisesRegex(ReportWorkerError, ResourceBusy.code):
                        future.result(timeout=3.)
                    self.assertIsNotNone(self.worker.process)
                    self.assertEqual(self.worker.process.pid, pid)
                    self.assertIsNone(self.worker.compute_lease)
        report, _ = self.worker.build(helpers.facts())
        self.assertEqual(report['completed_reps'], 1)
        self.assertEqual(self.worker.process.pid, pid)

    def test_background_open_error_is_real_unavailable_and_does_not_leak_primary(self):
        with tempfile.TemporaryDirectory(dir=paths()['run']) as directory:
            path = Path(directory)/'TEST-report.lock'
            path.with_name(path.name+'.background').mkdir()
            with patch('mobile_rehab.rehab_v2.report_worker.ComputeLease',
                       side_effect=lambda role: ComputeLease(role, _path=path)):
                with self.assertRaisesRegex(ReportWorkerError, ResourceUnavailable.code):
                    self.worker.build(helpers.facts())
            self.assertIsNone(self.worker.process)
            with ComputeLease('formal', _path=path):
                pass

    def test_unconfirmed_child_release_retains_real_parent_background_lease(self):
        self.worker.target = helpers.hanging_report
        self.worker.report_timeout_s = .15
        # Start outside a build as the existing native-release test does.
        self.worker._start()
        child = self.worker.process
        with patch.object(child, 'terminate'), patch.object(child, 'kill'):
            with self.assertRaisesRegex(ReportWorkerError, 'release_unconfirmed'):
                self.worker.build(helpers.facts())
            self.assertTrue(self.worker.compute_lease.held)
            with self.assertRaises(ResourceBusy):
                ComputeLease('heavy').acquire()
        self.worker.close()
        self.assertIsNone(self.worker.compute_lease)
        with ComputeLease('heavy'):
            pass


class ReportAdmissionServiceTests(unittest.TestCase):
    setUp = helpers.ReportServiceTests.setUp
    tearDown = helpers.ReportServiceTests.tearDown
    make = helpers.ReportServiceTests.make
    create_finish = helpers.ReportServiceTests.create_finish
    immutable = helpers.ReportServiceTests.immutable

    def finish_second(self, sid):
        revision = self.service.get(self.owner, sid)['revision']
        return self.service.finish(self.owner, sid,
            dict(idempotency_key='TEST-second-finish', expected_revision=revision))

    def test_active_paused_formal_defers_report_and_finish_rebuilds_immutable_facts(self):
        self.make()
        with ComputeLease('formal'):
            sid, receipt = self.create_finish()
            before = self.immutable(sid)
            second = self.service.create(self.owner, request('TEST-second'))['session_id']
        self.service.control(self.owner, second, 'pause',
                             dict(idempotency_key='TEST-pause', expected_revision=0))
        wait_until(lambda: self.service.diagnostics(self.owner, sid)['counters']['report_deferred'] > 0)
        result = self.service.rebuild_report(self.owner, sid)
        self.assertEqual(result['state'], 'deferred')
        self.assertEqual(result['reason'], ResourceBusy.code)
        self.assertEqual(self.service.get(self.owner, sid)['derived_report_state'], 'pending')
        self.assertIsNone(self.service.report_executor.process)
        self.assertEqual(self.service.commit(self.owner, sid)['receipt'], receipt)
        self.assertEqual(self.immutable(sid), before)
        self.finish_second(second)
        wait_until(lambda: self.service.get(self.owner, sid)['derived_report_state'] == 'ready')
        wait_until(lambda: self.service.get(self.owner, second)['derived_report_state'] == 'ready')
        self.assertEqual(self.immutable(sid), before)

    def test_restart_failed_report_becomes_durable_pending_while_actual_heavy_holds(self):
        self.make()
        sid, receipt = self.create_finish()
        wait_until(lambda: self.service.get(self.owner, sid)['derived_report_state'] == 'ready')
        before = self.immutable(sid)
        self.service.repository.report_state(self.owner, sid, 'failed', error='TEST-previous-failure')
        self.service.close()
        with ComputeLease('heavy'):
            self.make()
            wait_until(lambda: self.service.get(self.owner, sid)['derived_report_state'] == 'pending')
            self.assertIn((self.owner, sid), self.service.repository.report_work())
            self.assertIsNone(self.service.report_executor.process)
            self.assertEqual(self.immutable(sid), before)
        self.service.report_wake.set()
        wait_until(lambda: self.service.get(self.owner, sid)['derived_report_state'] == 'ready')
        self.assertEqual(self.service.commit(self.owner, sid)['receipt'], receipt)
        self.assertEqual(self.immutable(sid), before)

    def test_new_formal_create_preempts_only_this_owned_native_report_without_wait(self):
        self.make(helpers.hanging_report, timeout=30.)
        sid, receipt = self.create_finish()
        before = self.immutable(sid)
        wait_until(lambda: self.service.report_executor.last_request is not None)
        pid, name = self.service.report_executor.process.pid, self.service.report_executor.memory.name
        started = time.perf_counter()
        second = self.service.create(self.owner, request('TEST-second'))['session_id']
        self.assertLess(time.perf_counter()-started, .2)
        wait_until(lambda: self.service.diagnostics(self.owner, sid)['counters']['report_preempted'] == 1)
        self.assertEqual(self.service.get(self.owner, sid)['derived_report_state'], 'pending')
        self.assertNotIn(pid, {child.pid for child in mp.active_children()})
        with self.assertRaises(FileNotFoundError):
            SharedMemory(name=name)
        self.assertEqual(self.immutable(sid), before)
        self.assertEqual(self.service.commit(self.owner, sid)['receipt'], receipt)
        self.service.report_executor.target = report_process
        self.finish_second(second)
        wait_until(lambda: self.service.get(self.owner, sid)['derived_report_state'] == 'ready')
        self.assertEqual(self.immutable(sid), before)

    def test_deferred_old_feedback_revision_cannot_overwrite_newer_feedback(self):
        self.make()
        # Isolate this manual CAS interleaving from the automatic consumer.
        # Otherwise its legitimate single-slot admission can return 'running'
        # before this test's old-feedback build ever starts.
        with patch.object(self.service.repository, 'report_work', return_value=[]), ComputeLease('formal'):
            sid, receipt = self.create_finish()
            before = self.immutable(sid)
            def newer_then_busy(item):
                self.service.feedback(self.owner, sid, dict(idempotency_key='TEST-feedback',
                    expected_revision=0, feedback=dict(pain=None, fatigue=2)))
                raise ReportWorkerError(ResourceBusy.code)
            with patch.object(self.service.report_executor, 'build', side_effect=newer_then_busy):
                result = self.service.rebuild_report(self.owner, sid)
            self.assertEqual(result['state'], 'pending_newer_feedback')
            self.assertEqual(self.service.get(self.owner, sid)['feedback_revision'], 1)
            self.assertEqual(self.service.get(self.owner, sid)['latest_feedback']['fatigue'], 2)
            self.assertEqual(self.service.commit(self.owner, sid)['receipt'], receipt)
            self.assertEqual(self.immutable(sid), before)

    def test_rejected_or_idempotent_create_does_not_preempt_owned_report(self):
        self.make(helpers.hanging_report, timeout=30.)
        sid, receipt = self.create_finish()
        wait_until(lambda: self.service.report_executor.last_request is not None)
        process = self.service.report_executor.process
        invalid = request('TEST-invalid')
        invalid['consent'] = False
        with self.assertRaisesRegex(SessionError, 'camera_analysis_consent_required'):
            self.service.create(self.owner, invalid)
        self.assertEqual(self.service.create(self.owner, request())['session_id'], sid)
        self.assertFalse(self.service.report_executor.preempted)
        self.assertFalse(self.service.report_executor.cancel.is_set())
        self.assertIs(self.service.report_executor.process, process)
        self.assertTrue(process.is_alive())
        self.assertEqual(self.service.commit(self.owner, sid)['receipt'], receipt)

    def test_deferred_storage_failure_is_observable_not_false_pending(self):
        self.make()
        with patch.object(self.service.repository, 'report_work', return_value=[]), ComputeLease('formal'):
            sid, _ = self.create_finish()
            before = self.immutable(sid)
            with patch.object(self.service.repository, 'report_state',
                              side_effect=SessionError('TEST-report-write-failed', 503)):
                with self.assertRaisesRegex(SessionError, 'TEST-report-write-failed'):
                    self.service.rebuild_report(self.owner, sid)
            self.assertEqual(self.immutable(sid), before)
            self.assertIsNone(self.service.report_executor.process)
            self.assertEqual(self.service.rebuild_report(self.owner, sid)['state'], 'deferred')

    def test_unavailable_is_failed_not_automatically_retried_as_busy(self):
        self.make()
        original_work = self.service.repository.report_work
        with patch.object(self.service.repository, 'report_work', return_value=[]):
            sid, _ = self.create_finish()
            before = self.immutable(sid)
            with patch.object(self.service.report_executor, 'build',
                              side_effect=ReportWorkerError(ResourceUnavailable.code)):
                result = self.service.rebuild_report(self.owner, sid)
            self.assertEqual(result, dict(state='failed', error=ResourceUnavailable.code))
            self.assertEqual(self.service.get(self.owner, sid)['derived_report_state'], 'failed')
            self.assertEqual(original_work(), [])
            self.assertEqual(self.immutable(sid), before)
            self.assertEqual(self.service.rebuild_report(self.owner, sid)['state'], 'ready')

    def test_preexisting_quarantine_refuses_new_formal_without_creating_fact(self):
        self.make()
        self.service.report_executor.quarantined = True
        try:
            with self.assertRaisesRegex(SessionError, 'formal_report_release_unconfirmed'):
                self.service.create(self.owner, request())
            self.assertEqual(self.service.history(self.owner)['items'], [])
        finally:
            self.service.report_executor.quarantined = False

    def test_local_callable_holds_background_until_return_and_reports_no_hard_cancel(self):
        entered, release = threading.Event(), threading.Event()
        def local_report(item):
            entered.set()
            if not release.wait(5.):
                raise AssertionError('TEST local builder gate not released')
            return build_report(item)
        self.make(builder=local_report)
        sid, _ = self.create_finish()
        self.assertTrue(entered.wait(2.))
        try:
            with self.assertRaises(ResourceBusy):
                ComputeLease('heavy').acquire()
            second = self.service.create(self.owner, request('TEST-second'))['session_id']
            contract = self.service.get(self.owner, sid)['source']['report_execution_contract']
            self.assertFalse(contract['hard_cancellation'])
            self.assertEqual(contract['preemption'], 'not_supported_for_local_callable')
        finally:
            release.set()
        wait_until(lambda: self.service.get(self.owner, sid)['derived_report_state'] == 'ready')
        self.finish_second(second)

    def test_sixteen_deferred_rows_use_bounded_retry_not_a_tight_loop(self):
        self.make()
        with ComputeLease('formal'):
            for index in range(16):
                sid = self.service.create(self.owner, request('TEST-backlog-'+str(index)))['session_id']
                self.finish_second(sid)
            calls = []
            original = self.service.repository.report_work
            def work(**kwargs):
                calls.append(time.monotonic())
                return original(**kwargs)
            with patch.object(self.service.repository, 'report_work', side_effect=work):
                self.service.report_wake.set()
                wait_until(lambda: len(calls) > 0)
                time.sleep(.65)
                self.assertLessEqual(len(calls), 3)
            self.assertEqual(len(original()), 16)
            self.assertIsNone(self.service.report_executor.process)
