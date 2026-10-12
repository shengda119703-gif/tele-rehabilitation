"""Current five-page UI: real QTest input, isolated data, no private callbacks."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--platform',default='offscreen',choices=('windows','offscreen'));a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    os.environ['QT_QPA_PLATFORM']=a.platform
    os.environ['ANKANG_PRODUCT_DISABLE_MODEL']='1';os.environ['ANKANG_VOICE_DISABLED']='1'
    config=tempfile.TemporaryDirectory(prefix='desktop-qa-config-');data=tempfile.TemporaryDirectory(prefix='desktop-qa-data-')
    os.environ['APPDATA']=config.name
    root=Path(__file__).resolve().parents[2];sys.path[:0]=[str(root),str(root/'rehab_codex_single_camera_v2_1')]
    from PySide6.QtCore import Qt,QTimer
    from PySide6.QtGui import QFont,QFontDatabase
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication,QAbstractButton,QDialog,QLabel,QLineEdit,QSpinBox,QTabWidget,QPlainTextEdit
    from app.ui.product_window import ProductWindow
    app=QApplication([])
    font_id=QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc')
    families=QFontDatabase.applicationFontFamilies(font_id)
    if families:app.setFont(QFont(families[0],10))
    w=ProductWindow(data_dir=Path(data.name));w.resize(1280,900);w.show()
    cases=[];inventory=[]
    def pump(ms=100):
        QTest.qWait(ms);app.processEvents()
    def wait(fn,seconds=30):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            if fn():return
            pump()
        raise AssertionError('visible state not ready')
    def texts(parent=w):
        return '\n'.join(x.text() for x in parent.findChildren(QLabel) if x.isVisible())
    def button(title,parent=w):
        matches=[b for b in parent.findChildren(QAbstractButton) if b.isVisible() and
                 (b.text().replace('&','')==title or title=='我的档案' and b.text().endswith('· 我的档案'))]
        assert matches,'missing visible button '+title
        return matches[0]
    def click(title,parent=w):
        b=button(title,parent);wait(lambda:b.isEnabled(),seconds=60)
        QTest.mouseClick(b,Qt.LeftButton);pump(300)
    def case(name,fn):
        try:fn();status='PASS';detail='real visible UI checks passed'
        except Exception as error:status='FAIL';detail=repr(error)
        cases.append(dict(name=name,status=status,detail=detail))
        w.grab().save(str(a.output/f'{len(cases):02d}.png'))
        (a.output/f'{len(cases):02d}.txt').write_text(texts(),encoding='utf-8')
        print(json.dumps(cases[-1],ensure_ascii=False),flush=True)
    def onboarding():
        wait(lambda:any(d.isVisible() and d.objectName()=='firstUse' for d in app.topLevelWidgets()))
        d=next(d for d in app.topLevelWidgets() if isinstance(d,QDialog) and d.isVisible() and d.objectName()=='firstUse')
        click('完成建档',d);assert '请填写称呼' in texts(d)
        field=d.findChild(QLineEdit);field.setFocus();QTest.keyClicks(field,'TEST Desktop QA')
        age=d.findChild(QSpinBox);age.setFocus();QTest.keyClick(age,Qt.Key_A,Qt.ControlModifier);QTest.keyClicks(age,'65')
        click('完成建档',d)
        wait(lambda:not any(d.isVisible() and isinstance(d,QDialog) for d in app.topLevelWidgets()))
        wait(lambda:'TEST Desktop QA' in texts())
        wait(lambda:'正在读取 / 保存' not in texts(),seconds=60)
        wait(lambda:'档案与首次评估安排已保存' in texts(),seconds=60)
        assert '安排' in texts()
    case('首次建档：空名称验证、真实提交、首页刷新',onboarding)
    for title in ('首页','康复','健康','用药','家庭'):
        def page(title=title):
            marker={'首页':'今天的安排','康复':'今天的康复','健康':'健康','用药':'用药','家庭':'家人的近况'}[title]
            # The initial original-runtime profile save has its own busy state.
            # Reattempt visible navigation after that bounded operation completes.
            for attempt in range(30):
                click(title);pump(1000)
                if marker in texts():break
            assert marker in texts(),'navigation did not reach '+title
            wait(lambda:'正在读取 / 保存' not in texts(),seconds=60)
            buttons=[{'text':b.text(),'enabled':b.isEnabled(),'actionId':b.property('actionId')} for b in w.findChildren(QAbstractButton) if b.isVisible()]
            inventory.append({'page':title,'buttons':buttons})
        case('五页导航 '+title,page)
    def family():
        click('家庭');click('生成我的邀请码');pump(2000)
        assert '邀请码' in texts()
        assert '尚未关联家人' in texts()
    case('家庭未绑定保护与真实邀请码',family)
    def assistant():
        click('首页');click('和康复管家聊聊');pump(1000)
        field=next(f for f in w.findChildren(QPlainTextEdit) if f.isVisible())
        field.setFocus();QTest.keyClicks(field,'Hello TEST ordinary chat')
        from PySide6.QtWidgets import QTextBrowser
        def transcript():
            return '\n'.join(f.toPlainText() for f in w.findChildren(QTextBrowser) if f.isVisible())+texts()
        click('发送');wait(lambda:'本地回复' in transcript(),seconds=60)
        content=transcript()
        assert 'Hello TEST ordinary chat' in content
        assert '本地回复' in content
    case('管家真实发送与未配置来源提示',assistant)
    def settings():
        wait(lambda:'正在读取' not in texts(),seconds=60)
        errors=[]
        def choose():
            try:
                d=app.activeModalWidget() or next((d for d in app.topLevelWidgets() if isinstance(d,QDialog) and d.isVisible()),None)
                assert isinstance(d,QDialog),'account modal did not open'
                click('设置与数据管理',d)
            except Exception as error:
                errors.append(repr(error))
                if app.activeModalWidget():QTest.keyClick(app.activeModalWidget(),Qt.Key_Escape)
        QTimer.singleShot(500,choose);click('我的档案');pump(1000)
        assert not errors,errors
        assert '设置' in texts()
    case('我的档案进入设置与数据管理',settings)
    for title in ('首页','康复','健康','用药','家庭'):
        def tabs(title=title):
            click(title);pump(500)
            for tab in w.findChildren(QTabWidget):
                if not tab.isVisible():continue
                for i in range(tab.count()):
                    if not tab.isTabVisible(i):continue
                    QTest.mouseClick(tab.tabBar(),Qt.LeftButton,pos=tab.tabBar().tabRect(i).center());pump(200)
                    inventory.append({'page':title,'tab':tab.tabText(i),'labels':texts()[:3000]})
        case('可见子页面遍历 '+title,tabs)
    result={'cases':cases,'counts':{s:sum(c['status']==s for c in cases) for s in ('PASS','FAIL')},
            'inventory':inventory,'fontFamilies':families,'platform':a.platform,'dataPath':data.name,
            'scope':'visible QTest only; no camera/microphone/model requests'}
    (a.output/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    w.close();pump(2000);config.cleanup();data.cleanup()
    return int(result['counts']['FAIL']>0)


if __name__=='__main__':raise SystemExit(main())
