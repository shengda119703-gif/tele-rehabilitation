"""B01/B02 with real original Runtime and SQLite. All entered counts are QA inputs."""
import copy
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.guided_practice import execute, PracticeError, decision, records, PROVIDER
from app.runtime import Runtime
from app.storage import Storage
from app.training_plans import new_training_plan
from app.rehab_read_tools import RehabReadTools
from test_saved_training_plans import SCOPE, item
from test_training_runtime import response


@pytest.fixture
def arranged(tmp_path):
    store = Storage(tmp_path/'home_rehab.sqlite3')
    plan = store.save_training_plan(new_training_plan(SCOPE, 'TEST 已确定安排', [item(target_reps=3)]), expected_revision=0)
    yield store, plan
    store.close()


def start(plan, **kwargs):
    return dict(operation_id=str(uuid4()), plan_id=plan['id'], plan_revision=plan['revision'],
                entry_key=plan['items'][0]['key'], arrangement_confirmed=True,
                support_ready=True, companion_present=False, **kwargs)


def end(**kwargs):
    return dict(operation_id=str(uuid4()), count=None, elapsed_ms=1200, reason='ended',
                feedback=dict(pain=None, fatigue=None), **kwargs)


def run(store, command, **args):
    return execute(store, command, SCOPE, args)


def test_no_assessment_manual_allowed_but_no_formal_facts_and_exact_receipt(arranged):
    store, plan = arranged
    payload = start(plan)
    record = run(store, 'practice_start', payload=payload)
    assert record['execution_allowed'] and record['context']['provider'] == PROVIDER
    assert record['formal_plan_ref'] is None and record['assessment_ref'] is None
    assert record['confirmed_count'] is None and record['formal_plan_contribution'] is None
    assert store.list_sessions() == []
    assert run(store, 'practice_start', payload=payload)['id'] == record['id']
    ending = end(); ending['count'] = 3
    result = run(store, 'practice_finish', id=record['id'], payload=ending)
    assert result['state'] == 'COMMITTED' and result['self_reported_count'] == 3
    assert result['finish_payload']['feedback'] == dict(pain=None, fatigue=None)
    assert run(store, 'practice_finish', id=record['id'], payload=ending) == result
    assert len(run(store, 'practice_history')) == 1 and not store.list_sessions()
    assert not run(store, 'practice_get', id=record['id'])['execution_allowed']
    with pytest.raises(PracticeError, match='编号'):
        run(store, 'practice_start', payload=dict(payload, entry_key='knee_extension:right'))
    with pytest.raises(PracticeError, match='已保存'):
        run(store, 'practice_finish', id=record['id'], payload=dict(ending, count=4))


@pytest.mark.parametrize('change,code', [('arrangement_confirmed', 'ARRANGEMENT_CONFIRMATION_REQUIRED'),
                                       ('support_ready', 'SUPPORT_CONFIRMATION_REQUIRED')])
def test_user_adoption_and_support_are_not_a_frontend_grant(arranged, change, code):
    store, plan = arranged
    value = start(plan); value[change] = False
    with pytest.raises(PracticeError) as error: run(store, 'practice_start', payload=value)
    assert error.value.code == code and not run(store, 'practice_history')


def test_required_companion_and_original_settings_are_rechecked(arranged):
    store, plan = arranged
    plan['items'][0]['settings']['needs_companion'] = True
    plan = store.save_training_plan(plan, expected_revision=plan['revision'])
    value = start(plan)
    with pytest.raises(PracticeError) as error: run(store, 'practice_start', payload=value)
    assert error.value.code == 'COMPANION_REQUIRED'
    value['companion_present'] = True
    assert run(store, 'practice_start', payload=value)['execution_allowed']


@pytest.mark.parametrize('scope', [dict(SCOPE, participant_id='other'), dict(SCOPE, source_kind='LIVE_CAMERA'),
                                  dict(SCOPE, usage_context='SELF_USE')])
def test_owner_and_source_cannot_share_operations_or_grants(arranged, scope):
    store, plan = arranged
    record = run(store, 'practice_start', payload=start(plan))
    assert execute(store, 'practice_history', scope, {}) == []
    with pytest.raises(PracticeError): execute(store, 'practice_get', scope, {'id': record['id']})
    with pytest.raises(PracticeError): execute(store, 'practice_start', scope, {'payload': start(plan)})


def test_later_archive_blocks_resume_not_ended_fact_save(arranged):
    store, plan = arranged
    value = start(plan); record = run(store, 'practice_start', payload=value)
    store.set_training_plan_archived(plan['id'], SCOPE, True, expected_revision=1)
    resumed = run(store, 'practice_get', id=record['id'])
    assert not resumed['execution_allowed'] and resumed['execution_decision']['code'] == 'ARRANGEMENT_CHANGED'
    assert run(store, 'practice_start', payload=value)['id'] == record['id']
    assert run(store, 'practice_finish', id=record['id'], payload=end())['state'] == 'COMMITTED'


def test_stop_cannot_be_erased_by_new_arrangement_or_zero_feedback(arranged):
    store, plan = arranged
    record = run(store, 'practice_start', payload=start(plan))
    ending = end(); ending['reason'] = 'discomfort'
    run(store, 'practice_finish', id=record['id'], payload=ending)
    clone = store.save_training_plan(new_training_plan(SCOPE, 'TEST 新名称', [item()]), expected_revision=0)
    with pytest.raises(PracticeError) as error: run(store, 'practice_start', payload=start(clone))
    assert error.value.code == 'PRACTICE_STOP_RECORDED'


