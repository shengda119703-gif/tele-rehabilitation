from __future__ import annotations

from collections import deque
import math
import multiprocessing as mp
import queue
import time

from .domain import FramePacket, utc_now


def put_latest(slot, item):
    try:
        slot.put_nowait(item)
        return
    except queue.Full:
        pass
    try:
        slot.get_nowait()
    except queue.Empty:
        pass
    try:
        slot.put_nowait(item)
    except queue.Full:
        pass


def _capture(source, context, options, frames, statuses, commands, acknowledgements, stop):
    """Only this owned subprocess opens VideoCapture. Read can be forcibly isolated."""
    import cv2
    cap = None
    released = False
    try:
        if source['kind'] == 'LIVE_CAMERA':
            cap = cv2.VideoCapture(source['index'], source['backend'])
        else:
            cap = cv2.VideoCapture(source['path'], cv2.CAP_FFMPEG)
        if not cap.isOpened():
            raise RuntimeError('输入打开失败；请检查设备权限、占用或视频格式')
        live = source['kind'] == 'LIVE_CAMERA'
        set_results = {}
        if live:
            for name, prop, value in (('width', cv2.CAP_PROP_FRAME_WIDTH, options.get('width', 1280)),
                                      ('height', cv2.CAP_PROP_FRAME_HEIGHT, options.get('height', 720)),
                                      ('fps', cv2.CAP_PROP_FPS, options.get('fps', 30))):
                set_results[name] = bool(cap.set(prop, value))
        elif options.get('seek_s', 0) > 0:
            if not cap.set(cv2.CAP_PROP_POS_MSEC, options['seek_s']*1000):
                raise RuntimeError('视频后端无法定位此时间，请从头重新预览')
        reported = float(cap.get(cv2.CAP_PROP_FPS))
        reported = reported if math.isfinite(reported) and reported > 0 else None
        put_latest(statuses, {'status': 'OPENED', 'set_results': set_results, 'reported_fps': reported})
        received = deque(maxlen=60)
        seq, previous_pts, preview_sent, pending_seq = 0, None, False, None
        leading_skipped = 0
        previous_wall = None
        preview_until = None
        while not stop.is_set():
            changed = False
            try:
                while True:
                    command, payload = commands.get_nowait()
                    if command == 'context':
                        context, preview_sent, pending_seq = payload, False, None
                        preview_until = None
                        changed = True
                    elif command == 'preview_segment' and not context.run_id and not live:
                        preview_until = (previous_pts or 0)+max(.2, min(3., float(payload)))
                        preview_sent = False
            except queue.Empty:
                pass
            if not live:
                if pending_seq is not None:
                    try:
                        ack = acknowledgements.get(timeout=.03)
                        if ack == pending_seq:
                            pending_seq = None
                    except queue.Empty:
                        continue
                    if pending_seq is not None:
                        continue
                if not context.run_id and preview_sent and preview_until is None:
                    stop.wait(.025)
                    continue
            read_context = context  # Capture context BEFORE read; never relabel a buffered old frame.
            ok, frame = cap.read()
            now = time.monotonic()
            if not ok or frame is None:
                if live:
                    raise RuntimeError('无法取得新画面，输入已离线；请重新预览并确认')
                put_latest(statuses, {'status': 'EOF'})
                break
            if len(frame.shape) != 3 or frame.shape[2] != 3:
                raise RuntimeError('当前输入不是三通道 RGB/BGR 画面，请重选彩色设备')
            if live:
                analysis_t, basis = now, 'monotonic_receive'
            else:
                pts = float(cap.get(cv2.CAP_PROP_POS_MSEC))/1000
                # Some phone MP4s expose a small negative first timestamp in
                # OpenCV even though the decoder can read the picture. Omit
                # only a bounded leading preroll, never invent frame times or
                # repair an in-stream discontinuity. Keep subsequent PTS exact.
                if (previous_pts is None and not options.get('seek_s', 0)
                        and math.isfinite(pts) and -.25 <= pts < 0 and leading_skipped < 4):
                    leading_skipped += 1
                    put_latest(statuses, {'status': 'REPLAY_PREROLL_SKIPPED',
                                          'skipped_frames': leading_skipped, 'raw_time_s': pts})
                    continue
                if not math.isfinite(pts) or pts < 0 or (previous_pts is not None and pts <= previous_pts):
                    raise RuntimeError('录像媒体时间不可用或非单调；已停止分析，不以推理耗时替代')
                if previous_pts is not None and previous_wall is not None:
                    delay = (pts-previous_pts)/max(.25, options.get('speed', 1.)) - (now-previous_wall)
                    if delay > 0:
                        stop.wait(min(delay, 5.))
                analysis_t, basis = pts, 'opencv_media_pts'
                previous_pts, previous_wall = pts, time.monotonic()
            if stop.is_set():
                break
            received.append(now)
            fps = (len(received)-1)/(received[-1]-received[0]) if len(received) > 1 and received[-1] > received[0] else None
            seq += 1
            packet = FramePacket(read_context, seq, analysis_t, now, utc_now(), frame, reported, fps, basis)
            if live:
                put_latest(frames, packet)
            else:
                while not stop.is_set():
                    try:
                        frames.put(packet, timeout=.05)
                        break
                    except queue.Full:
                        continue
                pending_seq = seq
                preview_sent = True
                if preview_until is not None and analysis_t+1e-8 >= preview_until:
                    preview_until = None
    except Exception as exc:
        put_latest(statuses, {'status': 'ERROR', 'message': str(exc)})
    finally:
        if cap is not None:
            try:
                cap.release()
                released = True
            except Exception:
                pass
        put_latest(statuses, {'status': 'RELEASED' if released else 'RELEASE_UNCONFIRMED'})
        # Do not hang the owner at process exit if an old image is no longer consumed.
        frames.cancel_join_thread()


class SourceWorker:
    def __init__(self, source, context, options):
        ctx = mp.get_context('spawn')
        self.frames, self.statuses = ctx.Queue(maxsize=1), ctx.Queue(maxsize=16)
        self.commands, self.acks = ctx.Queue(), ctx.Queue()
        self.stop_event = ctx.Event()
        self.process = ctx.Process(target=_capture, args=(source, context, options, self.frames,
                                   self.statuses, self.commands, self.acks, self.stop_event), daemon=True)
        self.forced_stop = False
        self.stopped = False

    def start(self):
        self.process.start()

    def change_context(self, context):
        self.commands.put(('context', context))
        self.clear_frames()

    def clear_frames(self):
        try:
            while True:
                self.frames.get_nowait()
        except queue.Empty:
            pass

    def acknowledge(self, seq):
        self.acks.put(seq)

    def preview_segment(self, duration=1.2):
        self.commands.put(('preview_segment', duration))

    def read_latest(self):
        try:
            return self.frames.get_nowait()
        except queue.Empty:
            return None

    def read_status(self):
        result = []
        try:
            while True:
                result.append(self.statuses.get_nowait())
        except queue.Empty:
            return result

    def request_stop(self):
        self.stop_event.set()

    def stop(self):
        if self.stopped:
            return True
        self.request_stop()
        if self.process.pid is not None:
            self.process.join(timeout=2)
        if self.process.pid is not None and self.process.is_alive():
            self.forced_stop = True
            self.process.terminate()
            self.process.join(timeout=2)
        if self.process.pid is not None and self.process.is_alive():
            return False
        for slot in (self.frames, self.statuses, self.commands, self.acks):
            slot.cancel_join_thread()
            slot.close()
        self.stopped = True
        return True
