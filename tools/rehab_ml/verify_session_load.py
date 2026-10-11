"""Log arithmetic tests and three fixed-workload original-YOLO HTTP runs.

All attempts, including failures, are retained; this is not best-run selection.
"""
from __future__ import annotations

import json
import argparse
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


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    root = paths()['run']/('session-load-verification-'+uuid4().hex[:8])
    root.mkdir()
    sources = ('tools/rehab_ml/session_load_audit.py', 'tools/rehab_ml/verify_session_load.py',
               'tools/rehab_ml/cli.py', 'tests/rehab_backend/test_session_load_audit.py')
    hashes = {path: file_hash(ROOT/path) for path in sources}
    summary = dict(run_id=root.name, commands=[], attempts=[], implementation_sha256=hashes,
                   repetitions_declared_before_running=3, clinical_accuracy=None)
    write_json(root/'predeclared.json', summary)
    cases = [('unit', ['-m', 'unittest', 'discover', '-s', 'tests/rehab_backend', '-p', 'test_session_load_audit.py', '-v'])]
    cases.extend(('native_'+str(index+1), ['tools/rehab_ml/cli.py', 'benchmark-session-load']) for index in range(3))
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
            record = dict(name=name, arguments=arguments, exit_code=done.returncode,
                          elapsed_s=time.perf_counter()-started, log=str(log), log_sha256=file_hash(log),
                          tests=int(match.group(1)) if match else None)
            if name.startswith('native_'):
                # Parse this child stdout, never a shared "latest" result file.
                payload = json.loads(done.stdout)
                value = payload['result']
                summary['attempts'].append(dict(run_id=value['run_id'], passed=value['passed'],
                    engineering_invariants_passed=value['engineering_invariants_passed'],
                    control_budget=value['control_budget'], at_finish=value.get('at_finish'),
                    producer_done_at_finish=value.get('producer_done_at_finish'), load_http=value.get('load_http'),
                    status_counts=value.get('reconciliation', {}).get('status_counts'),
                    cold_first=value.get('cold_first'), warm_stages=value.get('warm_stages'),
                    raw_summary=value['raw_summary'], raw_details=value['raw_details']))
        except subprocess.TimeoutExpired as error:
            output = ''.join(value.decode('utf-8', errors='replace') if isinstance(value, bytes) else value or ''
                             for value in (error.stdout, error.stderr))
            log = root/(name+'-timeout.txt')
            log.write_text(output, encoding='utf-8')
            record = dict(name=name, arguments=arguments, exit_code=None, status='timeout',
                          elapsed_s=time.perf_counter()-started, log=str(log), log_sha256=file_hash(log))
        except Exception as error:
            # Invalid stdout or a launcher error is failure, not a replacement run.
            record = dict(name=name, arguments=arguments, exit_code=None, status='audit_error',
                          error_type=type(error).__name__, error=str(error), elapsed_s=time.perf_counter()-started)
        summary['commands'].append(record)
        if record.get('exit_code') != 0:
            break
    summary['implementation_unchanged'] = hashes == {path: file_hash(ROOT/path) for path in sources}
    summary['passed'] = (len(summary['commands']) == 4 and len(summary['attempts']) == 3 and
                         summary['commands'][0].get('tests') == 7 and summary['implementation_unchanged'] and
                         all(row.get('exit_code') == 0 for row in summary['commands']) and
                         all(row['passed'] for row in summary['attempts']))
    write_json(root/'summary.json', summary)
    write_json(ROOT/'reports/rehab_backend/session_load_verification.json', summary)
    print(json.dumps(summary, ensure_ascii=False, allow_nan=False))
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
