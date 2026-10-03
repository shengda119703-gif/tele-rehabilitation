"""Synthetic fixtures only; no tests claim human accuracy or phone hardware QA."""
import json
from pathlib import Path
import time
from datetime import datetime, timezone, timedelta

import pytest
from fastapi.testclient import TestClient
from mobile_rehab.server import create_app, save, Jobs, MAX_BYTES
from mobile_rehab.core import exercise_spec
from app.storage import Storage

HEADERS = {'X-Rehab-Client': 'mobile-v1', 'Content-Type': 'application/octet-stream'}
SCREEN = dict(general_activity_ok=True, standing_support_ok=True, companion_present=False)


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path, pair_key='test-key', runner=lambda item: None)
    with TestClient(app, headers=HEADERS) as client:
        client.post('/api/pair', json={'code': 'test-key'})
        yield client


def owner(client):
    return client.cookies['rehab_device'].split('.')[0]


def add_assessment(client):
    uid = owner(client)
    now = datetime.now(timezone.utc)
    spec = exercise_spec('shoulder_abduction')
    session = dict(id='fixture-assessment', scene_id='rehab', participant_id=uid,
                   source_kind='REPLAY_FILE', usage_context='SELF_USE', submode='assessment',
                   exercise_id='shoulder_abduction', side='left', status='FINISHED',
                   start_utc=(now-timedelta(minutes=1)).isoformat(), end_utc=now.isoformat(),
                   measurement_contract=spec['measurement_contract'],
                   summary=dict(primary_metric=spec['metric'], valid_ratio=.9, completed=3,
                                motion_range=dict(min_deg=5., max_deg=65., range_deg=60.)))
    store = Storage(client.app.state.jobs.root / uid / 'assessments.sqlite3')
    store.save_session(session)
    store.close()
    return session


def test_auth_catalog_and_static(client):
    response = client.get('/api/catalog')
    assert len(response.json()['exercises']) == 53
    assert response.headers['cache-control'] == 'no-store'
    assert client.get('/').status_code == 200
    assert client.get('/static/app.js').status_code == 200
    with TestClient(client.app) as other:
        assert other.get('/api/jobs').status_code == 401
        assert other.post('/api/pair', json={'code': 'test-key'}).status_code == 403


def test_barbell_demo_and_calibrated_upload(client):
    from mobile_rehab.tests.test_barbell import calibration
    result=client.get('/api/fitness/demo')
    assert result.status_code==200 and result.json()['synthetic'] is True
    assert client.get('/api/jobs').json()==[]
    headers={'X-Fitness-Calibration':json.dumps(calibration())}
    response=client.post('/api/jobs?exercise=fitness_deadlift&side=left&mode=fitness&consent=yes',content=b'x'*40,headers=headers)
    assert response.status_code==200
    job=client.get('/api/jobs/'+response.json()['id']).json()
    assert job['barbell_calibration']['mass_kg']==40
    for exercise,mode in [('shoulder_abduction','assessment'),('fitness_pushup','fitness')]:
        assert client.post(f'/api/jobs?exercise={exercise}&side=left&mode={mode}&consent=yes',content=b'x'*40,headers=headers).status_code==400
    headers['X-Fitness-Calibration']='{"mass_kg":NaN}'
    assert client.post('/api/jobs?exercise=fitness_deadlift&side=left&mode=fitness&consent=yes',content=b'x'*40,headers=headers).status_code==400
    with TestClient(client.app) as other:
        assert other.get('/api/fitness/demo').status_code==401


def test_pairing_invalid_and_large(client):
    assert client.post('/api/pair', json={'code': 'bad'}).status_code == 401
    assert client.post('/api/pair', content='x'*600).status_code == 413
    assert client.post('/api/pair', json=[]).status_code == 400


@pytest.mark.parametrize('query', ['exercise=unknown&side=left&consent=yes',
                                    'exercise=neck_flexion&side=up&consent=yes',
                                    'exercise=neck_flexion&side=left',
                                    'exercise=neck_flexion&side=left&consent=yes&mode=fake'])
def test_invalid_upload(client, query):
    assert client.post('/api/jobs?'+query, content=b'x'*40).status_code == 400


