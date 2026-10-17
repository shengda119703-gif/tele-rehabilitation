import copy
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from threading import Barrier

import pytest

from app.rehab_operation_tools import RehabOperationTools
from app.rehab_read_tools import RehabReadTools
from app.product.daily_store import DailyStore
from app.storage import Storage
from app.training_plans import item_from_plan, new_training_plan
from app.settings import default_plan


def sample_plan():
    scope = {
        'participant_id': 'SYNTHETIC-TEST-participant',
        'source_kind': 'SYNTHETIC',
        'usage_context': 'TEST',
    }
    base = default_plan('sit_to_stand')
    item = item_from_plan({
        'exercise_id': 'sit_to_stand',
        'side': 'left',
        **base,
    })
    return new_training_plan(scope, '测试康复计划', [item])


def test_patch_existing_plan_changes_only_supported_setting():
    plan = sample_plan()
    patched = RehabOperationTools._patch_plan(plan, {
        'update': [{
            'key': 'sit_to_stand:left',
            'settings': {'target_reps': 8},
        }],
    })
    assert patched['name'] == plan['name']
    assert patched['items'][0]['settings']['target_reps'] == 8
    assert patched['items'][0]['key'] == 'sit_to_stand:left'


def test_patch_rejects_unknown_setting_and_unknown_remove():
    plan = sample_plan()
    try:
        RehabOperationTools._patch_plan(plan, {
            'update': [{
                'key': 'sit_to_stand:left',
                'settings': {'made_up_field': 1},
            }],
        })
    except ValueError:
        pass
    else:
        raise AssertionError('unknown setting must be rejected')

    try:
        RehabOperationTools._patch_plan(plan, {'remove': ['missing:left']})
    except ValueError:
        pass
    else:
        raise AssertionError('unknown item must be rejected')


def test_patch_adds_real_action_and_preserves_plan_shape():
    plan = sample_plan()
    # Adding the same key is rejected; this also proves the operation layer
    # does not silently replace an existing user-selected action.
    try:
        RehabOperationTools._patch_plan(plan, {
            'add': [{
                'exercise_id': 'sit_to_stand',
                'side': 'left',
                'settings': copy.deepcopy(plan['items'][0]['settings']),
            }],
        })
    except ValueError:
        pass
    else:
        raise AssertionError('duplicate action key must be rejected')


SYNTHETIC_SCOPE = dict(participant_id='SYNTHETIC-TEST-operation-owner', source_kind='SYNTHETIC', usage_context='TEST')


@pytest.fixture
def real_host(tmp_path):
    database = tmp_path / 'SYNTHETIC-TEST-rehab.sqlite3'
    record = new_training_plan(SYNTHETIC_SCOPE, 'SYNTHETIC / TEST 康复计划', [
        item_from_plan(default_plan('sit_to_stand')),
        item_from_plan(dict(default_plan('knee_extension'), side='right')),
    ])
    store = Storage(database)
    try:
        saved = store.save_training_plan(record, expected_revision=0)
    finally:
        store.close()
    daily = DailyStore(tmp_path)
    return RehabOperationTools(database, SYNTHETIC_SCOPE, daily, SYNTHETIC_SCOPE['participant_id']), saved, daily


def read_plan(host, plan_id):
    store = Storage(host.database, readonly=True)
    try:
        return store.get_training_plan(plan_id)
    finally:
        store.close()


def audit_count(database):
    with sqlite3.connect(database) as db:
        return db.execute('SELECT count(*) FROM audit').fetchone()[0]


