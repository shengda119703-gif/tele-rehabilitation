"""Isolated engineering contracts/faults. These are NOT vendor or real-device evidence."""
import base64
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
from pathlib import Path
import sqlite3
import struct
import threading
import time
from contextlib import contextmanager
from urllib.parse import parse_qs, urlsplit

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
import httpx
import pytest

from mobile_rehab.server import create_app
from mobile_rehab.wearables.config import ProviderConfig, load_config
from mobile_rehab.wearables.contracts import HealthError, canonical, normalize, timestamp, SCOPES
from mobile_rehab.wearables.outbox import LocalOutbox
from mobile_rehab.wearables.providers import Provider, Transport, nonce, parse_huawei_steps, parse_xiaomi, verify_xiaomi_notification
from mobile_rehab.wearables.service import WearableService
from mobile_rehab.wearables.store import Store

HEADERS = {'X-Rehab-Client':'mobile-v1'}
START = 1791849600000
END = START+86400000


def record(kind='steps_daily', value=200, version='1', sid='source-1', **extra):
    unit = {'steps_daily':'count','steps_delta':'count','heart_rate_sample':'bpm','heart_rate_summary':'bpm',
            'sleep_session':'minute','exercise_session':'second'}[kind]
    return dict(kind=kind,unit=unit,value=value,start_ms=START,end_ms=START+1000,version=version,
        source_store_id='TEST-store',source_record_id=sid,original_data_origin='TEST-origin',
        timezone='Asia/Shanghai',**extra)


def configs():
    x = ProviderConfig('xiaomi', True, 'TEST-client', 'TEST-secret',
        'https://test.invalid/api/health/oauth/xiaomi/callback', tuple(SCOPES['xiaomi'].values()), 'Asia/Shanghai', subscription_enabled=True)
    h = ProviderConfig('huawei', True, 'TEST-huawei', 'TEST-h-secret',
        'https://test.invalid/api/health/oauth/huawei/callback', tuple(SCOPES['huawei'].values()),
        'Asia/Shanghai','CN','TEST-approved-header')
    return dict(xiaomi=x,huawei=h)


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path/'wearables.sqlite3',Fernet.generate_key().decode())


def bind(store, owner='A', provider='xiaomi', identity='TEST-vendor-A', scopes=None, expired=False):
    scopes = scopes if scopes is not None else list(SCOPES[provider].values())
    with store.db() as db:
        return store.bind(db,owner,provider,identity,dict(access_token='TEST-access',refresh_token='TEST-refresh',
            expires_at=time.time()+(-10 if expired else 3600),scopes=scopes),scopes,'Asia/Shanghai')


def event(r=None, eid='TEST-event', deleted=False, route='health_connect'):
    return dict(event_id=eid,route=route,record=r or record(),deleted=deleted)


def imported(store, cid, events, bid='TEST-batch', owner='A', lease=None):
    lease = lease or store.lease(owner,cid,'TEST-installation')
    return store.import_batch(owner,cid,lease['generation'],bid,lease['lease_id'],lease['lease_token'],events)


@pytest.fixture
def service(tmp_path):
    transport = Transport(httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={}))),sleeper=lambda s:None)
    s = WearableService(tmp_path,configs(),Fernet.generate_key().decode(),transport)
    yield s
    s.close()


@pytest.fixture
def client(tmp_path, service, monkeypatch):
    monkeypatch.setattr('mobile_rehab.wearables.api.WearableService',lambda root:service)
    app = create_app(tmp_path/'server',pair_key='TEST',runner=lambda item:None)
    with TestClient(app,headers=HEADERS) as c:
        c.post('/api/pair',json={'code':'TEST'})
        yield c


def test_disabled_provider_keeps_original_service_and_auth(tmp_path):
    with TestClient(create_app(tmp_path,pair_key='TEST',runner=lambda item:None),headers=HEADERS) as c:
        assert c.get('/api/health').status_code==200
        assert c.get('/api/health/capabilities').status_code==401
        c.post('/api/pair',json={'code':'TEST'})
        cap=c.get('/api/health/capabilities').json()
        assert cap['rehab_can_continue'] and not cap['native_readers_connected']
        assert all(p['status']=='PROVIDER_NOT_CONFIGURED' for p in cap['providers'])
        assert c.post('/api/health/oauth/xiaomi/start',json={}).status_code==503
        assert c.get('/api/catalog').status_code==200
        assert c.get('/api/health/summary').json()['days']==[]


