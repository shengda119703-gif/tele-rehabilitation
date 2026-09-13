"""End-to-end measurement contracts using controlled observations and temp data."""
import copy
import csv
import json

import pytest

from app.movement_timing import default_timing_plan, timing_for_plan
from app.reports import export_session, render_report
from app.storage import Storage
from app.training_plans import prepare_training_plan, validate_saved_binding, validate_training_plan
from test_training_execution import Sequence
from test_saved_training_plans import saved_record, profile, SCOPE


def test_observed_joint_phase_times_and_goals_do_not_modify_completion():
    seq = Sequence(target_angle_deg=60, timing_plan=dict(default_timing_plan(), outbound_min_s=3, hold_min_s=1))
    seq.cycle()
    rep = seq.engine.repetitions[0]
    timing = rep['movement_timing']
    assert rep['completion_status'] == 'COMPLETE' and rep['target_status'] == 'MET'
    assert timing['outbound_s']['value'] == pytest.approx(.1)
    assert timing['endpoint_dwell_s']['value'] == pytest.approx(1.4)
    assert timing['return_s']['value'] == pytest.approx(.3)
    assert timing['target_hold_s']['value'] == pytest.approx(1.4)
    assert timing['goals'] == {'outbound': 'NOT_MET', 'return': 'NOT_SET', 'hold': 'MET'}
    # Reading a summary or changing its copy cannot change the source record.
    seq.engine.summary()['last_movement_timing']['outbound_s']['value'] = 999
    assert rep['movement_timing']['outbound_s']['value'] == pytest.approx(.1)


def test_short_occlusion_keeps_count_but_does_not_make_a_valid_tempo():
    seq = Sequence(target_angle_deg=60, timing_plan=dict(default_timing_plan(), hold_min_s=2))
    seq.frames(0)
    seq.frames(75, n=8)
    seq.frames(75, n=1, valid=False)
    assert seq.engine.summary()['movement_timing_live'] is None
    seq.frames(75, n=8)
    seq.frames(0)
    timing = seq.engine.repetitions[-1]['movement_timing']
    assert seq.engine.completed == 1
    assert timing['target_hold_s']['value'] == pytest.approx(.7)
    assert timing['goals']['hold'] == 'UNASSESSABLE'
    assert all(timing[k]['value'] is None for k in ('outbound_s', 'endpoint_dwell_s', 'return_s'))


@pytest.mark.parametrize('boundary', ['pause', 'gap', 'identity'])
def test_boundaries_preserve_observed_hold_but_never_join_another_interval(boundary):
    seq = Sequence(target_angle_deg=60, timing_plan=dict(default_timing_plan(), hold_min_s=1))
    seq.frames(0)
    seq.frames(75)
    if boundary == 'pause':
        seq.command('pause')
        seq.frames(75, n=40)
        seq.command('resume')
    elif boundary == 'gap':
        seq.t += 2
        seq.frames(75)
    else:
        seq.frames(75, track='another')
    old = seq.engine.repetitions[0]['movement_timing']
    assert old['target_hold_s']['value'] == pytest.approx(1.4)
    assert old['goals']['hold'] == 'MET'
    assert old['return_s']['value'] is None
    assert seq.engine.completed == 0


def test_standing_hold_guidance_survives_set_completion_and_pause_ends_it():
    seq = Sequence('sit_to_stand', target_reps=1, target_sets=1,
                   timing_plan=dict(default_timing_plan(), hold_min_s=3))
    seq.frames(knee=90, hip=.65)
    seq.frames(knee=40, hip=.52)
    seq.frames(knee=5, hip=.4, n=8)
    assert seq.engine.stage == 'RECOVERY' and seq.engine.completed == 1
    assert '连续观察' in seq.engine.summary()['message']
    assert '/ 3 秒' in seq.engine.summary()['message']
    seq.frames(knee=5, hip=.4, valid=False, n=1)
    assert '未计入' in seq.engine.summary()['message']
    seq.frames(knee=5, hip=.4, n=2)
    seq.command('pause')
    assert seq.engine.summary()['movement_timing_live'] is None
    seq.frames(knee=5, hip=.4, n=50)
    seq.engine.finish('user_stop')
    timing = seq.engine.repetitions[0]['movement_timing']
    assert timing['outbound_s']['valid'] and timing['return_s']['value'] is None
    assert timing['target_hold_s']['value'] == pytest.approx(.7)
    assert timing['goals']['hold'] == 'UNASSESSABLE'


