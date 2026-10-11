"""Bounded audit tests plus explicitly chosen analysis-only original caches."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.rehab_ml.common import file_hash, paths, read_json, write_json
from tools.rehab_ml.sampling_audit import SOURCES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--result', action='append', type=Path, required=True)
    args = parser.parse_args()
    root = paths()['run']/('sampling-verification-'+uuid4().hex[:8])
    root.mkdir()
    sources = (*SOURCES, 'tests/rehab_backend/test_sampling_audit.py', 'tools/rehab_ml/verify_sampling_audit.py')
    hashes = {p: file_hash(ROOT/p) for p in sources}
    summary = dict(run_id=root.name, commands=[], implementation_sha256=hashes,
                   human_data_used_only_for_sampling_analysis=True,
                   training_performed=False, clinical_accuracy=None,
                   frontend_modified=False, apk_modified=False)
    cases = [
        ('unit', ['-m', 'unittest', 'discover', '-s', 'tests/rehab_backend', '-p', 'test_sampling_audit.py', '-v']),
        ('authorized_cache_profiles', ['-m', 'tools.rehab_ml.sampling_audit', '--publish',
            *[v for path in args.result for v in ('--result', str(path.resolve()))]]),
    ]
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
                       PYTHONPATH=str(ROOT/'rehab_codex_single_camera_v2_1')+os.pathsep+str(ROOT))
    for name, arguments in cases:
        started = time.perf_counter()
        try:
            done = subprocess.run([sys.executable, '-X', 'utf8', '-B', *arguments], cwd=ROOT, env=environment,
                                  capture_output=True, text=True, encoding='utf-8', timeout=90)
            output = done.stdout+done.stderr
            log = root/(name+'.txt')
            log.write_text(output, encoding='utf-8')
            match = re.search(r'Ran (\d+) tests', output)
            summary['commands'].append(dict(name=name, arguments=arguments, exit_code=done.returncode,
                elapsed_s=time.perf_counter()-started, log=str(log), log_sha256=file_hash(log),
                tests=int(match.group(1)) if match else None, tail=output[-1800:]))
        except subprocess.TimeoutExpired as error:
            log = root/(name+'-timeout.txt')
            output = ''.join(v.decode('utf-8', errors='replace') if isinstance(v, bytes) else v or ''
                             for v in (error.stdout, error.stderr))
            log.write_text(output, encoding='utf-8')
            summary['commands'].append(dict(name=name, exit_code=None, status='timeout', timeout_s=90,
                elapsed_s=time.perf_counter()-started, log=str(log), log_sha256=file_hash(log)))
        if summary['commands'][-1].get('exit_code') != 0:
            break
    summary['implementation_unchanged'] = hashes=={p:file_hash(ROOT/p) for p in sources}
    summary['passed'] = (len(summary['commands'])==2 and summary['implementation_unchanged']
                         and all(v.get('exit_code')==0 for v in summary['commands'])
                         and summary['commands'][0].get('tests')==17)
    if summary['passed']:
        audit = ROOT/'reports/rehab_backend/sampling_sensitivity.json'
        value = read_json(audit)
        summary['audit_run_id'] = value['run_id']
        summary['audit_summary_sha256'] = file_hash(audit)
        summary['verified_private_cache_inputs'] = len(value['results'])
        summary['profile_runs'] = sum(len(v['profiles']) for v in value['results'])
    write_json(ROOT/'reports/rehab_backend/sampling_verification.json', summary)
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
