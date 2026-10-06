"""Patient-first five-page experience over retained, tested domain workspaces."""
from datetime import date, datetime
from uuid import uuid4

from PySide6.QtCore import Qt, QDate, QTime, QTimer
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget,
    QDateEdit, QTimeEdit, QDialog, QDialogButtonBox, QFormLayout, QLineEdit,
    QComboBox, QCheckBox, QSpinBox, QMessageBox, QInputDialog, QPushButton)
from .product_widgets import label, button, table, rows, visual, CurrentStack
from .product_dialogs import blank_health

CATEGORY_NAMES = {'health': '健康近况（已允许共享的记录）', 'rehab': '近期康复完成情况', 'medication': '用药记录'}


def dated_picker():
    value = QDateEdit(QDate.currentDate())
    value.setCalendarPopup(True)
    value.setDisplayFormat('yyyy年MM月dd日')
    value.setAccessibleName('查看日期')
    return value


class ProductExperience:
    def _experience_setup(self):
        self.daily_data = {}
        self.daily_dialog = None
        self.initial_answers = None
        self._experience_home()
        self._experience_rehab()
        self._experience_health()
        self._experience_meds()
        self._experience_family()
        self._action(self.settings_tabs.widget(0).layout(), 'phoneConnect', '连接手机', self._connect_phone, target='本人手机连接与停止共享服务')
        self.interface_buttons['globalAssistant'].hide()
        self.user_select.hide()
        self.account_button.setText('我的档案')
        self.context_return.setText('返回健康记录')
        self.rehab_tabs.setCurrentIndex(2)
        self.last_rehab_tab = 2
        for widget in (self.dose_table, self.schedule_table, self.linked_family):
            widget.itemSelectionChanged.connect(self._completion_controls)

    def _connect_phone(self):
        if not self.owner:
            self._message('先建立或选择本人的档案。'); return
        dialog = QDialog(self); dialog.setWindowTitle('连接我的手机'); dialog.resize(520, 340)
        area = QVBoxLayout(dialog)
        area.addWidget(visual(label('手机与电脑，共用一份档案'), typography='section'))
        area.addWidget(label('手机连接同一可信 Wi-Fi，在浏览器打开下面的地址，输入连接码。电脑需保持开启。连接码允许操作本人的资料，只给自己的设备使用。', 'productMuted'))
        status = label('正在启动手机连接…'); status.setTextInteractionFlags(Qt.TextSelectableByMouse); area.addWidget(status)
        area.addWidget(label('当前为局域网 HTTP 连接；不向互联网发布，不会自动调整防火墙。', 'productMuted'))
        try:
            from mobile_rehab.desktop import PhoneHost
            hosts = getattr(self, 'phone_hosts', {})
            self.phone_hosts = hosts
            host = hosts.get(self.owner)
            if not host or host.stopped.is_set():
                hosts[self.owner] = host = PhoneHost(self.backend, self.owner)
            self.phone_host = host
        except Exception as error:
            status.setText('连接未启动：' + str(error)); host = None
        timer = QTimer(dialog)
        def refresh():
            if not host: return
            if host.error: status.setText('连接未启动：' + host.error); timer.stop()
            elif host.closing.is_set(): status.setText('手机连接正在停止，请稍后重新打开本窗口。'); timer.stop()
            elif host.server and host.server.started:
                status.setText('本人手机地址：\n' + '\n'.join(host.urls) + '\n\n连接码：' + host.code + '\n关闭此窗口后仍可连接；停止连接会撤销本次连接码。'); timer.stop()
            elif host.stopped.is_set(): status.setText('手机连接已停止。'); timer.stop()
        timer.timeout.connect(refresh); timer.start(200); refresh()
        actions = QHBoxLayout(); area.addLayout(actions)
        def open_browser():
            if not host or not host.server or not host.server.started:
                status.setText('连接正在启动，请稍候再打开。'); return
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(host.code)
            QDesktopServices.openUrl(QUrl(f'http://127.0.0.1:{host.port}/'))
            status.setText('已复制本人连接码。在浏览器粘贴连接后，进入“康复 → 健身”。\n连接码：'+host.code)
        area.addWidget(button('复制连接码并在电脑浏览器打开',open_browser))
        def stop():
            if host: host.close()
            status.setText('正在停止手机连接，已配对手机将无法继续访问。'); timer.stop()
        actions.addWidget(button('停止手机连接', stop)); actions.addStretch(); actions.addWidget(button('完成', dialog.accept))
        dialog.exec()

    def _experience_home(self):
        scroll = self.page_widgets['home']
        old = scroll.takeWidget()
        holder = QWidget(); box = QVBoxLayout(holder); box.setContentsMargins(0, 0, 8, 0)
        holder.setProperty('visualScope', 'core')
        self.home_sections = CurrentStack(); box.addWidget(self.home_sections)
        page = QWidget(); area = QVBoxLayout(page); area.setContentsMargins(0, 8, 0, 0); area.setSpacing(20)
        self.home_hello = visual(label('欢迎使用安康'), typography='display'); area.addWidget(self.home_hello)
        self.home_intro = visual(label('查看今天的安排，或和康复管家聊聊。'), typography='secondary'); area.addWidget(self.home_intro)
        visual(self._action(area, 'homeConversation', '和康复管家聊聊', lambda: self.navigate('assistant'), target='康复管家对话'), appearance='primary')
        area.addSpacing(12)
        heading = QHBoxLayout(); heading.addWidget(visual(label('今天的安排'), typography='section')); heading.addStretch()
        self._action(heading, 'homeScheduleDetail', '查看详细安排', lambda: self.navigate('rehab'), target='康复计划与日期安排')
        area.addLayout(heading)
        self.home_schedule = label('正在读取今天的安排…'); area.addWidget(self.home_schedule)
        self.home_schedule.setTextInteractionFlags(Qt.LinksAccessibleByMouse|Qt.LinksAccessibleByKeyboard)
        self.home_schedule.linkActivated.connect(lambda key:self.navigate(key) if key in ('rehab','medication') else None)
        self.home_attention = label(''); area.addWidget(self.home_attention)
        extra = QHBoxLayout()
        self._action(extra, 'homeAllTasks', '查看待办', self._show_today_tasks, target='本人待办')
        self._action(extra, 'homeInitialProfile', '补充初始资料', lambda: self._first_use(existing=True), target='选择题建档')
        extra.addStretch(); area.addLayout(extra); area.addStretch(1)
        self.home_sections.addWidget(page)
        detail=QWidget();tasks_area=QVBoxLayout(detail);tasks_area.setAlignment(Qt.AlignTop)
        self._action(tasks_area,'homeTasksBack','返回首页',lambda:self.home_sections.setCurrentIndex(0),target='首页')
        tasks_area.addWidget(visual(label('需要你确认的事项'),typography='section'))
        tasks_area.addWidget(self.tasks_empty);tasks_area.addWidget(self.tasks)
        actions=QHBoxLayout();actions.addWidget(self.interface_buttons['taskComplete']);actions.addWidget(self.interface_buttons['taskDismiss']);actions.addStretch();tasks_area.addLayout(actions)
        self.home_sections.addWidget(detail)
        old.setParent(holder);old.hide();self.retained_home=old
        scroll.setWidget(holder)

    def _experience_rehab(self):
        self.rehab_tabs.tabBar().hide()
        overview = self.rehab_sections.widget(0).layout()
        header = QHBoxLayout()
        header.addWidget(visual(label('今天的康复'), typography='section')); header.addStretch()
        self._action(header, 'rehabEvaluateNow', '开始评估', lambda: self._rehab_action('assessment'), target='原评估流程')
        overview.insertLayout(1, header)
        area = self.rehab_areas['训练计划']
        self.plan_hint = label('先完成评估，康复管家会根据已保存的结果准备计划。'); area.insertWidget(0, self.plan_hint)
        self.interface_buttons['rehabAutomatic'].setText('康复管家制定计划')
        self.interface_buttons['rehabLibrary'].setText('手动添加 / 编辑')
        self.interface_buttons['rehabPlanDetail'].setText('计划详情')
        self.plan_manage=QWidget();manage=QHBoxLayout(self.plan_manage);manage.setContentsMargins(0,0,0,0)
        manage.addWidget(self.interface_buttons['rehabAutomatic']);manage.addWidget(self.interface_buttons['rehabLibrary']);manage.addWidget(self.interface_buttons['rehabPlanDetail']);manage.addStretch()
        area.insertWidget(1,self.plan_manage)
        self.recovery_sections['flow'].hide()
        # A simple current plan selector replaces the prototype's equal-status tabs.
        self.current_plan = QComboBox(); self.current_plan.setAccessibleName('当前训练计划')
        self.current_plan.currentIndexChanged.connect(self._experience_plan_change)
        area.insertWidget(1, self.current_plan)
        self.current_plan_text = label('还没有动作计划。可先开始评估，或手动添加已有安排。')
        area.insertWidget(2, self.current_plan_text)
        actions = QHBoxLayout()
        self._action(actions, 'planSchedule', '安排日期', self._schedule_plan, kind='A', target='daily.schedule')
        self._action(actions, 'planPractice', '按计划开始', self._practice_selected, target='原计划准备与训练')
        self._action(actions, 'planManualCopy', '修改为个人计划', self._manual_plan_copy, target='另存人工计划；原自动计划保留')
        self._action(actions, 'planVersions', '旧版本', self._plan_versions, target='只读旧计划版本')
        actions.addStretch(); area.insertLayout(3, actions)
        date_row = QHBoxLayout(); date_row.addWidget(visual(label('日期安排'), typography='section')); date_row.addStretch()
        self.rehab_day = dated_picker(); self.rehab_day.dateChanged.connect(self._experience_schedule_render); date_row.addWidget(self.rehab_day)
        area.insertLayout(4, date_row)
        self.schedule_table = table(['时间', '安排', '状态']); area.insertWidget(5, self.schedule_table)
        self.schedule_empty = label('这一天没有安排。'); area.insertWidget(6, self.schedule_empty)
        schedule_actions = QHBoxLayout()
        self._action(schedule_actions, 'scheduleOpen', '查看 / 开始', self._open_schedule, target='评估 / 原计划准备')
        self._action(schedule_actions, 'scheduleMove', '调整日期', lambda: self._schedule_plan(edit=True), kind='A', target='daily.schedule')
        self._action(schedule_actions, 'scheduleRemove', '取消安排', self._remove_schedule, kind='D', target='daily.unschedule')
        schedule_actions.addStretch(); area.insertLayout(7, schedule_actions)
        for index,old_key in enumerate(('今日恢复', '康复评估', '康复进度')):
            item=self._action(self.rehab_areas[old_key],'rehabDetailsBack'+str(index),'返回训练计划',lambda:self.rehab_tabs.setCurrentIndex(2),target='训练计划')
            self.rehab_areas[old_key].removeWidget(item);self.rehab_areas[old_key].insertWidget(0,item)
        area.removeWidget(self.plan_manage)
        self.plan_manage.hide()
        self.plan_tools = QWidget(); tools_box = QVBoxLayout(self.plan_tools); tools_box.setContentsMargins(0,0,0,0)
        tools_box.addWidget(self.plan_manage); tools_box.addWidget(self.current_plan)
        for key in ('planSchedule','planManualCopy','planVersions'):
            tools_box.addWidget(self.interface_buttons[key])
        toggle = self._action(area, 'planManageToggle', '管理计划与日期', lambda:self._toggle_plan_tools(), target='展开计划管理')
        area.removeWidget(toggle); area.insertWidget(1,toggle); area.insertWidget(2,self.plan_tools)
        self.plan_tools.hide()
        self.plan_next = visual(label(''), typography='display'); area.insertWidget(0,self.plan_next)
        self.current_plan_text.hide()
        self.plan_hint.setWordWrap(True)
        # Keep overview and editing separate even when a snapshot updates child visibility.
        original=self.rehab_tabs.widget(2).widget()
        self.plan_overview=QWidget(original);self.plan_overview.setLayout(area)
        self.plan_editor_area=QVBoxLayout(original);self.plan_editor_area.setContentsMargins(0,0,0,0)
        self.plan_editor_area.addWidget(self.plan_overview)

    def _toggle_plan_tools(self):
        opened = not self.plan_tools.isVisible()
        self.plan_tools.setVisible(opened); self.plan_manage.setVisible(opened)
        self.interface_buttons['planManageToggle'].setText('收起计划管理' if opened else '管理计划与日期')

    def _experience_health(self):
        self.health_tabs.setTabText(0, '我的档案')
        self.health_tabs.setTabText(1, '身体记录')
        self.health_tabs.setTabText(2, '资料与图片')
        self.health_tabs.setTabVisible(3, False)
        # History remains the same widget/readers; its home is now the health archive.
        self.pages.removeWidget(self.page_widgets['history'])
        self.health_tabs.addTab(self.page_widgets['history'], '全部记录与报告')
        area = self.health_tabs.widget(0).layout()
        self.health_archive_intro = visual(label('我的健康档案'), typography='section'); area.insertWidget(0, self.health_archive_intro)
        row = QHBoxLayout()
        visual(self._action(row, 'healthUpload', '上传健康资料', self._add_attachment, kind='A', target='archive.save'), appearance='primary')
        self._action(row, 'healthPhoto', '识别健康图片', self._parse_image, kind='D', target='image.parse')
        self._action(row, 'healthCamera', '拍照', self._photo_capture, kind='D', target='原 CameraManager 画面测试 → archive.save')
        self._action(row, 'healthRecord', '记录身体情况', lambda: self.navigate('assistant'), target='管家表达与记录确认')
        row.addStretch(); area.insertLayout(1, row)
        self.health_archive_profile = label('正在读取档案…'); area.insertWidget(2, self.health_archive_profile)
        self.health_rehab_summary.hide(); self.concerns.hide(); self.twin_text.hide()
        # The technical state panel remains available in the detail route.
        self.health_status_sections.widget(0).layout().itemAt(0).widget().hide()
        entry=self._action(area, 'healthRehabRecords', '查看康复评估与训练记录', lambda: self._show_health_history('康复'), target='健康内康复记录')
        area.removeWidget(entry);area.insertWidget(3,entry)
        phone=self._action(area, 'healthPhoneRecords', '查看手机录像记录与计划', self._phone_records, target='同一本人数据库的录像来源记录')
        area.removeWidget(phone);area.insertWidget(4,phone)

    def _phone_records(self):
        data=self.snapshot.get('phoneRehabilitation',{})
        lines=[]
        for key,title in (('rehab.get_training_plan','手机录像计划'),('rehab.get_recent_assessments','手机录像评估'),('rehab.get_training_history','手机录像训练')):
            records=data.get(key,{}).get('records',[])
            lines.append(title+'：'+str(len(records))+' 项')
            for r in records[:20]:
                if key=='rehab.get_training_plan':
                    lines.append(r['name']+' · v'+str(r['revision'])+'\n'+'\n'.join(i['exercise_label']+' · '+self._plan_settings(i['settings']) for i in r['items']))
                else:
                    completed = (r.get('summary') or {}).get('completed', r.get('completed'))
                    progress = f'完成 {completed} 次' if isinstance(completed, (int, float)) else '次数未测得'
                    lines.append(str(r.get('exercise_label') or r.get('exercise_id'))+' · '+str(r.get('end_utc') or r.get('timestamp') or '')+'\n'+progress+'；'+str(r.get('reason') or r.get('measurement_note') or '详细分析报告可在手机健康页查看。'))
        self._detail('手机录像记录与计划',lines+['手机录像与电脑实时测量保留各自来源条件，不直接互换为训练依据。'])

    def _experience_meds(self):
        self.medication_tabs.setTabText(0, '按日记录')
        old = self.medication_tabs.widget(0)
        # Retain the daily overall check as an optional legacy task, distinct from doses.
        self.medication_tabs.removeTab(0)
        self.medication_tabs.addTab(old, '每日核对')
        page = QWidget(); area = QVBoxLayout(page); area.setAlignment(Qt.AlignTop); area.setSpacing(14)
        header = QHBoxLayout(); header.addWidget(visual(label('用药安排'), typography='section')); header.addStretch()
        self.med_day = dated_picker(); self.med_day.dateChanged.connect(self._experience_doses_render); header.addWidget(self.med_day); area.addLayout(header)
        area.addWidget(label('按已有医嘱设置时间，逐次记录服用情况。未记录不会自动算作漏服。', 'productMuted'))
        self.dose_table = table(['时间', '药物', '剂量', '记录']); area.addWidget(self.dose_table)
        self.dose_empty = label('这一天没有用药时间安排。添加药物后，为它设置服用时间。'); area.addWidget(self.dose_empty)
        row = QHBoxLayout()
        for key, title, status in [('doseTaken', '已服用', 'taken'), ('doseSkipped', '已跳过', 'skipped'), ('doseReset', '更正为未记录', 'unrecorded')]:
            visual(self._action(row, key, title, lambda checked=False, value=status: self._record_dose(value), kind='A', target='daily.dose'), appearance='primary' if status == 'taken' else 'secondary')
        row.addStretch(); area.addLayout(row)
        manage = QHBoxLayout()
        self._action(manage, 'doseAddMedicine', '添加药物', lambda: self._medication_edit(), kind='A', target='medication.save')
        self._action(manage, 'doseSetTimes', '设置服用时间', self._med_schedule, kind='A', target='daily.medSchedule')
        self._action(manage, 'doseManage', '管理药物', lambda: self.medication_tabs.setCurrentIndex(1), target='药物档案')
        manage.addStretch(); area.addLayout(manage)
        self.dose_history = table(['记录时间', '该次服用', '修改']); area.addWidget(self.dose_history)
        self.dose_history.setMaximumHeight(180)
        self.medication_tabs.insertTab(0, page, '今日用药'); self.medication_tabs.setCurrentIndex(0)
        for index in (2,3,4):self.medication_tabs.setTabVisible(index,False)
        old_actions=QHBoxLayout();self.medication_tabs.widget(1).layout().addLayout(old_actions)
        self._action(old_actions,'medLegacyHistory','旧核对与漏服记录',lambda:self.medication_tabs.setCurrentIndex(2),target='原用药记录')
        self._action(old_actions,'medLegacyCheck','每日整体核对',lambda:self.medication_tabs.setCurrentIndex(4),target='原用药核对任务')
        for index in (2,3,4):
            layout=self.medication_tabs.widget(index).layout()
            item=self._action(layout,'medLegacyBack'+str(index),'返回今日用药',lambda:self.medication_tabs.setCurrentIndex(0),target='今日用药')
            layout.removeWidget(item);layout.insertWidget(0,item)

    def _experience_family(self):
        scroll = self.page_widgets['family']; old = scroll.takeWidget()
        holder = QWidget(); holder.setProperty('visualScope', 'core'); area = QVBoxLayout(holder); area.setContentsMargins(0, 0, 8, 0)
        self.family_sections = CurrentStack(); area.addWidget(self.family_sections)
        page = QWidget(); box = QVBoxLayout(page); box.setAlignment(Qt.AlignTop); box.setSpacing(16)
        box.addWidget(visual(label('家人的近况'), typography='section'))
        box.addWidget(label('只查看家人主动共享的信息。双方分别选择共享范围；你不能修改家人的档案。', 'productMuted'))
        self.family_attention = label(''); box.addWidget(self.family_attention)
        self.linked_family = table(['家人', '对方允许我查看', '我向对方共享']); box.addWidget(self.linked_family)
        self.linked_family.setMaximumHeight(220)
        self.linked_empty = label('尚未关联家人。在家人的本机档案生成邀请码，再切回本人确认关联。'); box.addWidget(self.linked_empty)
        row = QHBoxLayout()
        self._action(row, 'familyReadOnly', '查看近况', self._read_family, target='获准只读摘要')
        self._action(row, 'familyCategories', '我共享哪些信息', self._family_categories, kind='D', target='daily.familyGrant')
        self._action(row, 'familyDisconnect', '解除关联', self._family_disconnect, kind='D', target='daily.familyUnbind')
        row.addStretch(); box.addLayout(row)
        relation = QHBoxLayout()
        self._action(relation, 'familyLocalInvite', '生成我的邀请码', lambda: self._request('daily.familyInvite'), kind='A', target='daily.familyInvite')
        self._action(relation, 'familyLocalBind', '关联家人', self._family_link, kind='D', target='daily.familyBind')
        self._action(relation, 'familyOldTools', '联系人与照护工具', lambda: self.family_sections.setCurrentIndex(1), target='原照护能力与联系人')
        relation.addStretch(); box.addLayout(relation)
        box.addWidget(label('家人分别选择共享范围。本人手机可在“我的档案 → 设置与数据管理 → 连接手机”中连接，读取同一份获准摘要。', 'productMuted')); box.addStretch()
        self.family_sections.addWidget(page)
        tools=QWidget();tools_box=QVBoxLayout(tools);tools_box.setAlignment(Qt.AlignTop);tools_box.setSpacing(16)
        self._action(tools_box,'familyToolsBack','返回家人近况',lambda:self.family_sections.setCurrentIndex(0),target='家人近况')
        tools_box.addWidget(visual(label('联系人与照护'),typography='section'));tools_box.addWidget(self.contact_state)
        self._action(tools_box,'familyEditContact','编辑我的联系人',self._profile,target='本人的联系人资料')
        tools_box.addWidget(self.interface_buttons['familySOS']);tools_box.addWidget(self.interface_buttons['silverFamily'])
        tools_box.addWidget(self.interface_buttons['familySharingRecords'])
        self.family_sections.addWidget(tools)
        item=self._action(old.layout(),'familyLegacyBack','返回家人近况',lambda:self.family_sections.setCurrentIndex(0),target='家人近况')
        old.layout().removeWidget(item);old.layout().insertWidget(0,item)
        old.layout().insertWidget(1,label('兼容旧版单关系共享接口。日常家人近况请使用新页面的逐人分类授权。','productMuted'))
        self.family_sections.addWidget(old)
        developer=self.settings_tabs.widget(5).layout()
        self._action(developer,'familyCompatibility','兼容旧版共享接口',lambda:(self.navigate('family'),self.family_sections.setCurrentIndex(2)),target='旧共享接口；与日常家人视图分离')
        scroll.setWidget(holder)

    def _first_use(self, existing=False):
        if self.pending or self._rehab_locked() or self.daily_dialog:
            return
        dialog = QDialog(self); dialog.setObjectName('firstUse'); dialog.setWindowTitle('建立我的档案'); dialog.resize(580, 660)
        dialog.setProperty('visualScope', 'core'); area = QVBoxLayout(dialog); area.setSpacing(12)
        area.addWidget(visual(label('先认识你，再安排康复'), typography='section'))
        area.addWidget(label('当前使用本机档案，不需要网络账号。以后可接入手机号 / 邮箱等登录。', 'productMuted'))
        form = QFormLayout(); area.addLayout(form)
        stored = self.snapshot.get('profile', {}) if existing else {}
        profile = stored.get('profile', {})
        name = QLineEdit(profile.get('name', '')); name.setMaxLength(60); name.setPlaceholderText('你的称呼'); form.addRow('怎么称呼你', name)
        age = QSpinBox(); age.setRange(0, 130); age.setSpecialValueText('暂不填写'); age.setValue(profile.get('age', 0)); form.addRow('年龄', age)
        def choice(title, options):
            select = QComboBox()
            for text, value in options:
                select.addItem(text, value)
            form.addRow(title, select); return select
        concern = choice('目前主要情况', [('暂不清楚 / 稍后补充', ''), ('一般活动能力恢复', '一般活动能力恢复'), ('关节活动困难', '关节活动困难'), ('疾病 / 术后恢复', '疾病或术后恢复'), ('其他已有健康问题', '其他已有健康问题')])
        mobility = choice('日常活动', [('暂不清楚', 'unknown'), ('通常可以独立活动', 'independent'), ('使用拐杖', 'uses_cane'), ('需要别人协助', 'needs_support')])
        discomfort = choice('目前是否不适 / 受限', [('暂不清楚', 'unknown'), ('目前没有不适，也没有活动限制', 'none'), ('有疼痛、头晕或其他不适', 'discomfort'), ('有医嘱或术后活动限制', 'restricted')])
        goal = choice('希望优先改善', [('日常活动更方便', '日常活动更方便'), ('关节活动更自然', '关节活动更自然'), ('坚持已有康复安排', '坚持已有康复安排')])
        clock = QTimeEdit(QTime(9, 0)); clock.setDisplayFormat('HH:mm'); form.addRow('方便的时间', clock)
        days = QWidget(); day_area = QHBoxLayout(days); day_area.setContentsMargins(0, 0, 0, 0); checks = []
        for i, title in enumerate(('一', '二', '三', '四', '五', '六', '日')):
            c = QCheckBox(title); c.setChecked(i in (0, 2, 4)); checks.append(c); day_area.addWidget(c)
        form.addRow('方便的星期', days)
        area.addWidget(label('资料可稍后拍照上传。首次没有有效动作评估时，先安排评估，不猜测训练次数或角度。', 'productMuted'))
        error = label(''); area.addWidget(error)
        row = QHBoxLayout(); area.addLayout(row)
        def save(skip):
            if not name.text().strip():
                error.setText('请填写称呼，其他问题可以跳过。'); name.setFocus(); return
            if not skip and not any(c.isChecked() for c in checks):
                error.setText('请选择至少一天方便的时间。'); return
            owner = self.owner if existing else 'person-' + uuid4().hex
            health = dict(profile or blank_health(name.text().strip()))
            health.update(name=name.text().strip(), age=age.value())
            if not skip:
                health.update(mobility=mobility.currentData(), usesCane=mobility.currentData() == 'uses_cane')
                if concern.currentData():
                    health['conditions'] = list(dict.fromkeys([*health.get('conditions', []), concern.currentData()]))
            self.initial_answers = {'owner': owner, 'skipped': skip, 'time': clock.time().toString('HH:mm'),
                                    'days': [i for i, c in enumerate(checks) if c.isChecked()], 'limitation': discomfort.currentData(), 'goal': goal.currentData(),
                                    'concern': concern.currentData(), 'mobility': mobility.currentData()}
            self.onboarding_to_align=dict(self.initial_answers)
            if self._request('profile.save', dict(profile=health, rehabGoal=stored.get('rehabGoal') or goal.currentData(), currentState=stored.get('currentState') or concern.currentData()), owner):
                dialog.accept()
        row.addWidget(button('跳过问题，进入首页', lambda: save(True)))
        row.addWidget(button('完成建档', lambda: save(False), True))
        self.daily_dialog = dialog
        dialog.finished.connect(lambda *_: setattr(self, 'daily_dialog', None))
        dialog.setAttribute(Qt.WA_DeleteOnClose); dialog.open()

    def _account(self):
        if self.pending or self._rehab_locked():
            self._message('请先完成当前操作，再打开个人资料。'); return
        dialog = QDialog(self); dialog.setWindowTitle('我的档案 · 本机'); area = QVBoxLayout(dialog)
        area.addWidget(label('当前为本机身份；切换档案不代表远程登录。', 'productMuted'))
        select = QComboBox()
        for p in self.profiles:
            select.addItem(p['profile']['name'], p['ownerId'])
        select.setCurrentIndex(select.findData(self.owner)); area.addWidget(select)
        area.addWidget(button('切换到所选档案', lambda: (dialog.accept(), self._select_owner(select.currentData()))))
        area.addWidget(button('编辑我的资料', lambda: (dialog.accept(), self._profile())))
        area.addWidget(button('新建本机档案', lambda: (dialog.accept(), self._first_use())))
        area.addWidget(button('连接我的手机', lambda: (dialog.accept(), self._connect_phone())))
        area.addWidget(button('设置与数据管理', lambda: (dialog.accept(), self.navigate('settings'))))
        close = QDialogButtonBox(QDialogButtonBox.Close); close.rejected.connect(dialog.reject); area.addWidget(close)
        dialog.exec()

    def _show_health_history(self, selected='全部'):
        from .product_structure import open_records
        open_records(self,selected=selected)

    def _experience_plan_change(self):
        if not hasattr(self, 'current_plan_text'):
            return
        p = self._selected_plan()
        self.current_plan_text.setText(p['name'] + '\n' + '\n'.join(i['exercise_label'] + ' · ' + ('左侧' if i['side'] == 'left' else '右侧') + ' · ' + self._plan_settings(i['settings']) for i in p['items']) if p else '还没有动作计划。可先开始评估，或添加已有安排。')
        if hasattr(self, 'plan_next'):
            next_item = next((i for i in (p or {}).get('items', []) if i['key'] == (p or {}).get('progress', {}).get('next_key')), None)
            self.plan_next.setText(next_item['exercise_label'] if next_item else '这一轮已完成' if p else '从一次评估开始')
            self.plan_hint.setText(('下一项 · ' + ('左侧' if next_item['side']=='left' else '右侧') + ' · ' + self._plan_settings(next_item['settings']) + ('\n' + p['availability_reason'] if p.get('availability_reason') else '')) if next_item else '可制定下一轮计划，已保存的训练记录会保留。' if p else '点击“去做评估”完成一次动作测试，再让康复管家制定计划。已有安排可在管理计划中添加。')
            self.interface_buttons['planPractice'].setText('制定下一轮' if p and not p.get('has_next') else '补充评估' if p and not p.get('next_available') else '开始下一项')
        if p:
            self.rehab_tables['训练计划'].selectRow(self.current_plan.currentIndex())

    def _selected_plan(self):
        return next((p for p in self._rehab_data('rehab.get_training_plan') if p['id'] == self.current_plan.currentData()), None)

    def _schedule_plan(self, checked=False, edit=False):
        if self.pending or self._rehab_locked():
            return
        previous = self._selected_schedule() if edit else None
        p = self._selected_plan()
        if not p and not previous:
            self._message('先保存训练计划；首次评估安排会在完成建档后出现。'); return
        dialog = QDialog(self); dialog.setWindowTitle('调整日期' if edit else '安排训练日期'); box = QVBoxLayout(dialog)
        box.addWidget(label((previous or p)['name']))
        day = dated_picker(); day.setMinimumDate(QDate.currentDate()); day.setDate(QDate.fromString((previous or {}).get('date', date.today().isoformat()), 'yyyy-MM-dd')); box.addWidget(day)
        clock = QTimeEdit(QTime.fromString((previous or self.daily_data.get('onboarding', {})).get('time', '09:00'), 'HH:mm')); clock.setDisplayFormat('HH:mm'); box.addWidget(clock)
        box.addWidget(label('只调整安排，不改变训练记录。错过的安排不会自动顺延。', 'productMuted'))
        controls = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel); box.addWidget(controls)
        controls.rejected.connect(dialog.reject); controls.accepted.connect(dialog.accept)
        if dialog.exec() == QDialog.Accepted:
            payload = dict(previous or dict(planId=p['id'], revision=p['revision'], name=p['name'], kind='training'))
            payload.update(date=day.date().toString('yyyy-MM-dd'), time=clock.time().toString('HH:mm'))
            self._request('daily.schedule', payload)

    def _selected_schedule(self):
        r = self.schedule_table.currentRow()
        if not 0 <= r < len(getattr(self, 'visible_schedule', [])):
            self._message('请先选择一条日期安排。'); return None
        return self.visible_schedule[r]

    def _open_schedule(self):
        entry = self._selected_schedule()
        if not entry:
            return
        if entry['date'] != date.today().isoformat():
            self._detail('日期安排', [entry['date'] + ' ' + entry['time'], entry['name'], '实际评估与训练从今天的安排进入；过去记录不会改写。']); return
        if entry['kind'] == 'assessment':
            self._rehab_action('assessment'); return
        p = next((p for p in self._rehab_data('rehab.get_training_plan') if p['id'] == entry.get('planId') and p['revision'] == entry.get('revision')), None)
        if not p:
            self._message('这份安排引用的计划已更新，请重新安排当前版本。'); return
        self.current_plan.setCurrentIndex(self.current_plan.findData(p['id'])); self._practice_selected()

    def _remove_schedule(self):
        entry = self._selected_schedule()
        if entry and QMessageBox.question(self, '取消安排', '取消这次日期安排？已保存的训练与评估不会删除。') == QMessageBox.Yes:
            self._request('daily.unschedule', {'id': entry['id']})

    def _practice_selected(self):
        p = self._selected_plan()
        if not p:
            self._message('请先选择已保存的计划。'); return
        if not p.get('has_next'):
            self._automatic_plan(); return
        if not p.get('next_available'):
            if self._rehab_action('assessment'):
                item=next((i for i in p['items'] if i['key']==p.get('progress',{}).get('next_key')),None)
                if item:
                    self.legacy._choose_catalog_exercise(item['exercise_id'])
                    self.legacy.side.setCurrentIndex(self.legacy.side.findData(item['side']))
            return
        if self._rehab_action('training'):
            if p['record_origin'] == 'assessment_rules':
                self.legacy._open_automatic_plan()
                self.legacy._send('automatic_progress', scope=self.legacy._body_scope_key(), id=p['id'], revision=p['revision'])
            else:
                self.legacy._open_plan_library()
                self.legacy.plan_library_dialog.select_source_id = p['id']

    def _embed_plan_dialog(self, dialog):
        if not dialog:
            return
        area = self.plan_editor_area
        self.plan_overview.hide()
        # The legacy opener already showed this as a window-modal dialog.
        # Hide while its modal window still exists so Qt releases the native
        # parent lock before changing modality/flags/parent. Otherwise Windows
        # keeps the product window disabled although activeModalWidget is None.
        dialog.hide()
        dialog.setWindowModality(Qt.NonModal)
        dialog.setWindowFlags(Qt.Widget)
        dialog.setParent(self.rehab_tabs.widget(2).widget())
        dialog.setProperty('visualScope', 'core')
        dialog.setMinimumSize(0, 0); dialog.setMinimumHeight(570)
        if hasattr(dialog,'item_editor'):
            old=dialog.item_editor.layout()
            while old.count():old.takeAt(0)
            holder=QWidget();holder.setLayout(old);holder.deleteLater()
            layout=QVBoxLayout(dialog.item_editor);layout.setContentsMargins(0,0,0,0)
            choose=QHBoxLayout();choose.addWidget(dialog.exercise,1);choose.addWidget(dialog.side);choose.addWidget(dialog.add_item);layout.addLayout(choose)
            edit=QHBoxLayout()
            for item in (dialog.edit_item,dialog.remove_item,dialog.up,dialog.down):edit.addWidget(item)
            edit.addStretch();layout.addLayout(edit)
        area.insertWidget(0, dialog)
        dialog.five_page_flow = True
        dialog.version_store = self.backend.daily
        dialog.close_button.setText('返回计划概览')
        for index,item in enumerate(dialog.findChildren(QPushButton)):
            item.setProperty('actionId',type(dialog).__name__+'-'+str(index))
            item.setProperty('actionKind','B' if item is dialog.close_button else 'A')
            item.setProperty('actionTarget','原计划服务：'+item.text())
        def return_to_overview(*_):
            dialog.hide()
            self.plan_overview.show()
            if not self.pending: self._request('snapshot')
            else: self.refresh_needed = True
        dialog.finished.connect(return_to_overview)
        dialog.show()

    def _plan_library(self):
        if self.pending or self._rehab_locked():
            return
        self.navigate('rehab', refresh=False)
        if self.legacy.plan_library_dialog:
            self.legacy.plan_library_dialog.show(); return
        self.legacy._open_plan_library()
        self._embed_plan_dialog(self.legacy.plan_library_dialog)

    def _automatic_plan(self):
        if self.pending or self._rehab_locked():
            return
        self.navigate('rehab', refresh=False)
        if self.legacy.automatic_dialog:
            self.legacy.automatic_dialog.show(); return
        self.legacy._open_automatic_plan()
        self._embed_plan_dialog(self.legacy.automatic_dialog)
        dialog=self.legacy.automatic_dialog
        if dialog:
            dialog.generate_new=True
            dialog.archive_requested.connect(lambda old:self.legacy._send('archive_training_plan',scope=dialog.scope,id=old['id'],expected_revision=old['revision'],archived=True))
            dialog.title.setText('康复管家正在读取你的评估与活动条件')

    def _plan_versions(self):
        scope=self.legacy._body_scope_key()
        versions = [v for v in self.daily_data.get('planVersions', []) if all(v.get(k)==value for k,value in scope.items())]
        self._detail('保留的计划版本', [v['name'] + ' · v' + str(v['revision']) + '\n' + '\n'.join(i['exercise_id'] + ' · ' + self._plan_settings(i['settings']) for i in v['items']) for v in versions] or ['暂无被覆盖的旧版本。另存的新计划可从当前计划选择器查看。'])

    def _plan_detail(self):
        p=self._selected_plan()
        if not p:self._message('请先选择计划。');return
        self._detail('计划详情',[p['name']+' · v'+str(p['revision']),*[(i['exercise_label']+' · '+self._plan_settings(i['settings'])) for i in p['items']],
            '日期安排独立保存；已完成的计划不会自动清零。'],[('手动添加 / 编辑',self._plan_library),('修改为个人计划',self._manual_plan_copy),('查看旧版本',self._plan_versions)])

    def _manual_plan_copy(self):
        p = self._selected_plan()
        if not p:
            self._message('请先选择计划。'); return
        existing = self.legacy.plan_library_dialog
        if existing and getattr(existing, 'editing', False):
            self._message('请先保存或取消当前编辑，再修改另一份计划。'); return
        self._plan_library()
        if self.legacy.plan_library_dialog:
            self.legacy.plan_library_dialog.copy_source_id = p['id']
            if not self.legacy.plan_library_dialog.pending:
                self.legacy.plan_library_dialog.populate(self.legacy.plan_library_dialog.records)
            self._message('已打开计划编辑。另存为人工计划，原自动安排及其评估依据保留。')

    def _photo_capture(self):
        if not self.owner or self.pending or self._rehab_locked():return
        if self.legacy._body_scope_key()['source_kind']!='LIVE_CAMERA':
            self._message('拍摄资料需要实时摄像头，请先在设置中切换输入来源。');return
        self.photo_requested=True
        if self._rehab_action('assessment'):
            self.legacy._start_camera_test()
            if not self.legacy.camera_test_dialog:
                self._message('先选择摄像头，再点击“打开摄像头并测试”。收到画面后可拍摄健康资料。')

    def _save_camera_photo(self, dialog):
        import time
        from PySide6.QtCore import QBuffer, QIODevice
        packet=dialog.last_packet
        if self.pending or dialog.stopping:return
        if packet is None or packet.context.source_kind!='LIVE_CAMERA' or time.monotonic()-packet.received_monotonic>3 or dialog.canvas.image is None:
            dialog.status.setText('没有新鲜画面，请等待摄像头恢复后再拍摄。');return
        buffer=QBuffer();buffer.open(QIODevice.WriteOnly)
        if not dialog.canvas.image.save(buffer,'PNG'):
            dialog.status.setText('照片编码失败，尚未保存。');return
        content=bytes(buffer.data());buffer.close()
        if len(content)>10*1024*1024:
            dialog.status.setText('照片超过 10 MB，请降低分辨率后重试。');return
        title='健康照片 '+datetime.now().strftime('%Y-%m-%d %H-%M-%S')
        if self._request('archive.save',dict(name=title,fileName=title+'.png',category='影像资料',mediaType='image/png',bytes=list(content),visibility='private')):
            self.photo_return_needed=True
            dialog.photo_button.setEnabled(False)
            dialog.request_stop()

    def _med_schedule(self):
        active = [m for m in self.snapshot.get('profile', {}).get('profile', {}).get('medicationRecords', []) if m['status'] == 'active']
        if not active:
            self._message('先按已有医嘱添加药物。'); return
        dialog = QDialog(self); dialog.setWindowTitle('设置服用时间'); form = QFormLayout(dialog)
        select = QComboBox()
        for m in active:
            select.addItem(m['name'] + ' · ' + (m.get('dose') or '剂量未填写'), m['id'])
        form.addRow('药物', select)
        times = QLineEdit(); times.setPlaceholderText('例如 08:00, 20:00'); form.addRow('每日时间', times)
        start = dated_picker(); form.addRow('开始日期', start)
        has_end = QCheckBox('设置结束日期'); form.addRow(has_end)
        end = dated_picker(); end.setEnabled(False); has_end.toggled.connect(end.setEnabled); form.addRow('结束日期', end)
        def refresh():
            saved = self.daily_data.get('medSchedules', {}).get(select.currentData(), {})
            times.setText(', '.join(saved.get('times', [])))
            start.setDate(QDate.fromString(saved.get('start', date.today().isoformat()), 'yyyy-MM-dd'))
            has_end.setChecked(bool(saved.get('end')))
            end.setDate(QDate.fromString(saved.get('end') or date.today().isoformat(), 'yyyy-MM-dd'))
        select.currentIndexChanged.connect(refresh); refresh()
        note = label('时间由你按已有医嘱填写。仅在本机展示安排，没有发送手机提醒。', 'productMuted'); form.addRow(note)
        controls = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel); form.addRow(controls)
        controls.rejected.connect(dialog.reject); controls.accepted.connect(dialog.accept)
        if dialog.exec() == QDialog.Accepted:
            clock = [t.strip() for t in times.text().replace('，', ',').split(',') if t.strip()]
            self._request('daily.medSchedule', dict(medId=select.currentData(), times=clock, start=start.date().toString('yyyy-MM-dd'), end=end.date().toString('yyyy-MM-dd') if has_end.isChecked() else ''))

    def _record_dose(self, status):
        r = self.dose_table.currentRow()
        if not 0 <= r < len(getattr(self, 'visible_doses', [])):
            self._message('请先选择具体的一次服药。'); return
        payload = dict(self.visible_doses[r]); payload['status'] = status
        self._request('daily.dose', payload)

    def _family_link(self):
        code, ok = QInputDialog.getText(self, '关联家人', '输入家人在其本机档案生成的邀请码（15 分钟内有效）')
        if ok and code.strip() and QMessageBox.question(self, '确认关联', '只建立关系，不自动开放任何健康资料。确认关联？') == QMessageBox.Yes:
            self._request('daily.familyBind', {'code': code})

    def _selected_member(self):
        r = self.linked_family.currentRow()
        members = self.snapshot.get('familyMembers', [])
        if not 0 <= r < len(members):
            self._message('请先选择一位家人。'); return None
        return members[r]

    def _family_categories(self):
        member = self._selected_member()
        if not member:
            return
        dialog = QDialog(self); dialog.setWindowTitle('我向 ' + member['name'] + ' 共享哪些信息'); area = QVBoxLayout(dialog)
        area.addWidget(label('对方只能查看。取消全部勾选即撤销；聊天和附件不在共享范围。'))
        existing = self.daily_data.get('grants', {}).get(member['ownerId'], [])
        checks = {}
        for key, title in CATEGORY_NAMES.items():
            c = QCheckBox(title); c.setChecked(key in existing); area.addWidget(c); checks[key] = c
        controls = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel); area.addWidget(controls)
        controls.rejected.connect(dialog.reject); controls.accepted.connect(dialog.accept)
        if dialog.exec() == QDialog.Accepted:
            self._request('daily.familyGrant', {'member': member['ownerId'], 'categories': [k for k, c in checks.items() if c.isChecked()]})

    def _family_disconnect(self):
        member = self._selected_member()
        if member and QMessageBox.question(self, '解除关联', '解除与 ' + member['name'] + ' 的本机关联，并撤销双向共享？') == QMessageBox.Yes:
            self._request('daily.familyUnbind', {'member': member['ownerId']})

    def _read_family(self):
        from .product_widgets import display_time
        from .product_window import METRIC_LABELS
        member = self._selected_member()
        if not member:
            return
        lines = ['对方未开放资料。关系建立不等于共享。'] if not member['categories'] else ['仅本人主动共享的信息；只读。']
        for key in ('health', 'rehab'):
            if key in member['categories']:
                lines.append(CATEGORY_NAMES[key])
                for record in member.get(key, []):
                    text=record['text']
                    metric,separator,value=text.partition(': ')
                    if key=='health' and separator and metric in METRIC_LABELS:text=METRIC_LABELS[metric][0]+'：'+value
                    lines.append(display_time(record['timestamp'])+' · '+text)
                if not member.get(key):lines.append('暂无已共享记录；不能据此判断健康状态。')
        if 'medication' in member['categories']:
            lines.append('近期用药记录')
            lines += [r['date'] + ' ' + r['time'] + ' · ' + r.get('medName', '药物') + ' · ' + {'taken': '已服用', 'skipped': '已跳过', 'unrecorded': '未记录'}.get(r['status'], '待核对') for r in member.get('doses', [])] or ['暂无共享的逐次用药记录。']
        self._detail(member['name'] + ' · 近况', lines)

    def _experience_schedule_render(self):
        if not hasattr(self, 'rehab_day'):
            return
        day = self.rehab_day.date().toString('yyyy-MM-dd')
        self.visible_schedule = sorted([e for e in self.daily_data.get('schedules', []) if e['date'] == day], key=lambda e: e['time'])
        def state(entry):
            if entry['date']>date.today().isoformat():return '已安排'
            records=self._rehab_data('rehab.get_recent_assessments' if entry['kind']=='assessment' else 'rehab.get_training_history')
            matched=[]
            for record in records:
                try:
                    when=datetime.fromisoformat(record.get('end_utc','').replace('Z','+00:00')).astimezone()
                    if when.date().isoformat()!=entry['date'] or when.strftime('%H:%M')<entry['time']:continue
                except (ValueError,TypeError):continue
                ref=record.get('plan_reference',{})
                if entry['kind']=='assessment' or (ref.get('id'),ref.get('revision'))==(entry.get('planId'),entry.get('revision')):matched.append(record)
            if matched:return '已有 '+str(len(matched))+' 条保存记录（详情见健康）'
            return '尚无匹配记录' if entry['date']<date.today().isoformat() else '等待评估' if entry['kind']=='assessment' else '等待执行'
        rows(self.schedule_table, [(e['time'], e['name'],state(e)) for e in self.visible_schedule], keys=[e['id'] for e in self.visible_schedule])
        self.schedule_empty.setVisible(not self.visible_schedule); self.schedule_table.setVisible(bool(self.visible_schedule))

    def _experience_doses_render(self):
        if not hasattr(self, 'med_day'):
            return
        day = self.med_day.date().toString('yyyy-MM-dd')
        meds = self.snapshot.get('profile', {}).get('profile', {}).get('medicationRecords', [])
        values = {}
        for med in meds:
            schedule = self.daily_data.get('medSchedules', {}).get(med['id'])
            if med['status'] == 'active' and schedule and schedule['start'] <= day and (not schedule['end'] or day <= schedule['end']):
                for t in schedule['times']:
                    values[med['id'] + '|' + day + '|' + t] = dict(medId=med['id'], date=day, time=t, medName=med['name'], dose=med.get('dose', ''), status='unrecorded')
        # Saved facts stay visible after schedule edits or archiving the medicine.
        values.update({k: v for k, v in self.daily_data.get('doses', {}).items() if v['date'] == day})
        self.visible_doses = sorted(values.values(), key=lambda e: (e['time'], e.get('medName', '')))
        names = {'taken': '已服用', 'skipped': '已跳过', 'unrecorded': '未记录'}
        rows(self.dose_table, [(v['time'], v.get('medName', '药物'), v.get('dose') or '未填写', names[v['status']]) for v in self.visible_doses], keys=[v['medId'] + '|' + v['date'] + '|' + v['time'] for v in self.visible_doses])
        self.dose_empty.setVisible(not values); self.dose_table.setVisible(bool(values))
        from .product_widgets import display_time
        rows(self.dose_history, [(display_time(e['at']), e['record']['date'] + ' ' + e['record']['time'] + ' · ' + e['record'].get('medName', '药物'), names[e['record']['previous']] + ' → ' + names[e['record']['status']]) for e in self.daily_data.get('doseAudit', [])])
        self.dose_history.setVisible(bool(self.daily_data.get('doseAudit')))

    def _experience_render(self):
        self.daily_data = self.snapshot.get('dailyProduct', {})
        profile = self.snapshot['profile']['profile']
        self.home_hello.setText(profile['name'] + '，今天好。')
        name=profile['name']
        self.account_button.setText((name[:10]+'…' if len(name)>10 else name) + ' · 我的档案')
        self.account_button.setToolTip(name+' · 本机档案')
        self.home_intro.setText('和管家说说近况，或查看今天的康复与用药安排。')
        entries = sorted([e for e in self.daily_data.get('schedules', []) if e['date'] == date.today().isoformat()], key=lambda e: e['time'])
        self._experience_doses_render()
        today_doses = [v for v in self.daily_data.get('doses', {}).values() if v['date'] == date.today().isoformat()]
        med_count = 0
        for med in profile.get('medicationRecords', []):
            schedule = self.daily_data.get('medSchedules', {}).get(med['id'])
            if med['status'] == 'active' and schedule and schedule['start'] <= date.today().isoformat() and (not schedule['end'] or date.today().isoformat() <= schedule['end']):
                med_count += len(schedule['times'])
        import html
        lines=[(e['time'],'rehab',e['name']) for e in entries]
        for med in profile.get('medicationRecords',[]):
            schedule=self.daily_data.get('medSchedules',{}).get(med['id'])
            if med['status']=='active' and schedule and schedule['start']<=date.today().isoformat() and (not schedule['end'] or date.today().isoformat()<=schedule['end']):
                for clock in schedule['times']:
                    dose=self.daily_data.get('doses',{}).get(med['id']+'|'+date.today().isoformat()+'|'+clock,{})
                    lines.append((clock,'medication',med['name']+' · '+{'taken':'已服用','skipped':'已跳过','unrecorded':'未记录'}.get(dose.get('status'),'未记录')))
        lines.sort()
        text='<br><br>'.join('<a href="'+key+'">'+html.escape(clock+'  '+name)+'</a>' for clock,key,name in lines[:4])
        if len(lines)>4:text+='<br><br>还有 '+str(len(lines)-4)+' 项安排，进入对应页面查看。'
        if not text:
            upcoming=sorted((e for e in self.daily_data.get('schedules',[]) if e['date']>date.today().isoformat()),key=lambda e:(e['date'],e['time']))
            text=('今天没有康复安排。下一次：<a href="rehab">'+html.escape(upcoming[0]['date']+' '+upcoming[0]['time']+' '+upcoming[0]['name'])+'</a>') if upcoming else '今天还没有安排。可到康复制定计划，或到用药设置服用时间。'
        color=self.product_theme.colors['text']
        self.home_schedule.setText(text.replace('<a href=', '<a style="color:'+color+';" href='))
        self.home_schedule.setMinimumHeight(max(72,32+len(lines[:4])*44))
        pending = [t for t in self.snapshot['state']['tasks'] if t['status'] in ('pending', 'in_progress')]
        self.home_attention.setText('需要确认：' + '；'.join(t['title'] for t in pending[:2]) if pending else '')
        self.interface_buttons['homeAllTasks'].setVisible(bool(pending))
        self.interface_buttons['homeInitialProfile'].setVisible(not bool(self.daily_data.get('onboarding')))
        selected = self.current_plan.currentData(); self.current_plan.blockSignals(True); self.current_plan.clear()
        for p in self._rehab_data('rehab.get_training_plan'):
            self.current_plan.addItem(p['name'] + ' · v' + str(p['revision']), p['id'])
        self.current_plan.setCurrentIndex(max(0, self.current_plan.findData(selected))); self.current_plan.blockSignals(False)
        self._experience_plan_change(); self._experience_schedule_render()
        has_plan=bool(self._selected_plan())
        visual(self.interface_buttons['rehabEvaluateNow'], appearance='secondary' if has_plan else 'primary')
        self.current_plan.setVisible(has_plan)
        for key in ('planSchedule','planPractice'):self.interface_buttons[key].setVisible(has_plan)
        for key in ('planManualCopy','planVersions'):self.interface_buttons[key].hide()
        self.interface_buttons['rehabPlanDetail'].setVisible(has_plan)
        for key in ('scheduleOpen','scheduleMove','scheduleRemove'):self.interface_buttons[key].setVisible(bool(self.visible_schedule))
        self.rehab_tables['训练计划'].hide(); self.rehab_summary['训练计划'].hide(); self.recovery_sections['flow'].hide()
        self.health_archive_profile.setText(profile['name'] + ' · ' + (str(profile['age']) + ' 岁' if profile['age'] else '年龄未填写') + '\n已知情况：' + ('、'.join(profile.get('conditions', [])) or '尚未填写') + '\n康复目标：' + (self.snapshot['profile'].get('rehabGoal') or '尚未填写') + '\n资料与图片：' + str(len(self.snapshot.get('attachments', []))) + ' 份')
        members = self.snapshot.get('familyMembers', [])
        rows(self.linked_family, [(m['name'], '、'.join(CATEGORY_NAMES[k].split('（')[0] for k in m['categories']) or '尚未开放', '、'.join(CATEGORY_NAMES[k].split('（')[0] for k in self.daily_data.get('grants', {}).get(m['ownerId'], [])) or '尚未开放') for m in members], keys=[m['ownerId'] for m in members])
        self.linked_empty.setVisible(not members); self.linked_family.setVisible(bool(members))
        for key in ('familyReadOnly','familyCategories','familyDisconnect'):self.interface_buttons[key].setVisible(bool(members))
        skipped = [(m['name'], d) for m in members for d in m.get('doses', []) if d['status'] == 'skipped' and d['date'] == date.today().isoformat()]
        self.family_attention.setText('值得关注：' + '；'.join(name + ' 今天有已跳过的用药记录' for name, _ in skipped) if skipped else '暂无已共享的待关注事项；未更新不代表一切正常。')
        if hasattr(self,'home_week_preview'):
            from .product_structure import refresh
            refresh(self)

    def _daily_result(self, operation, result):
        if not isinstance(result, dict) or not result.get('dailyReceipt'):
            return False
        if 'code' in result:
            self._detail('我的本机邀请码', [result['code'], '15 分钟内有效，仅可使用一次。请切换到家人的本机档案确认关联。', '建立关系后，双方仍需分别选择共享范围。'])
        else:
            self._message('已保存本机安排，正在刷新。', severity='success')
        if operation=='daily.onboarding':
            answers=getattr(self,'onboarding_to_align',None)
            self.onboarding_to_align=None
            if answers and not answers['skipped']:
                from copy import deepcopy
                record=deepcopy(self.legacy.participant_records[self.owner])
                record['display_name']=self.snapshot['profile']['profile']['name']
                record['goals']=answers['goal']
                reason=answers['concern']
                if reason and reason!='一般活动能力恢复':record['reason']=record.get('reason') or reason
                restriction={'unknown':'问卷自报：活动限制尚未确认','discomfort':'问卷自报：目前有不适','restricted':'问卷自报：有医嘱或术后活动限制'}.get(answers['limitation'])
                if restriction:record['restrictions']=record.get('restrictions') or restriction
                if answers['mobility']=='needs_support':record['support']='assisted'
                self.legacy._send('save_participant',profile=record,expected_revision=record.get('revision',0))
                self.navigate('rehab',refresh=False)
                self._message('档案与首次评估安排已保存。完成有效评估后，管家才能生成动作计划。',severity='success')
        self._request('snapshot'); return True
