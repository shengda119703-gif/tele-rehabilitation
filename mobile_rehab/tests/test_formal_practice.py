"""Real HTTP/original writer tests; scalar TEST evidence is not human data."""
from copy import deepcopy
from pathlib import Path
import sys
import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from mobile_rehab.server import create_app
from app.rehab_v2.reporting import build_report
from app.rehab_v2.sessions import SessionError
from mobile_rehab.rehab_v2.practice import FormalPractices

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tests/rehab_backend'))
from test_protocols import Replay

HEADERS = {'X-Rehab-Client': 'mobile-v1'}
BASE = '/api/rehab/v2/practice'


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path, pair_key='TEST-formal-guided', rehab_v2=True)
    # Explicit in-process protocol TEST source, never an inferred human result.
    app.state.rehab_v2.internal_replay = True
    app.state.rehab_v2.report_builder = build_report
    with TestClient(app, headers=HEADERS) as client:
        client.post('/api/pair', json={'code': 'TEST-formal-guided'})
        yield client


def service(client):
    return client.app.state.rehab_v2


def owner(client):
    return client.cookies['rehab_device'].split('.')[0]


def create_visual(client, payload):
    deadline = time.monotonic()+5
    while True:
        try:
            return service(client).create(owner(client), payload)
        except SessionError as error:
            if error.code != 'rehab_compute_resource_busy' or time.monotonic() >= deadline:
                raise
            time.sleep(.01)


def arrangement(client, *, companion=False, sets=2):
    item = create_visual(client, dict(idempotency_key=str(uuid4()), consent=True,
        submode='assessment', exercise_id='shoulder_abduction', side='left', view='frontal'))
    sid = item['session_id']; replay = Replay()
    for angle, frames in ((0., 30), (45., 10), (0., 10)):
        for _ in range(frames):
            replay.feed(angle, 1)
            service(client).submit_evidence(owner(client), sid, 'TEST-scalar-'+str(replay.seq), replay.frame)
    service(client).finish(owner(client), sid, dict(idempotency_key=str(uuid4()), expected_revision=0, reason='completed'))
    plan = service(client).save_plan(owner(client), dict(idempotency_key=str(uuid4()), name='TEST 原安排',
        arrangement=dict(reference='TEST 自己提供的安排，非临床处方', confirmed=True), items=[dict(
            exercise_id='shoulder_abduction', side='left', assessment_session_id=sid,
            settings=dict(target_reps=3, target_sets=sets, target_angle_deg=None, needs_companion=companion,
                          use_of_hands='not_recorded', rest_between_sets_s=0))]))
    return plan


def start_payload(plan):
    return dict(operation_id=str(uuid4()), plan_id=plan['id'], plan_revision=plan['revision'],
        entry_key=plan['items'][0]['key'], manual_arrangement_confirmed=True,
        support_ready=True, companion_present=False)


def end_payload(count=None, reason='ended'):
    return dict(operation_id=str(uuid4()), count=count, elapsed_ms=1700, reason=reason,
                feedback=dict(pain=None, fatigue=None))


def saved_start(client, plan=None):
    plan = plan or arrangement(client); start = start_payload(plan)
    response = client.post(BASE, json=start)
    assert response.status_code == 200, response.text
    return plan, start, response.json()


def test_contract_is_opt_in_owned_and_not_camera_evidence(client, tmp_path):
    context = client.get(BASE+'/context').json()
    assert context['provider'] == 'hosted-rehab-v2-guided-1'
    assert context['source_context'] == 'GUIDED_PRACTICE:TEST'
    assert context['arrangement_source_context'] == 'SYNTHETIC:TEST'
    assert context['owner_scope'] == owner(client)
    cap = client.get('/api/catalog').json()['formal_measurement']['guided_practice']
    assert cap['base_path'] == '/rehab/v2/practice' and 'allowed' not in cap
    with TestClient(create_app(tmp_path/'legacy', pair_key='TEST-legacy')) as legacy:
        assert legacy.get(BASE).status_code == 404


@pytest.mark.parametrize('field', ['manual_arrangement_confirmed', 'support_ready', 'companion_present'])
def test_original_arrangement_support_and_companion_are_not_bypassed(client, field):
    plan = arrangement(client, companion=True); start = start_payload(plan)
    start['companion_present'] = True; start[field] = False
    response = client.post(BASE, json=start)
    assert response.status_code == 409 and response.json()['detail']['category'] == 'MISSING_INPUT'
    assert client.get(BASE).json() == []


def test_no_assessment_or_foreign_plan_cannot_grant_guided_execution(client):
    payload = start_payload(dict(id='v2plan-'+'0'*32, revision=1, items=[dict(key='shoulder_abduction:left')]))
    assert client.post(BASE, json=payload).status_code == 404
    plan = arrangement(client); payload = start_payload(plan)
    other = TestClient(client.app, headers=HEADERS)
    other.post('/api/pair', json={'code': 'TEST-formal-guided'})
    assert other.post(BASE, json=payload).status_code == 404
    assert service(client).storage.list_sessions() == []


