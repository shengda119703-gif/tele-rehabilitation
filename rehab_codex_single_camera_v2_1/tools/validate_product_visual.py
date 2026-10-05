"""Capture actual Qt Widgets using isolated SYNTHETIC/TEST services, no camera/LLM.

Run in separate processes for each QT_SCALE_FACTOR. Output is ignored QA material;
selected reviewed screenshots are copied into docs. No user data is opened.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ['ANKANG_PRODUCT_DISABLE_MODEL']='1'
os.environ.setdefault('ANKANG_VOICE_DISABLED','1')
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT.parent)]
from PySide6.QtCore import QEventLoop,QTimer,Qt
from PySide6.QtGui import QFont,QFontDatabase,QPalette,QColor
from PySide6.QtWidgets import QApplication,QTabWidget,QDialogButtonBox
from PySide6.QtTest import QTest
from app.runtime import Runtime
from app.storage import Storage
from app.demo_training_plan import install_demo_plan,DEMO_PARTICIPANT_ID
from app.ui.product_window import ProductWindow
from app.ui.product_dialogs import blank_health
from app.product.backend import ProductBackend
from bridges.ankang.client import AgentBridge


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--width',type=int,default=1440)
    parser.add_argument('--height',type=int,default=940)
    parser.add_argument('--theme',choices=('light','dark','high-contrast'),default='light')
    parser.add_argument('--output-root',type=Path)
    parser.add_argument('--phase',choices=('fluent-v1','assistant-modules','module-paths','ux-audit'),default='fluent-v1')
    args=parser.parse_args()
    factor=os.environ.get('QT_SCALE_FACTOR','auto')
    platform=os.environ['QT_QPA_PLATFORM']
    out=(args.output_root or ROOT/'qa-output'/args.phase)/f'{platform}-{args.theme}-{args.width}x{args.height}-scale{factor}'
    out.mkdir(parents=True,exist_ok=True)
    app=QApplication([]);app.setStyle('Fusion')
    for name in ('msyh.ttc','msyhbd.ttc','segoeui.ttf'):
        QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+name)
    app.setFont(QFont('Microsoft YaHei UI',10))
    with tempfile.TemporaryDirectory(prefix='fluent-qt-') as directory:
        data=Path(directory)
        store=Storage(data/'home_rehab.sqlite3');install_demo_plan(store);store.close()
        with AgentBridge(data_dir=data/'product') as bridge:
            bridge.product('profile.save',DEMO_PARTICIPANT_ID,dict(profile=blank_health('TEST 视觉验收用户'),rehabGoal='TEST 恢复日常活动'))
            bridge.product('medication.save',DEMO_PARTICIPANT_ID,dict(record=dict(id='test-med',name='TEST 医嘱药物',dose='TEST 剂量',purpose='',times='TEST 08:00',status='active')))
        runtime=Runtime(data);assert runtime.ready.wait(5)
        w=ProductWindow(runtime=runtime,backend=ProductBackend(data));w.resize(args.width,args.height);w.show()
        def settle():
            loop=QEventLoop();timer=QTimer();timer.setInterval(20)
            timer.timeout.connect(lambda:loop.quit() if w.snapshot and not w.pending and not w.legacy.busy else None)
            timer.start();QTimer.singleShot(20000,loop.quit);loop.exec();timer.stop();app.processEvents()
            assert w.snapshot and not w.pending and not w.legacy.busy
        def capture(name):
            app.processEvents();assert w.grab().save(str(out/(name+'.png')))
        try:
            settle()
            w.legacy.source_kind.setCurrentIndex(w.legacy.source_kind.findData('SYNTHETIC'))
            w.legacy.usage.setCurrentIndex(w.legacy.usage.findData('TEST'));settle()
            w._request('snapshot');settle()
            w._request('health.record',dict(metric='weight',value=62,visibility='private'));settle()
            w._send_chat('TEST 今天感觉有点疲劳');settle()
            palette=QPalette(app.palette())
            if args.theme=='high-contrast':
                for role,color in ((QPalette.Window,'black'),(QPalette.Base,'black'),(QPalette.Text,'white'),(QPalette.Highlight,'yellow'),(QPalette.HighlightedText,'black')):palette.setColor(role,QColor(color))
            w.product_theme.apply(args.theme,palette)
            results={}
            pages=('home','assistant','rehab','health','medication','family','history','notifications','settings') if args.phase=='ux-audit' else ('home','assistant','rehab','health','medication') if args.phase=='module-paths' else ('home','assistant','rehab')
            for key in pages:
                w.navigate(key);settle();capture(key)
                assert (w.width(),w.height())==(args.width,args.height),(key,w.size())
                results[key]=dict(platform=app.platformName(),size=[w.width(),w.height()],dpr=w.devicePixelRatioF(),
                                  horizontalOverflow=w.page_widgets[key].horizontalScrollBar().maximum() if key!='rehab' else 0)
                if args.phase=='ux-audit':
                    assert results[key]['horizontalOverflow']==0,(key,results[key])
                    results[key]['font']=w.title.font().family() if hasattr(w,'title') else w.greeting.font().family()
                    if key not in ('assistant','rehab'):
                        tabs=w.page_widgets[key].findChildren(QTabWidget)
                        if tabs:
                            for index in range(tabs[0].count()):
                                QTest.mouseClick(tabs[0].tabBar(),Qt.LeftButton,pos=tabs[0].tabBar().tabRect(index).center());settle();capture(key+'-tab'+str(index))
                            tabs[0].setCurrentIndex(0)
                if key=='assistant':
                    viewport=w.page_widgets[key].viewport()
                    results[key]['modules']={}
                    for section in ('conversation','voice','materials','reference'):
                        w.assistant_module_buttons[section].click();app.processEvents()
                        capture('assistant-'+section)
                        observation=dict(horizontalOverflow=w.page_widgets[key].horizontalScrollBar().maximum(),
                            verticalOverflow=w.page_widgets[key].verticalScrollBar().maximum())
                        assert observation['horizontalOverflow']==0,(section,observation)
                        if section=='conversation':
                            point=w.chat_send.mapTo(viewport,w.chat_send.rect().bottomRight())
                            observation['composerVisible']=viewport.rect().contains(point)
                            assert observation['composerVisible'],(point,viewport.size())
                        results[key]['modules'][section]=observation
                        w._assistant_back();app.processEvents()
                if key=='rehab':
                    for index in range(w.rehab_tabs.count()):
                        w.rehab_tabs.setCurrentIndex(index);settle();capture('rehab-'+str(index))
                    w.rehab_tabs.setCurrentIndex(0);w.interface_buttons['rehabOverview'].click();settle();capture('rehab-workspace')
                    results[key]['workspace']=dict(horizontalOverflow=w.rehab_workspace.horizontalScrollBar().maximum(),verticalOverflow=w.rehab_workspace.verticalScrollBar().maximum(),backVisible=w.interface_buttons['rehabWorkspaceBack'].isVisible())
                    if args.phase in ('module-paths','ux-audit'):
                        w.interface_buttons['rehabWorkspaceBack'].click();app.processEvents()
                        assert w.rehab_tabs.isVisible() and not w.legacy.isVisible()
                if key=='health':
                    assert not w.metrics.isVisible()
                    w.interface_buttons['healthMetricsEntry'].click();app.processEvents();capture('health-metrics')
                    assert w.metrics.isVisible()
                    w.interface_buttons['healthMetricsBack'].click();app.processEvents()
                    assert w.twin_text.isVisible() and not w.metrics.isVisible()
                if key=='medication':
                    assert not w.interface_buttons['medConfirm'].isVisible()
                    w.interface_buttons['medTodayActions'].click();app.processEvents();capture('medication-actions')
                    assert w.interface_buttons['medConfirm'].isVisible()
                    w.interface_buttons['medTodayActionsBack'].click();app.processEvents()
                    assert w.today_medications.isVisible()
            w._open_global_assistant();capture('global-assistant');w.assistant_dock.close()
            if args.phase=='ux-audit':
                w.navigate('assistant');settle();w.assistant_module_buttons['conversation'].click();app.processEvents()
                if w.record_disclosure.isVisible():
                    QTest.mouseClick(w.record_disclosure,Qt.LeftButton);app.processEvents();assert w.record_dialog.grab().save(str(out/'record-review.png'))
                    QTest.keyClick(w.record_dialog,Qt.Key_Escape);app.processEvents();assert not w.record_dialog.isVisible()
                    w.chat_input.setFocus(Qt.TabFocusReason);capture('keyboard-focus');assert w.chat_input.hasFocus()
                QTest.mouseMove(w.chat_send,w.chat_send.rect().center());app.processEvents();capture('hover')
                w._request('snapshot');capture('loading');settle()
            w.navigate('assistant');settle()
            w.assistant_module_buttons['conversation'].click();app.processEvents()
            # Actual ProductService validation failure; no simulated network response.
            w._request('health.record',dict(metric='missing',value=1));settle();capture('error')
            (out/'observations.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
            (out/'button-audit.json').write_text(json.dumps(w.button_audit(),ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(dict(output=str(out),observations=results),ensure_ascii=True))
        finally:
            w.legacy._allow_close=True;w.close();app.processEvents()
            if runtime.thread.is_alive():runtime.command('shutdown');runtime.thread.join(10)


if __name__=='__main__':main()
