"""Calibrated planar LOAD observations. Never measures muscle force or joint torque."""
import math

import cv2
import numpy as np

VERSION = 'barbell-planar-1'
SUPPORTED = {'fitness_squat', 'fitness_deadlift', 'fitness_bench_press', 'fitness_row',
             'fitness_overhead_press', 'fitness_curl', 'fitness_split_squat'}


def validate_calibration(value):
    if not isinstance(value, dict) or value.get('confirmed') is not True:
        raise ValueError('请确认固定机位、真实长度和自由重量条件')
    def number(v, lo, hi):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not lo <= v <= hi:
            raise ValueError('器械标定参数无效')
        return float(v)
    size = value.get('size', [])
    if not isinstance(size, list) or len(size) != 2:
        raise ValueError('缺少标定画面尺寸')
    size = [int(number(v, 128, 4096)) for v in size]
    points = []
    for key in ('reference_a', 'reference_b', 'target'):
        p = value.get(key)
        if not isinstance(p, list) or len(p) != 2:
            raise ValueError('请在第一帧标记长度两端和器械跟踪点')
        points.append([number(v, 0, 1) for v in p])
    a, b, target = points
    pixels = math.dist([a[i]*size[i] for i in range(2)], [b[i]*size[i] for i in range(2)])
    if pixels < 30:
        raise ValueError('标定长度在画面中至少需要 30 像素，请选择更长的参照物')
    length = number(value.get('length_m'), .05, 3.)
    mass = value.get('mass_kg')
    if mass is not None:
        mass = number(mass, .1, 500.)
    return dict(size=size, reference_a=a, reference_b=b, target=target,
                length_m=length, mass_kg=mass, meters_per_pixel=length/pixels, confirmed=True)


class BarTracker:
    """Fixed first-frame patch, bounded NCC search. No guessed reacquisition."""
    def __init__(self, calibration):
        self.calibration = validate_calibration(calibration)
        self.samples, self.template = [], None
        self.reason, self.last_t = '', None
        self.center = None

    def consume(self, image, t):
        h, w = image.shape[:2]
        if self.reason:
            self.samples.append(dict(t=t, x=None, y=None))
            return
        if [w, h] != self.calibration['size']:
            self.reason = '标定与解码画面尺寸不同，请使用普通横屏录像重新标定。'
        elif self.last_t is not None and (t <= self.last_t or t-self.last_t > .15):
            self.reason = '跟踪时间不连续，本段器械分析停止；人体分析仍保留。'
        if self.reason:
            self.samples.append(dict(t=t, x=None, y=None))
            return
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        if self.template is None:
            self.radius = max(6, round(min(w, h)*.025))
            x, y = [round(v*s) for v, s in zip(self.calibration['target'], (w, h))]
            r = self.radius
            if x-r < 0 or y-r < 0 or x+r >= w or y+r >= h:
                self.reason = '跟踪点太靠近边缘，请选择画面内的器械标记。'
            else:
                self.template = gray[y-r:y+r+1, x-r:x+r+1].copy()
                if self.template.std() < 12:
                    self.reason = '标记对比不足；可在器械端部贴醒目的十字胶带后重新拍摄。'
            self.center = (x, y)
            score = 1.
        else:
            r = self.radius
            dt = t-self.last_t
            reach = min(round(min(w, h)*.25), max(r*2, round(4*dt/self.calibration['meters_per_pixel'])))
            x, y = self.center
            left, top = max(0, x-reach-r), max(0, y-reach-r)
            right, bottom = min(w, x+reach+r+1), min(h, y+reach+r+1)
            scores = cv2.matchTemplate(gray[top:bottom, left:right], self.template, cv2.TM_CCOEFF_NORMED)
            _, score, _, loc = cv2.minMaxLoc(scores)
            lx, ly = loc
            alternatives = scores.copy()
            alternatives[max(0, ly-r):ly+r+1, max(0, lx-r):lx+r+1] = -1
            ambiguous = float(alternatives.max()) > score-.08
            if score < .7 or ambiguous:
                self.reason = '器械标记丢失或出现相似目标；缺失后不猜测轨迹，请回看并重录。'
            else:
                self.center = (left+lx+r, top+ly+r)
        self.last_t = t
        x, y = self.center
        self.samples.append(dict(t=float(t), x=None if self.reason else float(x),
                                 y=None if self.reason else float(y), match=round(score, 3)))

    def report(self):
        return analyze_track(self.samples, self.calibration, self.reason)


