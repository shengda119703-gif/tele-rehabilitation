"""TEST-only plan contract setup; NOT camera evidence or patient validation.

Uses the original JPEG queue/protocol/writer and BackendPlans, not DB surgery.
The geometric provider is reset before the actual browser camera run. This
positive contract fixture must never be counted as an observed human assessment.
"""
from io import BytesIO
from pathlib import Path
import time
from uuid import uuid4

from PIL import Image
from app.rehab_v2.evidence import EvidenceFrame, MetricEvidence
from app.rehab_v2.sessions import SessionError


def seed(service, directory):
    if not Path(directory).resolve().is_relative_to(Path('D:/RehabFrontendFlowVerification').resolve()):
        raise ValueError('TEST fixture requires the isolated private verification directory')
    owner = uuid4().hex
    original = service.inference_provider

    def geometry(value, runtime):
        seq, stamp = value['seq'], value['source_time_s']
        angle = 0. if seq <= 30 or seq > 40 else 45.
        metric = MetricEvidence(angle, 'degree', True, None, 'observed', stamp, stamp, 0.,
                                tuple(runtime.engine.spec['required_joints']))
        return EvidenceFrame(seq, stamp, runtime.context.epoch, 'TEST-contract-person', 'coco17-v1',
                             'TEST-geometric-contract-fixture-not-human', (320, 240),
                             {'raise_deg': metric}, 'VALID', 'browser-camera')

    try:
        service.inference_provider = geometry
        request = dict(idempotency_key='TEST-training-fixture-assessment', consent=True,
                       submode='assessment', exercise_id='shoulder_abduction', side='left', view='frontal')
        deadline = time.monotonic() + 20
        while True:
            try:
                item = service.create(owner, request)
                break
            except SessionError as error:
                if error.code != 'rehab_compute_resource_busy' or time.monotonic() >= deadline:
                    raise
                time.sleep(.05)
        sid = item['session_id']
        encoded = BytesIO()
        Image.new('RGB', (320, 240), 'white').save(encoded, format='JPEG')
        for seq in range(1, 51):
            service.submit_jpeg(owner, sid, 'TEST-fixture-frame-'+str(seq), seq, encoded.getvalue())
            deadline = time.monotonic() + 10
            while service.get(owner, sid)['processed_last_seq'] < seq:
                if time.monotonic() >= deadline:
                    raise RuntimeError('TEST fixture JPEG queue did not finish')
                time.sleep(.02)
            time.sleep(.11)
        item = service.get(owner, sid)
        if not item['snapshot']['baseline'] or item['snapshot']['completed'] != 1:
            raise RuntimeError('TEST contract fixture failed the ORIGINAL qualification rules')
        service.finish(owner, sid, dict(idempotency_key='TEST-fixture-end', expected_revision=0, reason='completed'))
        plan = service.save_plan(owner, dict(idempotency_key='TEST-fixture-arrangement',
            name='TEST 合同验证训练安排', arrangement=dict(reference='TEST 已有安排，不是人体评估或临床处方', confirmed=True),
            items=[dict(exercise_id='shoulder_abduction', side='left', assessment_session_id=sid,
                        settings=dict(target_reps=3, target_sets=2, target_angle_deg=None,
                                      needs_companion=False, use_of_hands='not_recorded'))]))
        return owner, plan['id'], sid
    finally:
        service.inference_provider = original
