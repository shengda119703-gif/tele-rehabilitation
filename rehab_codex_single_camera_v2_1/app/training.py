"""Execution of an explicitly confirmed plan; never a prescription generator."""
import copy
import math

from .rehab import RehabEngine


FEEDBACK_REASONS = {'not_recorded': '未填写', 'completed': '按安排结束', 'discomfort': '出现不适',
                    'fatigue': '感到疲劳', 'time': '时间安排', 'technical': '设备或识别问题', 'other': '其他'}


def validate_training_feedback(value):
    if not isinstance(value, dict):
        raise ValueError('训练感受内容无效')
    result = {'record_origin': 'self_report'}
    for key in ('pain', 'fatigue'):
        score = value.get(key)
        if score is not None and (type(score) is not int or not 0 <= score <= 10):
            raise ValueError('疼痛和疲劳自评分应为 0–10 的整数，或留空')
        result[key] = score
    reason = value.get('reason', 'not_recorded')
    if not isinstance(reason, str) or reason not in FEEDBACK_REASONS:
        raise ValueError('请选择结束原因')
    notes = value.get('notes', '')
    if not isinstance(notes, str) or len(notes.strip()) > 1000:
        raise ValueError('补充说明最多 1000 个字')
    result.update(reason=reason, notes=notes.strip())
    return result


