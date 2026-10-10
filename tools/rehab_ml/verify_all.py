"""Bounded isolated backend regressions; no UI, APK or patient DB operations."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.rehab_ml.common import file_hash, paths, write_json


def main():
    root = paths()['run'] / ('verification-'+uuid4().hex[:8])
    root.mkdir()
    summary = dict(commands=[], product_environment=sys.executable, clinical_accuracy=None)
    cases = [
        ('new_backend', ['-m', 'unittest', 'discover', '-s', 'tests/rehab_backend', '-p', 'test_*.py', '-v']),
        ('legacy_rehab', ['-m', 'unittest', 'discover', '-s', 'rehab_codex_single_camera_v2_1/tests', '-p', 'test_app_rehab.py', '-v']),
        ('legacy_mobile', ['-m', 'pytest', 'mobile_rehab/tests/test_mobile.py', '-q', '-p', 'no:cacheprovider',
                           '--basetemp', str(root / 'pytest-temporary')]),
        ('scope', ['tools/rehab_ml/cli.py', 'verify-scope', '--baseline', 'reports/rehab_backend/protected_files.json']),
    ]
    for name, arguments in cases:
        started = time.perf_counter()
        try:
            environment = dict(os.environ)
            environment['PYTHONPATH'] = str(ROOT / 'rehab_codex_single_camera_v2_1')+os.pathsep+str(ROOT)
            completed = subprocess.run([sys.executable, '-X', 'utf8', *arguments], cwd=ROOT, env=environment,
                capture_output=True, text=True, encoding='utf-8', timeout=150)
            log = root / (name+'.txt')
            log.write_text(completed.stdout+completed.stderr, encoding='utf-8')
            summary['commands'].append(dict(name=name, arguments=arguments, exit_code=completed.returncode,
                elapsed_s=time.perf_counter()-started, log=str(log), log_sha256=file_hash(log),
                tail=(completed.stdout+completed.stderr)[-400:]))
        except subprocess.TimeoutExpired:
            summary['commands'].append(dict(name=name, arguments=arguments, exit_code=None, status='timeout',
                                           elapsed_s=time.perf_counter()-started))
        write_json(ROOT / 'reports/rehab_backend/regression.json', summary)
    summary['passed'] = all(c.get('exit_code') == 0 for c in summary['commands'])
    write_json(ROOT / 'reports/rehab_backend/regression.json', summary)
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
