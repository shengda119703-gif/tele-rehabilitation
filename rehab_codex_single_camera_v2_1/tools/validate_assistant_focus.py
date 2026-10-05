"""Native assistant presentation audit with isolated TEST data and the real bridge."""
import argparse,json,os,sys,tempfile
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','windows')
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tests'),str(ROOT),str(ROOT.parent)]
import pytest,PySide6
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from test_product_window import desktop,wait
parser=argparse.ArgumentParser();parser.add_argument('--stage',required=True);args=parser.parse_args()
out=ROOT/'qa-output/assistant-focus'/args.stage;out.mkdir(parents=True,exist_ok=True)
observations=[]
for width,theme in [(1440,'light'),(1024,'light'),(1440,'dark'),(1024,'dark')]:
 with tempfile.TemporaryDirectory(prefix='assistant-focus-') as td:
  patch=pytest.MonkeyPatch();gen=desktop.__wrapped__(Path(td),patch);w,app=next(gen)
  try:
   w.resize(width,940);w.product_theme.apply(theme)
   w.navigate('assistant');wait(app,lambda:not w.pending)
   def capture(state,settle=True):
    if settle:QTest.qWait(100)
    view=w.page_widgets['assistant'].viewport()
    assert not w.page_widgets['assistant'].horizontalScrollBar().maximum()
    assert view.rect().contains(w.chat_send.mapTo(view,w.chat_send.rect().bottomRight())),state
    w.grab().save(str(out/f'{width}-{theme}-{state}.png'))
    observations.append(dict(width=width,theme=theme,state=state,qt=PySide6.__version__,platform=app.platformName(),dpr=w.devicePixelRatioF(),chatHeight=w.chat.height(),composerVisible=True))
   capture('empty')
   w.chat_input.setPlainText('今天收缩压130');QTest.mouseClick(w.chat_send,Qt.LeftButton)
   capture('loading',False);assert not w.chat_send.isEnabled();wait(app,lambda:not w.pending)
   capture('recorded')
   QTest.mouseClick(w.record_disclosure,Qt.LeftButton);QTest.qWait(50)
   assert w.record_dialog.isVisible();QTest.keyClick(w.record_dialog,Qt.Key_Escape);QTest.qWait(50)
   w.chat_input.setFocus(Qt.TabFocusReason);QTest.mouseMove(w.chat_send,w.chat_send.rect().center());capture('focus-hover');assert w.chat_input.hasFocus()
   if hasattr(w,'assistant_status_toggle'):
    w.assistant_status_toggle.setFocus();QTest.keyClick(w.assistant_status_toggle,Qt.Key_Space)
    assert w.agent_status.isVisible();capture('status');QTest.keyClick(w.assistant_status_toggle,Qt.Key_Space)
   w._request('health.record',dict(metric='missing',value=1));wait(app,lambda:not w.pending)
   capture('error');assert w.notice.isVisible() and w.notice.property('fluentStatus')=='danger'
   if args.stage=='after':
    assert not w.interface_buttons['globalAssistant'].isVisible()
    w.navigate('health');wait(app,lambda:not w.pending);assert w.interface_buttons['globalAssistant'].isVisible()
    QTest.mouseClick(w.interface_buttons['globalAssistant'],Qt.LeftButton);assert w.assistant_dock.isVisible();w.assistant_dock.close()
   print(f'{width} {theme} PASS',flush=True)
  finally:
   try:next(gen)
   except StopIteration:pass
   patch.undo()
(out/'observations.json').write_text(json.dumps(observations,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'states':len(observations),'output':str(out)},ensure_ascii=True))
