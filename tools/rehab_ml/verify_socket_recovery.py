"""Three tests and three fixed actual TCP/server-restart audit repetitions."""
from __future__ import annotations

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
from tools.rehab_ml.common import paths, write_json, file_hash
from tools.rehab_ml.socket_recovery_audit import SOURCES


def main():
    run = paths()['run']/('socket-verification-'+uuid4().hex[:8]); run.mkdir()
    sources = (*SOURCES, 'tools/rehab_ml/verify_socket_recovery.py', 'tests/rehab_backend/test_socket_recovery.py',
               'tools/rehab_ml/native_parent_audit.py', 'tools/rehab_ml/session_load_audit.py')
    hashes = {name:file_hash(ROOT/name) for name in sources}
    result = dict(run_id=run.name, source_sha256=hashes, repetitions_declared_before_running=3,
                  command_timeout_s=90, commands=[], attempts=[], clinical_accuracy=None)
    commands = [('unit', ['-m','unittest','discover','-s','tests/rehab_backend','-p','test_socket_recovery.py','-v'])]
    commands += [('repeat_'+str(index+1), ['tools/rehab_ml/socket_recovery_audit.py','--publish']) for index in range(3)]
    write_json(run/'predeclared.json', dict(result, command_plan=commands))
    for name, arguments in commands:
        started = time.perf_counter(); output = ''; record = dict(name=name, arguments=arguments, exit_code=None)
        try:
            command = subprocess.run([sys.executable,'-X','utf8','-B',*arguments], cwd=ROOT,
                env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=str(ROOT/'rehab_codex_single_camera_v2_1')+os.pathsep+str(ROOT)),
                capture_output=True,text=True,encoding='utf-8',timeout=result['command_timeout_s'])
            record['exit_code'] = command.returncode; output = command.stdout+command.stderr
            if name == 'unit':
                match = re.search(r'Ran (\d+) tests', output)
                record['tests'] = int(match.group(1)) if match else None
            else:
                payload = json.loads(command.stdout); raw = payload['raw_summary']; path = Path(raw['path']).resolve()
                if not path.is_relative_to(run.parent) or file_hash(path) != raw['sha256']:
                    raise RuntimeError('socket_raw_summary_scope_or_hash_failed')
                original = json.loads(path.read_text(encoding='utf-8'))
                if original['source_sha256'] != {name:hashes[name] for name in SOURCES}:
                    raise RuntimeError('socket_source_hash_mismatch')
                for host in original['hosts']:
                    log = Path(host['log']['path']).resolve()
                    if not log.is_relative_to(path.parent) or file_hash(log) != host['log']['sha256']:
                        raise RuntimeError('socket_host_log_scope_or_hash_failed')
                result['attempts'].append(dict(run_id=original['run_id'],raw_summary=raw,
                    passed=original['passed'] and payload['passed'],checks=original['checks'],hosts=original['hosts']))
        except subprocess.TimeoutExpired as error:
            output = ''.join(part.decode('utf-8',errors='replace') if isinstance(part,bytes) else part or '' for part in (error.stdout,error.stderr))
            record.update(status='timeout',cleanup='unverified_not_a_pass')
        except Exception as error:
            record.update(status='audit_error',error_type=type(error).__name__,error=str(error))
        log = run/(name+'.txt'); log.write_text(output,encoding='utf-8')
        record.update(elapsed_s=time.perf_counter()-started,log=str(log),log_sha256=file_hash(log))
        result['commands'].append(record); write_json(run/'summary.json',result)
        if record['exit_code'] != 0 or record.get('status'):
            break
    result['source_unchanged'] = hashes == {name:file_hash(ROOT/name) for name in sources}
    result['passed'] = (len(result['commands']) == 4 and len(result['attempts']) == 3 and result['source_unchanged']
        and result['commands'][0].get('tests') == 3 and all(row['exit_code'] == 0 and not row.get('status') for row in result['commands'])
        and all(row['passed'] and len(row['checks']) == 22 and all(row['checks'].values()) for row in result['attempts']))
    write_json(run/'summary.json',result); write_json(ROOT/'reports/rehab_backend/socket_verification.json',result)
    print(json.dumps(dict(run_id=result['run_id'],passed=result['passed'],commands=result['commands'],
                         attempts=[dict(run_id=row['run_id'],passed=row['passed']) for row in result['attempts']]),allow_nan=False))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
