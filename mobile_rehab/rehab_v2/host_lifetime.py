"""Windows kernel containment for an exact owned worker, not a sandbox.

Only the host holds the unnamed, non-inheritable job handle. A child is
admitted to its trusted target only after assignment succeeds. Closing the
last job handle (including host death) terminates its associated child tree.
Other platforms keep their existing lifecycle and do not claim this guarantee.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import multiprocessing as mp
import os
import time

VERSION = 'rehab-owned-host-lifetime-1'


def lifetime_contract():
    return dict(version=VERSION, kernel_enforced=os.name == 'nt',
        policy='windows_kill_on_job_close' if os.name == 'nt' else 'existing_owned_release_only',
        child_target_admission='after_exact_process_job_assignment' if os.name == 'nt' else None,
        child_inherits_job_handle=False, hostile_code_sandbox=False,
        os_process_start_hard_deadline=False)


def _api():
    class Basic(ctypes.Structure):
        _fields_ = [('PerProcessUserTimeLimit', ctypes.c_int64),
                    ('PerJobUserTimeLimit', ctypes.c_int64), ('LimitFlags', wintypes.DWORD),
                    ('MinimumWorkingSetSize', ctypes.c_size_t), ('MaximumWorkingSetSize', ctypes.c_size_t),
                    ('ActiveProcessLimit', wintypes.DWORD), ('Affinity', ctypes.c_size_t),
                    ('PriorityClass', wintypes.DWORD), ('SchedulingClass', wintypes.DWORD)]
    class IO(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in ('ReadOperationCount', 'WriteOperationCount',
                    'OtherOperationCount', 'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]
    class Extended(ctypes.Structure):
        _fields_ = [('BasicLimitInformation', Basic), ('IoInfo', IO),
                    ('ProcessMemoryLimit', ctypes.c_size_t), ('JobMemoryLimit', ctypes.c_size_t),
                    ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    api.CreateJobObjectW.restype = wintypes.HANDLE
    api.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    api.SetInformationJobObject.restype = wintypes.BOOL
    api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    api.AssignProcessToJobObject.restype = wintypes.BOOL
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    return api, Extended


class HostJob:
    def __init__(self):
        if os.name != 'nt':
            raise OSError('windows_host_job_required')
        self.api, info_type = _api()
        self.handle = self.api.CreateJobObjectW(None, None)  # NULL security: non-inheritable.
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        info = info_type()
        info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            error = ctypes.get_last_error()
            self.close()
            raise ctypes.WinError(error)

    def assign(self, process):
        # Windows multiprocessing sentinel is its retained native process
        # handle. Never OpenProcess from a persisted/untrusted PID here.
        if process.pid is None or not process.is_alive():
            raise OSError('owned_process_not_live_for_job_assignment')
        if not self.api.AssignProcessToJobObject(self.handle, process.sentinel):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self.handle is not None:
            if not self.api.CloseHandle(self.handle):
                raise ctypes.WinError(ctypes.get_last_error())
            self.handle = None


def admitted_target(target, pipe, memory_name, admission, timeout_s):
    """No model/shared-buffer target work before its host assigns containment."""
    deadline = time.monotonic()+timeout_s
    parent = mp.parent_process()
    while time.monotonic() < deadline:
        if parent is None or not parent.is_alive():
            pipe.close()
            return
        if admission.wait(min(.02, max(0., deadline-time.monotonic()))):
            target(pipe, memory_name)
            return
    pipe.close()  # Early host/assignment failure cannot leave an unbounded target.
