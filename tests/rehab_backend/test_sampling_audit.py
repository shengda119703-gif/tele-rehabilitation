"""TEST raw-pixel trajectories and cache guards, not human accuracy labels."""
from copy import deepcopy
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.rehab_ml.common import file_hash, paths, write_json
from tools.rehab_ml.sampling_audit import (
    PROFILES, Profile, comparison, load_cache, replay, run_audit, select, transformed_time,
)


def raw_frame(index, angle, *, exercise='shoulder_abduction', valid=True):
    xy, conf = [[0., 0.] for _ in range(17)], [0.] * 17
    if exercise == 'shoulder_abduction':
        xy[5] = [300., 180.]
        xy[7] = [300.+140.*math.sin(math.radians(angle)), 180.+140.*math.cos(math.radians(angle))]
        conf[5], conf[7] = .9, .9 if valid else .1
    else:
        xy[11], xy[13] = [300., 150.], [300., 290.]
        xy[15] = [300.+140.*math.sin(math.radians(angle)), 290.+140.*math.cos(math.radians(angle))]
        conf[11], conf[13], conf[15] = .9, .9, .9 if valid else .1
    return dict(seq=index+1, time_s=index/30., size=[640, 480], schema_id='coco17-v1',
                coordinate_space='raw_image_pixels', model_manifest_id='a'*64, decoded_bgr_sha256='b'*64,
                people=[dict(track_key='TEST-one', bbox=[150., 80., 530., 470.], xy=xy, conf=conf)],
                metrics={'TEST_poisoned_cache_metric': {'value': 999., 'valid': True}})


def trajectory(exercise='shoulder_abduction'):
    start, end = (90., 5.) if exercise == 'sit_to_stand' else (0., 70.)
    angles = ([start]*60 + [start+(end-start)*i/30. for i in range(1, 31)]
              + [end]*60 + [end+(start-end)*i/30. for i in range(1, 31)] + [start]*60)
    return [raw_frame(i, value, exercise=exercise) for i, value in enumerate(angles)]


class SamplingAuditTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=paths()['run'])
        self.root = Path(self.directory.name)

    def tearDown(self):
        self.directory.cleanup()

    def cache(self, *, rows=None):
        rows = trajectory() if rows is None else rows
        cache = self.root/'pose-frames.jsonl'
        cache.write_text(''.join(json.dumps(row, allow_nan=False)+'\n' for row in rows), encoding='utf-8')
        result = dict(kind='private_target_domain_backend_replay', video_sha256='c'*64,
                      model_manifest_id='a'*64, exercise_id='shoulder_abduction', side='left', frames=len(rows),
                      input_timing=dict(basis='opencv_media_pts'), analysis_authorization='explicit_local_cli_analysis',
                      training_authorized=False, professional_labels_available=False, pose_file_sha256=file_hash(cache),
                      v2_summary=dict(completed=1), observable_frames=len(rows), fixture='SYNTHETIC/TEST')
        path = self.root/'result.json'
        write_json(path, result)
        return path, cache, result

    def test_three_actions_raw_geometry_completes_under_reference_and_cadence(self):
        for exercise in ('shoulder_abduction', 'sit_to_stand', 'rehab_squat'):
            for profile in PROFILES[:4]:
                with self.subTest(exercise=exercise, profile=profile.name):
                    result = replay(trajectory(exercise), exercise, 'left', profile, target_angle_deg=60.)
                    self.assertEqual(result['completed'], 1, result['diagnostics'])
                    self.assertTrue(result['baseline_observed'])
                    self.assertEqual(result['retained_frame_coverage'], 1.)
                    self.assertTrue(result['timing']['outbound_s']['valid_complete'])
                    self.assertTrue(result['timing']['return_s']['valid_complete'])
                    self.assertGreater(result['max_observed_live_target_hold_s'], 1.)

    def test_cached_filtered_values_are_not_used(self):
        rows = trajectory()
        reference = replay(rows, 'shoulder_abduction', 'left', PROFILES[0])
        for row in rows:
            row['metrics'] = {'raise_deg': {'value': 0., 'valid': True}}
        poisoned = replay(rows, 'shoulder_abduction', 'left', PROFILES[0])
        self.assertEqual(reference, poisoned)

    def test_clock_origin_does_not_change_angle_count_or_relative_duration(self):
        for exercise in ('shoulder_abduction', 'sit_to_stand', 'rehab_squat'):
            with self.subTest(exercise=exercise):
                reference = replay(trajectory(exercise), exercise, 'left', PROFILES[0], target_angle_deg=60.)
                shifted = replay(trajectory(exercise), exercise, 'left', PROFILES[4], target_angle_deg=60.)
                self.assertEqual(reference['completed'], shifted['completed'])
                self.assertAlmostEqual(reference['first_ready_relative_s'], shifted['first_ready_relative_s'])
                self.assertLess(comparison(reference, shifted)['metric_absolute_disagreement_deg']['maximum'], 1e-9)
                for name in reference['timing']:
                    a, b = reference['timing'][name], shifted['timing'][name]
                    self.assertEqual(a['valid_complete'], b['valid_complete'])
                    if a['median_s'] is not None:
                        self.assertAlmostEqual(a['median_s'], b['median_s'])

    def test_jitter_is_explicit_counterfactual_not_gold_or_network(self):
        reference = replay(trajectory(), 'shoulder_abduction', 'left', PROFILES[0])
        jittered = replay(trajectory(), 'shoulder_abduction', 'left', PROFILES[5])
        result = comparison(reference, jittered)
        self.assertTrue(jittered['counterfactual_clock'])
        self.assertGreater(result['metric_absolute_disagreement_deg']['maximum'], 0.)
        self.assertIsNone(result['clinical_accuracy'])
        self.assertIsNone(result['timing_accuracy'])

    def test_downsampling_keeps_original_pts_seq_and_does_not_add_eof_sample(self):
        rows = trajectory()[:-2]
        result = replay(rows, 'shoulder_abduction', 'left', PROFILES[3])
        self.assertEqual([r['seq'] for r in result['trace']], [r['seq'] for r in rows[::6]])
        self.assertEqual([r['processed_time_s'] for r in result['trace']], [r['time_s'] for r in rows[::6]])
        self.assertEqual(result['retained_frames']+result['discarded_frames'], len(rows))
        self.assertLess(result['original_frame_retention_coverage'], result['retained_frame_coverage'])
        self.assertFalse(result['declared_known_loss'])

    def test_every_known_loss_breaks_continuity_and_is_not_smooth_fill(self):
        result = replay(trajectory(), 'shoulder_abduction', 'left', PROFILES[6], target_angle_deg=60.)
        self.assertTrue(result['declared_known_loss'])
        self.assertEqual(result['discarded_frames'], 12)
        self.assertGreater(result['longest_explicit_missing_span_s'], 0.)
        self.assertFalse(result['baseline_observed'])  # No uninterrupted default 1-second readiness.
        self.assertEqual(result['completed'], 0)
        self.assertEqual(result['timing']['outbound_s']['complete_denominator'], 0)
        self.assertIsNone(result['timing']['outbound_s']['median_s'])

    def test_middle_loss_cannot_invent_continuous_hold_or_complete_time(self):
        result = replay(trajectory(), 'shoulder_abduction', 'left', PROFILES[7], target_angle_deg=60.)
        self.assertGreater(result['longest_explicit_missing_span_s'], .5)
        self.assertEqual(result['completed'], 0)
        self.assertGreater(result['partial_or_unassessable'], 0)
        self.assertLess(result['max_observed_live_target_hold_s'], 2.)
        self.assertIsNone(result['timing']['target_hold_s']['median_s'])

    def test_pending_eof_loss_is_flushed_without_adding_count_or_hold(self):
        rows = trajectory()[:150]  # Ends before return; loss is in the hold plateau.
        result = replay(rows, 'shoulder_abduction', 'left', PROFILES[-1], target_angle_deg=60.)
        self.assertEqual(result['discarded_frames'], 1)
        self.assertEqual(result['completed'], 0)
        self.assertEqual(result['partial_or_unassessable'], 1)
        self.assertIsNone(result['summary']['pending_input_gap'])
        timing = result['summary']['repetitions'][0]['movement_timing']
        self.assertTrue(timing['partial_observation'])
        self.assertFalse(timing['cycle_complete'])
        self.assertTrue(timing['target_hold_s']['valid'])  # Known observed lower bound, not full duration.
        self.assertLess(timing['target_hold_s']['value'], rows[-1]['time_s']-rows[0]['time_s'])
        self.assertIsNone(result['timing']['target_hold_s']['median_s'])

    def test_missing_required_joint_stays_invalid_even_after_valid_history(self):
        rows = trajectory()
        for i in range(95, 110):
            rows[i] = raw_frame(i, 70., valid=False)
        result = replay(rows, 'shoulder_abduction', 'left', PROFILES[0])
        missing = [r for r in result['trace'] if 96 <= r['seq'] <= 110]
        self.assertTrue(all(not r['valid'] and r['value'] is None for r in missing))
        self.assertGreater(result['longest_explicit_missing_span_s'], .4)
        self.assertEqual(sum(result['invalid_primary_reasons'].values()), len(missing))

    def test_future_raw_pose_does_not_modify_existing_prefix(self):
        rows = trajectory()
        changed = deepcopy(rows)
        for row in changed[120:]:
            row['people'] = []
        a = replay(rows, 'shoulder_abduction', 'left', PROFILES[0])
        b = replay(changed, 'shoulder_abduction', 'left', PROFILES[0])
        self.assertEqual(a['trace'][:120], b['trace'][:120])
        self.assertEqual([p for p in a['phases'] if p['seq'] <= 120], [p for p in b['phases'] if p['seq'] <= 120])

    def test_fresh_runs_are_exact_and_do_not_mutate_raw_input(self):
        rows = trajectory()
        original = deepcopy(rows)
        a = replay(rows, 'shoulder_abduction', 'left', PROFILES[2])
        b = replay(rows, 'shoulder_abduction', 'left', PROFILES[2])
        self.assertEqual(a, b)
        self.assertEqual(rows, original)

    def test_cache_hash_and_analysis_permission_required(self):
        path, cache, result = self.cache()
        rows, _, identity = load_cache(path)
        self.assertEqual(len(rows), 240)
        self.assertEqual(identity['cache_sha256'], file_hash(cache))
        for key, value in [('training_authorized', True), ('professional_labels_available', True),
                           ('analysis_authorization', None), ('input_timing', {'basis': 'nominal_video_seconds'})]:
            with self.subTest(key=key):
                bad = dict(result, **{key: value})
                write_json(path, bad)
                with self.assertRaisesRegex(ValueError, 'authorized_analysis_only'):
                    load_cache(path)
        write_json(path, result)
        cache.write_text(cache.read_text(encoding='utf-8')+'\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'unchanged_pose_cache'):
            load_cache(path)

    def test_unordered_time_seq_or_changed_geometry_is_rejected(self):
        for key, value in [('seq', True), ('seq', 1), ('time_s', 0.), ('time_s', -1.),
                           ('size', [320, 240]), ('model_manifest_id', 'd'*64),
                           ('schema_id', 'mediapipe33-v1'), ('decoded_bgr_sha256', '')]:
            with self.subTest(key=key, value=value):
                rows = trajectory()
                rows[2][key] = value
                path, _, _ = self.cache(rows=rows)
                with self.assertRaisesRegex(ValueError, 'geometry_and_identity'):
                    load_cache(path)

    def test_candidate_shape_finite_and_confidence_contract(self):
        for key, value in [('xy', [[0., 0.]]*16), ('xy', [[True, 0.]]*17),
                           ('conf', [1.2]*17), ('bbox', [0., 0., 640.]), ('track_key', 2)]:
            with self.subTest(key=key):
                rows = trajectory()
                rows[1]['people'][0][key] = value
                path, _, _ = self.cache(rows=rows)
                with self.assertRaisesRegex(ValueError, 'candidate_shape'):
                    load_cache(path)

    def test_duplicate_nonfinite_or_unterminated_json_is_rejected(self):
        for literal in ('{"seq":1,"seq":2}\n', '{"seq":NaN}\n', '{}'):
            with self.subTest(literal=literal):
                path, cache, result = self.cache()
                cache.write_text(literal, encoding='utf-8')
                result['pose_file_sha256'] = file_hash(cache)
                write_json(path, result)
                with self.assertRaises(ValueError):
                    load_cache(path)

    def test_unknown_profile_and_nonmonotonic_counterfactual_are_not_accepted(self):
        with self.assertRaisesRegex(ValueError, 'predeclared'):
            replay(trajectory(), 'shoulder_abduction', 'left', Profile('tuned'))
        rows = trajectory()
        rows[1]['time_s'] = 0.
        with self.assertRaisesRegex(ValueError, 'not_monotonic'):
            replay(rows, 'shoulder_abduction', 'left', PROFILES[0])
        self.assertFalse(select(PROFILES[7], 120, 240))
        self.assertEqual(transformed_time(PROFILES[4], rows[0], 0), 1000.)

    def test_new_artifacts_are_ignored_and_public_statistics_exclude_private_trace(self):
        path, cache, _ = self.cache()
        before = (file_hash(path), file_hash(cache))
        artifact = run_audit([path], publish=False)
        summary = json.loads(Path(artifact['summary']).read_text(encoding='utf-8'))
        self.assertEqual(before, (file_hash(path), file_hash(cache)))
        self.assertEqual(artifact['profile_runs'], 9)
        self.assertFalse(summary['training_performed'])
        self.assertFalse(summary['network_or_phone_tested'])
        self.assertFalse(summary['population_sampling_invariance_validated'])
        self.assertIsNone(summary['count_accuracy'])
        self.assertTrue(summary['inputs_unchanged'])
        self.assertTrue(summary['implementation_unchanged'])
        text = json.dumps(summary)
        for field in ('"people"', '"xy"', '"trace"', '"summary"', '"result_path"', '"phases"'):
            self.assertNotIn(field, text)
        self.assertTrue(Path(artifact['summary']).is_relative_to(paths()['run']))


if __name__ == '__main__':
    unittest.main()
