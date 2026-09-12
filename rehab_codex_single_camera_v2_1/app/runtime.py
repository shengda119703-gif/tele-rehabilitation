from __future__ import annotations

import copy
import math
from dataclasses import asdict
from pathlib import Path
import queue
import threading
import time
from types import SimpleNamespace

from .audio import AudioGate
from .camera_manager import CameraManager
from .domain import digest, dumps, utc_now, PacketGate
from .reports import export_session, render_report, render_body_profile, export_body_profile
from .assessment import build_body_profile
from .exercises import exercise_spec
from .measurement_guidance import measurement_hint, adjustment_action
from .guidance import GuidancePolicy
from .guided import prompt_state
from .joint_calibration import same_conditions
from .scene_controller import SceneController
from .settings import ROOT, load_settings, default_setup
from .source_worker import put_latest
from .storage import Storage
from .vision import VisionWorker


def input_timeout_reason(state, now, connect_started_wall, last_frame_wall, settings):
    """Keep slow camera startup separate from an established stream going stale."""
    if state == 'CONNECTING' and connect_started_wall is not None:
        if now-connect_started_wall > settings.get('connect_timeout_s', 15):
            return 'connect_timeout'
    elif state in ('PREVIEW', 'ONLINE') and last_frame_wall is not None:
        if now-last_frame_wall > settings.get('stale_after_s', 3):
            return 'stream_stale'
    return None