def test_size_limits_and_empty(client):
    url = '/api/jobs?exercise=shoulder_abduction&side=left&consent=yes'
    assert client.post(url, content=b'x', headers={'content-length': str(MAX_BYTES+1)}).status_code == 413
    assert client.post(url, content=b'').status_code == 400
    assert not list(client.app.state.jobs.root.glob('*/*/upload.part'))


def test_job_isolation_persistence_and_deletion(client):
    jobs = client.app.state.jobs
    def runner(item):
        save(jobs.folder(item) / 'result.json', {'summary': {'completed': 0}})
    jobs.runner = runner
    response = client.post('/api/jobs?exercise=neck_flexion&side=left&consent=yes', content=b'x'*50)
    assert response.status_code == 200
    jid = response.json()['id']
    for _ in range(100):
        result = client.get('/api/jobs/'+jid).json()
        if result['state'] == 'done':
            break
        time.sleep(.01)
    assert result['state'] == 'done'
    assert 'owner' not in result
    cookie = client.cookies['rehab_device']
    client.cookies.clear()
    client.post('/api/pair', json={'code': 'test-key'})
    assert client.get('/api/jobs').json() == []
    assert client.get('/api/jobs/'+jid).status_code == 404
    assert client.get('/api/jobs/'+jid+'/video').status_code == 404
    assert client.delete('/api/jobs/'+jid+'/video').status_code == 404
    client.cookies.clear()
    client.cookies.set('rehab_device', cookie)
    assert client.get('/api/jobs/'+jid+'/video').status_code == 200
    assert client.delete('/api/jobs/'+jid+'/video').status_code == 200
    assert client.get('/api/jobs/'+jid+'/video').status_code == 404
    assert client.get('/api/jobs/'+jid).json()['result']['summary']['completed'] == 0


def test_restart_marks_pending_failed(tmp_path):
    jobs = Jobs(tmp_path)
    item = jobs.reserve('a'*32, 'neck_flexion', 'left')
    jobs.close()
    restarted = Jobs(tmp_path)
    assert restarted.get(item['id'], item['owner'])['state'] == 'failed'
    restarted.close()


def test_one_active_per_device_and_busy_delete(client):
    jobs = client.app.state.jobs
    item = jobs.reserve(owner(client), 'neck_flexion', 'left')
    assert client.delete('/api/jobs/'+item['id']+'/video').status_code == 409
    assert client.post('/api/jobs?exercise=neck_flexion&side=left&consent=yes', content=b'x'*50).status_code == 409


def test_plan_requires_evidence_and_consent(client):
    assert client.get('/api/plan').json()['proposal']['candidates'] == []
    assert client.post('/api/plan', json=SCREEN).status_code == 400
    add_assessment(client)
    data = client.get('/api/plan').json()
    assert data['proposal']['candidates'][0]['settings']['target_reps'] == 3
    assert client.post('/api/plan', json={**SCREEN, 'general_activity_ok': False}).status_code == 400
    response = client.post('/api/plan', json=SCREEN)
    assert response.status_code == 200, response.text
    record = response.json()
    assert record['items'][0]['settings']['target_angle_deg'] == 53
    data = client.get('/api/plan').json()
    assert data['progress']['next_key'] == 'shoulder_abduction:left'
    assert not data['progress']['blocked']
    assert record['source_kind'] == 'REPLAY_FILE'


def test_training_binding_cannot_be_forged(client):
    add_assessment(client)
    record = client.post('/api/plan', json=SCREEN).json()
    url = f"/api/jobs?exercise=neck_flexion&side=left&consent=yes&mode=training&plan_id={record['id']}&entry_key=shoulder_abduction:left"
    assert client.post(url, content=b'x'*50).status_code == 400


