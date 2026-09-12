from __future__ import annotations

import csv
from datetime import datetime, timezone
import html
from pathlib import Path
import re
from collections import Counter
from statistics import median

from .assessment import (COMPARISON_NOTE, EXERCISE_IDS, STATUS_LABELS, anonymous_participant,
                         finite_number, session_conditions, session_motion_range, session_value)
from .domain import SOURCES, CONTEXTS, SCENES, clean_json, digest, dumps
from .exercises import exercise_spec
from .storage import Storage


LABELS = {'COMPLETE': '完整完成', 'PARTIAL': '部分尝试', 'INTERRUPTED': '中断',
          'UNASSESSABLE': '无法评价', 'MET': '达到个人目标', 'NOT_MET': '未达个人目标',
          'NOT_SET': '未设置目标', 'VALID': '观察有效', 'PARTIAL_OBSERVABLE': '部分可观察',
          'UNUSABLE': '观察不足', 'elbow_flexion': '抬举时可见屈肘',
          'trunk_tilt': '可见躯干侧倾', 'lowering_tempo': '下降节奏超出已设范围',
          'target_not_reached': '未达人工设置的角度目标'}
SIDES = {'left': '左侧', 'right': '右侧'}
MODES = {'assessment': '身体评估', 'training': '康复训练'}
SESSION_STATUSES = {'FINISHED': '已结束', 'COMPLETED': '已结束', 'INTERRUPTED': '已中断', 'RUNNING': '进行中'}
TIMING_METRICS = ('outbound_s', 'endpoint_dwell_s', 'return_s', 'target_hold_s')
TIMING_REASONS = {'incomplete_cycle': '未观察到完整回程', 'standing_not_observed': '未观察到确认站位',
                  'occlusion': '期间缺测', 'stream_gap': '输入时间断开', 'invalid_metric': '指标无效',
                  'insufficient_valid_samples': '有效样本不足', 'unobserved_phase_boundary': '阶段边界未观察完整',
                  'ambiguous_peak_band': '多段峰区，无法唯一分期', 'no_hold_anchor': '未设置保持角度',
                  'no_valid_samples': '没有有效样本', 'user_pause': '用户暂停', 'user_stop': '用户结束',
                  'training_boundary': '训练阶段切换', 'identity_ambiguous': '参与者不明确'}
STYLE = """body{font-family:'Microsoft YaHei UI',sans-serif;color:#203c3d;background:#f5f8f6;
max-width:1200px;margin:24px auto;padding:24px;line-height:1.7}h1{font-size:26px}h2{font-size:18px}
.tag{color:#13776c}.muted{color:#627476}table{border-collapse:collapse;width:100%;background:white}
td,th{padding:8px;border:1px solid #dbe7e1;text-align:left;vertical-align:top}
.note{background:#e7f1eb;padding:14px}code{font-size:12px;word-break:break-all}"""


def fmt(value, decimals=1):
    if value is None:
        return '—'
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = finite_number(value)
        return '—' if number is None else f'{number:.{decimals}f}'
    return html.escape(str(value), quote=True)


def _percent(value):
    number = finite_number(value)
    return fmt(number*100) + ' %' if number is not None and 0 <= number <= 1 else '—'


def _document(title, body, style=STYLE):
    return (f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>{fmt(title)}</title>'
            f'<style>{style}</style></head><body>{body}</body></html>')


def _public_ref(value):
    if value is None or value == '':
        return None
    if isinstance(value, str) and re.fullmatch(r'source-[0-9a-f]{16}', value):
        return value
    return 'source-' + digest(value)[:16]


MEASUREMENT_MODES = {'auto_observed': '自动测量', 'guided_timed': '引导计时（不自动测角度）'}


def continuation_evidence(session):
    """Split this record into observed, approximate, self-reported and unavailable."""
    summary = session.get('summary') or {}
    continuation = session.get('continuation') or {}
    mode = session.get('measurement_mode') or summary.get('measurement_mode') or 'auto_observed'
    reports = continuation.get('self_reports') or []
    approximate = summary.get('approximate_range')
    approximate = approximate if isinstance(approximate, dict) else None
    return {'mode': mode, 'mode_label': MEASUREMENT_MODES.get(mode, '测量方式未记录'),
            'self_reported': len(reports), 'prompt_plan': continuation.get('prompt_plan'),
            'prompted_cycles': continuation.get('prompted_cycles') or 0,
            'approximate_range': approximate, 'guided': mode == 'guided_timed'}


def _continuation_html(session):
    if session.get('scene_id') != 'rehab':
        return ''
    evidence = continuation_evidence(session)
    if not evidence['guided'] and not evidence['self_reported']:
        return ''
    rows = ['<tr><td><b>本次进行方式</b><br>'+fmt(evidence['mode_label'])+'</td><td>'
            + ('引导计时按固定节奏提示动作，没有自动判定动作阶段、次数或幅度；'
               '本记录不作为训练所需的评估依据。' if evidence['guided'] else
               '自动测量按动作定义观察；本人另外记录的次数单独列出。')+'</td></tr>']
    if evidence['guided']:
        plan = evidence['prompt_plan'] or {}
        rows.append('<tr><td><b>提示节奏</b><br>'
                    + fmt(f"准备 {plan.get('ready_s')} 秒 / 动作 {plan.get('outbound_s')} 秒 / 回位 {plan.get('return_s')} 秒")
                    + '</td><td>本机固定提示计时，共提示 '+fmt(evidence['prompted_cycles'], 0)
                    + ' 轮。提示轮数只表示界面提示了几次，不表示已完成几次动作。</td></tr>')
        approximate = evidence['approximate_range']
        rows.append('<tr><td><b>近似角度范围</b><br>'
                    + (f"{fmt(approximate['min_deg'])}° ～ {fmt(approximate['max_deg'])}°" if approximate else '— · 无可用角度样本')
                    + '</td><td>'
                    + ('按本次有效帧统计的投影角范围，没有按动作出程 / 回程分期；'
                       '不是一次完整动作的幅度，也不是临床关节活动度。' if approximate else
                       '本次没有取得足够的连续有效帧；缺测不等于 0。')+'</td></tr>')
    if evidence['self_reported']:
        rows.append('<tr><td><b>自己记录的完成次数</b><br>'+fmt(evidence['self_reported'], 0)+' 次</td>'
                    '<td>由本人在运行中点击记录，属于人工报告，不是画面测量；不与自动观察到的次数相加。</td></tr>')
    return ('<h2>本次可以和不能说明什么</h2>'
            '<table><tr><th>记录内容</th><th>怎么理解</th></tr>'+''.join(rows)+'</table>')


def _conditions_html(conditions):
    c = conditions or {}
    view = {'frontal': '正面', 'sagittal': '侧面', 'front': '正面'}.get(c.get('view'), c.get('view'))
    return (f'机位：{fmt(view)} · 机位版本：{fmt(c.get("profile_version"))}'
            f' · 采集模式：{fmt({"single": "单路", "dual": "双摄"}.get(c.get("capture_mode")))}'
            f' · 放置版本：{fmt(c.get("placement_revision"), 0)} · 实际尺寸：{fmt(c.get("actual_size"))}<br>'
            f'模型：<code>{fmt(c.get("model_manifest_id"))}</code> · 骨架：{fmt(c.get("schema_id"))}<br>'
            f'规则：{fmt(c.get("rule_version"))} · 预处理：{fmt(c.get("preprocess_version"))}'
            f' · 测量契约：{fmt(c.get("measurement_contract"))}'
            f' · 时间基准：{fmt(c.get("time_basis"))}<br>来源引用：{fmt(_public_ref(c.get("source_ref")))}')


