"""Real owned SQLite/manual-library seam, with explicitly declared TEST doses."""
from contextlib import closing
from uuid import uuid4
import copy

from fastapi.testclient import TestClient
from app.storage import Storage
from app.settings import default_plan
from app.training_plans import item_from_plan, new_training_plan
from mobile_rehab.tests.test_practice import client, end_payload, feedback_payload, arrangement
from mobile_rehab.tests.test_mobile import HEADERS, owner, add_assessment


def save_manual(client, *, needs_companion=False):
    participant = client.get('/api/practice/context').json()['participant_id']
    scope = dict(participant_id=participant, source_kind='REPLAY_FILE', usage_context='SELF_USE')
    settings = default_plan('shoulder_abduction')
    settings.update(side='left', target_reps=7, target_sets=2, target_angle_deg=None,
                    needs_companion=needs_companion)
    record = new_training_plan(scope, 'TEST 已有人工安排', [item_from_plan(settings)])
    database = client.app.state.jobs.root / owner(client) / 'assessments.sqlite3'
    with closing(Storage(database)) as store:
        return store.save_training_plan(record, expected_revision=0)


def start_manual(plan, **changes):
    return dict(operation_id=str(uuid4()), plan_id=plan['id'], plan_revision=plan['revision'],
                entry_key=plan['items'][0]['key'], manual_arrangement_confirmed=True,
                support_ready=True, companion_present=False, **changes)


def test_existing_manual_arrangement_can_be_practised_without_fabricating_assessment(client):
    plan = save_manual(client)
    assert client.get('/api/plan').json()['proposal']['candidates'] == []
    catalog = client.get('/api/catalog').json()
    assert catalog['manual_practice_arrangements'] is True
    available = client.get('/api/practice/arrangements').json()
    assert len(available) == 1 and available[0]['items'][0]['settings'] == plan['items'][0]['settings']
    start = start_manual(plan)
    response = client.post('/api/practice', json=start)
    assert response.status_code == 200, response.text
    item = response.json()
    assert item['execution_allowed'] is True
    assert item['guidance_policy'] == 'explicit-saved-manual-practice-1'
    assert item['arrangement_ref']['kind'] == 'MANUAL_SAVED'
    assert item['formal_plan_ref'] is None and item['assessment_ref'] is None
    assert item['settings'] == plan['items'][0]['settings']
    assert client.post('/api/practice', json=start).json() == item
    finish = end_payload(3)
    path = '/api/practice/' + item['id']
    saved = client.post(path + '/finish', json=finish).json()
    assert saved['state'] == 'COMMITTED' and saved['self_reported_count'] == 3
    assert saved['confirmed_count'] is None and saved['formal_plan_contribution'] is None
    assert client.post(path + '/finish', json=finish).json() == saved
    assert client.get(path).json() == saved
    database = client.app.state.jobs.root / owner(client) / 'assessments.sqlite3'
    with closing(Storage(database)) as store:
        assert store.list_sessions() == []
        assert store.get_training_plan(plan['id']) == plan


def test_manual_does_not_relax_automatic_path_or_accept_false_and_untyped_intent(client):
    plan = save_manual(client)
    plain = {k: v for k, v in start_manual(plan).items() if k not in ('manual_arrangement_confirmed', 'support_ready', 'companion_present')}
    assert client.post('/api/practice', json=plain).status_code == 409
    for field in ('manual_arrangement_confirmed', 'support_ready'):
        value = start_manual(plan)
        value[field] = False
        result = client.post('/api/practice', json=value)
        assert result.status_code == 409 and result.json()['detail']['category'] == 'MISSING_INPUT'
        value[field] = 1
        assert client.post('/api/practice', json=value).status_code == 400
    automatic = arrangement(client)
    automatic.update(manual_arrangement_confirmed=True, support_ready=True, companion_present=False)
    result = client.post('/api/practice', json=automatic)
    assert result.status_code == 409 and result.json()['detail']['code'] == 'MANUAL_ARRANGEMENT_REQUIRED'
    assert client.get('/api/practice').json() == []


def test_companion_and_current_plan_revision_are_real_gates_not_camera_ready(client):
    plan = save_manual(client, needs_companion=True)
    start = start_manual(plan)
    rejected = client.post('/api/practice', json=start)
    assert rejected.status_code == 409 and rejected.json()['detail']['code'] == 'COMPANION_REQUIRED'
    start['companion_present'] = True
    assert client.post('/api/practice', json=start).json()['execution_allowed'] is True
    database = client.app.state.jobs.root / owner(client) / 'assessments.sqlite3'
    with closing(Storage(database)) as store:
        edited = copy.deepcopy(plan)
        edited['items'][0]['settings']['target_reps'] = 8
        store.save_training_plan(edited, expected_revision=plan['revision'])
    path = '/api/practice/' + start['operation_id']
    assert client.get(path).json()['execution_allowed'] is False
    assert client.post(path + '/finish', json=end_payload()).json()['state'] == 'COMMITTED'


def test_manual_stop_cannot_be_erased_by_another_arrangement_or_later_zero(client):
    plan = save_manual(client)
    start = start_manual(plan)
    path = '/api/practice/' + start['operation_id']
    assert client.post('/api/practice', json=start).status_code == 200
    assert client.post(path + '/finish', json=end_payload()).status_code == 200
    assert client.post(path + '/feedback', json=feedback_payload(pain=1)).status_code == 200
    assert client.post(path + '/feedback', json=feedback_payload(1, pain=0)).status_code == 200
    other = save_manual(client)
    rejected = client.post('/api/practice', json=start_manual(other))
    assert rejected.status_code == 409 and rejected.json()['detail']['code'] == 'PRACTICE_STOP_RECORDED'
    assert client.get(path).json()['state'] == 'COMMITTED'


def test_manual_original_owner_and_settings_binding_are_not_client_overridable(client):
    plan = save_manual(client)
    with TestClient(client.app, headers=HEADERS) as other:
        other.post('/api/pair', json={'code': 'TEST-only'})
        assert other.get('/api/practice/arrangements').json() == []
        assert other.post('/api/practice', json=start_manual(plan)).status_code == 404
    for extra in ({'participant_id': 'foreign'}, {'settings': {'target_reps': 100}}, {'assessment_ref': 'fiction'}):
        assert client.post('/api/practice', json=dict(start_manual(plan), **extra)).status_code == 400
    assert client.get('/api/practice').json() == []


def test_recent_measured_stop_also_blocks_manual_without_requiring_new_assessment(client):
    add_assessment(client)
    plan = save_manual(client)
    database = client.app.state.jobs.root / owner(client) / 'assessments.sqlite3'
    with closing(Storage(database)) as store:
        session = store.list_sessions()[0]
        session['submode'] = 'training'
        session['training_feedback'] = dict(pain=1, fatigue=None)
        store.save_session(session)
    rejected = client.post('/api/practice', json=start_manual(plan))
    assert rejected.status_code == 409 and rejected.json()['detail']['code'] == 'TRAINING_STOP_RECORDED'


def test_automatic_guided_path_cannot_bypass_a_manual_practice_stop(client):
    automatic = arrangement(client)
    manual = save_manual(client)
    start = start_manual(manual)
    path = '/api/practice/' + start['operation_id']
    assert client.post('/api/practice', json=start).status_code == 200
    end = end_payload()
    end['reason'] = 'discomfort'
    assert client.post(path + '/finish', json=end).status_code == 200
    rejected = client.post('/api/practice', json=automatic)
    assert rejected.status_code == 409 and rejected.json()['detail']['code'] == 'PRACTICE_STOP_RECORDED'
