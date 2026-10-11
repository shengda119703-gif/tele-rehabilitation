"""Opt-in bounded offline pose training; never a product model installer.

Research needs independently reviewed, permission-scoped RGB supervision.
Engineering fixtures exercise the same multi-epoch loop, not human accuracy.
"""
from __future__ import annotations

import argparse
import copy
from io import BytesIO
import math
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import time

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.rehab_ml.common import ROOT, canonical_hash, file_hash, git, paths, read_json, write_json
from tools.rehab_ml.pose_dataset import (JOINTS, PREDICTION_VERSION, _json, _new_output,
                                         evaluate, load_reference)
from tools.rehab_ml.pose_masked_smoke import BASE_SHA256, _tensor_digest, verified_weights

VERSION = 'rehab-pose-finetune-1'


class TrainingLease:
    """One live offline pose trainer; OS lock, not existence of a lock file."""
    def __init__(self):
        self.stream = None

    def __enter__(self):
        self.stream = (paths()['run']/'pose-training.lock').open('a+b')
        if self.stream.seek(0, os.SEEK_END) == 0:
            self.stream.write(b'0')
            self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self.stream.close()
            self.stream = None
            raise RuntimeError('offline_pose_training_capacity_one') from error
        return self

    def __exit__(self, *args):
        if self.stream is not None:
            self.stream.close()  # OS releases on actual child exit, including crash.
            self.stream = None


def owned_output(path):
    path = Path(path).resolve()
    roots = paths()
    if not any(path != roots[k] and path.is_relative_to(roots[k]) for k in ('data', 'run')):
        raise ValueError('pose_training_output_must_be_inside_dedicated_ignored_root')
    return path


def configuration(source):
    source, value, fingerprint = _json(source)
    required = {'schema_version', 'mode', 'reference', 'output_dir', 'seed', 'device', 'image_size',
                'batch_size', 'max_epochs', 'patience', 'threads', 'learning_rate', 'weight_decay',
                'clip_norm', 'freeze_first_layers', 'brightness', 'contrast', 'confidence_min',
                'pck_threshold', 'timeout_s'}
    if set(value) != required or value['schema_version'] != VERSION:
        raise ValueError('explicit_versioned_pose_training_config_required_no_unknown_options')
    if value['mode'] not in ('engineering_test', 'research') or value['device'] not in ('cpu', 'cuda:0'):
        raise ValueError('explicit_offline_training_mode_and_device_required')
    bounds = dict(seed=(0, 2**31-1), image_size=(64, 640), batch_size=(1, 8), max_epochs=(1, 100),
                  patience=(1, 100), threads=(1, 4), freeze_first_layers=(0, 22))
    for key, (low, high) in bounds.items():
        if type(value[key]) is not int or not low <= value[key] <= high:
            raise ValueError('bounded_integer_training_option:'+key)
    bounds = dict(learning_rate=(1e-7, .01), weight_decay=(0., .01), clip_norm=(.1, 100.),
                  brightness=(0., .2), contrast=(0., .2), confidence_min=(.5, 1.),
                  pck_threshold=(.001, 1.), timeout_s=(10., 7200.))
    for key, (low, high) in bounds.items():
        if type(value[key]) not in (int, float) or not math.isfinite(value[key]) or not low <= value[key] <= high:
            raise ValueError('finite_bounded_training_option:'+key)
    if value['image_size'] % 32 or value['patience'] > value['max_epochs']:
        raise ValueError('stride_aligned_image_and_bounded_patience_required')
    for key in ('reference', 'output_dir'):
        if not isinstance(value[key], str) or not value[key]:
            raise ValueError('explicit_reference_and_new_output_required')
        value[key] = str((source.parent/value[key]).resolve())
    owned_output(value['output_dir'])
    return source, value, fingerprint


