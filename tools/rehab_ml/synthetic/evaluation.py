"""Source-verified synthetic B0/B2 comparison; no product activation.

The metric functions are shared with reviewed real-video research, while source
qualification remains separate. Engineering TEST outputs cannot become evidence
of a trained candidate or of human/clinical performance.
"""
from __future__ import annotations

import copy
from pathlib import Path

from ..common import canonical_hash, file_hash, read_json, utc_now, write_json
from ..temporal_evaluation import aggregate, score_sample
from .temporal import BOUNDARIES, PHASE_BOUNDARIES, _finite, _pose, validate_records

VERSION='rehab_synthetic_evaluation/v1'


def _manifest(value):
    return read_json(value) if isinstance(value,(str,Path)) else copy.deepcopy(value)


def _label(record):
    """Translate the independently qualified synthetic label, never predictions."""
    annotation=record['annotation']; sample=record.get('sample',{})
    reps=[]
    for repetition in annotation.get('repetitions',[]):
        boundaries=dict.fromkeys(BOUNDARIES); masks=dict.fromkeys(BOUNDARIES,False)
        for phase,boundary in PHASE_BOUNDARIES.items():
            known=repetition.get('boundary_masks',{}).get(phase,False)
            masks[boundary]=known
            boundaries[boundary]=repetition.get('boundaries',{}).get(phase) if known else None
        reps.append(dict(boundaries=boundaries,label_masks=dict(phase=masks)))
    return dict(sample_id=record['sample_id'],side=record.get('side',sample.get('side','left')),
        source=dict(subject_group=record['source_group_id'],exercise_id=sample.get('exercise_id','shoulder_abduction'),
                    view=sample.get('view','frontal')),
        repetitions=reps,observable_count=annotation.get('observable_count'),
        observable_count_mask=annotation.get('observable_count_mask',False))


def validate_predictions(manifest,records,*,kind):
    value=_manifest(manifest)
    if (value.get('schema_version')!='rehab_synthetic_predictions/v1' or value.get('kind')!=kind
            or value.get('reference_used_for_predictions') is not False):
        raise ValueError('independent_synthetic_backend_prediction_manifest_required')
    by_id={r['sample_id']:r for r in records}
    rows=value.get('samples')
    if not isinstance(rows,list) or any(not isinstance(r,dict) for r in rows):
        raise ValueError('prediction_rows_required')
    if len({r.get('sample_id') for r in rows})!=len(rows) or any(r.get('sample_id') not in by_id for r in rows):
        raise ValueError('unique_known_prediction_sources_required')
    predictions={r['sample_id']:r for r in rows}
    result=[]
    for source in records:
        pose=_pose(source['pose']); sid=source['sample_id']
        row=predictions.get(sid)
        if row is None:
            result.append(dict(sample_id=sid,status='unavailable',completed_count=None,boundary_events=dict.fromkeys(BOUNDARIES)))
            continue
        if row.get('source_sha256')!=pose['source_sha256'] or row.get('backend')!=pose['backend'] or row.get('split')!=source['split']:
            raise ValueError('prediction_source_backend_or_fixed_split_changed')
        if row.get('status') not in ('completed','failed','unavailable'):
            raise ValueError('prediction_status_required')
        count=row.get('completed_count')
        if count is not None and (type(count) is not int or not 0<=count<=500):
            raise ValueError('prediction_count_is_explicit_integer_or_missing')
        events=row.get('boundary_events')
        if not isinstance(events,dict) or set(events)!=set(BOUNDARIES):
            raise ValueError('independent_boundary_availability_required')
        if row['status']!='completed' and (count is not None or any(v is not None for v in events.values())):
            raise ValueError('failed_prediction_cannot_be_zero_or_partial_count')
        timeline=source.get('timeline',{}).get('presentation_s')
        if timeline is None: timeline=[r['timestamp_s'] for r in pose['frames']]
        for entries in events.values():
            if entries is None: continue
            if not isinstance(entries,list) or len(entries)>500: raise ValueError('bounded_event_inventory_required')
            previous=-1.; ids=set()
            for event in entries:
                t=event.get('time_s')
                if (not _finite(t) or t<previous or not event.get('event_id') or event['event_id'] in ids
                        or event.get('evidence_kind') not in ('observed','filtered')
                        or not any(abs(t-stamp)<=.0002 for stamp in timeline)):
                    raise ValueError('chronological_unique_actual_pts_events_required')
                previous=t; ids.add(event['event_id'])
        result.append(row)
    return value,result


