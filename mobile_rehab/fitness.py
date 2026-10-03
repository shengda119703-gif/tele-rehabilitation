"""Versioned 2-D video observations, not force estimation or exercise recognition.

The user selects the exercise and visible anatomical side. Thresholds segment
cycles; they are engineering defaults, NOT clinical/sport judging standards.
"""
from __future__ import annotations

import copy
import math
from statistics import mean, pstdev

VERSION = 'fitness-video-1'
SOURCE = 'https://www.acefitness.org/resources/everyone/exercise-library/'
OBSERVABLES = {
    'fitness_squat': ('knee', 'hip', 'torso', 'hip_knee_height'),
    'fitness_deadlift': ('hip', 'knee', 'torso'),
    'fitness_bench_press': ('elbow', 'upper_arm'),
    'fitness_row': ('elbow', 'torso'),
    'fitness_overhead_press': ('elbow', 'upper_arm', 'torso'),
    'fitness_curl': ('elbow', 'upper_arm'),
    'fitness_pushup': ('elbow', 'body_line'),
    'fitness_split_squat': ('knee', 'hip', 'torso'),
}


def exercise(label, group, metric, start, turn, phases, steps, camera, note):
    return dict(label=label, group=group, metric=metric, start_angle=start,
                turn_angle=turn, phases=phases, steps=steps, camera=camera,
                note=note, source=SOURCE, view='sagittal', backend='yolo')


EXERCISES = {
    'fitness_squat': exercise('深蹲', '下肢', 'knee', 155., 105., ['下蹲', '起身'],
        ['站稳，停留 2 秒。', '按平时的幅度下蹲。', '站起后，再做下一次。'],
        '固定侧面机位，肩、髋、膝和踝完整入镜；选择靠近镜头的一侧。',
        '观察膝髋角、躯干倾角和髋膝相对高度；不判断比赛深度、膝内扣或关节受力。'),
    'fitness_deadlift': exercise('硬拉', '下肢', 'hip', 115., 155., ['拉起', '下放'],
        ['俯身握住器械，保持稳定。', '拉起器械，站直。', '缓慢放回起点。'],
        '从正侧面拍摄，肩、髋、膝和踝完整入镜，尽量避免杠铃片遮住关节。',
        '本版按髋开合观察往返，不能区分硬拉变式，不判断腰椎弯曲或杠铃轨迹。'),
    'fitness_bench_press': exercise('卧推', '推', 'elbow', 150., 105., ['下放', '推起'],
        ['做好安全保护，握稳器械。', '缓慢下放器械。', '推回起点，放稳器械后再查看手机。'],
        '侧面机位，与凳面接近同高；测试侧肩、肘、腕清楚入镜，避开杠铃片遮挡。',
        '以肘屈伸观察次数与节奏，不判断触胸、杠铃轨迹、肩胛稳定或保护者助力。'),
    'fitness_row': exercise('俯身划船', '拉', 'elbow', 150., 85., ['拉起', '放回'],
        ['保持俯身，手臂自然伸展。', '拉起器械。', '缓慢放回，保持身体稳定。'],
        '固定侧面机位，肩、肘、腕入镜；髋部入镜时额外观察躯干倾角。',
        '本入口适用于俯身划船，不适用于划船机有氧运动；不推断背部肌肉募集。'),
    'fitness_overhead_press': exercise('肩上推举', '推', 'elbow', 100., 155., ['推起', '下放'],
        ['屈肘握稳器械。', '向上推起器械。', '缓慢放回起点。'],
        '侧面拍摄，肩、肘、腕及举过头顶后的手完整入镜，顶部留足空间。',
        '观察肘伸展与节奏，不判断肩部三维运动、腰椎受力或器械重量。'),
    'fitness_curl': exercise('二头弯举', '拉', 'elbow', 150., 75., ['弯举', '下放'],
        ['手臂自然伸展。', '屈肘举起器械。', '缓慢放下，回到起点。'],
        '侧面拍摄，肩、肘、腕清楚入镜；一次分析指定侧，避免双手互相遮挡。',
        '观察肘屈伸及上臂投影摆幅，不据此估计二头肌发力或肌电。'),
    'fitness_pushup': exercise('俯卧撑', '推', 'elbow', 150., 100., ['下降', '撑起'],
        ['双手撑地，保持身体稳定。', '缓慢下降。', '撑起身体，回到起点。'],
        '手机固定在身体侧面低位；肩、肘、腕入镜，髋和踝可见时观察整体身体线。',
        '计次依据肘屈伸，不判断胸部触地、负重或脊柱节段位置。'),
    'fitness_split_squat': exercise('分腿蹲', '下肢', 'knee', 150., 110., ['下降', '起身'],
        ['双脚前后站稳，选择前腿为测试侧。', '缓慢下蹲。', '起身回位，换腿时另录一段。'],
        '从前腿一侧拍摄，前腿髋、膝、踝完整入镜；本版不分析交替行进弓步。',
        '观察固定站姿前腿的往返，不推断双脚受力比例或平衡能力。'),
}
METRICS = {'knee': '膝关节二维夹角', 'hip': '髋部二维夹角', 'elbow': '肘关节二维夹角',
           'torso': '躯干相对画面竖直倾角', 'upper_arm': '上臂相对画面竖直倾角',
           'body_line': '肩—髋—踝二维夹角', 'hip_knee_height': '髋低于膝的投影高度 / 大腿长度'}


