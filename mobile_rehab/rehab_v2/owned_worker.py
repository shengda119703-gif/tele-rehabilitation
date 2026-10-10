"""Exact-owned spawn lifecycle shared by bounded local JSON workers.

This is a trusted local process boundary, not a hostile-code sandbox. The OS
Process.start call itself has no hard deadline; readiness and work waits do.
Retain all handles until exit is confirmed, so cleanup can safely be retried.
"""
from __future__ import annotations

import json
import math
import multiprocessing as mp
from multiprocessing.shared_memory import SharedMemory
import threading
import time

NOTIFICATION_CAPACITY = 4096


class OwnedJsonWorker:
    def __init__(self, *, target, version, role, memory_capacity, error_type,
                 startup_timeout_s, release_timeout_s):
        for value in (startup_timeout_s, release_timeout_s):
            if type(value) not in (int, float) or not math.isfinite(value) or not .01 <= value <= 120:
                raise ValueError('finite_bounded_'+role+'_worker_budget_required')
        self.target, self.version, self.role = target, version, role
        self.memory_capacity, self.error_type = memory_capacity, error_type
        self.startup_timeout_s, self.release_timeout_s = startup_timeout_s, release_timeout_s
        self.lock, self.stop = threading.Lock(), threading.Event()
        self.state_lock, self.cancel = threading.Lock(), threading.Event()
        self.active_sid = None
        self.process = self.pipe = self.memory = None
        self.warm = False
        self.quarantined = False
        self.last_release = self.last_request = None

    def _error(self, suffix):
        return self.error_type(self.role+'_worker_'+suffix)

    def _receive(self, budget, stage):
        deadline = time.monotonic()+budget
        while time.monotonic() < deadline:
            if self.stop.is_set() or self.cancel.is_set():
                raise self._error('cancelled')
            if self.pipe.poll(min(.02, max(0., deadline-time.monotonic()))):
                try:
                    value = json.loads(self.pipe.recv_bytes(NOTIFICATION_CAPACITY))
                except (EOFError, OSError, ValueError):
                    raise self.error_type('invalid_'+self.role+'_worker_response') from None
                if not isinstance(value, dict):
                    raise self.error_type('invalid_'+self.role+'_worker_response')
                return value
            if not self.process.is_alive():
                raise self._error('exited')
        raise self._error(stage+'_timeout')

    def _start(self):
        context = mp.get_context('spawn')
        self.memory = SharedMemory(create=True, size=self.memory_capacity)
        self.pipe, child = context.Pipe()
        self.process = context.Process(target=self.target, args=(child, self.memory.name),
                                       name='rehab-v2-owned-'+self.role, daemon=True)
        try:
            self.process.start()
        finally:
            child.close()
        if self._receive(self.startup_timeout_s, 'startup').get('ready') != self.version:
            raise self._error('handshake_mismatch')

    def _release(self, reason):
        if self.process is None and self.memory is None and self.pipe is None:
            return
        process = self.process
        pid = process.pid if process is not None else None
        if process is not None and pid is not None:
            if process.is_alive():
                process.terminate()
            process.join(self.release_timeout_s)
            if process.is_alive():
                process.kill()
                process.join(self.release_timeout_s)
            if process.is_alive():
                self.quarantined = True
                raise self._error('release_unconfirmed')
        exit_code = process.exitcode if process is not None else None
        if self.memory is not None:
            self.memory.buf[:] = b'\0'*self.memory_capacity
            self.memory.close()
            self.memory.unlink()
        if self.pipe is not None:
            self.pipe.close()
        if process is not None:
            process.close()
        self.last_release = dict(pid=pid, exit_code=exit_code, reason=reason, confirmed=True)
        self.process = self.pipe = self.memory = None
        self.warm = False
        self.quarantined = False

    def cancel_current(self, sid):
        with self.state_lock:
            if self.active_sid == sid:
                self.cancel.set()

    def request_stop(self):
        self.stop.set()

    def close(self):
        self.request_stop()
        if not self.lock.acquire(timeout=2*self.release_timeout_s+1.):
            raise self._error('shutdown_lock_unconfirmed')
        try:
            self._release('host_shutdown')
        finally:
            self.lock.release()
