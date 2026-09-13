"""Synthetic guided-continuation journeys. No camera, no human-accuracy claim."""
import math
import tempfile
import time
import unittest
from pathlib import Path

import numpy as np
import pytest

from app.assessment import build_body_profile
from app.camera_manager import CameraManager
from app.domain import FramePacket, PoseFrame, PosePerson, utc_now
from app.guidance import GuidancePolicy
from app.guided import CYCLE_S, GuidedEngine, prompt_plan, prompt_state
from app.journey import current_step, preparation_steps
from app.reports import continuation_evidence, export_session, render_report, render_result_summary
from app.scene_controller import SceneController
from app.settings import default_plan, default_setup
from app.storage import Storage


class GuidedFixture:
    def __init__(self, directory, exercise='neck_flexion', guided=True):
        self.store = Storage(Path(directory)/'guided.sqlite3')
        self.camera = CameraManager()
        self.c = SceneController(self.store, self.camera, test_mode=True)
        self.source = {'kind': 'SYNTHETIC', 'ref': 'synthetic-guided', 'usage_context': 'TEST'}
        self.setup = default_setup(exercise=exercise)
        self.setup.update(participant_confirmed=True, continuation_mode='guided' if guided else 'auto')
        self.c.open(self.source, self.setup)
        self.seq = 0

    def frame(self, t, angle=0., *, visible=True, people=1):
        self.seq += 1
        context = self.c.context
        xy = [[120., 100.] for _ in range(17)]
        xy[5], xy[6], xy[11], xy[12] = [200., 150.], [300., 150.], [200., 300.], [300., 300.]
        r = math.radians(angle)
        xy[7], xy[9] = [200+100*math.sin(r), 150+100*math.cos(r)], [200+150*math.sin(r), 150+150*math.cos(r)]
        xy[13], xy[15] = [200., 400.], [200., 500.]
        confidence = [1.]*17 if visible else [0.]*17
        crowd = [PosePerson(context.epoch+f':{i+1}', [100, 50, 500, 600], xy, confidence) for i in range(people)]
        pose = PoseFrame(context, self.seq, t, (1280, 720), crowd, model_manifest_id='synthetic-guided-model')
        packet = FramePacket(context, self.seq, t, time.monotonic(), utc_now(),
                            np.zeros((720, 1280, 3), dtype=np.uint8), time_basis='synthetic_test_time')
        return self.c.consume(packet, pose)

    def close(self):
        if self.c.pending:
            self.c.retry_save()
        self.c.stop('test_end')
        self.store.close()


@pytest.fixture
def guided(tmp_path):
    fixture = GuidedFixture(tmp_path)
    yield fixture
    fixture.close()


def test_guided_journey_drops_baseline_steps_but_keeps_the_explicit_acknowledgement():
    plan = default_plan('neck_flexion')
    keys = [step[0] for step in preparation_steps(plan, guided=True)]
    assert keys == ['camera', 'framing', 'confirm', 'start', 'active', 'result']
    assert 'rest' not in keys and 'direction' not in keys
    assert current_step(plan, 'PREVIEW', framed=True, guided=True).key == 'confirm'
    assert current_step(plan, 'PREVIEW', framed=True, confirmed=True, guided=True).key == 'start'
    sit = default_plan('sit_to_stand')
    assert [s[0] for s in preparation_steps(sit, guided=True)][:3] == ['camera', 'framing', 'confirm']


def test_guided_session_starts_without_a_measurable_pose_and_saves_a_labelled_record(guided):
    guided.frame(0., visible=False)
    guided.c.confirm(guided.setup)
    run_id = guided.c.start().run_id
    assert guided.c.state == 'ONLINE' and isinstance(guided.c.engine, GuidedEngine)
    t = 0.
    for _ in range(20):
        guided.frame(t, visible=False)
        t += .1
    assert guided.c.record_self_report() == 1
    assert guided.c.record_self_report() == 2
    guided.c.stop('user_stop')
    saved = guided.store.get_session(run_id)
    assert saved['measurement_mode'] == 'guided_timed'
    assert saved['summary']['completed'] == 0 and saved['summary']['self_reported_reps'] == 2
    assert saved['summary']['motion_range'] is None and saved['summary']['motion_range_valid'] is False
    assert saved['summary']['approximate_range'] is None
    assert saved['repetitions'] == []
    assert [r['origin'] for r in saved['continuation']['self_reports']] == ['participant_report']*2
    assert saved['continuation']['prompt_plan']['version'] == prompt_plan()['version']


