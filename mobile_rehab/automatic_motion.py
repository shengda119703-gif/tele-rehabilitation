"""Automatic offline trajectories; no user marks, invented mass or camera owner.

Circle candidates use an explicit 0.45 m plate-size prior. Wrist fallback is
relative and never acquires physical units. This is not a muscle-force model.
"""
import math

import cv2
import numpy as np

VERSION = 'automatic-motion-1'
G = 9.80665


def pose_points(pose):
    if pose is None or not pose.people:
        return {}, None
    person = max(pose.people, key=lambda p: max(0, p.bbox[2]-p.bbox[0])*max(0, p.bbox[3]-p.bbox[1]))
    points = {}
    for name, i in dict(nose=0, left_shoulder=5, right_shoulder=6, left_wrist=9,
                        right_wrist=10, left_hip=11, right_hip=12).items():
        if (len(person.xy) > i and len(person.conf) > i and person.conf[i] is not None and person.conf[i] >= .5
                and all(math.isfinite(v) for v in person.xy[i])
                and 0 <= person.xy[i][0] < pose.size[0] and 0 <= person.xy[i][1] < pose.size[1]):
            points[name] = person.xy[i]
    return points, person.track_key


def body_scale(p, w, h):
    for side in ('left', 'right'):
        a, b = p.get(side+'_shoulder'), p.get(side+'_hip')
        if a is not None and b is not None and math.dist(a, b) >= h*.08:
            return math.dist(a, b), 'torso_length', '躯干长度'
    a, b = p.get('left_shoulder'), p.get('right_shoulder')
    if a is not None and b is not None and math.dist(a, b) >= w*.04:
        return math.dist(a, b), 'shoulder_width', '肩宽'
    return h, 'image_height', '画面高度'


