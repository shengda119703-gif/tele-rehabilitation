"""Generate the Android catalog from the existing contracts, not a second list."""
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mobile_rehab.core import EXERCISE_IDS, exercise_spec
from app.exercise_instructions import exercise_instructions, JOINT_LABELS
from app.automatic_plans import RECIPES, SOURCES
from mobile_rehab.fitness import catalog as fitness_catalog
from mobile_rehab.posture import catalog as posture_catalog, METRICS
from mobile_rehab.barbell import demo_report

PROJECT = ROOT / 'android_offline'
OUTPUT = PROJECT / 'build/assets'
OUTPUT.mkdir(parents=True, exist_ok=True)
shutil.copytree(PROJECT / 'web', OUTPUT / 'local', dirs_exist_ok=True, ignore=shutil.ignore_patterns('app.js','index.html','style.css'))
# These generated artifacts came from the archived 0.1 UI, not user documents.
for name in ['app.js','index.html','style.css']:
    (OUTPUT / 'local' / name).unlink(missing_ok=True)
# Formal UI is copied unchanged. Only non-visual loaders are inserted in HTML.
static = ROOT / 'mobile_rehab/static'
shutil.copytree(static, OUTPUT / 'static', dirs_exist_ok=True)
adapters = ''.join('<script src="' + path + '"></script>' for path in ['/local/engine.js','/local/product.js','/local/model-policy.js','/local/deepseek.js','/local/store.js','/local/motion.js','/local/lin-profile.js','/local/cloud.js','/local/account.js','/local/local-api.js'])
for source, target in [('unified.html', 'index.html'), ('index.html', 'capture.html')]:
    html = (static / source).read_text(encoding='utf-8').replace('<head>', '<head>' + adapters)
    (OUTPUT / target).write_text(html, encoding='utf-8')
locked = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in static.iterdir() if p.is_file()}
(OUTPUT / 'ui-lock.json').write_text(json.dumps(locked, sort_keys=True), encoding='utf-8')
vendor = PROJECT / 'node_modules/@mediapipe/tasks-vision'
if not (vendor / 'vision_bundle.cjs').exists():
    raise SystemExit('Run npm ci in android_offline first')
shutil.copytree(vendor / 'wasm', OUTPUT / 'vendor/wasm', dirs_exist_ok=True)
shutil.copy2(vendor / 'vision_bundle.cjs', OUTPUT / 'vendor/vision_bundle.js')
# Remove stale generated OCR files from previous builds, not source or user data.
retired_ocr = OUTPUT / 'ocr'
if not OUTPUT.resolve().is_relative_to(PROJECT.resolve()) or not retired_ocr.resolve().is_relative_to(OUTPUT.resolve()):
    raise SystemExit('Generated OCR cleanup path escaped the Android assets directory')
shutil.rmtree(retired_ocr, ignore_errors=True)
(OUTPUT / 'local/ocr.js').unlink(missing_ok=True)
data = dict(version='android-local-projection-1', rehab=[dict(
    id=eid, **exercise_spec(eid), joint_label=JOINT_LABELS[exercise_spec(eid)['joint']],
    instructions=exercise_instructions(eid)) for eid in EXERCISE_IDS],
    fitness=fitness_catalog(), posture=posture_catalog(), posture_metrics=METRICS,
    recipes=RECIPES, sources=SOURCES)
(OUTPUT / 'catalog.json').write_text(json.dumps(data, ensure_ascii=False, allow_nan=False), encoding='utf-8')
# The existing explicit simulation stays separate from all personal records.
(OUTPUT / 'fitness-demo.json').write_text(json.dumps(demo_report(), ensure_ascii=False, allow_nan=False), encoding='utf-8')
models = ROOT / 'rehab_codex_single_camera_v2_1/assets/models'
manifest_path = models / 'landmarks-manifest.json'
manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
for record in manifest['models'].values():
    source = models / record['filename']
    if hashlib.sha256(source.read_bytes()).hexdigest() != record['sha256']:
        raise SystemExit('Model checksum mismatch: ' + record['filename'])
    (OUTPUT / 'models').mkdir(exist_ok=True)
    shutil.copy2(source, OUTPUT / 'models' / record['filename'])
shutil.copy2(manifest_path, OUTPUT / 'models/manifest.json')
print(f"Catalog: {len(data['rehab'])} rehabilitation, {len(data['fitness'])} fitness, {len(data['posture'])} posture; assets prepared")
