"""Offline synthetic-domain temporal research. Never changes the product engine.

Pose estimates are inputs, not labels. Training requires explicitly reviewed
human intervals, unless the whole run is an unmistakable TEST engineering smoke.
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path
import random
import re
import sys
import time

import numpy as np

from ..common import ROOT, canonical_hash, file_hash, read_json, utc_now, write_json
from ..models import CausalTCN, masked_cross_entropy
import torch
from torch import nn

VERSION = 'rehab_synthetic_temporal/v1'
PHASES = ('ready', 'outbound', 'endpoint_or_hold', 'return', 'rest_or_other')
BOUNDARIES = ('preparation_confirmed_s', 'outbound_start_s', 'endpoint_start_s',
              'endpoint_end_s', 'return_start_s', 'end_s')
PHASE_BOUNDARIES = dict(zip(PHASES, (BOUNDARIES[0], BOUNDARIES[1], BOUNDARIES[2], BOUNDARIES[4], BOUNDARIES[5])))
COCO17 = ('nose', 'left_eye', 'right_eye', 'left_ear', 'right_ear', 'left_shoulder',
          'right_shoulder', 'left_elbow', 'right_elbow', 'left_wrist', 'right_wrist',
          'left_hip', 'right_hip', 'left_knee', 'right_knee', 'left_ankle', 'right_ankle')
MP33 = ('nose', 'left_eye_inner', 'left_eye', 'left_eye_outer', 'right_eye_inner',
        'right_eye', 'right_eye_outer', 'left_ear', 'right_ear', 'mouth_left', 'mouth_right',
        'left_shoulder', 'right_shoulder', 'left_elbow', 'right_elbow', 'left_wrist',
        'right_wrist', 'left_pinky', 'right_pinky', 'left_index', 'right_index', 'left_thumb',
        'right_thumb', 'left_hip', 'right_hip', 'left_knee', 'right_knee', 'left_ankle',
        'right_ankle', 'left_heel', 'right_heel', 'left_foot_index', 'right_foot_index')


def _finite(value):
    return isinstance(value,(int,float,np.integer,np.floating)) and not isinstance(value,(bool,np.bool_)) and math.isfinite(value)


def _pose(value):
    result = read_json(value) if isinstance(value, (str, Path)) else copy.deepcopy(value)
    if result.get('schema_version') != 'rehab_synthetic_pose/v1' or result.get('backend') not in ('yolo17', 'mediapipe33'):
        raise ValueError('synthetic_pose_schema_and_explicit_backend_required')
    status=result.get('metadata',{}).get('status',result.get('status'))
    if status in ('running','failed'):
        raise ValueError('failed_or_running_pose_extraction_is_not_training_input')
    if not isinstance(result.get('frames'), list) or not result['frames']:
        raise ValueError('nonempty_pose_timeline_required')
    times = [r.get('timestamp_s') for r in result['frames']]
    if any(not _finite(t) or t < 0 for t in times) or any(a >= b for a, b in zip(times, times[1:])):
        raise ValueError('strict_real_pose_pts_required_no_fps_repair')
    if len({r.get('frame_index') for r in result['frames']}) != len(times):
        raise ValueError('unique_source_frames_required')
    if any(type(r.get('frame_index')) is not int or r['frame_index'] < 0 or r.get('pts') is None or not r.get('time_base')
           for r in result['frames']):
        raise ValueError('actual_pts_time_base_and_frame_index_required')
    size = result.get('source_size')
    if not isinstance(size, list) or len(size) != 2 or any(type(v) is not int or v <= 0 for v in size):
        raise ValueError('original_pixel_size_required')
    return result


def causal_features(pose, *, side='left', hz=15., max_age_s=.5, confidence_min=.5):
    """Floor to arrived frames only; retain native joints and absolute arm angle.

    The returned grid is an experimental causal input clock. ``source_time_s``
    and frame indices preserve original media PTS; labels/events use those PTS.
    No clip min/max normalization, future interpolation or offline smoothing.
    """
    pose = _pose(pose)
    if side not in ('left', 'right') or not _finite(hz) or not 1 <= hz <= 60 or not 0 < max_age_s <= 2:
        raise ValueError('bounded_causal_feature_configuration_required')
    names = COCO17 if pose['backend'] == 'yolo17' else MP33
    frames = pose['frames']
    stamps = np.asarray([r['timestamp_s'] for r in frames], dtype=np.float64)
    grid = stamps[0] + np.arange(int(math.floor((stamps[-1]-stamps[0])*hz+1e-8))+1)/hz
    ids = np.searchsorted(stamps, grid, side='right')-1
    n, j = len(grid), len(names)
    xy, usable, confidence = np.zeros((n,j,2)), np.zeros((n,j), bool), np.zeros((n,j))
    age, fresh = grid-stamps[ids], np.r_[True, ids[1:] != ids[:-1]]
    tracks = [frames[k].get('track_id') for k in ids]
    reset = np.r_[True, [a != b or a is None or b is None for a,b in zip(tracks, tracks[1:])]]
    dt = np.r_[0., np.diff(stamps[ids])]
    reset |= dt > max_age_s
    width, height = pose['source_size']
    for i, k in enumerate(ids):
        row = frames[k]
        for z, name in enumerate(names):
            point = row.get('joints', {}).get(name, {})
            c, x, y = point.get('confidence'), point.get('x'), point.get('y')
            confidence[i,z] = c if _finite(c) and 0 <= c <= 1 else 0.
            good = (row.get('pose_detected') is True and tracks[i] is not None and age[i] <= max_age_s
                    and _finite(c) and confidence_min <= c <= 1 and _finite(x) and _finite(y)
                    and 0 <= x < width and 0 <= y < height)
            if good:
                xy[i,z], usable[i,z] = (x,y), True
    ls, rs = names.index('left_shoulder'), names.index('right_shoulder')
    root = (xy[:,ls]+xy[:,rs])/2
    scale = np.linalg.norm(xy[:,ls]-xy[:,rs], axis=1)
    body_valid = usable[:,ls] & usable[:,rs] & (scale >= 1.)
    normalized = (xy-root[:,None,:])/np.maximum(scale,1.)[:,None,None]
    coord_mask = usable & body_valid[:,None]
    normalized[~coord_mask] = 0.
    velocity, velocity_mask = np.zeros_like(normalized), np.zeros_like(usable)
    for i in range(1,n):
        if fresh[i] and not reset[i] and 0 < dt[i] <= max_age_s:
            velocity_mask[i] = coord_mask[i] & coord_mask[i-1]
            velocity[i] = (normalized[i]-normalized[i-1])/dt[i]
            velocity[i,~velocity_mask[i]] = 0.
    shoulder, elbow = names.index(side+'_shoulder'), names.index(side+'_elbow')
    arm = xy[:,elbow]-xy[:,shoulder]
    arm_length = np.linalg.norm(arm,axis=1)
    angle_mask = usable[:,shoulder] & usable[:,elbow] & (arm_length >= 1.)
    # Image y grows downwards: a relaxed downward arm is 0 degrees.
    angle = np.degrees(np.arccos(np.clip(arm[:,1]/np.maximum(arm_length,1.),-1.,1.)))
    angle[~angle_mask] = 0.
    angular_velocity = np.zeros(n)
    av_mask = np.zeros(n, bool)
    for i in range(1,n):
        if fresh[i] and not reset[i] and angle_mask[i] and angle_mask[i-1] and 0 < dt[i] <= max_age_s:
            angular_velocity[i] = (angle[i]-angle[i-1])/dt[i]
            av_mask[i] = True
    values = np.concatenate((normalized.reshape(n,-1), velocity.reshape(n,-1), coord_mask,
        velocity_mask, confidence, np.stack((angle/180., angle_mask, angular_velocity/180., av_mask,
        dt, age, fresh, reset, np.full(n,side=='left'), np.full(n,side=='right')),axis=1)),axis=1).astype(np.float32)
    return dict(schema_version=VERSION, feature_schema=f'{VERSION}/{pose["backend"]}/native_joints',
        backend=pose['backend'], joint_names=list(names), features=values, time_s=grid,
        source_time_s=stamps[ids], source_frame_index=np.asarray([frames[k]['frame_index'] for k in ids]),
        prediction_mask=angle_mask, angle_deg=angle, angle_mask=angle_mask, joint_mask=usable,
        source_age_s=age, fresh=fresh, track_reset=reset, hz=float(hz), side=side,
        causal=True, interpolation=False, confidence_kind='backend_native_not_fused')


def phase_targets(source_times, annotation):
    """Only explicit intervals supervise steps; gaps and unknowns remain masked.

    Half-open intervals prevent ambiguous adjacent boundaries. The last reviewed
    endpoint is included only when no following interval starts there.
    """
    times = np.asarray(source_times,dtype=float)
    labels, mask = np.zeros(len(times),dtype=np.int64), np.zeros(len(times),bool)
    claimed = np.zeros(len(times),bool)
    intervals = annotation.get('phase_intervals', [])
    if not isinstance(intervals,list): raise ValueError('explicit_phase_intervals_list_required')
    previous_end = None
    for k, interval in enumerate(intervals):
        start,end = interval.get('start_s'), interval.get('end_s')
        if interval.get('phase') not in PHASES or type(interval.get('label_mask')) is not bool:
            raise ValueError('explicit_phase_name_and_boolean_mask_required')
        if not interval['label_mask']:
            if start is not None or end is not None: raise ValueError('unknown_phase_times_must_be_null')
            continue
        if (not _finite(start) or not _finite(end) or start < 0 or end <= start
                or previous_end is not None and start < previous_end):
            raise ValueError('ordered_nonoverlapping_explicit_phase_intervals_required')
        select = (times >= start) & (times < end)
        if len(times) and end==times[-1]:
            select |= times == end
        if np.any(claimed & select):
            raise ValueError('phase_interval_supervision_overlap')
        claimed |= select
        if interval['label_mask']:
            labels[select],mask[select] = PHASES.index(interval['phase']),True
        previous_end = end
    return labels,mask


class PhaseTCN(nn.Module):
    receptive_field_steps = 61
    def __init__(self,input_dim,channels=32,dropout=.1):
        super().__init__()
        self.encoder = CausalTCN(input_dim,channels,dropout)
        # Remove the unrelated legacy whole-video binary head from checkpoints.
        self.encoder.head = nn.Identity()
        self.phase_head = nn.Linear(channels,len(PHASES))
    def forward(self,features,padding_mask=None):
        return self.phase_head(self.encoder.encode(features))


def sequence_loss(logits,labels,label_mask,padding_mask):
    if logits.shape[:-1] != labels.shape or labels.shape != label_mask.shape or labels.shape != padding_mask.shape:
        raise ValueError('aligned_per_step_logits_labels_and_masks_required')
    return masked_cross_entropy(logits,labels,label_mask.bool() & padding_mask.bool())


def collate_sequences(items,mean,std):
    """Whole source clips; padding is separate from unknown reference labels."""
    lengths=[len(r['features']) for r in items]
    x=np.zeros((len(items),max(lengths),len(mean)),np.float32)
    y=np.zeros(x.shape[:2],np.int64)
    label=np.zeros(x.shape[:2],bool)
    padding=np.zeros(x.shape[:2],bool)
    for i,row in enumerate(items):
        end=lengths[i]
        x[i,:end]=(row['features']-mean)/std
        y[i,:end],label[i,:end],padding[i,:end]=row['labels'],row['label_mask'],True
    return tuple(torch.from_numpy(a) for a in (x,y,label,padding))


def decode_phases(phases,source_times,*,available=None,track_reset=None):
    """Cross-stage memory; count only ready -> outward -> endpoint -> return -> ready.

    No amplitude criterion labels small complete ranges as incomplete. Missing
    evidence or track change breaks a candidate, preserving emitted history.
    Events are current observed source PTS, never retrospectively backdated.
    """
    phases=list(phases); times=list(source_times)
    if len(phases)!=len(times) or any(p not in PHASES for p in phases):
        raise ValueError('aligned_known_phase_sequence_required')
    available=[True]*len(times) if available is None else list(available)
    reset=[False]*len(times) if track_reset is None else list(track_reset)
    if len(available)!=len(times) or len(reset)!=len(times) or any(not _finite(t) or t<0 for t in times) or any(a>b for a,b in zip(times,times[1:])):
        raise ValueError('aligned_monotonic_source_pts_and_evidence_masks_required')
    events={key:None if key=='endpoint_end_s' else [] for key in BOUNDARIES}
    state='idle'; count=0; previous=None; last_arrived=None
    for i,(phase,stamp) in enumerate(zip(phases,times)):
        if reset[i] or not available[i]: state,previous='idle',None
        if not available[i]: continue
        # Repeated floor samples may inform the model of age, but are not new
        # observed motion evidence and cannot emit another phase transition.
        if last_arrived is not None and stamp==last_arrived: continue
        last_arrived=stamp
        if phase==previous: continue
        previous=phase
        emitted=None
        if phase=='ready':
            if state=='return': count+=1; emitted='end_s'
            state='ready'
            if emitted is None: emitted='preparation_confirmed_s'
        elif phase=='outbound' and state=='ready': state='outbound'; emitted='outbound_start_s'
        elif phase=='endpoint_or_hold' and state=='outbound': state='endpoint'; emitted='endpoint_start_s'
        elif phase=='return' and state=='endpoint': state='return'; emitted='return_start_s'
        elif phase=='rest_or_other':
            if state=='return': count+=1; emitted='end_s'
            state='idle'
        elif not ((phase=='outbound' and state=='outbound') or (phase=='endpoint_or_hold' and state=='endpoint') or (phase=='return' and state=='return')):
            state='idle'
        if emitted is not None:
            entries=events[emitted]
            if not entries or stamp>entries[-1]['time_s']:
                entries.append(dict(event_id=f'{emitted}-{i}',time_s=float(stamp),evidence_kind='filtered'))
    any_available=any(available)
    return dict(status='completed' if any_available else 'unavailable',completed_count=count if any_available else None,
                boundary_events=events if any_available else dict.fromkeys(BOUNDARIES),
                incomplete_candidate=state in ('outbound','endpoint','return'),
                event_definition='current_predicted_phase_confirmation_pts_not_physical_onset')


def validate_records(records,*,engineering_test=False):
    if not records or len({r['sample_id'] for r in records})!=len(records):
        raise ValueError('nonempty_unique_source_records_required')
    ownership={}; sources={}; backends=set(); component_sources=[]
    for row in records:
        if not isinstance(row['sample_id'],str) or re.fullmatch(r'[\w.-]{1,120}',row['sample_id']) is None:
            raise ValueError('safe_source_sample_identifier_required')
        if row.get('split') not in ('train','val','test') or not row.get('source_group_id'):
            raise ValueError('explicit_source_group_and_fixed_split_required')
        pose=_pose(row['pose']); backends.add(pose['backend'])
        if pose.get('sample_id')!=row['sample_id'] or not pose.get('source_sha256'):
            raise ValueError('source_pose_identity_required')
        groups=[row['source_group_id'],*row.get('related_source_groups',[])]
        for group in groups:
            if group in ownership and ownership[group]!=row['split']: raise ValueError('source_group_split_leakage')
            ownership[group]=row['split']
        fingerprint=pose['source_sha256']
        if fingerprint in sources and sources[fingerprint]!=row['split']: raise ValueError('raw_or_derived_source_split_leakage')
        sources[fingerprint]=row['split']
        sample=row.get('sample',{})
        origins=[sample.get('sample_id',row['sample_id']),sample.get('source_group_id',row['source_group_id']),
                 *sample.get('lineage_ids',[]),*row.get('related_source_groups',[])]
        reference=sample.get('reference_group_id',row['source_group_id'])
        if any(not isinstance(value,str) or not value for value in [reference,*origins]):
            raise ValueError('explicit_reference_and_lineage_identifiers_required')
        component_sources.append(dict(sample_id=row['sample_id'],source_group_id=row['source_group_id'],
            reference_group_id=reference,lineage_ids=origins,video=dict(sha256=fingerprint),
            generation=sample.get('generation',{})))
        annotation=row.get('annotation',{})
        if annotation.get('sample_id')!=row['sample_id']: raise ValueError('annotation_source_identity_required')
        if engineering_test:
            if not row['sample_id'].startswith('TEST-') or not str(row['source_group_id']).startswith('TEST-'):
                raise ValueError('engineering_smoke_requires_TEST_sources')
        else:
            review=annotation.get('review',{})
            if (annotation.get('reviewer_role')!='human_operator' or not annotation.get('reviewer_id')
                    or review.get('full_video_watched') is not True or review.get('reviewed_video_sha256')!=fingerprint
                    or type(review.get('reviewed_frame_count')) is not int or review['reviewed_frame_count']<len(pose['frames'])
                    or not review.get('watched_at')):
                raise ValueError('genuine_full_video_human_review_required_no_ai_draft_training')
            if row.get('sample') is None or row.get('timeline') is None:
                raise ValueError('frozen_sample_and_full_pts_timeline_required_for_human_review')
            sample=row['sample']
            if (any(sample.get(key)!=row.get(key) for key in ('sample_id','source_group_id','split'))
                    or sample.get('video',{}).get('sha256')!=fingerprint
                    or annotation.get('side')!=row.get('side','left')):
                raise ValueError('frozen_manifest_source_split_side_binding_required')
            frame_manifest=row.get('frame_manifest',pose.get('frame_manifest_path'))
            if frame_manifest is None: raise ValueError('shared_decoded_frame_manifest_required')
            from .pose import validate_pose
            validate_pose(pose,frame_manifest=frame_manifest,verify_model=True)
            from .contracts import validate_annotation
            checked=validate_annotation(annotation,row['sample'],row['timeline'])
            if not checked['eligible_for_training']:
                raise ValueError('qualified_human_phase_reference_required:'+','.join(checked['reasons']))
    # Reuse the source contract's transitive, shared namespace closure. A link
    # may be a person in one row and a reference/motion source in another.
    from .contracts import source_components
    splits={r['sample_id']:r['split'] for r in records}
    for component in source_components(component_sources):
        if len({splits[sample_id] for sample_id in component})>1:
            raise ValueError('transitive_reference_or_lineage_source_split_leakage')
    if len(backends)!=1: raise ValueError('separate_backend_training_required_no_confidence_fusion')
    return next(iter(backends))


def _prepare(records,config,engineering_test):
    backend=validate_records(records,engineering_test=engineering_test)
    items=[]
    for row in records:
        extracted=causal_features(row['pose'],side=row.get('side','left'),hz=config['hz'],max_age_s=config['max_age_s'])
        y,known=phase_targets(extracted['source_time_s'],row['annotation'])
        items.append(dict(row,**extracted,labels=y,label_mask=known & extracted['prediction_mask']))
    return backend,items


def _new_directory(output):
    output=Path(output).resolve()
    if output.exists(): raise ValueError('new_output_directory_required_no_overwrite')
    output.mkdir(parents=True)
    return output


def train(records,output_dir,config=None,*,engineering_test=False):
    """CPU-only independent backend training, frozen split and validation early stop."""
    cfg=dict(seed=20261019,channels=32,dropout=.1,learning_rate=3e-4,weight_decay=1e-4,
             max_epochs=50,patience=8,batch_size=4,hz=15.,max_age_s=.5,device='cpu')
    cfg.update(config or {})
    if (cfg['device']!='cpu' or cfg['channels'] not in (32,64) or cfg['dropout'] not in (.1,.2)
            or not 1<=cfg['max_epochs']<=50 or not 1<=cfg['patience']<=50 or not 1<=cfg['batch_size']<=16
            or not 0<cfg['learning_rate']<=.01):
        raise ValueError('bounded_cpu_temporal_training_configuration_required')
    backend,items=_prepare(records,cfg,engineering_test)
    groups={key:[r for r in items if r['split']==key] for key in ('train','val','test')}
    if any(not group for group in groups.values()): raise ValueError('all_fixed_source_splits_required')
    if any(not any(r['label_mask'].any() for r in groups[key]) for key in ('train','val')):
        raise ValueError('reviewed_train_and_validation_phase_supervision_required')
    output=_new_directory(output_dir)
    feature_dir=output/'features'; feature_dir.mkdir()
    feature_files=[]
    for row in items:
        target=feature_dir/(row['sample_id']+'.npz')
        np.savez_compressed(target,**{key:row[key] for key in ('features','time_s','source_time_s','source_frame_index',
            'prediction_mask','angle_deg','angle_mask','joint_mask','source_age_s','fresh','track_reset','labels','label_mask')})
        feature_files.append(dict(sample_id=row['sample_id'],split=row['split'],file=target.name,sha256=file_hash(target),
            feature_schema=row['feature_schema'],joint_names=row['joint_names'],side=row['side']))
    write_json(feature_dir/'manifest.json',dict(schema_version=VERSION,files=feature_files,backend=backend,
        causality='arrived_frame_floor_backward_velocity_no_future_interpolation',engineering_test=engineering_test))
    rng=random.Random(cfg['seed']); torch.manual_seed(cfg['seed']); torch.set_num_threads(min(4,torch.get_num_threads()))
    torch.use_deterministic_algorithms(True)
    values=np.concatenate([r['features'] for r in groups['train']])
    mean=values.mean(0).astype(np.float32); std=np.maximum(values.std(0),1e-6).astype(np.float32)
    model=PhaseTCN(len(mean),cfg['channels'],cfg['dropout'])
    optimizer=torch.optim.AdamW(model.parameters(),lr=cfg['learning_rate'],weight_decay=cfg['weight_decay'])
    provenance=dict(schema_version=VERSION,backend=backend,config=cfg,phases=list(PHASES),
        normalization_fit='train_only',standardization_train_sample_ids=[r['sample_id'] for r in groups['train']],
        source_records=[dict(sample_id=r['sample_id'],source_group_id=r['source_group_id'],split=r['split'],
            pose_sha256=canonical_hash(_pose(r['pose'])),annotation_sha256=canonical_hash(r['annotation'])) for r in records],
        engineering_test=engineering_test,claim='engineering_TEST_smoke_only' if engineering_test else 'synthetic_domain_temporal_candidate',
        implementation_sha256=file_hash(__file__),product_enabled=False,created_at=utc_now(),
        features_manifest_sha256=file_hash(feature_dir/'manifest.json'),
        runtime=dict(torch=torch.__version__,numpy=np.__version__,python=sys.version.split()[0]),
        validation_metric='known_phase_cross_entropy_minimize',test_used_for_selection=False)
    write_json(output/'config.json',provenance)
    best=float('inf'); stale=0; history=[]; start=time.perf_counter()
    for epoch in range(1,cfg['max_epochs']+1):
        shuffled=list(groups['train']); rng.shuffle(shuffled); model.train(); losses=[]
        for offset in range(0,len(shuffled),cfg['batch_size']):
            x,y,known,padding=collate_sequences(shuffled[offset:offset+cfg['batch_size']],mean,std)
            if not (known & padding).any(): continue
            optimizer.zero_grad(set_to_none=True)
            loss=sequence_loss(model(x),y,known,padding)
            if not torch.isfinite(loss): raise ValueError('nonfinite_phase_training_loss')
            loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(),1.); optimizer.step(); losses.append(float(loss.detach()))
        model.eval(); numerator=0.; denominator=0
        with torch.inference_mode():
            for row in groups['val']:
                x,y,known,padding=collate_sequences([row],mean,std); count=int((known & padding).sum())
                numerator+=float(sequence_loss(model(x),y,known,padding))*count; denominator+=count
        val=numerator/denominator
        history.append(dict(epoch=epoch,train_loss=float(np.mean(losses)),val_known_phase_loss=val))
        if val<best-1e-8:
            best=val; stale=0
            torch.save(dict(state_dict=model.state_dict(),mean=torch.from_numpy(mean),std=torch.from_numpy(std),
                input_dim=len(mean),best_epoch=epoch,backend=backend,config=cfg,config_sha256=file_hash(output/'config.json')),output/'checkpoint.pt')
        else: stale+=1
        write_json(output/'training-progress.json',dict(history=history,best_val_loss=best))
        if stale>=cfg['patience']: break
    result=dict(schema_version=VERSION,status='completed',backend=backend,epochs=len(history),best_val_loss=best,
        checkpoint_sha256=file_hash(output/'checkpoint.pt'),elapsed_s=time.perf_counter()-start,
        engineering_test=engineering_test,product_enabled=False,clinical_accuracy=None)
    write_json(output/'result.json',result)
    predict_run(output,records,output/'fixed-predictions',engineering_test=engineering_test)
    return dict(result,run_dir=str(output))


def predict_run(run_dir,records,output_dir,*,engineering_test=False):
    run=Path(run_dir); provenance=read_json(run/'config.json')
    if provenance['engineering_test']!=engineering_test: raise ValueError('explicit_engineering_run_identity_required')
    checkpoint=torch.load(run/'checkpoint.pt',map_location='cpu',weights_only=True)
    if checkpoint['config_sha256']!=file_hash(run/'config.json'): raise ValueError('frozen_run_configuration_changed')
    result=read_json(run/'result.json')
    if result.get('status')!='completed' or result.get('checkpoint_sha256')!=file_hash(run/'checkpoint.pt'):
        raise ValueError('completed_frozen_checkpoint_required')
    # Inference never loads annotations or masks derived from reference labels.
    items=[]; backends=set()
    if not records or len({r['sample_id'] for r in records})!=len(records):
        raise ValueError('unique_prediction_source_records_required')
    for row in records:
        if not isinstance(row['sample_id'],str) or re.fullmatch(r'[\w.-]{1,120}',row['sample_id']) is None:
            raise ValueError('safe_prediction_sample_identifier_required')
        pose=_pose(row['pose']); backends.add(pose['backend'])
        if pose['sample_id']!=row['sample_id'] or row.get('split') not in ('train','val','test'):
            raise ValueError('fixed_prediction_source_identity_and_split_required')
        features=causal_features(pose,side=row.get('side','left'),hz=checkpoint['config']['hz'],max_age_s=checkpoint['config']['max_age_s'])
        items.append(dict(row,**features,labels=np.zeros(len(features['features']),np.int64),label_mask=np.zeros(len(features['features']),bool)))
    if len(backends)!=1: raise ValueError('separate_backend_prediction_required')
    backend=next(iter(backends))
    if backend!=checkpoint['backend']: raise ValueError('backend_checkpoint_mismatch')
    model=PhaseTCN(checkpoint['input_dim'],checkpoint['config']['channels'],checkpoint['config']['dropout'])
    model.load_state_dict(checkpoint['state_dict'],strict=True); model.eval()
    output=_new_directory(output_dir); predictions=[]
    with torch.inference_mode():
        for row in items:
            x,_,_,_=collate_sequences([row],checkpoint['mean'].numpy(),checkpoint['std'].numpy())
            probabilities=torch.softmax(model(x),-1)[0].numpy()
            phases=[PHASES[k] for k in probabilities.argmax(1)]
            decoded=decode_phases(phases,row['source_time_s'],available=row['prediction_mask'],track_reset=row['track_reset'])
            details=dict(sample_id=row['sample_id'],backend=backend,time_s=row['time_s'].tolist(),
                source_time_s=row['source_time_s'].tolist(),source_frame_index=row['source_frame_index'].tolist(),
                phase=phases,phase_probabilities=probabilities.tolist(),prediction_mask=row['prediction_mask'].tolist(),
                source_age_s=row['source_age_s'].tolist(),fresh=row['fresh'].tolist(),
                track_reset=row['track_reset'].tolist(),angle_deg=row['angle_deg'].tolist(),angle_mask=row['angle_mask'].tolist())
            write_json(output/(row['sample_id']+'.json'),details)
            predictions.append(dict(sample_id=row['sample_id'],backend=backend,split=row['split'],
                source_sha256=_pose(row['pose'])['source_sha256'],**decoded))
    manifest=dict(schema_version='rehab_synthetic_predictions/v1',kind='B2',backend=backend,
        checkpoint_sha256=file_hash(run/'checkpoint.pt'),config_sha256=file_hash(run/'config.json'),
        reference_used_for_predictions=False,engineering_test=engineering_test,product_enabled=False,samples=predictions)
    write_json(output/'predictions.json',manifest)
    return dict(path=str(output/'predictions.json'),sha256=file_hash(output/'predictions.json'))


def replay_baseline(pose,*,side='left',exercise_id='shoulder_abduction'):
    """Frozen original adapter/engine on stored native pose predictions (CPU)."""
    pose=_pose(pose)
    sys.path.insert(0,str(ROOT/'rehab_codex_single_camera_v2_1'))
    from app.domain import Context,PoseFrame,PosePerson
    from app.landmark_schemas import ORDERS
    from app.rehab_v2.evidence import EvidenceAdapter
    from app.rehab_v2.engine import ProtocolEngine
    from ..temporal_replay import event_inventory,append_events,transition_events
    context=Context(1,'rehab',pose['source_sha256'],'REPLAY_FILE','RESEARCH','synthetic-B0')
    adapter=EvidenceAdapter(exercise_id,side); engine=ProtocolEngine(dict(exercise_id=exercise_id,side=side),source_epoch=context.epoch)
    names=COCO17 if pose['backend']=='yolo17' else MP33
    schema='coco17-v1' if pose['backend']=='yolo17' else 'mediapipe33-v1'
    events=event_inventory(); trace=[]; observable=0; detected=0
    for r in pose['frames']:
        points=r.get('joints',{}); people=[]
        if r.get('pose_detected') and r.get('track_id') is not None:
            xy=[[points.get(n,{}).get('x'),points.get(n,{}).get('y')] for n in names]
            conf=[points.get(n,{}).get('confidence') for n in names]
            valid=[p for p in xy if all(_finite(v) for v in p)]
            box=r.get('bbox') or ([min(p[0] for p in valid),min(p[1] for p in valid),max(p[0] for p in valid),max(p[1] for p in valid)] if valid else [0.]*4)
            people=[PosePerson(str(r['track_id']),box,xy,conf,dict(confidence_kind='backend_native'))]
        frame=PoseFrame(context,r['frame_index']+1,r['timestamp_s'],tuple(pose['source_size']),people,0.,
            schema_id=schema,keypoint_order_version=ORDERS[schema],model_manifest_id=pose['model']['sha256'],
            backend='yolo' if pose['backend']=='yolo17' else 'mediapipe_pose')
        evidence=adapter.analyze(frame,processing_age_ms=0.,time_basis='mapped_source_seconds')
        metric=evidence.metrics.get(engine.spec['metric'])
        metric_observable=bool(metric is not None and metric.observable(engine.plan['max_age_ms']))
        observable+=metric_observable;detected+=bool(people)
        before=dict(phase=engine.phase,repetitions=list(engine.repetitions))
        if not engine.process(evidence): raise ValueError('original_engine_rejected_saved_source_pose')
        after=dict(phase=engine.phase,repetitions=list(engine.repetitions))
        append_events(events,transition_events(before,after,frame.seq,frame.time_s))
        trace.append(dict(frame_index=r['frame_index'],timestamp_s=r['timestamp_s'],phase=engine.phase,completed=engine.completed,
            required_metric_observable=metric_observable,observation_status=evidence.observation_status))
    engine.finish('offline_synthetic_video_ended')
    coverage=dict(processed_frames=len(trace),pose_detected_frames=detected,observable_frames=observable,
        observable_fraction=observable/len(trace),required_metric=engine.spec['metric'],
        entirely_unobservable=observable==0)
    return dict(sample_id=pose['sample_id'],backend=pose['backend'],source_sha256=pose['source_sha256'],
        status='completed' if observable else 'unavailable',
        completed_count=engine.completed if observable else None,
        boundary_events=events if observable else dict.fromkeys(BOUNDARIES),trace=trace,coverage=coverage,
        engine_implementation_sha256={str(p.relative_to(ROOT)):file_hash(p) for p in
            (ROOT/'rehab_codex_single_camera_v2_1/app/rehab_v2').glob('*.py')},
        event_definition='unchanged_protocol_confirmation_not_physical_motion_onset',product_enabled=False)
