from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'rehab_codex_single_camera_v2_1'))
from tools.rehab_ml.common import paths
from mobile_rehab.rehab_v2.service import SessionService
from app.rehab_v2.sessions import SessionError
from app.rehab_v2.evidence import EvidenceFrame, MetricEvidence
from test_protocols import Replay


def frozen_plan(owner, request):
    if request.get('expected_plan_revision') != 7:
        raise SessionError('plan_revision_conflict')
    return dict(plan_id='TEST-plan', plan_revision=7, entry_key='shoulder_abduction:left',
                reference=dict(owner=owner, record_origin='manual', fixture=True),
                plan=dict(exercise_id='shoulder_abduction', side='left', target_reps=2,
                          target_sets=1, target_angle_deg=60., submode='training'))


def request(key='create'):
    return dict(idempotency_key=key, expected_plan_revision=7, plan_id='TEST-plan', consent=True)


def wait_report(service, owner, sid, state):
    deadline = time.monotonic()+3.
    while time.monotonic() < deadline:
        item = service.get(owner, sid)
        if item['derived_report_state'] == state:
            return item
        time.sleep(.01)
    raise AssertionError(item['derived_report_state'])


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=paths()['run'])
        self.database = Path(self.directory.name) / 'sessions.sqlite3'
        self.service = SessionService(self.database, frozen_plan, internal_replay=True)
        self.owner = 'TEST-owner'

    def tearDown(self):
        self.service.close()
        self.directory.cleanup()

    def create(self):
        return self.service.create(self.owner, request())['session_id']

    def cycle(self, sid):
        replay = Replay()
        for value, count in ((0., 30), (70., 10), (0., 10)):
            for _ in range(count):
                replay.feed(value, 1)
                self.service.submit_evidence(self.owner, sid, 'frame-'+str(replay.seq), replay.frame)

    def finish(self, sid, key='finish'):
        return self.service.finish(self.owner, sid, dict(idempotency_key=key, expected_revision=0, reason='user_stopped'))

    def test_C14_lost_create_response_retries_before_current_plan_check(self):
        first = self.service.create(self.owner, request())
        self.service.plan_resolver = lambda owner, value: (_ for _ in ()).throw(RuntimeError('plan changed'))
        second = self.service.create(self.owner, request())
        self.assertEqual(first['session_id'], second['session_id'])

    def test_C15_parallel_finish_retries_changed_keys_one_fact(self):
        sid = self.create()
        self.cycle(sid)
        with ThreadPoolExecutor(max_workers=8) as pool:
            receipts = list(pool.map(lambda i: self.finish(sid, 'finish-'+str(i)), range(8)))
        self.assertEqual(len({r['commit_id'] for r in receipts}), 1)
        self.assertEqual(receipts[0]['completed_reps'], 1)
        self.assertEqual(self.finish(sid, 'finish-0')['commit_id'], receipts[0]['commit_id'])
        audit = self.service.repository.audit_view(self.owner, sid)
        self.assertEqual(len([r for r in audit['repetitions'] if r['completion_status'] == 'COMPLETE']), 1)
        self.assertEqual(len([a for a in audit['audit'] if a['kind'] == 'finalize']), 1)
        contribution = self.service.repository.plan_contribution(self.owner, sid)
        self.assertEqual(contribution['commit_id'], receipts[0]['commit_id'])
        self.assertEqual(contribution['completed_reps'], 1)
        self.assertFalse(contribution['plan_completed'])  # Prescribed two, only one confirmed.
        self.assertEqual(self.service.storage._call(lambda conn: conn.execute(
            'SELECT COUNT(*) FROM rehab_v2_plan_contributions WHERE session_id=?', (sid,)).fetchone()[0]), 1)

    def test_C16_same_create_or_finish_key_different_payload_conflicts(self):
        sid = self.create()
        with self.assertRaisesRegex(SessionError, 'idempotency_payload_conflict'):
            self.service.create(self.owner, dict(request(), consent=False))
        self.finish(sid)
        with self.assertRaisesRegex(SessionError, 'idempotency_payload_conflict'):
            self.service.finish(self.owner, sid, dict(idempotency_key='finish', expected_revision=0, reason='completed'))

    def test_C17_report_failure_does_not_roll_back_fact_and_can_rebuild(self):
        sid = self.create()
        self.cycle(sid)
        self.service.report_builder = lambda item: (_ for _ in ()).throw(OSError('injected report failure'))
        receipt = self.finish(sid)
        wait_report(self.service, self.owner, sid, 'failed')
        query = self.service.commit(self.owner, sid)
        self.assertEqual(query['receipt']['commit_id'], receipt['commit_id'])
        self.assertEqual(query['persistence_state'], 'finalized')
        self.assertEqual(query['derived_report_state'], 'failed')
        self.service.report_builder = self.service._report
        self.assertEqual(self.service.rebuild_report(self.owner, sid)['state'], 'ready')
        self.assertEqual(self.service.commit(self.owner, sid)['receipt'], receipt)

    def test_C18_restart_retains_confirmed_rep_but_never_resumes_half(self):
        sid = self.create()
        self.cycle(sid)
        replay = Replay()
        replay.seq, replay.t = 50, 2.5
        for i in range(6):
            replay.feed(70., 1)
            self.service.submit_evidence(self.owner, sid, 'half-'+str(i), replay.frame)
        self.assertIsNotNone(self.service.get(self.owner, sid)['snapshot']['current'])
        self.service.close(graceful=False)
        self.service = SessionService(self.database, frozen_plan, internal_replay=True)
        item = self.service.get(self.owner, sid)
        self.assertEqual(item['end_reason'], 'interrupted')
        self.assertEqual(item['snapshot']['completed'], 1)
        self.assertEqual(item['persistence_state'], 'finalized')
        self.assertIsNone(item['snapshot']['current'])
        self.assertEqual(item['snapshot']['repetitions'][-1]['reason'], 'process_restart_interrupted')
        self.assertEqual(item['snapshot']['repetitions'][-1]['completion_status'], 'UNASSESSABLE')
        with self.assertRaises(SessionError):
            self.service.control(self.owner, sid, 'resume', dict(idempotency_key='resume', expected_revision=item['revision']))

    def test_C18_real_process_exit_has_same_durable_recovery(self):
        database = Path(self.directory.name) / 'process-probe.sqlite3'
        result = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'tools/rehab_ml/crash_probe.py'),
                                 '--database', str(database)], cwd=ROOT, capture_output=True,
                                text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 27, result.stderr)
        sid = json.loads(result.stdout.strip())['session_id']
        recovery = SessionService(database, frozen_plan, internal_replay=True)
        try:
            item = recovery.get('TEST-crash-owner', sid)
            self.assertEqual(item['snapshot']['completed'], 1)
            self.assertEqual(item['end_reason'], 'interrupted')
            self.assertEqual(item['run_state'], 'ended')
        finally:
            recovery.close()

    def test_C19_feedback_missing_then_appended_without_rewriting_visual(self):
        sid = self.create()
        self.cycle(sid)
        receipt = self.finish(sid)
        before = self.service.get(self.owner, sid)
        self.assertEqual(before['feedback_status'], 'missing')
        self.assertNotIn('latest_feedback', before)
        payload = dict(idempotency_key='feedback', expected_revision=0,
                       feedback=dict(pain=None, fatigue=3, reason='completed'))
        response = self.service.feedback(self.owner, sid, payload)
        self.assertIsNone(response['pain'])
        self.assertEqual(response['fatigue'], 3)
        self.assertEqual(self.service.feedback(self.owner, sid, payload), response)
        after = self.service.get(self.owner, sid)
        self.assertEqual(before['snapshot'], after['snapshot'])
        self.assertEqual(after['canonical_commit'], receipt)

    def test_owner_and_event_id_binding(self):
        sid = self.create()
        with self.assertRaisesRegex(SessionError, 'session_not_found'):
            self.service.get('different-owner', sid)
        replay = Replay()
        replay.feed(0., 1)
        self.service.submit_evidence(self.owner, sid, 'same', replay.frame)
        duplicate = self.service.submit_evidence(self.owner, sid, 'same', replay.frame)
        self.assertTrue(duplicate['duplicate'])
        with self.assertRaisesRegex(SessionError, 'frame_payload_conflict'):
            self.service.submit_evidence(self.owner, sid, 'same', replace(replay.frame, seq=2))

    def test_pause_resume_idempotency_and_revision(self):
        sid = self.create()
        payload = dict(idempotency_key='pause', expected_revision=0)
        response = self.service.control(self.owner, sid, 'pause', payload)
        self.assertEqual(response['run_state'], 'paused')
        self.assertEqual(self.service.control(self.owner, sid, 'pause', payload), response)
        resumed = self.service.control(self.owner, sid, 'resume', dict(idempotency_key='resume', expected_revision=1))
        self.assertEqual(resumed['run_state'], 'recovering')
        self.assertEqual(resumed['revision'], 2)

    def test_os_lease_blocks_second_host_recovering_live_draft(self):
        sid = self.create()
        with self.assertRaisesRegex(SessionError, 'formal_session_store_already_owned'):
            SessionService(self.database, frozen_plan)
        self.assertEqual(self.service.get(self.owner, sid)['persistence_state'], 'draft')

    def test_pending_or_failed_report_rebuilt_on_restart(self):
        sid = self.create()
        self.cycle(sid)
        self.service.report_builder = lambda item: (_ for _ in ()).throw(OSError('report unavailable'))
        receipt = self.finish(sid)
        wait_report(self.service, self.owner, sid, 'failed')
        self.service.close()
        self.service = SessionService(self.database, frozen_plan, internal_replay=True)
        wait_report(self.service, self.owner, sid, 'ready')
        self.assertEqual(self.service.commit(self.owner, sid)['receipt'], receipt)

    def test_slow_report_does_not_delay_finish_or_overwrite_new_feedback(self):
        sid = self.create()
        entered, released = threading.Event(), threading.Event()
        def report(item):
            if item['feedback_revision'] == 0:
                entered.set()
                released.wait(2.)
            return self.service._report(item)
        self.service.report_builder = report
        try:
            started = time.monotonic()
            receipt = self.finish(sid)
            self.assertLess(time.monotonic()-started, .3)
            self.assertTrue(entered.wait(.5))
            self.service.feedback(self.owner, sid, dict(idempotency_key='feedback', expected_revision=0,
                                  feedback=dict(pain=None, fatigue=2)))
            released.set()
            item = wait_report(self.service, self.owner, sid, 'ready')
            self.assertEqual(item['latest_feedback']['fatigue'], 2)
            self.assertEqual(item['canonical_commit'], receipt)
            payload = self.service.storage._call(lambda conn: json.loads(conn.execute(
                'SELECT payload FROM rehab_v2_reports WHERE session_id=?', (sid,)).fetchone()[0]))
            self.assertEqual(payload['feedback_status'], 'recorded')
        finally:
            released.set()


