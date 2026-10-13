"""Automatic tracking contracts; synthetic images are not lift accuracy evidence."""
import json
import math

import cv2
import numpy as np
import pytest

from mobile_rehab.automatic_motion import AutomaticTracker, body_scale, detect_plate, summarize


def image(y=300):
    result = np.zeros((480, 640, 3), np.uint8)
    cv2.circle(result, (320, y), 65, (220, 220, 220), -1)
    cv2.circle(result, (320, y), 20, (40, 40, 40), -1)
    return result


def test_plate_is_found_without_any_marks_or_reference_dimensions():
    p = detect_plate(image(), {})
    assert p is not None
    assert p['point'] == pytest.approx([320, 300], abs=9)
    assert p['radius'] == pytest.approx(65, abs=9)
    tracker = AutomaticTracker()
    for i in range(50):
        tracker.consume(image(300-i), i/30)
    r = tracker.report()
    assert r['automatic'] and not r['synthetic']
    assert r['measurement']['scale_source'] == 'plate_diameter_prior'
    assert r['measurement']['approximate'] is True
    assert r['summary']['peak_velocity_m_s'] > 0
    assert r['summary']['peak_specific_lifting_power_w_kg'] > 0
    assert r['calibration']['mass_kg'] is None
    assert r['summary']['peak_power_w'] is None
    json.dumps(r, allow_nan=False)


def samples(metric=False, missing=None):
    out = []
    for i in range(301):
        t = i/30
        height = .2*(1-math.cos(math.pi*(t-1))) if 1 <= t <= 3 else .2*(1-math.cos(math.pi*(t-5))) if 5 <= t <= 7 else 0
        out.append(dict(t=t, point=None if i == missing else [320., 300-height*200],
                        scale=200., size=[640, 480], epoch=0))
    return out


@pytest.mark.parametrize('metric', [False, True])
def test_relative_and_metric_units_never_mix(metric):
    r = summarize(samples(), dict(target_kind='plate' if metric else 'wrist',
                                   length_unit='m' if metric else 'relative', speed_unit='m/s' if metric else '躯干长度/s'))
    assert r['summary']['bounded_segments'] == 2
    assert r['summary']['tracked_ratio'] == 1
    assert (r['summary']['peak_velocity_m_s'] is not None) == metric
    assert (r['summary']['peak_relative_velocity'] is not None) != metric
    assert all(v['force_n'] is None and v['power_w'] is None for v in r['series'])
    if not metric:
        assert all(v['height_m'] is None and v['acceleration_m_s2'] is None for v in r['series'])


def test_gap_epoch_and_unknown_do_not_join_or_make_zero_measurements():
    s = samples(missing=60)
    r = summarize(s, dict(target_kind='wrist', length_unit='relative'))
    assert r['summary']['bounded_segments'] == 1
    assert r['series'][60]['point'] is None
    assert r['series'][60]['relative_velocity'] is None
    for row in s[150:]:
        row['epoch'] = 2
    r = summarize(s, dict(target_kind='wrist', length_unit='relative'))
    assert r['series'][150]['relative_height'] == 0  # observed new origin, not old continuation
    empty = AutomaticTracker().report()
    assert empty['summary']['peak_velocity_m_s'] is None
    assert empty['summary']['bounded_segments'] == 0


def test_body_scale_degrades_without_requiring_hips():
    assert body_scale({'left_shoulder': [100, 100], 'right_shoulder': [200, 100]}, 640, 480)[1] == 'shoulder_width'
    assert body_scale({}, 640, 480)[1] == 'image_height'


def test_low_sampling_rate_keeps_relative_velocity():
    rows = [dict(t=i*.24, point=[100, 200-i*2], scale=100, size=[320, 240], epoch=0) for i in range(40)]
    result = summarize(rows, dict(target_kind='wrist', length_unit='relative'))
    assert result['summary']['peak_relative_velocity'] > .08
    assert sum(s['relative_velocity'] is not None for s in result['series']) > 30