def test_unknown_fields_and_bad_types_are_rejected_not_written(client):
    plan = arrangement(client)
    for extra in ({'target_reps':100}, {'plan_id':[]}, {'plan_revision':True}, {'support_ready':1}):
        start = dict(start_payload(plan), **extra)
        assert client.post(BASE, json=start).status_code == 400
    assert client.get(BASE).json() == []


def test_idempotent_independent_finish_and_archived_original_recovery(client):
    plan, start, created = saved_start(client)
    assert created['execution_allowed'] is True and created['saved_parts']['visual_facts'] is None
    assert created['execution_grant']['code'] == 'FORMAL_ARRANGEMENT_GUIDED_ALLOWED'
    assert created['execution_grant']['grants_formal_measurement'] is False
    assert client.post(BASE, json=start).json() == created
    service(client).save_plan(owner(client), dict(idempotency_key=str(uuid4()), expected_revision=1), plan_id=plan['id'], archive=True)
    recovered = client.post(BASE, json=start).json()
    assert recovered['id'] == start['operation_id'] and recovered['execution_allowed'] is False
    finish = end_payload(10)
    reply = client.post(BASE+'/'+start['operation_id']+'/finish', json=finish)
    assert reply.status_code == 200, reply.text
    item = reply.json()
    assert item['saved_parts'] == dict(practice_records='COMMITTED', visual_facts=None, feedback=None)
    assert item['confirmed_count'] is None and item['formal_plan_contribution'] is None
    assert item['self_reported_count'] == 10 and item['count_scope'] == 'set_total'
    assert item['finish_payload']['feedback'] == dict(pain=None, fatigue=None)
    assert item['mode_segments'] == []  # No invented uninterrupted observed segment.
    assert client.post(BASE+'/'+start['operation_id']+'/finish', json=finish).json() == item
    assert client.post(BASE+'/'+start['operation_id']+'/finish', json=dict(finish, count=11)).status_code == 409
    assert service(client).plans.get(owner(client), plan['id'])['revision'] == 2
    assert client.get('/api/practice').json() == [] and service(client).storage.list_sessions() == []


def test_two_sets_share_journey_and_do_not_complete_the_formal_plan(client):
    plan, start, first = saved_start(client)
    identity = start['operation_id']
    first = client.post(BASE+'/'+identity+'/finish', json=end_payload(3, 'completed_set')).json()
    assert first['continuation']['set_index'] == 2
    continuation = dict(operation_id=str(uuid4()), manual_arrangement_confirmed=True,
                        support_ready=True, companion_present=False)
    second = client.post(BASE+'/'+identity+'/continue', json=continuation)
    assert second.status_code == 200, second.text
    second = second.json()
    assert second['journey_id'] == identity and second['predecessor_id'] == identity
    assert second['set_index'] == 2 and second['settings'] == first['settings']
    assert client.post(BASE+'/'+identity+'/continue', json=continuation).json() == second
    final = client.post(BASE+'/'+second['id']+'/finish', json=end_payload(None, 'completed_set')).json()
    assert final['continuation'] is None and final['self_reported_count'] is None
    progress = service(client).plan(owner(client), plan['id'])['progress']
    assert progress['completed'] == 0 and progress['next_key'] == first['plan_ref']['entry_key']
    assert len(client.get(BASE).json()) == 2
    closure = dict(operation_id=str(uuid4()))
    one = client.post(BASE+'/'+second['id']+'/close-journey', json=closure)
    assert one.status_code == 200 and one.json()['journey_closed'] is True
    assert client.post(BASE+'/'+second['id']+'/close-journey', json=closure).json() == one.json()


def test_feedback_is_independent_and_old_stop_cannot_be_cleared_by_later_zero(client):
    plan, start, _ = saved_start(client)
    identity = start['operation_id']; client.post(BASE+'/'+identity+'/finish', json=end_payload())
    path = BASE+'/'+identity+'/feedback'
    snapshot = client.get(path).json()
    assert snapshot['revision'] == 0 and snapshot['values'] == dict(pain=None, fatigue=None, note=None)
    first = dict(operation_id=str(uuid4()), expected_revision=0, values=dict(pain=2, fatigue=None, note=None))
    receipt = client.post(path, json=first)
    assert receipt.status_code == 200, receipt.text
    assert client.get(path+'/operations/'+first['operation_id']).json() == receipt.json()
    assert client.post(path, json=first).json() == receipt.json()
    assert client.post(path, json=dict(first, operation_id=str(uuid4()))).status_code == 409
    assert client.post(path, json=dict(operation_id=str(uuid4()), expected_revision=1,
                                     values=dict(pain=0, fatigue=0, note=None))).status_code == 200
    assert client.post(BASE, json=start_payload(plan)).json()['detail']['code'] == 'PRACTICE_STOP_RECORDED'
    saved = client.get(BASE+'/'+identity).json()
    assert saved['finish_payload']['feedback']['pain'] is None and saved['saved_parts']['feedback'] == 'COMMITTED'


