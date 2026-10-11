from __future__ import annotations

import copy
import hashlib
from io import BytesIO
import os
from pathlib import Path
import queue
import sys
import threading
import time
from uuid import uuid4

from ..core import CORE
from app.domain import Context, digest, utc_now
from app.storage import Storage
from app.rehab_v2.cues import CueEvents
from app.rehab_v2.engine import ProtocolEngine
from app.rehab_v2.rounds import TrainingRounds
from app.rehab_v2.evidence import EvidenceAdapter
from app.rehab_v2.sessions import SessionError, SessionRepository, identifier
from app.rehab_v2.telemetry import SessionTelemetry, VERSION as DIAGNOSTICS_VERSION
from app.rehab_v2.resources import ComputeLease, ResourceBusy, ResourceUnavailable, compute_contract
from .pose_worker import IsolatedPoseWorker
from .report_worker import IsolatedReportWorker
from app.rehab_v2.reporting import build_report
from app.rehab_v2.storage_boundary import RehabStorageBoundary, StorageFault, classify_sqlite_fault


class StoreLease:
    """OS-released single-host lease; a second host must not recover a live draft."""
    def __init__(self, path):
        self.stream = Path(path).open('a+b')
        if self.stream.seek(0, 2) == 0:
            self.stream.write(b'1')
            self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.stream.close()
            raise SessionError('formal_session_store_already_owned', 503)

    def close(self):
        if not self.stream.closed:
            self.stream.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
            self.stream.close()


class Runtime:
    def __init__(self, item, compute_lease):
        self.context_owner = item['owner']
        plan = item['frozen_plan']['plan']
        engine_type = TrainingRounds if plan.get('submode') == 'training' else ProtocolEngine
        self.engine = engine_type(plan, source_epoch=item['source_epoch'], session_id=item['session_id'])
        self.adapter = EvidenceAdapter(plan['exercise_id'], plan.get('side', 'left'), max_gap_s=self.engine.plan['max_gap_s'])
        self.cues = CueEvents(item['session_id'])
        self.lock, self.finish_lock = threading.RLock(), threading.Lock()
        self.started = time.monotonic()
        self.control_epoch = item['control_epoch']
        self.terminal_epoch = item['terminal_epoch']
        self.compute_lease = compute_lease
        self.terminal_committed = False
        self.context = Context(1, 'rehab', item['source']['source_ref'], item['source']['source_kind'],
                               item['source']['usage_context'], item['session_id'], item['source_epoch'])
        self.telemetry = SessionTelemetry(item['source'].get('execution_trace_id'),
                                         item['session_id'], self.engine.spec['protocol_version'])


