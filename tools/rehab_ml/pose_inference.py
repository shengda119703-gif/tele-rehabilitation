"""Pinned original YOLO on consented reference images, not new product logic."""
from __future__ import annotations

from io import BytesIO
import hashlib
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

from .common import ROOT, file_hash, write_json
from .pose_dataset import JOINTS, PREDICTION_VERSION, _new_output, load_reference


def _iou(first, second):
    x1, y1 = max(first[0], second[0]), max(first[1], second[1])
    x2, y2 = min(first[2], second[2]), min(first[3], second[3])
    intersection = max(0., x2-x1)*max(0., y2-y1)
    area = (first[2]-first[0])*(first[3]-first[1])+(second[2]-second[0])*(second[3]-second[1])
    return intersection/(area-intersection) if area > intersection else 0.


def infer_baseline(source, output, *, split='test'):
    """One bounded owned worker; no camera, SQL, training or client activation."""
    from PIL import Image
    if split not in ('val', 'test'):
        raise ValueError('explicit_pose_validation_or_test_split_required')
    source, reference, reference_fingerprint = load_reference(source)
    sys.path.insert(0, str(ROOT/'rehab_codex_single_camera_v2_1'))
    from app.domain import Context
    from mobile_rehab.rehab_v2.pose_worker import IsolatedPoseWorker, JPEG_CAPACITY
    weights = ROOT/'rehab_codex_single_camera_v2_1/assets/models/yolo11n-pose.pt'
    manifest = json.loads(weights.with_name('manifest.json').read_text(encoding='utf-8'))
    fingerprint = file_hash(weights)
    if (fingerprint != manifest.get('sha256') or manifest.get('schema_id') != 'coco17-v1'
            or manifest.get('coordinate_space') != 'raw_image_pixels'):
        raise ValueError('pinned_original_pose_weight_contract_mismatch')
    selected = [row for row in reference['samples'] if row['split'] == split]
    if any(row['frame_size'][0]*row['frame_size'][1] > 1920*1080 for row in selected):
        raise ValueError('owned_original_pose_decoding_pixel_limit_exceeded_no_implicit_rescaling')
    output = _new_output(output)
    worker = IsolatedPoseWorker()
    rows = []
    try:
        for sample in selected:
            image = (source.parent/sample['image_ref']).resolve()
            if file_hash(image) != sample['image_sha256']:
                raise ValueError('reference_image_changed_before_inference')
            with Image.open(image) as picture:
                buffer = BytesIO()
                picture.convert('RGB').save(buffer, format='JPEG', quality=95)
                encoded = buffer.getvalue()
            if len(encoded) > JPEG_CAPACITY:
                raise ValueError('reference_jpeg_exceeds_owned_worker_capacity_no_implicit_resize')
            context = Context(1, 'rehab', sample['image_sha256'], 'REPLAY_FILE', 'TEST', output.name)
            runtime = SimpleNamespace(context=context, engine=SimpleNamespace(spec=dict(side=sample['side'])))
            started = time.perf_counter()
            pose, stages = worker.infer(dict(sid=sample['sample_id'], seq=sample['frame_seq'],
                source_time_s=sample['source_time_s'], encoded=encoded), runtime)
            elapsed = 1000*(time.perf_counter()-started)
            if (pose.size != tuple(sample['frame_size']) or pose.model_manifest_id != fingerprint
                    or pose.schema_id != 'coco17-v1' or pose.coordinate_space != 'raw_image_pixels'
                    or pose.keypoint_order_version != 'coco17-anatomical-lr-v1'):
                raise ValueError('baseline_pose_result_contract_mismatch')
            candidates = [person for person in pose.people if _iou(person.bbox, sample['bbox_xyxy_px']) >= .5]
            matched = candidates[0] if len(candidates) == 1 else None
            status = 'matched' if matched else 'ambiguous' if candidates else 'no_person'
            row = {key: sample[key] for key in ('sample_id', 'subject_group', 'recording_id',
                                               'image_sha256', 'frame_size', 'frame_seq', 'source_time_s')}
            row.update(status=status, xy=matched.xy if matched else [None]*17,
                conf=matched.conf if matched else [None]*17, roundtrip_ms=elapsed, stages_ms=stages,
                predicted_people=len(pose.people), reference_box_match_candidates=len(candidates),
                inference_image_sha256=hashlib.sha256(encoded).hexdigest())
            rows.append(row)
    except Exception as error:
        write_json(output/'failure.json', dict(status='failed', error_type=type(error).__name__,
            code=getattr(error, 'code', 'baseline_reference_inference_failed'), processed_images=len(rows),
            clinical_accuracy=None, no_training_or_product_activation=True))
        raise
    finally:
        worker.close()  # Release failure remains nonzero, never claim cleanup succeeded.
    if file_hash(source) != reference_fingerprint:
        raise ValueError('reference_changed_during_baseline_inference')
    result = dict(schema_version=PREDICTION_VERSION, schema_id='coco17-v1',
        coordinate_space='raw_image_pixels', keypoint_order=list(JOINTS), reference_sha256=reference_fingerprint,
        model=dict(model_id='original-yolo11n-pose-cpu640', weights_sha256=fingerprint,
                   trained_on_reference=False, upstream_training_exclusion_not_verified=True),
        split=split, samples=rows, inference_contract=worker.contract, owned_resource_release=worker.last_release,
        reference_usage_context=reference['usage_context'], association='independent_reference_bbox_iou_ge_0.5_unique',
        preprocessing='original_unresized_frame_reencoded_as_quality95_jpeg',
        tracking_context='reset_per_reference_image_not_continuous_video_tracking',
        no_training_or_product_activation=True, clinical_accuracy=None)
    path = write_json(output/'predictions.json', result)
    return dict(path=path, artifact_sha256=file_hash(path), images=len(rows),
                weights_sha256=fingerprint, owned_release_confirmed=worker.last_release['confirmed'],
                clinical_accuracy=None)
