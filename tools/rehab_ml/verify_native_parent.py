"""Seven lifecycle tests and three predeclared native host-death repeats."""
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
from tools.rehab_ml.native_parent_audit import CASES, SOURCES
from tools.rehab_ml.common import file_hash, paths, write_json


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    run = paths()['run']/('native-parent-verification-'+uuid4().hex[:8])
    run.mkdir()
    sources = (*SOURCES, 'tools/rehab_ml/verify_native_parent.py', 'tests/rehab_backend/test_host_lifetime.py')
    hashes = {path: file_hash(ROOT/path) for path in sources}
    commands = [('unit', ['-m', 'unittest', 'discover', '-s', 'tests/rehab_backend',
                           '-p', 'test_host_lifetime.py', '-v'])]
    commands.extend(('repeat_'+str(index+1), ['tools/rehab_ml/native_parent_audit.py', '--publish']) for index in range(3))
    result = dict(run_id=run.name, commands=[], attempts=[], source_sha256=hashes,
                  repetitions_declared_before_running=3, command_timeout_s=180,
                  clinical_accuracy=None, target_platform='Windows', socket_or_camera=False)
    write_json(run/'predeclared.json', result)
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
        PYTHONPATH=str(ROOT/'rehab_codex_single_camera_v2_1')+os.pathsep+str(ROOT))
    for name, arguments in commands:
        started = time.perf_counter()
        record = dict(name=name, arguments=arguments, exit_code=None)
        output = ''
        try:
            command = subprocess.run([sys.executable, '-X', 'utf8', '-B', *arguments], cwd=ROOT,
                env=environment, capture_output=True, text=True, encoding='utf-8', timeout=result['command_timeout_s'])
            record['exit_code'] = command.returncode
            output = command.stdout+command.stderr
            if name == 'unit':
                match = re.search(r'Ran (\d+) tests', output)
                record['tests'] = int(match.group(1)) if match else None
            else:
                payload = json.loads(command.stdout)
                raw = payload['raw_summary']
                path = Path(raw['path']).resolve()
                if not path.is_relative_to(run.parent) or file_hash(path) != raw['sha256']:
                    raise RuntimeError('native_raw_summary_scope_or_hash_failed')
                original = json.loads(path.read_text(encoding='utf-8'))
                if original['source_sha256'] != {name: hashes[name] for name in SOURCES}:
                    raise RuntimeError('native_source_mismatch')
                cases = []
                for case in original['cases']:
                    artifact = Path(case['log']['path']).resolve()
                    if not artifact.is_relative_to(path.parent) or file_hash(artifact) != case['log']['sha256']:
                        raise RuntimeError('native_child_log_scope_or_hash_failed')
                    cases.append({key: value for key, value in case.items() if key != 'proof'})
                passed = (original['passed'] and payload['passed'] and original['source_unchanged']
                    and [row['case'] for row in cases] == list(CASES)
                    and all(row['passed'] and not row['supervisor_cleanup_required']
                            and row['host_actual_exit_confirmed'] and len(row['checks']) == 11
                            and all(row['checks'].values()) for row in cases))
                result['attempts'].append(dict(run_id=original['run_id'], passed=passed, raw_summary=raw, cases=cases))
        except subprocess.TimeoutExpired as error:
            output = ''.join(value.decode('utf-8', errors='replace') if isinstance(value, bytes)
                             else value or '' for value in (error.stdout, error.stderr))
            record.update(status='timeout', cleanup='unverified_not_a_pass')
        except Exception as error:
            record.update(status='audit_error', error_type=type(error).__name__, error=str(error))
        log = run/(name+'.txt')
        log.write_text(output, encoding='utf-8')
        record.update(elapsed_s=time.perf_counter()-started, log=str(log), log_sha256=file_hash(log))
        result['commands'].append(record)
        write_json(run/'summary.json', result)
        if record.get('exit_code') != 0 or record.get('status'):
            break
    result['source_unchanged'] = hashes == {path: file_hash(ROOT/path) for path in sources}
    result['passed'] = (len(result['commands']) == 4 and len(result['attempts']) == 3
        and result['commands'][0].get('tests') == 7 and result['source_unchanged']
        and all(row.get('exit_code') == 0 and not row.get('status') for row in result['commands'])
        and all(row['passed'] for row in result['attempts']))
    write_json(run/'summary.json', result)
    write_json(ROOT/'reports/rehab_backend/native_parent_verification.json', result)
    print(json.dumps(dict(run_id=result['run_id'], passed=result['passed'], commands=result['commands'],
        attempts=[dict(run_id=row['run_id'], passed=row['passed'],
                       auto_exit_wait_ms=[case['auto_exit_wait_ms'] for case in row['cases']])
                  for row in result['attempts']]), allow_nan=False))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
