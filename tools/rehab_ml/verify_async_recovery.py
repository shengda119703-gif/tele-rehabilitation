"""Four tests plus three predeclared repeats of exact-owned host crash windows."""
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
from tools.rehab_ml.async_recovery import CASES, SOURCES
from tools.rehab_ml.common import file_hash, paths, write_json


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    run = paths()['run']/('async-recovery-verification-'+uuid4().hex[:8])
    run.mkdir()
    sources = (*SOURCES, 'tools/rehab_ml/verify_async_recovery.py',
               'tests/rehab_backend/test_async_recovery.py')
    hashes = {name: file_hash(ROOT/name) for name in sources}
    commands = [('unit', ['-m', 'unittest', 'discover', '-s', 'tests/rehab_backend',
                          '-p', 'test_async_recovery.py', '-v'])]
    commands.extend(('repeat_'+str(index+1), ['tools/rehab_ml/async_recovery.py']) for index in range(3))
    result = dict(run_id=run.name, commands=[], attempts=[], source_sha256=hashes,
                  repetitions_declared_before_running=3, command_timeout_s=180,
                  clinical_accuracy=None, network_test=False, native_inflight_child=False)
    write_json(run/'predeclared.json', result)
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
        PYTHONPATH=str(ROOT/'rehab_codex_single_camera_v2_1')+os.pathsep+str(ROOT))
    for name, arguments in commands:
        started = time.perf_counter()
        record = dict(name=name, arguments=arguments, exit_code=None)
        output = ''
        log = run/(name+'.txt')
        try:
            completed = subprocess.run([sys.executable, '-X', 'utf8', '-B', *arguments],
                cwd=ROOT, env=environment, capture_output=True, text=True,
                encoding='utf-8', timeout=result['command_timeout_s'])
            output = completed.stdout+completed.stderr
            record['exit_code'] = completed.returncode
            if name == 'unit':
                match = re.search(r'Ran (\d+) tests', output)
                record['tests'] = int(match.group(1)) if match else None
            else:
                payload = json.loads(completed.stdout)
                raw = payload['raw_summary']
                raw_path = Path(raw['path']).resolve()
                if not raw_path.is_relative_to(run.parent) or file_hash(raw_path) != raw['sha256']:
                    raise RuntimeError('raw_summary_scope_or_hash_failed')
                original = json.loads(raw_path.read_text(encoding='utf-8'))
                if (original['source_sha256'] != {path: hashes[path] for path in SOURCES}
                        or original['passed'] != payload['passed']):
                    raise RuntimeError('source_or_summary_mismatch')
                cases = []
                for case in original['cases']:
                    for artifact in ('log', 'details'):
                        path = Path(case[artifact]['path']).resolve()
                        if not path.is_relative_to(raw_path.parent) or file_hash(path) != case[artifact]['sha256']:
                            raise RuntimeError('case_artifact_scope_or_hash_failed')
                    cases.append(dict(case=case['case'], passed=case['passed'],
                        checks=case['checks'], actual_exit_confirmed=case['actual_exit_confirmed'],
                        exit_code=case['exit_code'], elapsed_s=case['elapsed_s'],
                        log=case['log'], details=case['details']))
                passed = (payload['passed'] and original['source_unchanged']
                    and [row['case'] for row in cases] == list(CASES)
                    and all(row['passed'] and row['actual_exit_confirmed']
                        and row['exit_code'] not in (None, 0)
                        and len(row['checks']) >= 30 and all(row['checks'].values()) for row in cases))
                result['attempts'].append(dict(run_id=payload['run_id'], passed=passed,
                                               raw_summary=raw, cases=cases))
        except subprocess.TimeoutExpired as error:
            output = ''.join(value.decode('utf-8', errors='replace') if isinstance(value, bytes)
                             else value or '' for value in (error.stdout, error.stderr))
            record.update(status='timeout', actual_host_cleanup='unverified_not_a_pass')
        except Exception as error:
            record.update(status='audit_error', error_type=type(error).__name__, error=str(error))
        log.write_text(output, encoding='utf-8')
        record.update(elapsed_s=time.perf_counter()-started, log=str(log), log_sha256=file_hash(log))
        result['commands'].append(record)
        write_json(run/'summary.json', result)
        if record.get('exit_code') != 0 or record.get('status'):
            break
    result['source_unchanged'] = hashes == {name: file_hash(ROOT/name) for name in sources}
    result['passed'] = (len(result['commands']) == 4 and len(result['attempts']) == 3
        and result['commands'][0].get('tests') == 4 and result['source_unchanged']
        and all(row.get('exit_code') == 0 and not row.get('status') for row in result['commands'])
        and all(row['passed'] for row in result['attempts']))
    write_json(run/'summary.json', result)
    write_json(ROOT/'reports/rehab_backend/async_recovery_verification.json', result)
    print(json.dumps(dict(run_id=result['run_id'], passed=result['passed'],
        source_unchanged=result['source_unchanged'], commands=result['commands'],
        attempts=[dict(run_id=row['run_id'], passed=row['passed'],
                       cases=[dict(case=case['case'], checks=len(case['checks']),
                                   passed=case['passed'], exit_code=case['exit_code'])
                              for case in row['cases']]) for row in result['attempts']]),
        ensure_ascii=False, allow_nan=False))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
