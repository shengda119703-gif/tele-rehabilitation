"""Bounded, isolated browser-camera inference. Frames stay in memory only."""
import asyncio
from io import BytesIO
import multiprocessing as mp
import os
import signal
import subprocess
import threading
import time
from uuid import uuid4

from fastapi import HTTPException, Request
from .core import EXERCISE_IDS, exercise_spec


def worker(pipe, exercise, side):
    if os.name != 'nt':
        os.setsid()
    import cv2
    import numpy as np
    from .core import CORE
    from app.domain import Context, FramePacket, utc_now, clean_json
    from app.vision import VisionWorker
    from app.quality import PoseAnalyzer
    from app.rehab import RehabEngine
    from app.settings import default_plan
    from app.guidance import GuidancePolicy
    plan = default_plan(exercise)
    plan['side'] = side
    engine, analyzer, policy = RehabEngine(plan), PoseAnalyzer(side=side, exercise_id=exercise), GuidancePolicy()
    vision = VisionWorker(start_thread=False)
    context = Context(1, 'rehab', 'browser-camera', 'LIVE_CAMERA', 'SELF_USE')
    size = None
    try:
        while pipe.poll(30):  # Lost browser / network releases the model automatically.
            value = pipe.recv()
            if value is None:
                break
            seq, stamp, encoded = value
            frame = cv2.imdecode(np.frombuffer(encoded, np.uint8), cv2.IMREAD_COLOR)
            if frame is None:
                raise ValueError('画面无法解码')
            actual = tuple(frame.shape[1::-1])
            if size and size != actual:
                raise ValueError('画面尺寸已变化，请重新开始')
            size = actual
            packet = FramePacket(context, seq, stamp, time.monotonic(), utc_now(), frame)
            pose = vision.infer(packet, backend=exercise_spec(exercise)['backend'], side=side)
            observation = analyzer.analyze(pose)
            engine.process(observation)
            summary = engine.summary()
            valid = observation.status == 'VALID' and observation.value(engine.primary_metric) is not None
            cue = policy.render(dict(state='ONLINE', context=context.run_id, summary=summary,
                                     current_measurement_valid=valid), plan, now=stamp)
            # Draw only the selected person's current valid points, never stale frames.
            points = []
            if valid and observation.bbox_raw_px:
                person = min(pose.people, key=lambda p: sum(abs(a-b) for a,b in zip(p.bbox, observation.bbox_raw_px)))
                points = [[x/size[0],y/size[1]] for (x,y),c in zip(person.xy,person.conf)
                          if c is not None and c >= .5 and 0 <= x < size[0] and 0 <= y < size[1]]
            pipe.send(dict(ok=True, data=clean_json(dict(seq=seq, summary=summary, cue=cue,
                points=points, inference_ms=pose.inference_ms, valid=valid, elapsed_s=stamp))))
    except (EOFError, BrokenPipeError):
        pass
    except Exception:
        try:
            pipe.send(dict(ok=False, error='实时分析中断，请检查本机模型后重新开始。'))
        except (EOFError, BrokenPipeError):
            pass
    finally:
        vision.close()
        pipe.close()


class LiveManager:
    def __init__(self, target=worker):
        self.lock, self.session, self.target = threading.RLock(), None, target

    def start(self, uid, exercise, side):
        with self.lock:
            if self.session:
                s = self.session
                if s['process'].is_alive() and time.monotonic()-s['touched'] < 30:
                    raise HTTPException(409, '实时指导正在使用中，请先结束上一次')
                self._close()
            parent, child = mp.get_context('spawn').Pipe()
            process = mp.get_context('spawn').Process(target=self.target, args=(child,exercise,side), daemon=True)
            process.start()
            child.close()
            self.session = dict(id=uuid4().hex, owner=uid, pipe=parent, process=process,
                                started=time.monotonic(), touched=time.monotonic(), seq=0, busy=False)
            return dict(id=self.session['id'], max_seconds=600)

    def _get(self, uid, ident):
        if not self.session or self.session['id'] != ident or self.session['owner'] != uid:
            raise HTTPException(404, '实时任务已结束，请重新开始')
        return self.session

    def frame(self, uid, ident, encoded):
        from PIL import Image
        try:
            with Image.open(BytesIO(encoded)) as im:
                if im.format != 'JPEG' or max(im.size) > 1280 or min(im.size) < 64:
                    raise ValueError()
                im.verify()
        except Exception:
            raise HTTPException(400, '请发送 1280 像素以内的 JPEG 画面')
        with self.lock:
            s = self._get(uid, ident)
            if s['busy']:
                raise HTTPException(429, '上一帧仍在分析')
            if time.monotonic()-s['started'] > 600:
                self._close()
                raise HTTPException(409, '本次指导已达10分钟，请休息后重新开始')
            s.update(seq=s['seq']+1, touched=time.monotonic(), busy=True)
        try:
            s['pipe'].send((s['seq'], time.monotonic()-s['started'], encoded))
            if not s['pipe'].poll(25):
                raise RuntimeError('实时分析超时')
            result = s['pipe'].recv()
            if not result.get('ok'):
                raise RuntimeError(result.get('error'))
            return result['data']
        except (EOFError, OSError, RuntimeError, ValueError):
            with self.lock:
                if self.session is s:
                    self._close()
            raise HTTPException(503, '实时分析已断开，请检查电脑模型后重新开始')
        finally:
            with self.lock:
                s['busy'] = False
                s['touched'] = time.monotonic()

    def stop(self, uid, ident):
        with self.lock:
            self._get(uid, ident)
            self._close()

    def _close(self):
        if not self.session:
            return
        s, self.session = self.session, None
        if s['process'].is_alive():
            # Optional landmark inference owns a child process. Stop the whole
            # owned process tree, not only this worker's Python interpreter.
            if os.name == 'nt':
                try:
                    subprocess.run(['taskkill','/PID',str(s['process'].pid),'/T','/F'],
                                   capture_output=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
                except subprocess.TimeoutExpired:
                    s['process'].terminate()
            else:
                try:
                    os.killpg(s['process'].pid, signal.SIGTERM)
                except ProcessLookupError:
                    s['process'].terminate()
        s['process'].join(3)
        if s['process'].is_alive():
            s['process'].kill()
            s['process'].join(2)
        s['pipe'].close()

    def close(self):
        with self.lock:
            self._close()


def install_live(app, owner, small_json):
    manager = LiveManager()
    app.state.live = manager

    @app.post('/api/live')
    async def start(request: Request):
        uid, data = owner(request), await small_json(request)
        if data.get('exercise') not in EXERCISE_IDS or data.get('side') not in ('left','right') or data.get('consent') is not True:
            raise HTTPException(400, '请选择动作和侧别，并同意将画面传至电脑分析')
        return await asyncio.to_thread(manager.start, uid, data['exercise'], data['side'])

    @app.post('/api/live/{ident}/frame')
    async def frame(ident: str, request: Request):
        uid = owner(request)
        encoded = bytearray()
        async for chunk in request.stream():
            encoded.extend(chunk)
            if len(encoded) > 512*1024:
                raise HTTPException(413, '画面过大，请降低清晰度')
        return await asyncio.to_thread(manager.frame, uid, ident, bytes(encoded))

    @app.delete('/api/live/{ident}')
    async def stop(ident: str, request: Request):
        await asyncio.to_thread(manager.stop, owner(request), ident)
        return dict(ok=True)