def _range_html(value):
    if not isinstance(value, dict):
        return '—（未评估或无有效测量）'
    return (f'{fmt(value.get("min_deg"))}° 至 {fmt(value.get("max_deg"))}°'
            f'<br>观察幅度 {fmt(value.get("range_deg"))}°')


def _issues_html(issues):
    rows = []
    for issue in issues or []:
        if not isinstance(issue, dict):
            continue
        rule = issue.get('rule_id')
        label = LABELS.get(rule, rule or '未记录问题名称')
        evidence = '已记录证据' if issue.get('evidence_valid') is True else '证据未确认'
        trace = f' · 第 {fmt(issue.get("repetition_number"), 0)} 次' if 'repetition_number' in issue else ''
        rows.append(f'{fmt(label)}（{evidence}{trace}）')
    return '<br>'.join(rows) or '无已确认问题证据'


def _short_utc(value):
    if not isinstance(value, str):
        return '—'
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc)
        return parsed.strftime('%Y-%m-%d %H:%M')
    except ValueError:
        return '—'


def _compact_body_profile(profile):
    rows = []
    for item in profile.get('items') or []:
        motion = item.get('motion_range') if item.get('status') == 'ASSESSED' else None
        angles = f'{fmt(motion.get("min_deg"))}–{fmt(motion.get("max_deg"))}°' if motion else '—'
        completed = fmt(item.get('completed'), 0)
        status = fmt(STATUS_LABELS.get(item.get('status'), '未记录'))
        if item.get('session_status') == 'INTERRUPTED':
            status += '<br>中断结束'
        cells = (f'{fmt(item.get("exercise_label"))} · {fmt(SIDES.get(item.get("side"), item.get("side")))}'+
                 ('<br>实验性观察' if item.get('experimental') else ''),
                 status,
                 angles, f'{_percent(item.get("valid_ratio"))} / {completed} 次',
                 _short_utc(item.get('end_utc')))
        rows.append('<tr>' + ''.join(f'<td>{cell}</td>' for cell in cells) + '</tr>')
    body = (f'<p>匿名参与者：{fmt(profile.get("participant_id") or profile.get("participant_label"))}'
            f'　已评估 {fmt(profile.get("assessed_count"), 0)} / {fmt(profile.get("total_items"), 0)} 项<br>'
            f'{fmt(SOURCES.get(profile.get("source_kind"), "来源未记录"))} / '
            f'{fmt(CONTEXTS.get(profile.get("usage_context"), "用途未记录"))}</p>'
            '<table cellspacing="0" cellpadding="5"><tr><th width="23%">动作 / 侧别</th>'
            '<th width="12%">状态</th><th width="20%">投影角度范围</th>'
            '<th width="21%">有效观察 / 完整次数</th><th width="24%">最近评估（UTC）</th></tr>'
            + ''.join(rows) + '</table>'
            '<p class="muted">— 表示未测量；本次不可用时不沿用旧结果。完整证据请打开所选评估报告。</p>'+
            _coverage_html(profile))
    style = ("body{font-family:'Microsoft YaHei UI',sans-serif;font-size:12px;color:#203c3d;"
             'margin:4px;padding:4px;line-height:1.3}p{margin:4px 0 8px}.muted{color:#627476}'
             'table{border-collapse:collapse;width:100%;background:white}'
             'td,th{padding:5px;border-bottom:1px solid #dbe7e1;text-align:left;vertical-align:middle}')
    return _document('身体评估汇总', body, style)


def render_body_profile(profile, compact=False):
    """Self-contained HTML using the table/text subset supported by QTextBrowser."""
    if compact:
        return _compact_body_profile(profile)
    rows = []
    for item in profile.get('items') or []:
        status = STATUS_LABELS.get(item.get('status'), '状态未记录')
        motion_range = item.get('motion_range') if item.get('status') == 'ASSESSED' else None
        origin = '由旧记录连续有效样本三点中位数派生' if item.get('motion_range_source') == 'metrics' else '原会话汇总'
        trace = (f'记录 ID：<code>{fmt(item.get("session_id"))}</code><br>'
                 f'开始：{fmt(item.get("start_utc"))}<br>结束：{fmt(item.get("end_utc"))}<br>'
                 f'会话状态：{fmt(SESSION_STATUSES.get(item.get("session_status"), item.get("session_status")))}<br>'
                 f'结束原因：{fmt(item.get("stop_reason"))}')
        counts = (f'完整 {fmt(item.get("completed"), 0)} / 部分 {fmt(item.get("partial"), 0)}'
                  f' / 无效 {fmt(item.get("invalid"), 0)}')
        rows.append('<tr>' + ''.join(f'<td>{value}</td>' for value in (
            f'{fmt(item.get("exercise_label"))}<br>{fmt(SIDES.get(item.get("side"), item.get("side")))}'
            f'<br><span class="muted">{fmt(item.get("primary_metric_label"))}</span>',
            f'{status}<br>{fmt(item.get("reason")) if item.get("reason") else ""}',
            _range_html(motion_range) + (f'<br><span class="muted">{origin}</span>' if motion_range else ''),
            f'{_percent(item.get("valid_ratio"))}<br>{counts}',
            _issues_html(item.get('issues')), trace, _conditions_html(item.get('conditions')))) + '</tr>')
    body = (f'<p class="tag">居家康复助手 · 个人身体评估汇总</p><h1>身体评估汇总</h1>'
            f'<p>匿名参与者：{fmt(profile.get("participant_id") or profile.get("participant_label"))}</p>'
            f'<p>{fmt(SOURCES.get(profile.get("source_kind"), "来源未记录"))} / '
            f'{fmt(CONTEXTS.get(profile.get("usage_context"), "用途未记录"))} · '
            f'已评估 {fmt(profile.get("assessed_count"), 0)} / {fmt(profile.get("total_items"), 0)} 项</p>'
            '<p class="note">每项展示最近一次已结束评估；本次不可用时不沿用旧成功结果。'
            '— 表示缺失，不代表 0。仅描述本次观察，不能推断疾病、肌力或真实负重，不能作为自动训练处方。</p>'
            '<table><tr><th>动作与侧别</th><th>评估状态</th><th>二维投影角度</th>'
            '<th>有效观察 / 次数</th><th>可见问题</th><th>原始评估记录</th><th>测量条件</th></tr>'
            + ''.join(rows) + '</table>'
            f'<p class="muted">{fmt(COMPARISON_NOTE)}</p>'+_coverage_html(profile))
    return _document('身体评估汇总', body)


def _coverage_html(profile):
    rows = ''.join(f'<p><b>{fmt(item.get("label"))}</b><br>{fmt(item.get("reason"))}</p>'
                   for item in profile.get('unsupported_coverage') or [])
    return ('<h2>当前测量边界</h2><p>不要求完成全部项目；按已确认的适用范围选择。腕、踝和手指为实验性二维观察，'
            '需清楚可见且运动处于成像平面。标记“已评估”仅表示保存了观察值，不表示临床验证通过。</p>'
            '<h3>暂不输出关节角及原因</h3>'+rows) if rows else ''


def _assessment_reference(session):
    if 'assessment_reference' in session:
        return session['assessment_reference']
    return ((session.get('config_snapshot') or {}).get('plan') or {}).get('assessment_reference')


