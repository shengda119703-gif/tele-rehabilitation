"""Synchronous local stdin/stdout client; all Agent behavior stays in TypeScript."""

import json
import os
import queue
import threading
import subprocess
from datetime import datetime
from pathlib import Path


ROUTE_ROOT = Path(__file__).resolve().parents[2] / "ankang" / "route1-health-agent"


class AgentBridge:
    def __init__(self, node: str | None = None, timeout: float = 60):
        node = node or os.environ.get("ANKANG_NODE", "node")
        self.timeout = timeout
        if not (ROUTE_ROOT / ".bridge-build" / "runtime" / "index.js").is_file():
            raise RuntimeError("Build the bridge first: npm run build:bridge (in route1-health-agent)")
        self._process = subprocess.Popen(
            [node, str(ROUTE_ROOT / "scripts" / "agent-bridge.cjs")],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        self._lines = queue.Queue()
        self._reader = threading.Thread(target=self._read_stdout, daemon=True, name="ankang-stdout")
        self._reader.start()

    def _read_stdout(self):
        try:
            for line in self._process.stdout:
                self._lines.put(line)
        finally:
            self._lines.put("")

    def terminate(self):
        """Interrupt a blocked request during application shutdown; no protocol change."""
        if self._process.poll() is None:
            self._process.kill()

    def _request(self, operation: str, **fields) -> dict:
        self._process.stdin.write(json.dumps({"operation": operation, **fields}, ensure_ascii=False) + "\n")
        self._process.stdin.flush()
        try:
            line = self._lines.get(timeout=self.timeout)
        except queue.Empty:
            self.terminate()
            raise TimeoutError("Ankang bridge response timed out; session ended") from None
        if not line:
            raise RuntimeError("Node bridge exited without a response; see stderr")
        response = json.loads(line)
        if not response["ok"]:
            raise RuntimeError(response["error"])
        return response["result"]

    def open_session(self, session_id: str, profile: dict) -> dict:
        return self._request("open", sessionId=session_id, profile=profile, now=datetime.now().astimezone().isoformat())

    def process_turn(self, session_id: str, text: str) -> dict:
        return self._request("process", sessionId=session_id, text=text, now=datetime.now().astimezone().isoformat())

    def close_session(self, session_id: str) -> dict:
        return self._request("close", sessionId=session_id)

    def __enter__(self):
        return self

    def close(self):
        if self._process.stdin and not self._process.stdin.closed:
            try:
                self._process.stdin.close()
            except OSError:
                pass
        try:
            self._process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.terminate()
            self._process.wait(timeout=2)
        self._reader.join(timeout=2)
        self._process.stdout.close()

    def __exit__(self, *_):
        self.close()
