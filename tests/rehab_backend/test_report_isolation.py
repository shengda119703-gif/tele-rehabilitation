"""Owned report process tests with isolated TEST facts, never patient storage."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import multiprocessing as mp
from multiprocessing.shared_memory import SharedMemory
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mobile_rehab.rehab_v2.report_worker import (IsolatedReportWorker, ReportWorkerError,
    VERSION, INPUT_CAPACITY, RESPONSE_CAPACITY, MEMORY_CAPACITY, _send, _reply, report_process)
from mobile_rehab.rehab_v2.service import SessionService
from app.domain import digest
from app.rehab_v2.reporting import build_report
from app.rehab_v2.sessions import SessionError
from tools.rehab_ml.common import paths
from test_isolation import wait_until
from test_sessions import frozen_plan, request
from test_protocols import Replay


def report_fixture(pipe, memory_name, *, delay_first=False):
    """Trusted test-only target. Select fault from TEST source metadata."""
    memory = SharedMemory(name=memory_name)
    try:
        _send(pipe, dict(ready=VERSION))
        while True:
            request = json.loads(pipe.recv_bytes(4096))
            if request is None:
                return
            payload = bytes(memory.buf[:request['length']])
            if hashlib.sha256(payload).hexdigest() != request['input_sha256']:
                raise AssertionError('TEST input hash mismatch')
            item = json.loads(payload)
            mode = item['source'].get('TEST_fault')
            if mode == 'hang':
                while True:
                    time.sleep(.02)
            if mode == 'crash':
                os._exit(31)
            if mode in ('bad-length', 'oversized-response'):
                _send(pipe, dict(reply_length=True if mode == 'bad-length' else RESPONSE_CAPACITY+1,
                                 reply_sha256='TEST-invalid'))
                continue
            if mode == 'bad-hash':
                _send(pipe, dict(reply_length=2, reply_sha256='TEST-invalid'))
                continue
            if (mode == 'delay' or delay_first) and item['feedback_revision'] == 0:
                time.sleep(.5)
            report = build_report(item)
            response = {key: request[key] for key in ('ticket', 'session_id', 'feedback_revision', 'input_sha256')}
            response.update(ok=True, report=report, compute_ms=.1)
            if mode in ('ticket', 'session_id', 'input_sha256'):
                response[mode] = 'TEST-wrong'
            if mode == 'feedback_revision':
                response[mode] += 1
            if mode == 'revision-bool':
                response['feedback_revision'] = False
            if mode == 'duration':
                response['compute_ms'] = None
            if mode == 'fact':
                response['report']['completed_reps'] += 1
            if mode == 'failed':
                response.update(ok=False, error_type='TEST-internal-exception-not-public-text')
            _reply(pipe, memory, response)
    except (EOFError, BrokenPipeError, OSError):
        pass
    finally:
        memory.close()
        pipe.close()


def hanging_report(pipe, memory_name):
    _send(pipe, dict(ready=VERSION))
    pipe.recv_bytes(4096)
    while True:
        time.sleep(.02)


def delayed_report(pipe, memory_name):
    report_fixture(pipe, memory_name, delay_first=True)


def no_report_handshake(pipe, memory_name):
    while True:
        time.sleep(.02)


def wrong_report_handshake(pipe, memory_name):
    _send(pipe, dict(ready='TEST-wrong-version'))
    time.sleep(2.)


def facts(mode=None, sid='TEST-session', revision=0):
    return dict(session_id=sid, source_epoch='TEST-source-epoch',
        source=dict(source_kind='SYNTHETIC', usage_context='TEST', TEST_fault=mode),
        frozen_plan=dict(protocol=dict(protocol_version='TEST-protocol', exercise_id='shoulder_abduction')),
        snapshot=dict(completed=1, protocol={}), end_reason='user_stopped',
        feedback_status='missing' if revision == 0 else 'recorded', feedback_revision=revision,
        owner='TEST-not-transported', canonical_commit={'TEST-private': 'not-transported'})


class ReportTransportTests(unittest.TestCase):
    def setUp(self):
        self.worker = IsolatedReportWorker(target=report_fixture, startup_timeout_s=5.,
                                           report_timeout_s=.25, release_timeout_s=.25)

    def tearDown(self):
        self.worker.close()

    def assert_released(self, name=None):
        self.assertTrue(self.worker.last_release['confirmed'])
        self.assertNotIn(self.worker.last_release['pid'], {child.pid for child in mp.active_children()})
        self.assertIsNotNone(self.worker.last_release['exit_code'])
        self.assertIsNone(self.worker.process)
        self.assertIsNone(self.worker.memory)
        if name is not None:
            with self.assertRaises(FileNotFoundError):
                SharedMemory(name=name)

    def test_actual_default_pure_builder_matches_facts_reuses_and_clears(self):
        self.worker.target = report_process
        item = facts()
        item['snapshot']['TEST-padding'] = 'x'*100000
        report, durations = self.worker.build(item)
        self.assertEqual(report, build_report(item))
        self.assertGreaterEqual(durations['report_compute_ms'], 0.)
        self.assertGreaterEqual(durations['report_roundtrip_ms'], durations['report_compute_ms'])
        pid, name = self.worker.process.pid, self.worker.memory.name
        self.assertEqual(bytes(self.worker.memory.buf), b'\0'*MEMORY_CAPACITY)
        report, _ = self.worker.build(facts(sid='TEST-next', revision=1))
        self.assertEqual(self.worker.process.pid, pid)
        self.assertEqual(report['session_id'], 'TEST-next')
        self.assertEqual(report['feedback_status'], 'recorded')
        self.assertNotIn('owner', report)
        self.assertNotIn('canonical_commit', report)
        self.worker.close()
        self.assert_released(name)
        self.worker.close()

    def test_real_hang_is_released_and_next_report_can_restart(self):
        with self.assertRaisesRegex(ReportWorkerError, 'report_worker_report_timeout'):
            self.worker.build(facts('hang'))
        self.assert_released()
        pid = self.worker.last_release['pid']
        report, _ = self.worker.build(facts())
        self.assertEqual(report['completed_reps'], 1)
        self.assertNotEqual(self.worker.process.pid, pid)

    def test_startup_timeout_and_bad_handshake_release_exact_child(self):
        for target, code in ((no_report_handshake, 'startup_timeout'), (wrong_report_handshake, 'handshake_mismatch')):
            with self.subTest(target=target.__name__):
                self.worker.target = target
                self.worker.startup_timeout_s = .6
                with self.assertRaisesRegex(ReportWorkerError, code):
                    self.worker.build(facts())
                self.assert_released()

    def test_real_exit_is_failed_report_not_zero_measurement(self):
        with self.assertRaises(ReportWorkerError):
            self.worker.build(facts('crash'))
        self.assert_released()
        self.assertEqual(self.worker.last_release['exit_code'], 31)

    def test_bad_lengths_hash_identity_duration_facts_are_rejected(self):
        cases = [('bad-length', 'invalid_report_worker_response_length'),
                 ('oversized-response', 'invalid_report_worker_response_length'),
                 ('bad-hash', 'response_fingerprint_mismatch'), ('ticket', 'identity_mismatch'),
                 ('session_id', 'identity_mismatch'), ('feedback_revision', 'identity_mismatch'),
                 ('input_sha256', 'identity_mismatch'), ('duration', 'invalid_report_worker_stage_duration'),
                 ('fact', 'fact_mismatch'), ('failed', 'build_failed'), ('revision-bool', 'identity_mismatch')]
        for mode, code in cases:
            with self.subTest(mode=mode), self.assertRaisesRegex(ReportWorkerError, code):
                self.worker.build(facts(mode))
            self.assert_released()

    def test_bounds_checked_before_spawn_and_busy_has_no_queue(self):
        for key in ('startup_timeout_s', 'report_timeout_s', 'release_timeout_s'):
            for bad in (None, True, float('nan'), 0., 121.):
                with self.subTest(key=key, bad=bad), self.assertRaises(ValueError):
                    IsolatedReportWorker(**{key: bad})
        item = facts()
        item['snapshot']['TEST-padding'] = 'x'*(INPUT_CAPACITY+1)
        with self.assertRaisesRegex(ReportWorkerError, 'input_capacity_exceeded'):
            self.worker.build(item)
        self.assertIsNone(self.worker.process)
        with self.worker.lock, self.assertRaisesRegex(ReportWorkerError, 'report_worker_busy'):
            self.worker.build(facts())
        self.assertIsNone(self.worker.process)

    def test_current_cancel_only_and_stop_forbids_restart(self):
        self.worker.report_timeout_s = 30.
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.worker.build, facts('hang'))
            wait_until(lambda: self.worker.last_request is not None)
            name = self.worker.memory.name
            self.worker.cancel_current('TEST-other')
            self.assertFalse(future.done())
            self.worker.cancel_current('TEST-session')
            with self.assertRaisesRegex(ReportWorkerError, 'report_worker_cancelled'):
                future.result(timeout=2.)
            self.assert_released(name)
        self.worker.close()
        with self.assertRaisesRegex(ReportWorkerError, 'report_worker_cancelled'):
            self.worker.build(facts())

    def test_release_unconfirmed_retains_handles_and_retry_uses_same_owner(self):
        self.worker.target = hanging_report
        self.worker._start()
        process, name = self.worker.process, self.worker.memory.name
        with patch.object(process, 'terminate'), patch.object(process, 'kill'):
            with self.assertRaisesRegex(ReportWorkerError, 'report_worker_release_unconfirmed'):
                self.worker.build(facts())
            self.assertTrue(self.worker.quarantined)
            self.assertIs(self.worker.process, process)
            self.assertTrue(process.is_alive())
            self.assertIsNone(self.worker.last_release)
        self.worker.close()
        self.assert_released(name)


class ReportServiceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=paths()['run'])
        self.database = Path(self.directory.name)/'sessions.sqlite3'
        self.owner = 'TEST-owner'
        self.service = None

    def tearDown(self):
        if self.service:
            self.service.close(graceful=False)
        self.directory.cleanup()

    def make(self, target=report_process, *, timeout=.25, builder=None):
        executor = IsolatedReportWorker(target=target, startup_timeout_s=5.,
                                        report_timeout_s=timeout, release_timeout_s=.25)
        self.service = SessionService(self.database, frozen_plan, internal_replay=True,
                                     report_executor=executor, report_builder=builder)
        return self.service

    def create_finish(self):
        sid = self.service.create(self.owner, request())['session_id']
        replay = Replay()
        for value, count in ((0., 30), (70., 10), (0., 10)):
            for _ in range(count):
                replay.feed(value, 1)
                self.service.submit_evidence(self.owner, sid, 'TEST-frame-'+str(replay.seq), replay.frame)
        receipt = self.service.finish(self.owner, sid,
            dict(idempotency_key='finish', expected_revision=0, reason='user_stopped'))
        return sid, receipt

    def immutable(self, sid):
        item = self.service.repository.get(self.owner, sid)
        return digest(dict(snapshot=item['snapshot'], receipt=item['canonical_commit'],
                           contribution=self.service.repository.plan_contribution(self.owner, sid)))

    def test_default_report_contract_and_diagnostics_do_not_change_facts(self):
        self.make()
        sid, receipt = self.create_finish()
        before = self.immutable(sid)
        wait_until(lambda: self.service.get(self.owner, sid)['derived_report_state'] == 'ready')
        item = self.service.get(self.owner, sid)
        self.assertEqual(item['source']['report_execution_contract']['mode'], 'owned_spawn')
        self.assertEqual(receipt['completed_reps'], 1)
        trace = self.service.diagnostics(self.owner, sid)
        self.assertEqual(trace['stages']['report_compute_ms']['total_samples'], 1)
        self.assertEqual(trace['stages']['report_roundtrip_ms']['total_samples'], 1)
        self.assertIsNone(trace['memory']['owned_report_rss_bytes'])  # Idle child isn't this active job.
        self.assertEqual(self.immutable(sid), before)
        self.assertEqual(self.service.rebuild_report(self.owner, sid)['state'], 'ready')
        self.assertEqual(self.immutable(sid), before)

    def test_real_report_timeout_preserves_commit_progress_and_manual_rebuild(self):
        self.make(hanging_report)
        sid, receipt = self.create_finish()
        before = self.immutable(sid)
        wait_until(lambda: self.service.get(self.owner, sid)['derived_report_state'] == 'failed')
        self.assertEqual(self.service.diagnostics(self.owner, sid)['counters']['report_timeout'], 1)
        self.assertEqual(self.service.commit(self.owner, sid)['receipt'], receipt)
        self.assertEqual(self.immutable(sid), before)
        self.service.report_executor.target = report_process
        self.assertEqual(self.service.rebuild_report(self.owner, sid)['state'], 'ready')
        self.assertEqual(self.immutable(sid), before)

    def test_close_cancels_real_hang_releases_store_and_restart_rebuilds(self):
        self.make(hanging_report, timeout=30.)
        sid, receipt = self.create_finish()
        before = self.immutable(sid)
        wait_until(lambda: self.service.report_executor.last_request is not None)
        pid, name = self.service.report_executor.process.pid, self.service.report_executor.memory.name
        started = time.monotonic()
        self.service.close()
        self.assertLess(time.monotonic()-started, 3.)
        self.assertTrue(self.service.resources_released)
        self.assertNotIn(pid, {child.pid for child in mp.active_children()})
        with self.assertRaises(FileNotFoundError):
            SharedMemory(name=name)
        self.make()
        wait_until(lambda: self.service.get(self.owner, sid)['derived_report_state'] == 'ready')
        self.assertEqual(self.service.commit(self.owner, sid)['receipt'], receipt)
        self.assertEqual(self.immutable(sid), before)
        self.assertFalse(self.service.diagnostics(self.owner, sid)['available'])

    def test_wrong_owner_draft_and_closed_cannot_start_report(self):
        self.make()
        sid = self.service.create(self.owner, request())['session_id']
        with self.assertRaisesRegex(SessionError, 'session_not_found'):
            self.service.rebuild_report('TEST-other-owner', sid)
        with self.assertRaisesRegex(SessionError, 'report_requires_finalized_session'):
            self.service.rebuild_report(self.owner, sid)
        self.assertIsNone(self.service.report_executor.process)
        self.service.closed = True
        with self.assertRaisesRegex(SessionError, 'service_closed'):
            self.service.create(self.owner, request('TEST-new'))

    def test_concurrent_rebuild_returns_running_and_control_queries_stay_short(self):
        self.make(hanging_report, timeout=30.)
        sid, receipt = self.create_finish()
        wait_until(lambda: self.service.report_executor.last_request is not None)
        before = self.immutable(sid)
        started = time.monotonic()
        for _ in range(10):
            self.assertEqual(self.service.rebuild_report(self.owner, sid), dict(state='running'))
            self.assertEqual(self.service.commit(self.owner, sid)['receipt'], receipt)
            self.assertEqual(self.service.get(self.owner, sid)['derived_report_state'], 'pending')
        self.assertLess(time.monotonic()-started, 1.)
        self.assertEqual(self.immutable(sid), before)
        self.assertEqual(self.service.diagnostics(self.owner, sid)['counters']['report_busy'], 10)
        self.service.report_executor.cancel_current(sid)
        wait_until(lambda: self.service.get(self.owner, sid)['derived_report_state'] == 'failed')

    def test_local_callable_hook_is_truthfully_in_process_and_cannot_release_early(self):
        entered, release = threading.Event(), threading.Event()
        def local_report(item):
            entered.set()
            release.wait(8.)
            return build_report(item)
        self.make(builder=local_report)
        sid, _ = self.create_finish()
        self.assertTrue(entered.wait(1.))
        self.assertEqual(self.service.get(self.owner, sid)['source']['report_execution_contract']['mode'],
                         'trusted_local_callable')
        self.assertIsNone(self.service.report_executor.process)
        try:
            with self.assertRaisesRegex(SessionError, 'vision_shutdown_not_confirmed'):
                self.service.close()
            self.assertFalse(self.service.resources_released)
            with self.assertRaisesRegex(SessionError, 'formal_session_store_already_owned'):
                SessionService(self.database, frozen_plan, internal_replay=True)
        finally:
            release.set()
            self.service.report_worker.join(timeout=2.)
            self.service.close()

    def test_report_storage_failure_is_observable_and_never_claims_saved(self):
        self.make()
        with patch.object(self.service.repository, 'report_work', side_effect=OSError('TEST-only')):
            self.service.report_wake.set()
            wait_until(lambda: self.service.report_worker_failure == 'OSError')
            sid = self.service.create(self.owner, request())['session_id']
            self.assertEqual(self.service.get(self.owner, sid)['backend_execution']['report_failure'], 'OSError')
            self.assertEqual(self.service.diagnostics(self.owner, sid)['consumers']['report_failure'], 'OSError')
            self.assertEqual(self.service.get(self.owner, sid)['persistence_state'], 'draft')
        self.service.report_wake.set()
        wait_until(lambda: self.service.report_worker_failure is None)

    def test_child_old_feedback_reply_cannot_overwrite_new_revision(self):
        self.make(delayed_report, timeout=2.)
        sid, receipt = self.create_finish()
        before = self.immutable(sid)
        wait_until(lambda: self.service.report_executor.last_request is not None)
        self.assertEqual(self.service.report_executor.last_request['feedback_revision'], 0)
        self.service.feedback(self.owner, sid, dict(idempotency_key='TEST-feedback', expected_revision=0,
                                                   feedback=dict(pain=None, fatigue=2)))
        wait_until(lambda: self.service.get(self.owner, sid)['derived_report_state'] == 'ready')
        item = self.service.get(self.owner, sid)
        self.assertEqual(item['latest_feedback']['fatigue'], 2)
        self.assertEqual(item['canonical_commit'], receipt)
        payload = self.service.storage._call(lambda conn: json.loads(conn.execute(
            'SELECT payload FROM rehab_v2_reports WHERE session_id=?', (sid,)).fetchone()[0]))
        self.assertEqual(payload['feedback_status'], 'recorded')
        self.assertEqual(self.service.diagnostics(self.owner, sid)['counters']['report_superseded'], 1)
        self.assertEqual(self.immutable(sid), before)

    def test_derived_report_write_failure_leaves_fact_and_pending_for_retry(self):
        self.make(delayed_report, timeout=2.)
        sid, receipt = self.create_finish()
        before = self.immutable(sid)
        wait_until(lambda: self.service.report_executor.last_request is not None)
        with patch.object(self.service.repository, 'report_state', side_effect=OSError('TEST-only-write')):
            wait_until(lambda: self.service.report_worker_failure == 'OSError')
            self.assertEqual(self.service.get(self.owner, sid)['derived_report_state'], 'pending')
            self.assertEqual(self.service.commit(self.owner, sid)['receipt'], receipt)
            self.assertEqual(self.immutable(sid), before)
        self.service.report_wake.set()
        wait_until(lambda: self.service.get(self.owner, sid)['derived_report_state'] == 'ready')
        self.assertEqual(self.immutable(sid), before)

    def test_unconfirmed_report_release_holds_store_until_exact_cleanup_retry(self):
        self.make(hanging_report, timeout=30.)
        sid, receipt = self.create_finish()
        wait_until(lambda: self.service.report_executor.last_request is not None)
        process, name = self.service.report_executor.process, self.service.report_executor.memory.name
        with patch.object(process, 'terminate'), patch.object(process, 'kill'):
            with self.assertRaisesRegex(ReportWorkerError, 'report_worker_release_unconfirmed'):
                self.service.close()
            self.assertFalse(self.service.resources_released)
            self.assertIs(self.service.report_executor.process, process)
            with self.assertRaisesRegex(SessionError, 'formal_session_store_already_owned'):
                SessionService(self.database, frozen_plan, internal_replay=True)
            self.assertEqual(self.service.commit(self.owner, sid)['receipt'], receipt)
        self.service.close()
        self.assertTrue(self.service.resources_released)
        with self.assertRaises(FileNotFoundError):
            SharedMemory(name=name)


if __name__ == '__main__':
    unittest.main()
