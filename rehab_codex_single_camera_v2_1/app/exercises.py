"""Exercise contracts shared by measurement, session gates and presentation.

Angles are camera-plane projections, never clinical ROM measurements. A chosen
view must still be confirmed by the participant; geometry cannot verify it.
"""
from __future__ import annotations

import copy


_SPECS = {
    'shoulder_abduction': {
        'label': '肩外展', 'joint': 'shoulder', 'view': 'frontal',
        'metric': 'raise_deg', 'metric_label': '肩部相对画面竖直线二维投影抬举角',
        'required_metrics': ('raise_deg',), 'rep_value_key': 'peak_angle_deg',
        'target_direction': 'increase',
        'guide': '正面机位，测试侧肩、肘入镜；保持摄像头和身体稳定，在舒适范围向侧方抬臂，再回到垂臂姿势。',
        'ready_hint': '请自然垂臂，保持舒适准备姿势约 1 秒',
        'outbound_hint': '在舒适范围缓慢向侧方抬臂',
        'return_hint': '缓慢放下手臂，回到起始垂臂姿势',
    },
    'sit_to_stand': {
        'label': '居家坐站', 'joint': 'knee', 'view': 'sagittal',
        'metric': 'knee_flexion_deg', 'metric_label': '坐站膝屈曲二维投影角',
        'required_metrics': ('knee_flexion_deg', 'hip_y'),
        'rep_value_key': 'min_angle_deg', 'target_direction': 'decrease',
        'guide': '侧面机位，尽量让测试侧髋、膝、踝入镜；开始时先舒适坐稳，系统会在清楚画面中自动建立本轮起点。达到站位记一次，回坐后才可再计。',
        'ready_hint': '请在已确认的座椅上保持舒适坐位约 1 秒',
        'outbound_hint': '按已确认计划缓慢起立',
        'return_hint': '缓慢回坐到已确认的座椅，回坐后才可开始下一次',
    },
    'shoulder_flexion': {
        'label': '肩前屈', 'joint': 'shoulder', 'view': 'sagittal',
        'metric': 'raise_deg', 'metric_label': '肩部相对画面竖直线二维投影抬举角',
        'required_metrics': ('raise_deg',), 'rep_value_key': 'peak_angle_deg',
        'target_direction': 'increase',
        'guide': '侧面机位，测试侧肩、肘入镜；保持摄像头和身体稳定，在舒适范围向前抬臂，再回到垂臂姿势。',
        'ready_hint': '请侧对镜头，自然垂臂并保持舒适准备姿势约 1 秒',
        'outbound_hint': '在舒适范围缓慢向前抬臂',
        'return_hint': '缓慢放下手臂，回到起始垂臂姿势',
    },
    'elbow_flexion': {
        'label': '肘屈伸', 'joint': 'elbow', 'view': 'sagittal',
        'metric': 'elbow_flexion_deg', 'metric_label': '肘屈曲二维投影角',
        'required_metrics': ('elbow_flexion_deg',), 'rep_value_key': 'peak_angle_deg',
        'target_direction': 'increase',
        'guide': '侧面机位，测试侧肩、肘、腕入镜；上臂保持舒适位置，缓慢屈肘，再回到起始伸肘姿势。',
        'ready_hint': '请舒适伸肘，保持起始姿势约 1 秒，不要强行伸直',
        'outbound_hint': '保持上臂舒适，缓慢屈肘',
        'return_hint': '缓慢伸肘，回到起始姿势',
    },
    'knee_extension': {
        'label': '坐位膝屈伸', 'joint': 'knee', 'view': 'sagittal',
        'metric': 'knee_flexion_deg', 'metric_label': '坐位膝屈曲二维投影角',
        'required_metrics': ('knee_flexion_deg',), 'rep_value_key': 'min_angle_deg',
        'target_direction': 'decrease',
        'guide': '侧面机位，坐稳并让测试侧髋、膝、踝入镜；保持坐位，缓慢伸膝再屈膝回位。伸展时屈曲投影角减小。',
        'ready_hint': '请坐稳，舒适屈膝并保持起始坐位约 1 秒',
        'outbound_hint': '保持坐稳，缓慢伸膝；屈曲角随伸展减小',
        'return_hint': '保持坐稳，缓慢屈膝回到起始坐位',
    },
    'hip_abduction': {
        'label': '髋外展', 'joint': 'hip', 'view': 'frontal',
        'metric': 'hip_abduction_deg', 'metric_label': '骨盆参考髋外展二维投影角',
        'required_metrics': ('hip_abduction_deg',), 'rep_value_key': 'peak_angle_deg',
        'target_direction': 'increase',
        'guide': '正面机位，双髋与测试侧膝入镜；按已确认的支撑与陪同安排，在舒适范围向侧方移腿并回位。仅记录骨盆参考二维投影，不是临床ROM。',
        'ready_hint': '请按已确认的支撑安排站稳，测试腿自然下垂并保持约 1 秒',
        'outbound_hint': '保持支撑稳定，在舒适范围缓慢向侧方移腿',
        'return_hint': '缓慢收回测试腿，回到起始站位',
    },
}

