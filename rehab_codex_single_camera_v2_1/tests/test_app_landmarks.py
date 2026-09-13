"""Synthetic geometry/protocol tests; NOT camera or clinical validation."""
import copy
import hashlib
import io
import json
import math
import time
import threading
from types import SimpleNamespace as NS

import numpy as np
import pytest

from app.domain import Context, FramePacket, PoseFrame, PosePerson, Metric, Observation
from app.exercises import EXERCISE_IDS, exercise_spec
from app.landmark_schemas import SCHEMAS, ORDERS, BACKEND_SCHEMAS, skeleton_edges
from app.landmark_process import encode_result, merge_wrist, _read_exact
from app.landmark_backend import LandmarkBackend, landmark_python, verified_model
from app.quality import PoseAnalyzer, angle_delta
from app.joint_calibration import stable_preview_value
from app.rehab import RehabEngine
from app.settings import ROOT, default_plan


def frame(schema='mediapipe33-v1', *, context=None, side='left', angle=0., seq=1, t=0.):
    names = SCHEMAS[schema]
    xy = [[200.+i*5, 100.+i*3] for i in range(len(names))]
    values = {'left_shoulder': [300., 180.], 'right_shoulder': [600., 180.],
              'left_elbow': [300., 280.], 'right_elbow': [600., 280.],
              'left_wrist': [400., 280.], 'right_wrist': [700., 280.],
              'left_hip': [300., 350.], 'right_hip': [600., 350.],
              'left_knee': [300., 480.], 'right_knee': [600., 480.],
              'left_ankle': [300., 600.], 'right_ankle': [600., 600.],
              'left_heel': [280., 620.], 'right_heel': [580., 620.],
              'left_foot_index': [400., 620.], 'right_foot_index': [700., 620.]}
    for name, point in values.items():
        if name in names:
            xy[names.index(name)] = point
    r = math.radians(angle)
    if schema == 'mediapipe-wrist54-v1':
        wx, wy = values[side+'_wrist']
        xy[names.index('hand_wrist')] = [wx, wy]
        xy[names.index('hand_middle_mcp')] = [wx+80*math.cos(r), wy+80*math.sin(r)]
    if schema == 'mediapipe33-v1':
        heel = values[side+'_heel']
        xy[names.index(side+'_foot_index')] = [heel[0]+120*math.cos(r), heel[1]+120*math.sin(r)]
    confidence = [None if schema == 'mediapipe-hand21-v1' or i >= 33 else .99 for i in range(len(names))]
    ctx = context or Context(1, 'rehab', 'synthetic-landmark-fixture', 'SYNTHETIC', 'TEST')
    return PoseFrame(ctx, seq, t, (1280, 720), [PosePerson(ctx.epoch+':one', [100,50,900,700], xy, confidence)],
                     schema_id=schema, keypoint_order_version=ORDERS[schema],
                     backend=next(k for k,v in BACKEND_SCHEMAS.items() if v == schema),
                     model_manifest_id='synthetic-geometry-not-real-model')


def settled(pose, *, side='left', exercise_id=None, baseline=None):
    analyzer = PoseAnalyzer(side=side, exercise_id=exercise_id, joint_baseline=baseline)
    for i in range(4):
        pose.time_s, pose.seq = i*.1, i+1
        observation = analyzer.analyze(pose)
    return observation


@pytest.mark.parametrize('schema', list(SCHEMAS))
def test_schema_order_and_edges_are_explicit(schema):
    assert len(set(SCHEMAS[schema])) == len(SCHEMAS[schema])
    assert all(0 <= a < len(SCHEMAS[schema]) and 0 <= b < len(SCHEMAS[schema]) for a,b in skeleton_edges(schema))
    pose = frame(schema)
    pose.keypoint_order_version = 'same-count-wrong-order'
    with pytest.raises(ValueError, match='顺序'):
        PoseAnalyzer().analyze(pose)
    pose.keypoint_order_version = ORDERS[schema]
    pose.people[0].xy.pop()
    with pytest.raises(ValueError, match='数量'):
        PoseAnalyzer().analyze(pose)


