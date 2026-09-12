"""Presentation policy only. It never admits observations or changes a rule."""
import math

from .exercise_instructions import exercise_instructions
from .guided import GUIDED_NOTE

# Offered, never forced: a long run of missing measurement suggests the guided
# path instead of repeating the same adjustment request.
CONTINUATION_OFFER = '一直看不清也可以继续：在“步骤”里选“引导计时练习”。'
GUIDED_STATUS = '引导计时 · 本次不自动测角度'


def _next_action_cue(info, observed_phase, *, returning=False):
    """Translate an observed phase into the action the participant should do next.

    The observed phase describes evidence already obtained.  The cue deliberately
    advances only after that evidence crosses a state-machine boundary, so REST
    means the start position is confirmed and the next request is the outbound
    movement, rather than another description of the start position.
    """
    if observed_phase == 'WAIT_READY':
        return {'key': 'start', 'phase': 'ready', 'label': '保持准备姿势',
                'instruction': info['start']}
    if returning or observed_phase in ('STANDING_REACHED', 'LOWERING'):
        return {'key': 'return', 'phase': 'return', 'label': '缓慢回到起点',
                'instruction': info['return']}
    if observed_phase in ('REST', 'SEATED_READY', 'RAISING', 'RISING', 'PEAK_OR_HOLD'):
        return {'key': 'move', 'phase': 'outbound', 'label': '开始完成动作',
                'instruction': info['move']}
    return None


