"""New flows use isolated TEST directories, never existing user records."""
from io import BytesIO
import json
import time

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image

from mobile_rehab.server import create_app, save
from mobile_rehab.care import CareStore
from mobile_rehab.network import NetworkCameras, validate_url
from mobile_rehab.live import LiveManager

HEADERS = {'X-Rehab-Client':'mobile-v1'}


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path, pair_key='test-key', runner=lambda item: None)
    with TestClient(app, headers=HEADERS) as client:
        client.post('/api/pair', json={'code':'test-key'})
        yield client


def uid(client):
    return client.cookies['rehab_device'].split('.')[0]


def record(client, mode='assessment', **changes):
    jobs = client.app.state.jobs
    item = jobs.reserve(uid(client),'shoulder_abduction','left')
    save(jobs.folder(item)/'result.json',dict(summary=dict(completed=3,plan_completed=True)))
    jobs.update(item['id'],state='done',mode=mode,**changes)
    return item['id']


def test_device_link_is_one_time_and_shared_profile_not_merge(client):
    jid = record(client)
    code = client.post('/api/account/link-code').json()['code']
    cookie = client.cookies['rehab_device']
    client.cookies.clear()
    client.post('/api/pair',json={'code':'test-key'})
    assert client.get('/api/jobs').json()==[]
    assert client.post('/api/account/link',json={'code':code}).status_code==400
    assert client.post('/api/account/link',json={'code':code,'confirm_switch':True}).status_code==200
    assert client.cookies['rehab_device']==cookie
    assert client.get('/api/jobs/'+jid).status_code==200
    assert client.post('/api/account/link',json={'code':code,'confirm_switch':True}).status_code==404


def test_link_expiry_supersession_hash_and_busy(client):
    first=client.post('/api/account/link-code').json()['code']
    second=client.post('/api/account/link-code').json()['code']
    assert client.post('/api/account/link',json={'code':first,'confirm_switch':True}).status_code==404
    store=client.app.state.care
    with store.connect() as db:
        assert not db.execute('SELECT digest FROM capabilities WHERE digest=?',(second,)).fetchone()
        db.execute('UPDATE capabilities SET expires=0')
    assert client.post('/api/account/link',json={'code':second,'confirm_switch':True}).status_code==404
    third=client.post('/api/account/link-code').json()['code']
    client.app.state.jobs.reserve(uid(client),'neck_flexion','left')
    assert client.post('/api/account/link',json={'code':third,'confirm_switch':True}).status_code==409


def test_share_requires_consent_no_video_snapshot_revoke_and_owner_isolation(client):
    assert client.post('/api/care/shares',json={'consent':True}).status_code==400
    record(client)
    assert client.post('/api/care/shares',json={}).status_code==400
    share=client.post('/api/care/shares',json={'consent':True}).json()
    other = TestClient(client.app,headers=HEADERS)
    try:
        view=other.post('/api/care/view',json={'code':share['code']})
        assert view.status_code==200 and view.json()['snapshot'] is True
        text=view.text
        assert 'video' not in text and uid(client) not in text
        assert other.post('/api/care/note',json={'code':share['code'],'author':'家人','text':'已查看'}).status_code==200
        other.post('/api/pair',json={'code':'test-key'})
        assert other.delete('/api/care/shares/'+share['id']).status_code==404
    finally:
        other.close()
    assert client.get('/api/care/shares').json()[0]['notes'][0]['text']=='已查看'
    record(client)
    assert len(client.post('/api/care/view',json={'code':share['code']}).json()['report']['records'])==1
    assert client.delete('/api/care/shares/'+share['id']).status_code==200
    assert client.post('/api/care/view',json={'code':share['code']}).status_code==404
    assert client.post('/api/care/note',json={'code':share['code'],'author':'家人','text':'已查看'}).status_code==404


def test_followup_pain_not_completion_alone(client):
    assert client.get('/api/body').json()['next_step']['status']=='assess'
    jid=record(client,'training')
    assert client.get('/api/body').json()['next_step']['status']=='feedback'
    client.app.state.jobs.update(jid,feedback=dict(pain=2,fatigue=1))
    assert client.get('/api/body').json()['next_step']['status']=='rest'
    client.app.state.jobs.update(jid,feedback=dict(pain=0,fatigue=1))
    assert client.get('/api/body').json()['next_step']['status']=='continue'


