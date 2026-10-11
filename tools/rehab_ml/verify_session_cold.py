"""Eight finalization checks and three predeclared original-YOLO cold runs."""
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
from tools.rehab_ml.common import file_hash, paths, write_json


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    run = paths()['run']/('session-cold-verification-'+uuid4().hex[:8])
    run.mkdir()
    sources = ('tools/rehab_ml/session_cold_audit.py', 'tools/rehab_ml/verify_session_cold.py',
               'tools/rehab_ml/cli.py', 'tests/rehab_backend/test_async_finish.py',
               'mobile_rehab/rehab_v2/api.py', 'mobile_rehab/rehab_v2/service.py')
    hashes = {path: file_hash(ROOT/path) for path in sources}
    result = dict(run_id=run.name, commands=[], attempts=[], source_sha256=hashes,
                  repetitions_declared_before_running=3, clinical_accuracy=None)
    write_json(run/'predeclared.json', result)
    cases = [('unit', ['-m', 'unittest', 'discover', '-s', 'tests/rehab_backend', '-p', 'test_async_finish.py', '-v'])]
    cases.extend(('native_'+str(index+1), ['tools/rehab_ml/cli.py', 'benchmark-session-cold']) for index in range(3))
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
        PYTHONPATH=str(ROOT/'rehab_codex_single_camera_v2_1')+os.pathsep+str(ROOT))
    for name, arguments in cases:
        started = time.perf_counter()
        try:
            completed = subprocess.run([sys.executable, '-X', 'utf8', '-B', *arguments],
                cwd=ROOT, env=environment, capture_output=True, text=True, encoding='utf-8', timeout=90)
            output = completed.stdout+completed.stderr
            log = run/(name+'.txt')
            log.write_text(output, encoding='utf-8')
            match = re.search(r'Ran (\d+) tests', output)
            record = dict(name=name, arguments=arguments, exit_code=completed.returncode,
                          elapsed_s=time.perf_counter()-started, log=str(log), log_sha256=file_hash(log),
                          tests=int(match.group(1)) if match else None)
            if name.startswith('native_'):
                payload = json.loads(completed.stdout)['result']
                result['attempts'].append(dict(run_id=payload['run_id'], passed=payload['passed'],
                    checks=payload.get('reconciliation', {}).get('checks'), control_budget=payload['control_budget'],
                    finish_to_commit_observed_ms=payload.get('finish_to_commit_observed_ms'),
                    status_counts=payload.get('reconciliation', {}).get('status_counts'),
                    raw_details=payload['raw_details'], raw_summary=payload['raw_summary']))
        except subprocess.TimeoutExpired as error:
            output = ''.join(value.decode('utf-8', errors='replace') if isinstance(value, bytes) else value or ''
                             for value in (error.stdout, error.stderr))
            log = run/(name+'-timeout.txt')
            log.write_text(output, encoding='utf-8')
            record = dict(name=name, arguments=arguments, exit_code=None, status='timeout',
                          log=str(log), log_sha256=file_hash(log), elapsed_s=time.perf_counter()-started)
        except Exception as error:
            record = dict(name=name, arguments=arguments, exit_code=None, status='audit_error',
                          error_type=type(error).__name__, error=str(error), elapsed_s=time.perf_counter()-started)
        result['commands'].append(record)
        if record.get('exit_code') != 0:
            break
    result['source_unchanged'] = hashes == {path: file_hash(ROOT/path) for path in sources}
    result['passed'] = (len(result['commands']) == 4 and len(result['attempts']) == 3 and
                        result['commands'][0].get('tests') == 8 and result['source_unchanged'] and
                        all(row.get('exit_code') == 0 for row in result['commands']) and
                        all(row['passed'] for row in result['attempts']))
    write_json(run/'summary.json', result)
    write_json(ROOT/'reports/rehab_backend/session_cold_verification.json', result)
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
