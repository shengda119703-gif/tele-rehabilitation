from dataclasses import replace
import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'rehab_codex_single_camera_v2_1'))
from app.domain import Context, PoseFrame, PosePerson
from app.rehab_v2.engine import ProtocolEngine
from app.rehab_v2.evidence import EvidenceAdapter, EvidenceFrame, MetricEvidence
from app.rehab_v2.cues import CueEvents
from app.rehab_v2.rounds import TrainingRounds


class Replay:
    def __init__(self, exercise='shoulder_abduction', **plan):
        self.engine = ProtocolEngine(dict(exercise_id=exercise, **plan), source_epoch='epoch', session_id='session')
        self.seq, self.t = 0, 0.
        self.frame = None

    def feed(self, value, count=8, *, valid=True, track='one', epoch='epoch', kind='observed',
             elbow=0., tilt=0., age=0.):
        for _ in range(count):
            self.t += .05
            self.seq += 1
            spec = self.engine.spec
            metric = MetricEvidence(value if valid else None, 'degree', valid, None if valid else 'occluded',
                                    kind, self.t if valid else None, self.t+age/1000, age,
                                    tuple(spec['required_joints']))
            metrics = {spec['metric']: metric}
            for key, val in [('elbow_flexion_deg', elbow), ('trunk_tilt_deg', tilt)]:
                if key in spec['optional_quality_metrics']:
                    metrics[key] = MetricEvidence(val, 'degree', val is not None, None, 'observed',
                                                   self.t if val is not None else None, self.t, 0.,
                                                   tuple(spec['optional_quality_metrics'][key]))
            self.frame = EvidenceFrame(self.seq, self.t, epoch, track, 'coco17-v1', 'original-yolo-sha',
                                        (1280, 720), metrics, 'VALID' if valid else 'UNKNOWN')
            self.engine.process(self.frame)
        return self.engine.summary()

    def cycle(self, peak=70.):
        self.feed(0., 30)
        self.feed(peak, 10)
        self.feed(0., 10)


