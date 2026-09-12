import copy
from datetime import datetime, timedelta, timezone

import pytest

from app.automatic_plans import (ORIGIN, RECIPES, create_automatic_plan, generate_proposal,
                                 observed_quality, program_progress, validate_automatic_use)
from app.assessment import build_body_profile
from app.exercises import exercise_spec
from app.storage import Storage
from app.training_plans import prepare_training_plan, validate_training_plan
from test_saved_training_plans import assessment, SCOPE

NOW = datetime(2026, 9, 12, 10, tzinfo=timezone.utc)
SCREEN = dict(general_activity_ok=True, standing_support_ok=True, companion_present=False)


def measured(eid='shoulder_abduction', side='left', **changes):
    spec = exercise_spec(eid)
    row = assessment(exercise_id=eid, side=side, id=eid+':'+side,
                     measurement_contract=spec['measurement_contract'],
                     start_utc=(NOW-timedelta(minutes=2)).isoformat(),
                     end_utc=(NOW-timedelta(minutes=1)).isoformat())
    row['summary'].update(primary_metric=spec['metric'], completed=3, partial=0, invalid=0)
    row.update(changes)
    return row


def proposal(sessions=None, participant=None):
    sessions = [measured()] if sessions is None else sessions
    return generate_proposal(build_body_profile(sessions, **SCOPE), sessions, participant, now=NOW)


def record(sessions=None, participant=None):
    value = create_automatic_plan(proposal(sessions, participant), SCREEN, now=NOW)
    value.update(revision=1)
    return value


def test_no_form_required_and_targets_are_explicit_adaptations_with_sources():
    p = proposal()
    r = record()
    assert p['body'][0]['session_id'] == measured()['id']
    assert r['record_origin'] == ORIGIN
    assert r['items'][0]['settings']['target_reps'] == 3
    assert r['items'][0]['settings']['target_sets'] == 1
    assert r['items'][0]['settings']['target_angle_deg'] == 53
    assert r['items'][0]['settings']['allowed_trunk_tilt_deg'] is None
    assert r['automatic']['entries'][0]['source']['url'].startswith('https://www.nth.nhs.uk/')
    assert r['automatic']['screening'] == SCREEN
    assert validate_training_plan(r)['automatic'] == r['automatic']
    assert '不是疾病' in p['note']
    from app.exercises import EXERCISE_IDS
    assert set(RECIPES) == set(EXERCISE_IDS)


@pytest.mark.parametrize('eid', RECIPES)
@pytest.mark.parametrize('side', ('left', 'right'))
def test_all_53_actions_and_both_sides_have_compatible_current_contract(eid, side):
    p = proposal([measured(eid, side)])
    assert len(p['candidates']) == 1
    entry = p['candidates'][0]
    assert entry['side'] == side
    assert entry['measurement_contract'] == exercise_spec(eid)['measurement_contract']
    assert entry['assessment_fingerprint']
    assert entry['source']['section']
    generated = create_automatic_plan(p, SCREEN, now=NOW)
    assert validate_training_plan(generated)['items'][0]['key'] == f'{eid}:{side}'
    if eid == 'knee_extension':
        assert entry['settings']['target_angle_deg'] == 17
    if eid == 'sit_to_stand':
        assert entry['settings']['target_angle_deg'] is None


@pytest.mark.parametrize('change', [dict(status='INTERRUPTED'), dict(measurement_contract='old'),
    dict(measurement_mode='guided_timed'), dict(source_kind='REPLAY_FILE'), dict(participant_id='other'),
    dict(usage_context='CONTROLLED_DEMO'), dict(end_utc='2026-09-01T10:00:00Z'),
    dict(end_utc='2027-09-01T10:00:00Z')])
def test_invalid_stale_other_scope_and_guided_records_are_not_evidence(change):
    assert proposal([measured(**change)])['candidates'] == []


@pytest.mark.parametrize('field,value', [('valid_ratio', None), ('valid_ratio', .79),
    ('valid_ratio', float('nan')), ('completed', 0), ('completed', True),
    ('completed', None), ('motion_range', None)])
