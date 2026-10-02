"""One serialized worker for the existing TypeScript bridge, never an LLM client."""
import queue
import json
import sys
import threading
from pathlib import Path

from ..rehab_read_tools import RehabReadTools, TOOLS


class ProductBackend:
    def __init__(self, data_dir, bridge_factory=None):
        self.data_dir = Path(data_dir)
        self.jobs, self.results = queue.Queue(), queue.Queue()
        self.stop_event = threading.Event()
        self.bridge = None
        self.factory = bridge_factory
        self.thread = threading.Thread(target=self._run, daemon=True, name='ankang-product')
        self.thread.start()

    def submit(self, operation, owner='', payload=None, scope=None, token=None):
        self.jobs.put((operation, owner, payload or {}, dict(scope or {}), token))

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
                try:
                    payload = dict(payload)
                    if operation == 'ui.file.write':
                        content = payload.get('text')
                        data = content.encode('utf-8') if isinstance(content, str) else bytes(payload['bytes'])
                        Path(payload['path']).write_bytes(data)
                        self.results.put((operation, owner, token, {'fileExport': True}, None))
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
                        self.bridge = self.factory() if self.factory else AgentBridge(data_dir=self.data_dir/'product')
                    tools = RehabReadTools(self.data_dir/'home_rehab.sqlite3', scope) if scope else None
                    result = self.bridge.product(operation, owner, payload, tool_handler=tools)
                    snapshot = result.get('snapshot', result) if isinstance(result, dict) else None
                    if isinstance(snapshot, dict) and 'state' in snapshot and tools:
                        snapshot['rehabilitation'] = {name: tools(name, {}) for name in TOOLS}
                        snapshot['rehabilitation_ui'] = tools.desktop_snapshot()
                    if export_path:
                        data = bytes(result['bytes']) if operation == 'archive.read' else json.dumps(result, ensure_ascii=False, indent=2).encode('utf-8')
                        Path(export_path).write_bytes(data)
                        result = {'fileExport': True}
                    self.results.put((operation, owner, token, result, None))
                except Exception as error:
                    # Preserve in-flight domain sessions on validation failures. Failed child resets on next job.
                    if self.bridge and self.bridge._process.poll() is not None:
                        self.bridge.close()
                        self.bridge = None
                    self.results.put((operation, owner, token, None, str(error)))
        finally:
            if self.bridge:
                self.bridge.close()

    def close(self):
        self.stop_event.set()
        self.jobs.put(None)
        if self.bridge:
            self.bridge.terminate()
        self.thread.join(timeout=2)
