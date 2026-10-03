"""Synthetic geometry/cycles are unit evidence, not validation on human lifting."""
import math

import pytest
from mobile_rehab.core import CORE
from mobile_rehab.fitness import FitnessEngine, EXERCISES, angle, measure
from app.domain import Context, PoseFrame, PosePerson

CTX = Context(1, 'fitness', 'fixture', 'SYNTHETIC', 'TEST', 'test-run')


def pose(eid, degrees, t, side='left', confidence=1., track='one'):
    xy = [[100.+i*20, 100.+i*15] for i in range(17)]
    indices = {'knee': [11, 13, 15], 'hip': [5, 11, 13], 'elbow': [5, 7, 9]}[EXERCISES[eid]['metric']]
    indices = [i+(side == 'right') for i in indices]
    r = math.radians(degrees)
    a, b, c = indices
    xy[a], xy[b], xy[c] = [500., 300.], [500., 500.], [500+180*math.sin(r), 500-180*math.cos(r)]
    conf = [1.]*17
    conf[b] = confidence
    return PoseFrame(CTX, int(t*100)+1, t, (1000, 1000),
                     [PosePerson(track, [100, 100, 900, 900], xy, conf)], model_manifest_id='test-only')


def motion(eid):
    a, b = (170., 65.) if EXERCISES[eid]['start_angle'] > EXERCISES[eid]['turn_angle'] else (80., 175.)
    return [a]*12+[a+(b-a)*i/8 for i in range(1, 9)]+[b]*8+[b+(a-b)*i/8 for i in range(1, 9)]+[a]*10


@pytest.mark.parametrize('eid', EXERCISES)
@pytest.mark.parametrize('side', ['left', 'right'])
def test_each_action_counts_and_times_two_cycles(eid, side):
    engine = FitnessEngine(eid, side)
    sequence = motion(eid)*2
    for index, value in enumerate(sequence):
        engine.consume(pose(eid, value, index*.1, side))
    result = engine.summary()
    assert result['completed'] == 2
    if eid == 'fitness_bench_press':
        assert set(result['metrics']) == {'elbow', 'upper_arm'}
    assert result['valid_ratio'] == 1.
    assert result['tempo_cv'] is None  # at least 3 full cycles required
    for rep in engine.repetitions:
        assert rep['start']['t'] < rep['turn']['t'] < rep['end']['t']
        assert rep['range_deg'] > 30
        assert rep['outbound_s'] > 0 and rep['return_s'] > 0


@pytest.mark.parametrize('eid', EXERCISES)
def test_missing_point_does_not_join_halves(eid):
    engine = FitnessEngine(eid, 'left')
    sequence = motion(eid)
    for index, value in enumerate(sequence):
        engine.consume(pose(eid, value, index*.1, confidence=0 if index == 22 else 1))
    assert engine.summary()['completed'] == 0
    assert engine.summary()['partial'] == 1
    assert any(p['angle'] is None for p in engine.series)


def test_timestamp_gap_identity_and_schema():
    eid = 'fitness_squat'
    engine = FitnessEngine(eid, 'left')
    for i, v in enumerate(motion(eid)):
        engine.consume(pose(eid, v, i*.1+(1 if i >= 22 else 0)))
    assert engine.summary()['completed'] == 0
    engine = FitnessEngine(eid, 'left')
    for i, v in enumerate(motion(eid)):
        engine.consume(pose(eid, v, i*.1, track='one' if i < 22 else 'bystander'))
    assert engine.summary()['completed'] == 0
    with pytest.raises(ValueError):
        engine.consume(pose(eid, 170, 0.))
    other = pose(eid, 170, 10.)
    other.schema_id = 'unknown'
    with pytest.raises(ValueError):
        engine.consume(other)


def test_empty_stationary_and_partial_start():
    eid = 'fitness_bench_press'
    engine = FitnessEngine(eid, 'left')
    for i in range(40):
        p = pose(eid, 90 if i < 20 else 170, i*.1)
        engine.consume(p)
    assert engine.summary()['completed'] == 0
    assert engine.summary()['mean_cycle_s'] is None
    empty = FitnessEngine(eid, 'left')
    for i in range(10):
        p = pose(eid, 170, i*.1)
        p.people = []
        empty.consume(p)
    assert empty.summary()['valid_ratio'] == 0
    assert empty.summary()['metrics'] == {}


def test_geometry_low_confidence_and_no_unrelated_hip_requirement():
    assert angle([0, 10], [0, 0], [10, 0]) == 90
    assert angle([0, 0], [0, 0], [10, 0]) is None
    p = pose('fitness_bench_press', 90, 0)
    p.people[0].conf[11] = 0
    metrics, points = measure(p.people[0], 'left', p.size)
    assert metrics['elbow'] == 90
    assert metrics['hip'] is None
    assert 'hip' not in points
    p.people[0].xy[7][0] = float('nan')
    assert measure(p.people[0], 'left', p.size)[0]['elbow'] is None


def test_gap_breaks_plot_and_new_context_can_select_new_track():
    eid = 'fitness_squat'
    engine = FitnessEngine(eid, 'left')
    engine.consume(pose(eid, 170, 0))
    engine.consume(pose(eid, 170, 1))
    assert engine.series[1]['angle'] is None
    new_context = Context(2, 'fitness', 'other-fixture', 'SYNTHETIC', 'TEST', 'other-run')
    for i, value in enumerate(motion(eid)):
        p = pose(eid, value, 2+i*.1, track='other-track')
        p.context = new_context
        engine.consume(p)
    assert engine.summary()['completed'] == 1
    assert engine.track == 'other-track'


def test_fitness_video_adapter_replay_and_saved_keyframes(tmp_path, monkeypatch):
    import cv2
    import json
    import numpy as np
    from mobile_rehab import fitness_analyzer
    from mobile_rehab.server import save
    sequence = motion('fitness_squat')
    class TestVision:
        def __init__(self, **kwargs):
            pass
        def infer(self, packet, **kwargs):
            value = sequence[min(len(sequence)-1, round(packet.time_s*10))]
            result = pose('fitness_squat', value, packet.time_s)
            result.context = packet.context
            return result
        def close(self):
            pass
    monkeypatch.setattr(fitness_analyzer, 'VisionWorker', TestVision)
    writer = cv2.VideoWriter(str(tmp_path / 'video.mp4'), cv2.VideoWriter_fourcc(*'mp4v'), 10., (1000, 1000))
    assert writer.isOpened()
    for _ in sequence:
        writer.write(np.zeros((1000, 1000, 3), dtype=np.uint8))
    writer.release()
    save(tmp_path / 'job.json', dict(id='adapter-test', owner='test-only', mode='fitness', exercise='fitness_squat', side='left'))
    fitness_analyzer.analyze(tmp_path / 'job.json')
    result = json.loads((tmp_path / 'result.json').read_text(encoding='utf-8'))
    assert result['summary']['completed'] == 1
    assert result['conditions']['size'] == [1000, 1000]
    assert result['repetitions'][0]['turn']['points']['knee'] == [.5, .5]
    assert result['series'] and result['source_kind'] == 'REPLAY_FILE'
