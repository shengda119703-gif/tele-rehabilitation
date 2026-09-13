from datetime import datetime, timezone

from app.assessment import build_body_profile
from app.automatic_plans import generate_proposal, validate_automatic_use
from app.demo_training_plan import (DEMO_PLAN_NAME, DEMO_SCOPE, build_demo_plan,
                                    install_demo_plan)
from app.storage import Storage
from app.training_plans import prepare_training_plan


NOW = datetime(2026, 9, 13, 8, 0, tzinfo=timezone.utc)


def test_demo_uses_four_isolated_synthetic_assessments_and_real_rules():
    participant, sessions, proposal, plan = build_demo_plan(now=NOW)
    assert participant['display_name'].startswith('演示患者')
    assert len(sessions) == len(proposal['candidates']) == len(plan['items']) == 4
    assert all(s['source_kind'] == 'SYNTHETIC' and s['usage_context'] == 'TEST' for s in sessions)
    assert all(s['annotation_origin'] == 'synthetic_demo' for s in sessions)
    assert plan['name'] == DEMO_PLAN_NAME
    assert plan['record_origin'] == 'assessment_rules'
    assert [i['settings']['target_reps'] for i in plan['items']] == [5, 5, 5, 5]
    assert [i['settings']['target_angle_deg'] for i in plan['items']] == [63.2, 73.6, 103.0, 41.0]
    assert '不能用于真实患者' in plan['automatic']['note']


def test_install_replaces_only_active_demo_plan_and_remains_executable_as_evidence(tmp_path):
    store = Storage(tmp_path/'demo.sqlite3')
    try:
        first = install_demo_plan(store, now=NOW)
        second = install_demo_plan(store, now=NOW)
        active = store.list_training_plans(DEMO_SCOPE)
        all_plans = store.list_training_plans(DEMO_SCOPE, include_archived=True)
        assert len(active) == 1 and active[0]['id'] == second['plan']['id']
        assert len(all_plans) == 2 and first['plan']['status'] == 'ACTIVE'
        assert sum(p['status'] == 'ARCHIVED' for p in all_plans) == 1

        sessions = store.list_sessions()
        profile = build_body_profile(sessions, **DEMO_SCOPE)
        participant = store.get_participant(DEMO_SCOPE['participant_id'])
        current = generate_proposal(profile, sessions, participant, now=NOW)
        assert current['participant_fingerprint'] == second['plan']['automatic']['participant_fingerprint']
        key = second['plan']['items'][0]['key']
        prepared = prepare_training_plan(second['plan'], key, profile)
        validate_automatic_use(second['plan'], key, profile, sessions, participant, prepared, now=NOW)
    finally:
        store.close()
