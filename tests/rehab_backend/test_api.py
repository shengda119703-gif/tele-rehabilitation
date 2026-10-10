from contextlib import asynccontextmanager
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.rehab_ml.common import paths
from mobile_rehab.rehab_v2.api import install_rehab_v2
from test_sessions import frozen_plan, request


class ApiTests(unittest.TestCase):
    def setUp(self):
        from fastapi import FastAPI, Request, HTTPException
        from fastapi.testclient import TestClient
        self.directory = tempfile.TemporaryDirectory(dir=paths()['run'])
        @asynccontextmanager
        async def lifespan(app):
            yield
            app.state.rehab_v2.close()
        app = FastAPI(lifespan=lifespan)
        def owner(req):
            value = req.cookies.get('test-owned-session')
            if value not in ('TEST-owner', 'other-owner'):
                raise HTTPException(401, 'authentication_required')
            return value
        async def small_json(req):
            content = await req.body()
            if len(content) > 4096:
                raise HTTPException(413)
            return json.loads(content)
        self.service = install_rehab_v2(app, Path(self.directory.name)/'http.sqlite3', owner, small_json, frozen_plan)
        self.client = TestClient(app)
        self.client.__enter__()
        self.client.cookies.set('test-owned-session', 'TEST-owner')

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.directory.cleanup()

    def test_actual_http_lifecycle_controls_commit_feedback_and_owner(self):
        base = '/api/rehab/v2/sessions'
        created = self.client.post(base, json=request())
        self.assertEqual(created.status_code, 200, created.text)
        sid = created.json()['session_id']
        endpoint = base+'/'+sid
        self.assertEqual(self.client.post(base, json=request()).json()['session_id'], sid)
        self.assertEqual(self.client.post(endpoint+'/pause', json=dict(idempotency_key='pause', expected_revision=0)).status_code, 200)
        self.assertEqual(self.client.post(endpoint+'/resume', json=dict(idempotency_key='resume', expected_revision=1)).status_code, 200)
        self.assertEqual(self.client.post(endpoint+'/frames', json=dict(keypoints=[])).status_code, 415)
        receipt = self.client.post(endpoint+'/finish', json=dict(idempotency_key='finish', expected_revision=2, reason='user_stopped'))
        self.assertEqual(receipt.status_code, 200, receipt.text)
        self.assertEqual(self.client.get(endpoint+'/commit').json()['receipt']['commit_id'], receipt.json()['commit_id'])
        self.assertEqual(self.client.post(endpoint+'/feedback', json=dict(idempotency_key='feedback', expected_revision=0,
                         feedback=dict(pain=None, fatigue=None))).status_code, 200)
        self.client.cookies.set('test-owned-session', 'other-owner')
        self.assertEqual(self.client.get(endpoint).status_code, 404)
        self.client.cookies.clear()
        self.assertEqual(self.client.post(base, json=request()).status_code, 401)

    def test_jpeg_endpoint_runs_real_baseline_pose_backend(self):
        from PIL import Image
        base = '/api/rehab/v2/sessions'
        sid = self.client.post(base, json=request()).json()['session_id']
        image = BytesIO()
        Image.new('RGB', (320, 240), 'white').save(image, format='JPEG')
        response = self.client.post(base+'/'+sid+'/frames', content=image.getvalue(),
                                   headers={'content-type': 'image/jpeg', 'x-rehab-event-id': 'frame1', 'x-rehab-seq': '1'})
        self.assertEqual(response.status_code, 200, response.text)
        deadline = time.monotonic()+20
        while time.monotonic() < deadline:
            state = self.client.get(base+'/'+sid).json()
            if state['processed_count'] > 0:
                break
            time.sleep(.02)
        self.assertEqual(state['processed_count'], 1, state)
        self.assertEqual(state['snapshot']['completed'], 0)
        self.assertEqual(state['observation_state'], 'missing')


class HostIntegrationTests(unittest.TestCase):
    def test_real_host_auth_existing_auto_plan_and_legacy_live_stays_preview(self):
        from fastapi.testclient import TestClient
        from mobile_rehab.server import create_app
        from mobile_rehab.tests.test_mobile import add_assessment, SCREEN
        with tempfile.TemporaryDirectory(dir=paths()['run']) as directory:
            app = create_app(directory, pair_key='TEST-host-qualification', runner=lambda item: None, rehab_v2=True)
            with TestClient(app, headers={'X-Rehab-Client': 'mobile-v1'}) as client:
                self.assertEqual(client.post('/api/pair', json={'code': 'TEST-host-qualification'}).status_code, 200)
                add_assessment(client)  # Original fixture: isolated existing schema, not fabricated real patient data.
                plan = client.post('/api/plan', json=SCREEN)
                self.assertEqual(plan.status_code, 200, plan.text)
                plan = plan.json()
                payload = dict(idempotency_key='formal-create', consent=True, plan_id=plan['id'],
                    expected_plan_revision=plan['revision'], entry_key=plan['items'][0]['key'])
                response = client.post('/api/rehab/v2/sessions', json=payload)
                self.assertEqual(response.status_code, 200, response.text)
                sid = response.json()['session_id']
                self.assertEqual(response.json()['frozen_plan']['reference']['revision'], plan['revision'])
                finished = client.post('/api/rehab/v2/sessions/'+sid+'/finish',
                    json=dict(idempotency_key='formal-finish', expected_revision=0, reason='user_stopped'))
                self.assertEqual(finished.status_code, 200, finished.text)
                self.assertEqual(finished.json()['completed_reps'], 0)
                self.assertEqual(client.get('/api/rehab/v2/sessions/'+sid+'/commit').json()['receipt'], finished.json())
                # New explicit namespace is not projected into legacy history/progress.
                self.assertEqual(client.get('/api/plan').json()['progress']['next_key'], plan['items'][0]['key'])

    def test_default_host_does_not_enable_formal_routes(self):
        from fastapi.testclient import TestClient
        from mobile_rehab.server import create_app
        with tempfile.TemporaryDirectory(dir=paths()['run']) as directory:
            app = create_app(directory, pair_key='TEST-default-host', runner=lambda item: None)
            with TestClient(app, headers={'X-Rehab-Client': 'mobile-v1'}) as client:
                self.assertEqual(client.post('/api/rehab/v2/sessions', json={}).status_code, 404)
            self.assertFalse(any(route.path == '/api/rehab/v2/sessions' for route in app.routes))
            self.assertFalse((Path(directory)/'rehab-v2.sqlite3').exists())


if __name__ == '__main__':
    unittest.main()