def _add(exercise_id, label, joint, view, metric, metric_label, guide,
         *, backend='yolo', direction='increase', directional=False, experimental=False):
    _SPECS[exercise_id] = {
        'label': label, 'joint': joint, 'view': view, 'metric': metric,
        'metric_label': metric_label, 'required_metrics': (metric,),
        'rep_value_key': 'peak_angle_deg' if direction == 'increase' else 'min_angle_deg',
        'target_direction': direction, 'backend': backend, 'baseline_required': True,
        'directional_calibration': directional, 'experimental': experimental,
        'guide': guide,
        'ready_hint': '请保持舒适起始姿势约 1 秒；清楚入镜后自动建立本轮起点',
        'outbound_hint': '按所选动作方向，在舒适范围缓慢完成'+label,
        'return_hint': '缓慢回到本轮舒适起始姿势',
    }


_add('shoulder_adduction', '肩内收回位', 'shoulder', 'frontal', 'raise_deg',
     '肩部相对画面竖直线二维投影抬举角（内收时减小）',
     '正面，测试侧肩、肘清楚可见；从舒适侧抬臂姿势向身体收回，再返回起始位置。仅测抬臂平面内内收，不测横向内收。', direction='decrease')
_SPECS['shoulder_adduction'].update(
    ready_hint='请先舒适侧抬手臂并保持约 1 秒；系统会自动以此作为本轮起点',
    outbound_hint='从侧抬臂起点向身体缓慢收回手臂，角度减小',
    return_hint='向侧方抬回已记录的侧抬臂起点，回位后计 1 次',
    measurement_contract='shoulder-adduction-start-2')
_add('elbow_extension', '肘伸展', 'elbow', 'sagittal', 'elbow_flexion_deg',
     '肘屈曲二维投影角（伸展时减小）', '侧面，肩、肘、腕入镜；开始时保持舒适屈肘姿势，缓慢伸肘后回位。', direction='decrease')
_add('knee_flexion', '膝屈曲', 'knee', 'sagittal', 'knee_flexion_deg',
     '膝屈曲二维投影角', '侧面，髋、膝、踝入镜；使用稳定坐位或支撑姿势，开始时保持舒适起点，缓慢屈膝后回位。')

# Signed angles are direction-calibrated against a comfortable starting pose.
# A small, manually identified excursion establishes screen direction, NOT ROM
# or a clinical target. This avoids confusing flexion with extension after mirroring.
for eid, label, joint, view, raw, guide in (
    ('shoulder_extension', '肩后伸', 'shoulder', 'sagittal', 'shoulder_sagittal_raw_deg', '侧面，测试侧肩、肘入镜；保持摄像头和身体稳定，向身体后方小幅移臂。'),
    ('hip_flexion', '髋屈曲', 'hip', 'sagittal', 'hip_sagittal_raw_deg', '侧面，肩、髋、膝入镜；使用已确认的稳定支撑，向身体前方小幅移腿。'),
    ('hip_extension', '髋后伸', 'hip', 'sagittal', 'hip_sagittal_raw_deg', '侧面，肩、髋、膝入镜；使用已确认的稳定支撑，向身体后方小幅移腿。'),
    ('hip_adduction', '髋内收', 'hip', 'frontal', 'hip_abduction_deg', '正面，双髋与测试侧膝入镜；从舒适外展位置向身体中线收腿，避免另一条腿遮挡。'),
):
    _add(eid, label, joint, view, eid+'_excursion_deg', label+'相对舒适起点二维投影变化',
         guide+'开始时保持舒适起点，再按所选动作方向小幅移动；系统会在清楚画面中自动建立本轮起点和方向。', directional=True)
    _SPECS[eid]['raw_metric'] = raw
    if eid in ('hip_flexion', 'hip_extension'):
        _SPECS[eid]['guide'] += '角度参考肩—髋躯干线与大腿线；骨盆/躯干转动会影响结果，不能分离为纯髋关节ROM。'

