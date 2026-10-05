"""Completion flows: real isolated domain storage, reversible actions, no user data."""
import json
import subprocess
from pathlib import Path
import wave

import pytest
from fastapi.testclient import TestClient
from mobile_rehab.server import create_app
from mobile_rehab.tests.test_health import HEADERS, profile, post


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path,pair_key='TEST',runner=lambda item:None),headers=HEADERS) as c:
        c.post('/api/pair',json={'code':'TEST'})
        profile(c)
        yield c


def test_archive_trash_restore_backup_quota_and_other_owner(client):
    result=client.post('/api/product-archive?consent=yes&name=TEST&category=其他资料',content=b'TEST document',headers={'Content-Type':'text/plain'})
    ident=result.json()['attachments'][0]['id']
    assert client.post('/api/product-archive/'+ident+'/trash',json={}).status_code==400
    assert client.post('/api/product-archive/'+ident+'/trash',json={'confirm':True}).status_code==200
    assert not client.get('/api/product').json()['snapshot']['attachments']
    assert client.get('/api/product-archive/'+ident).status_code!=200
    assert client.get('/api/product-trash').json()[0]['id']==ident
    assert any(a['id']==ident for a in client.get('/api/product-backup').json()['attachments'])
    with TestClient(client.app,headers=HEADERS) as other:
        other.post('/api/pair',json={'code':'TEST'});profile(other,'OTHER')
        assert not other.get('/api/product-trash').json()
        assert other.post('/api/product-archive/'+ident+'/restore',json={'confirm':True}).status_code!=200
    assert client.post('/api/product-archive/'+ident+'/restore',json={'confirm':True}).status_code==200
    assert not client.get('/api/product-trash').json()
    assert client.get('/api/product-archive/'+ident).content==b'TEST document'
    # Repeating an authorized action is idempotent, not a new attachment or quota bypass.
    assert client.post('/api/product-archive/'+ident+'/restore',json={'confirm':True}).status_code==200
    assert len(client.get('/api/product').json()['snapshot']['attachments'])==1


def test_rehab_context_empty_is_not_fabricated(client):
    result=client.get('/api/product-rehab').json()
    assert result['total']==0 and result['latest']==[]
    assert result['source']=='current-mobile-profile'
    assert result['next_step']['status']=='assess'
    with TestClient(client.app) as unpaired:
        assert unpaired.get('/api/product-rehab').status_code==401


def test_voice_invalid_output_fails_cleanly_and_removes_temporary_audio(client,monkeypatch):
    from mobile_rehab import voice
    handler=client.app.state.phone_voice
    monkeypatch.setattr(handler,'status',lambda:dict(available=True))
    monkeypatch.setattr(voice.subprocess,'run',lambda args,**kwargs:subprocess.CompletedProcess(args,0,b'invalid JSON',b''))
    assert client.post('/api/product-voice',content=b'TEST').status_code==502
    assert not list(handler.root.glob('asr-*'))


def test_voice_timeout_busy_and_cleanup(client,monkeypatch):
    from mobile_rehab import voice
    handler=client.app.state.phone_voice
    monkeypatch.setattr(handler,'status',lambda:dict(available=True))
    def timeout(args,**kwargs):raise subprocess.TimeoutExpired(args,90)
    monkeypatch.setattr(voice.subprocess,'run',timeout)
    assert client.post('/api/product-voice',content=b'TEST').status_code==504
    assert not list(handler.root.glob('asr-*'))
    with handler.lock:
        assert client.post('/api/product-voice',content=b'TEST').status_code==429


def test_actual_installed_voice_worker_silence(tmp_path):
    from mobile_rehab.voice import PhoneVoice
    handler=PhoneVoice(tmp_path/'voice')
    if not handler.status()['available']:pytest.skip('Optional local voice model not installed')
    path=tmp_path/'silence.wav'
    with wave.open(str(path),'wb') as audio:
        audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(16000);audio.writeframes(b'\0\0'*32000)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:handler.recognize(path.read_bytes())
    assert error.value.status_code==400
    assert not list(handler.root.glob('asr-*'))


def test_backup_restore_empty_profile_preserves_timestamp_drugs_archive_and_denies_sharing(client):
    post(client,'health.record',{'metric':'weight','value':61})
    post(client,'medication.save',{'record':{'id':'m1','name':'TEST medicine','status':'stopped'}})
    post(client,'chat',{'text':'不要记录：TEST transient'})
    response=client.post('/api/product-archive?consent=yes&name=TEST&category=其他资料',content=b'FILE',headers={'Content-Type':'text/plain'})
    ident=response.json()['attachments'][0]['id']
    client.post('/api/product-archive/'+ident+'/trash',json={'confirm':True})
    backup=client.get('/api/product-backup').json()
    stamp=backup['snapshot']['state']['healthData']['measurements'][0]['timestamp']
    assert backup['version']==2 and backup['attachments'][0]['content']=='RklMRQ=='
    assert client.post('/api/product-restore?confirm=yes',json=backup).status_code==409
    with TestClient(client.app,headers=HEADERS) as empty:
        empty.post('/api/pair',json={'code':'TEST'})
        assert empty.post('/api/product-restore',json=backup).status_code==400
        response=empty.post('/api/product-restore?confirm=yes',json=backup)
        assert response.status_code==200,response.text
        result=response.json()
        assert result['ownerId']!=backup['snapshot']['ownerId']
        assert result['state']['healthData']['measurements'][0]['timestamp']==stamp
        assert result['state']['healthData']['measurements'][0]['source']=='import'
        assert result['profile']['profile']['medicationRecords'][0]['status']=='stopped'
        assert result['profile']['profile']['familySharing']=='denied'
        assert 'TEST transient' not in json.dumps(result)
        assert empty.get('/api/product-trash').json()[0]['id']==ident
        assert empty.post('/api/product-archive/'+ident+'/restore',json={'confirm':True}).status_code==200
        assert empty.get('/api/product-archive/'+ident).content==b'FILE'
    assert client.get('/api/product-trash').json()[0]['id']==ident


