"""Reproducible, root-scoped synthetic research commands. CPU only.

Examples (no product environment upgrade or model activation):
  python -m tools.rehab_ml.synthetic.experiment validate --root E:/ai-video-lab/datasets/rehab_synthetic_v1
  python -m tools.rehab_ml.synthetic.experiment extract --root ... --run-id extract_01 --backend all
  python -m tools.rehab_ml.synthetic.experiment train --root ... --run-id phase_01 --backend all

The train command requires all 60 independently grouped formal sources and
actual saved human references. It has no engineering bypass or pseudo-label mode.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import json
from pathlib import Path
import re
import sys

if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
    __package__='tools.rehab_ml.synthetic'

from ..common import ROOT, canonical_hash, file_hash, utc_now, write_json
from . import contracts as c
from . import review, video, pose, temporal, evaluation

VERSION='rehab_synthetic_experiment/v1'
DEFAULT_ROOT=Path('E:/ai-video-lab/datasets/rehab_synthetic_v1')
DEFAULT_CONFIG=ROOT/'configs/rehab_ml/synthetic_tcn.json'
BACKENDS=('yolo17','mediapipe33')


def _identifier(value):
    if not isinstance(value,str) or re.fullmatch(r'[A-Za-z0-9_-]{1,96}',value) is None:
        raise argparse.ArgumentTypeError('ASCII letters, numbers, underscore or hyphen required (1-96 characters)')
    return value


def _root(value):
    root=Path(value).resolve()
    if not root.is_dir():raise ValueError('existing_dataset_root_required')
    return root


def _owned(root,*parts):
    target=root.joinpath(*parts).resolve()
    if not target.is_relative_to(root):raise ValueError('experiment_output_outside_dataset_root')
    return target


def _run_path(root,run_id):
    _identifier(run_id)
    target=_owned(root,'runs',run_id)
    if target.exists():raise ValueError('new_experiment_run_required_no_overwrite')
    return target


def _backends(value):
    if value=='all':return BACKENDS
    if value not in BACKENDS:raise ValueError('explicit_supported_backend_required')
    return (value,)


def _snapshot(root,*,formal=False):
    # load_reviewed rehashes original bytes, verifies full real PTS by decoding,
    # and only applies saved acceptance decisions in memory.
    snapshot=review.load_reviewed(root)
    summary=c.validate_manifest(snapshot['manifest'],snapshot['timelines'],require_formal_complete=formal)
    # Requalify instead of trusting a caller-provided eligible list.
    snapshot['eligible_annotations']=c.load_eligible_annotations(snapshot['annotations'],snapshot['manifest'],snapshot['timelines'])
    return snapshot,summary


def validate(root,*,require_formal_complete=False):
    root=_root(root);snapshot,summary=_snapshot(root,formal=require_formal_complete)
    media_present=summary['sample_count']>0
    return dict(schema_version=VERSION,command='validate',root=str(root),
        status='verified_sources' if media_present else 'verified_structure_empty_inventory',
        **summary,eligible_annotations=len(snapshot['eligible_annotations']),
        verified_video_count=summary['sample_count'],real_pts_verified=media_present,raw_hashes_verified=media_present,
        formal_gate_required=require_formal_complete,
        scenario_coverage_basis='requested_generation_targets_only',
        observed_scenario_coverage='not_established_by_this_command',
        training_performed=False,clinical_accuracy=None,product_enabled=False)


def _missing_baseline(sample,backend,reason):
    return dict(sample_id=sample['sample_id'],backend=backend,split=sample['split'],
        source_sha256=sample['video']['sha256'],status='unavailable',completed_count=None,
        boundary_events=dict.fromkeys(temporal.BOUNDARIES),reason=reason)


def extract(root,run_id,*,backend='all',sample_ids=None,reuse_existing=False,baseline_side=None,timeout_s=600.):
    root=_root(root);run=_run_path(root,run_id);backends=_backends(backend)
    if baseline_side not in (None,'left','right'):raise ValueError('explicit_analyzed_side_or_none_required')
    snapshot,summary=_snapshot(root)
    samples=snapshot['manifest']['samples']
    if sample_ids is not None:
        if len(set(sample_ids))!=len(sample_ids) or not set(sample_ids)<={r['sample_id'] for r in samples}:
            raise ValueError('unique_known_extract_sample_ids_required')
        requested=set(sample_ids);samples=[r for r in samples if r['sample_id'] in requested]
    if not samples:raise ValueError('nonempty_source_cohort_required_for_extraction')
    for sample in samples:
        _identifier(sample['sample_id'])
        for name in backends:
            target=_owned(root,'pose_'+name,sample['sample_id'])
            if target.exists() and not reuse_existing:
                raise ValueError('existing_pose_output_requires_explicit_reuse_existing')
    run.mkdir(parents=True,exist_ok=False)
    config=dict(schema_version=VERSION,command='extract',run_id=run_id,created_at=utc_now(),
        backends=list(backends),sample_ids=[r['sample_id'] for r in samples],sampling_hz=15.,
        device='cpu',reuse_existing=reuse_existing,predeclared_analyzed_side=baseline_side,
        analyzed_side_is_not_affected_side_or_reference=True,
        snapshot_sha256=canonical_hash(snapshot),implementation_sha256=file_hash(__file__),
        labels_generated=False,training_performed=False,product_enabled=False)
    write_json(run/'config.json',config)
    annotations={r['sample_id']:r for r in snapshot['annotations']}
    statuses=[];baselines={name:[] for name in backends}
    try:
        for sample in samples:
            sid=sample['sample_id'];source=review._within(root,sample['video']['path'])
            # v2 separates media semantics from the producer decoder version;
            # preserve all earlier v1 inventories and failed runs unchanged.
            shared=_owned(root,'features','shared_frames_v2',sid+'.json')
            if shared.exists():frames=video.validate_frame_manifest(shared,video=source,verify_decode=True)
            else:
                shared.parent.mkdir(parents=True,exist_ok=True)
                probe=snapshot['timelines'][sid]
                frames=video.create_frame_manifest(source,shared,sampling_hz=15.,probe=probe if 'frames' in probe else None)
            for name in backends:
                target=_owned(root,'pose_'+name,sid)
                if target.exists():
                    prediction=pose.validate_pose(target/'pose.json',frame_manifest=frames,verify_model=True)
                    if prediction.get('status') not in ('completed','completed_with_failures'):
                        raise ValueError('failed_or_running_pose_output_cannot_be_reused')
                    reused=True
                else:
                    prediction=pose.extract_pose(source,frames,target,sample_id=sid,backend=name,timeout_s=timeout_s)
                    reused=False
                saved=target/'pose.json'
                if prediction.get('sample_id')!=sid or prediction.get('backend')!=name or prediction.get('source_sha256')!=sample['video']['sha256']:
                    raise ValueError('pose_extraction_source_identity_changed')
                status=dict(sample_id=sid,backend=name,status=prediction.get('status'),
                    pose_ref=str(saved),pose_sha256=file_hash(saved),shared_frames_sha256=canonical_hash(frames),reused=reused)
                statuses.append(status)
                annotation=annotations.get(sid,{})
                side=baseline_side or (annotation.get('side') if annotation.get('side_mask') else None)
                if prediction.get('status') not in ('completed','completed_with_failures'):
                    base=_missing_baseline(sample,name,'pose_extraction_failed')
                    base.update(status='failed')
                elif side not in ('left','right'):
                    base=_missing_baseline(sample,name,'analyzed_anatomical_side_not_predeclared')
                else:
                    base=temporal.replay_baseline(prediction,side=side,exercise_id=sample['exercise_id'])
                    base.pop('trace',None);base['split']=sample['split'];base['analyzed_side']=side
                baselines[name].append(base)
                write_json(run/'progress.json',dict(status='running',samples=statuses))
        for name,rows in baselines.items():
            write_json(run/('baseline_'+name+'.json'),dict(schema_version='rehab_synthetic_predictions/v1',kind='B0',
                backend=name,reference_used_for_predictions=False,engineering_test=False,samples=rows,
                label_ground_truth=False,product_enabled=False))
        outcome=('failed' if any(r['status']=='failed' for r in statuses) else
                 'completed' if all(r['status']=='completed' for r in statuses) else 'completed_with_failures')
        result=dict(schema_version=VERSION,status=outcome,
            command='extract',run_id=run_id,backend_outputs=statuses,sources=len(samples),
            backend_count=len(backends),labels_generated=False,training_performed=False,product_enabled=False)
        write_json(run/'result.json',result)
        return dict(result,run_dir=str(run))
    except Exception as error:
        write_json(run/'failure.json',dict(status='failed',error_type=type(error).__name__,error=str(error),samples=statuses))
        raise


def _formal_sources(snapshot):
    manifest=snapshot['manifest'];timelines=snapshot['timelines']
    audit=c.validate_manifest(manifest,timelines,require_formal_complete=True)
    audit.update(scenario_coverage_basis='requested_generation_targets_only',
        observed_scenario_coverage='not_established_by_this_command',
        acceptance_scope='source_slots_and_eligible_references_not_observed_six_scenario_acceptance')
    selected=[r for r in manifest['samples'] if r['stage']=='formal' and r.get('status')=='accepted']
    if any(r.get('exercise_id')!='shoulder_abduction' or r.get('view') not in ('front','frontal') for r in selected):
        raise ValueError('P0_frontal_shoulder_abduction_only_for_formal_temporal_training')
    if len(selected)!=60 or Counter(r['split'] for r in selected)!=Counter(train=36,val=12,test=12):
        raise ValueError('formal_60_source_36_12_12_cohort_required')
    groups={split:{r['source_group_id'] for r in selected if r['split']==split} for split in c.SPLITS}
    if tuple(len(groups[k]) for k in c.SPLITS)!=(6,2,2):raise ValueError('formal_independent_groups_6_2_2_required')
    eligible={r['sample_id']:r for r in c.load_eligible_annotations(snapshot['annotations'],manifest,timelines)}
    if any(r['sample_id'] not in eligible for r in selected):
        raise ValueError('all_sixty_formal_sources_require_saved_human_temporal_reference')
    for sample in selected:
        annotation=eligible[sample['sample_id']]
        if annotation.get('side') not in ('left','right'):
            raise ValueError('single_anatomical_test_side_required_for_temporal_training')
        if not any(interval['label_mask'] for interval in annotation['phase_intervals']):
            raise ValueError('all_formal_sources_require_reviewed_phase_intervals_not_count_only')
    return selected,eligible,audit


def train(root,run_id,*,backend='all',config=None,event_tolerance_s=.25):
    root=_root(root);run=_run_path(root,run_id);backends=_backends(backend)
    if not 0<event_tolerance_s<=1:raise ValueError('predeclared_bounded_event_tolerance_required')
    snapshot,_=_snapshot(root,formal=True)
    samples,annotations,audit=_formal_sources(snapshot)
    records={name:[] for name in backends}
    # All qualification and source checks happen before a train directory is
    # created or an optimizer is called. No implicit "latest" model is loaded.
    for sample in samples:
        sid=sample['sample_id']
        for name in backends:
            prediction_path=_owned(root,'pose_'+name,sid,'pose.json')
            prediction=c._read_json(prediction_path)
            frame_path=_owned(root,'pose_'+name,sid,'frame-manifest.json')
            prediction=pose.validate_pose(prediction,frame_manifest=frame_path,verify_model=True)
            if prediction.get('status') not in ('completed','completed_with_failures'):
                raise ValueError('completed_backend_prediction_required_before_training')
            record=dict(sample_id=sid,source_group_id=sample['source_group_id'],split=sample['split'],
                side=annotations[sid]['side'],sample=sample,timeline=snapshot['timelines'][sid],
                frame_manifest=str(frame_path),pose=prediction,annotation=annotations[sid])
            records[name].append(record)
    for rows in records.values():temporal.validate_records(rows)
    cfg=copy.deepcopy(c._read_json(DEFAULT_CONFIG) if config is None else config)
    if not isinstance(cfg,dict):raise ValueError('temporal_hyperparameters_json_object_required')
    if cfg.get('device','cpu')!='cpu':raise ValueError('synthetic_experiment_CPU_only')
    run.mkdir(parents=True,exist_ok=False)
    write_json(run/'config.json',dict(schema_version=VERSION,command='train',run_id=run_id,
        backends=list(backends),config=cfg,event_tolerance_s=event_tolerance_s,
        source_manifest_sha256=file_hash(root/'manifests/dataset.json'),
        reviewed_snapshot_sha256=canonical_hash(snapshot),formal_audit=audit,
        implementation_sha256=file_hash(__file__),created_at=utc_now(),device='cpu',
        product_enabled=False,real_human_test_status='not_performed_by_this_command'))
    write_json(run/'reviewed-snapshot.json',snapshot)
    completed=[]
    try:
        for name,rows in records.items():
            target=run/name
            candidate=temporal.train(rows,target,cfg,engineering_test=False)
            baseline=evaluation.baseline_manifest(rows,engineering_test=False)
            write_json(target/'baseline-predictions.json',baseline)
            comparisons={}
            for split in c.SPLITS:
                selected=[r for r in rows if r['split']==split]
                predictions=temporal.predict_run(target,selected,target/('fixed-'+split),engineering_test=False)
                if split!='train':
                    comparisons[split]=evaluation.compare(rows,baseline,predictions['path'],target/('comparison-'+split),
                        split=split,tolerance_s=event_tolerance_s,engineering_test=False)
            completed.append(dict(backend=name,candidate=candidate,comparisons=comparisons))
            write_json(run/'progress.json',dict(status='running',completed=completed))
        checked,_=_snapshot(root,formal=True)
        if canonical_hash(checked)!=canonical_hash(snapshot):
            raise ValueError('source_manifest_or_human_reference_changed_during_experiment')
        for rows in records.values():temporal.validate_records(rows)
        result=dict(schema_version=VERSION,command='train',status='completed',run_id=run_id,
            formal_sources=60,formal_splits=dict(train=36,val=12,test=12),backends=completed,
            scenario_coverage_basis='requested_generation_targets_only',
            observed_scenario_coverage='not_established_by_this_command',
            completion_scope='pipeline_execution_only_not_full_dataset_plan_acceptance',
            training_domain='AI_generated_only',real_human_test_status='pending_separate_frozen_holdout',
            clinical_accuracy=None,product_enabled=False)
        write_json(run/'result.json',result)
        return dict(result,run_dir=str(run))
    except Exception as error:
        write_json(run/'failure.json',dict(status='failed',error_type=type(error).__name__,error=str(error),completed=completed))
        raise


def parser():
    result=argparse.ArgumentParser(description=__doc__)
    commands=result.add_subparsers(dest='command',required=True)
    for name in ('validate','extract','train'):
        item=commands.add_parser(name)
        item.add_argument('--root',type=Path,default=DEFAULT_ROOT)
        if name=='validate':item.add_argument('--require-formal-complete',action='store_true')
        else:
            item.add_argument('--run-id',type=_identifier,required=True)
            item.add_argument('--backend',choices=['all',*BACKENDS],default='all')
        if name=='extract':
            item.add_argument('--samples',nargs='+',type=_identifier)
            item.add_argument('--reuse-existing',action='store_true')
            item.add_argument('--baseline-side',choices=['left','right'],help='Predeclared analyzed side; never affected-side truth')
            item.add_argument('--timeout-s',type=float,default=600.)
        if name=='train':
            item.add_argument('--config',type=Path,default=DEFAULT_CONFIG,help='JSON hyperparameters; CPU only, default is the versioned project config')
            item.add_argument('--event-tolerance-s',type=float,default=.25)
    return result


def main(argv=None):
    args=parser().parse_args(argv)
    try:
        if args.command=='validate':result=validate(args.root,require_formal_complete=args.require_formal_complete)
        elif args.command=='extract':
            result=extract(args.root,args.run_id,backend=args.backend,sample_ids=args.samples,
                reuse_existing=args.reuse_existing,baseline_side=args.baseline_side,timeout_s=args.timeout_s)
        else:
            config=None
            if args.config is not None:
                config=c._read_json(args.config.resolve())
            result=train(args.root,args.run_id,backend=args.backend,config=config,event_tolerance_s=args.event_tolerance_s)
        print(json.dumps(result,ensure_ascii=False,allow_nan=False))
        return 0 if result.get('status') in ('completed','verified_sources','verified_structure_empty_inventory') else 2
    except (ValueError,OSError,RuntimeError,TimeoutError) as error:
        print(json.dumps(dict(status='rejected_or_failed',error_type=type(error).__name__,error=str(error)),ensure_ascii=False))
        return 2


if __name__=='__main__':raise SystemExit(main())
