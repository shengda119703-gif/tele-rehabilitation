"""Offline UI smoke only: real bridge/SQLite, isolated SYNTHETIC/TEST, no camera/model."""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'rehab_codex_single_camera_v2_1'),
                str(ROOT / 'rehab_codex_single_camera_v2_1/tests')]
os.environ.update(QT_QPA_PLATFORM='offscreen', ANKANG_PRODUCT_DISABLE_MODEL='1', ANKANG_VOICE_DISABLED='1')

from app.product.backend import ProductBackend
from app.ui.product_dialogs import blank_health
from app.settings import default_plan
from app.storage import Storage
from app.training_plans import item_from_plan, new_training_plan

OWNER = 'SYNTHETIC-TEST-pr13-ui'
SCOPE = dict(participant_id=OWNER, source_kind='SYNTHETIC', usage_context='TEST')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--serve', action='store_true')
    parser.add_argument('--port', type=int, default=8768)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    args.data_dir.mkdir(parents=True, exist_ok=True)
    backend = ProductBackend(args.data_dir)
    try:
        backend.call('profile.save', OWNER, dict(profile=blank_health('SYNTHETIC / TEST 验收用户')), SCOPE)
        store = Storage(args.data_dir / 'home_rehab.sqlite3')
        try:
            plans = store.list_training_plans(SCOPE)
            plan = plans[0] if plans else store.save_training_plan(new_training_plan(
                SCOPE, 'SYNTHETIC / TEST 手工计划（未验证适用性）',
                [item_from_plan(default_plan('sit_to_stand'))]), expected_revision=0)
        finally:
            store.close()
        if args.serve:
            import uvicorn
            from mobile_rehab.server import create_app
            from mobile_rehab.unified import SharedProduct
            class SyntheticShared(SharedProduct):
                def scope(self, source='LIVE_CAMERA'):
                    return dict(SCOPE)
            app = create_app(args.data_dir / 'phone', 'test-code', shared=SyntheticShared(backend, OWNER))
            print(json.dumps(dict(url=f'http://127.0.0.1:{args.port}', scope=SCOPE,
                                  offline=True, plan_id=plan['id']), ensure_ascii=False), flush=True)
            uvicorn.run(app, host='127.0.0.1', port=args.port, log_level='warning')
            return

        from PySide6.QtGui import QFont, QFontDatabase
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from app.ui.product_window import ProductWindow, NAVIGATION
        from test_product_window import PassiveRuntime, wait
        app = QApplication.instance() or QApplication([])
        for filename in ('msyh.ttc', 'msyhbd.ttc', 'segoeui.ttf'):
            font = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / filename
            if font.is_file():
                QFontDatabase.addApplicationFont(str(font))
        app.setFont(QFont('Microsoft YaHei UI', 10))
        window = ProductWindow(runtime=PassiveRuntime(args.data_dir), backend=backend)
        try:
            window.legacy.source_kind.setCurrentIndex(window.legacy.source_kind.findData('SYNTHETIC'))
            window.legacy.usage.setCurrentIndex(window.legacy.usage.findData('TEST'))
            window.legacy.busy = 0
            window.show()
            wait(app, lambda: bool(window.snapshot) and window.pending == 0)
            assert window.owner == OWNER and window.legacy._body_scope_key() == SCOPE
            assert window.snapshot['rehabilitation_ui']['rehab.get_training_plan']['records'][0]['id'] == plan['id']
            results = []
            for page in [p[0] for p in NAVIGATION] + ['assistant']:
                assert window.navigate(page)
                wait(app, lambda: window.pending == 0)
                assert window.pages.currentWidget() is window.page_widgets[page]
                QTest.qWait(150)
                if page in ('home', 'rehab', 'assistant'):
                    assert window.grab().save(str(args.output / f'desktop-{page}.png'))
                results.append('实际 Qt 页面：' + page)
            window._send_chat('你好')
            wait(app, lambda: window.pending == 0)
            assert window.snapshot['state']['chat'][-1]['conversation']['provider'] == 'local'
            assert not window.snapshot['state']['events']
            assert window.grab().save(str(args.output / 'desktop-offline-chat.png'))
            results.append('离线聊天真实回执，无新增健康事件')
            (args.output / 'desktop-results.json').write_text(json.dumps(dict(
                offline=True, scope=SCOPE, results=results, plan_id=plan['id'], revision=plan['revision'],
                candidate_adoption=False, runtime='PassiveRuntime: no camera commands executed'), ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps(dict(offline=True, results=results), ensure_ascii=False))
        finally:
            window.legacy._allow_close = True
            window.close()
            window.deleteLater()
            app.processEvents()
    finally:
        backend.close()


if __name__ == '__main__':
    main()
