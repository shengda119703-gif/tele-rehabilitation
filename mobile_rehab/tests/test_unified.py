"""Real bridge/shared storage integration, not a mock of the phone UI."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import hashlib
import hmac
import json
import time

import pytest
from fastapi.testclient import TestClient
from mobile_rehab.server import create_app
from mobile_rehab.unified import SharedProduct
from app.product.backend import ProductBackend
from app.ui.product_dialogs import blank_health


@pytest.fixture
def shared(tmp_path, monkeypatch):
    monkeypatch.setenv('ANKANG_PRODUCT_DISABLE_MODEL', '1')
    monkeypatch.setenv('ANKANG_VOICE_DISABLED', '1')
    backend = ProductBackend(tmp_path/'desktop')
    for owner in ('owner-a', 'owner-b'):
        backend.call('profile.save', owner, {'profile': blank_health('TEST '+owner)})
    adapter = SharedProduct(backend, 'owner-a')
    def runner(item):
        (app.state.jobs.folder(item)/'result.json').write_text('{"test":true}')
    app = create_app(tmp_path/'phone', 'test-code', runner, shared=adapter)
    try:
        with TestClient(app) as client:
            client.headers['X-Rehab-Client'] = 'mobile-v1'
            yield backend, adapter, app, client
    finally:
        backend.close()


def pair(client):
    assert client.post('/api/pair', json={'code': 'test-code'}).status_code == 200


def test_pairing_is_owner_bound_and_csrf_guarded(shared):
    backend, adapter, app, c = shared
    assert c.get('/api/unified').status_code == 401
    pair(c)
    assert c.get('/api/unified').json()['snapshot']['profile']['ownerId'] == 'owner-a'
    uid = 'b'*32
    signature = hmac.new(b'test-code', uid.encode(), hashlib.sha256).hexdigest()
    c.cookies.clear();c.cookies.set('rehab_device', uid+'.'+signature)
    assert c.get('/api/unified').status_code == 401
    c.cookies.clear();pair(c)
    c.headers.pop('X-Rehab-Client')
    assert c.post('/api/product/chat',json={'text':'你好'}).status_code == 403


def test_phone_and_desktop_use_one_writer_and_per_dose_history(shared):
    backend, adapter, app, c = shared
    pair(c)
    med = dict(id='med-test', name='TEST 药物', dose='按既有医嘱', status='active')
    assert c.post('/api/product/medication.save', json={'record':med}).status_code == 200
    assert backend.call('snapshot','owner-a')['profile']['profile']['medicationRecords'][0]['id'] == 'med-test'
    day = date.today().isoformat()
    assert c.post('/api/unified/daily.medSchedule',json=dict(medId='med-test',times=['08:00','20:00'],start=day,end='')).status_code == 200
    for status in ('taken','skipped','unrecorded'):
        assert c.post('/api/unified/daily.dose',json=dict(medId='med-test',date=day,time='08:00',status=status)).status_code == 200
    with ThreadPoolExecutor(2) as pool:
        futures=[pool.submit(backend.call,'health.record','owner-a',dict(metric='weight',value=v,visibility='private')) for v in (60,61)]
        for f in futures:f.result()
    s=c.get('/api/unified').json()['snapshot']
    assert len(s['dailyProduct']['doseAudit']) == 3
    assert s['dailyProduct']['doses']['med-test|'+day+'|08:00']['status']=='unrecorded'
    assert [m['value'] for m in s['state']['healthData']['measurements'] if m['metric']=='weight'] == [60,61]
    assert not backend.call('snapshot','owner-b')['profile']['profile'].get('medicationRecords')
    assert backend.results.empty(), 'phone replies must never be consumed by the Qt poller'


def test_family_defaults_private_and_cannot_edit_another_person(shared):
    backend, adapter, app, c = shared
    pair(c)
    code=backend.call('daily.familyInvite','owner-b')['code']
    assert c.post('/api/unified/daily.familyBind',json={'code':code}).status_code == 200
    view=c.get('/api/unified').json()['snapshot']['familyMembers'][0]
    assert view['categories']==[] and 'health' not in view
    assert c.post('/api/unified/daily.familyGrant',json={'member':'owner-b','categories':['health'],'owner':'owner-b'}).status_code==400
    assert c.post('/api/unified/lifecycle.clear',json={'confirmOwner':'owner-b'}).status_code==404
    assert c.post('/api/product/profile.save',json={'ownerId':'owner-b','profile':{'name':'TEST renamed','age':30}}).status_code==200
    assert backend.call('snapshot','owner-b')['profile']['profile']['name']=='TEST owner-b'


def test_phone_upload_uses_trusted_shared_database_without_exposing_path(shared):
    backend, adapter, app, c = shared
    pair(c)
    r=c.post('/api/jobs?exercise=shoulder_abduction&side=left&consent=yes', content=b'x'*64,
             headers={'Content-Type':'video/mp4'})
    assert r.status_code==200, r.text
    job=list(app.state.jobs.items.values())[0]
    assert job['participant_id']=='owner-a'
    assert job['shared_database']==str(backend.data_dir/'home_rehab.sqlite3')
    result=c.get('/api/jobs').json()
    assert 'shared_database' not in result[0] and 'participant_id' not in result[0]


def test_routes_and_reload_preserve_shared_data(shared):
    backend, adapter, app, c = shared
    pair(c)
    assert 'unified.js' in c.get('/').text
    assert 'app.js' in c.get('/capture').text
    assert c.get('/api/unified?source=SYNTHETIC').status_code==400
    assert c.post('/api/unified/daily.schedule',json={'kind':'assessment','date':date.today().isoformat(),'time':'09:00','name':'TEST 评估'}).status_code==200
    assert backend.daily.snapshot('owner-a',adapter.scope())['schedules'][0]['name']=='TEST 评估'
    assert c.get('/api/unified?source=REPLAY_FILE').json()['snapshot']['dailyProduct']['schedules']==[]


def test_real_blank_video_saves_under_desktop_owner_and_keeps_source(shared, tmp_path):
    import cv2
    import numpy as np
    from app.storage import Storage
    from app.assessment import session_value
    backend, adapter, app, c = shared
    pair(c)
    video=tmp_path/'blank.mp4'
    writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'mp4v'),10.,(320,240))
    assert writer.isOpened()
    for _ in range(20):writer.write(np.zeros((240,320,3),dtype=np.uint8))
    writer.release()
    app.state.jobs.runner=app.state.jobs.run
    r=c.post('/api/jobs?exercise=shoulder_abduction&side=left&consent=yes',content=video.read_bytes(),headers={'Content-Type':'video/mp4'})
    assert r.status_code==200,r.text
    ident=r.json()['id']
    deadline=time.monotonic()+60
    while time.monotonic()<deadline:
        job=c.get('/api/jobs/'+ident).json()
        if job['state'] in ('done','failed'):break
        time.sleep(.1)
    assert job['state']=='done',job
    store=Storage(backend.data_dir/'home_rehab.sqlite3')
    try:
        saved=store.get_session(job['result']['session_id'])
        assert session_value(saved,'participant_id')=='owner-a'
        assert session_value(saved,'source_kind')=='REPLAY_FILE'
        assert saved['summary']['completed']==0
    finally:store.close()
    s=c.get('/api/unified?source=REPLAY_FILE').json()['snapshot']
    assert s['rehabilitation_ui']['rehab.get_recent_assessments']['records']
    live=c.get('/api/unified').json()['snapshot']
    assert not live['rehabilitation_ui']['rehab.get_recent_assessments']['records']
    assert live['phoneRehabilitation']['rehab.get_recent_assessments']['records']


def test_stop_revokes_phone_without_stopping_desktop(shared):
    backend, adapter, app, c = shared
    pair(c);adapter.close()
    assert c.get('/api/unified').status_code==401
    assert c.post('/api/product/chat',json={'text':'你好'}).status_code==401
    assert backend.call('snapshot','owner-a')['profile']['ownerId']=='owner-a'