def test_guided_session_reports_an_approximate_range_without_claiming_repetitions(tmp_path):
    guided = GuidedFixture(tmp_path, exercise='shoulder_abduction')
    guided.frame(0.)
    guided.c.confirm(guided.setup)
    run_id = guided.c.start().run_id
    t, angles = 0., [0., 4., 8., 12., 16., 20., 16., 12., 8., 4., 0.]
    for angle in angles:
        guided.frame(t, angle)
        t += .1
    guided.c.stop('user_stop')
    saved = guided.store.get_session(run_id)
    guided.close()
    approximate = saved['summary']['approximate_range']
    assert approximate['approximate'] is True and approximate['range_deg'] > 0
    assert saved['summary']['completed'] == 0 and saved['summary']['motion_range'] is None
    evidence = continuation_evidence(saved)
    assert evidence['guided'] and evidence['approximate_range'] == approximate
    summary_html = render_result_summary(saved)
    assert '引导计时' in summary_html and '近似角度范围' in summary_html
    assert '不作为训练所需的评估依据' in summary_html
    assert '近似角度范围' in render_report(saved)


def test_guided_records_are_history_not_assessment_evidence(guided):
    guided.frame(0.)
    guided.c.confirm(guided.setup)
    run_id = guided.c.start().run_id
    for i in range(12):
        guided.frame(i*.1, i*2.)
    guided.c.stop('user_stop')
    saved = guided.store.get_session(run_id)
    assert saved['status'] == 'FINISHED'
    profile = build_body_profile([saved], saved['participant_id'], 'SYNTHETIC', 'TEST')
    item = next(i for i in profile['items'] if i['exercise_id'] == 'neck_flexion' and i['side'] == saved['side'])
    assert item['status'] == 'NOT_ASSESSED' and item['session_id'] is None


def test_guided_selects_a_primary_participant_when_a_carer_is_visible(guided):
    guided.frame(0., people=2)
    guided.c.confirm(guided.setup)
    guided.frame(.4, people=2)
    assert guided.c.confirmed and not guided.c.confirmation_withdrawn
    guided.c.start()
    assert guided.c.state == 'ONLINE'


def test_self_report_is_refused_outside_a_running_rehab_session(guided):
    with pytest.raises(ValueError, match='请先开始'):
        guided.c.record_self_report()


def test_guided_export_keeps_self_reports_as_human_annotations(tmp_path):
    fixture = GuidedFixture(tmp_path/'store')
    try:
        fixture.frame(0.)
        fixture.c.confirm(fixture.setup)
        run_id = fixture.c.start().run_id
        fixture.c.record_self_report()
        fixture.c.stop('user_stop')
        saved = fixture.store.get_session(run_id)
    finally:
        fixture.close()
    out = export_session(saved, tmp_path/'export')
    annotations = (out/'annotations.csv').read_text(encoding='utf-8-sig')
    assert 'self_reported_repetition' in annotations and 'human' in annotations
    assert 'guided_timed' in (out/'continuation.json').read_text(encoding='utf-8')
    assert (out/'repetitions.csv').read_text(encoding='utf-8-sig').strip().count('\n') == 0