def test_return_occlusion_never_emits_legacy_lowering_quality_issue():
    seq = Sequence('sit_to_stand', lowering_tempo_min_s=20)
    seq.frames(knee=90, hip=.65)
    seq.frames(knee=40, hip=.52)
    seq.frames(knee=5, hip=.4)
    seq.frames(knee=45, hip=.52, n=5)
    seq.frames(knee=45, hip=.52, n=1, valid=False)
    seq.frames(knee=90, hip=.65)
    rep = seq.engine.repetitions[0]
    assert seq.engine.completed == 1 and rep['rise_time_s'] is not None
    assert rep['lowering_time_s'] is None
    assert not any(i['rule_id'] == 'lowering_tempo' for i in rep['issues'])
    assert rep['movement_timing']['goals']['return'] == 'UNASSESSABLE'


def test_saved_v010_plan_without_new_key_is_reusable_without_invented_goals():
    record = saved_record()
    for entry in record['items']:
        entry['settings'].pop('timing_plan')
    original = copy.deepcopy(record)
    normalized = validate_training_plan(record)
    assert normalized['items'][0]['settings']['timing_plan'] == default_timing_plan()
    plan = prepare_training_plan(record, record['items'][0]['key'], profile())
    binding = validate_saved_binding(record, plan['saved_plan_reference'], plan, SCOPE)
    assert binding['session_overrides'] == {}
    assert record == original


def test_old_sitstand_tempo_maps_explicitly_and_conflicting_settings_reject():
    seq = Sequence('sit_to_stand', lowering_tempo_min_s=2, lowering_tempo_max_s=5)
    assert seq.engine.timing_plan['return_min_s'] == 2
    conflicting = dict(seq.engine.plan, timing_plan=dict(default_timing_plan(), return_min_s=3))
    with pytest.raises(ValueError, match='不一致'):
        timing_for_plan(conflicting)


def test_timing_reopens_and_html_json_csv_agree_without_rewriting_old_records(tmp_path):
    seq = Sequence(target_angle_deg=60, timing_plan=dict(default_timing_plan(), hold_min_s=1))
    seq.cycle()
    seq.engine.finish('user_stop')
    snapshot = dict(id='timed', scene_id='rehab', participant_id='timing-qa', source_kind='SYNTHETIC',
                    usage_context='TEST', exercise_id='shoulder_abduction', side='left', submode='training',
                    start_utc='2026-09-10T08:00:00+00:00', end_utc='2026-09-10T08:00:05+00:00', status='FINISHED',
                    summary=seq.engine.summary(), repetitions=seq.engine.repetitions, config_snapshot={'plan': seq.engine.plan})
    db = tmp_path/'data.sqlite3'
    store = Storage(db)
    store.save_session(snapshot)
    store.close()
    store = Storage(db)
    restored = store.get_session('timed')
    assert restored['repetitions'] == snapshot['repetitions']
    store.close()
    out = export_session(restored, tmp_path/'export')
    rep = json.loads((out/'repetitions.json').read_text(encoding='utf-8'))[0]
    with (out/'repetitions.csv').open(encoding='utf-8-sig', newline='') as stream:
        row = list(csv.DictReader(stream))[0]
    assert float(row['target_hold_s']) == pytest.approx(rep['movement_timing']['target_hold_s']['value'])
    assert row['timing_goal_hold'] == 'MET' and row['target_hold_s_valid'] == 'True'
    html = (out/'report.html').read_text(encoding='utf-8')
    assert '最长连续保持' in html and '峰区' in html and '不累加' in html
    legacy = copy.deepcopy(restored)
    for r in legacy['repetitions']:
        r.pop('movement_timing')
    original = copy.deepcopy(legacy)
    assert '不从旧总时长补算' in render_report(legacy)
    assert legacy == original
