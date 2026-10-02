"""One serialized worker for the existing TypeScript bridge, never an LLM client."""
import queue
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
                    if self.bridge is None:
                        self.bridge = self.factory() if self.factory else AgentBridge(data_dir=self.data_dir/'product')
                    tools = RehabReadTools(self.data_dir/'home_rehab.sqlite3', scope) if scope else None
                    result = self.bridge.product(operation, owner, payload, tool_handler=tools)
                    snapshot = result.get('snapshot', result) if isinstance(result, dict) else None
                    if isinstance(snapshot, dict) and 'state' in snapshot and tools:
                        snapshot['rehabilitation'] = {name: tools(name, {}) for name in TOOLS}
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
