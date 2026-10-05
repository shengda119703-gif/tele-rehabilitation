"""Visible native polish review, including minimum window and inner panes.

Only isolated TEST profiles; no camera/ASR/LLM. QT_SCALE_FACTOR may be supplied.
"""
import os
os.environ['QT_QPA_PLATFORM']='windows'
import sys,json,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tests'),str(ROOT),str(ROOT.parent)]
import pytest
from PySide6.QtCore import Qt,QPoint,qVersion,qInstallMessageHandler
from PySide6.QtGui import QPalette,QColor
from PySide6.QtWidgets import QScrollArea,QLabel
from PySide6.QtTest import QTest
from test_product_window import desktop,wait
from app.ui.product_motion import reduced_motion

out=ROOT/'qa-output'/('polish-detail-'+os.environ.get('POLISH_RUN','default'))
out.mkdir(parents=True,exist_ok=True)
notes=[];messages=[]
previous=qInstallMessageHandler(lambda kind,context,message:messages.append(str(message)))
try:
    with tempfile.TemporaryDirectory(prefix='polish-TEST-') as td:
        patch=pytest.MonkeyPatch();gen=desktop.__wrapped__(Path(td),patch);w,app=next(gen)
        try:
            w.resize(1024,720)
            def capture(name):
                QTest.qWait(350);app.processEvents()
                assert w.grab().save(str(out/(name+'.png')))
                page=w.page_widgets[w.active_page]
                overflow=page.horizontalScrollBar().maximum() if isinstance(page,QScrollArea) else 0
                notes.append(dict(state=name,page=w.active_page,dpr=w.devicePixelRatioF(),qt=qVersion(),platform=app.platformName(),horizontal=overflow,vertical=page.verticalScrollBar().maximum() if isinstance(page,QScrollArea) else 0))
                assert overflow==0,(name,overflow)
                if w.active_page=='settings':
                    for text in w.settings_tabs.currentWidget().findChildren(QLabel):
                        if text.isVisible() and text.wordWrap() and text.text():
                            assert text.height()>=text.heightForWidth(text.width()),(name,text.text(),text.size())
            for theme in ('light','dark'):
                w.product_theme.apply(theme)
                for key in ('home','rehab','health','medication','family','assistant'):
                    w.navigate(key);wait(app,lambda:not w.pending);capture(theme+'-'+key)
                for key,tabs in (('health',w.health_tabs),('medication',w.medication_tabs),('settings',w.settings_tabs)):
                    w.navigate(key);wait(app,lambda:not w.pending)
                    for i in range(tabs.count()):
                        if not tabs.isTabVisible(i):continue
                        tabs.setCurrentIndex(i);capture(theme+'-'+key+'-pane'+str(i))
                w.navigate('health');wait(app,lambda:not w.pending)
                bar=w.health_tabs.tabBar();bar.setFocus(Qt.TabFocusReason)
                bar.setCurrentIndex(0);QTest.keyClick(bar,Qt.Key_Right)
                assert w.health_tabs.currentIndex()==1;capture(theme+'-tab-keyboard')
                w.navigate('rehab');wait(app,lambda:not w.pending)
                day=w.rehab_day;day.setFocus();QTest.mouseClick(day,Qt.LeftButton,pos=day.rect().topRight()+QPoint(-12,day.height()//2))
                QTest.qWait(100)
                popup=app.activePopupWidget()
                assert popup,'Calendar arrow must open native date popup'
                popup.grab().save(str(out/(theme+'-calendar.png')))
                QTest.keyClick(popup,Qt.Key_Escape)
            w.navigate('health');wait(app,lambda:not w.pending);bar=w.health_tabs.tabBar()
            bar.setCurrentIndex(0);QTest.qWait(350);bar.setCurrentIndex(2)
            QTest.qWait(70)
            if not reduced_motion():assert bar._thumb!=bar._destination(),'Pane layout must preserve selection travel'
            bar.grab().save(str(out/'segment-travel.png'))
            QTest.qWait(300);bar.grab().save(str(out/'segment-settled.png'))
            palette=QPalette();palette.setColor(QPalette.Window,QColor('black'));palette.setColor(QPalette.Base,QColor('black'))
            for role in (QPalette.Text,QPalette.WindowText):palette.setColor(role,QColor('white'))
            palette.setColor(QPalette.Highlight,QColor('yellow'));palette.setColor(QPalette.HighlightedText,QColor('black'))
            w.product_theme.apply('high-contrast',palette);w.navigate('health');wait(app,lambda:not w.pending);capture('contrast-health')
        finally:
            try:next(gen)
            except StopIteration:pass
            patch.undo()
finally:
    qInstallMessageHandler(previous)
    (out/'observations.json').write_text(json.dumps(dict(captures=notes,qtMessages=messages),ensure_ascii=False,indent=2),encoding='utf-8')
print('PASS',len(notes),'main states;',len(messages),'Qt messages; output',out)