def _training_html(session):
    if session_value(session, 'submode') != 'training':
        return ''
    reference = _assessment_reference(session)
    title = '<h2>训练所用的评估参考</h2>'
    if not isinstance(reference, dict) or not reference:
        return title + '<p>未记录评估参考（旧报告可无此字段）。训练目标以当次人工确认的计划为准。</p>'
    status = reference.get('status')
    same_scope = all(reference.get(key) == session_value(session, key) for key in
                     ('participant_id', 'exercise_id', 'side'))
    same_scope = same_scope and all(reference.get(key) == session.get(key) for key in ('source_kind', 'usage_context'))
    usable = status == 'ASSESSED' and same_scope
    explanation = '原评估的观察结果；训练目标仍需人工确认。' if usable else '引用不可用于当前训练：未评估、本次不可用或参与者/动作/侧别/来源情境不一致。'
    return (title + f'<p>{fmt(STATUS_LABELS.get(status, "状态未记录"))} · {fmt(explanation)}</p>'
            f'<p>匿名参与者：{fmt(reference.get("participant_id"))} · '
            f'{fmt(reference.get("exercise_label") or reference.get("exercise_id"))} / '
            f'{fmt(SIDES.get(reference.get("side"), reference.get("side")))} · '
            f'{fmt(SOURCES.get(reference.get("source_kind"), "来源未记录"))} / '
            f'{fmt(CONTEXTS.get(reference.get("usage_context"), "用途未记录"))}</p>'
            f'<p>评估记录 ID：<code>{fmt(reference.get("session_id"))}</code><br>'
            f'评估开始：{fmt(reference.get("start_utc"))} · 评估结束：{fmt(reference.get("end_utc"))}<br>'
            f'原评估状态：{fmt(SESSION_STATUSES.get(reference.get("session_status"), reference.get("session_status")))} · '
            f'结束原因：{fmt(reference.get("stop_reason"))}<br>'
            f'参考投影角度：{_range_html(reference.get("motion_range") if usable else None)} · '
            f'有效观察：{_percent(reference.get("valid_ratio"))}</p>'
            f'<p>{_conditions_html(reference.get("conditions"))}</p>'
            f'<p class="muted">{fmt(COMPARISON_NOTE)}本报告不计算跨条件改善幅度。</p>')


def _rep_angle(rep, spec):
    key = spec.get('rep_value_key')
    if key in rep:
        return rep[key]
    legacy = {'raise_deg': 'max_raise_projection_deg', 'knee_flexion_deg': 'min_knee_flexion_projection_deg'}
    return rep.get(legacy.get(spec.get('metric')))


def _timing_html(session):
    reps = session.get('repetitions') or []
    if not any(r.get('movement_timing') for r in reps):
        return '<h2>动作时间</h2><p>本记录没有逐阶段时间数据；不从旧总时长补算。</p>'
    rows = []
    for rep in reps:
        timing = rep.get('movement_timing') or {}
        values = [fmt(rep.get('number'), 0)]
        for key in TIMING_METRICS:
            metric = timing.get(key) or {}
            values.append(fmt(metric.get('value')) if metric.get('valid') else
                          '—（'+fmt(TIMING_REASONS.get(metric.get('reason'), metric.get('reason') or '未记录'))+'）')
        goals = timing.get('goals') or {}
        values.append('<br>'.join(label+'：'+fmt(LABELS.get(goals.get(key), '未记录'))
                                 for key, label in (('outbound', '出程'), ('return', '回程'), ('hold', '保持'))))
        rows.append('<tr>'+''.join('<td>'+v+'</td>' for v in values)+'</tr>')
    plan = ((session.get('config_snapshot') or {}).get('plan') or {})
    from .movement_timing import timing_for_plan
    try:
        arrangement = timing_for_plan(plan)
    except (ValueError, KeyError):
        arrangement = {}
    goal_text = '；'.join(label+' '+fmt(arrangement.get(key))+' 秒' for key, label in (
        ('outbound_min_s', '出程最短'), ('outbound_max_s', '出程最长'), ('return_min_s', '回程最短'),
        ('return_max_s', '回程最长'), ('hold_min_s', '连续保持至少')))
    return ('<h2>动作时间</h2><p>人工安排：'+goal_text+'。— 表示未设置。</p>'
            '<p class="muted">关节出程 / 峰区停留 / 回程为完整往返结束后的分期统计：连续三点中位数在中心帧时刻、'
            '距本次峰值 3° 内的单段区域定义峰区。坐站按确认站位与回坐边界分期，起立计数仍在站位确认时完成。'
            '连续保持为人工目标角度范围（坐站为校准站位）内最长一段连续观察；分段不累加，缺测不补计。'
            '峰区停留不表示平衡或支撑稳定性，时间目标与完成次数分别评价。</p>'
            '<table><tr><th>序号</th><th>出程 s</th><th>峰区 / 站位停留 s</th><th>回程 s</th><th>最长连续保持 s</th>'
            '<th>时间目标</th></tr>'+''.join(rows)+'</table>')


