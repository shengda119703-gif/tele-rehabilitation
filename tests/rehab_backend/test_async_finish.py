"""Durable processing receipt, bounded owned finalization and failure retry."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'rehab_codex_single_camera_v2_1'))
from tools.rehab_ml.common import paths
from mobile_rehab.rehab_v2.service import SessionService
from app.rehab_v2.sessions import SessionError
from test_sessions import frozen_plan, request


class AsyncFinishTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=paths()['run'])
        self.service = SessionService(Path(self.directory.name)/'isolated.sqlite3', frozen_plan,
                                      internal_replay=True, drain_timeout_s=.08)
        self.owner = 'TEST-owner'
        self.sid = self.service.create(self.owner, request())['session_id']
        self.payload = dict(idempotency_key='TEST-finish', expected_revision=0, reason='user_stopped')
        self.release = threading.Event()
        self.entered = threading.Event()
        self.calls = []
        original = self.service._finish
        def blocked(owner, sid, payload):
            self.calls.append((owner, sid, dict(payload)))
            self.entered.set()
            if not self.release.wait(3.):
                raise RuntimeError('TEST_owned_finalize_gate_timeout')
            return original(owner, sid, payload)
        self.service._finish = blocked

    def tearDown(self):
        self.release.set()
        self.service.close()
        self.directory.cleanup()

    def accept(self, payload=None):
        return self.service.request_finish(self.owner, self.sid, self.payload if payload is None else payload)

    def settle(self):
        self.release.set()
        deadline = time.monotonic()+3.
        while time.monotonic() < deadline:
            result = self.service.commit(self.owner, self.sid)
            if result['receipt'] and self.sid not in self.service.finish_pending:
                return result['receipt']
            time.sleep(.005)
        self.fail(str(result))

    def test_processing_receipt_durable_before_work_and_same_key_never_queues_twice(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            receipts = list(pool.map(lambda _: self.accept(), range(4)))
        self.assertTrue(self.entered.wait(1.))
        self.assertTrue(all(value == dict(status='finishing', session_id=self.sid, accepted_last_seq=-1) for value in receipts))
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.service.finish_queue.maxsize, 1)
        self.assertEqual(self.service.finish_pending, {self.sid})
        item = self.service.repository.get(self.owner, self.sid)
        self.assertEqual(item['run_state'], 'finishing')
        self.assertEqual(item['persistence_state'], 'draft')
        self.assertIsNone(self.service.commit(self.owner, self.sid)['receipt'])
        self.assertEqual(self.service.repository.lookup_operation(self.owner, self.sid, 'finish',
                         self.payload['idempotency_key'], __import__('app.domain', fromlist=['digest']).digest(self.payload)), receipts[0])
        self.assertEqual(self.service.repository.audit_view(self.owner, self.sid)['frames'], [])
        commit = self.settle()
        self.assertEqual(self.accept(), commit)
        self.assertEqual(self.accept(dict(self.payload, idempotency_key='TEST-new-key', expected_revision=999)), commit)
        audit = self.service.repository.audit_view(self.owner, self.sid)['audit']
        self.assertEqual(sum(row['kind'] == 'freeze_boundary' for row in audit), 1)
        self.assertEqual(sum(row['kind'] == 'finalize' for row in audit), 1)
        self.assertEqual(sum(row['kind'] == 'plan_contribution' for row in audit), 1)

    def test_alias_and_payload_conflict_during_processing_preserve_first_reason(self):
        first = self.accept()
        self.assertTrue(self.entered.wait(1.))
        self.assertEqual(self.accept(dict(self.payload, idempotency_key='TEST-alias', reason='completed')), first)
        with self.assertRaisesRegex(SessionError, 'idempotency_payload_conflict'):
            self.accept(dict(self.payload, reason='completed'))
        with self.assertRaisesRegex(SessionError, 'idempotency_payload_conflict'):
            self.accept(dict(self.payload, expected_revision=99))
        with self.assertRaises(SessionError) as denied:
            self.service.request_finish('TEST-other-owner', self.sid, self.payload)
        self.assertEqual(denied.exception.status, 404)
        self.assertEqual(self.settle()['end_reason'], 'user_stopped')
        self.assertEqual(len(self.calls), 1)

    def test_bad_first_revision_does_not_freeze_and_latest_valid_control_can_finish(self):
        with self.assertRaisesRegex(SessionError, 'control_revision_conflict'):
            self.accept(dict(self.payload, expected_revision=10))
        self.assertNotEqual(self.service.get(self.owner, self.sid)['run_state'], 'finishing')
        self.service.control(self.owner, self.sid, 'pause', dict(idempotency_key='pause', expected_revision=0))
        self.payload['expected_revision'] = 1
        self.assertEqual(self.accept()['status'], 'finishing')
        self.assertEqual(self.settle()['status'], 'finalized')

    def test_missing_consumer_rejects_before_freeze(self):
        self.service.finish_stop.set()
        self.service.finish_worker.join(1.)
        with self.assertRaisesRegex(SessionError, 'finish_consumer_unavailable'):
            self.accept()
        self.assertNotEqual(self.service.repository.get(self.owner, self.sid)['run_state'], 'finishing')
        self.assertEqual(self.service.repository.audit_view(self.owner, self.sid)['audit'][-1]['kind'], 'create')

    def test_storage_failure_stays_processing_and_identical_retry_reschedules_once(self):
        original = self.service.repository.finalize
        attempts = []
        def fail_once(*args):
            attempts.append(1)
            if len(attempts) == 1:
                raise SessionError('TEST_finalize_write_failed', 503)
            return original(*args)
        with patch.object(self.service.repository, 'finalize', fail_once):
            self.accept()
            self.release.set()
            deadline = time.monotonic()+2.
            while self.sid in self.service.finish_pending and time.monotonic() < deadline:
                time.sleep(.005)
            item = self.service.get(self.owner, self.sid)
            self.assertEqual(item['backend_execution']['finish_failure'], 'TEST_finalize_write_failed')
            self.assertEqual(item['run_state'], 'finishing')
            self.assertIsNone(self.service.commit(self.owner, self.sid)['receipt'])
            self.assertEqual(item['feedback_revision'], 0)
            self.assertEqual(item['feedback_status'], 'missing')
            self.accept()
            self.settle()
        self.assertEqual(len(attempts), 2)
        self.assertEqual(sum(row['kind'] == 'finalize' for row in self.service.repository.audit_view(self.owner, self.sid)['audit']), 1)
        self.assertIsNone(self.service.get(self.owner, self.sid)['backend_execution']['finish_failure'])

    def test_graceful_shutdown_joins_owned_finalizer_before_closing_storage(self):
        self.accept()
        self.assertTrue(self.entered.wait(1.))
        with ThreadPoolExecutor(max_workers=1) as pool:
            closing_result = pool.submit(self.service.close)
            self.release.set()
            closing_result.result(timeout=4.)
        self.assertTrue(self.service.resources_released)
        self.assertFalse(any(worker.is_alive() for worker in
                         (self.service.worker, self.service.report_worker, self.service.finish_worker)))
        # Fresh read-only connection, after the owning storage is closed.
        import sqlite3, json
        with closing(sqlite3.connect(self.service.database.as_uri()+'?mode=ro', uri=True)) as conn:
            saved = json.loads(conn.execute('SELECT payload FROM rehab_v2_sessions').fetchone()[0])
            self.assertEqual(saved['canonical_commit']['status'], 'finalized')
            self.assertEqual(saved['canonical_commit']['end_reason'], 'user_stopped')

    def test_http_202_processing_then_200_same_receipt_and_null_feedback(self):
        from fastapi import FastAPI, HTTPException
        from fastapi.testclient import TestClient
        import json
        from mobile_rehab.rehab_v2.api import install_rehab_v2
        # The test host owns no camera and uses a separate isolated database.
        self.release.set()
        self.service.close()
        self.release.clear()
        self.entered.clear()
        app = FastAPI()
        def owner(req):
            if req.cookies.get('TEST-auth') != 'yes':
                raise HTTPException(401)
            return self.owner
        async def small_json(req):
            return json.loads(await req.body())
        self.service = install_rehab_v2(app, Path(self.directory.name)/'http.sqlite3', owner, small_json, frozen_plan)
        original = self.service._finish
        def blocked(*args):
            self.entered.set()
            if not self.release.wait(3.):
                raise RuntimeError('TEST_finalize_gate_timeout')
            return original(*args)
        self.service._finish = blocked
        with TestClient(app, cookies={'TEST-auth': 'yes'}) as client:
            self.sid = client.post('/api/rehab/v2/sessions', json=request()).json()['session_id']
            endpoint = '/api/rehab/v2/sessions/'+self.sid
            response = client.post(endpoint+'/finish', json=self.payload)
            self.assertEqual(response.status_code, 202, response.text)
            self.assertEqual(response.json()['status'], 'finishing')
            self.assertIsNone(client.get(endpoint+'/commit').json()['receipt'])
            self.assertEqual(client.post(endpoint+'/finish', json=self.payload).json(), response.json())
            self.assertEqual(client.post(endpoint+'/finish', json=dict(self.payload, reason='completed')).status_code, 409)
            self.assertEqual(client.post(endpoint+'/feedback', json=dict(idempotency_key='feedback', expected_revision=0,
                feedback=dict(pain=None, fatigue=None))).status_code, 409)
            receipt = self.settle()
            retry = client.post(endpoint+'/finish', json=self.payload)
            self.assertEqual(retry.status_code, 200, retry.text)
            self.assertEqual(retry.json(), receipt)
            feedback = client.post(endpoint+'/feedback', json=dict(idempotency_key='feedback', expected_revision=0,
                feedback=dict(pain=None, fatigue=None)))
            self.assertEqual(feedback.status_code, 200, feedback.text)
            self.assertIsNone(feedback.json()['pain'])
            self.assertIsNone(feedback.json()['fatigue'])

    def test_failed_native_audit_cli_returns_nonzero_without_inventing_success(self):
        from tools.rehab_ml.cli import main
        from contextlib import redirect_stdout
        from io import StringIO
        for command, module, function in (
            ('benchmark-session-cold', 'tools.rehab_ml.session_cold_audit', 'benchmark_session_cold'),
            ('benchmark-session-load', 'tools.rehab_ml.session_load_audit', 'benchmark_session_load')):
            with self.subTest(command=command), patch(module+'.'+function, return_value=dict(passed=False)), redirect_stdout(StringIO()) as output:
                self.assertEqual(main([command]), 1)
                self.assertIn('"ok": false', output.getvalue())


if __name__ == '__main__':
    unittest.main()
