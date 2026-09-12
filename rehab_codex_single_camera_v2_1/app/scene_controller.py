from __future__ import annotations

import copy
from dataclasses import asdict, replace
from datetime import datetime
import json
import math
from pathlib import Path
from uuid import uuid4

from .domain import Context, PacketGate, RULE_VERSION, PREPROCESS_VERSION, JOINTS, digest, utc_now, dumps
from .geometry import valid_roi
from .quality import PoseAnalyzer
from .rehab import RehabEngine
from .training import TrainingEngine
from .exercises import exercise_spec
from .assessment import build_body_profile, build_training_reference
from .landmark_schemas import joint_names, BACKEND_SCHEMAS
from .guided import GuidedEngine, measurement_mode, prompt_plan
from .joint_calibration import (stable_preview_value, provenance, validate_start_value,
                                same_conditions)
from .measurement_guidance import measurement_hint
from .quality import angle_delta


class SceneController:
    """Single owner, used by runtime worker; no UI toolkit or camera construction."""
    # How long the participant may be absent from the picture before this
    # preview's explicit acknowledgement has to be given again.
    CONFIRMATION_ABSENCE_S = 2.

    def __init__(self, storage, camera, test_mode=False, vision_config=None):
        self.storage, self.camera, self.test_mode = storage, camera, test_mode
        self.generation = 0
        self.vision_config = copy.deepcopy(vision_config or {'imgsz': 640, 'keypoint_conf_min': .5, 'filter_tau_s': .12, 'invalid_gap_s': .5})
        self.capture_options = {}
        self.input_diagnostics = {}
        self.gate = PacketGate()
        self.context = None
        self.state = 'UNSELECTED'
        self.source = None
        self.setup = {}
        self.confirmed = False
        self.engine = None
        self.session = None
        self.latest_packet = self.latest_pose = self.latest_observation = None
        self.pending_path = self.storage.path.parent/'pending-session.json'
        self.pending = None
        self.recovery_backup_dir = None
        self.persisted_events = set()
        self.last_saved_id = None
        self.last_error = ''
        self.processed_frames = 0
        self.dropped_frames = 0
        self.previous_seq = None
        self.dual_config = None
        self.secondary_gate = PacketGate()
        self.secondary_analyzer = None
        self.latest_secondary_observation = self.latest_primary_observation = None
        self.active_secondary_track = None
        self.confirmation_binding = None
        self.confirmation_absent_since = None
        self.confirmation_withdrawn = ''
        self.confirmation_reacquired = False
        self.live_joint_baseline = {}
        self.carried_preparation = None
        self.preparation_reuse = None
        if self.pending_path.is_file():
            self.pending = json.loads(self.pending_path.read_text(encoding='utf-8'))
            self.state = 'SAVE_FAILED'

    def _context(self, run_id=''):
        self.generation += 1
        source = self.source
        return Context(self.generation, self.setup['scene_id'], source['ref'], source['kind'], source['usage_context'], run_id)

    def _analyzer(self, side):
        return PoseAnalyzer(side=side, conf_min=self.vision_config.get('keypoint_conf_min', .5),
                            tau=self.vision_config.get('filter_tau_s', .12), max_gap=self.vision_config.get('invalid_gap_s', .5),
                            exercise_id=self.setup['plan']['exercise_id'] if self.setup['scene_id'] == 'rehab' else None,
                            joint_baseline=self.setup['plan'].get('joint_baseline'))

    def _new_secondary_analyzer(self):
        from .dual_camera import other_view
        return PoseAnalyzer(side=self.setup['plan']['side'],
                            conf_min=self.vision_config.get('keypoint_conf_min', .5),
                            tau=self.vision_config.get('filter_tau_s', .12), max_gap=self.vision_config.get('invalid_gap_s', .5),
                            auxiliary_view=other_view(self.dual_config['primary_view']))

    def _reset_secondary(self, context=None):
        from .dual_camera import other_view, secondary_context
        self.latest_secondary_observation = self.latest_primary_observation = None
        self.active_secondary_track = None
        self.secondary_gate.reset(secondary_context(context, other_view(self.dual_config['primary_view']))
                                  if context is not None and self.dual_config else None)
        self.secondary_analyzer = self._new_secondary_analyzer() if self.dual_config else None

    def _validate_current_pair(self):
        from .dual_view import validate_pair_pose
        import time
        if self.latest_packet is None or self.latest_pose is None:
            raise ValueError('请先取得两路有效姿态')
        now = time.monotonic() if self.source['kind'] == 'LIVE_CAMERA' and not self.test_mode else None
        validate_pair_pose(self.latest_packet, self.latest_pose, self.dual_config['primary_view'], now=now)
        from .dual_view import identity_visible
        if not identity_visible(self.latest_secondary_observation):
            raise ValueError('请让两路画面中的同一位参与者清楚可见，再人工确认归属')

    def open(self, source, setup, options=None):
        if self.pending is not None:
            raise RuntimeError('仍有未保存结果，请先重试保存或明确导出备份')
        if self.camera.worker is not None or self.context is not None:
            self.stop('configuration_change')
        self.source, self.setup = copy.deepcopy(source), copy.deepcopy(setup)
        self.live_joint_baseline = {}
        # Preparation the person already completed is offered back to this preview
        # only once the same recorded conditions are observed again.
        self.carried_preparation = dict(joint_baseline=copy.deepcopy(self.setup['plan'].get('joint_baseline') or {}),
                                        calibration=copy.deepcopy(self.setup['plan'].get('calibration') or {}))
        self.preparation_reuse = None
        self.setup['plan']['joint_baseline'] = {}
        self.setup['plan']['calibration'] = {}
        self.capture_options = copy.deepcopy(options or {})
        self.input_diagnostics = {}
        self.last_error = ''
        kind = source['kind']
        if kind == 'SYNTHETIC' and not self.test_mode:
            raise ValueError('合成输入仅用于明确标记的软件测试')
        if kind not in ('LIVE_CAMERA', 'REPLAY_FILE', 'SYNTHETIC'):
            raise ValueError('仅支持本地摄像头和录像')
        if self.setup['scene_id'] in ('bedroom_demo', 'safety_demo'):
            self.source['usage_context'] = 'CONTROLLED_DEMO'
        if kind == 'SYNTHETIC':
            self.source['usage_context'] = 'TEST'
        self.dual_config = None
        if 'dual_camera' in source:
            from .dual_camera import validate_dual_source
            if self.setup['scene_id'] != 'rehab':
                raise ValueError('双摄当前用于一个康复任务，请切回身体评估或训练')
            self.dual_config = validate_dual_source(self.source, self.setup['view'], allow_synthetic=self.test_mode)
            self.setup['dual_camera'] = dict(primary_view=self.dual_config['primary_view'], same_participant_confirmed=False)
        else:
            self.setup.pop('dual_camera', None)
        self.context = self._context()
        self.gate.reset(self.context)
        self._reset_secondary(self.context)
        self.confirmed = False
        self.confirmation_binding = self.confirmation_absent_since = None
        self.confirmation_withdrawn, self.confirmation_reacquired = '', False
        self.analyzer = self._analyzer(setup['plan']['side'])
        self.latest_packet = self.latest_pose = self.latest_observation = None
        self.state = 'CONNECTING'
        try:
            if kind == 'LIVE_CAMERA':
                if self.dual_config:
                    self.camera.open_pair(self.dual_config['devices'], self.dual_config['primary_view'], self.context, options)
                    for view, ref in self.dual_config['devices'].items():
                        self.storage.save_device(source['ref']+':'+view, ref)
                else:
                    self.camera.open_camera(source['device_ref'], self.context, options)
                    self.storage.save_device(source['ref'], source['device_ref'])
            elif kind == 'REPLAY_FILE':
                self.camera.open_replay(source['file'], self.context, options)
        except Exception:
            self.gate.reset()
            self.context = None
            self.state = 'ERROR'
            self.camera.stop()
            raise
        return self.context

    def _review_confirmation(self, pose, observation, auxiliary):
        """Withdraw this preview's acknowledgement only on evidenced change.

        A tracker id is explicitly not an identity, so re-acquired tracking of a
        continuously visible person keeps the acknowledgement and is only noted.
        A crowd, or the participant actually leaving the picture, withdraws it
        with a stated reason so the person knows what to check.
        """
        from .joint_calibration import preparation_binding
        if not self.confirmed:
            self.confirmation_absent_since = None
            return
        binding = preparation_binding(self)
        if not same_conditions(self.confirmation_binding, binding):
            self.confirmed, self.confirmation_absent_since = False, None
            self.confirmation_withdrawn = '拍摄条件已变化，请重新核对本次准备'
            return
        views = [observation.status] + ([auxiliary.status] if auxiliary is not None else [])
        if 'MULTI_PERSON' in views:
            self.confirmed, self.confirmation_absent_since = False, None
            self.confirmation_withdrawn = '画面中不止一位，请只保留本人后重新核对'
            return
        if 'NO_PERSON_DETECTED' not in views:
            self.confirmation_absent_since = None
            self.confirmation_reacquired = self.confirmation_reacquired or binding != self.confirmation_binding
            return
        if self.confirmation_absent_since is None:
            self.confirmation_absent_since = pose.time_s
        elif pose.time_s-self.confirmation_absent_since >= self.CONFIRMATION_ABSENCE_S:
            self.confirmed, self.confirmation_absent_since = False, None
            self.confirmation_withdrawn = '画面中一度没有人，请回到画面后重新核对'

    def _calibration_provenance(self):
        return {'source_ref': self.source['ref'], 'frame_size': list(self.latest_pose.size) if self.latest_pose else None,
                'side': self.setup['plan']['side'], 'view': self.setup['view']}

    def _adopt_carried_preparation(self):
        """Reuse still-applicable preparation instead of demanding a repeat.

        Reuse needs complete recorded evidence of the same person, source, frame
        size, model, action, side and view. Anything else is reset with the
        reason, and the person still re-acknowledges this preview explicitly.
        """
        carried, self.carried_preparation = self.carried_preparation, None
        if not carried or self.setup['scene_id'] != 'rehab' or self.latest_pose is None:
            return
        plan = self.setup['plan']
        reused, reasons = [], []
        baseline = carried.get('joint_baseline') or {}
        if baseline.get('rest_value') is not None:
            if same_conditions(baseline.get('provenance'), provenance(self)):
                self.live_joint_baseline = copy.deepcopy(baseline)
                plan['joint_baseline'] = copy.deepcopy(baseline)
                self.analyzer = self._analyzer(plan['side'])
                reused.append('joint_baseline')
            else:
                reasons.append('动作、侧别、机位、画面尺寸或输入已变化，需要重新记录起点')
        calibration = carried.get('calibration') or {}
        if any(calibration.get(key) is not None for key in ('seated_knee', 'standing_knee')):
            if calibration.get('provenance') == self._calibration_provenance():
                plan['calibration'] = copy.deepcopy(calibration)
                reused.append('calibration')
            else:
                reasons.append('坐站基线的输入、画面尺寸、侧别或机位已变化，需要重新记录')
        if reused or reasons:
            self.preparation_reuse = dict(reused=reused, reasons=sorted(set(reasons)))

    def record_joint_baseline(self, history, position):
        if self.state != 'PREVIEW' or self.setup['scene_id'] != 'rehab' or self.latest_pose is None:
            raise ValueError('请先预览并取得所选动作的有效关键点')
        plan = self.setup['plan']
        spec = exercise_spec(plan['exercise_id'])
        if plan['exercise_id'] == 'sit_to_stand':
            raise ValueError('坐站请使用舒适坐位和站位基线')
        metric = spec.get('raw_metric', spec['metric'])
        current_metric = self.latest_observation.metrics.get(metric)
        if current_metric is None or not current_metric.valid:
            hint = measurement_hint(self.latest_observation, plan, self.latest_pose.schema_id, preview=True)
            if hint:
                raise ValueError(hint)
        value = stable_preview_value(history, metric, now_time=self.latest_pose.time_s,
                                     track_key=self.latest_observation.track_key,
                                     circular=spec['directional_calibration'])
        current_provenance = provenance(self)
        if position == 'rest':
            validate_start_value(plan, value)
            baseline = {'rest_value': value, 'raw_metric': metric, 'provenance': current_provenance,
                        'measurement_kind': 'observed_comfort_start', 'recorded_at': utc_now()}
        elif position == 'direction' and spec['directional_calibration']:
            baseline = copy.deepcopy(self.live_joint_baseline)
            if not same_conditions(baseline.get('provenance'), current_provenance):
                raise ValueError('请先在当前预览记录舒适起点')
            delta = angle_delta(value, baseline['rest_value'])
            if not 5 <= abs(delta) <= 90:
                raise ValueError('暂不能区分活动方向；仅在舒适范围内做清楚的小幅试动作，不要勉强扩大幅度')
            baseline.update(direction_sign=1 if delta > 0 else -1, direction_probe_value=value,
                            direction_recorded_at=utc_now(), direction_manually_identified=True)
        else:
            raise ValueError('未知的关节基线操作')
        self.live_joint_baseline = copy.deepcopy(baseline)
        self.setup['plan']['joint_baseline'] = copy.deepcopy(baseline)
        self.analyzer = self._analyzer(plan['side'])
        self.confirmed = False
        return baseline

    def _check_joint_baseline(self, plan):
        spec = exercise_spec(plan['exercise_id'])
        baseline = plan.get('joint_baseline') or {}
        if not baseline and not spec['baseline_required']:
            return
        if (not baseline or baseline != self.live_joint_baseline
                or not same_conditions(baseline.get('provenance'), provenance(self))):
            raise ValueError('请在本次预览重新记录舒适起始姿势；不能沿用其他人或旧机位的基线')
        if spec['directional_calibration'] and baseline.get('direction_sign') not in (-1, 1):
            raise ValueError('请先按所选动作方向做舒适的小幅试动作，并点击“记录活动方向”')
        if baseline:
            validate_start_value(plan, baseline['rest_value'])

    def confirm(self, setup):
        if self.state != 'PREVIEW' or self.latest_packet is None:
            raise ValueError('请先打开有效画面预览')
        setup = copy.deepcopy(setup)
        if (setup['scene_id'] != self.context.scene_id or setup['plan']['side'] != self.setup['plan']['side']
                or setup['plan']['exercise_id'] != self.setup['plan']['exercise_id'] or setup['view'] != self.setup['view']
                or setup['plan'].get('participant_id') != self.setup['plan'].get('participant_id')
                or setup['plan'].get('submode') != self.setup['plan'].get('submode')
                or setup.get('mirror') != self.setup.get('mirror')):
            raise ValueError('用户、模式、场景、动作、侧别或机位已经改变，请重新预览')
        if not setup.get('participant_confirmed'):
            raise ValueError('请人工确认参与者和机位')
        if self.latest_observation is not None and self.latest_observation.status == 'MULTI_PERSON':
            raise ValueError('画面中不止一位，请只保留当前参与者后再核对')
        if setup.get('continuation_mode', 'auto') not in ('auto', 'guided'):
            raise ValueError('未知的本次进行方式')
        if self.dual_config:
            from .dual_camera import other_view
            dual = setup.get('dual_camera') or {}
            if dual.get('same_participant_confirmed') is not True or dual.get('primary_view') != self.dual_config['primary_view']:
                raise ValueError('请人工确认两路均为同一人，正面 / 侧面角色和测试侧正确')
            self._validate_current_pair()
            primary = self.dual_config['primary_view']
            setup['dual_camera'] = {k: copy.deepcopy(v) for k, v in self.dual_config.items() if k != 'devices'}
            setup['dual_camera'].update(same_participant_confirmed=True,
                                       confirmed_sizes={primary: list(self.latest_pose.size),
                                                        other_view(primary): list(self.latest_pose.paired_pose.size)})
        elif setup.get('dual_camera'):
            raise ValueError('双摄设置已经改变，请重新预览')
        scene, exercise = setup['scene_id'], setup['plan']['exercise_id']
        required = {'activity': ['chair'], 'bedroom_demo': ['bed', 'bed_edge', 'exit', 'floor_watch'],
                    'safety_demo': ['floor_watch']}.get(scene, [])
        missing = [name for name in required if not valid_roi(setup.get('rois', {}).get(name))]
        if missing:
            raise ValueError('请在原画面圈定并确认区域：'+', '.join(missing))
        if scene == 'activity' and not setup.get('activity_permission'):
            raise ValueError('活动任务需要人工确认活动许可')
        if scene == 'rehab':
            # A guided, timed session may proceed without a recorded baseline; any
            # baseline it does carry is still checked against this preview.
            guided = setup.get('continuation_mode') == 'guided'
            if not guided or setup['plan'].get('joint_baseline'):
                self._check_joint_baseline(setup['plan'])
            expected_view = exercise_spec(exercise)['view']
            if setup['view'] != expected_view:
                raise ValueError('此动作需要'+('正面' if expected_view == 'frontal' else '侧面')+'机位')
            if exercise == 'sit_to_stand' and not (guided and not setup['plan'].get('calibration', {}).get('seated_knee')):
                c = setup['plan'].get('calibration', {})
                if not all(k in c for k in ('seated_knee', 'standing_knee', 'seated_hip_y', 'standing_hip_y')):
                    raise ValueError('请分别记录舒适坐位与站位基线')
                if c['seated_knee']-c['standing_knee'] < 20 or c['seated_hip_y']-c['standing_hip_y'] < .05:
                    raise ValueError('坐位/站位基线区分不足，请检查完整下肢视野并重新记录')
                if c.get('provenance') != self._calibration_provenance():
                    raise ValueError('坐站基线不属于当前来源、尺寸、侧别或机位，请重新记录')
                from .joint_calibration import preparation_binding
                if c.get('sampling_identity') is not None and not same_conditions(
                        c['sampling_identity'], preparation_binding(self)):
                    raise ValueError('坐站基线的记录条件已变化，请重新记录')
        setup['setup_confirmed_at'] = utc_now()
        setup['actual_size_confirmed'] = list(self.latest_packet.image.shape[1::-1])
        setup['source_ref'] = self.source['ref']
        setup['profile_id'] = digest({k: setup.get(k) for k in ('scene_id', 'source_ref', 'view', 'rois', 'placement_revision')}
                                     | {'exercise': exercise, 'side': setup['plan']['side']})[:24]
        setup['profile_version'] = digest({'view': setup['view'], 'rois': setup['rois'], 'size': setup['actual_size_confirmed'],
                                           'calibration': setup['plan'].get('calibration'),
                                           'joint_baseline': setup['plan'].get('joint_baseline'),
                                           'placement_revision': setup['placement_revision']})[:16]
        if self.dual_config:
            setup['profile_version'] = digest({'primary_profile': setup['profile_version'], 'dual_camera': setup['dual_camera']})[:16]
        self.storage.save_profile(setup)
        self.setup, self.confirmed = setup, True
        from .joint_calibration import preparation_binding
        self.confirmation_binding = preparation_binding(self)
        self.confirmation_absent_since = None
        self.confirmation_withdrawn, self.confirmation_reacquired = '', False
        return copy.deepcopy(setup)

    def start(self):
        if self.pending is not None or self.state != 'PREVIEW' or not self.confirmed:
            # Say what changed instead of only repeating that a confirmation is missing.
            raise ValueError(self.confirmation_withdrawn if self.confirmation_withdrawn and self.state == 'PREVIEW'
                             else '需要有效预览和本次核对后才能开始')
        # A guided, timed session still needs a working input and this preview's
        # human acknowledgement; only the automatic measurement gate is relaxed.
        guided = self.setup.get('continuation_mode') == 'guided' and self.setup['scene_id'] == 'rehab'
        if self.latest_pose is None or self.latest_observation is None:
            raise ValueError('尚未取得画面，请重新打开预览')
        if not guided and self.latest_observation.status != 'VALID':
            raise ValueError('尚未取得有效的单人姿态，请检查模型与站位')
        if self.latest_observation.status == 'MULTI_PERSON':
            raise ValueError('画面中不止一位，请只保留当前参与者后重新核对')
        if self.dual_config:
            self._validate_current_pair()
            sizes = self.setup['dual_camera']['confirmed_sizes']
            from .dual_camera import other_view
            primary = self.dual_config['primary_view']
            if list(self.latest_pose.size) != sizes[primary] or list(self.latest_pose.paired_pose.size) != sizes[other_view(primary)]:
                raise ValueError('两路采集尺寸已变化，请重新确认机位')
        plan = copy.deepcopy(self.setup['plan'])
        if not str(plan.get('participant_id', '')).strip():
            raise ValueError('请先选择当前用户')
        if self.setup['scene_id'] == 'rehab':
            from .joint_calibration import preparation_binding
            binding = preparation_binding(self)
            if not same_conditions(self.confirmation_binding, binding):
                self.confirmed = False
                raise ValueError('拍摄条件已变化，请重新完成本次核对')
            sampling = (plan.get('calibration') or {}).get('sampling_identity')
            if sampling is not None and not same_conditions(sampling, binding):
                raise ValueError('坐站基线的记录条件已变化，请重新记录')
            if not guided or plan.get('joint_baseline'):
                self._check_joint_baseline(plan)
            necessary = exercise_spec(plan['exercise_id'])['required_metrics']
            if not guided and any(self.latest_observation.value(k) is None for k in necessary):
                raise ValueError(measurement_hint(self.latest_observation, plan, self.latest_pose.schema_id)
                                 or '动作必要关节不可见，请调整机位后再开始')
            if plan.get('submode') not in ('assessment', 'training'):
                raise ValueError('请明确选择身体评估或训练指导')
            if plan['submode'] == 'training':
                plan.pop('assessment_batch_id', None)
                plan.pop('assessment_entry_key', None)
                if not plan.get('training_plan_confirmed'):
                    raise ValueError('请先使用自动安排，或设置并确认本次训练计划')
                profile = build_body_profile(self.storage.list_sessions(), plan['participant_id'],
                                             self.source['kind'], self.source['usage_context'])
                reference = build_training_reference(profile, plan['exercise_id'], plan['side'])
                selected = plan.get('assessment_reference') or {}
                if reference.get('status') != 'ASSESSED' or not selected.get('session_id'):
                    raise ValueError('请先完成此用户、动作与侧别的有效评估，再从身体信息进入训练')
                if reference.get('session_id') != selected.get('session_id'):
                    raise ValueError('评估记录已更新或已删除，请回到身体信息重新选择')
                # Rebuild from saved evidence; never trust a UI-supplied measurement or goal.
                plan['assessment_reference'] = copy.deepcopy(reference)
                if plan.get('saved_plan_reference'):
                    from .training_plans import validate_saved_binding
                    supplied = plan['saved_plan_reference']
                    saved = self.storage.get_training_plan(supplied.get('id'))
                    if (saved or {}).get('record_origin') == 'assessment_rules':
                        from .automatic_plans import validate_automatic_use
                        if guided:
                            raise ValueError('自动计划需使用自动观察；引导计时请另选普通练习，不用于核实本计划')
                        validate_automatic_use(saved, supplied.get('entry_key'), profile,
                                               self.storage.list_sessions(), self.storage.get_participant(plan['participant_id']), plan)
                    bound = validate_saved_binding(saved, supplied, plan,
                        dict(participant_id=plan['participant_id'], source_kind=self.source['kind'],
                             usage_context=self.source['usage_context']))
                    if (reference.get('conditions') or {}).get('measurement_contract') != bound['item']['measurement_contract']:
                        raise ValueError('评估与来源计划的测量定义不一致，请重新评估并选择计划')
                    plan['saved_plan_reference'] = bound
            else:
                plan.pop('assessment_reference', None)
                plan.pop('saved_plan_reference', None)
                plan['training_plan_confirmed'] = False
                if plan.get('assessment_batch_id') or plan.get('assessment_entry_key'):
                    from .assessment_batches import validate_binding
                    validate_binding(self.storage.get_assessment_batch(plan.get('assessment_batch_id')),
                                     dict(participant_id=plan['participant_id'], source_kind=self.source['kind'],
                                          usage_context=self.source['usage_context']),
                                     plan['exercise_id'], plan['side'], plan.get('assessment_entry_key'))
        self.setup['plan'] = copy.deepcopy(plan)
        if self.setup['plan']['needs_companion'] and not self.setup.get('companion_confirmed'):
            raise ValueError('训练计划要求陪同，请确认陪同者在场')
        scene = self.setup['scene_id']
        if scene == 'rehab':
            engine = (GuidedEngine(plan) if guided else
                      TrainingEngine(plan) if plan['submode'] == 'training' else RehabEngine(plan))
        else:
            from .activity import ActivityEngine
            from .bedroom import BedroomEngine
            from .safety import SafetyEngine
            engine = {'activity': ActivityEngine, 'bedroom_demo': BedroomEngine, 'safety_demo': SafetyEngine}[scene](self.setup)
        participant_snapshot = self.storage.get_participant(plan['participant_id'])
        run_id = uuid4().hex
        context = self._context(run_id)
        packet = self.latest_packet
        self.setup['preprocessing'] = {k: self.vision_config.get(k) for k in ('imgsz', 'keypoint_conf_min', 'filter_tau_s', 'invalid_gap_s', 'device_at_start')}
        self.session = {'id': run_id, 'run_id': run_id, 'status': 'RUNNING', 'scene_id': self.setup['scene_id'],
                        'source_ref': self.source['ref'], 'source_kind': self.source['kind'],
                        'capture_mode': 'dual' if self.dual_config else 'single',
                        'usage_context': self.source['usage_context'], 'submode': plan['submode'],
                        'exercise_id': plan['exercise_id'], 'side': plan['side'],
                        'participant_id': plan['participant_id'], 'recording_id': self.source.get('recording_id', run_id),
                        'participant_snapshot': copy.deepcopy(participant_snapshot),
                        'start_utc': utc_now(), 'local_utc_offset': datetime.now().astimezone().strftime('%z'),
                        'time_basis': packet.time_basis, 'generation': context.generation, 'epoch': context.epoch,
                        'device_ref': self.source.get('device_ref'), 'backend': self.source.get('device_ref', {}).get('backend'),
                        'resolved_index_at_start': self.camera.resolved.index if self.camera.resolved else None,
                        'profile_id': self.setup['profile_id'], 'profile_version': self.setup['profile_version'],
                        'model_manifest_id': self.latest_pose.model_manifest_id,
                        'schema_id': self.latest_pose.schema_id, 'coordinate_space': self.latest_pose.coordinate_space,
                        'keypoint_order_version': self.latest_pose.keypoint_order_version,
                        'joint_order': joint_names(self.latest_pose.schema_id),
                        'pose_backend': self.latest_pose.backend, 'target_kind': self.latest_pose.target_kind,
                        'measurement_limitations': exercise_spec(plan['exercise_id'])['guide'] if self.setup['scene_id'] == 'rehab' else None,
                        'measurement_contract': exercise_spec(plan['exercise_id'])['measurement_contract'] if self.setup['scene_id'] == 'rehab' else None,
                        'rule_version': RULE_VERSION, 'preprocess_version': PREPROCESS_VERSION,
                        'preprocessing_hash': digest(self.setup['preprocessing']),
                        'requested_capture': {k: self.capture_options.get(k) for k in ('width', 'height', 'fps')} if self.source['kind'] == 'LIVE_CAMERA' else None,
                        'capture_backend_report': copy.deepcopy(self.input_diagnostics),
                        'plan_hash': digest(plan), 'config_snapshot': copy.deepcopy(self.setup),
                        'movement_timing_version': engine.summary().get('movement_timing_version') if scene == 'rehab' else None,
                        'actual_capture': {'size': list(packet.image.shape[1::-1]), 'reported_fps': packet.reported_fps,
                                           'received_fps': packet.received_fps},
                        'repetitions': [], 'events': [], 'metrics': [], 'summary': {}}
        if scene == 'rehab':
            # Keep the operating mode with the evidence: a guided, timed run is a
            # different kind of record, never a relabelled automatic measurement.
            self.session['measurement_mode'] = measurement_mode(self.setup.get('continuation_mode'))
            self.session['continuation'] = {'mode': self.session['measurement_mode'],
                                            'prompt_plan': prompt_plan() if guided else None,
                                            'prompted_cycles': 0, 'self_reports': []}
        if self.dual_config:
            from .dual_view import session_snapshot
            self.session['dual_camera'] = session_snapshot(self)
        if plan.get('assessment_reference'):
            self.session['assessment_reference'] = copy.deepcopy(plan['assessment_reference'])
        if plan.get('saved_plan_reference'):
            self.session['saved_plan_reference'] = copy.deepcopy(plan['saved_plan_reference'])
        if scene == 'rehab' and plan['submode'] == 'assessment' and plan.get('assessment_batch_id'):
            self.session.update(assessment_batch_id=plan['assessment_batch_id'],
                                assessment_entry_key=plan['assessment_entry_key'])
        if self.setup['poses_consent']:
            self.session['poses'] = []
        self.engine = engine
        if isinstance(self.engine, TrainingEngine):
            self.session['training_execution_version'] = 'sets-rest-1'
        try:
            self.storage.save_session(self.session)
        except Exception:
            self.stop('initial_save_failed')
            raise
        self.context = context
        self.gate.reset(context)
        self.analyzer = self._analyzer(plan['side'])
        self._reset_secondary(context)
        self.processed_frames = self.dropped_frames = 0
        self.previous_seq = None
        self.latest_packet = self.latest_pose = self.latest_observation = None
        if self.source['kind'] != 'SYNTHETIC':
            try:
                self.camera.change_context(context)
            except Exception:
                self.stop('context_change_failed')
                raise
        self.state = 'ONLINE'
        return context

    def consume(self, packet, pose):
        if packet.context != self.context or not self.gate.admit(pose):
            return False
        if isinstance(self.engine, TrainingEngine) and not self.engine.accepts_time(pose.time_s):
            return False
        if tuple(packet.image.shape[1::-1]) != tuple(pose.size):
            raise ValueError('画面与姿态尺寸不一致')
        backend = exercise_spec(self.setup['plan']['exercise_id'])['backend'] if self.setup['scene_id'] == 'rehab' else 'yolo'
        if pose.schema_id != BACKEND_SCHEMAS[backend]:
            raise ValueError('所选动作与关键点组件不匹配，未进行测量')
        if self.state == 'ONLINE' and list(pose.size) != self.setup.get('actual_size_confirmed'):
            self.stop('frame_shape_changed')
            raise RuntimeError('采集尺寸改变，已结束任务；需重新确认机位与区域')
        auxiliary = None
        if self.dual_config:
            from .dual_view import validate_pair_pose
            from .dual_camera import other_view
            import time
            now = time.monotonic() if self.source['kind'] == 'LIVE_CAMERA' and not self.test_mode else None
            _, auxiliary_pose = validate_pair_pose(packet, pose, self.dual_config['primary_view'], now=now)
            if not self.secondary_gate.admit(auxiliary_pose):
                return False
            if self.state == 'ONLINE' and list(auxiliary_pose.size) != self.setup['dual_camera']['confirmed_sizes'][other_view(self.dual_config['primary_view'])]:
                self.stop('secondary_frame_shape_changed')
                raise RuntimeError('辅助摄像头尺寸改变，已结束双摄任务；请重新确认机位')
            auxiliary = self.secondary_analyzer.analyze(auxiliary_pose)
        obs = self.analyzer.analyze(pose)
        primary_observation = obs
        self.latest_primary_observation, self.latest_secondary_observation = obs, auxiliary
        from .dual_view import identity_visible
        if auxiliary is not None and not identity_visible(auxiliary):
            obs = replace(obs, status='UNKNOWN', metrics={}, reasons=obs.reasons+['secondary_view_'+auxiliary.status.lower()])
        self.latest_packet, self.latest_pose, self.latest_observation = packet, pose, obs
        if self.carried_preparation and self.state in ('CONNECTING', 'PREVIEW'):
            self._adopt_carried_preparation()
        if self.state == 'PREVIEW' and self.setup['scene_id'] == 'rehab':
            self._review_confirmation(pose, obs, auxiliary)
        if self.state == 'CONNECTING':
            self.state = 'PREVIEW'
        if self.state != 'ONLINE' or self.engine is None:
            return True
        if auxiliary is not None:
            if (auxiliary.status == 'MULTI_PERSON' or (auxiliary.track_key is None and pose.paired_pose.people) or
                    self.active_secondary_track and auxiliary.track_key and auxiliary.track_key != self.active_secondary_track):
                from .dual_view import observation_row
                invalid = replace(obs, status='UNKNOWN', metrics={}, reasons=['secondary_view_identity_ambiguous'])
                self.engine.process(invalid)
                self.session['dual_camera']['observations'].append(observation_row(self, packet, primary_observation, auxiliary))
                self.stop('dual_identity_ambiguous')
                self.last_error = '辅助机位的参与者归属不明确，双摄任务已保存；请重新预览并确认同一人'
                return True
            if auxiliary.track_key:
                self.active_secondary_track = auxiliary.track_key
        previous_track = getattr(self, 'active_track', None)
        if (primary_observation.status == 'MULTI_PERSON' or (primary_observation.track_key is None and pose.people)
                or (previous_track and obs.track_key and obs.track_key != previous_track)):
            self.engine.process(primary_observation)
            if auxiliary is not None:
                from .dual_view import observation_row
                self.session['dual_camera']['observations'].append(observation_row(self, packet, primary_observation, auxiliary))
            self.stop('identity_ambiguous')
            self.last_error = '参与者归属不明确，任务已保存；请重新预览并人工确认'
            return True
        if obs.track_key:
            self.active_track = obs.track_key
        training_event_count = len(self.engine.training_events) if isinstance(self.engine, TrainingEngine) else None
        self.engine.process(obs)
        self.processed_frames += 1
        if self.previous_seq is not None:
            self.dropped_frames += max(0, pose.seq-self.previous_seq-1)
        self.previous_seq = pose.seq
        included = not isinstance(self.engine, TrainingEngine) or self.engine.last_observation_included
        if auxiliary is not None:
            from .dual_view import observation_row
            self.session['dual_camera']['observations'].append(observation_row(
                self, packet, primary_observation, auxiliary, included=included if isinstance(self.engine, TrainingEngine) else None))
            streams = self.session['dual_camera']['streams']
            for view, frame, frame_pose in ((self.dual_config['primary_view'], packet, pose),
                                            (self.session['dual_camera']['secondary_view'], packet.paired_frame, pose.paired_pose)):
                streams[view]['actual_capture'].update(received_fps=frame.received_fps, inference_ms=frame_pose.inference_ms)
        self.session['metrics'].append({'time_s': obs.time_s, 'seq': pose.seq, 'phase': self.engine.phase,
                                        'training_stage': self.engine.stage if isinstance(self.engine, TrainingEngine) else None,
                                        'included_in_training': included if isinstance(self.engine, TrainingEngine) else None,
                                        'observation_status': obs.status, 'metrics': asdict_metrics(obs.metrics) if included else {},
                                        'annotation_origin': 'prediction', 'reasons': obs.reasons})
        if self.setup['poses_consent']:
            self.session['poses'].append({'pose': asdict(pose), 'center_raw_px': obs.center_raw_px,
                                           'local_pose': obs.local_pose})
        self.session['actual_capture'].update(received_fps=packet.received_fps, inference_ms=pose.inference_ms)
        for event in getattr(self.engine, 'events', []):
            if event['id'] not in self.persisted_events:
                event.update(run_id=self.context.run_id, source_kind=self.context.source_kind,
                             participant_id=self.setup['plan']['participant_id'],
                             usage_context=self.context.usage_context, scene_id=self.context.scene_id,
                             source_ref=self.context.source_ref, profile_id=self.setup['profile_id'],
                             time_basis=self.session['time_basis'], rule_version=RULE_VERSION)
                self.session['events'].append(copy.deepcopy(event))
                try:
                    self.storage.save_event(event)
                except Exception:
                    self.stop('event_save_failed')
                    raise
                self.persisted_events.add(event['id'])
        if training_event_count is not None and training_event_count != len(self.engine.training_events):
            self._checkpoint_training()
        return True

    def record_self_report(self):
        """An explicit human count. Never mixed into measured repetitions."""
        if self.state != 'ONLINE' or self.session is None or self.setup['scene_id'] != 'rehab':
            raise ValueError('请先开始本次康复任务，再记录完成情况')
        continuation = self.session.setdefault('continuation', {'mode': self.session.get('measurement_mode', 'auto_observed'),
                                                                'prompt_plan': None, 'prompted_cycles': 0, 'self_reports': []})
        reports = continuation.setdefault('self_reports', [])
        observed = self.latest_observation.time_s if self.latest_observation else None
        reports.append({'number': len(reports)+1, 'at_utc': utc_now(),
                        'observation_time_s': observed if isinstance(observed, (int, float)) else None,
                        'origin': 'participant_report', 'annotation_origin': 'human',
                        'measured': False})
        if isinstance(self.engine, GuidedEngine):
            self.engine.note_self_report(len(reports))
        self._checkpoint_continuation()
        return len(reports)

    def set_guided_pause(self, paused):
        """Pause or resume the guided prompt. Capture and privacy are unchanged."""
        if self.state != 'ONLINE' or self.session is None or not isinstance(self.engine, GuidedEngine):
            raise ValueError('只有进行中的引导计时可以暂停提示')
        if self.engine.set_paused(paused):
            self.session['continuation']['prompt_pauses'] = self.engine.pause_count
            self._checkpoint_continuation()
        return self.engine.paused

    def note_guided_prompt(self, cycle):
        if self.state != 'ONLINE' or self.session is None or not isinstance(self.engine, GuidedEngine):
            return False
        before = self.engine.prompted_cycles
        self.engine.note_prompt_cycle(cycle)
        if self.engine.prompted_cycles == before:
            return False
        self.session['continuation']['prompted_cycles'] = self.engine.prompted_cycles
        self._checkpoint_continuation()
        return True

    def _checkpoint_continuation(self):
        self.session['summary'] = self.engine.summary()
        try:
            self.storage.save_session(self.session)
        except Exception as exc:
            # A checkpoint is a convenience, not the save gate. Record the
            # attempt with the session instead of reporting a broken input.
            self.session.setdefault('continuation', {})['checkpoint_error'] = dict(
                at_utc=utc_now(), message=str(exc))

    def checkpoint_activity(self):
        if self.session is None or self.setup['scene_id'] != 'activity':
            return
        self.session.update(summary=self.engine.summary(), tasks=copy.deepcopy(self.engine.tasks),
                            intervals=copy.deepcopy(self.engine.intervals))
        try:
            self.storage.save_session(self.session)
        except Exception:
            self.stop('activity_checkpoint_failed')
            raise

    def _checkpoint_training(self):
        self._update_dual_diagnostics()
        self.session.update(summary=self.engine.summary(), repetitions=copy.deepcopy(self.engine.repetitions),
                            processed_frames=self.processed_frames, skipped_capture_frames=self.dropped_frames)
        from .dual_view import update_summary
        update_summary(self.session)
        try:
            self.storage.save_session(self.session)
        except Exception:
            self.stop('training_checkpoint_failed')
            raise

    def training_control(self, action, now=None, *, setup_confirmed=False):
        if self.state != 'ONLINE' or not isinstance(self.engine, TrainingEngine) or self.pending is not None:
            raise ValueError('请先开始已确认的训练计划')
        if self.source['kind'] == 'LIVE_CAMERA':
            import time
            t = time.monotonic() if now is None else now
        else:
            t = self.latest_observation.time_s if self.latest_observation else self.engine.clock_t
        if type(t) not in (int, float) or not math.isfinite(t):
            raise ValueError('尚未取得有效输入时间，请等待新画面')
        if action in ('resume', 'next_set'):
            if setup_confirmed is not True:
                raise ValueError('请先确认本人、测试侧与机位未变')
            obs = self.latest_observation
            packet, pose = self.latest_packet, self.latest_pose
            if (obs is None or obs.status != 'VALID' or not obs.track_key
                    or packet is None or pose is None or packet.context != self.context or pose.context != self.context
                    or packet.seq != pose.seq or obs.time_s != pose.time_s
                    or any(type(obs.value(k)) not in (int, float) or not math.isfinite(obs.value(k))
                           for k in self.engine.spec['required_metrics'])
                    or (self.source['kind'] == 'LIVE_CAMERA' and
                        (type(packet.received_monotonic) not in (int, float)
                         or not math.isfinite(packet.received_monotonic)
                         or not 0 <= t-packet.received_monotonic <= 3))):
                raise ValueError('请让当前参与者和必要关节重新清楚入镜，再继续')
            if self.dual_config:
                self._validate_current_pair()
        self.engine.control(action, t)
        if action in ('resume', 'next_set'):
            self.engine.training_events[-1]['setup_manually_confirmed'] = True
        if action in ('resume', 'next_set'):
            self.analyzer = self._analyzer(self.setup['plan']['side'])
            if self.dual_config:
                self.secondary_analyzer = self._new_secondary_analyzer()
        self._checkpoint_training()
        return self.engine.summary()

    def _update_dual_diagnostics(self):
        worker = self.camera.worker
        if self.session and self.dual_config and callable(getattr(worker, 'diagnostics', None)):
            self.session['dual_camera']['capture_pairing_diagnostics'] = copy.deepcopy(worker.diagnostics())

    def stop(self, reason='user_stop', privacy=False):
        if self.pending is not None and self.session is None:
            self.camera.stop()
            self.state = 'SAVE_FAILED'
            raise RuntimeError('仍有未保存结果，请先重试保存')
        self._update_dual_diagnostics()
        self.generation += 1
        self.gate.reset()
        self.context = None
        self.confirmed = False
        self.confirmation_binding = self.confirmation_absent_since = None
        self.confirmation_withdrawn, self.confirmation_reacquired = '', False
        self.carried_preparation, self.preparation_reuse = None, None
        self.active_track = None
        self._reset_secondary()
        self.latest_packet = self.latest_pose = self.latest_observation = None
        stop_error = None
        try:
            self.camera.stop()
        except Exception as exc:
            stop_error = exc
        if self.session is not None:
            self.engine.finish(reason)
            snapshot = self.session
            snapshot.update(end_utc=utc_now(), stop_reason=reason, status='FINISHED' if reason == 'user_stop' else 'INTERRUPTED',
                            summary=self.engine.summary(), repetitions=copy.deepcopy(getattr(self.engine, 'repetitions', [])),
                            intervals=copy.deepcopy(getattr(self.engine, 'intervals', [])), tasks=copy.deepcopy(getattr(self.engine, 'tasks', [])),
                            processed_frames=self.processed_frames, skipped_capture_frames=self.dropped_frames)
            from .dual_view import update_summary
            update_summary(snapshot)
            if snapshot.get('scene_id') == 'rehab':
                # Human-reported completion stays a separate, labelled count.
                reports = (snapshot.get('continuation') or {}).get('self_reports') or []
                snapshot['summary']['self_reported_reps'] = len(reports)
                snapshot['summary'].setdefault('measurement_mode', snapshot.get('measurement_mode', 'auto_observed'))
            self.pending = self.storage.authorized_snapshot(snapshot)
            self.session, self.engine = None, None
            try:
                self.retry_save()
            except Exception as exc:
                self.last_error = f'报告保存失败，结果已保留待重试：{exc}'
                self.state = 'SAVE_FAILED'
                raise RuntimeError(self.last_error) from exc
        self.state = 'ERROR' if stop_error else ('PRIVACY_PAUSED' if privacy else 'UNSELECTED')
        if stop_error:
            raise stop_error

    def retry_save(self):
        if self.pending is None:
            return
        try:
            sid = self.storage.save_session(self.pending)
        except Exception:
            try:
                temp = self.pending_path.with_suffix('.tmp')
                temp.write_text(dumps(self.pending), encoding='utf-8')
                temp.replace(self.pending_path)
            except OSError:
                pass  # In-memory snapshot remains intact even if the disk is full.
            raise
        self.last_saved_id, self.pending = sid, None
        if self.pending_path.exists():
            self.pending_path.unlink()
        self.state = 'UNSELECTED'

    def backup_pending(self, directory):
        if self.pending is None:
            raise ValueError('没有待保存结果')
        target = Path(directory)/('pending-'+self.pending['id']+'.json')
        with target.open('x', encoding='utf-8') as stream:
            stream.write(dumps(self.pending, indent=2))
        self.recovery_backup_dir = target.parent
        return target

    def discard_pending(self, reason):
        if self.pending is None or not reason.strip():
            raise ValueError('明确填写丢弃原因后才能继续')
        record = {'run_id': self.pending['id'], 'reason': reason, 'at_utc': utc_now()}
        try:
            self.storage.audit('discard_pending_session', record)
        except Exception:
            directory = self.recovery_backup_dir or self.pending_path.parent
            with (directory/'recovery-actions.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(dumps({'action': 'discard_pending_session', **record})+'\n')
        if self.pending_path.exists():
            self.pending_path.unlink()
        self.pending = None
        self.state = 'UNSELECTED'

    def summary(self):
        return self.engine.summary() if self.engine else {}


def asdict_metrics(metrics):
    return {k: asdict(v) for k, v in metrics.items()}