def qualified_reference(config):
    source, reference, fingerprint = load_reference(config['reference'], training=True)
    engineering = config['mode'] == 'engineering_test'
    origin = 'synthetic_fixture' if engineering else 'human'
    if reference['usage_context'] != ('TEST' if engineering else 'RESEARCH') or any(
            row['annotations']['origin'] != origin for row in reference['samples']):
        raise ValueError('mode_must_match_independent_human_or_explicit_test_reference')
    # Case variants of the same pseudonymous identity cannot evade isolation.
    for key in ('subject_group', 'recording_id'):
        groups = {}
        for row in reference['samples']:
            name = row[key].casefold()
            if name in groups and groups[name] != row['split']:
                raise ValueError('casefolded_subject_or_recording_split_leakage')
            groups[name] = row['split']
    for split in ('train', 'val', 'test'):
        if not any(row['split'] == split and any(m and v in (1, 2) for m, v in
                zip(row['annotation_mask'], row['visibility'])) for row in reference['samples']):
            raise ValueError('coordinate_supervision_required_in_each_isolated_split')
    if any(r['frame_size'][0]*r['frame_size'][1] > 1920*1080 for r in reference['samples']):
        raise ValueError('bounded_original_inference_pixels_required')
    return source, reference, fingerprint


def training_batch(source, rows, config, generator):
    """One bounded batch; train-only colour augmentation, no geometry guessing."""
    import numpy as np
    from PIL import Image, ImageEnhance
    import torch
    from tools.rehab_ml.pose_masked_loss import validate_batch
    size = config['image_size']
    if not rows or len(rows) > config['batch_size'] or any(row['split'] != 'train' for row in rows):
        raise ValueError('only_bounded_train_rows_may_enter_optimizer_batch')
    images, boxes, points, masks, transforms = [], [], [], [], []
    for row in rows:
        image = source.parent/row['image_ref']
        if file_hash(image) != row['image_sha256']:
            raise ValueError('training_image_hash_changed')
        width, height = row['frame_size']
        ratio = size/max(width, height)
        resized = [max(1, round(width*ratio)), max(1, round(height*ratio))]
        scales = [resized[0]/width, resized[1]/height]
        pad = [(size-resized[0])//2, (size-resized[1])//2]
        brightness = generator.uniform(1-config['brightness'], 1+config['brightness'])
        contrast = generator.uniform(1-config['contrast'], 1+config['contrast'])
        with Image.open(image) as picture:
            picture = picture.convert('RGB').resize(tuple(resized), Image.Resampling.BILINEAR)
            picture = ImageEnhance.Brightness(picture).enhance(brightness)
            picture = ImageEnhance.Contrast(picture).enhance(contrast)
            canvas = Image.new('RGB', (size, size), (114, 114, 114))
            canvas.paste(picture, tuple(pad))
            images.append(torch.from_numpy(np.array(canvas, dtype=np.uint8)).permute(2, 0, 1).float()/255.)
        if file_hash(image) != row['image_sha256']:
            raise ValueError('training_image_changed_during_decode')
        xyxy = [(row['bbox_xyxy_px'][j]*scales[j % 2]+pad[j % 2])/size for j in range(4)]
        boxes.append([(xyxy[0]+xyxy[2])/2, (xyxy[1]+xyxy[3])/2, xyxy[2]-xyxy[0], xyxy[3]-xyxy[1]])
        points.append([[0., 0., 0.] if not mask or v == 0 else
            [(xy[0]*scales[0]+pad[0])/size, (xy[1]*scales[1]+pad[1])/size, float(v)]
            for xy, v, mask in zip(row['xy'], row['visibility'], row['annotation_mask'])])
        masks.append(row['annotation_mask'])
        transforms.append(dict(sample_id=row['sample_id'], resized_size=resized, scales=scales,
            pad_left_top=pad, brightness=brightness, contrast=contrast, geometry_augmented=False))
    batch = dict(img=torch.stack(images), batch_idx=torch.arange(len(rows), dtype=torch.float32),
        cls=torch.zeros((len(rows), 1)), bboxes=torch.tensor(boxes, dtype=torch.float32),
        keypoints=torch.tensor(points, dtype=torch.float32), annotation_mask=torch.tensor(masks, dtype=torch.bool))
    validate_batch(batch)
    return batch, transforms


def selection_score(summary):
    """Coverage-sensitive PCK first, coverage second; never use training loss."""
    pck, coverage = summary['pck_all_coordinate_references'], summary['coordinate_coverage']
    if (summary['coordinate_reference_count'] < 1 or any(type(n) not in (int, float)
            or not math.isfinite(n) or not 0 <= n <= 1 for n in (pck, coverage))):
        raise ValueError('finite_independent_validation_score_required')
    return pck, coverage


def _checkpoint(path, model, optimizer, metadata):
    import torch
    descriptor, temporary = tempfile.mkstemp(prefix=path.name+'.', suffix='.part', dir=path.parent)
    os.close(descriptor)
    # Partial failure remains recoverable; only our own last checkpoint is replaced.
    torch.save(dict(metadata, state_dict=model.state_dict(), optimizer_state=optimizer.state_dict(),
                    torch_rng_state=torch.get_rng_state()), temporary)
    if Path(temporary).stat().st_size > 64*1024*1024:
        raise RuntimeError('checkpoint_byte_budget_exceeded')
    os.replace(temporary, path)
    return file_hash(path)


def infer_split(model, reference, source, output, split, config, checkpoint_sha, trained):
    """Unfused training model stays untouched; cloned original tracking route.

    Every image resets tracking. JPEG95 and 640px track match the old reference
    audit, but are not continuous-video or clinical tracking evaluation.
    """
    import cv2
    import numpy as np
    import torch
    from PIL import Image
    from ultralytics import YOLO
    from tools.rehab_ml.pose_inference import _iou
    if split not in ('val', 'test'):
        raise ValueError('explicit_heldout_pose_split_required')
    digest = _tensor_digest(model.state_dict().items())
    wrapper = YOLO(str(verified_weights()), task='pose')
    wrapper.model = copy.deepcopy(model).eval()
    rows = []
    for sample in reference['samples']:
        if sample['split'] != split:
            continue
        if (output.parent/'cancel.request').exists():
            raise InterruptedError('offline_pose_training_cancel_requested')
        image = source.parent/sample['image_ref']
        if file_hash(image) != sample['image_sha256']:
            raise ValueError('heldout_image_hash_changed')
        with Image.open(image) as picture:
            buffer = BytesIO()
            picture.convert('RGB').save(buffer, format='JPEG', quality=95)
            encoded = buffer.getvalue()
        decoded = cv2.imdecode(np.frombuffer(encoded, dtype=np.uint8), cv2.IMREAD_COLOR)
        if decoded is None or file_hash(image) != sample['image_sha256']:
            raise ValueError('heldout_image_decode_or_hash_failed')
        predictor = getattr(wrapper, 'predictor', None)
        for tracker in getattr(predictor, 'trackers', []):
            tracker.reset()
        started = time.perf_counter()
        with torch.no_grad():
            prediction = wrapper.track(decoded, persist=True, tracker='bytetrack.yaml', conf=.35,
                                       imgsz=640, device=config['device'], verbose=False)[0]
        elapsed = 1000*(time.perf_counter()-started)
        candidates = []
        if prediction.boxes is not None and prediction.keypoints is not None:
            for i, box in enumerate(prediction.boxes.xyxy.cpu().tolist()):
                if _iou(box, sample['bbox_xyxy_px']) >= .5:
                    candidates.append(i)
        matched = candidates[0] if len(candidates) == 1 else None
        status = 'matched' if matched is not None else 'ambiguous' if candidates else 'no_person'
        row = {k: sample[k] for k in ('sample_id', 'subject_group', 'recording_id', 'image_sha256',
                                       'frame_size', 'frame_seq', 'source_time_s')}
        row.update(status=status, xy=prediction.keypoints.xy[matched].cpu().tolist() if matched is not None else [None]*17,
            conf=prediction.keypoints.conf[matched].cpu().tolist() if matched is not None else [None]*17,
            roundtrip_ms=elapsed)
        rows.append(row)
    if _tensor_digest(model.state_dict().items()) != digest:
        raise RuntimeError('evaluation_changed_unfused_training_model')
    groups = lambda group_split: sorted({r['subject_group'] for r in reference['samples'] if r['split'] == group_split})
    predictions = dict(schema_version=PREDICTION_VERSION, schema_id='coco17-v1', coordinate_space='raw_image_pixels',
        keypoint_order=list(JOINTS), reference_sha256=file_hash(source), split=split, samples=rows,
        model=dict(model_id='offline-yolo11n-pose-'+checkpoint_sha[:16] if trained else 'original-yolo11n-pose-cpu640',
            weights_sha256=checkpoint_sha, trained_on_reference=trained, training_subject_groups=groups('train') if trained else [],
            selection_subject_groups=groups('val') if trained else [], upstream_training_exclusion_not_verified=True),
        preprocessing='original_unresized_frame_reencoded_as_quality95_jpeg',
        association='independent_reference_bbox_iou_ge_0.5_unique',
        tracking_context='reset_per_reference_image_not_continuous_video_tracking')
    output.mkdir()
    prediction_path = write_json(output/'predictions.json', predictions)
    return read_json(evaluate(source, prediction_path, output/'evaluation', split=split,
        confidence_min=config['confidence_min'], pck_threshold=config['pck_threshold'])['path'])


def owned_child_request(request_file):
    request_file = Path(request_file).resolve()
    owned_output(request_file.parent)
    if request_file.name != 'request.json':
        raise ValueError('owned_pose_training_request_filename_required')
    return request_file


def record_child_failure(request_file, error):
    """Invalid child invocations never write beside an arbitrary caller file."""
    try:
        request_file = owned_child_request(request_file)
    except (OSError, ValueError):
        return False
    output = request_file.parent
    phase = 'cancelled' if isinstance(error, InterruptedError) else 'failed'
    write_json(output/'failure.json', dict(status=phase, error_type=type(error).__name__,
        code=str(error)[:160], completed=False, product_enabled=False))
    status_file = output/'status.json'
    try:
        state = read_json(status_file) if status_file.is_file() else dict(version=VERSION)
        if not isinstance(state, dict):
            state = dict(version=VERSION)
    except (OSError, ValueError):
        state = dict(version=VERSION)
    write_json(status_file, dict(state, phase=phase, completed=False, product_enabled=False))
    return True


def run_child(request_file):
    request_file = owned_child_request(request_file)
    with TrainingLease():
        return _run_locked_child(request_file)


def _run_locked_child(request_file):
    request_file, request, _ = _json(request_file)
    config_source, config, config_hash = configuration(request['config'])
    source, reference, reference_hash = qualified_reference(config)
    if config_hash != request['config_sha256'] or reference_hash != request['reference_sha256']:
        raise ValueError('training_request_input_changed')
    output = owned_output(request_file.parent)
    if str(output) != config['output_dir']:
        raise ValueError('owned_training_output_mismatch')
    import torch
    from ultralytics import YOLO
    from ultralytics.cfg import get_cfg
    from tools.rehab_ml.pose_masked_loss import MaskedPoseLoss, implementation_contract
    contract = implementation_contract()
    if config['device'] != 'cpu' and not torch.cuda.is_available():
        raise ValueError('requested_cuda_unavailable_no_silent_device_change')
    torch.set_num_threads(config['threads'])
    torch.manual_seed(config['seed'])
    torch.use_deterministic_algorithms(True)
    generator = random.Random(config['seed'])
    started = time.perf_counter()
    steps, epoch, history, best, best_epoch, bad_epochs = 0, 0, [], None, None, 0

    def status(phase):
        write_json(output/'status.json', dict(version=VERSION, phase=phase, epoch=epoch,
            optimizer_steps=steps, elapsed_s=time.perf_counter()-started, product_enabled=False,
            human_training_performed=config['mode'] == 'research' and steps > 0))

    def check():
        if (output/'cancel.request').exists():
            raise InterruptedError('offline_pose_training_cancel_requested')
        if file_hash(config_source) != config_hash or file_hash(source) != reference_hash:
            raise ValueError('frozen_training_inputs_changed')
        if time.perf_counter()-started >= config['timeout_s']:
            raise TimeoutError('offline_pose_training_time_budget_exceeded')

    status('baseline_validation')
    model = YOLO(str(verified_weights()), task='pose').model.to(config['device']).float()
    model.args = get_cfg()
    before = _tensor_digest(model.named_parameters())
    baseline_val = infer_split(model, reference, source, output/'baseline-val', 'val', config, BASE_SHA256, False)
    if config['mode'] == 'research' and selection_score(baseline_val['summary'])[0] >= 1.:
        raise ValueError('baseline_validation_does_not_demonstrate_configured_pose_problem')
    model.requires_grad_(True)
    freeze = config['freeze_first_layers']
    if freeze >= len(model.model):
        raise ValueError('pose_head_must_remain_unfrozen')
    for i, layer in enumerate(model.model):
        if i < freeze:
            layer.requires_grad_(False)
    for name, parameter in model.named_parameters():
        if '.dfl.' in name:
            parameter.requires_grad_(False)  # Original fixed distribution projection.
    criterion = MaskedPoseLoss(model)
    optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],
        lr=config['learning_rate'], weight_decay=config['weight_decay'])
    train_rows = [r for r in reference['samples'] if r['split'] == 'train']
    initial_buffers = {n: t.detach().cpu().clone() for n, t in model.state_dict().items()
                       if any(n.startswith(f'model.{i}.') for i in range(freeze))}
    checkpoint_metadata = dict(version=VERSION, config_sha256=config_hash, reference_sha256=reference_hash,
        base_sha256=BASE_SHA256, fixture_only=config['mode'] == 'engineering_test', product_enabled=False)
    order_log = output/'train-order.jsonl'
    stop_reason = 'max_epochs'
    for epoch in range(1, config['max_epochs']+1):
        check()
        status('training')
        model.train()
        for layer in list(model.model)[:freeze]:
            layer.eval()  # Freeze BN buffers as well as trainable parameters.
        ordered = list(train_rows)
        generator.shuffle(ordered)
        losses = []
        for start in range(0, len(ordered), config['batch_size']):
            check()
            batch, transforms = training_batch(source, ordered[start:start+config['batch_size']], config, generator)
            batch = {k: t.to(config['device']) for k, t in batch.items()}
            optimizer.zero_grad(set_to_none=True)
            loss, components = criterion(model(batch['img']), batch)
            loss.sum().backward()
            parameters = [p for p in model.parameters() if p.grad is not None]
            if not parameters or any(not torch.isfinite(p.grad).all() for p in parameters):
                raise RuntimeError('finite_training_gradients_required_before_step')
            norm = float(torch.nn.utils.clip_grad_norm_(parameters, config['clip_norm'], error_if_nonfinite=True))
            optimizer.step()
            steps += 1
            if any(not torch.isfinite(p).all() for p in model.parameters()):
                raise RuntimeError('nonfinite_training_parameter')
            losses.append(components.detach().cpu().tolist())
            with order_log.open('a', encoding='utf-8') as stream:
                import json
                stream.write(json.dumps(dict(epoch=epoch, step=steps, transforms=transforms,
                    loss_components=losses[-1], gradient_norm_before_clip=norm,
                    assigned_supervision=criterion.last_mask_stats), allow_nan=False)+'\n')
            status('training')
        status('checkpoint')
        last_sha = _checkpoint(output/'last.pt', model, optimizer, dict(checkpoint_metadata, epoch=epoch, optimizer_steps=steps))
        status('validation')
        validation = infer_split(model, reference, source, output/f'val-epoch-{epoch}', 'val', config, last_sha, True)
        check()
        score = selection_score(validation['summary'])
        improved = best is None or score > best
        if improved:
            best, best_epoch, bad_epochs = score, epoch, 0
            best_sha = _checkpoint(output/'best.pt', model, optimizer, dict(checkpoint_metadata, epoch=epoch, optimizer_steps=steps))
        else:
            bad_epochs += 1
        history.append(dict(epoch=epoch, optimizer_steps=steps, batch_count=len(losses), validation_score=list(score),
            best_updated=improved, checkpoint_sha256=last_sha, validation_summary=validation['summary']))
        write_json(output/'history.json', history)
        if bad_epochs >= config['patience']:
            stop_reason = 'validation_patience'
            break
    check()
    after = _tensor_digest(model.named_parameters())
    if before == after or not steps:
        raise RuntimeError('no_actual_optimizer_parameter_update')
    if any(not torch.equal(model.state_dict()[n].cpu(), t) for n, t in initial_buffers.items()):
        raise RuntimeError('frozen_layers_changed')
    status('reload_selected_checkpoint')
    saved = torch.load(output/'best.pt', map_location=config['device'], weights_only=True)
    if saved['config_sha256'] != config_hash or saved['reference_sha256'] != reference_hash or saved['epoch'] != best_epoch:
        raise RuntimeError('selected_checkpoint_provenance_mismatch')
    selected = YOLO(str(verified_weights()), task='pose').model.to(config['device']).float()
    selected.load_state_dict(saved['state_dict'], strict=True)
    if _tensor_digest(selected.state_dict().items()) != _tensor_digest(saved['state_dict'].items()):
        raise RuntimeError('selected_checkpoint_state_reload_mismatch')
    # Test is untouched until selection is frozen, and each model is evaluated once.
    status('test')
    baseline = YOLO(str(verified_weights()), task='pose').model.to(config['device']).float()
    baseline_test = infer_split(baseline, reference, source, output/'baseline-test', 'test', config, BASE_SHA256, False)
    candidate_test = infer_split(selected, reference, source, output/'candidate-test', 'test', config, best_sha, True)
    check()
    if file_hash(verified_weights()) != BASE_SHA256:
        raise RuntimeError('original_pose_weight_changed')
    result = dict(version=VERSION, mode=config['mode'], evidence_scope='synthetic_multi_epoch_engineering_not_human_accuracy'
        if config['mode'] == 'engineering_test' else 'independent_reference_offline_pose_finetuning_not_clinical_validation',
        reference_sha256=reference_hash, config_sha256=config_hash, contract=contract,
        baseline_weight_sha256=BASE_SHA256, original_weight_unchanged=True,
        epochs_completed=epoch, optimizer_steps=steps, stop_reason=stop_reason, best_epoch=best_epoch,
        best_validation_score=list(best), best_checkpoint_sha256=best_sha, last_checkpoint_sha256=last_sha,
        parameter_digest_before=before, parameter_digest_after_last_epoch=after,
        selected_checkpoint_strictly_reloaded=True, validation_test_used_for_optimization=False,
        test_used_for_selection=False, inference_size=640, training_image_size=config['image_size'],
        baseline_validation_summary=baseline_val['summary'], baseline_test_summary=baseline_test['summary'],
        candidate_test_summary=candidate_test['summary'], human_training_performed=config['mode'] == 'research',
        clinical_accuracy=None, anatomical_rom_accuracy=None, product_enabled=False,
        elapsed_s=time.perf_counter()-started)
    write_json(output/'result.json', result)
    write_json(output/'model-card.json', dict(version=VERSION, config=config, git_commit=git('rev-parse', 'HEAD'),
        model_id='offline-yolo11n-pose-'+best_sha[:16], model_role='pose_estimation',
        artifact='best.pt', artifact_sha256=best_sha, input_domain='rgb_2d', input_schema_version='coco17-v1',
        coordinate_space='raw_image_pixels', inference_mode='independent_image_offline',
        protocol_versions=[], action_outcome_compatibility_not_verified=True,
        python=sys.version, torch=torch.__version__, ultralytics=contract['ultralytics'], device=config['device'],
        seed=config['seed'], trainable_role='offline_coco17_pose', source_dataset=reference['dataset_id'],
        supported_exercises=sorted({r['exercise_id'] for r in reference['samples']}),
        supported_sides=sorted({r['side'] for r in reference['samples']}), supported_views=sorted({r['view'] for r in reference['samples']}),
        data_manifest_hash=reference_hash, license_evidence_refs=[dict(reference=reference['permissions']['evidence_ref'],
            sha256=reference['permissions']['evidence_sha256'])],
        groups={s: sorted({r['subject_group'] for r in reference['samples'] if r['split'] == s}) for s in ('train', 'val', 'test')},
        split_sha256=canonical_hash([{k: r[k] for k in ('sample_id', 'subject_group', 'recording_id', 'split', 'image_sha256')}
                                    for r in reference['samples']]),
        permissions=reference['permissions'], permission_document_content_not_legally_attested=True,
        upstream_pretraining_exclusion_not_verified=True, fixture_only=config['mode'] == 'engineering_test',
        product_enabled=False, deployment_eligible=False,
        prohibited_claims=['clinical_rom', 'prescription', 'phone_validation', 'training_gain_without_independent_results'],
        remaining=['independent_action_outcome_validation', 'target_phone_and_pressure_verification', 'deployment_gate']))
    status('completed')
    return result


