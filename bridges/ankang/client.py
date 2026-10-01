"""Synchronous local stdin/stdout client; all Agent behavior stays in TypeScript."""

import json
import subprocess
from datetime import datetime
from pathlib import Path


ROUTE_ROOT = Path(__file__).resolve().parents[2] / "ankang" / "route1-health-agent"


class AgentBridge:
    def __init__(self, node: str = "node"):
        if not (ROUTE_ROOT / ".bridge-build" / "runtime" / "index.js").is_file():
            raise RuntimeError("Build the bridge first: npm run build:bridge (in route1-health-agent)")
        self._process = subprocess.Popen(
            [node, str(ROUTE_ROOT / "scripts" / "agent-bridge.cjs")],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )

    def _request(self, operation: str, **fields) -> dict:
        self._process.stdin.write(json.dumps({"operation": operation, **fields}, ensure_ascii=False) + "\n")
        self._process.stdin.flush()
        line = self._process.stdout.readline()
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

    def __exit__(self, *_):
        self._process.stdin.close()
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait()
        finally:
            self._process.stdout.close()
