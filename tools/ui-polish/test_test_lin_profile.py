"""Real TEST-only fixture integration; no patient or hardware accuracy claim."""
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'rehab_codex_single_camera_v2_1'), str(ROOT), str(Path(__file__).parent)]

from test_lin_profile import (OWNER, NAME, FAMILY, MARKER, SCHEMA, PROVENANCE, FITNESS_IDS,
    FixtureClock, claim_directory, scope, seed, _fitness_load_report, refresh_fitness_load)
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
                bar = result['barbell']
                assert result['participant_name']==NAME and bar['participant_name']==NAME
                assert bar['synthetic'] and bar['fixture']==SCHEMA
                assert bar['source']=='SYNTHETIC / TEST' and bar['calibration']['mass_kg']==20.
                assert bar['summary']['bounded_segments']==result['summary']['completed']
                assert bar['summary']['peak_velocity_m_s']>0 and bar['summary']['peak_power_w']>0
                assert not any(word in json.dumps(result,ensure_ascii=False) for word in ('模拟','估算','示例'))
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


def _legacy_fixture(tmp_path, complete):
    """Only generated TEST reports copied to a separate temporary QA directory."""
    import hashlib
    from types import SimpleNamespace
    source,_,_,_,manifest=complete
    data=tmp_path/'qa-output'/'legacy'
    data.mkdir(parents=True)
    (data/MARKER).write_text(json.dumps(manifest),encoding='utf-8')
    uid=hashlib.sha256(OWNER.encode()).hexdigest()[:32]
    paths=[]
    for eid in FITNESS_IDS:
        sid=hashlib.sha256((SCHEMA+eid).encode()).hexdigest()[:32]
        folder=data/'phone'/'jobs'/uid/sid
        folder.mkdir(parents=True)
        original=source/'phone'/'jobs'/uid/sid
        (folder/'job.json').write_bytes((original/'job.json').read_bytes())
        result=json.loads((original/'result.json').read_text(encoding='utf-8'))
        result['barbell']=None
        result.pop('participant_name')
        (folder/'result.json').write_text(json.dumps(result),encoding='utf-8')
        paths.append(folder)
    backend=SimpleNamespace(data_dir=data/'desktop',call=lambda *a,**kw:[
        dict(ownerId=OWNER,dataMode='demo',profile=dict(name=NAME))])
    return data,backend,paths


def test_load_upgrade_preserves_history_and_is_backed_up_idempotent(tmp_path,complete):
    data,b,paths=_legacy_fixture(tmp_path,complete)
    originals=[json.loads((p/'result.json').read_text(encoding='utf-8')) for p in paths]
    jobs=[(p/'job.json').read_bytes() for p in paths]
    changed=refresh_fitness_load(b,data,workspace=tmp_path)
    assert len(changed)==2 and all(r['changed'] for r in changed)
    for p,old,job in zip(paths,originals,jobs):
        result=json.loads((p/'result.json').read_text(encoding='utf-8'))
        assert (p/'job.json').read_bytes()==job
        assert json.loads((p/'result.before-load-v1.json').read_text(encoding='utf-8'))==old
        assert {k:v for k,v in result.items() if k not in ('barbell','participant_name')}=={
            k:v for k,v in old.items() if k!='barbell'}
    before=[(p/'result.json').read_bytes() for p in paths]
    assert not any(r['changed'] for r in refresh_fitness_load(b,data,workspace=tmp_path))
    assert before==[(p/'result.json').read_bytes() for p in paths]
    assert len(list((data/'phone'/'jobs').glob('*/*/job.json')))==2


@pytest.mark.parametrize('problem',['foreign_job','foreign_result','changed_bar','backup','identity','writer'])
def test_load_upgrade_validates_all_targets_before_writing(tmp_path,complete,problem):
    data,b,paths=_legacy_fixture(tmp_path,complete)
    path=paths[1]/('job.json' if problem=='foreign_job' else 'result.json')
    value=json.loads(path.read_text(encoding='utf-8'))
    if problem=='foreign_job': value['owner']='real-person'
    if problem=='foreign_result': value['synthetic']=False
    if problem=='changed_bar': value['barbell']={'synthetic':False}
    if problem=='backup': (paths[1]/'result.before-load-v1.json').write_text('{}')
    if problem=='identity': b.call=lambda *a,**kw:[]
    if problem=='writer': b.data_dir=data/'wrong-desktop'
    path.write_text(json.dumps(value),encoding='utf-8')
    before=[(p/'result.json').read_bytes() for p in paths]
    with pytest.raises(ValueError): refresh_fitness_load(b,data,workspace=tmp_path)
    assert before==[(p/'result.json').read_bytes() for p in paths]
    assert not (paths[0]/'result.before-load-v1.json').exists()


def test_load_uses_original_rep_phases_and_mass_scales_force_and_power(tmp_path,complete):
    import math
    data,b,paths=_legacy_fixture(tmp_path,complete)
    for p in paths:
        result=json.loads((p/'result.json').read_text(encoding='utf-8'))
        original=json.loads(json.dumps(result))
        low=_fitness_load_report(result,20.)
        high=_fitness_load_report(result,40.)
        assert result==original
        assert low['summary']['bounded_segments']==len(result['repetitions'])
        assert high['summary']['peak_velocity_m_s']==low['summary']['peak_velocity_m_s']
        for key in ('peak_force_n','peak_power_w'):
            assert high['summary'][key]==pytest.approx(low['summary'][key]*2)
        for rep,lift in zip(result['repetitions'],low['lifts']):
            start=rep['turn']['t'] if result['exercise']=='fitness_squat' else rep['start']['t']
            end=rep['end']['t'] if result['exercise']=='fitness_squat' else rep['turn']['t']
            assert start-.18<=lift['start_s']<lift['peak_time_s']<lift['end_s']<=end+.18
            assert lift['peak_force_n']>0 and lift['peak_power_w']>0
        for row in low['series']:
            assert all(v is None or math.isfinite(v) for k,v in row.items() if k!='point')
            assert all(0<=v<=1 for v in row['point'])