@pytest.mark.parametrize('unit,multiplier',[('second',1),('millisecond',1000),('nanosecond',1000000000)])
def test_exact_time_units(unit,multiplier):
    assert timestamp(str(1791849600*multiplier+multiplier//10),unit)==1791849600000+(0 if unit=='second' else 100)


@pytest.mark.parametrize('bad',[True,1.0,'1.1','-1',None])
def test_bad_time_never_guessed(bad):
    with pytest.raises(HealthError):timestamp(bad,'nanosecond')


@pytest.mark.parametrize('patch',[{'unit':'hour'},{'value':True},{'value':float('nan')},
    {'timezone':'NOT/A/ZONE'},{'source_record_id':9007199254740993},{'version':1},{'end_ms':START-1}])
def test_strict_semantics(patch):
    with pytest.raises(HealthError):normalize({**record(),**patch})


def test_unknown_value_not_zero_summary_not_fake_samples(store):
    cid=bind(store)
    imported(store,cid,[event(record(value=None)),event(record('heart_rate_summary',80,sid='summary'),eid='summary')])
    summary=store.summary('A',START,END)
    assert summary['days'][0]['value'] is None
    assert not any(r['kind']=='heart_rate_sample' for r in store.records('A'))
    zero=record(value=0,sid='zero-on-earlier-day')
    zero.update(start_ms=START-86400000,end_ms=START-86400000+1000)
    imported(store,cid,[event(zero,eid='late-zero')],bid='late-zero')
    assert store.summary('A',START-86400000,START)['days'][0]['value']==0
    actual=next(r for r in store.records('A') if r['source_record_id']=='zero-on-earlier-day')
    assert actual['start_ms']==START-86400000


def test_owner_identity_generation_and_encrypted_tokens(store):
    cid=bind(store)
    c=store.connection('A',cid)
    assert b'TEST-access' not in c['tokens'] and 'TEST-vendor-A' not in canonical(store.connections('A'))
    with pytest.raises(HealthError):store.connection('B',cid)
    assert store.connections('B')==[]
    same=bind(store)
    assert same==cid and store.connection('A',cid)['logical_source_id']==c['logical_source_id']
    assert store.connection('A',cid)['generation']==2
    other=bind(store,identity='TEST-vendor-B')
    assert other!=cid
    assert bind(store,owner='B')!=cid


@pytest.mark.parametrize('fault',['wrong_state','wrong_owner','wrong_provider','expired','replay','newer_attempt'])
def test_authorization_state_faults(store,fault):
    a=store.create_attempt('A','xiaomi',[])
    if fault=='expired':
        with store.db() as db:db.execute('UPDATE attempts SET expires=0')
    if fault=='newer_attempt':store.create_attempt('A','xiaomi',[])
    if fault=='replay':store.consume_attempt('A','xiaomi',a['state'])
    with pytest.raises(HealthError):
        store.consume_attempt('B' if fault=='wrong_owner' else 'A','huawei' if fault=='wrong_provider' else 'xiaomi',
                              'wrong' if fault=='wrong_state' else a['state'])
    assert store.connections('A')==[]


def test_explicit_identity_change_and_revoked_auth_attempt(store):
    cid=bind(store)
    a=store.create_attempt('A','xiaomi',[],cid)
    old=store.consume_attempt('A','xiaomi',a['state'])
    with pytest.raises(HealthError,match='IDENTITY_MISMATCH'):
        store.finish_attempt(old,'different',{},[],'Asia/Shanghai')
    store.revoke('A',cid)
    with pytest.raises(HealthError,match='STALE_CONNECTION_GENERATION'):
        store.finish_attempt(old,'TEST-vendor-A',{},[],'Asia/Shanghai')


def test_authorization_http_roundtrip_partial_scope_without_secret(client,service):
    def handler(req):
        assert req.method=='POST' and req.url.path=='/oauth2/token'
        assert 'TEST-secret' not in str(req.url)
        form=parse_qs(req.content.decode());assert form['client_secret']==['TEST-secret']
        return httpx.Response(200,content=b'&&&START&&& '+json.dumps(dict(access_token='TEST-access',expires_in=3600,
            refresh_token='TEST-refresh',openId='TEST-vendor',scope='200016')).encode())
    service.transport.client=httpx.Client(transport=httpx.MockTransport(handler))
    start=client.post('/api/health/oauth/xiaomi/start',json={'metrics':['steps_daily','sleep_session']}).json()
    params=parse_qs(urlsplit(start['authorization_url']).query)
    assert params['scope_provider']==['healthkit']
    reply=client.get('/api/health/oauth/xiaomi/callback',params={'state':params['state'][0],'code':'TEST-code'})
    assert reply.status_code==200,reply.text
    assert reply.json()['granted_scopes']==['200016']
    assert not any(x in reply.text for x in ('TEST-access','TEST-refresh','TEST-secret','TEST-vendor'))
    assert client.get('/api/health/oauth-attempts/'+start['attempt_id']).json()['status']=='connected'
    assert client.get('/api/health/oauth/xiaomi/callback',params={'state':params['state'][0],'code':'TEST-code'}).status_code==400
    assert client.post('/api/health/oauth/xiaomi/start',json={'patient_id':'B'}).status_code==400


def test_huawei_tokeninfo_verified_identity(service):
    cfg=service.configs['huawei']
    def handler(req):
        if req.url.path.endswith('/tokeninfo'):
            assert parse_qs(req.content.decode())['id_token']==['TEST-id-token']
            return httpx.Response(200,json=dict(iss='https://accounts.huawei.com',aud=cfg.client_id,exp=int(time.time()+1000),
                                               sub='TEST-h-sub',alg='RS256',nonce='TEST-nonce'))
        return httpx.Response(200,json=dict(access_token='TEST-h-access',expires_in=3600,refresh_token='TEST-h-refresh',
                                           id_token='TEST-id-token',scope='openid '+SCOPES['huawei']['steps_daily']))
    p=Provider(cfg,Transport(httpx.Client(transport=httpx.MockTransport(handler))))
    identity,_,granted=p.token(code='TEST-code',auth_nonce='TEST-nonce')
    assert identity=='TEST-h-sub' and SCOPES['huawei']['steps_daily'] in granted
    with pytest.raises(HealthError,match='IDENTITY_MISMATCH'):p.token(code='TEST-code',auth_nonce='wrong')


def test_batches_repeat_lost_response_and_conflict(store):
    cid=bind(store); lease=store.lease('A',cid,'TEST-install')
    receipts=[imported(store,cid,[event()],lease=lease) for _ in range(3)]
    assert receipts[0]==receipts[1]==receipts[2]
    assert len(store.records('A'))==1
    assert store.receipt('A','TEST-batch')==receipts[0]
    assert imported(store,cid,[event()],bid='retry-new-batch',lease=lease)['items'][0]['status']=='duplicate'
    with pytest.raises(HealthError,match='IDEMPOTENCY_CONFLICT'):
        imported(store,cid,[event(record(value=999))],lease=lease)


def test_old_versions_tombstones_and_stable_scope_keys(store):
    cid=bind(store);l=store.lease('A',cid,'TEST-install')
    imported(store,cid,[event(record(version='10'))],bid='v10',lease=l)
    imported(store,cid,[event(record(version='11'),eid='delete',deleted=True)],bid='v11',lease=l)
    assert store.records('A')==[]
    assert imported(store,cid,[event(record(version='10'),eid='old')],bid='old',lease=l)['items'][0]['status']=='stale'
    assert imported(store,cid,[event(record(version='11'),eid='tie')],bid='tie',lease=l)['items'][0]['status']=='stale'
    imported(store,cid,[event(record(version='12'),eid='new')],bid='v12',lease=l)
    assert len(store.records('A'))==1
    other=bind(store,identity='TEST-other');imported(store,other,[event()],bid='other')
    assert len(store.records('A'))==2


def test_revoke_late_worker_logout_lease_and_delete_scope(store):
    cid=bind(store); other=bind(store,identity='TEST-other')
    l=store.lease('A',cid,'TEST-install')
    imported(store,cid,[event()],lease=l)
    store.stop_lease('A',l['lease_id'])
    assert store.connection('A',cid)['active']
    with pytest.raises(HealthError,match='UPLOAD_LEASE_INVALID'):
        imported(store,cid,[event(eid='late')],bid='late',lease=l)
    r=store.revoke('A',cid,delete_copy=True)
    assert not r['active'] and store.connection('A',other)['active']
    assert store.records('A')==[]
    with pytest.raises(HealthError):store.snapshot('A',cid,1,'steps_daily','cloud',START,END,5,[record()],list(SCOPES['xiaomi'].values()))
    with pytest.raises(HealthError,match='REIMPORT_CONFIRMATION_REQUIRED'):bind(store)


def test_snapshots_complete_window_revision_replay_and_scope_loss(store):
    cid=bind(store);scopes=list(SCOPES['xiaomi'].values())
    store.snapshot('A',cid,1,'steps_daily','cloud',START,END,1,[record(value=20,sid=None)],scopes)
    with pytest.raises(HealthError):store.snapshot('A',cid,1,'steps_daily','cloud',START,END,2,[record(unit_override='x',value=-1,sid=None)],scopes)
    assert store.summary('A',START,END)['days'][0]['value']==20
    store.snapshot('A',cid,1,'steps_daily','cloud',START,END,3,[record(value=30,sid=None)],scopes)
    assert store.snapshot('A',cid,1,'steps_daily','cloud',START,END,2,[record(value=99,sid=None)],scopes)['status']=='stale'
    assert store.summary('A',START,END)['days'][0]['value']==30
    with pytest.raises(HealthError,match='SCOPE_CHANGED'):
        store.snapshot('A',cid,1,'steps_daily','cloud',START,END,4,[],['200016'])
    assert store.summary('A',START,END)['days'][0]['value']==30


def test_multi_page_no_id_failure_never_switches_active_snapshot(service):
    cid=bind(service.store,scopes=['200007'])
    scopes=['200007']
    service.store.snapshot('A',cid,1,'heart_rate_sample','cloud',START,END,1,[record('heart_rate_sample',80,sid=None)],scopes)
    def handler(req):
        if 'cursor' in req.url.params:return httpx.Response(503,json={})
        p=dict(dataTypeName='com.xiaomi.heart_rate.delta',startTime=START,endTime=START+1000,value=[dict(fieldName='bpm',integerValue=90)])
        return httpx.Response(200,json=dict(group=[dict(dataSet=[dict(dataPoints=[p])])],hasMore=True,cursor='TEST-next'))
    p=Provider(service.configs['xiaomi'],Transport(httpx.Client(transport=httpx.MockTransport(handler)),sleeper=lambda s:None))
    staged=[]
    with pytest.raises(HealthError,match='NETWORK_RETRYABLE'):
        for records,_ in p.pages('heart_rate_sample',START,END,'TEST'):staged.extend(records)
    assert len(staged)==1
    assert service.store.records('A')[0]['value']==80


@pytest.mark.parametrize('cursor', ['',None,'repeat'])
def test_cursor_guards(cursor,service):
    def handler(req):return httpx.Response(200,json=dict(group=[],hasMore=True,cursor=cursor))
    p=Provider(service.configs['xiaomi'],Transport(httpx.Client(transport=httpx.MockTransport(handler))))
    with pytest.raises(HealthError,match='CURSOR_INVALID'):
        list(p.pages('heart_rate_sample',START,END,'TEST'))


def test_nonce_format_fresh_retry_and_no_redirect(service):
    raw=base64.urlsafe_b64decode(nonce(1791849600)+'==')
    assert len(raw)==12 and struct.unpack('>I',raw[8:])[0]==1791849600//60
    seen=[]
    def handler(req):
        seen.append(req.headers['X-Client-Nonce'])
        return httpx.Response(503 if len(seen)<3 else 200,json={})
    t=Transport(httpx.Client(transport=httpx.MockTransport(handler)),sleeper=lambda s:None)
    t.request('GET','https://hlthopen.io.mi.com/healthkit/test',retry=True)
    assert len(seen)==3 and len(set(seen))==3
    with pytest.raises(HealthError,match='VENDOR_ADDRESS_INVALID'):t.request('GET','https://attacker.invalid/',headers={'Authorization':'Bearer TEST'})
    t.client=httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(302,headers={'Location':'https://attacker.invalid'})))
    with pytest.raises(HealthError,match='VENDOR_HTTP_ERROR'):t.request('GET','https://health-api.cloud.huawei.com/healthkit/v2/test')


