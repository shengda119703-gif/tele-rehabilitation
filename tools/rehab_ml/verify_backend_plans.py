"""Run owned isolated plan/host audits; no UI, APK or normal data operations."""
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
from tools.rehab_ml.common import file_hash, paths, write_json

SOURCES = ('rehab_codex_single_camera_v2_1/app/rehab_v2/plans.py',
           'mobile_rehab/rehab_v2/service.py', 'mobile_rehab/rehab_v2/api.py', 'mobile_rehab/server.py',
           'tests/rehab_backend/test_backend_plans.py', 'tools/rehab_ml/verify_backend_plans.py')


def main():
    root = paths()['run']/('backend-plan-audit-'+uuid4().hex[:8])
    root.mkdir()
    hashes = {p:file_hash(ROOT/p) for p in SOURCES}
    arguments = ['-m','unittest','discover','-s','tests/rehab_backend','-p','test_backend_plans.py','-v']
    environment = dict(os.environ, PYTHONPATH=str(ROOT/'rehab_codex_single_camera_v2_1')+os.pathsep+str(ROOT))
    started = time.perf_counter()
    result = dict(run_id=root.name, commands=[], implementation_sha256=hashes,
        scope='isolated_backend_explicit_plans_and_actual_host_http', clinical_accuracy=None,
        human_data=False, training_performed=False, frontend_modified=False, apk_modified=False,
        evidence_domains=['SYNTHETIC/TEST internal evidence', 'isolated TEST-only HTTP geometry provider',
                         'real original YOLO white-JPEG missing-person rejection'],
        no_human_accuracy_or_automatic_prescription_claim=True)
    try:
        completed = subprocess.run([sys.executable,'-X','utf8','-B',*arguments], cwd=ROOT, env=environment,
            capture_output=True, text=True, encoding='utf-8', timeout=120)
        output = completed.stdout+completed.stderr
        log = root/'plans.txt'
        log.write_text(output, encoding='utf-8')
        match = re.search(r'Ran (\d+) tests', output)
        count = int(match.group(1)) if match else None
        result['commands'].append(dict(arguments=arguments, exit_code=completed.returncode,
            elapsed_s=time.perf_counter()-started, log=str(log), log_sha256=file_hash(log), tests=count,
            tail=output[-1600:]))
        result['passed'] = completed.returncode == 0 and count is not None and count >= 19
    except subprocess.TimeoutExpired:
        result.update(passed=False, timeout_s=120)
    result['implementation_unchanged'] = hashes == {p:file_hash(ROOT/p) for p in SOURCES}
    result['passed'] = result['passed'] and result['implementation_unchanged']
    write_json(ROOT/'reports/rehab_backend/backend_plan_verification.json', result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