def test_posture_upload_separate_from_rehab_plan(client):
    jobs=client.app.state.jobs
    jobs.runner=lambda item:save(jobs.folder(item)/'result.json',dict(kind='posture',summary=dict(valid_metrics=0)))
    response=client.post('/api/jobs?mode=posture&exercise=posture_front&side=left&consent=yes',
                         content=b'x'*40,headers={'Content-Type':'video/mp4'})
    assert response.status_code==200
    for _ in range(100):
        result=client.get('/api/jobs/'+response.json()['id']).json()
        if result['state']=='done':break
        time.sleep(.01)
    assert result['result']['kind']=='posture'
    assert client.get('/api/plan').json()['proposal']['candidates']==[]
    assert len(client.get('/api/catalog').json()['posture'])==2


@pytest.mark.parametrize('url',['http://192.168.1.20/x','rtsp://127.0.0.1/x','rtsp://169.254.169.254/x',
                               'rtsp://example.com/x','rtsp://8.8.8.8/x','file:///secret','rtsp://[::1]/x'])
def test_network_camera_rejects_unapproved_address_types(url):
    with pytest.raises(ValueError):validate_url(url)


def test_network_names_only_and_recording_owner(client):
    jobs=client.app.state.jobs
    assert client.get('/api/cameras').json()==[]
    save(jobs.cameras.config,[dict(id='front',name='客厅机位',url='rtsp://name:secret@192.168.1.20/stream')])
    result=client.get('/api/cameras')
    assert result.json()==[dict(id='front',name='客厅机位')]
    assert 'secret' not in result.text
    assert client.post('/api/cameras/front/record',json={}).status_code==400
    # Do not touch a real network in tests.
    jobs.runner=lambda item:save(jobs.folder(item)/'result.json',dict(summary={}))
    response=client.post('/api/cameras/front/record',json=dict(exercise='shoulder_abduction',side='left',seconds=10,consent=True))
    assert response.status_code==200
    item=jobs.get(response.json()['id'],uid(client))
    assert item['capture_source']=='NETWORK_CAMERA'


def test_live_api_ownership_and_validation_without_camera(client):
    assert client.post('/api/live',json={}).status_code==400
    assert client.delete('/api/live/not-real').status_code==404
    assert client.post('/api/live/not-real/frame',content=b'x'*600000).status_code==413
    assert client.post('/api/live/not-real/frame',content=b'bad').status_code==400


def fake_live_worker(pipe, exercise, side):
    while pipe.poll(3):
        value=pipe.recv()
        if value is None:break
        pipe.send(dict(ok=True,data=dict(seq=value[0],elapsed_s=value[1])))


def jpeg():
    output=BytesIO()
    Image.new('RGB',(64,64)).save(output,format='JPEG')
    return output.getvalue()


def test_live_bounded_process_and_no_cross_owner():
    manager=LiveManager(target=fake_live_worker)
    try:
        session=manager.start('owner','shoulder_abduction','left')
        with pytest.raises(HTTPException):manager.start('other','shoulder_abduction','left')
        with pytest.raises(HTTPException):manager.frame('other',session['id'],jpeg())
        assert manager.frame('owner',session['id'],jpeg())['seq']==1
        process=manager.session['process']
        manager.stop('owner',session['id'])
        assert not process.is_alive()
    finally:manager.close()


def test_host_header_allowlist(client,monkeypatch):
    monkeypatch.setenv('REHAB_ALLOWED_HOSTS','testserver')
    assert client.get('/api/health',headers={'Host':'evil.example'}).status_code==400
    assert client.get('/api/health').status_code==200


def test_real_local_model_live_empty_frame_no_false_counts():
    """Real local model + IPC on generated blank pixels, NOT a human/camera test."""
    manager=LiveManager()
    try:
        session=manager.start('test-only','shoulder_abduction','left')
        data=manager.frame('test-only',session['id'],jpeg())
        assert data['summary']['completed']==0
        assert data['valid'] is False and data['points']==[]
        assert data['cue']['instruction']
    finally:manager.close()