def test_huawei_verified_daily_payload_preserves_ns_and_collector(service):
    p=dict(startTime=str(START*1000000),endTime=str((END-1)*1000000+999999),
        dataTypeName='com.huawei.continuous.steps.total',originalDataCollectorId='TEST-origin',
        value=[dict(fieldName='steps',integerValue=9000)])
    parsed=parse_huawei_steps(dict(group=[dict(sampleSet=[dict(dataCollectorId='TEST-long-id',samplePoints=[p])])]),'Asia/Shanghai')
    assert parsed[0]['start_ms']==START and parsed[0]['end_ms']==END-1
    assert parsed[0]['details']['original_end']==p['endTime']
    seen=[]
    def handler(req):
        seen.append(req)
        return httpx.Response(200,json={'group':[]})
    cloud=Provider(service.configs['huawei'],Transport(httpx.Client(transport=httpx.MockTransport(handler))))
    assert list(cloud.pages('steps_daily',START,END,'TEST'))==[([],None)]
    body=json.loads(seen[0].content)
    assert body['dataTypes']==['com.huawei.continuous.steps.delta'] and body['timeZone']=='+0800'
    assert seen[0].headers['x-version']=='TEST-approved-header'
    with pytest.raises(HealthError):list(cloud.pages('heart_rate_sample',START,END,'TEST'))