def test_feedback_saved_and_blocks_when_unwell(client):
    add_assessment(client)
    record = client.post('/api/plan', json=SCREEN).json()
    uid, jobs = owner(client), client.app.state.jobs
    item = jobs.reserve(uid, 'shoulder_abduction', 'left')
    now = datetime.now(timezone.utc).isoformat()
    store = Storage(jobs.root / uid / 'assessments.sqlite3')
    session = dict(id='training-fixture', scene_id='rehab', source_kind='REPLAY_FILE',
                   usage_context='SELF_USE', participant_id=uid, submode='training',
                   exercise_id='shoulder_abduction', side='left', status='FINISHED',
                   start_utc=now, end_utc=now, summary={'plan_completed': True},
                   saved_plan_reference={'id': record['id'], 'revision': record['revision'],
                                         'entry_key': record['items'][0]['key']})
    store.save_session(session)
    store.close()
    save(jobs.folder(item) / 'result.json', {'session_id': session['id']})
    jobs.update(item['id'], state='done', mode='training')
    assert client.get('/api/plan').json()['progress']['blocked']
    response = client.post('/api/jobs/'+item['id']+'/feedback', json={'pain': 2, 'fatigue': 0, 'reason': 'discomfort'})
    assert response.status_code == 200, response.text
    assert '不适' in client.get('/api/plan').json()['progress']['blocked']
    assert client.post('/api/jobs/'+item['id']+'/feedback', json={'pain': 0, 'fatigue': 0}).status_code == 400


def test_large_json_and_tampered_cookie(client):
    assert client.post('/api/plan', content='x'*5000).status_code == 413
    client.cookies.clear()
    client.cookies.set('rehab_device', 'a'*32+'.bad')
    assert client.get('/api/catalog').status_code == 401


def test_fitness_api_is_separate_and_does_not_create_rehab_evidence(client):
    from mobile_rehab.fitness import EXERCISES
    assert {x['id'] for x in client.get('/api/catalog').json()['fitness']} == set(EXERCISES)
    jobs = client.app.state.jobs
    jobs.runner = lambda item: save(jobs.folder(item) / 'result.json', {'kind': 'fitness', 'summary': {'completed': 0}})
    assert client.post('/api/jobs?exercise=fitness_squat&side=left&consent=yes', content=b'x'*50).status_code == 400
    assert client.post('/api/jobs?exercise=shoulder_abduction&side=left&consent=yes&mode=fitness', content=b'x'*50).status_code == 400
    response = client.post('/api/jobs?exercise=fitness_squat&side=left&consent=yes&mode=fitness', content=b'x'*50)
    assert response.status_code == 200
    jid = response.json()['id']
    for _ in range(100):
        report = client.get('/api/jobs/'+jid).json()
        if report['state'] == 'done':
            break
        time.sleep(.01)
    assert report['mode'] == 'fitness' and report['result']['kind'] == 'fitness'
    brief = client.get('/api/jobs?brief=true').json()
    assert brief[0]['mode'] == 'fitness' and 'result' not in brief[0]
    assert client.get('/api/plan').json()['proposal']['candidates'] == []
    assert client.post('/api/jobs/'+jid+'/feedback', json={'pain': 0, 'fatigue': 0}).status_code == 409


def test_fitness_mode_real_model_empty_video(tmp_path):
    import cv2
    import numpy as np
    import subprocess
    import sys
    from mobile_rehab.core import ROOT
    folder = tmp_path / 'fitness-empty'
    folder.mkdir()
    writer = cv2.VideoWriter(str(folder / 'video.mp4'), cv2.VideoWriter_fourcc(*'mp4v'), 10., (320, 240))
    assert writer.isOpened()
    for _ in range(12):
        writer.write(np.zeros((240, 320, 3), dtype=np.uint8))
    writer.release()
    save(folder / 'job.json', dict(id='empty', owner='test-only', mode='fitness', exercise='fitness_deadlift', side='left'))
    process = subprocess.run([sys.executable, '-m', 'mobile_rehab.analyzer', str(folder / 'job.json')], cwd=ROOT, capture_output=True, timeout=100)
    assert process.returncode == 0, process.stderr.decode(errors='replace')
    result = json.loads((folder / 'result.json').read_text(encoding='utf-8'))
    assert result['kind'] == 'fitness'
    assert result['summary']['completed'] == 0
    assert result['summary']['metrics'] == {}
    assert result['conditions']['model_manifest_id']
    assert not list(tmp_path.rglob('assessments.sqlite3'))


