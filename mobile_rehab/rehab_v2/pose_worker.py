"""One owned, restartable YOLO process; no camera, SQL or business decisions.

Reuse the product's spawn/owned-process lifecycle and VisionWorker. Only the
JPEG is shared in a bounded volatile buffer. The pipe transports small JSON
notifications; bounded JSON poses also use shared memory. No external Python
objects are deserialized, and a large pipe read cannot defeat the deadline.
The host alone owns clocks, EMA, protocol state, durable facts and consent.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import math
import multiprocessing as mp
from multiprocessing.shared_memory import SharedMemory
import threading
import time
from uuid import uuid4

from ..core import CORE
from app.domain import Context, FramePacket, PoseFrame, PosePerson, dumps, utc_now

VERSION = 'rehab-pose-process-1'
JPEG_CAPACITY = 512*1024
REQUEST_CAPACITY = 4096
RESPONSE_CAPACITY = 4*1024*1024
MEMORY_CAPACITY = JPEG_CAPACITY+RESPONSE_CAPACITY


class PoseWorkerError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _send(pipe, value):
    payload = dumps(value).encode('utf-8')
    if len(payload) > REQUEST_CAPACITY:
        raise ValueError('pose_notification_capacity_exceeded')
    pipe.send_bytes(payload)


def _reply(pipe, memory, value):
    payload = dumps(value).encode('utf-8')
    if not 0 < len(payload) <= RESPONSE_CAPACITY:
        raise ValueError('pose_response_capacity_exceeded')
    memory.buf[JPEG_CAPACITY:JPEG_CAPACITY+len(payload)] = payload
    _send(pipe, dict(reply_length=len(payload), reply_sha256=hashlib.sha256(payload).hexdigest()))


def pose_process(pipe, memory_name):
    """Trusted local entry point. Models are reused, tracker context is not."""
    memory = SharedMemory(name=memory_name)
    vision = None
    try:
        _send(pipe, dict(ready=VERSION))
        while True:
            request = json.loads(pipe.recv_bytes(REQUEST_CAPACITY))
            if request is None:
                break
            ticket = request['ticket']
            try:
                length = request['length']
                if type(length) is not int or not 0 < length <= JPEG_CAPACITY:
                    raise ValueError('invalid_jpeg_buffer_length')
                encoded = bytes(memory.buf[:length])
                if hashlib.sha256(encoded).hexdigest() != request['image_sha256']:
                    raise ValueError('jpeg_buffer_fingerprint_mismatch')
                import cv2
                import numpy as np
                from app.vision import VisionWorker
                started = time.perf_counter()
                image = cv2.imdecode(np.frombuffer(encoded, np.uint8), cv2.IMREAD_COLOR)
                if image is None or min(image.shape[:2]) < 32 or image.shape[0]*image.shape[1] > 1920*1080:
                    raise ValueError('invalid_decoded_frame')
                decode_ms = 1000*(time.perf_counter()-started)
                del encoded
                if vision is None:
                    vision = VisionWorker(start_thread=False)
                # No child clock is used as a host age or an exposure time.
                packet = FramePacket(Context(**request['context']), request['seq'],
                                     request['source_time_s'], 0., utc_now(), image)
                started = time.perf_counter()
                pose = vision.infer(packet, backend='yolo', side=request['side'])
                inference_ms = 1000*(time.perf_counter()-started)
                del image
                _reply(pipe, memory, dict(ticket=ticket, ok=True, pose=asdict(pose),
                                         decode_ms=decode_ms, inference_ms=inference_ms))
            except Exception as exc:
                _reply(pipe, memory, dict(ticket=ticket, ok=False, error_type=type(exc).__name__))
    except (EOFError, BrokenPipeError, OSError):
        pass
    finally:
        if vision is not None:
            vision.close()
        memory.close()  # Parent alone unlinks; Windows frees after all handles close.
        pipe.close()


class IsolatedPoseWorker:
    def __init__(self, *, target=pose_process, startup_timeout_s=10., cold_timeout_s=30.,
                 frame_timeout_s=5., release_timeout_s=1.):
        for value in (startup_timeout_s, cold_timeout_s, frame_timeout_s, release_timeout_s):
            if type(value) not in (int, float) or not math.isfinite(value) or not .01 <= value <= 120:
                raise ValueError('finite_bounded_pose_worker_budget_required')
        self.target = target  # Only a trusted local constructor, never an HTTP field.
        self.startup_timeout_s, self.cold_timeout_s = startup_timeout_s, cold_timeout_s
        self.frame_timeout_s, self.release_timeout_s = frame_timeout_s, release_timeout_s
        self.lock, self.stop = threading.Lock(), threading.Event()
        self.state_lock, self.cancel = threading.Lock(), threading.Event()
        self.active_sid = None
        self.process = self.pipe = self.memory = None
        self.warm = False
        self.quarantined = False
        self.last_release = self.last_request = None

    @property
    def contract(self):
        return dict(version=VERSION, start_method='spawn', jpeg_buffer_bytes=JPEG_CAPACITY,
                    pose_response_bytes=RESPONSE_CAPACITY, shared_memory_bytes=MEMORY_CAPACITY,
                    startup_timeout_s=self.startup_timeout_s, cold_timeout_s=self.cold_timeout_s,
                    frame_timeout_s=self.frame_timeout_s, release_timeout_s=self.release_timeout_s,
                    no_camera_or_storage_in_child=True, child_clock_not_used_for_evidence_age=True)

    def _receive(self, budget, stage):
        deadline = time.monotonic()+budget
        while time.monotonic() < deadline:
            if self.stop.is_set() or self.cancel.is_set():
                raise PoseWorkerError('pose_worker_cancelled')
            if self.pipe.poll(min(.02, max(0., deadline-time.monotonic()))):
                try:
                    value = json.loads(self.pipe.recv_bytes(REQUEST_CAPACITY))
                except (EOFError, OSError, ValueError):
                    raise PoseWorkerError('invalid_pose_worker_response') from None
                if not isinstance(value, dict):
                    raise PoseWorkerError('invalid_pose_worker_response')
                return value
            if not self.process.is_alive():
                raise PoseWorkerError('pose_worker_exited')
        raise PoseWorkerError('pose_worker_'+stage+'_timeout')

    def _start(self):
        context = mp.get_context('spawn')
        self.memory = SharedMemory(create=True, size=MEMORY_CAPACITY)
        self.pipe, child = context.Pipe()
        self.process = context.Process(target=self.target, args=(child, self.memory.name),
                                       name='rehab-v2-owned-pose', daemon=True)
        try:
            self.process.start()
        finally:
            child.close()
        if self._receive(self.startup_timeout_s, 'startup').get('ready') != VERSION:
            raise PoseWorkerError('pose_worker_handshake_mismatch')

    def _release(self, reason):
        if self.process is None and self.memory is None and self.pipe is None:
            return
        process = self.process
        pid = process.pid if process is not None else None
        if process is not None and pid is not None:
            if process.is_alive():
                process.terminate()  # Only this exact owned process object, no PID pattern.
            process.join(self.release_timeout_s)
            if process.is_alive():
                process.kill()
                process.join(self.release_timeout_s)
            if process.is_alive():
                self.quarantined = True
                raise PoseWorkerError('pose_worker_release_unconfirmed')
        exit_code = process.exitcode if process is not None else None
        if self.memory is not None:
            self.memory.buf[:] = b'\0'*MEMORY_CAPACITY
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

    def infer(self, value, runtime):
        encoded = value['encoded']
        if not isinstance(encoded, bytes) or not 0 < len(encoded) <= JPEG_CAPACITY:
            raise PoseWorkerError('invalid_pose_worker_input_size')
        with self.lock:
            if self.stop.is_set():
                raise PoseWorkerError('pose_worker_cancelled')
            with self.state_lock:
                self.active_sid = value['sid']
                self.cancel.clear()
            try:
                if self.quarantined:
                    self._release('retry_quarantined_release')
                if self.process is None:
                    self._start()
                ticket = uuid4().hex
                request = dict(ticket=ticket, length=len(encoded), image_sha256=hashlib.sha256(encoded).hexdigest(),
                               context=asdict(runtime.context), seq=value['seq'],
                               source_time_s=value['source_time_s'], side=runtime.engine.spec['side'])
                header = dumps(request).encode('utf-8')
                if len(header) > REQUEST_CAPACITY:
                    raise PoseWorkerError('pose_worker_request_capacity_exceeded')
                self.memory.buf[:len(encoded)] = encoded
                self.last_request = dict(ticket=ticket, session_id=value['sid'], seq=value['seq'],
                                         pid=self.process.pid, source_epoch=runtime.context.epoch)
                # Only one small metadata message is outstanding; JPEG never
                # blocks a pipe write or leaves a queue feeder behind on timeout.
                self.pipe.send_bytes(header)
                notification = self._receive(self.frame_timeout_s if self.warm else self.cold_timeout_s, 'inference')
                length = notification.get('reply_length')
                if type(length) is not int or not 0 < length <= RESPONSE_CAPACITY:
                    raise PoseWorkerError('invalid_pose_worker_response_length')
                payload = bytes(self.memory.buf[JPEG_CAPACITY:JPEG_CAPACITY+length])
                if hashlib.sha256(payload).hexdigest() != notification.get('reply_sha256'):
                    raise PoseWorkerError('pose_worker_response_fingerprint_mismatch')
                result = json.loads(payload)
                if not isinstance(result, dict):
                    raise PoseWorkerError('invalid_pose_worker_response')
                if result.get('ticket') != ticket:
                    raise PoseWorkerError('pose_worker_ticket_mismatch')
                if result.get('ok') is not True:
                    raise PoseWorkerError('pose_worker_inference_failed')
                pose = dict(result['pose'])
                pose['context'] = Context(**pose['context'])
                pose['people'] = [PosePerson(**person) for person in pose['people']]
                pose['size'] = tuple(pose['size'])
                evidence = PoseFrame(**pose)
                if (evidence.context != runtime.context or evidence.seq != value['seq']
                        or evidence.time_s != value['source_time_s']):
                    raise PoseWorkerError('pose_worker_evidence_identity_mismatch')
                for key in ('decode_ms', 'inference_ms'):
                    number = result.get(key)
                    if type(number) not in (int, float) or not math.isfinite(number) or number < 0:
                        raise PoseWorkerError('invalid_pose_worker_stage_duration')
                self.warm = True
                return evidence, dict(decode_ms=result['decode_ms'], inference_ms=result['inference_ms'])
            except Exception as exc:
                self._release(getattr(exc, 'code', type(exc).__name__))
                raise
            finally:
                if self.memory is not None and self.warm:
                    self.memory.buf[:] = b'\0'*MEMORY_CAPACITY
                with self.state_lock:
                    self.active_sid = None
                    self.cancel.clear()

    def cancel_current(self, sid):
        with self.state_lock:
            if self.active_sid == sid:
                self.cancel.set()

    def request_stop(self):
        self.stop.set()  # Does not wait for an inference or acquire its lock.

    def close(self):
        self.request_stop()
        if not self.lock.acquire(timeout=2*self.release_timeout_s+1.):
            raise PoseWorkerError('pose_worker_shutdown_lock_unconfirmed')
        try:
            self._release('host_shutdown')
        finally:
            self.lock.release()
