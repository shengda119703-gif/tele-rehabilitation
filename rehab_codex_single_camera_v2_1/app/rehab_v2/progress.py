"""Plan-only projections of committed v2 facts, never legacy measurements.

The existing completion/feedback policy remains authoritative. These views are
temporary inputs to that policy; no legacy session, assessment, angle or patient
record is rewritten. Actual input scope must match the frozen plan scope.
"""
from __future__ import annotations

import copy

from ..assessment_batches import scope_key
from ..automatic_plans import program_progress
from ..domain import digest


VERSION = 'rehab-plan-contribution-1'


def contribution(item):
    frozen, summary = item['frozen_plan'], item['snapshot'] or {}
    plan, spec = frozen['plan'], frozen.get('protocol') or {}
    training = summary.get('training') or {}
    scope, reason = frozen.get('progress_scope'), None
    try:
        scope = scope_key(scope)
    except ValueError:
        scope, reason = None, 'missing_verified_plan_scope'
    if scope and (scope['source_kind'] != item['source']['source_kind']
                  or scope['usage_context'] != item['source']['usage_context']
                  or scope['participant_id'] != plan.get('participant_id')):
        reason = 'actual_input_does_not_match_plan_scope'
    if plan.get('submode') != 'training':
        reason = 'assessment_is_not_training_progress'
    complete = (reason is None and item['end_reason'] in ('completed', 'user_stopped', 'discomfort')
                and training.get('plan_complete') is True
                and training.get('completed_sets') == plan.get('target_sets')
                and training.get('target_reps') == plan.get('target_reps')
                and training.get('target_sets') == plan.get('target_sets'))
    identity = dict(session_id=item['session_id'], plan_id=frozen['plan_id'],
                    plan_revision=frozen['plan_revision'], entry_key=frozen['entry_key'])
    receipt = item['canonical_commit']
    return dict(identity, contribution_id=digest(identity), policy_version=VERSION,
                commit_id=receipt['commit_id'], committed_at=receipt['committed_at'],
                visual_snapshot_digest=receipt['visual_snapshot_digest'],
                reference_digest=digest(frozen['reference']), scope=scope,
                actual_source=copy.deepcopy(item['source']), exercise_id=plan['exercise_id'],
                side=spec.get('side', plan.get('side')), protocol_version=spec.get('protocol_version'),
                metric_version=spec.get('metric_version'), completed_reps=summary.get('completed', 0),
                completed_sets=training.get('completed_sets', 0), plan_completed=complete,
                progress_eligible=reason is None, exclusion_reason=reason,
                end_reason=item['end_reason'], record_origin='committed_visual_training_fact',
                no_legacy_measurement_projection=True)


def progress_session(item, record):
    """Validate binding before presenting a fact to the original plan policy."""
    value = item['plan_contribution']
    frozen = item['frozen_plan']
    scope = scope_key(record)
    if (not value['progress_eligible'] or value['scope'] != scope
            or value['plan_id'] != record['id'] or value['plan_revision'] != record['revision']
            or value['entry_key'] not in {entry['key'] for entry in record['items']}):
        return None
    if value['reference_digest'] != digest(frozen['reference']):
        raise ValueError('committed_plan_reference_digest_mismatch')
    reference = frozen['reference']
    entry = next(entry for entry in record['items'] if entry['key'] == value['entry_key'])
    if (reference.get('id'), reference.get('revision'), reference.get('entry_key'), reference.get('item')) != (
            record['id'], record['revision'], entry['key'], entry):
        raise ValueError('committed_plan_binding_mismatch')
    return eligibility_session(item)


def eligibility_session(item):
    """Pain/fatigue follows the actual person/action, not only one plan ID."""
    value, frozen = item['plan_contribution'], item['frozen_plan']
    if not value['progress_eligible']:
        return None
    scope, plan = value['scope'], frozen['plan']
    if (value['reference_digest'] != digest(frozen['reference'])
            or value['visual_snapshot_digest'] != digest(item['snapshot'])):
        raise ValueError('committed_evidence_digest_mismatch')
    return dict(scope, id=item['session_id'], submode='training',
                exercise_id=plan['exercise_id'], side=plan['side'],
                status='FINISHED' if item['end_reason'] in ('completed', 'user_stopped', 'discomfort') else 'INTERRUPTED',
                end_utc=item['canonical_commit']['committed_at'],
                saved_plan_reference=dict(id=value['plan_id'], revision=value['plan_revision'], entry_key=value['entry_key']),
                measurement_mode='backend_v2_auto_observed',
                summary=dict(plan_completed=value['plan_completed']),
                training_feedback=copy.deepcopy(item.get('latest_feedback') or {}),
                repetitions=[], projection_kind='plan_policy_only_not_legacy_measurement',
                plan_contribution_id=value['contribution_id'])


def progress_views(items, record):
    return [view for item in items if (view := progress_session(item, record)) is not None]


def eligibility_views(items):
    return [view for item in items if (view := eligibility_session(item)) is not None]


def plan_progress(record, legacy_sessions, items):
    """Same dose/order/feedback rules, with v2 evidence kept separately typed."""
    result = program_progress(record, legacy_sessions + progress_views(items, record))
    by_id = {item['session_id']: item for item in items}
    for row in result['items']:
        item = by_id.get(row['session_id'])
        if item:
            # Do not run the legacy angle/quality interpretation on v2 reps.
            row['quality'] = None
            row['v2_observed_quality'] = [dict(rep_index=rep['rep_index'],
                completion_status=rep['completion_status'], target_status=rep['target_status'],
                quality_status=rep['quality_status'], quality_assessable=rep['quality_assessable'])
                for rep in (item['snapshot'] or {}).get('repetitions', [])]
            row['contribution'] = item['plan_contribution']
            row['feedback_revision'] = item['feedback_revision']
    result.update(progress_policy_version=VERSION, eligibility_rule_ref='general-activity-rules-1',
                  legacy_records_unchanged=True, derived_from_committed_facts=True)
    return result