def detect_plate(image, points):
    h, w = image.shape[:2]
    scale = min(1., 240/max(w, h))
    small = cv2.resize(image, (round(w*scale), round(h*scale)))
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    circles = cv2.HoughCircles(cv2.GaussianBlur(gray, (5, 5), 0), cv2.HOUGH_GRADIENT,
                              1, 12, param1=80, param2=22,
                              minRadius=8, maxRadius=max(9, min(55, min(gray.shape)//4)))
    if circles is None:
        return None
    wrists = [points[k] for k in ('left_wrist', 'right_wrist') if k in points]
    best = None
    for x, y, r in circles[0][:32]:
        point, radius = [float(x/scale), float(y/scale)], float(r/scale)
        if 'nose' in points and math.dist(point, points['nose']) < radius*1.5:
            continue
        distance = min((math.dist(point, p) for p in wrists), default=0)
        if wrists and distance > max(radius*3, w*.3):
            continue
        # A circle needs radial edge support; arbitrary round body/background
        # patches are not assigned a physical diameter just from a box.
        supported = 0
        for angle in np.arange(24)*math.pi/12:
            strength = 0
            for dr in (-2, -1, 0, 1, 2):
                ix, iy = round(float(x+(r+dr)*math.cos(angle))), round(float(y+(r+dr)*math.sin(angle)))
                if 1 < ix < gray.shape[1]-2 and 1 < iy < gray.shape[0]-2:
                    gx, gy = int(gray[iy, ix+1])-int(gray[iy, ix-1]), int(gray[iy+1, ix])-int(gray[iy-1, ix])
                    strength = max(strength, abs(gx*math.cos(angle)+gy*math.sin(angle)))
            supported += strength > 35
        coverage = supported/24
        score = coverage-distance/max(w, h)*.6
        if coverage >= .7 and (best is None or score > best['score']):
            best = dict(point=point, radius=radius, score=score)
    return best


class AutomaticTracker:
    def __init__(self, side='left'):
        self.side, self.samples, self.total = side, [], 0
        self.pending, self.lock, self.wrist, self.measurement = None, None, None, None
        self.last_t, self.last_size, self.last_identity, self.relative_scale = None, None, None, None
        self.epoch = 0
        self.last_plate = None
        self.fallback_samples, self.fallback_epoch, self.fallback_scale = [], 0, None
        self.wrist_epochs = dict(left_wrist=0, right_wrist=0)

    def consume(self, image, t, pose=None):
        if not math.isfinite(t) or t < 0 or self.last_t is not None and t <= self.last_t:
            return
        h, w = image.shape[:2]
        points, identity = pose_points(pose)
        if ((self.last_size is not None and self.last_size != (w, h))
                or identity is not None and self.last_identity is not None and identity != self.last_identity):
            self.epoch += 1
            self.lock = self.pending = self.relative_scale = None
            self.fallback_epoch += 1
            self.fallback_scale = None
        self.last_t, self.last_size = t, (w, h)
        if identity is not None:
            self.last_identity = identity
        self.total += 1
        # Keep the anatomical fallback independently: a spurious/occluded
        # circle must not erase otherwise usable wrist observations.
        if self.wrist is None:
            self.wrist = next((k for k in (self.side+'_wrist', 'right_wrist', 'left_wrist') if k in points), None)
        if any(k in points for k in ('left_wrist', 'right_wrist')) and self.fallback_scale is None:
            self.fallback_scale = body_scale(points, w, h)
        if self.fallback_scale is not None:
            pixels, source, unit = self.fallback_scale
            for wrist in (self.side+'_wrist', ('left' if self.side == 'right' else 'right')+'_wrist'):
                wrist_point = points.get(wrist)
                previous = next((s for s in reversed(self.fallback_samples[-2:]) if s['measurement']['target_source'] == wrist), None)
                if wrist_point is not None and previous is not None and previous['point'] is not None and math.dist(
                    [wrist_point[0]/w, wrist_point[1]/h],
                    [previous['point'][i]/previous['size'][i] for i in range(2)]) > .3:
                    self.wrist_epochs[wrist] += 1
                if len(self.fallback_samples) < 30000:
                    self.fallback_samples.append(dict(t=float(t), point=wrist_point, scale=pixels, size=[w, h],
                        epoch=(self.fallback_epoch, self.wrist_epochs[wrist]), measurement=dict(target_kind='wrist', target_source=wrist,
                        scale_source=source, length_unit='relative', speed_unit=unit+'/s', mass_kg=None, approximate=False)))
        candidate = detect_plate(image, points)
        point, scale, measurement = None, None, None
        if candidate is not None:
            consistent = (self.pending is not None and math.dist(candidate['point'], self.pending['point']) < w*.15
                          and abs(candidate['radius']/self.pending['radius']-1) < .3)
            candidate['count'] = self.pending['count']+1 if consistent else 1
            self.pending = candidate
            if candidate['count'] >= 3:
                self.last_plate = t
                if self.lock is None or abs(candidate['radius']/self.lock-1) > .3:
                    self.lock = candidate['radius']
                    self.epoch += 1
                point, scale = candidate['point'], 2*self.lock/.45
                measurement = dict(target_kind='plate', target_source='opencv_circle_candidate',
                                   scale_source='plate_diameter_prior', reference_length_m=.45,
                                   length_unit='m', speed_unit='m/s', mass_kg=None, approximate=True)
        else:
            self.pending = None
        if self.lock is not None and self.last_plate is not None and t-self.last_plate > 1.2:
            self.lock = self.relative_scale = None
            self.epoch += 1
        if self.lock is None:
            if self.wrist is None:
                self.wrist = next((k for k in (self.side+'_wrist', 'right_wrist', 'left_wrist') if k in points), None)
            point = points.get(self.wrist)
            pixels, source, unit = body_scale(points, w, h)
            if self.relative_scale is None or self.relative_scale[1] != source:
                self.relative_scale = pixels, source
            scale = self.relative_scale[0]
            measurement = dict(target_kind='wrist', target_source=self.wrist, scale_source=source,
                               length_unit='relative', speed_unit=unit+'/s', mass_kg=None, approximate=False)
        if measurement is not None:
            if self.measurement is not None and any(measurement[k] != self.measurement[k] for k in ('target_kind', 'scale_source')):
                self.epoch += 1
            self.measurement = measurement
        before = self.samples[-1] if self.samples else None
        if (point is not None and before is not None and before['point'] is not None
                and measurement is not None and measurement['target_kind'] == 'wrist'
                and math.dist([point[0]/w, point[1]/h], [before['point'][i]/before['size'][i] for i in range(2)]) > .3):
            self.epoch += 1
        if len(self.samples) < 15000:
            self.samples.append(dict(t=float(t), point=point, scale=scale, size=[w, h],
                                     epoch=self.epoch, measurement=self.measurement))

    def report(self):
        groups = {}
        for s in [s for s in self.samples if s['measurement'] and s['measurement']['target_kind'] == 'plate'] + self.fallback_samples:
            m = s['measurement']
            if m is not None:
                key = m['target_kind'], m.get('target_source'), m['scale_source']
                group = groups.setdefault(key, dict(measurement=m, samples=[], valid=0))
                group['samples'].append(s)
                group['valid'] += s['point'] is not None
        reports = [(g, summarize(g['samples'], g['measurement'], self.total)) for g in groups.values()]
        # A few background circles cannot outrank a full wrist trajectory.
        plates = [r for g, r in reports if g['measurement']['target_kind'] == 'plate'
                  and g['valid'] >= max(5, self.total*.5)
                  and sum(s['velocity_m_s'] is not None for s in r['series']) >= max(3, self.total*.3)]
        if plates:
            return max(plates, key=lambda r: r['summary']['tracked_ratio'])
        wrists = [r for g, r in reports if g['measurement']['target_kind'] == 'wrist']
        if wrists:
            return max(wrists, key=lambda r: r['summary']['tracked_ratio'])
        return summarize([], None, self.total)


def summarize(samples, measurement, total=None):
    metric = measurement is not None and measurement.get('length_unit') == 'm'
    series, parts, part, origin, last = [], [], [], None, None
    for s in samples:
        valid = s['point'] is not None and s['scale'] is not None and s['scale'] > 0
        if part and (not valid or s['epoch'] != last['epoch'] or s['t']-last['t'] > .3):
            parts.append(part)
            part, origin = [], None
        row = dict(t=s['t'], point=[v/s['size'][i] for i, v in enumerate(s['point'])] if valid else None,
                   height=None, x=None, velocity=None, acceleration=None)
        if valid:
            if origin is None:
                origin = s['point']
            row.update(height=(origin[1]-s['point'][1])/s['scale'], x=(s['point'][0]-origin[0])/s['scale'])
            part.append(row)
        series.append(row)
        last = s
    if part:
        parts.append(part)
    for part in parts:
        for index, row in enumerate(part):
            neighbors = part[max(0, index-120):index+121]
            interval = float(np.median(np.diff([r['t'] for r in neighbors]))) if len(neighbors) > 1 else 0
            radius = min(.6, max(.28, 2.1*interval))
            window = [r for r in neighbors if abs(r['t']-row['t']) <= radius]
            if len(window) < 5 or row is window[0] or row is window[-1]:
                continue
            times = np.array([r['t']-row['t'] for r in window])
            heights = np.array([r['height'] for r in window])
            coef = np.polyfit(times, heights, 2)
            residual = float(np.sqrt(np.mean((np.polyval(coef, times)-heights)**2)))
            row.update(velocity=float(coef[1]), acceleration=float(2*coef[0]) if residual < .025 else None)
    lifts = []
    for part in parts:
        run, previous, known = [], None, False
        def finish(bounded):
            nonlocal run
            if len(run) >= 3:
                first, end = run[0], run[-1]
                duration, displacement = end['t']-first['t'], end['height']-first['height']
                if duration >= .15 and displacement >= (.025 if metric else .04):
                    peak = max(run, key=lambda r: r['velocity'])
                    lifts.append(dict(number=len(lifts)+1, bounded=bool(known and bounded),
                        duration_s=duration, displacement=displacement, mean_velocity=displacement/duration,
                        peak_velocity=peak['velocity'], peak_time_s=peak['t'], time_to_peak_s=peak['t']-first['t'],
                        mean_specific_power_w_kg=G*displacement/duration if metric else None,
                        displacement_m=displacement if metric else None,
                        mean_velocity_m_s=displacement/duration if metric else None,
                        peak_velocity_m_s=peak['velocity'] if metric else None))
            run = []
        for row in part:
            threshold = .03 if metric else .06
            if row['velocity'] is not None and row['velocity'] > threshold:
                if not run:
                    known = previous is not None and previous['velocity'] is not None and previous['velocity'] <= threshold
                run.append(row)
            else:
                finish(row['velocity'] is not None)
            previous = row
        finish(False)
    speeds = [r['mean_velocity'] for r in lifts if r['bounded']]
    valid = [r for r in series if r['velocity'] is not None]
    positive = [r['velocity'] for r in valid if r['velocity'] > 0]
    peak = max(positive) if positive else None
    output = [dict(t=r['t'], point=r['point'], x_m=r['x'] if metric else None,
                   height_m=r['height'] if metric else None, velocity_m_s=r['velocity'] if metric else None,
                   acceleration_m_s2=r['acceleration'] if metric else None,
                   relative_height=None if metric else r['height'], relative_velocity=None if metric else r['velocity'],
                   force_n=None, power_w=None,
                   specific_lifting_power_w_kg=G*max(0, r['velocity']) if metric and r['velocity'] is not None else None)
              for r in series]
    return dict(version=VERSION, automatic=True, synthetic=False,
        measurement=measurement or dict(target_kind='unavailable', length_unit='relative', speed_unit='画面高度/s'),
        calibration=dict(mode='automatic', length_m=measurement.get('reference_length_m') if measurement else None, mass_kg=None),
        summary=dict(bounded_segments=len(speeds), tracked_ratio=sum(r['point'] is not None for r in series)/(total or len(samples) or 1),
                     peak_velocity_m_s=peak if metric else None, peak_relative_velocity=None if metric else peak,
                     peak_force_n=None, peak_power_w=None,
                     peak_specific_lifting_power_w_kg=G*peak if metric and peak is not None else None,
                     last_vs_best_velocity_loss_pct=100*(1-speeds[-1]/max(speeds)) if len(speeds) >= 2 else None),
        lifts=lifts, series=output, stop_reason='' if valid else '本段未取得连续轨迹，动作分析已保留。',
        assumptions=['自动圆形器械候选，按45厘米直径换算；未确认器械规格，长度与速度为近似值。' if metric else '手腕运动轨迹，不代表器械或人体重心。',
                     '单位负重抬升功率=g×上升速度，仅表示竖直重力功率分量。' if metric else '相对轨迹按实际可见躯干、肩宽或画面高度归一化，不换算米、牛顿或瓦。',
                     '重量未知时不推断重量；遮挡、尺度变化及时间缺口分段，不补轨迹。'])
