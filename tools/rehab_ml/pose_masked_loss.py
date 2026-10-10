"""Offline partial COCO17 supervision for the pinned Ultralytics criterion.

Uses Ultralytics 8.3.199 (AGPL-3.0 / its separately obtained Enterprise route).
No monkey patch, client change, pseudo-label generation or production loading.
Unknown annotation and reviewed not-locatable are deliberately different.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import threading

import torch
from torch.nn import functional as F
import ultralytics
from ultralytics.utils.loss import v8PoseLoss

VERSION = 'rehab-coco17-dual-masked-loss-1'
LOCKED_ULTRALYTICS = '8.3.199'
LOSS_SOURCE_SHA256 = 'c09d05d83a514c8f7e7bd69dc489b68a8d3371745ad114d615339ced6992d7e0'


def implementation_contract():
    import ultralytics.utils.loss as source
    path = Path(source.__file__)
    normalized = path.read_text(encoding='utf-8').replace('\r\n', '\n')
    fingerprint = hashlib.sha256(normalized.encode('utf-8')).hexdigest()
    if ultralytics.__version__ != LOCKED_ULTRALYTICS or fingerprint != LOSS_SOURCE_SHA256:
        raise ValueError('locked_ultralytics_pose_loss_source_required')
    return dict(version=VERSION, ultralytics=ultralytics.__version__, loss_source_sha256=fingerprint,
                code_license_route='Ultralytics AGPL-3.0 or separately obtained Enterprise; no Enterprise asserted',
                stock_detection_loss_reused=True, unknown_coordinate_and_objectness_supervision=False,
                clinical_accuracy=None, product_enabled=False)


def _finite(value):
    return isinstance(value, torch.Tensor) and bool(torch.isfinite(value).all())


def masked_keypoint_terms(predicted, target, annotated, area, sigmas):
    """Assigned anchors only. Gradients at unannotated output slots are zero.

    Coordinate mean: mean over anchors with coordinates of that anchor's mean
    OKS-style error over reviewed locatable joints. Objectness mean: only over
    reviewed slots. Reviewed visibility 0 is a negative ONLY for objectness.
    An entirely unlabelled anchor cannot dilute either supervised denominator.
    """
    if (predicted.ndim != 3 or predicted.shape[-2:] != (17, 3) or target.shape != predicted.shape
            or annotated.shape != predicted.shape[:2] or annotated.dtype != torch.bool
            or area.shape != (len(predicted), 1) or sigmas.shape != (17,)
            or any(not _finite(t) for t in (predicted, target, area, sigmas))
            or bool((area <= 0).any()) or bool((sigmas <= 0).any())
            or bool(~torch.isin(target[..., 2], target.new_tensor([0., 1., 2.])).all())):
        raise ValueError('finite_assigned_coco17_masks_and_positive_bbox_area_required')
    coordinate = annotated & (target[..., 2] != 0)
    squared_distance = (predicted[..., :2]-target[..., :2]).square().sum(-1)
    denominator = (2*sigmas).square() * (area+1e-9) * 2
    errors = -torch.expm1(-squared_distance/denominator)
    count = coordinate.sum(1)
    included = count > 0
    zero = (predicted*0).sum()
    location = ((errors*coordinate).sum(1)[included]/count[included]).mean() if included.any() else zero
    visibility = (F.binary_cross_entropy_with_logits(predicted[..., 2][annotated],
        (target[..., 2][annotated] != 0).to(predicted.dtype), reduction='mean') if annotated.any() else zero)
    return location, visibility


def assigned_targets(foreground, target_gt_idx, keypoints, batch_idx, annotation_mask):
    """Map TAL's per-image GT ordinal to the SAME global object and mask row.

    Never gather a background anchor's dummy ordinal; images with no GT are
    valid. Original order within each image is the locked parent's order.
    """
    if (foreground.ndim != 2 or foreground.dtype != torch.bool or target_gt_idx.shape != foreground.shape
            or target_gt_idx.dtype != torch.long or keypoints.ndim != 3 or keypoints.shape[1:] != (17, 3)
            or batch_idx.numel() != len(keypoints) or annotation_mask.shape != keypoints.shape[:2]
            or annotation_mask.dtype != torch.bool):
        raise ValueError('aligned_assignment_keypoints_and_annotation_masks_required')
    batch_idx = batch_idx.flatten().to(device=keypoints.device)
    if (not _finite(batch_idx) or bool((batch_idx != batch_idx.long()).any())
            or bool(((batch_idx < 0) | (batch_idx >= len(foreground))).any())):
        raise ValueError('integral_assignment_batch_identity_required')
    image_indices, anchor_indices = torch.where(foreground)
    objects = torch.empty(len(image_indices), device=keypoints.device, dtype=torch.long)
    for image in range(len(foreground)):
        selected = image_indices == image
        if not selected.any():
            continue
        global_rows = torch.where(batch_idx == image)[0]
        ordinal = target_gt_idx[image, anchor_indices[selected]]
        if bool(((ordinal < 0) | (ordinal >= len(global_rows))).any()):
            raise ValueError('foreground_assignment_has_no_corresponding_ground_truth')
        objects[selected] = global_rows[ordinal]
    return keypoints[objects].clone(), annotation_mask[objects], image_indices, anchor_indices


def validate_batch(batch):
    if not isinstance(batch, dict) or any(not isinstance(batch.get(k), torch.Tensor) for k in
            ('img', 'batch_idx', 'cls', 'bboxes', 'keypoints', 'annotation_mask')):
        raise ValueError('explicit_dual_masked_training_batch_required')
    images, points, boxes = batch['img'], batch['keypoints'], batch['bboxes']
    if points.ndim != 3:
        raise ValueError('aligned_coco17_target_tensor_required')
    count = len(points)
    if (count > 64 or images.ndim != 4 or not 1 <= len(images) <= 8 or images.shape[1] != 3
            or any(not 64 <= n <= 640 or n % 32 for n in images.shape[2:])
            or not images.is_floating_point() or not _finite(images)
            or bool(((images < 0) | (images > 1)).any())
            or points.shape != (count, 17, 3) or not points.is_floating_point() or not _finite(points)
            or boxes.shape != (count, 4) or not _finite(boxes)
            or batch['annotation_mask'].shape != (count, 17) or batch['annotation_mask'].dtype != torch.bool
            or batch['batch_idx'].numel() != count or batch['cls'].numel() != count
            or any(t.device != images.device for t in (points, boxes, batch['annotation_mask'], batch['batch_idx'], batch['cls']))):
        raise ValueError('bounded_aligned_normalized_pose_training_batch_required')
    indices = batch['batch_idx'].flatten()
    if (not _finite(indices) or bool((indices != indices.long()).any())
            or bool(((indices < 0) | (indices >= len(images))).any())
            or not _finite(batch['cls']) or bool((batch['cls'] != 0).any())
            or bool(((boxes < 0) | (boxes > 1)).any()) or bool((boxes[:, 2:] <= 0).any())
            or bool((boxes[:, :2]-boxes[:, 2:]/2 < -1e-6).any())
            or bool((boxes[:, :2]+boxes[:, 2:]/2 > 1+1e-6).any())):
        raise ValueError('person_class_integral_batch_id_and_full_person_bbox_required')
    visibility, mask = points[..., 2], batch['annotation_mask']
    if (not torch.isin(visibility, visibility.new_tensor([0., 1., 2.])).all()
            or bool(((points[..., :2] < 0) | (points[..., :2] > 1)).any())
            or bool((points[~mask] != 0).any()) or bool((points[..., :2][visibility == 0] != 0).any())):
        raise ValueError('independent_visibility_and_zero_only_unlabelled_placeholders_required')


class MaskedPoseLoss(v8PoseLoss):
    """Opt-in criterion instance, not a replacement of the installed library.

    Single caller per instance; one call's labels cannot leak into another.
    Detection/assignment/gains remain the pinned parent implementation.
    """
    def __init__(self, model):
        self.contract = implementation_contract()
        if model.model[-1].kpt_shape != [17, 3] or model.model[-1].nc != 1:
            raise ValueError('original_person_coco17_pose_model_required')
        super().__init__(model)
        self._call_lock = threading.Lock()
        self._annotation_mask = None
        self.last_mask_stats = None

    def __call__(self, preds, batch):
        if not self._call_lock.acquire(blocking=False):
            raise RuntimeError('masked_criterion_concurrent_call_refused')
        try:
            validate_batch(batch)
            self._annotation_mask = batch['annotation_mask']
            self.last_mask_stats = dict(assigned_anchors=0, coordinate_slots=0, objectness_slots=0)
            total, components = super().__call__(preds, batch)
            if not _finite(total):
                raise ValueError('nonfinite_pose_loss_no_optimizer_step_allowed')
            return total, components
        finally:
            self._annotation_mask = None
            self._call_lock.release()

    def calculate_keypoints_loss(self, masks, target_gt_idx, keypoints, batch_idx,
                                 stride_tensor, target_bboxes, pred_kpts):
        if self._annotation_mask is None:
            raise RuntimeError('masked_loss_requires_an_owned_validated_batch')
        target, annotated, images, anchors = assigned_targets(masks, target_gt_idx, keypoints,
                                                            batch_idx, self._annotation_mask)
        target[..., :2] /= stride_tensor[anchors].view(-1, 1, 1)
        boxes = target_bboxes[images, anchors]
        area = ((boxes[:, 2:]-boxes[:, :2]).prod(1)).unsqueeze(1)
        self.last_mask_stats = dict(assigned_anchors=len(images),
            coordinate_slots=int((annotated & (target[..., 2] != 0)).sum()), objectness_slots=int(annotated.sum()))
        return masked_keypoint_terms(pred_kpts[images, anchors], target, annotated, area, self.keypoint_loss.sigmas)