def test_sleep_midnight_and_effective_exercise_not_rehab_completion():
    p=dict(dataTypeName='com.xiaomi.sleep.health',startTime=START-9*3600000,endTime=START,
        value=[dict(fieldName='bedtime',longValue=START-9*3600000),dict(fieldName='wakeup_time',longValue=START),
               dict(fieldName='all_sleep_duration',integerValue=420),dict(fieldName='sleep_awake_duration',integerValue=30)])
    r=normalize(parse_xiaomi({'healthRecords':[p]},'sleep_session','Asia/Shanghai')[0])
    assert r['value']==420 and r['details']['sleep_awake_duration']==30
    assert r['details']['sleep_day_rule']=='wake-local-date-1'
    from zoneinfo import ZoneInfo
    assert datetime.fromtimestamp(r['start_ms']/1000,ZoneInfo('Asia/Shanghai')).date() < datetime.fromtimestamp(r['end_ms']/1000,ZoneInfo('Asia/Shanghai')).date()
    assert r['day']==datetime.fromtimestamp(START/1000,ZoneInfo('Asia/Shanghai')).date().isoformat()
    e=parse_xiaomi({'sportRecords':[dict(startTime=START,endTime=START+20*60000,sportKey='walk',sportId='TEST-sport')]},'exercise_session','Asia/Shanghai')[0]
    assert e['value'] is None


def test_multiple_routes_logical_ids_and_delta_dedup(store):
    cid=bind(store);other=bind(store,identity='TEST-other')
    store.snapshot('A',cid,1,'steps_daily','cloud',START,END,1,[record(value=500)],list(SCOPES['xiaomi'].values()))
    imported(store,cid,[event(record(value=500,sid='HC-other-ID'))])
    imported(store,other,[event(record(value=700))],bid='second-owner-source')
    rows=store.summary('A',START,END)['days']
    assert len(rows)==1 and rows[0]['value']==500 and rows[0]['alternative_records']==2


