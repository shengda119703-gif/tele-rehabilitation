"""Visible native rehabilitation audit, using an isolated TEST bridge and no camera."""
import os, sys, tempfile, json, argparse
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='windows'
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tests'),str(ROOT),str(ROOT.parent)]
import pytest, PySide6
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from test_product_window import desktop, wait
from test_product_rehab_focus import plan
parser=argparse.ArgumentParser();parser.add_argument('--stage',required=True);args=parser.parse_args()
out=ROOT/'qa-output/rehab-focus'/args.stage;out.mkdir(parents=True,exist_ok=True)
observations=[]
for width,theme in [(1440,'light'),(1024,'light'),(1440,'dark'),(1024,'dark')]:
 with tempfile.TemporaryDirectory(prefix='rehab-focus-TEST-') as td:
  patch=pytest.MonkeyPatch();gen=desktop.__wrapped__(Path(td),patch);w,app=next(gen)
  try:
   w.resize(width,940);w.product_theme.apply(theme);w.navigate('rehab');wait(app,lambda:not w.pending)
   def capture(state,settle=True):
    if settle:QTest.qWait(120)
    scroll=w.rehab_tabs.currentWidget()
    assert not scroll.horizontalScrollBar().maximum(),state
    w.grab().save(str(out/f'{width}-{theme}-{state}.png'))
    observations.append(dict(width=width,theme=theme,state=state,qt=PySide6.__version__,dpr=w.devicePixelRatioF()))
   capture('empty')
   for i in range(1,4):w.rehab_tabs.setCurrentIndex(i);capture(f'tab-{i}')
   w.rehab_tabs.setCurrentIndex(0)
   w.interface_buttons['rehabContinue'].setFocus(Qt.TabFocusReason)
   QTest.mouseMove(w.interface_buttons['rehabContinue']);capture('focus-hover')
   QTest.keyClick(w.interface_buttons['rehabContinue'],Qt.Key_Space);QTest.qWait(100)
   assert w.rehab_workspace.isVisible();w.interface_buttons['rehabWorkspaceBack'].click();wait(app,lambda:not w.pending)
   assert w.rehab_tabs.isVisible()
   w._request('snapshot');assert w.pending;capture('loading',False);wait(app,lambda:not w.pending)
   w._request('health.record',dict(metric='missing',value=1));wait(app,lambda:not w.pending);capture('error')
   if args.stage!='before':
    w._request('snapshot');wait(app,lambda:not w.pending)
    w.notice.clear();w.notice.hide()
    w.page_feedback.pop('rehab',None);w._completion_controls()
    w.refresher.stop();w.rehab_tabs.setCurrentIndex(0)
    for state,p in [('plan',plan()),('unavailable',plan(False)),('complete',plan(done=True))]:
     w.snapshot['rehabilitation_ui']['rehab.get_training_plan']['records']=[p]
     w._completion_render();w._completion_controls();capture(state)
    from datetime import datetime
    record=dict(id='TEST-saved',exercise_label='TEST 肩外展',end_utc=datetime.now().astimezone().isoformat(),
      status='FINISHED',summary=dict(completed=1,plan_completed=True),training_feedback=dict(pain=0,fatigue=0,notes='TEST 保存反馈。'*25))
    w.snapshot['rehabilitation_ui']['rehab.get_training_plan']['records']=[]
    w.snapshot['rehabilitation_ui']['rehab.get_training_history']['records']=[record]
    w._completion_render();w._completion_controls();capture('saved-feedback')
    field=w.recovery_fields['result'];assert field.height()>=field.heightForWidth(field.width())
    w.rehab_tabs.setCurrentIndex(3);capture('record-trend')
   print(f'{width} {theme} PASS',flush=True)
  finally:
   try:next(gen)
   except StopIteration:pass
   patch.undo()
(out/'observations.json').write_text(json.dumps(observations,ensure_ascii=False,indent=2),encoding='utf-8')
