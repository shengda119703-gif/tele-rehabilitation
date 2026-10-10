"""TEST loss, assignment, transform and owned-child faults; not human accuracy."""
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import torch
from PIL import Image
from ultralytics.utils.loss import KeypointLoss, v8PoseLoss
from tools.rehab_ml.common import file_hash, paths, read_json, write_json
from tools.rehab_ml.pose_dataset import JOINTS, REFERENCE_VERSION
from tools.rehab_ml.pose_masked_loss import (MaskedPoseLoss, assigned_targets, implementation_contract,
                                            masked_keypoint_terms, validate_batch)
from tools.rehab_ml.pose_masked_smoke import smoke_masked_pose, training_batch


def fixture(root):
    evidence = root/'TEST-permission.txt'
    evidence.write_text('SYNTHETIC TEST engineering loss fixture only; no human labels or clinical truth.', encoding='utf-8')
    value = dict(schema_version=REFERENCE_VERSION, schema_id='coco17-v1', coordinate_space='raw_image_pixels',
        keypoint_order=list(JOINTS), dataset_id='TEST-masked-loss', usage_context='TEST',
        permissions=dict(analysis=True, training=True, verified_by='TEST-reviewer', evidence_ref=evidence.name,
                         evidence_sha256=file_hash(evidence)), samples=[])
    for i, split in enumerate(('train', 'val', 'test')):
        image = root/(split+'.png')
        Image.new('RGB', (96, 64), (180+20*i,)*3).save(image)
        points, visibility, masks = [[12.+j, 20.+j%3] for j in range(17)], [2]*17, [True]*17
        points[0], visibility[0], masks[0] = None, None, False
        points[9], visibility[9] = None, 0
        value['samples'].append(dict(sample_id='TEST-'+split, subject_group='TEST-person-'+split,
            recording_id='TEST-recording-'+split, split=split, exercise_id='shoulder_abduction', side='left', view='front',
            image_ref=image.name, image_sha256=file_hash(image), frame_seq=0, source_time_s=0.,
            time_basis='synthetic_test_time', frame_size=[96, 64], bbox_xyxy_px=[0., 0., 96., 64.],
            bbox_origin='fixture_box', xy=points, visibility=visibility, annotation_mask=masks,
            annotations=dict(origin='synthetic_fixture', annotator='TEST-annotator', reviewer='TEST-reviewer',
                             version='TEST-v1', independently_reviewed=True)))
    source = Path(write_json(root/'reference.json', value))
    return source, value


def minimal_model():
    model = torch.nn.Module()
    model.register_parameter('TEST_parameter', torch.nn.Parameter(torch.zeros(1)))
    head = torch.nn.Module()
    head.kpt_shape, head.nc, head.reg_max, head.stride = [17, 3], 1, 16, torch.tensor([8., 16., 32.])
    model.model = torch.nn.ModuleList([head])
    model.args = SimpleNamespace(box=7.5, pose=12., kobj=1., cls=.5, dfl=1.5)
    return model


def artificial_batch():
    return dict(img=torch.zeros(1, 3, 64, 64), batch_idx=torch.zeros(1), cls=torch.zeros(1, 1),
        bboxes=torch.tensor([[.5, .5, .8, .8]]),
        keypoints=torch.tensor([[[.5, .5, 2.]]*17]), annotation_mask=torch.ones(1, 17, dtype=torch.bool))


def artificial_predictions():
    torch.manual_seed(17)
    features = [torch.randn(1, 65, n, n, requires_grad=True) for n in (8, 4, 2)]
    return features, torch.randn(1, 51, 84, requires_grad=True)


class MaskedPoseLossTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.threads = torch.get_num_threads()
        torch.set_num_threads(2)

    @classmethod
    def tearDownClass(cls):
        torch.set_num_threads(cls.threads)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=paths()['run'])
        self.root = Path(self.directory.name)
        self.source, self.reference = fixture(self.root)

    def tearDown(self):
        self.directory.cleanup()

    def terms(self, *, anchors=1):
        predicted = torch.ones(anchors, 17, 3, requires_grad=True)
        target = torch.zeros_like(predicted)
        target[..., 2] = 2.
        annotated = torch.ones(anchors, 17, dtype=torch.bool)
        return predicted, target, annotated, torch.ones(anchors, 1)*100., torch.ones(17)*.1

    def test_unknown_xy_and_objectness_have_zero_output_gradient(self):
        p, t, a, area, sigma = self.terms()
        a[:, 0] = False
        t[:, 0] = 0.
        x, v = masked_keypoint_terms(p, t, a, area, sigma)
        (x+v).backward()
        self.assertTrue(torch.equal(p.grad[:, 0], torch.zeros(1, 3)))
        self.assertGreater(float(p.grad[:, 1:].abs().sum()), 0.)

    def test_reviewed_not_locatable_is_only_objectness_negative(self):
        p, t, a, area, sigma = self.terms()
        t[:, 0] = 0.
        x, v = masked_keypoint_terms(p, t, a, area, sigma)
        (x+v).backward()
        self.assertTrue(torch.equal(p.grad[:, 0, :2], torch.zeros(1, 2)))
        self.assertGreater(float(p.grad[0, 0, 2]), 0.)  # SGD reduces the absent logit.
        self.assertLess(float(p.grad[0, 1, 2]), 0.)  # Reviewed present logit moves up.

    def test_all_unknown_terms_are_zero_with_zero_gradient(self):
        p, t, a, area, sigma = self.terms()
        a[:] = False
        t[:] = 0.
        x, v = masked_keypoint_terms(p, t, a, area, sigma)
        self.assertEqual(float((x+v).detach()), 0.)
        (x+v).backward()
        self.assertTrue(torch.equal(p.grad, torch.zeros_like(p)))

    def test_reviewed_occluded_coordinate_is_not_an_unannotated_joint(self):
        p, t, a, area, sigma = self.terms()
        t[..., 2] = 1.
        x, v = masked_keypoint_terms(p, t, a, area, sigma)
        (x+v).backward()
        self.assertGreater(float(p.grad[..., :2].abs().sum()), 0.)
        self.assertTrue(bool((p.grad[..., 2] < 0).all()))

    def test_unknown_anchors_do_not_dilute_supervised_denominators(self):
        p, t, a, area, sigma = self.terms(anchors=2)
        one = masked_keypoint_terms(p[:1], t[:1], a[:1], area[:1], sigma)
        a[1] = False
        t[1] = 0.
        two = masked_keypoint_terms(p, t, a, area, sigma)
        for expected, actual in zip(one, two):
            self.assertTrue(torch.equal(expected, actual))

    def test_complete_coordinates_match_locked_keypoint_loss(self):
        p, t, a, area, sigma = self.terms(anchors=3)
        location, visibility = masked_keypoint_terms(p, t, a, area, sigma)
        self.assertAlmostEqual(float(location.detach()), float(KeypointLoss(sigma)(p, t, a, area).detach()), places=6)
        self.assertAlmostEqual(float(visibility.detach()), float(torch.nn.functional.binary_cross_entropy_with_logits(
            p[..., 2], torch.ones(3, 17)).detach()), places=6)

    def test_no_foreground_returns_graph_attached_zeros(self):
        p, t, a, area, sigma = self.terms(anchors=0)
        x, v = masked_keypoint_terms(p, t, a, area, sigma)
        (x+v).backward()
        self.assertEqual(p.grad.numel(), 0)

    def test_invalid_visibility_nonfinite_area_and_masks_refused(self):
        for change in ('visibility', 'nan', 'area', 'mask'):
            values = list(self.terms())
            if change == 'visibility': values[1][0, 0, 2] = .5
            if change == 'nan': values[0] = values[0].detach(); values[0][0, 0, 0] = float('nan')
            if change == 'area': values[3][0] = 0.
            if change == 'mask': values[2] = values[2].float()
            with self.subTest(change=change), self.assertRaises(ValueError): masked_keypoint_terms(*values)

    def test_assignment_tracks_per_image_gt_and_mask_not_global_ordinal(self):
        points = torch.zeros(3, 17, 3)
        points[:, :, 0] = torch.tensor([10., 20., 30.]).view(-1, 1)
        annotations = torch.zeros(3, 17, dtype=torch.bool)
        annotations[0, 6], annotations[1, 8], annotations[2, 9] = True, True, True
        foreground = torch.tensor([[True, True], [False, True], [False, False]])
        ordinal = torch.tensor([[1, 0], [999, 0], [999, 999]])
        target, mask, images, anchors = assigned_targets(foreground, ordinal, points,
            torch.tensor([0., 1., 0.]), annotations)
        self.assertEqual(target[:, 0, 0].tolist(), [30., 10., 20.])
        self.assertEqual(mask.nonzero().tolist(), [[0, 9], [1, 6], [2, 8]])
        self.assertEqual(images.tolist(), [0, 0, 1])
        self.assertEqual(anchors.tolist(), [0, 1, 1])

    def test_foreground_out_of_range_gt_and_fractional_image_id_refused(self):
        foreground = torch.tensor([[True]])
        for ordinal, index in ((1, 0.), (0, .5)):
            with self.assertRaises(ValueError): assigned_targets(foreground, torch.tensor([[ordinal]]),
                torch.zeros(1, 17, 3), torch.tensor([index]), torch.ones(1, 17, dtype=torch.bool))

    def test_batch_requires_annotation_mask_independent_integer_visibility(self):
        for change in ('missing', 'floatmask', 'confidence', 'unknown_coordinates', 'fractional_id', 'class', 'bbox'):
            batch = artificial_batch()
            if change == 'missing': del batch['annotation_mask']
            if change == 'floatmask': batch['annotation_mask'] = batch['annotation_mask'].float()
            if change == 'confidence': batch['keypoints'][0, 0, 2] = .5
            if change == 'unknown_coordinates': batch['annotation_mask'][0, 0] = False
            if change == 'fractional_id': batch['batch_idx'][0] = .5
            if change == 'class': batch['cls'][0] = 1.
            if change == 'bbox': batch['bboxes'][0, 2] = 0.
            with self.subTest(change=change), self.assertRaises(ValueError): validate_batch(batch)

    def test_current_library_source_pinned_not_just_version(self):
        contract = implementation_contract()
        self.assertEqual(contract['ultralytics'], '8.3.199')
        self.assertFalse(contract['product_enabled'])
        with patch('tools.rehab_ml.pose_masked_loss.LOSS_SOURCE_SHA256', 'a'*64):
            with self.assertRaisesRegex(ValueError, 'source'): implementation_contract()

    def test_complete_batch_stock_detection_and_pose_components_match(self):
        model, predictions, batch = minimal_model(), artificial_predictions(), artificial_batch()
        criterion = MaskedPoseLoss(model)
        expected, expected_detached = v8PoseLoss(model)(predictions, batch)
        actual, detached = criterion(predictions, batch)
        self.assertTrue(torch.allclose(actual, expected, atol=1e-5, rtol=1e-6))
        self.assertTrue(torch.allclose(detached, expected_detached, atol=1e-5, rtol=1e-6))
        self.assertGreater(criterion.last_mask_stats['assigned_anchors'], 0)
        self.assertIsNone(criterion._annotation_mask)

    def test_actual_parent_assignment_backward_preserves_unknown_output_slots(self):
        batch, predictions = artificial_batch(), artificial_predictions()
        batch['annotation_mask'][0, 0] = False
        batch['keypoints'][0, 0] = 0.
        criterion = MaskedPoseLoss(minimal_model())
        predictions[1].retain_grad()
        stock, _ = v8PoseLoss(minimal_model())(predictions, batch)
        old = torch.autograd.grad(stock.sum(), predictions[1], retain_graph=True)[0]
        self.assertGreater(float(old[:, :3].abs().sum()), 0.)
        predictions[1].grad = None
        loss, _ = criterion(predictions, batch)
        loss.sum().backward()
        gradient = predictions[1].grad.view(1, 17, 3, -1)
        self.assertEqual(float(gradient[:, 0].abs().sum()), 0.)
        self.assertGreater(float(gradient[:, 1:].abs().sum()), 0.)

    def test_all_unknown_pose_does_not_disable_independent_person_box_supervision(self):
        batch, predictions = artificial_batch(), artificial_predictions()
        batch['annotation_mask'][:] = False
        batch['keypoints'][:] = 0.
        criterion = MaskedPoseLoss(minimal_model())
        loss, detached = criterion(predictions, batch)
        self.assertEqual(detached[1:3].tolist(), [0., 0.])
        self.assertGreater(float(detached[0]+detached[3]+detached[4]), 0.)
        loss.sum().backward()
        self.assertEqual(float(predictions[1].grad.abs().sum()), 0.)
        self.assertGreater(float(predictions[0][0].grad.abs().sum()), 0.)

    def test_full_image_without_person_targets_has_no_pose_supervision(self):
        batch, predictions = artificial_batch(), artificial_predictions()
        for key in ('batch_idx', 'cls', 'bboxes', 'keypoints', 'annotation_mask'):
            batch[key] = batch[key][:0]
        criterion = MaskedPoseLoss(minimal_model())
        loss, detached = criterion(predictions, batch)
        self.assertEqual(detached[1:3].tolist(), [0., 0.])
        self.assertEqual(criterion.last_mask_stats['assigned_anchors'], 0)
        loss.sum().backward()
        self.assertIsNone(predictions[1].grad)

    def test_nonfinite_wrong_size_and_known_absent_coordinates_are_rejected(self):
        for change in ('nan', 'size', 'absent', 'too_many_objects'):
            batch = artificial_batch()
            if change == 'nan': batch['img'][0, 0, 0, 0] = float('nan')
            if change == 'size': batch['img'] = torch.zeros(1, 3, 641, 641)
            if change == 'absent': batch['keypoints'][0, 0, 2] = 0.
            if change == 'too_many_objects': batch['keypoints'] = torch.zeros(65, 17, 3)
            with self.subTest(change=change), self.assertRaises(ValueError): validate_batch(batch)

    def test_failure_and_next_batch_cannot_leak_annotations_or_lock(self):
        criterion = MaskedPoseLoss(minimal_model())
        invalid = artificial_batch()
        del invalid['annotation_mask']
        with self.assertRaises(ValueError): criterion(artificial_predictions(), invalid)
        self.assertIsNone(criterion._annotation_mask)
        criterion(artificial_predictions(), artificial_batch())
        self.assertEqual(criterion.last_mask_stats['coordinate_slots'], criterion.last_mask_stats['objectness_slots'])
        criterion._call_lock.acquire()
        try:
            with self.assertRaisesRegex(RuntimeError, 'concurrent'): criterion(artificial_predictions(), artificial_batch())
        finally: criterion._call_lock.release()

    def test_rectangular_pixel_transform_and_masks_use_train_only(self):
        batch, provenance = training_batch(self.source)
        transform = provenance['transforms'][0]
        self.assertEqual(provenance['train_sample_ids'], ['TEST-train'])
        self.assertFalse(provenance['validation_test_used_for_optimization'])
        self.assertEqual(transform['resized_size'], [128, 85])
        self.assertEqual(transform['pad_left_top'], [0, 21])
        self.assertAlmostEqual(float(batch['keypoints'][0, 6, 0]), 18/96, places=6)
        self.assertAlmostEqual(float(batch['keypoints'][0, 6, 1]), (20*85/64+21)/128, places=6)
        self.assertEqual(batch['keypoints'][0, 0].tolist(), [0., 0., 0.])
        self.assertFalse(batch['annotation_mask'][0, 0])
        self.assertTrue(batch['annotation_mask'][0, 9])

    def test_training_permission_and_bounded_batch_required(self):
        self.reference['permissions']['training'] = False
        write_json(self.source, self.reference)
        with self.assertRaisesRegex(ValueError, 'permission'): training_batch(self.source)
        with self.assertRaises(ValueError): training_batch(self.source, image_size=129)

    def test_smoke_rejects_non_test_data_before_output_or_process(self):
        self.reference['usage_context'] = 'RESEARCH'
        write_json(self.source, self.reference)
        with patch('tools.rehab_ml.pose_masked_smoke.subprocess.Popen') as process:
            with self.assertRaises(ValueError): smoke_masked_pose(self.source, self.root/'must-not-exist')
        process.assert_not_called()
        self.assertFalse((self.root/'must-not-exist').exists())

    def test_timeout_terminates_only_owned_child_and_has_no_success(self):
        process = Mock(pid=123)
        process.poll.side_effect = [None, 0]
        process.wait.side_effect = [subprocess.TimeoutExpired('TEST-child', 5), 0]
        with patch('tools.rehab_ml.pose_masked_smoke.subprocess.Popen', return_value=process):
            with self.assertRaises(TimeoutError): smoke_masked_pose(self.source, self.root/'timeout', timeout_s=5)
        process.terminate.assert_called_once_with()
        process.kill.assert_not_called()
        self.assertTrue(read_json(self.root/'timeout/failure.json')['owned_exit_confirmed'])
        self.assertFalse((self.root/'timeout/result.json').exists())

    def test_keyboard_cancel_and_unconfirmed_release_do_not_claim_success(self):
        for unconfirmed in (False, True):
            process = Mock(pid=123)
            process.poll.return_value = None if unconfirmed else 0
            if not unconfirmed: process.poll.side_effect = [None, 0]
            process.wait.side_effect = ([KeyboardInterrupt(), subprocess.TimeoutExpired('TEST-child', 2),
                                        subprocess.TimeoutExpired('TEST-child', 2)] if unconfirmed else [KeyboardInterrupt(), 0])
            output = self.root/('unconfirmed' if unconfirmed else 'cancel')
            with patch('tools.rehab_ml.pose_masked_smoke.subprocess.Popen', return_value=process):
                with self.assertRaises(RuntimeError if unconfirmed else KeyboardInterrupt):
                    smoke_masked_pose(self.source, output, timeout_s=5)
            process.terminate.assert_called_once_with()
            self.assertEqual(process.kill.call_count, int(unconfirmed))
            self.assertFalse((output/'result.json').exists())
            self.assertEqual(read_json(output/'failure.json')['owned_exit_confirmed'], not unconfirmed)


if __name__ == '__main__':
    unittest.main()
