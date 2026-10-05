"""Native five-page captures using isolated TEST profiles and real product bridge."""
import os
os.environ['QT_QPA_PLATFORM'] = 'windows'
import sys
import json
import tempfile
from datetime import date
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tests'), str(ROOT), str(ROOT.parent)]
import pytest
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt
from test_product_window import desktop, wait
from bridges.ankang.client import AgentBridge
from app.ui.product_dialogs import blank_health

out = ROOT / 'qa-output/five-pages'
out.mkdir(parents=True, exist_ok=True)
observations = []
for width, theme in ((1440, 'light'), (1024, 'light'), (1440, 'dark'), (1024, 'dark')):
    with tempfile.TemporaryDirectory(prefix='ankang-five-TEST-') as td:
        patch = pytest.MonkeyPatch()
        gen = desktop.__wrapped__(Path(td), patch)
        w, app = next(gen)
        try:
            w.resize(width, 940); w.product_theme.apply(theme)
            def capture(name):
                QTest.qWait(150)
                path = out / f'{width}-{theme}-{name}.png'
                assert w.grab().save(str(path))
                observations.append(dict(width=width, theme=theme, state=name, dpr=w.devicePixelRatioF()))
            for page in ('home', 'rehab', 'health', 'medication', 'family', 'assistant'):
                w.navigate(page); wait(app, lambda: not w.pending); capture(page)
            w.navigate('home'); wait(app, lambda: not w.pending)
            w.interface_buttons['homeConversation'].setFocus(Qt.TabFocusReason)
            QTest.mouseMove(w.interface_buttons['homeConversation']); capture('focus-hover')
            QTest.keyClick(w.interface_buttons['homeConversation'], Qt.Key_Space)
            assert w.active_page == 'assistant'
            w._request('health.record', dict(metric='invalid', value=1)); wait(app, lambda: not w.pending); capture('error')
            w.navigate('rehab'); wait(app, lambda: not w.pending)
            w._request('snapshot'); capture('loading'); wait(app, lambda: not w.pending)
            w._first_use(existing=True); QTest.qWait(80)
            assert w.daily_dialog
            w.daily_dialog.grab().save(str(out / f'{width}-{theme}-onboarding.png'))
            w.daily_dialog.reject()
            day=date.today().isoformat()
            w._request('medication.save',{'record':dict(id='TEST-med',name='TEST 已有医嘱药物',dose='按已有医嘱',purpose='',times='早晚',status='active')});wait(app,lambda:not w.pending)
            w._request('daily.medSchedule',dict(medId='TEST-med',times=['08:00','20:00'],start=day,end=''));wait(app,lambda:not w.pending)
            w.navigate('medication');wait(app,lambda:not w.pending)
            w.dose_table.selectRow(0);w._completion_controls();w.interface_buttons['doseTaken'].click();wait(app,lambda:not w.pending);capture('medication-populated')
            with AgentBridge(data_dir=Path(td)/'product') as bridge:
                bridge.product('profile.save','TEST-parent',dict(profile=blank_health('TEST 家人')))
                bridge.product('health.record','TEST-parent',dict(metric='weight',value=61,visibility='family_ok'))
            scope=w.legacy._body_scope_key()
            code=w.backend.daily.apply('TEST-parent','daily.familyInvite',{},scope)['code']
            w._request('daily.familyBind',{'code':code});wait(app,lambda:not w.pending)
            w.backend.daily.apply('TEST-parent','daily.familyGrant',dict(member=w.owner,categories=['health']),scope)
            w.navigate('family');wait(app,lambda:not w.pending);capture('family-populated')
            w.linked_family.selectRow(0);w._completion_controls();w.interface_buttons['familyReadOnly'].click();QTest.qWait(80)
            w.last_detail.grab().save(str(out/f'{width}-{theme}-family-readonly.png'));w.last_detail.close()
            w.navigate('home');wait(app,lambda:not w.pending);capture('home-populated')
            print(f'{width} {theme}: captured', flush=True)
        finally:
            try: next(gen)
            except StopIteration: pass
            patch.undo()
(out / 'observations.json').write_text(json.dumps(observations, ensure_ascii=False, indent=2), encoding='utf-8')