def analyze_track(samples, calibration, reason='', synthetic=False):
    """Local quadratic regression on contiguous media timestamps; upward is positive."""
    c = validate_calibration(calibration)
    scale, mass = c['meters_per_pixel'], c['mass_kg']
    data, groups, group = [], [], []
    origin = next((s for s in samples if s['y'] is not None), None)
    for sample in samples:
        valid = sample['y'] is not None and sample['x'] is not None
        if group and (not valid or sample['t']-group[-1]['t'] > .15):
            groups.append(group)
            group = []
        row = dict(t=round(sample['t'], 4), x_m=None, height_m=None, velocity_m_s=None,
                   acceleration_m_s2=None, force_n=None, power_w=None)
        if valid:
            row.update(x_m=(sample['x']-origin['x'])*scale,
                       height_m=(origin['y']-sample['y'])*scale,
                       point=[sample['x']/c['size'][0], sample['y']/c['size'][1]])
            group.append(row)
        data.append(row)
    if group:
        groups.append(group)
    for part in groups:
        times = np.array([s['t'] for s in part])
        heights = np.array([s['height_m'] for s in part])
        if len(times) < 7:
            continue
        fps = 1/float(np.median(np.diff(times)))
        for i, row in enumerate(part):
            # Centered windows only: no exaggerated derivative at clip/gap edges.
            if times[i]-times[0] < .17 or times[-1]-times[i] < .17:
                continue
            mask = np.abs(times-times[i]) <= .18+1e-6
            if mask.sum() < 7:
                continue
            local_t = times[mask]-times[i]
            coef = np.polyfit(local_t, heights[mask], 2)
            residual = float(np.sqrt(np.mean((np.polyval(coef, local_t)-heights[mask])**2)))
            row['height_m'] = float(coef[2])
            row['velocity_m_s'] = float(coef[1])
            if fps >= 20 and residual <= .01:
                row['acceleration_m_s2'] = float(2*coef[0])
                if mass is not None:
                    row['force_n'] = mass*(9.80665+row['acceleration_m_s2'])
                    row['power_w'] = row['force_n']*row['velocity_m_s']
    lifts, rising = [], []
    def finish(end_known):
        nonlocal rising
        if len(rising) >= 4:
            start, end = rising[0], rising[-1]
            dt = end['t']-start['t']
            height = end['height_m']-start['height_m']
            if dt >= .2 and height >= .04:
                peak = max(rising, key=lambda s: s['velocity_m_s'])
                force = [s['force_n'] for s in rising if s['force_n'] is not None]
                power = [s['power_w'] for s in rising if s['power_w'] is not None]
                lifts.append(dict(number=len(lifts)+1, start_s=start['t'], end_s=end['t'],
                    bounded=bool(end_known and rising_start_known), displacement_m=height,
                    duration_s=dt, mean_velocity_m_s=height/dt,
                    peak_velocity_m_s=peak['velocity_m_s'], peak_time_s=peak['t'],
                    time_to_peak_s=peak['t']-start['t'],
                    peak_force_n=max(force) if len(force)==len(rising) else None,
                    peak_power_w=max(power) if len(power)==len(rising) else None))
        rising = []
    previous, rising_start_known = None, False
    for row in data:
        v = row['velocity_m_s']
        continuous = previous is not None and row['t']-previous['t'] <= .15
        if v is not None and v > .05:
            if not continuous:
                finish(False)
            if not rising:
                rising_start_known = continuous and previous['velocity_m_s'] is not None and previous['velocity_m_s'] <= .05
            rising.append(row)
        else:
            finish(continuous and v is not None)
        previous = row
    finish(False)
    complete = [r for r in lifts if r['bounded']]
    mean_speeds = [r['mean_velocity_m_s'] for r in complete]
    summary = dict(upward_segments=len(lifts), bounded_segments=len(complete),
        tracked_ratio=sum(s['y'] is not None for s in samples)/len(samples) if samples else 0,
        peak_velocity_m_s=max((r['peak_velocity_m_s'] for r in complete), default=None),
        peak_force_n=max((r['peak_force_n'] for r in complete if r['peak_force_n'] is not None), default=None),
        peak_power_w=max((r['peak_power_w'] for r in complete if r['peak_power_w'] is not None), default=None),
        last_vs_best_velocity_loss_pct=100*(1-mean_speeds[-1]/max(mean_speeds)) if len(mean_speeds)>=2 else None)
    for row in data:
        for key, value in row.items():
            if isinstance(value, float):
                row[key] = round(value, 5)
    return dict(version=VERSION, source='SYNTHETIC / TEST' if synthetic else 'CALIBRATED_VIDEO_ESTIMATE',
        synthetic=synthetic, calibration=c, summary=summary, lifts=lifts, series=data, stop_reason=reason,
        assumptions=['固定水平侧面机位；标尺与器械处于同一运动平面；无变焦、慢放或剪辑。',
                     '跟踪点是器械平移标记，不是旋转配重片边缘；长度、重量由用户提供。',
                     '外力与功率仅针对填写的自由器械总质量，假设仅重力与举起作用；不适用于滑轮、弹力带、器械架接触或他人助力。',
                     'F竖直=m(g+a)，P竖直=F竖直×v。不是肌肉力量、关节力矩、全身功率或测力台读数。',
                     '峰速、峰值器械功率、达到峰速时间仅是本次爆发力相关观察；没有通用等级或诊断评分。',
                     '导数采用约0.36秒窗口平滑，会削弱短时峰值；低帧率或噪声较大时不提供力与功率。'])


def demo_report():
    c = dict(size=[1000, 1000], reference_a=[.1,.2], reference_b=[.1,.7],
             target=[.5,.7], length_m=.5, mass_kg=40., confirmed=True)
    samples=[]
    for i in range(601):
        t=i/60
        height=0.
        for start, duration in [(1.,1.),(4.,1.25),(7.,1.5)]:
            if start <= t <= start+2*duration:
                height=.25*(1-math.cos(math.pi*(t-start)/duration))
                break
        samples.append(dict(t=t,x=500.,y=700-height*1000))
    return analyze_track(samples,c,synthetic=True)
