"""Offline fitness adapter; owns no capture outside the existing CameraManager."""
import json
from pathlib import Path
import time

from .core import CORE  # initialize the existing core import path
from .fitness import FitnessEngine, EXERCISES, VERSION
from .analyzer import write_json
from app.camera_manager import CameraManager
from app.vision import VisionWorker
from app.domain import Context, utc_now


def analyze(job_path):
    job_path = Path(job_path)
    job = json.loads(job_path.read_text(encoding='utf-8'))
    folder = job_path.parent
    engine = FitnessEngine(job['exercise'], job['side'])
    camera, vision = CameraManager(), VisionWorker(start_thread=False)
    context = Context(1, 'fitness', job['id'], 'REPLAY_FILE', 'SELF_USE', job['id'])
    last_frame, last_progress = time.monotonic(), 0.
    size, model_id = None, None
    try:
        camera.open_replay(str(folder / 'video.mp4'), context, dict(speed=1000))
        while True:
            worker = camera.worker
            statuses = worker.read_status()
            if any(s['status'] == 'ERROR' for s in statuses):
                raise ValueError('录像读取失败，请选择普通 MP4 录像重新上传。')
            if any(s['status'] == 'EOF' for s in statuses):
                break
            if any(s['status'] in ('RELEASED', 'RELEASE_UNCONFIRMED') for s in statuses):
                raise ValueError('录像提前中断，本次没有生成完整健身报告。')
            packet = worker.read_latest()
            if packet is None:
                if time.monotonic()-last_frame > 45:
                    raise ValueError('读取录像超时，请尝试更短的视频。')
                time.sleep(.01)
                continue
            last_frame = time.monotonic()
            if packet.time_s > 120 or engine.frames >= 15000:
                raise ValueError('请使用两分钟以内、正常帧率的一组动作录像。')
            actual = tuple(packet.image.shape[1::-1])
            if max(actual) > 4096 or (size is not None and actual != size):
                raise ValueError('画面尺寸过大或中途变化，请使用固定机位的普通 720p / 1080p 录像。')
            size = actual
            pose = vision.infer(packet, backend='yolo', side=job['side'])
            model_id = pose.model_manifest_id
            engine.consume(pose)
            worker.acknowledge(packet.seq)
            if time.monotonic()-last_progress > 1:
                write_json(folder / 'progress.json', dict(processed_frames=engine.frames,
                           analyzed_seconds=round(packet.time_s, 1)))
                last_progress = time.monotonic()
        if engine.frames < 3:
            raise ValueError('视频太短，请重新录制一组完整动作。')
        write_json(folder / 'result.json', dict(kind='fitness', exercise=job['exercise'], side=job['side'],
            rule_version=VERSION, source_kind='REPLAY_FILE', usage_context='SELF_USE',
            finished_at=utc_now(), summary=engine.summary(), repetitions=engine.repetitions,
            series=engine.series, spec=EXERCISES[job['exercise']], processed_frames=engine.frames,
            conditions=dict(view='sagittal_user_selected', size=size, schema='coco17-v1',
                            model_manifest_id=model_id, confidence_min=.5, gap_s=engine.GAP,
                            smoothing='causal-ema-tau-0.1s', timing='opencv_media_pts'),
            limitations=['仅观察所选侧二维投影，不自动确认动作类别或拍摄机位。',
                         '计次阈值用于切分动作，不是标准动作合格线。未计完整不等于动作错误。',
                         '缺测与参与者跟踪丢失会中断当前往返，不跨缺口拼接次数。',
                         '不测实际力、肌肉发力、杠铃位移/速度、重量、功率或爆发力。']))
    finally:
        try:
            camera.stop()
        finally:
            vision.close()
