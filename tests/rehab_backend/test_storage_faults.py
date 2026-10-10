"""Native SQLite faults in bounded TEST databases, never a full real drive.

query_only/mode=ro, max_page_count, external locks and damaged TEST copies
produce genuine SQLite error codes. No patched exception substitutes for them.
The capacity fixture is a SQLite limit, explicitly NOT physical ENOSPC.
"""
from contextlib import closing
from dataclasses import asdict
from io import BytesIO
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mobile_rehab.rehab_v2.service import SessionService
from mobile_rehab.rehab_v2.pose_worker import IsolatedPoseWorker, VERSION, _send, _reply
from multiprocessing.shared_memory import SharedMemory
from app.domain import Context, PoseFrame, digest
from app.storage import Storage
from app.rehab_v2.storage_boundary import RehabStorageBoundary, StorageFault, BUSY_TIMEOUT_MS
from app.rehab_v2.sessions import SessionError
from tools.rehab_ml.common import paths, file_hash
from test_sessions import frozen_plan, request
from test_protocols import Replay
from test_isolation import wait_until


def delayed_empty_pose(pipe, memory_name):
    memory = SharedMemory(name=memory_name)
    try:
        _send(pipe, dict(ready=VERSION))
        while True:
            value = json.loads(pipe.recv_bytes(4096))
            time.sleep(.5)
            pose = PoseFrame(Context(**value['context']), value['seq'], value['source_time_s'],
                             (64, 64), [], model_manifest_id='TEST-storage-fault-fixture')
            _reply(pipe, memory, dict(ticket=value['ticket'], ok=True, pose=asdict(pose),
                                     decode_ms=.1, inference_ms=.2))
    except (EOFError, BrokenPipeError, OSError):
        pass
    finally:
        memory.close()
        pipe.close()


class NativeStorageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=paths()['run'])
        self.root = Path(self.directory.name).resolve()
        self.database = self.root/'TEST-sessions.sqlite3'
        self.owner = 'TEST-storage-owner'
        self.service = SessionService(self.database, frozen_plan, internal_replay=True)

    def tearDown(self):
        self.service.close(graceful=False)
        self.directory.cleanup()

    def create(self):
        return self.service.create(self.owner, request())['session_id']

    def cycle(self, sid):
        replay = Replay()
        for value, count in ((0., 30), (70., 10), (0., 10)):
            for _ in range(count):
                replay.feed(value, 1)
                self.service.submit_evidence(self.owner, sid, 'TEST-frame-'+str(replay.seq), replay.frame)

    def finish(self, sid):
        return self.service.finish(self.owner, sid,
            dict(idempotency_key='finish', expected_revision=0, reason='user_stopped'))

    def pragma(self, sql):
        return self.service.storage._call(lambda conn: conn.execute(sql).fetchone())

    def immutable(self, sid):
        item = self.service.repository.get(self.owner, sid)
        return digest(dict(snapshot=item['snapshot'], receipt=item['canonical_commit'],
                           contribution=self.service.repository.plan_contribution(self.owner, sid)))

    def backup(self, name):
        target = (self.root/name).resolve()
        self.assertEqual(target.parent, self.root)
        self.assertFalse(target.exists())
        def copy(conn):
            with closing(sqlite3.connect(target)) as other:
                conn.backup(other)
        self.service.storage._call(copy)
        return target

    def test_real_readonly_uri_denies_write_and_preserves_database(self):
        sid = self.create()
        self.service.close(graceful=False)
        before = file_hash(self.database)
        storage = Storage(self.database, readonly=True)
        observed = []
        try:
            boundary = RehabStorageBoundary(storage, observed.append)
            with self.assertRaises(StorageFault) as raised:
                boundary._call(lambda conn: conn.execute(
                    'UPDATE rehab_v2_sessions SET payload=payload WHERE id=?', (sid,)))
            self.assertEqual(raised.exception.sqlite_code & 255, sqlite3.SQLITE_READONLY)
            self.assertEqual(raised.exception.code, 'formal_store_readonly')
            self.assertEqual(observed[0].public['commit_state'], 'not_confirmed_by_this_error')
        finally:
            storage.close()
        self.assertEqual(file_hash(self.database), before)

    def test_query_only_control_rolls_back_runtime_revision_and_same_key_can_retry(self):
        sid = self.create()
        payload = dict(idempotency_key='pause', expected_revision=0)
        before = self.service.get(self.owner, sid)
        self.pragma('PRAGMA query_only=1')
        try:
            with self.assertRaises(StorageFault) as raised:
                self.service.control(self.owner, sid, 'pause', payload)
            self.assertEqual(raised.exception.sqlite_code & 255, sqlite3.SQLITE_READONLY)
            item = self.service.get(self.owner, sid)
            self.assertEqual(item['revision'], before['revision'])
            self.assertEqual(item['snapshot'], before['snapshot'])
            self.assertEqual(self.service.runtimes[sid].engine.run_state, before['run_state'])
            self.assertEqual(item['backend_execution']['last_storage_fault']['reason'], 'readonly')
        finally:
            self.pragma('PRAGMA query_only=0')
        first = self.service.control(self.owner, sid, 'pause', payload)
        self.assertEqual(first['revision'], 1)
        self.assertEqual(self.service.control(self.owner, sid, 'pause', payload), first)

    def test_sqlite_capacity_fault_rolls_back_final_fact_report_and_contribution(self):
        sid = self.create()
        self.cycle(sid)
        snapshot = self.service.get(self.owner, sid)['snapshot']
        self.assertEqual(snapshot['completed'], 1)
        # A bounded 256 KiB allocation is requested inside the final transaction.
        self.service.storage._call(lambda conn: conn.executescript('''
            CREATE TABLE TEST_capacity_padding(value BLOB);
            CREATE TRIGGER TEST_capacity BEFORE INSERT ON rehab_v2_plan_contributions
            BEGIN INSERT INTO TEST_capacity_padding VALUES(zeroblob(262144)); END;
        '''))
        pages = self.pragma('PRAGMA page_count')[0]
        original_max = self.pragma('PRAGMA max_page_count')[0]
        self.assertEqual(self.pragma('PRAGMA max_page_count='+str(pages))[0], pages)
        try:
            with self.assertRaises(StorageFault) as raised:
                self.finish(sid)
            self.assertEqual(raised.exception.sqlite_code & 255, sqlite3.SQLITE_FULL)
            self.assertEqual(raised.exception.reason, 'capacity')
            item = self.service.get(self.owner, sid)
            self.assertEqual(item['persistence_state'], 'draft')
            self.assertIsNone(item['canonical_commit'])
            self.assertIsNone(item['plan_contribution'])
            self.assertEqual(item['snapshot'], snapshot)
            self.assertEqual(self.service.history(self.owner)['items'], [])
            def counts(conn):
                return tuple(conn.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in
                    ('rehab_v2_reports', 'rehab_v2_plan_contributions', 'TEST_capacity_padding'))
            self.assertEqual(self.service.storage._call(counts), (0, 0, 0))
            self.assertEqual(self.pragma('PRAGMA integrity_check')[0], 'ok')
        finally:
            self.pragma('PRAGMA max_page_count='+str(original_max))
            self.service.storage._call(lambda conn: conn.execute('DROP TRIGGER TEST_capacity'))
        first = self.finish(sid)
        self.assertEqual(first['completed_reps'], 1)
        self.assertEqual(self.finish(sid), first)
        self.assertEqual(self.service.storage._call(lambda conn: conn.execute(
            'SELECT COUNT(*) FROM rehab_v2_plan_contributions WHERE session_id=?', (sid,)).fetchone()[0]), 1)

    def test_external_sqlite_lock_has_bounded_busy_error_and_safe_same_key_retry(self):
        sid = self.create()
        self.assertEqual(self.pragma('PRAGMA busy_timeout')[0], BUSY_TIMEOUT_MS)
        before = self.service.get(self.owner, sid)
        payload = dict(idempotency_key='pause-lock', expected_revision=0)
        with closing(sqlite3.connect(self.database, timeout=0.)) as blocker:
            blocker.execute('BEGIN IMMEDIATE')
            started = time.monotonic()
            with self.assertRaises(StorageFault) as raised:
                self.service.control(self.owner, sid, 'pause', payload)
            self.assertEqual(raised.exception.sqlite_code & 255, sqlite3.SQLITE_BUSY)
            self.assertLess(time.monotonic()-started, 1.2)
            self.assertEqual(self.service.get(self.owner, sid)['snapshot'], before['snapshot'])
            blocker.rollback()
        receipt = self.service.control(self.owner, sid, 'pause', payload)
        self.assertEqual(receipt['revision'], 1)
        self.assertEqual(self.service.control(self.owner, sid, 'pause', payload), receipt)

    def test_business_constraint_and_programming_errors_are_not_storage_outages(self):
        self.service.storage_boundary._call(lambda conn: conn.execute('CREATE TABLE TEST_unique(id INTEGER UNIQUE)'))
        self.service.storage_boundary._call(lambda conn: conn.execute('INSERT INTO TEST_unique VALUES(1)'))
        with self.assertRaises(sqlite3.IntegrityError):
            self.service.storage_boundary._call(lambda conn: conn.execute('INSERT INTO TEST_unique VALUES(1)'))
        with self.assertRaises(sqlite3.OperationalError):
            self.service.storage_boundary._call(lambda conn: conn.execute('SELECT TEST_typo FROM TEST_unique'))
        self.assertIsNone(self.service.last_storage_fault)

    def test_readonly_feedback_failure_never_changes_visual_fact_or_feedback_revision(self):
        sid = self.create()
        self.cycle(sid)
        receipt = self.finish(sid)
        wait_until(lambda: self.service.get(self.owner, sid)['derived_report_state'] == 'ready')
        before = self.immutable(sid)
        payload = dict(idempotency_key='TEST-feedback', expected_revision=0, feedback=dict(pain=None, fatigue=2))
        self.pragma('PRAGMA query_only=1')
        try:
            with self.assertRaises(StorageFault) as raised:
                self.service.feedback(self.owner, sid, payload)
            self.assertEqual(raised.exception.sqlite_code & 255, sqlite3.SQLITE_READONLY)
            item = self.service.get(self.owner, sid)
            self.assertEqual(item['feedback_revision'], 0)
            self.assertEqual(item['feedback_status'], 'missing')
            self.assertEqual(self.immutable(sid), before)
        finally:
            self.pragma('PRAGMA query_only=0')
        result = self.service.feedback(self.owner, sid, payload)
        self.assertEqual(self.service.feedback(self.owner, sid, payload), result)
        self.assertEqual(self.service.commit(self.owner, sid)['receipt'], receipt)
        self.assertEqual(self.immutable(sid), before)

    def test_real_readonly_report_write_stays_pending_and_retries_without_recount(self):
        armed = [True]
        def report(item):
            if armed[0]:
                armed[0] = False
                self.pragma('PRAGMA query_only=1')
            return SessionService._report(item)
        self.service.report_builder = report  # Local scheduling hook, not a fake SQL failure.
        sid = self.create()
        self.cycle(sid)
        receipt = self.finish(sid)
        before = self.immutable(sid)
        try:
            wait_until(lambda: self.service.report_worker_failure == 'formal_store_readonly')
            self.assertEqual(self.service.get(self.owner, sid)['derived_report_state'], 'pending')
            self.assertEqual(self.service.commit(self.owner, sid)['receipt'], receipt)
            self.assertEqual(self.immutable(sid), before)
        finally:
            self.pragma('PRAGMA query_only=0')
        self.service.report_builder = self.service._report
        self.service.report_wake.set()
        wait_until(lambda: self.service.get(self.owner, sid)['derived_report_state'] == 'ready')
        self.assertEqual(self.immutable(sid), before)

    def test_damaged_test_copy_is_preserved_and_failed_open_releases_lease(self):
        sid = self.create()
        self.cycle(sid)
        backup = self.backup('TEST-consistent-backup.sqlite3')
        damaged = self.root/'TEST-damaged-copy.sqlite3'
        self.assertFalse(damaged.exists())
        shutil.copy2(backup, damaged)
        data = damaged.read_bytes()
        damaged.write_bytes(b'BAD_TEST_HEADER!'+data[16:])
        fingerprint = file_hash(damaged)
        source_fingerprint = file_hash(backup)
        for _ in range(2):
            with self.assertRaises(StorageFault) as raised:
                SessionService(damaged, frozen_plan, internal_replay=True)
            self.assertEqual(raised.exception.sqlite_code & 255, sqlite3.SQLITE_NOTADB)
            self.assertFalse(raised.exception.public['automatic_recreation'])
            self.assertEqual(raised.exception.public['recovery'], 'preserve_database_and_require_explicit_recovery')
            self.assertEqual(file_hash(damaged), fingerprint)
        self.assertEqual(file_hash(backup), source_fingerprint)
        self.assertEqual(self.service.get(self.owner, sid)['snapshot']['completed'], 1)

    def test_explicit_sqlite_backup_restore_to_new_path_recovers_only_checkpointed_fact(self):
        sid = self.create()
        self.cycle(sid)
        original = self.service.get(self.owner, sid)['snapshot']['repetitions']
        backup = self.backup('TEST-last-good.sqlite3')
        fingerprint = file_hash(backup)
        restored = self.root/'TEST-restored-new-path.sqlite3'
        self.assertFalse(restored.exists())
        with closing(sqlite3.connect(backup.as_uri()+'?mode=ro', uri=True)) as source:
            self.assertEqual(source.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            with closing(sqlite3.connect(restored)) as target:
                source.backup(target)
        recovered = SessionService(restored, frozen_plan, internal_replay=True)
        try:
            item = recovered.get(self.owner, sid)
            self.assertEqual(item['end_reason'], 'interrupted')
            self.assertEqual(item['snapshot']['completed'], 1)
            self.assertEqual(item['snapshot']['repetitions'], original)
            receipt = recovered.commit(self.owner, sid)['receipt']
            self.assertEqual(receipt['completed_reps'], 1)
            self.assertEqual(recovered.commit(self.owner, sid)['plan_contribution']['commit_id'], receipt['commit_id'])
        finally:
            recovered.close()
        self.assertEqual(file_hash(backup), fingerprint)
        with closing(sqlite3.connect(restored.as_uri()+'?mode=ro', uri=True)) as conn:
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM rehab_v2_plan_contributions').fetchone()[0], 1)

    def test_native_readonly_checkpoint_stops_consumer_not_as_input_failure(self):
        from PIL import Image
        self.service.close(graceful=False)
        self.service = SessionService(self.root/'TEST-camera-storage.sqlite3', frozen_plan)
        self.service.inference_worker = IsolatedPoseWorker(target=delayed_empty_pose,
            startup_timeout_s=5., cold_timeout_s=2., frame_timeout_s=2., release_timeout_s=.25)
        sid = self.create()
        stream = BytesIO()
        Image.new('RGB', (64, 64), 'white').save(stream, format='JPEG')
        self.service.submit_jpeg(self.owner, sid, 'TEST-jpeg', 1, stream.getvalue())
        wait_until(lambda: self.service.inference_worker.last_request is not None)
        self.pragma('PRAGMA query_only=1')
        try:
            wait_until(lambda: not self.service.worker.is_alive())
            item = self.service.get(self.owner, sid)
            self.assertEqual(item['backend_execution']['failure'], 'formal_store_readonly')
            self.assertEqual(item['persistence_state'], 'draft')
            self.assertIsNone(item['canonical_commit'])
            self.assertEqual(item['processed_count'], 0)
            frames = self.service.repository.audit_view(self.owner, sid)['frames']
            self.assertEqual(frames[0]['status'], 'accepted')
            trace = self.service.diagnostics(self.owner, sid)
            self.assertEqual(trace['counters']['input_failed'], 0)
            self.assertEqual(trace['counters']['background_failure'], 1)
            self.assertEqual(trace['last_storage_fault']['reason'], 'readonly')
            self.assertTrue(self.service.inference_worker.last_release['confirmed'])
        finally:
            self.pragma('PRAGMA query_only=0')
        with self.assertRaisesRegex(SessionError, 'formal_inference_worker_unavailable'):
            self.service.submit_jpeg(self.owner, sid, 'TEST-jpeg2', 2, stream.getvalue())
        self.service.close(graceful=False)
        self.service = SessionService(self.root/'TEST-camera-storage.sqlite3', frozen_plan)
        item = self.service.get(self.owner, sid)
        self.assertEqual(item['end_reason'], 'interrupted')
        self.assertEqual(item['snapshot']['completed'], 0)
        self.assertEqual(self.service.commit(self.owner, sid)['receipt']['completed_reps'], 0)


class NativeStorageHttpTests(unittest.TestCase):
    def setUp(self):
        from fastapi import FastAPI, Request, HTTPException
        from fastapi.testclient import TestClient
        from mobile_rehab.rehab_v2.api import install_rehab_v2
        self.directory = tempfile.TemporaryDirectory(dir=paths()['run'])
        app = FastAPI()
        def owner(req):
            if req.cookies.get('TEST-storage-auth') != 'TEST-owner':
                raise HTTPException(401, 'authentication_required')
            return 'TEST-owner'
        async def small_json(req):
            return json.loads(await req.body())
        self.service = install_rehab_v2(app, Path(self.directory.name)/'TEST-http.sqlite3', owner, small_json, frozen_plan)
        self.client = TestClient(app)
        self.client.cookies.set('TEST-storage-auth', 'TEST-owner')

    def tearDown(self):
        self.service.storage._call(lambda conn: conn.execute('PRAGMA query_only=0').fetchone())
        self.service.close()
        self.client.close()
        self.directory.cleanup()

    def test_native_readonly_create_returns_503_without_private_sql_or_fake_receipt(self):
        self.service.storage._call(lambda conn: conn.execute('PRAGMA query_only=1').fetchone())
        response = self.client.post('/api/rehab/v2/sessions', json=request())
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(response.json()['detail'], 'formal_store_readonly')
        self.assertEqual(response.json()['storage_fault']['sqlite_code'] & 255, sqlite3.SQLITE_READONLY)
        self.assertEqual(response.json()['storage_fault']['commit_state'], 'not_confirmed_by_this_error')
        self.assertNotIn('receipt', response.json())
        self.assertNotIn('sqlite3', response.text)
        self.assertNotIn(self.directory.name, response.text)
        self.service.storage._call(lambda conn: conn.execute('PRAGMA query_only=0').fetchone())
        first = self.client.post('/api/rehab/v2/sessions', json=request())
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(self.client.post('/api/rehab/v2/sessions', json=request()).json()['session_id'],
                         first.json()['session_id'])

    def test_native_busy_control_503_preserves_commit_query_and_retry(self):
        base = '/api/rehab/v2/sessions'
        sid = self.client.post(base, json=request()).json()['session_id']
        payload = dict(idempotency_key='TEST-pause', expected_revision=0)
        with closing(sqlite3.connect(self.service.database, timeout=0.)) as blocker:
            blocker.execute('BEGIN IMMEDIATE')
            response = self.client.post(base+'/'+sid+'/pause', json=payload)
            self.assertEqual(response.status_code, 503, response.text)
            self.assertEqual(response.json()['detail'], 'formal_store_busy')
            state = self.client.get(base+'/'+sid+'/commit')
            self.assertEqual(state.status_code, 200)
            self.assertIsNone(state.json()['receipt'])
            self.assertEqual(self.client.get(base+'/'+sid).json()['revision'], 0)
            blocker.rollback()
        result = self.client.post(base+'/'+sid+'/pause', json=payload)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(self.client.post(base+'/'+sid+'/pause', json=payload).json(), result.json())


if __name__ == '__main__':
    unittest.main()