for eid, label, view, plane in (
    ('wrist_flexion', '腕屈曲', 'sagittal', '从手的侧缘拍摄，向掌侧弯腕'),
    ('wrist_extension', '腕伸展', 'sagittal', '从手的侧缘拍摄，向手背侧弯腕'),
    ('wrist_radial_deviation', '腕桡偏', 'frontal', '手背或手掌正对镜头，向拇指侧偏腕'),
    ('wrist_ulnar_deviation', '腕尺偏', 'frontal', '手背或手掌正对镜头，向小指侧偏腕'),
):
    _add(eid, label, 'wrist', view, eid+'_excursion_deg', label+'相对舒适起点二维投影变化',
         plane+'；让测试侧肘、腕、整只手尽量清楚入镜。开始时保持舒适起点，再小幅完成所选动作；系统自动建立本轮方向。',
         backend='mediapipe_wrist', directional=True, experimental=True)
    _SPECS[eid]['raw_metric'] = 'wrist_raw_deg'

for eid, label, movement in (
    ('ankle_dorsiflexion', '踝背屈', '向小腿方向抬脚尖'),
    ('ankle_plantarflexion', '踝跖屈', '向远离小腿方向下压脚尖'),
):
    _add(eid, label, 'ankle', 'sagittal', eid+'_excursion_deg', label+'相对舒适起点二维投影变化',
         '侧面稳定坐位，小腿、踝、足跟、足尖尽量可见；'+movement+'，不以踮脚站立代替。开始时保持舒适起点，再小幅完成所选动作。仅测小腿—足部投影变化。',
         backend='mediapipe_pose', directional=True, experimental=True)
    _SPECS[eid]['raw_metric'] = 'ankle_raw_deg'

for finger, label, joints in (
    ('thumb', '拇指', ('mcp', 'ip')),
    ('index', '食指', ('mcp', 'pip', 'dip')),
    ('middle', '中指', ('mcp', 'pip', 'dip')),
    ('ring', '无名指', ('mcp', 'pip', 'dip')),
    ('pinky', '小指', ('mcp', 'pip', 'dip')),
):
    for joint in joints:
        part = {'mcp': '掌指关节', 'pip': '近端指间关节', 'dip': '远端指间关节', 'ip': '指间关节'}[joint]
        eid = f'{finger}_{joint}_flexion'
        _add(eid, label+part+'屈伸', 'finger', 'sagittal', eid+'_deg', label+part+'二维投影屈曲角',
             '单只测试手近景，所测手指从侧面展开在成像平面内，其余手指尽量不遮挡。开始时保持舒适起点，然后缓慢弯曲、回位。手部模型不提供逐点置信度，遮挡和离开测量平面可能无法自动发现；仅作实验性观察。'+
             ('掌指角的近端参考使用腕—掌指连线，不是骨性关节测量。' if joint == 'mcp' and finger != 'thumb' else ''),
             backend='mediapipe_hands', experimental=True)
        _add(f'{finger}_{joint}_extension', label+part+'伸展', 'finger', 'sagittal', eid+'_deg',
             label+part+'二维投影屈曲角（伸展时减小）',
             '单只测试手侧面近景；开始时保持舒适屈曲起点，缓慢伸展所测关节，再屈回起点。不要求完全伸直，不测超伸；其余手指尽量不遮挡。'
             '手部点没有逐点置信度，离面运动可能无法自动发现，仅作实验性观察。',
             backend='mediapipe_hands', direction='decrease', experimental=True)

