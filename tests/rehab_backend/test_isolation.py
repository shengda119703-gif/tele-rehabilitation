"""Real owned child-process failures, isolated TEST storage; no user devices.

Fixture workers prove transport/lifecycle only. The existing HTTP JPEG test
separately executes the real verified YOLO through the default process target.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from io import BytesIO
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
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mobile_rehab.rehab_v2.pose_worker import (IsolatedPoseWorker, PoseWorkerError, VERSION,
                                             JPEG_CAPACITY, MEMORY_CAPACITY, _send, _reply)
from mobile_rehab.rehab_v2.service import SessionService
from app.domain import Context, PoseFrame
from app.rehab_v2.sessions import SessionError
from test_sessions import frozen_plan, request
from tools.rehab_ml.common import paths


def echo_pose(pipe, memory_name):
    memory = SharedMemory(name=memory_name)
    try:
        _send(pipe, dict(ready=VERSION))
        while True:
            value = json.loads(pipe.recv_bytes(4096))
            if value is None:
                return
            encoded = bytes(memory.buf[:value['length']])
            if hashlib.sha256(encoded).hexdigest() != value['image_sha256']:
                raise ValueError('TEST transport mismatch')
            if encoded == b'hang':
                while True:
                    time.sleep(.05)
            if encoded == b'bad-length':
                _send(pipe, dict(reply_length=True, reply_sha256='TEST-bad'))
                continue
            if encoded == b'bad-hash':
                _send(pipe, dict(reply_length=2, reply_sha256='TEST-bad'))
                continue
            pose = PoseFrame(Context(**value['context']), value['seq'], value['source_time_s'],
                             (64, 64), [], model_manifest_id='TEST-transport-only-not-model')
            result = dict(ticket=value['ticket'], ok=True, pose=asdict(pose), decode_ms=.1, inference_ms=.2)
            if encoded == b'large-response':
                result['pose']['people'] = [dict(track_key=None, bbox=[0., 0., 64., 64.],
                    xy=[[1., 1.]]*17, conf=[1.]*17, attributes={'TEST-padding': 'x'*(1024*1024)})]
            if encoded == b'ticket':
                result['ticket'] = 'TEST-wrong-ticket'
            if encoded == b'context':
                result['pose']['context']['epoch'] = 'TEST-wrong-epoch'
            if encoded == b'duration':
                result['decode_ms'] = None
            _reply(pipe, memory, result)
    except (EOFError, BrokenPipeError, OSError):
        pass
    finally:
        memory.close()
        pipe.close()


def hanging_pose(pipe, memory_name):
    _send(pipe, dict(ready=VERSION))
    pipe.recv_bytes(4096)
    while True:
        time.sleep(.05)  # A real live process which cannot return an inference.


def no_handshake(pipe, memory_name):
    while True:
        time.sleep(.05)


def crashing_pose(pipe, memory_name):
    _send(pipe, dict(ready=VERSION))
    pipe.recv_bytes(4096)
    os._exit(29)


def wait_until(predicate, timeout=6.):
    deadline = time.monotonic()+timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.01)
    raise AssertionError('TEST condition did not complete within its declared deadline')


def input_value(encoded=b'jpeg-test', *, sid='TEST-sid', seq=1, epoch='TEST-epoch'):
    runtime = SimpleNamespace(context=Context(1, 'rehab', 'TEST-memory', 'SYNTHETIC', 'TEST', sid, epoch),
                              engine=SimpleNamespace(spec=dict(side='left')))
    return dict(encoded=encoded, sid=sid, seq=seq, source_time_s=seq*.05), runtime


class ProcessTransportTests(unittest.TestCase):
    def setUp(self):
        self.worker = IsolatedPoseWorker(target=echo_pose, startup_timeout_s=5.,
                                         cold_timeout_s=.25, frame_timeout_s=.25, release_timeout_s=.25)

    def tearDown(self):
        self.worker.close()

    def assert_released(self, name=None):
        receipt = self.worker.last_release
        self.assertTrue(receipt['confirmed'])
        self.assertIsNotNone(receipt['exit_code'])
        self.assertNotIn(receipt['pid'], {child.pid for child in mp.active_children()})
        self.assertIsNone(self.worker.process)
        self.assertIsNone(self.worker.memory)
        if name is not None:
            with self.assertRaises(FileNotFoundError):
                SharedMemory(name=name)

    def test_same_child_reuses_model_contract_not_context_and_clears_buffer(self):
        pose, durations = self.worker.infer(*input_value(b'large'*100000))
        pid, name = self.worker.process.pid, self.worker.memory.name
        self.assertEqual(pose.context.epoch, 'TEST-epoch')
        self.assertEqual(durations, dict(decode_ms=.1, inference_ms=.2))
        self.assertEqual(bytes(self.worker.memory.buf), b'\0'*MEMORY_CAPACITY)
        pose, _ = self.worker.infer(*input_value(b'next', sid='TEST-next', epoch='TEST-next-epoch'))
        self.assertEqual(self.worker.process.pid, pid)
        self.assertEqual(pose.context.run_id, 'TEST-next')
        self.assertEqual(pose.context.epoch, 'TEST-next-epoch')
        self.worker.close()
        self.assert_released(name)
        self.worker.close()
        self.assertEqual(self.worker.last_release['pid'], pid)

    def test_real_hang_times_out_releases_then_next_request_can_restart(self):
        self.worker.target = hanging_pose
        with self.assertRaisesRegex(PoseWorkerError, 'pose_worker_inference_timeout'):
            self.worker.infer(*input_value(b'x'*JPEG_CAPACITY))
        self.assert_released()
        first = self.worker.last_release['pid']
        self.worker.target = echo_pose
        pose, _ = self.worker.infer(*input_value())
        self.assertNotEqual(self.worker.process.pid, first)
        self.assertEqual(pose.seq, 1)

    def test_startup_without_handshake_is_bounded_and_released(self):
        self.worker.target = no_handshake
        self.worker.startup_timeout_s = .15
        with self.assertRaisesRegex(PoseWorkerError, 'pose_worker_startup_timeout'):
            self.worker.infer(*input_value())
        self.assert_released()

    def test_child_exit_is_detected_not_reported_as_valid_zero_pose(self):
        self.worker.target = crashing_pose
        with self.assertRaises(PoseWorkerError):
            self.worker.infer(*input_value())
        self.assert_released()
        self.assertEqual(self.worker.last_release['exit_code'], 29)

    def test_reply_identity_and_durations_are_rejected(self):
        for payload, code in ((b'ticket', 'ticket_mismatch'), (b'context', 'evidence_identity_mismatch'),
                              (b'duration', 'invalid_pose_worker_stage_duration')):
            with self.subTest(payload=payload), self.assertRaisesRegex(PoseWorkerError, code):
                self.worker.infer(*input_value(payload))
            self.assert_released()

    def test_only_current_session_cancelled_and_host_stop_cannot_restart(self):
        self.worker.target = hanging_pose
        self.worker.cold_timeout_s = 30.
        with ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(self.worker.infer, *input_value())
            wait_until(lambda: self.worker.last_request is not None)
            pid, name = self.worker.process.pid, self.worker.memory.name
            self.assertTrue(self.worker.process.is_alive())  # Confirm a live handle before cancelling.
            self.worker.cancel_current('different-sid')
            self.assertFalse(result.done())
            started = time.monotonic()
            self.worker.cancel_current('TEST-sid')
            with self.assertRaisesRegex(PoseWorkerError, 'pose_worker_cancelled'):
                result.result(timeout=2.)
            self.assertLess(time.monotonic()-started, 2.)
            self.assert_released(name)
            self.assertEqual(self.worker.last_release['pid'], pid)
        self.worker.close()
        with self.assertRaisesRegex(PoseWorkerError, 'pose_worker_cancelled'):
            self.worker.infer(*input_value())

    def test_budgets_and_input_capacity_validated_without_spawning(self):
        for bad in (None, True, float('nan'), 0., 121.):
            with self.assertRaises(ValueError):
                IsolatedPoseWorker(cold_timeout_s=bad)
        for payload in (b'', b'x'*(JPEG_CAPACITY+1), 'not-bytes'):
            with self.assertRaisesRegex(PoseWorkerError, 'invalid_pose_worker_input_size'):
                self.worker.infer(*input_value(payload))
        self.assertIsNone(self.worker.process)

    def test_unconfirmed_owned_process_release_is_quarantined_then_retryable(self):
        self.worker.target = hanging_pose
        self.worker._start()
        process, name = self.worker.process, self.worker.memory.name
        self.assertTrue(process.is_alive())
        with patch.object(process, 'terminate'), patch.object(process, 'kill'):
            with self.assertRaisesRegex(PoseWorkerError, 'pose_worker_release_unconfirmed'):
                self.worker.infer(*input_value())
            self.assertTrue(self.worker.quarantined)
            self.assertTrue(process.is_alive())
            self.assertIsNone(self.worker.last_release)
        self.worker.close()  # Same owned handle, not a new process or broad kill.
        self.assert_released(name)

    def test_warm_timeout_does_not_reuse_the_long_cold_budget(self):
        self.worker.cold_timeout_s = 30.
        self.worker.infer(*input_value())
        started = time.monotonic()
        with self.assertRaisesRegex(PoseWorkerError, 'pose_worker_inference_timeout'):
            self.worker.infer(*input_value(b'hang', seq=2))
        self.assertLess(time.monotonic()-started, 1.5)
        self.assert_released()

    def test_large_response_is_shared_not_a_large_blocking_pipe_message(self):
        pose, _ = self.worker.infer(*input_value(b'large-response'))
        self.assertEqual(len(pose.people[0].attributes['TEST-padding']), 1024*1024)
        self.assertEqual(bytes(self.worker.memory.buf), b'\0'*MEMORY_CAPACITY)

    def test_response_capacity_and_fingerprint_fail_closed(self):
        for payload, code in ((b'bad-length', 'invalid_pose_worker_response_length'),
                              (b'bad-hash', 'pose_worker_response_fingerprint_mismatch')):
            with self.subTest(payload=payload), self.assertRaisesRegex(PoseWorkerError, code):
                self.worker.infer(*input_value(payload))
            self.assert_released()


class ProcessServiceTests(unittest.TestCase):
    def setUp(self):
        from PIL import Image
        self.directory = tempfile.TemporaryDirectory(dir=paths()['run'])
        self.service = SessionService(Path(self.directory.name)/'process.sqlite3', frozen_plan, drain_timeout_s=.05)
        self.service.inference_worker = IsolatedPoseWorker(target=hanging_pose, startup_timeout_s=5.,
            cold_timeout_s=.2, frame_timeout_s=.2, release_timeout_s=.25)
        self.owner = 'TEST-owner'
        self.sid = self.service.create(self.owner, request())['session_id']
        stream = BytesIO()
        Image.new('RGB', (64, 64), 'white').save(stream, format='JPEG')
        self.image = stream.getvalue()

    def tearDown(self):
        self.service.close()
        self.directory.cleanup()

    def submit(self, seq=1, sid=None):
        self.service.submit_jpeg(self.owner, sid or self.sid, 'TEST-jpeg-'+str(seq), seq, self.image)

    def test_hang_finalizes_once_with_exact_failure_and_allows_new_session(self):
        self.submit()
        wait_until(lambda: self.service.get(self.owner, self.sid)['persistence_state'] == 'finalized')
        item = self.service.get(self.owner, self.sid)
        self.assertEqual(item['end_reason'], 'input_failed')
        self.assertEqual(item['snapshot']['completed'], 0)
        self.assertEqual(self.service.repository.audit_view(self.owner, self.sid)['frames'][0]['reason'],
                         'pose_worker_inference_timeout')
        receipt = self.service.finish(self.owner, self.sid, dict(idempotency_key='retry', expected_revision=0))
        self.assertEqual(receipt, item['canonical_commit'])
        self.assertTrue(self.service.inference_worker.last_release['confirmed'])
        diagnostics = self.service.diagnostics(self.owner, self.sid)
        self.assertEqual(diagnostics['counters']['timeout'], 1)
        self.assertEqual(diagnostics['counters']['commit_success'], 1)
        self.assertIsNone(diagnostics['stages']['inference_ms']['p95_ms'])
        self.service.inference_worker.target = echo_pose
        new = self.service.create(self.owner, request('next'))['session_id']
        self.submit(sid=new)
        wait_until(lambda: self.service.get(self.owner, new)['processed_count'] == 1)
        self.assertEqual(self.service.get(self.owner, new)['persistence_state'], 'draft')
        self.assertEqual(len(self.service.history(self.owner)['items']), 1)

    def test_finish_drain_cancels_real_hang_without_mutating_terminal_receipt(self):
        self.service.inference_worker.cold_timeout_s = 30.
        self.submit()
        wait_until(lambda: self.service.inference_worker.last_request is not None)
        self.assertTrue(self.service.inference_worker.process.is_alive())
        self.submit(seq=2)
        started = time.monotonic()
        receipt = self.service.finish(self.owner, self.sid, dict(idempotency_key='finish', expected_revision=0))
        self.assertLess(time.monotonic()-started, .5)
        before = self.service.get(self.owner, self.sid)['snapshot']
        wait_until(lambda: self.service.inflight is None and self.service.frames.unfinished_tasks == 0)
        self.assertTrue(self.service.inference_worker.last_release['confirmed'])
        self.assertEqual(self.service.commit(self.owner, self.sid)['receipt'], receipt)
        self.assertEqual(self.service.get(self.owner, self.sid)['snapshot'], before)
        self.assertIsNone(self.service.inference_worker.process)  # No new child for the old queued frame.
        diagnostics = self.service.diagnostics(self.owner, self.sid)
        self.assertEqual(diagnostics['counters']['unprocessed_at_finish'], 2)
        self.assertEqual(diagnostics['counters']['commit_success'], 1)
        self.assertEqual([row['status'] for row in self.service.repository.audit_view(self.owner, self.sid)['frames']],
                         ['unprocessed', 'unprocessed'])

    def test_close_cancels_live_hang_and_releases_storage_lease(self):
        self.service.inference_worker.cold_timeout_s = 30.
        self.submit()
        wait_until(lambda: self.service.inference_worker.last_request is not None)
        self.assertTrue(self.service.inference_worker.process.is_alive())
        started = time.monotonic()
        self.service.close()
        self.assertLess(time.monotonic()-started, 3.)
        self.assertTrue(self.service.resources_released)
        self.assertFalse(self.service.worker.is_alive())
        self.assertTrue(self.service.inference_worker.last_release['confirmed'])
        self.service = SessionService(Path(self.directory.name)/'process.sqlite3', frozen_plan)
        self.assertEqual(self.service.get(self.owner, self.sid)['end_reason'], 'interrupted')

    def test_late_failed_inference_does_not_end_resumed_epoch(self):
        entered, release = threading.Event(), threading.Event()
        def delayed_failure(value, runtime):
            entered.set()
            release.wait(3.)
            raise OSError('TEST old failed inference')
        self.service.inference_provider = delayed_failure
        try:
            self.submit()
            self.assertTrue(entered.wait(1.))
            self.service.control(self.owner, self.sid, 'pause', dict(idempotency_key='pause', expected_revision=0))
            self.service.control(self.owner, self.sid, 'resume', dict(idempotency_key='resume', expected_revision=1))
            release.set()
            wait_until(lambda: self.service.inflight is None)
            item = self.service.get(self.owner, self.sid)
            self.assertEqual(item['persistence_state'], 'draft')
            self.assertEqual(item['run_state'], 'recovering')
            self.assertEqual(item['snapshot']['completed'], 0)
            self.assertEqual(self.service.repository.audit_view(self.owner, self.sid)['frames'][0]['status'], 'dropped')
        finally:
            release.set()

    def test_failed_shutdown_can_be_retried_without_false_release_claim(self):
        entered, release = threading.Event(), threading.Event()
        def report(item):
            entered.set()
            release.wait(8.)
            return SessionService._report(item)
        self.service.report_builder = report
        self.service.finish(self.owner, self.sid, dict(idempotency_key='finish', expected_revision=0))
        self.assertTrue(entered.wait(1.))
        try:
            with self.assertRaisesRegex(SessionError, 'vision_shutdown_not_confirmed'):
                self.service.close()
            self.assertFalse(self.service.resources_released)
            self.assertTrue(self.service.report_worker.is_alive())
            self.assertEqual(self.service.get(self.owner, self.sid)['persistence_state'], 'finalized')
        finally:
            release.set()
        self.service.close()
        self.assertTrue(self.service.resources_released)

    def test_persistence_failure_stops_child_and_new_admission_without_claiming_commit(self):
        self.service.inference_worker.target = echo_pose
        with patch.object(self.service.repository, 'checkpoint', side_effect=OSError('TEST storage unavailable')):
            self.submit()
            wait_until(lambda: not self.service.worker.is_alive())
        item = self.service.get(self.owner, self.sid)
        self.assertEqual(item['backend_execution']['failure'], 'OSError')
        self.assertEqual(self.service.diagnostics(self.owner, self.sid)['counters']['background_failure'], 1)
        self.assertEqual(item['persistence_state'], 'draft')
        self.assertIsNone(item['canonical_commit'])
        self.assertTrue(self.service.inference_worker.last_release['confirmed'])
        with self.assertRaisesRegex(SessionError, 'formal_inference_worker_unavailable'):
            self.submit(seq=2)
        with self.assertRaisesRegex(SessionError, 'formal_inference_worker_unavailable'):
            self.service.create(self.owner, request('new-after-failure'))
        self.assertEqual(len(self.service.repository.audit_view(self.owner, self.sid)['frames']), 1)
        self.service.close(graceful=False)
        self.service = SessionService(Path(self.directory.name)/'process.sqlite3', frozen_plan)
        recovered = self.service.get(self.owner, self.sid)
        self.assertEqual(recovered['end_reason'], 'interrupted')
        self.assertEqual(recovered['snapshot']['completed'], 0)


if __name__ == '__main__':
    unittest.main()