def test_prompt_clock_is_a_local_timer_and_never_a_measurement():
    assert prompt_state(-1., 'neck_flexion') is None
    assert prompt_state(float('nan'), 'neck_flexion') is None
    first = prompt_state(0., 'neck_flexion')
    assert first['key'] == 'ready' and first['cycle'] == 1 and first['remaining_s'] == pytest.approx(3.)
    assert prompt_state(3.5, 'neck_flexion')['key'] == 'outbound'
    assert prompt_state(8., 'neck_flexion')['key'] == 'return'
    assert prompt_state(CYCLE_S+.1, 'neck_flexion')['cycle'] == 2
    plan = prompt_plan()
    assert plan['origin'] == 'fixed_local_prompt_timer'
    assert plan['ready_s']+plan['outbound_s']+plan['return_s'] == pytest.approx(CYCLE_S)


def test_guided_guidance_never_asks_for_a_framing_fix_it_does_not_need():
    policy, plan = GuidancePolicy(), default_plan('neck_flexion')
    frame = dict(state='ONLINE', context='one', continuation_mode='guided',
                 observation_status='UNKNOWN', current_measurement_valid=False,
                 adjustment='请调整侧面取景，让左髋也进入画面。', summary={'phase': None},
                 guided_prompt=prompt_state(4., 'neck_flexion'))
    for i in range(30):
        result = policy.render(frame, plan, now=i*.5)
        assert result['level'] == 'status' and '取景' not in result['instruction']
        assert result['measurement_quality'] == 'approximate' and result['offer'] is None
    assert result['prompt_label'] == '做动作'


def test_long_missing_measurement_offers_the_guided_path_instead_of_repeating_itself():
    policy, plan = GuidancePolicy(), default_plan('neck_flexion')
    frame = dict(state='PREVIEW', context='one', observation_status='UNKNOWN',
                 current_measurement_valid=False, adjustment='请让测试部位清楚进入画面。', summary={})
    offers = [policy.render(frame, plan, now=i*.5)['offer'] for i in range(40)]
    assert offers[:20] == [None]*20 and offers[-1] == 'guided'
    assert policy.render(frame, plan, now=25.)['offer_text']


class GuidedEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp.cleanup()

    def test_engine_never_infers_a_repetition_or_a_timing_result(self):
        engine = GuidedEngine(default_plan('shoulder_abduction'))
        summary = engine.summary()
        self.assertEqual(summary['completed'], 0)
        self.assertEqual(summary['measurement_mode'], 'guided_timed')
        self.assertIsNone(summary['movement_timing_version'])
        self.assertIsNone(summary['movement_timing_live'])
        self.assertIsNone(summary['valid_ratio'])
        self.assertEqual(engine.repetitions, [])
        engine.note_prompt_cycle(3)
        engine.note_prompt_cycle(2)
        self.assertEqual(engine.summary()['prompted_cycles'], 3)


def test_guided_pause_stops_crediting_time_and_needs_an_explicit_resume(tmp_path):
    guided = GuidedFixture(tmp_path, exercise='shoulder_abduction')
    guided.frame(0.)
    guided.c.confirm(guided.setup)
    run_id = guided.c.start().run_id
    for i in range(6):
        guided.frame(i*.1)
    observed = guided.c.engine.valid_s
    assert observed > 0
    assert guided.c.set_guided_pause(True) is True
    for i in range(6, 12):
        guided.frame(i*.1)
    assert guided.c.engine.valid_s == pytest.approx(observed)
    assert guided.c.engine.paused_s > 0
    assert guided.c.set_guided_pause(False) is False
    for i in range(12, 20):
        guided.frame(i*.1)
    assert guided.c.engine.valid_s > observed
    guided.c.stop('user_stop')
    saved = guided.store.get_session(run_id)
    guided.close()
    assert saved['continuation']['prompt_pauses'] == 1
    assert saved['summary']['pause_count'] == 1 and saved['summary']['paused_s'] > 0
    assert saved['summary']['prompt_paused'] is False


def test_guided_pause_is_refused_for_a_measuring_session(tmp_path):
    fixture = GuidedFixture(tmp_path, exercise='shoulder_abduction', guided=False)
    try:
        fixture.frame(0.)
        fixture.c.confirm(fixture.setup)
        fixture.c.start()
        with pytest.raises(ValueError, match='引导计时'):
            fixture.c.set_guided_pause(True)
    finally:
        fixture.close()
