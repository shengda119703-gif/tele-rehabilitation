"""Visible-control acceptance of the real Qt product with isolated TEST storage.

Setup seeds data through existing services. Acceptance uses visible text, widget
events, screenshots and persisted UI after reopening, not controller state.
"""
import os,sys,tempfile,json,argparse,time
from pathlib import Path
from datetime import date
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'rehab_codex_single_camera_v2_1'),str(ROOT)]
os.environ['QT_QPA_PLATFORM']='windows'
os.environ['ANKANG_VOICE_DISABLED']='1'
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont,QFontDatabase
from PySide6.QtWidgets import QApplication,QPushButton,QToolButton,QLabel,QTabWidget,QScrollArea,QPlainTextEdit,QCheckBox,QTextBrowser
from PySide6.QtTest import QTest
from app.runtime import Runtime
from app.ui.product_window import ProductWindow
from app.product.backend import ProductBackend
from app.ui.product_dialogs import blank_health
from bridges.ankang.client import AgentBridge

p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--width',type=int,default=1440);p.add_argument('--theme',default='light');p.add_argument('--home-only',action='store_true');args=p.parse_args()
args.out.mkdir(parents=True,exist_ok=True)
app=QApplication([])
for font in ('msyh.ttc','msyhbd.ttc'):QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+font)
app.setFont(QFont('Microsoft YaHei UI',10))
results=[]
def wait(predicate,timeout=25):
    until=time.monotonic()+timeout
    while time.monotonic()<until:
        app.processEvents();QTest.qWait(35)
        if predicate():QTest.qWait(400);return
    raise AssertionError('Visible result did not arrive')
def text():
    return '\n'.join(x.text() for x in w.findChildren(QLabel) if x.isVisible())+'\n'+'\n'.join(x.toPlainText() for x in w.findChildren(QTextBrowser) if x.isVisible())
def click(caption):
    buttons=[b for typ in (QPushButton,QToolButton) for b in w.findChildren(typ) if b.isVisible() and b.text()==caption]
    assert buttons,caption
    b=buttons[0];wait(lambda:b.isEnabled())
    parent=b.parentWidget()
    while parent:
        if isinstance(parent,QScrollArea):parent.ensureWidgetVisible(b)
        parent=parent.parentWidget()
    QTest.mouseClick(b,Qt.LeftButton);QTest.qWait(450);app.processEvents()
def capture(name):
    if name!='FAIL':wait(lambda:'正在读取 / 保存' not in text(),timeout=60)
    app.processEvents();w.grab().save(str(args.out/(name+'.png')))
    if name.startswith('home') and w.home_attention.isVisible():
        assert w.home_schedule.geometry().bottom()<w.home_attention.geometry().top(),'Schedule overlaps task feedback'
    overflow=[s.objectName() for s in w.findChildren(QScrollArea) if s.isVisible() and s.horizontalScrollBar().maximum()>0]
    assert not overflow,(name,overflow)
def tab(caption):
    for tabs in w.findChildren(QTabWidget):
        if not tabs.isVisible() or not tabs.tabBar().isVisible():continue
        for i in range(tabs.count()):
            if tabs.tabText(i)==caption:
                QTest.mouseClick(tabs.tabBar(),Qt.LeftButton,pos=tabs.tabBar().tabRect(i).center());QTest.qWait(450);return
    raise AssertionError('Missing tab '+caption)
