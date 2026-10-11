"""Real OS admission tests plus TEST-only session boundaries; no user devices."""
from io import BytesIO
import multiprocessing as mp
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
sys.path.insert(0, str(ROOT/'rehab_codex_single_camera_v2_1'))
from app.rehab_v2.resources import ComputeLease, LOCK_PATH, ResourceBusy, ResourceUnavailable
from app.domain import PoseFrame
from mobile_rehab.rehab_v2.service import SessionService
from mobile_rehab.rehab_v2.pose_worker import (IsolatedPoseWorker, PoseWorkerError,
                                             offline_pose_process)
from app.rehab_v2.sessions import SessionError
from tools.rehab_ml.common import paths, write_json
from test_sessions import frozen_plan, request
from test_isolation import input_value, wait_until


def hold_lease(pipe, role, path):
    try:
        with ComputeLease(role, _path=path):
            pipe.send(dict(held=True, pid=os.getpid()))
            command = pipe.recv()
            if command == 'crash':
                os._exit(31)
    except (ResourceBusy, ResourceUnavailable) as error:
        pipe.send(dict(held=False, error=error.code, pid=os.getpid()))
    finally:
        pipe.close()


class ComputeLeaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=paths()['run'])
        self.path = Path(self.temporary.name)/'TEST-compute.lock'
        self.children = []

    def tearDown(self):
        for child, pipe in self.children:
            if child.is_alive():
                try:
                    pipe.send('close')
                except (EOFError, OSError):
                    pass
                child.join(3.)
                if child.is_alive():
                    child.terminate()
                    child.join(3.)
            self.assertFalse(child.is_alive())
            child.close()
            pipe.close()
        self.temporary.cleanup()

    def child(self, role):
        context = mp.get_context('spawn')
        pipe, remote = context.Pipe()
        child = context.Process(target=hold_lease, args=(remote, role, self.path), daemon=True)
        child.start()
        remote.close()
        self.children.append((child, pipe))
        self.assertTrue(pipe.poll(5.), 'TEST child failed to report real lock acquisition')
        return child, pipe, pipe.recv()

    def test_shared_leases_coexist_in_different_processes(self):
        with ComputeLease('formal', _path=self.path):
            child, _, receipt = self.child('formal')
            self.assertTrue(receipt['held'])
            self.assertTrue(child.is_alive())
            with self.assertRaises(ResourceBusy):
                ComputeLease('heavy', _path=self.path).acquire()

    def test_formal_blocks_actual_heavy_child(self):
        with ComputeLease('formal', _path=self.path):
            child, _, receipt = self.child('heavy')
            self.assertFalse(receipt['held'])
            self.assertEqual(receipt['error'], ResourceBusy.code)
            child.join(3.)
            self.assertEqual(child.exitcode, 0)

    def test_heavy_blocks_formal_and_other_heavy_without_wait(self):
        child, pipe, receipt = self.child('heavy')
        self.assertTrue(receipt['held'])
        for role in ('formal', 'heavy'):
            tick = time.perf_counter()
            with self.assertRaises(ResourceBusy):
                ComputeLease(role, _path=self.path).acquire()
            self.assertLess(time.perf_counter()-tick, .2)
        pipe.send('close')
        child.join(3.)
        self.assertFalse(child.is_alive())
        with ComputeLease('formal', _path=self.path):
            pass

    def test_crash_releases_real_handle_but_keeps_file(self):
        child, pipe, receipt = self.child('heavy')
        self.assertTrue(receipt['held'])
        pipe.send('crash')
        child.join(3.)
        self.assertEqual(child.exitcode, 31)
        self.assertTrue(self.path.is_file())
        with ComputeLease('heavy', _path=self.path):
            pass

    def test_stale_file_content_is_never_a_liveness_claim(self):
        self.path.write_bytes(b'TEST-old-owner-not-live')
        with ComputeLease('heavy', _path=self.path):
            pass
        self.assertEqual(self.path.read_bytes(), b'TEST-old-owner-not-live')

    def test_close_idempotent_and_exception_releases(self):
        lease = ComputeLease('heavy', _path=self.path)
        with self.assertRaisesRegex(ValueError, 'TEST failure'):
            with lease:
                self.assertTrue(lease.held)
                self.assertIs(lease.acquire(), lease)
                raise ValueError('TEST failure')
        lease.close()
        self.assertFalse(lease.held)
        with self.assertRaisesRegex(ValueError, 'cannot_be_reused'):
            lease.acquire()
        with ComputeLease('heavy', _path=self.path):
            pass

    def test_open_failure_is_not_busy_or_success(self):
        self.path.mkdir()
        with self.assertRaises(ResourceUnavailable):
            ComputeLease('formal', _path=self.path).acquire()

    def test_invalid_role_and_output_root_cannot_bypass_capacity(self):
        with self.assertRaisesRegex(ValueError, 'explicit_rehab_compute_role'):
            ComputeLease('preview')
        with patch.dict(os.environ, REHAB_RUN_ROOT=self.temporary.name):
            from tools.rehab_ml.resource_gate import heavy_compute
            self.assertEqual(heavy_compute().path, LOCK_PATH)
            self.assertEqual(ComputeLease('formal').path, LOCK_PATH)


class SessionComputeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=paths()['run'])
        self.service = SessionService(Path(self.temporary.name)/'TEST.sqlite3', frozen_plan,
                                      internal_replay=True, drain_timeout_s=.02)
        self.owner = 'TEST-resource-owner'

    def tearDown(self):
        self.service.close(graceful=False)
        self.temporary.cleanup()

    def create(self, key='create'):
        return self.service.create(self.owner, request(key))['session_id']

    def finish(self, sid):
        revision = self.service.get(self.owner, sid)['revision']
        return self.service.finish(self.owner, sid, dict(idempotency_key='finish', expected_revision=revision))

    def assert_busy(self):
        with self.assertRaises(ResourceBusy):
            ComputeLease('heavy').acquire()

    def assert_free(self):
        with ComputeLease('heavy'):
            pass

    def test_active_and_paused_session_keep_lease(self):
        sid = self.create()
        self.assert_busy()
        self.service.control(self.owner, sid, 'pause', dict(idempotency_key='pause', expected_revision=0))
        self.assert_busy()
        self.service.control(self.owner, sid, 'resume', dict(idempotency_key='resume', expected_revision=1))
        self.assert_busy()
        self.finish(sid)
        self.assert_free()
        self.assertFalse(self.service.runtimes[sid].compute_lease.held)

    def test_busy_rejects_before_sql_creation_and_retry_after_release(self):
        with ComputeLease('heavy'):
            started = time.perf_counter()
            with self.assertRaisesRegex(SessionError, ResourceBusy.code) as caught:
                self.create()
            self.assertEqual(caught.exception.status, 503)
            self.assertLess(time.perf_counter()-started, .2)
            self.assertEqual(self.service.history(self.owner)['items'], [])
            self.assertEqual(self.service.runtimes, {})
        sid = self.create()
        self.assertEqual(self.service.get(self.owner, sid)['session_id'], sid)
        self.assertEqual(len(self.service.runtimes), 1)
        self.assert_busy()
        self.finish(sid)

    def test_finished_idempotent_create_does_not_acquire_again(self):
        sid = self.create()
        self.finish(sid)
        with ComputeLease('heavy'):
            self.assertEqual(self.create(), sid)
        self.assertFalse(self.service.runtimes[sid].compute_lease.held)

    def test_sql_creation_failure_releases_admission(self):
        with patch.object(self.service.repository, 'create', side_effect=OSError('TEST SQL unavailable')):
            with self.assertRaisesRegex(OSError, 'SQL unavailable'):
                self.create()
        self.assert_free()
        self.assertEqual(self.service.runtimes, {})

    def test_failed_final_commit_does_not_release_based_on_memory_state(self):
        sid = self.create()
        with patch.object(self.service.repository, 'finalize', side_effect=OSError('TEST commit failed')):
            with self.assertRaisesRegex(OSError, 'commit failed'):
                self.finish(sid)
        self.service._release_terminal_compute()
        self.assertFalse(self.service.runtimes[sid].terminal_committed)
        self.assert_busy()
        self.service.close(graceful=False)
        self.assert_free()

    def test_unconfirmed_native_release_keeps_host_lease(self):
        sid = self.create()
        self.service.inference_worker.quarantined = True
        try:
            self.finish(sid)
            self.assert_busy()
            self.assertTrue(self.service.runtimes[sid].terminal_committed)
        finally:
            self.service.inference_worker.quarantined = False
        self.service._release_terminal_compute()
        self.assert_free()

    def test_non_graceful_close_releases_only_after_consumers_exit(self):
        self.create()
        self.service.close(graceful=False)
        self.assertFalse(self.service.worker.is_alive())
        self.assertTrue(self.service.resources_released)
        self.assert_free()

    def test_persisted_contract_does_not_claim_old_desktop_coverage(self):
        sid = self.create()
        contract = self.service.get(self.owner, sid)['source']['compute_execution_contract']
        self.assertFalse(contract['uninstrumented_entry_points_covered'])
        self.assertEqual(contract['admission'], 'nonblocking')

    def test_finish_during_inflight_holds_until_actual_return(self):
        self.service.close()
        entered, released = threading.Event(), threading.Event()
        def delayed(value, runtime):
            entered.set()
            if not released.wait(5.):
                raise TimeoutError('TEST release not supplied')
            return PoseFrame(runtime.context, value['seq'], value['source_time_s'], (64, 64), [])
        self.service = SessionService(Path(self.temporary.name)/'TEST-inflight.sqlite3', frozen_plan,
            inference_provider=delayed, drain_timeout_s=.02)
        sid = self.create()
        from PIL import Image
        image = BytesIO()
        Image.new('RGB', (64, 64), 'white').save(image, format='JPEG')
        try:
            self.service.submit_jpeg(self.owner, sid, 'TEST-frame', 1, image.getvalue())
            self.assertTrue(entered.wait(1.))
            receipt = self.finish(sid)
            self.assertEqual(receipt['processed_last_seq'], -1)
            self.assert_busy()
            released.set()
            wait_until(lambda: self.service.inflight is None)
            self.assert_free()
            self.assertEqual(self.service.commit(self.owner, sid)['receipt'], receipt)
        finally:
            released.set()


