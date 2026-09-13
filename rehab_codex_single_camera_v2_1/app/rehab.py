from __future__ import annotations

import copy
import math
from collections import deque
from statistics import median
from .domain import clean_json
from .exercises import exercise_spec
from .joint_calibration import validate_start_value
from .movement_timing import MovementTiming, TIMING_VERSION, timing_for_plan


class _AngleEvidence:
    """Observed three-sample medians; never bridge an invalid observation."""

    def __init__(self):
        self.window = deque(maxlen=3)
        self.sample_count = 0
        self.minimum = self.maximum = None

    def add(self, value):
        self.sample_count += 1
        self.window.append(value)
        if len(self.window) == 3:
            value = median(self.window)
            self.minimum = value if self.minimum is None else min(self.minimum, value)
            self.maximum = value if self.maximum is None else max(self.maximum, value)

    def break_continuity(self):
        self.window.clear()

    def motion_range(self):
        if self.minimum is None:
            return None
        return {'min_deg': self.minimum, 'max_deg': self.maximum,
                'range_deg': self.maximum-self.minimum}


class RehabEngine:
    """Causal, explicit exercise state machines. No camera/model access."""

    def __init__(self, plan):
        self.plan = copy.deepcopy(plan)
        self.exercise = plan['exercise_id']
        self.spec = exercise_spec(self.exercise)
        if self.plan.get('view', self.spec['view']) != self.spec['view']:
            raise ValueError('动作与已确认机位不匹配')
        target = self.plan['target_angle_deg']
        if target is not None and (not math.isfinite(target) or not 0 <= target <= 180):
            raise ValueError('人工角度目标必须是 0–180 度之间的有限数值或 null')
        self.primary_metric = self.spec['metric']
        baseline = self.plan.get('joint_baseline') or {}
        if baseline:
            value = baseline.get('rest_value')
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
                raise ValueError('舒适起点不是有效测量')
            validate_start_value(self.plan, value)
        self.automatic_rest_value = None
        self.automatic_sitstand = False
        self.direction = 1 if self.spec['target_direction'] == 'increase' else -1
        self.timing_plan = timing_for_plan(self.plan)
        self.timing_history = deque()
        self.standing_timing = None
        self.motion_evidence = _AngleEvidence()
        self.rest_samples = deque(maxlen=3)
        self.phase = 'WAIT_READY'
        self.repetitions = []
        self.current = None
        self.last_standing_rep = None
        self.last_t = self.first_t = self.last_good_t = None
        self.last_track = None
        self.previous_valid = False
        self.valid_s = 0.
        self.holds = {}
        self.issue_starts = {}
        self.latest_metrics = {}
        self.message = self.spec['ready_hint']
        self.position_hint = None

    @property
    def completed(self):
        return sum(r['completion_status'] == 'COMPLETE' for r in self.repetitions)

    def _held(self, key, condition, t, duration):
        if not condition:
            self.holds.pop(key, None)
            return False
        return t - self.holds.setdefault(key, t) + 1e-8 >= duration

    def _new(self, t):
        # Observed ready angles anchor the excursion, without extending its timer.
        evidence = _AngleEvidence()
        for value in self.rest_samples:
            evidence.add(value)
        self.current = {'start_time_s': t, 'samples': {self.primary_metric: list(self.rest_samples)},
                        'unavailable': {}, 'issues': [], 'angle_evidence': evidence}
        timer = MovementTiming(direction=self.direction, max_gap_s=self.plan['max_gap_s'],
                               target=self.plan['target_angle_deg'], goals=self.timing_plan,
                               sit_to_stand=self.exercise == 'sit_to_stand')
        start = self.holds.get('rise' if self.exercise == 'sit_to_stand' else 'raise', t)
        history = list(self.timing_history)
        first = next((i for i, sample in enumerate(history) if sample[0] >= start), len(history))
        for sample_t, angle, standing in history[max(0, first-1):]:
            timer.add(sample_t, angle, at_standing=standing)
        self.current['timing'] = timer
        self.rest_samples.clear()
        self.issue_starts.clear()

    def _collect(self, o):
        if self.current is None:
            return
        self.current['angle_evidence'].add(o.value(self.primary_metric))
        shoulder = self.spec['joint'] == 'shoulder'
        relevant = set(self.spec['required_metrics'])
        if shoulder:
            relevant.update(('elbow_flexion_deg', 'trunk_tilt_deg', 'raise_deg'))
        for name, metric in o.metrics.items():
            if name not in relevant:
                continue
            if (shoulder and name in ('elbow_flexion_deg', 'trunk_tilt_deg')
                    and (self.phase not in ('RAISING', 'PEAK_OR_HOLD') or (o.value('raise_deg') or 0) <= self.plan['rest_deg'])):
                continue
            if metric.valid and metric.value is not None and math.isfinite(metric.value):
                self.current['samples'].setdefault(name, []).append(metric.value)
            else:
                self.current['unavailable'][name] = metric.reason or 'missing_or_nonfinite'
        if not shoulder or self.phase not in ('RAISING', 'PEAK_OR_HOLD'):
            return
        for rule, name, limit_name in (
            ('elbow_flexion', 'elbow_flexion_deg', 'allowed_elbow_flexion_deg'),
            ('trunk_tilt', 'trunk_tilt_deg', 'allowed_trunk_tilt_deg'),
        ):
            value, limit = o.value(name), self.plan[limit_name]
            if value is None or limit is None or value <= limit:
                self.issue_starts.pop(rule, None)
                continue
            start = self.issue_starts.setdefault(rule, o.time_s)
            if o.time_s - start + 1e-8 < self.plan['issue_hold_s']:
                continue
            issue = next((x for x in self.current['issues'] if x['rule_id'] == rule), None)
            if issue is None:
                issue = {'rule_id': rule, 'phase': self.phase, 'start_time_s': start,
                         'end_time_s': o.time_s, 'metric': name, 'measured_value': value,
                         'configured_limit': limit, 'evidence_valid': True,
                         'feedback_emitted_at': None}
                self.current['issues'].append(issue)
            issue['end_time_s'] = o.time_s
            issue['measured_value'] = max(issue['measured_value'], value)

    @staticmethod
    def _stable_peak(samples):
        if len(samples) < 3:
            return None
        return max(median(samples[i:i+3]) for i in range(len(samples)-2))

    @staticmethod
    def _stable_min(samples):
        return None if len(samples) < 3 else min(median(samples[i:i+3]) for i in range(len(samples)-2))

    def _record(self, t, completion, reason=None):
        if self.current is None:
            return None
        c = self.current
        sample_metrics = c['samples']
        validity = {}
        for key in set(sample_metrics) | set(c['unavailable']):
            present = bool(sample_metrics.get(key))
            validity[key] = {'valid': present, 'reason': None if present else c['unavailable'][key],
                             'partial_observation': key in c['unavailable']}
        motion_range = c['angle_evidence'].motion_range()
        maximum = motion_range['max_deg'] if motion_range else None
        minimum = motion_range['min_deg'] if motion_range else None
        validity[self.primary_metric] = {
            'valid': motion_range is not None,
            'reason': None if motion_range else 'insufficient_valid_samples',
            'partial_observation': self.primary_metric in c['unavailable']}
        peak = maximum if self.primary_metric == 'raise_deg' else self._stable_peak(sample_metrics.get('raise_deg', []))
        knee_samples = sample_metrics.get('knee_flexion_deg', [])
        knee_min = minimum if self.primary_metric == 'knee_flexion_deg' else self._stable_min(knee_samples)
        target = self.plan['target_angle_deg']
        measured = maximum if self.direction == 1 else minimum
        if target is None:
            target_status = 'NOT_SET'
        elif measured is None or completion in ('UNASSESSABLE', 'INTERRUPTED'):
            target_status = 'UNASSESSABLE'
        else:
            met = measured >= target if self.direction == 1 else measured <= target
            target_status = 'MET' if met else 'NOT_MET'
        observation_status = ('UNUSABLE' if completion == 'UNASSESSABLE' else
                              'PARTIAL_OBSERVABLE' if c['unavailable'] or reason else 'VALID')
        rep = {'number': len(self.repetitions)+1, 'start_time_s': c['start_time_s'],
               'end_time_s': t, 'duration_s': max(0., t-c['start_time_s']),
               'observation_status': observation_status,
               'observation_reasons': sorted(set(c['unavailable'].values()) | ({reason} if reason else set())),
               'completion_status': completion, 'target_status': target_status,
               'exercise_id': self.exercise, 'primary_metric': self.primary_metric,
               'primary_metric_label': self.spec['metric_label'],
               'peak_angle_deg': maximum, 'min_angle_deg': minimum,
               'range_deg': motion_range['range_deg'] if motion_range else None,
               'motion_range': motion_range, 'target_direction': self.spec['target_direction'],
               'measurement_type': '2d_projection', 'clinical_rom': False,
               'max_raise_projection_deg': peak, 'min_knee_flexion_projection_deg': knee_min,
               'rise_time_s': max(0., t-c['start_time_s']) if self.exercise == 'sit_to_stand' and completion == 'COMPLETE' else None,
               'lowering_time_s': None, 'metric_validity': validity, 'issues': copy.deepcopy(c['issues'])}
        timer = c['timing']
        if self.exercise == 'sit_to_stand' and completion == 'COMPLETE':
            timer.mark_standing(t)
            self.standing_timing = timer
        rep['movement_timing'] = timer.snapshot(completion, reason=reason,
                                                cycle_complete=completion == 'COMPLETE' and self.exercise != 'sit_to_stand')
        if self.exercise == 'sit_to_stand':
            rep['rise_time_s'] = rep['movement_timing']['outbound_s']['value']
        if self.exercise == 'sit_to_stand' and target_status == 'NOT_MET':
            rep['issues'].append({'rule_id': 'target_not_reached', 'phase': self.phase,
                                 'start_time_s': c['start_time_s'], 'end_time_s': t,
                                 'metric': 'knee_flexion_deg', 'measured_value': knee_min,
                                 'configured_limit': target, 'evidence_valid': True,
                                 'feedback_emitted_at': None})
        self.repetitions.append(rep)
        self.current = None
        self.issue_starts.clear()
        return rep

    def _interrupt(self, t, reason):
        self._close_standing_timing(reason)
        self._record(t, 'UNASSESSABLE', reason)
        self.phase = 'WAIT_READY'
        self.holds.clear()
        self.rest_samples.clear()
        self.motion_evidence.break_continuity()
        self.last_standing_rep = None
        self.timing_history.clear()

    def _close_standing_timing(self, reason=None, *, cycle_complete=False):
        if self.standing_timing and self.last_standing_rep is not None:
            self.last_standing_rep['movement_timing'] = self.standing_timing.snapshot(
                'COMPLETE', cycle_complete=cycle_complete, reason=reason)
            self.last_standing_rep['lowering_time_s'] = self.last_standing_rep['movement_timing']['return_s']['value']
        self.standing_timing = None

    def _standing_condition(self, o):
        c = self.plan.get('calibration') or {}
        return (self.exercise == 'sit_to_stand' and 'standing_knee' in c and 'standing_hip_y' in c
                and o.value('knee_flexion_deg') <= c['standing_knee']+10
                and o.value('hip_y') <= c['standing_hip_y']+.04)

    def _timing_observation(self, o):
        t, angle, standing = o.time_s, o.value(self.primary_metric), self._standing_condition(o)
        self.timing_history.append((t, angle, standing))
        cutoff = t-max(2., self.plan['dwell_s']+self.plan['max_gap_s']+.5)
        while len(self.timing_history) > 1 and self.timing_history[1][0] < cutoff:
            self.timing_history.popleft()
        timer = self.current['timing'] if self.current else self.standing_timing
        if timer:
            timer.add(t, angle, at_standing=standing)
        if self.standing_timing and self.last_standing_rep is not None:
            self.last_standing_rep['movement_timing'] = self.standing_timing.snapshot('COMPLETE')

    def process(self, o):
        t = o.time_s
        if self.phase == 'FINISHED' or t is None or not math.isfinite(t):
            return
        if self.last_t is not None and t <= self.last_t:
            return
        if self.first_t is None:
            self.first_t = t
        dt = 0 if self.last_t is None else t-self.last_t
        identity_change = self.last_track is not None and o.track_key is not None and self.last_track != o.track_key
        gap = dt > self.plan['max_gap_s']
        missing_gap = self.last_good_t is not None and t-self.last_good_t > self.plan['max_gap_s']
        if gap or identity_change or o.status == 'MULTI_PERSON' or missing_gap:
            reason = ('identity_ambiguous' if identity_change or o.status == 'MULTI_PERSON' else
                      'stream_gap' if gap else 'occlusion')
            self._interrupt(t, reason)
            self.previous_valid = False
        self.last_t = t
        if o.track_key is not None:
            self.last_track = o.track_key
        necessary = self.spec['required_metrics']
        valid = (o.status == 'VALID' and o.track_key is not None and
                 all(o.value(k) is not None and math.isfinite(o.value(k)) for k in necessary))
        self.latest_metrics = clean_json(o.metrics)
        if not valid:
            self.timing_history.clear()
            timer = self.current['timing'] if self.current else self.standing_timing
            if timer:
                timer.break_continuity(t, 'occlusion')
            self.holds.clear()
            self.issue_starts.clear()
            self.rest_samples.clear()
            self.motion_evidence.break_continuity()
            if self.current:
                self.current['angle_evidence'].break_continuity()
                for key in necessary:
                    metric = o.metrics.get(key)
                    if o.status != 'VALID' or o.track_key is None or o.value(key) is None or not math.isfinite(o.value(key)):
                        self.current['unavailable'][key] = (metric.reason if metric and metric.reason else
                                                             'identity_ambiguous' if o.track_key is None else 'occlusion')
            self.previous_valid = False
            self.message = '当前片段暂未计入；画面清楚后会自动继续'
            return
        if self.previous_valid and not gap and not identity_change:
            self.valid_s += dt
        self.previous_valid, self.last_good_t = True, t
        self.motion_evidence.add(o.value(self.primary_metric))
        self._timing_observation(o)
        self._collect(o)
        if self.exercise == 'sit_to_stand':
            self._sitstand(o)
        else:
            self._joint_cycle(o)

    def _joint_cycle(self, o):
        t, angle = o.time_s, o.value(self.primary_metric)
        self.position_hint = None
        rest, dwell = self.plan['rest_deg'], self.plan['dwell_s']
        # RAISING means outbound for all joint tasks; knee extension decreases
        # the flexion metric and does not enter the sit-to-stand state machine.
        at_rest = angle >= rest if self.direction == -1 else -rest <= angle <= rest
        outbound = self.direction*(angle-rest) >= self.plan['raising_delta_deg']
        baseline = self.plan.get('joint_baseline') or {}
        if baseline:
            rest = 0. if self.spec['directional_calibration'] else baseline['rest_value']
            at_rest = abs(angle-rest) <= 5.
            outbound = self.direction*(angle-rest) >= self.plan['raising_delta_deg']
        elif self.spec['baseline_required']:
            if self.automatic_rest_value is None:
                self.automatic_rest_value = angle
            rest = self.automatic_rest_value
            at_rest = abs(angle-rest) <= 5.
            outbound = self.direction*(angle-rest) >= self.plan['raising_delta_deg']
        if self.phase in ('WAIT_READY', 'REST') and at_rest:
            self.rest_samples.append(angle)
        if self.phase == 'WAIT_READY':
            self.message = self.spec['ready_hint']
            if self._held('ready', at_rest, t, self.plan['ready_s']):
                self.phase, self.message = 'REST', f"准备就绪，正在测量{self.spec['label']}"
        elif self.phase == 'REST':
            self.message = f"正在测量{self.spec['label']}，等待下一次动作"
            if self._held('raise', outbound, t, dwell):
                self._new(t-dwell)
                self.phase, self.message = 'RAISING', f"正在测量{self.spec['label']}出程"
                self._collect(o)
        else:
            self.message = ('正在观察回位' if self.phase == 'LOWERING' else
                            '正在测量本次幅度与停留' if self.phase == 'PEAK_OR_HOLD' else
                            f"正在测量{self.spec['label']}出程")
            peak = max(self.direction*v for v in self.current['samples'].get(self.primary_metric, [angle]))
            if self._held('return', at_rest, t, dwell):
                self._record(t, 'COMPLETE')
                self.phase, self.message = 'REST', f'已记录 {self.completed} 次完整往返'
                self.holds.clear()
            elif not at_rest:
                if self.direction*angle < peak-8:
                    self.phase, self.message = 'LOWERING', '正在观察回位'
                elif self.phase == 'RAISING' and t-self.current['start_time_s'] > .5:
                    self.phase, self.message = 'PEAK_OR_HOLD', '正在测量本次幅度与停留'
        if self.exercise == 'shoulder_adduction':
            if self.phase == 'WAIT_READY':
                self.position_hint = f'请回到侧抬臂起点 {rest:.0f}°，保持约 1 秒；当前 {angle:.0f}°'
            elif self.phase == 'REST' and angle > rest+5.:
                self.position_hint = '当前在向外抬臂；先回到已记录的侧抬臂起点，再向身体内收。'
            elif self.phase in ('RAISING', 'PEAK_OR_HOLD', 'LOWERING'):
                self.message = '正在观察内收与回位；回到侧抬臂起点后计 1 次。'
            if self.position_hint:
                self.message = self.position_hint

    def _sitstand(self, o):
        t, knee, hip = o.time_s, o.value('knee_flexion_deg'), o.value('hip_y')
        c = self.plan['calibration']
        if not all(k in c for k in ('seated_knee', 'standing_knee', 'seated_hip_y', 'standing_hip_y')):
            # Start is deliberately non-blocking. The first clearly measured pose
            # is treated as the prompted seated start, and conservative relative
            # thresholds establish the standing region for this run.
            c.update(seated_knee=knee, standing_knee=max(0., knee-65.),
                     seated_hip_y=hip, standing_hip_y=max(0., hip-.18),
                     automatic=True, method='first-valid-seated-pose-relative-thresholds-1')
            self.automatic_sitstand = True
        seated = knee >= c['seated_knee']-12 and hip >= c['seated_hip_y']-.04
        standing = knee <= c['standing_knee']+10 and hip <= c['standing_hip_y']+.04
        rising = knee < c['seated_knee']-10 and hip < c['seated_hip_y']-.025
        dwell = self.plan['dwell_s']
        if self.phase in ('WAIT_READY', 'SEATED_READY') and seated:
            self.rest_samples.append(knee)
        if self.phase == 'WAIT_READY':
            self.message = '请在已确认的座椅上保持舒适坐位约 1 秒'
            if self._held('sit_ready', seated, t, self.plan['ready_s']):
                self.phase, self.message = 'SEATED_READY', '准备就绪，正在测量居家坐站'
        elif self.phase == 'SEATED_READY':
            if self._held('rise', rising, t, dwell):
                self._new(t-dwell)
                self.phase, self.message = 'RISING', '正在观察起立'
                self._collect(o)
        elif self.phase == 'RISING':
            if self._held('stand', standing, t, dwell):
                self.last_standing_rep = self._record(t, 'COMPLETE')
                self.phase, self.message = 'STANDING_REACHED', f'已完成 {self.completed} 次起立；回坐后才开始下一次'
                self.holds.clear()
            elif self._held('partial', seated, t, dwell):
                self._record(t, 'PARTIAL')
                self.phase, self.message = 'SEATED_READY', '已记录部分起立'
                self.holds.clear()
        elif self.phase == 'STANDING_REACHED':
            if not standing and self._held('lower', knee > c['standing_knee']+15, t, dwell):
                self.phase = 'LOWERING'
                self.lower_start = t-dwell
                if self.standing_timing:
                    self.standing_timing.mark_return(self.holds['lower'])
        elif self.phase == 'LOWERING' and self._held('reseat', seated, t, dwell):
            if self.last_standing_rep is not None:
                self._close_standing_timing(cycle_complete=True)
                duration = self.last_standing_rep['lowering_time_s']
                low, high = self.plan['lowering_tempo_min_s'], self.plan['lowering_tempo_max_s']
                if duration is not None and ((low is not None and duration < low) or (high is not None and duration > high)):
                    self.last_standing_rep['issues'].append({
                        'rule_id': 'lowering_tempo', 'phase': 'LOWERING', 'start_time_s': self.lower_start,
                        'end_time_s': t, 'metric': 'lowering_time_s', 'measured_value': duration,
                        'configured_limit': [low, high], 'evidence_valid': True, 'feedback_emitted_at': None})
            self.phase, self.message = 'SEATED_READY', '已观察回坐，可开始下一次'
            self.holds.clear()

    def finish(self, reason):
        self._record(self.last_t or 0, 'INTERRUPTED', reason)
        self._close_standing_timing(reason)
        self.phase = 'FINISHED'

    def _hold_guidance(self):
        timer = self.current['timing'] if self.current else self.standing_timing
        if not self.previous_valid or not timer or self.timing_plan['hold_min_s'] is None:
            return None
        live = timer.live()
        if not live['at_target'] or live['hold_elapsed_s'] is None:
            return None
        elapsed, target = live['hold_elapsed_s'], self.timing_plan['hold_min_s']
        anchor = '已确认站位范围' if self.exercise == 'sit_to_stand' else '人工角度目标范围'
        if elapsed+1e-8 < target:
            return f'{anchor}内连续观察 {elapsed:.1f} / {target:g} 秒；按本次安排保持，不适时停止'
        return f'已观察到本次连续保持目标 {target:g} 秒；'+self.spec['return_hint']

    def _training_message(self):
        if not self.previous_valid or self.phase == 'FINISHED':
            return self.message
        if self.position_hint:
            return self.position_hint
        if self.phase == 'WAIT_READY':
            return self.message
        hold = self._hold_guidance()
        if hold and self.phase in ('RAISING', 'PEAK_OR_HOLD', 'RISING', 'STANDING_REACHED'):
            return hold
        angle = self.latest_metrics.get(self.primary_metric, {}).get('value')
        target = self.plan['target_angle_deg']
        target_text = '未设置角度目标，按舒适范围活动'
        reached = False
        if target is not None:
            sign = '≥' if self.direction == 1 else '≤'
            target_text = f'人工目标 {sign} {target:g}°'
            # A single raw peak cannot trigger target-reached guidance.
            motion = self.current['angle_evidence'].motion_range() if self.current else None
            if motion:
                measured = motion['max_deg'] if self.direction == 1 else motion['min_deg']
                reached = self.direction*(measured-target) >= 0
        current_text = f'当前 {angle:.0f}°；' if angle is not None else ''
        if self.phase in ('LOWERING', 'STANDING_REACHED'):
            hint = self.spec['return_hint']
        elif self.phase in ('RAISING', 'PEAK_OR_HOLD', 'RISING') and reached:
            hint = ('已观察到目标范围；' + self.spec['return_hint'] if self.exercise != 'sit_to_stand' else
                    '已观察到角度目标；继续按已确认站位完成起立')
        elif self.phase == 'PEAK_OR_HOLD':
            hint = '按舒适幅度完成出程后，' + self.spec['return_hint']
        else:
            hint = self.spec['outbound_hint']
        if self.phase in ('REST', 'SEATED_READY') and self.completed:
            hint = f'已记录 {self.completed} 次；' + hint
        return f'{hint}；{current_text}{target_text}'

    def summary(self):
        duration = (self.last_t-self.first_t) if self.first_t is not None else 0
        current_issues = []
        if self.current and self.phase in ('RAISING', 'PEAK_OR_HOLD'):
            for issue in self.current['issues']:
                metric = self.latest_metrics.get(issue['metric'], {})
                if metric.get('valid') and metric.get('value', 0) > issue['configured_limit']:
                    current_issues.append(copy.deepcopy(issue))
        training = self.plan['submode'] == 'training'
        message = self._training_message() if training else self.message
        if current_issues and training and self.previous_valid:
            labels = {'elbow_flexion': '本次上举时可见屈肘超出已设范围', 'trunk_tilt': '本次上举时可见躯干投影倾斜超出已设范围'}
            message = '；'.join(labels[i['rule_id']] for i in current_issues[:2])
        goal = self.plan['target_reps']*self.plan['target_sets']
        if training and self.completed >= goal and self.previous_valid and not self.standing_timing:
            message = f'已完成计划的 {goal} 次，可停止并保存本次任务'
        motion_range = self.motion_evidence.motion_range()
        timer = self.current['timing'] if self.current else self.standing_timing
        return {'exercise_id': self.exercise, 'joint': self.spec['joint'],
                'movement_timing_version': TIMING_VERSION,
                'movement_timing_live': timer.live() if timer and self.previous_valid and self.phase != 'FINISHED' else None,
                'last_movement_timing': copy.deepcopy(self.repetitions[-1].get('movement_timing')) if self.repetitions else None,
                'primary_metric': self.primary_metric, 'primary_metric_label': self.spec['metric_label'],
                'motion_range': motion_range, 'valid_sample_count': self.motion_evidence.sample_count,
                'motion_range_valid': motion_range is not None,
                'motion_range_reason': None if motion_range else 'insufficient_valid_samples',
                'measurement_type': '2d_projection', 'clinical_rom': False,
                'readiness_note': self.spec['readiness_note'],
                'target_direction': self.spec['target_direction'],
                'completed': self.completed, 'target_met': sum(r['target_status'] == 'MET' for r in self.repetitions),
                'partial': sum(r['completion_status'] == 'PARTIAL' for r in self.repetitions),
                'invalid': sum(r['completion_status'] in ('INTERRUPTED', 'UNASSESSABLE') for r in self.repetitions),
                'valid_s': self.valid_s, 'observed_span_s': duration,
                'valid_ratio': self.valid_s/duration if duration > 0 else None,
                'phase': self.phase, 'message': message, 'metrics': self.latest_metrics,
                'current_issues': current_issues, 'plan_completed': self.completed >= goal,
                'completed_sets': min(self.plan['target_sets'], self.completed//self.plan['target_reps'])}
