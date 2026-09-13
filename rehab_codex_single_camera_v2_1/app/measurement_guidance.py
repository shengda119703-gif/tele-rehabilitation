"""Explain existing metric validity; never infer hidden joints or camera pose."""
from .exercises import exercise_spec
from .landmark_schemas import SCHEMAS


SUPPORTED = ('neck_flexion', 'neck_extension', 'neck_lateral_flexion', 'shoulder_adduction')
PARTS = {'eye': '眼', 'ear': '耳', 'shoulder': '肩', 'hip': '髋', 'elbow': '肘'}


def adjustment_action(observation, plan, schema_id):
    """Choose one evidenced missing point, with no inferred camera position."""
    if observation is None or observation.status == 'NO_PERSON_DETECTED':
        return '请让测试部位清楚进入画面。'
    spec = exercise_spec(plan['exercise_id'])
    names = SCHEMAS.get(schema_id, ())
    parts = dict(PARTS, wrist='腕', knee='膝', ankle='踝', heel='脚跟', foot_index='前脚掌')
    for key in dict.fromkeys([spec.get('raw_metric', spec['metric'])]+list(spec['required_metrics'])):
        metric = observation.metrics.get(key)
        for item in (metric.reason if metric and not metric.valid else '').split(','):
            index = item.partition(':')[0]
            if index.isdigit() and int(index) < len(names):
                side, _, part = names[int(index)].partition('_')
                if side in ('left', 'right') and part in parts:
                    view = '侧面' if spec['view'] == 'sagittal' else '正面'
                    return '请调整'+view+'取景，让'+('左' if side == 'left' else '右')+parts[part]+'也进入画面。'
    if spec['backend'] in ('mediapipe_hand', 'mediapipe_wrist'):
        return '请让测试手和所测关节分开可见。'
    return '请调整取景，让测试部位清楚可见。'


def measurement_hint(observation, plan, schema_id, *, preview=False):
    eid = plan['exercise_id']
    if eid not in SUPPORTED:
        return None
    spec = exercise_spec(eid)
    if observation is None:
        return '等待当前动作的关键点，请保持机位固定。'
    if observation.status == 'NO_PERSON_DETECTED':
        return '未检测到参与者，请让测试部位入镜。'
    if observation.status == 'MULTI_PERSON':
        return None
    if observation.track_key is None:
        return '正在选择主要参与者，请面向镜头并保持测试部位清楚。'
    key = spec.get('raw_metric', spec['metric']) if preview else spec['metric']
    metric = observation.metrics.get(key)
    if metric is not None and metric.valid:
        if not preview:
            return None
        baseline = plan.get('joint_baseline') or {}
        if eid == 'shoulder_adduction':
            if not baseline:
                return '先侧抬手臂，再记录侧抬臂起点；不要垂臂记录，也不是横向抱胸。'
            return f"侧抬臂起点 {baseline['rest_value']:.0f}°；向身体收回后，再抬回起点计 1 次。"
        if not baseline:
            return '所需关键点已识别；请在舒适起点保持约 1 秒，再记录起始姿势。'
        if not baseline.get('direction_sign'):
            return '起点已记录；请按动作方向小幅试做、稳定保持，再记录活动方向。'
        return '起点和方向已记录；回到舒适起点，勾选人工确认后点击“确认准备”。'
    reason = metric.reason if metric is not None else ''
    if reason == 'direction_calibration_required':
        return '正在用本轮第一段清楚动作自动建立起点和方向。'
    names = SCHEMAS.get(schema_id, ())
    missing = []
    for item in (reason or '').split(','):
        index = item.partition(':')[0]
        if index.isdigit() and int(index) < len(names):
            side, _, part = names[int(index)].partition('_')
            if side in ('left', 'right') and part in PARTS:
                missing.append(('左' if side == 'left' else '右')+PARTS[part])
    if missing:
        hint = '未看清：'+'、'.join(dict.fromkeys(missing))+'；'
        if spec['view'] == 'sagittal':
            return hint+'让测试侧朝向镜头，同侧眼、耳和肩入镜；不要求髋部入镜。'
        return hint+('正对镜头，让双眼、双肩入镜。' if spec['joint'] == 'neck' else
                     '正对镜头，让测试侧肩、肘入镜。')
    if spec['joint'] == 'neck':
        return ('参考线过短或不清楚；检查侧面耳—眼连线，保持身体和机位固定。'
                if spec['view'] == 'sagittal' else '参考线过短或不清楚；请正对镜头，让双眼和双肩清楚入镜。')
    return '上臂参考线不清楚；请让测试侧肩、肘分开可见，并保持摄像头固定。'