def test_additional_person_keeps_the_existing_spatial_focus():
    analyzer = PoseAnalyzer(exercise_id='shoulder_abduction')
    pose = frame('coco17-v1')
    first = analyzer.analyze(pose)
    original_bbox = list(pose.people[0].bbox)
    carer = copy.deepcopy(pose.people[0])
    carer.track_key = 'carer'
    carer.bbox = [0., 0., 1270., 710.]
    carer.xy = [[x+250., y] for x, y in carer.xy]
    pose.people.append(carer)
    pose.time_s = .1
    selected = analyzer.analyze(pose)
    assert selected.status == 'VALID' and selected.track_key == first.track_key
    assert selected.bbox_raw_px == original_bbox
    assert 'additional_candidates_ignored' in selected.reasons


@pytest.mark.parametrize('side', ['left', 'right'])
def test_pose33_maps_semantics_not_coco_indices(side):
    coco = settled(frame('coco17-v1'), side=side)
    body = settled(frame(), side=side)
    for key in ('raise_deg', 'elbow_flexion_deg', 'knee_flexion_deg', 'hip_abduction_deg', 'hip_y'):
        assert body.value(key) == pytest.approx(coco.value(key))


@pytest.mark.parametrize('side', ['left', 'right'])
@pytest.mark.parametrize('angle', [-60., -25., 0., 25., 60.])
def test_sagittal_shoulder_and_hip_retain_opposite_directions(side, angle):
    pose = frame('coco17-v1')
    names, xy = SCHEMAS[pose.schema_id], pose.people[0].xy
    r = math.radians(angle)
    for base, end in [('shoulder', 'elbow'), ('hip', 'knee')]:
        x, y = xy[names.index(side+'_'+base)]
        xy[names.index(side+'_'+end)] = [x+100*math.sin(r), y+100*math.cos(r)]
    observation = settled(pose, side=side)
    assert observation.value('shoulder_sagittal_raw_deg') == pytest.approx(-angle)
    assert observation.value('hip_sagittal_raw_deg') == pytest.approx(-angle)


@pytest.mark.parametrize('side', ['left', 'right'])
@pytest.mark.parametrize('angle', [-40, -20, 0, 25, 50])
def test_ankle_uses_shank_and_actual_foot_vector(side, angle):
    pose = frame(side=side, angle=angle)
    o = settled(pose, side=side)
    assert o.value('ankle_raw_deg') == pytest.approx(90+angle)
    # Moving the whole leg/foot rigidly cannot change its angle.
    pose.people[0].xy = [[x*.7+100, y*.7+50] for x,y in pose.people[0].xy]
    assert settled(pose, side=side).value('ankle_raw_deg') == pytest.approx(90+angle)
    pose.people[0].conf[SCHEMAS[pose.schema_id].index(side+'_heel')] = .1
    missing = settled(pose, side=side)
    assert missing.value('ankle_raw_deg') is None
    assert missing.value('knee_flexion_deg') is not None


@pytest.mark.parametrize('side', ['left', 'right'])
@pytest.mark.parametrize('angle', [-40, 0, 30, 60])
def test_wrist_uses_forearm_and_hand_not_upper_arm(side, angle):
    pose = frame('mediapipe-wrist54-v1', side=side, angle=angle)
    assert settled(pose, side=side).value('wrist_raw_deg') == pytest.approx(angle)
    r = math.radians(20)
    pose.people[0].xy = [[x*math.cos(r)-y*math.sin(r)+200,
                         x*math.sin(r)+y*math.cos(r)] for x,y in pose.people[0].xy]
    assert settled(pose, side=side).value('wrist_raw_deg') == pytest.approx(angle)
    pose.people[0].xy[42] = [None, None]  # selected hand middle MCP
    assert settled(pose, side=side).value('wrist_raw_deg') is None


FINGER_IDS = [e for e in EXERCISE_IDS if exercise_spec(e)['joint'] == 'finger']


@pytest.mark.parametrize('eid', FINGER_IDS)
@pytest.mark.parametrize('angle', [0, 45, 90])
def test_each_finger_joint_has_its_own_known_angle(eid, angle):
    pose = frame('mediapipe-hand21-v1')
    names = SCHEMAS[pose.schema_id]
    finger, joint, _ = eid.split('_')
    i = names.index(finger+'_'+joint)
    before = 0 if joint == 'mcp' and finger != 'thumb' else i-1
    pose.people[0].xy[before] = [250., 300.]
    pose.people[0].xy[i] = [300., 300.]
    pose.people[0].xy[i+1] = [300+50*math.cos(math.radians(angle)), 300+50*math.sin(math.radians(angle))]
    metric = exercise_spec(eid)['metric']
    assert settled(pose).value(metric) == pytest.approx(angle)
    assert all(v is None for v in pose.people[0].conf)
    pose.people[0].xy[i+1] = pose.people[0].xy[i][:]
    assert settled(pose).value(metric) is None