class SessionService:
    def __init__(self, database, plan_resolver, *, internal_replay=False, report_builder=None,
                 inference_provider=None, drain_timeout_s=2., plan_reader=None, report_executor=None):
        self.database = Path(database).resolve()
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.lease = StoreLease(str(self.database)+'.owner-lock')
        self.last_storage_fault = None
        try:
            self.storage = Storage(self.database)
            self.storage_boundary = RehabStorageBoundary(self.storage, self._storage_fault)
            self.repository = SessionRepository(self.storage_boundary)
            self.recovered = self.repository.recover_unfinished()
        except Exception as error:
            if hasattr(self, 'storage'):
                self.storage.close()
            self.lease.close()
            fault = classify_sqlite_fault(error)
            if fault is not None:
                raise fault from None
            raise
        self.plan_resolver, self.internal_replay = plan_resolver, internal_replay
        self.plan_reader = plan_reader
        self.report_builder = report_builder or self._report
        self.inference_provider = inference_provider
        self.drain_timeout_s = drain_timeout_s
        self.frames = queue.Queue(maxsize=1)
        self.guard = threading.RLock()
        self.controls = threading.BoundedSemaphore(8)
        self.runtimes = {}
        self.closed, self.worker_stop, self.inflight = False, threading.Event(), None
        self.resources_released = False
        self.worker_failure = None
        self.inference_worker = IsolatedPoseWorker()
        self.report_executor = report_executor if report_executor is not None else IsolatedReportWorker()
        # Local callable test hooks remain in-process; public default is owned.
        self.report_slots = threading.BoundedSemaphore(1)
        self.report_worker_failure = None
        self.latencies = {'control_ms': [], 'decode_ms': [], 'inference_ms': [],
                          'feature_ms': [], 'cue_ms': [], 'commit_ms': [], 'queue_wait_ms': []}
        self.report_stop = threading.Event()
        self.report_wake = threading.Event()
        self.worker = threading.Thread(target=self._run, name='rehab-v2-vision', daemon=True)
        self.worker.start()
        self.report_worker = threading.Thread(target=self._run_reports, name='rehab-v2-reports', daemon=True)
        self.report_worker.start()

    def _storage_fault(self, fault):
        # Immutable last-observed metadata, not a health probe or saved fact.
        # Callback runs after Storage has rolled back and returned the error.
        self.last_storage_fault = fault.public

    def _run_reports(self):
        # Durable pending rows are the queue. An unfinished report never holds
        # up a control request or determines whether a training fact exists.
        first = True
        while not self.report_stop.is_set():
            try:
                work = self.repository.report_work(include_failed=first)
                first = False
                busy = False
                for owner, sid in work:
                    if self.report_stop.is_set():
                        break
                    busy = self.rebuild_report(owner, sid)['state'] == 'running' or busy
                self.report_worker_failure = None
                if len(work) == 16 and not busy:
                    continue
            except Exception as exc:
                # SQLite failures must not be reported as successful rebuilds.
                # Durable pending rows remain recoverable at the next start.
                self.report_worker_failure = getattr(exc, 'code', type(exc).__name__)
            self.report_wake.wait(.2)
            self.report_wake.clear()

    def _release_terminal_compute(self):
        with self.guard:
            # A cancellation request is not an exit receipt. Keep the host
            # lease if the owned native process could not be released.
            if self.inference_worker.quarantined:
                return
            for sid, runtime in self.runtimes.items():
                if (runtime.terminal_committed and runtime.engine.run_state == 'ended'
                        and (not self.inflight or self.inflight['sid'] != sid)):
                    runtime.compute_lease.close()

    def _prune_terminal_runtimes(self):
        self._release_terminal_compute()
        # Keep the one in-flight object alive even if its fact is finalized.
        ended = [sid for sid, runtime in self.runtimes.items() if runtime.engine.run_state == 'ended'
                 and not runtime.compute_lease.held
                 and (not self.inflight or self.inflight['sid'] != sid)]
        for sid in ended[:-32]:
            del self.runtimes[sid]

    def _bounded(self, fn):
        if not self.controls.acquire(blocking=False):
            raise SessionError('control_queue_full', 429)
        started = time.perf_counter()
        try:
            return fn()
        finally:
            self.latencies['control_ms'] = (self.latencies['control_ms']+[1000*(time.perf_counter()-started)])[-512:]
            self.controls.release()

    def create(self, owner, request):
        started = time.perf_counter()
        def create():
            key = identifier(request.get('idempotency_key'))
            fingerprint = digest(request)
            # Lookup precedes plan revision/current eligibility checks.
            found = self.repository.lookup_create(owner, key, fingerprint)
            if found:
                return found
            if request.get('consent') is not True:
                raise SessionError('camera_analysis_consent_required', 400)
            with self.guard:
                if self.closed:
                    raise SessionError('service_closed', 503)
                if not self.worker.is_alive() or self.worker_failure:
                    raise SessionError('formal_inference_worker_unavailable', 503)
                self._prune_terminal_runtimes()
                active = [sid for sid, runtime in self.runtimes.items() if runtime.engine.run_state != 'ended']
                if active:
                    raise SessionError('formal_camera_capacity_reached', 429)
                frozen = self.plan_resolver(owner, copy.deepcopy(request))
                if not isinstance(frozen, dict) or not isinstance(frozen.get('plan'), dict):
                    raise SessionError('invalid_frozen_plan', 400)
                if not all(k in frozen for k in ('plan_id', 'plan_revision', 'entry_key', 'reference')):
                    raise SessionError('missing_plan_provenance', 400)
                if (not isinstance(frozen['plan_id'], str) or not 1 <= len(frozen['plan_id']) <= 128
                        or type(frozen['plan_revision']) is not int or frozen['plan_revision'] < 1
                        or not isinstance(frozen['reference'], dict)):
                    raise SessionError('invalid_plan_provenance', 400)
                plan = frozen['plan']
                if plan.get('submode') not in ('assessment', 'training'):
                    raise SessionError('explicit_session_submode_required', 400)
                # Validate protocol before persisting; does not invent dosage.
                validator = TrainingRounds if plan.get('submode') == 'training' else ProtocolEngine
                checked_engine = validator(plan, source_epoch='validation')
                if plan.get('needs_companion') and request.get('companion_confirmed') is not True:
                    raise SessionError('required_companion_confirmation_missing')
                checked = checked_engine.spec
                frozen['plan'] = checked_engine.plan  # Freeze actual engineering defaults too.
                if frozen['entry_key'] != checked['exercise_id']+':'+checked['side']:
                    raise SessionError('plan_entry_does_not_match_action', 400)
                frozen['protocol'] = checked
                source = dict(source_ref='internal-replay' if self.internal_replay else 'browser-camera',
                              source_kind='SYNTHETIC' if self.internal_replay else 'LIVE_CAMERA',
                              usage_context='TEST' if self.internal_replay else 'SELF_USE',
                              input_mode='trusted_internal_evidence' if self.internal_replay else 'server_inferred_jpeg',
                              consent_at=utc_now(), time_basis='mapped_source_seconds',
                              no_exposure_synchronization_claim=True,
                              execution_trace_id=uuid4().hex, diagnostics_version=DIAGNOSTICS_VERSION)
                source['report_execution_contract'] = self._report_execution_contract()
                source['compute_execution_contract'] = compute_contract()
                source['storage_execution_contract'] = self.storage_boundary.contract
                if not self.internal_replay and self.inference_provider is None:
                    source['inference_execution_contract'] = self.inference_worker.contract
                if frozen.get('progress_scope') is not None:
                    from app.assessment_batches import scope_key
                    scope = scope_key(frozen['progress_scope'])
                    if (scope['source_kind'] != source['source_kind'] or scope['usage_context'] != source['usage_context']
                            or scope['participant_id'] != frozen['plan'].get('participant_id')):
                        raise SessionError('actual_input_does_not_match_plan_scope')
                compute_lease = ComputeLease('formal')
                try:
                    compute_lease.acquire()
                except (ResourceBusy, ResourceUnavailable) as error:
                    raise SessionError(error.code, 503) from None
                try:
                    item = self.repository.create(owner, key, fingerprint, frozen, source)
                    self.runtimes[item['session_id']] = Runtime(item, compute_lease)
                except BaseException:
                    compute_lease.close()
                    raise
                return item
        result = self._bounded(create)
        runtime = self.runtimes.get(result['session_id'])
        if runtime:
            runtime.telemetry.observe('create_request_ms', 1000*(time.perf_counter()-started))
        return result

    def _session_operation(self, owner, sid, stage, fn):
        # Authenticate before reading or writing per-session diagnostic state.
        self.repository.get(owner, sid)
        runtime = self.runtimes.get(sid)
        started = time.perf_counter()
        try:
            return self._bounded(fn)
        finally:
            if runtime:
                duration = 1000*(time.perf_counter()-started)
                runtime.telemetry.observe(stage, duration)
                runtime.telemetry.observe('control_ms', duration)

    def _runtime(self, owner, sid):
        item = self.repository.get(owner, sid)
        runtime = self.runtimes.get(sid)
        if runtime is None:
            raise SessionError('session_not_running')
        return item, runtime

    def submit_jpeg(self, owner, sid, event_id, seq, encoded):
        request_started = time.perf_counter()
        if self.internal_replay:
            raise SessionError('replay_host_does_not_accept_camera_frames', 400)
        if not isinstance(encoded, bytes) or not 0 < len(encoded) <= 512*1024:
            raise SessionError('frame_size_exceeded', 413)
        # Header-size check before decoder allocation; JPEG only, no arbitrary landmarks.
        from PIL import Image
        try:
            with Image.open(BytesIO(encoded)) as image:
                if image.format != 'JPEG' or min(image.size) < 32 or image.width*image.height > 1920*1080:
                    raise SessionError('unsupported_frame_dimensions_or_format', 400)
                image.verify()
        except SessionError:
            raise
        except Exception:
            raise SessionError('invalid_jpeg_frame', 400)
        item, runtime = self._runtime(owner, sid)
        if self.closed or not self.worker.is_alive() or self.worker_failure:
            raise SessionError('formal_inference_worker_unavailable', 503)
        fingerprint = digest(dict(event_id=event_id, seq=seq, image_sha256=hashlib.sha256(encoded).hexdigest()))
        with self.guard, runtime.lock:
            accepted = self.repository.accept_frame(owner, sid, event_id, seq, fingerprint)
            if accepted['duplicate']:
                runtime.telemetry.event('duplicate', seq=seq)
                return dict(status=accepted['status'], duplicate=True, seq=seq)
            received = time.monotonic()
            frame = dict(owner=owner, sid=sid, event_id=event_id, seq=seq, encoded=encoded,
                         received=received, source_time_s=received-runtime.started,
                         control_epoch=runtime.control_epoch, terminal_epoch=runtime.terminal_epoch)
            if self.frames.full():
                try:
                    previous = self.frames.get_nowait()
                except queue.Empty:
                    previous = None
                if previous is not None:
                    previous_runtime = self.runtimes[previous['sid']]
                    previous_runtime.engine.note_input_gap(previous['seq'], previous['source_time_s'], 'latest_frame_replaced')
                    self.repository.checkpoint(previous['owner'], previous['sid'], previous_runtime.engine.summary(),
                                               seq=previous['seq'], frame_status='dropped', reason='latest_frame_replaced')
                    previous_runtime.telemetry.event('latest_replaced', seq=previous['seq'])
                    self.frames.task_done()
            self.frames.put_nowait(frame)
            runtime.telemetry.event('accepted', seq=seq, control_epoch=runtime.control_epoch,
                                    terminal_epoch=runtime.terminal_epoch)
            runtime.telemetry.arrival('accepted', received, queue_depth=1)
            runtime.telemetry.observe('frame_request_ms', 1000*(time.perf_counter()-request_started))
            return dict(status='accepted', duplicate=False, seq=seq, accepted_last_seq=accepted['session']['accepted_last_seq'])

    def submit_evidence(self, owner, sid, event_id, evidence):
        """Only the internal deterministic replay harness can submit landmark evidence."""
        if not self.internal_replay:
            raise SessionError('external_landmark_evidence_forbidden', 400)
        item, runtime = self._runtime(owner, sid)
        from dataclasses import asdict, replace
        evidence = replace(evidence, source_epoch=item['source_epoch'], source_ref='internal-replay')
        with runtime.lock:
            accepted = self.repository.accept_frame(owner, sid, event_id, evidence.seq, digest(asdict(evidence)))
            if accepted['duplicate']:
                runtime.telemetry.event('duplicate', seq=evidence.seq)
                return accepted
            runtime.telemetry.event('accepted', seq=evidence.seq)
            runtime.telemetry.arrival('accepted', time.monotonic())
            with runtime.telemetry.span('rules_ms'):
                runtime.engine.process(evidence)
            with runtime.telemetry.span('cue_ms'):
                cue = runtime.cues.update(runtime.engine, evidence, emission_monotonic=time.monotonic())
            with runtime.telemetry.span('checkpoint_ms'):
                result = self.repository.checkpoint(owner, sid, runtime.engine.summary(), seq=evidence.seq,
                                                    frame_status='processed', cue=cue)
            runtime.telemetry.event('processed', seq=evidence.seq)
            runtime.telemetry.arrival('processed', time.monotonic())
            return result

    def _infer(self, value, runtime):
        if self.inference_provider:
            return self.inference_provider(value, runtime)
        pose, durations = self.inference_worker.infer(value, runtime)
        for key, duration in durations.items():
            self.latencies[key].append(duration)
            runtime.telemetry.observe(key, duration)
        return pose  # Do not mutate EMA before checking the control epoch.

    def _run(self):
        try:
            self._run_frames()
        except Exception as exc:
            # Persistence may be unavailable: do not pretend a failure fact
            # was saved, and do not accept new work into a dead frame consumer.
            self.worker_failure = getattr(exc, 'code', type(exc).__name__)
        finally:
            try:
                self.inference_worker.close()
                self._release_terminal_compute()
            except Exception as exc:
                self.worker_failure = getattr(exc, 'code', type(exc).__name__)

    def _run_frames(self):
        while not self.worker_stop.is_set():
            try:
                value = self.frames.get(timeout=.05)
            except queue.Empty:
                # A disconnected sender cannot leave a formal draft running
                # forever. The explicit maximum is backend-only, not a dose.
                for sid, runtime in list(self.runtimes.items()):
                    if runtime.engine.run_state != 'ended' and time.monotonic()-runtime.started > 1200:
                        try:
                            self.finish(runtime.context_owner, sid, dict(idempotency_key='source-duration-limit',
                                expected_revision=self.repository.get(runtime.context_owner, sid)['revision'],
                                reason='interrupted'))
                        except SessionError:
                            pass
                continue
            runtime = self.runtimes[value['sid']]
            with self.guard:
                self.inflight = value
            try:
                with runtime.lock:
                    item = self.repository.get(value['owner'], value['sid'])
                    if item['persistence_state'] == 'finalized':
                        runtime.telemetry.event('terminal_discarded', seq=value['seq'])
                        continue
                    if value['control_epoch'] != runtime.control_epoch or value['terminal_epoch'] != runtime.terminal_epoch:
                        self.repository.checkpoint(value['owner'], value['sid'], runtime.engine.summary(),
                            seq=value['seq'], frame_status='dropped', reason='control_or_terminal_epoch_changed')
                        runtime.telemetry.event('epoch_discarded', seq=value['seq'])
                        continue
                waiting = 1000*(time.monotonic()-value['received'])
                self.latencies['queue_wait_ms'].append(waiting)
                runtime.telemetry.observe('queue_wait_ms', waiting)
                with runtime.telemetry.span('pose_roundtrip_ms'):
                    evidence = self._infer(value, runtime)
                runtime.telemetry.observe('pose_result_age_ms', 1000*(time.monotonic()-value['received']))
                with runtime.lock:
                    item = self.repository.get(value['owner'], value['sid'])
                    if item['persistence_state'] == 'finalized':
                        runtime.telemetry.event('terminal_discarded', seq=value['seq'])
                        continue  # Frozen fact and frame audit remain immutable after terminal boundary.
                    if value['control_epoch'] != runtime.control_epoch or value['terminal_epoch'] != runtime.terminal_epoch:
                        self.repository.checkpoint(value['owner'], value['sid'], runtime.engine.summary(),
                                                   seq=value['seq'], frame_status='dropped', reason='control_or_terminal_epoch_changed')
                        runtime.telemetry.event('epoch_discarded', seq=value['seq'])
                        continue
                    from app.domain import PoseFrame
                    if isinstance(evidence, PoseFrame):
                        started = time.perf_counter()
                        evidence = runtime.adapter.analyze(evidence,
                            processing_age_ms=1000*(time.monotonic()-value['received']))
                        self.latencies['feature_ms'].append(1000*(time.perf_counter()-started))
                        runtime.telemetry.observe('feature_ms', 1000*(time.perf_counter()-started))
                    with runtime.telemetry.span('rules_ms'):
                        runtime.engine.process(evidence)
                    started = time.perf_counter()
                    cue = runtime.cues.update(runtime.engine, evidence, emission_monotonic=time.monotonic())
                    self.latencies['cue_ms'].append(1000*(time.perf_counter()-started))
                    runtime.telemetry.observe('cue_ms', 1000*(time.perf_counter()-started))
                    started = time.perf_counter()
                    self.repository.checkpoint(value['owner'], value['sid'], runtime.engine.summary(),
                                               seq=value['seq'], frame_status='processed', cue=cue)
                    self.latencies['commit_ms'].append(1000*(time.perf_counter()-started))
                    runtime.telemetry.observe('checkpoint_ms', 1000*(time.perf_counter()-started))
                    runtime.telemetry.event('processed', seq=value['seq'])
                    runtime.telemetry.arrival('processed', time.monotonic())
                    runtime.telemetry.observe('result_age_ms', 1000*(time.monotonic()-value['received']))
            except Exception as exc:
                if isinstance(exc, StorageFault):
                    # Persistence failed, not the camera or motion evidence.
                    # Do not attempt to save memory-only progress as input_failed.
                    raise
                runtime.telemetry.event('inference_cancelled' if getattr(exc, 'code', '') == 'pose_worker_cancelled'
                                        else 'input_failed', seq=value['seq'])
                if getattr(exc, 'code', '').endswith('_timeout'):
                    runtime.telemetry.event('timeout', seq=value['seq'])
                with runtime.lock:
                    item = self.repository.get(value['owner'], value['sid'])
                    if item['persistence_state'] != 'finalized':
                        if (self.worker_stop.is_set() or value['control_epoch'] != runtime.control_epoch
                                or value['terminal_epoch'] != runtime.terminal_epoch):
                            self.repository.checkpoint(value['owner'], value['sid'], runtime.engine.summary(),
                                seq=value['seq'], frame_status='dropped', reason='control_or_terminal_epoch_changed')
                            runtime.telemetry.event('epoch_discarded', seq=value['seq'])
                            continue  # A failed old inference cannot terminate a resumed context.
                        runtime.engine.invalidate('input_failed')
                        runtime.cues.cancel('input_failed')
                        self.repository.checkpoint(value['owner'], value['sid'], runtime.engine.summary(),
                                                   seq=value['seq'], frame_status='failed', reason=getattr(exc, 'code', type(exc).__name__))
                        item = self.repository.freeze(value['owner'], value['sid'], 'worker-input-failure',
                            digest(dict(seq=value['seq'], error_type=type(exc).__name__)), item['revision'], 'input_failed')
                        runtime.engine.finish(item['requested_end_reason'])
                        with runtime.telemetry.span('final_commit_ms'):
                            self.repository.finalize(value['owner'], value['sid'], runtime.engine.summary(), item['requested_end_reason'])
                        runtime.telemetry.event('commit_success')
                        runtime.terminal_committed = True
                        runtime.terminal_epoch += 1
                        self.report_wake.set()
            finally:
                if sys.exc_info()[0] is not None:
                    runtime.telemetry.event('background_failure', seq=value['seq'])
                with self.guard:
                    self.inflight = None
                    self._release_terminal_compute()
                self.frames.task_done()
                for key in self.latencies:
                    self.latencies[key] = self.latencies[key][-512:]
    def control(self, owner, sid, operation, request):
        if operation not in ('pause', 'resume'):
            raise SessionError('unknown_control', 400)
        def control():
            key, fingerprint = identifier(request.get('idempotency_key')), digest(request)
            found = self.repository.lookup_operation(owner, sid, operation, key, fingerprint)
            if found:
                return found
            _, runtime = self._runtime(owner, sid)
            with runtime.lock:
                candidate = copy.deepcopy(runtime.engine)
                if operation == 'pause':
                    candidate.pause()
                else:
                    if isinstance(candidate, TrainingRounds):
                        source_time = (candidate.last_t or 0.) if self.internal_replay else time.monotonic()-runtime.started
                        candidate.resume(preserve_baseline=False, source_time_s=source_time)
                    else:
                        candidate.resume(preserve_baseline=False)
                receipt = self.repository.control(owner, sid, operation, key, fingerprint,
                                                  request.get('expected_revision'), candidate.summary())
                runtime.engine = candidate
                if operation == 'resume':
                    runtime.adapter = EvidenceAdapter(candidate.spec['exercise_id'], candidate.spec['side'],
                                                       max_gap_s=candidate.plan['max_gap_s'])
                runtime.control_epoch += 1
                runtime.cues.cancel(operation)
                return receipt
        return self._session_operation(owner, sid, operation+'_request_ms', control)

    def finish(self, owner, sid, request):
        return self._session_operation(owner, sid, 'finish_request_ms', lambda: self._finish(owner, sid, request))

    def _finish(self, owner, sid, request):
        key, fingerprint = identifier(request.get('idempotency_key')), digest(request)
        found = self.repository.lookup_operation(owner, sid, 'finish', key, fingerprint)
        if found and found.get('status') == 'finalized':
            return found
        item = self.repository.get(owner, sid)
        if item['persistence_state'] == 'finalized':
            self.repository.freeze(owner, sid, key, fingerprint, request.get('expected_revision'), request.get('reason', 'user_stopped'))
            return item['canonical_commit']
        _, runtime = self._runtime(owner, sid)
        with runtime.finish_lock:
            item = self.repository.freeze(owner, sid, key, fingerprint, request.get('expected_revision'), request.get('reason', 'user_stopped'))
            if item['persistence_state'] == 'finalized':
                return item['canonical_commit']
            # Drain bounded in-flight/retained frames outside the runtime/control lock.
            deadline = time.monotonic()+self.drain_timeout_s
            while time.monotonic() < deadline:
                if self.repository.pending_frames(owner, sid) == 0:
                    break
                time.sleep(.01)
            with runtime.lock:
                latest = self.repository.get(owner, sid)
                if latest['persistence_state'] == 'finalized':
                    return latest['canonical_commit']
                runtime.engine.finish(item['requested_end_reason'])
                runtime.cues.cancel('finish')
                pending = self.repository.pending_frames(owner, sid)
                with runtime.telemetry.span('final_commit_ms'):
                    receipt = self.repository.finalize(owner, sid, runtime.engine.summary(), item['requested_end_reason'])
                runtime.telemetry.event('commit_success')
                runtime.terminal_committed = True
                if pending:
                    runtime.telemetry.event('unprocessed_at_finish', count=pending)
                runtime.terminal_epoch += 1
            self.inference_worker.cancel_current(sid)  # Only after the immutable terminal fact exists.
            self._release_terminal_compute()
            self.report_wake.set()
            return receipt

    def feedback(self, owner, sid, request):
        key, fingerprint = identifier(request.get('idempotency_key')), digest(request)
        found = self.repository.lookup_operation(owner, sid, 'feedback', key, fingerprint)
        if found:
            return found
        result = self._session_operation(owner, sid, 'feedback_request_ms', lambda: self.repository.feedback(owner, sid, key, fingerprint,
                               request.get('expected_revision'), request.get('feedback', {})))
        self.report_wake.set()
        return result

    def get(self, owner, sid):
        item = self.repository.get(owner, sid)
        item['backend_execution'] = dict(frame_consumer_alive=self.worker.is_alive(),
            failure=self.worker_failure, report_consumer_alive=self.report_worker.is_alive(),
            report_failure=self.report_worker_failure,
            report_execution_mode=self._report_execution_contract()['mode'],
            last_storage_fault=self.last_storage_fault,
            resources_released=self.resources_released)
        item['plan_contribution'] = self.repository.plan_contribution(owner, sid)
        runtime = self.runtimes.get(sid)
        if runtime and item.get('current_cue'):
            with runtime.lock:
                age = 1000*(time.monotonic()-(runtime.cues.last_emission or time.monotonic()))
                source_time = runtime.engine.last_t if self.internal_replay else time.monotonic()-runtime.started
                current = runtime.cues.query(source_time_s=source_time or 0.,
                    emission_age_ms=age, phase=runtime.engine.phase, calibration_epoch=runtime.engine.calibration_epoch)
                item['current_cue'] = current
        return item

    def history(self, owner, *, limit=20, before=None):
        return self.repository.history(owner, limit=limit, before=before)

    def diagnostics(self, owner, sid):
        item = self.repository.get(owner, sid)  # No metrics before authorization.
        runtime = self.runtimes.get(sid)
        if runtime is None:
            return dict(version=DIAGNOSTICS_VERSION, available=False,
                        reason='runtime_not_retained_or_host_restarted',
                        trace_id=item['source'].get('execution_trace_id'), session_id=sid,
                        job_id=None, protocol_version=item['frozen_plan']['protocol']['protocol_version'],
                        stages=None, counters=None)
        result = runtime.telemetry.snapshot()
        with self.frames.mutex:
            retained = sum(1 for value in self.frames.queue if value['sid'] == sid)
        active = self.inflight
        result['backlog'] = dict(retained_frames=retained,
            in_flight=bool(active and active['sid'] == sid),
            durable_pending_frames=self.repository.pending_frames(owner, sid), retained_capacity=1)
        result['memory'] = dict(host_rss_bytes=None, owned_pose_rss_bytes=None, owned_report_rss_bytes=None,
                                measurement='current_process_rss_not_peak_or_device_memory')
        try:
            import psutil
            result['memory']['host_rss_bytes'] = psutil.Process(os.getpid()).memory_info().rss
            process = self.inference_worker.process
            if runtime.engine.run_state != 'ended' and process is not None and process.is_alive():
                result['memory']['owned_pose_rss_bytes'] = psutil.Process(process.pid).memory_info().rss
            process = self.report_executor.process
            if (self.report_executor.active_sid == sid and process is not None and process.is_alive()):
                result['memory']['owned_report_rss_bytes'] = psutil.Process(process.pid).memory_info().rss
        except Exception:
            pass  # Missing observation stays null; do not fabricate zero bytes.
        result['consumers'] = dict(frame_alive=self.worker.is_alive(), frame_failure=self.worker_failure,
                                   report_alive=self.report_worker.is_alive(), report_failure=self.report_worker_failure,
                                   report_execution_mode=self._report_execution_contract()['mode'])
        result['last_storage_fault'] = self.last_storage_fault
        return result

    def plan(self, owner, plan_id):
        if self.plan_reader is None:
            raise SessionError('host_plan_reader_not_configured', 503)
        return self._bounded(lambda: self.plan_reader(owner, plan_id))

    def commit(self, owner, sid):
        item = self.repository.get(owner, sid)
        return dict(session_id=sid, persistence_state=item['persistence_state'],
                    receipt=item['canonical_commit'], derived_report_state=item['derived_report_state'],
                    plan_contribution=self.repository.plan_contribution(owner, sid))

    @staticmethod
    def _report(item):
        return build_report(item)

    def _report_execution_contract(self):
        if self.report_builder is self._report:
            return self.report_executor.contract
        return dict(mode='trusted_local_callable', concurrency=1, hard_cancellation=False)

    def rebuild_report(self, owner, sid):
        item = self.repository.get(owner, sid)
        if item['persistence_state'] != 'finalized':
            raise SessionError('report_requires_finalized_session', 409)
        if self.closed or self.report_stop.is_set():
            raise SessionError('service_closed', 503)
        runtime = self.runtimes.get(sid)
        if not self.report_slots.acquire(blocking=False):
            if runtime:
                runtime.telemetry.event('report_busy')
            return dict(state='running')
        started = time.perf_counter()
        try:
            if self.closed or self.report_stop.is_set():
                raise SessionError('service_closed', 503)
            if self.report_builder is self._report:
                report, durations = self.report_executor.build(item)
                if runtime:
                    for stage, duration in durations.items():
                        runtime.telemetry.observe(stage, duration)
            else:
                report = self.report_builder(item)
            saved = self.repository.report_state(owner, sid, 'ready', report,
                expected_feedback_revision=item['feedback_revision'])
            if runtime:
                runtime.telemetry.event('report_ready' if saved else 'report_superseded')
            return dict(state='ready' if saved else 'pending_newer_feedback')
        except Exception as exc:
            error = getattr(exc, 'code', type(exc).__name__)
            if runtime:
                runtime.telemetry.event('report_failed')
                if error.endswith('_timeout'):
                    runtime.telemetry.event('report_timeout')
                elif error == 'report_worker_cancelled':
                    runtime.telemetry.event('report_cancelled')
            saved = self.repository.report_state(owner, sid, 'failed', error=error,
                expected_feedback_revision=item['feedback_revision'])
            return dict(state='failed' if saved else 'pending_newer_feedback', error=error)
        finally:
            if runtime:
                runtime.telemetry.observe('report_ms', 1000*(time.perf_counter()-started))
            self.report_slots.release()

    def close(self, *, graceful=True):
        if self.resources_released:
            return
        self.closed = True
        if graceful:
            for sid, runtime in list(self.runtimes.items()):
                item = self.repository.get(self.storage._call(lambda conn: conn.execute(
                    'SELECT owner FROM rehab_v2_sessions WHERE id=?', (sid,)).fetchone()[0]), sid)
                if item['persistence_state'] == 'draft':
                    self.finish(item['owner'], sid, dict(idempotency_key='host-close', expected_revision=item['revision'], reason='interrupted'))
        self.worker_stop.set()
        self.inference_worker.request_stop()
        self.report_stop.set()
        self.report_executor.request_stop()
        self.report_wake.set()
        self.worker.join(timeout=max(3., self.drain_timeout_s+1.))
        self.report_worker.join(timeout=3.)
        if self.worker.is_alive() or self.report_worker.is_alive():
            # Do not close SQLite while its owning inference thread may still write.
            raise SessionError('vision_shutdown_not_confirmed', 503)
        self.inference_worker.close()
        self.report_executor.close()
        # An explicit local rebuild may run outside the durable consumer thread.
        if not self.report_slots.acquire(timeout=3.):
            raise SessionError('report_shutdown_not_confirmed', 503)
        self.report_slots.release()  # Closed flag prevents any subsequent writer.
        # Discard only this host's volatile pending JPEGs. Durable accepted
        # rows remain recorded by finalize or subsequent restart recovery.
        while True:
            try:
                self.frames.get_nowait()
            except queue.Empty:
                break
            self.frames.task_done()
        self.storage.close()
        self.lease.close()
        with self.guard:
            for runtime in self.runtimes.values():
                runtime.compute_lease.close()
        self.resources_released = True
