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
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT.parent)]
from PySide6.QtCore import QEventLoop,QTimer
from PySide6.QtGui import QFont,QFontDatabase
from PySide6.QtWidgets import QApplication
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
    parser.add_argument('--theme',choices=('light','dark'),default='light')
    args=parser.parse_args()
    factor=os.environ.get('QT_SCALE_FACTOR','auto')
    platform=os.environ['QT_QPA_PLATFORM']
    out=ROOT/'qa-output'/'fluent-v1'/f'{platform}-{args.theme}-{args.width}x{args.height}-scale{factor}'
    out.mkdir(parents=True,exist_ok=True)
    app=QApplication([])
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
            w.product_theme.apply(args.theme)
            results={}
            for key in ('home','assistant','rehab'):
                w.navigate(key);settle();capture(key)
                assert (w.width(),w.height())==(args.width,args.height),(key,w.size())
                results[key]=dict(platform=app.platformName(),size=[w.width(),w.height()],dpr=w.devicePixelRatioF(),
                                  horizontalOverflow=w.page_widgets[key].horizontalScrollBar().maximum() if key!='rehab' else w.rehab_workspace.horizontalScrollBar().maximum())
                if key=='assistant':
                    viewport=w.page_widgets[key].viewport()
                    point=w.chat_send.mapTo(viewport,w.chat_send.rect().bottomRight())
                    results[key]['composerVisible']=viewport.rect().contains(point)
                    assert results[key]['composerVisible'],(point,viewport.size())
                if key=='rehab':
                    for index in range(w.rehab_tabs.count()):
                        w.rehab_tabs.setCurrentIndex(index);settle();capture('rehab-'+str(index))
                    w.rehab_tabs.setCurrentIndex(0);w.interface_buttons['rehabOverview'].click();settle();capture('rehab-workspace')
            w._open_global_assistant();capture('global-assistant');w.assistant_dock.close()
            w.navigate('assistant');settle()
            # Actual ProductService validation failure; no simulated network response.
            w._request('health.record',dict(metric='missing',value=1));settle();capture('error')
            (out/'observations.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
            (out/'button-audit.json').write_text(json.dumps(w.button_audit(),ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(dict(output=str(out),observations=results),ensure_ascii=True))
        finally:
            w.legacy._allow_close=True;w.close();app.processEvents()
            if runtime.thread.is_alive():runtime.command('shutdown');runtime.thread.join(10)


if __name__=='__main__':main()
