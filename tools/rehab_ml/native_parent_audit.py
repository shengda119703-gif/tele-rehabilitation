"""Windows TEST host-death audit with exact retained native child handles.

No user process lookup, camera, patient store or APK operation. TEST native
waits deliberately hold the GIL; the original YOLO case uses a white JPEG.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'rehab_codex_single_camera_v2_1'))
from tools.rehab_ml.common import paths, file_hash, write_json

CASES = ('TEST_native_pose_wait', 'TEST_native_report_wait', 'original_YOLO_cold_ticket')
WORKLOAD = dict(version='rehab-native-parent-audit-1', cases=list(CASES),
                host_barrier_s=30, child_exit_after_host_s=2, owned_cleanup_s=5,
                TEST_native_wait_s=60, no_camera_or_patient_database=True,
                scope='Windows_exact_owned_process_handles_not_cross_platform', clinical_accuracy=None)
SOURCES = ('tools/rehab_ml/native_parent_audit.py', 'mobile_rehab/rehab_v2/owned_worker.py',
           'mobile_rehab/rehab_v2/host_lifetime.py', 'mobile_rehab/rehab_v2/pose_worker.py',
           'mobile_rehab/rehab_v2/report_worker.py',
           'rehab_codex_single_camera_v2_1/app/rehab_v2/resources.py',
           'rehab_codex_single_camera_v2_1/assets/models/yolo11n-pose.pt')


class ExactChildHandle:
    """Capture only a freshly proven child while the owned host is still live."""
    def __init__(self, pid):
        self.api = ctypes.WinDLL('kernel32', use_last_error=True)
        for name, arguments, result in (
            ('OpenProcess', [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
            ('GetProcessId', [wintypes.HANDLE], wintypes.DWORD),
            ('WaitForSingleObject', [wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
            ('GetExitCodeProcess', [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
            ('TerminateProcess', [wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
            ('CloseHandle', [wintypes.HANDLE], wintypes.BOOL)):
            function = getattr(self.api, name)
            function.argtypes, function.restype = arguments, result
        self.handle = self.api.OpenProcess(0x100000 | 0x1000 | 1, False, pid)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        if self.api.GetProcessId(self.handle) != pid or self.exited(0.):
            self.close()
            raise RuntimeError('fresh_owned_child_not_live')

    def exited(self, budget):
        value = self.api.WaitForSingleObject(self.handle, int(1000*budget))
        if value == 0xffffffff:
            raise ctypes.WinError(ctypes.get_last_error())
        if value not in (0, 258):
            raise RuntimeError('invalid_process_wait_result')
        return value == 0

    def code(self):
        code = wintypes.DWORD()
        if not self.api.GetExitCodeProcess(self.handle, ctypes.byref(code)):
            raise ctypes.WinError(ctypes.get_last_error())
        return code.value

    def cleanup(self):
        if not self.exited(0.):
            if not self.api.TerminateProcess(self.handle, 31):
                raise ctypes.WinError(ctypes.get_last_error())
            if not self.exited(WORKLOAD['owned_cleanup_s']):
                raise RuntimeError('exact_owned_child_cleanup_unconfirmed')

    def close(self):
        if self.handle is not None:
            if not self.api.CloseHandle(self.handle):
                raise ctypes.WinError(ctypes.get_last_error())
            self.handle = None


def native_wait(pipe, memory_name, role):
    from multiprocessing.shared_memory import SharedMemory
    from app.rehab_v2.resources import ComputeLease
    from mobile_rehab.rehab_v2.pose_worker import VERSION as POSE_VERSION, _send
    from mobile_rehab.rehab_v2.report_worker import VERSION as REPORT_VERSION
    memory = SharedMemory(name=memory_name)
    try:
        _send(pipe, dict(ready=POSE_VERSION if role == 'pose' else REPORT_VERSION))
        request = json.loads(pipe.recv_bytes(4096))
        with ComputeLease('formal' if role == 'pose' else 'report'):
            write_json(Path(os.environ['REHAB_TEST_NATIVE_MARKER']), dict(pid=os.getpid(),
                parent_pid=os.getppid(), ticket=request['ticket'], role=role, memory=memory_name,
                next_call='kernel32.Sleep_60000_via_PyDLL_GIL_held'))
            api = ctypes.PyDLL('kernel32')  # No Python watchdog can run during this native wait.
            api.Sleep.argtypes = [wintypes.DWORD]
            api.Sleep.restype = None
            api.Sleep(int(WORKLOAD['TEST_native_wait_s']*1000))
    finally:
        memory.close()
        pipe.close()


def waiting_pose(pipe, memory_name):
    return native_wait(pipe, memory_name, 'pose')


def waiting_report(pipe, memory_name):
    return native_wait(pipe, memory_name, 'report')


def host_probe(folder, case):
    from PIL import Image
    from mobile_rehab.rehab_v2.pose_worker import IsolatedPoseWorker
    from mobile_rehab.rehab_v2.report_worker import IsolatedReportWorker
    from tools.rehab_ml.async_recovery import test_host, OWNER, CREATE, FINISH
    from app.rehab_v2.evidence import EvidenceFrame, MetricEvidence
    folder = folder.resolve()
    if (not folder.is_relative_to(paths()['run']) or case not in CASES
            or folder.name != case or not folder.parent.name.startswith('native-parent-')
            or any((folder/name).exists() for name in ('host.json', 'native.json', 'TEST-host.sqlite3'))):
        raise ValueError('new_isolated_TEST_probe_required')
    os.environ['REHAB_TEST_NATIVE_MARKER'] = str(folder/'native.json')
    app, service = test_host(folder/'TEST-host.sqlite3')
    item = service.create(OWNER, CREATE)
    sid = item['session_id']
    runtime = service.runtimes[sid]
    seq = 0
    for angle, count in ((0., 30), (70., 10), (0., 10), (70., 6)):
        for _ in range(count):
            seq += 1
            stamp = seq*.05
            metric = MetricEvidence(angle, 'degree', True, None, 'observed', stamp, stamp, 0.,
                                    tuple(runtime.engine.spec['required_joints']))
            evidence = EvidenceFrame(seq, stamp, item['source_epoch'], 'TEST-native-owner', 'coco17-v1',
                'TEST-not-a-model', (640, 480), {'raise_deg': metric}, 'VALID')
            service.submit_evidence(OWNER, sid, 'TEST-'+str(seq), evidence)
    prior = service.get(OWNER, sid)
    if prior['snapshot']['completed'] != 1 or prior['snapshot']['current'] is None:
        raise RuntimeError('real_TEST_checkpoint_required')
    buffer = BytesIO()
    Image.new('RGB', (320, 240), 'white').save(buffer, format='JPEG')
    errors = []
    if case == 'TEST_native_report_wait':
        service.finish(OWNER, sid, FINISH)
        prior = service.get(OWNER, sid)
        worker = IsolatedReportWorker(target=waiting_report, report_timeout_s=90.)
        operation = lambda: worker.build(prior)
    else:
        worker = IsolatedPoseWorker(target=waiting_pose, cold_timeout_s=90.) if case == 'TEST_native_pose_wait' else IsolatedPoseWorker()
        value = dict(encoded=buffer.getvalue(), sid=sid, seq=seq+1, source_time_s=seq*.05+.05)
        operation = lambda: worker.infer(value, runtime)
    def execute():
        try:
            operation()
        except Exception as error:
            errors.append(type(error).__name__)
    job = threading.Thread(target=execute, daemon=True)
    job.start()
    deadline = time.monotonic()+WORKLOAD['host_barrier_s']
    while time.monotonic() < deadline:
        native = folder/'native.json'
        marker_ready = case == 'original_YOLO_cold_ticket' or native.exists()
        process = worker.process
        if process is not None and process.is_alive() and worker.last_request and marker_ready:
            proof = dict(host_pid=os.getpid(), child_pid=process.pid, case=case, session_id=sid,
                memory_name=worker.memory.name, last_request=worker.last_request, operation_thread_alive=job.is_alive(),
                warm=worker.warm, prior_commit=prior.get('canonical_commit'),
                runtime_snapshot=prior['snapshot'], native=json.loads(native.read_text()) if native.exists() else None)
            if not proof['operation_thread_alive'] or proof['warm']:
                raise RuntimeError('cold_inflight_owned_operation_required')
            write_json(folder/'host.json', proof)
            time.sleep(60.)  # Supervisor kills exact owned host; not a graceful close.
            raise RuntimeError('TEST_supervisor_did_not_end_host')
        if not job.is_alive():
            raise RuntimeError('operation_exited_before_barrier:'+str(errors))
        time.sleep(.005)
    raise TimeoutError('TEST_owned_child_not_live_at_barrier')


def audit(*, publish=False):
    if os.name != 'nt':
        raise RuntimeError('Windows_native_parent_audit_required')
    from multiprocessing.shared_memory import SharedMemory
    from app.rehab_v2.resources import ComputeLease
    from tools.rehab_ml.async_recovery import test_host, read_database, OWNER, FINISH
    run = paths()['run']/('native-parent-'+uuid4().hex[:8])
    run.mkdir()
    hashes = {name: file_hash(ROOT/name) for name in SOURCES}
    result = dict(run_id=run.name, predeclared=WORKLOAD, source_sha256=hashes, cases=[])
    write_json(run/'predeclared.json', result)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', __PYVENV_LAUNCHER__=sys.executable)
    for case in CASES:
        folder = run/case
        folder.mkdir()
        row = dict(case=case, checks={})
        result['cases'].append(row)
        host = child = None
        try:
            with (folder/'host.txt').open('w', encoding='utf-8') as log:
                host = subprocess.Popen([sys._base_executable, '-X', 'utf8', '-B', str(Path(__file__).resolve()),
                    '--host-probe', str(folder), '--case', case], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
                deadline = time.monotonic()+WORKLOAD['host_barrier_s']
                while not (folder/'host.json').exists():
                    if host.poll() is not None:
                        raise RuntimeError('host_exited_before_barrier')
                    if time.monotonic() >= deadline:
                        raise TimeoutError('host_barrier_timeout')
                    time.sleep(.005)
                proof = json.loads((folder/'host.json').read_text(encoding='utf-8'))
                if host.poll() is not None or proof['host_pid'] != host.pid:
                    raise RuntimeError('exact_live_host_required')
                if proof['native'] and (proof['native']['pid'] != proof['child_pid'] or proof['native']['parent_pid'] != host.pid):
                    raise RuntimeError('fresh_child_identity_mismatch')
                child = ExactChildHandle(proof['child_pid'])  # Retained before host death; no PID lookup later.
                row['proof'] = proof
                row['checks']['exact_host_and_child_live'] = True
                time.sleep(.1)
                row['checks']['native_task_still_live'] = not child.exited(0.)
                host.kill()
                host.wait(WORKLOAD['owned_cleanup_s'])
                row['host_exit'] = host.returncode
                started = time.perf_counter()
                auto_exit = child.exited(WORKLOAD['child_exit_after_host_s'])
                row['auto_exit_wait_ms'] = 1000*(time.perf_counter()-started)
                row['checks']['child_auto_exit_without_supervisor_kill'] = auto_exit
                row['child_exit_before_cleanup'] = child.code()
                row['supervisor_cleanup_required'] = not auto_exit
                child.cleanup()  # Failed baseline is retained, never changed into a pass.
                row['checks']['actual_child_exit_confirmed'] = child.exited(0.)
                lease = ComputeLease('heavy').acquire()
                lease.close()
                row['checks']['compute_lease_released_after_actual_exit'] = True
                try:
                    memory = SharedMemory(name=proof['memory_name'])
                except FileNotFoundError:
                    row['checks']['volatile_memory_released'] = True
                else:
                    memory.close()
                    row['checks']['volatile_memory_released'] = False
                read_database(folder/'TEST-host.sqlite3')  # Independent read before recovery.
                app, recovered = test_host(folder/'TEST-host.sqlite3')
                try:
                    item = recovered.get(OWNER, proof['session_id'])
                    receipt = recovered.finish(OWNER, proof['session_id'], FINISH)
                    row['checks']['checkpoint_confirmed_rep_preserved'] = item['snapshot']['completed'] == 1 and item['snapshot']['current'] is None
                    row['checks']['canonical_found_not_duplicated'] = receipt == item['canonical_commit']
                    row['checks']['prior_final_commit_or_interrupted_recovery'] = (item['canonical_commit'] == proof['prior_commit']
                        if proof['prior_commit'] else item['end_reason'] == 'interrupted')
                finally:
                    recovered.close(graceful=False)
                saved = read_database(folder/'TEST-host.sqlite3')
                row['checks']['one_final_contribution'] = len(saved['contributions']) == 1
                row['checks']['null_feedback_not_replaced'] = saved['item']['feedback_status'] == 'missing' and saved['feedback_rows'] == 0
        except Exception as error:
            row['error'] = dict(type=type(error).__name__, message=str(error))
        finally:
            if host is not None and host.poll() is None:
                host.kill()
                host.wait(WORKLOAD['owned_cleanup_s'])
            if child is not None:
                child.cleanup()
                child.close()
            row['host_actual_exit_confirmed'] = host is not None and host.poll() is not None
            row['log'] = dict(path=str(folder/'host.txt'), sha256=file_hash(folder/'host.txt'))
            row['passed'] = not row.get('error') and row['host_actual_exit_confirmed'] and all(row['checks'].values())
            write_json(run/'summary.json', result)
    result['source_unchanged'] = hashes == {name: file_hash(ROOT/name) for name in SOURCES}
    result['passed'] = result['source_unchanged'] and all(row['passed'] for row in result['cases'])
    write_json(run/'summary.json', result)
    result['raw_summary'] = dict(path=str(run/'summary.json'), sha256=file_hash(run/'summary.json'))
    if publish:
        write_json(ROOT/'reports/rehab_backend/native_parent_audit.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host-probe', type=Path)
    parser.add_argument('--case', choices=CASES)
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    if args.host_probe:
        if not args.case or args.publish:
            parser.error('explicit TEST case required, publication forbidden in host')
        host_probe(args.host_probe, args.case)
        return 1
    if args.case:
        parser.error('case only valid for TEST host')
    result = audit(publish=args.publish)
    print(json.dumps(dict(run_id=result['run_id'], passed=result['passed'], raw_summary=result['raw_summary'],
        cases=[{key: value for key, value in row.items() if key != 'proof'} for row in result['cases']]), allow_nan=False))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
