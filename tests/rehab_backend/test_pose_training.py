"""TEST-only training gates, transforms, selection and owned-child faults."""
import copy
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.rehab_ml.common import file_hash, paths, read_json, write_json
from tools.rehab_ml.pose_training import (VERSION, TrainingLease, configuration, owned_output, qualified_reference,
    record_child_failure, request_cancel, run_child, selection_score, train_pose, training_batch)
from test_pose_masked_loss import fixture


def test_config(root, source):
    value = dict(schema_version=VERSION, mode='engineering_test', reference=str(source), output_dir=str(root/'training'),
        seed=20261011, device='cpu', image_size=128, batch_size=2, max_epochs=2, patience=2, threads=2,
        learning_rate=1e-5, weight_decay=.0001, clip_norm=10., freeze_first_layers=1,
        brightness=.05, contrast=.05, confidence_min=.5, pck_threshold=.05, timeout_s=120.)
    source = Path(write_json(root/'config.json', value))
    return source, value


class PoseTrainingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=paths()['run'])
        self.root = Path(self.temporary.name)
        self.reference, self.data = fixture(self.root)
        self.source, self.config = test_config(self.root, self.reference)

    def tearDown(self):
        self.temporary.cleanup()

    def save(self):
        write_json(self.source, self.config)
        write_json(self.reference, self.data)

    def test_explicit_strict_config_paths_and_digest(self):
        source, config, digest = configuration(self.source)
        self.assertEqual(source, self.source)
        self.assertEqual(len(digest), 64)
        self.assertEqual(config['output_dir'], str(self.root/'training'))

    def test_unknown_option_cannot_change_production_or_augmentation(self):
        for option in ('product_enabled', 'hflip', 'resume', 'unverified_labels'):
            with self.subTest(option=option):
                bad = dict(self.config, **{option: True})
                write_json(self.source, bad)
                with self.assertRaisesRegex(ValueError, 'no_unknown_options'):
                    configuration(self.source)

    def test_integer_ranges_and_boolean_rejected(self):
        for key, bad in (('batch_size', 9), ('max_epochs', 101), ('image_size', 641), ('threads', 5),
                         ('seed', True), ('freeze_first_layers', -1), ('patience', 0)):
            with self.subTest(key=key):
                write_json(self.source, dict(self.config, **{key: bad}))
                with self.assertRaisesRegex(ValueError, 'bounded_integer'):
                    configuration(self.source)

    def test_float_ranges_and_boolean_rejected(self):
        for key, bad in (('learning_rate', .1), ('weight_decay', -1), ('brightness', .3), ('contrast', True),
                         ('timeout_s', 9), ('pck_threshold', 0), ('confidence_min', .1)):
            with self.subTest(key=key):
                write_json(self.source, dict(self.config, **{key: bad}))
                with self.assertRaisesRegex(ValueError, 'finite_bounded'):
                    configuration(self.source)

    def test_stride_and_patience(self):
        for key, value in (('image_size', 100), ('patience', 3)):
            write_json(self.source, dict(self.config, **{key: value}))
            with self.assertRaisesRegex(ValueError, 'stride_aligned'):
                configuration(self.source)

    def test_output_outside_dedicated_root_is_refused(self):
        self.config['output_dir'] = str(ROOT/'docs'/'do-not-create')
        self.save()
        with self.assertRaisesRegex(ValueError, 'dedicated_ignored_root'):
            configuration(self.source)
        with self.assertRaisesRegex(ValueError, 'dedicated_ignored_root'):
            owned_output(paths()['run'])

    def test_child_request_name_checked_before_lease_and_failure_writes(self):
        request = write_json(self.root/'not-a-request.json', {})
        with patch('tools.rehab_ml.pose_training.TrainingLease') as lease:
            with self.assertRaisesRegex(ValueError, 'request_filename'):
                run_child(request)
            lease.assert_not_called()
        self.assertFalse(record_child_failure(request, ValueError('TEST')))
        self.assertFalse((self.root/'failure.json').exists())
        self.assertFalse((self.root/'status.json').exists())

    def test_native_unowned_child_leaves_neighbor_files_unchanged(self):
        # Only our own E-drive temporary fixtures, outside both allowed roots.
        with tempfile.TemporaryDirectory(dir=ROOT/'.runtime') as directory:
            parent = Path(directory)
            request = write_json(parent/'request.json', {'version': VERSION})
            failure = Path(write_json(parent/'failure.json', {'TEST': 'preserve failure'}))
            status = Path(write_json(parent/'status.json', {'TEST': 'preserve status'}))
            before = {p.name: file_hash(p) for p in parent.iterdir()}
            with patch('tools.rehab_ml.pose_training.TrainingLease') as lease:
                with self.assertRaisesRegex(ValueError, 'dedicated_ignored_root'):
                    run_child(request)
                lease.assert_not_called()
            self.assertFalse(record_child_failure(request, ValueError('TEST')))
            child = subprocess.run([sys.executable, '-X', 'utf8', '-B',
                str(ROOT/'tools/rehab_ml/pose_training.py'), '--child-request', request],
                cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=10,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            self.assertEqual(child.returncode, 1)
            self.assertIn('dedicated_ignored_root', child.stderr)
            self.assertEqual(before, {p.name: file_hash(p) for p in parent.iterdir()})
            self.assertTrue(failure.is_file() and status.is_file())

    def test_owned_failure_records_terminal_state_even_after_invalid_status(self):
        request = write_json(self.root/'request.json', {})
        write_json(self.root/'status.json', ['TEST invalid state'])
        self.assertTrue(record_child_failure(request, InterruptedError('TEST cancel')))
        self.assertEqual(read_json(self.root/'failure.json')['status'], 'cancelled')
        self.assertEqual(read_json(self.root/'status.json')['phase'], 'cancelled')
        self.assertFalse(read_json(self.root/'status.json')['completed'])

    def test_missing_training_permission_refused_before_process_or_output(self):
        self.data['permissions']['training'] = False
        self.save()
        with patch('tools.rehab_ml.pose_training.subprocess.Popen') as spawn:
            with self.assertRaisesRegex(ValueError, 'training_permission'):
                train_pose(self.source)
            spawn.assert_not_called()
        self.assertFalse((self.root/'training').exists())

    def test_research_does_not_train_engineering_fixture(self):
        self.config['mode'] = 'research'
        with self.assertRaisesRegex(ValueError, 'mode_must_match'):
            qualified_reference(self.config)

    def test_nonempty_coordinate_supervision_in_each_split_required(self):
        row = self.data['samples'][1]
        row['annotation_mask'], row['visibility'], row['xy'] = [False]*17, [None]*17, [None]*17
        self.save()
        with self.assertRaisesRegex(ValueError, 'coordinate_supervision'):
            qualified_reference(self.config)

    def test_case_variant_people_cannot_cross_splits(self):
        self.data['samples'][0]['subject_group'] = 'TEST-person'
        self.data['samples'][1]['subject_group'] = 'test-PERSON'
        self.save()
        with self.assertRaisesRegex(ValueError, 'casefolded'):
            qualified_reference(self.config)

    def test_train_tensor_rejects_validation_and_test_rows(self):
        for row in self.data['samples'][1:]:
            with self.assertRaisesRegex(ValueError, 'only_bounded_train'):
                training_batch(self.reference, [row], self.config, random.Random(1))

    def test_batch_preserves_masks_visibility_and_integer_resize(self):
        batch, transforms = training_batch(self.reference, self.data['samples'][:1], self.config, random.Random(1))
        self.assertFalse(batch['annotation_mask'][0, 0])
        self.assertEqual(batch['keypoints'][0, 0].tolist(), [0., 0., 0.])
        self.assertTrue(batch['annotation_mask'][0, 9])
        self.assertEqual(batch['keypoints'][0, 9].tolist(), [0., 0., 0.])
        self.assertEqual(transforms[0]['resized_size'], [128, 85])
        self.assertAlmostEqual(batch['keypoints'][0, 1, 1].item(), (21*85/64+21)/128, places=6)
        self.assertFalse(transforms[0]['geometry_augmented'])

    def test_colour_augmentation_reproducible_without_changing_labels(self):
        a, aa = training_batch(self.reference, self.data['samples'][:1], self.config, random.Random(2))
        b, bb = training_batch(self.reference, self.data['samples'][:1], self.config, random.Random(2))
        c, cc = training_batch(self.reference, self.data['samples'][:1], self.config, random.Random(3))
        self.assertEqual(aa, bb)
        self.assertNotEqual(aa, cc)
        self.assertTrue(a['keypoints'].equal(c['keypoints']))
        self.assertTrue(a['img'].equal(b['img']))

    def test_selection_uses_all_reference_pck_then_coverage(self):
        def score(pck, coverage):
            return selection_score(dict(coordinate_reference_count=15, pck_all_coordinate_references=pck, coordinate_coverage=coverage))
        self.assertGreater(score(.8, .8), score(.7, 1.))
        self.assertGreater(score(.8, 1.), score(.8, .8))
        self.assertEqual(score(0., 0.), (0., 0.))  # No person is not a perfect score.

    def test_missing_or_nonfinite_validation_score_is_not_success(self):
        for count, pck, coverage in ((0, None, None), (1, float('nan'), 1.), (1, 1.1, 1.)):
            with self.assertRaisesRegex(ValueError, 'validation_score'):
                selection_score(dict(coordinate_reference_count=count, pck_all_coordinate_references=pck, coordinate_coverage=coverage))

    def test_image_tampering_rejected(self):
        (self.root/'train.png').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'image_hash_changed'):
            training_batch(self.reference, self.data['samples'][:1], self.config, random.Random(1))

    def test_full_disk_preflight_no_output_or_child(self):
        with patch('tools.rehab_ml.pose_training.shutil.disk_usage', return_value=Mock(free=0)), \
                patch('tools.rehab_ml.pose_training.subprocess.Popen') as spawn:
            with self.assertRaisesRegex(ValueError, 'insufficient_space'):
                train_pose(self.source)
            spawn.assert_not_called()
        self.assertFalse((self.root/'training').exists())

    def test_timeout_releases_only_owned_child_and_never_returns_success(self):
        process = Mock()
        process.wait.side_effect = [subprocess.TimeoutExpired('TEST', 120), 0]
        process.poll.side_effect = [None, 0]
        with patch('tools.rehab_ml.pose_training.subprocess.Popen', return_value=process):
            with self.assertRaisesRegex(TimeoutError, 'no_success_claim'):
                train_pose(self.source)
        process.terminate.assert_called_once()
        failure = read_json(self.root/'training/failure.json')
        self.assertFalse(failure['completed'])
        self.assertTrue(failure['owned_exit_confirmed'])

    def test_release_unconfirmed_is_not_timeout_success(self):
        process = Mock()
        process.wait.side_effect = subprocess.TimeoutExpired('TEST', 120)
        process.poll.return_value = None
        with patch('tools.rehab_ml.pose_training.subprocess.Popen', return_value=process):
            with self.assertRaisesRegex(RuntimeError, 'release_unconfirmed'):
                train_pose(self.source)
        self.assertFalse(read_json(self.root/'training/failure.json')['owned_exit_confirmed'])
        process.kill.assert_called_once()

    def test_cancel_request_is_not_proof_of_exit(self):
        output = self.root/'training'
        output.mkdir()
        write_json(output/'resolved-config.json', self.config)
        write_json(output/'request.json', dict(version=VERSION, output_dir=str(output),
            resolved_config_sha256=file_hash(output/'resolved-config.json')))
        response = request_cancel(output)
        self.assertTrue(response['cancel_requested'])
        self.assertFalse(response['exit_confirmed'])
        self.assertTrue((output/'cancel.request').is_file())

    def test_cancel_outside_run_and_wrong_request_refused(self):
        with self.assertRaisesRegex(ValueError, 'dedicated_ignored'):
            request_cancel(ROOT/'docs')
        output = self.root/'training'
        output.mkdir()
        write_json(output/'resolved-config.json', self.config)
        write_json(output/'request.json', dict(version='wrong', output_dir=str(output),
            resolved_config_sha256=file_hash(output/'resolved-config.json')))
        with self.assertRaisesRegex(ValueError, 'owned_pose_training_request'):
            request_cancel(output)

    def test_cancel_uses_frozen_run_not_deleted_external_config(self):
        output = self.root/'training'
        output.mkdir()
        write_json(output/'resolved-config.json', self.config)
        write_json(output/'request.json', dict(version=VERSION, output_dir=str(output),
            resolved_config_sha256=file_hash(output/'resolved-config.json')))
        self.source.unlink()
        self.assertTrue(request_cancel(output)['cancel_requested'])

    def test_cancel_rejects_tampered_frozen_config(self):
        output = self.root/'training'
        output.mkdir()
        write_json(output/'resolved-config.json', self.config)
        write_json(output/'request.json', dict(version=VERSION, output_dir=str(output),
            resolved_config_sha256=file_hash(output/'resolved-config.json')))
        write_json(output/'resolved-config.json', dict(self.config, seed=0))
        with self.assertRaisesRegex(ValueError, 'owned_pose_training_request'):
            request_cancel(output)

    def test_os_lease_enforces_capacity_and_release(self):
        with TrainingLease():
            with self.assertRaisesRegex(RuntimeError, 'capacity_one'):
                with TrainingLease():
                    self.fail('two live trainers acquired the same OS lease')
        with TrainingLease():
            pass

    def test_create_process_failure_is_explicit(self):
        with patch('tools.rehab_ml.pose_training.subprocess.Popen', side_effect=OSError('TEST creation failure')):
            with self.assertRaises(OSError):
                train_pose(self.source)
        self.assertEqual(read_json(self.root/'training/failure.json')['status'], 'process_creation_failed')

    def test_keyboard_cancel_preserves_failure_and_owned_release(self):
        process = Mock()
        process.wait.side_effect = [KeyboardInterrupt(), 0]
        process.poll.side_effect = [None, 0]
        with patch('tools.rehab_ml.pose_training.subprocess.Popen', return_value=process):
            with self.assertRaises(KeyboardInterrupt):
                train_pose(self.source)
        self.assertTrue(read_json(self.root/'training/failure.json')['owned_exit_confirmed'])
        self.assertFalse((self.root/'training/result.json').exists())

    def test_research_baseline_problem_gate_precedes_optimizer(self):
        # Controlled gate-only injection, not fabricated human supervision.
        self.config['mode'] = 'research'
        self.save()
        output = self.root/'training'
        output.mkdir()
        request = write_json(output/'request.json', dict(config=str(self.source), config_sha256=file_hash(self.source),
            reference_sha256=file_hash(self.reference)))
        perfect = dict(summary=dict(coordinate_reference_count=15, pck_all_coordinate_references=1., coordinate_coverage=1.))
        with patch('tools.rehab_ml.pose_training.qualified_reference', return_value=(self.reference, self.data, file_hash(self.reference))), \
                patch('tools.rehab_ml.pose_training.infer_split', return_value=perfect), \
                patch('torch.optim.AdamW') as optimizer:
            with self.assertRaisesRegex(ValueError, 'does_not_demonstrate'):
                run_child(request)
            optimizer.assert_not_called()
        self.assertFalse((output/'best.pt').exists())


if __name__ == '__main__':
    unittest.main()
