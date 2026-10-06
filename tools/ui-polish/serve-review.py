"""Isolated real shared-product server for visual QA. Never opens patient data."""
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'rehab_codex_single_camera_v2_1'), str(ROOT)]
os.environ['ANKANG_PRODUCT_DISABLE_MODEL'] = '1'
os.environ['ANKANG_VOICE_DISABLED'] = '1'
from app.product.backend import ProductBackend
from app.ui.product_dialogs import blank_health
from mobile_rehab.server import create_app
from mobile_rehab.unified import SharedProduct
import uvicorn

with tempfile.TemporaryDirectory(prefix='ankang-visual-TEST-') as folder:
    data = Path(folder)
    backend = ProductBackend(data / 'desktop')
    owner = 'visual-test'
    try:
        profile = blank_health('TEST 林女士')
        profile['age'] = 68
        backend.call('profile.save', owner, {'profile': profile, 'rehabGoal': 'TEST 恢复日常活动'})
        backend.call('medication.save', owner, {'record': {'id': 'test-med', 'name': 'TEST 医嘱药物', 'dose': '按既有医嘱', 'purpose': '', 'times': '08:00 / 20:00', 'status': 'active'}})
        backend.call('daily.medSchedule', owner, {'medId': 'test-med', 'times': ['08:00', '20:00'], 'start': date.today().isoformat(), 'end': ''})
        backend.call('health.record', owner, {'metric': 'weight', 'value': 62, 'visibility': 'private'})
        adapter = SharedProduct(backend, owner)
        app = create_app(data / 'phone', 'test-code', shared=adapter)
        uvicorn.run(app, host='127.0.0.1', port=8876, log_level='warning')
    finally:
        backend.close()
