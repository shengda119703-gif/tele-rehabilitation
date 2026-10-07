"""Real TEST-only fixture integration; no patient or hardware accuracy claim."""
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'rehab_codex_single_camera_v2_1'), str(ROOT), str(Path(__file__).parent)]

from test_lin_profile import OWNER, NAME, FAMILY, MARKER, FixtureClock, claim_directory, scope, seed
from app.product.backend import ProductBackend
from app.storage import Storage
from mobile_rehab.server import create_app
from mobile_rehab.unified import SharedProduct


@pytest.fixture(scope='module')
def complete(tmp_path_factory):
    import os
    old = {k:os.environ.get(k) for k in ('ANKANG_PRODUCT_DISABLE_MODEL','ANKANG_VOICE_DISABLED')}
    os.environ.update(ANKANG_PRODUCT_DISABLE_MODEL='1', ANKANG_VOICE_DISABLED='1')
    workspace = tmp_path_factory.mktemp('test-lin')
    data = workspace/'qa-output'/'lin'
    claim_directory(data, workspace=workspace)
    clock = FixtureClock()
    backend = ProductBackend(data/'desktop', bridge_factory=lambda:clock.bridge(data))
    try:
        manifest = seed(backend, data, clock, workspace=workspace)
        yield data, workspace, backend, clock, manifest
    finally:
        backend.close()
        for key,value in old.items():
            if value is None:
                os.environ.pop(key,None)
            else:
                os.environ[key]=value


def test_guards_refuse_production_unmarked_root_and_foreign_identity(tmp_path):
    for path in (tmp_path, tmp_path/'data', tmp_path/'qa-output'):
        with pytest.raises(ValueError):
            claim_directory(path, workspace=tmp_path)
    path=tmp_path/'qa-output'/'occupied'
    path.mkdir(parents=True)
    (path/'keep.txt').write_text('unchanged')
    with pytest.raises(ValueError):
        claim_directory(path, workspace=tmp_path)
    assert (path/'keep.txt').read_text()=='unchanged'
    path=tmp_path/'qa-output'/'foreign'
    path.mkdir()
    (path/MARKER).write_text(json.dumps(dict(owner='real-person',name='林女士',complete=True)))
    with pytest.raises(ValueError):
        claim_directory(path, workspace=tmp_path)


def test_incomplete_initialization_is_preserved_not_retried_over_data(tmp_path):
    path=tmp_path/'qa-output'/'incomplete'
    value=claim_directory(path,workspace=tmp_path)
    assert value['complete'] is False
    with pytest.raises(ValueError,match='初始化未完成'):
        claim_directory(path,workspace=tmp_path)


def test_seed_cannot_bypass_directory_or_writer_guard(complete):
    data,workspace,b,clock,manifest=complete
    with pytest.raises(ValueError):
        seed(b,workspace/'data',clock,workspace=workspace)
    other=workspace/'qa-output'/'other'
    other.mkdir()
    (other/MARKER).write_text(json.dumps(manifest),encoding='utf-8')
    with pytest.raises(ValueError,match='写入器'):
        seed(b,other,clock,workspace=workspace)


def test_profile_health_medication_chat_archive_family(complete):
    data,workspace,b,clock,manifest=complete
    s=b.call('snapshot',OWNER,scope=scope('LIVE_CAMERA'))
    p=s['profile']
    assert p['dataMode']=='demo' and p['profile']['name']==NAME
    assert p['profile']['sex']=='female' and p['profile']['cognition']=='stable'
    assert p['rehabGoal'] and p['currentState']
    assert len(p['profile']['medicationRecords'])==3
    measurements=s['state']['healthData']['measurements']
    assert len(measurements)==140 and len({m['metric'] for m in measurements})==10
    assert all(m['source']=='demo' and m['metadata']['synthetic'] for m in measurements)
    assert len({m['timestamp'][:10] for m in measurements})==14
    assert len(s['state']['chat'])>=8
    assert s['history']['report']['sections']
    assert len(s['attachments'])==3
    for a in s['attachments']:
        text=bytes(b.call('archive.read',OWNER,dict(id=a['id']))['bytes']).decode('utf-8')
        assert NAME in text
    daily=s['dailyProduct']
    assert len(daily['medSchedules'])==2 and len(daily['doses'])>=26
    assert len(daily['doseAudit'])==len(daily['doses'])
    assert daily['grants'][FAMILY] and s['familyMembers'][0]['categories']==['health']
    assert s['familyMembers'][0]['name'].startswith('TEST ')
    assert clock.at is None