def test_local_bootstrap_transaction_outbox_restart_response_lost(tmp_path,store):
    cid=bind(store);lease=store.lease('A',cid,'TEST-install')
    q=LocalOutbox(tmp_path/'local.sqlite3');scope=q.bind('A',cid,1,'TEST-install')
    q.bootstrap_token(scope,'steps_daily','TEST-before-snapshot')
    q.commit_page(scope,'steps_daily',[event()],expected_cursor=None,next_cursor='page2',snapshot=True)
    with pytest.raises(HealthError):
        q.commit_page(scope,'steps_daily',[event(record(value=-1))],expected_cursor='page2',next_cursor=None,snapshot=True,complete=True)
    assert q.inspect(scope)['cursors'][0]['page_cursor']=='page2'
    q=LocalOutbox(q.path)
    q.commit_page(scope,'steps_daily',[],expected_cursor='page2',next_cursor=None,snapshot=True,complete=True)
    q.commit_page(scope,'steps_daily',[event(record(version='2',value=300))],expected_cursor='TEST-before-snapshot',next_cursor='TEST-after-changes')
    batch=q.next_batch(scope)
    receipt=store.import_batch('A',cid,1,batch['batch_id'],lease['lease_id'],lease['lease_token'],batch['events'])
    assert q.next_batch(scope)==batch  # Server ACK lost; same payload / same event IDs survive process restart.
    assert store.import_batch('A',cid,1,batch['batch_id'],lease['lease_id'],lease['lease_token'],batch['events'])==receipt
    q.acknowledge(scope,receipt)
    assert q.inspect(scope)['pending']==0 and store.summary('A',START,END)['days'][0]['value']==300
    assert q.next_batch(scope) is None


def test_local_account_change_and_expired_cursor_preserve_past(tmp_path):
    q=LocalOutbox(tmp_path/'q.sqlite3');a=q.bind('A','TEST-cid',1,'TEST-install')
    q.bootstrap_token(a,'steps_daily','TEST-first')
    q.commit_page(a,'steps_daily',[event()],expected_cursor=None,next_cursor=None,snapshot=True,complete=True)
    q.bootstrap_token(a,'steps_daily','TEST-restricted-new')
    assert q.inspect(a)['pending']==1
    b=q.bind('B','OTHER',1,'TEST-install')
    with pytest.raises(HealthError):q.next_batch(a)
    assert q.next_batch(b) is None


def test_local_server_partial_or_wrong_receipt_keeps_queue(tmp_path):
    q=LocalOutbox(tmp_path/'q.sqlite3');scope=q.bind('A','TEST',1,'TEST-install')
    q.bootstrap_token(scope,'steps_daily','T')
    q.commit_page(scope,'steps_daily',[event()],expected_cursor=None,next_cursor=None,snapshot=True,complete=True)
    batch=q.next_batch(scope)
    with pytest.raises(HealthError):q.acknowledge(scope,dict(batch_id=batch['batch_id'],status='committed',items=[]))
    assert q.inspect(scope)['pending']==1


def test_cross_process_refresh_single_exchange(service,tmp_path):
    cid=bind(service.store,expired=True)
    calls=[]
    def handler(req):
        calls.append(req);time.sleep(.1)
        return httpx.Response(200,json=dict(access_token='TEST-new',refresh_token='TEST-new-refresh',expires_in=3600,
            open_id='TEST-vendor-A',scope='200016'))
    service.transport.client=httpx.Client(transport=httpx.MockTransport(handler))
    second=WearableService(service.store.path.parent,configs(),'',service.transport)
    second.store.cipher=service.store.cipher
    results=[];errors=[]
    def refresh(s):
        try:results.append(s.access_token('A',cid,1))
        except Exception as exc:errors.append(exc)
    workers=[threading.Thread(target=refresh,args=(s,)) for s in (service,second,service)]
    for t in workers:t.start()
    for t in workers:t.join()
    second.close()
    assert errors==[] and results==['TEST-new']*3 and len(calls)==1


def test_xiaomi_callback_signature_metadata_replay_revoked(service,client):
    cid=bind(service.store)
    service.sync=lambda owner,cid: {'queued':True}
    e=dict(openId='TEST-vendor-A',eventType='FITNESS_DATA_EVENT',subType='UPDATE',eventTime=START,
           metaData=[dict(metaKey='url',metaValue='https://attacker.invalid')])
    message='_'.join(str(e[k]) for k in ('openId','eventType','subType','eventTime'))
    sig=hmac.new(b'TEST-secret',message.encode(),hashlib.sha256).hexdigest()
    assert verify_xiaomi_notification('TEST-secret',e,sig)
    assert client.post('/callbacks/xiaomi/healthkit/notifications',json=e,headers={'x-notification-signature':'wrong'}).status_code==403
    for _ in range(2):
        assert client.post('/callbacks/xiaomi/healthkit/notifications',json=e,headers={'x-notification-signature':sig}).status_code==200
    with service.store.db() as db:assert db.execute('SELECT COUNT(*) FROM notifications').fetchone()[0]==1
    service.store.revoke('A',cid)
    e['eventTime']+=1;message='_'.join(str(e[k]) for k in ('openId','eventType','subType','eventTime'))
    sig=hmac.new(b'TEST-secret',message.encode(),hashlib.sha256).hexdigest()
    assert client.post('/callbacks/xiaomi/healthkit/notifications',json=e,headers={'x-notification-signature':sig}).status_code==200
    assert client.post('/callbacks/huawei/healthkit/notifications',json={'eventType':'CONNECTION_VERIFY_EVENT$VERIFY'}).status_code==503