def test_backup_rejects_invalid_and_keeps_profile_empty(client):
    backup=client.get('/api/product-backup').json()
    with TestClient(client.app,headers=HEADERS) as empty:
        empty.post('/api/pair',json={'code':'TEST'})
        for value in (b'{bad',json.dumps({'version':True}).encode(),json.dumps({**backup,'version':9}).encode()):
            assert empty.post('/api/product-restore?confirm=yes',content=value).status_code==400
        assert empty.get('/api/product').json()['needs_profile']


def test_actual_chinese_synthetic_recording_http_roundtrip(tmp_path):
    from mobile_rehab.core import ROOT
    from mobile_rehab.voice import PhoneVoice
    audio=ROOT/'.runtime/mobile/validation/chinese-synthetic-test.wav'
    if not audio.is_file() or not PhoneVoice(tmp_path/'probe').status()['available']:
        pytest.skip('Local optional synthetic ASR validation input absent')
    with TestClient(create_app(tmp_path,pair_key='TEST',runner=lambda item:None),headers=HEADERS) as c:
        c.post('/api/pair',json={'code':'TEST'})
        response=c.post('/api/product-voice',content=audio.read_bytes())
        assert response.status_code==200,response.text
        assert '肩' in response.json()['text'] and response.json()['automatic_send'] is False


def test_actual_local_ocr_http_and_no_health_write(client):
    from mobile_rehab.core import ROOT
    image=ROOT/'.runtime/mobile/validation/ocr-synthetic-test.png'
    if not image.is_file() or not client.app.state.document_ocr.status()['available']:
        pytest.skip('Optional local synthetic OCR validation input absent')
    result=client.post('/api/product-archive?consent=yes&name=TEST&category=体检报告',content=image.read_bytes(),headers={'Content-Type':'image/png'})
    ident=result.json()['attachments'][0]['id']
    response=client.post('/api/product-ocr/'+ident)
    assert response.status_code==200,response.text
    assert '120' in response.json()['text'] and '体重' in response.json()['text']
    assert response.json()['automatic_record'] is False
    assert not client.get('/api/product').json()['snapshot']['state']['healthData']['measurements']
    assert not list(client.app.state.document_ocr.root.glob('ocr-*'))
    with TestClient(client.app,headers=HEADERS) as other:
        other.post('/api/pair',json={'code':'TEST'});profile(other,'OTHER')
        assert other.post('/api/product-ocr/'+ident).status_code!=200


def test_ocr_unsupported_file_never_runs_inference(client,monkeypatch):
    result=client.post('/api/product-archive?consent=yes&name=TEST&category=其他资料',content=b'FILE',headers={'Content-Type':'text/plain'})
    ident=result.json()['attachments'][0]['id']
    def forbidden(*args):raise AssertionError('OCR must not execute')
    monkeypatch.setattr(client.app.state.document_ocr,'read',forbidden)
    assert client.post('/api/product-ocr/'+ident).status_code==400


def test_ocr_invalid_image_busy_unavailable(client,monkeypatch):
    from mobile_rehab import ocr
    handler=client.app.state.document_ocr
    monkeypatch.setattr(handler,'status',lambda:dict(available=True))
    monkeypatch.setattr(ocr.subprocess,'run',lambda args,**kwargs:subprocess.CompletedProcess(args,1,b'',b'BAD'))
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:handler.read(b'BAD IMAGE')
    assert error.value.status_code==400
    assert not list(handler.root.glob('ocr-*'))
    with handler.lock:
        with pytest.raises(HTTPException) as error:handler.read(b'TEST')
        assert error.value.status_code==429
    monkeypatch.setattr(handler,'status',lambda:dict(available=False))
    with pytest.raises(HTTPException) as error:handler.read(b'TEST')
    assert error.value.status_code==503


def test_chinese_chat_limit_counts_characters_and_stays_bounded(client):
    assert client.post('/api/product/chat',json={'text':'今天感觉很好。'*200}).status_code==200
    assert client.post('/api/product/chat',content=b'x'*16385).status_code==413
    assert client.post('/api/product/mobile.restore',json={}).status_code==404
