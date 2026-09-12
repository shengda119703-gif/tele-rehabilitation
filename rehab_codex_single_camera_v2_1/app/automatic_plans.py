"""Auditable general-activity suggestions, not diagnosis or disease prescriptions.

Recipes select compatible movements from official public exercise guidance.
Evidence gates, dose caps and projected-angle targets are versioned engineering
adaptations, NOT clinical cut-offs or doses prescribed by those publications.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone

from .assessment import _time, finite_number, session_value
from .assessment_batches import scope_key
from .domain import digest
from .exercises import EXERCISE_IDS, exercise_spec
from .settings import default_plan
from .training_plans import item_from_plan, new_training_plan, prescription_settings

VERSION = 'general-activity-rules-1'
ORIGIN = 'assessment_rules'
SOURCES = {
    'chair': {'title': 'NHS North Tees：Chair Exercises',
              'url': 'https://www.nth.nhs.uk/resources/chair-exercises/'},
    'bed': {'title': 'NHS North Tees：Bed Exercise',
            'url': 'https://www.nth.nhs.uk/resources/bed-exercise/'},
    'strength': {'title': 'NHS：Strength exercises',
                 'url': 'https://www.nhs.uk/live-well/exercise/strength-exercises/'},
    'sitting': {'title': 'NHS：Sitting exercises',
                'url': 'https://www.nhs.uk/live-well/exercise/sitting-exercises/'},
    'who': {'title': 'WHO：Guidelines on physical activity and sedentary behaviour',
            'url': 'https://www.who.int/publications/i/item/9789240015128'},
}
# source section, supported standing needed, optional projected-angle ceiling,
# and whether the public source describes this same movement pattern.
RECIPES = {
    'shoulder_flexion': ('chair', 'Frontal Raise', False, 90., 'matched'),
    'shoulder_abduction': ('chair', 'Lateral Raise', False, 90., 'matched'),
    'elbow_flexion': ('bed', 'Elbow Flexion', False, None, 'matched'),
    'knee_extension': ('chair', 'Knee Extension', False, None, 'matched'),
    'ankle_dorsiflexion': ('sitting', 'Ankle stretch', False, None, 'matched'),
    'ankle_plantarflexion': ('sitting', 'Ankle stretch', False, None, 'matched'),
    'hip_abduction': ('strength', 'Sideways leg lift', True, None, 'matched'),
    'hip_extension': ('strength', 'Leg extension', True, None, 'matched'),
    'sit_to_stand': ('strength', 'Sit-to-stand', True, None, 'matched'),
}
_SUPPORTED_STANDING = {'sit_to_stand', 'hip_abduction', 'hip_adduction', 'hip_flexion',
                       'hip_extension', 'knee_flexion'}
for _eid in EXERCISE_IDS:
    RECIPES.setdefault(_eid, ('who', '从少量开始，并按本人功能能力调整',
                              _eid in _SUPPORTED_STANDING, None, 'assessment_adapted'))
SCREEN_FIELDS = ('general_activity_ok', 'standing_support_ok', 'companion_present')


def _now(now=None):
    return now or datetime.now(timezone.utc)


def _same_scope(session, scope):
    return all(session_value(session, k) == v for k, v in scope.items())


def observed_quality(repetitions):
    """Scope is only recorded goals/metrics; absence of issues is not global quality."""
    counts = dict(observed_goals_met=0, needs_adjustment=0, unassessable=0)
    for rep in repetitions:
        primary = (rep.get('metric_validity') or {}).get(rep.get('primary_metric'), {})
        if (rep.get('completion_status') != 'COMPLETE' or rep.get('observation_status') != 'VALID'
                or primary.get('valid') is not True or primary.get('partial_observation')
                or rep.get('target_status') not in ('MET', 'NOT_MET', 'NOT_SET')):
            category = 'unassessable'
        elif rep.get('target_status') == 'NOT_MET':
            category = 'needs_adjustment'
        elif any(i.get('evidence_valid') is True for i in rep.get('issues', [])):
            category = 'needs_adjustment'
        elif rep.get('target_status') == 'NOT_SET':
            category = 'unassessable'
        else:
            goals = (rep.get('movement_timing') or {}).get('goals', {})
            states = list(goals.values())
            category = ('needs_adjustment' if 'NOT_MET' in states else
                        'unassessable' if 'UNASSESSABLE' in states else 'observed_goals_met')
        counts[category] += 1
    counts['note'] = '仅评价已设置目标与可见指标，不代表整体动作完全正确、肌力或诊断。'
    return counts


def feedback_block(session):
    feedback = session.get('training_feedback') or {}
    pain, fatigue = finite_number(feedback.get('pain')), finite_number(feedback.get('fatigue'))
    return bool((pain is not None and pain > 0) or (fatigue is not None and fatigue >= 5)
                or feedback.get('reason') in ('discomfort', 'fatigue'))


def generate_proposal(profile, sessions, participant=None, *, now=None):
    now, scope = _now(now), scope_key(profile)
    participant = participant or {}
    blocked = []
    if participant.get('restrictions') or participant.get('reason'):
        blocked.append('档案已有疾病、康复原因或活动限制，请先由专业人员核对适用方案；保留人工计划入口。')
    candidates, excluded, body = [], [], []
    for row in profile['items']:
        if not row.get('session_id'):
            continue
        eid, side = row['exercise_id'], row['side']
        label = row['exercise_label'] + (' · 左侧' if side == 'left' else ' · 右侧')
        span = row.get('motion_range')
        body.append(dict(label=label, status=row['status'], motion_range=copy.deepcopy(span),
                         completed=row.get('completed'), valid_ratio=row.get('valid_ratio'),
                         session_id=row['session_id'], metric_label=row['primary_metric_label']))
        reason = None
        end = _time(row.get('end_utc'))
        completed = row.get('completed')
        ratio = finite_number(row.get('valid_ratio'))
        if eid not in RECIPES:
            reason = '此动作暂未接入适用的自动练习规则，可保留评估或使用专业人员安排。'
        elif row['status'] != 'ASSESSED' or row.get('session_status') not in ('FINISHED', 'COMPLETED'):
            reason = '最近一次评估未有效完成，请补测。'
        elif end is None or not 0 <= (now-end).total_seconds() <= 7*86400:
            reason = '评估已超过本版 7 天复核窗口或日期异常，请重新评估。'
        elif ratio is None or ratio < .8 or type(completed) is not int or completed < 1:
            reason = '本次有效观察或完整动作不足，请调整取景后补测。'
        elif (row.get('conditions') or {}).get('measurement_contract') != exercise_spec(eid)['measurement_contract']:
            reason = '测量定义已变化，请重新评估。'
        # Recent unresolved discomfort is not erased by an unrelated assessment.
        training = [s for s in sessions if _same_scope(s, scope) and session_value(s, 'submode') == 'training'
                    and session_value(s, 'exercise_id') == eid and session_value(s, 'side') == side
                    and _time(s.get('end_utc')) is not None]
        latest = max(training, key=lambda s: (_time(s['end_utc']), s.get('id', '')), default=None)
        if latest and feedback_block(latest):
            reason = '最近训练报告了不适或明显疲劳，先处理原因并由专业人员核对，不自动续练。'
        if reason:
            excluded.append(dict(label=label, reason=reason))
            continue
        source, section, standing, cap, evidence_kind = RECIPES[eid]
        plan = default_plan(eid)
        low, high = span['min_deg'], span['max_deg']
        target = (low+.8*(high-low) if exercise_spec(eid)['target_direction'] == 'increase'
                  else high-.8*(high-low))
        if cap is not None:
            target = min(target, cap)
        # No forced end-range; sit-to-stand continues to use its personal baseline.
        if eid == 'sit_to_stand' or not 0 <= target <= 180 or not low <= target <= high or high-low < 15:
            target = None
        plan.update(side=side, target_reps=min(5, completed), target_sets=1,
                    rest_between_sets_s=60., target_angle_deg=round(target, 1) if target is not None else None,
                    needs_companion=participant.get('support') == 'assisted',
                    use_of_hands='allowed' if standing else 'not_recorded')
        # Preserve existing explicit quality limits only; never infer a normal
        # elbow/trunk range from the absence of recorded issues.
        evidence = next((s for s in sessions if s.get('id') == row['session_id']), {})
        old = (evidence.get('config_snapshot') or {}).get('plan') or {}
        for field in ('allowed_elbow_flexion_deg', 'allowed_trunk_tilt_deg'):
            plan[field] = old.get(field)
        entry = item_from_plan(plan)
        entry.update(label=label, standing=standing, assessment_id=row['session_id'],
                     assessment_fingerprint=digest(row), source=dict(SOURCES[source], section=section, checked='2026-09-12'),
                     evidence_kind=evidence_kind,
                     rationale=f'有效评估完成 {completed} 次；先安排 {plan["target_reps"]} 次 × 1 组，不超过本次已观察次数。',
                     instruction=('使用稳固无轮椅作为支撑，站稳后练习。' if standing else '坐稳后练习，不加负重。')
                     + '只在舒适范围内活动，不为追角度忍痛。')
        candidates.append(entry)
    trained_at = {}
    for session in sessions:
        if (_same_scope(session, scope) and session_value(session, 'submode') == 'training'
                and session.get('measurement_mode') != 'guided_timed'
                and session.get('status') in ('FINISHED', 'COMPLETED')
                and (session.get('summary') or {}).get('plan_completed') is True
                and _time(session.get('end_utc'))):
            key = (session_value(session, 'exercise_id'), session_value(session, 'side'))
            trained_at[key] = max(trained_at.get(key, datetime.min.replace(tzinfo=timezone.utc)), _time(session['end_utc']))
    candidates.sort(key=lambda i: ((i['exercise_id'], i['side']) in trained_at, i['standing'],
                                   EXERCISE_IDS.index(i['exercise_id']), i['side']))
    result = dict(scope, schema_version=1, rule_version=VERSION, candidates=candidates,
                  excluded=excluded, body=body, blockers=blocked,
                  participant_fingerprint=digest(participant), max_items=4,
                  note='53 项现有动作均已接入。一般关节活动与基础功能建议，不是疾病或术后处方。每次最多 4 项，完成后下一轮优先安排尚未练过的动作；不自动加量。')
    result['fingerprint'] = digest(result)
    return result


def create_automatic_plan(proposal, screening, *, now=None):
    if (not isinstance(screening, dict) or set(screening) != set(SCREEN_FIELDS)
            or any(type(screening[k]) is not bool for k in SCREEN_FIELDS)):
        raise ValueError('请完成本次简短适用性确认')
    if proposal['blockers']:
        raise ValueError(proposal['blockers'][0])
    if not screening['general_activity_ok']:
        raise ValueError('有不适、医嘱限制、术后限制或不确定时，不启用一般自动计划，请先咨询专业人员。')
    selected = [i for i in proposal['candidates'] if not i['standing'] or screening['standing_support_ok']][:4]
    if not selected:
        raise ValueError('暂时没有适用项目，请先完成一次可用评估；站立项目还需确认稳固支撑。')
    if any(i['settings']['needs_companion'] for i in selected) and not screening['companion_present']:
        raise ValueError('档案注明需要协助，请陪同者在场后再继续')
    record = new_training_plan(proposal, '自动安排 · 基础活动', selected)
    record['record_origin'] = ORIGIN
    record['automatic'] = dict(rule_version=VERSION, proposal_fingerprint=proposal['fingerprint'],
                               participant_fingerprint=proposal['participant_fingerprint'],
                               screening=copy.deepcopy(screening), confirmed_utc=_now(now).isoformat(),
                               entries=copy.deepcopy(selected), body=copy.deepcopy(proposal['body']),
                               note=proposal['note'])
    return record


def validate_metadata(record):
    meta = record.get('automatic')
    if (not isinstance(meta, dict) or meta.get('rule_version') != VERSION
            or not isinstance(meta.get('entries'), list) or not 1 <= len(meta['entries']) <= 4
            or _time(meta.get('confirmed_utc')) is None):
        raise ValueError('自动计划规则版本无效，请重新生成')
    screening = meta.get('screening')
    if (not isinstance(screening, dict) or set(screening) != set(SCREEN_FIELDS)
            or any(type(screening[k]) is not bool for k in SCREEN_FIELDS)):
        raise ValueError('自动计划适用性记录无效，请重新生成')
    for entry in meta['entries']:
        recipe = RECIPES.get(entry.get('exercise_id'))
        if not recipe:
            raise ValueError('自动计划动作规则无效，请重新生成')
        source, section, standing, _, evidence_kind = recipe
        if (entry.get('source') != dict(SOURCES[source], section=section, checked='2026-09-12')
                or entry.get('standing') is not standing or entry.get('evidence_kind') != evidence_kind
                or not isinstance(entry.get('assessment_fingerprint'), str)):
            raise ValueError('自动计划来源证据无效，请重新生成')
    expected = [item_from_plan(dict(i['settings'], exercise_id=i['exercise_id'], side=i['side']))
                for i in meta['entries']]
    if expected != record['items']:
        raise ValueError('自动安排已被改动，请重新生成；人工修改请另建人工计划')
    return copy.deepcopy(meta)


def validate_automatic_use(record, entry_key, profile, sessions, participant, execution=None, *, now=None):
    meta = validate_metadata(record)
    now = _now(now)
    if not 0 <= (now-_time(meta['confirmed_utc'])).total_seconds() <= 86400:
        raise ValueError('本次适用确认已过期，请重新生成今天的计划')
    proposal = generate_proposal(profile, sessions, participant, now=now)
    if meta['participant_fingerprint'] != proposal['participant_fingerprint'] or proposal['blockers']:
        raise ValueError('个人适用条件已变化，请重新核对自动计划')
    # Rebuild from current saved evidence and rules; do not trust copied UI goals.
    canonical = create_automatic_plan(proposal, meta['screening'], now=now)
    selected = next((i for i in canonical['automatic']['entries'] if i['key'] == entry_key), None)
    frozen = next((i for i in meta['entries'] if i['key'] == entry_key), None)
    if selected is None or selected != frozen:
        raise ValueError('本项评估或适用条件已变化，请重新生成计划，不沿用旧目标')
    progress = program_progress(record, sessions)
    if progress['blocked']:
        raise ValueError(progress['blocked'])
    if progress['next_key'] != entry_key:
        raise ValueError('请按计划顺序继续；已完成的项目不自动追加练习')
    if execution is not None and prescription_settings(execution, selected['exercise_id']) != selected['settings']:
        raise ValueError('自动计划参数已改变，请重新生成或改用单独的人工计划')
    return meta


def program_progress(record, sessions):
    scope, rows, blocked = scope_key(record), [], ''
    for entry in record['items']:
        matches = []
        for session in sessions:
            ref = session_value(session, 'saved_plan_reference') or {}
            if (_same_scope(session, scope) and session_value(session, 'submode') == 'training'
                    and ref.get('id') == record['id'] and ref.get('revision') == record['revision']
                    and ref.get('entry_key') == entry['key'] and _time(session.get('end_utc')) is not None):
                matches.append(session)
        latest = max(matches, key=lambda s: (_time(s['end_utc']), s.get('id', '')), default=None)
        done, quality = False, None
        if latest:
            feedback = latest.get('training_feedback') or {}
            if feedback_block(latest):
                blocked = '已报告不适或明显疲劳，本次计划到此结束。先休息并处理原因，必要时联系专业人员。'
            elif feedback.get('pain') is None or feedback.get('fatigue') is None:
                blocked = blocked or '请先在上一项训练结果中记录疼痛和疲劳感受，再继续。'
            done = (latest.get('measurement_mode') != 'guided_timed'
                    and (latest.get('summary') or {}).get('plan_completed') is True
                    and latest.get('status') in ('FINISHED', 'COMPLETED'))
            quality = observed_quality(latest.get('repetitions') or [])
        rows.append(dict(key=entry['key'], done=done, session_id=latest.get('id') if latest else None,
                         quality=quality))
    return dict(items=rows, completed=sum(i['done'] for i in rows), total=len(rows), blocked=blocked,
                next_key=next((i['key'] for i in rows if not i['done']), None))