def test_hand_unknown_confidence_requires_temporal_warmup_after_gap():
    p = frame('mediapipe-hand21-v1')
    analyzer = PoseAnalyzer()
    assert analyzer.analyze(p).status == 'UNKNOWN'
    p.time_s = .2
    assert analyzer.analyze(p).status == 'VALID'
    p.time_s = 1.0
    assert analyzer.analyze(p).status == 'UNKNOWN'


def test_analyzer_cannot_reuse_hand_evidence_across_epoch():
    p = frame('mediapipe-hand21-v1')
    analyzer = PoseAnalyzer()
    analyzer.analyze(p)
    p.time_s = .2
    assert analyzer.analyze(p).status == 'VALID'
    p.context = Context(2, 'rehab', 'new', 'SYNTHETIC', 'TEST')
    p.time_s = .3
    assert analyzer.analyze(p).status == 'UNKNOWN'


def sdk_points(count, x=.25, y=.5):
    return [NS(x=x, y=y, visibility=.9, presence=.8) for _ in range(count)]


def test_sdk_adapter_scales_pixels_and_does_not_invent_hand_confidence():
    points = sdk_points(21)
    result = NS(hand_landmarks=[points], handedness=[[NS(category_name='Left', score=.999)]])
    target = encode_result(result, 'mediapipe_hands', 1280, 720)[0]
    assert target['xy'][0] == [320, 360]
    assert target['conf'] == [None]*21
    assert target['attributes']['handedness_score'] == .999
    body = encode_result(NS(pose_landmarks=[sdk_points(33)]), 'mediapipe_pose', 1280, 720)[0]
    assert body['conf'] == [.8]*33
    points[0].x = float('nan')
    assert encode_result(result, 'mediapipe_hands', 1280, 720)[0]['xy'][0][0] is None


def test_wrist_matching_rejects_other_hand_and_multi_hand_without_filling():
    p = sdk_points(33)
    p[15].x, p[16].x = .25, .75
    hands = NS(hand_landmarks=[sdk_points(21)], handedness=[])
    bodies = NS(pose_landmarks=[p])
    merged = merge_wrist(bodies, hands, 1280, 720, 'left')[0]
    assert len(merged['xy']) == 54 and merged['attributes']['hand_matched']
    other = merge_wrist(bodies, hands, 1280, 720, 'right')[0]
    assert other['xy'][33:] == [[None, None]]*21
    hands.hand_landmarks.append(sdk_points(21))
    assert not merge_wrist(bodies, hands, 1280, 720, 'left')[0]['attributes']['hand_matched']


def test_short_protocol_frame_is_rejected():
    with pytest.raises(EOFError):
        _read_exact(io.BytesIO(b'12'), 3)


def test_worker_receive_is_bounded_and_can_be_cancelled():
    backend = LandmarkBackend('mediapipe_hands')
    start = time.monotonic()
    with pytest.raises(TimeoutError):
        backend._receive(.01)
    assert time.monotonic()-start < .5
    backend.cancel_event.set()
    with pytest.raises(RuntimeError, match='取消'):
        backend._receive(25.)


def test_stale_protocol_reply_closes_only_owned_model_process(monkeypatch):
    class OwnedProcess:
        def __init__(self):
            self.stdin, self.stdout = io.BytesIO(), io.BytesIO()
            self.terminated = False
        def poll(self):
            return 0 if self.terminated else None
        def terminate(self):
            self.terminated = True
        def wait(self, timeout):
            return 0
    backend = LandmarkBackend('mediapipe_hands')
    owned = OwnedProcess()
    backend.process = owned
    backend.responses.put({'kind': 'result', 'seq': 99, 'epoch': 'old', 'targets': []})
    context = Context(1, 'rehab', 'synthetic-protocol', 'SYNTHETIC', 'TEST')
    packet = FramePacket(context, 1, 0., 0., '', np.zeros((32,32,3), dtype=np.uint8))
    with pytest.raises(RuntimeError, match='过期'):
        backend.infer(packet)
    assert owned.terminated and backend.process is None


