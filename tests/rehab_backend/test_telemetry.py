"""Engineering diagnostics cannot manufacture measurements or training facts."""
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'rehab_codex_single_camera_v2_1'))
from app.domain import PoseFrame
from app.rehab_v2.sessions import SessionError
from app.rehab_v2.telemetry import SessionTelemetry, SAMPLE_LIMIT, EVENT_LIMIT, percentiles
from mobile_rehab.rehab_v2.service import SessionService
from tools.rehab_ml.common import paths
from test_sessions import frozen_plan, request
from test_isolation import wait_until


class TelemetryTests(unittest.TestCase):
    def setUp(self):
        self.trace = SessionTelemetry('TEST-trace', 'TEST-session', 'rehab-protocol-2.0')

    def test_empty_and_disabled_stages_are_unknown_not_zero(self):
        value = self.trace.snapshot()
        self.assertIsNone(value['stages']['inference_ms']['p95_ms'])
        self.assertIsNone(value['stages']['temporal_ms']['p50_ms'])
        self.assertFalse(value['temporal_model']['enabled'])
        self.assertIsNone(value['host_rates']['accepted']['hz'])
        self.assertIsNone(value['job_id'])

    def test_bounded_windows_do_not_claim_whole_run_percentiles(self):
        for i in range(700):
            self.trace.observe('inference_ms', i)
            self.trace.event('accepted', seq=i)
            self.trace.arrival('accepted', i/10., queue_depth=1)
        value = self.trace.snapshot()
        stage = value['stages']['inference_ms']
        self.assertEqual(stage['total_samples'], 700)
        self.assertEqual(stage['retained_samples'], SAMPLE_LIMIT)
        self.assertEqual(stage['p50_ms'], 443.)
        self.assertEqual(stage['p95_ms'], 674.)
        self.assertEqual(len(value['events']), EVENT_LIMIT)
        self.assertEqual(value['counters']['accepted'], 700)
        self.assertAlmostEqual(value['host_rates']['accepted']['hz'], 10.)
        self.assertEqual(value['max_retained_queue_depth'], 1)

    def test_fixed_enums_finite_numbers_and_no_text_payloads(self):
        for invalid in (True, float('nan'), float('inf'), -1, 'secret'):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.trace.observe('inference_ms', invalid)
        with self.assertRaises(ValueError):
            self.trace.event('private-user-note')
        with self.assertRaises(ValueError):
            self.trace.observe('dynamic-name', 1.)
        with self.assertRaises(ValueError):
            self.trace.event('accepted', seq='private')
        with self.assertRaises(ValueError):
            self.trace.arrival('accepted', 1., queue_depth=2)
        self.trace.arrival('accepted', 2.)
        with self.assertRaises(ValueError):
            self.trace.arrival('accepted', 1.)
        json.dumps(self.trace.snapshot(), allow_nan=False)

    def test_concurrent_snapshot_is_bounded_and_does_not_mutate_source(self):
        def write(_):
            for i in range(250):
                self.trace.observe('rules_ms', i)
                self.trace.event('processed', seq=i)
                self.trace.snapshot()
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(write, range(4)))
        value = self.trace.snapshot()
        self.assertEqual(value['stages']['rules_ms']['total_samples'], 1000)
        self.assertEqual(value['counters']['processed'], 1000)
        value['events'].clear()
        value['counters']['processed'] = -1
        self.assertEqual(len(self.trace.snapshot()['events']), EVENT_LIMIT)
        self.assertEqual(self.trace.snapshot()['counters']['processed'], 1000)

    def test_span_records_failure_duration_without_success_counter(self):
        with self.assertRaises(RuntimeError):
            with self.trace.span('final_commit_ms'):
                raise RuntimeError('TEST failure')
        value = self.trace.snapshot()
        self.assertEqual(value['stages']['final_commit_ms']['total_samples'], 1)
        self.assertEqual(value['counters']['commit_success'], 0)
        self.assertEqual(percentiles([1., 2., 3.])['p50_ms'], 2.)


class ServiceTelemetryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=paths()['run'])
        self.database = Path(self.directory.name)/'diagnostics.sqlite3'
        self.service = SessionService(self.database, frozen_plan, internal_replay=True)
        self.owner = 'TEST-owner'
        self.item = self.service.create(self.owner, request())
        self.sid = self.item['session_id']

    def tearDown(self):
        self.service.close()
        self.directory.cleanup()

    def finish(self):
        return self.service.finish(self.owner, self.sid, dict(idempotency_key='finish', expected_revision=0))

    def test_trace_stable_on_create_retry_restart_and_owner_protected(self):
        trace = self.item['source']['execution_trace_id']
        self.assertEqual(len(trace), 32)
        self.assertEqual(self.service.create(self.owner, request())['source']['execution_trace_id'], trace)
        with self.assertRaisesRegex(SessionError, 'session_not_found'):
            self.service.diagnostics('wrong-owner', self.sid)
        self.finish()
        self.service.close()
        self.service = SessionService(self.database, frozen_plan, internal_replay=True)
        value = self.service.diagnostics(self.owner, self.sid)
        self.assertEqual(value['trace_id'], trace)
        self.assertFalse(value['available'])
        self.assertIsNone(value['stages'])
        self.assertIsNone(value['counters'])

    def test_repeated_diagnostics_and_finish_do_not_change_fact_or_contribution(self):
        receipt = self.finish()
        before = self.service.repository.get(self.owner, self.sid)['snapshot']
        for _ in range(10):
            value = self.service.diagnostics(self.owner, self.sid)
            self.assertIsNone(value['stages']['inference_ms']['p95_ms'])
        self.assertEqual(self.finish(), receipt)
        self.assertEqual(self.service.repository.get(self.owner, self.sid)['snapshot'], before)
        value = self.service.diagnostics(self.owner, self.sid)
        self.assertEqual(value['counters']['commit_success'], 1)
        self.assertEqual(value['stages']['final_commit_ms']['total_samples'], 1)
        self.assertEqual(self.service.commit(self.owner, self.sid)['receipt'], receipt)

    def test_report_delay_does_not_block_query_or_control(self):
        entered, release = threading.Event(), threading.Event()
        def report(item):
            entered.set()
            release.wait(6.)
            return SessionService._report(item)
        self.service.report_builder = report
        self.finish()
        self.assertTrue(entered.wait(1.))
        try:
            started = time.monotonic()
            value = self.service.diagnostics(self.owner, self.sid)
            self.assertEqual(self.finish()['status'], 'finalized')
            self.assertLess(time.monotonic()-started, .5)
            self.assertIsNone(value['stages']['report_ms']['p95_ms'])
        finally:
            release.set()
        wait_until(lambda: self.service.diagnostics(self.owner, self.sid)['stages']['report_ms']['total_samples'] > 0)

    def test_latest_frame_replacement_and_old_epoch_counted_without_observed_facts(self):
        self.service.close()
        entered, release = threading.Event(), threading.Event()
        def delayed(value, runtime):
            entered.set()
            release.wait(3.)
            return PoseFrame(runtime.context, value['seq'], value['source_time_s'], (64, 64), [])
        self.database = Path(self.directory.name)/'jpeg.sqlite3'
        self.service = SessionService(self.database, frozen_plan, inference_provider=delayed)
        self.sid = self.service.create(self.owner, request())['session_id']
        from PIL import Image
        buffer = BytesIO()
        Image.new('RGB', (64, 64), 'white').save(buffer, format='JPEG')
        encoded = buffer.getvalue()
        try:
            self.service.submit_jpeg(self.owner, self.sid, 'frame1', 1, encoded)
            self.assertTrue(entered.wait(1.))
            self.service.submit_jpeg(self.owner, self.sid, 'frame2', 2, encoded)
            self.service.submit_jpeg(self.owner, self.sid, 'frame3', 3, encoded)
            value = self.service.diagnostics(self.owner, self.sid)
            self.assertEqual(value['backlog']['retained_frames'], 1)
            self.assertTrue(value['backlog']['in_flight'])
            self.assertEqual(value['counters']['latest_replaced'], 1)
            self.service.control(self.owner, self.sid, 'pause', dict(idempotency_key='pause', expected_revision=0))
            self.service.control(self.owner, self.sid, 'resume', dict(idempotency_key='resume', expected_revision=1))
            release.set()
            wait_until(lambda: self.service.frames.unfinished_tasks == 0)
            value = self.service.diagnostics(self.owner, self.sid)
            self.assertEqual(value['counters']['accepted'], 3)
            self.assertEqual(value['counters']['epoch_discarded'], 2)
            self.assertEqual(value['counters']['processed'], 0)
            self.assertEqual(self.service.get(self.owner, self.sid)['snapshot']['completed'], 0)
            self.assertIsNone(value['stages']['inference_ms']['p95_ms'])  # Injected provider is not YOLO timing.
            self.assertEqual(value['stages']['pose_roundtrip_ms']['total_samples'], 1)
            self.assertNotIn('TEST-owner', json.dumps(value))
            self.assertNotIn('encoded', json.dumps(value))
        finally:
            release.set()


if __name__ == '__main__':
    unittest.main()
