"""Original owning SQLite, explicit TEST completion, never motion evidence."""
import copy
from uuid import uuid4

import pytest

from app.guided_practice import execute, PracticeError
from app.storage import Storage
from app.training_plans import new_training_plan
from test_saved_training_plans import SCOPE, item
from test_qt_guided_practice import start, end, run


@pytest.fixture
def sequence(tmp_path):
    store = Storage(tmp_path/'home_rehab.sqlite3')
    plan = store.save_training_plan(new_training_plan(SCOPE, 'TEST 两项安排', [
        item(target_reps=3, target_sets=2, rest_between_sets_s=0),
        item('knee_extension', 'right', target_reps=2, target_sets=1, needs_companion=True)]), expected_revision=0)
    yield store, plan
    store.close()


def completed(store, record, count=None, **changes):
    payload = end(); payload.update(reason='completed_set', count=count, **changes)
    return run(store, 'practice_finish', id=record['id'], payload=payload)


def next_payload(**changes):
    return dict(operation_id=str(uuid4()), arrangement_confirmed=True,
                support_ready=True, companion_present=False, **changes)


def test_two_sets_then_next_action_keep_journey_and_individual_fact_scopes(sequence):
    store, plan = sequence
    first = completed(store, run(store, 'practice_start', payload=start(plan)), 3)
    assert first['continuation']['kind'] == 'next_set' and first['continuation']['set_index'] == 2
    payload = next_payload()
    second = run(store, 'practice_continue', id=first['id'], payload=payload)
    assert second['journey_id'] == first['journey_id'] and second['id'] != first['id']
    assert second['set_index'] == 2 and second['predecessor_id'] == first['id']
    assert second['draft']['count'] is None and second['draft']['elapsed_ms'] == 0
    assert run(store, 'practice_continue', id=first['id'], payload=payload)['id'] == second['id']
    second = completed(store, second, None)
    assert second['continuation']['kind'] == 'next_action'
    assert second['continuation']['decision']['code'] == 'SUPPORT_CONFIRMATION_REQUIRED'
    value = next_payload()
    with pytest.raises(PracticeError) as error:
        run(store, 'practice_continue', id=second['id'], payload=value)
    assert error.value.code == 'COMPANION_REQUIRED'
    value['companion_present'] = True
    third = run(store, 'practice_continue', id=second['id'], payload=value)
    assert third['set_index'] == 1 and third['exercise_id'] == 'knee_extension' and third['side'] == 'right'
    third = completed(store, third, 2)
    assert third['continuation'] is None
    history = run(store, 'practice_history')
    assert len(history) == 3 and len({r['journey_id'] for r in history}) == 1
    assert {r['id']: r['self_reported_count'] for r in history} == {first['id']: 3, second['id']: None, third['id']: 2}
    assert all(r['confirmed_count'] is None and r['formal_plan_contribution'] is None for r in history)
    assert store.list_sessions() == [] and store.get_training_plan(plan['id']) == plan


def test_plain_end_never_authorizes_next_set_or_fills_count(sequence):
    store, plan = sequence
    r = run(store, 'practice_start', payload=start(plan))
    ended = run(store, 'practice_finish', id=r['id'], payload=end())
    assert ended['self_reported_count'] is None and ended['continuation'] is None
    with pytest.raises(PracticeError): run(store, 'practice_continue', id=r['id'], payload=next_payload())
    assert len(run(store, 'practice_history')) == 1


def test_rest_uses_original_duration_and_never_counts_as_exercise(sequence, monkeypatch):
    store, plan = sequence
    plan['items'][0]['settings']['rest_between_sets_s'] = 30
    plan = store.save_training_plan(plan, expected_revision=1)
    monkeypatch.setattr('app.guided_practice.utc_now', lambda: '2026-10-12T02:00:00+00:00')
    first = completed(store, run(store, 'practice_start', payload=start(plan)))
    assert first['continuation']['rest_remaining_ms'] == 30000
    value = next_payload()
    with pytest.raises(PracticeError) as error:
        run(store, 'practice_continue', id=first['id'], payload=value)
    assert error.value.code == 'REST_PENDING' and len(run(store, 'practice_history')) == 1
    monkeypatch.setattr('app.guided_practice.utc_now', lambda: '2026-10-12T02:00:31+00:00')
    assert run(store, 'practice_get', id=first['id'])['continuation']['rest_remaining_ms'] == 0
    second = run(store, 'practice_continue', id=first['id'], payload=value)
    assert second['draft']['elapsed_ms'] == 0 and second['draft']['count'] is None


