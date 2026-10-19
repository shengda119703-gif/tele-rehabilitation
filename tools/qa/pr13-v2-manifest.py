"""Hash reproducible evidence; never interpret fixture results as live model tests."""
from datetime import datetime
from hashlib import sha256
from importlib.metadata import version
import json
from pathlib import Path
import platform
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'docs/validation/pr13-v2-evidence'
BASE = '06a8650b196991564cce431ec88d4b48c66df8a1'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True, encoding='utf-8').strip()


def checksum(path):
    return sha256(path.read_bytes()).hexdigest()


def generate():
    changed = git('diff', '--name-only', BASE, 'HEAD').splitlines()
    sources = [p for p in changed if not p.startswith('docs/') and (ROOT / p).is_file()]
    # Logs reflect real commands run in this task, not results inferred from hashes.
    runs = [
        dict(id='agent', cwd='ankang/route1-health-agent', command='npm run ci',
             result='582 TypeScript tests + 36 product tests passed; build/security passed', exit_code=0, evidence='agent-ci.txt', model='protocol fixtures'),
        dict(id='host', command='python -m pytest rehab_codex_single_camera_v2_1/tests/test_rehab_read_tools.py rehab_codex_single_camera_v2_1/tests/test_rehab_operation_tools.py -q --junitxml=.runtime/v2-host.xml',
             environment='PYTHONPATH=rehab_codex_single_camera_v2_1', result='23 passed', exit_code=0, evidence='host-tests.txt', database='real temporary SYNTHETIC TEST SQLite', model='protocol fixtures'),
        dict(id='cloud', command='python -m pytest cloud_service/tests -q --junitxml=.runtime/v2-cloud.xml',
             result='76 passed, 4 PostgreSQL tests skipped, 1 deprecation warning', exit_code=0, evidence='cloud-tests.txt', database='local test database, not production'),
        dict(id='web', command='node --test mobile_rehab/tests/*.cjs', result='124 passed', exit_code=0, evidence='web-tests.txt'),
        dict(id='android', command='python android_offline/tools/prepare_assets.py; node android_offline/tools/bundle_product.cjs; node --test android_offline/tests/*.test.cjs',
             result='assets/bundle succeeded; 85 JS tests passed', exit_code=0, evidence='android-tests.txt', limitation='repository root cwd; no APK/device verification'),
        dict(id='qt', command='python tools/qa/pr13-ui.py --data-dir .runtime/SYNTHETIC_TEST_PR13_V2_UI --output .runtime/v2-ui',
             result='6 Qt pages and offline chat passed', exit_code=0, evidence='desktop-results.json', limitation='offscreen PassiveRuntime, no camera or AI adoption'),
        dict(id='qt-main', cwd='rehab_codex_single_camera_v2_1',
             command='python -m app.main --data-dir ../.runtime/SYNTHETIC_TEST_PR13_V2_LAUNCH --screenshot ../.runtime/v2-ui/desktop-real-launch.png',
             environment='QT_QPA_PLATFORM=offscreen, ANKANG_PRODUCT_DISABLE_MODEL=1, ANKANG_VOICE_DISABLED=1',
             result='actual main screenshot startup completed', exit_code=0, evidence='desktop-real-launch.png', limitation='no camera/model test'),
        dict(id='browser', command='manual actual browser via cua against pr13-ui.py test server', result='pairing/navigation/offline reply/reload persistence passed',
             evidence='browser-review.md', limitation='not online model or candidate adoption'),
        dict(id='desktop-bulk', command='python -m pytest <all tests/test_product*.py> -q', result='incomplete: 10 failure markers by 48%, then no progress; interrupted',
             exit_code=1, evidence='desktop-bulk-interrupted.txt', limitation='no final count or complete JUnit'),
        dict(id='desktop-first', command='python -m pytest rehab_codex_single_camera_v2_1/tests/test_product_assistant.py -x -vv --junitxml=.runtime/v2-desktop-first.xml',
             result='4 passed, 1 failed (StopIteration: missing product-201 shortcut)', exit_code=1, evidence='desktop-tests.txt'),
    ]
    status = json.loads((OUT / 'status.json').read_text(encoding='utf-8'))
    result = dict(schema='pr13-v2-run-manifest-1', generated_at=datetime.now().astimezone().isoformat(),
        source_head=git('rev-parse', 'HEAD'), branch=git('branch', '--show-current'), baseline_head=BASE,
        complete=False, merge_recommended=False, live_model_tested=False,
        model_configuration_check=dict(configured=False, method='Boolean(localKey() || ANKANG_REHAB_LLM_API_KEY), no values printed'),
        environment=dict(python=platform.python_version(), node=subprocess.check_output(['node','--version'],text=True).strip(),
            packages={name:version(name) for name in ['pytest','PySide6-Essentials','numpy','opencv-python','SQLAlchemy','fastapi']}),
        runs=runs, source_files={p:checksum(ROOT / p) for p in sorted(sources)},
        evidence_files={p.name:checksum(p) for p in sorted(OUT.iterdir()) if p.is_file() and p.name != 'run-manifest.json'},
        acceptance=dict(original_nodes=len(status['nodes'][:77]), additional_ux=len(status['nodes'][77:]), full_results='status.json'))
    (OUT / 'run-manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(f"Manifest: {len(sources)} changed source files, {len(result['evidence_files'])} evidence files; complete=False")


if __name__ == '__main__':
    generate()
