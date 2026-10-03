"""UI-only exploratory acceptance with the real ProductWindow and both runtimes.

No bridge fixtures, mocked services, dialog return-value patches, private callbacks,
or hidden-widget clicks. QTest supplies mouse/keyboard input to visible Qt widgets.
Outputs distinguish interaction coverage from end-to-end acceptance.
Run in a dedicated process: python tools/validate_product_blackbox.py --output DIR
"""

if __name__ == '__main__':

    import argparse
    import csv
    import json
    import os
    import sys
    import tempfile
    import time
    from collections import Counter
    from pathlib import Path

    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--only', default='')
    args = parser.parse_args()
    OUT = args.output.resolve()
    if (OUT/'data').exists():parser.error('Use a fresh output directory; existing application data is never overwritten.')
    OUT.mkdir(parents=True, exist_ok=True)
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    os.environ['ANKANG_PRODUCT_DISABLE_MODEL'] = '1'
    os.environ['ANKANG_VOICE_DISABLED'] = '1'
    # Developer settings are deliberately outside the checkout and never use a real key.
    private = tempfile.TemporaryDirectory(prefix='rehab-blackbox-config-')
    os.environ['APPDATA'] = private.name
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import Qt, QTimer, QPoint
    from PySide6.QtGui import QFont
    from PySide6.QtTest import QTest, QSignalSpy
    from shiboken6 import isValid
    from PySide6.QtWidgets import (QApplication, QAbstractButton, QComboBox, QTabWidget,
        QLineEdit, QPlainTextEdit, QTextBrowser, QLabel, QScrollArea, QFileDialog,
        QInputDialog, QMessageBox, QDialog, QTableWidget, QFormLayout, QSpinBox,
        QDoubleSpinBox, QCheckBox, QListWidget, QWidget)
    from app.ui.product_window import ProductWindow

    app = QApplication([])
    app.setStyle('Fusion')
    app.setFont(QFont('Microsoft YaHei UI', 10))
    cases, observations, dialogs, button_hits, options = [], {}, [], Counter(), {}
    visible_controls=[]
    selected_options=[]
    clicked_controls=[]
    policy = []
    modal_errors = []
    handling = set()
    window = None


    def texts(root):
        result = []
        for x in root.findChildren(QWidget):
            if isinstance(x,(QLabel, QTextBrowser, QPlainTextEdit)) and x.isVisible():
                result.append(x.text() if isinstance(x, QLabel) else x.toPlainText())
        return '\n'.join(result)


    def pump(ms=100):
        QTest.qWait(ms)
        if modal_errors:
            raise RuntimeError(modal_errors.pop(0))


    def ready(timeout=60):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            pump(80)
            # Only rendered busy indicators are used; no pending/backend internals.
            rendered_busy=any(x.isVisible() and x.text() in ('正在读取 / 保存…','正在读取或保存，请稍候。')
                              for x in window.findChildren(QLabel))
            users=next((c for c in window.findChildren(QComboBox) if c.accessibleName()=='当前产品用户'),None)
            if not rendered_busy and users is not None and users.isEnabled():
                pump(120)
                return
        raise TimeoutError('Rendered busy state did not finish')


    def reveal(widget):
        assert widget.isVisible(), f'hidden: {widget.objectName()} {type(widget).__name__}'
        chain = []
        parent = widget.parentWidget()
        while parent:
            if isinstance(parent, QScrollArea): chain.append(parent)
            parent = parent.parentWidget()
        for scroll in reversed(chain):
            scroll.ensureWidgetVisible(widget)
        pump(25)
        assert widget.visibleRegion().contains(widget.rect().center()), 'click center clipped'


    def click(widget):
        reveal(widget)
        deadline=time.monotonic()+15
        while handling and isValid(widget) and not widget.isEnabled() and time.monotonic()<deadline:pump(80)
        assert widget.isEnabled(), f'disabled: {widget.objectName()}'
        modal=app.activeModalWidget()
        check(not modal or widget.window() is modal,'click is blocked by a visible modal dialog')
        spy=QSignalSpy(widget.clicked)
        key = widget.property('actionId')
        if key: button_hits[str(key)] += 1
        clicked_controls.append(dict(window=widget.window().windowTitle(),caption=widget.text(),name=widget.accessibleName(),id=key))
        if handling and policy:QTimer.singleShot(50,modal_tick)
        pos=QPoint(10,widget.height()//2) if isinstance(widget,QCheckBox) else widget.rect().center()
        QTest.mouseClick(widget, Qt.LeftButton, pos=pos)
        if spy.count()==0 and isValid(widget):
            QTest.keyClick(widget,Qt.Key_Space)
            check(spy.count()>0,'mouse and keyboard did not activate the visible button')
        pump(80)


    def button(text, root=None):
        items = [b for b in (root or app.activeModalWidget() or window).findChildren(QAbstractButton)
                 if b.isVisible() and b.text().replace('&', '') == text]
        assert items, f'visible button missing: {text}'
        return items[0]


    def by_id(key):
        items = [b for b in window.findChildren(QAbstractButton)
                 if b.property('actionId') == key and b.isVisible()]
        assert len(items) == 1, f'visible action {key}: {len(items)}'
        return items[0]


    def action(key):
        ready()
        target=by_id(key)
        deadline=time.monotonic()+60
        while not target.isEnabled() and time.monotonic()<deadline:pump(100)
        click(target);ready();inventory()


    def edit(field, value):
        reveal(field); click_focus(field)
        QTest.keyClick(field, Qt.Key_A, Qt.ControlModifier)
        app.clipboard().setText(str(value))
        QTest.keyClick(field, Qt.Key_V, Qt.ControlModifier)
        pump(30)


    def click_focus(field):
        QTest.mouseClick(field, Qt.LeftButton, pos=field.rect().center())
        pump(20)


    def select(combo, index):
        reveal(combo)
        assert combo.isEnabled() and 0 <= index < combo.count()
        click_focus(combo)
        QTest.keyClick(combo, Qt.Key_Home)
        for _ in range(index): QTest.keyClick(combo, Qt.Key_Down)
        if app.activePopupWidget():QTest.keyClick(app.activePopupWidget(),Qt.Key_Escape)
        pump(30)
        assert combo.currentIndex() == index
        selected_options.append(dict(window=combo.window().windowTitle(),option=combo.currentText()))


    def tab(title, root=None):
        tabs = [t for t in (root or window).findChildren(QTabWidget) if t.isVisible()
                and title in [t.tabText(i) for i in range(t.count())]]
        assert tabs, f'visible tab missing: {title}'
        t = tabs[0]; i = next(i for i in range(t.count()) if t.tabText(i) == title)
        reveal(t.tabBar())
        QTest.mouseClick(t.tabBar(), Qt.LeftButton, pos=t.tabBar().tabRect(i).center())
        pump(); ready(); inventory()
        assert t.currentIndex() == i


    def nav(title):
        click(button(title, window)); ready(); inventory()
        assert window.findChild(QLabel, 'productTitle').text() == title


    def check(condition, explanation):
        assert condition, explanation


    def texts_tables(root):
        parts=[texts(root)]
        for t in root.findChildren(QTableWidget):
            if t.isVisible():
                parts.extend(t.item(r,c).text() for r in range(t.rowCount()) for c in range(t.columnCount()) if t.item(r,c))
        return '\n'.join(parts)


    def select_first_table():
        candidates=[t for t in window.findChildren(QTableWidget) if t.isVisible() and t.rowCount()]
        if candidates:
            t=candidates[0];reveal(t);QTest.mouseClick(t.viewport(),Qt.LeftButton,pos=t.visualItemRect(t.item(0,0)).center());pump(30)


    def record(name, fn):
        if args.only and not name.startswith('01 ') and not any(part in name for part in args.only.split('|')):return
        start = time.monotonic()
        try:
            fn(); status, detail = 'PASS', 'Assertions passed through visible UI'
        except Exception as exc:
            status, detail = 'FAIL', f'{type(exc).__name__}: {exc}'
            (OUT/('failed-'+str(len(cases))+'.txt')).write_text(texts(app.activeModalWidget() or window),encoding='utf-8')
        cases.append(dict(name=name, status=status, detail=detail,
                          seconds=round(time.monotonic()-start, 2)))
        policy.clear()
        modal_errors.clear()
        print(json.dumps(cases[-1], ensure_ascii=False), flush=True)
        write()


    def inventory():
        if not window: return
        title = window.findChild(QLabel, 'productTitle').text()
        for b in window.findChildren(QAbstractButton):
            key = b.property('actionId')
            if key and b.isVisible():
                observations.setdefault(str(key), []).append(dict(page=title, text=b.text(),
                    enabled=b.isEnabled(), reason=b.toolTip()))
        for combo in window.findChildren(QComboBox):
            if combo.isVisible():
                label = combo.accessibleName() or combo.objectName() or '|'.join(combo.itemText(i) for i in range(min(2,combo.count())))
                key = title + '/' + label
                options[key] = [combo.itemText(i) for i in range(combo.count())]


    def write():
        audit = Path(__file__).resolve().parents[2]/'docs/validation/PRODUCT_MODULE_BUTTON_AUDIT_2026-10-03.csv'
        with audit.open(encoding='utf-8-sig') as f: published = list(csv.DictReader(f))
        coverage = []
        for row in published:
            key = row['id']; seen = observations.get(key, [])
            state = ('CLICKED' if button_hits[key] else 'DISABLED_OBSERVED' if seen and all(not x['enabled'] for x in seen)
                     else 'SEEN_NOT_CLICKED' if seen else 'NOT_REACHED')
            coverage.append(dict(id=key, button=row['button'], state=state,
                                 clicks=button_hits[key], observations=seen[-3:]))
        (OUT/'results.json').write_text(json.dumps(dict(cases=cases, counts=dict(Counter(x['status'] for x in cases)),
            button_coverage=coverage, coverage_counts=dict(Counter(x['state'] for x in coverage)),
            options=options, selected_options=selected_options, clicked_controls=clicked_controls, visible_controls=visible_controls, dialogs=dialogs, environment=dict(platform='Qt offscreen QTest',
            model='disabled; real deterministic Runtime/bridge',voice='disabled; native tests separate',
            data=str(OUT/'data'))),ensure_ascii=False,indent=2),encoding='utf-8')


    def modal_tick():
        dlg = app.activeModalWidget() or next((d for d in app.topLevelWidgets() if isinstance(d,QDialog) and d.isVisible()),None)
        if not dlg or dlg in handling:return
        handling.add(dlg)
        visible_controls.extend(dict(window=dlg.windowTitle(),caption=b.text(),enabled=b.isEnabled()) for b in dlg.findChildren(QAbstractButton) if b.isVisible())
        try:
            dialogs.append(dict(title=dlg.windowTitle(), type=type(dlg).__name__, text=texts(dlg)[:2500]))
            choice = policy.pop(0) if policy else dict(kind='cancel')
            kind = choice.get('kind')
            print(json.dumps({'dialog':dlg.windowTitle(),'policy':kind},ensure_ascii=False),flush=True)
            if kind=='flow':
                nested=QTimer();nested.timeout.connect(modal_tick);nested.start(70)
                try:choice['run'](dlg)
                finally:nested.stop()
            elif kind=='input':
                edit(dlg.findChild(QPlainTextEdit) or dlg.findChild(QLineEdit),choice['text'])
                click(next(b for b in dlg.findChildren(QAbstractButton) if b.isVisible() and b.text().replace('&','') in ('OK','确定')))
            elif kind == 'profile':
                # Empty submission must leave the form open with a visible validation error.
                if choice.get('empty'):
                    click(button('保存资料',dlg))
                    check('请填写称呼' in texts(dlg), 'empty profile lacks feedback')
                for title in ('基础资料','康复目标','家庭与用药'):
                    tabs = dlg.findChild(QTabWidget)
                    i = next(i for i in range(tabs.count()) if tabs.tabText(i)==title)
                    QTest.mouseClick(tabs.tabBar(),Qt.LeftButton,pos=tabs.tabBar().tabRect(i).center());pump(20)
                    for form in dlg.findChildren(QFormLayout):
                        for row in range(form.rowCount()):
                            item=form.itemAt(row,QFormLayout.FieldRole); lab=form.itemAt(row,QFormLayout.LabelRole)
                            field=item.widget() if item else None; label=lab.widget().text() if lab and lab.widget() else ''
                            if field and field.isVisible() and label in choice['fields']:
                                value=choice['fields'][label]
                                if isinstance(field,QComboBox):select(field,value)
                                else:edit(field,value)
                click(button('保存资料',dlg))
            elif kind == 'medication':
                if choice.get('empty'):
                    click(button('保存',dlg));check('药物' in texts(dlg),'empty medication validation missing')
                for f in dlg.findChildren(QFormLayout):
                    for row in range(f.rowCount()):
                        field=f.itemAt(row,QFormLayout.FieldRole).widget(); lab=f.itemAt(row,QFormLayout.LabelRole).widget().text()
                        if lab in choice['fields']: edit(field,choice['fields'][lab])
                click(button('保存',dlg))
            elif kind == 'file':
                check(isinstance(dlg,QFileDialog),'expected real Qt file dialog')
                field=dlg.findChild(QLineEdit,'fileNameEdit');edit(field,str(choice['path']))
                click(next(b for b in dlg.findChildren(QAbstractButton) if b.isVisible() and b.isEnabled() and b.text().replace('&','') in ('Open','Save','打开','保存')))
            elif kind == 'category':
                select(dlg.findChild(QComboBox),choice.get('index',5))
                click(next(b for b in dlg.findChildren(QAbstractButton) if b.isVisible() and b.text().replace('&','') in ('OK','确定')))
            elif kind == 'confirm':
                check(isinstance(dlg,QMessageBox),'expected confirmation')
                click(dlg.button(QMessageBox.Yes if choice.get('yes') else QMessageBox.No))
            else:
                if isinstance(dlg,QMessageBox):
                    target=dlg.button(QMessageBox.No) or dlg.button(QMessageBox.Cancel) or dlg.button(QMessageBox.Ok)
                else:
                    target=next((b for b in dlg.findChildren(QAbstractButton) if b.isVisible() and b.text().replace('&','') in ('放弃修改','取消','关闭','返回','返回康复界面','暂不训练','Cancel','Close')),None)
                if target is None:
                    QTest.keyClick(dlg,Qt.Key_Escape);pump(50)
                    check(not dlg.isVisible(),'Escape did not close dialog')
                elif target.isEnabled():click(target)
        except Exception as exc:
            modal_errors.append(f'{type(dlg).__name__}: {exc}')
            try:
                (OUT/('failed-dialog-'+str(len(cases))+'.txt')).write_text(texts_tables(dlg),encoding='utf-8')
                dlg.grab().save(str(OUT/('failed-dialog-'+str(len(cases))+'.png')))
            except RuntimeError:pass
            # Escape is a real user cancellation, never accept()/reject() shortcuts.
            try:QTest.keyClick(dlg,Qt.Key_Escape)
            except RuntimeError:pass
        finally:
            handling.discard(dlg)


    timer=QTimer();timer.timeout.connect(modal_tick);timer.start(70)
    policy.append(dict(kind='profile',empty=True,fields={'称呼':'TEST 黑箱甲','年龄':65,'行动情况':0,
        '康复 / 生活目标':'TEST 日常活动','家庭联系人':'TEST 家属','家属电话':'00000000000'}))
    window=ProductWindow(data_dir=OUT/'data');window.show()


    def startup():
        deadline=time.monotonic()+90
        while 'TEST 黑箱甲' not in texts(window) and time.monotonic()<deadline:pump(100)
        ready();check('TEST 黑箱甲' in texts(window),'profile never appeared');inventory()
        for text in ('今天暂无康复计划','暂无用药安排','今天没有待完成任务','暂无健康记录'):
            check(text in texts(window),'missing empty state: '+text)


    record('01 首次建档：空值校验、三个资料页、保存、空首页',startup)
    if cases[0]['status']!='PASS':
        window.close();timer.stop();private.cleanup();raise SystemExit(1)
    for title in ('首页','AI 康复管家','康复','健康','用药','家庭','记录','通知','设置'):
        record('导航/'+title,lambda title=title:nav(title))


    def assistant():
        nav('AI 康复管家')
        for key,back in [('assistantModuleConversation','assistantBackConversation'),('assistantModuleVoice','assistantBackVoice'),
                         ('assistantModuleMaterials','assistantBackMaterials'),('assistantModuleRecords','assistantBackReference')]:
            action(key);action(back)
        action('assistantModuleConversation')
        field=next(x for x in window.findChildren(QPlainTextEdit) if x.isVisible())
        edit(field,'TEST 今天的训练计划是什么');action('product-202')
        check('TEST 今天的训练计划是什么' in texts(window),'sent text missing from transcript')
        edit(field,'TEST 未发送草稿');action('assistantMaterialsEntry');action('assistantBackMaterials')
        check(field.toPlainText()=='TEST 未发送草稿','draft lost on return')
        action('assistantReferenceEntry');action('assistantBackReference')
        action('assistantVoiceEntry');action('assistantVoiceText')
        for key in ('product-199','product-200','product-201'):action(key)
        action('assistantReferenceEntry');action('assistantRehab');check(window.findChild(QLabel,'productTitle').text()=='康复','rehab link wrong')


    record('AI 四模块、发送、三推荐问题、草稿、返回、康复链接',assistant)


    def dock():
        nav('健康');action('globalAssistant')
        field=next(x for x in window.findChildren(QPlainTextEdit) if x.isVisible())
        edit(field,'TEST 我的健康记录');action('dockSend')
        check('TEST 我的健康记录' in texts(window),'dock reply missing')
        check(window.findChild(QLabel,'productTitle').text()=='健康','dock changed page')
        # The actual Qt dock close affordance is reached with its native close shortcut.
        dock=field.parentWidget()
        while dock and type(dock).__name__!='QDockWidget':dock=dock.parentWidget()
        check(dock is not None,'dock missing');click(dock.findChild(QAbstractButton,'qt_dockwidget_closebutton'));pump()


    record('全局管家发送且不丢失健康页',dock)


    def metric_all():
        nav('健康');tab('当前状态');action('healthMetricsEntry')
        combo=next(x for x in window.findChildren(QComboBox) if x.isVisible() and x.count()==10)
        spin=next(x for x in window.findChildren(QDoubleSpinBox) if x.isVisible())
        values=[1234,0.7,7,1,68,62,97,120,80,5.5]
        for i,val in enumerate(values):
            select(combo,i);edit(spin,val);action('product-77')
            check(str(val) in texts_tables(window),'saved number absent in visible UI: '+str(val))
        action('healthMetricsBack');tab('健康记录')
        combo=next(c for c in window.findChildren(QComboBox) if c.isVisible() and c.count()==5)
        for i in range(combo.count()):select(combo,i);select_first_table();action('healthDetail')
        select(combo,0);action('product-75')


    record('健康十种指标逐项选择、保存、反馈与返回',metric_all)


    def medication():
        nav('用药');tab('我的药物')
        policy.append(dict(kind='medication',empty=True,fields={'药物名称':'TEST 医嘱药物','已有医嘱剂量':'TEST 剂量','已知用途':'TEST 验收','服用时间 / 频次':'08:00'}))
        action('medAdd');check('TEST 医嘱药物' in texts_tables(window),'saved medication missing')
        select_first_table();action('medView')
        policy.append(dict(kind='medication',fields={'已有医嘱剂量':'TEST 修改剂量'}));action('medEdit')
        check('TEST 修改剂量' in texts_tables(window),'edit not reflected')
        for yes in (False,True,True):
            select_first_table();policy.append(dict(kind='confirm',yes=yes));action('medStatus')
        tab('今日用药');select_first_table();action('medTodayDetail');action('medTodayActions')
        action('medConfirm');check(not by_id('medDose').isEnabled(),'per-dose action falsely enabled')
        action('medTodayActionsBack');action('medTodayActions');action('medMiss')
        nav('用药');tab('用药历史');select_first_table();action('medHistoryDetail')
        tab('漏服记录');select_first_table();action('medMissedDetail');action('medMissedAdd');nav('用药');tab('今日用药')
        if any(b.isVisible() and b.property('actionId')=='medTodayActionsBack' for b in window.findChildren(QAbstractButton)):action('medTodayActionsBack')
        action('medBack')


    record('用药新增/编辑/查看、停用取消与确认、恢复、今日核对、漏服与历史',medication)


    def attachment():
        nav('AI 康复管家');action('assistantModuleConversation')
        field=next(x for x in window.findChildren(QPlainTextEdit) if x.isVisible());edit(field,'TEST 附件后继续对话')
        action('assistantMaterialsEntry')
        source=OUT/'TEST-公开资料.txt';source.write_text('TEST 黑箱附件原文',encoding='utf-8')
        policy.extend([dict(kind='file',path=source),dict(kind='category',index=5)])
        action('assistantAttachment')
        check(by_id('assistantBackMaterials').isVisible(),'AI upload navigated away; advertised Back button unreachable')
        action('assistantBackMaterials');check(field.toPlainText()=='TEST 附件后继续对话','upload lost draft')
        action('assistantMaterialsEntry');action('assistantArchiveEntry');check(window.findChild(QLabel,'productTitle').text()=='健康','archive link wrong')


    record('AI 添加真实本机附件后可直接返回未发送草稿',attachment)


    def archive():
        nav('健康');tab('健康档案');select_first_table();action('archiveDetail')
        exported=OUT/'exported-TEST.txt';policy.append(dict(kind='file',path=exported));action('product-70')
        check(exported.exists() and exported.read_text(encoding='utf-8')=='TEST 黑箱附件原文','attachment bytes differ')
        action('archiveProfile')
        for i,category in enumerate(['体检报告','就诊记录','检验检查','影像资料','病历资料','其他资料']):
            source=OUT/f'TEST-{i}.txt';source.write_text('TEST '+category,encoding='utf-8')
            policy.extend([dict(kind='file',path=source),dict(kind='category',index=i)])
            action('product-69');check(category in texts_tables(window),'category missing: '+category)


    record('档案六分类真实导入、详情、原字节导出、资料表单取消',archive)


    def family():
        nav('家庭')
        for key in ('product-37','familySOS','product-7','familyDetail','familySharingRecords','product-45','silverFamily'):
            action(key)
            if window.findChild(QLabel,'productTitle').text()!='家庭':nav('家庭')
        action('product-40')
        for key in ('product-41','product-42','product-43','product-44'):
            for yes in (False,True):
                policy.append(dict(kind='confirm',yes=yes));action(key)
                check(not policy,'sensitive action did not show confirmation: '+key)


    record('照护圈联系人、SOS、详情、共享记录、邀请、绑定/授权/撤销/解绑确认',family)


    def history():
        nav('记录');tab('统一历史')
        combo=next(x for x in window.findChildren(QComboBox) if x.isVisible() and x.count()==5)
        for i in range(5):
            select(combo,i);inventory();select_first_table()
            for key in ('historyDetail','historyTrends','historyReport'):
                tab('统一历史');select(combo,i);select_first_table()
                action(key)
                if window.findChild(QLabel,'productTitle').text()!='记录':nav('记录');tab('统一历史');select(combo,i)
            tab('统一历史');select(combo,i)
            file=OUT/f'history-{i}.txt';policy.append(dict(kind='file',path=file));action('historyExport')
            check(file.exists(),'filtered export absent')
        tab('报告与趋势');policy.append(dict(kind='file',path=OUT/'report.txt'));action('product-31')
        check((OUT/'report.txt').exists(),'report export absent');tab('统一历史');action('product-32')


    record('记录五分类、详情/趋势/报告、各分类真实文件导出',history)


    def notification():
        nav('通知')
        for combo in [x for x in window.findChildren(QComboBox) if x.isVisible() and x.count()>1]:
            for i in range(combo.count()):select(combo,i);inventory()
            select(combo,0)
        policy.append(dict(kind='confirm',yes=False));action('product-27')
        policy.append(dict(kind='confirm',yes=True));action('product-27')
        select_first_table();action('notificationDetail');action('product-28');action('notificationBusiness')


    record('通知筛选、台账取消/确认、详情、确认、业务跳转',notification)


    def rehab():
        nav('康复')
        for title,keys in [('今日训练',['rehabContinue','rehabAction']),('康复评估',['rehabAssess','rehabAssessmentDetail','rehabBody']),
          ('训练计划',['rehabLibrary','rehabAutomatic','rehabPlanDetail']),('康复进度',['rehabTrainingDetail','rehabProgress','rehabReports'])]:
            for key in keys:
                nav('康复');tab(title);action(key)
                # Workspace has a public, conditionally enabled return path.
                back=[b for b in window.findChildren(QAbstractButton) if b.isVisible() and b.property('actionId')=='rehabWorkspaceBack']
                if back and back[0].isEnabled():action('rehabWorkspaceBack')
        nav('康复')
        for key in ('rehabPerson','silverRehab'):
            nav('康复');action(key)
            backs=[b for b in window.findChildren(QAbstractButton) if b.isVisible() and b.property('actionId')=='rehabWorkspaceBack']
            if backs:action('rehabWorkspaceBack')
        nav('康复');action('rehabOverview');action('rehabWorkspaceBack');action('rehabHome')


    record('康复四页签全部主入口、原评估/计划/历史、身体档案、返回',rehab)


    def devices():
        nav('健康');tab('设备')
        for key in ('deviceRefresh','deviceConnect','deviceData'):
            action(key)
            tab('设备')
        action('deviceImport') # Cancel actual file chooser.
        bad=OUT/'invalid-device.json';bad.write_text('{invalid',encoding='utf-8')
        policy.extend([dict(kind='file',path=bad),dict(kind='confirm',yes=True)]);action('deviceImport')
        check(any(x.isVisible() and x.property('fluentStatus')=='danger' and x.text() for x in window.findChildren(QLabel)),'invalid import lacks error')
        action('cameraSettings');action('rehabWorkspaceBack')


    record('设备状态/刷新/查看、导入取消、坏 JSON 拒绝、摄像头设置导航',devices)


    def settings():
        nav('设置')
        for title,keys in [('个人资料',['settingsProfile']),('家庭共享',['settingsSharing']),
         ('设备与同步',['settingsRefresh','settingsDevices','notificationSettings','familySettings']),
         ('通知',['settingsNotification']),('开发者设置',['settingsDeveloper'])]:
            for key in keys:nav('设置');tab(title);action(key)
        nav('设置');tab('数据与隐私')
        export=OUT/'TEST-backup.json';policy.append(dict(kind='file',path=export));action('settingsBackup')
        check(export.exists() and isinstance(json.loads(export.read_text(encoding='utf-8')),dict),'invalid backup')
        policy.append(dict(kind='confirm',yes=False));action('settingsClear')
        action('settingsHome')


    record('设置六页签、真实备份、清除取消、开发者取消、所有业务链接',settings)


    def home_actions():
        for key in ('homeContinue','homePlans','homeAsk','homeMedication','homeTasks','homeHealth','taskComplete','taskDismiss','homeAI','homeProfile'):
            nav('首页');action(key)
            # Close the dock via Escape or caption separately; leave parent page unchanged.
            for d in window.findChildren(__import__('PySide6.QtWidgets',fromlist=['QDockWidget']).QDockWidget):
                if d.isVisible():click(d.findChild(QAbstractButton,'qt_dockwidget_closebutton'));pump()


    record('首页十个入口逐项实际点击（无数据按真实提示处理）',home_actions)


    def second_owner():
        nav('健康');tab('当前状态');action('healthMetricsEntry')
        field=next(x for x in window.findChildren(QDoubleSpinBox) if x.isVisible());edit(field,999)
        policy.append(dict(kind='profile',fields={'称呼':'TEST 黑箱乙'}));action('product-8')
        check('TEST 黑箱甲' not in texts_tables(window),'other owner data remains')
        nav('AI 康复管家');action('assistantModuleConversation')
        check('TEST 今天的训练计划是什么' not in texts(window),'chat crossed owners')
        check(next(x for x in window.findChildren(QPlainTextEdit) if x.isVisible()).toPlainText()=='','draft crossed owners')
        user=next(x for x in window.findChildren(QComboBox) if x.accessibleName()=='当前产品用户')
        select(user,next(i for i in range(user.count()) if user.itemText(i)=='TEST 黑箱甲'));ready()
        nav('健康');tab('当前状态');action('healthMetricsEntry')
        check(next(x for x in window.findChildren(QDoubleSpinBox) if x.isVisible()).value()==0,'unsaved number crossed owner')


    record('创建第二用户、对话/草稿/未保存数值隔离、切回第一用户',second_owner)

    def until(predicate,timeout=30):
        deadline=time.monotonic()+timeout
        while not predicate() and time.monotonic()<deadline:pump(80)
        check(predicate(),'visible UI did not reach expected state')


    def original_catalog():
        nav('康复');tab('康复评估');action('rehabAssess')
        for part in ('头颈','肩部','肘部','腕部','手指','躯干','髋部','膝部','踝部','全部动作'):
            click(button(part,window));pump(80)
            check('项动作' in texts(window),'body filter lacks result count')
        names=[b.accessibleName() for b in window.findChildren(QAbstractButton) if b.isVisible() and b.text()=='选择动作']
        check(len(names)==53,'expected existing 53 actions')
        for name in names:
            field=next(x for x in window.findChildren(QLineEdit) if x.isVisible() and x.placeholderText()=='搜索动作 / 关节')
            edit(field,name.removeprefix('选择'));pump(80)
            candidates=[b for b in window.findChildren(QAbstractButton) if b.isVisible() and b.accessibleName()==name]
            click(candidates[0]);pump(100)
            for title in ('动作图解','设置','步骤'):tab(title)
            click(button('更换动作',window));pump(50);click(button('全部动作',window))
        field=next(x for x in window.findChildren(QLineEdit) if x.isVisible() and x.placeholderText()=='搜索动作 / 关节')
        edit(field,'TEST 不存在的动作');check('0 项动作' in texts(window),'search empty feedback missing')
        edit(field,'');action('rehabWorkspaceBack')


    def plan_flow(dlg):
        until(lambda:button('新建计划',dlg).isEnabled());click(button('新建计划',dlg))
        click(button('保存到计划库',dlg));check(dlg.isVisible(),'invalid empty plan accepted')
        name=next(x for x in dlg.findChildren(QLineEdit) if x.isVisible());edit(name,'TEST 用户操作计划')
        def child(d):
            for c in d.findChildren(QCheckBox):
                if c.isVisible():click(c);click(c)
            click(button('保存项目',d))
        side=next(c for c in dlg.findChildren(QComboBox) if c.isVisible() and c.count()==2)
        for index in (0,1):
            select(side,index);policy.append(dict(kind='flow',run=child));click(button('添加项目',dlg))
        table=dlg.findChild(QTableWidget);check(table.rowCount()==2,'two plan sides missing')
        click(button('上移',dlg));click(button('下移',dlg))
        policy.append(dict(kind='flow',run=child));click(button('修改项目',dlg))
        click(button('保存到计划库',dlg));until(lambda:button('新建计划',dlg).isEnabled())
        check('已保存' in texts(dlg),'plan save receipt missing')
        check(not button('使用所选项目',dlg).isEnabled(),'plan without valid assessment allowed training')
        click(button('编辑计划',dlg));click(button('移除项目',dlg));click(button('放弃修改',dlg))
        check(table.rowCount()==2,'discard lost saved plan')
        click(button('归档计划',dlg));until(lambda:any(b.isVisible() and b.text()=='恢复计划' and b.isEnabled() for b in dlg.findChildren(QAbstractButton)))
        click(button('恢复计划',dlg));until(lambda:any(b.isVisible() and b.text()=='归档计划' and b.isEnabled() for b in dlg.findChildren(QAbstractButton)))
        click(button('刷新',dlg));until(lambda:button('关闭',dlg).isEnabled());click(button('关闭',dlg))


    def original_plan():
        nav('康复');tab('训练计划');policy.append(dict(kind='flow',run=plan_flow));action('rehabLibrary')
        check(not policy,'plan dialog did not consume user flow')
        action('rehabWorkspaceBack')


    def batch_flow(dlg):
        until(lambda:button('保存本轮清单',dlg).isEnabled());click(button('保存本轮清单',dlg))
        check('请至少勾选' in texts(dlg),'empty assessment checklist accepted')
        choices=dlg.findChild(QListWidget);check(choices.count()==106,'existing 53×2 checklist lost')
        # Keyboard selection toggles every existing option, then leaves two real items selected.
        click_focus(choices);QTest.keyClick(choices,Qt.Key_Home)
        for i in range(choices.count()):
            QTest.keyClick(choices,Qt.Key_Space);QTest.keyClick(choices,Qt.Key_Space)
            if i<choices.count()-1:QTest.keyClick(choices,Qt.Key_Down)
        QTest.keyClick(choices,Qt.Key_Home);QTest.keyClick(choices,Qt.Key_Space)
        QTest.keyClick(choices,Qt.Key_Down);QTest.keyClick(choices,Qt.Key_Space)
        click(button('保存本轮清单',dlg));until(lambda:dlg.findChild(QTableWidget).rowCount()==2)
        table=dlg.findChild(QTableWidget);QTest.mouseClick(table.viewport(),Qt.LeftButton,pos=table.visualItemRect(table.item(0,0)).center());pump(50)
        policy.append(dict(kind='input',text='TEST 暂不评估'));click(button('跳过所选项目',dlg));until(lambda:table.item(0,4) is not None and table.item(0,4).text()=='TEST 暂不评估')
        QTest.mouseClick(table.viewport(),Qt.LeftButton,pos=table.visualItemRect(table.item(0,0)).center());pump(60)
        check(button('恢复为待测',dlg).isEnabled(),'skipped item cannot be restored')
        check('TEST 暂不评估' in texts_tables(dlg),'skip reason not displayed')
        click(button('恢复为待测',dlg));until(lambda:any(b.isVisible() and b.text()=='跳过所选项目' and b.isEnabled() for b in dlg.findChildren(QAbstractButton)))
        check(not button('查看报告',dlg).isEnabled(),'unmeasured item has report')
        for yes in (False,True):
            policy.append(dict(kind='confirm',yes=yes));click(button('结束本轮',dlg))
            until(lambda:any(b.isVisible() and b.isEnabled() and b.text()==('新建下一轮' if yes else '结束本轮') for b in dlg.findChildren(QAbstractButton)))
        check('本轮已结束' in texts(dlg),'round completion receipt absent')
        QTest.keyClick(dlg,Qt.Key_Escape);pump(50)


    def original_batch():
        nav('康复');tab('康复评估');action('rehabAssess')
        policy.append(dict(kind='flow',run=batch_flow));click(button('本轮评估清单',window));ready()
        action('rehabWorkspaceBack')


    def original_history():
        nav('记录');tab('统一历史');action('product-32')
        for caption in ('刷新','打开报告','纵向记录','导出所选报告','比较两份报告','删除所选报告'):
            click(button(caption,window));pump(150)
        check('尚无历史报告' in texts(window),'empty original history lacks feedback')
        click(button('返回任务',window));action('rehabWorkspaceBack')


    def clear_data():
        nav('设置');tab('数据与隐私');policy.append(dict(kind='confirm',yes=True));action('settingsClear')
        nav('健康');tab('健康记录');check('暂无健康记录' in texts(window),'health clear did not finish')
        tab('健康档案');check('暂无健康资料' in texts(window),'attachments not cleared')
        nav('AI 康复管家');action('assistantModuleConversation');check('TEST 今天的训练计划是什么' not in texts(window),'chat not cleared')
        nav('用药');tab('我的药物');check('TEST 医嘱药物' in texts_tables(window),'clear wrongly removed retained medication')
        nav('首页');check('TEST 黑箱甲' in texts(window),'clear wrongly removed profile')

    record('原康复/九部位、全部53动作、图解设置步骤、搜索空态',original_catalog)
    record('原康复/人工计划新增、两侧项目、编辑排序、保存、归档恢复',original_plan)
    record('原康复/106评估选项、空值拒绝、清单保存跳过恢复结束确认',original_batch)
    record('原康复/空历史打开导出比较删除与返回保护',original_history)

    def silver_flow(dlg):
        until(lambda:'观察快照' in texts(dlg))
        def stab(title):
            t=dlg.findChild(QTabWidget);i=next(i for i in range(t.count()) if t.tabText(i)==title)
            QTest.mouseClick(t.tabBar(),Qt.LeftButton,pos=t.tabBar().tabRect(i).center());pump(80)
        def refresh_done(before):until(lambda:'观察快照' in texts(dlg) and texts(dlg)!=before)
        click(button('今天的任务',dlg))
        for title in ('功能变化','家庭回应与安全','共享与提示设置','今天的任务'):stab(title)
        stab('功能变化')
        for c in dlg.findChildren(QComboBox):
            if c.isVisible() and c.count()>2:
                for i in range(c.count()):select(c,i)
        for caption in ('已逐条核对：记录所选报告的实际条件','建立新参考期','比较所选单次','记录本人情况'):
            click(button(caption,dlg));pump(1200);ready()
        stab('共享与提示设置')
        recipient=next(x for x in dlg.findChildren(QLineEdit) if x.isVisible() and '家属称呼' in x.placeholderText());edit(recipient,'TEST 同电脑照护者')
        for c in dlg.findChildren(QCheckBox):
            if c.isVisible() and c.text()!='启用本机语音（请先测试是否能听见）' and not c.isChecked():click(c)
        old_stamp=next(x.text() for x in dlg.findChildren(QLabel) if x.isVisible() and x.text().startswith('观察快照'))
        policy.append(dict(kind='confirm',yes=False));click(button('确认共享范围',dlg))
        check(button('确认共享范围',dlg).isEnabled(),'cancelled sharing leaves save disabled')
        check(next(b for b in dlg.findChildren(QAbstractButton) if b.text()=='建立居家整改任务').isEnabled(),'cancelled sharing leaves unrelated mutations disabled')
        policy.append(dict(kind='confirm',yes=True));click(button('确认共享范围',dlg))
        until(lambda:any(x.isVisible() and x.text().startswith('观察快照') and x.text()!=old_stamp for x in dlg.findChildren(QLabel)))
        pump(300)
        check(not policy,'sharing lacks confirmation')
        click(button('测试语音提示',dlg));pump(3400);check('语音不可用' in texts(dlg),'unavailable local TTS lacked persistent error')
        stab('家庭回应与安全')
        c=next(x for x in dlg.findChildren(QComboBox) if x.isVisible() and x.count()>2)
        for i in range(c.count()):select(c,i)
        field=next(x for x in dlg.findChildren(QLineEdit) if x.isVisible());edit(field,'TEST 人工测试整改，不涉及真实居家风险')
        click(button('建立居家整改任务',dlg))
        requests=next(x for x in dlg.findChildren(QListWidget) if x.isVisible())
        until(lambda:any('TEST 人工测试整改' in requests.item(i).text() for i in range(requests.count())))
        row=next(i for i in range(requests.count()) if 'TEST 人工测试整改' in requests.item(i).text())
        QTest.mouseClick(requests.viewport(),Qt.LeftButton,pos=requests.visualItemRect(requests.item(row)).center());pump(180)
        until(lambda:button('我已查看',dlg).isEnabled())
        click(button('我已查看',dlg));until(lambda:button('我来联系 / 处理',dlg).isEnabled())
        click(button('我来联系 / 处理',dlg));until(lambda:button('记录处理结果',dlg).isEnabled())
        policy.append(dict(kind='input',text='TEST 本机流程验收记录，不表示实际到场'));click(button('记录处理结果',dlg));check(not policy,'resolve input dialog not handled')
        until(lambda:button('本人确认整改完成',dlg).isEnabled())
        policy.append(dict(kind='input',text='TEST 人工流程闭环'));click(button('本人确认整改完成',dlg));check(not policy,'owner confirmation input not handled');until(lambda:'已处理' in texts_tables(dlg) or not button('本人确认整改完成',dlg).isEnabled())
        click(button('希望家人联系',dlg));until(lambda:button('我已查看',dlg).isEnabled());pump(1000)
        click(button('我需要帮助',dlg));until(lambda:'本人主动请求帮助' in texts(dlg));pump(180)
        stab('共享与提示设置');policy.append(dict(kind='confirm',yes=True));click(button('撤销全部共享',dlg));pump(1200);check(not policy,'revocation lacked confirmation')
        role=next(x for x in dlg.findChildren(QComboBox) if x.isVisible() and [x.itemText(i) for i in range(x.count())]==['本人','本机家属（同电脑演示）'])
        select(role,1);until(lambda:'未获共享授权' in texts(dlg) or '授权已撤销' in texts(dlg))
        select(role,0);pump(200);click(button('刷新',dlg));pump(300);click(button('返回康复界面',dlg))


    def original_silver():
        nav('家庭');policy.append(dict(kind='flow',run=silver_flow));action('silverFamily')
        check(not policy,'silver flow not consumed')
        action('rehabWorkspaceBack')

    record('银发/四页签、选择项、共享确认、求助与人工整改真实闭环、撤销',original_silver)

    record('清除本人数据确认后真实清除、保留药物与本人档案',clear_data)


    def file_imports():
        nav('设置');tab('数据与隐私');backup=OUT/'import-owner-backup.json'
        policy.append(dict(kind='file',path=backup));action('settingsBackup')
        owner=json.loads(backup.read_text(encoding='utf-8'))['snapshot']['ownerId']
        from datetime import datetime,timezone
        timestamp=datetime.now(timezone.utc).isoformat()
        measures=[dict(id='TEST-import-'+metric,metric=metric,value=value,unit=unit,source='device',timestamp=timestamp,visibility='private')
            for metric,value,unit in [('restingHr',71,'bpm'),('systolic',123,'mmHg'),('spo2',98,'%'),('steps',2222,'步')]]
        good=dict(ownerId=owner,source='device',measurements=measures)
        nav('健康');tab('健康记录')
        combo=next(x for x in window.findChildren(QComboBox) if x.isVisible() and x.count()==5);select(combo,2)
        before=next(x for x in window.findChildren(QTableWidget) if x.isVisible()).rowCount()
        tab('设备')
        for name,value in [('foreign',dict(good,ownerId='TEST-another-owner')),('wrong-unit',dict(good,measurements=[dict(measures[0],unit='TEST-wrong-unit')])),('valid',good),('repeat',good)]:
            path=OUT/(name+'-device.json');path.write_text(json.dumps(value),encoding='utf-8')
            policy.extend([dict(kind='file',path=path),dict(kind='confirm',yes=True)]);action('deviceImport')
            labels=[x for x in window.findChildren(QLabel) if x.isVisible() and x.property('fluentStatus') in ('danger','success')]
            check(any(x.property('fluentStatus')==('success' if name in ('valid','repeat') else 'danger') for x in labels),'file import feedback does not match validation '+name)
        tab('健康记录');combo=next(x for x in window.findChildren(QComboBox) if x.isVisible() and x.count()==5);select(combo,2)
        t=next(x for x in window.findChildren(QTableWidget) if x.isVisible())
        check(t.rowCount()==before+4,'device import was duplicated or failed')
        check('2222' in texts_tables(window),'imported activity missing')


    def source_body():
        nav('康复');tab('康复评估');action('rehabAssess');click(button('输入设置',window));pump(100)
        combos=[x for x in window.findChildren(QComboBox) if x.isVisible() and x.count()>1]
        for c in combos:
            labels=[c.itemText(i) for i in range(c.count())]
            if labels not in [['实时摄像头','本地录像回放','自动计划演示（合成）'],['DSHOW','MSMF'],['自主使用','受控演示','软件测试']]:continue
            for i in range(c.count()):select(c,i);ready();pump(100)
            select(c,0);ready()
        click(button('输入设置',window));click(button('双摄：正面＋侧面',window));pump(100)
        check(any(c.isVisible() and c.accessibleName()=='侧面摄像头' for c in window.findChildren(QComboBox)),'dual input missing')
        click(button('双摄：正面＋侧面',window));action('rehabWorkspaceBack')
        nav('康复');tab('康复评估');action('rehabBody')
        combo=next(c for c in window.findChildren(QComboBox) if c.isVisible() and c.count()==10 and c.itemText(0)=='全部部位')
        click(button('显示未评估项目',window))
        for i in range(combo.count()):select(combo,i);pump(30)
        click(button('完整明细',window));pump(200)
        action('rehabWorkspaceBack')

    record('文件接口/设备四指标导入、错误用户、错误单位、重复去重',file_imports)
    record('输入与身体档案/输入来源接口情境选择、双摄、十部位与明细',source_body)


    def details_privacy_media():
        nav('家庭')
        for caption in ('允许长期共享','撤销共享','修改联系人','查看家属摘要'):
            def member(dlg,caption=caption):
                if caption in ('允许长期共享','撤销共享'):policy.append(dict(kind='confirm',yes=False))
                click(button(caption,dlg));pump(300)
                check(not policy,'member sensitive action lacks confirmation')
            policy.append(dict(kind='flow',run=member));action('familyDetail')
        nav('AI 康复管家');action('assistantModuleConversation')
        field=next(x for x in window.findChildren(QPlainTextEdit) if x.isVisible())
        private_box=next(x for x in window.findChildren(QCheckBox) if x.isVisible() and x.text()=='本轮不记录')
        click(private_box);edit(field,'TEST_PRIVATE 不持久化这轮身体感受');action('product-202');click(private_box)
        nav('设置');tab('数据与隐私');backup=OUT/'privacy-backup.json'
        policy.append(dict(kind='file',path=backup));action('settingsBackup')
        check('TEST_PRIVATE' not in backup.read_text(encoding='utf-8'),'private turn leaked into persisted backup')
        from PySide6.QtGui import QImage,QColor
        png=OUT/'TEST-image.png';q=QImage(32,32,QImage.Format_RGB32);q.fill(QColor('white'));check(q.save(str(png)),'PNG fixture creation failed')
        import av,numpy as np
        video=OUT/'TEST-video.mp4'
        with av.open(str(video),'w') as container:
            stream=container.add_stream('mpeg4',rate=3);stream.width=64;stream.height=64;stream.pix_fmt='yuv420p'
            for _ in range(3):
                frame=av.VideoFrame.from_ndarray(np.zeros((64,64,3),dtype=np.uint8),format='rgb24')
                for packet in stream.encode(frame):container.mux(packet)
            for packet in stream.encode():container.mux(packet)
        nav('健康');tab('健康档案')
        for path in (png,video):
            policy.extend([dict(kind='file',path=path),dict(kind='category',index=5)]);action('product-69')
            t=next(x for x in window.findChildren(QTableWidget) if x.isVisible())
            row=next(r for r in range(t.rowCount()) if t.item(r,0).text()==path.stem)
            QTest.mouseClick(t.viewport(),Qt.LeftButton,pos=t.visualItemRect(t.item(row,0)).center());pump(30)
            action('archiveDetail');dest=OUT/('export-'+path.name);policy.append(dict(kind='file',path=dest));action('product-70')
            check(dest.read_bytes()==path.read_bytes(),'media bytes changed during archive/export')
        check(not by_id('product-71').isEnabled(),'unconfigured vision claims available')

    record('额外/成员详情操作、私密对话备份、真实PNG与MP4导入导出',details_privacy_media)


    def real_notifications():
        nav('家庭');action('product-40')
        policy.append(dict(kind='confirm',yes=True));action('product-41')
        policy.append(dict(kind='confirm',yes=True));action('product-42')
        nav('AI 康复管家');action('assistantModuleConversation')
        field=next(x for x in window.findChildren(QPlainTextEdit) if x.isVisible())
        edit(field,'TEST 软件黑箱测试：我刚才在卫生间摔了一跤，现在胸口有点疼');action('product-202')
        nav('通知');policy.append(dict(kind='confirm',yes=True));action('product-27')
        t=next(x for x in window.findChildren(QTableWidget) if x.isVisible())
        check(t.rowCount()>0,'authorized findings produced no notification')
        select_first_table();action('notificationDetail');select_first_table();action('product-28')
        check('已确认' in texts_tables(window),'notification acknowledgment not displayed')
        select_first_table();action('notificationBusiness');check(window.findChild(QLabel,'productTitle').text() in ('健康','用药'),'notification business link failed')
        nav('通知');combo=next(x for x in window.findChildren(QComboBox) if x.isVisible() and x.count()==3)
        for i in range(3):select(combo,i);inventory()
        check('送达' not in texts_tables(window) or '未' in texts_tables(window),'unconfigured push falsely claimed delivery')

    record('有通知/真实记录检测、授权台账、已查看确认、三筛选与业务跳转',real_notifications)


    def original_remaining():
        nav('康复');tab('今日训练');action('rehabContinue')
        def automatic_empty(dlg):
            until(lambda:button('重新读取评估',dlg).isEnabled())
            check('还没有已保存的评估' in texts(dlg),'automatic plan fabricates assessment')
            check(not button('使用这个安排',dlg).isEnabled(),'automatic plan accepts missing assessments')
            for c in dlg.findChildren(QCheckBox):click(c);click(c)
            click(button('重新读取评估',dlg));until(lambda:button('暂不训练',dlg).isEnabled())
            click(button('暂不训练',dlg))
        policy.append(dict(kind='flow',run=automatic_empty));click(button('根据评估自动安排 / 继续训练',window))
        click(button('选择评估记录',window));ready()
        for caption in ('查看报告','导出评估','进入训练'):
            b=button(caption,window)
            if b.isEnabled():
                click(b);ready();until(lambda:button('打开摄像头并测试',window).isEnabled())
            else:visible_controls.append(dict(window='身体档案/缺评估',caption=caption,enabled=False))
        click(button('编辑个人信息',window));pump(150)
        until(lambda:button('打开摄像头并测试',window).isEnabled())
        click(button('继续评估',window));until(lambda:any(b.isVisible() and b.text()=='全部动作' for b in window.findChildren(QAbstractButton)))
        for b in [b for b in window.findChildren(QAbstractButton) if b.isVisible() and b.text()=='+']:
            click(b);pump(50);check('项动作' in texts(window),'body icon filter failed')
        click(button('全部动作',window));click(button('评估结果',window));ready()
        action('rehabWorkspaceBack')

    record('补测/自动计划空态、原身体档案保护与全部人体图标导航',original_remaining)


    def silver_navigation():
        for caption in ('开始训练','准备活动观察','床边演示','安全演示','暂停摄像头'):
            nav('家庭')
            def flow(dlg,caption=caption):
                until(lambda:'观察快照' in texts(dlg));tab('今天的任务',dlg)
                click(button(caption,dlg));pump(500);ready()
                if dlg.isVisible():
                    check(caption=='暂停摄像头' or '请先选择实时摄像头' in texts(dlg),'navigation failed silently')
                    click(button('返回康复界面',dlg))
            policy.append(dict(kind='flow',run=flow));action('silverFamily');ready();action('rehabWorkspaceBack')
        nav('家庭')
        def phone_outer(dlg):
            until(lambda:'观察快照' in texts(dlg));tab('共享与提示设置',dlg)
            def phone(d):
                until(lambda:'服务未开启；原配对已失效' in texts(d))
                check(not button('我已核对手机：确认待配对家属',d).isEnabled(),'pairing without phone enabled')
                click(button('手动开启演示',d));until(lambda:'操作未确认成功' in texts(d))
                QTest.keyClick(d,Qt.Key_Escape);pump(100)
            policy.append(dict(kind='flow',run=phone));click(button('手机家属联动（仅隔离测试资料）',dlg));pump(200)
            click(button('返回康复界面',dlg))
        policy.append(dict(kind='flow',run=phone_outer));action('silverFamily');action('rehabWorkspaceBack')

    record('补测/银发五场景入口与手机演示未确认拒绝',silver_navigation)


    def raw_camera():
        nav('康复');tab('康复评估');action('rehabAssess');ready()
        def camera(dlg):
            until(lambda:'正在打开摄像头' not in texts(dlg),timeout=40)
            receipt=texts(dlg);(OUT/'raw-camera-receipt.txt').write_text(receipt,encoding='utf-8')
            check(any(t in receipt for t in ('已收到画面','未取得画面','无法','失败','不可用','关闭后')),'raw camera lacks result')
            toggle=next(x for x in dlg.findChildren(QCheckBox) if x.text()=='镜像预览');click(toggle);click(toggle)
            close=next(b for b in dlg.findChildren(QAbstractButton) if b.isVisible() and b.text().startswith('关闭摄像头'))
            click(close);until(lambda:not isValid(dlg) or not dlg.isVisible())
        policy.append(dict(kind='flow',run=camera));click(button('打开摄像头并测试',window));pump(700)
        if policy:
            policy.clear();check('请先选择摄像头' in texts(window),'no-camera guard lacks feedback')
            (OUT/'raw-camera-receipt.txt').write_text(texts(window),encoding='utf-8')
        action('rehabWorkspaceBack')

    record('补测/原始摄像头打开、真实结果、镜像与关闭',raw_camera)


    def demo_plan():
        nav('康复');tab('今日训练');action('rehabContinue')
        check(not any(b.isVisible() and b.text()=='一键生成演示计划' for b in window.findChildren(QAbstractButton)),
              'synthetic helper leaked into formal product flow')
        action('rehabWorkspaceBack');nav('首页');check('TEST 黑箱甲' in texts(window),'product owner changed')

    record('补测/合成演示按钮不进入正式用户路径',demo_plan)


    def phone_local():
        nav('家庭')
        def outer(dlg):
            until(lambda:'观察快照' in texts(dlg));tab('共享与提示设置',dlg)
            def phone(d):
                until(lambda:'服务未开启；原配对已失效' in texts(d))
                c=next(c for c in d.findChildren(QCheckBox) if c.isVisible());click(c)
                click(button('手动开启演示',d));until(lambda:'手机地址：http://127.0.0.1' in texts(d))
                check(not button('我已核对手机：确认待配对家属',d).isEnabled(),'unknown phone identity accepted')
                click(button('注入 TEST_EVENT 演示求助（非视觉检测）',d))
                until(lambda:d.findChild(QListWidget).count()>0)
                check(all(d.findChild(QListWidget).item(i).text().startswith('OPEN') for i in range(d.findChild(QListWidget).count())),'no-phone request falsely confirmed')
                click(button('撤销配对并关闭服务',d));until(lambda:'服务未开启；原配对已失效' in texts(d))
                check(not button('注入 TEST_EVENT 演示求助（非视觉检测）',d).isEnabled(),'stopped demo still enabled')
                QTest.keyClick(d,Qt.Key_Escape);pump(100)
            policy.append(dict(kind='flow',run=phone));click(button('手机家属联动（仅隔离测试资料）',dlg));pump(200)
            click(button('返回康复界面',dlg))
        policy.append(dict(kind='flow',run=outer));action('silverFamily');action('rehabWorkspaceBack')

    record('补测/手机TEST演示本机开启、注入请求、无配对保护与关闭',phone_local)

    inventory();write()
    print(json.dumps(dict(counts=dict(Counter(x['status'] for x in cases)),output=str(OUT)),ensure_ascii=False),flush=True)
    window.close()
    deadline=time.monotonic()+8
    while window.isVisible() and time.monotonic()<deadline:pump(100)
    timer.stop()
    private.cleanup()
    raise SystemExit(0 if all(x['status']=='PASS' for x in cases) else 1)
