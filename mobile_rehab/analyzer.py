"""One disposable analysis process, using the desktop capture/measurement stack."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import time

from .core import exercise_spec
from app.camera_manager import CameraManager
from app.scene_controller import SceneController
from app.settings import default_setup
from app.storage import Storage
from app.vision import VisionWorker
from app.domain import clean_json
from app.assessment import build_body_profile
from app.automatic_plans import generate_proposal, validate_automatic_use, observed_quality
from app.training_plans import prepare_training_plan


def write_json(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(clean_json(value), ensure_ascii=False), encoding='utf-8')
    temp.replace(path)


def analyze(job_path):
    job_path = Path(job_path)
    job = json.loads(job_path.read_text(encoding='utf-8'))
    if job.get('mode') == 'fitness':
        from .fitness_analyzer import analyze as analyze_fitness
        return analyze_fitness(job_path)
    folder = job_path.parent
    storage = Storage(folder.parent / 'assessments.sqlite3')
    camera, vision = CameraManager(), VisionWorker(start_thread=False)
    controller = SceneController(storage, camera)
    setup = default_setup('rehab', job['exercise'])
    setup['plan'].update(side=job['side'], participant_id=job['owner'])
    # This confirms the selected replay configuration, not a human identity or
    # camera placement inferred by AI. Upload consent is recorded separately.
    setup['mirror'] = False
    spec = exercise_spec(job['exercise'])
    started = False
    last_frame = time.monotonic()
    last_progress = 0.
    processed = 0
    try:
        if job.get('mode') == 'training':
            sessions = storage.list_sessions()
            profile = build_body_profile(sessions, job['owner'], 'REPLAY_FILE', 'SELF_USE')
            record = storage.get_training_plan(job['plan_id'])
            validate_automatic_use(record, job['entry_key'], profile, sessions, None)
            setup['plan'] = prepare_training_plan(record, job['entry_key'], profile)
            setup['plan']['training_plan_confirmed'] = True
        controller.open(dict(kind='REPLAY_FILE', ref=job['id'], usage_context='SELF_USE',
                             file=str(folder / 'video.mp4'), recording_id=job['id']),
                        setup, dict(speed=1000))
        while True:
            worker = camera.worker
            statuses = worker.read_status()
            if any(s['status'] == 'ERROR' for s in statuses):
                raise ValueError('视频无法解码。请使用手机普通录像模式，选择 MP4 / H.264 后重试。')
            if any(s['status'] == 'EOF' for s in statuses):
                break
            if any(s['status'] in ('RELEASED', 'RELEASE_UNCONFIRMED') for s in statuses):
                raise ValueError('视频读取提前结束，请重新录制或转换为 MP4。')
            packet = worker.read_latest()
            if packet is None:
                if time.monotonic() - last_frame > 45:
                    raise ValueError('读取视频超时，请尝试更短的普通录像。')
                time.sleep(.01)
                continue
            last_frame = time.monotonic()
            if packet.time_s > 120 or processed > 15000:
                raise ValueError('视频过长，请截取不超过 2 分钟的一项动作再上传。')
            if max(packet.image.shape[:2]) > 4096:
                raise ValueError('视频分辨率过高，请选择 720p 或 1080p 录像。')
            pose = vision.infer(packet, backend=spec['backend'], side=job['side'])
            controller.consume(packet, pose)
            worker.acknowledge(packet.seq)
            if not started:
                controller.confirm(setup)
                controller.start()
                started = True
            processed += 1
            if time.monotonic() - last_progress > 1:
                write_json(folder / 'progress.json', dict(processed_frames=processed,
                           analyzed_seconds=round(packet.time_s, 1)))
                last_progress = time.monotonic()
        if not started or processed < 3:
            raise ValueError('视频太短或没有可读取画面，请重新录制。')
        controller.stop('user_stop')
        session = storage.get_session(controller.last_saved_id)
        sessions = storage.list_sessions()
        profile = build_body_profile(sessions, job['owner'], 'REPLAY_FILE', 'SELF_USE')
        proposal = generate_proposal(profile, sessions)
        result = dict(session_id=session['id'], source_kind='REPLAY_FILE', usage_context='SELF_USE',
                      summary=session['summary'], repetitions=session.get('repetitions', []),
                      finished_at=session.get('end_utc'), proposal=proposal,
                      measurement_type='2d_projection', clinical_rom=False,
                      processed_frames=processed, quality=observed_quality(session.get('repetitions', [])))
        write_json(folder / 'result.json', result)
    finally:
        try:
            if controller.context is not None or controller.session is not None:
                controller.stop('mobile_analysis_failed')
        finally:
            vision.close()
            storage.close()


if __name__ == '__main__':
    try:
        analyze(sys.argv[1])
    except Exception as exc:
        import traceback
        traceback.print_exc()
        write_json(Path(sys.argv[1]).parent / 'error.json', dict(
            message=str(exc) if isinstance(exc, ValueError) else
            '分析未能完成。请检查电脑端模型和运行日志后重试；未生成测试结论。'))
        sys.exit(1)