def catalog():
    return [dict(copy.deepcopy(spec), id=eid, rule_version=VERSION,
                 metric_label=METRICS[spec['metric']]) for eid, spec in EXERCISES.items()]


def angle(a, b, c):
    u, v = (a[0]-b[0], a[1]-b[1]), (c[0]-b[0], c[1]-b[1])
    lengths = math.hypot(*u), math.hypot(*v)
    if min(lengths) < 8:
        return None
    return math.degrees(math.acos(max(-1., min(1., sum(x*y for x, y in zip(u, v)) / math.prod(lengths)))))


def measure(person, side, size):
    offset = 0 if side == 'left' else 1
    points = {}
    for name, index in [('shoulder', 5), ('elbow', 7), ('wrist', 9), ('hip', 11), ('knee', 13), ('ankle', 15)]:
        idx = index + offset
        if len(person.xy) <= idx or len(person.conf) <= idx:
            continue
        p, conf = person.xy[idx], person.conf[idx]
        if (len(p) == 2 and math.isfinite(conf) and conf >= .5 and all(math.isfinite(v) for v in p)
                and 0 <= p[0] < size[0] and 0 <= p[1] < size[1]):
            points[name] = p
    metrics = {}
    for key, names in {'knee': ('hip', 'knee', 'ankle'), 'hip': ('shoulder', 'hip', 'knee'),
                       'elbow': ('shoulder', 'elbow', 'wrist'), 'body_line': ('shoulder', 'hip', 'ankle')}.items():
        metrics[key] = angle(*(points[n] for n in names)) if all(n in points for n in names) else None
    for key, names in {'torso': ('hip', 'shoulder'), 'upper_arm': ('elbow', 'shoulder')}.items():
        if all(n in points for n in names):
            a, b = (points[n] for n in names)
            dx, dy = b[0]-a[0], b[1]-a[1]
            metrics[key] = math.degrees(math.atan2(abs(dx), -dy)) if math.hypot(dx, dy) >= 8 else None
    if all(n in points for n in ('hip', 'knee')):
        hip, knee = points['hip'], points['knee']
        length = math.dist(hip, knee)
        metrics['hip_knee_height'] = (hip[1]-knee[1])/length if length >= 8 else None
    return metrics, points


