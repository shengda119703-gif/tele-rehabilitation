"""Timestamp AND decoded-pixel matched model disagreement, never accuracy."""
from __future__ import annotations

import json
import math
from pathlib import Path
import sys

from .common import ROOT, file_hash, write_json
from .pose_dataset import JOINTS, _json, _new_output, _sha


def _frames(result_path, expected_schema, result):
    path = Path(result_path).resolve().parent/'pose-frames.jsonl'
    if (not path.is_file() or path.stat().st_size > 128*1024*1024
            or file_hash(path) != result.get('pose_file_sha256')):
        raise ValueError('bounded_verified_private_pose_frames_required')
    rows, previous = {}, None
    with path.open('rb') as stream:
        while line := stream.readline(256*1024+1):
            if len(line) > 256*1024 or not line.endswith(b'\n'):
                raise ValueError('bounded_complete_pose_frame_required')
            value = json.loads(line)
            if not isinstance(value,dict):
                raise ValueError('pose_frame_object_required')
            stamp = value.get('time_s')
            if (type(stamp) not in (float,int) or not math.isfinite(stamp) or stamp < 0
                    or previous is not None and stamp <= previous or len(rows) >= 15000
                    or value.get('schema_id') != expected_schema
                    or value.get('coordinate_space') != 'raw_image_pixels'
                    or not _sha(value.get('decoded_bgr_sha256'))):
                raise ValueError('explicit_monotonic_schema_and_decoded_pixel_identity_required')
            key = round(stamp*1000000)
            if key in rows:
                raise ValueError('ambiguous_pose_timestamp_alignment')
            rows[key], previous = value, stamp
    if len(rows) != result.get('frames') or len(rows) < 3:
        raise ValueError('declared_pose_frame_count_mismatch')
    if file_hash(path) != result['pose_file_sha256']:
        raise ValueError('pose_frames_changed_during_comparison')
    return rows


def compare_video_inputs(yolo_result, mediapipe_result, output):
    ypath, y, yh = _json(yolo_result)
    mpath, m, mh = _json(mediapipe_result)
    if (y.get('kind') != 'private_target_domain_backend_replay'
            or m.get('status') != 'python_video_approximation_not_apk_acceptance'
            or any(y.get(k) != m.get(k) for k in ('video_sha256','exercise_id','side'))
            or not _sha(y.get('video_sha256')) or y.get('training_authorized') is not False
            or m.get('training_authorized') is not False):
        raise ValueError('same_authorized_video_action_side_and_explicit_domains_required')
    sys.path.insert(0,str(ROOT/'rehab_codex_single_camera_v2_1'))
    from app.landmark_schemas import POSE33
    yr, mr = _frames(ypath,'coco17-v1',y), _frames(mpath,'mediapipe33-v1',m)
    common = sorted(yr.keys() & mr.keys())
    if not common:
        raise ValueError('no_shared_verified_video_timestamps')
    metrics, joints = {}, {joint:[] for joint in JOINTS}
    ycov, mcov = {}, {}
    for stamp in common:
        a,b = yr[stamp],mr[stamp]
        if (a.get('size') != b.get('size') or a['decoded_bgr_sha256'] != b['decoded_bgr_sha256']
                or abs(a['time_s']-b['time_s']) > .000001):
            raise ValueError('timestamp_matched_frames_have_different_decoded_pixels_or_geometry')
        for name in set(a.get('metrics',{})) | set(b.get('metrics',{})):
            first,second = a.get('metrics',{}).get(name,{}),b.get('metrics',{}).get(name,{})
            def valid(value):
                return (value.get('valid') is True and type(value.get('value')) in (float,int)
                        and math.isfinite(value['value']))
            fa,fb = valid(first),valid(second)
            ycov[name],mcov[name] = ycov.get(name,0)+fa,mcov.get(name,0)+fb
            metrics.setdefault(name,[])
            if fa and fb:
                metrics[name].append(abs(first['value']-second['value']))
        yp,mp = a.get('people'),b.get('raw_pose')
        # Multiple candidates are not silently paired by their array position.
        if not isinstance(yp,list) or not isinstance(mp,list) or len(yp)!=1 or len(mp)!=1:
            continue
        first,second = yp[0],mp[0]
        if len(first.get('xy',[]))!=17 or len(first.get('conf',[]))!=17 or len(second.get('xy',[]))!=33:
            raise ValueError('anatomical_point_mapping_shape_mismatch')
        for index,joint in enumerate(JOINTS):
            other = POSE33.index(joint)
            p,q = first['xy'][index],second['xy'][other]
            v,n = second['visibility'][other],second['presence'][other]
            cs = [first['conf'][index],v,n]
            width,height = a['size']
            if (all(type(c) in (float,int) and math.isfinite(c) and .5<=c<=1 for c in cs)
                    and all(isinstance(point,list) and len(point)==2 and
                            all(type(c) in (float,int) and math.isfinite(c) for c in point)
                            and 0<point[0]<width and 0<point[1]<height for point in (p,q))):
                joints[joint].append(math.dist(p,q))
    def summary(values):
        values=sorted(values)
        return dict(shared_valid_samples=len(values),mean_absolute_disagreement=sum(values)/len(values) if values else None,
                    p95_absolute_disagreement=values[max(0,math.ceil(.95*len(values))-1)] if values else None)
    value=dict(version='rehab-pose-input-disagreement-1',video_sha256=y['video_sha256'],
        exercise_id=y['exercise_id'],side=y['side'],yolo_result_sha256=yh,mediapipe_result_sha256=mh,
        frames=dict(yolo=len(yr),mediapipe=len(mr),timestamp_and_pixel_matched=len(common),
                    yolo_unpaired=len(yr)-len(common),mediapipe_unpaired=len(mr)-len(common)),
        coordinate_space='raw_image_pixels',joint_mapping='COCO17 named anatomical counterpart in MediaPipe33',
        model_confidence_thresholds_not_probability_calibrated=True,
        point_disagreement_px={k:summary(v) for k,v in joints.items()},
        filtered_projected_angle_disagreement_deg={k:dict(summary(v),yolo_valid=ycov[k],mediapipe_valid=mcov[k],
            shared_frame_denominator=len(common)) for k,v in metrics.items()},
        yolo_v2_completed=y['v2_summary']['completed'],mediapipe_v2_completed=m['v2_summary']['completed'],
        independent_reference_available=False,clinical_accuracy=None,count_accuracy=None,
        comparison_kind='model_disagreement_not_independent_reference_error',
        elapsed_and_latency_not_used_to_claim_model_speedup=True,
        limitations=['Different Python/WASM SDK and OpenCV versions, not target-phone execution.',
            'Each engine keeps its own causal history; unpaired leading frame affects EMA state.',
            'Single-candidate pairing is spatial only, not proof of participant identity.',
            'Model agreement cannot prove either prediction is correct.'])
    if file_hash(ypath)!=yh or file_hash(mpath)!=mh:
        raise ValueError('replay_results_changed_during_comparison')
    output=_new_output(output)
    path=write_json(output/'comparison.json',value)
    return dict(path=path,artifact_sha256=file_hash(path),frames=value['frames'],
        clinical_accuracy=None,comparison_kind=value['comparison_kind'])