class Runtime:
    """UI sends commands; this thread owns orchestration, rules, and storage calls."""
    # Interface tolerances for ordinary tracking noise. They buffer presentation
    # and sampling patience only; no measurement threshold is relaxed by them.
    dropout_tolerance_s = 1.5
    crowd_tolerance_s = .8
    sampling_window_s = 6.

    def __init__(self, data_dir=None):
        self.data_dir = Path(data_dir or ROOT/'data')
        self.commands, self.messages, self.views = queue.Queue(), queue.Queue(), queue.Queue(maxsize=1)
        self.stop_event = threading.Event()
        self.ready = threading.Event()
        self.controller = None
        self.preview_history = []
        self.guidance_policy = GuidancePolicy()
        self.preparation = None
        self.connect_started_wall = None
        self.last_frame_wall = None
        self.last_sound_count = 0
        self.last_sound_event = None
        self.capture_settings = {}
        self.camera_test = False
        self.camera_test_frames = 0
        self.guided_started = None
        self.guided_paused_at = None
        self._guided_key = None
        self.dual_receive_gate = PacketGate()
        self.thread = threading.Thread(target=self._run, name='application-runtime', daemon=True)
        self.thread.start()

    def command(self, name, **kw):
        self.commands.put((name, kw))

    def _dispatch_optional(self, name, kw):
        # Freeze only structured evidence on the owning thread; never pass live
        # controllers, frames, cameras or inference objects to optional workers.
        if name == 'silver':
            c = self.controller
            summary = copy.deepcopy(c.summary())
            frozen = SimpleNamespace(session=copy.deepcopy(c.session), setup=copy.deepcopy(c.setup),
                source=copy.deepcopy(c.source), state=c.state, context=c.context,
                summary=lambda: copy.deepcopy(summary))
            kw = dict(copy.deepcopy(kw), _controller_snapshot=frozen, _snapshot_utc=utc_now(), _generation=c.generation)
        else:
            kw = copy.deepcopy(kw)
        if not getattr(self, '_optional_thread', None):
            self._optional_jobs = queue.Queue(maxsize=16)
            self._optional_stopping = threading.Event()
            self._optional_thread = threading.Thread(target=self._run_optional, name='optional-support', daemon=True)
            self._optional_thread.start()
        try:
            self._optional_jobs.put_nowait((name, kw))
        except queue.Full:
            raise ValueError('可选服务正忙，本次操作未接收；请稍后重试')

    def _run_optional(self):
        try:
            while not self._optional_stopping.is_set():
                try:
                    name, kw = self._optional_jobs.get(timeout=.1)
                except queue.Empty:
                    continue
                try:
                    self._execute(name, kw)
                except Exception as exc:
                    self._message('error', text=str(exc), command=name, request_id=kw.get('request_id'))
                finally:
                    self._message('command_done', command=name)
        finally:
            if getattr(self, 'family_demo', None):
                try:
                    self.family_demo.stop()
                except Exception:
                    pass

    def _close_optional(self):
        if getattr(self, '_optional_thread', None):
            self._optional_stopping.set()
            self._optional_thread.join(timeout=25)
            if self._optional_thread.is_alive():
                self._message('error', command='silver', text='可选服务退出超时，未确认尚在处理的操作结果')

    def _view(self, packet=None, pose=None, error=None, *, operation_error=False):
        c = self.controller
        testing = getattr(self, 'camera_test', False)
        hint = None
        if not testing and pose and c.latest_observation and c.state in ('PREVIEW', 'ONLINE') and c.setup['scene_id'] == 'rehab':
            hint = measurement_hint(c.latest_observation, c.setup['plan'], pose.schema_id, preview=c.state == 'PREVIEW')
        dual_view = None
        if c.dual_config:
            from .dual_camera import other_view
            from .dual_view import auxiliary_hint, AUXILIARY_VERSION
            auxiliary = c.latest_secondary_observation if pose else None
            dual_view = dict(version=c.dual_config['version'], primary_view=c.dual_config['primary_view'],
                             secondary_view=other_view(c.dual_config['primary_view']),
                             pairing=copy.deepcopy(packet.pairing) if packet else None,
                             auxiliary_version=AUXILIARY_VERSION,
                             auxiliary_status=auxiliary.status if auxiliary else None,
                             auxiliary_metrics={k: asdict(v) for k, v in auxiliary.metrics.items()} if auxiliary else {})
            if not testing and pose:
                hint = auxiliary_hint(c) or hint
        view = {'state': c.state, 'context': c.context, 'summary': {} if testing else c.summary(),
                               'confirmed': False if testing else c.confirmed, 'packet': packet, 'pose': None if testing else pose,
                               'camera_test': testing, 'camera_test_frames': getattr(self, 'camera_test_frames', 0),
                               'error': error, 'operation_error': operation_error, 'last_saved_id': c.last_saved_id,
                               'pending': c.pending is not None,
                               'dual_camera': dual_view,
                               'measurement_hint': hint,
                               'observation_status': c.latest_observation.status if pose and c.latest_observation else None}
        if not testing and c.setup.get('scene_id') == 'rehab':
            plan = c.setup['plan']
            view['continuation_mode'] = c.setup.get('continuation_mode', 'auto')
            view['guided_prompt'] = self._guided_prompt()
            view['preparation_reuse'] = copy.deepcopy(c.preparation_reuse)
            view['self_reported'] = len(((c.session or {}).get('continuation') or {}).get('self_reports') or [])
            obs = c.latest_observation if pose else None
            spec = exercise_spec(plan['exercise_id'])
            keys = [spec.get('raw_metric', spec['metric'])] if c.state == 'PREVIEW' else spec['required_metrics']
            fresh = bool(packet) and (packet.context.source_kind != 'LIVE_CAMERA' or 0 <= time.monotonic()-packet.received_monotonic <= 3)
            if fresh and packet.paired_frame and packet.context.source_kind == 'LIVE_CAMERA':
                fresh = 0 <= time.monotonic()-packet.paired_frame.received_monotonic <= 3
            view['current_measurement_valid'] = bool(fresh and obs and obs.status == 'VALID' and
                all(isinstance(obs.value(k), (float, int)) and math.isfinite(obs.value(k)) for k in keys))
            view['adjustment'] = adjustment_action(obs, plan, pose.schema_id if pose else '')
            view['identity_ambiguous'] = bool(obs and (obs.status == 'MULTI_PERSON' or (obs.track_key is None and pose.people)))
            auxiliary = c.latest_secondary_observation if pose and c.dual_config else None
            if auxiliary is not None:
                from .dual_view import identity_visible
                view['auxiliary_missing'] = identity_visible(auxiliary) and any(not m.valid for m in auxiliary.metrics.values())
                view['identity_ambiguous'] |= auxiliary.status == 'MULTI_PERSON' or (auxiliary.track_key is None and bool(pose.paired_pose.people))
                if not identity_visible(auxiliary):
                    view['adjustment'] = '请让同一位参与者进入辅助画面。'
            if c.state == 'PREVIEW':
                baseline = plan.get('joint_baseline') or {}
                calibration = plan.get('calibration') or {}
                instruction = '核对本次参与者与机位，然后确认准备。'
                if c.confirmed:
                    instruction = '准备已确认，可以开始'+('训练。' if plan['submode'] == 'training' else '评估。')
                elif plan['exercise_id'] == 'sit_to_stand':
                    if 'seated_knee' not in calibration:
                        instruction = '请在舒适坐位保持，倒计时记录坐位。'
                    elif 'standing_knee' not in calibration:
                        instruction = '请在舒适站位保持，倒计时记录站位。'
                elif not baseline and spec['baseline_required']:
                    instruction = ('请先舒适侧抬臂，再倒计时记录起点。' if plan['exercise_id'] == 'shoulder_adduction'
                                   else '保持舒适起点，倒计时记录。')
                elif baseline and spec['directional_calibration'] and not baseline.get('direction_sign'):
                    instruction = '按所选动作方向小幅试做，再倒计时记录。'
                if getattr(self, 'preparation', None):
                    instruction = '请保持当前舒适姿势，等待采样完成。'
                view['preparation_instruction'] = instruction
            if not hasattr(self, 'guidance_policy'):
                self.guidance_policy = GuidancePolicy()
            view['guidance'] = self.guidance_policy.render(view, plan, now=time.monotonic())
        put_latest(self.views, view)

    def _message(self, kind, **data):
        self.messages.put({'kind': kind, **data})

    def _guided_prompt(self):
        """Local prompt clock for a guided session. Presentation only."""
        c = self.controller
        if (c.state != 'ONLINE' or c.setup.get('scene_id') != 'rehab'
                or c.setup.get('continuation_mode') != 'guided' or self.guided_started is None):
            return None
        paused_at = self.guided_paused_at
        state = prompt_state((paused_at if paused_at is not None else time.monotonic())-self.guided_started,
                             c.setup['plan']['exercise_id'])
        if state is not None and paused_at is not None:
            state = dict(state, paused=True)
        return state

    def _preparation_binding(self):
        from .joint_calibration import preparation_binding
        return preparation_binding(self.controller)

    def _cancel_preparation(self, text='本次采样已取消。'):
        if getattr(self, 'preparation', None) is not None:
            self.preparation = None
            self.preview_history = []
            self._message('preparation', active=False, text=text, context=self.controller.context)

    def _begin_preparation(self, sample, position):
        c = self.controller
        if c.state != 'PREVIEW' or c.setup['scene_id'] != 'rehab':
            raise ValueError('请先打开当前动作的预览')
        if sample not in ('baseline', 'joint_baseline') or position not in (
                ('seated', 'standing') if sample == 'baseline' else ('rest', 'direction')):
            raise ValueError('未知的准备采样')
        if sample == 'joint_baseline' and position == 'direction' and not c.live_joint_baseline:
            raise ValueError('请先记录本次舒适起点，再记录活动方向')
        binding = self._preparation_binding()
        if (not binding or not binding['track_key'] or c.latest_observation.status == 'MULTI_PERSON'
                or (c.dual_config and (not binding['auxiliary']['track_key'] or c.latest_secondary_observation.status == 'MULTI_PERSON'))):
            raise ValueError('请先让当前参与者清楚入镜，再开始倒计时')
        self._cancel_preparation()
        c.confirmed = False
        self.preview_history = []
        self.preparation = dict(sample=sample, position=position, binding=binding, context=c.context,
                                countdown_until=time.monotonic()+3., sampling_until=None, last_count=None)
        self._tick_preparation()

    def _tick_preparation(self, now=None):
        import math
        preparation = getattr(self, 'preparation', None)
        if preparation is None:
            return
        c = self.controller
        now = time.monotonic() if now is None else now
        binding = self._preparation_binding()
        if (c.state != 'PREVIEW' or c.context != preparation['context'] or
                not same_conditions(binding, preparation['binding'])):
            self._cancel_preparation('拍摄条件已变化，请重新准备后采样。')
            return
        if binding != preparation['binding']:
            # Re-acquired tracking is not a new posture, so this sampling keeps
            # running. The stable window still requires one continuous run under
            # the current track, so observations are never mixed across it.
            preparation['binding'] = binding
        crowded = (c.latest_observation.status == 'MULTI_PERSON' or
                   (c.dual_config and c.latest_secondary_observation.status == 'MULTI_PERSON'))
        missing = (c.latest_observation.status == 'NO_PERSON_DETECTED' or
                   (c.dual_config and c.latest_secondary_observation.status == 'NO_PERSON_DETECTED'))
        # A single dropped frame is not a changed posture. Only a problem that
        # persists ends the sampling, so ordinary tracking flicker is absorbed.
        if crowded or missing:
            since = preparation.setdefault('trouble_since', now)
            limit = self.crowd_tolerance_s if crowded else self.dropout_tolerance_s
            if now-since >= limit:
                self._cancel_preparation('画面中不止一位，请只保留当前参与者后重试。' if crowded else
                                         '一直没看到测试部位，请调整取景后重试，或改用引导计时练习。')
                return
        else:
            preparation.pop('trouble_since', None)
        until = preparation['countdown_until']
        if now < until:
            count = math.ceil(until-now)
            if count != preparation['last_count']:
                preparation['last_count'] = count
                self._message('preparation', active=True, text=f'{count} 秒后采样，请保持当前舒适姿势。', context=c.context)
            return
        if preparation['sampling_until'] is None:
            preparation['sampling_until'] = now+self.sampling_window_s
            preparation['sampling_started_wall'] = now
            self.preview_history = []  # Never sample the pose held before the countdown ended.
            self._message('preparation', active=True, text='正在采样，请稳定保持约 1 秒。', context=c.context)
            if c.source['kind'] == 'REPLAY_FILE':
                try:
                    self.camera.worker.preview_segment(1.2)
                except Exception:
                    self._cancel_preparation('无法读取新的预览片段，请重新打开录像。')
            return
        if self.preview_history:
            try:
                self._execute(preparation['sample'], {'position': preparation['position']})
            except ValueError:
                pass  # A bounded fresh window must satisfy the original measurement gates.
            except Exception:
                self._cancel_preparation('采样未完成，请重新预览后重试。')
                return
            else:
                self.preparation = None
                self._message('preparation', active=False, text='已记录。准备好后核对并确认本次准备。', context=c.context)
                self._view(c.latest_packet, c.latest_pose)
                return
        if now >= preparation['sampling_until']:
            self._cancel_preparation('尚未取得连续稳定画面。可以再试一次，也可以改用引导计时练习。')

    def _collect_preview_observation(self, packet):
        c = self.controller
        if c.state != 'PREVIEW' or c.latest_observation is None:
            return
        preparation = getattr(self, 'preparation', None)
        if preparation and packet.received_monotonic < preparation.get('sampling_started_wall', float('-inf')):
            return  # Inference completion time cannot turn an earlier captured frame into a new sample.
        obs = c.latest_observation
        self.preview_history = [o for o in self.preview_history if 0 <= obs.time_s-o.time_s <= 1.2 and o.track_key == obs.track_key]
        self.preview_history.append(obs)

    def _inference_failed(self, packet, error):
        if getattr(self.controller, 'state', None) in ('PREVIEW', 'ONLINE'):
            had_session = self.controller.session is not None
            dual = bool(self.controller.dual_config)
            if dual:
                self._record_dual_failure('dual_view_inference_error')
            try:
                self.controller.stop('dual_view_inference_error' if dual else 'inference_error')
            except Exception as exc:
                self._message('error', text=str(exc))
            else:
                if had_session and self.controller.last_saved_id:
                    self._message('saved', id=self.controller.last_saved_id)
            self.preview_history = []
            self.audio.reset()
            self.vision.clear()
            self._view(error=error)
            return
        self.controller.latest_packet = packet
        self.controller.latest_pose = self.controller.latest_observation = None
        self.controller.latest_secondary_observation = self.controller.latest_primary_observation = None
        self.preview_history = []
        self.audio.reset(self.controller.context)
        self._view(packet, error=error)

    def _record_dual_failure(self, category, view=None):
        c = self.controller
        if c.session and c.dual_config:
            c.session['dual_camera']['input_failure'] = dict(category=category, view=view, observed_utc=utc_now())

    def _execute(self, name, kw):
        c, store = self.controller, self.store
        if name == 'family_demo':
            demo = getattr(self, 'family_demo', None)
            action = kw.get('action')
            if action == 'start':
                if kw.get('demo_confirmed') is not True or demo:
                    raise ValueError('请明确确认测试资料与联网边界；已有服务请先关闭')
                from .family_demo import FamilyDemo
                self.family_demo = demo = FamilyDemo(self.data_dir/'isolated-family-demo', kw['host'])
            elif action == 'stop' and demo:
                try:
                    demo.stop()
                finally:
                    self.family_demo = demo = None
            elif action == 'approve' and demo:
                demo.approve(kw['id'])
            elif action == 'request' and demo:
                demo.request()
            elif action not in ('status', 'stop'):
                raise ValueError('请先开启隔离测试服务')
            self._message('family_demo', data=demo.status() if demo else dict(running=False))
            return
        if name == 'silver':
            from .silver_store import SilverStore
            from .silver_service import execute
            if not getattr(self, 'silver_store', None):
                self.silver_store = SilverStore(self.data_dir/'silver_support.sqlite3')
            frozen = kw.pop('_controller_snapshot', c)
            at = kw.pop('_snapshot_utc', utc_now())
            generation = kw.pop('_generation', c.generation)
            result = execute(self.silver_store, store, frozen, **kw)
            result['observation_snapshot_utc'] = at
            if c.generation != generation:
                result.update(state='INACTIVE', active_scene=None, live_summary={})
            self._message('silver', data=result)
            return
        if name in ('open', 'camera_test', 'confirm', 'unconfirm', 'start', 'stop', 'privacy', 'switch', 'shutdown', 'cancel_preparation'):
            self._cancel_preparation()
        if getattr(self, 'camera_test', False) and name not in (
                'stop_camera_test', 'stop', 'privacy', 'switch', 'shutdown', 'enumerate', 'remember_camera', 'remember_camera_pair',
                'history', 'participants', 'body_profile', 'report', 'profile', 'events', 'training_review',
                'export', 'export_body_profile', 'longitudinal_history', 'export_longitudinal_history', 'unconfirm'):
            raise ValueError('请先关闭摄像头测试，再开始评估或训练')
        if name == 'enumerate':
            devices = self.camera.enumerate(kw['backend'])
            self._message('devices', backend=kw['backend'], devices=[asdict(d) for d in devices])
        elif name == 'remember_camera':
            self._remember_camera(kw['device'])
        elif name == 'remember_camera_pair':
            self._remember_camera_pair(kw['devices'])
        elif name in ('open', 'camera_test'):
            if name == 'camera_test':
                if c.session is not None or c.pending is not None or c.state in ('ONLINE', 'SAVE_FAILED'):
                    raise ValueError('请先结束并保存本次任务，再测试摄像头')
                if kw['source']['kind'] != 'LIVE_CAMERA':
                    raise ValueError('摄像头测试仅支持实时摄像头')
                self.camera_test = True
                self.camera_test_frames = 0
            self.audio.reset()
            self.vision.clear()
            options = {k: self.capture_settings.get('request_'+k, default) for k, default in (('width', 1280), ('height', 720), ('fps', 30))}
            options.update(kw.get('options') or {})
            setup = default_setup() if name == 'camera_test' else kw['setup']
            if name == 'camera_test' and (kw['source'].get('dual_camera') or {}).get('primary_view') == 'sagittal':
                setup = default_setup(exercise='elbow_flexion')
            c.open(kw['source'], setup, options)
            if c.dual_config:
                self.dual_receive_gate = PacketGate()
                self.dual_receive_gate.reset(c.context)
            self.preview_history = []
            self.connect_started_wall = time.monotonic()
            self.last_frame_wall = None
            self._view()
        elif name == 'confirm':
            confirmed = c.confirm(kw['setup'])
            self._message('confirmed', setup=confirmed)
            self._view(c.latest_packet, c.latest_pose)
            if c.source['kind'] == 'LIVE_CAMERA':
                if c.dual_config:
                    self._remember_camera_pair(c.dual_config['devices'])
                else:
                    self._remember_camera(c.source['device_ref'])
        elif name == 'unconfirm':
            c.confirmed = False
            self._view(c.latest_packet, c.latest_pose)
        elif name == 'start':
            if c.source['kind'] == 'LIVE_CAMERA' and (c.latest_packet is None or time.monotonic()-c.latest_packet.received_monotonic > 3):
                raise ValueError('画面过期，请重新预览')
            c.vision_config['device_at_start'] = self.vision.device
            context = c.start()
            self.guided_started = time.monotonic() if c.setup.get('continuation_mode') == 'guided' else None
            self.guided_paused_at = None
            self._guided_key = None
            if c.dual_config:
                self.dual_receive_gate.reset(context)
            self.vision.clear()
            self.audio.reset(context)
            self.preview_history = []
            self.last_sound_count = 0
            self.last_sound_event = None
            self._view()
        elif name in ('stop', 'privacy', 'switch', 'stop_camera_test'):
            # A late duplicate close must never stop a subsequent clinical run.
            if name == 'stop_camera_test' and not getattr(self, 'camera_test', False):
                self._message('camera_test_stopped')
                return
            self.audio.reset()
            self.vision.clear()
            had_session = c.session is not None
            c.stop(kw.get('reason', name), privacy=name == 'privacy')
            if getattr(self, 'camera_test', False):
                self.camera_test = False
                self.camera_test_frames = 0
                self._message('camera_test_stopped')
            self.preview_history = []
            self.connect_started_wall = None
            self.last_frame_wall = None
            self.guided_started = self.guided_paused_at = self._guided_key = None
            self._view()
            if had_session and c.last_saved_id:
                self._message('saved', id=c.last_saved_id)
        elif name == 'guided_pause':
            paused = c.set_guided_pause(kw['paused'])
            now = time.monotonic()
            if paused and self.guided_paused_at is None:
                self.guided_paused_at = now
            elif not paused and self.guided_paused_at is not None:
                # Resuming continues the same prompt cycle; paused time is not counted.
                self.guided_started += now-self.guided_paused_at
                self.guided_paused_at = None
            self._view(c.latest_packet, c.latest_pose)
        elif name == 'self_report':
            total = c.record_self_report()
            self._message('self_report', count=total, context=c.context)
            self._view(c.latest_packet, c.latest_pose)
        elif name == 'training_control':
            self.audio.reset()
            try:
                c.training_control(kw['action'], setup_confirmed=kw.get('setup_confirmed', False))
            finally:
                self.audio.reset(c.context)
            self.last_sound_count = c.engine.completed
            self._view(c.latest_packet, c.latest_pose)
        elif name == 'preview_segment':
            if c.state != 'PREVIEW' or c.context.source_kind != 'REPLAY_FILE' or self.camera.worker is None:
                raise ValueError('请先打开录像预览')
            self.camera.worker.preview_segment(1.2)
            self._message('notice', text='正在分析 1.2 秒预览片段；不计正式动作，可用于检查稳定机位和坐站基线。')
        elif name == 'prepare_sample':
            if kw.get('expected_context', c.context) != c.context:
                raise ValueError('预览已变化，请重新选择当前起点或方向')
            self._begin_preparation(kw['sample'], kw['position'])
        elif name == 'cancel_preparation':
            self._view(c.latest_packet, c.latest_pose)
        elif name == 'baseline':
            if c.state != 'PREVIEW':
                raise ValueError('基线只在预览中记录')
            from .joint_calibration import stable_preview_value
            obs = c.latest_observation
            if obs is None or c.latest_pose is None or c.latest_packet is None or (c.source['kind'] == 'LIVE_CAMERA' and time.monotonic()-c.latest_packet.received_monotonic > 3):
                raise ValueError('请重新取得当前参与者的预览画面')
            values = [stable_preview_value(self.preview_history, key, now_time=obs.time_s,
                      track_key=obs.track_key, tolerance=tolerance)
                      for key, tolerance in (('knee_flexion_deg', 10), ('hip_y', .03))]
            identity = self._preparation_binding()
            calibration = c.setup['plan'].setdefault('calibration', {})
            if calibration.get('sampling_identity') != identity:
                calibration = c.setup['plan']['calibration'] = {'sampling_identity': identity}
            calibration.update({kw['position']+'_knee': values[0], kw['position']+'_hip_y': values[1],
                                'provenance': {'source_ref': c.source['ref'], 'frame_size': list(c.latest_pose.size),
                                               'side': c.setup['plan']['side'], 'view': c.setup['view']}})
            self._message('baseline', position=kw['position'], knee=values[0], hip=values[1],
                          context=c.context, sampling_identity=self._preparation_binding(),
                          provenance={'source_ref': c.source['ref'], 'frame_size': list(c.latest_pose.size),
                                      'side': c.setup['plan']['side'], 'view': c.setup['view']})
            self.preview_history = []
            c.confirmed = False
            self._view(c.latest_packet, c.latest_pose)
        elif name == 'joint_baseline':
            if (c.latest_packet is None or (c.source['kind'] == 'LIVE_CAMERA' and
                    time.monotonic()-c.latest_packet.received_monotonic > 3)):
                raise ValueError('预览画面过期，请重新预览后记录')
            baseline = c.record_joint_baseline(self.preview_history, kw['position'])
            self.preview_history = []
            self._message('joint_baseline', baseline=baseline, context=c.context)
            self._view(c.latest_packet, c.latest_pose)
        elif name == 'history':
            sessions = store.list_sessions()
            self._message('history', sessions=[{k: v for k, v in s.items() if k not in ('metrics', 'poses')} for s in sessions])
        elif name in ('longitudinal_history', 'export_longitudinal_history'):
            from .longitudinal import build_longitudinal_history
            from .reports import export_longitudinal_history
            history = build_longitudinal_history(store.list_sessions(), kw['anchor_id'])
            if name == 'longitudinal_history':
                self._message('longitudinal_history', history=history, request_id=kw.get('request_id'))
            else:
                if kw.get('expected_fingerprint') != history['fingerprint']:
                    raise ValueError('历史记录已变化，请重新选择基准刷新后再导出')
                output = export_longitudinal_history(history, kw['directory'], kw.get('metric', 'range_deg'))
                self._message('longitudinal_exported', directory=output, request_id=kw.get('request_id'))
        elif name == 'participants':
            self._message('participants', participants=store.list_participants())
        elif name in ('automatic_proposal', 'accept_automatic_plan', 'automatic_progress', 'prepare_automatic_item'):
            from .assessment_batches import scope_key
            from .automatic_plans import (ORIGIN, generate_proposal, create_automatic_plan,
                                           validate_automatic_use, validate_metadata, program_progress)
            from .training_plans import prepare_training_plan
            scope = scope_key(kw['scope'])
            if c.session is not None or c.pending is not None or c.state in ('ONLINE', 'SAVE_FAILED', 'PREVIEW', 'CONNECTING'):
                raise ValueError('请先结束并保存当前任务，再安排下一项训练')
            sessions = store.list_sessions()
            profile = build_body_profile(sessions, **scope)
            participant = store.get_participant(scope['participant_id'])
            if name in ('automatic_proposal', 'accept_automatic_plan'):
                proposal = generate_proposal(profile, sessions, participant)
                if name == 'automatic_proposal':
                    records = [p for p in store.list_training_plans(scope) if p.get('record_origin') == ORIGIN]
                    record = records[0] if records else None
                    if record:
                        validate_metadata(record)
                    self._message('automatic_proposal', scope=scope, proposal=proposal, record=record,
                                  progress=program_progress(record, sessions) if record else None)
                    return
                if kw.get('fingerprint') != proposal['fingerprint']:
                    raise ValueError('评估或适用条件已变化，请刷新后查看新的自动安排')
                record = store.save_training_plan(create_automatic_plan(proposal, kw.get('screening')), expected_revision=0)
            else:
                record = store.get_training_plan(kw['id'])
                if (not record or record.get('record_origin') != ORIGIN or scope_key(record) != scope
                        or record['status'] != 'ACTIVE' or record['revision'] != kw.get('revision')):
                    raise ValueError('自动计划已变化，请重新打开训练中心')
                validate_metadata(record)
            progress = program_progress(record, sessions)
            if name == 'prepare_automatic_item':
                entry_key = kw['entry_key']
                validate_automatic_use(record, entry_key, profile, sessions, participant)
                plan = prepare_training_plan(record, entry_key, profile)
                plan['training_plan_confirmed'] = True
                self._message('automatic_item_prepared', scope=scope, plan=plan)
            else:
                self._message('automatic_progress', scope=scope, record=record, progress=progress)
        elif name in ('training_plans', 'save_training_plan', 'archive_training_plan', 'prepare_training_plan'):
            from .assessment_batches import scope_key
            from .training_plans import prepare_training_plan, training_plan_view
            scope = scope_key(kw['scope'])
            if name != 'training_plans' and (c.session is not None or c.pending is not None
                                             or c.state in ('ONLINE', 'SAVE_FAILED', 'PREVIEW', 'CONNECTING')):
                raise ValueError('请先结束并保存当前任务，再修改或使用训练计划')
            selected_id = None
            if name == 'save_training_plan':
                previous = store.get_training_plan(kw['plan'].get('id'))
                if kw['plan'].get('record_origin') == 'assessment_rules' or (previous or {}).get('record_origin') == 'assessment_rules':
                    raise ValueError('自动计划请在自动安排中重新生成；人工修改请另建计划')
                if scope_key(kw['plan']) != scope:
                    raise ValueError('计划不属于当前用户与来源')
                record = store.save_training_plan(kw['plan'], expected_revision=kw['expected_revision'])
                selected_id = record['id']
            elif name == 'archive_training_plan':
                record = store.set_training_plan_archived(kw['id'], scope, kw['archived'],
                                                           expected_revision=kw['expected_revision'])
                selected_id = record['id']
            profile = build_body_profile(store.list_sessions(), **scope)
            if name == 'prepare_training_plan':
                record = store.get_training_plan(kw['id'])
                if (record is None or type(kw.get('expected_revision')) is not int
                        or record['revision'] != kw['expected_revision']):
                    raise ValueError('保存的计划已更新，请刷新后重新选择')
                plan = prepare_training_plan(record, kw['entry_key'], profile)
                if record.get('record_origin') == 'assessment_rules':
                    raise ValueError('请从训练中心的自动安排入口按顺序继续')
                self._message('training_plan_prepared', scope=scope, plan=plan)
            else:
                plans = [training_plan_view(p, profile) for p in store.list_training_plans(scope, include_archived=True)]
                self._message('training_plans', scope=scope, plans=plans, selected_id=selected_id,
                              saved=name == 'save_training_plan')
        elif name in ('assessment_batch', 'create_assessment_batch', 'change_assessment_batch'):
            from .assessment_batches import scope_key, batch_view
            scope = scope_key(kw['scope'])
            if name != 'assessment_batch' and (c.session is not None or c.pending is not None
                                               or c.state in ('ONLINE', 'SAVE_FAILED', 'PREVIEW', 'CONNECTING')):
                raise ValueError('请先结束并保存当前任务，再修改评估清单')
            if name == 'create_assessment_batch':
                batch = store.create_assessment_batch(scope, kw['items'])
            elif name == 'change_assessment_batch':
                batch = store.get_assessment_batch(kw['id'])
                if batch is None or scope_key(batch) != scope:
                    raise ValueError('清单不属于当前用户与来源')
                batch = store.change_assessment_batch(kw['id'], kw['action'], expected_revision=kw['expected_revision'],
                                                       entry_key=kw.get('entry_key'), reason=kw.get('reason'))
            else:
                batch = store.current_assessment_batch(scope)
            self._message('assessment_batch', scope=scope,
                          batch=batch_view(batch, store.list_sessions()) if batch else None)
        elif name == 'save_participant':
            if c.session is not None or c.pending is not None or c.state in ('ONLINE', 'SAVE_FAILED', 'PREVIEW', 'CONNECTING'):
                raise ValueError('请先停止采集并保存当前任务，再编辑个人信息')
            profile = store.save_participant(kw['profile'], expected_revision=kw['expected_revision'])
            self._message('participant_saved', profile=profile)
        elif name in ('body_profile', 'export_body_profile'):
            profile = build_body_profile(store.list_sessions(), kw['participant_id'],
                                         kw['source_kind'], kw['usage_context'])
            if name == 'body_profile':
                self._message('body_profile', profile=profile, html=render_body_profile(profile, compact=True))
            else:
                output = export_body_profile(profile, kw['directory'])
                self._message('notice', text=f'身体信息已导出：{output}')
        elif name in ('report', 'training_review'):
            s = store.get_session(kw['id'])
            if s is None:
                raise ValueError('报告不存在')
            self._message(name, snapshot=s, html=render_report(s))
        elif name == 'save_training_feedback':
            saved = store.save_training_feedback(kw['id'], kw['feedback'], expected_revision=kw['expected_revision'])
            self._message('training_feedback_saved', snapshot=saved, html=render_report(saved))
        elif name == 'export':
            snapshot = store.get_session(kw['id'])
            if snapshot is None:
                raise ValueError('报告不存在')
            out = export_session(snapshot, kw['directory'])
            self._message('notice', text=f'报告已导出到：{out}')
        elif name == 'delete':
            store.delete_session(kw['id'])
            self._execute('history', {})
        elif name == 'events':
            self._message('events', events=store.list_events())
        elif name == 'event_transition':
            store.transition_event(kw['id'], kw['status'], kw['operator'], kw['note'])
            self._execute('events', {})
        elif name == 'retry_save':
            c.retry_save()
            self._view()
            self._message('saved', id=c.last_saved_id)
        elif name == 'backup_pending':
            output = c.backup_pending(kw['directory'])
            self._message('notice', text=f'待保存结果已备份到：{output}')
        elif name == 'discard_pending':
            c.discard_pending(kw['reason'])
            self._view()
            self._message('notice', text='已按明确操作丢弃待保存结果，并记录了丢弃原因。')
        elif name == 'task':
            if c.state != 'ONLINE' or c.context.scene_id != 'activity':
                raise ValueError('请先开始活动场景')
            c.engine.choose_task(kw['task'], c.latest_observation.time_s if c.latest_observation else 0)
            c.checkpoint_activity()
            self._view(c.latest_packet, c.latest_pose)
        elif name == 'profile':
            profiles = store._call(lambda db: [__import__('json').loads(r[0]) for r in db.execute('SELECT payload FROM scene_profiles')])
            self._message('profiles', profiles=profiles)
        elif name == 'shutdown':
            self.audio.reset()
            self.vision.clear()
            c.stop('application_exit')
            if c.pending is not None:
                raise RuntimeError('存在未保存结果，不能关闭')
            self.stop_event.set()
        else:
            raise ValueError('未知操作')

    def _remember_camera(self, device):
        try:
            self.store.save_camera_preference(device)
        except Exception:
            # Preferences are optional; failure must not interrupt a live run or
            # masquerade as a failed clinical report save.
            self._message('notice', text='本次摄像头可继续使用，但未能记住选择；下次启动可能需要重选。')

    def _remember_camera_pair(self, devices):
        try:
            self.store.save_camera_pair_preference(devices)
        except Exception:
            self._message('notice', text='本次双摄可继续使用，但未能记住正侧面对应；下次需要重新选择。')

    def _receive_packet(self, packet, worker):
        c = self.controller
        if packet.context != c.context:
            worker.acknowledge(packet.seq)
            return
        if c.dual_config:
            from .dual_camera import validate_pair
            try:
                validate_pair(packet, c.dual_config['primary_view'], now=time.monotonic())
            except ValueError:
                return  # Do not refresh the watchdog with unpaired or stale input.
            gate = getattr(self, 'dual_receive_gate', None)
            if gate is None:
                self.dual_receive_gate = gate = PacketGate()
                gate.reset(c.context)
            if not gate.admit(packet):
                return
        if getattr(self, 'camera_test', False):
            worker.acknowledge(packet.seq)
            if (c.state not in ('CONNECTING', 'PREVIEW') or
                    not 0 <= time.monotonic()-packet.received_monotonic <= 3 or not c.gate.admit(packet)):
                return
            self.camera_test_frames += 1
            c.latest_packet = packet
            c.latest_pose = c.latest_observation = None
            c.confirmed = False
        self.last_frame_wall = time.monotonic()
        self.connect_started_wall = None
        if c.state == 'CONNECTING':
            c.state = 'PREVIEW'
        if getattr(self, 'camera_test', False):
            # Raw preview deliberately does not submit to a model or an assessment engine.
            self._view(packet)
        else:
            backend = exercise_spec(c.setup['plan']['exercise_id'])['backend'] if c.setup['scene_id'] == 'rehab' else 'yolo'
            self.vision.submit(packet, backend=backend, side=c.setup['plan']['side'])
            if c.latest_pose is None:
                self._view(packet)

    def _run(self):
        self.store = None
        self.camera = CameraManager()
        self.vision = None
        self.audio = AudioGate()
        try:
            settings = load_settings()
            self.capture_settings = settings['capture']
            self.store = Storage(self.data_dir/'home_rehab.sqlite3')
            recovered = self.store.recover_unfinished()
            self.controller = SceneController(self.store, self.camera, vision_config=settings['vision'])
            self.vision = VisionWorker(ROOT/settings['vision']['model_path'],
                                       imgsz=settings['vision']['imgsz'], device=settings['vision'].get('device', 'cpu'))
            try:
                preferred_camera = self.store.get_camera_preference()
                preference_error = False
            except Exception:
                preferred_camera, preference_error = None, True
            try:
                preferred_pair = self.store.get_camera_pair_preference()
            except Exception:
                preferred_pair = None
            self._message('ready', preferred_camera=preferred_camera, preferred_camera_pair=preferred_pair,
                          camera_preference_error=preference_error)
            if recovered:
                self._message('notice', text=f'发现 {recovered} 条上次非正常结束的任务，已标记中断；未补造缺失结果。')
            self._view()
            self.ready.set()
            while not self.stop_event.is_set():
                try:
                    name, kw = self.commands.get_nowait()
                except queue.Empty:
                    name = None
                if name is not None:
                    dispatched = False
                    try:
                        if name in ('silver', 'family_demo'):
                            self._dispatch_optional(name, kw)
                            dispatched = True
                        else:
                            self._execute(name, kw)
                    except Exception as exc:
                        self._message('error', text=str(exc), command=name, request_id=kw.get('request_id'))
                        if name not in ('silver', 'family_demo'):
                            self._view(error=str(exc), operation_error=True)
                    finally:
                        if not dispatched:
                            self._message('command_done', command=name)
                c = self.controller
                self._tick_preparation()
                prompt = self._guided_prompt()
                if prompt is not None and not prompt.get('paused') and prompt['key'] != self._guided_key:
                    # Refresh the prompt even between frames; the record only ever
                    # counts prompts issued, never an assumed movement.
                    self._guided_key = prompt['key']
                    c.note_guided_prompt(prompt['cycle'])
                    self._view(c.latest_packet, c.latest_pose)
                worker = self.camera.worker
                if worker is not None:
                    statuses = worker.read_status()
                    for status in statuses:
                        if status['status'] == 'OPENED':
                            c.input_diagnostics = {k: v for k, v in status.items() if k != 'status'}
                    error = next((s for s in statuses if s['status'] == 'ERROR'), None)
                    ended = any(s['status'] == 'EOF' for s in statuses)
                    if error or ended:
                        had_session = c.session is not None
                        save_ok = True
                        if error:
                            self._record_dual_failure('input_error', error.get('view'))
                        try:
                            c.stop('input_error' if error else 'replay_end')
                        except Exception as exc:
                            save_ok = False
                            self._message('error', text=str(exc))
                        self.audio.reset()
                        self.vision.clear()
                        self.connect_started_wall = None
                        self.last_frame_wall = None
                        self._view(error=error['message'] if error else None)
                        if save_ok:
                            if had_session and c.last_saved_id:
                                self._message('saved', id=c.last_saved_id)
                            self._message('notice', text=error['message'] if error else
                                          '回放结束，已保存本次任务。' if had_session else '回放已结束；预览没有生成任务报告。')
                        continue
                    packet = worker.read_latest()
                    if packet is not None:
                        self._receive_packet(packet, worker)
                    timeout_reason = (input_timeout_reason(c.state, time.monotonic(), self.connect_started_wall,
                                                           self.last_frame_wall, self.capture_settings)
                                      if c.context and c.context.source_kind == 'LIVE_CAMERA' else None)
                    if timeout_reason:
                        self._record_dual_failure(timeout_reason)
                        try:
                            c.stop(timeout_reason)
                            c.state = 'OFFLINE'
                        except Exception as exc:
                            self._message('error', text=str(exc))
                        self.audio.reset()
                        self.vision.clear()
                        self.connect_started_wall = None
                        self.last_frame_wall = None
                        connect_timeout = self.capture_settings.get('connect_timeout_s', 15)
                        stale_timeout = self.capture_settings.get('stale_after_s', 3)
                        message = (f'摄像头启动超过 {connect_timeout:g} 秒仍未取得画面；请检查占用后重新预览'
                                   if timeout_reason == 'connect_timeout' else
                                   f'超过 {stale_timeout:g} 秒未取得新画面，任务已中断；请重新预览')
                        self._view(error=message)
                try:
                    packet, pose, error = self.vision.outputs.get_nowait()
                except queue.Empty:
                    time.sleep(.01)
                    continue
                if self.camera.worker is not None:
                    self.camera.worker.acknowledge(packet.seq)
                if packet.context != c.context or getattr(self, 'camera_test', False):
                    continue
                if error:
                    self._inference_failed(packet, error)
                    continue
                try:
                    if not c.consume(packet, pose):
                        continue
                    if c.state == 'ONLINE' and c.setup['scene_id'] == 'activity':
                        signature = (c.context.run_id, tuple((t['id'], t['status']) for t in c.engine.tasks))
                        if signature != getattr(self, '_activity_checkpoint_signature', None):
                            c.checkpoint_activity()
                            self._activity_checkpoint_signature = signature
                    self._collect_preview_observation(packet)
                    if c.state == 'ONLINE' and c.setup['plan']['sound_enabled']:
                        summary = c.summary()
                        events = getattr(c.engine, 'events', [])
                        new_event = events and events[-1]['id'] != self.last_sound_event
                        issues = summary.get('current_issues', []) if c.setup['plan']['submode'] == 'training' else []
                        new_count = summary.get('completed', 0) > self.last_sound_count
                        due = summary.get('reminder_due', False)
                        if new_event or issues or new_count or due:
                            priority = 0 if new_event else 2 if issues else 3
                            if self.audio.play(c.context, packet.time_s, ROOT/'assets/audio'/('alert.wav' if new_event else 'cue.wav'), priority):
                                if new_event:
                                    self.last_sound_event = events[-1]['id']
                                self.last_sound_count = summary.get('completed', 0)
                                if issues and getattr(c.engine, 'current', None):
                                    for issue in c.engine.current['issues']:
                                        if issue['rule_id'] == issues[0]['rule_id']:
                                            issue['feedback_emitted_at'] = utc_now()
                    self._view(packet if c.context else None, pose if c.context else None, error=c.last_error or None)
                except Exception as exc:
                    try:
                        c.stop('analysis_error')
                    except Exception as save_exc:
                        self._message('error', text=str(save_exc))
                    self.audio.reset()
                    self.vision.clear()
                    self._view(error=str(exc))
        except Exception as exc:
            self._message('fatal', text=str(exc))
            self.ready.set()
        finally:
            self.audio.reset()
            try:
                self.camera.stop()
            except Exception:
                pass
            if self.vision:
                self.vision.close()
            self._close_optional()
            if self.store:
                self.store.close()
            self._message('shutdown_done')
