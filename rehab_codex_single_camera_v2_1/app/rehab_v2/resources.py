"""Cooperative, non-waiting compute admission for this checkout only.

Formal sessions share a lease. An offline heavy task needs an exclusive
lease in the process actually doing the work. File existence is not a lease;
do not unlink this file to clear capacity. Old uninstrumented entry points
and other checkouts/machines are outside this boundary.
"""
from __future__ import annotations

import errno
import os
from pathlib import Path
import threading

VERSION = 'rehab-compute-coordination-1'
ROOT = Path(__file__).resolve().parents[3]
LOCK_PATH = ROOT / '.runtime/rehab_ml/run/compute-coordination.lock'


class ResourceBusy(RuntimeError):
    code = 'rehab_compute_resource_busy'

    def __init__(self):
        super().__init__(self.code)


class ResourceUnavailable(RuntimeError):
    code = 'rehab_compute_resource_unavailable'

    def __init__(self):
        super().__init__(self.code)


def compute_contract():
    return dict(version=VERSION, scope='instrumented_processes_in_this_checkout',
                formal='shared', offline_heavy='exclusive', admission='nonblocking',
                release='os_handle_close_or_actual_process_exit',
                path_not_derived_from_job_output_root=True,
                no_queue_or_automatic_job_start=True, uninstrumented_entry_points_covered=False)


def _windows_api():
    import ctypes
    from ctypes import wintypes

    # Offset/OffsetHigh occupy the same union as Pointer. This layout covers
    # both native 32-bit and 64-bit OVERLAPPED; all unused fields stay zero.
    class Overlapped(ctypes.Structure):
        _fields_ = [('Internal', ctypes.c_size_t), ('InternalHigh', ctypes.c_size_t),
                    ('Offset', wintypes.DWORD), ('OffsetHigh', wintypes.DWORD),
                    ('hEvent', wintypes.HANDLE)]

    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.LockFileEx.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                              wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(Overlapped)]
    api.LockFileEx.restype = wintypes.BOOL
    api.UnlockFileEx.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                                wintypes.DWORD, ctypes.POINTER(Overlapped)]
    api.UnlockFileEx.restype = wintypes.BOOL
    return ctypes, api, Overlapped


class ComputeLease:
    def __init__(self, role, *, _path=None):
        if role not in ('formal', 'heavy'):
            raise ValueError('explicit_rehab_compute_role_required')
        self.role = role
        # Private path injection is for isolated OS-lock tests, never HTTP or
        # job configuration. Production callers all use the checkout path.
        self.path = LOCK_PATH if _path is None else Path(_path)
        self._stream = None
        self._closed = False
        self._guard = threading.RLock()

    @property
    def held(self):
        with self._guard:
            return self._stream is not None

    def acquire(self):
        with self._guard:
            if self._closed:
                raise ValueError('closed_rehab_compute_lease_cannot_be_reused')
            if self._stream is not None:
                return self
            stream = None
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                stream = self.path.open('a+b')
                os.set_inheritable(stream.fileno(), False)
                if os.name == 'nt':
                    import msvcrt
                    ctypes, api, overlapped_type = _windows_api()
                    overlap = overlapped_type()
                    flags = 1 | (2 if self.role == 'heavy' else 0)
                    # Synchronous descriptor + FAIL_IMMEDIATELY; no wait and
                    # no need to write/inspect a potentially locked byte.
                    if not api.LockFileEx(msvcrt.get_osfhandle(stream.fileno()), flags, 0, 1, 0,
                                          ctypes.byref(overlap)):
                        error = ctypes.get_last_error()
                        if error == 33:  # ERROR_LOCK_VIOLATION
                            raise ResourceBusy()
                        raise ResourceUnavailable()
                else:
                    import fcntl
                    try:
                        fcntl.flock(stream.fileno(), (fcntl.LOCK_EX if self.role == 'heavy'
                                                     else fcntl.LOCK_SH) | fcntl.LOCK_NB)
                    except OSError as error:
                        if error.errno in (errno.EACCES, errno.EAGAIN):
                            raise ResourceBusy() from None
                        raise ResourceUnavailable() from None
                self._stream = stream
                return self
            except BaseException as error:
                if stream is not None:
                    stream.close()
                if isinstance(error, OSError):
                    raise ResourceUnavailable() from None
                raise

    def close(self):
        with self._guard:
            stream = self._stream
            if stream is None:
                self._closed = True
                return
            try:
                if os.name == 'nt':
                    import msvcrt
                    ctypes, api, overlapped_type = _windows_api()
                    overlap = overlapped_type()
                    if not api.UnlockFileEx(msvcrt.get_osfhandle(stream.fileno()), 0, 1, 0,
                                            ctypes.byref(overlap)):
                        raise ResourceUnavailable()
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
            except OSError:
                raise ResourceUnavailable() from None
            finally:
                stream.close()  # OS close releases even if explicit unlock failed.
                self._stream = None
                self._closed = True

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *_):
        self.close()
