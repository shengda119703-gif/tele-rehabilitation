"""Independent auxiliary-view measurement records and immutable run snapshots."""
import copy
from dataclasses import asdict
from statistics import median

from .domain import digest, Metric
from .dual_camera import DUAL_VERSION, VIEWS, other_view, validate_pair
from .exercises import exercise_spec

AUXILIARY_VERSION = 'auxiliary-projection-1'
VALIDITY_POLICY = 'primary-focus-with-auxiliary-1'


def identity_visible(observation):
    return bool(observation and observation.track_key is not None and observation.status in ('VALID', 'UNKNOWN'))


AUXILIARY_METRICS = {
    'aux_shoulder_line_deg': dict(label='肩线倾角（正面）', view='frontal',
                                 definition='两肩连线与画面水平线的无符号夹角；肩距至少 40 像素'),
    'aux_trunk_frontal_deg': dict(label='躯干相对骨盆偏斜（正面）', view='frontal',
                                 definition='肩髋中线相对骨盆连线法线的无符号二维偏斜；沿用整体躯干参考线门槛'),
    'aux_trunk_sagittal_deg': dict(label='躯干倾斜（侧面）', view='sagittal',
                                  definition='所测侧髋至肩连线与画面竖线的无符号夹角；连线至少 50 像素；未扣除机位倾斜'),
}


def validate_pair_pose(packet, pose, primary_view, *, now=None):
    paired = validate_pair(packet, primary_view, now=now)
    auxiliary = pose.paired_pose
    if (pose.context != packet.context or pose.seq != packet.seq or pose.time_s != packet.time_s
            or auxiliary is None or auxiliary.paired_pose is not None
            or auxiliary.context != paired.context or auxiliary.seq != paired.seq or auxiliary.time_s != paired.time_s
            or tuple(auxiliary.size) != tuple(paired.image.shape[1::-1])
            or auxiliary.schema_id != 'coco17-v1' or auxiliary.coordinate_space != 'raw_image_pixels'
            or auxiliary.keypoint_order_version != 'coco17-anatomical-lr-v1' or auxiliary.backend != 'yolo'):
        raise ValueError('辅助画面与姿态来源、时间、序号或关键点定义不一致')
    return paired, auxiliary


def session_snapshot(controller):
    c = controller
    config = copy.deepcopy(c.dual_config)
    primary, secondary = config['primary_view'], other_view(config['primary_view'])
    packets = {primary: c.latest_packet, secondary: c.latest_packet.paired_frame}
    poses = {primary: c.latest_pose, secondary: c.latest_pose.paired_pose}
    streams = {}
    for view in VIEWS:
        packet, pose = packets[view], poses[view]
        device = config['devices'][view]
        streams[view] = dict(source_ref='camera:'+digest({k: device[k] for k in ('path', 'backend')})[:24],
                             device_ref=device, source_kind=c.source['kind'], time_basis=packet.time_basis,
                             resolved_index_at_start=getattr(getattr(c.camera, 'resolved_views', {}).get(view), 'index', None),
                             schema_id=pose.schema_id, coordinate_space=pose.coordinate_space,
                             keypoint_order_version=pose.keypoint_order_version, pose_backend=pose.backend,
                             model_manifest_id=pose.model_manifest_id,
                             measurement_contract=(exercise_spec(c.setup['plan']['exercise_id'])['measurement_contract']
                                                   if view == primary else AUXILIARY_VERSION),
                             requested_capture=copy.deepcopy(c.capture_options),
                             capture_backend_report=copy.deepcopy((c.input_diagnostics.get('streams') or {}).get(view, {})),
                             actual_capture=dict(size=list(pose.size), reported_fps=packet.reported_fps,
                                                 received_fps=packet.received_fps, inference_ms=pose.inference_ms))
    return dict(version=DUAL_VERSION, primary_view=primary, secondary_view=secondary,
                pairing_version=config['pairing_version'], max_receive_delta_s=config['max_receive_delta_s'],
                auxiliary_version=AUXILIARY_VERSION, validity_policy=VALIDITY_POLICY,
                same_participant_manually_confirmed=bool(
                    (c.setup.get('dual_camera') or {}).get('same_participant_confirmed')),
                auxiliary_metrics={k: copy.deepcopy(v) for k, v in AUXILIARY_METRICS.items() if v['view'] == secondary},
                streams=streams, observations=[], summary={},
                limitations='两路独立二维观察；每路自动保持主要参与者焦点，陪同者入镜不会阻止任务；'
                            '仅接收时间配对，未验证曝光同步，未作空间标定或三维重建。')


