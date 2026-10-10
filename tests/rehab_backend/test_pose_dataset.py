"""Synthetic tool fixtures, never human reference accuracy or training."""
import copy
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.rehab_ml.common import file_hash, paths, read_json, write_json
from tools.rehab_ml.pose_dataset import JOINTS, FLIP, REFERENCE_VERSION, PREDICTION_VERSION, convert, evaluate, load_reference
from tools.rehab_ml.cli import main, parser


class PoseDatasetTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=paths()['run'])
        self.root = Path(self.directory.name)
        evidence = self.root/'TEST-permission.txt'
        evidence.write_text('SYNTHETIC TEST fixture only. No patient or clinical reference.', encoding='utf-8')
        self.reference = dict(schema_version=REFERENCE_VERSION, schema_id='coco17-v1',
            coordinate_space='raw_image_pixels', keypoint_order=list(JOINTS), dataset_id='TEST-pose-tools',
            usage_context='TEST', permissions=dict(analysis=True, training=True, verified_by='TEST-reviewer',
                evidence_ref=evidence.name, evidence_sha256=file_hash(evidence)), samples=[])
        for index, split in enumerate(('train', 'val', 'test')):
            image = self.root/(split+'.png')
            Image.new('RGB', (64, 64), (200+index*10,)*3).save(image)
            self.reference['samples'].append(dict(sample_id='TEST-'+split, subject_group='TEST-person-'+split,
                recording_id='TEST-recording-'+split, split=split, exercise_id='shoulder_abduction',
                side='left', view='front', image_ref=image.name, image_sha256=file_hash(image), frame_seq=0,
                source_time_s=0., time_basis='synthetic_test_time', frame_size=[64, 64],
                bbox_xyxy_px=[0., 0., 64., 64.], bbox_origin='fixture_box',
                xy=[[10.+i, 15.+i%3] for i in range(17)], visibility=[2]*17, annotation_mask=[True]*17,
                annotations=dict(origin='synthetic_fixture', annotator='TEST-annotator', reviewer='TEST-reviewer',
                                 version='TEST-v1', independently_reviewed=True)))
        self.source = self.root/'reference.json'
        self.save_reference()
        self.predictions = dict(schema_version=PREDICTION_VERSION, schema_id='coco17-v1',
            coordinate_space='raw_image_pixels', keypoint_order=list(JOINTS), reference_sha256=file_hash(self.source),
            model=dict(model_id='TEST-fixture-model', weights_sha256='a'*64, trained_on_reference=False), samples=[])
        self.add_prediction()
        self.prediction_path = self.root/'predictions.json'
        self.save_predictions()

    def tearDown(self):
        self.directory.cleanup()

    def save_reference(self):
        write_json(self.source, self.reference)

    def add_prediction(self):
        sample = self.reference['samples'][2]
        row = {key: copy.deepcopy(sample[key]) for key in ('sample_id', 'subject_group', 'recording_id',
                'image_sha256', 'frame_size', 'frame_seq', 'source_time_s')}
        row.update(status='matched', xy=copy.deepcopy(sample['xy']), conf=[1.]*17)
        self.predictions['samples'].append(row)

    def save_predictions(self):
        self.predictions['reference_sha256'] = file_hash(self.source)
        write_json(self.prediction_path, self.predictions)

    def result(self, **kwargs):
        return read_json(evaluate(self.source, self.prediction_path, self.root/'evaluation', **kwargs)['path'])

    def test_masked_conversion_preserves_unknown_and_separate_loss_masks(self):
        row = self.reference['samples'][0]
        row['annotation_mask'][9], row['visibility'][9], row['xy'][9] = False, None, None
        self.save_reference()
        result = read_json(convert(self.source, self.root/'masked')['path'])
        converted = result['converted_samples'][0]
        self.assertIsNone(converted['xy'][9])
        self.assertFalse(converted['coordinate_loss_mask'][9])
        self.assertFalse(converted['visibility_loss_mask'][9])
        self.assertFalse(result['fine_tuning_qualified'])
        self.assertFalse((self.root/'masked'/'dataset.yaml').exists())

    def test_partial_annotation_refuses_stock_yolo_before_output_creation(self):
        row = self.reference['samples'][0]
        row['annotation_mask'][0], row['visibility'][0], row['xy'][0] = False, None, None
        self.save_reference()
        with self.assertRaisesRegex(ValueError, 'partial_annotation'):
            convert(self.source, self.root/'yolo', output_format='yolo_pose')
        self.assertFalse((self.root/'yolo').exists())

    def test_yolo_complete_labels_use_original_bbox_axes_and_anatomical_flip(self):
        import yaml
        result = convert(self.source, self.root/'yolo', output_format='yolo_pose')
        values = [float(value) for value in (self.root/'yolo/labels/train/TEST-train.txt').read_text().split()]
        self.assertEqual(len(values), 56)
        self.assertEqual(values[:5], [0., .5, .5, 1., 1.])
        self.assertEqual(values[5:8], [10/64, 15/64, 2.])
        definition = yaml.safe_load((self.root/'yolo/dataset.yaml').read_text())
        self.assertEqual(definition['flip_idx'], list(FLIP))
        self.assertTrue(result['labels_format_ready'])
        self.assertFalse(result['fine_tuning_qualified'])
        self.assertEqual(file_hash(self.root/'yolo/images/test/TEST-test.png'), self.reference['samples'][2]['image_sha256'])

    def test_explicit_known_not_locatable_is_distinct_from_unannotated(self):
        row = self.reference['samples'][2]
        row['visibility'][0], row['xy'][0] = 0, None
        self.save_reference()
        self.save_predictions()
        result = self.result()['summary']
        self.assertEqual(result['coordinate_reference_count'], 16)
        self.assertEqual(result['known_not_locatable_count'], 1)
        self.assertEqual(result['predicted_present_on_not_locatable'], 1)
        self.assertEqual(result['unannotated'], 0)

    def test_permission_analysis_and_training_are_separate(self):
        self.reference['permissions']['training'] = False
        self.save_reference()
        convert(self.source, self.root/'masked')
        with self.assertRaisesRegex(ValueError, 'permission'):
            convert(self.source, self.root/'yolo', output_format='yolo_pose')

    def test_permission_evidence_hash_is_verified(self):
        self.reference['permissions']['evidence_sha256'] = 'b'*64
        self.save_reference()
        with self.assertRaisesRegex(ValueError, 'file_hash'):
            load_reference(self.source)

    def test_image_hash_and_original_pixel_size_are_verified(self):
        for change in ('hash', 'size'):
            with self.subTest(change=change):
                original = copy.deepcopy(self.reference)
                if change == 'hash':
                    self.reference['samples'][0]['image_sha256'] = 'f'*64
                else:
                    self.reference['samples'][0]['frame_size'] = [128, 64]
                self.save_reference()
                with self.assertRaises(ValueError):
                    load_reference(self.source)
                self.reference = original

    def test_schema_joint_order_and_coordinate_space_must_be_explicit(self):
        for key, value in (('schema_id', 'kinect25-v1'), ('coordinate_space', 'normalized_xy'),
                           ('keypoint_order', list(reversed(JOINTS)))):
            with self.subTest(key=key):
                original = copy.deepcopy(self.reference)
                self.reference[key] = value
                self.save_reference()
                with self.assertRaisesRegex(ValueError, 'contract'):
                    load_reference(self.source)
                self.reference = original

    def test_subject_recording_and_image_hash_leakage_all_rejected(self):
        for key in ('subject_group', 'recording_id', 'image_sha256'):
            with self.subTest(key=key):
                original = copy.deepcopy(self.reference)
                self.reference['samples'][2][key] = self.reference['samples'][0][key]
                self.save_reference()
                with self.assertRaisesRegex(ValueError, 'leakage'):
                    load_reference(self.source)
                self.reference = original

    def test_model_pseudo_labels_and_unreviewed_human_references_refused(self):
        for key, value in (('origin', 'model'), ('independently_reviewed', False), ('reviewer', 'TEST-annotator')):
            with self.subTest(key=key):
                original = copy.deepcopy(self.reference)
                self.reference['samples'][0]['annotations'][key] = value
                self.save_reference()
                with self.assertRaisesRegex(ValueError, 'annotation'):
                    load_reference(self.source)
                self.reference = original

    def test_nonmonotonic_recording_time_and_derived_arm_bbox_denied(self):
        second = copy.deepcopy(self.reference['samples'][0])
        second['sample_id'], second['frame_seq'] = 'TEST-train-second', 1
        self.reference['samples'].append(second)
        self.save_reference()
        with self.assertRaisesRegex(ValueError, 'time_must_increase'):
            load_reference(self.source)
        self.reference['samples'].pop()
        self.reference['samples'][0]['bbox_origin'] = 'visible_arm_points'
        self.save_reference()
        with self.assertRaisesRegex(ValueError, 'bbox_origin'):
            load_reference(self.source)

    def test_stock_yolo_zero_only_for_explicit_annotated_not_locatable(self):
        row = self.reference['samples'][0]
        row['xy'][0], row['visibility'][0] = None, 0
        self.save_reference()
        convert(self.source, self.root/'known-absent', output_format='yolo_pose')
        label = [float(n) for n in (self.root/'known-absent/labels/train/TEST-train.txt').read_text().split()]
        self.assertEqual(label[5:8], [0., 0., 0.])
        converted = read_json(self.root/'known-absent/conversion.json')['converted_samples'][0]
        self.assertFalse(converted['coordinate_loss_mask'][0])
        self.assertTrue(converted['visibility_loss_mask'][0])

    def test_confidence_float_cannot_be_human_visibility(self):
        self.reference['samples'][0]['visibility'][0] = .9
        self.save_reference()
        with self.assertRaisesRegex(ValueError, 'visibility'):
            load_reference(self.source)

    def test_unknown_joint_zero_placeholder_is_not_a_negative_label(self):
        self.reference['samples'][0]['annotation_mask'][0] = False
        self.reference['samples'][0]['visibility'][0] = None
        self.reference['samples'][0]['xy'][0] = [0., 0.]
        self.save_reference()
        with self.assertRaisesRegex(ValueError, 'remain_null'):
            load_reference(self.source)

    def test_paths_windows_aliases_and_no_overwrite(self):
        original = copy.deepcopy(self.reference)
        self.reference['samples'][0]['image_ref'] = '../outside.png'
        self.save_reference()
        with self.assertRaisesRegex(ValueError, 'escape'):
            load_reference(self.source)
        self.reference = copy.deepcopy(original)
        self.reference['samples'][1]['sample_id'] = 'test-TRAIN'
        self.save_reference()
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            load_reference(self.source)
        self.reference = copy.deepcopy(original)
        self.save_reference()
        convert(self.source, self.root/'masked')
        before = file_hash(self.root/'masked/conversion.json')
        with self.assertRaises(FileExistsError):
            convert(self.source, self.root/'masked')
        self.assertEqual(file_hash(self.root/'masked/conversion.json'), before)
        with self.assertRaisesRegex(ValueError, 'ignored'):
            convert(self.source, ROOT/'docs/TEST-pose-output-must-not-exist')
        self.assertFalse((ROOT/'docs/TEST-pose-output-must-not-exist').exists())

    def test_non_square_original_pixels_not_double_normalized(self):
        row = self.reference['samples'][0]
        image = self.root/row['image_ref']
        Image.new('RGB', (128, 64), 'white').save(image)
        row['frame_size'] = [128, 64]
        row['image_sha256'] = file_hash(image)
        row['bbox_xyxy_px'] = [0., 0., 128., 64.]
        self.save_reference()
        convert(self.source, self.root/'nonsquare', output_format='yolo_pose')
        label = [float(n) for n in (self.root/'nonsquare/labels/train/TEST-train.txt').read_text().split()]
        self.assertEqual(label[5:8], [10/128, 15/64, 2.])

    def test_fixture_cannot_be_relabelled_as_real_research_reference(self):
        self.reference['usage_context'] = 'RESEARCH'
        self.save_reference()
        with self.assertRaisesRegex(ValueError, 'annotation'):
            load_reference(self.source)

    def test_exact_geometry_errors_coverage_and_pck_denominators(self):
        self.predictions['samples'][0]['xy'] = [[x+3, y+4] for x, y in self.predictions['samples'][0]['xy']]
        self.save_predictions()
        result = self.result()
        self.assertEqual(result['summary']['mean_euclidean_error_px'], 5.)
        self.assertAlmostEqual(result['summary']['mean_bbox_diagonal_normalized_error'], 5/(64*2**.5))
        self.assertEqual(result['summary']['coordinate_coverage'], 1.)
        self.assertEqual(result['summary']['pck_all_coordinate_references'], 0.)
        self.assertEqual(result['evidence_scope'], 'synthetic_tool_verification_not_target_accuracy')
        self.assertIsNone(result['clinical_accuracy'])

    def test_missing_point_counts_against_coverage_not_zero_error(self):
        row = self.predictions['samples'][0]
        row['xy'][0], row['conf'][0] = None, None
        self.save_predictions()
        result = self.result()['summary']
        self.assertEqual(result['covered_coordinate_count'], 16)
        self.assertAlmostEqual(result['coordinate_coverage'], 16/17)
        self.assertAlmostEqual(result['pck_all_coordinate_references'], 16/17)
        self.assertEqual(result['pck_on_covered_coordinates'], 1.)

    def test_absent_sample_is_not_silently_excluded(self):
        self.predictions['samples'] = []
        self.save_predictions()
        result = self.result()
        self.assertEqual(result['summary']['coordinate_coverage'], 0.)
        self.assertIsNone(result['summary']['mean_euclidean_error_px'])
        self.assertEqual(result['summary']['pck_all_coordinate_references'], 0.)
        self.assertEqual(result['observation_states'], {'prediction_missing': 1})

    def test_unannotated_point_does_not_enter_error_or_absence_denominator(self):
        row = self.reference['samples'][2]
        row['xy'][0], row['visibility'][0], row['annotation_mask'][0] = None, None, False
        self.save_reference()
        self.save_predictions()
        result = self.result()['summary']
        self.assertEqual(result['coordinate_reference_count'], 16)
        self.assertEqual(result['unannotated'], 1)
        self.assertEqual(result['known_not_locatable_count'], 0)

    def test_low_confidence_out_of_frame_not_observed(self):
        row = self.predictions['samples'][0]
        row['conf'][0], row['xy'][1] = .49, [-1., 20.]
        self.save_predictions()
        self.assertEqual(self.result()['summary']['covered_coordinate_count'], 15)

    def test_alignment_digest_and_duplicate_predictions_rejected(self):
        for change in ('digest', 'duplicate', 'timestamp'):
            with self.subTest(change=change):
                original = copy.deepcopy(self.predictions)
                if change == 'digest':
                    self.predictions['reference_sha256'] = 'd'*64
                elif change == 'duplicate':
                    self.predictions['samples'] *= 2
                else:
                    self.predictions['samples'][0]['source_time_s'] += 1.
                write_json(self.prediction_path, self.predictions)
                with self.assertRaises(ValueError):
                    evaluate(self.source, self.prediction_path, self.root/'evaluation')
                self.assertFalse((self.root/'evaluation').exists())
                self.predictions = original

    def test_unmatched_status_cannot_carry_predicted_evidence(self):
        self.predictions['samples'][0]['status'] = 'no_person'
        self.save_predictions()
        with self.assertRaisesRegex(ValueError, 'unmatched'):
            self.result()

    def test_candidate_training_and_selection_groups_do_not_leak_test(self):
        model = self.predictions['model']
        model.update(trained_on_reference=True, training_subject_groups=['TEST-person-test'],
                     selection_subject_groups=['TEST-person-val'])
        self.save_predictions()
        with self.assertRaisesRegex(ValueError, 'leakage'):
            self.result()

    def test_left_right_suspected_swap_remains_explicit_not_clinical_accuracy(self):
        row = self.reference['samples'][2]
        row['xy'][5], row['xy'][6] = [10., 10.], [50., 10.]
        self.save_reference()
        self.predictions['samples'][0]['xy'] = copy.deepcopy(row['xy'])
        self.predictions['samples'][0]['xy'][5], self.predictions['samples'][0]['xy'][6] = row['xy'][6], row['xy'][5]
        self.save_predictions()
        summary = self.result()['grouped']['joint']
        self.assertEqual(summary['left_shoulder']['left_right_suspected_swaps'], 1)
        self.assertEqual(summary['right_shoulder']['left_right_suspected_swaps'], 1)

    def test_duplicate_keys_and_nonfinite_json_denied(self):
        for payload in ('{"schema_version":"x","schema_version":"y"}', '{"value":NaN}'):
            self.source.write_text(payload, encoding='utf-8')
            with self.assertRaises(ValueError):
                load_reference(self.source)

    def test_cli_real_conversion_and_evaluation_json_paths_and_failure_exit(self):
        with redirect_stdout(StringIO()) as stdout:
            code = main(['build-pose-dataset', '--reference', str(self.source), '--target-schema', 'coco17',
                         '--output-dir', str(self.root/'cli-conversion')])
        self.assertEqual(code, 0)
        self.assertTrue(Path(json.loads(stdout.getvalue())['result']['path']).is_file())
        with redirect_stdout(StringIO()) as stdout:
            code = main(['evaluate-pose', '--reference', str(self.source), '--predictions', str(self.prediction_path),
                         '--split', 'test', '--output-dir', str(self.root/'cli-evaluation')])
        self.assertEqual(code, 0)
        self.assertTrue(Path(json.loads(stdout.getvalue())['result']['path']).is_file())
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
            code = main(['evaluate-pose', '--reference', str(self.source), '--predictions', str(self.prediction_path),
                         '--split', 'test', '--confidence-min', 'nan', '--output-dir', str(self.root/'failure')])
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(stderr.getvalue())['ok'])
        self.assertFalse((self.root/'failure').exists())

    def test_cli_help_and_old_qualification_commands_preserved(self):
        for command in ('build-pose-dataset', 'infer-pose-reference', 'evaluate-pose'):
            with redirect_stdout(StringIO()) as stdout, self.assertRaises(SystemExit) as raised:
                parser().parse_args([command, '--help'])
            self.assertEqual(raised.exception.code, 0)
            self.assertIn('--', stdout.getvalue())
        args = parser().parse_args(['build-pose-dataset', '--dataset', 'rehab24_6', '--target-schema', 'coco17'])
        self.assertIsNone(args.reference)
        self.assertEqual(args.dataset, 'rehab24_6')

    def test_original_owned_yolo_inference_retains_unobserved_coverage(self):
        from tools.rehab_ml.pose_inference import infer_baseline
        result = infer_baseline(self.source, self.root/'baseline', split='test')
        predictions = read_json(result['path'])
        self.assertTrue(result['owned_release_confirmed'])
        self.assertEqual(result['weights_sha256'], '869e83fcdffdc7371fa4e34cd8e51c838cc729571d1635e5141e3075e9319dc0')
        self.assertEqual(predictions['samples'][0]['status'], 'no_person')
        self.assertEqual(predictions['samples'][0]['xy'], [None]*17)
        assessment = read_json(evaluate(self.source, result['path'], self.root/'baseline-eval')['path'])
        self.assertEqual(assessment['summary']['coordinate_coverage'], 0.)
        self.assertIsNone(assessment['summary']['mean_euclidean_error_px'])
        self.assertEqual(assessment['evidence_scope'], 'synthetic_tool_verification_not_target_accuracy')


if __name__ == '__main__':
    unittest.main()
