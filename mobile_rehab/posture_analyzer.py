"""Posture video uses the existing owned decoder and local model."""
import json
from pathlib import Path
import time

from .core import CORE
from .posture import PostureEngine, VERSION, TASKS
from .analyzer import write_json
from app.camera_manager import CameraManager
from app.vision import VisionWorker
from app.domain import Context, utc_now
from .replay_status import replay_ended


def analyze(job_path):
    folder = Path(job_path).parent
    job = json.loads(Path(job_path).read_text(encoding='utf-8'))
    engine = PostureEngine(job['exercise'], job['side'])
    camera, vision = CameraManager(), VisionWorker(start_thread=False)
    context = Context(1, 'posture', job['id'], 'REPLAY_FILE', 'SELF_USE', job['id'])
    last, last_progress, size, model = time.monotonic(), 0., None, ''
    timing = dict(basis='opencv_media_pts', skipped_leading_frames=0)
    try:
        camera.open_replay(str(folder/'video.mp4'), context, dict(speed=1000))
        while True:
            statuses = camera.worker.read_status()
            if replay_ended(statuses, timing):
                break
            packet = camera.worker.read_latest()
            if packet is None:
                if time.monotonic()-last > 45:
                    raise ValueError('录像读取超时')
                time.sleep(.01)
                continue
            last = time.monotonic()
            actual = tuple(packet.image.shape[1::-1])
            if packet.time_s > 120 or engine.frames > 15000 or max(actual) > 4096 or (size and size != actual):
                raise ValueError('请使用固定尺寸、两分钟以内的录像')
            size = actual
            pose = vision.infer(packet)
            model = pose.model_manifest_id
            engine.consume(pose)
            camera.worker.acknowledge(packet.seq)
            if time.monotonic()-last_progress > 1:
                try:
                    write_json(folder/'progress.json', dict(processed_frames=engine.frames, analyzed_seconds=round(packet.time_s, 1)))
                except PermissionError:
                    pass
                last_progress = time.monotonic()
        if engine.frames < 3:
            raise ValueError('录像过短')
        write_json(folder/'result.json', dict(kind='posture', rule_version=VERSION,
            source_kind='REPLAY_FILE', usage_context='SELF_USE', exercise=job['exercise'], side=job['side'],
            finished_at=utc_now(), summary=engine.summary(),
            input_timing=timing,
            conditions=dict(view=TASKS[job['exercise']]['view'], side=job['side'], size=size,
                            model_manifest_id=model, schema='coco17-v1'),
            limitations=['不诊断骨盆前倾、圆肩、脊柱侧弯或颈椎疾病。',
                         '普通姿态模型没有髂前上棘、髂后上棘和 C7 等精细体表标志点。']))
    finally:
        try:
            camera.stop()
        finally:
            vision.close()
