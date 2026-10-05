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

PROJECT = ROOT / 'android_offline'
OUTPUT = PROJECT / 'build/assets'
OUTPUT.mkdir(parents=True, exist_ok=True)
shutil.copytree(PROJECT / 'web', OUTPUT, dirs_exist_ok=True)
vendor = PROJECT / 'node_modules/@mediapipe/tasks-vision'
if not (vendor / 'vision_bundle.cjs').exists():
    raise SystemExit('Run npm ci in android_offline first')
shutil.copytree(vendor / 'wasm', OUTPUT / 'vendor/wasm', dirs_exist_ok=True)
shutil.copy2(vendor / 'vision_bundle.cjs', OUTPUT / 'vendor/vision_bundle.js')
data = dict(version='android-local-projection-1', rehab=[dict(
    id=eid, **exercise_spec(eid), joint_label=JOINT_LABELS[exercise_spec(eid)['joint']],
    instructions=exercise_instructions(eid)) for eid in EXERCISE_IDS],
    fitness=fitness_catalog(), posture=posture_catalog(), posture_metrics=METRICS,
    recipes=RECIPES, sources=SOURCES)
(OUTPUT / 'catalog.json').write_text(json.dumps(data, ensure_ascii=False, allow_nan=False), encoding='utf-8')
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