def train_pose(config_file):
    config_file, config, config_hash = configuration(config_file)
    source, reference, reference_hash = qualified_reference(config)
    verified_weights()
    python = ROOT/'rehab_codex_single_camera_v2_1/.venv/Scripts/python.exe'
    if not python.is_file():
        raise ValueError('existing_locked_pose_environment_required_no_install')
    output_path = owned_output(config['output_dir'])
    existing = output_path.parent
    while not existing.exists():
        existing = existing.parent
    counts = {s: sum(r['split'] == s for r in reference['samples']) for s in ('train', 'val', 'test')}
    # Conservative initial estimate, not a physical full-disk/fault guarantee.
    estimated = (256*1024*1024 + counts['val']*config['max_epochs']*16*1024
                 + counts['train']*config['max_epochs']*2048 + counts['test']*64*1024)
    if shutil.disk_usage(existing).free < estimated:
        raise ValueError('insufficient_space_for_bounded_pose_training_outputs')
    output = _new_output(config['output_dir'])
    write_json(output/'resource-budget.json', dict(estimated_bytes=estimated, available_bytes=shutil.disk_usage(existing).free,
        max_checkpoint_bytes=64*1024*1024, threads=config['threads'], batch_size=config['batch_size'],
        max_epochs=config['max_epochs'], timeout_s=config['timeout_s'], no_physical_full_disk_test=True))
    write_json(output/'resolved-config.json', config)
    write_json(output/'request.json', dict(version=VERSION, config=str(config_file), config_sha256=config_hash,
        reference_sha256=reference_hash, output_dir=str(output), resolved_config_sha256=file_hash(output/'resolved-config.json')))
    for name in ('process-temp', 'ultralytics-config'):
        (output/name).mkdir()
    environment = dict(os.environ, TEMP=str(output/'process-temp'), TMP=str(output/'process-temp'),
        PYTHONDONTWRITEBYTECODE='1', YOLO_CONFIG_DIR=str(output/'ultralytics-config'),
        YOLO_AUTOINSTALL='false', YOLO_OFFLINE='true', CUBLAS_WORKSPACE_CONFIG=':4096:8')
    arguments = [str(python), '-X', 'utf8', '-B', str(Path(__file__).resolve()), '--child-request', str(output/'request.json')]
    started = time.perf_counter()
    with (output/'child.log').open('wb') as log:
        try:
            process = subprocess.Popen(arguments, cwd=ROOT, env=environment, stdout=log, stderr=log,
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except Exception as error:
            write_json(output/'failure.json', dict(status='process_creation_failed', error_type=type(error).__name__))
            raise
        try:
            code = process.wait(timeout=config['timeout_s'])
        except BaseException as error:
            from tools.rehab_ml.mediapipe_video import release_owned
            confirmed = release_owned(process)
            write_json(output/'failure.json', dict(status='release_unconfirmed' if not confirmed else
                'timeout' if isinstance(error, subprocess.TimeoutExpired) else 'cancelled_or_wait_failed',
                owned_exit_confirmed=confirmed, completed=False, product_enabled=False))
            if not confirmed:
                raise RuntimeError('owned_pose_training_release_unconfirmed') from error
            if isinstance(error, subprocess.TimeoutExpired):
                raise TimeoutError('owned_pose_training_timeout_no_success_claim') from error
            raise
    provenance = dict(version=VERSION, arguments=arguments, exit_code=code, elapsed_s=time.perf_counter()-started,
        child_log_sha256=file_hash(output/'child.log'), owned_exit_confirmed=process.poll() is not None,
        implementation_sha256={p: file_hash(ROOT/p) for p in ('tools/rehab_ml/pose_training.py',
            'tools/rehab_ml/pose_masked_loss.py', 'tools/rehab_ml/pose_dataset.py')}, os_creation_hard_deadline_verified=False)
    write_json(output/'provenance.json', provenance)
    if code or not provenance['owned_exit_confirmed'] or file_hash(config_file) != config_hash or file_hash(source) != reference_hash:
        raise RuntimeError('offline_pose_training_failed_no_success_claim')
    result = read_json(output/'result.json')
    if (result['config_sha256'] != config_hash or result['reference_sha256'] != reference_hash
            or result['product_enabled'] is not False or result['optimizer_steps'] < 1
            or file_hash(output/'best.pt') != result['best_checkpoint_sha256']):
        raise RuntimeError('offline_pose_training_result_provenance_mismatch')
    return dict(path=str(output/'result.json'), result_sha256=file_hash(output/'result.json'),
        epochs_completed=result['epochs_completed'], optimizer_steps=result['optimizer_steps'],
        human_training_performed=result['human_training_performed'], product_enabled=False, clinical_accuracy=None,
        owned_exit_confirmed=True)


def request_cancel(output):
    output = owned_output(output)
    request_file = output/'request.json'
    _, request, _ = _json(request_file)
    _, config, digest = _json(output/'resolved-config.json')
    if (request.get('version') != VERSION or config.get('output_dir') != str(output)
            or request.get('output_dir') != str(output) or request.get('resolved_config_sha256') != digest):
        raise ValueError('owned_pose_training_request_required')
    # A request is not proof of a running process or confirmation of termination.
    write_json(output/'cancel.request', dict(version=VERSION, cancel_requested=True))
    return dict(cancel_requested=True, exit_confirmed=False, terminal_state_not_inferred=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--child-request', type=Path, required=True)
    args = parser.parse_args()
    try:
        run_child(args.child_request)
    except Exception as error:
        record_child_failure(args.child_request, error)
        raise
