"""Actual HTTP/SQLite contract tests. Arrangements below are TEST fixtures."""
import copy
from contextlib import closing
import sqlite3
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from mobile_rehab.server import create_app
from mobile_rehab.tests.test_mobile import add_assessment, SCREEN, HEADERS, owner
from app.storage import Storage


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path, pair_key='TEST-only', runner=lambda item: None)
    with TestClient(app, headers=HEADERS) as client:
        client.post('/api/pair', json={'code': 'TEST-only'})
        yield client


def arrangement(client):
    add_assessment(client)
    assert client.post('/api/plan', json=SCREEN).status_code == 200
    plan = client.get('/api/plan').json()['plan']
    return dict(operation_id=str(uuid4()), plan_id=plan['id'], plan_revision=plan['revision'],
                entry_key=plan['items'][0]['key'])


def end_payload(count=None):
    return dict(operation_id=str(uuid4()), count=count, elapsed_ms=1500, reason='ended',
                feedback=dict(pain=None, fatigue=None))


def test_real_writer_commits_independent_record_without_visual_or_plan_contribution(client):
    start = arrangement(client)
    created = client.post('/api/practice', json=start)
    assert created.status_code == 200, created.text
    assert created.json()['state'] == 'PRACTICING'
    assert client.post('/api/practice', json=start).json() == created.json()
    finish = end_payload(10)
    one = client.post('/api/practice/' + start['operation_id'] + '/finish', json=finish)
    assert one.status_code == 200, one.text
    saved = one.json()
    assert saved['state'] == 'COMMITTED'
    assert saved['self_reported_count'] == 10
    assert saved['confirmed_count'] is None and saved['visual_session_ref'] is None
    assert saved['formal_plan_contribution'] is None
    assert saved['finish_payload']['feedback'] == {'pain': None, 'fatigue': None}
    assert client.post('/api/practice/' + start['operation_id'] + '/finish', json=finish).json() == saved
    assert client.get('/api/practice/' + start['operation_id']).json() == saved
    assert client.get('/api/plan').json()['progress']['completed'] == 0
    database = client.app.state.jobs.root / owner(client) / 'assessments.sqlite3'
    with sqlite3.connect(database) as conn:
        assert conn.execute('SELECT COUNT(*) FROM sessions').fetchone()[0] == 1
        assert conn.execute('SELECT COUNT(*) FROM guided_practices').fetchone()[0] == 1
    with closing(Storage(database)) as store:
        assert store.list_sessions()[0]['submode'] == 'assessment'
    assert len(client.get('/api/practice').json()) == 1


def test_finish_without_count_is_not_implicit_completion_and_replays_cannot_change_facts(client):
    start = arrangement(client)
    assert client.post('/api/practice', json=start).status_code == 200
    finish = end_payload()
    saved = client.post('/api/practice/' + start['operation_id'] + '/finish', json=finish).json()
    assert saved['self_reported_count'] is None
    assert saved['record_origin'] == 'GUIDED_PRACTICE'
    different = copy.deepcopy(finish)
    different['count'] = 4
    assert client.post('/api/practice/' + start['operation_id'] + '/finish', json=different).status_code == 409
    assert client.get('/api/practice/' + start['operation_id']).json() == saved
    start['entry_key'] = 'not-the-original-entry'
    assert client.post('/api/practice', json=start).status_code == 409


def test_unknown_plan_and_latest_insufficient_assessment_never_grant_practice(client):
    unknown = dict(operation_id=str(uuid4()), plan_id='missing', plan_revision=1, entry_key='shoulder_abduction:left')
    assert client.post('/api/practice', json=unknown).status_code == 404
    start = arrangement(client)
    database = client.app.state.jobs.root / owner(client) / 'assessments.sqlite3'
    with closing(Storage(database)) as store:
        session = store.list_sessions()[0]
        session['summary']['completed'] = 0
        store.save_session(session)
    rejected = client.post('/api/practice', json=start)
    assert rejected.status_code == 409
    assert rejected.json()['detail']['code'] == 'ARRANGEMENT_NOT_ALLOWED'
    assert client.get('/api/practice').json() == []


def test_only_one_open_journey_and_explicit_discomfort_blocks_new_execution_not_saving(client):
    start = arrangement(client)
    assert client.post('/api/practice', json=start).status_code == 200
    another = dict(start, operation_id=str(uuid4()))
    assert client.post('/api/practice', json=another).json()['detail']['code'] == 'ORIGINAL_PRACTICE_OPEN'
    finish = end_payload()
    finish['feedback']['pain'] = 1
    saved = client.post('/api/practice/' + start['operation_id'] + '/finish', json=finish)
    assert saved.status_code == 200
    assert client.post('/api/practice', json=another).json()['detail']['code'] == 'PRACTICE_STOP_RECORDED'
    assert client.get('/api/practice/' + start['operation_id']).json()['state'] == 'COMMITTED'


def test_owner_format_and_payload_boundaries_are_enforced_by_original_routes(client):
    start = arrangement(client)
    assert client.post('/api/practice', json=dict(start, owner='foreign')).status_code == 400
    assert client.post('/api/practice', json=start).status_code == 200
    with TestClient(client.app, headers=HEADERS) as other:
        other.post('/api/pair', json={'code': 'TEST-only'})
        assert other.get('/api/practice/' + start['operation_id']).status_code == 404
        assert other.get('/api/practice').json() == []
    assert client.get('/api/practice/not-a-uuid').status_code == 400
    for invalid in [True, -1, 1.5, 10001]:
        assert client.post('/api/practice/' + start['operation_id'] + '/finish', json=end_payload(invalid)).status_code == 400
    assert client.get('/api/practice/' + start['operation_id']).json()['state'] == 'PRACTICING'


