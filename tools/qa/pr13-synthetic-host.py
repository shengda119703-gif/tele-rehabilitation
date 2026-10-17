"""Real isolated SQLite host for PR13 acceptance; never opens an application data path."""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'rehab_codex_single_camera_v2_1'))
from app.demo_training_plan import DEMO_SCOPE, install_demo_plan
from app.storage import Storage
from app.rehab_read_tools import RehabReadTools
from app.rehab_operation_tools import RehabOperationTools
from app.product.daily_store import DailyStore

folder = Path(sys.argv[2]).resolve()
assert 'SYNTHETIC_TEST_PR13' in folder.parts, 'requires explicit isolated SYNTHETIC/TEST directory'
database = folder / 'synthetic.sqlite3'
if sys.argv[1] == 'init':
    folder.mkdir(parents=True, exist_ok=True)
    assert not database.exists(), 'use a fresh isolated directory per run'
    store = Storage(database)
    try:
        plan = install_demo_plan(store)['plan']
        entry = plan['items'][0]
        store.save_session(dict(DEMO_SCOPE, id='SYNTHETIC_TEST_PR13_HISTORY', scene_id='rehab',
            submode='training', exercise_id=entry['exercise_id'], side=entry['side'], status='FINISHED',
            start_utc='2026-10-17T00:00:00+00:00', end_utc='2026-10-17T00:10:00+00:00',
            measurement_mode='auto_observed', summary={'completed': 3, 'plan_completed': True},
            saved_plan_reference={'id': plan['id'], 'revision': plan['revision'], 'entry_key': entry['key']},
            repetitions=[], config_snapshot={}))
    finally:
        store.close()
    print(json.dumps({'scope': DEMO_SCOPE, 'database_sha256': hashlib.sha256(database.read_bytes()).hexdigest()}))
elif sys.argv[1] == 'read':
    print(json.dumps(RehabReadTools(database, DEMO_SCOPE)(sys.argv[3], json.loads(sys.argv[4])), ensure_ascii=False))
elif sys.argv[1] == 'operation':
    daily = DailyStore(folder / 'daily')
    print(json.dumps(RehabOperationTools(database, DEMO_SCOPE, daily, DEMO_SCOPE['participant_id'])(
        sys.argv[3], json.loads(sys.argv[4])), ensure_ascii=False))
else:
    raise ValueError('unknown host command')
