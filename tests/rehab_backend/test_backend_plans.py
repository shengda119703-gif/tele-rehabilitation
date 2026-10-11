import copy
from contextlib import closing
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'rehab_codex_single_camera_v2_1'))
from tools.rehab_ml.common import paths
from app.rehab_v2.sessions import SessionError
from app.rehab_v2.reporting import build_report
from mobile_rehab.rehab_v2.service import SessionService
from test_protocols import Replay
from test_sessions import frozen_plan
from http_finish import finish_http


class BackendPlanTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=paths()['run'])
        self.database = Path(self.directory.name)/'plans.sqlite3'
        self.owner = 'TEST-plan-owner'
        self.service = SessionService(self.database, frozen_plan, internal_replay=True, report_builder=build_report)
        self.counter = 0

    def tearDown(self):
        self.service.close()
        self.directory.cleanup()

    def assess(self, eid='rehab_squat', side='left', *, finish=True, complete=True):
        self.counter += 1
        payload = dict(idempotency_key='assessment-'+str(self.counter), consent=True,
            submode='assessment', exercise_id=eid, side=side, view='frontal' if eid == 'shoulder_abduction' else 'sagittal')
        result = self.create(payload)
        sid = result['session_id']
        if complete:
            self.cycle(sid, eid)
        if finish:
            self.service.finish(self.owner, sid, dict(idempotency_key='finish', expected_revision=0, reason='completed'))
        return sid

    def create(self, payload):
        # The actual same-host report preflight can briefly own the main lease.
        # Retry only its explicit busy response, without bypassing admission.
        deadline = time.monotonic()+3
        while True:
            try: return self.service.create(self.owner, payload)
            except SessionError as error:
                if error.code != 'rehab_compute_resource_busy' or time.monotonic() >= deadline:
                    raise
                time.sleep(.01)

    def cycle(self, sid, eid='rehab_squat', *, start_seq=0, start_t=0., peak_frames=10, **quality):
        replay = Replay(eid, side=self.service.runtimes[sid].engine.spec['side'])
        replay.seq, replay.t = start_seq, start_t
        ready, peak = (80., 0.) if eid == 'sit_to_stand' else (0., 45.)
        for value, count in ((ready, 30), (peak, peak_frames), (ready, 10)):
            for _ in range(count):
                stage = getattr(self.service.runtimes[sid].engine, 'training_stage', None)
                if stage in ('RESTING', 'COMPLETE'):
                    return replay.seq, replay.t
                replay.feed(value, 1, **quality)
                self.service.submit_evidence(self.owner, sid, 'frame-'+str(replay.seq), replay.frame)
        return replay.seq, replay.t

    def payload(self, sid, eid='rehab_squat', side='left', key='save'):
        return dict(idempotency_key=key, name='TEST explicit arrangement',
            arrangement=dict(reference='TEST user-provided arrangement, not verified clinical advice', confirmed=True),
            items=[dict(exercise_id=eid, side=side, assessment_session_id=sid,
                settings=dict(target_reps=1, target_sets=1, target_angle_deg=80.,
                              needs_companion=False, use_of_hands='allowed', timing_plan=None))])

    def start(self, plan, key='training', **extra):
        row = plan['items'][0]
        return self.create(dict(idempotency_key=key, consent=True, plan_id=plan['id'],
            expected_plan_revision=plan['revision'], entry_key=row['key'],
            view='frontal' if row['exercise_id'] == 'shoulder_abduction' else 'sagittal',
            training_plan_confirmed=True, **extra))

    def finish(self, sid):
        return self.service.finish(self.owner, sid, dict(idempotency_key='finish', expected_revision=0, reason='completed'))

    def test_three_actions_bind_exact_projection_without_legacy_catalog_or_dose_generation(self):
        for eid, side in ((eid, side) for eid in ('rehab_squat', 'shoulder_abduction', 'sit_to_stand')
                          for side in ('left', 'right')):
            with self.subTest(eid=eid, side=side):
                sid = self.assess(eid, side)
                payload = self.payload(sid, eid, side, key='save-'+eid+'-'+side)
                plan = self.service.save_plan(self.owner, payload)
                result = self.start(plan, key='start-'+eid+'-'+side, target_reps=999, target_sets=20, target_angle_deg=1.)
                frozen = result['frozen_plan']
                self.assertEqual(frozen['plan']['target_reps'], 1)
                self.assertEqual(frozen['plan']['target_sets'], 1)
                self.assertEqual(frozen['plan']['target_angle_deg'], 80.)
                self.assertEqual(frozen['reference']['item'], plan['items'][0])
                self.assertEqual(frozen['plan']['assessment_reference']['session_id'], sid)
                self.assertFalse(plan['automatic_dose'])
                self.assertFalse(plan['arrangement']['independently_verified'])
                self.assertEqual(frozen['plan']['participant_id'], self.owner)
                self.assertEqual(frozen['plan']['side'], side)
                self.cycle(result['session_id'], eid)
                self.assertEqual(self.finish(result['session_id'])['completed_reps'], 1)
                # Explicitly record feedback, no synthetic self-report is auto-filled.
                self.service.feedback(self.owner, result['session_id'], dict(idempotency_key='feedback', expected_revision=0,
                    feedback=dict(pain=0, fatigue=2, reason='completed')))
        self.assertEqual(self.service.storage.list_sessions(), [])
        self.assertEqual(self.service.storage._call(lambda c:c.execute('SELECT COUNT(*) FROM training_plans').fetchone()[0]), 0)
        self.assertEqual(len(self.service.plans_list(self.owner)['items']), 6)
        self.assertEqual(self.service.plans_list('other-owner')['items'], [])
        with self.assertRaisesRegex(SessionError, 'page_size'):
            self.service.plans_list(self.owner, 101)

    def test_host_participant_mapping_is_not_client_owner_or_a_cross_person_assessment(self):
        # Shared hosts bind a trusted participant separately from HTTP owner.
        self.service.participant_provider = lambda owner: 'TEST-shared-participant'
        sid = self.assess(side='right')
        plan = self.service.save_plan(self.owner, self.payload(sid, side='right'))
        self.assertEqual(plan['participant_id'], 'TEST-shared-participant')
        with self.assertRaisesRegex(SessionError, 'session_not_found'):
            self.service.save_plan('other-owner', self.payload(sid, side='right'))
        active = self.start(plan)['session_id']
        self.cycle(active)
        self.assertEqual(self.finish(active)['completed_reps'], 1)
        self.service.feedback(self.owner, active, dict(idempotency_key='feedback', expected_revision=0,
            feedback=dict(pain=0, fatigue=2, reason='completed')))
        self.assertEqual(self.service.plan(self.owner, plan['id'])['progress']['completed'], 1)
        self.service.participant_provider = lambda owner: 'TEST-different-participant'
        self.assertEqual(self.service.plan(self.owner, plan['id'])['progress']['blocked'],
                         'actual_input_does_not_match_plan_scope')
        with self.assertRaisesRegex(SessionError, 'action_or_scope_mismatch'):
            self.service.save_plan(self.owner, self.payload(sid, side='right', key='different-person'))

    def test_required_companion_cannot_be_overridden_and_needs_explicit_confirmation(self):
        sid = self.assess()
        payload = self.payload(sid)
        payload['items'][0]['settings']['needs_companion'] = True
        plan = self.service.save_plan(self.owner, payload)
        with self.assertRaisesRegex(SessionError, 'required_companion_confirmation_missing'):
            self.start(plan, needs_companion=False, use_of_hands='not_allowed')
        active = self.start(plan, companion_confirmed=True, needs_companion=False)['session_id']
        frozen = self.service.get(self.owner, active)['frozen_plan']['plan']
        self.assertTrue(frozen['needs_companion'])
        self.assertEqual(frozen['use_of_hands'], 'allowed')
        self.cycle(active)
        self.assertEqual(self.finish(active)['completed_reps'], 1)
        self.assertEqual(self.service.get(self.owner, active)['feedback_status'], 'missing')

    def test_explicit_shoulder_quality_limits_freeze_and_missing_auxiliary_points_do_not_cancel_count(self):
        for case, elbow, tilt, expected in (('missing', None, None, 'UNASSESSABLE'),
                                            ('observed', 30., 20., 'ISSUES_OBSERVED')):
            with self.subTest(case=case):
                assessment = self.assess('shoulder_abduction', side='right')
                payload = self.payload(assessment, 'shoulder_abduction', 'right', key='quality-'+case)
                settings = payload['items'][0]['settings']
                settings.update(allowed_elbow_flexion_deg=10., allowed_trunk_tilt_deg=8.)
                plan = self.service.save_plan(self.owner, payload)
                active = self.start(plan, key='quality-start-'+case,
                    allowed_elbow_flexion_deg=180., allowed_trunk_tilt_deg=180.)['session_id']
                frozen = self.service.get(self.owner, active)['frozen_plan']['plan']
                self.assertEqual(frozen['allowed_elbow_flexion_deg'], 10.)
                self.assertEqual(frozen['allowed_trunk_tilt_deg'], 8.)
                self.cycle(active, 'shoulder_abduction', peak_frames=30, elbow=elbow, tilt=tilt)
                self.assertEqual(self.finish(active)['completed_reps'], 1)
                record = self.service.get(self.owner, active)
                rep = record['snapshot']['repetitions'][0]
                self.assertEqual(rep['completion_status'], 'COMPLETE')
                self.assertEqual(rep['quality_status'], expected)
                self.assertEqual(record['feedback_status'], 'missing')
                if case == 'missing':
                    self.assertEqual(rep['issues'], [])
                    self.assertFalse(rep['quality_assessable'])
                    for metric in ('elbow_flexion_deg', 'trunk_tilt_deg'):
                        self.assertFalse(rep['metric_validity'][metric]['valid'])
                        self.assertEqual(rep['metric_validity'][metric]['reason'], 'missing_quality_evidence')
                else:
                    self.assertTrue(rep['quality_assessable'])
                    issues = {issue['metric']: issue for issue in rep['issues']}
                    self.assertEqual(set(issues), {'elbow_flexion_deg', 'trunk_tilt_deg'})
                    self.assertEqual(issues['elbow_flexion_deg']['configured_limit'], 10.)
                    self.assertEqual(issues['trunk_tilt_deg']['configured_limit'], 8.)
                    self.assertEqual(issues['elbow_flexion_deg']['measured_value'], elbow)
                    self.assertEqual(issues['trunk_tilt_deg']['measured_value'], tilt)
                # Explicit test feedback permits another independent arrangement;
                # creating it cannot manufacture or clear the previous self-report.
                self.service.feedback(self.owner, active, dict(idempotency_key='quality-feedback', expected_revision=0,
                    feedback=dict(pain=0, fatigue=2, reason='completed')))
                self.assertEqual(self.service.get(self.owner, active)['snapshot'], record['snapshot'])

    def test_quality_limits_reject_unsupported_actions_and_invalid_values_without_plan_writes(self):
        for eid in ('sit_to_stand', 'rehab_squat', 'shoulder_abduction'):
            assessment = self.assess(eid)
            original = self.payload(assessment, eid, key='quality-validate-'+eid)
            before = self.service.storage._call(lambda conn: conn.execute('SELECT COUNT(*) FROM rehab_v2_plans').fetchone()[0])
            for field in ('allowed_elbow_flexion_deg', 'allowed_trunk_tilt_deg'):
                invalids = (10.,) if eid != 'shoulder_abduction' else (True, -1., 181., float('nan'), float('inf'), '10')
                for invalid in invalids:
                    payload = copy.deepcopy(original)
                    payload['items'][0]['settings'][field] = invalid
                    with self.subTest(eid=eid, field=field, invalid=invalid):
                        with self.assertRaises(SessionError) as caught:
                            self.service.save_plan(self.owner, payload)
                        self.assertEqual(caught.exception.status, 400)
                        if eid != 'shoulder_abduction':
                            self.assertEqual(caught.exception.code, 'unsupported_explicit_quality_constraint')
                        self.assertEqual(self.service.storage._call(lambda conn: conn.execute('SELECT COUNT(*) FROM rehab_v2_plans').fetchone()[0]), before)
            unconfigured = copy.deepcopy(original)
            unconfigured['items'][0]['settings'].update(allowed_elbow_flexion_deg=None, allowed_trunk_tilt_deg=None)
            plan = self.service.save_plan(self.owner, unconfigured)
            self.assertIsNone(plan['items'][0]['settings']['allowed_elbow_flexion_deg'])
            self.assertIsNone(plan['items'][0]['settings']['allowed_trunk_tilt_deg'])

    def test_squat_shallow_rep_completes_plan_independent_of_target_then_feedback_blocks_repeat(self):
        assessment = self.assess()
        plan = self.service.save_plan(self.owner, self.payload(assessment))
        sid = self.start(plan)['session_id']
        self.cycle(sid)
        receipt = self.finish(sid)
        item = self.service.get(self.owner, sid)
        self.assertEqual(receipt['completed_reps'], 1)
        self.assertEqual(item['snapshot']['repetitions'][0]['target_status'], 'NOT_MET')
        view = self.service.plan(self.owner, plan['id'])
        self.assertEqual(view['progress']['completed'], 1)
        self.assertIsNone(view['progress']['next_key'])
        self.assertTrue(view['progress']['blocked'])
        self.assertEqual(self.service.finish(self.owner, sid, dict(idempotency_key='another-finish', expected_revision=0)), receipt)
        self.assertEqual(len(self.service.repository.plan_items(self.owner, plan['id'], 1)), 1)
        feedback = dict(idempotency_key='feedback', expected_revision=0, feedback=dict(pain=0, fatigue=2, reason='completed'))
        self.service.feedback(self.owner, sid, feedback)
        self.assertEqual(self.service.feedback(self.owner, sid, feedback)['revision'], 1)
        self.assertEqual(self.service.plan(self.owner, plan['id'])['progress']['blocked'], '')
        with self.assertRaisesRegex(SessionError, 'order_or_completion'):
            self.start(plan, key='repeat-dose')
        self.assertEqual(self.service.get(self.owner, sid)['snapshot'], item['snapshot'])

    def test_newer_failed_assessment_cannot_fall_back_to_old_success(self):
        first = self.assess()
        plan = self.service.save_plan(self.owner, self.payload(first))
        self.assess(complete=False)
        self.assertEqual(self.service.plan(self.owner, plan['id'])['progress']['blocked'], 'newer_assessment_requires_plan_review')
        with self.assertRaisesRegex(SessionError, 'newer_assessment'):
            self.start(plan)
        with self.assertRaisesRegex(SessionError, 'newer_assessment'):
            self.service.save_plan(self.owner, self.payload(first, key='new-plan'))

    def test_missing_draft_training_wrong_side_and_owner_not_assessments(self):
        sid = self.assess(complete=False)
        with self.assertRaisesRegex(SessionError, 'committed_observable'):
            self.service.save_plan(self.owner, self.payload(sid))
        sid = self.assess()
        with self.assertRaisesRegex(SessionError, 'action_or_scope'):
            self.service.save_plan(self.owner, self.payload(sid, side='right'))
        with self.assertRaisesRegex(SessionError, 'session_not_found'):
            self.service.save_plan('other-owner', self.payload(sid))
        draft = self.assess(finish=False)
        with self.assertRaisesRegex(SessionError, 'committed_observable'):
            self.service.save_plan(self.owner, self.payload(draft))
        self.finish(draft)

    def test_commit_hash_scope_protocol_and_review_age_are_checked_not_filename(self):
        sid = self.assess()
        original = self.service.repository.get(self.owner, sid)
        for mutation, code in (
            (lambda i:i['snapshot'].update(completed=99), 'evidence_digest'),
            (lambda i:i['frozen_plan']['protocol'].update(metric_version='other'), 'protocol_changed'),
            (lambda i:i['source'].update(source_kind='REPLAY_FILE'), 'action_or_scope'),
            (lambda i:i['canonical_commit'].update(committed_at=(datetime.now(timezone.utc)-timedelta(days=8)).isoformat()), 'window_expired')):
            changed = copy.deepcopy(original)
            mutation(changed)
            self.service.storage._call(lambda c:c.execute('UPDATE rehab_v2_sessions SET payload=? WHERE id=?',
                                                          (json.dumps(changed), sid)))
            with self.assertRaisesRegex(SessionError, code):
                self.service.save_plan(self.owner, self.payload(sid))
            self.service.storage._call(lambda c:c.execute('UPDATE rehab_v2_sessions SET payload=? WHERE id=?',
                                                          (json.dumps(original), sid)))

    def test_durable_idempotency_revision_archive_and_old_session_binding(self):
        sid = self.assess()
        payload = self.payload(sid)
        plan = self.service.save_plan(self.owner, payload)
        active = self.start(plan)['session_id']
        frozen = self.service.get(self.owner, active)['frozen_plan']
        changed = copy.deepcopy(payload)
        changed.update(idempotency_key='revise', expected_revision=1)
        changed['items'][0]['settings']['target_reps'] = 2
        revised = self.service.save_plan(self.owner, changed, plan_id=plan['id'])
        self.assertEqual(revised['revision'], 2)
        self.assertEqual(self.service.get(self.owner, active)['frozen_plan'], frozen)
        self.finish(active)
        archive = dict(idempotency_key='archive', expected_revision=2)
        archived = self.service.save_plan(self.owner, archive, plan_id=plan['id'], archive=True)
        self.assertEqual(archived['revision'], 3)
        self.service.close()
        self.service = SessionService(self.database, frozen_plan, internal_replay=True, report_builder=build_report)
        self.assertEqual(self.service.save_plan(self.owner, payload), plan)
        self.assertEqual(self.service.save_plan(self.owner, changed, plan_id=plan['id']), revised)
        self.assertEqual(self.service.save_plan(self.owner, archive, plan_id=plan['id'], archive=True), archived)
        self.assertEqual(self.service.plan(self.owner, plan['id'])['plan']['status'], 'ARCHIVED')
        self.assertEqual(self.service.get(self.owner, active)['frozen_plan'], frozen)
        with self.assertRaisesRegex(SessionError, 'idempotency_payload_conflict'):
            self.service.save_plan(self.owner, dict(payload, name='changed'))
        with self.assertRaisesRegex(SessionError, 'revision_conflict'):
            self.service.save_plan(self.owner, dict(changed, idempotency_key='stale'), plan_id=plan['id'])
        with self.assertRaisesRegex(SessionError, 'owned_explicit_plan'):
            self.service.plan('other-owner', plan['id'])

    def test_plan_snapshot_operation_and_revision_rollback_together(self):
        sid = self.assess()
        self.service.storage._call(lambda c:c.execute('''CREATE TRIGGER TEST_plan_fail BEFORE INSERT ON rehab_v2_plan_operations
            BEGIN SELECT RAISE(ABORT,'TEST-plan-failure'); END'''))
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'TEST-plan-failure'):
            self.service.save_plan(self.owner, self.payload(sid))
        for table in ('rehab_v2_plans', 'rehab_v2_plan_revisions', 'rehab_v2_plan_operations'):
            self.assertEqual(self.service.storage._call(lambda c:c.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]), 0)
        self.service.storage._call(lambda c:c.execute('DROP TRIGGER TEST_plan_fail'))
        self.assertEqual(self.service.save_plan(self.owner, self.payload(sid))['revision'], 1)

    def test_concurrent_lost_create_response_has_one_plan_and_receipt(self):
        sid = self.assess()
        payload = self.payload(sid)
        results, failures = [], []
        def save():
            try: results.append(self.service.save_plan(self.owner, payload))
            except Exception as exc: failures.append(exc)
        threads = [threading.Thread(target=save) for _ in range(4)]
        for t in threads: t.start()
        for t in threads: t.join(10)
        self.assertFalse(any(t.is_alive() for t in threads))
        self.assertEqual(failures, [])
        self.assertEqual(len(results), 4)
        self.assertTrue(all(r == results[0] for r in results))
        self.assertEqual(self.service.storage._call(lambda c:c.execute('SELECT COUNT(*) FROM rehab_v2_plans').fetchone()[0]), 1)

    def test_explicit_fields_dose_companion_and_no_unsupported_rule_overrides(self):
        sid = self.assess()
        original = self.payload(sid)
        for field, bad in (('target_reps', None), ('target_sets', True), ('use_of_hands', 'assumed'),
                           ('needs_companion', 1), ('target_angle_deg', float('nan')), ('ready_s', .01)):
            payload = copy.deepcopy(original)
            payload['items'][0]['settings'][field] = bad
            with self.assertRaises((SessionError, ValueError)):
                self.service.save_plan(self.owner, payload)
        payload = copy.deepcopy(original)
        payload['items'][0]['settings']['needs_companion'] = True
        plan = self.service.save_plan(self.owner, payload)
        with self.assertRaisesRegex(SessionError, 'companion'):
            self.start(plan)
        item = self.start(plan, companion_confirmed=True)
        self.finish(item['session_id'])

    def test_namespace_migration_has_consistent_backup_and_keeps_old_facts(self):
        sid = self.assess()
        old = self.service.get(self.owner, sid)
        self.service.close()
        with closing(sqlite3.connect(self.database)) as conn:
            for name in ('rehab_v2_plan_meta', 'rehab_v2_plans', 'rehab_v2_plan_revisions', 'rehab_v2_plan_operations'):
                conn.execute('DROP TABLE '+name)
            conn.commit()
        backups = set(self.database.parent.glob('*.before-explicit-plans-*.bak'))
        self.service = SessionService(self.database, frozen_plan, internal_replay=True, report_builder=build_report)
        added = set(self.database.parent.glob('*.before-explicit-plans-*.bak'))-backups
        self.assertEqual(len(added), 1)
        with closing(sqlite3.connect(next(iter(added)))) as conn:
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertIsNone(conn.execute("SELECT name FROM sqlite_master WHERE name='rehab_v2_plans'").fetchone())
        self.assertEqual(self.service.get(self.owner, sid)['snapshot'], old['snapshot'])
        self.assertEqual(self.service.get(self.owner, sid)['canonical_commit'], old['canonical_commit'])
        self.assertEqual(self.service.storage._call(lambda c:c.execute('PRAGMA user_version').fetchone()[0]), 4)

    def test_prior_discomfort_cannot_be_erased_by_new_plan_or_revision(self):
        assessment = self.assess()
        first = self.service.save_plan(self.owner, self.payload(assessment))
        sid = self.start(first)['session_id']
        self.cycle(sid)
        self.finish(sid)
        self.service.feedback(self.owner, sid, dict(idempotency_key='pain', expected_revision=0,
            feedback=dict(pain=2, fatigue=2, reason='discomfort')))
        newer = self.service.save_plan(self.owner, self.payload(assessment, key='new-plan'))
        with self.assertRaisesRegex(SessionError, 'discomfort'):
            self.start(newer, key='new-after-pain')
        changed = self.payload(assessment, key='revised')
        changed['expected_revision'] = 1
        revised = self.service.save_plan(self.owner, changed, plan_id=newer['id'])
        with self.assertRaisesRegex(SessionError, 'discomfort'):
            self.start(revised, key='revision-after-pain')

    def test_two_sets_recovery_pause_and_return_to_prepare_keep_explicit_dose(self):
        assessment = self.assess()
        payload = self.payload(assessment)
        payload['items'][0]['settings']['target_sets'] = 2
        plan = self.service.save_plan(self.owner, payload)
        sid = self.start(plan)['session_id']
        seq, stamp = self.cycle(sid)
        first = self.service.get(self.owner, sid)
        self.assertEqual(first['snapshot']['training']['completed_sets'], 1)
        self.assertEqual(first['snapshot']['training']['stage'], 'RESTING')
        replay = Replay('rehab_squat')
        replay.seq, replay.t = seq, stamp
        replay.feed(0., 1)
        with self.assertRaisesRegex(SessionError, 'session_not_accepting_frames'):
            self.service.submit_evidence(self.owner, sid, 'paused-frame', replay.frame)
        self.assertEqual(self.service.get(self.owner, sid)['snapshot']['completed'], 1)
        self.service.control(self.owner, sid, 'resume', dict(idempotency_key='next-set', expected_revision=0))
        self.assertIsNone(self.service.get(self.owner, sid)['snapshot']['baseline'])
        self.cycle(sid, start_seq=seq, start_t=stamp)
        receipt = self.service.finish(self.owner, sid, dict(idempotency_key='finish', expected_revision=1))
        self.assertEqual(receipt['completed_reps'], 2)
        self.assertEqual(self.service.get(self.owner, sid)['snapshot']['training']['completed_sets'], 2)
        self.assertTrue(self.service.commit(self.owner, sid)['plan_contribution']['plan_completed'])


class BackendPlanHttpTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from mobile_rehab.server import create_app
        from mobile_rehab.tests.test_mobile import owner
        self.directory = tempfile.TemporaryDirectory(dir=paths()['run'])
        self.app = create_app(self.directory.name, pair_key='TEST-v2-explicit-plan', runner=lambda item: None, rehab_v2=True)
        self.client = TestClient(self.app, headers={'X-Rehab-Client': 'mobile-v1'})
        self.client.__enter__()
        self.client.post('/api/pair', json=dict(code='TEST-v2-explicit-plan'))
        self.owner = owner(self.client)
        self.service = self.app.state.rehab_v2
        self.base = '/api/rehab/v2/sessions'

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.directory.cleanup()

    def create(self, payload):
        deadline = time.monotonic()+3
        while True:
            result = self.client.post(self.base, json=payload)
            if result.status_code != 503 or result.json().get('detail') != 'rehab_compute_resource_busy':
                self.assertEqual(result.status_code, 200, result.text)
                return result.json()
            if time.monotonic() >= deadline:
                self.fail(result.text)
            time.sleep(.01)

    def assess_request(self, key='assessment'):
        return dict(idempotency_key=key, consent=True, submode='assessment', exercise_id='rehab_squat', side='left', view='sagittal')

    def payload(self, sid):
        return dict(idempotency_key='plan-create', name='TEST HTTP explicit squat',
            arrangement=dict(reference='TEST owner-declared existing arrangement', confirmed=True),
            items=[dict(exercise_id='rehab_squat', side='left', assessment_session_id=sid,
                settings=dict(target_reps=1, target_sets=1, target_angle_deg=80., needs_companion=False, use_of_hands='allowed'))])

    def jpeg(self):
        from io import BytesIO
        from PIL import Image
        stream = BytesIO()
        Image.new('RGB', (320, 240), 'white').save(stream, format='JPEG')
        return stream.getvalue()

    def frames(self, sid, count=50):
        encoded = self.jpeg()
        for seq in range(1, count+1):
            result = self.client.post(self.base+'/'+sid+'/frames', content=encoded, headers={
                'content-type':'image/jpeg', 'x-rehab-event-id':'TEST-http-'+str(seq), 'x-rehab-seq':str(seq)})
            self.assertEqual(result.status_code, 200, result.text)
            deadline = time.monotonic()+20
            while self.client.get(self.base+'/'+sid).json()['processed_last_seq'] < seq:
                if time.monotonic() >= deadline:
                    self.fail('owned pose result did not arrive')
                time.sleep(.01)
            time.sleep(.05)

    def finish(self, sid):
        return finish_http(self.client, self.base+'/'+sid, dict(idempotency_key='finish', expected_revision=0, reason='completed'))

    def test_native_jpeg_missing_person_cannot_qualify_a_plan(self):
        item = self.create(self.assess_request())
        sid = item['session_id']
        self.frames(sid, count=1)
        receipt = self.finish(sid)
        self.assertEqual(receipt['completed_reps'], 0)
        self.assertEqual(self.client.get(self.base+'/'+sid).json()['observation_state'], 'missing')
        result = self.client.post('/api/rehab/v2/plans', json=self.payload(sid))
        self.assertEqual(result.status_code, 409, result.text)
        self.assertEqual(result.json()['detail'], 'committed_observable_v2_assessment_required')
        self.assertEqual(self.client.get('/api/rehab/v2/plans').json()['items'], [])
        self.assertFalse(self.service.internal_replay)
        self.assertIsNotNone(self.service.inference_worker.process)

    def test_actual_host_routes_assessment_plan_training_history_and_feedback_not_clinical_accuracy(self):
        from app.rehab_v2.evidence import EvidenceFrame, MetricEvidence
        # TEST-only deterministic geometry provider, NOT a camera accuracy or
        # human assessment. The public JPEG route still rejects supplied points
        # and uses real host receipt time throughout this isolated HTTP run.
        def provider(value, runtime):
            seq, stamp = value['seq'], value['source_time_s']
            angle = 0. if seq <= 30 or seq > 40 else 45.
            metric = MetricEvidence(angle, 'degree', True, None, 'observed', stamp, stamp, 0.,
                                    tuple(runtime.engine.spec['required_joints']))
            return EvidenceFrame(seq, stamp, runtime.context.epoch, 'TEST-fixed-person', 'coco17-v1',
                                 'TEST-http-geometric-provider', (320,240), {'knee_flexion_deg':metric}, 'VALID', 'browser-camera')
        self.service.inference_provider = provider
        sid = self.create(self.assess_request())['session_id']
        self.assertEqual(self.client.post(self.base+'/'+sid+'/frames', json=dict(keypoints=[])).status_code, 415)
        self.frames(sid)
        self.assertEqual(self.finish(sid)['completed_reps'], 1)
        payload = self.payload(sid)
        saved = self.client.post('/api/rehab/v2/plans', json=payload)
        self.assertEqual(saved.status_code, 200, saved.text)
        plan = saved.json()
        self.assertEqual(self.client.post('/api/rehab/v2/plans', json=payload).json(), plan)
        endpoint = '/api/rehab/v2/plans/'+plan['id']
        self.assertEqual(self.client.get(endpoint).json()['progress']['blocked'], '')
        request = dict(idempotency_key='training', consent=True, plan_id=plan['id'], expected_plan_revision=1,
            entry_key='rehab_squat:left', view='sagittal', training_plan_confirmed=True, target_reps=999)
        training = self.create(request)
        tsid = training['session_id']
        self.assertEqual(training['frozen_plan']['plan']['target_reps'], 1)
        self.frames(tsid)
        receipt = self.finish(tsid)
        self.assertEqual(receipt['completed_reps'], 1)
        self.assertEqual(self.client.get(self.base+'/'+tsid+'/commit').json()['receipt'], receipt)
        self.assertEqual(self.client.post(self.base, json=request).json()['session_id'], tsid)
        self.assertTrue(self.client.get(endpoint).json()['progress']['blocked'])
        feedback = dict(idempotency_key='feedback', expected_revision=0, feedback=dict(pain=0, fatigue=2, reason='completed'))
        self.assertEqual(self.client.post(self.base+'/'+tsid+'/feedback', json=feedback).status_code, 200)
        self.assertEqual(self.client.get(endpoint).json()['progress']['completed'], 1)
        self.assertEqual(self.client.get(endpoint).json()['progress']['blocked'], '')
        self.assertEqual(len(self.client.get(self.base).json()['items']), 2)
        self.assertIsNone(self.client.get('/api/plan').json()['plan'])
        self.client.cookies.clear()
        self.assertEqual(self.client.get(endpoint).status_code, 401)
        self.assertEqual(self.client.post('/api/rehab/v2/plans', json=payload).status_code, 401)

    def test_http_version_view_and_owner_cannot_create_or_relabel_an_arrangement(self):
        invalid = dict(self.assess_request(), view='frontal')
        self.assertEqual(self.client.post(self.base, json=invalid).status_code, 400)
        self.assertEqual(self.client.post('/api/rehab/v2/plans', json=self.payload('not-owned')).status_code, 404)
        self.assertEqual(self.client.get('/api/rehab/v2/plans?limit=101').status_code, 400)
        sid = self.create(self.assess_request())['session_id']
        self.finish(sid)
        from fastapi.testclient import TestClient
        other = TestClient(self.app, headers={'X-Rehab-Client':'mobile-v1'})
        try:
            other.post('/api/pair', json=dict(code='TEST-v2-explicit-plan'))
            self.assertEqual(other.post('/api/rehab/v2/plans', json=self.payload(sid)).status_code, 404)
            self.assertEqual(other.get('/api/rehab/v2/plans').json()['items'], [])
        finally:
            other.close()


if __name__ == '__main__':
    unittest.main()
