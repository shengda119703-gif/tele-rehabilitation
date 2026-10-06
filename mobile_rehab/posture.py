"""Independent 2-D posture observations. No diagnostic thresholds or pelvic tilt.

COCO hip points are hip centres, not ASIS/PSIS. Ear/shoulder projection is not
a craniovertebral angle (C7 is unavailable). All units refer to image geometry.
"""
import math
from statistics import median

VERSION = 'posture-projection-1'
TASKS = {
    'posture_front': dict(label='正面体态', view='frontal', steps=[
        '手机放平，镜头与身体正对。', '自然站立，双肩、髋、膝和脚踝入镜。', '保持平时站姿，录制 5–10 秒。']),
    'posture_side': dict(label='侧面体态', view='sagittal', steps=[
        '手机放平，从身体正侧面拍摄。', '选择靠近镜头的一侧，耳、肩、髋、膝和踝入镜。', '自然站立，目视前方，录制 5–10 秒。']),
}
METRICS = {
    'shoulder_level': ('双肩连线倾角', '°', '双肩连线与画面水平的夹角。'),
    'hip_level': ('双髋连线倾角', '°', '双髋中心连线与画面水平的夹角，不是骨盆前倾角。'),
    'trunk_lean': ('躯干偏离竖直', '°', '肩部到髋部的连线偏离画面竖直的角度。'),
    'head_offset': ('耳肩水平偏移', '%', '耳与肩的水平距离，占肩髋长度的比例；不区分前后，不诊断头前伸。'),
    'knee_angle': ('膝部侧面夹角', '°', '髋、膝和踝形成的二维夹角，不用于判断膝过伸。'),
}


def catalog():
    return [dict(id=k, **v) for k, v in TASKS.items()]


def measure(person, size, view, side):
    from .fitness import angle
    def p(i):
        if person is None or len(person.xy) <= i or len(person.conf) <= i:
            return None
        point, confidence = person.xy[i], person.conf[i]
        if (not isinstance(confidence, (int, float)) or not math.isfinite(confidence)
                or confidence < .5 or len(point) != 2
                or not all(math.isfinite(x) for x in point)
                or not 0 <= point[0] < size[0] or not 0 <= point[1] < size[1]):
            return None
        return point
    def line(a, b, horizontal=False):
        if a is None or b is None or math.dist(a, b) < 8:
            return None
        dx, dy = abs(a[0]-b[0]), abs(a[1]-b[1])
        return math.degrees(math.atan2(dy, dx) if horizontal else math.atan2(dx, dy))
    if view == 'frontal':
        shoulders, hips = (p(5), p(6)), (p(11), p(12))
        mid = lambda pair: [(pair[0][i]+pair[1][i])/2 for i in (0, 1)] if all(x is not None for x in pair) else None
        return dict(shoulder_level=line(*shoulders, True), hip_level=line(*hips, True),
                    trunk_lean=line(mid(shoulders), mid(hips)))
    offset = 0 if side == 'left' else 1
    ear, shoulder, hip, knee, ankle = (p(i+offset) for i in (3, 5, 11, 13, 15))
    length = math.dist(shoulder, hip) if shoulder is not None and hip is not None else 0
    return dict(trunk_lean=line(shoulder, hip),
                head_offset=100*abs(ear[0]-shoulder[0])/length if ear is not None and length >= 30 else None,
                knee_angle=angle(hip, knee, ankle) if all(x is not None for x in (hip, knee, ankle)) else None)


class PostureEngine:
    def __init__(self, exercise, side):
        self.spec, self.side = TASKS[exercise], side
        self.frames, self.track, self.last_t = 0, None, None
        self.samples = {k: [] for k in (('shoulder_level', 'hip_level', 'trunk_lean')
                        if self.spec['view'] == 'frontal' else ('trunk_lean', 'head_offset', 'knee_angle'))}

    def consume(self, pose):
        if pose.schema_id != 'coco17-v1' or pose.coordinate_space != 'raw_image_pixels':
            raise ValueError('体态关键点定义不匹配')
        if pose.time_s is None or not math.isfinite(pose.time_s) or (self.last_t is not None and pose.time_s <= self.last_t):
            raise ValueError('录像时间无效')
        self.last_t = pose.time_s
        self.frames += 1
        if self.track is None:
            person = max((p for p in pose.people if p.track_key is not None),
                         key=lambda p: max(0, p.bbox[2]-p.bbox[0])*max(0, p.bbox[3]-p.bbox[1]), default=None)
            if person:
                self.track = person.track_key
        else:
            person = next((p for p in pose.people if p.track_key == self.track), None)
        values = measure(person, pose.size, self.spec['view'], self.side)
        for key, value in values.items():
            if value is not None:
                self.samples[key].append((pose.time_s, value))

    def summary(self):
        rows = []
        for key, samples in self.samples.items():
            label, unit, note = METRICS[key]
            # Require a continuous observed window, not samples either side of a disappearance.
            runs, run = [], []
            for t, value in samples:
                if run and t-run[-1][0] > .5:
                    runs.append(run)
                    run = []
                run.append((t, value))
            runs.append(run)
            usable = max(runs, key=lambda x: x[-1][0]-x[0][0] if x else 0)
            valid = len(usable) >= 10 and usable[-1][0]-usable[0][0] >= 2
            values = [v for _, v in usable]
            center = median(values) if valid else None
            rows.append(dict(key=key, label=label, unit=unit, value=round(center, 2) if valid else None,
                valid=valid, reason=None if valid else '请保持自然站姿，连续录制至少 5 秒',
                sample_count=len(usable), coverage=round(len(samples)/max(1, self.frames), 3),
                variation=round(median(abs(v-center) for v in values), 2) if valid else None, note=note))
        return dict(metrics=rows, frames=self.frames, valid_metrics=sum(r['valid'] for r in rows),
                    note='结果反映画面中的站姿。机位倾斜、遮挡和主动摆姿都会影响读数。')
