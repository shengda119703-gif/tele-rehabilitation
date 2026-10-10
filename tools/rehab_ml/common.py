from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def paths():
    base = ROOT / '.runtime' / 'rehab_ml'
    result = {key: Path(os.environ.get('REHAB_' + key.upper() + '_ROOT', base / key)).resolve()
              for key in ('data', 'run', 'model')}
    for path in result.values():
        path.mkdir(parents=True, exist_ok=True)
    return result


def file_hash(path, algorithm='sha256'):
    digest = hashlib.new(algorithm)
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + '.', suffix='.part', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return str(path)


def read_json(path):
    with Path(path).open(encoding='utf-8') as stream:
        return json.load(stream)


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], encoding='utf-8').strip()


def load_registry(path=None):
    import yaml
    with Path(path or ROOT / 'configs/rehab_ml/datasets.yaml').open(encoding='utf-8') as stream:
        return yaml.safe_load(stream)['datasets']
