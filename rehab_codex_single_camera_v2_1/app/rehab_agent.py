"""Local, evidence-backed turn planner adapted from Ankang's routing pattern.

Only reads saved evidence and proposes allowlisted navigation. The existing
automatic planner and controller retain all screening, dose and camera authority.
No network model, free-form tool execution, or patient-data writes occur here.
"""
from __future__ import annotations

import re

from .assessment import build_body_profile, session_value
from .assessment_batches import scope_key
from .automatic_plans import (ORIGIN, generate_proposal, program_progress,
                              validate_metadata, validate_automatic_use)
from .domain import utc_now

VERSION = 'rehab-agent-local-1'
ACTIONS = {
    'assessment': '去做身体评估',
    'automatic': '查看并确认训练安排',
    'body': '查看身体档案',
    'history': '查看历史记录',
}


def understand(text):
    """Deliberately bounded intents; uncertainty never authorizes exercise."""
    if not isinstance(text, str) or not text.strip() or len(text) > 500:
        raise ValueError('请输入 1–500 字的问题')
    # Mentions (including negation/history) go to clarification, not diagnosis.
    # This conservative rule never infers that a symptom actually occurred.
    if re.search(r'疼|痛|累|疲劳|不舒服|头晕|胸闷|喘|摔|跌|无力|麻木|术后|手术|医嘱', text):
        return 'check_condition'
    if re.search(r'不想练|不练|不想训练|不训练|先不|暂不|休息|取消', text):
        return 'defer'
    if re.search(r'历史|进展|进步|变化|上次|以前|记录', text):
        return 'history'
    if re.search(r'评估|测试结果|身体情况|身体状态|测得|测了', text):
        return 'assessment'
    if re.search(r'练|计划|安排|做什么|干什么|为什么|依据|继续', text):
        return 'plan'
    return 'help'


def answer(store, scope, text, *, now=None):
    """Fresh scope-filtered facts per request, never cached across people."""
    scope = scope_key(scope)
    intent = understand(text)
    result = dict(scope=scope, version=VERSION, intent=intent, at=utc_now(),
                  text='', actions=[], evidence=[], tools=[])

    def reply(message, *actions):
        result['text'] = message
        result['actions'] = [dict(id=a, label=ACTIONS[a]) for a in actions]
        return result

    if intent == 'check_condition':
        return reply('你提到了身体感受或活动限制，我还不能判断是在说现在、过去，还是没有这些情况。'
                     '请先核对当前感受；当前有不适时暂不开始训练。'
                     '已结束的训练可在训练结果中填写疼痛和疲劳。'
                     '这句话没有被记成诊断，也没有自动修改计划。', 'history')
    if intent == 'help':
        return reply('我目前能根据本机记录回答：今天该练什么、评估结果如何、为什么这样安排，'
                     '以及带你查看历史。可以试试下方的快捷问题。'
                     '当前是本地规则版，还不支持通用聊天或语音。')
    if intent == 'defer':
        return reply('好的，现在先不安排训练。可以关闭管家；已有计划和记录会保留。')

    sessions = [s for s in store.list_sessions()
                if all(session_value(s, k) == v for k, v in scope.items())]
    result['tools'].append('rehab.read_saved_sessions')
    prefix = ('当前是合成演示数据，不用于真人训练。\n' if scope['source_kind'] == 'SYNTHETIC'
              else '当前查看录像回放记录。\n' if scope['source_kind'] == 'REPLAY_FILE' else '')
    if scope['usage_context'] != 'SELF_USE':
        prefix += '记录属于演示或测试情境。\n'
    if intent == 'history':
        assessments = sum(s.get('scene_id') == 'rehab' and session_value(s, 'submode') == 'assessment' for s in sessions)
        trainings = sum(s.get('scene_id') == 'rehab' and session_value(s, 'submode') == 'training' for s in sessions)
        return reply(prefix + f'当前用户和来源下，保存了 {assessments} 条评估、{trainings} 条训练记录。'
                     '这些是保存记录数，不代表全部有效或全部完成。'
                     '是否有变化需要在历史页面核对相同测量条件。', 'history')

    profile = build_body_profile(sessions, **scope)
    participant = store.get_participant(scope['participant_id'])
    proposal = generate_proposal(profile, sessions, participant, now=now)
    result['tools'].extend(['rehab.build_body_profile', 'rehab.generate_proposal'])
    result['evidence'] = [dict(session_id=r['session_id'], label=r['label'], status=r['status'])
                          for r in proposal['body']]
    if intent == 'assessment':
        if not proposal['body']:
            return reply(prefix + '还没有找到当前用户和来源下的评估记录。先选择一个动作完成评估并保存。', 'assessment')
        lines = [prefix + '最近保存的各项评估：']
        for row in proposal['body'][:8]:
            span = row.get('motion_range')
            detail = (f"完整动作 {row['completed']} 次，投影角范围 {span['min_deg']:.0f}°–{span['max_deg']:.0f}°"
                      if row['status'] == 'ASSESSED' and span else '没有可用于安排训练的有效结果')
            lines.append(row['label'] + '：' + detail)
        lines.append('这是摄像头下的动作观察，不是诊断；完整明细见身体档案。')
        return reply('\n'.join(lines), 'body', 'assessment')

    if proposal['blockers']:
        return reply(prefix + '\n'.join(proposal['blockers']), 'body')
    records = [r for r in store.list_training_plans(scope) if r.get('record_origin') == ORIGIN]
    result['tools'].append('rehab.read_training_plans')
    if records:
        record = records[0]
        try:
            validate_metadata(record)
            progress = program_progress(record, sessions)
            lead = f"已保存的这轮计划完成 {progress['completed']} / {progress['total']} 项。"
            if progress['blocked']:
                return reply(prefix + lead + '\n' + progress['blocked'], 'automatic')
            if progress['next_key'] is None:
                return reply(prefix + lead + '\n这轮已经完成，不自动追加训练。可以查看结果；下次使用前重新核对安排。', 'history')
            validate_automatic_use(record, progress['next_key'], profile, sessions, participant, now=now)
            entry = next(e for e in record['automatic']['entries'] if e['key'] == progress['next_key'])
            return reply(prefix + lead + '\n下一项：' + entry['label'] + '。\n' + entry['rationale']
                         + '\n点击后进入现有计划页面，核对安排并按原步骤准备；不会自动打开摄像头。', 'automatic')
        except ValueError as exc:
            return reply(prefix + '旧计划需要重新核对：' + str(exc), 'automatic', 'assessment')
    if not proposal['candidates']:
        reasons = '\n'.join(e['label'] + '：' + e['reason'] for e in proposal['excluded'][:3])
        return reply(prefix + '目前没有足够的有效评估来安排训练。'
                     + ('\n' + reasons if reasons else '\n先完成一个动作的评估并保存。'), 'assessment')
    lines = [prefix + '根据最近有效评估，以下项目可供确认（这还不是已保存的计划）：']
    for entry in proposal['candidates'][:4]:
        lines.append(entry['label'] + '：' + entry['rationale']
                     + (' 需要确认站立支撑。' if entry['standing'] else ''))
    lines.append('依据：7 天内、有效观察至少 80%、有完整动作；每项先 1 组、最多 5 次。'
                 '这些是现有软件规则，不是疾病处方。请在下一页确认当前感受、活动限制和陪同条件。')
    return reply('\n'.join(lines), 'automatic')