def compare(records,baseline,candidate,output_dir,*,split='test',tolerance_s=.25,engineering_test=False):
    """Keep full split denominators, known/unknown tasks and per-source errors."""
    if split not in ('val','test') or not _finite(tolerance_s) or not 0<tolerance_s<=1:
        raise ValueError('predeclared_heldout_split_and_tolerance_required')
    backend=validate_records(records,engineering_test=engineering_test)
    selected=[r for r in records if r['split']==split]
    if not selected: raise ValueError('nonempty_fixed_heldout_cohort_required')
    def requested(value):
        manifest=_manifest(value)
        known={r['sample_id']:r for r in records}
        if any(r.get('sample_id') not in known for r in manifest.get('samples',[])):
            raise ValueError('prediction_contains_foreign_source')
        # Check immutable identities before filtering. Otherwise a test row
        # misdeclared as train could disappear and masquerade as missing output.
        for row in manifest.get('samples',[]):
            source=known[row['sample_id']];pose=_pose(source['pose'])
            if (row.get('split')!=source['split'] or row.get('backend')!=pose['backend']
                    or row.get('source_sha256')!=pose['source_sha256']):
                raise ValueError('prediction_source_backend_or_fixed_split_changed')
        manifest['samples']=[r for r in manifest.get('samples',[]) if r.get('split')==split]
        return manifest
    b0,p0=validate_predictions(requested(baseline),selected,kind='B0')
    b2,p2=validate_predictions(requested(candidate),selected,kind='B2')
    if b0.get('engineering_test') is not engineering_test or b2.get('engineering_test') is not engineering_test:
        raise ValueError('engineering_and_actual_research_cannot_be_mixed')
    r0=[score_sample(_label(r),p,tolerance_s) for r,p in zip(selected,p0)]
    r2=[score_sample(_label(r),p,tolerance_s) for r,p in zip(selected,p2)]
    for scores,predictions in ((r0,p0),(r2,p2)):
        for score,prediction in zip(scores,predictions):
            score['input_pose_coverage']=prediction.get('coverage')
    a0,a2=aggregate(r0,len(selected)),aggregate(r2,len(selected))
    errors=[]; paired=[]
    for source,left,right in zip(selected,r0,r2):
        delta=None
        if left['count_error'] is not None and right['count_error'] is not None:
            delta=abs(left['count_error'])-abs(right['count_error'])
            paired.append((source['source_group_id'],delta))
        errors.append(dict(sample_id=source['sample_id'],source_group_id=source['source_group_id'],
            B0=left,B2=right,count_absolute_error_improvement=delta))
    complete=(len(paired)==a0['known_count_reference_videos'] and len(paired)>0)
    independent_groups=len({g for g,_ in paired})
    mean_improvement=sum(d for _,d in paired)/len(paired) if paired else None
    # A directional descriptive result is not statistical or clinical proof.
    verdict='evidence_insufficient'
    if not engineering_test and complete and independent_groups>=2 and mean_improvement:
        verdict='improved' if mean_improvement>0 else 'regressed'
    report=dict(schema_version=VERSION,split=split,backend=backend,event_tolerance_s=tolerance_s,
        verdict=verdict,verdict_zh={'improved':'改善','regressed':'退化','evidence_insufficient':'证据不足'}[verdict],
        verdict_basis='paired_per_video_count_absolute_error; descriptive_only_no_significance_claim',
        event_semantics=dict(reference='human_visible_stage_boundaries_on_original_media_pts_not_clinical_3D_truth',
            B0='unchanged_protocol_current_filtered_confirmation_pts_not_physical_motion_onset',
            B2='causal_model_phase_transition_confirmation_at_arrived_source_pts_not_backdated_onset',
            timing_interpretation='definition_and_detection_lag_comparison_not_clinical_ROM_or_motion_capture_accuracy'),
        paired_videos=len(paired),paired_independent_source_groups=independent_groups,
        mean_count_absolute_error_improvement=mean_improvement,B0=a0,B2=a2,per_sample=errors,
        B1=dict(status='not_evaluated',reason='no_separately_frozen_rule_candidate_and_corresponding_reference'),
        quality=dict(status='not_evaluated',reason='no_independent_observable_quality_head_predictions'),
        engineering_test=engineering_test,clinical_accuracy=None,real_human_generalization=None,
        product_enabled=False,created_at=utc_now(),implementation_sha256=file_hash(__file__),
        reference_sha256=canonical_hash([r['annotation'] for r in selected]),
        baseline_sha256=canonical_hash(b0),candidate_sha256=canonical_hash(b2),
        limitation='Synthetic-domain evidence only; no model activation or clinical ROM/quality claim.')
    output=Path(output_dir).resolve()
    if output.exists(): raise ValueError('new_evaluation_output_required_no_overwrite')
    output.mkdir(parents=True)
    write_json(output/'comparison.json',report)
    return dict(path=str(output/'comparison.json'),sha256=file_hash(output/'comparison.json'),
                verdict=verdict,engineering_test=engineering_test)


def baseline_manifest(records,*,engineering_test=False):
    """Actually replay original engine, retaining failures as missing predictions."""
    from .temporal import replay_baseline
    rows=[]; backend=None
    for row in records:
        pose=_pose(row['pose']); backend=backend or pose['backend']
        if pose['backend']!=backend: raise ValueError('separate_backend_baseline_required')
        try:
            prediction=replay_baseline(pose,side=row.get('side','left'),exercise_id=row.get('sample',{}).get('exercise_id','shoulder_abduction'))
            prediction.pop('trace',None)
        except Exception as error:
            prediction=dict(sample_id=row['sample_id'],backend=pose['backend'],source_sha256=pose['source_sha256'],
                status='failed',completed_count=None,boundary_events=dict.fromkeys(BOUNDARIES),
                failure=dict(type=type(error).__name__,message=str(error)))
        prediction['split']=row['split']; rows.append(prediction)
    return dict(schema_version='rehab_synthetic_predictions/v1',kind='B0',backend=backend,
        reference_used_for_predictions=False,engineering_test=engineering_test,product_enabled=False,
        engine='unchanged_ProtocolEngine',samples=rows)
