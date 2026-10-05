from datetime import date, timedelta
import pytest
from app.product.daily_store import DailyStore

SCOPE={'source_kind':'LIVE_CAMERA','usage_context':'SELF_USE'}


def test_onboarding_once_and_scope_separation(tmp_path):
    store=DailyStore(tmp_path)
    store.apply('self','daily.onboarding',dict(skipped=False,time='09:00',days=[0,2,4]),SCOPE)
    store.apply('self','daily.onboarding',dict(skipped=False,time='10:00'),SCOPE)
    assert len(store.snapshot('self',SCOPE)['schedules'])==1
    assert not store.snapshot('self',dict(source_kind='SYNTHETIC',usage_context='TEST'))['schedules']
    assert not store.snapshot('other',SCOPE)['schedules']
    # Connections really close, including after errors; Windows can rename the file.
    store.path.rename(tmp_path/'renamed.sqlite3')


def test_skip_no_plan_and_schedule_changes_are_explicit(tmp_path):
    store=DailyStore(tmp_path)
    store.apply('self','daily.onboarding',dict(skipped=True),SCOPE)
    assert not store.snapshot('self',SCOPE)['schedules']
    payload=dict(date=date.today().isoformat(),time='09:00',kind='training',planId='plan',revision=1,name='已有计划')
    store.apply('self','daily.schedule',payload,SCOPE)
    entry=store.snapshot('self',SCOPE)['schedules'][0]
    with pytest.raises(ValueError):store.apply('self','daily.schedule',payload,SCOPE)
    store.apply('self','daily.schedule',dict(entry,date=(date.today()+timedelta(days=1)).isoformat()),SCOPE)
    assert store.snapshot('self',SCOPE)['schedules'][0]['id']==entry['id']
    store.apply('self','daily.unschedule',{'id':entry['id']},SCOPE)
    assert not store.snapshot('self',SCOPE)['schedules']


def test_doses_survive_schedule_edit_corrections_and_restart(tmp_path):
    store=DailyStore(tmp_path)
    day=date.today().isoformat()
    store.apply('self','daily.medSchedule',dict(medId='med',times=['08:00','20:00'],start=day,end=''),SCOPE)
    record=dict(medId='med',date=day,time='08:00',status='taken',medName='已有药物',dose='医嘱剂量')
    store.apply('self','daily.dose',record,SCOPE)
    store.apply('self','daily.medSchedule',dict(medId='med',times=['10:00'],start=day,end=''),SCOPE)
    store.apply('self','daily.dose',dict(record,status='unrecorded'),SCOPE)
    restarted=DailyStore(tmp_path).snapshot('self',SCOPE)
    assert next(iter(restarted['doses'].values()))['status']=='unrecorded'
    assert restarted['doseAudit'][0]['record']['previous']=='taken'
    assert len(restarted['doseAudit'])==2
    with pytest.raises(ValueError):store.apply('self','daily.dose',dict(record,date=(date.today()+timedelta(days=1)).isoformat()),SCOPE)
    assert not store.snapshot('other',SCOPE)['doses']


def test_invalid_dates_times_and_permissions_are_not_saved(tmp_path):
    store=DailyStore(tmp_path)
    for clock in (['8am'],['25:00'],[]):
        with pytest.raises(ValueError):store.apply('self','daily.medSchedule',dict(medId='med',times=clock,start=date.today().isoformat()),SCOPE)
    with pytest.raises(ValueError):store.apply('self','daily.familyGrant',dict(member='stranger',categories=['health']),SCOPE)
    assert not store.snapshot('self',SCOPE)['medSchedules']


def test_family_binding_is_not_consent_and_directions_are_independent(tmp_path):
    store=DailyStore(tmp_path)
    code=store.apply('parent','daily.familyInvite',{},SCOPE)['code']
    with pytest.raises(ValueError):store.apply('parent','daily.familyBind',{'code':code},SCOPE)
    store.apply('self','daily.familyBind',{'code':code},SCOPE)
    assert store.allowed_members('self')==[('parent',[])]
    assert store.allowed_members('parent')==[('self',[])]
    with pytest.raises(ValueError):store.apply('third','daily.familyBind',{'code':code},SCOPE)
    store.apply('parent','daily.familyGrant',dict(member='self',categories=['health']),SCOPE)
    assert store.allowed_members('self')==[('parent',['health'])]
    assert store.allowed_members('parent')==[('self',[])]
    store.apply('parent','daily.familyGrant',dict(member='self',categories=[]),SCOPE)
    assert store.allowed_members('self')==[('parent',[])]
    store.apply('parent','daily.familyUnbind',dict(member='self'),SCOPE)
    assert not store.allowed_members('self') and not store.allowed_members('parent')


def test_clear_unlinks_every_member_and_removes_only_owners_new_data(tmp_path):
    store=DailyStore(tmp_path)
    code=store.apply('parent','daily.familyInvite',{},SCOPE)['code']
    store.apply('self','daily.familyBind',{'code':code},SCOPE)
    store.apply('parent','daily.onboarding',dict(skipped=True),SCOPE)
    store.clear('self')
    assert not store.allowed_members('parent')
    assert store.snapshot('parent',SCOPE)['onboarding']['skipped']


def test_plan_versions_survive_restart_and_do_not_cross_owners(tmp_path):
    store=DailyStore(tmp_path)
    record=dict(id='original',revision=1,name='原计划',scope=dict(SCOPE,participant_id='self'),items=[{'key':'original-item'}])
    store.remember_plan('self',record)
    record['items'][0]['key']='changed-in-memory'
    saved=DailyStore(tmp_path).snapshot('self',SCOPE)['planVersions']
    assert saved[0]['items'][0]['key']=='original-item'
    assert not store.snapshot('other',SCOPE)['planVersions']
