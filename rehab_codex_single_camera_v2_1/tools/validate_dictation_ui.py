"""Visible Qt dictation interaction audit. Synthetic voice, real product bridge; no microphone."""
import os, sys, tempfile, threading, json
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','windows')
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tests'),str(ROOT),str(ROOT.parent)]
import pytest
from test_product_window import desktop, wait
from app.product.native_voice import NativeVoiceHost
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

class AuditVoice(NativeVoiceHost):
    def __init__(self):
        super().__init__();self.release=threading.Event();self.failure=False
        self.state.update(available=True,phase='idle',outputAvailable=False,detail='TEST 隔离语音宿主')
    def status(self):return self.live_status()
    def handle(self,name,args):
        self.state.update(phase='recording',elapsed=3,level=.42)
        try:
            while not self.finished.wait(.01):self._check_cancelled()
            self._check_cancelled();self.state.update(phase='transcribing',level=0)
            while not self.release.wait(.01):self._check_cancelled()
            self._check_cancelled()
            if self.failure:raise RuntimeError('TEST 无法识别语音')
            return {'text':'TEST 今天走路有些累，想记录下来。'}
        finally:self.state['phase']='idle'

out=ROOT/'qa-output/dictation-ui';out.mkdir(parents=True,exist_ok=True)
observations=[]
for width,theme in [(1024,'light'),(1440,'dark')]:
    with tempfile.TemporaryDirectory(prefix='dictation-test-') as td:
        patch=pytest.MonkeyPatch();gen=desktop.__wrapped__(Path(td),patch);w,app=next(gen)
        try:
            w.resize(width,720 if width==1024 else 940);w.product_theme.apply(theme)
            host=AuditVoice();w.backend.voice=host;w.backend.bridge.voice_host=host
            w._request('extensions.status');wait(app,lambda:not w.pending)
            w.navigate('assistant');wait(app,lambda:not w.pending)
            def capture(state):
                QTest.qWait(150);view=w.page_widgets['assistant'].viewport()
                w.grab().save(str(out/f'{width}-{theme}-{state}.png'))
                print(state,view.height(),w.page_widgets['assistant'].widget().height(),w.chat.height(),w.chat_send.mapTo(view,w.chat_send.rect().bottomRight()).y(),flush=True)
                assert w.page_widgets['assistant'].horizontalScrollBar().maximum()==0
                if w.assistant_sections.currentWidget() is w.assistant_views['conversation']:
                    assert view.rect().contains(w.chat_send.mapTo(view,w.chat_send.rect().bottomRight())),state
                w.grab().save(str(out/f'{width}-{theme}-{state}.png'))
                observations.append({'width':width,'theme':theme,'state':state,'horizontalOverflow':0})
            capture('ready')
            w.chat_input.setPlainText('TEST 已有草稿')
            mic=w.interface_buttons['assistantVoiceEntry']
            QTest.mouseClick(mic,Qt.LeftButton);wait(app,lambda:host.state['phase']=='recording')
            assert w.assistant_sections.currentWidget() is w.assistant_views['conversation']
            capture('recording')
            QTest.mouseClick(mic,Qt.LeftButton);wait(app,lambda:host.state['phase']=='transcribing')
            capture('transcribing')
            host.release.set();wait(app,lambda:not w.pending)
            assert not w.snapshot['state']['chat'] and not w.snapshot['state']['events']
            assert w.chat_input.toPlainText().startswith('TEST 已有草稿')
            capture('draft')
            w.private_turn.setChecked(True);QTest.mouseClick(w.chat_send,Qt.LeftButton);wait(app,lambda:not w.pending)
            assert not w.snapshot['state']['events'] and '今天走路' in w.chat.toPlainText()
            capture('sent')
            w.chat_input.setPlainText('TEST 取消后保留');host.release.clear()
            QTest.mouseClick(mic,Qt.LeftButton);wait(app,lambda:host.state['phase']=='recording')
            QTest.mouseClick(w.dictation_cancel,Qt.LeftButton);wait(app,lambda:not w.pending)
            assert w.chat_input.toPlainText()=='TEST 取消后保留';capture('cancelled')
            host.failure=True;host.release.set()
            QTest.mouseClick(mic,Qt.LeftButton);wait(app,lambda:host.state['phase']=='recording')
            QTest.mouseClick(mic,Qt.LeftButton);wait(app,lambda:not w.pending)
            assert '无法识别' in w.dictation_status.text();capture('error')
            QTest.mouseClick(w.interface_buttons['assistantVoiceSettings'],Qt.LeftButton);capture('voice-page')
        finally:
            try:next(gen)
            except StopIteration:pass
            patch.undo()
(out/'observations.json').write_text(json.dumps(observations,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'states':len(observations),'output':str(out),'result':'PASS'},ensure_ascii=False))
