"""Bounded derived-report worker; no camera, database, credentials or LLM.

Only an already-finalized, whitelisted fact snapshot crosses the boundary.
The host verifies the response against that snapshot and commits it with a
feedback-revision CAS. Timeout/cancellation can fail a report, never a fact.
"""
from __future__ import annotations

import hashlib
import json
import math
from multiprocessing.shared_memory import SharedMemory
import time
from uuid import uuid4

from ..core import CORE
from app.domain import digest, dumps
from app.rehab_v2.reporting import REPORT_INPUT_FIELDS, build_report
from .owned_worker import NOTIFICATION_CAPACITY, OwnedJsonWorker

VERSION = 'rehab-report-process-1'
INPUT_CAPACITY = 2*1024*1024
RESPONSE_CAPACITY = 2*1024*1024
MEMORY_CAPACITY = INPUT_CAPACITY+RESPONSE_CAPACITY


class ReportWorkerError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _send(pipe, value):
    payload = dumps(value).encode('utf-8')
    if len(payload) > NOTIFICATION_CAPACITY:
        raise ValueError('report_notification_capacity_exceeded')
    pipe.send_bytes(payload)


def _reply(pipe, memory, value):
    payload = dumps(value).encode('utf-8')
    if not 0 < len(payload) <= RESPONSE_CAPACITY:
        raise ValueError('report_response_capacity_exceeded')
    memory.buf[INPUT_CAPACITY:INPUT_CAPACITY+len(payload)] = payload
    _send(pipe, dict(reply_length=len(payload), reply_sha256=hashlib.sha256(payload).hexdigest()))


def report_process(pipe, memory_name):
    memory = SharedMemory(name=memory_name)
    try:
        _send(pipe, dict(ready=VERSION))
        while True:
            request = json.loads(pipe.recv_bytes(NOTIFICATION_CAPACITY))
            if request is None:
                break
            identity = {key: request[key] for key in ('ticket', 'session_id', 'feedback_revision', 'input_sha256')}
            try:
                length = request['length']
                if type(length) is not int or not 0 < length <= INPUT_CAPACITY:
                    raise ValueError('invalid_report_input_length')
                payload = bytes(memory.buf[:length])
                if hashlib.sha256(payload).hexdigest() != request['input_sha256']:
                    raise ValueError('report_input_fingerprint_mismatch')
                item = json.loads(payload)
                del payload
                if (set(item) != set(REPORT_INPUT_FIELDS) or item['session_id'] != request['session_id']
                        or item['feedback_revision'] != request['feedback_revision']):
                    raise ValueError('report_input_identity_mismatch')
                started = time.perf_counter()
                report = build_report(item)
                compute_ms = 1000*(time.perf_counter()-started)
                _reply(pipe, memory, dict(identity, ok=True, report=report, compute_ms=compute_ms))
                del item, report
            except Exception as exc:
                _reply(pipe, memory, dict(identity, ok=False, error_type=type(exc).__name__))
    except (EOFError, BrokenPipeError, OSError):
        pass
    finally:
        memory.close()
        pipe.close()


class IsolatedReportWorker(OwnedJsonWorker):
    def __init__(self, *, target=report_process, startup_timeout_s=10.,
                 report_timeout_s=5., release_timeout_s=1.):
        if (type(report_timeout_s) not in (int, float) or not math.isfinite(report_timeout_s)
                or not .01 <= report_timeout_s <= 120):
            raise ValueError('finite_bounded_report_worker_budget_required')
        super().__init__(target=target, version=VERSION, role='report', memory_capacity=MEMORY_CAPACITY,
                         error_type=ReportWorkerError, startup_timeout_s=startup_timeout_s,
                         release_timeout_s=release_timeout_s)
        self.report_timeout_s = report_timeout_s

    @property
    def contract(self):
        return dict(version=VERSION, mode='owned_spawn', start_method='spawn',
                    input_buffer_bytes=INPUT_CAPACITY, response_buffer_bytes=RESPONSE_CAPACITY,
                    shared_memory_bytes=MEMORY_CAPACITY, concurrency=1,
                    startup_timeout_s=self.startup_timeout_s, report_timeout_s=self.report_timeout_s,
                    release_timeout_s=self.release_timeout_s, no_camera_or_storage_in_child=True,
                    commit_authority='host_feedback_revision_cas', os_process_start_hard_deadline=False)

    def build(self, item):
        if not self.lock.acquire(blocking=False):
            raise ReportWorkerError('report_worker_busy')
        try:
            if self.stop.is_set():
                raise ReportWorkerError('report_worker_cancelled')
            # Serialize inside the single slot: no unbounded queue of snapshots.
            facts = {key: item[key] for key in REPORT_INPUT_FIELDS}
            payload = dumps(facts, sort_keys=True).encode('utf-8')
            if not 0 < len(payload) <= INPUT_CAPACITY:
                raise ReportWorkerError('report_worker_input_capacity_exceeded')
            with self.state_lock:
                self.active_sid = facts['session_id']
                self.cancel.clear()
            try:
                if self.quarantined:
                    self._release('retry_quarantined_release')
                if self.process is None:
                    self._start()
                request = dict(ticket=uuid4().hex, length=len(payload),
                    session_id=facts['session_id'], feedback_revision=facts['feedback_revision'],
                    input_sha256=hashlib.sha256(payload).hexdigest())
                header = dumps(request).encode('utf-8')
                if len(header) > NOTIFICATION_CAPACITY:
                    raise ReportWorkerError('report_worker_request_capacity_exceeded')
                self.memory.buf[:len(payload)] = payload
                self.last_request = dict(request, pid=self.process.pid)
                started = time.perf_counter()
                self.pipe.send_bytes(header)
                notification = self._receive(self.report_timeout_s, 'report')
                length = notification.get('reply_length')
                if type(length) is not int or not 0 < length <= RESPONSE_CAPACITY:
                    raise ReportWorkerError('invalid_report_worker_response_length')
                response = bytes(self.memory.buf[INPUT_CAPACITY:INPUT_CAPACITY+length])
                if hashlib.sha256(response).hexdigest() != notification.get('reply_sha256'):
                    raise ReportWorkerError('report_worker_response_fingerprint_mismatch')
                result = json.loads(response)
                if not isinstance(result, dict):
                    raise ReportWorkerError('invalid_report_worker_response')
                for key in ('ticket', 'session_id', 'feedback_revision', 'input_sha256'):
                    if type(result.get(key)) is not type(request[key]) or result.get(key) != request[key]:
                        raise ReportWorkerError('report_worker_identity_mismatch')
                if result.get('ok') is not True:
                    raise ReportWorkerError('report_worker_build_failed')
                duration = result.get('compute_ms')
                if type(duration) not in (int, float) or not math.isfinite(duration) or duration < 0:
                    raise ReportWorkerError('invalid_report_worker_stage_duration')
                report = result['report']
                # Verify meaning, not merely the child echoing its envelope.
                # This pure, bounded check cannot invoke a model, storage or LLM.
                if not isinstance(report, dict) or digest(report) != digest(build_report(facts)):
                    raise ReportWorkerError('report_worker_fact_mismatch')
                self.warm = True
                return report, dict(report_compute_ms=duration,
                                    report_roundtrip_ms=1000*(time.perf_counter()-started))
            except Exception as exc:
                self._release(getattr(exc, 'code', type(exc).__name__))
                raise
            finally:
                if self.memory is not None and not self.quarantined:
                    self.memory.buf[:] = b'\0'*MEMORY_CAPACITY
                with self.state_lock:
                    self.active_sid = None
                    self.cancel.clear()
        finally:
            self.lock.release()