class GuidancePolicy:
    adjustment_after_s = 1.5
    recovery_status_s = 1.
    candidate_switch_s = .6
    # A gap that already produced one instruction must last longer before the
    # interface speaks up again, so a flickering detection cannot nag.
    repeat_adjustment_after_s = 3.
    offer_after_s = 10.

    def __init__(self):
        self.context = None
        self.invalid_since = None
        self.recovered_at = None
        self.adjustment = None
        self.candidate_adjustment = None
        self.candidate_since = None
        self.critical = None
        self.escalations = 0
        self.period_escalated = False
        self.missing_total_s = 0.
        self.last_now = None
        self.action_cue = None

    def _reset_context(self):
        self.invalid_since = self.recovered_at = self.adjustment = self.critical = None
        self.candidate_adjustment = self.candidate_since = None
        self.escalations = 0
        self.period_escalated = False
        self.missing_total_s = 0.
        self.last_now = None
        self.action_cue = None

    def _clear_gap(self):
        self.invalid_since = self.adjustment = None
        self.candidate_adjustment = self.candidate_since = None
        self.period_escalated = False

    def render(self, data, plan, *, now):
        context = (data.get('context'), plan['exercise_id'], plan['side'], data['state'])
        if context != self.context:
            self._reset_context()
            self.context = context
        info = exercise_instructions(plan['exercise_id'])
        state = data['state']
        summary = data.get('summary') or {}
        stage = (summary.get('training') or {}).get('stage')
        phase = summary.get('phase')
        valid = bool(data.get('current_measurement_valid'))
        guided = data.get('continuation_mode') == 'guided'
        if self.last_now is not None and not valid and now >= self.last_now:
            self.missing_total_s += now-self.last_now
        self.last_now = now
        offer = (not guided and state in ('PREVIEW', 'ONLINE')
                 and self.missing_total_s >= self.offer_after_s)
        pending = self.action_cue or {}
        result = dict(level='action', instruction=pending.get('instruction', info['start']), status='',
                      phase=pending.get('phase'), cue_key=pending.get('key'),
                      cue_label=pending.get('label', ''), observed_phase=None,
                      measurement_valid=valid, recovery=None,
                      measurement_quality='observed' if valid else 'unavailable',
                      offer='guided' if offer else None,
                      offer_text=CONTINUATION_OFFER if offer else '')

        def display(level, instruction, status='', recovery=None, **extra):
            if level in ('critical', 'adjust', 'paused'):
                extra = dict(extra, phase=None, cue_key=None, cue_label='')
            return dict(result, level=level, instruction=instruction, status=status, recovery=recovery, **extra)

        if state == 'SAVE_FAILED':
            return display('critical', '结果尚未保存，请重试保存。', recovery='save', offer=None, offer_text='')
        if data.get('error') and not data.get('operation_error'):
            self.critical = str(data['error'])
        identity = data.get('identity_ambiguous') or data.get('observation_status') == 'MULTI_PERSON'
        if identity:
            return display('critical', '请只保留当前参与者，再重新确认。', recovery='confirm', offer=None, offer_text='')
        if state in ('OFFLINE', 'ERROR') or self.critical:
            text = ('请只保留当前参与者，再重新预览确认。' if '归属' in (self.critical or '') else
                    '画面已中断，请重新预览。')
            return dict(display('critical', text, recovery='preview', offer=None, offer_text=''),
                        detail=self.critical or text)
        if data.get('error'):
            return display('adjust', str(data['error']).split('；')[0])
        if state == 'PRIVACY_PAUSED':
            return display('paused', '采集已暂停，准备好后重新预览。', recovery='preview')
        if state not in ('PREVIEW', 'ONLINE'):
            return display('paused', '请先打开预览，完成本次准备。')
        if state == 'ONLINE' and stage in ('PAUSED', 'RESTING', 'COMPLETE', 'FINISHED'):
            self._clear_gap()
            self.recovered_at = None
            text = {'PAUSED': '训练已暂停，请先休息。', 'RESTING': '组间休息，准备好后继续。',
                    'COMPLETE': '本次训练已完成，请结束并保存。', 'FINISHED': '训练已结束。'}[stage]
            remaining = (summary.get('training') or {}).get('rest_remaining_s')
            if stage == 'RESTING' and isinstance(remaining, (int, float)) and math.isfinite(remaining) and remaining > 0:
                text = f'组间休息，还需 {math.ceil(remaining)} 秒。'
            return display('paused', text)
        if guided:
            # The guided path never asks for a framing fix it does not need; the
            # prompt keeps the person moving and the record says what was measured.
            prompt = data.get('guided_prompt') or {}
            self._clear_gap()
            if prompt.get('paused'):
                return display('paused', '提示已暂停，准备好后点“继续提示”。', '引导计时 · 暂停中')
            status = GUIDED_STATUS if state == 'ONLINE' else ''
            if state == 'PREVIEW':
                return display('status', data.get('preparation_instruction') or GUIDED_NOTE,
                               '引导计时 · 准备好后开始', measurement_quality='observed' if valid else 'approximate')
            return display('status', prompt.get('instruction') or info['move'], status,
                           measurement_quality='observed' if valid else 'approximate',
                           phase=prompt.get('key'), prompt_label=prompt.get('label'),
                           prompt_remaining_s=prompt.get('remaining_s'), prompt_cycle=prompt.get('cycle'))
        if not valid:
            if self.invalid_since is None:
                self.invalid_since = now
                self.period_escalated = False
            self.recovered_at = None
            threshold = self.adjustment_after_s if self.escalations == 0 else self.repeat_adjustment_after_s
            if not self.period_escalated and now-self.invalid_since+1e-8 < threshold:
                quiet = '正在重新识别，当前不计次' if state == 'ONLINE' else '正在识别，请保持当前姿势'
                instruction = (self.action_cue or {}).get('instruction') or '请保持当前姿势，等待重新识别。'
                return display('status', instruction, quiet, phase=None, cue_key=None, cue_label='')
            if not self.period_escalated:
                self.period_escalated = True
                self.escalations += 1
            # A newly missing point must persist before replacing the single instruction.
            action = data.get('adjustment') or '请让测试部位清楚进入画面。'
            if self.adjustment is None:
                self.adjustment = action
            elif action == self.adjustment:
                self.candidate_adjustment = self.candidate_since = None
            elif action != self.candidate_adjustment:
                self.candidate_adjustment, self.candidate_since = action, now
            elif now-self.candidate_since >= self.candidate_switch_s:
                self.adjustment = action
                self.candidate_adjustment = self.candidate_since = None
            return display('adjust', self.adjustment)
        if self.invalid_since is not None:
            self._clear_gap()
            self.recovered_at = now
        if self.recovered_at is not None and now-self.recovered_at < self.recovery_status_s:
            result['status'] = '已重新识别'
        if data.get('auxiliary_missing'):
            result['status'] = '辅助指标：本项无法评价'
            result['measurement_quality'] = 'observed'
        if state == 'PREVIEW':
            return dict(result, instruction=data.get('preparation_instruction') or '保持舒适起点，完成本次准备。',
                        phase=None, cue_key=None, cue_label='', observed_phase=phase)
        if plan.get('submode') == 'training' and stage not in ('ACTIVE', 'RECOVERY'):
            return display('paused', '请暂停动作，等待训练状态确认。')
        if summary.get('current_issues') and summary.get('message'):
            rule = summary['current_issues'][0].get('rule_id')
            action = {'trunk_tilt': '请保持躯干稳定。', 'elbow_flexion': '请按已确认的安排调整肘部姿势。'}.get(rule)
            return display('adjust', action or summary['message'].split('；')[0])
        timing = summary.get('movement_timing_live') or {}
        held, goal = timing.get('hold_elapsed_s'), timing.get('hold_min_s')
        if (plan.get('submode') == 'training' and isinstance(held, (float, int)) and isinstance(goal, (float, int))
                and held+1e-8 < goal and phase in ('RAISING', 'PEAK_OR_HOLD', 'RISING', 'STANDING_REACHED')):
            return dict(result, instruction=f'本段连续保持 {held:.1f} / {goal:g} 秒。',
                        phase='outbound', cue_key='hold', cue_label='继续保持', observed_phase=phase)
        message = summary.get('message', '')
        returning = (stage == 'RECOVERY' or phase in ('LOWERING', 'STANDING_REACHED') or
                     message.startswith(('已观察到目标范围；', '已观察到本次连续保持目标')))
        cue = _next_action_cue(info, phase, returning=returning)
        if cue:
            self.action_cue = cue
            return dict(result, instruction=cue['instruction'], phase=cue['phase'], cue_key=cue['key'],
                        cue_label=cue['label'], observed_phase=phase)
        return dict(result, instruction=info['move'], phase=None, cue_key=None, cue_label='',
                    observed_phase=phase)