def render_result_summary(s, *, document=True):
    """Patient-facing explanations of saved evidence, never a diagnosis or ROM norm."""
    eid = session_value(s, 'exercise_id')
    if s.get('scene_id') != 'rehab' or eid not in EXERCISE_IDS:
        return _document('本次结果', '<p>请查看详细数据。</p>') if document else ''
    spec = exercise_spec(eid)
    summary = s.get('summary') or {}
    motion, origin = session_motion_range(s)
    metric_label = summary.get('primary_metric_label') or spec['metric_label']
    rows = []

    def row(term, value, explanation):
        rows.append('<tr><td><b>'+fmt(term)+'</b><br>'+value+'</td><td>'+fmt(explanation)+'</td></tr>')

    evidence = continuation_evidence(s)
    if evidence['guided']:
        row('任务完成', '— · 本次为引导计时',
            '引导计时不自动判定动作次数。下面的自报次数是本人记录，本记录不作为训练所需的评估依据。')
    else:
        row('任务完成', fmt(summary.get('completed'), 0)+' 次',
            '到达已记录的站位计一次，回坐后才可再计次。次数不代表起立能力评级。' if eid == 'sit_to_stand' else
            '观察到动作出程并回到起点才计一次。完成次数与活动幅度、动作质量分别评价。')
    row('部分尝试 / 中断或无法评价', fmt(summary.get('partial'), 0)+' / '+fmt(summary.get('invalid'), 0),
        '未完成往返和因遮挡、断流等无法判断的尝试单独保留；不能一概解释为做得差。')
    if motion:
        value = f'{fmt(motion["min_deg"])}° ～ {fmt(motion["max_deg"])}°<br>可观察幅度 {fmt(motion["range_deg"])}°'
        meaning = '前两个数是本次有效观察中的最小、最大投影角；幅度是两者之差，不是临床关节活动度（ROM）。'
        if spec['directional_calibration']:
            meaning += ' 角度相对本次记录的舒适起点，方向来自人工试动作。'
        if origin == 'metrics':
            meaning += ' 这项范围由旧记录的连续有效样本派生，不是旧会话当时生成的汇总。'
    else:
        value = '— · 暂无可解释的角度范围'
        meaning = '没有足够有效证据，或该旧记录与当前指标不匹配；不是活动幅度为零。请检查机位和遮挡后重测。'
    row(metric_label, value, meaning)
    row('有效观察比例', _percent(summary.get('valid_ratio')),
        '表示观察跨度中有效可见时间所占比例，不是识别准确率，也不是动作合格率；各项指标仍有独立有效性。')
    row('有效观察时间', fmt(summary.get('valid_s'))+' 秒 / 跨度 '+fmt(summary.get('observed_span_s'))+' 秒',
        '仅统计有证据的可见时段；缺测、暂停和断流不补算成连续活动。')
    reps = s.get('repetitions') or []
    targets = Counter(r.get('target_status') for r in reps)
    target_text = '；'.join(f'{LABELS[k]} {targets[k]} 次' for k in ('MET', 'NOT_MET', 'NOT_SET', 'UNASSESSABLE') if targets[k])
    row('个人幅度目标', fmt(target_text or '尚无可评价的动作记录'),
        '只比较人工设置的个人目标，不与所谓正常值比较。未设置目标不是失败；未达目标也不是疾病判断。')
    for key, term in (('outbound_s', '出程时间'), ('endpoint_dwell_s', '峰区 / 站位停留时间'),
                      ('return_s', '回程时间'), ('target_hold_s', '最长连续保持时间')):
        values = []
        for rep in reps:
            metric = (rep.get('movement_timing') or {}).get(key) or {}
            value = finite_number(metric.get('value'))
            if metric.get('valid') is True and value is not None and value >= 0:
                values.append(value)
        row(term, (fmt(median(values))+' 秒（'+str(len(values))+' 次记录的中位数）') if values else '— · 尚无有效时间记录',
            {'outbound_s': '从起始方向移动到本次峰区（坐站为确认站位）的分期时间。',
             'endpoint_dwell_s': '峰区是本次动作峰值附近的一段区间；停留时间不代表平衡或支撑稳定性。',
             'return_s': '从峰区或站位返回起点的分期时间；回程没看完整时不补算。',
             'target_hold_s': '每次在人工目标范围内最长的一段连续保持；中断片段不相加，没有保持目标时不评价。'}[key])
    issues = [issue for rep in reps for issue in rep.get('issues') or [] if issue.get('evidence_valid') is True]
    issue_names = list(dict.fromkeys(LABELS.get(i.get('rule_id'), '其他已记录的可见规则事件') for i in issues))
    row('可见动作表现', fmt('；'.join(issue_names) if issue_names else '未记录到有有效证据的规则问题'),
        '只说明画面中被规则记录的表现。没有记录到问题，不等于动作完全正常，也不能判断肌力或病因。')
    if evidence['guided']:
        approximate = evidence['approximate_range']
        row('近似角度范围', (f"{fmt(approximate['min_deg'])}° ～ {fmt(approximate['max_deg'])}°"
                       if approximate else '— · 无可用角度样本'),
            '按有效帧统计，没有按动作分期；不是一次动作的幅度，也不是临床活动度。' if approximate else
            '本次没有取得足够连续有效帧；缺测不等于 0。')
    if evidence['self_reported']:
        row('自己记录的完成次数', fmt(evidence['self_reported'], 0)+' 次',
            '本人在运行中点击记录的人工报告，不是画面测量，也不与自动次数相加。')
    view = {'frontal': '正面', 'sagittal': '侧面'}.get(session_conditions(s).get('view'), '机位未记录')
    body = ('<h1>本次结果解读</h1><p>'+fmt(spec['label'])+' · '+fmt(SIDES.get(session_value(s, 'side'), '测试侧未记录'))+
            ' · '+fmt(view)+' · '+fmt(MODES.get(session_value(s, 'submode'), '模式未记录'))+'</p>'
            '<p>'+fmt(SOURCES.get(s.get('source_kind'), '来源未记录'))+' / '+fmt(CONTEXTS.get(s.get('usage_context'), '用途未记录'))+
            ' · '+fmt(s.get('start_utc'))+'</p>'
            '<p class="note">这是摄像头观察报告，不是诊断或临床活动度鉴定。— 表示缺少有效证据或不适用，不能读成 0。</p>'
            '<table><tr><th>康复指标与测试数据</th><th>这些数字怎么理解</th></tr>'+''.join(rows)+'</table>')
    body += _continuation_html(s)
    if eid in ('neck_flexion', 'neck_extension'):
        body += ('<h2>头颈测量说明</h2><p>本项是头部相对躯干的二维投影变化：同侧眼—耳线作为头部参考，'
                 '肩—髋线作为躯干参考。髋点用于区别头部运动与身体前倾，不是在评估髋关节；'
                 '不能分离颈椎各节段，也不是三维颈椎 ROM。</p>')
    if s.get('dual_camera'):
        body += '<p>双摄由本动作的主机位给出上述数据，辅助机位独立观察；不是两路角度平均，也不是三维重建。</p>'
        if s['dual_camera'].get('validity_policy') == 'primary-with-auxiliary-identity-1':
            body += ('<p>辅助指标缺测只表示那一项无法评价，不等于本次动作失败。两路均能确认人员归属、'
                     '主机位测量有效时，主结果仍可记录；身份不明或画面中断时不会继续计入。</p>')
        else:
            body += '<p>本记录沿用保存时的双摄有效性规则，未按新版规则重新计算。</p>'
    body += '<h2>下一步</h2><p>'
    if evidence['guided']:
        body += ('本次活动已保存。想要可比较的测量记录时，可在光线和取景较好时重做一次自动测量评估；'
                 '引导计时记录只保存在历史中。')
    else:
        body += '可继续评估其他动作，在“身体档案”汇总。'
    body += ('进入训练前，需选择可用评估记录并人工确认个人计划；'
             '本报告不会自动开具处方。复测请尽量保持相同机位、测试侧和测量条件，不凭一次角度变化判断康复改善。'
             '疼痛、头晕或不适时停止，并向康复专业人员反馈。</p>')
    return _document('本次结果解读', body) if document else body