with tempfile.TemporaryDirectory(prefix='ankang-BLACKBOX-TEST-') as folder:
    data=Path(folder)
    with AgentBridge(data_dir=data/'product') as bridge:
        profile=blank_health('TEST 林女士');profile['age']=68
        bridge.product('profile.save','blackbox-test',dict(profile=profile,rehabGoal='TEST 日常活动'))
        bridge.product('medication.save','blackbox-test',dict(record=dict(id='test-med',name='TEST 医嘱药物',dose='按既有医嘱',purpose='',times='08:00 / 20:00',status='active')))
    backend=ProductBackend(data)
    backend.call('daily.medSchedule','blackbox-test',dict(medId='test-med',times=['08:00','20:00'],start=date.today().isoformat(),end=''))
    backend.call('health.record','blackbox-test',dict(metric='weight',value=62,visibility='private'))
    runtime=Runtime(data);assert runtime.ready.wait(10)
    w=ProductWindow(runtime=runtime,backend=backend);w.resize(args.width,940);w.show();w.product_theme.apply(args.theme)
    try:
        wait(lambda:'林女士' in text(),timeout=90);capture('home')
        if args.home_only:
            diagnostics=[];item=w.home_schedule
            while item:
                diagnostics.append(dict(type=type(item).__name__,name=item.objectName(),rect=item.geometry().getRect(),minimum=item.minimumSize().toTuple(),maximum=item.maximumSize().toTuple(),hint=item.sizeHint().toTuple(),minhint=item.minimumSizeHint().toTuple()))
                item=item.parentWidget()
            (args.out/'layout.json').write_text(json.dumps(diagnostics,indent=2));sys.exit(0)
        click('查看本周周报');wait(lambda:'身体数据这一周' in text());capture('weekly-report');click('返回首页')
        click('全部记录');capture('records')
        assert any(t.isVisible() and t.tabText(t.currentIndex())=='统一历史' for t in w.findChildren(QTabWidget)),'Records entry did not select timeline'
        click('返回首页')
        results.append(dict(flow='首页 → 周报 / 全部记录 → 返回',status='PASS'))
        click('康复');capture('rehab-training');click('去做评估');capture('rehab-assessment');tab('健身');capture('rehab-fitness');tab('训练')
        click('管理计划与日期');capture('plan-management');click('收起计划管理')
        results.append(dict(flow='康复三入口及计划管理展开/收起',status='PASS'))
        click('健康');capture('health');tab('身体记录');capture('health-records');tab('资料与图片');capture('health-documents');tab('我的档案')
        click('查看 / 记录健康指标');capture('health-metrics');click('返回当前健康状态')
        results.append(dict(flow='健康档案 / 指标 / 资料导航',status='PASS'))
        click('用药');wait(lambda:'正在读取 / 保存' not in text());capture('medication')
        from PySide6.QtWidgets import QTableWidget
        table=next(t for t in w.findChildren(QTableWidget) if t.isVisible() and t.rowCount() and t.columnCount()==4 and t.item(0,1) and '医嘱药物' in t.item(0,1).text())
        QTest.mouseClick(table.viewport(),Qt.LeftButton,pos=table.visualItemRect(table.item(0,0)).center());click('已服用')
        wait(lambda:any(t.item(0,3) and t.item(0,3).text()=='已服用' for t in w.findChildren(QTableWidget) if t.isVisible() and t.rowCount() and t.columnCount()==4))
        capture('dose-saved');click('首页');click('用药');capture('dose-revisited')
        results.append(dict(flow='逐次服药 → 保存反馈 → 跨页返回保留',status='PASS'))
        click('家庭');capture('family');click('首页');click('和康复管家聊聊');capture('assistant')
        click('连接与能力');capture('assistant-capability')
        results.append(dict(flow='联网模型对话',status='BLOCKED' if '尚未配置' in text() else 'NOT_TESTED',reason='本机无模型配置；不发送个人数据，不伪造 API 成功'))
        draft=next(x for x in w.findChildren(QPlainTextEdit) if x.isVisible() and not x.isReadOnly())
        draft.setFocus();app.clipboard().setText('我今天体重63公斤');QTest.keyClick(draft,Qt.Key_V,Qt.ControlModifier);click('发送')
        wait(lambda:'63' in text() and '正在读取 / 保存' not in text(),timeout=40);capture('assistant-response')
        results.append(dict(flow='真实界面文字输入/发送/回复',status='PASS'))
        click('健康');wait(lambda:'63' in text());capture('health-chat-record');click('首页');capture('home-return')
    except Exception as error:
        capture('FAIL');results.append(dict(flow='acceptance',status='FAIL',reason=str(error)));raise
    finally:
        (args.out/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
        w.legacy._allow_close=True;w.close();app.processEvents()
        if runtime.thread.is_alive():runtime.command('shutdown');runtime.thread.join(10)
        print(json.dumps(results,ensure_ascii=True))