def test_source_separation_evidence_and_training_progress(complete):
    data,workspace,b,clock,manifest=complete
    store=Storage(data/'desktop'/'home_rehab.sqlite3',readonly=True)
    try:
        sessions=store.list_sessions()
        assert len(sessions)==40
        assert all(s['participant_id']==OWNER and s['synthetic'] for s in sessions)
        assert all(s['model_manifest_id']=='fixture-geometry' for s in sessions)
        for source in ('LIVE_CAMERA','REPLAY_FILE'):
            s=b.call('snapshot',OWNER,scope=scope(source))['rehabilitation_ui']
            assert len(s['rehab.get_recent_assessments']['records'])==18
            assert len(s['rehab.get_training_history']['records'])==2
            plan=s['rehab.get_training_plan']['records'][0]
            assert plan['record_origin']=='assessment_rules'
            assert plan['progress']['completed']==2 and plan['progress']['total']==4
            assert plan['next_available'] and not plan['progress']['blocked']
            assert all(r['quality']['observed_goals_met']==5 for r in plan['progress']['items'] if r['done'])
            assert len(b.daily.snapshot(OWNER,scope(source))['schedules'])==4
    finally:
        store.close()


def test_normal_phone_routes_and_report_readers(complete):
    data,workspace,b,clock,manifest=complete
    app=create_app(data/'phone','test-code',shared=SharedProduct(b,OWNER))
    with TestClient(app,headers={'X-Rehab-Client':'mobile-v1'}) as c:
        assert c.get('/api/unified').status_code==401
        assert c.post('/api/pair',json={'code':'test-code'}).status_code==200
        assert c.get('/api/unified').json()['snapshot']['profile']['profile']['name']==NAME
        jobs=c.get('/api/jobs').json()
        assert len(jobs)==24
        assert all(j['synthetic'] and not j['video_available'] for j in jobs)
        body=c.get('/api/body').json()
        assert body['training_count']==2 and body['total']==24
        assert body['next_step']['status']=='continue'
        plan=c.get('/api/plan').json()
        assert plan['progress']['completed']==2 and not plan['progress']['blocked']
        for row in jobs:
            result=c.get('/api/jobs/'+row['id']).json()['result']
            assert result['synthetic']
            if row['mode']=='fitness':
                assert result['summary']['completed'] in (6,8) and result['series']
                if row['exercise']=='fitness_squat':
                    metrics=result['summary']['metrics']
                    assert metrics['torso']['max']<=30
                    assert metrics['hip']['max']-metrics['hip']['min']>10
            elif row['mode']=='posture':
                assert result['summary']['valid_metrics']==3
        assert c.get('/api/catalog').json()['network_camera']['connected'] is False


def test_restart_is_idempotent_and_preserves_new_usage(complete):
    data,workspace,b,clock,manifest=complete
    before=len(b.call('snapshot',OWNER)['state']['healthData']['measurements'])
    b.call('health.record',OWNER,dict(metric='weight',value=61.9,visibility='private'))
    same=claim_directory(data,workspace=workspace)
    assert same==manifest and seed(b,data,clock,workspace=workspace)==manifest
    assert len(b.call('snapshot',OWNER)['state']['healthData']['measurements'])==before+1
    other=ProductBackend(data/'desktop')
    try:
        assert seed(other,data,FixtureClock(),workspace=workspace)==manifest
        assert len(other.call('snapshot',OWNER)['state']['healthData']['measurements'])==before+1
    finally:
        other.close()
