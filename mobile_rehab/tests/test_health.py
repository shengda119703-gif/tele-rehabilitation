"""Real Node domain bridge, isolated TEST data; no desktop/user data is opened."""
import json
import subprocess

import pytest
from fastapi.testclient import TestClient
from mobile_rehab.server import create_app
from mobile_rehab.product import validate
from fastapi import HTTPException

HEADERS={'X-Rehab-Client':'mobile-v1'}


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path,pair_key='TEST',runner=lambda item:None),headers=HEADERS) as c:
        c.post('/api/pair',json={'code':'TEST'})
        yield c


def post(c, op, data):
    response=c.post('/api/product/'+op,json=data)
    assert response.status_code==200,response.text
    return response.json()


def profile(c, name='TEST person'):
    return post(c,'profile.save',{'profile':{'name':name,'age':68,'conditions':[]}})


def test_auth_whitelist_and_owner_isolation(client):
    assert client.get('/api/product').json()['needs_profile']
    with TestClient(client.app,headers=HEADERS) as other:
        assert other.get('/api/product').status_code==401
        other.post('/api/pair',json={'code':'TEST'})
        profile(client)
        assert other.get('/api/product').json()['needs_profile']
    assert client.post('/api/product/lifecycle.clear',json={}).status_code==404
    assert client.post('/api/product/profile.list',json={}).status_code==404
    assert client.post('/api/product/healthkit.import',json={}).status_code==404
    assert client.post('/api/product/health.record',headers={'X-Rehab-Client':'wrong'},json={'metric':'weight','value':65}).status_code==403


def test_health_medication_profile_edits_and_tasks(client):
    profile(client)
    post(client,'health.record',{'metric':'systolic','value':123,'visibility':'family_ok'})
    post(client,'medication.save',{'record':{'id':'TEST-med','name':'医嘱药物','dose':'按既有医嘱','times':'早餐后'}})
    profile(client,'NEW name')
    snapshot=client.get('/api/product').json()['snapshot']
    assert snapshot['profile']['profile']['medicationRecords'][0]['name']=='医嘱药物'
    assert snapshot['profile']['profile']['familySharing']=='denied'
    assert snapshot['state']['healthData']['measurements'][0]['value']==123
    assert snapshot['state']['healthData']['measurements'][0]['visibility']=='private'
    tasks=snapshot['state']['tasks']
    assert any(t['kind']=='medication_check' for t in tasks)
    task=next(t for t in tasks if t['kind']=='medication_check')
    result=post(client,'task.status',{'id':task['id'],'status':'completed'})
    assert next(t for t in result['state']['tasks'] if t['id']==task['id'])['status']=='completed'
    post(client,'medication.status',{'id':'TEST-med','status':'stopped'})
    assert client.get('/api/product').json()['snapshot']['profile']['profile']['medicationRecords'][0]['status']=='stopped'


def test_chat_private_not_in_backup_or_restart(client):
    profile(client)
    marker='TEST-private-secret-1025'
    result=post(client,'chat',{'text':marker,'private':True})
    assert any(marker in m['text'] for m in result['snapshot']['state']['chat'])
    assert marker not in client.get('/api/product-backup').text
    client.app.state.product.close()
    assert marker not in json.dumps(client.get('/api/product').json())


def test_archive_roundtrip_private_and_foreign_download(client):
    profile(client)
    assert client.post('/api/product-archive?name=TEST&category=其他资料',content=b'hello',headers={'Content-Type':'text/plain'}).status_code==400
    result=client.post('/api/product-archive?consent=yes&name=TEST&category=其他资料',content=b'hello',headers={'Content-Type':'text/plain'})
    assert result.status_code==200,result.text
    entry=result.json()['attachments'][0]
    assert entry['visibility']=='private'
    response=client.get('/api/product-archive/'+entry['id'])
    assert response.content==b'hello'
    assert 'attachment' in response.headers['content-disposition']
    with TestClient(client.app,headers=HEADERS) as other:
        other.post('/api/pair',json={'code':'TEST'})
        profile(other,'OTHER person')
        assert other.get('/api/product-archive/'+entry['id']).status_code!=200
    assert client.post('/api/product-archive?consent=yes&name=TEST',content=b'<script/>',headers={'Content-Type':'text/html'}).status_code==400
    assert client.post('/api/product-archive?consent=yes&name=TEST',content=b'x'*(8*1024*1024+1),headers={'Content-Type':'text/plain'}).status_code==413


def test_share_minimal_snapshot_revoke_and_no_private_leak(client):
    profile(client)
    post(client,'health.record',{'metric':'weight','value':66})
    post(client,'medication.save',{'record':{'id':'m','name':'TEST medication'}})
    post(client,'chat',{'text':'TEST chat secret','private':True})
    assert client.post('/api/product-share',json={}).status_code==400
    share=client.post('/api/product-share',json={'consent':True}).json()
    report=client.post('/api/care/view',json={'code':share['code']}).json()['report']
    assert report['health']['measurements'][0]['value']==66
    assert report['health']['medications'][0]['name']=='TEST medication'
    for private in ('TEST chat secret','familyPhone','attachments','ownerId'):
        assert private not in json.dumps(report)
    post(client,'health.record',{'metric':'weight','value':67})
    assert client.post('/api/care/view',json={'code':share['code']}).json()['report']['health']['measurements'][0]['value']==66
    assert client.delete('/api/care/shares/'+share['id']).status_code==200
    assert client.post('/api/care/view',json={'code':share['code']}).status_code==404


@pytest.mark.parametrize('operation,value',[
    ('profile.save',{'profile':{'name':'test','age':True}}),
    ('health.record',{'metric':'weight','value':True}),
    ('health.record',{'metric':'unknown','value':20}),
    ('chat',{'text':' '}),('chat',{'text':'x'*1901}),
    ('task.status',{'id':'test','status':'invalid'}),
    ('medication.save',{'record':{'id':'test','name':''}}),
])
def test_validation(operation,value):
    with pytest.raises(HTTPException):validate(operation,value)


def test_voice_unavailable_no_desktop_microphone(client,monkeypatch):
    monkeypatch.setattr(client.app.state.phone_voice,'status',lambda:dict(available=False))
    assert not client.get('/api/product-voice').json()['available']
    assert client.post('/api/product-voice',content=b'TEST').status_code==503


def test_voice_upload_bounded_editable_and_temp_cleanup(client,monkeypatch):
    from mobile_rehab import voice
    handler=client.app.state.phone_voice
    monkeypatch.setattr(handler,'status',lambda:dict(available=True))
    seen=[]
    def worker(args,**kwargs):
        from pathlib import Path
        seen.append(Path(args[-2]));assert seen[-1].read_bytes()==b'TEST'
        return subprocess.CompletedProcess(args,0,json.dumps({'text':'测试录音'}).encode(),b'')
    monkeypatch.setattr(voice.subprocess,'run',worker)
    result=client.post('/api/product-voice',content=b'TEST').json()
    assert result=={'text':'测试录音','automatic_send':False}
    assert seen and not seen[0].exists()
    assert client.post('/api/product-voice',content=b'x'*(8*1024*1024+1)).status_code==413
    assert client.post('/api/product-voice',content=b'').status_code==400