def test_resume_rechecks_current_arrangement_but_does_not_block_saving_ended_facts(client):
    start = arrangement(client)
    assert client.post('/api/practice', json=start).json()['execution_allowed'] is True
    database = client.app.state.jobs.root / owner(client) / 'assessments.sqlite3'
    with closing(Storage(database)) as store:
        session = store.list_sessions()[0]
        session['summary']['completed'] = 0
        store.save_session(session)
    current = client.get('/api/practice/' + start['operation_id']).json()
    assert current['state'] == 'PRACTICING' and current['execution_allowed'] is False
    assert current['execution_reason']
    assert client.post('/api/practice', json=start).json()['execution_allowed'] is False
    saved = client.post('/api/practice/' + start['operation_id'] + '/finish', json=end_payload()).json()
    assert saved['state'] == 'COMMITTED' and saved['confirmed_count'] is None


def feedback_payload(revision=0, **values):
    return dict(operation_id=str(uuid4()), expected_revision=revision,
                values=dict(pain=values.get('pain'), fatigue=values.get('fatigue'), note=values.get('note')))


def test_feedback_can_follow_committed_practice_with_nulls_and_one_durable_receipt(client):
    start = arrangement(client)
    identity = start['operation_id']
    path = '/api/practice/' + identity
    client.post('/api/practice', json=start)
    payload = feedback_payload(note='TEST 结束后补填')
    assert client.post(path + '/feedback', json=payload).status_code == 409
    end = end_payload(10)
    original = client.post(path + '/finish', json=end).json()
    empty = client.get(path + '/feedback').json()
    assert empty['revision'] == 0 and empty['values'] == dict(pain=None, fatigue=None, note=None)
    saved = client.post(path + '/feedback', json=payload)
    assert saved.status_code == 200, saved.text
    assert saved.json()['status'] == 'COMMITTED'
    assert saved.json()['values'] == payload['values']
    assert client.get(path + '/feedback/operations/' + payload['operation_id']).json() == saved.json()
    assert client.post(path + '/feedback', json=payload).json() == saved.json()
    record = client.get(path).json()
    for field in ('finish_payload', 'self_reported_count', 'confirmed_count', 'mode_segments', 'formal_plan_contribution'):
        assert record[field] == original[field]
    assert len(record['practice_feedback']['operations']) == 1
    assert client.get('/api/plan').json()['progress']['completed'] == 0


def test_feedback_revision_conflict_never_overwrites_and_original_receipt_remains_queryable(client):
    start = arrangement(client)
    path = '/api/practice/' + start['operation_id']
    client.post('/api/practice', json=start)
    client.post(path + '/finish', json=end_payload())
    first = feedback_payload(note='TEST first')
    receipt = client.post(path + '/feedback', json=first).json()
    stale = feedback_payload(fatigue=3)
    rejected = client.post(path + '/feedback', json=stale)
    assert rejected.status_code == 409
    assert rejected.json()['detail']['code'] == 'FEEDBACK_REVISION_CONFLICT'
    assert client.get(path + '/feedback').json()['values'] == first['values']
    assert client.get(path + '/feedback/operations/' + stale['operation_id']).status_code == 404
    latest = dict(stale, operation_id=str(uuid4()), expected_revision=1)
    assert client.post(path + '/feedback', json=latest).json()['revision'] == 2
    assert client.post(path + '/feedback', json=first).json() == receipt
    assert client.get(path + '/feedback').json()['revision'] == 2
    assert client.post(path + '/feedback', json=dict(first, values=latest['values'])).json()['detail']['code'] == 'FEEDBACK_KEY_CONFLICT'


def test_feedback_does_not_cross_owner_or_accept_empty_invalid_or_scope_overriding_data(client):
    start = arrangement(client)
    path = '/api/practice/' + start['operation_id']
    client.post('/api/practice', json=start)
    client.post(path + '/finish', json=end_payload())
    for payload in (feedback_payload(), feedback_payload(pain=True), feedback_payload(pain=-1),
                    feedback_payload(fatigue=11), feedback_payload(note=' '), feedback_payload(note='x'*501),
                    dict(feedback_payload(note='TEST'), owner='another'),
                    dict(feedback_payload(note='TEST'), expected_revision=True)):
        assert client.post(path + '/feedback', json=payload).status_code == 400
    with TestClient(client.app, headers=HEADERS) as other:
        other.post('/api/pair', json={'code': 'TEST-only'})
        assert other.get(path + '/feedback').status_code == 404
        assert other.post(path + '/feedback', json=feedback_payload(note='TEST')).status_code == 404
    assert client.get(path + '/feedback').json()['revision'] == 0


def test_explicit_later_discomfort_survives_edits_and_stops_new_or_open_practice_not_fact_saving(client):
    start = arrangement(client)
    path = '/api/practice/' + start['operation_id']
    client.post('/api/practice', json=start)
    client.post(path + '/finish', json=end_payload())
    another = dict(start, operation_id=str(uuid4()))
    assert client.post('/api/practice', json=another).json()['execution_allowed'] is True
    assert client.post(path + '/feedback', json=feedback_payload(pain=1)).status_code == 200
    assert client.post(path + '/feedback', json=feedback_payload(1, pain=0)).status_code == 200
    assert client.get('/api/practice/' + another['operation_id']).json()['execution_allowed'] is False
    assert client.post('/api/practice/' + another['operation_id'] + '/finish', json=end_payload()).status_code == 200
    rejected = client.post('/api/practice', json=dict(start, operation_id=str(uuid4())))
    assert rejected.json()['detail']['code'] == 'PRACTICE_STOP_RECORDED'