def test_visual_link_is_owned_frozen_and_does_not_confirm_other_parts(client):
    plan, start, _ = saved_start(client)
    visual = create_visual(client, dict(idempotency_key=str(uuid4()), consent=True, submode='training',
        plan_id=plan['id'], expected_plan_revision=1, entry_key=start['entry_key'],
        view='frontal', training_plan_confirmed=True))
    identity = start['operation_id']; sid = visual['session_id']
    link = dict(operation_id=str(uuid4()), session_id=sid)
    path = BASE+'/'+identity+'/visual-link'
    linked = client.post(path, json=link)
    assert linked.status_code == 200, linked.text
    assert client.post(path, json=link).json() == linked.json()
    assert linked.json()['association_scope'] == 'journey_not_self_reported_set_total'
    assert client.post(path, json=dict(link, session_id='TEST-other-session')).status_code == 409
    before = client.get(BASE+'/'+identity).json()
    assert before['saved_parts']['practice_records'] == 'LOCAL_DRAFT'
    assert before['saved_parts']['visual_facts'] == 'LOCAL_DRAFT'
    service(client).finish(owner(client), sid, dict(idempotency_key=str(uuid4()), expected_revision=0, reason='user_stopped'))
    measured = client.get(BASE+'/'+identity).json()
    assert measured['saved_parts']['visual_facts'] == 'COMMITTED'
    assert measured['saved_parts']['practice_records'] == 'LOCAL_DRAFT'
    assert measured['saved_parts']['feedback'] is None
    done = client.post(BASE+'/'+identity+'/finish', json=end_payload(10)).json()
    assert done['self_reported_count'] == 10 and done['confirmed_count'] is None
    assert service(client).get(owner(client), sid)['snapshot']['completed'] == 0
    assert done['visual_session_refs'][0]['canonical_commit'] == service(client).get(owner(client), sid)['canonical_commit']


def test_unknown_namespace_is_not_migrated_or_repaired(client):
    storage = service(client).storage_boundary
    storage._call(lambda c:c.execute('UPDATE rehab_v2_practice_meta SET version=99'))
    with pytest.raises(SessionError, match='unsupported_formal_practice_schema'):
        FormalPractices(service(client))
    assert storage._call(lambda c:c.execute('SELECT version FROM rehab_v2_practice_meta').fetchone()[0]) == 99


def test_assessment_is_not_a_training_visual_link_and_link_identity_is_unique(client):
    plan, start, _ = saved_start(client)
    assessment = service(client).plans.get(owner(client), plan['id'])['items'][0]['assessment_reference']['session_id']
    path = BASE+'/'+start['operation_id']+'/visual-link'
    rejected = client.post(path, json=dict(operation_id=str(uuid4()), session_id=assessment))
    assert rejected.status_code == 409 and rejected.json()['detail']['code'] == 'VISUAL_BINDING_MISMATCH'
    assert client.get(BASE+'/'+start['operation_id']).json()['visual_session_refs'] == []
    other = TestClient(client.app, headers=HEADERS)
    other.post('/api/pair', json={'code':'TEST-formal-guided'})
    assert other.get(BASE+'/'+start['operation_id']).status_code == 404
    visual = create_visual(client, dict(idempotency_key=str(uuid4()), consent=True, submode='training',
        plan_id=plan['id'], expected_plan_revision=1, entry_key=start['entry_key'],
        view='frontal', training_plan_confirmed=True))
    value = dict(operation_id=str(uuid4()), session_id=visual['session_id'])
    assert client.post(path, json=value).status_code == 200
    duplicate = client.post(path, json=dict(value, operation_id=str(uuid4())))
    assert duplicate.status_code == 409 and duplicate.json()['detail']['code'] == 'VISUAL_ALREADY_LINKED'


def test_current_person_change_blocks_execution_but_owned_ended_facts_can_save(client):
    plan, start, _ = saved_start(client)
    service(client).participant_provider = lambda _: 'TEST-another-person'
    projected = client.get(BASE+'/'+start['operation_id']).json()
    assert projected['execution_allowed'] is False
    assert projected['execution_decision']['code'] == 'PRACTICE_SCOPE_CHANGED'
    assert client.post(BASE, json=start_payload(plan)).status_code == 409
    ended = client.post(BASE+'/'+start['operation_id']+'/finish', json=end_payload()).json()
    assert ended['state'] == 'COMMITTED'
    assert ended['context']['participant_id'] == owner(client)
