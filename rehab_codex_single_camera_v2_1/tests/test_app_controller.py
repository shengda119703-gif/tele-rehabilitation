import math
import tempfile
import time
import unittest
from pathlib import Path

import numpy as np

from app.camera_manager import CameraManager
from app.domain import FramePacket, PoseFrame, PosePerson, Metric, utc_now
from app.exercises import exercise_spec
from app.scene_controller import SceneController
from app.settings import default_setup
from app.storage import Storage
from app.assessment import build_body_profile, build_training_reference


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.temp.name)/'test.sqlite3')
        self.camera = CameraManager()
        self.c = SceneController(self.store, self.camera, test_mode=True)
        self.source = {'kind': 'SYNTHETIC', 'ref': 'synthetic-fixture', 'usage_context': 'TEST'}
        self.setup = default_setup()
        self.setup['participant_confirmed'] = True
        self.c.open(self.source, self.setup)
        self.seq = 0
        self.frame(0, 0)
        self.c.confirm(self.setup)

    def tearDown(self):
        if self.c.pending:
            self.c.retry_save()
        self.c.stop('test_end')
        self.store.close()
        self.temp.cleanup()

    def frame(self, t, angle, context=None):
        self.seq += 1
        context = context or self.c.context
        xy = [[120., 100.] for _ in range(17)]
        xy[5], xy[6], xy[11], xy[12] = [200., 150.], [300., 150.], [200., 300.], [300., 300.]
        r = math.radians(angle)
        xy[7], xy[9] = [200+100*math.sin(r), 150+100*math.cos(r)], [200+150*math.sin(r), 150+150*math.cos(r)]
        xy[13], xy[15] = [200., 400.], [200., 500.]
        pose = PoseFrame(context, self.seq, t, (1280, 720), [PosePerson(context.epoch+':1', [100, 50, 500, 600], xy, [1.]*17)], model_manifest_id='synthetic-schema-test')
        packet = FramePacket(context, self.seq, t, time.monotonic(), utc_now(), np.zeros((720, 1280, 3), dtype=np.uint8), time_basis='synthetic_test_time')
        return self.c.consume(packet, pose)

    def test_preview_start_shoulder_save_and_reopen(self):
        self.c.start()
        t = 0
        for angle in (0, 90, 0):
            for _ in range(20):
                self.frame(t, angle)
                t += .1
        self.assertEqual(self.c.engine.completed, 1)
        run_id = self.c.context.run_id
        self.c.stop('user_stop')
        self.assertIsNone(self.c.latest_packet)
        self.store.close()
        self.store = Storage(Path(self.temp.name)/'test.sqlite3')
        self.c.storage = self.store
        saved = self.store.get_session(run_id)
        self.assertEqual(saved['summary']['completed'], 1)
        self.assertEqual(saved['source_kind'], 'SYNTHETIC')
        self.assertEqual(saved['usage_context'], 'TEST')
        self.assertNotIn('poses', saved)

    def test_manual_profile_is_snapshotted_at_start_without_changing_targets(self):
        from app.participants import legacy_participant
        draft = dict(legacy_participant('participant-local'), display_name='测试档案',
                     goals='开始时的目标', support='assisted')
        saved = self.store.save_participant(draft, expected_revision=0)
        self.c.start()
        run_id = self.c.context.run_id
        self.assertEqual(self.c.session['participant_snapshot'], saved)
        self.assertIsNone(self.c.setup['plan']['target_angle_deg'])
        # This is a manual statement, not a silently applied clinical plan.
        self.assertFalse(self.c.setup['plan']['needs_companion'])
        self.store.save_participant(dict(saved, goals='后来填写的目标'), expected_revision=1)
        self.c.stop('user_stop')
        reopened = self.store.get_session(run_id)
        self.assertEqual(reopened['participant_snapshot']['goals'], '开始时的目标')
        self.assertEqual(reopened['participant_snapshot']['revision'], 1)

    def _assessment_reference(self):
        self.c.start()
        t = 0
        for angle in (0, 90, 0):
            for _ in range(20):
                self.frame(t, angle)
                t += .1
        self.c.stop('user_stop')
        profile = build_body_profile(self.store.list_sessions(), 'participant-local', 'SYNTHETIC', 'TEST')
        return build_training_reference(profile, 'shoulder_abduction', 'left')

    def _training_preview(self, reference=None, confirmed=True, participant='participant-local'):
        self.setup['plan'].update(submode='training', training_plan_confirmed=confirmed,
                                  assessment_reference=reference, participant_id=participant)
        self.c.open(self.source, self.setup)
        self.frame(0, 0)
        self.c.confirm(self.setup)

    def test_assessment_to_training_revalidates_and_freezes_reference(self):
        reference = self._assessment_reference()
        self.assertEqual(reference['status'], 'ASSESSED')
        original_max = reference['motion_range']['max_deg']
        reference['motion_range']['max_deg'] = 999  # UI cannot inject measurements.
        self._training_preview(reference)
        self.c.start()
        snapshot = self.c.session
        self.assertEqual(snapshot['assessment_reference']['motion_range']['max_deg'], original_max)
        self.assertIsNone(snapshot['config_snapshot']['plan']['target_angle_deg'])
        self.assertEqual(snapshot['submode'], 'training')
        self.assertEqual(snapshot['assessment_reference'], snapshot['config_snapshot']['plan']['assessment_reference'])
        reference['session_id'] = 'changed-after-start'
        self.assertNotEqual(snapshot['assessment_reference']['session_id'], reference['session_id'])
        self.c.stop('user_stop')
        reopened = self.store.get_session(snapshot['id'])
        self.assertEqual(reopened['assessment_reference']['motion_range']['max_deg'], original_max)

    def test_training_requires_manual_plan_and_matching_assessment(self):
        self._training_preview(confirmed=False)
        with self.assertRaisesRegex(ValueError, '确认.*训练计划'):
            self.c.start()
        self.c.setup['plan']['training_plan_confirmed'] = True
        with self.assertRaisesRegex(ValueError, '有效评估'):
            self.c.start()

    def test_training_pause_checkpoint_and_source_time_barrier(self):
        self._training_preview(self._assessment_reference())
        self.c.start()
        run_id = self.c.context.run_id
        for i in range(16):
            self.frame(i*.1, 0)
        for i in range(16, 26):
            self.frame(i*.1, 80)
        self.c.training_control('pause')
        checkpoint = self.store.get_session(run_id)
        self.assertEqual(checkpoint['summary']['training']['stage'], 'PAUSED')
        self.assertEqual(checkpoint['repetitions'][-1]['completion_status'], 'INTERRUPTED')
        metrics_count = len(self.c.session['metrics'])
        self.assertFalse(self.frame(1., 100))
        self.assertEqual(len(self.c.session['metrics']), metrics_count)
        for i in range(26, 40):
            self.frame(i*.1, 0)
        self.assertFalse(self.c.session['metrics'][-1]['included_in_training'])
        self.assertEqual(self.c.session['metrics'][-1]['metrics'], {})
        self.c.training_control('resume', setup_confirmed=True)
        for i in range(40, 55):
            self.frame(i*.1, 0)
        for i in range(55, 75):
            self.frame(i*.1, 80)
        for i in range(75, 95):
            self.frame(i*.1, 0)
        self.c.stop('user_stop')
        saved = self.store.get_session(run_id)
        self.assertEqual(saved['summary']['completed'], 1)
        self.assertEqual(saved['summary']['training']['stage'], 'FINISHED')
        self.assertEqual(saved['training_execution_version'], 'sets-rest-1')

    def test_invalid_training_plan_never_leaves_an_unsaved_running_session(self):
        self._training_preview(self._assessment_reference())
        self.c.setup['plan']['rest_between_sets_s'] = -5
        with self.assertRaises(ValueError):
            self.c.start()
        self.assertIsNone(self.c.session)
        self.assertEqual(self.c.state, 'PREVIEW')

    def test_training_checkpoint_failure_releases_and_preserves_pending_result(self):
        self._training_preview(self._assessment_reference())
        self.c.start()
        self.frame(1., 0)
        original = self.store.save_session
        def fail(snapshot):
            raise OSError('disk full')
        self.store.save_session = fail
        try:
            with self.assertRaises(RuntimeError):
                self.c.training_control('pause')
            self.assertEqual(self.c.state, 'SAVE_FAILED')
            self.assertIsNotNone(self.c.pending)
            self.assertIsNone(self.camera.worker)
            self.assertEqual(self.c.pending['summary']['training']['ended_stage'], 'PAUSED')
        finally:
            self.store.save_session = original

    def test_training_resume_allows_temporary_missing_participant_and_assessment_has_no_controls(self):
        self.c.start()
        with self.assertRaises(ValueError):
            self.c.training_control('pause')
        self.c.stop('user_stop')
        self.c.open(self.source, self.setup)
        self.frame(0, 0)
        self.c.confirm(self.setup)
        self._training_preview(self._assessment_reference())
        self.c.start()
        self.frame(1., 0)
        self.c.training_control('pause')
        self.c.latest_observation = None
        self.c.training_control('resume', setup_confirmed=True)
        self.assertEqual(self.c.engine.stage, 'ACTIVE')

    def test_training_resume_does_not_gate_on_current_pose_or_metrics(self):
        self._training_preview(self._assessment_reference())
        self.c.start()
        self.frame(1., 0)
        self.c.training_control('pause')
        self.frame(2., 0)
        self.c.latest_pose = None
        self.c.training_control('resume', setup_confirmed=True)
        self.assertEqual(self.c.engine.stage, 'ACTIVE')

    def test_training_live_resume_does_not_gate_on_receipt_timestamp(self):
        self._training_preview(self._assessment_reference())
        self.c.start()
        self.frame(1., 0)
        self.c.training_control('pause')
        self.frame(2., 0)
        # Controller-only clock fixture; no live camera is opened or evidence relabelled.
        self.c.source = dict(self.source, kind='LIVE_CAMERA')
        try:
            self.c.latest_packet.received_monotonic = float('nan')
            self.c.training_control('resume', now=10., setup_confirmed=True)
            self.assertFalse(self.frame(9.9, 90))
            self.assertTrue(self.frame(10.1, 0))
        finally:
            self.c.source = self.source

    def test_other_participant_cannot_use_assessment_reference(self):
        reference = self._assessment_reference()
        self._training_preview(reference, participant='different-user')
        with self.assertRaisesRegex(ValueError, '有效评估'):
            self.c.start()

    def test_deleted_assessment_cannot_start_training(self):
        reference = self._assessment_reference()
        self._training_preview(reference)
        self.store.delete_session(reference['session_id'])
        with self.assertRaisesRegex(ValueError, '有效评估'):
            self.c.start()

    def test_confirmation_rejects_identity_or_mode_change_since_preview(self):
        self.setup['plan']['participant_id'] = 'different-user'
        with self.assertRaisesRegex(ValueError, '重新预览'):
            self.c.confirm(self.setup)
        self.setup['plan']['participant_id'] = 'participant-local'
        self.setup['plan']['submode'] = 'training'
        with self.assertRaisesRegex(ValueError, '重新预览'):
            self.c.confirm(self.setup)

    def test_new_joint_sessions_use_their_own_required_metrics_and_camera_view(self):
        for exercise in ('shoulder_flexion', 'elbow_flexion', 'knee_extension', 'hip_abduction'):
            with self.subTest(exercise=exercise):
                self.c.stop('configuration_change')
                setup = default_setup(exercise=exercise)
                setup['participant_confirmed'] = True
                self.c.open(self.source, setup)
                self.frame(0, 0)
                self.c.confirm(setup)
                metric = exercise_spec(exercise)['metric']
                observation = self.c.latest_observation
                observation.metrics[metric] = Metric.missing('synthetic-missing')
                self.c.start()
                self.assertEqual(self.c.session['exercise_id'], exercise)
                self.assertEqual(self.c.engine.primary_metric, metric)
                self.assertEqual(self.c.session['config_snapshot']['view'], exercise_spec(exercise)['view'])
                self.assertEqual(self.c.session['readiness_policy'], 'nonblocking-observation-1')
                self.c.stop('user_stop')

    def test_preview_packets_rejected_after_start(self):
        old = self.c.context
        self.c.start()
        self.assertFalse(self.frame(1, 90, old))
        self.assertEqual(self.c.engine.completed, 0)

    def test_privacy_has_no_active_context_and_rejects_late_data(self):
        self.c.start()
        old = self.c.context
        self.c.stop('privacy_pause', privacy=True)
        self.assertEqual(self.c.state, 'PRIVACY_PAUSED')
        self.assertIsNone(self.camera.worker)
        self.assertFalse(self.frame(1, 90, old))

    def test_failed_save_keeps_snapshot_and_blocks_new_run(self):
        self.c.start()
        original = self.store.save_session
        def failure(snapshot):
            raise OSError('simulated disk full')
        self.store.save_session = failure
        try:
            with self.assertRaises(RuntimeError):
                self.c.stop('user_stop')
            self.assertEqual(self.c.state, 'SAVE_FAILED')
            self.assertIsNotNone(self.c.pending)
            self.assertTrue(self.c.pending_path.exists())
            with self.assertRaises(RuntimeError):
                self.c.open(self.source, self.setup)
        finally:
            self.store.save_session = original
        self.c.retry_save()
        self.assertIsNone(self.c.pending)

    def test_session_rules_are_immutable_after_start(self):
        self.c.start()
        self.setup['plan']['target_angle_deg'] = 150
        self.assertIsNone(self.c.session['config_snapshot']['plan']['target_angle_deg'])
        self.assertEqual(self.c.session['config_snapshot']['preprocessing']['imgsz'], 640)
        self.c.vision_config['imgsz'] = 320
        self.assertEqual(self.c.session['config_snapshot']['preprocessing']['imgsz'], 640)

    def test_pending_backup_and_explicit_discard_are_audited(self):
        self.c.pending = {'id': 'pending-fixture', 'config_snapshot': {'poses_consent': False}}
        out = self.c.backup_pending(self.temp.name)
        self.assertTrue(out.exists())
        with self.assertRaises(ValueError):
            self.c.discard_pending('')
        self.c.discard_pending('synthetic test explicitly discarded')
        self.assertIsNone(self.c.pending)
        rows = self.store._call(lambda db: db.execute("SELECT COUNT(*) FROM audit WHERE action='discard_pending_session'").fetchone()[0])
        self.assertEqual(rows, 1)

    def test_changed_frame_shape_ends_task(self):
        self.c.start()
        ctx = self.c.context
        self.seq += 1
        packet = FramePacket(ctx, self.seq, 1, time.monotonic(), utc_now(), np.zeros((480, 640, 3), dtype=np.uint8))
        pose = PoseFrame(ctx, self.seq, 1, (640, 480), [])
        with self.assertRaises(RuntimeError):
            self.c.consume(packet, pose)
        self.assertIsNone(self.c.context)


if __name__ == '__main__':
    unittest.main()
