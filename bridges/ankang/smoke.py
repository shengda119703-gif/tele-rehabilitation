"""Run from any directory: python path/to/bridges/ankang/smoke.py [--node PATH]."""

import argparse
import subprocess
import sys

from client import AgentBridge, ROUTE_ROOT


def main():
    parser = argparse.ArgumentParser(description="Python -> original Ankang TypeScript Runtime smoke")
    parser.add_argument("--node", default="node", help="Node 22+ executable")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    subprocess.run([args.node, str(ROUTE_ROOT / "scripts" / "build-agent-bridge.cjs")], check=True)
    profile = {
        "name": "Bridge smoke (synthetic)", "age": 72, "conditions": [], "medications": [],
        "familyContact": "", "familyPhone": "", "mobility": "unknown", "usesCane": False,
        "nightVision": "unknown", "cognition": "unknown", "familySharing": "denied",
    }
    with AgentBridge(args.node) as bridge:
        opened = bridge.open_session("python-smoke", profile)
        assert opened["revision"] == 0
        for revision, text in enumerate(["我今天头晕", "我今天量了血压150/95"], start=1):
            print(f"Python -> {text}", flush=True)
            result = bridge.process_turn("python-smoke", text)
            assert result["reply"]["text"]
            assert result["revision"] == revision
            assert len(result["snapshot"]["chat"]) == revision * 2
            assert result["snapshot"]["events"]
            print(f"Agent -> {result['reply']['text']}")
            print(f"revision={result['revision']}, events={len(result['snapshot']['events'])}")
        assert bridge.close_session("python-smoke")["closed"]
    print("Received fields: " + ", ".join(result))
    print("Python successfully received Agent result")


if __name__ == "__main__":
    main()