def observation_row(controller, packet, primary_observation, auxiliary_observation, *, included=None):
    spec = exercise_spec(controller.setup['plan']['exercise_id'])
    required = spec['required_metrics']
    primary_keys = set(required) | {spec['metric'], spec.get('raw_metric', spec['metric'])}
    main_valid = primary_observation.status == 'VALID' and all(primary_observation.value(k) is not None for k in required)
    primary_focus = (identity_visible(primary_observation)
                     and getattr(controller, 'active_track', None) in (None, primary_observation.track_key))
    auxiliary_focus = (identity_visible(auxiliary_observation)
                       and controller.active_secondary_track in (None, auxiliary_observation.track_key))
    main_usable = main_valid and primary_focus
    return dict(primary_seq=packet.seq, secondary_seq=packet.paired_frame.seq,
                primary_time_s=packet.time_s, secondary_time_s=packet.paired_frame.time_s,
                receive_delta_s=packet.pairing['receive_delta_s'],
                phase=controller.engine.phase if controller.engine else None,
                included_in_training=included,
                primary_status=primary_observation.status, auxiliary_status=auxiliary_observation.status,
                identity_confirmed=primary_focus, auxiliary_focus_available=auxiliary_focus,
                main_measurement_usable=main_usable,
                primary_used=main_usable and included is not False,
                jointly_valid=main_usable and auxiliary_observation.status == 'VALID',
                primary_metrics={k: asdict(primary_observation.metrics.get(k, Metric.missing('not_observed'))) for k in sorted(primary_keys)},
                auxiliary_metrics={k: asdict(v) for k, v in auxiliary_observation.metrics.items()},
                auxiliary_reasons=list(auxiliary_observation.reasons), annotation_origin='prediction')


def update_summary(session):
    dual = session.get('dual_camera')
    if not dual:
        return
    rows = dual['observations']
    deltas = [row['receive_delta_s'] for row in rows]
    measured = {}
    for key in dual['auxiliary_metrics']:
        values = [m['value'] for row in rows if row.get('identity_confirmed', True)
                  and (m := row['auxiliary_metrics'].get(key)) and m['valid']]
        measured[key] = dict(valid_samples=len(values), total_samples=len(rows),
                             median=median(values) if values else None,
                             min=min(values) if values else None, max=max(values) if values else None)
    dual['summary'] = dict(paired_observations=len(rows), both_views_valid=sum(r['jointly_valid'] for r in rows),
                           primary_used_observations=sum(bool(r.get('primary_used')) for r in rows),
                           main_only_observations=sum(bool(r.get('primary_used')) and not r['jointly_valid'] for r in rows),
                           median_receive_delta_s=median(deltas) if deltas else None,
                           max_receive_delta_s=max(deltas) if deltas else None, auxiliary_metrics=measured)


def auxiliary_hint(controller):
    if not controller.dual_config:
        return None
    view = other_view(controller.dual_config['primary_view'])
    obs = controller.latest_secondary_observation
    if obs is None:
        return '等待'+VIEWS[view]+'辅助机位的有效姿态。'
    if identity_visible(obs) and obs.status != 'VALID':
        return VIEWS[view]+'辅助指标：本项无法评价。'
    message = {'NO_PERSON_DETECTED': '未检测到人，请让参与者入镜',
               'MULTI_PERSON': '正在自动选择主要参与者',
               'UNKNOWN': '姿态暂不清楚，请检查所需肩髋点和遮挡'}.get(obs.status)
    return VIEWS[view]+'辅助机位：'+message+'；不影响主机位已取得的数据。' if message else None


def capture_conditions(session):
    config = session.get('config_snapshot') or {}
    dual_trace = ('dual_camera' in session or 'dual_camera' in config
                  or str(session.get('source_ref', '')).startswith('camera-pair:'))
    # Earlier supported schemas only captured one input. Absence of all dual
    # fields retains that single-input contract; a damaged pair never defaults.
    mode = session.get('capture_mode', 'dual' if dual_trace else 'single')
    values = {'capture_mode': mode}
    if mode == 'single' and not dual_trace:
        return dict(values, **{key: 'not_applicable' for key in ('dual_camera', 'dual_camera.frontal', 'dual_camera.sagittal')})
    dual = session.get('dual_camera')
    dual = dual if isinstance(dual, dict) else {}
    common_keys = ('version', 'primary_view', 'secondary_view', 'pairing_version', 'max_receive_delta_s',
                   'auxiliary_version', 'same_participant_manually_confirmed')
    values['dual_camera'] = {k: dual.get(k) for k in common_keys}
    values['dual_camera']['validity_policy'] = dual.get('validity_policy', 'all-views-required-1' if dual.get('version') == 'dual-2d-1' else None)
    streams = dual.get('streams') or {}
    for view in VIEWS:
        stream = streams.get(view)
        stream = stream if isinstance(stream, dict) else {}
        keys = ('source_ref', 'source_kind', 'time_basis', 'schema_id', 'coordinate_space',
                'keypoint_order_version', 'pose_backend', 'model_manifest_id', 'measurement_contract')
        record = {k: stream.get(k) for k in keys}
        record['size'] = (stream.get('actual_capture') or {}).get('size')
        request = stream.get('requested_capture')
        record['requested_capture'] = ({k: request.get(k) for k in ('width', 'height', 'fps', 'fourcc')}
                                       if isinstance(request, dict) and session.get('source_kind') == 'LIVE_CAMERA' else 'not_applicable')
        if isinstance(record['requested_capture'], dict) and record['requested_capture']['fourcc'] is None:
            record['requested_capture']['fourcc'] = 'backend_default'
        values['dual_camera.'+view] = record
    return copy.deepcopy(values)