def test_missing_optional_interpreter_has_no_download_or_process_start(tmp_path, monkeypatch):
    monkeypatch.setattr('app.landmark_backend.verified_model', lambda *args: (tmp_path/'not-loaded.task', 'a'*64))
    backend = LandmarkBackend('mediapipe_hands', python_path=tmp_path/'missing-python.exe')
    with pytest.raises(RuntimeError, match='独立环境'):
        backend._start()
    assert backend.process is None


def test_manifest_mismatch_or_missing_model_fails_without_download(tmp_path):
    with pytest.raises(RuntimeError, match='清单'):
        verified_model('mediapipe_hands', tmp_path)
    model = tmp_path/'hand.task'
    model.write_bytes(b'synthetic-test-model')
    manifest = {'models': {'mediapipe_hands': {'filename': model.name, 'schema_id': 'mediapipe-hand21-v1', 'sha256': 'wrong'}}}
    (tmp_path/'landmarks-manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises(RuntimeError, match='SHA256'):
        verified_model('mediapipe_hands', tmp_path)
    manifest['models']['mediapipe_hands']['sha256'] = hashlib.sha256(model.read_bytes()).hexdigest()
    (tmp_path/'landmarks-manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    assert verified_model('mediapipe_hands', tmp_path)[0] == model


def observations(values, metric='angle', track='one'):
    return [Observation(i*.1, track, 'VALID', {metric: Metric.of(value)}) for i,value in enumerate(values)]


def test_baseline_requires_continuous_visible_and_stable_suffix():
    history = observations([30.]*13)
    assert stable_preview_value(history, 'angle', now_time=1.2, track_key='one') == 30
    history[7].metrics['angle'] = Metric.missing('occlusion')
    with pytest.raises(ValueError):
        stable_preview_value(history, 'angle', now_time=1.2, track_key='one')
    with pytest.raises(ValueError):
        stable_preview_value(observations(list(range(13))), 'angle', now_time=1.2, track_key='one')
    with pytest.raises(ValueError):
        stable_preview_value(observations([30.]*13), 'angle', now_time=1.2, track_key='other')


def test_signed_baseline_handles_angle_wrap_without_false_large_range():
    history = observations([179., -179.]*7)
    result = stable_preview_value(history, 'angle', now_time=1.3, track_key='one', circular=True)
    assert abs(abs(result)-180) < 2
    assert angle_delta(-179, 179) == 2


NEW_IDS = [e for e in EXERCISE_IDS if exercise_spec(e)['baseline_required']]


@pytest.mark.parametrize('eid', NEW_IDS)
def test_each_new_action_auto_establishes_baseline_and_counts_only_complete_return(eid):
    plan = default_plan(eid)
    spec = exercise_spec(eid)
    rest = 0. if spec['directional_calibration'] else 40.
    engine = RehabEngine(plan)
    direction = 1 if spec['target_direction'] == 'increase' else -1
    def feed(value, count=15):
        for _ in range(count):
            t = 0. if engine.last_t is None else engine.last_t+.1
            engine.process(Observation(t, 'one', 'VALID', {spec['metric']: Metric.of(value)}))
    feed(rest)
    assert engine.automatic_rest_value == pytest.approx(rest)
    feed(rest+direction*30)
    assert engine.completed == 0
    feed(rest)
    assert engine.completed == 1
    assert engine.repetitions[0]['target_status'] == 'NOT_SET'
    assert engine.summary()['motion_range']['range_deg'] == pytest.approx(30)


@pytest.mark.parametrize('backend', ['mediapipe_pose', 'mediapipe_hands', 'mediapipe_wrist'])
@pytest.mark.skipif(not landmark_python().is_file() or not (ROOT/'assets/models/hand_landmarker.task').is_file(),
                    reason='Optional official local runtime/models not prepared')
def test_official_local_models_really_load_on_blank_image_without_false_person(backend):
    p = frame()
    packet = FramePacket(p.context, 1, 0., time.monotonic(), '', np.zeros((480,640,3), dtype=np.uint8))
    worker = LandmarkBackend(backend)
    try:
        output = worker.infer(packet)
        process = worker.process
        assert output.schema_id == BACKEND_SCHEMAS[backend]
        assert output.people == []
        assert worker.runtime_version == '1.0.1'
    finally:
        worker.close()
    assert process.poll() is not None