def test_real_sqlite_preview_commit_revision_audit_and_reopen(real_host):
    host, plan, _ = real_host
    args = dict(plan_id=plan['id'], expected_revision=1, patch={'name': 'SYNTHETIC / TEST 晚间计划'})
    assert host('rehab.plan.change', dict(args, commit=False))['status'] == 'preview'
    assert read_plan(host, plan['id']) == plan
    assert audit_count(host.database) == 1
    receipt = host('rehab.plan.change', dict(args, commit=True))
    assert receipt['plan_id'] == plan['id'] and receipt['revision'] == 2
    patch = {'update': [{'key': plan['items'][0]['key'], 'settings': {'target_reps': 8}}],
             'add': [{'exercise_id': 'shoulder_abduction', 'side': 'left'}],
             'remove': [plan['items'][1]['key']]}
    assert host('rehab.plan.change', dict(plan_id=plan['id'], expected_revision=2, patch=patch, commit=True))['revision'] == 3
    saved = read_plan(host, plan['id'])
    assert saved['name'] == args['patch']['name']
    assert [i['exercise_id'] for i in saved['items']] == ['sit_to_stand', 'shoulder_abduction']
    assert saved['items'][0]['settings']['target_reps'] == 8
    assert audit_count(host.database) == 3
    records = RehabReadTools(host.database, SYNTHETIC_SCOPE)('rehab.get_training_plan', {})['records']
    assert records[0]['id'] == saved['id'] and records[0]['revision'] == saved['revision']
    assert records[0]['items'][0]['settings']['target_reps'] == 8
    with pytest.raises(ValueError, match='变化'):
        host('rehab.plan.change', dict(args, commit=True))
    assert audit_count(host.database) == 3


@pytest.mark.parametrize('scope_change', [dict(participant_id='SYNTHETIC-TEST-other'), dict(source_kind='REPLAY_FILE'), dict(usage_context='SELF_USE')])
def test_real_sqlite_owner_and_source_isolation(real_host, scope_change):
    host, plan, daily = real_host
    scope = dict(SYNTHETIC_SCOPE, **scope_change)
    other = RehabOperationTools(host.database, scope, daily, scope['participant_id'])
    with pytest.raises(ValueError, match='不属于'):
        other('rehab.plan.change', dict(plan_id=plan['id'], expected_revision=1, patch={'name': 'SYNTHETIC / TEST forbidden'}, commit=True))
    assert read_plan(host, plan['id']) == plan
    assert audit_count(host.database) == 1


def publish_test_plan(host, plan):
    plan = copy.deepcopy(plan)
    plan['doctor_publication'] = {'id': '00000000-0000-0000-0000-000000000001', 'version': 1}
    store = Storage(host.database)
    try:
        return store.save_training_plan(plan, expected_revision=plan['revision'])
    finally:
        store.close()


@pytest.mark.parametrize('patch', [
    {'update': [{'key': 'sit_to_stand:left', 'settings': {'target_reps': 80}}]},
    {'add': [{'exercise_id': 'shoulder_abduction', 'side': 'left'}]},
    {'remove': ['knee_extension:right']},
])
def test_published_prescription_cannot_be_changed_by_patient_confirmation(real_host, patch):
    host, plan, _ = real_host
    published = publish_test_plan(host, plan)
    for commit in (False, True):
        with pytest.raises(ValueError, match='医生'):
            host('rehab.plan.change', dict(plan_id=plan['id'], expected_revision=published['revision'], patch=patch, commit=commit))
    assert read_plan(host, plan['id']) == published
    assert audit_count(host.database) == 2


@pytest.mark.parametrize('strip_publication', [False, True])
def test_storage_rechecks_published_prescription_even_without_operation_adapter(real_host, strip_publication):
    host, plan, _ = real_host
    published = publish_test_plan(host, plan)
    changed = copy.deepcopy(published)
    changed['items'][0]['settings']['target_reps'] = 80
    if strip_publication:
        changed.pop('doctor_publication')
    store = Storage(host.database)
    try:
        with pytest.raises(ValueError, match='医生'):
            store.save_training_plan(changed, expected_revision=published['revision'])
    finally:
        store.close()
    assert read_plan(host, plan['id']) == published
    assert audit_count(host.database) == 2


def test_published_plan_can_be_renamed_without_changing_prescription(real_host):
    host, plan, _ = real_host
    published = publish_test_plan(host, plan)
    host('rehab.plan.change', dict(plan_id=plan['id'], expected_revision=published['revision'], patch={'name': 'SYNTHETIC / TEST 自选名称'}, commit=True))
    saved = read_plan(host, plan['id'])
    assert saved['items'] == published['items'] and saved['doctor_publication'] == published['doctor_publication']


