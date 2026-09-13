"""Isolated synthetic evidence for demonstrating assessment-driven planning."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .assessment import build_body_profile
from .automatic_plans import create_automatic_plan, generate_proposal
from .exercises import exercise_spec
from .participants import legacy_participant


DEMO_PARTICIPANT_ID = 'demo-automatic-rehab'
DEMO_SCOPE = {
    'participant_id': DEMO_PARTICIPANT_ID,
    'source_kind': 'SYNTHETIC',
    'usage_context': 'TEST',
}
DEMO_PLAN_NAME = '临时演示 · 评估生成训练计划'

# These are plausible camera-plane observations for a product demonstration,
# not reference ranges, clinical norms, diagnoses, or measurements of a person.
DEMO_ASSESSMENTS = (
    ('shoulder_abduction', 'left', 12., 76., 5, .94),
    ('shoulder_flexion', 'left', 16., 88., 5, .92),
    ('elbow_flexion', 'left', 35., 120., 6, .96),
    ('knee_extension', 'right', 25., 105., 5, .91),
)


def demo_participant():
    profile = legacy_participant(DEMO_PARTICIPANT_ID)
    profile.update(
        display_name='演示患者 · 自动计划',
        affected_side='left',
        reported_by='self',
        support='independent',
        goals='演示评估结果如何自动形成基础训练安排',
        notes='仅供产品演示；全部评估数值均为合成测试数据，不代表任何真实患者。',
    )
    return profile


def demo_assessment_sessions(*, now=None):
    now = now or datetime.now(timezone.utc)
    sessions = []
    for index, (exercise_id, side, low, high, completed, ratio) in enumerate(DEMO_ASSESSMENTS):
        spec = exercise_spec(exercise_id)
        end = now-timedelta(minutes=8-index)
        sessions.append({
            **DEMO_SCOPE,
            'id': f'demo-auto-assessment-{exercise_id}-{side}',
            'scene_id': 'rehab',
            'submode': 'assessment',
            'exercise_id': exercise_id,
            'side': side,
            'status': 'FINISHED',
            'stop_reason': 'demo_completed',
            'start_utc': (end-timedelta(minutes=2)).isoformat(),
            'end_utc': end.isoformat(),
            'measurement_mode': 'auto_observed',
            'measurement_contract': spec['measurement_contract'],
            'source_ref': 'synthetic:temporary-automatic-plan-demo',
            'schema_id': 'demo-synthetic-pose-1',
            'model_manifest_id': 'synthetic-demo-no-model',
            'annotation_origin': 'synthetic_demo',
            'config_snapshot': {
                'poses_consent': False,
                'source_ref': 'synthetic:temporary-automatic-plan-demo',
                'schema_id': 'demo-synthetic-pose-1',
                'model_manifest_id': 'synthetic-demo-no-model',
                'view': spec['view'],
                'plan': {
                    **DEMO_SCOPE,
                    'submode': 'assessment',
                    'exercise_id': exercise_id,
                    'side': side,
                },
            },
            'summary': {
                'primary_metric': spec['metric'],
                'valid_ratio': ratio,
                'valid_sample_count': 40,
                'completed': completed,
                'partial': 0,
                'invalid': 0,
                'motion_range_valid': True,
                'motion_range': {
                    'min_deg': low,
                    'max_deg': high,
                    'range_deg': high-low,
                },
                'demo_note': '合成演示数据，不是患者测量或临床正常值。',
            },
            'repetitions': [],
        })
    return sessions


def build_demo_plan(*, now=None):
    """Run the production planning rules against synthetic demo evidence."""
    now = now or datetime.now(timezone.utc)
    sessions = demo_assessment_sessions(now=now)
    participant = demo_participant()
    profile = build_body_profile(sessions, **DEMO_SCOPE)
    proposal = generate_proposal(profile, sessions, participant, now=now)
    plan = create_automatic_plan(proposal, {
        'general_activity_ok': True,
        'standing_support_ok': False,
        'companion_present': False,
    }, now=now)
    plan['name'] = DEMO_PLAN_NAME
    plan['automatic']['note'] = (
        '临时产品演示：评估数值为 SYNTHETIC / TEST 合成数据。'
        '动作、次数组合与角度目标由当前自动安排规则计算，不能用于真实患者。'
    )
    return participant, sessions, proposal, plan


def install_demo_plan(store, *, now=None):
    """Idempotently replace only this isolated demo participant's plan/data."""
    now = now or datetime.now(timezone.utc)
    participant, sessions, _, _ = build_demo_plan(now=now)
    existing = store.get_participant(DEMO_PARTICIPANT_ID)
    saved_participant = store.save_participant(
        participant, expected_revision=(existing or {}).get('revision', 0))
    for session in sessions:
        session['participant_snapshot'] = saved_participant
        store.save_session(session)
    profile = build_body_profile(sessions, **DEMO_SCOPE)
    proposal = generate_proposal(profile, sessions, saved_participant, now=now)
    plan = create_automatic_plan(proposal, {
        'general_activity_ok': True,
        'standing_support_ok': False,
        'companion_present': False,
    }, now=now)
    plan['name'] = DEMO_PLAN_NAME
    plan['automatic']['note'] = (
        '临时产品演示：评估数值为 SYNTHETIC / TEST 合成数据。'
        '动作、次数组合与角度目标由当前自动安排规则计算，不能用于真实患者。'
    )
    for old in store.list_training_plans(DEMO_SCOPE):
        if old.get('record_origin') == 'assessment_rules':
            store.set_training_plan_archived(
                old['id'], DEMO_SCOPE, True, expected_revision=old['revision'])
    saved_plan = store.save_training_plan(plan, expected_revision=0)
    return {
        'scope': dict(DEMO_SCOPE),
        'participant': saved_participant,
        'proposal': proposal,
        'plan': saved_plan,
    }