def test_lost_continue_reply_original_key_reopens_one_successor_not_new_group(sequence):
    store, plan = sequence
    first = completed(store, run(store, 'practice_start', payload=start(plan)))
    payload = next_payload(); successor = run(store, 'practice_continue', id=first['id'], payload=payload)
    projection = run(store, 'practice_get', id=first['id'])
    assert projection['continuation']['successor_id'] == successor['id']
    for _ in range(3):
        assert run(store, 'practice_continue', id=first['id'], payload=payload)['id'] == successor['id']
    with pytest.raises(PracticeError):
        run(store, 'practice_continue', id=first['id'], payload=dict(payload, operation_id=str(uuid4())))
    assert len(run(store, 'practice_history')) == 2


def test_new_revision_or_stop_blocks_next_but_never_undoes_committed_group(sequence):
    store, plan = sequence
    first = completed(store, run(store, 'practice_start', payload=start(plan)), 3,
                      feedback=dict(pain=1, fatigue=None))
    assert first['continuation']['decision']['code'] == 'PRACTICE_STOP_RECORDED'
    with pytest.raises(PracticeError): run(store, 'practice_continue', id=first['id'], payload=next_payload())
    store.set_training_plan_archived(plan['id'], SCOPE, True, expected_revision=1)
    assert run(store, 'practice_get', id=first['id'])['state'] == 'COMMITTED'
    assert run(store, 'practice_get', id=first['id'])['self_reported_count'] == 3


def test_cancel_rest_persists_end_intent_without_altering_group_or_formal_progress(sequence):
    store, plan = sequence
    first = completed(store, run(store, 'practice_start', payload=start(plan)), 3)
    finish = copy.deepcopy(first['finish_payload'])
    value = dict(operation_id=str(uuid4()))
    stopped = run(store, 'practice_close_journey', id=first['id'], payload=value)
    assert stopped['continuation'] is None and stopped['journey_closed']
    assert stopped['finish_payload'] == finish and stopped['self_reported_count'] == 3
    assert run(store, 'practice_close_journey', id=first['id'], payload=value) == stopped
    with pytest.raises(PracticeError): run(store, 'practice_continue', id=first['id'], payload=next_payload())
    assert len(run(store, 'practice_history')) == 1 and not store.list_sessions()


def test_continue_is_owner_bound_and_strict_payload_never_accepts_client_dose(sequence):
    store, plan = sequence
    first = completed(store, run(store, 'practice_start', payload=start(plan)))
    for scope in (dict(SCOPE, participant_id='other'), dict(SCOPE, source_kind='LIVE_CAMERA')):
        with pytest.raises(PracticeError): execute(store, 'practice_continue', scope, dict(id=first['id'], payload=next_payload()))
    with pytest.raises(PracticeError):
        run(store, 'practice_continue', id=first['id'], payload=dict(next_payload(), set_index=9))
    assert len(run(store, 'practice_history')) == 1


def test_other_open_journey_cannot_be_parallelized_by_continuation(sequence):
    store, plan = sequence
    first = completed(store, run(store, 'practice_start', payload=start(plan)))
    other = run(store, 'practice_start', payload=start(plan))
    with pytest.raises(PracticeError) as error:
        run(store, 'practice_continue', id=first['id'], payload=next_payload())
    assert error.value.code == 'ORIGINAL_PRACTICE_OPEN'
    assert run(store, 'practice_get', id=other['id'])['state'] == 'PRACTICING'