class ProtocolTests(unittest.TestCase):
    def test_C01_shoulder_wrist_and_hip_not_required(self):
        names = ('nose', 'left_eye', 'right_eye', 'left_ear', 'right_ear', 'left_shoulder',
                 'right_shoulder', 'left_elbow', 'right_elbow', 'left_wrist', 'right_wrist',
                 'left_hip', 'right_hip', 'left_knee', 'right_knee', 'left_ankle', 'right_ankle')
        xy, conf = [[0, 0] for _ in names], [0.] * len(names)
        for joint, point in [('left_shoulder', [300, 200]), ('left_elbow', [400, 200])]:
            idx = names.index(joint)
            xy[idx], conf[idx] = point, .9
        pose = PoseFrame(Context(1, 'rehab', 'fixture', 'SYNTHETIC', 'TEST'), 1, .1, (640, 480),
                         [PosePerson('one', [200, 100, 500, 450], xy, conf)], model_manifest_id='verified')
        evidence = EvidenceAdapter('shoulder_abduction').analyze(pose)
        self.assertAlmostEqual(evidence.metrics['raise_deg'].value, 90.)
        self.assertTrue(evidence.metrics['raise_deg'].valid)
        self.assertFalse(evidence.metrics['elbow_flexion_deg'].valid)
        replay = Replay(allowed_elbow_flexion_deg=10.)
        replay.feed(0., 30, elbow=None)
        replay.feed(70., 10, elbow=None)
        replay.feed(0., 10, elbow=None)
        self.assertEqual(replay.engine.completed, 1)
        self.assertEqual(replay.engine.repetitions[0]['quality_status'], 'UNASSESSABLE')

    def test_C02_short_gap_preserves_baseline_without_accumulating_hold(self):
        replay = Replay()
        replay.feed(0., 30)
        baseline = replay.engine.baseline.copy()
        replay.feed(70., 8)
        replay.feed(None, 2, valid=False)
        self.assertIsNone(replay.engine.latest)
        self.assertEqual(replay.engine.baseline, baseline)
        replay.feed(70., 8)
        replay.feed(0., 10)
        self.assertEqual(replay.engine.completed, 1)

    def test_C03_hidden_turn_not_complete(self):
        replay = Replay()
        replay.feed(0., 30)
        replay.feed(70.)
        replay.feed(None, 2, valid=False)
        replay.feed(0., 30)
        self.assertEqual(replay.engine.completed, 0)
        self.assertEqual(replay.engine.repetitions[0]['reason'], 'hidden_motion_boundary')

    def test_C04_standing_entry_not_seated_baseline(self):
        replay = Replay('sit_to_stand')
        replay.feed(5., 60)
        self.assertEqual(replay.engine.completed, 0)
        self.assertIsNone(replay.engine.baseline)
        self.assertEqual(replay.engine.phase, 'WAIT_READY')

    def test_C05_standing_cannot_count_twice_until_seated(self):
        replay = Replay('sit_to_stand')
        replay.feed(90., 30)
        replay.feed(40.)
        replay.feed(5., 60)
        self.assertEqual(replay.engine.completed, 1)
        replay.feed(90., 15)
        replay.feed(40.)
        replay.feed(5.)
        self.assertEqual(replay.engine.completed, 2)

    def test_C06_squat_no_hip_proxy_and_partial_amplitude_separate(self):
        replay = Replay('rehab_squat', target_angle_deg=80.)
        replay.cycle(35.)
        self.assertEqual(replay.engine.completed, 1)
        self.assertEqual(replay.engine.repetitions[0]['target_status'], 'NOT_MET')
        missing = replace(replay.frame, seq=replay.seq+1, time_s=replay.t+.05,
                          metrics={'hip_y': MetricEvidence(.6, 'fraction', True, None, 'observed',
                                                          replay.t+.05, replay.t+.05, 0., ('left_hip',))})
        replay.engine.process(missing)
        self.assertEqual(replay.engine.observation_state, 'missing')
        self.assertEqual(replay.engine.completed, 1)

    def test_C07_resolution_change_invalidates_baseline_and_half_rep(self):
        replay = Replay()
        replay.feed(0., 30)
        replay.feed(70.)
        frame = replace(replay.frame, seq=replay.seq+1, time_s=replay.t+.05, size=(640, 360))
        replay.engine.process(frame)
        self.assertEqual(replay.engine.completed, 0)
        self.assertIsNone(replay.engine.baseline)
        self.assertEqual(replay.engine.calibration_epoch, 1)

    def test_C08_seq_epoch_stale_predicted_rejected(self):
        replay = Replay()
        replay.feed(0., 30)
        seq = replay.engine.last_seq
        self.assertFalse(replay.engine.process(replay.frame))
        self.assertEqual(replay.engine.last_seq, seq)
        replay.feed(70., 10, epoch='old')
        self.assertEqual(replay.engine.last_seq, seq)
        replay.feed(70., 10, age=900.)
        replay.feed(70., 10, kind='predicted')
        replay.feed(0., 30)
        self.assertEqual(replay.engine.completed, 0)

    def test_C09_changed_person_does_not_join_half_rep(self):
        replay = Replay()
        replay.feed(0., 30)
        replay.feed(70.)
        replay.feed(0., 30, track='other')
        self.assertEqual(replay.engine.completed, 0)
        self.assertEqual(replay.engine.repetitions[0]['reason'], 'participant_changed')

    def test_C10_pause_does_not_carry_half_rep(self):
        replay = Replay()
        replay.feed(0., 30)
        replay.feed(70.)
        replay.engine.pause()
        replay.feed(0., 30)
        replay.engine.resume()
        replay.feed(0., 30)
        self.assertEqual(replay.engine.completed, 0)
        self.assertEqual(replay.engine.calibration_epoch, 1)

    def test_C11_cue_queries_expire_and_cancel(self):
        replay = Replay()
        replay.feed(0., 30)
        cues = CueEvents('session')
        event = cues.update(replay.engine, replay.frame, emission_monotonic=50.)
        self.assertEqual(event['cue_key'], 'move')
        self.assertIsNone(cues.query(source_time_s=replay.t+3, emission_age_ms=1000,
                                     phase='REST', calibration_epoch=0))
        replay.feed(70.)
        cues.update(replay.engine, replay.frame, emission_monotonic=54.)
        replay.engine.pause()
        self.assertIsNone(cues.update(replay.engine, replay.frame, emission_monotonic=55.))

    def test_C11_current_correction_stops_after_observed_improvement(self):
        replay = Replay(allowed_elbow_flexion_deg=10.)
        replay.feed(0., 30)
        replay.feed(70., 18, elbow=35.)
        cues = CueEvents('session')
        event = cues.update(replay.engine, replay.frame, emission_monotonic=50.)
        self.assertEqual(event['cue_key'], 'adjust:elbow_flexion')
        self.assertEqual(event['evidence_refs'][0]['metric'], 'elbow_flexion_deg')
        replay.feed(70., 12, elbow=0.)
        event = cues.update(replay.engine, replay.frame, emission_monotonic=51.)
        self.assertEqual(event['cue_key'], 'move')
        self.assertTrue(replay.engine.current['issues'])
        self.assertFalse(replay.engine.current_issues)

    def test_invalid_view_and_target_never_silently_prescribed(self):
        with self.assertRaises(ValueError):
            ProtocolEngine(dict(exercise_id='shoulder_abduction', view='sagittal'), source_epoch='epoch')
        with self.assertRaises(ValueError):
            ProtocolEngine(dict(exercise_id='rehab_squat', target_angle_deg=math.nan), source_epoch='epoch')

    def test_C10_rounds_rest_requires_explicit_resume_and_original_dose(self):
        replay = Replay()
        replay.engine = TrainingRounds(dict(exercise_id='shoulder_abduction', target_reps=1, target_sets=2,
                                             rest_between_sets_s=20.), source_epoch='epoch')
        replay.cycle()
        self.assertEqual(replay.engine.training_stage, 'RESTING')
        self.assertEqual(replay.engine.completed_sets, 1)
        with self.assertRaisesRegex(ValueError, 'prescribed_rest_not_finished'):
            replay.engine.resume(source_time_s=replay.t)
        replay.t += 20.
        replay.engine.resume(source_time_s=replay.t)
        replay.cycle()
        self.assertEqual(replay.engine.training_stage, 'COMPLETE')
        self.assertTrue(replay.engine.summary()['training']['plan_complete'])
        self.assertEqual(replay.engine.completed, 2)
        replay.cycle()
        self.assertEqual(replay.engine.completed, 2)

    def test_sitstand_set_completion_waits_for_observed_recovery(self):
        replay = Replay('sit_to_stand')
        replay.engine = TrainingRounds(dict(exercise_id='sit_to_stand', target_reps=1, target_sets=1), source_epoch='epoch')
        replay.feed(90., 30)
        replay.feed(40.)
        replay.feed(5.)
        self.assertEqual(replay.engine.completed, 1)
        self.assertEqual(replay.engine.training_stage, 'RECOVERY')
        self.assertEqual(replay.engine.completed_sets, 0)
        replay.feed(90., 15)
        self.assertEqual(replay.engine.training_stage, 'COMPLETE')


if __name__ == '__main__':
    unittest.main()