# Whole-segment projections, deliberately distinct from vertebral joint ROM.
for eid, label, joint, view, raw, guide in (
    ('neck_lateral_flexion', '头颈侧屈观察', 'neck', 'frontal', 'head_roll_raw_deg',
     '坐稳并正对镜头，双眼与双肩清楚可见；向所选左/右侧小幅侧屈头部，不转头、不耸肩。记录双眼线相对双肩线的变化，不是颈椎各节段角。'),
    ('neck_flexion', '头颈前屈观察', 'neck', 'sagittal', 'head_pitch_raw_deg',
     '坐稳并从测试侧拍摄，同侧眼、耳和肩清楚可见；按已确认安排小幅低头。记录耳—眼线相对固定画面的变化，不是颈椎关节角。'),
    ('neck_extension', '头颈后伸观察', 'neck', 'sagittal', 'head_pitch_raw_deg',
     '坐稳并从测试侧拍摄，同侧眼、耳和肩清楚可见；仅在已获准的舒适范围小幅抬头，不追求后仰极限。记录耳—眼线相对固定画面的变化。'),
    ('trunk_lateral_flexion', '躯干侧屈观察', 'trunk', 'frontal', 'trunk_frontal_raw_deg',
     '稳定坐位正对镜头，双肩、双髋完整入镜；按已确认安排向所选左/右侧小幅侧屈。记录肩髋中线相对骨盆参考线的变化，不分离脊柱各节段。'),
    ('trunk_flexion', '躯干前屈观察', 'trunk', 'sagittal', 'trunk_sagittal_raw_deg',
     '稳定坐位从测试侧拍摄，同侧肩、髋完整入镜；按已确认安排小幅前倾后回位。记录肩髋连线相对起点的变化，不能区分腰椎活动与髋部转动。'),
    ('trunk_extension', '躯干后伸观察', 'trunk', 'sagittal', 'trunk_sagittal_raw_deg',
     '稳定坐位从测试侧拍摄，同侧肩、髋完整入镜；仅在已确认安排内小幅后移躯干，再回到起点，不追求后仰极限。不能分离胸腰椎、骨盆和髋部贡献。'),
):
    _add(eid, label, joint, view, eid+'_excursion_deg', label+'相对舒适起点二维投影变化',
         guide+'开始时保持舒适起点，再按提示小幅试做；系统在清楚画面中自动建立本轮起点和方向。疼痛、头晕或不适立即停止。',
         directional=True, experimental=True)
    _SPECS[eid].update(raw_metric=raw,
                       measurement_contract=('head-pitch-screen-reference-2'
                                             if eid in ('neck_flexion', 'neck_extension')
                                             else 'whole-segment-projection-1'))

for _shoulder_id in ('shoulder_abduction', 'shoulder_flexion', 'shoulder_extension'):
    _SPECS[_shoulder_id]['measurement_contract'] = 'shoulder-screen-vertical-1'
_SPECS['shoulder_adduction']['measurement_contract'] = 'shoulder-adduction-screen-reference-3'

EXERCISE_IDS = tuple(_SPECS)

UNSUPPORTED_COVERAGE = (
    ('肩内/外旋、水平内/外收', '单目常用机位存在离面运动与肢段重叠，不能可靠分离肩关节旋转。'),
    ('前臂旋前/旋后', '手掌朝向变化不能直接当成桡尺关节旋转角；暂不输出角度。'),
    ('髋内/外旋', '二维骨架不能可靠区分髋轴向旋转、骨盆转动与机位变化。'),
    ('踝内/外翻、足弓', '现有足跟/足尖不足以独立量化后足与距下关节运动。'),
    ('拇指腕掌关节、对掌、手指侧向外展', '涉及多平面与遮挡，未建立可验证的单目测量契约。'),
    ('颈椎、胸腰椎各节段及轴向旋转', '已提供头颈/躯干整体屈伸和侧屈观察；没有椎体关键点，不输出节段活动度或轴向旋转角。'),
    ('足趾各关节', '现有足部点没有各足趾的关节链；不以足尖位移冒充足趾屈伸。'),
    ('肌力、疼痛、关节稳定性、病种诊断', '不能从摄像头投影角推断；需要用户自述或专业检查。'),
)


def exercise_spec(exercise_id: str) -> dict:
    """Return a detached spec; reject unknown actions instead of guessing."""
    if not isinstance(exercise_id, str) or exercise_id not in _SPECS:
        raise ValueError(f'未知康复动作：{exercise_id!r}')
    spec = copy.deepcopy(_SPECS[exercise_id])
    spec.setdefault('backend', 'yolo')
    spec.setdefault('baseline_required', False)
    spec.setdefault('directional_calibration', False)
    spec.setdefault('experimental', False)
    spec.setdefault('measurement_contract', 'joint-projection-0.3')
    spec.update(measurement_type='2d_projection', clinical_rom=False,
                readiness_note='起始姿势与方向校准仅用于工程分期，不是正常值或医学目标；有不适立即停止。')
    return spec