class FrameBoundaryTests(unittest.TestCase):
    def test_C08_pause_during_inference_drops_before_mutating_ema(self):
        from app.domain import PoseFrame
        with tempfile.TemporaryDirectory(dir=paths()['run']) as directory:
            entered, released = threading.Event(), threading.Event()
            calls = []
            def delayed(value, runtime):
                entered.set()
                released.wait(2.)
                return PoseFrame(runtime.context, value['seq'], value['source_time_s'], (64, 64), [],
                                 model_manifest_id='TEST-real-epoch')
            service = SessionService(Path(directory)/'epoch.sqlite3', frozen_plan, inference_provider=delayed)
            try:
                sid = service.create('TEST-owner', request())['session_id']
                service.runtimes[sid].adapter.analyze = lambda *args, **kwargs: calls.append('mutated')
                from PIL import Image
                stream = BytesIO()
                Image.new('RGB', (64, 64)).save(stream, format='JPEG')
                service.submit_jpeg('TEST-owner', sid, 'frame1', 1, stream.getvalue())
                self.assertTrue(entered.wait(.5))
                tick = time.monotonic()
                service.control('TEST-owner', sid, 'pause', dict(idempotency_key='pause', expected_revision=0))
                self.assertLess(time.monotonic()-tick, .3)
                released.set()
                service.frames.join()
                self.assertEqual(calls, [])
                self.assertEqual(service.repository.audit_view('TEST-owner', sid)['frames'][0]['reason'], 'control_or_terminal_epoch_changed')
            finally:
                released.set()
                service.close()

    def test_inference_failure_finalizes_input_failed_with_one_receipt(self):
        with tempfile.TemporaryDirectory(dir=paths()['run']) as directory:
            def failed(value, runtime):
                raise OSError('injected input decoder failure')
            service = SessionService(Path(directory)/'failed.sqlite3', frozen_plan, inference_provider=failed)
            try:
                sid = service.create('TEST-owner', request())['session_id']
                from PIL import Image
                image = BytesIO()
                Image.new('RGB', (64, 64)).save(image, format='JPEG')
                service.submit_jpeg('TEST-owner', sid, 'frame1', 1, image.getvalue())
                service.frames.join()
                item = service.get('TEST-owner', sid)
                self.assertEqual(item['persistence_state'], 'finalized')
                self.assertEqual(item['end_reason'], 'input_failed')
                self.assertEqual(item['snapshot']['completed'], 0)
                self.assertEqual(service.repository.audit_view('TEST-owner', sid)['frames'][0]['status'], 'failed')
                receipt = service.finish('TEST-owner', sid, dict(idempotency_key='retry', expected_revision=0, reason='user_stopped'))
                self.assertEqual(receipt, item['canonical_commit'])
            finally:
                service.close()

    def test_C23_finish_bounds_inflight_retained_and_ignores_late_results(self):
        temporary = tempfile.TemporaryDirectory(dir=paths()['run'])
        entered, released = threading.Event(), threading.Event()
        def slow_provider(value, runtime):
            entered.set()
            released.wait(2.)
            stamp = value['source_time_s']
            metric = MetricEvidence(0., 'degree', True, None, 'observed', stamp, stamp, 0.,
                                    tuple(runtime.engine.spec['required_joints']))
            return EvidenceFrame(value['seq'], stamp, runtime.context.epoch, 'one', 'coco17-v1',
                                 'TEST-model', (640, 480), {'raise_deg': metric}, 'VALID', 'browser-camera')
        service = SessionService(Path(temporary.name)/'boundary.sqlite3', frozen_plan,
                                 inference_provider=slow_provider, drain_timeout_s=.05)
        owner = 'TEST-owner'
        try:
            sid = service.create(owner, request())['session_id']
            from PIL import Image
            encoded = BytesIO()
            Image.new('RGB', (640, 480), 'white').save(encoded, format='JPEG')
            image = encoded.getvalue()
            service.submit_jpeg(owner, sid, 'frame1', 1, image)
            self.assertTrue(entered.wait(.5))
            service.submit_jpeg(owner, sid, 'frame2', 2, image)
            service.submit_jpeg(owner, sid, 'frame3', 3, image)
            started = time.monotonic()
            receipt = service.finish(owner, sid, dict(idempotency_key='finish', expected_revision=0, reason='user_stopped'))
            self.assertLess(time.monotonic()-started, .5)
            self.assertEqual(receipt['accepted_last_seq'], 3)
            self.assertEqual(receipt['processed_last_seq'], -1)
            audit = service.repository.audit_view(owner, sid)
            self.assertEqual([f['status'] for f in audit['frames']], ['unprocessed', 'dropped', 'unprocessed'])
            before = service.get(owner, sid)['snapshot']
            released.set()
            service.frames.join()
            self.assertEqual(service.get(owner, sid)['snapshot'], before)
            self.assertEqual(service.commit(owner, sid)['receipt'], receipt)
            self.assertEqual(service.get(owner, sid)['snapshot']['completed'], 0)
        finally:
            released.set()
            service.close()
            temporary.cleanup()


if __name__ == '__main__':
    unittest.main()