def test_training_background_finite_real_samples_only(service):
    cid=bind(service.store)
    imported(service.store,cid,[event(record('heart_rate_sample',85)),event(record('exercise_session',1200,sid='sport'),eid='sport')])
    r=service.training_context('A',START,END)
    assert len(r['heart_rate_samples'])==1 and not r['interpolation'] and not r['training_completion_affected']
    assert service.training_context('B',START,END)['heart_rate_samples']==[]


def test_vendor_revoke_success_not_http_200(service):
    p=Provider(service.configs['xiaomi'],service.transport)
    calls=[]
    def handler(req):
        calls.append(parse_qs(req.content.decode()))
        return httpx.Response(200,json={'code':0})
    service.transport.client=httpx.Client(transport=httpx.MockTransport(handler))
    assert p.revoke('TEST-access')
    assert calls[0]['access_token']==['TEST-access'] and calls[0]['client_secret']==['TEST-secret']
    service.transport.client=httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'deleteResult':1})))
    assert not p.revoke('TEST-access')


def test_configs_fail_closed_for_guessed_region_header_and_callback():
    assert not load_config({})['xiaomi'].enabled
    cfg=configs()['huawei']
    assert replace(cfg,region='EU').reason()=='VENDOR_CONTRACT_REQUIRED'
    assert replace(cfg,api_version='***').reason()=='VENDOR_CONTRACT_REQUIRED'
    assert replace(cfg,redirect_uri='http://example.com/callback').reason()=='REDIRECT_URI_INVALID'


def cloud_fixture(req):
    """Exact vendor-shaped responses, never placed in real user history."""
    q=req.url.params
    if req.url.path=='/healthkit/profile/authorize':
        return httpx.Response(200,json={'authInfo':[dict(scopeId=int(s),scopeType='read') for s in SCOPES['xiaomi'].values()]})
    if req.url.path=='/healthkit/aggregate/dailies':
        day=datetime.strptime(q['startDay'],'%Y%m%d').replace(tzinfo=timezone(timedelta(hours=8)))
        ms=int(day.timestamp()*1000)
        point=dict(dataTypeName='com.xiaomi.steps.total',startTime=ms,endTime=ms+86399999,
                   value=[dict(fieldName='steps',integerValue=1234)])
        return httpx.Response(200,json=dict(group=[dict(dataSet=[dict(dataPoints=[point])])]))
    start=int(q['startTime'])
    end=int(q['endTime'])
    if req.url.path.endswith('sportRecords/all'):
        return httpx.Response(200,json={'sportRecords':[dict(startTime=start+3600000,endTime=start+4800000,
                        sportTime=1000,sportId='TEST-sport-'+str(start),sportKey='walking')]})
    kind=q['dataTypeName']
    if kind=='com.xiaomi.sleep.health':
        point=dict(dataTypeName=kind,startTime=start+1000,endTime=start+8*3600000,
            value=[dict(fieldName='bedtime',longValue=start+1000),dict(fieldName='wakeup_time',longValue=start+8*3600000),
                   dict(fieldName='all_sleep_duration',integerValue=400)])
        return httpx.Response(200,json={'healthRecords':[point]})
    key={'com.xiaomi.heart_rate.delta':'bpm','com.xiaomi.spo2.instantaneous':'spo2','com.xiaomi.weight.instantaneous':'weight'}[kind]
    point=dict(dataTypeName=kind,startTime=start+3600000,endTime=start+3600000,
               value=[dict(fieldName=key,integerValue=85 if key=='bpm' else 98 if key=='spo2' else 65)])
    return httpx.Response(200,json=dict(group=[dict(dataSet=[dict(dataPoints=[point])])]))


def test_full_cloud_sync_atomic_checkpoint_coalescing_reconcile(service):
    from datetime import timedelta
    cid=bind(service.store,scopes=list(SCOPES['xiaomi'].values())[:4])
    service.transport.client=httpx.Client(transport=httpx.MockTransport(cloud_fixture))
    jid,created=service.store.enqueue('A',cid)
    assert created and service.store.enqueue('A',cid)==(jid,False)
    service.run('A',jid)
    job=service.store.job('A',jid)
    assert job['status']=='completed',job
    assert len(service.store.records('A'))==28
    assert len(job['report']['_committed_windows'])==28
    assert all(job['report'][kind]['lookback_days']==7 for kind in list(SCOPES['xiaomi'])[:4])
    jid2,_=service.store.enqueue('A',cid);service.run('A',jid2)
    assert len(service.store.records('A'))==28
    assert all(service.store.job('A',jid2)['report'][kind]['lookback_days']==3 for kind in list(SCOPES['xiaomi'])[:4])