def render_report(s):
    summary = s.get('summary') or {}
    source = SOURCES.get(s.get('source_kind'), '来源未记录')
    usage = CONTEXTS.get(s.get('usage_context'), '用途未记录')
    scene = s.get('scene_id')
    exercise_id = session_value(s, 'exercise_id')
    spec = exercise_spec(exercise_id) if exercise_id in EXERCISE_IDS else {}
    name = spec.get('label', '康复任务') if scene == 'rehab' else SCENES.get(scene, '任务')
    detail = ''
    if scene == 'rehab':
        rows = []
        for rep in s.get('repetitions') or []:
            number = fmt(rep.get('number'), 0)+(f" · 第 {fmt(rep['set_number'], 0)} 组" if rep.get('set_number') else '')
            values = (number, fmt(LABELS.get(rep.get('completion_status'), rep.get('completion_status'))),
                      fmt(LABELS.get(rep.get('target_status'), rep.get('target_status'))), fmt(_rep_angle(rep, spec)),
                      fmt(rep.get('min_angle_deg')), fmt(rep.get('peak_angle_deg')), fmt(rep.get('range_deg')),
                      fmt(rep.get('duration_s')), fmt(LABELS.get(rep.get('observation_status'), rep.get('observation_status'))),
                      _issues_html(rep.get('issues')))
            rows.append('<tr>' + ''.join(f'<td>{value}</td>' for value in values) + '</tr>')
        motion_range, evidence_source = session_motion_range(s)
        evidence_note = '由旧记录连续有效样本三点中位数派生' if evidence_source == 'metrics' else '原会话汇总'
        metric_label = summary.get('primary_metric_label') or spec.get('metric_label', '二维投影角')
        detail += (f'<h2>本次投影角度</h2><p>{fmt(metric_label)}：{_range_html(motion_range)}'
                   + (f'（{evidence_note}）' if motion_range else '') + '</p>'
                   '<h2>每次动作</h2><p class="muted">代表角度按动作定义取抬举峰值或最小屈曲角；'
                   '最小、最大及幅度列保留本次可观察范围。— 表示无有效证据或不适用。</p>'
                   '<table><tr><th>序号</th><th>完成情况</th><th>个人目标</th><th>代表角度 °</th>'
                   '<th>最小 °</th><th>最大 °</th><th>幅度 °</th><th>时长 s</th><th>观察情况</th><th>可见问题</th></tr>'
                   + (''.join(rows) or '<tr><td colspan="10">没有已记录的动作重复。</td></tr>') + '</table>')
        detail += _continuation_html(s)
        detail += _saved_plan_html(s)
        detail += _timing_html(s)
        detail += _dual_camera_html(s)
        detail += _training_html(s)
        detail += _training_execution_html(s)
        if s.get('measurement_limitations'):
            detail += '<h2>本动作的测量限制</h2><p>'+fmt(s['measurement_limitations'])+'</p>'
        baseline = ((s.get('config_snapshot') or {}).get('plan') or {}).get('joint_baseline') or {}
        if baseline:
            detail += ('<h2>舒适起点记录</h2><p>起点原始投影角 '+fmt(baseline.get('rest_value'))+
                       '°；记录时间 '+fmt(baseline.get('recorded_at'))+'。'+
                       ('本动作报告相对该起点、按人工确认方向的角度变化；不是临床绝对ROM。' if spec.get('directional_calibration') else
                        '起点仅用于动作分期，不是正常值或训练目标。')+'</p>')
    elif scene == 'activity':
        labels = {'SEATED': '可见坐位', 'STANDING': '可见站位', 'WALKING': '可见步行', 'VISIBLE_MOVING': '可见移动'}
        detail = '<h2>有效可见时长</h2><table><tr><th>状态</th><th>有效秒数</th></tr>'
        detail += ''.join(f'<tr><td>{fmt(labels.get(k, k))}</td><td>{fmt(v)} 秒</td></tr>' for k, v in (summary.get('totals') or {}).items()) + '</table>'
        detail += '<h2>活动任务</h2><table><tr><th>任务</th><th>状态</th><th>视觉核实</th><th>另行自报</th></tr>'
        for task in s.get('tasks') or []:
            status = {'ACTIVE': '进行中', 'COMPLETED': '已完成', 'INTERRUPTED': '已中断'}.get(task.get('status'), '待确认')
            detail += (f'<tr><td>{fmt({"stand": "站立", "walk": "步行"}.get(task.get("kind"), task.get("kind")))}</td>'
                       f'<td>{status}</td><td>{fmt(task.get("visible_s"))} / {fmt(task.get("target_s"))} 秒</td>'
                       f'<td>{"已自报" if task.get("self_reported") else "无"}</td></tr>')
        detail += '</table>'
        if summary.get('demo_thresholds'):
            detail += '<p class="note">本次使用演示阈值，实际时间正常流逝。</p>'
    elif scene in ('bedroom_demo', 'safety_demo'):
        detail += '<h2>观察记录</h2><p>' + fmt(summary.get('message', '暂无有效观察')) + '</p>'
        if scene == 'bedroom_demo':
            detail += '<p>' + ('已人工确认真实床区；仍为受控演示。' if summary.get('real_bed_confirmed') else '本次为模拟区域演示。') + '</p>'
        detail += '<h2>本次建立的事件</h2><ul>'
        detail += ''.join('<li>' + fmt(e.get('message', '疑似事件')) + f'（触发时间 {fmt(e.get("event_emitted_time"))} 秒）</li>' for e in s.get('events') or [])
        detail += '</ul><p>事件的最新处理状态请在应用的事件页面查看；报告保留当次建立记录。</p>'
    headline = (f'<table><tr><th>完整次数</th><th>部分尝试</th><th>中断 / 无法评价</th><th>有效观察</th></tr>'
                f'<tr><td>{fmt(summary.get("completed"), 0)}</td><td>{fmt(summary.get("partial"), 0)}</td>'
                f'<td>{fmt(summary.get("invalid"), 0)}</td><td>{_percent(summary.get("valid_ratio"))}</td></tr></table>') if scene == 'rehab' else f'<p>有效观察比例：{_percent(summary.get("valid_ratio"))}</p>'
    body = (f'<p class="tag">居家康复助手 · 本地任务报告</p><h1>{fmt(name)}记录</h1>'
            f'<p>模式：{fmt(MODES.get(session_value(s, "submode"), "模式未记录"))} · '
            f'匿名参与者：{fmt(session_value(s, "participant_id"))}</p>'
            f'<p>{fmt(source)} / {fmt(usage)} · 开始 {fmt(s.get("start_utc"))} · 结束 {fmt(s.get("end_utc"))}</p>'
            '<p class="note">仅报告所选场景的可见时段。二维投影测量；缺测不是动作差，个人目标不是通用医学标准。'
            '不据此推断疾病、肌力或真实负重。</p>'
            + _participant_html(s.get('participant_snapshot'))
            + render_result_summary(s, document=False)
            + headline + f'<p>有效观察 {fmt(summary.get("valid_s"))} 秒 / 观察跨度 {fmt(summary.get("observed_span_s"))} 秒。'
            f'会话状态：{fmt(SESSION_STATUSES.get(s.get("status"), s.get("status")))} · '
            f'结束原因：{fmt(s.get("stop_reason"))}。</p>' + detail
            + f'<h2>测量条件</h2><p>测试侧：{fmt(SIDES.get(session_value(s, "side"), session_value(s, "side")))}</p>'
            f'<p>{_conditions_html(session_conditions(s))}</p>'
            f'<p class="muted">记录 ID：<code>{fmt(s.get("id"))}</code>。{fmt(COMPARISON_NOTE)}</p>')
    return _document('任务报告', body)


def _dual_camera_html(session):
    dual = session.get('dual_camera')
    if not isinstance(dual, dict):
        return ''
    from .dual_camera import VIEWS
    summary = dual.get('summary') or {}

    def milliseconds(value):
        number = finite_number(value)
        return fmt(number*1000 if number is not None else None)

    result = ('<h2>双摄观察</h2><p>动作测量使用'+fmt(VIEWS.get(dual.get('primary_view')))+'机位；'
              +fmt(VIEWS.get(dual.get('secondary_view')))+'机位提供独立辅助投影。'
              '人工确认两路为同一人，不用跨画面的坐标补点或自动匹配身份。</p>'
              '<p class="muted">按单调接收时间配对，每帧最多使用一次；未验证曝光同步，未作空间标定或三维重建。'
              '接收差筛选上限 '+milliseconds(dual.get('max_receive_delta_s'))+' 毫秒；'
              '本次配对观察 '+fmt(summary.get('paired_observations'), 0)+' 帧，其中两路指标可测 '
              +fmt(summary.get('both_views_valid'), 0)+' 帧。接收差中位数 '
              +milliseconds(summary.get('median_receive_delta_s'))+' 毫秒，最大 '
              +milliseconds(summary.get('max_receive_delta_s'))+' 毫秒。缺测不补计，辅助指标没有自动临床阈值。</p>'
              '<table><tr><th>机位与用途</th><th>实际图幅</th><th>报告 / 接收帧率</th><th>来源引用</th></tr>')
    for view in ('frontal', 'sagittal'):
        stream = (dual.get('streams') or {}).get(view) or {}
        actual = stream.get('actual_capture') or {}
        result += ('<tr><td>'+fmt(VIEWS[view])+(' · 动作测量' if view == dual.get('primary_view') else ' · 辅助观察')
                   +'</td><td>'+fmt(actual.get('size'))+'</td><td>'+fmt(actual.get('reported_fps'))+' / '
                   +fmt(actual.get('received_fps'))+'</td><td>'+fmt(_public_ref(stream.get('source_ref')))+'</td></tr>')
    result += '</table>'
    failure = dual.get('input_failure')
    if dual.get('validity_policy') == 'primary-with-auxiliary-identity-1':
        result += ('<p>有效性规则：主测量与辅助指标分别判定；两路人员归属明确且主路必要点满足原门槛时，'
                   '辅助几何缺测不否定主测量。主测量实际纳入 '+fmt(summary.get('primary_used_observations'), 0)
                   +' 帧，其中辅助整体缺测 '+fmt(summary.get('main_only_observations'), 0)
                   +' 帧。单项辅助缺测表示本项无法评价，不表示动作不合格。身份不明和断流仍停用；'
                   '此规则与旧版要求两路均有效的记录不同。</p>')
    else:
        result += '<p>历史有效性规则：沿用保存时的双摄门槛；未按新版逐项规则重新计算。</p>'
    if failure:
        reasons = {'input_error': '输入失效', 'dual_view_inference_error': '姿态推理失败',
                   'stream_stale': '新配对画面超时', 'connect_timeout': '启动超时'}
        result += ('<p>输入中断：'+fmt(reasons.get(failure.get('category'), failure.get('category')))
                   +'；机位：'+fmt(VIEWS.get(failure.get('view'), '未定位到单一路'))+'。</p>')
    diagnostics = dual.get('capture_pairing_diagnostics')
    if diagnostics:
        result += ('<p class="muted">当前任务的配对器发出 '+fmt(diagnostics.get('emitted_pairs'), 0)
                   +' 对画面。此数值统计进入应用的配对结果，可能因推理队列丢帧而多于上方的姿态观察数；不代表相机曝光总数。</p>')
    result += '<h3>辅助指标（二维投影）</h3><table><tr><th>指标</th><th>有效帧 / 配对观察</th><th>中位数 °</th><th>最小 °</th><th>最大 °</th></tr>'
    for key, definition in (dual.get('auxiliary_metrics') or {}).items():
        values = (summary.get('auxiliary_metrics') or {}).get(key) or {}
        result += ('<tr><td>'+fmt(definition.get('label'))+'</td><td>'+fmt(values.get('valid_samples'), 0)+' / '
                   +fmt(values.get('total_samples'), 0)+'</td>'+''.join('<td>'+fmt(values.get(k))+'</td>' for k in ('median', 'min', 'max'))+'</tr>')
    result += '</table><ul>'
    for definition in (dual.get('auxiliary_metrics') or {}).values():
        result += '<li>'+fmt(definition.get('label'))+'：'+fmt(definition.get('definition'))+'。</li>'
    return result+'</ul>'