class TrainingEngine(RehabEngine):
    """One source-clock timeline, bounded sets, explicit rest/resume boundaries.

    The existing action engine measures only ACTIVE / RECOVERY observations.
    Rest and pause do not enter angle evidence, counts, or quality coverage.
    Sit-to-stand keeps its standing endpoint; return is observed separately.
    """
    def __init__(self, plan):
        if plan.get('submode') != 'training':
            raise ValueError('训练执行需要明确的训练计划')
        for key, maximum in (('target_reps', 999), ('target_sets', 20)):
            if type(plan.get(key)) is not int or not 1 <= plan[key] <= maximum:
                raise ValueError('训练次数或组数无效')
        rest = plan.get('rest_between_sets_s')
        if rest is not None and (type(rest) not in (int, float) or not math.isfinite(rest) or not 0 <= rest <= 1800):
            raise ValueError('组间休息时间应为 0–1800 秒，或不设置')
        super().__init__(plan)
        self.stage = 'ACTIVE'
        self.paused_from = None
        self.ended_stage = None
        self.clock_t = self.clock_start = self.boundary_time = None
        self.active_span_s = self.rest_total_s = self.paused_total_s = 0.
        self.rest_elapsed_s = 0.
        self.set_number = 1
        self.sets = [self._new_set()]
        self.training_events = []
        self.last_observation_included = False

    def _new_set(self):
        return {'number': self.set_number, 'status': 'ACTIVE', 'start_time_s': None,
                'end_time_s': None, 'rest_start_s': None, 'rest_end_s': None, 'rest_s': 0.}

    def _event(self, kind, t):
        self.training_events.append({'type': kind, 'time_s': t, 'set_number': self.set_number})

    def accepts_time(self, t):
        return (type(t) in (int, float) and math.isfinite(t) and self.stage != 'FINISHED'
                and (self.clock_t is None or t > self.clock_t))

    def _advance(self, t):
        if type(t) not in (int, float) or not math.isfinite(t) or (self.clock_t is not None and t < self.clock_t):
            raise ValueError('输入时间已过期，请等待新画面')
        if self.clock_start is None:
            self.clock_start = t
        dt = 0. if self.clock_t is None else t-self.clock_t
        if self.stage in ('ACTIVE', 'RECOVERY'):
            self.active_span_s += dt
        elif self.stage == 'RESTING':
            self.rest_total_s += dt
            self.rest_elapsed_s += dt
            self.sets[-1]['rest_s'] += dt
        elif self.stage == 'PAUSED':
            self.paused_total_s += dt
        self.clock_t = t

    def _reset_motion(self, t):
        self._close_standing_timing('training_boundary')
        self.timing_history.clear()
        self.phase = 'WAIT_READY'
        self.holds.clear()
        self.rest_samples.clear()
        self.issue_starts.clear()
        self.motion_evidence.break_continuity()
        self.last_standing_rep = None
        self.last_t, self.last_good_t, self.previous_valid = t, None, False
        self.latest_metrics = {}

    def _record(self, t, completion, reason=None):
        rep = super()._record(t, completion, reason)
        if rep is not None:
            rep['set_number'] = self.set_number
        return rep

    def _enter_rest(self, t):
        self._reset_motion(t)
        if self.set_number == self.plan['target_sets']:
            self.stage = 'COMPLETE'
            self._event('plan_complete', t)
        else:
            self.stage = 'RESTING'
            self.rest_elapsed_s = 0.
            self.sets[-1]['rest_start_s'] = t
            self._event('rest_start', t)

    def process(self, observation):
        t = observation.time_s
        if not self.accepts_time(t):
            return
        self._advance(t)
        self.last_observation_included = self.stage in ('ACTIVE', 'RECOVERY')
        if not self.last_observation_included:
            self.last_t = t
            self.latest_metrics = {}
            self.previous_valid = False
            return
        if self.sets[-1]['start_time_s'] is None:
            self.sets[-1]['start_time_s'] = t
        before = self.completed
        super().process(observation)
        if self.stage == 'RECOVERY':
            if self.phase == 'SEATED_READY':
                self._enter_rest(t)
            return
        if self.completed > before and self.completed >= self.set_number*self.plan['target_reps']:
            self.sets[-1].update(status='COMPLETE', end_time_s=t)
            self._event('set_complete', t)
            if self.exercise == 'sit_to_stand':
                self.stage = 'RECOVERY'
            else:
                self._enter_rest(t)

    def _remaining(self):
        configured = self.plan.get('rest_between_sets_s')
        return None if configured is None else max(0., configured-self.rest_elapsed_s)

    def control(self, action, t):
        allowed = {'pause': self.stage in ('ACTIVE', 'RECOVERY', 'RESTING'),
                   'resume': self.stage == 'PAUSED', 'next_set': self.stage == 'RESTING'}
        if not allowed.get(action):
            raise ValueError('当前训练阶段不能执行此操作')
        self._advance(t)
        if action == 'next_set' and self._remaining() is not None and self._remaining() > 1e-8:
            raise ValueError('尚未达到本次计划的休息时间；可继续休息或结束训练')
        self.boundary_time = t
        self.last_observation_included = False
        if action == 'pause':
            self._record(t, 'INTERRUPTED', 'user_pause')
            self.paused_from = self.stage
            self._reset_motion(t)
            self.stage = 'PAUSED'
        elif action == 'resume':
            self._reset_motion(t)
            self.stage = self.paused_from
            self.paused_from = None
        else:
            self.sets[-1]['rest_end_s'] = t
            self.set_number += 1
            self.sets.append(self._new_set())
            self._reset_motion(t)
            self.stage = 'ACTIVE'
        self._event(action, t)

    def finish(self, reason):
        if self.stage == 'FINISHED':
            return
        super().finish(reason)
        if self.sets[-1]['status'] != 'COMPLETE':
            self.sets[-1].update(status='INTERRUPTED', end_time_s=self.clock_t)
        self.ended_stage = self.stage
        self.stage = 'FINISHED'
        self.latest_metrics = {}
        self._event('finish:'+reason, self.clock_t)

    def summary(self):
        result = super().summary()
        from .automatic_plans import observed_quality
        result['observed_quality'] = observed_quality(self.repetitions)
        completed_sets = sum(s['status'] == 'COMPLETE' for s in self.sets)
        sets = copy.deepcopy(self.sets)
        for group in sets:
            reps = [r for r in self.repetitions if r.get('set_number') == group['number']]
            group.update(completed=sum(r['completion_status'] == 'COMPLETE' for r in reps),
                         interrupted=sum(r['completion_status'] in ('INTERRUPTED', 'UNASSESSABLE') for r in reps),
                         partial=sum(r['completion_status'] == 'PARTIAL' for r in reps))
        remaining = self._remaining()
        messages = {'PAUSED': '训练已暂停，不计动作。摄像头仍在预览；恢复后重新准备。',
                    'RESTING': ('按已确认安排休息，准备好后点击“下一组”。' if remaining is None or remaining <= 1e-8 else
                                f'组间休息，剩余 {math.ceil(remaining)} 秒；休息期间不计动作。'),
                    'COMPLETE': '计划次数已完成，不再计次。可以结束并记录本次感受。',
                    'RECOVERY': '本组起立次数已完成；按已确认安排回坐，或结束本次训练。',
                    'FINISHED': '本次训练已结束。'}
        if self.stage in messages:
            result['message'] = messages[self.stage]
        if self.stage == 'RECOVERY':
            if not self.previous_valid:
                result['message'] = self.message
            elif self.phase == 'STANDING_REACHED' and self._hold_guidance():
                result['message'] = self._hold_guidance()
        result.update(observed_span_s=self.active_span_s,
                      valid_ratio=min(1., self.valid_s/self.active_span_s) if self.active_span_s > 0 else None,
                      completed_sets=completed_sets, plan_completed=completed_sets == self.plan['target_sets'])
        result['training'] = {'schema_version': 1, 'stage': self.stage, 'ended_stage': self.ended_stage,
                              'exercise_label': self.spec['label'], 'side': self.plan['side'],
                              'guidance': result['message'],
                              'observed_quality': copy.deepcopy(result['observed_quality']),
                              'set_number': self.set_number, 'set_reps': sets[-1]['completed'],
                              'target_reps': self.plan['target_reps'], 'target_sets': self.plan['target_sets'],
                              'rest_remaining_s': remaining, 'rest_s': self.rest_total_s,
                              'paused_s': self.paused_total_s,
                              'session_span_s': self.clock_t-self.clock_start if self.clock_t is not None else 0.,
                              'can_pause': self.stage in ('ACTIVE', 'RECOVERY', 'RESTING'),
                              'can_resume': self.stage == 'PAUSED',
                              'can_next_set': self.stage == 'RESTING' and (remaining is None or remaining <= 1e-8),
                              'sets': sets, 'events': copy.deepcopy(self.training_events)}
        return result
