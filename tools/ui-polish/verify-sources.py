"""Check vendored skill integrity, tolerating Git's configured LF normalization."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[2]
manifest = json.loads((root / 'tools/ui-polish/sources.lock.json').read_text(encoding='utf-8'))
failures = []
for relative, expected in manifest['files'].items():
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file():
        failures.append(f'Missing or invalid path: {relative}')
        continue
    content = candidate.read_bytes()
    if b'\0' not in content:
        content = content.replace(b'\r\n', b'\n')
    if hashlib.sha256(content).hexdigest() != expected:
        failures.append(f'Hash mismatch: {relative}')
if failures:
    raise SystemExit('\n'.join(failures))
print(f"PASS: {len(manifest['files'])} vendored skill files match the source manifest")