def test_inadequate_evidence_is_not_turned_into_a_plan(field, value):
    s = measured()
    s['summary'][field] = value
    assert not proposal([s])['candidates']


def test_latest_failure_does_not_resurrect_old_success():
    old = measured()
    bad = measured(id='new-failure', end_utc=NOW.isoformat(), summary={'valid_ratio': 0, 'motion_range': None})
    assert not proposal([old, bad])['candidates']
    assert proposal([old, bad])['body'][0]['session_id'] == 'new-failure'


def test_order_cap_sides_and_supported_standing_are_not_inferred():
    all_rows = [measured(eid, side) for eid in RECIPES for side in ('left', 'right')]
    p = proposal(all_rows)
    r = create_automatic_plan(p, dict(SCREEN, standing_support_ok=False), now=NOW)
    assert len(r['items']) == 4 and not any(i['standing'] for i in r['automatic']['entries'])
    assert {i['side'] for i in r['items']} == {'left', 'right'}
    with pytest.raises(ValueError, match='站立'):
        create_automatic_plan(proposal([measured('sit_to_stand')]), dict(SCREEN, standing_support_ok=False), now=NOW)


def test_next_generated_block_prioritises_actions_not_yet_trained():
    sessions = [measured('shoulder_abduction'), measured('shoulder_flexion'), measured('elbow_flexion')]
    first = record(sessions)
    trained = execution(first)
    p = proposal(sessions+[trained])
    assert p['candidates'][-1]['key'] == first['items'][0]['key']
    assert p['candidates'][0]['key'] != first['items'][0]['key']
    interrupted = execution(first, status='INTERRUPTED', summary={'plan_completed': False})
    assert proposal(sessions+[interrupted])['candidates'][0]['key'] == first['items'][0]['key']


@pytest.mark.parametrize('screen', [None, {}, dict(SCREEN, general_activity_ok=False), dict(SCREEN, general_activity_ok=1)])
def test_missing_or_unfavourable_screen_is_not_default_consent(screen):
    with pytest.raises(ValueError):
        create_automatic_plan(proposal(), screen, now=NOW)


def test_known_restrictions_and_required_companion_are_respected():
    with pytest.raises(ValueError, match='限制'):
        create_automatic_plan(proposal(participant={'restrictions': '术后限制'}), SCREEN, now=NOW)
    p = proposal(participant={'support': 'assisted'})
    with pytest.raises(ValueError, match='陪同'):
        create_automatic_plan(p, SCREEN, now=NOW)
    r = create_automatic_plan(p, dict(SCREEN, companion_present=True), now=NOW)
    assert r['items'][0]['settings']['needs_companion'] is True


def test_persistence_and_frozen_provenance_survive_reopen(tmp_path):
    r = record()
    store = Storage(tmp_path/'test.sqlite3')
    saved = store.save_training_plan(r, expected_revision=0)
    store.close()
    store = Storage(tmp_path/'test.sqlite3')
    try:
        loaded = store.get_training_plan(saved['id'])
        assert loaded == saved
        p = build_body_profile([measured()], **SCOPE)
        prepared = prepare_training_plan(loaded, loaded['items'][0]['key'], p)
        assert prepared['saved_plan_reference']['automatic'] == saved['automatic']
        validate_automatic_use(loaded, loaded['items'][0]['key'], p, [measured()], None, prepared, now=NOW)
    finally:
        store.close()


@pytest.mark.parametrize('mutation', ['target', 'assessment', 'person', 'expired', 'rule'])
def test_stale_or_modified_plan_cannot_start(mutation):
    s, r = measured(), record()
    p = build_body_profile([s], **SCOPE)
    key = r['items'][0]['key']
    plan = prepare_training_plan(r, key, p)
    person, now = None, NOW
    if mutation == 'target':
        plan['target_reps'] += 1
    elif mutation == 'assessment':
        s['summary']['motion_range']['max_deg'] -= 5
        s['summary']['motion_range']['range_deg'] -= 5
        p = build_body_profile([s], **SCOPE)
    elif mutation == 'person':
        person = {'support': 'assisted'}
    elif mutation == 'expired':
        now += timedelta(days=2)
    else:
        r['automatic']['rule_version'] = 'unreviewed-rules'
    with pytest.raises(ValueError):
        validate_automatic_use(r, key, p, [s], person, plan, now=now)