def test_full_cloud_sync_empty_does_not_erase_past(service):
    cid=bind(service.store,scopes=['200016'])
    service.transport.client=httpx.Client(transport=httpx.MockTransport(cloud_fixture))
    jid,_=service.store.enqueue('A',cid);service.run('A',jid)
    assert len(service.store.records('A'))==7
    service.transport.client=httpx.Client(transport=httpx.MockTransport(lambda r:cloud_fixture(r) if r.url.path.endswith('/authorize') else httpx.Response(200,json={'group':[]})))
    jid2,_=service.store.enqueue('A',cid);service.run('A',jid2)
    assert len(service.store.records('A'))==7
    r=service.store.job('A',jid2)['report']['steps_daily']
    assert r['status']=='NO_RECORDS' and r['coverage']=='empty_response_upload_state_unknown'


def test_server_disk_full_atomic_no_receipt_or_partial_facts(store,monkeypatch):
    cid=bind(store);lease=store.lease('A',cid,'TEST-install')
    original=store.db
    @contextmanager
    def limited():
        with original() as db:
            pages=db.execute('PRAGMA page_count').fetchone()[0]
            db.execute('PRAGMA max_page_count='+str(pages))
            yield db
    monkeypatch.setattr(store,'db',limited)
    large=[event(record(sid='disk-'+str(i),details={'TEST-padding':'x'*16000}),eid='disk-'+str(i)) for i in range(10)]
    with pytest.raises(HealthError,match='LOCAL_STORAGE_FULL'):imported(store,cid,large,lease=lease)
    monkeypatch.setattr(store,'db',original)
    assert store.records('A')==[]
    with pytest.raises(HealthError,match='IMPORT_BATCH_NOT_FOUND'):store.receipt('A','TEST-batch')


def test_local_disk_full_cursor_does_not_advance(tmp_path,monkeypatch):
    q=LocalOutbox(tmp_path/'q.sqlite3');scope=q.bind('A','TEST',1,'TEST-install')
    q.bootstrap_token(scope,'steps_daily','before')
    original=q.db
    @contextmanager
    def limited():
        with original() as db:
            db.execute('PRAGMA max_page_count='+str(db.execute('PRAGMA page_count').fetchone()[0]))
            yield db
    monkeypatch.setattr(q,'db',limited)
    with pytest.raises(HealthError,match='LOCAL_STORAGE_FULL'):
        q.commit_page(scope,'steps_daily',[event(record(details={'TEST-padding':'x'*20000}))],
                      expected_cursor=None,next_cursor=None,snapshot=True,complete=True)
    monkeypatch.setattr(q,'db',original)
    assert q.inspect(scope)['pending']==0 and q.inspect(scope)['cursors'][0]['phase']=='snapshot'


def test_database_version_unknown_does_not_rewrite(tmp_path):
    path=tmp_path/'unknown.sqlite3'
    with sqlite3.connect(path) as db:db.execute('PRAGMA user_version=999')
    before=path.read_bytes()
    with pytest.raises(HealthError,match='STORAGE_VERSION_UNSUPPORTED'):Store(path)
    assert path.read_bytes()==before


def test_snapshot_fact_and_job_progress_rollback_together(store):
    cid=bind(store);scopes=list(SCOPES['xiaomi'].values())
    jid,_=store.enqueue('A',cid)
    with pytest.raises(HealthError,match='STALE_SYNC_JOB'):
        store.snapshot('A',cid,1,'steps_daily','cloud',START,END,store.job('A',jid)['sequence'],[record()],scopes,job_id=jid)
    assert store.records('A')==[] and store.job('A',jid)['report']=={}


def test_two_service_start_does_not_steal_live_worker(service):
    cid=bind(service.store)
    jid,_=service.store.enqueue('A',cid)
    with service.store.db() as db:
        db.execute("UPDATE jobs SET status='running',worker_holder='OTHER-live-worker',lease_until=? WHERE id=?",(time.time()+180,jid))
    second=WearableService(service.store.path.parent,configs(),'',service.transport)
    assert second.store.job('A',jid)['status']=='running'
    second.close()


def test_http_history_receipts_owner_isolation_and_original_write_guard(client,service):
    uid=client.cookies.get('rehab_device').split('.')[0]
    cid=bind(service.store,owner=uid)
    lease=client.post('/api/health/connections/'+cid+'/upload-lease',json={'installation_id':'TEST-install'}).json()
    payload=dict(connection_id=cid,generation=1,batch_id='TEST-http-batch',lease_id=lease['lease_id'],
                 lease_token=lease['lease_token'],events=[event()])
    saved=client.post('/api/health/import-batches',json=payload)
    assert saved.status_code==200,saved.text
    assert client.get('/api/health/import-batches/TEST-http-batch').json()==saved.json()
    assert client.post('/api/health/import-batches',json=payload).json()==saved.json()
    assert len(client.get('/api/health/records').json()['records'])==1
    assert client.get('/api/health/summary').json()['days'][0]['value']==200
    with TestClient(client.app,headers=HEADERS) as other:
        other.post('/api/pair',json={'code':'TEST'})
        assert other.get('/api/health/records').json()['records']==[]
        assert other.get('/api/health/import-batches/TEST-http-batch').status_code==404
        assert other.post('/api/health/connections/'+cid+'/sync',json={}).status_code==404
    assert client.post('/api/health/connections/'+cid+'/sync',json={},headers={'X-Rehab-Client':'wrong'}).status_code==403
    assert client.delete('/api/health/upload-leases/'+lease['lease_id']).json()['cloud_connection_revoked'] is False
    assert client.post('/api/health/import-batches',json={**payload,'batch_id':'TEST-late'}).status_code==403