def test_automatic_wrist_choice_does_not_mix_sides(monkeypatch):
    from types import SimpleNamespace
    from mobile_rehab import automatic_motion
    monkeypatch.setattr(automatic_motion, 'detect_plate', lambda *args: None)
    tracker = AutomaticTracker('left')
    for i in range(60):
        conf = [0]*17
        conf[9], conf[10] = (1 if i < 5 else 0), 1
        pose = SimpleNamespace(people=[SimpleNamespace(bbox=[0, 0, 640, 480], track_key='TEST',
                xy=[[320, 300-i]]*17, conf=conf)], size=(640, 480))
        tracker.consume(image(), i/30, pose)
    result = tracker.report()
    assert result['measurement']['target_source'] == 'right_wrist'
    assert result['summary']['tracked_ratio'] == 1
    assert result['summary']['peak_relative_velocity'] > 0


def test_brief_circle_lock_does_not_erase_continuous_wrist(monkeypatch):
    from types import SimpleNamespace
    from mobile_rehab import automatic_motion
    tracker = AutomaticTracker()
    monkeypatch.setattr(automatic_motion, 'detect_plate', lambda image, points:
                        dict(point=[320, 300], radius=65, score=1) if 280 < points['left_wrist'][1] < 295 else None)
    for i in range(90):
        pose = SimpleNamespace(people=[SimpleNamespace(bbox=[0, 0, 640, 480], track_key='TEST',
                xy=[[320, 300-i]]*17, conf=[1]*17)], size=(640, 480))
        tracker.consume(image(), i/30, pose)
    result = tracker.report()
    assert result['measurement']['target_kind'] == 'wrist'
    assert result['summary']['tracked_ratio'] == 1
    assert result['summary']['peak_relative_velocity'] > 0
    assert result['summary']['peak_velocity_m_s'] is None


@pytest.mark.parametrize('trajectory_failure', [False, True])
def test_plain_video_needs_no_calibration_and_preserves_anatomical_results(tmp_path, monkeypatch, trajectory_failure):
    from mobile_rehab import fitness_analyzer
    from app.domain import PoseFrame
    class EmptyVision:
        def __init__(self, **kwargs):
            pass
        def infer(self, packet, **kwargs):
            return PoseFrame(packet.context, packet.seq, packet.time_s, (640, 480), [], model_manifest_id='TEST-empty')
        def close(self):
            pass
    monkeypatch.setattr(fitness_analyzer, 'VisionWorker', EmptyVision)
    if trajectory_failure:
        def unavailable(self):
            raise ValueError('TEST trajectory-only report failure')
        monkeypatch.setattr(AutomaticTracker, 'report', unavailable)
    writer = cv2.VideoWriter(str(tmp_path/'video.mp4'), cv2.VideoWriter_fourcc(*'mp4v'), 30., (640, 480))
    assert writer.isOpened()
    for i in range(120):
        t = i/30
        delta = 70*(1-math.cos(math.pi*(t-1))) if 1 <= t <= 3 else 0
        writer.write(image(300-round(delta)))
    writer.release()
    (tmp_path/'job.json').write_text(json.dumps(dict(id='TEST-automatic', mode='fitness', exercise='fitness_deadlift', side='left')), encoding='utf-8')
    fitness_analyzer.analyze(tmp_path/'job.json')
    result = json.loads((tmp_path/'result.json').read_text(encoding='utf-8'))
    assert result['equipment_analysis']['mode'] == 'automatic'
    if trajectory_failure:
        assert result['barbell'] is None
        assert result['equipment_analysis']['error']
    else:
        assert result['barbell']['automatic']
        assert result['barbell']['summary']['peak_velocity_m_s'] > 0
    assert result['summary']['completed'] == 0
    assert not list(tmp_path.rglob('*.sqlite3'))