def _participant_html(profile):
    if not profile:
        return ''
    from .participants import REPORTERS, SIDES, SUPPORT, TEXT_FIELDS
    rows = [('称呼', profile.get('display_name')), ('出生年份', profile.get('birth_year')),
            ('关注侧别', SIDES.get(profile.get('affected_side'))),
            ('日常陪同', SUPPORT.get(profile.get('support')))]
    rows.extend((label, profile.get(key)) for key, label in TEXT_FIELDS.items())
    return ('<h2>本次个人信息</h2><p>手工填写 · '+fmt(REPORTERS.get(profile.get('reported_by')))
            +' · 开始任务时的档案版本 '+fmt(profile.get('revision'), 0)
            +'。不代表专业审核或摄像头测量，不自动调整训练目标。</p><table>'
            + ''.join(f'<tr><th>{fmt(label)}</th><td>{fmt(value)}</td></tr>' for label, value in rows if value not in (None, ''))
            + '</table>')


def _saved_plan_html(session):
    if session_value(session, 'submode') != 'training':
        return ''
    reference = session.get('saved_plan_reference') or (((session.get('config_snapshot') or {}).get('plan') or {}).get('saved_plan_reference'))
    if not isinstance(reference, dict) or not reference.get('id'):
        return ''
    result = ('<h2>来源计划</h2><p>'+fmt(reference.get('name') or '名称未随导出提供')+
              ' · 版本 '+fmt(reference.get('revision'), 0)+' · 项目 '+fmt(reference.get('entry_key'))+
              '</p><p class="muted">保留开始时的计划版本；之后修改或归档计划不会改写本次报告。</p>')
    changes = reference.get('session_overrides') or {}
    automatic = reference.get('automatic')
    if reference.get('record_origin') == 'assessment_rules' and isinstance(automatic, dict):
        result += '<h3>根据评估自动安排</h3><p>规则版本：'+fmt(automatic.get('rule_version'))+'</p>'
        result += '<p>一般基础活动建议；动作选择参考官方公开指导，剂量与投影角适配是软件工程规则，不是疾病或术后处方。</p>'
        entry = next((i for i in automatic.get('entries', []) if i.get('key') == reference.get('entry_key')), {})
        source = entry.get('source') or {}
        result += '<p>'+fmt(entry.get('rationale'))+'</p><p>依据评估：'+fmt(entry.get('assessment_id'))+'</p>'
        result += '<p>证据类型：'+fmt('官方动作条目匹配' if entry.get('evidence_kind') == 'matched' else
                                      '本人评估适配；公开指南仅作为从少量开始的一般原则')+'</p>'
        result += '<p>来源：'+fmt(source.get('title'))+' · '+fmt(source.get('section'))+'<br>'+fmt(source.get('url'))+'</p>'
        result += '<p>适用性确认时间：'+fmt(automatic.get('confirmed_utc'))+'；本人报告，不由摄像头推断。</p>'
    labels = {'target_reps': '每组次数', 'target_sets': '组数', 'rest_between_sets_s': '组间休息秒数',
              'target_angle_deg': '角度目标', 'allowed_elbow_flexion_deg': '可见屈肘上限',
              'allowed_trunk_tilt_deg': '躯干侧倾上限', 'lowering_tempo_min_s': '下降最短秒数',
              'lowering_tempo_max_s': '下降最长秒数', 'use_of_hands': '扶物安排',
              'needs_companion': '陪同要求', 'sound_enabled': '提示音'}
    if changes:
        result += '<p>本次人工确认时修改了以下设置，实际执行以本次设置为准：</p><table><tr><th>设置</th><th>保存计划</th><th>本次使用</th></tr>'
        result += ''.join('<tr><td>'+fmt(labels.get(k, k))+'</td><td>'+fmt(v.get('saved'))+
                          '</td><td>'+fmt(v.get('used'))+'</td></tr>' for k, v in changes.items())+'</table>'
    return result


def _training_execution_html(session):
    if session_value(session, 'submode') != 'training':
        return ''
    from .training import FEEDBACK_REASONS
    summary = session.get('summary') or {}
    training = summary.get('training') or {}
    html = '<h2>训练执行</h2>'
    quality = summary.get('observed_quality')
    if isinstance(quality, dict):
        html += ('<p>已观察目标达成 '+fmt(quality.get('observed_goals_met'), 0)+' 次；需调整 '+
                 fmt(quality.get('needs_adjustment'), 0)+' 次；未能核实 '+fmt(quality.get('unassessable'), 0)+
                 ' 次。仅限已设置目标和可见指标，不是整体动作合格率；没有设置目标不算动作差。</p>')
    if not training:
        html += '<p>此记录未保存组间执行过程。</p>'
    else:
        html += (f'<p>计划 {fmt(training.get("target_reps"), 0)} 次 × {fmt(training.get("target_sets"), 0)} 组；'
                 f'完成 {fmt(summary.get("completed_sets"), 0)} 组。完整动作与角度目标达成分别记录。</p>'
                 f'<p>组间休息 {fmt(training.get("rest_s"))} 秒；暂停 {fmt(training.get("paused_s"))} 秒。'
                 '这些时间按输入时钟记录，不计入训练的有效观察比例。暂停不是停止摄像头采集。</p>'
                 '<table><tr><th>组</th><th>状态</th><th>完成次数</th><th>部分尝试</th><th>中断 / 无法评价</th><th>组后休息 s</th></tr>')
        for group in training.get('sets', []):
            values = [fmt(group.get('number'), 0), fmt({'ACTIVE': '进行中', 'COMPLETE': '次数已完成', 'INTERRUPTED': '提前结束'}.get(group.get('status'), '未记录')),
                      fmt(group.get('completed'), 0), fmt(group.get('partial'), 0), fmt(group.get('interrupted'), 0), fmt(group.get('rest_s'))]
            html += '<tr>'+''.join('<td>'+v+'</td>' for v in values)+'</tr>'
        html += '</table>'
    html += '<h2>本次训练感受</h2>'
    feedback = session.get('training_feedback')
    if not feedback:
        return html + ('<p>导出未包含个人填写信息。</p>' if session.get('manual_information_omitted') else '<p>尚未填写，可在本地报告中补充。</p>')
    return (html+f'<p>本人自述（可由照护者代录），不是摄像头判断。记录时间：{fmt(feedback.get("recorded_utc"))}。</p>'
            f'<p>疼痛自评：{fmt(feedback.get("pain"), 0)} / 10；疲劳自评：{fmt(feedback.get("fatigue"), 0)} / 10。'
            '— 表示未填写，不代表 0。</p>'
            f'<p>结束原因：{fmt(FEEDBACK_REASONS.get(feedback.get("reason"), "未填写"))}</p>'
            f'<p>{fmt(feedback.get("notes"))}</p>')


