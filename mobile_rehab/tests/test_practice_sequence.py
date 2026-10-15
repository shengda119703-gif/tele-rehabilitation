"""Original hosted HTTP/SQLite sequence; all counts/settings are TEST input."""
from contextlib import closing
import copy
import json
from uuid import uuid4

from fastapi.testclient import TestClient

from app.settings import default_plan
from app.storage import Storage
from app.training_plans import item_from_plan, new_training_plan
from mobile_rehab.tests.test_practice import client, end_payload, feedback_payload
from mobile_rehab.tests.test_manual_practice import start_manual
from mobile_rehab.tests.test_mobile import HEADERS, owner, add_assessment, SCREEN


def sequence(client, rest=0):
    participant = client.get('/api/practice/context').json()['participant_id']
    scope = dict(participant_id=participant, source_kind='REPLAY_FILE', usage_context='SELF_USE')
    first = default_plan('shoulder_abduction')
    first.update(side='left', target_reps=3, target_sets=2, rest_between_sets_s=rest)
    second = default_plan('knee_extension')
    second.update(side='right', target_reps=2, target_sets=1, needs_companion=True)
    plan = new_training_plan(scope, 'TEST 原两项安排', [item_from_plan(first), item_from_plan(second)])
    with closing(Storage(database(client))) as store:
        return store.save_training_plan(plan, expected_revision=0)


def database(client):
    return client.app.state.jobs.root / owner(client) / 'assessments.sqlite3'


def completed(client, item, count=None):
    value = end_payload(count)
    value['reason'] = 'completed_set'
    response = client.post('/api/practice/' + item['id'] + '/finish', json=value)
    assert response.status_code == 200, response.text
    return response.json()


def next_payload(companion=False):
    return dict(operation_id=str(uuid4()), manual_arrangement_confirmed=True,
                support_ready=True, companion_present=companion)


def advance(client, item, value):
    return client.post('/api/practice/' + item['id'] + '/continue', json=value)


def test_original_two_sets_then_next_action_have_separate_facts_same_journey(client):
    plan = sequence(client)
    first = completed(client, client.post('/api/practice', json=start_manual(plan)).json(), 3)
    assert first['continuation']['kind'] == 'next_set'
    second_response = advance(client, first, next_payload())
    assert second_response.status_code == 200, second_response.text
    second = completed(client, second_response.json())
    assert second['set_index'] == 2 and second['continuation']['kind'] == 'next_action'
    value = next_payload()
    denied = advance(client, second, value)
    assert denied.status_code == 409 and denied.json()['detail']['code'] == 'COMPANION_REQUIRED'
    value['companion_present'] = True
    third = completed(client, advance(client, second, value).json(), 2)
    assert third['set_index'] == 1 and third['exercise_id'] == 'knee_extension'
    assert third['continuation'] is None
    rows = client.get('/api/practice').json()
    assert len(rows) == 3 and len({r['journey_id'] for r in rows}) == 1
    assert {r['id']: r['self_reported_count'] for r in rows} == {first['id']: 3, second['id']: None, third['id']: 2}
    assert all(r['confirmed_count'] is None and r['formal_plan_contribution'] is None for r in rows)
    with closing(Storage(database(client))) as store:
        assert store.list_sessions() == [] and store.get_training_plan(plan['id']) == plan


def test_lost_continue_reply_original_key_does_not_duplicate_group(client):
    plan = sequence(client)
    first = completed(client, client.post('/api/practice', json=start_manual(plan)).json())
    value = next_payload()
    original = advance(client, first, value)
    assert original.status_code == 200, original.text
    for _ in range(3):
        assert advance(client, first, value).json()['id'] == original.json()['id']
    prior = client.get('/api/practice/' + first['id']).json()
    assert prior['continuation']['successor_id'] == original.json()['id']
    assert advance(client, first, next_payload()).status_code == 409
    assert len(client.get('/api/practice').json()) == 2


def test_rest_uses_owning_server_time_not_client_elapsed_or_set_count(client, monkeypatch):
    monkeypatch.setattr('mobile_rehab.practice.utc_now', lambda: '2026-10-12T08:00:00+00:00')
    plan = sequence(client, 30)
    first = completed(client, client.post('/api/practice', json=start_manual(plan)).json())
    assert first['continuation']['rest_remaining_ms'] == 30000
    value = next_payload()
    early = advance(client, first, value)
    assert early.status_code == 409 and early.json()['detail']['code'] == 'REST_PENDING'
    monkeypatch.setattr('mobile_rehab.practice.utc_now', lambda: '2026-10-12T08:00:31+00:00')
    second = advance(client, first, value)
    assert second.status_code == 200 and second.json()['set_index'] == 2
    assert second.json().get('self_reported_count') is None and second.json()['finish_payload'] is None