def test_provenance_and_suitability_metadata_cannot_be_forged():
    from app.automatic_plans import validate_metadata
    for change in ('source', 'standing', 'evidence', 'screening'):
        r = record()
        if change == 'source':
            r['automatic']['entries'][0]['source']['url'] = 'https://example.invalid'
        elif change == 'standing':
            r['automatic']['entries'][0]['standing'] = not r['automatic']['entries'][0]['standing']
        elif change == 'evidence':
            r['automatic']['entries'][0]['evidence_kind'] = 'clinical_guideline'
        else:
            r['automatic']['screening']['general_activity_ok'] = 'yes'
        with pytest.raises(ValueError):
            validate_metadata(r)


def execution(r, index=0, **changes):
    entry = r['items'][index]
    s = dict(SCOPE, id='training-'+str(index), scene_id='rehab', submode='training',
             exercise_id=entry['exercise_id'], side=entry['side'], status='FINISHED',
             end_utc=NOW.isoformat(), summary={'plan_completed': True}, repetitions=[],
             config_snapshot={'plan': {'saved_plan_reference': dict(id=r['id'], revision=r['revision'], entry_key=entry['key'])}},
             training_feedback={'pain': 0, 'fatigue': 0, 'reason': 'completed'})
    s.update(changes)
    return s


def test_sequence_progress_uses_saved_sessions_and_preserves_missing_feedback():
    sessions = [measured(), measured('knee_extension')]
    r = record(sessions)
    first = execution(r)
    p = program_progress(r, [first])
    assert p['completed'] == 1 and p['next_key'] == r['items'][1]['key']
    profile = build_body_profile(sessions, **SCOPE)
    validate_automatic_use(r, p['next_key'], profile, sessions+[first], None, now=NOW)
    with pytest.raises(ValueError, match='顺序'):
        validate_automatic_use(r, r['items'][0]['key'], profile, sessions+[first], None, now=NOW)
    first.pop('training_feedback')
    assert '感受' in program_progress(r, [first])['blocked']


@pytest.mark.parametrize('feedback', [dict(pain=1, fatigue=0), dict(pain=0, fatigue=5),
                                     dict(pain=0, fatigue=0, reason='discomfort')])
def test_discomfort_stops_current_sequence_and_new_automatic_suggestion(feedback):
    r = record()
    s = execution(r, training_feedback=feedback)
    assert program_progress(r, [s])['blocked']
    assert not proposal([measured(), s])['candidates']


@pytest.mark.parametrize('change', [dict(measurement_mode='guided_timed'), dict(status='INTERRUPTED'),
    dict(summary={'plan_completed': False}), dict(participant_id='other'), dict(source_kind='LIVE_CAMERA')])
def test_guided_interrupted_wrong_scope_does_not_complete_program(change):
    r = record()
    assert program_progress(r, [execution(r, **change)])['completed'] == 0


def test_quality_distinguishes_targets_issues_and_unknown_without_changing_reps():
    good = dict(completion_status='COMPLETE', observation_status='VALID', primary_metric='raise_deg',
                metric_validity={'raise_deg': {'valid': True}}, target_status='MET', issues=[])
    reps = [good, dict(good, target_status='NOT_MET'), dict(good, target_status='NOT_SET'),
            dict(good, observation_status='PARTIAL_OBSERVABLE', target_status='NOT_MET'),
            dict(good, issues=[{'evidence_valid': True}]),
            dict(good, movement_timing={'goals': {'return': 'UNASSESSABLE'}})]
    before = copy.deepcopy(reps)
    q = observed_quality(reps)
    assert (q['observed_goals_met'], q['needs_adjustment'], q['unassessable']) == (1, 2, 3)
    assert reps == before