def test_pause_draft_same_key_conflict_reopen_not_formal_result(arranged):
    store, plan = arranged
    record = run(store, 'practice_start', payload=start(plan))
    value = dict(operation_id=str(uuid4()), expected_revision=0, elapsed_ms=1000, count=2)
    saved = run(store, 'practice_draft', id=record['id'], payload=value)
    assert saved['draft']['revision'] == 1 and saved['draft']['count'] == 2
    assert run(store, 'practice_draft', id=record['id'], payload=value) == saved
    with pytest.raises(PracticeError): run(store, 'practice_draft', id=record['id'], payload=dict(value, count=4))
    with pytest.raises(PracticeError): run(store, 'practice_draft', id=record['id'], payload=dict(value, operation_id=str(uuid4())))
    prepared = run(store, 'practice_prepare', id=plan['id'], revision=1, entry_key=plan['items'][0]['key'])
    assert prepared['open_record']['draft']['count'] == 2
    assert prepared['open_record']['confirmed_count'] is None
    with pytest.raises(PracticeError): run(store, 'practice_finish', id=record['id'], payload=dict(end(), elapsed_ms=999))


@pytest.mark.parametrize('field,value', [('count', True), ('count', -1), ('elapsed_ms', True),
                                       ('elapsed_ms', float('nan')), ('elapsed_ms', -1), ('count', 10001)])
def test_invalid_self_inputs_never_become_measurements(arranged, field, value):
    store, plan = arranged
    record = run(store, 'practice_start', payload=start(plan))
    ending = end(); ending[field] = value
    with pytest.raises(PracticeError): run(store, 'practice_finish', id=record['id'], payload=ending)
    assert run(store, 'practice_get', id=record['id'])['state'] == 'PRACTICING'


def test_read_only_desktop_history_type_not_old_session_summary(arranged):
    store, plan = arranged
    record = run(store, 'practice_start', payload=start(plan))
    run(store, 'practice_finish', id=record['id'], payload=end())
    reader = RehabReadTools(store.path, SCOPE)
    desktop = reader.desktop_snapshot()
    assert len(desktop['guided_practice']['records']) == 1
    assert desktop['rehab.get_training_history']['records'] == []
    original = desktop['rehab.get_training_plan']['records'][0]
    assert not original['next_available'] and original['guided_available']
    assert reader('rehab.get_training_history', {})['records'] == []
    assert store.get_training_plan(plan['id'])['revision'] == 1 and not store.list_sessions()


def test_real_runtime_and_sqlite_reopen_without_camera_or_fake_ready(tmp_path):
    with_store = Storage(tmp_path/'home_rehab.sqlite3')
    plan = with_store.save_training_plan(new_training_plan(SCOPE, 'TEST 原安排', [item()]), expected_revision=0)
    with_store.close()
    runtime = Runtime(tmp_path)
    def command(name, **kwargs):
        replies = response(runtime, name, scope=SCOPE, request_id=str(uuid4()), **kwargs)
        assert not any(r['kind'] == 'error' for r in replies), replies
        return next(r['result'] for r in replies if r['kind'] == 'practice_result')
    try:
        assert runtime.ready.wait(5)
        prepared = command('practice_prepare', id=plan['id'], revision=1, entry_key=plan['items'][0]['key'])
        assert prepared['decision']['code'] == 'ARRANGEMENT_CONFIRMATION_REQUIRED'
        record = command('practice_start', payload=start(plan))
        command('practice_finish', id=record['id'], payload=end())
        assert runtime.camera.worker is None and runtime.controller.session is None
    finally:
        response(runtime, 'shutdown'); runtime.thread.join(6); assert not runtime.thread.is_alive()
    store = Storage(tmp_path/'home_rehab.sqlite3')
    try:
        assert len(run(store, 'practice_history')) == 1 and not store.list_sessions()
    finally: store.close()


def test_prepare_wrong_owner_does_not_return_private_arrangement_name_or_settings(arranged):
    store, plan = arranged
    result = execute(store, 'practice_prepare', dict(SCOPE, participant_id='TEST-other'),
        dict(id=plan['id'], revision=1, entry_key=plan['items'][0]['key']))
    assert result['decision']['code'] == 'ARRANGEMENT_NOT_OWNED'
    assert result['entry'] is None and result['name'] is None and result['open_record'] is None


def test_scoped_practice_error_never_overwrites_original_scene_view(tmp_path):
    runtime = Runtime(tmp_path)
    try:
        assert runtime.ready.wait(5)
        original = runtime.controller.state
        view_spy = Mock(wraps=runtime._view)
        runtime._view = view_spy
        replies = response(runtime, 'practice_get', scope=SCOPE, id=str(uuid4()), request_id=str(uuid4()))
        error = next(r for r in replies if r['kind'] == 'error' and r['command'] == 'practice_get')
        assert error['code'] == 'NOT_FOUND' and error['category'] == 'AUTHORIZATION'
        assert not any(call.kwargs.get('operation_error') for call in view_spy.call_args_list)
        assert runtime.controller.state == original and runtime.camera.worker is None
    finally:
        response(runtime, 'shutdown'); runtime.thread.join(6); assert not runtime.thread.is_alive()
