"""Isolated real shared-product server for visual QA. Never opens patient data."""
import os
import argparse
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

def serve(data, *, complete=False, port=8876):
    from test_lin_profile import FixtureClock, OWNER, claim_directory, seed
    if complete:
        claim_directory(data)
    clock = FixtureClock()
    backend = ProductBackend(data / 'desktop', bridge_factory=(lambda: clock.bridge(data)) if complete else None)
    owner = OWNER
    try:
        if complete:
            seed(backend, data, clock)
        else:
            profile = blank_health('TEST 林女士')
            profile['age'] = 68
            backend.call('profile.save', owner, {'profile': profile, 'rehabGoal': 'TEST 恢复日常活动'})
            backend.call('medication.save', owner, {'record': {'id': 'test-med', 'name': 'TEST 医嘱药物', 'dose': '按既有医嘱', 'purpose': '', 'times': '08:00 / 20:00', 'status': 'active'}})
            backend.call('daily.medSchedule', owner, {'medId': 'test-med', 'times': ['08:00', '20:00'], 'start': date.today().isoformat(), 'end': ''})
            backend.call('health.record', owner, {'metric': 'weight', 'value': 62, 'visibility': 'private'})
        adapter = SharedProduct(backend, owner)
        app = create_app(data / 'phone', 'test-code', shared=adapter)
        server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, log_level='warning'))
        # Reuse the app's own graceful-stop watcher for this independently owned host.
        (data/'phone'/'stop-request').unlink(missing_ok=True)
        app.state.shutdown = lambda: setattr(server, 'should_exit', True)
        server.run()
    finally:
        backend.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='独立 TEST 档案，不打开患者数据库。')
    parser.add_argument('--complete', action='store_true', help='保留完整 TEST 林女士档案')
    parser.add_argument('--data-root', type=Path, default=ROOT/'qa-output'/'test-lin-profile')
    parser.add_argument('--port', type=int, default=8876)
    args = parser.parse_args()
    if args.complete:
        serve(args.data_root.resolve(), complete=True, port=args.port)
    else:
        with tempfile.TemporaryDirectory(prefix='ankang-visual-TEST-') as folder:
            serve(Path(folder), port=args.port)
