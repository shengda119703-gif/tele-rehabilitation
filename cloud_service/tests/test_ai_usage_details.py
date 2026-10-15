"""Actual-provider usage arithmetic with fictional receipts and isolated users."""
from uuid import uuid4
from sqlalchemy import select, update

from cloud_service.ai_usage import receipts, request_labels, usage_groups
from cloud_service.app import BASE, create_app
from cloud_service.tests.test_beta import answer, configured
from cloud_service.tests.test_workbench import setup, people, path


def test_daily_purpose_actual_usage_and_remaining_calls(setup):
    app = configured(setup, lambda *_: answer())
    aid, _, alice, _, doctor = people((app, *setup[1:]))
    for purpose in ['CHAT', 'RESULT_EXPLANATION', 'CHAT']:
        r = alice.post(path(aid, '/ai/requests'), json={'operation_id':str(uuid4()),'text':'TEST','purpose':purpose})
        assert r.json()['state'] == 'SUCCEEDED'
    detail = doctor.get(path(aid, '/ai/usage')).json()
    assert detail['usage']['calls'] == 3 and detail['usage']['total_tokens'] == 450
    assert detail['usage']['cache_hit_tokens'] == 60 and detail['usage']['cache_miss_tokens'] == 240
    assert detail['remaining_calls'] == 197
    assert detail['today']['usage']['calls'] == 3
    assert {p['purpose']:p['usage']['calls'] for p in detail['by_purpose']} == {'CHAT':2, 'RESULT_EXPLANATION':1}
    assert len(detail['days']) == 1 and detail['days'][0]['usage']['total_tokens'] == 450
    assert all(row['purpose'] in {'CHAT','RESULT_EXPLANATION'} for row in detail['items'])
    assert all('answer' not in row and 'text' not in row for row in detail['items'])
    assert alice.get(path(aid, '/ai/usage?period=not-a-month')).status_code == 422
    assert alice.get(path(aid, '/ai/usage?period=2026-01')).json()['usage']['calls'] == 0


def test_admin_budget_limits_and_isolation(setup):
    app = configured(setup, lambda *_: answer())
    aid, bid, alice, bob, doctor = people((app, *setup[1:]))
    value = {'monthly_tokens':3000,'monthly_calls':1}
    endpoint = path(aid, '/ai/budget')
    assert alice.put(endpoint,json=value).status_code == 403
    assert doctor.put(endpoint,json=value).is_success
    assert doctor.put(endpoint,json={**value,'monthly_calls':0}).status_code == 422
    assert doctor.put(endpoint,json=value,headers={'X-CSRF-Token':'wrong'}).status_code == 403
    assert bob.get(path(aid, '/ai/usage')).status_code == 404
    assert alice.post(path(aid, '/ai/requests'),json={'operation_id':str(uuid4()),'text':'TEST'}).is_success
    assert alice.post(path(aid, '/ai/requests'),json={'operation_id':str(uuid4()),'text':'TEST next'}).status_code == 429
    assert bob.get(path(bid, '/ai/usage')).json()['quota_calls'] == 200
    assert alice.get(BASE+'/care/ai/usage').status_code == 403
    overview = doctor.get(BASE+'/care/ai/usage?limit=1').json()
    assert overview['total'] == 2 and len(overview['items']) == 1 and overview['usage']['calls'] == 1
    assert all('answer' not in item for item in overview['items'])


def test_bjt_midnight_grouping_and_unknown_is_not_guessed(setup):
    row = {'created_at':1791993599,'purpose':'CHAT','state':'UNKNOWN','reservation':2500,'usage':None,'estimated_cost':None}
    from datetime import datetime, timezone
    # Explicit UTC times straddle midnight in Beijing, not host-local dates.
    row['created_at'] = int(datetime(2026,10,14,15,59,59,tzinfo=timezone.utc).timestamp())
    next_row = {**row,'created_at':row['created_at']+1}
    result = usage_groups([row,next_row])
    assert [day['date'] for day in result['days']] == ['2026-10-14','2026-10-15']
    assert result['by_purpose'][0]['usage']['total_tokens'] == 0
    assert result['by_purpose'][0]['usage']['uncertain_calls'] == 2
    assert result['by_purpose'][0]['usage']['reserved_tokens'] == 5000


def test_same_operation_cannot_change_usage_category(setup):
    app = configured(setup, lambda *_: answer())
    aid, _, alice, _, _ = people((app, *setup[1:]))
    body = {'operation_id':str(uuid4()),'text':'TEST','purpose':'RESULT_EXPLANATION'}
    one = alice.post(path(aid,'/ai/requests'),json=body)
    assert one.is_success
    assert alice.post(path(aid,'/ai/requests'),json=body).json()['id'] == one.json()['id']
    assert alice.post(path(aid,'/ai/requests'),json={**body,'purpose':'CHAT'}).status_code == 409
    with setup[1].engine.connect() as c:
        assert len(list(c.execute(select(request_labels)))) == 1


def test_truncated_or_invalid_answer_preserves_actual_billable_usage(setup):
    raw=answer();raw['choices'][0]['finish_reason']='length'
    app=configured(setup,lambda *_:raw,tariff={'version':'TEST','currency':'CNY','cache_hit':'.1','cache_miss':'1','output':'2'})
    aid,_,alice,_,doctor=people((app,*setup[1:]))
    body={'operation_id':str(uuid4()),'text':'TEST truncated'}
    result=alice.post(path(aid,'/ai/requests'),json=body).json()
    assert result['state']=='UNKNOWN' and result['answer'] is None
    assert result['usage']['total_tokens']==150 and result['estimated_cost']=='0.000182'
    assert alice.post(path(aid,'/ai/requests'),json=body).json()==result
    used=doctor.get(path(aid,'/ai/usage')).json()['usage']
    assert used['total_tokens']==150 and used['reserved_tokens']==0