def test_real_capture_model_and_empty_report(tmp_path):
    """Real local YOLO + SourceWorker; black test clip must yield NO movement."""
    import cv2
    import numpy as np
    import subprocess
    import sys
    from mobile_rehab.core import ROOT
    folder = tmp_path / ('b'*32) / ('c'*32)
    folder.mkdir(parents=True)
    writer = cv2.VideoWriter(str(folder / 'video.mp4'), cv2.VideoWriter_fourcc(*'mp4v'), 10., (320, 240))
    assert writer.isOpened()
    for _ in range(30):
        writer.write(np.zeros((240, 320, 3), dtype=np.uint8))
    writer.release()
    save(folder / 'job.json', dict(id='c'*32, owner='b'*32, exercise='shoulder_abduction', side='left'))
    result = subprocess.run([sys.executable, '-m', 'mobile_rehab.analyzer', str(folder / 'job.json')],
                            cwd=ROOT, capture_output=True, timeout=100)
    assert result.returncode == 0, result.stderr.decode(errors='replace')
    report = json.loads((folder / 'result.json').read_text(encoding='utf-8'))
    assert report['summary']['completed'] == 0
    assert report['summary']['motion_range'] is None
    assert report['proposal']['candidates'] == []
    assert report['source_kind'] == 'REPLAY_FILE'


def test_replay_controller_assessment_to_training(tmp_path, monkeypatch):
    """Test-only generated poses + real replay/controller/storage, never user data."""
    import math
    import cv2
    import numpy as np
    from mobile_rehab import analyzer
    from app.domain import PoseFrame, PosePerson
    from app.assessment import build_body_profile
    from app.automatic_plans import generate_proposal, create_automatic_plan

    class TestVision:
        def __init__(self, **kwargs):
            pass

        def infer(self, packet, **kwargs):
            angle = 90. if 2.2 <= packet.time_s <= 4.4 else 0.
            r = math.radians(angle)
            xy = [[120., 100.] for _ in range(17)]
            xy[5], xy[6], xy[11], xy[12] = [200., 150.], [300., 150.], [200., 300.], [300., 300.]
            xy[7] = [200+100*math.sin(r), 150+100*math.cos(r)]
            xy[9] = [200+150*math.sin(r), 150+150*math.cos(r)]
            xy[13], xy[15] = [200., 400.], [200., 500.]
            return PoseFrame(packet.context, packet.seq, packet.time_s, (640, 720),
                [PosePerson(packet.context.epoch+':1', [100, 50, 500, 600], xy, [1.]*17)],
                model_manifest_id='synthetic-test-pose-not-human-validation')

        def close(self):
            pass

    monkeypatch.setattr(analyzer, 'VisionWorker', TestVision)
    uid = 'd'*32
    first = tmp_path / uid / 'assessment'
    first.mkdir(parents=True)
    writer = cv2.VideoWriter(str(first / 'video.mp4'), cv2.VideoWriter_fourcc(*'mp4v'), 10., (640, 720))
    assert writer.isOpened()
    for _ in range(75):
        writer.write(np.zeros((720, 640, 3), dtype=np.uint8))
    writer.release()
    job = dict(id='assessment', owner=uid, exercise='shoulder_abduction', side='left')
    save(first / 'job.json', job)
    analyzer.analyze(first / 'job.json')
    result = json.loads((first / 'result.json').read_text(encoding='utf-8'))
    assert result['summary']['completed'] == 1
    assert result['summary']['valid_ratio'] >= .8
    store = Storage(first.parent / 'assessments.sqlite3')
    sessions = store.list_sessions()
    profile = build_body_profile(sessions, uid, 'REPLAY_FILE', 'SELF_USE')
    record = store.save_training_plan(create_automatic_plan(generate_proposal(profile, sessions), SCREEN), expected_revision=0)
    store.close()
    second = first.parent / 'training'
    second.mkdir()
    import shutil
    shutil.copyfile(first / 'video.mp4', second / 'video.mp4')
    save(second / 'job.json', dict(job, id='training', mode='training', plan_id=record['id'], entry_key=record['items'][0]['key']))
    analyzer.analyze(second / 'job.json')
    result = json.loads((second / 'result.json').read_text(encoding='utf-8'))
    assert result['summary']['completed'] == 1
    assert result['summary']['plan_completed'] is True
    assert result['quality']['observed_goals_met'] == 1