# Nested plans/calibrations/references can carry the same sensitive metadata as
# the top-level session. Redact recursively, not just the device_ref at the root.
PRIVATE_KEYS = {'device_ref', 'device_path', 'path', 'file_path', 'video_path', 'model_path',
                'participant_name', 'person_name', 'patient_name', 'full_name', 'display_name',
                'name', 'operator', 'annotator', 'email', 'phone', 'address', 'serial_number',
                'participant_snapshot', 'training_feedback'}


def _export_snapshot(snapshot):
    def redact(value):
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                if str(key).lower() in PRIVATE_KEYS:
                    continue
                if key == 'participant_id':
                    result[key] = anonymous_participant(item)
                elif key == 'participant_label':
                    result[key] = anonymous_participant(value.get('participant_id'))
                elif key == 'source_ref':
                    result[key] = _public_ref(item)
                else:
                    result[key] = redact(item)
            return result
        if isinstance(value, (list, tuple)):
            return [redact(item) for item in value]
        return clean_json(value)
    result = redact(snapshot)
    if snapshot.get('participant_snapshot') or snapshot.get('training_feedback'):
        result['manual_information_omitted'] = True
    return result


def _empty_export_directory(directory):
    out = Path(directory)
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise ValueError('导出目录须为空，避免残留此前授权的骨架或视频')
    out.mkdir(parents=True, exist_ok=True)
    return out


def _csv_value(value):
    # Spreadsheet formula injection applies to untrusted labels as well as HTML.
    if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
        return "'" + value
    return clean_json(value)


def export_session(snapshot, directory):
    s = _export_snapshot(Storage.authorized_snapshot(snapshot))
    out = _empty_export_directory(directory)
    metadata = {k: v for k, v in s.items() if k not in ('metrics', 'poses', 'events', 'repetitions')}
    (out/'session.json').write_text(dumps(metadata, indent=2), encoding='utf-8')
    (out/'repetitions.json').write_text(dumps(s.get('repetitions') or [], indent=2), encoding='utf-8')
    for key, filename in (('metrics', 'metrics.jsonl'), ('events', 'events.jsonl')):
        (out/filename).write_text(''.join(dumps(row)+'\n' for row in s.get(key) or []), encoding='utf-8')
    if (s.get('config_snapshot') or {}).get('poses_consent'):
        (out/'poses.jsonl').write_text(''.join(dumps(row)+'\n' for row in s.get('poses') or []), encoding='utf-8')
    (out/'report.html').write_text(render_report(s), encoding='utf-8')
    if isinstance(s.get('dual_camera'), dict):
        _export_dual_camera_csv(s, out/'dual-camera.csv')
    with (out/'repetitions.csv').open('w', newline='', encoding='utf-8-sig') as f:
        columns = ['number', 'completion_status', 'target_status', 'observation_status', 'duration_s',
                   'peak_angle_deg', 'min_angle_deg', 'range_deg', 'max_raise_projection_deg',
                   'min_knee_flexion_projection_deg', 'rise_time_s', 'lowering_time_s',
                   'exercise_id', 'side', 'submode', 'participant_id', 'source_kind', 'usage_context',
                   'primary_metric', 'primary_metric_label', 'assessment_session_id', 'issues',
                   'movement_timing_version', 'timing_cycle_complete', 'timing_partial_observation']
        columns += [key+suffix for key in TIMING_METRICS for suffix in ('', '_valid', '_reason')]
        columns += ['timing_goal_'+key for key in ('outbound', 'return', 'hold')]
        columns += ['timing_arrangement']
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        exercise_id = session_value(s, 'exercise_id')
        spec = exercise_spec(exercise_id) if exercise_id in EXERCISE_IDS else {}
        reference = _assessment_reference(s) or {}
        for rep in s.get('repetitions') or []:
            row = dict(rep)
            timing = rep.get('movement_timing') or {}
            row.update(movement_timing_version=timing.get('version'), timing_cycle_complete=timing.get('cycle_complete'),
                       timing_partial_observation=timing.get('partial_observation'), timing_arrangement=dumps(timing.get('arrangement')))
            for key in TIMING_METRICS:
                metric = timing.get(key) or {}
                row.update({key: metric.get('value') if metric.get('valid') else None,
                            key+'_valid': metric.get('valid'), key+'_reason': metric.get('reason')})
            row.update({'timing_goal_'+key: (timing.get('goals') or {}).get(key) for key in ('outbound', 'return', 'hold')})
            row.update({key: session_value(s, key) for key in ('exercise_id', 'side', 'submode', 'participant_id')})
            row.update({key: s.get(key) for key in ('source_kind', 'usage_context')})
            row.update(primary_metric=(s.get('summary') or {}).get('primary_metric') or spec.get('metric'),
                       primary_metric_label=(s.get('summary') or {}).get('primary_metric_label') or spec.get('metric_label'),
                       assessment_session_id=reference.get('session_id') if isinstance(reference, dict) else None,
                       issues=dumps(rep.get('issues') or []))
            writer.writerow({key: _csv_value(value) for key, value in row.items()})
    with (out/'annotations.csv').open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['annotation_origin', 'annotator', 'annotation_version', 'participant_id', 'recording_id', 'evidence_time_s', 'human_label', 'notes'])
        # A self-reported completion is a human annotation, never a measured repetition.
        for report in ((s.get('continuation') or {}).get('self_reports') or []):
            writer.writerow([_csv_value(v) for v in ('human', 'participant', 'self-report-1',
                            session_value(s, 'participant_id'), s.get('recording_id'),
                            report.get('observation_time_s'), 'self_reported_repetition',
                            'reported at '+str(report.get('at_utc')))])
    if s.get('scene_id') == 'rehab':
        (out/'continuation.json').write_text(dumps(continuation_evidence(s), indent=2), encoding='utf-8')
    return out


