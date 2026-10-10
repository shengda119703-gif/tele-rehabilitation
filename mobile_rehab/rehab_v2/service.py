from __future__ import annotations

import copy
import hashlib
from io import BytesIO
import os
from pathlib import Path
import queue
import threading
import time

from ..core import CORE
from app.domain import Context, FramePacket, digest, utc_now
from app.storage import Storage
from app.rehab_v2.cues import CueEvents
from app.rehab_v2.engine import ProtocolEngine
from app.rehab_v2.rounds import TrainingRounds
from app.rehab_v2.evidence import EvidenceAdapter
from app.rehab_v2.sessions import SessionError, SessionRepository, identifier


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
    def __init__(self, item):
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
        self.context = Context(1, 'rehab', item['source']['source_ref'], item['source']['source_kind'],
                               item['source']['usage_context'], item['session_id'], item['source_epoch'])


class SessionService:
    def __init__(self, database, plan_resolver, *, internal_replay=False, report_builder=None,
                 inference_provider=None, drain_timeout_s=2.):
        self.database = Path(database).resolve()
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.lease = StoreLease(str(self.database)+'.owner-lock')
        try:
            self.storage = Storage(self.database)
            self.repository = SessionRepository(self.storage)
            self.recovered = self.repository.recover_unfinished()
        except Exception:
            if hasattr(self, 'storage'):
                self.storage.close()
            self.lease.close()
            raise
        self.plan_resolver, self.internal_replay = plan_resolver, internal_replay
        self.report_builder = report_builder or self._report
        self.inference_provider = inference_provider
        self.drain_timeout_s = drain_timeout_s
        self.frames = queue.Queue(maxsize=1)
        self.guard = threading.RLock()
        self.controls = threading.BoundedSemaphore(8)
        self.runtimes = {}
        self.closed, self.worker_stop, self.inflight = False, threading.Event(), None
        self.vision = None
        self.latencies = {'control_ms': [], 'decode_ms': [], 'inference_ms': [],
                          'feature_ms': [], 'cue_ms': [], 'commit_ms': [], 'queue_wait_ms': []}
        self.report_stop = threading.Event()
        self.report_wake = threading.Event()
        self.worker = threading.Thread(target=self._run, name='rehab-v2-vision', daemon=True)
        self.worker.start()
        self.report_worker = threading.Thread(target=self._run_reports, name='rehab-v2-reports', daemon=True)
        self.report_worker.start()

    def _run_reports(self):
        # Durable pending rows are the queue. An unfinished report never holds
        # up a control request or determines whether a training fact exists.
        first = True
        while not self.report_stop.is_set():
            try:
                work = self.repository.report_work(include_failed=first)
                first = False
                for owner, sid in work:
                    if self.report_stop.is_set():
                        break
                    self.rebuild_report(owner, sid)
                if len(work) == 16:
                    continue
            except Exception:
                # SQLite failures must not be reported as successful rebuilds.
                # Durable pending rows remain recoverable at the next start.
                pass
            self.report_wake.wait(.2)
            self.report_wake.clear()

    def _prune_terminal_runtimes(self):
        # Keep the one in-flight object alive even if its fact is finalized.
        ended = [sid for sid, runtime in self.runtimes.items() if runtime.engine.run_state == 'ended'
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
                self._prune_terminal_runtimes()
                active = [sid for sid, runtime in self.runtimes.items() if runtime.engine.run_state != 'ended']
                if active:
                    raise SessionError('formal_camera_capacity_reached', 429)
                frozen = self.plan_resolver(owner, copy.deepcopy(request))
                if not isinstance(frozen, dict) or not isinstance(frozen.get('plan'), dict):
                    raise SessionError('invalid_frozen_plan', 400)
                if not all(k in frozen for k in ('plan_id', 'plan_revision', 'entry_key', 'reference')):
                    raise SessionError('missing_plan_provenance', 400)
                plan = frozen['plan']
                # Validate protocol before persisting; does not invent dosage.
                validator = TrainingRounds if plan.get('submode') == 'training' else ProtocolEngine
                checked = validator(plan, source_epoch='validation').spec
                frozen['protocol'] = checked
                source = dict(source_ref='internal-replay' if self.internal_replay else 'browser-camera',
                              source_kind='SYNTHETIC' if self.internal_replay else 'LIVE_CAMERA',
                              usage_context='TEST' if self.internal_replay else 'SELF_USE',
                              input_mode='trusted_internal_evidence' if self.internal_replay else 'server_inferred_jpeg',
                              consent_at=utc_now(), time_basis='mapped_source_seconds',
                              no_exposure_synchronization_claim=True)
                item = self.repository.create(owner, key, fingerprint, frozen, source)
                self.runtimes[item['session_id']] = Runtime(item)
                return item
        return self._bounded(create)

    def _runtime(self, owner, sid):
        item = self.repository.get(owner, sid)
        runtime = self.runtimes.get(sid)
        if runtime is None:
            raise SessionError('session_not_running')
        return item, runtime

    def submit_jpeg(self, owner, sid, event_id, seq, encoded):
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
        fingerprint = digest(dict(event_id=event_id, seq=seq, image_sha256=hashlib.sha256(encoded).hexdigest()))
        with self.guard, runtime.lock:
            accepted = self.repository.accept_frame(owner, sid, event_id, seq, fingerprint)
            if accepted['duplicate']:
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
                    previous_runtime.engine.gap = True
                    self.repository.checkpoint(previous['owner'], previous['sid'], previous_runtime.engine.summary(),
                                               seq=previous['seq'], frame_status='dropped', reason='latest_frame_replaced')
                    self.frames.task_done()
            self.frames.put_nowait(frame)
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
                return accepted
            runtime.engine.process(evidence)
            cue = runtime.cues.update(runtime.engine, evidence, emission_monotonic=time.monotonic())
            return self.repository.checkpoint(owner, sid, runtime.engine.summary(), seq=evidence.seq,
                                              frame_status='processed', cue=cue)

    def _infer(self, value, runtime):
        if self.inference_provider:
            return self.inference_provider(value, runtime)
        import cv2
        import numpy as np
        from app.vision import VisionWorker
        started = time.perf_counter()
        image = cv2.imdecode(np.frombuffer(value['encoded'], np.uint8), cv2.IMREAD_COLOR)
        if image is None or image.shape[0]*image.shape[1] > 1920*1080:
            raise ValueError('invalid_decoded_frame')
        self.latencies['decode_ms'].append(1000*(time.perf_counter()-started))
        if self.vision is None:
            self.vision = VisionWorker(start_thread=False)
        packet = FramePacket(runtime.context, value['seq'], value['source_time_s'], value['received'], utc_now(), image)
        started = time.perf_counter()
        pose = self.vision.infer(packet, backend='yolo', side=runtime.engine.spec['side'])
        self.latencies['inference_ms'].append(1000*(time.perf_counter()-started))
        return pose  # Do not mutate EMA before checking the control epoch.

    def _run(self):
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
                self.latencies['queue_wait_ms'].append(1000*(time.monotonic()-value['received']))
                evidence = self._infer(value, runtime)
                with runtime.lock:
                    item = self.repository.get(value['owner'], value['sid'])
                    if item['persistence_state'] == 'finalized':
                        continue  # Frozen fact and frame audit remain immutable after terminal boundary.
                    if value['control_epoch'] != runtime.control_epoch or value['terminal_epoch'] != runtime.terminal_epoch:
                        self.repository.checkpoint(value['owner'], value['sid'], runtime.engine.summary(),
                                                   seq=value['seq'], frame_status='dropped', reason='control_or_terminal_epoch_changed')
                        continue
                    from app.domain import PoseFrame
                    if isinstance(evidence, PoseFrame):
                        started = time.perf_counter()
                        evidence = runtime.adapter.analyze(evidence,
                            processing_age_ms=1000*(time.monotonic()-value['received']))
                        self.latencies['feature_ms'].append(1000*(time.perf_counter()-started))
                    runtime.engine.process(evidence)
                    started = time.perf_counter()
                    cue = runtime.cues.update(runtime.engine, evidence, emission_monotonic=time.monotonic())
                    self.latencies['cue_ms'].append(1000*(time.perf_counter()-started))
                    started = time.perf_counter()
                    self.repository.checkpoint(value['owner'], value['sid'], runtime.engine.summary(),
                                               seq=value['seq'], frame_status='processed', cue=cue)
                    self.latencies['commit_ms'].append(1000*(time.perf_counter()-started))
            except Exception as exc:
                with runtime.lock:
                    item = self.repository.get(value['owner'], value['sid'])
                    if item['persistence_state'] != 'finalized':
                        runtime.engine.invalidate('input_failed')
                        runtime.cues.cancel('input_failed')
                        self.repository.checkpoint(value['owner'], value['sid'], runtime.engine.summary(),
                                                   seq=value['seq'], frame_status='failed', reason=type(exc).__name__)
                        item = self.repository.freeze(value['owner'], value['sid'], 'worker-input-failure',
                            digest(dict(seq=value['seq'], error_type=type(exc).__name__)), item['revision'], 'input_failed')
                        runtime.engine.finish(item['requested_end_reason'])
                        self.repository.finalize(value['owner'], value['sid'], runtime.engine.summary(), item['requested_end_reason'])
                        runtime.terminal_epoch += 1
                        self.report_wake.set()
            finally:
                with self.guard:
                    self.inflight = None
                self.frames.task_done()
                for key in self.latencies:
                    self.latencies[key] = self.latencies[key][-512:]
        if self.vision:
            self.vision.close()

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
        return self._bounded(control)

    def finish(self, owner, sid, request):
        return self._bounded(lambda: self._finish(owner, sid, request))

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
                receipt = self.repository.finalize(owner, sid, runtime.engine.summary(), item['requested_end_reason'])
                runtime.terminal_epoch += 1
            self.report_wake.set()
            return receipt

    def feedback(self, owner, sid, request):
        key, fingerprint = identifier(request.get('idempotency_key')), digest(request)
        found = self.repository.lookup_operation(owner, sid, 'feedback', key, fingerprint)
        if found:
            return found
        result = self._bounded(lambda: self.repository.feedback(owner, sid, key, fingerprint,
                               request.get('expected_revision'), request.get('feedback', {})))
        self.report_wake.set()
        return result

    def get(self, owner, sid):
        item = self.repository.get(owner, sid)
        runtime = self.runtimes.get(sid)
        if runtime and item.get('current_cue'):
            with runtime.lock:
                age = 1000*(time.monotonic()-(runtime.cues.last_emission or time.monotonic()))
                source_time = runtime.engine.last_t if self.internal_replay else time.monotonic()-runtime.started
                current = runtime.cues.query(source_time_s=source_time or 0.,
                    emission_age_ms=age, phase=runtime.engine.phase, calibration_epoch=runtime.engine.calibration_epoch)
                item['current_cue'] = current
        return item

    def commit(self, owner, sid):
        item = self.repository.get(owner, sid)
        return dict(session_id=sid, persistence_state=item['persistence_state'],
                    receipt=item['canonical_commit'], derived_report_state=item['derived_report_state'])

    @staticmethod
    def _report(item):
        from app.rehab_v2.compatibility import comparison_contract
        snapshot = item['snapshot']
        contract = comparison_contract(item)
        return dict(session_id=item['session_id'], end_reason=item['end_reason'],
                    completed_reps=snapshot['completed'], visual_evidence=snapshot,
                    source=item['source'], frozen_plan=item['frozen_plan'],
                    feedback_status=item['feedback_status'],
                    interpretation='observed_training_facts_not_diagnosis',
                    protocol_compatibility=contract,
                    evidence_fingerprint=contract['evidence_fingerprint'])

    def rebuild_report(self, owner, sid):
        item = self.repository.get(owner, sid)
        try:
            report = self.report_builder(item)
            saved = self.repository.report_state(owner, sid, 'ready', report,
                expected_feedback_revision=item['feedback_revision'])
            return dict(state='ready' if saved else 'pending_newer_feedback')
        except Exception as exc:
            saved = self.repository.report_state(owner, sid, 'failed', error=type(exc).__name__,
                expected_feedback_revision=item['feedback_revision'])
            return dict(state='failed' if saved else 'pending_newer_feedback', error=type(exc).__name__)

    def close(self, *, graceful=True):
        if self.closed:
            return
        self.closed = True
        if graceful:
            for sid, runtime in list(self.runtimes.items()):
                item = self.repository.get(self.storage._call(lambda conn: conn.execute(
                    'SELECT owner FROM rehab_v2_sessions WHERE id=?', (sid,)).fetchone()[0]), sid)
                if item['persistence_state'] == 'draft':
                    self.finish(item['owner'], sid, dict(idempotency_key='host-close', expected_revision=item['revision'], reason='interrupted'))
        self.worker_stop.set()
        self.report_stop.set()
        self.report_wake.set()
        self.worker.join(timeout=max(3., self.drain_timeout_s+1.))
        self.report_worker.join(timeout=3.)
        if self.worker.is_alive() or self.report_worker.is_alive():
            # Do not close SQLite while its owning inference thread may still write.
            raise SessionError('vision_shutdown_not_confirmed', 503)
        self.storage.close()
        self.lease.close()
