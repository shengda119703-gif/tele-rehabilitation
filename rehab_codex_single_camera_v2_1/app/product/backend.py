"""One serialized worker for the existing TypeScript bridge, never an LLM client."""
import queue
import json
import sys
import threading
from pathlib import Path

from ..rehab_read_tools import RehabReadTools, TOOLS


class _Reply:
    def __init__(self):
        self.queue = queue.Queue(maxsize=1)
        self.cancelled = False


class ProductBackend:
    def __init__(self, data_dir, bridge_factory=None):
        self.data_dir = Path(data_dir)
        self.jobs, self.results = queue.Queue(), queue.Queue()
        self.stop_event = threading.Event()
        self.bridge = None
        self.factory = bridge_factory
        from .daily_store import DailyStore
        self.daily = DailyStore(self.data_dir)
        from .native_voice import NativeVoiceHost
        self.voice = NativeVoiceHost()
        self.thread = threading.Thread(target=self._run, daemon=True, name='ankang-product')
        self.thread.start()

    def submit(self, operation, owner='', payload=None, scope=None, token=None):
        if operation in ('voice.input','ui.voice.transcribe'):self.voice.prepare()
        self.jobs.put((operation, owner, payload or {}, dict(scope or {}), token))

    def call(self, operation, owner, payload=None, scope=None, timeout=165):
        """Phone requests share the desktop's single writer, with private replies."""
        if self.stop_event.is_set():
            raise RuntimeError('电脑服务已停止。')
        reply = _Reply()
        self.submit(operation, owner, payload, scope, reply)
        try:
            _, _, _, result, error = reply.queue.get(timeout=timeout)
        except queue.Empty:
            reply.cancelled = True
            raise TimeoutError('请求超时，请刷新核对是否已保存后再操作。') from None
        if error:
            raise RuntimeError(error)
        return result

    def _deliver(self, value):
        reply = value[2]
        if isinstance(reply, _Reply):
            if not reply.cancelled:
                reply.queue.put_nowait(value)
        else:
            self.results.put(value)

    def submit_capture(self, owner, batch, *, visibility='private', scope=None, token=None):
        from .capture import archive_payload
        self.submit('media.import', owner, archive_payload(batch, visibility=visibility), scope, token)

    def _run(self):
        try:
            root = str(Path(__file__).resolve().parents[3])
            if root not in sys.path:
                sys.path.insert(0, root)
            from bridges.ankang.client import AgentBridge
            while not self.stop_event.is_set():
                job = self.jobs.get()
                if job is None or self.stop_event.is_set():
                    break
                operation, owner, payload, scope, token = job
                if isinstance(token, _Reply) and token.cancelled:
                    continue
                try:
                    payload = dict(payload)
                    if operation == 'ui.voice.transcribe':
                        # Input-only operation: no Agent turn, health event or persistence.
                        result = self.voice.handle('voice.recognize', {})
                        self._deliver((operation, owner, token, result, None))
                        continue
                    if operation == 'ui.file.write':
                        content = payload.get('text')
                        data = content.encode('utf-8') if isinstance(content, str) else bytes(payload['bytes'])
                        Path(payload['path']).write_bytes(data)
                        self._deliver((operation, owner, token, {'fileExport': True}, None))
                        continue
                    local_file = payload.pop('_local_file', None)
                    export_path = payload.pop('_local_export_path', None)
                    if local_file:
                        limit = 2*1024*1024 if operation == 'device.import' else 10*1024*1024 if operation == 'image.parse' else 20*1024*1024
                        with Path(local_file).open('rb') as stream:
                            data = stream.read(limit+1)
                        if len(data) > limit:
                            raise ValueError(f'请选择不超过 {limit//(1024*1024)} MB 的文件。')
                        if operation == 'device.import':
                            payload = json.loads(data)
                            if not isinstance(payload, dict) or payload.get('ownerId') != owner:
                                raise ValueError('设备文件用户须与当前用户一致。')
                        else:
                            payload['bytes'] = list(data)
                    if self.bridge is None:
                        self.bridge = self.factory() if self.factory else AgentBridge(data_dir=self.data_dir/'product',voice_host=self.voice,timeout=150)
                    tools = RehabReadTools(self.data_dir/'home_rehab.sqlite3', scope) if scope else None
                    if operation.startswith('daily.'):
                        own = self.bridge.product('snapshot', owner, {}, tool_handler=tools)
                        if operation in ('daily.dose', 'daily.medSchedule'):
                            medicines = own['profile']['profile'].get('medicationRecords', [])
                            medicine = next((m for m in medicines if m['id'] == payload['medId']), None)
                            if not medicine or operation == 'daily.medSchedule' and medicine['status'] != 'active':
                                raise ValueError('请选择当前在用药物；停用药物的过去记录仍可更正。')
                            payload = dict(payload, medName=medicine['name'], dose=medicine.get('dose', ''))
                        if operation == 'daily.schedule' and payload.get('planId'):
                            plans = tools.desktop_snapshot()['rehab.get_training_plan']['records'] if tools else []
                            if not any(p['id'] == payload['planId'] and p['revision'] == payload['revision'] for p in plans):
                                raise ValueError('计划已变化，请刷新后重新安排。')
                        result = self.daily.apply(owner, operation, payload, scope)
                        self._deliver((operation, owner, token, result, None))
                        continue
                    result = self.bridge.product(operation, owner, payload, tool_handler=tools)
                    if operation == 'lifecycle.clear':
                        self.daily.clear(owner)
                    if operation == 'lifecycle.export' and isinstance(result, dict):
                        result['dailyProduct'] = self.daily.snapshot(owner, scope)
                    snapshot = result.get('snapshot', result) if isinstance(result, dict) else None
                    if isinstance(snapshot, dict) and 'state' in snapshot and tools:
                        snapshot['rehabilitation'] = {name: tools(name, {}) for name in TOOLS}
                        snapshot['rehabilitation_ui'] = tools.desktop_snapshot()
                        phone_scope = dict(participant_id=owner, source_kind='REPLAY_FILE', usage_context='SELF_USE')
                        snapshot['phoneRehabilitation'] = RehabReadTools(self.data_dir/'home_rehab.sqlite3', phone_scope).desktop_snapshot()
                        snapshot['dailyProduct'] = self.daily.snapshot(owner, scope)
                        members = []
                        for member, categories in self.daily.allowed_members(owner):
                            profiles = self.bridge.product('profile.list', '', {})
                            profile = next((p for p in profiles if p['ownerId'] == member), None)
                            if not profile:
                                continue
                            view = {'ownerId': member, 'name': profile['profile']['name'], 'categories': categories}
                            # Only explicitly shared summaries leave this worker. Never return another owner's raw snapshot.
                            if categories:
                                shared = self.bridge.product('snapshot', member, {})
                                if 'health' in categories:
                                    events = [e for e in shared['state']['events'] if (e.get('observation') or e.get('measurement') or e.get('labResult') or {}).get('visibility') == 'family_ok']
                                    view['health'] = [dict(timestamp=e['timestamp'], text=e['observation']['text'] if e['type'] == 'observation' else str((e.get('measurement') or e.get('labResult')).get('metric') or (e.get('labResult') or {}).get('name')) + ': ' + str((e.get('measurement') or e.get('labResult'))['value']) + ' ' + str((e.get('measurement') or e.get('labResult'))['unit'])) for e in sorted(events, key=lambda e: e['timestamp'], reverse=True)[:3]]
                                if 'medication' in categories:
                                    view['doses'] = list(self.daily.snapshot(member, {})['doses'].values())[-30:]
                                if 'rehab' in categories:
                                    member_scope = dict(scope, participant_id=member)
                                    read = RehabReadTools(self.data_dir/'home_rehab.sqlite3', member_scope)
                                    records = read.desktop_snapshot()['rehab.get_training_history']['records'][:3]
                                    view['rehab'] = [dict(timestamp=r.get('end_utc', ''), text=r.get('exercise_label', '') + ' · ' + ('目标已完成' if r.get('summary', {}).get('plan_completed') is True else '已保存，目标未核实完成')) for r in records]
                            members.append(view)
                        snapshot['familyMembers'] = members
                    if export_path:
                        data = bytes(result['bytes']) if operation == 'archive.read' else json.dumps(result, ensure_ascii=False, indent=2).encode('utf-8')
                        Path(export_path).write_bytes(data)
                        result = {'fileExport': True}
                    self._deliver((operation, owner, token, result, None))
                except Exception as error:
                    # Preserve in-flight domain sessions on validation failures. Failed child resets on next job.
                    if self.bridge and self.bridge._process.poll() is not None:
                        self.bridge.close()
                        self.bridge = None
                    self._deliver((operation, owner, token, None, str(error)))
        finally:
            if self.bridge:
                self.bridge.close()

    def close(self):
        self.voice.close()
        self.stop_event.set()
        self.jobs.put(None)
        if self.bridge:
            self.bridge.terminate()
        self.thread.join(timeout=2)
