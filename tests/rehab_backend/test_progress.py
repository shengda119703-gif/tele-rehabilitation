import copy
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'rehab_codex_single_camera_v2_1'))
from tools.rehab_ml.common import paths
from app.rehab_v2.progress import plan_progress, progress_views, eligibility_views
from app.rehab_v2.sessions import SessionError
from mobile_rehab.rehab_v2.service import SessionService
from test_protocols import Replay


def record(owner):
    return dict(id='TEST-progress-plan', revision=3, participant_id=owner,
                source_kind='SYNTHETIC', usage_context='TEST',
                items=[dict(key='shoulder_abduction:left', exercise_id='shoulder_abduction', side='left',
                            settings=dict(target_reps=1, target_sets=1)),
                       dict(key='sit_to_stand:left', exercise_id='sit_to_stand', side='left',
                            settings=dict(target_reps=1, target_sets=1))])


def resolver(owner, request):
    saved = record(owner)
    entry = saved['items'][0]
    scope = {key: saved[key] for key in ('participant_id', 'source_kind', 'usage_context')}
    return dict(plan_id=saved['id'], plan_revision=3, entry_key=entry['key'], progress_scope=scope,
                reference=dict(scope, id=saved['id'], revision=3, entry_key=entry['key'], item=entry),
                plan=dict(exercise_id='shoulder_abduction', side='left', participant_id=owner,
                          target_reps=1, target_sets=1, target_angle_deg=None, submode='training'))


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=paths()['run'])
        self.database = Path(self.directory.name)/'progress.sqlite3'
        self.service = SessionService(self.database, resolver, internal_replay=True)
        self.owner = 'TEST-progress-owner'

    def tearDown(self):
        self.service.close()
        self.directory.cleanup()

    def create(self, key='create', owner=None):
        return self.service.create(owner or self.owner, dict(idempotency_key=key, consent=True))['session_id']

    def complete(self, sid):
        replay = Replay()
        for value, count in ((0., 30), (70., 10), (0., 10)):
            for _ in range(count):
                replay.feed(value, 1)
                self.service.submit_evidence(self.owner, sid, 'TEST-frame-'+str(replay.seq), replay.frame)
        return self.service.finish(self.owner, sid, dict(idempotency_key='finish', expected_revision=0, reason='completed'))

    def items(self):
        return self.service.repository.plan_items(self.owner, record(self.owner)['id'], 3)

    def feedback(self, sid, pain=0, fatigue=2, revision=0, key='feedback'):
        return self.service.feedback(self.owner, sid, dict(idempotency_key=key, expected_revision=revision,
            feedback=dict(pain=pain, fatigue=fatigue, reason='completed')))

    def test_C15_C19_unique_execution_and_feedback_only_recomputes_continuation(self):
        sid = self.create()
        receipt = self.complete(sid)
        before = self.service.get(self.owner, sid)
        initial = plan_progress(record(self.owner), [], self.items())
        self.assertEqual(initial['completed'], 1)
        self.assertEqual(initial['next_key'], 'sit_to_stand:left')
        self.assertTrue(initial['blocked'])  # No self report has been invented.
        self.feedback(sid, pain=None)
        self.assertTrue(plan_progress(record(self.owner), [], self.items())['blocked'])
        self.feedback(sid, revision=1, key='complete-feedback')
        ready = plan_progress(record(self.owner), [], self.items())
        self.assertEqual(ready['blocked'], '')
        self.assertEqual(ready['completed'], 1)
        self.assertIsNone(ready['items'][0]['quality'])
        self.assertEqual(ready['items'][0]['v2_observed_quality'][0]['completion_status'], 'COMPLETE')
        self.feedback(sid, pain=1, revision=2, key='pain-update')
        blocked = plan_progress(record(self.owner), [], self.items())
        self.assertTrue(blocked['blocked'])
        self.assertEqual(blocked['completed'], 1)
        after = self.service.get(self.owner, sid)
        self.assertEqual(before['snapshot'], after['snapshot'])
        self.assertEqual(before['plan_contribution'], after['plan_contribution'])
        self.assertEqual(after['canonical_commit'], receipt)
        self.assertEqual(self.service.storage.list_sessions(), [])  # No legacy measurements written.

    def test_fact_and_contribution_roll_back_together_then_retry(self):
        sid = self.create()
        self.service.storage._call(lambda conn: conn.execute('''
            CREATE TRIGGER TEST_fail_contribution BEFORE INSERT ON rehab_v2_plan_contributions
            BEGIN SELECT RAISE(ABORT,'TEST_contribution_write_failure'); END
        '''))
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'TEST_contribution_write_failure'):
            self.service.finish(self.owner, sid, dict(idempotency_key='finish', expected_revision=0))
        state = self.service.get(self.owner, sid)
        self.assertEqual(state['persistence_state'], 'draft')
        self.assertIsNone(state['canonical_commit'])
        self.assertIsNone(state['plan_contribution'])
        self.assertEqual(self.service.history(self.owner)['items'], [])
        self.service.storage._call(lambda conn: conn.execute('DROP TRIGGER TEST_fail_contribution'))
        receipt = self.service.finish(self.owner, sid, dict(idempotency_key='finish', expected_revision=0))
        self.assertEqual(self.service.commit(self.owner, sid)['plan_contribution']['commit_id'], receipt['commit_id'])

    def test_schema1_backup_backfill_keeps_final_receipt_and_visual_evidence(self):
        sid = self.create()
        self.complete(sid)
        before = self.service.get(self.owner, sid)
        self.service.close()
        with closing(sqlite3.connect(self.database)) as conn:
            conn.execute('DROP TABLE rehab_v2_plan_contributions')
            conn.execute('UPDATE rehab_v2_meta SET version=1')
            conn.commit()
        old_backups = set(self.database.parent.glob(self.database.name+'.before-rehab-v2-*.bak'))
        self.service = SessionService(self.database, resolver, internal_replay=True)
        after = self.service.get(self.owner, sid)
        self.assertEqual(before['canonical_commit'], after['canonical_commit'])
        self.assertEqual(before['snapshot'], after['snapshot'])
        self.assertEqual(before['plan_contribution'], after['plan_contribution'])
        new_backups = set(self.database.parent.glob(self.database.name+'.before-rehab-v2-*.bak'))-old_backups
        self.assertEqual(len(new_backups), 1)
        with closing(sqlite3.connect(next(iter(new_backups)))) as conn:
            self.assertEqual(conn.execute('SELECT version FROM rehab_v2_meta').fetchone()[0], 1)
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        self.assertEqual(self.service.storage._call(lambda conn: conn.execute('PRAGMA user_version').fetchone()[0]), 4)

    def test_progress_owner_revision_scope_and_latest_incomplete_do_not_fall_back(self):
        sid = self.create()
        self.complete(sid)
        self.feedback(sid)
        self.assertEqual(plan_progress(record(self.owner), [], self.items())['completed'], 1)
        changed = copy.deepcopy(record(self.owner))
        changed['revision'] = 4
        self.assertEqual(progress_views(self.items(), changed), [])
        changed = copy.deepcopy(record(self.owner))
        changed['usage_context'] = 'SELF_USE'
        self.assertEqual(progress_views(self.items(), changed), [])
        self.assertEqual(self.service.repository.plan_items('other-owner', record(self.owner)['id'], 3), [])
        newer = self.create('next-attempt')
        self.service.finish(self.owner, newer, dict(idempotency_key='finish-new', expected_revision=0))
        latest = plan_progress(record(self.owner), [], self.items())
        self.assertEqual(latest['completed'], 0)
        self.assertEqual(latest['items'][0]['session_id'], newer)

    def test_paginated_history_is_owned_bounded_final_facts_not_report_files(self):
        sessions = []
        for number in range(3):
            sid = self.create('history-'+str(number))
            sessions.append(sid)
            self.service.finish(self.owner, sid, dict(idempotency_key='finish-'+str(number), expected_revision=0))
        draft = self.create('draft')
        page = self.service.history(self.owner, limit=2)
        self.assertEqual(len(page['items']), 2)
        self.assertIsNotNone(page['next_cursor'])
        tail = self.service.history(self.owner, limit=2, before=page['next_cursor'])
        self.assertEqual(len(tail['items']), 1)
        self.assertIsNone(tail['next_cursor'])
        self.assertEqual({item['session_id'] for item in page['items']+tail['items']}, set(sessions))
        self.assertEqual(self.service.history('other-owner')['items'], [])
        with self.assertRaisesRegex(SessionError, 'session_not_found'):
            self.service.history('other-owner', before=page['next_cursor'])
        with self.assertRaisesRegex(SessionError, 'history_cursor_not_finalized'):
            self.service.history(self.owner, before=draft)
        with self.assertRaises(SessionError):
            self.service.history(self.owner, limit=101)

    def test_restart_interrupted_keeps_execution_not_completed_plan(self):
        sid = self.create()
        # A real durable checkpoint is recovered, not a memory-only fixture.
        replay = Replay()
        replay.feed(0., 30)
        self.service.submit_evidence(self.owner, sid, 'TEST-preparation', replay.frame)
        self.service.close(graceful=False)
        self.service = SessionService(self.database, resolver, internal_replay=True)
        value = self.service.commit(self.owner, sid)
        self.assertEqual(value['receipt']['end_reason'], 'interrupted')
        self.assertFalse(value['plan_contribution']['plan_completed'])
        self.assertEqual(len(self.service.history(self.owner)['items']), 1)

    def test_commit_order_not_utc_or_random_uuid_selects_latest_attempt(self):
        first = self.create()
        with patch('app.rehab_v2.sessions.utc_now', return_value='2031-01-01T00:00:00+00:00'):
            self.complete(first)
        self.feedback(first)
        second = self.create('second')
        with patch('app.rehab_v2.sessions.utc_now', return_value='2030-01-01T00:00:00+00:00'):
            self.service.finish(self.owner, second, dict(idempotency_key='stop', expected_revision=0))
        self.assertEqual(self.items()[0]['session_id'], second)
        self.assertEqual(self.service.history(self.owner)['items'][0]['session_id'], second)
        latest = self.service.repository.scope_items(self.owner, record(self.owner))
        self.assertEqual(latest[0]['session_id'], second)

    def test_discomfort_scope_lookup_crosses_plan_version_but_not_other_person(self):
        first = self.create()
        self.complete(first)
        self.feedback(first, pain=2)
        changed_record = record(self.owner)
        changed_record.update(id='TEST-new-plan', revision=1)
        items = self.service.repository.scope_items(self.owner, changed_record)
        views = eligibility_views(items)
        self.assertEqual(views[0]['training_feedback']['pain'], 2)
        self.assertEqual(views[0]['saved_plan_reference']['id'], record(self.owner)['id'])
        self.assertEqual(progress_views(items, changed_record), [])  # Not a new-plan completion.
        self.assertEqual(self.service.repository.scope_items('other-owner', changed_record), [])

    def test_verified_plan_scope_mismatch_rejected_before_persistence(self):
        def invalid_scope(owner, request):
            frozen = resolver(owner, request)
            frozen['progress_scope']['source_kind'] = 'LIVE_CAMERA'
            return frozen
        self.service.plan_resolver = invalid_scope
        with self.assertRaisesRegex(SessionError, 'actual_input_does_not_match_plan_scope'):
            self.create()
        self.assertEqual(self.service.storage._call(lambda conn: conn.execute(
            'SELECT COUNT(*) FROM rehab_v2_sessions').fetchone()[0]), 0)

    def test_missing_or_invalid_mode_cannot_leave_a_persisted_unconstructable_session(self):
        for mode in (None, 'guided', {}, False):
            def invalid_mode(owner, request):
                frozen = resolver(owner, request)
                frozen['plan']['submode'] = mode
                return frozen
            self.service.plan_resolver = invalid_mode
            with self.assertRaisesRegex(SessionError, 'explicit_session_submode_required'):
                self.create()
        self.assertEqual(self.service.storage._call(lambda conn: conn.execute(
            'SELECT COUNT(*) FROM rehab_v2_sessions').fetchone()[0]), 0)


if __name__ == '__main__':
    unittest.main()