def _export_dual_camera_csv(session, path):
    dual = session['dual_camera']
    primary, secondary = dual.get('primary_view'), dual.get('secondary_view')
    primary_metric = exercise_spec(session_value(session, 'exercise_id'))['metric']
    auxiliary_metrics = sorted((dual.get('auxiliary_metrics') or {}).keys())
    columns = ['primary_view', 'secondary_view', 'primary_source_ref', 'secondary_source_ref',
               'primary_seq', 'secondary_seq', 'primary_time_s', 'secondary_time_s', 'receive_delta_s',
               'phase', 'included_in_training', 'primary_status', 'auxiliary_status', 'jointly_valid',
               'validity_policy', 'identity_confirmed', 'main_measurement_usable', 'primary_used',
               'primary_metric', 'primary_value', 'primary_valid', 'primary_reason', 'auxiliary_reasons',
               'source_kind', 'usage_context', 'annotation_origin']
    columns += [key+suffix for key in auxiliary_metrics for suffix in ('', '_valid', '_reason')]
    with path.open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        for observation in dual.get('observations') or []:
            metric = (observation.get('primary_metrics') or {}).get(primary_metric) or {}
            row = dict(observation, primary_view=primary, secondary_view=secondary,
                       validity_policy=dual.get('validity_policy', 'all-views-required-1'),
                       primary_source_ref=((dual.get('streams') or {}).get(primary) or {}).get('source_ref'),
                       secondary_source_ref=((dual.get('streams') or {}).get(secondary) or {}).get('source_ref'),
                       primary_metric=primary_metric, primary_value=metric.get('value') if metric.get('valid') else None,
                       primary_valid=metric.get('valid'), primary_reason=metric.get('reason'),
                       auxiliary_reasons=dumps(observation.get('auxiliary_reasons') or []),
                       source_kind=session.get('source_kind'), usage_context=session.get('usage_context'))
            for key in auxiliary_metrics:
                measured = (observation.get('auxiliary_metrics') or {}).get(key) or {}
                row.update({key: measured.get('value') if measured.get('valid') else None,
                            key+'_valid': measured.get('valid'), key+'_reason': measured.get('reason')})
            writer.writerow({key: _csv_value(value) for key, value in row.items() if key in columns})


def export_body_profile(profile, folder) -> dict:
    """Export anonymised summary and evidence IDs; return absolute html/json paths."""
    exported = _export_snapshot(profile)
    out = _empty_export_directory(folder).resolve()
    html_path, json_path = out/'body_profile.html', out/'body_profile.json'
    html_path.write_text(render_body_profile(exported), encoding='utf-8')
    json_path.write_text(dumps(exported, indent=2), encoding='utf-8')
    return {'html': str(html_path), 'json': str(json_path)}


def _history_svg(history, metric):
    from .longitudinal import plot_series, METRICS
    segments = plot_series(history, metric)
    body = f'<text x="16" y="24" font-size="16">{fmt(METRICS[metric])} · 横轴为按日期排序的记录序号</text>'
    if not segments:
        body += '<text x="220" y="145" font-size="16">没有满足比较条件的有效数据点；请核对表中原因。</text>'
    else:
        values = [value for segment in segments for _, value in segment]
        low, high = min(0., min(values)), max(values)
        high += max(1., high-low)*.1
        count = len(history['rows'])
        for index in range(4):
            y = 40+180*index/3
            body += f'<path d="M60 {y} H900" stroke="#e3ddeb"/><text x="5" y="{y+5}" font-size="13">{high-(high-low)*index/3:.1f}</text>'
        for segment in segments:
            points = [(60+840*index/max(1, count-1), 40+180*(high-value)/(high-low), index, value) for index, value in segment]
            if len(points) > 1:
                joined = ' '.join(f'{x:.2f},{y:.2f}' for x, y, _, _ in points)
                body += f'<polyline points="{joined}" fill="none" stroke="#7044d5" stroke-width="2"/>'
            for x, y, index, value in points:
                body += f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4" fill="#7044d5"><title>记录 {index+1}: {value:.2f}</title></circle>'
        body += f'<text x="60" y="252">1</text><text x="880" y="252">{count}</text>'
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 940 270" role="img" '
            'aria-label="相同记录条件下的观测数值；缺失记录断开曲线" style="width:100%;background:white">'+body+'</svg>')


def render_longitudinal_history(history, metric='range_deg'):
    from .longitudinal import METRICS, DATA_LABELS, COMPARISON_LABELS, CONDITION_LABELS
    if metric not in METRICS:
        raise ValueError('未知历史指标')
    scope = history['scope']
    text = '<h1>'+fmt(history['exercise_label'])+' · 纵向记录</h1><p>'+fmt(scope['participant_id'])+' · '+fmt(SIDES.get(scope['side']))+' · '+fmt(MODES.get(scope['submode']))+' · '+fmt(SOURCES.get(scope['source_kind']))+' / '+fmt(CONTEXTS.get(scope['usage_context']))+'</p>'
    text += '<p class="note">'+fmt(history['note'])+'</p><p>比较基准：<code>'+fmt(history['anchor_id'])+'</code>。曲线仅连接相邻的、已结束且有完整动作与有效测量的同条件记录；横轴不按日历间隔缩放。</p>'
    text += _history_svg(history, metric)
    text += '<h2>全部同用户 / 来源 / 情境 / 动作 / 侧别 / 模式记录</h2><p>失败、日期缺失与条件不同的记录保留。时间中位数只使用各次完整动作的有效时间；括号为有效样本数 / 完整动作数。空值不表示 0。</p>'
    text += '<table><tr><th>序号 / 开始 UTC</th><th>记录</th><th>条件</th><th>完整次数</th><th>观察幅度 °</th><th>当前指标：'+fmt(METRICS[metric])+'</th><th>有效观察</th></tr>'
    for index, row in enumerate(history['rows']):
        count = row['timing_counts'].get(metric)
        value = fmt(row['values'][metric], 2)+(f" ({count['measured']} / {count['complete_repetitions']})" if count else '')
        values = [str(index+1)+' · '+fmt(row['start_utc']), fmt(DATA_LABELS[row['data_state']]),
                  fmt(COMPARISON_LABELS[row['comparison']['status']]), fmt(row['values']['completed'], 0),
                  fmt(row['values']['range_deg']), value, _percent(row['valid_ratio'])]
        text += '<tr>'+''.join('<td>'+v+'</td>' for v in values)+'</tr>'
    text += '</table><h2>比较条件与原始记录引用</h2>'
    for row in history['rows']:
        keys = row['comparison']['differences']+row['comparison']['missing']
        text += '<details><summary>'+fmt(row['session_id'])+' · '+fmt(COMPARISON_LABELS[row['comparison']['status']])+'</summary>'
        text += '<p>差异 / 缺失：'+fmt('、'.join(CONDITION_LABELS.get(k, k) for k in keys) or '无已记录条件差异')+'</p>'
        text += '<p>数据状态：'+fmt(row['status'])+'；结束原因：'+fmt(row['stop_reason'])+'；角度来源：'+fmt(row['motion_evidence_source'])+'</p>'
        text += '<table>'+''.join('<tr><th>'+fmt(CONDITION_LABELS.get(key, key))+'</th><td>'+fmt(dumps(value))+'</td></tr>' for key, value in row['conditions']['values'].items())+'</table></details>'
    return _document('纵向记录', text)


def export_longitudinal_history(history, folder, metric='range_deg'):
    from .longitudinal import METRICS
    if metric not in METRICS:
        raise ValueError('未知历史指标')
    result = _export_snapshot(history)
    result['source_fingerprint'] = result.pop('fingerprint')
    result['selected_metric'] = metric
    result['export_content_sha256'] = digest(result)
    out = _empty_export_directory(folder).resolve()
    (out/'history.json').write_text(dumps(result, indent=2), encoding='utf-8')
    (out/'history.html').write_text(render_longitudinal_history(result, metric), encoding='utf-8')
    (out/'chart.svg').write_text(_history_svg(result, metric), encoding='utf-8')
    with (out/'history.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        columns = ['session_id', 'start_utc', 'end_utc', 'status', 'stop_reason', 'data_state', 'comparison', 'differences', 'missing', 'valid_ratio', *METRICS, 'timing_counts', *result['scope']]
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for row in result['rows']:
            values = {key: row.get(key) for key in columns[:6]}
            values.update(row['values'], **result['scope'], valid_ratio=row['valid_ratio'], comparison=row['comparison']['status'],
                          differences=dumps(row['comparison']['differences']), missing=dumps(row['comparison']['missing']), timing_counts=dumps(row['timing_counts']))
            writer.writerow({key: _csv_value(value) for key, value in values.items()})
    return str(out)
