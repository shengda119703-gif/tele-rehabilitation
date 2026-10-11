"""Native Windows containment; no devices, user process or patient data."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mobile_rehab.rehab_v2.host_lifetime import HostJob, lifetime_contract
from mobile_rehab.rehab_v2.pose_worker import IsolatedPoseWorker, PoseWorkerError
from tools.rehab_ml.common import paths, write_json
from tools.rehab_ml.native_parent_audit import audit, CASES
from test_isolation import input_value, echo_pose


def forbidden_target(pipe, memory_name):
    write_json(Path(os.environ['REHAB_TEST_FORBIDDEN_TARGET']), dict(entered=True))
    while True:
        time.sleep(.02)


class LifetimeContractTests(unittest.TestCase):
    def test_other_platform_does_not_claim_kernel_containment(self):
        with patch('mobile_rehab.rehab_v2.host_lifetime.os.name', 'posix'):
            contract = lifetime_contract()
        self.assertFalse(contract['kernel_enforced'])
        self.assertEqual(contract['policy'], 'existing_owned_release_only')


@unittest.skipUnless(os.name == 'nt', 'actual Windows kernel containment required')
class WindowsLifetimeTests(unittest.TestCase):
    def test_owned_host_death_releases_native_pose_report_and_original_YOLO(self):
        result = audit()
        self.assertTrue(result['passed'], str(result))
        self.assertTrue(result['source_unchanged'])
        self.assertEqual([row['case'] for row in result['cases']], list(CASES))
        for row in result['cases']:
            self.assertFalse(row['supervisor_cleanup_required'])
            self.assertTrue(row['checks']['child_auto_exit_without_supervisor_kill'])

    def test_job_handle_is_non_inheritable_and_close_idempotent(self):
        job = HostJob()
        try:
            api = ctypes.WinDLL('kernel32', use_last_error=True)
            api.GetHandleInformation.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
            api.GetHandleInformation.restype = wintypes.BOOL
            flags = wintypes.DWORD()
            self.assertTrue(api.GetHandleInformation(job.handle, ctypes.byref(flags)))
            self.assertEqual(flags.value & 1, 0)
        finally:
            job.close()
        job.close()
        self.assertIsNone(job.handle)

    def test_job_creation_failure_never_starts_target_or_leaks_memory(self):
        worker = IsolatedPoseWorker(target=echo_pose)
        try:
            with patch('mobile_rehab.rehab_v2.owned_worker.HostJob', side_effect=OSError('TEST create failed')):
                with self.assertRaisesRegex(PoseWorkerError, 'host_lifetime_unavailable'):
                    worker.infer(*input_value())
            self.assertIsNone(worker.process)
            self.assertIsNone(worker.memory)
            self.assertIsNone(worker.host_job)
        finally:
            worker.close()

    def test_assignment_failure_does_not_admit_target_and_releases_exact_child(self):
        with tempfile.TemporaryDirectory(dir=paths()['run']) as folder:
            marker = Path(folder)/'TEST-forbidden.json'
            worker = IsolatedPoseWorker(target=forbidden_target, startup_timeout_s=2.)
            try:
                with patch.dict(os.environ, REHAB_TEST_FORBIDDEN_TARGET=str(marker)):
                    with patch.object(HostJob, 'assign', side_effect=OSError('TEST assign failed')):
                        with self.assertRaisesRegex(PoseWorkerError, 'host_lifetime_unavailable'):
                            worker.infer(*input_value())
                self.assertFalse(marker.exists())
                self.assertTrue(worker.last_release['confirmed'])
                self.assertIsNone(worker.process)
                self.assertIsNone(worker.memory)
                self.assertIsNone(worker.host_job)
            finally:
                worker.close()

    def test_reuse_then_owned_restart_gets_fresh_job_without_changing_transport(self):
        worker = IsolatedPoseWorker(target=echo_pose)
        try:
            pose, _ = worker.infer(*input_value())
            first, pid = worker.host_job, worker.process.pid
            value, runtime = input_value()
            value.update(seq=2, source_time_s=.1)
            pose, _ = worker.infer(value, runtime)
            self.assertIs(worker.host_job, first)
            self.assertEqual(worker.process.pid, pid)
            self.assertEqual(pose.seq, 2)
            worker._release('TEST-owned-restart')
            self.assertIsNone(first.handle)
            pose, _ = worker.infer(*input_value())
            self.assertIsNot(worker.host_job, first)
            self.assertEqual(pose.seq, 1)
            self.assertTrue(worker.contract['host_lifetime']['kernel_enforced'])
        finally:
            worker.close()

    def test_job_close_failure_keeps_valid_handles_for_retry(self):
        worker = IsolatedPoseWorker(target=echo_pose)
        worker.infer(*input_value())
        job = worker.host_job
        try:
            with patch.object(job, 'close', side_effect=OSError('TEST close failed')):
                with self.assertRaisesRegex(PoseWorkerError, 'host_lifetime_release_unconfirmed'):
                    worker._release('TEST-close-fault')
            self.assertTrue(worker.quarantined)
            self.assertIs(worker.host_job, job)
            self.assertFalse(worker.process.is_alive())
            self.assertIsNotNone(worker.memory)
            worker._release('TEST-retry-close')
            self.assertIsNone(worker.process)
            self.assertIsNone(worker.memory)
            self.assertIsNone(worker.host_job)
            self.assertTrue(worker.last_release['confirmed'])
        finally:
            worker.close()


if __name__ == '__main__':
    unittest.main()
