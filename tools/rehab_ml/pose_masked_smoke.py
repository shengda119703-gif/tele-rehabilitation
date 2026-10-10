"""Bounded TEST-only native forward/backward/step/reload of partial pose loss.

This engineering smoke is NOT qualified fine-tuning. Human data is refused;
train-pose remains gated until independent target-domain supervision exists.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.rehab_ml.common import ROOT, canonical_hash, file_hash, read_json, write_json
from tools.rehab_ml.pose_dataset import _json, _new_output, load_reference

BASE_SHA256 = '869e83fcdffdc7371fa4e34cd8e51c838cc729571d1635e5141e3075e9319dc0'


def verified_weights():
    weights = ROOT/'rehab_codex_single_camera_v2_1/assets/models/yolo11n-pose.pt'
    manifest = read_json(weights.with_name('manifest.json'))
    if (file_hash(weights) != BASE_SHA256 or manifest.get('sha256') != BASE_SHA256
            or manifest.get('schema_id') != 'coco17-v1'
            or manifest.get('coordinate_space') != 'raw_image_pixels'):
        raise ValueError('original_verified_yolo_weight_required_no_download_or_replacement')
    return weights


def training_batch(source, *, image_size=128):
    """Only grouped train images enter tensors; no augment/pseudo label paths.

    PIL's actual integer resize axes and letterbox offsets are applied to both
    independent full-person bbox and reviewed points. Masks never transform
    into confidence or visibility. No annotation for unknown slots is inferred.
    """
    import numpy as np
    from PIL import Image
    import torch
    if type(image_size) is not int or not 64 <= image_size <= 640 or image_size % 32:
        raise ValueError('bounded_stride_aligned_training_image_size_required')
    source, reference, fingerprint = load_reference(source, training=True)
    rows = [row for row in reference['samples'] if row['split'] == 'train']
    if not 1 <= len(rows) <= 4:
        raise ValueError('engineering_batch_requires_one_to_four_train_images')
    images, points, boxes, annotations, transforms = [], [], [], [], []
    for row in rows:
        image = (source.parent/row['image_ref']).resolve()
        if file_hash(image) != row['image_sha256']:
            raise ValueError('reference_image_changed_before_batch')
        width, height = row['frame_size']
        ratio = image_size/max(width, height)
        resized = [max(1, round(width*ratio)), max(1, round(height*ratio))]
        offset = [(image_size-resized[0])//2, (image_size-resized[1])//2]
        scales = [resized[0]/width, resized[1]/height]
        with Image.open(image) as picture:
            picture = picture.convert('RGB').resize(tuple(resized), Image.Resampling.BILINEAR)
            canvas = Image.new('RGB', (image_size, image_size), (114, 114, 114))
            canvas.paste(picture, tuple(offset))
            images.append(torch.from_numpy(np.array(canvas, dtype=np.uint8)).permute(2, 0, 1).float()/255.)
        if file_hash(image) != row['image_sha256']:
            raise ValueError('reference_image_changed_during_batch')
        xyxy = [(row['bbox_xyxy_px'][j]*scales[j%2]+offset[j%2])/image_size for j in range(4)]
        boxes.append([(xyxy[0]+xyxy[2])/2, (xyxy[1]+xyxy[3])/2, xyxy[2]-xyxy[0], xyxy[3]-xyxy[1]])
        points.append([[0., 0., 0.] if not mask or visible == 0 else
            [(xy[0]*scales[0]+offset[0])/image_size, (xy[1]*scales[1]+offset[1])/image_size, float(visible)]
            for xy, visible, mask in zip(row['xy'], row['visibility'], row['annotation_mask'])])
        annotations.append(row['annotation_mask'])
        transforms.append(dict(sample_id=row['sample_id'], original_size=row['frame_size'],
            resized_size=resized, scales=scales, pad_left_top=offset, output_size=[image_size, image_size],
            preprocessing='actual_integer_axis_resize_then_letterbox_no_flip_or_augmentation'))
    if file_hash(source) != fingerprint:
        raise ValueError('reference_changed_during_batch')
    batch = dict(img=torch.stack(images), batch_idx=torch.arange(len(rows), dtype=torch.float32),
        cls=torch.zeros((len(rows), 1)), bboxes=torch.tensor(boxes, dtype=torch.float32),
        keypoints=torch.tensor(points, dtype=torch.float32), annotation_mask=torch.tensor(annotations, dtype=torch.bool))
    from tools.rehab_ml.pose_masked_loss import validate_batch
    validate_batch(batch)
    return batch, dict(reference_sha256=fingerprint, train_sample_ids=[row['sample_id'] for row in rows],
        train_subject_groups=sorted({row['subject_group'] for row in rows}), transforms=transforms,
        validation_test_used_for_optimization=False, random_augmentation=False)


def _tensor_digest(named):
    result = hashlib.sha256()
    for name, tensor in named:
        tensor = tensor.detach().cpu().contiguous()
        result.update(canonical_hash(dict(name=name, shape=list(tensor.shape), dtype=str(tensor.dtype))).encode())
        result.update(tensor.numpy().tobytes())
    return result.hexdigest()


def run_child(request_file):
    request_file, request, _ = _json(request_file)
    source, reference, fingerprint = load_reference(request['reference'], training=True)
    if fingerprint != request['reference_sha256'] or reference['usage_context'] != 'TEST' or any(
            row['annotations']['origin'] != 'synthetic_fixture' for row in reference['samples']):
        raise ValueError('native_loss_smoke_requires_explicit_synthetic_test_fixture_only')
    import torch
    from ultralytics import YOLO
    from ultralytics.cfg import get_cfg
    from ultralytics.utils.loss import v8PoseLoss
    from tools.rehab_ml.pose_masked_loss import MaskedPoseLoss, implementation_contract
    contract = implementation_contract()
    weights = verified_weights()
    output = request_file.parent
    started = time.perf_counter()
    torch.set_num_threads(2)
    torch.manual_seed(20261011)
    torch.use_deterministic_algorithms(True)
    batch, provenance = training_batch(source)
    if not bool((~batch['annotation_mask']).any()) or not bool(
            (batch['annotation_mask'] & (batch['keypoints'][..., 2] == 0)).any()):
        raise ValueError('smoke_requires_both_unknown_and_reviewed_not_locatable_joints')
    model = YOLO(str(weights), task='pose').model.cpu().float().train()
    model.requires_grad_(True)
    model.args = get_cfg()  # Locked library defaults; saved component gains below.
    criterion = MaskedPoseLoss(model)
    optimizer = torch.optim.SGD(model.parameters(), lr=1e-5, momentum=0., weight_decay=0.)
    optimizer.zero_grad(set_to_none=True)
    before = _tensor_digest(model.named_parameters())
    predictions = model(batch['img'])
    raw_points = predictions[1]
    raw_points.retain_grad()
    stock, _ = v8PoseLoss(model)(predictions, batch)
    old_gradient = torch.autograd.grad(stock.sum(), raw_points, retain_graph=True)[0]
    # retain_grad also observes autograd.grad's stock-control backward. Clear
    # that retained output buffer before measuring this criterion separately.
    raw_points.grad = None
    loss, components = criterion(predictions, batch)
    loss.sum().backward()
    gradients = raw_points.grad.view(len(batch['img']), 17, 3, -1)
    old_gradient = old_gradient.view_as(gradients)
    unknown = (~batch['annotation_mask']).all(0)
    absent = (batch['annotation_mask'] & (batch['keypoints'][..., 2] == 0)).all(0)
    if not unknown.any() or not absent.any():
        raise ValueError('smoke_requires_consistent_fixture_masks_for_output_gradient_audit')
    audit = dict(unknown_joint_gradient_max=float(gradients[:, unknown].abs().max()),
        known_absent_xy_gradient_max=float(gradients[:, absent, :2].abs().max()),
        known_absent_objectness_gradient_l1=float(gradients[:, absent, 2].abs().sum()),
        stock_unknown_objectness_gradient_l1=float(old_gradient[:, unknown, 2].abs().sum()),
        reviewed_locatable_gradient_l1=float(gradients[:, ~(unknown | absent)].abs().sum()),
        output_gradient_not_shared_trunk_parameter_claim=True)
    write_json(output/'gradient-audit.json', dict(audit, assigned_supervision=criterion.last_mask_stats,
        loss_components=components.tolist(), stock_components=stock.detach().tolist()))
    if (audit['unknown_joint_gradient_max'] != 0. or audit['known_absent_xy_gradient_max'] != 0.
            or audit['known_absent_objectness_gradient_l1'] <= 0.
            or audit['stock_unknown_objectness_gradient_l1'] <= 0.
            or audit['reviewed_locatable_gradient_l1'] <= 0.):
        raise RuntimeError('actual_yolo_output_gradient_mask_check_failed')
    parameters = [p for p in model.parameters() if p.grad is not None]
    if not parameters or any(not torch.isfinite(p.grad).all() for p in parameters):
        raise RuntimeError('finite_native_pose_gradients_required')
    gradient_norm = float(torch.nn.utils.clip_grad_norm_(parameters, 10., error_if_nonfinite=True))
    optimizer.step()
    after = _tensor_digest(model.named_parameters())
    if before == after:
        raise RuntimeError('engineering_optimizer_step_did_not_change_parameters')
    checkpoint = output/'TEST-engineering-checkpoint.pt'
    torch.save(dict(version=contract['version'], fixture_only=True, product_enabled=False,
        base_sha256=BASE_SHA256, reference_sha256=fingerprint, state_dict=model.state_dict()), checkpoint)
    saved = torch.load(checkpoint, map_location='cpu', weights_only=True)
    reloaded = YOLO(str(weights), task='pose').model.cpu().float()
    reloaded.load_state_dict(saved['state_dict'], strict=True)
    if _tensor_digest(model.state_dict().items()) != _tensor_digest(reloaded.state_dict().items()):
        raise RuntimeError('native_pose_checkpoint_state_roundtrip_failed')
    model.eval()
    reloaded.eval()
    with torch.no_grad():
        expected, actual = model(batch['img'])[0], reloaded(batch['img'])[0]
    max_difference = float((expected-actual).abs().max())
    if not torch.isfinite(actual).all() or max_difference > 1e-6:
        raise RuntimeError('native_pose_checkpoint_prediction_roundtrip_failed')
    if file_hash(source) != fingerprint or file_hash(weights) != BASE_SHA256:
        raise RuntimeError('smoke_source_or_original_weight_changed')
    result = dict(kind='synthetic_native_dual_masked_loss_smoke_not_finetuning', contract=contract,
        provenance=provenance, seed=20261011, device='cpu', image_size=128, threads=2,
        optimizer=dict(type='SGD', lr=1e-5, momentum=0., weight_decay=0., clip_norm=10.),
        loss_gains={k: getattr(model.args, k) for k in ('box', 'pose', 'kobj', 'cls', 'dfl')},
        engineering_optimizer_steps=1, human_training_performed=False, fine_tuning_qualified=False,
        clinical_accuracy=None, product_enabled=False, original_weight_unchanged=True,
        parameter_digest_before=before, parameter_digest_after=after, gradient_audit=audit,
        loss_components=components.tolist(), component_order=['box', 'pose', 'kobj', 'cls', 'dfl'],
        assigned_supervision=criterion.last_mask_stats, gradient_norm_before_clip=gradient_norm,
        checkpoint_sha256=file_hash(checkpoint), reload_prediction_max_abs_difference=max_difference,
        elapsed_s=time.perf_counter()-started)
    write_json(output/'result.json', result)
    return result


def smoke_masked_pose(reference, output, *, timeout_s=120.):
    if type(timeout_s) not in (int, float) or not math.isfinite(timeout_s) or not 5 <= timeout_s <= 300:
        raise ValueError('bounded_pose_smoke_timeout_required')
    source, value, fingerprint = load_reference(reference, training=True)
    if value['usage_context'] != 'TEST' or any(
            row['annotations']['origin'] != 'synthetic_fixture' for row in value['samples']):
        raise ValueError('native_loss_smoke_requires_explicit_synthetic_test_fixture_only')
    python = ROOT/'rehab_codex_single_camera_v2_1/.venv/Scripts/python.exe'
    if not python.is_file():
        raise ValueError('existing_pinned_product_interpreter_required_no_install')
    verified_weights()
    output = _new_output(output)
    write_json(output/'request.json', dict(reference=str(source), reference_sha256=fingerprint))
    temporary = output/'process-temp'
    temporary.mkdir()
    (output/'ultralytics-config').mkdir()
    environment = dict(os.environ, TEMP=str(temporary), TMP=str(temporary), PYTHONDONTWRITEBYTECODE='1',
        YOLO_CONFIG_DIR=str(output/'ultralytics-config'), OMP_NUM_THREADS='2', MKL_NUM_THREADS='2')
    arguments = [str(python), '-X', 'utf8', '-B', str(Path(__file__).resolve()), '--child-request', str(output/'request.json')]
    started = time.perf_counter()
    with (output/'child.log').open('wb') as log:
        process = subprocess.Popen(arguments, cwd=ROOT, env=environment, stdout=log, stderr=log,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            code = process.wait(timeout=timeout_s)
        except BaseException as error:
            from tools.rehab_ml.mediapipe_video import release_owned
            confirmed = release_owned(process)
            write_json(output/'failure.json', dict(status='release_unconfirmed' if not confirmed else
                'timeout' if isinstance(error, subprocess.TimeoutExpired) else 'cancelled_or_wait_failed',
                owned_exit_confirmed=confirmed, human_training_performed=False, clinical_accuracy=None))
            if not confirmed:
                raise RuntimeError('owned_pose_smoke_release_unconfirmed') from error
            if isinstance(error, subprocess.TimeoutExpired):
                raise TimeoutError('owned_pose_smoke_timeout_no_success_claim') from error
            raise
    provenance = dict(arguments=arguments, exit_code=code, elapsed_s=time.perf_counter()-started,
        child_log_sha256=file_hash(output/'child.log'), owned_exit_confirmed=process.poll() is not None,
        source_hash_unchanged=file_hash(source) == fingerprint, original_weight_unchanged=file_hash(verified_weights()) == BASE_SHA256,
        implementation_sha256={p: file_hash(ROOT/p) for p in (
            'tools/rehab_ml/pose_masked_loss.py', 'tools/rehab_ml/pose_masked_smoke.py', 'tools/rehab_ml/pose_dataset.py')},
        os_process_creation_hard_deadline_verified=False)
    write_json(output/'provenance.json', provenance)
    if code != 0 or not provenance['source_hash_unchanged'] or not provenance['owned_exit_confirmed']:
        raise RuntimeError('native_pose_smoke_failed_no_finetuning_or_success_claim')
    result = read_json(output/'result.json')
    if (result['provenance']['reference_sha256'] != fingerprint or result['human_training_performed'] is not False
            or file_hash(output/'TEST-engineering-checkpoint.pt') != result['checkpoint_sha256']):
        raise RuntimeError('native_pose_smoke_result_provenance_mismatch')
    return dict(path=str(output/'result.json'), result_sha256=file_hash(output/'result.json'),
                owned_exit_confirmed=True, engineering_optimizer_steps=result['engineering_optimizer_steps'],
                human_training_performed=False, clinical_accuracy=None, product_enabled=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--child-request', type=Path, required=True)
    args = parser.parse_args()
    try:
        run_child(args.child_request)
    except Exception as error:
        write_json(args.child_request.resolve().parent/'failure.json', dict(status='failed',
            error_type=type(error).__name__, code=str(error)[:160], human_training_performed=False, clinical_accuracy=None))
        raise
