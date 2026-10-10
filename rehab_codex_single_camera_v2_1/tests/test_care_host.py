"""Real local transactions with isolated TEST owners; no camera or model."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
import copy
import pytest
from app.product.daily_store import DailyStore
from app.product.care_host import CareHost

SCOPE = {'participant_id': 'TEST', 'source_kind': 'SYNTHETIC', 'usage_context': 'TEST'}

@pytest.fixture
def host(tmp_path):
    daily = DailyStore(tmp_path)
    meds = [{'id':'m','name':'测试药','dose':'既有说明','purpose':'','times':'','status':'active'}]
    daily.apply('TEST','daily.medSchedule',{'medId':'m','times':['08:00'],'start':date.today().isoformat(),'end':''},SCOPE)
    plans = [{'id':'p','revision':1,'next_available':True,'progress':{'next_key':'e','blocked':''}}]
    daily.apply('TEST','daily.schedule',{'id':'s','date':date.today().isoformat(),'time':'14:00','kind':'training','name':'TEST 训练','planId':'p','revision':1},SCOPE)
    h = CareHost(tmp_path,daily,'TEST',SCOPE,profile_reader=lambda:copy.deepcopy(meds),rehab_reader=lambda:copy.deepcopy({'plans':plans,'history':[]}))
    return h,daily,meds,plans

def dose(h):
    f=h.read();p={'medId':'m','date':date.today().isoformat(),'time':'08:00','status':'taken'}
    return {'operation':'daily.dose','payload':p,'expected':{'medicine':f['medications'][0],'schedule':f['daily']['medSchedules']['m'],'dose':None},'label':'TEST'}

def test_occurrence_and_receipt_commit_together_and_replay_does_not_add_audit(host):
    h,d,_,_=host;a=dose(h)
    r=h.execute(a,'TEST-once:0');assert r['status']=='succeeded'
    assert h.execute(a,'TEST-once:0')==r
    assert len(d.snapshot('TEST',SCOPE)['doseAudit'])==1
    a['payload']['status']='skipped'
    with pytest.raises(ValueError):h.execute(a,'TEST-once:0')

def test_concurrent_replays_have_one_business_write(host):
    h,d,_,_=host;a=dose(h)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda _:h.execute(a,'TEST-concurrent:0'),range(4)))
    assert all(r==results[0] for r in results)
    assert len(d.snapshot('TEST',SCOPE)['doseAudit'])==1

def test_stale_medicine_or_occurrence_is_not_overwritten(host):
    h,d,meds,_=host;a=dose(h);meds[0]['dose']='changed'
    with pytest.raises(ValueError):h.execute(a,'TEST-medicine:0')
    meds[0]['dose']='既有说明';d.apply('TEST','daily.dose',dict(a['payload'],status='skipped'),SCOPE)
    with pytest.raises(ValueError):h.execute(a,'TEST-stale:0')
    assert d.snapshot('TEST',SCOPE)['doses']['m|'+date.today().isoformat()+'|08:00']['status']=='skipped'

def test_reschedule_rechecks_plan_and_preserves_original_target(host):
    h,d,_,plans=host;f=h.read();s=f['daily']['schedules'][0]
    a={'operation':'daily.schedule','payload':dict(s,time='16:00'),'expected':{'schedule':s,'plan':{'id':'p','revision':1}},'label':'TEST'}
    # The domain only accepts the original arrangement fields, not arbitrary createdAt metadata.
    a['payload']={k:v for k,v in a['payload'].items() if k!='createdAt'}
    plans[0]['revision']=2
    with pytest.raises(ValueError):h.execute(a,'TEST-plan:0')
    plans[0]['revision']=1;h.execute(a,'TEST-plan:0')
    saved=d.snapshot('TEST',SCOPE)['schedules'][0]
    assert saved['time']=='16:00' and saved['planId']=='p'

def test_forged_scope_extra_payload_and_unsupported_operation_do_not_write(host,tmp_path):
    h,d,_,_=host
    with pytest.raises(ValueError):CareHost(tmp_path,d,'OTHER',SCOPE)
    for op,p in [('medication.save',{}),('daily.dose',dict(dose(h)['payload'],owner='OTHER'))]:
        a=dose(h);a.update(operation=op,payload=p)
        with pytest.raises(ValueError):h.execute(a,'TEST-forged:0')
    assert not d.snapshot('TEST',SCOPE)['doses']

def test_unrelated_change_does_not_invalidate_a_specific_occurrence(host):
    h,d,_,_=host;a=dose(h)
    d.apply('TEST','daily.onboarding',{'skipped':True},SCOPE)
    assert h.execute(a,'TEST-unrelated:0')['status']=='succeeded'

def test_bad_precondition_rolls_back_without_receipt(host):
    h,d,_,_=host;a=dose(h);a['expected']['schedule']['times']=['09:00']
    with pytest.raises(ValueError):h.execute(a,'TEST-rollback:0')
    assert not d.snapshot('TEST',SCOPE)['doses']
    assert h.execute(dose(h),'TEST-rollback:0')['status']=='succeeded'


def test_expiry_prevents_new_write_but_keeps_committed_receipt_recoverable(host):
    h,d,_,_=host;a=dose(h)
    expired=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat()
    with pytest.raises(ValueError):h.execute(a,'TEST-expired:0',expired)
    assert not d.snapshot('TEST',SCOPE)['doses']
    valid=(datetime.now(timezone.utc)+timedelta(minutes=1)).isoformat()
    receipt=h.execute(a,'TEST-recover-expired:0',valid)
    assert h.execute(a,'TEST-recover-expired:0',expired)==receipt
    assert len(d.snapshot('TEST',SCOPE)['doseAudit'])==1
