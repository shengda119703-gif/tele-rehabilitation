from uuid import uuid4
from fastapi.testclient import TestClient
from mobile_rehab.phone_cloud import create_cloud

def enroll(c):
    r=c.post('/v1/enroll',json={'code':'TEST','client_id':str(uuid4())})
    assert r.status_code==200
    return r.json(),{'Authorization':'Bearer '+r.json()['token']}

def test_device_identity_default_private_grants_revocation_and_owner_binding(tmp_path):
    with TestClient(create_cloud(tmp_path,'TEST')) as c:
        a,ah=enroll(c);b,bh=enroll(c)
        assert c.get('/v1/family').status_code==401
        assert c.put('/v1/summary',headers=ah,json={'name':'TEST A','health':[{'text':'TEST shareable weight','timestamp':'2026-10-07'}],'rehab':[],'doses':[]}).status_code==200
        assert c.put('/v1/summary',headers=ah,json={'name':'TEST','chat':'secret','health':[],'rehab':[],'doses':[]}).status_code==400
        code=c.post('/v1/family/invite',headers=ah,json={}).json()['code']
        assert c.post('/v1/family/bind',headers=bh,json={'code':code}).status_code==200
        assert c.post('/v1/family/bind',headers=bh,json={'code':code}).status_code==400
        m=c.get('/v1/family',headers=bh).json()['familyMembers'][0]
        assert m['health']==[] and m['categories']==[]
        assert c.post('/v1/family/grant',headers=ah,json={'member':b['owner'],'categories':['health']}).status_code==200
        assert c.get('/v1/family',headers=bh).json()['familyMembers'][0]['health'][0]['text']=='TEST shareable weight'
        assert c.post('/v1/family/grant',headers=bh,json={'member':str(uuid4()),'categories':['health']}).status_code==404
        assert c.post('/v1/family/grant',headers=ah,json={'member':b['owner'],'categories':[]}).status_code==200
        assert c.get('/v1/family',headers=bh).json()['familyMembers'][0]['health']==[]
        c.post('/v1/family/unbind',headers=ah,json={'member':b['owner']})
        assert c.get('/v1/family',headers=bh).json()['familyMembers']==[]

def test_backup_consent_isolation_idempotency_conflicts_and_restart(tmp_path):
    app=create_cloud(tmp_path,'TEST')
    with TestClient(app) as c:
        a,ah=enroll(c);b,bh=enroll(c)
        body={'consent':True,'revision':0,'document':{'kind':'ankang-phone-backup','version':2,'data':{'TEST':'PRIVATE'}}}
        assert c.put('/v1/backup',headers=ah,json={**body,'consent':False}).status_code==400
        assert c.put('/v1/backup',headers=ah,json=body).json()['revision']==1
        assert c.put('/v1/backup',headers=ah,json=body).json()['idempotent']
        assert c.get('/v1/backup',headers=bh).status_code==404
        body['document']['data']['TEST']='NEW'
        assert c.put('/v1/backup',headers=ah,json=body).status_code==409
    with TestClient(create_cloud(tmp_path,'TEST')) as c:
        assert c.get('/v1/backup',headers=ah).json()['document']['data']['TEST']=='PRIVATE'
        assert c.delete('/v1/device',headers=ah).status_code==200
        assert c.get('/v1/backup',headers=ah).status_code==401

def test_enrollment_limits_and_body_validation(tmp_path):
    with TestClient(create_cloud(tmp_path,'TEST')) as c:
        for _ in range(20):assert c.post('/v1/enroll',json={'code':'wrong','client_id':str(uuid4())}).status_code==401
        assert c.post('/v1/enroll',json={'code':'TEST','client_id':str(uuid4())}).status_code==429
    with TestClient(create_cloud(tmp_path/'other','TEST')) as c:
        assert c.post('/v1/enroll',content=b'x'*1025).status_code==413
        assert c.post('/v1/enroll',json={'code':'TEST','client_id':'../../bad'}).status_code==400