def schedule_args(plan):
    return dict(plan_id=plan['id'], plan_revision=plan['revision'], date=(date.today()+timedelta(days=1)).isoformat(), time='09:00', name='SYNTHETIC / TEST 训练')


def test_real_schedule_preview_commit_readback_reschedule_remove_and_audit(real_host):
    host, plan, daily = real_host
    args = schedule_args(plan)
    preview = host('rehab.schedule.upsert', dict(args, commit=False))
    assert preview['previous'] is None
    assert not daily.snapshot(host.owner, host.scope)['schedules']
    assert audit_count(daily.path) == 0
    receipt = host('rehab.schedule.upsert', dict(args, expected_existing=None, commit=True))
    saved = receipt['schedule']
    assert saved['id'] and saved['date'] == args['date'] and saved['time'] == '09:00'
    assert DailyStore(daily.path.parent).snapshot(host.owner, host.scope)['schedules'] == [saved]
    assert audit_count(daily.path) == 1
    args.update(id=saved['id'], time='20:00')
    preview = host('rehab.schedule.upsert', dict(args, commit=False))
    changed = host('rehab.schedule.upsert', dict(args, expected_existing=preview['previous'], commit=True))['schedule']
    assert changed['id'] == saved['id'] and changed['time'] == '20:00'
    assert daily.snapshot(host.owner, host.scope)['schedules'] == [changed]
    assert host('rehab.schedule.remove', dict(id=changed['id'], commit=False))['status'] == 'preview'
    assert host('rehab.schedule.remove', dict(id=changed['id'], expected_existing=changed, commit=True))['schedule'] == changed
    assert not daily.snapshot(host.owner, host.scope)['schedules']
    assert audit_count(daily.path) == 3


@pytest.mark.parametrize('operation', ['rehab.schedule.upsert', 'rehab.schedule.remove'])
def test_schedule_conflict_is_checked_inside_write_transaction(real_host, monkeypatch, operation):
    host, plan, daily = real_host
    args = schedule_args(plan)
    daily.apply(host.owner, 'daily.schedule', dict(args, kind='training', planId=plan['id'], revision=1), host.scope)
    previous = daily.snapshot(host.owner, host.scope)['schedules'][0]
    original_apply = daily.apply
    competing = dict(previous, time='18:00')
    def competing_apply(owner, name, payload, scope, **kwargs):
        original_apply(owner, 'daily.schedule', competing, scope)
        return original_apply(owner, name, payload, scope, **kwargs)
    monkeypatch.setattr(daily, 'apply', competing_apply)
    commit_args = dict(args, id=previous['id'], time='20:00') if operation.endswith('upsert') else dict(id=previous['id'])
    with pytest.raises(ValueError, match='变化'):
        host(operation, dict(commit_args, expected_existing=previous, commit=True))
    saved = daily.snapshot(host.owner, host.scope)['schedules']
    assert len(saved) == 1 and saved[0]['time'] == '18:00'
    assert audit_count(daily.path) == 2


def test_concurrent_confirmations_do_not_overwrite_the_winning_schedule(real_host, monkeypatch):
    host, plan, daily = real_host
    args = schedule_args(plan)
    previous = host('rehab.schedule.upsert', dict(args, commit=True))['schedule']
    original_apply, barrier = daily.apply, Barrier(2)
    def simultaneous_apply(*args, **kwargs):
        barrier.wait(timeout=5)
        return original_apply(*args, **kwargs)
    monkeypatch.setattr(daily, 'apply', simultaneous_apply)
    def commit(clock):
        try:
            return host('rehab.schedule.upsert', dict(args, id=previous['id'], time=clock, expected_existing=previous, commit=True))
        except ValueError as error:
            return str(error)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(commit, ['18:00', '20:00']))
    applied = [r for r in results if isinstance(r, dict)]
    assert len(applied) == 1 and sum(isinstance(r, str) and '变化' in r for r in results) == 1
    assert daily.snapshot(host.owner, host.scope)['schedules'] == [applied[0]['schedule']]
    assert audit_count(daily.path) == 2