def test_revocation_mid_page_permission_change_no_snapshot(service):
    cid=bind(service.store,scopes=['200007'])
    service.store.snapshot('A',cid,1,'heart_rate_sample','cloud',START,END,1,[record('heart_rate_sample',80,sid=None)],['200007'])
    calls=[]
    def handler(req):
        if req.url.path.endswith('/authorize'):
            calls.append(req)
            return httpx.Response(200,json={'authInfo':[dict(scopeId=200007,scopeType='read')] if len(calls)==1 else []})
        return cloud_fixture(req)
    service.transport.client=httpx.Client(transport=httpx.MockTransport(handler))
    jid,_=service.store.enqueue('A',cid);service.run('A',jid)
    assert service.store.records('A')[0]['value']==80
    assert service.store.job('A',jid)['report']['heart_rate_sample']['status']=='SCOPE_CHANGED'


def test_sleep_overlap_no_fabricated_total(store):
    cid=bind(store)
    imported(store,cid,[event(record('sleep_session',420,sid='s1')),
                         event(record('sleep_session',430,sid='s2'),eid='s2')])
    r=store.summary('A',START,END)['days'][0]
    assert r['value'] is None and r['availability']=='OVERLAPPING_SOURCE_INTERVALS'


@pytest.mark.parametrize('kind',[[],{},None,True])
def test_malformed_kind_is_structured_error(kind):
    with pytest.raises(HealthError):normalize({**record(),'kind':kind})


def test_daily_total_suppresses_same_day_increment(store):
    cid=bind(store)
    imported(store,cid,[event(record(value=200),eid='daily'),event(record('steps_delta',value=30,sid='delta'),eid='delta')])
    days=store.summary('A',START,END)['days']
    assert len(days)==1 and days[0]['value']==200


def test_sleep_midnight_revision_replaces_only_same_source(store):
    cid=bind(store)
    first=record('sleep_session',value=420,sid='sleep')
    first.update(start_ms=START-9*3600000,end_ms=START)
    imported(store,cid,[event(first,eid='sleep-v1')])
    second=dict(first,value=450,version='2',details={'deep_sleep_duration':90})
    imported(store,cid,[event(second,eid='sleep-v2')],bid='revision')
    imported(store,cid,[event(first,eid='late-sleep-v1')],bid='late')
    rows=store.records('A',START-86400000,END,'sleep_session')
    assert len(rows)==1 and rows[0]['value']==450 and rows[0]['version']=='2'
    assert store.summary('A',START-86400000,END)['days'][0]['value']==450


def test_expired_worker_resumes_same_job_and_sequence(service,monkeypatch):
    cid=bind(service.store)
    jid,_=service.store.enqueue('A',cid)
    sequence=service.store.job('A',jid)['sequence']
    with service.store.db() as db:
        db.execute("UPDATE jobs SET status='running',worker_holder='TEST-dead',lease_until=? WHERE id=?",(time.time()-1,jid))
    submitted=[]
    monkeypatch.setattr(service.pool,'submit',lambda fn,owner,job:submitted.append(job))
    result=service.sync('A',cid)
    assert result['job_id']==jid and result['coalesced'] and submitted==[jid]
    assert service.store.job('A',jid)['sequence']==sequence
    assert service.store.job('A',jid)['worker_holder'] is None


def test_wearable_storage_failure_does_not_disable_original_catalog(tmp_path,monkeypatch):
    def failed_store(*args,**kwargs):raise OSError('TEST-unavailable-disk')
    monkeypatch.setattr('mobile_rehab.wearables.service.Store',failed_store)
    with TestClient(create_app(tmp_path,pair_key='TEST',runner=lambda item:None),headers=HEADERS) as client:
        client.post('/api/pair',json={'code':'TEST'})
        assert client.get('/api/catalog').status_code==200
        r=client.get('/api/health/capabilities')
        assert r.status_code==503 and r.json()['code']=='STORAGE_UNAVAILABLE'


@pytest.mark.parametrize('kind',[[],{},None,True])
def test_http_import_malformed_kind_returns_400(client,service,kind):
    uid=client.cookies.get('rehab_device').split('.')[0]
    cid=bind(service.store,owner=uid)
    lease=service.store.lease(uid,cid,'TEST-install')
    r=client.post('/api/health/import-batches',json=dict(connection_id=cid,generation=1,batch_id='TEST-bad-kind',
        lease_id=lease['lease_id'],lease_token=lease['lease_token'],events=[event(dict(record(),kind=kind))]))
    assert r.status_code==400 and r.json()['code']=='PAYLOAD_SCHEMA_UNSUPPORTED'