def test_plain_end_and_closed_rest_do_not_make_implicit_completion(client):
    plan = sequence(client)
    item = client.post('/api/practice', json=start_manual(plan)).json()
    ended = client.post('/api/practice/' + item['id'] + '/finish', json=end_payload()).json()
    assert ended['self_reported_count'] is None and ended['continuation'] is None
    assert advance(client, ended, next_payload()).status_code == 409
    second = completed(client, client.post('/api/practice', json=start_manual(plan)).json(), 3)
    payload = dict(operation_id=str(uuid4()))
    path = '/api/practice/' + second['id'] + '/close-journey'
    closed = client.post(path, json=payload)
    assert closed.status_code == 200, closed.text
    assert closed.json()['journey_closed'] and closed.json()['continuation'] is None
    assert closed.json()['finish_payload'] == second['finish_payload']
    assert client.post(path, json=payload).json() == closed.json()
    assert advance(client, closed.json(), next_payload()).status_code == 409


def test_stop_or_archived_plan_denies_next_without_undoing_saved_group(client):
    plan = sequence(client)
    first = completed(client, client.post('/api/practice', json=start_manual(plan)).json(), 3)
    path = '/api/practice/' + first['id']
    assert client.post(path + '/feedback', json=feedback_payload(pain=1)).status_code == 200
    denied = advance(client, first, next_payload())
    assert denied.status_code == 409 and denied.json()['detail']['code'] == 'PRACTICE_STOP_RECORDED'
    with closing(Storage(database(client))) as store:
        store.set_training_plan_archived(plan['id'], dict(participant_id=plan['participant_id'],
            source_kind='REPLAY_FILE', usage_context='SELF_USE'), True, expected_revision=1)
    assert advance(client, first, next_payload()).status_code == 409
    saved = client.get(path).json()
    assert saved['state'] == 'COMMITTED' and saved['self_reported_count'] == 3


def test_continue_is_owner_bound_strict_and_cannot_parallelize_another_open_group(client):
    plan = sequence(client)
    first = completed(client, client.post('/api/practice', json=start_manual(plan)).json())
    with TestClient(client.app, headers=HEADERS) as other:
        other.post('/api/pair', json={'code': 'TEST-only'})
        assert advance(other, first, next_payload()).status_code == 404
    assert advance(client, first, dict(next_payload(), set_index=7)).status_code == 400
    other = client.post('/api/practice', json=start_manual(plan)).json()
    blocked = advance(client, first, next_payload())
    assert blocked.status_code == 409 and blocked.json()['detail']['code'] == 'ORIGINAL_PRACTICE_OPEN'
    assert client.get('/api/practice/' + other['id']).json()['state'] == 'PRACTICING'


def test_old_schema_one_is_readable_without_inventing_group_sequence(client):
    plan = sequence(client)
    item = completed(client, client.post('/api/practice', json=start_manual(plan)).json(), 3)
    old = copy.deepcopy(item)
    old['schema_version'] = 1
    for field in ('journey_id', 'arrangement_sequence', 'sequence_index', 'sequence_policy', 'journey_closed', 'successor_id', 'continuation'):
        old.pop(field, None)
    with closing(Storage(database(client))) as store:
        store._call(lambda c: c.execute('UPDATE guided_practices SET payload=? WHERE owner=? AND id=?',
            (json.dumps(old), owner(client), item['id'])))
    saved = client.get('/api/practice/' + item['id']).json()
    assert saved['self_reported_count'] == 3 and saved['continuation'] is None
    assert advance(client, saved, next_payload()).status_code == 409


def test_guided_navigation_never_fakes_original_automatic_plan_sequence_progress(client):
    first_assessment = add_assessment(client)
    other = copy.deepcopy(first_assessment)
    other.update(id='TEST-right-assessment', side='right')
    with closing(Storage(database(client))) as store:
        store.save_session(other)
    assert client.post('/api/plan', json=SCREEN).status_code == 200
    plan = client.get('/api/plan').json()['plan']
    assert len(plan['items']) == 2
    start = dict(operation_id=str(uuid4()), plan_id=plan['id'], plan_revision=plan['revision'], entry_key=plan['items'][0]['key'])
    created = client.post('/api/practice', json=start)
    assert created.status_code == 200, created.text
    first = completed(client, created.json(), 3)
    assert first['continuation']['kind'] == 'next_action'
    assert first['continuation']['decision']['code'] == 'ARRANGEMENT_NOT_ALLOWED'
    denied = advance(client, first, next_payload())
    assert denied.status_code == 409 and denied.json()['detail']['code'] == 'ARRANGEMENT_NOT_ALLOWED'
    assert client.get('/api/plan').json()['progress']['completed'] == 0
    assert len(client.get('/api/practice').json()) == 1
    with closing(Storage(database(client))) as store:
        assert len(store.list_sessions()) == 2 and store.get_training_plan(plan['id']) == plan