class FitnessEngine:
    GAP = .3
    DWELL = .18

    def __init__(self, exercise_id, side):
        if exercise_id not in EXERCISES or side not in ('left', 'right'):
            raise ValueError('健身动作或观察侧无效')
        self.spec, self.exercise_id, self.side = EXERCISES[exercise_id], exercise_id, side
        self.last_t = self.first_t = None
        self.track = None
        self.center = None
        self.frames = self.valid_frames = self.partial = 0
        self.valid_s = 0.
        self.was_valid = False
        self.smooth = None
        self.ready_since = None
        self.ready = False
        self.current = None
        self.last_rest = None
        self.repetitions, self.series = [], []
        self.values = {k: [] for k in OBSERVABLES[exercise_id]}
        self.reasons = {}
        self.last_plot = -1.
        self.last_context = None

    def reset_cycle(self):
        if self.current:
            self.partial += 1
        self.current = None
        self.ready = False
        self.ready_since = None
        self.last_rest = None
        self.smooth = None

    def choose(self, pose):
        if not pose.people:
            return None
        matching = [p for p in pose.people if self.track is not None and p.track_key == self.track]
        if self.track is not None:
            # Keep the selected tracked person, not the nearest bystander, when
            # the participant is temporarily occluded. Track IDs are not identity.
            return matching[0] if matching else None
        if self.center is not None:
            return min(pose.people, key=lambda p: math.dist(self.center, ((p.bbox[0]+p.bbox[2])/2, (p.bbox[1]+p.bbox[3])/2)))
        return max(pose.people, key=lambda p: max(0., p.bbox[2]-p.bbox[0])*max(0., p.bbox[3]-p.bbox[1]))

    def consume(self, pose):
        if (pose.schema_id != 'coco17-v1' or pose.coordinate_space != 'raw_image_pixels'
                or pose.keypoint_order_version != 'coco17-anatomical-lr-v1'):
            raise ValueError('健身分析的骨架定义不兼容')
        t = pose.time_s
        if t is None or not math.isfinite(t) or (self.last_t is not None and t <= self.last_t):
            raise ValueError('录像时间必须连续递增')
        if self.first_t is None:
            self.first_t = t
        dt = t-self.last_t if self.last_t is not None else 0.
        context_changed = self.last_context is not None and pose.context != self.last_context
        if dt > self.GAP or context_changed:
            self.reset_cycle()
            self.was_valid = False
            self.series.append(dict(t=round(t, 3), angle=None, phase='unobserved'))
        if context_changed:
            self.track = self.center = None
        self.last_t, self.last_context = t, pose.context
        self.frames += 1
        person = self.choose(pose)
        reason = 'no_person' if person is None else ''
        metrics, points = {}, {}
        if person is not None:
            center = ((person.bbox[0]+person.bbox[2])/2, (person.bbox[1]+person.bbox[3])/2)
            changed = self.center is not None and (person.track_key != self.track or
                       math.dist(center, self.center) > .25*math.hypot(*pose.size))
            if changed:
                self.reset_cycle()
                self.was_valid = False
                reason = 'participant_changed'
            self.track, self.center = person.track_key, center
            metrics, points = measure(person, self.side, pose.size)
        value = metrics.get(self.spec['metric'])
        if value is None:
            reason = reason or 'keypoints_missing'
        if reason:
            self.reasons[reason] = self.reasons.get(reason, 0)+1
            self.reset_cycle()
            self.was_valid = False
            self.series.append(dict(t=round(t, 3), angle=None, phase='unobserved'))
            return
        self.valid_frames += 1
        if self.was_valid and dt <= self.GAP:
            self.valid_s += dt
        self.was_valid = True
        for key, val in metrics.items():
            if val is not None and key in self.values:
                self.values[key].append(val)
        alpha = 1-math.exp(-dt/.1) if dt else 1.
        self.smooth = value if self.smooth is None else self.smooth+alpha*(value-self.smooth)
        p = (self.smooth-self.spec['start_angle'])/(self.spec['turn_angle']-self.spec['start_angle'])
        sample = dict(t=round(t, 3), angle=round(self.smooth, 2),
                      points={k: [round(v[0]/pose.size[0], 5), round(v[1]/pose.size[1], 5)] for k, v in points.items()},
                      metrics={k: round(v, 3) for k, v in metrics.items() if v is not None})
        self._advance(p, sample)
        if t-self.last_plot >= .095:
            self.series.append(dict(t=sample['t'], angle=sample['angle'],
                                    phase='moving' if self.current else 'ready' if self.ready else 'waiting'))
            self.last_plot = t

    def _advance(self, progress, sample):
        t = sample['t']
        rest = progress <= 0
        if self.current is not None:
            rep = self.current
            if progress > rep['extreme_progress']:
                rep['extreme_progress'], rep['turn'] = progress, sample
            if progress >= 1:
                if rep['target_since'] is None:
                    rep['target_since'] = t
                if t-rep['target_since'] >= .1-1e-6:
                    rep['reached'] = True
            else:
                rep['target_since'] = None
            if rest:
                if self.ready_since is None:
                    self.ready_since = t
                    rep['end'] = sample
                if t-self.ready_since >= self.DWELL-1e-6:
                    if rep['reached']:
                        self._complete(rep)
                    else:
                        self.partial += 1
                    self.current = None
                    self.ready = True
            else:
                self.ready_since = None
        elif rest:
            if self.ready_since is None:
                self.ready_since = t
            if t-self.ready_since >= self.DWELL-1e-6:
                self.ready = True
            self.last_rest = sample
        elif self.ready and progress > .08:
            self.current = dict(start=self.last_rest, turn=sample, extreme_progress=progress,
                                reached=False, target_since=None, end=None)
            self.ready_since = None
        else:
            self.ready_since = None

    def _complete(self, rep):
        start, turn, end = rep['start'], rep['turn'], rep['end']
        out, back = turn['t']-start['t'], end['t']-turn['t']
        if min(out, back) <= 0:
            self.partial += 1
            return
        span = abs(turn['angle']-start['angle'])
        notes = []
        if self.exercise_id == 'fitness_row':
            values = [s['metrics'].get('torso') for s in (start, turn, end)]
            if all(v is not None for v in values) and max(values)-min(values) > 15:
                notes.append('关键时刻躯干投影倾角变化超过 15°，可回看身体摆动或机位变化；不是伤害风险判定。')
        if self.exercise_id == 'fitness_curl':
            values = [s['metrics'].get('upper_arm') for s in (start, turn, end)]
            if all(v is not None for v in values) and max(values)-min(values) > 20:
                notes.append('关键时刻上臂投影角变化超过 20°，可回看是否存在明显摆臂或机位变化。')
        self.repetitions.append(dict(number=len(self.repetitions)+1, start=start, turn=turn, end=end,
            outbound_s=round(out, 3), return_s=round(back, 3), total_s=round(out+back, 3),
            range_deg=round(span, 2), outbound_mean_angular_rate=round(span/out, 2), notes=notes))
        self.last_rest = end

    def summary(self):
        span = self.last_t-self.first_t if self.last_t is not None else 0.
        durations = [r['total_s'] for r in self.repetitions]
        stats = {k: dict(label=METRICS[k], min=round(min(v), 3), max=round(max(v), 3),
                         samples=len(v), coverage=round(len(v)/self.frames, 3),
                         unit='ratio' if k == 'hip_knee_height' else 'deg')
                 for k, v in self.values.items() if v}
        return dict(completed=len(self.repetitions), partial=self.partial+int(self.current is not None),
            observed_span_s=round(span, 3), valid_ratio=round(self.valid_s/span, 4) if span > 0 else None,
            valid_frames=self.valid_frames, total_frames=self.frames, missing_reasons=self.reasons,
            metrics=stats, mean_cycle_s=round(mean(durations), 3) if durations else None,
            tempo_cv=round(pstdev(durations)/mean(durations), 3) if len(durations) >= 3 else None,
            primary_metric=self.spec['metric'], primary_metric_label=METRICS[self.spec['metric']])
