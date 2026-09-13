from __future__ import annotations

import math
from .domain import Metric, Observation
from .geometry import angle_deg
from .landmark_schemas import SCHEMAS, ORDERS
from .exercises import exercise_spec


def signed_angle(a, b):
    if min(math.hypot(*a), math.hypot(*b)) < 1.:
        return None
    return math.degrees(math.atan2(a[0]*b[1]-a[1]*b[0], a[0]*b[0]+a[1]*b[1]))


def angle_delta(value, reference):
    return (value-reference+180) % 360-180


class PoseAnalyzer:
    def __init__(self, side='left', conf_min=.5, tau=.12, max_gap=.5, exercise_id=None, joint_baseline=None,
                 auxiliary_view=None):
        self.side, self.conf_min, self.tau, self.max_gap = side, conf_min, tau, max_gap
        self.previous = {}
        self.previous_track = None
        self.focus_context = None
        self.focus_model_track = None
        self.focus_center = None
        self.focus_key = None
        self.focus_number = 0
        self.exercise_id = exercise_id
        self.joint_baseline = joint_baseline or {}
        self.automatic_rest_value = None
        self.automatic_direction_sign = None
        if auxiliary_view not in (None, 'frontal', 'sagittal'):
            raise ValueError('辅助视角不明确')
        self.auxiliary_view = auxiliary_view

    def analyze(self, frame):
        if (frame.schema_id not in SCHEMAS or frame.coordinate_space != 'raw_image_pixels'
                or frame.keypoint_order_version != ORDERS.get(frame.schema_id)):
            raise ValueError('骨架 schema / 坐标系 / 关节顺序不兼容')
        t = frame.time_s
        if t is None or not math.isfinite(t):
            raise ValueError('视频时间不可用，不能计时')
        if not frame.people:
            self.previous.clear()
            return Observation(t, None, 'NO_PERSON_DETECTED', {}, size=frame.size,
                               reasons=['no_person_detected'])
        w, h = frame.size
        if w <= 0 or h <= 0:
            raise ValueError('画面尺寸不可用')
        context = frame.context
        focus_context = ((context.generation, context.scene_id, context.source_ref,
                          context.source_kind, context.usage_context, context.run_id), frame.schema_id)
        if focus_context != self.focus_context:
            self.focus_context = focus_context
            self.focus_model_track = self.focus_center = self.focus_key = None
            self.automatic_rest_value = self.automatic_direction_sign = None
        def center(person):
            x1, y1, x2, y2 = person.bbox
            return ((x1+x2)/2, (y1+y2)/2)
        def area(person):
            x1, y1, x2, y2 = person.bbox
            return max(0., x2-x1)*max(0., y2-y1)
        matching = next((person for person in frame.people
                         if self.focus_model_track is not None and person.track_key == self.focus_model_track), None)
        if matching is not None:
            p = matching
        elif self.focus_center is not None:
            # A tracker id may be reacquired. Continue with the spatially nearest
            # candidate rather than blocking the whole task because a carer is visible.
            p = min(frame.people, key=lambda person: math.dist(center(person), self.focus_center))
        else:
            image_center = (w/2, h/2)
            p = max(frame.people, key=lambda person: (area(person), -math.dist(center(person), image_center)))
        selected_center = center(p)
        changed_focus = (self.focus_center is not None and matching is None and
                         math.dist(selected_center, self.focus_center) > .25*math.hypot(w, h))
        if self.focus_key is None or changed_focus:
            self.focus_number += 1
            self.focus_key = f'focus:{self.focus_number}'
            self.previous.clear()
            self.automatic_rest_value = self.automatic_direction_sign = None
        self.focus_model_track = p.track_key
        self.focus_center = selected_center
        selected_track = self.focus_key
        names = SCHEMAS[frame.schema_id]
        if len(p.xy) != len(names) or len(p.conf) != len(names):
            raise ValueError('关键点数量不符合骨架契约')
        track_context = (frame.context, frame.schema_id, selected_track)
        if track_context != self.previous_track:
            self.previous.clear()
            self.previous_track = track_context
        points, reasons = {}, {}
        for i, (point, confidence) in enumerate(zip(p.xy, p.conf)):
            hand_point = frame.schema_id == 'mediapipe-hand21-v1' or (frame.schema_id == 'mediapipe-wrist54-v1' and i >= 33)
            if len(point) != 2 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in point):
                reasons[i] = 'nonfinite'
            elif not hand_point and (confidence is None or not isinstance(confidence, (int, float)) or not math.isfinite(confidence)):
                reasons[i] = 'confidence_unavailable'
            elif not hand_point and confidence < self.conf_min:
                reasons[i] = 'low_confidence'
            elif not (0 < point[0] < w and 0 < point[1] < h):
                reasons[i] = 'out_of_frame'
            else:
                previous = self.previous.get(i)
                raw = (float(point[0]), float(point[1]))
                if previous and 0 < t - previous[0] <= self.max_gap:
                    dt = t - previous[0]
                    if math.dist(raw, previous[2]) > math.hypot(w, h) * .35:
                        reasons[i] = 'coordinate_jump'
                        self.previous.pop(i, None)
                        continue
                    a = 1 - math.exp(-dt / self.tau)
                    points[i] = tuple(previous[1][j] + a * (raw[j] - previous[1][j]) for j in (0, 1))
                else:
                    points[i] = raw
                first_seen = previous[3] if previous and 0 < t-previous[0] <= self.max_gap else t
                self.previous[i] = (t, points[i], raw, first_seen)
                if hand_point and t-first_seen < .15:
                    points.pop(i, None)
                    reasons[i] = 'hand_temporal_warmup'
            if i in reasons:
                if reasons[i] != 'hand_temporal_warmup':
                    self.previous.pop(i, None)

        def measured(ids, fn):
            ids = [names.index(i) if isinstance(i, str) and i in names else -1 if isinstance(i, str) else i for i in ids]
            missing = [f'{i}:{reasons.get(i, "missing")}' for i in ids if i not in points]
            if missing:
                return Metric.missing(','.join(missing))
            return Metric.of(fn(*(points[i] for i in ids)))

        sh, el, wr, hi, kn, an = [self.side+'_'+n for n in ('shoulder', 'elbow', 'wrist', 'hip', 'knee', 'ankle')]

        def flexion(a, b, c):
            angle = angle_deg(a, b, c)
            return None if angle is None else 180 - angle

        def tilt(ls, rs, lh, rh):
            dx, dy = (ls[0]+rs[0]-lh[0]-rh[0])/2, (ls[1]+rs[1]-lh[1]-rh[1])/2
            return None if math.hypot(dx, dy) < 1e-8 else math.degrees(math.atan2(abs(dx), abs(dy)))

        def hip_abduction(hip, other_hip, knee):
            # Pelvis-relative signed projection. Outward is positive; shoulders
            # do not participate, so trunk tilt cannot masquerade as a hip angle.
            outward = (hip[0]-other_hip[0], hip[1]-other_hip[1])
            thigh = (knee[0]-hip[0], knee[1]-hip[1])
            width, length = math.hypot(*outward), math.hypot(*thigh)
            if width < 1. or length < 1. or abs(outward[0]) < 1.:
                return None
            outward = tuple(v/width for v in outward)
            down = (-outward[1], outward[0])
            if down[1] < 0:
                down = tuple(-v for v in down)
            return math.degrees(math.atan2(
                sum(thigh[i]*outward[i] for i in (0, 1)),
                sum(thigh[i]*down[i] for i in (0, 1))))

        def arm_raise(shoulder, elbow):
            # Fixed image vertical removes the hip from shoulder tasks. A fixed
            # camera and stable torso remain setup requirements, not hidden points.
            return angle_deg((shoulder[0], shoulder[1]+100.), shoulder, elbow)

        metrics = {
            'raise_deg': measured([sh, el], arm_raise),
            'elbow_flexion_deg': measured([sh, el, wr], flexion),
            'knee_flexion_deg': measured([hi, kn, an], flexion),
            'hip_abduction_deg': measured([hi, 'right_hip' if self.side == 'left' else 'left_hip', kn], hip_abduction),
            'trunk_tilt_deg': measured(['left_shoulder', 'right_shoulder', 'left_hip', 'right_hip'], tilt),
            'hip_y': measured([hi], lambda a: a[1]/h),
            'left_knee': measured(['left_hip', 'left_knee', 'left_ankle'], flexion),
            'right_knee': measured(['right_hip', 'right_knee', 'right_ankle'], flexion),
            'ankle_delta': measured(['left_ankle', 'right_ankle'], lambda a, b: (a[0]-b[0])/w),
            'shoulder_sagittal_raw_deg': measured([sh, el], lambda a,b: signed_angle(
                (0., 1.), (b[0]-a[0], b[1]-a[1]))),
            'hip_sagittal_raw_deg': measured([sh, hi, kn], lambda a,b,c: signed_angle(
                (b[0]-a[0], b[1]-a[1]), (c[0]-b[0], c[1]-b[1]))),
        }
        if frame.schema_id in ('mediapipe33-v1', 'mediapipe-wrist54-v1'):
            def ankle(k,a,h,f):
                if math.dist(k,a) < 20 or math.dist(h,f) < 15:
                    return None
                return signed_angle((k[0]-a[0], k[1]-a[1]), (f[0]-h[0], f[1]-h[1]))
            metrics['ankle_raw_deg'] = measured([kn, an, self.side+'_heel', self.side+'_foot_index'],
                                                ankle)
        if frame.schema_id == 'mediapipe-wrist54-v1':
            def wrist(e, w, hw, m):
                if math.dist(w, hw) > .08*math.hypot(*frame.size) or math.dist(hw, m) < 20:
                    return None
                return signed_angle((w[0]-e[0], w[1]-e[1]), (m[0]-hw[0], m[1]-hw[1]))
            metrics['wrist_raw_deg'] = measured([el, wr, 'hand_wrist', 'hand_middle_mcp'], wrist)
        if frame.schema_id == 'mediapipe-hand21-v1':
            metrics = {}
            # The SDK exposes no per-landmark confidence. Geometric and temporal
            # checks are limited engineering guards, never an occlusion guarantee.
            def finger_angle(a,b,c):
                if min(math.dist(a,b), math.dist(b,c)) < 4:
                    return None
                return flexion(a,b,c)
            for finger in ('thumb', 'index', 'middle', 'ring', 'pinky'):
                joints = ('mcp', 'ip') if finger == 'thumb' else ('mcp', 'pip', 'dip')
                for joint in joints:
                    i = names.index(finger+'_'+joint)
                    before = 'wrist' if joint == 'mcp' and finger != 'thumb' else names[i-1]
                    metrics[f'{finger}_{joint}_flexion_deg'] = measured([before, names[i], names[i+1]], finger_angle)
            reasons[-2] = 'hand_point_confidence_not_provided'
        if self.exercise_id:
            spec = exercise_spec(self.exercise_id)
            if spec['joint'] in ('neck', 'trunk'):
                from .axial_geometry import head_roll, head_pitch, trunk_frontal, trunk_sagittal
                raw_contracts = {
                    'head_roll_raw_deg': (['left_shoulder', 'right_shoulder', 'left_eye', 'right_eye'], head_roll),
                    'head_pitch_raw_deg': ([self.side+'_ear', self.side+'_eye'], head_pitch),
                    'trunk_frontal_raw_deg': (['left_hip', 'right_hip', 'left_shoulder', 'right_shoulder'], trunk_frontal),
                    'trunk_sagittal_raw_deg': ([hi, sh], trunk_sagittal),
                }
                ids, function = raw_contracts[spec['raw_metric']]
                metrics[spec['raw_metric']] = measured(ids, function)
            if spec['directional_calibration']:
                raw = metrics.get(spec['raw_metric'], Metric.missing('missing_raw_metric'))
                baseline = self.joint_baseline
                if raw.valid:
                    rest = baseline.get('rest_value')
                    if not isinstance(rest, (int, float)) or isinstance(rest, bool) or not math.isfinite(rest):
                        if self.automatic_rest_value is None:
                            self.automatic_rest_value = raw.value
                        rest = self.automatic_rest_value
                    delta = angle_delta(raw.value, rest)
                    direction = baseline.get('direction_sign')
                    if direction not in (-1, 1):
                        if self.automatic_direction_sign is None and abs(delta) >= 5.:
                            self.automatic_direction_sign = 1 if delta > 0 else -1
                        direction = self.automatic_direction_sign
                    # The opening pose is a valid zero excursion. The first clear
                    # movement establishes screen direction without blocking start.
                    metrics[spec['metric']] = Metric.of(0. if direction is None else direction*delta)
                else:
                    metrics[spec['metric']] = Metric.missing(raw.reason)
        raw_center = None
        local = None
        body_indices = [names.index(n) for n in ('left_shoulder', 'right_shoulder', 'left_hip', 'right_hip') if n in names]
        if len(body_indices) == 4 and all(i in points for i in body_indices):
            ls, rs, lh, rh = body_indices
            # Preserve unsmoothed global displacement separately from local shape.
            raw_center = tuple((p.xy[lh][j]+p.xy[rh][j])/2 for j in (0, 1))
            shoulder = tuple((p.xy[ls][j]+p.xy[rs][j])/2 for j in (0, 1))
            scale = math.dist(raw_center, shoulder)
            metrics['torso_scale_px'] = Metric.of(scale if scale > 1 else None)
            if scale > 1:
                local = [([(p.xy[i][j]-raw_center[j])/scale for j in (0, 1)]
                          if i in points else None) for i in range(len(names))]
        if self.auxiliary_view:
            from .axial_geometry import trunk_frontal, trunk_sagittal

            def shoulder_line(left, right):
                if math.dist(left, right) < 40.:
                    return None
                return math.degrees(math.atan2(abs(right[1]-left[1]), abs(right[0]-left[0])))

            def frontal_deviation(*points):
                angle = trunk_frontal(*points)
                return None if angle is None else abs(abs(angle)-90.)

            def sagittal_deviation(hip, shoulder):
                angle = trunk_sagittal(hip, shoulder)
                return None if angle is None else abs(angle)

            # Use only filtered, valid points in THIS view. These are auxiliary
            # projections with no clinical target and never drive repetition rules.
            metrics = ({
                'aux_shoulder_line_deg': measured(['left_shoulder', 'right_shoulder'], shoulder_line),
                'aux_trunk_frontal_deg': measured(['left_hip', 'right_hip', 'left_shoulder', 'right_shoulder'], frontal_deviation),
            } if self.auxiliary_view == 'frontal' else {
                'aux_trunk_sagittal_deg': measured([hi, sh], sagittal_deviation),
            })
        valid = any(m.valid for m in metrics.values())
        observation_reasons = sorted(set(reasons.values()))
        if len(frame.people) > 1:
            observation_reasons.append('additional_candidates_ignored')
        return Observation(t, selected_track, 'VALID' if valid else 'UNKNOWN', metrics,
                           raw_center, p.bbox, local, frame.size, observation_reasons)

    def automatic_calibration(self):
        if self.automatic_rest_value is None:
            return None
        return {'rest_value': self.automatic_rest_value,
                'direction_sign': self.automatic_direction_sign,
                'method': 'first-valid-pose-and-first-clear-excursion-1'}