class HeavyEntryTests(unittest.TestCase):
    def test_actual_training_and_video_entries_refuse_before_heavy_work(self):
        from tools.rehab_ml import training, target_domain, mediapipe_video, pose_masked_smoke, pose_training
        with tempfile.TemporaryDirectory(dir=paths()['run']) as directory:
            request_file = write_json(Path(directory)/'request.json', {})
            functions = [training.train, target_domain.extract_pose, mediapipe_video.run_child,
                         pose_masked_smoke.run_child, pose_training.run_child]
            arguments = [('TEST-no-config',), ('TEST-no-video', 'shoulder_abduction', 'left'),
                         ('TEST-no-request',), ('TEST-no-request',), (request_file,)]
            with ComputeLease('formal'):
                for function, args in zip(functions, arguments):
                    with self.subTest(entry=function.__module__), self.assertRaises(ResourceBusy):
                        function(*args)
            self.assertEqual(list(Path(directory).iterdir()), [Path(request_file)])

    def test_training_child_keeps_exclusive_lease_during_actual_body(self):
        from tools.rehab_ml.pose_training import run_child
        def body(_):
            for role in ('formal', 'heavy'):
                with self.assertRaises(ResourceBusy):
                    ComputeLease(role).acquire()
            return 'TEST-body-result'
        with tempfile.TemporaryDirectory(dir=paths()['run']) as directory:
            request_file = write_json(Path(directory)/'request.json', {})
            with patch('tools.rehab_ml.pose_training._run_locked_child', side_effect=body) as called:
                self.assertEqual(run_child(request_file), 'TEST-body-result')
                called.assert_called_once_with(Path(request_file).resolve())
        with ComputeLease('formal'):
            pass

    def test_original_offline_yolo_child_busy_handshake_released(self):
        worker = IsolatedPoseWorker(target=offline_pose_process, startup_timeout_s=5., release_timeout_s=.25)
        try:
            with ComputeLease('formal'):
                with self.assertRaisesRegex(PoseWorkerError, ResourceBusy.code):
                    worker.infer(*input_value())
                self.assertTrue(worker.last_release['confirmed'])
                self.assertIsNone(worker.process)
        finally:
            worker.close()

    def test_formal_pose_child_refuses_heavy_before_decoder_import(self):
        worker = IsolatedPoseWorker(startup_timeout_s=5., release_timeout_s=.25)
        try:
            with ComputeLease('heavy'):
                with self.assertRaisesRegex(PoseWorkerError, ResourceBusy.code):
                    worker.infer(*input_value())  # Not JPEG: lock refusal must come first.
                self.assertTrue(worker.last_release['confirmed'])
                self.assertIsNone(worker.process)
        finally:
            worker.close()


if __name__ == '__main__':
    unittest.main()
