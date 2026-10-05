"""Product navigation and read-only presentation over existing services and rehab actions."""
from datetime import datetime, timedelta
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QComboBox,
    QDialog, QDialogButtonBox, QTextBrowser, QMessageBox, QFileDialog, QPushButton, QListWidget,
    QProgressBar, QScrollArea, QFrame, QStackedWidget)
from .product_widgets import label, button, card, table, rows, core_card, visual, ResponsiveGrid, WrappingLabel, display_time, ContentTabs
from .product_theme import SPACING, METRICS
from ..domain import SOURCES, CONTEXTS

# Published audit identities remain stable when widgets change parents.
STABLE_ACTION_IDS = dict(zip(
    ('首页','AI 康复管家','康复','健康','用药','家庭','记录','我需要帮助','新建用户','通知','设置',
     '我的训练计划','最近的评估结果','记录用药情况','发送','记录数值','记录身体感受 / 更正记录',
     '添加资料 / 图片 / 视频','导出所选附件','识别健康图片','确认识别结果并记录','编辑联系人',
     '生成本机邀请码','确认绑定','授权家庭共享','撤销共享','解绑','刷新家属摘要',
     '查看原康复历史与评估趋势','导出健康报告','核对可共享通知并建立台账','确认所选通知'),
    (0,1,2,3,4,5,6,7,8,9,10,199,200,201,202,77,75,69,70,71,72,37,40,41,42,43,44,45,32,31,27,28)))

MODULE_NAV_ACTIONS={'rehabWorkspaceBack','healthMetricsEntry','healthMetricsBack','medTodayActions','medTodayActionsBack'}
RECOVERY_NAV_ACTIONS={'recoveryAssessment','recoveryHistory','recoveryPlans','recoveryAsk','contextReturn'}


class ProductCompletion:
    def _action(self, layout, key, text, callback=None, *, kind='B', target='', reason=''):
        item = button(text, callback or (lambda:self._message(reason)))
        item.setObjectName(key)
        item.setProperty('actionId',key)
        item.setProperty('actionKind', 'C' if reason else kind)
        item.setProperty('actionTarget',target or reason)
        item.setProperty('unavailableReason',reason)
        if reason:
            item.setEnabled(False)
            item.setToolTip(reason)
        layout.addWidget(item)
        self.interface_buttons[key]=item
        return item

    def _home_page(self):
        box=self._page('home')
        self.greeting=visual(label('请建立或选择自己的资料。','productTitle'),typography='display')
        self.today_note=visual(label(),typography='secondary')
        box.addWidget(self.greeting);box.addWidget(self.today_note);box.addSpacing(16)
        columns=ResponsiveGrid(columns=2,threshold=960)
        primary=QWidget();left=QVBoxLayout(primary);left.setContentsMargins(0,0,24,0);left.setSpacing(24)
        item,area=core_card('接下来 · 康复训练',True)
        self.next_training=visual(label('今天暂无康复计划'),typography='section');area.addWidget(self.next_training)
        self.home_progress=QProgressBar();self.home_progress.setTextVisible(False)
        self.home_progress.setAccessibleName('当前计划累计进度');area.addWidget(self.home_progress)
        actions=QHBoxLayout()
        for key,text,call in [('homeContinue','继续训练',self._continue_training),
            ('homePlans','查看训练计划',lambda:self._rehab_action('plans')),
            ('homeAsk','问康复管家',self._open_global_assistant)]:
            visual(self._action(actions,key,text,call,target='康复/训练计划' if key=='homePlans' else text),appearance='primary' if key=='homeContinue' else 'ghost')
        actions.addStretch();area.addLayout(actions);left.addWidget(item)
        item,area=core_card('需要你确认')
        self.tasks=QListWidget();self.tasks.setMinimumHeight(100);self.tasks.setMaximumHeight(136)
        self.tasks_empty=visual(label('今天没有待完成任务'),typography='secondary')
        area.addWidget(self.tasks_empty);area.addWidget(self.tasks)
        row=QHBoxLayout()
        self._action(row,'taskComplete','确认完成',lambda:self._task_status('completed'),kind='A',target='task.status')
        visual(self._action(row,'taskDismiss','暂不处理',lambda:self._task_status('dismissed'),kind='A',target='task.status'),appearance='ghost')
        row.addStretch();area.addLayout(row);left.addWidget(item)
        item,area=core_card('已保存的训练计划')
        self.plan_table=table(['当前保存的计划','是否可继续']);self.plan_table.setProperty('compactSummary',True)
        area.addWidget(self.plan_table);left.addWidget(item);left.addStretch();columns.add(primary)
        secondary=QWidget();right=QVBoxLayout(secondary);right.setContentsMargins(0,0,0,0);right.setSpacing(12)
        right.addWidget(visual(label('今日概况'),typography='section'));self.tile_values={}
        for key,title in [('plan','康复'),('medication','用药'),('tasks','任务'),('health','健康')]:
            item,area=core_card();area.setContentsMargins(0,6,0,6);area.setSpacing(4);heading=QHBoxLayout();heading.addWidget(visual(label(title),typography='card'))
            entry={'medication':('homeMedication','查看用药',lambda:self.navigate('medication')),
                'tasks':('homeTasks','查看今日任务',self._show_today_tasks),
                'health':('homeHealth','查看健康状态',lambda:self._health_tab(0))}.get(key)
            heading.addStretch()
            if entry:
                k,text,call=entry;visual(self._action(heading,k,text,call,target=text),appearance='ghost')
            area.addLayout(heading);self.tile_values[key]=visual(label('正在读取…'),typography='secondary')
            area.addWidget(self.tile_values[key]);right.addWidget(item)
        item,area=core_card('近期身体状况')
        self.home_status=visual(label('尚无记录，无法判断当前健康状态。'),typography='body');area.addWidget(self.home_status)
        row=QHBoxLayout()
        visual(self._action(row,'homeAI','查看管家摘要与对话',lambda:self.navigate('assistant'),target='AI 康复管家'),appearance='ghost')
        visual(self._action(row,'homeProfile','建立 / 编辑资料',self._profile,kind='A',target='profile.save'),appearance='ghost')
        row.addStretch();area.addLayout(row);right.addWidget(item);right.addStretch();columns.add(secondary)
        box.addWidget(columns);box.addStretch()

    def _rehab_page(self):
        page=QWidget();box=QVBoxLayout(page);box.setContentsMargins(0,0,0,0)
        self.rehab_sections=QStackedWidget();box.addWidget(self.rehab_sections,1)
        overview=QWidget();overview.setProperty('visualScope','core')
        overview_box=QVBoxLayout(overview);overview_box.setContentsMargins(0,0,0,0);overview_box.setSpacing(SPACING['sm'])
        top=QHBoxLayout()
        self._action(top,'rehabHome','返回首页',lambda:self.navigate('home'),target='首页')
        self._action(top,'rehabPerson','个人康复信息',self.legacy._edit_participant,kind='A',target='原参与者档案')
        self._interface_button(top,'silverRehab','银发健康守护',self._open_silver)
        self._action(top,'rehabOverview','收起概览',self._toggle_rehab_overview,target='收起/展开康复概览，保留训练工作区')
        for index in range(top.count()):
            widget=top.itemAt(index).widget()
            if widget:visual(widget,appearance='ghost')
        overview_box.addLayout(top)
        self.rehab_tabs=QTabWidget()
        self.rehab_summary={};self.rehab_tables={}
        definitions=[('今日恢复',['动作','恢复流程（计划累计）','目标']),('康复评估',['时间','动作 / 侧别','有效性']),
                     ('训练计划',['计划','累计完成情况','创建时间']),('康复进度',['时间','训练','完成 / 反馈'])]
        for title,headers in definitions:
            sub=QWidget();area=QVBoxLayout(sub)
            area.setSpacing(SPACING['sm']);area.setContentsMargins(*([SPACING['lg']]*4))
            self.rehab_summary[title]=visual(label('正在读取…'),typography='body');area.addWidget(self.rehab_summary[title])
            if title=='今日恢复':
                self.rehab_progress=QProgressBar();self.rehab_progress.setTextVisible(False)
                self.rehab_progress.setAccessibleName('当前计划累计进度');area.addWidget(self.rehab_progress)
            self.rehab_tables[title]=table(headers);self.rehab_tables[title].setMinimumHeight(90)
            if title=='今日恢复':self.rehab_tables[title].setProperty('compactSummary',True)
            area.addWidget(self.rehab_tables[title])
            row=QHBoxLayout()
            if title=='今日恢复':
                self._action(row,'rehabContinue','继续训练',self._continue_training,target='原训练准备与确认')
                self._action(row,'rehabAction','查看下一项 / 动作目录',self._show_training_action,target='原动作目录')
                self._action(row,'rehabStart','开始训练',self._start_existing_training,kind='A',target='原 Runtime.start')
            elif title=='康复评估':
                self._action(row,'rehabAssess','开始新评估',lambda:self._rehab_action('assessment'),target='原康复评估')
                self._action(row,'rehabAssessmentDetail','查看详情',lambda:self._rehab_detail('assessment'),target='原 report')
                self._action(row,'rehabBody','身体档案与测量条件',lambda:self._rehab_action('body'),target='原 Body Profile')
            elif title=='训练计划':
                self._action(row,'rehabLibrary','我的训练计划',self._plan_library,target='原计划库')
                self._action(row,'rehabAutomatic','根据评估自动安排',self._automatic_plan,target='原自动计划/接受/准备')
                self._action(row,'rehabPlanDetail','查看计划详情',self._plan_detail,target='保存的计划读模型')
            else:
                self._action(row,'rehabTrainingDetail','训练详情 / 反馈',lambda:self._rehab_detail('training'),target='原 report/反馈')
                self._action(row,'rehabProgress','评估变化 / 完整历史',lambda:self._rehab_action('history'),target='原可比历史')
                self._action(row,'rehabReports','报告',lambda:self._rehab_detail('training'),target='原 report')
            for index in range(row.count()):
                widget=row.itemAt(index).widget()
                if widget:visual(widget,appearance='primary' if widget.objectName() in ('rehabContinue','rehabAssess','rehabAutomatic') else 'secondary')
            row.addStretch();area.addLayout(row)
            if title=='今日恢复':
                # Put the primary action before the plan table in the reading order.
                area.removeWidget(self.rehab_tables[title]);area.addWidget(self.rehab_tables[title])
                self.recovery_fields={};details=ResponsiveGrid(columns=1,threshold=0)
                for key,heading in [('flow','今日恢复流程'),('result','最近训练结果'),('assessment','最近评估'),('trend','恢复趋势')]:
                    section,section_box=core_card(heading);section_box.setContentsMargins(0,12,0,8)
                    field=WrappingLabel('正在读取…');field.setWordWrap(True);visual(field,typography='body')
                    field.setObjectName('recovery-'+key);self.recovery_fields[key]=field;section_box.addWidget(field);details.add(section)
                area.addWidget(details)
                shortcuts=QHBoxLayout()
                self._action(shortcuts,'recoveryAssessment','新评估 / 查看详情',lambda:self.rehab_tabs.setCurrentIndex(1),target='康复评估')
                self._action(shortcuts,'recoveryHistory','历史训练 / 反馈',lambda:self.rehab_tabs.setCurrentIndex(3),target='康复进度')
                self._action(shortcuts,'recoveryPlans','安排训练计划',lambda:self.rehab_tabs.setCurrentIndex(2),target='训练计划')
                self._action(shortcuts,'recoveryAsk','问问康复管家',self._open_global_assistant,target='同一用户管家侧栏')
                area.addLayout(shortcuts)
            scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.NoFrame);scroll.setWidget(sub)
            self.rehab_tabs.addTab(scroll,title)
        overview_box.addWidget(self.rehab_tabs,1);self.rehab_sections.addWidget(overview)
        # Original cameras, dual-camera, report and training UI keep their native layout.
        # A scroll boundary lets 1024px windows use it without shrinking its controls.
        self.rehab_workspace=QScrollArea();self.rehab_workspace.setWidgetResizable(True)
        self.rehab_workspace.setFrameShape(QFrame.NoFrame)
        self.rehab_workspace.setWidget(self.legacy)
        workspace=QWidget();workspace_box=QVBoxLayout(workspace);workspace_box.setContentsMargins(0,0,0,0)
        self._action(workspace_box,'rehabWorkspaceBack','返回今日恢复',self._return_recovery,target='今日恢复，刷新已保存数据')
        workspace_box.addWidget(self.rehab_workspace,1);self.rehab_sections.addWidget(workspace)
        self.rehab_tabs.currentChanged.connect(self._rehab_tab_changed)
        self.pages.addWidget(page);self.page_widgets['rehab']=page

    def _medication_page(self):
        box=self._page('medication');self.medication_tabs=QTabWidget();box.addWidget(self.medication_tabs)
        def tab(title):
            p=QWidget();area=QVBoxLayout(p);area.setAlignment(Qt.AlignTop);self.medication_tabs.addTab(p,title);return area
        area=tab('今日用药');self.medication_today=label('暂无用药安排');area.addWidget(self.medication_today)
        self.med_today_sections=QStackedWidget();area.addWidget(self.med_today_sections)
        overview=QWidget();today_box=QVBoxLayout(overview)
        self.today_medications=table(['药物','已有剂量','已有时间 / 频次','状态']);today_box.addWidget(self.today_medications)
        today_actions=QHBoxLayout();today_box.addLayout(today_actions)
        self._action(today_actions,'medTodayDetail','查看用药详情',lambda:self._medication_detail(self.today_medications),target='药物档案')
        visual(self._action(today_actions,'medTodayActions','核对 / 记录今日用药',lambda:self.med_today_sections.setCurrentIndex(1),target='今日用药操作'),appearance='primary');today_actions.addStretch()
        self._action(today_actions,'medBack','返回首页',lambda:self.navigate('home'),target='首页')
        self.med_today_sections.addWidget(overview)
        detail=QWidget();detail_box=QVBoxLayout(detail)
        self._action(detail_box,'medTodayActionsBack','返回今日用药',lambda:self.med_today_sections.setCurrentIndex(0),target='今日用药概览')
        detail_box.addWidget(label('请先按已有医嘱核对今日安排，再记录本人确认或漏服。'))
        self._action(detail_box,'medConfirm','本人确认今日用药已核对',self._confirm_medication,kind='A',target='task.status')
        self._action(detail_box,'medDose','标记某一剂已服用',reason='当前只支持每日核对，不支持逐药逐剂确认。')
        detail_box.addWidget(label('当前只支持每日核对，不支持逐药逐剂确认。'))
        self._action(detail_box,'medMiss','记录漏服',lambda:self._send_chat('今天漏服了药'),kind='A',target='chat')
        detail_box.addStretch();self.med_today_sections.addWidget(detail)
        area=tab('我的药物');self.medications=table(['药物','已有剂量','用途','时间 / 频次','状态']);area.addWidget(self.medications)
        self.medication_empty=label('暂无药物档案，请按已有医嘱添加。');area.addWidget(self.medication_empty)
        row=QHBoxLayout()
        for key,text,call in [('medAdd','新增',lambda:self._medication_edit()),('medEdit','编辑',lambda:self._medication_edit(edit=True)),
            ('medView','查看',lambda:self._medication_detail(self.medications)),('medStatus','停用 / 恢复',self._medication_status)]:
            self._action(row,key,text,call,kind='D' if key=='medStatus' else 'A' if key in ('medAdd','medEdit') else 'B',target='medication.status' if key=='medStatus' else 'medication.save' if key in ('medAdd','medEdit') else '药物档案详情')
        row.addStretch();area.addLayout(row)
        area=tab('用药历史');self.medication_history=table(['时间','事项','内容']);area.addWidget(self.medication_history)
        self.med_history_empty=label('暂无用药核对记录。');area.addWidget(self.med_history_empty)
        self._action(area,'medHistoryDetail','查看详情',lambda:self._table_detail(self.medication_history,'用药记录'),target='用药记录详情')
        area=tab('漏服记录');self.missed_medications=table(['时间','事项','内容']);area.addWidget(self.missed_medications)
        self.med_missed_empty=label('暂无已记录的漏服信息。');area.addWidget(self.med_missed_empty)
        self._action(area,'medMissedDetail','查看详情',lambda:self._table_detail(self.missed_medications,'漏服记录'),target='漏服记录详情')
        self._action(area,'medMissedAdd','记录漏服',lambda:self._send_chat('今天漏服了药'),kind='A',target='chat')
        box.addStretch()

    def _settings_page(self):
        box=self._page('settings');self.settings_tabs=ContentTabs();box.addWidget(self.settings_tabs)
        def tab(title):
            p=QWidget();area=QVBoxLayout(p);area.setAlignment(Qt.AlignTop);self.settings_tabs.addTab(p,title);return area
        area=tab('个人资料');self.profile_summary=label('请建立个人资料。');self.profile_summary.setMaximumHeight(120);area.addWidget(self.profile_summary)
        self._action(area,'settingsProfile','编辑个人资料与康复目标',self._profile,kind='A',target='profile.save')
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QCheckBox
        preference=QSettings('Ankang','ProductUI')
        self.reduce_motion=QCheckBox('减少界面动画');self.reduce_motion.setChecked(preference.value('reducedMotion',False,type=bool))
        self.reduce_motion.toggled.connect(lambda value:preference.setValue('reducedMotion',value));area.addWidget(self.reduce_motion)
        area=tab('数据与隐私');self.data_location=label('本机资料独立保存；清除前可导出备份。');area.addWidget(self.data_location)
        self._action(area,'settingsBackup','导出本人本地备份',self._backup,kind='A',target='lifecycle.export')
        self._action(area,'settingsClear','清除本人健康聊天与附件',self._clear,kind='D',target='lifecycle.clear')
        area.addWidget(label('清除健康记录、聊天、附件、共享许可和通知，保留药物档案及原康复记录。'))
        area=tab('家庭共享');self._action(area,'settingsSharing','我的照护圈 / 允许查看',lambda:self.navigate('family'),target='家庭')
        area=tab('设备与同步');self.capabilities_text=label();area.addWidget(self.capabilities_text)
        self._sync_controls(area)
        self._interface_button(area,'settingsDevices','查看设备与健康数据',self._open_devices)
        self._interface_button(area,'settingsRefresh','刷新连接状态',self._refresh_extensions)
        area=tab('通知');self._action(area,'settingsNotification','通知与渠道状态',lambda:self.navigate('notifications'),target='通知')
        area.addWidget(label('外部通知渠道尚未配置时不发送；允许查看、渠道接受和对端送达是不同状态。'))
        area=tab('开发者设置');area.addWidget(label('仅用于本机开发配置，不属于日常健康操作。'))
        self._action(area,'settingsDeveloper','打开开发者配置',self._developer,kind='D',target='工作区外模型凭据配置')
        self._action(box,'settingsHome','返回首页',lambda:self.navigate('home'),target='首页');box.addStretch()

    def _completion_setup(self):
        self.last_rehab_tab=0;self.rehab_save_marker=None;self.filtered_entries=[];self.health_entries=[]
        self.page_states={};self.page_feedback={}
        for key,widget in self.page_widgets.items():
            # Explicit state belongs to each page, in addition to the global operation receipt.
            state=label('正在读取…');state.setObjectName('pageState-'+key)
            layout=widget.widget().layout() if hasattr(widget,'widget') else widget.layout()
            layout.insertWidget(0,state);self.page_states[key]=state
            if key in ('home','assistant','rehab'):visual(state,typography='caption')
        for i,title in enumerate(('当前状态','健康记录','健康档案','设备')):
            self.health_tabs.setTabText(i,title)
        area=self.health_tabs.widget(0).layout()
        self.health_rehab_summary=label();area.insertWidget(0,self.health_rehab_summary)
        area=self.health_tabs.widget(1).layout();self.health_filter=QComboBox();self.health_filter.setMaximumWidth(260)
        self.health_filter.addItems(['全部','身体感受','健康指标','检验结果','用药'])
        area.insertWidget(0,self.health_filter);self.health_filter.currentTextChanged.connect(self._filter_health)
        self.health_empty=label('暂无健康记录。');area.addWidget(self.health_empty)
        self._action(area,'healthDetail','查看记录详情',self._health_detail,target='HealthEvent 用户可读详情')
        area=self.health_tabs.widget(2).layout()
        self._action(area,'archiveProfile','基础健康资料',self._profile,kind='A',target='profile.save')
        self._action(area,'archiveDetail','查看资料详情',self._attachment_detail,target='archive metadata')
        self.archive_empty=label('暂无健康资料，可上传图片、报告或视频。');area.addWidget(self.archive_empty)
        self._action(self.health_tabs.widget(3).layout(),'deviceData','查看设备数据',lambda:self._health_tab(1),target='健康记录')
        self._action(self.health_tabs.widget(3).layout(),'deviceConnect','连接 / 导入',self._device_connection_help,target='实际设备导入与配置说明')
        self.devices_table=table(['设备 / 数据来源','当前状态','使用范围'])
        self.health_tabs.widget(3).layout().insertWidget(0,self.devices_table)
        self._action(self.assistant_tools,'assistantRehab','去康复页面',lambda:self._rehab_action('training'),target='康复/今日训练')
        self._action(self.assistant_tools,'assistantNew','清空 / 新会话',reason='当前没有只重置对话的接口；可使用本轮不记录，或在设置管理本人数据。')
        self.assistant_tools.addWidget(visual(label('当前没有只重置对话的接口；清除全部健康数据须在设置另行确认。'),typography='caption'))
        self.history_tabs=self.timeline.parentWidget()
        while not isinstance(self.history_tabs,QTabWidget):self.history_tabs=self.history_tabs.parentWidget()
        history_actions=QHBoxLayout();self.history_tabs.widget(0).layout().addLayout(history_actions)
        self._action(history_actions,'historyDetail','查看详情',self._history_detail,target='统一记录详情/原康复报告')
        self._action(history_actions,'historyTrends','趋势',self._history_trends,target='健康趋势/原康复纵向记录')
        self._action(history_actions,'historyReport','报告',self._history_report,target='健康报告/原康复报告')
        self._action(history_actions,'historyExport','导出当前筛选记录',self._export_timeline,kind='A',target='本机导出只读视图')
        history_actions.addStretch()
        self.history_empty=label('暂无记录。');self.history_tabs.widget(0).layout().addWidget(self.history_empty)
        area=self.family_management_layout
        self.family_members=table(['成员 / 联系人','关系','绑定状态','允许查看']);self.family_members.setProperty('compactSummary',True)
        self.family_empty=label('暂无家庭联系人。请先添加联系人，绑定与共享需分别确认。')
        area.insertWidget(0,self.family_empty);area.insertWidget(0,self.family_members)
        self._action(area,'familyDetail','查看成员 / 允许查看',self._family_detail,target='家庭成员详情/FamilyService')
        self._action(area,'familySharingRecords','查看共享记录',lambda:self.navigate('notifications'),target='通知/共享记录')
        self._action(area,'familyTemporary','临时 / 逐字段授权',reason='当前仅支持整体长期共享及原管家共享意图，暂不提供逐成员逐字段授权表单。')
        area.addWidget(label('当前仅支持一个绑定关系及整体共享许可，临时 / 逐字段授权表单暂未提供。'))
        self.family_members.cellDoubleClicked.connect(lambda *_:self._family_detail())
        self.timeline.cellDoubleClicked.connect(lambda *_:self._history_detail())
        self.health_timeline.cellDoubleClicked.connect(lambda *_:self._health_detail())
        self.attachments.cellDoubleClicked.connect(lambda *_:self._attachment_detail())
        self.notifications.setColumnCount(5)
        self.notifications.setHorizontalHeaderLabels(['时间','事项','类型','渠道结果','确认状态'])
        area=self.notifications.parentWidget().layout()
        self.notification_filter=QComboBox();self.notification_filter.setMaximumWidth(260);self.notification_filter.addItems(['全部','未确认','已确认'])
        area.insertWidget(0,self.notification_filter);self.notification_filter.currentTextChanged.connect(self._render_notifications)
        self.notification_empty=label('暂无通知。');area.addWidget(self.notification_empty)
        notification_actions=QHBoxLayout();area.addLayout(notification_actions)
        self._action(notification_actions,'notificationDetail','打开通知 / 查看详情',self._notification_detail,target='通知详情')
        self._action(notification_actions,'notificationBusiness','进入对应业务页面',self._notification_business,target='用药/健康/家庭')
        notification_actions.addStretch()
        self.notifications.cellDoubleClicked.connect(lambda *_:self._notification_detail())
        for widget in (self.medications,self.today_medications,self.family_members,self.attachments,self.timeline,self.health_timeline,self.notifications):
            widget.itemSelectionChanged.connect(self._completion_controls)
        self.tasks.itemSelectionChanged.connect(self._completion_controls)
        self._register_existing_actions()
        self._completion_controls()

    def _detail(self,title,lines,actions=()):
        if getattr(self,'last_detail',None):self.last_detail.close()
        dialog=QDialog(self);dialog.setWindowTitle(title);dialog.resize(650,480)
        area=QVBoxLayout(dialog);text=QTextBrowser();text.setPlainText('\n'.join(lines));area.addWidget(text)
        for caption,callback in actions:
            item=button(caption,lambda checked=False,call=callback:(dialog.accept(),call()))
            item.setProperty('actionId','detail-'+caption)
            item.setProperty('actionKind','D' if caption in ('允许长期共享','撤销共享') else 'A' if caption in ('导出所选附件','查看家属摘要','本人确认已查看','修改联系人','导入设备数据') else 'B')
            item.setProperty('actionTarget',{'允许长期共享':'family.grant','撤销共享':'family.revoke','导出所选附件':'archive.read','查看家属摘要':'family.summary','本人确认已查看':'notification.ack','修改联系人':'profile.save','导入设备数据':'device.import'}.get(caption,caption))
            area.addWidget(item)
        close=QDialogButtonBox(QDialogButtonBox.Close);close.rejected.connect(dialog.reject);area.addWidget(close)
        close_button=close.button(QDialogButtonBox.Close)
        close_button.setProperty('actionId','detailClose');close_button.setProperty('actionKind','B');close_button.setProperty('actionTarget','关闭详情返回原页面')
        self.detail_owner=self.owner
        dialog.setAttribute(Qt.WA_DeleteOnClose);dialog.show();self.last_detail=dialog
        dialog.finished.connect(lambda *_:setattr(self,'last_detail',None))
        self._message('已打开'+title+'，关闭可返回原页面。')
        return dialog

    def _table_detail(self,widget,title):
        r=widget.currentRow()
        if r<0:
            self._message('请先选择要查看的记录。');return
        lines=[widget.horizontalHeaderItem(c).text()+'：'+widget.item(r,c).text() for c in range(widget.columnCount()) if widget.item(r,c)]
        self._detail(title,lines)

    def _medication_detail(self,widget):
        self._table_detail(widget,'用药详情（已有医嘱资料）')

    def _attachment_detail(self):
        r=self.attachments.currentRow();entries=self.snapshot.get('attachments',[])
        if not 0<=r<len(entries):
            self._message('请先选择资料。');return
        entry=entries[r]
        self._detail('健康资料详情',[entry['name'],'文件：'+entry['fileName'],'分类：'+entry['category'],
            '保存时间：'+entry['date'],'可见性：仅本人' if entry['visibility']=='private' else '可用于获准家属摘要',
            '图片 / 视频内容可导出至本机查看；附件本身不等于健康识别结论。'],[('导出所选附件',self._export_attachment)])

    def _family_detail(self):
        p=self.snapshot.get('profile',{}).get('profile',{})
        if not p.get('familyContact') and not self.snapshot.get('family',{}).get('familyLink'):
            self._message('暂无家庭成员或绑定关系，请先编辑联系人。');return
        family=self.snapshot['family'];allowed=self.snapshot['projection']['canViewSharedDetail']
        self._detail('我的照护圈 · 成员详情',[p.get('familyContact') or '已绑定家属','关系：家庭照护联系人',
            '联系电话：'+(p.get('familyPhone') or '未填写'),
            '允许查看：已授权且允许共享的健康摘要、记录与照护任务' if allowed else '允许查看：尚未开放',
            '私密记录不会进入家属摘要。康复详情未通过家庭共享接口开放。',
            '当前仅支持一个绑定关系及整体共享许可；临时 / 逐字段授权暂未提供。'],
            [('允许长期共享',lambda:self._consent(True)),('撤销共享',lambda:self._consent(False)),('修改联系人',self._profile),('查看家属摘要',lambda:self._request('family.summary'))])

    def _unbind_family(self):
        if QMessageBox.question(self,'解除绑定','解除当前家庭绑定并关闭共享范围，确认继续？')==QMessageBox.Yes:
            self._request('family.unbind')

    def _plan_notifications(self):
        if QMessageBox.question(self,'核对可共享通知','依据已有共享许可建立台账；外部渠道已配置时会向该渠道提交通知。确认继续？')==QMessageBox.Yes:
            self._request('notification.plan')

    def _health_tab(self,index):
        if self.navigate('health'): self.health_tabs.setCurrentIndex(index)

    def _show_today_tasks(self):
        if self.navigate('home'):
            self.page_widgets['home'].ensureWidgetVisible(self.tasks)
            self.tasks.setFocus();self._message('已定位今日任务，选择任务后可确认或暂不处理。')

    def _device_connection_help(self):
        self._detail('设备连接 / 导入',[self.device_status.text(),
            '康复摄像头：进入康复输入设置，选择设备后测试；不会自动开启。',
            '通用设备：导入符合当前用户编号的设备导出 JSON，或读取已配置数据源。',
            'Apple Health：需要 iPhone 端授权与已配置的数据来源。',
            '特殊硬件：当前仅保留数据接入接口，没有独立厂商连接驱动。'],
            [('导入设备数据',self._import_device_file),('摄像头 / 回放设置',lambda:self._rehab_action('assessment'))])

    def _continue_training(self):
        if not self._rehab_action('training'): return
        plans=self._rehab_data('rehab.get_training_plan')
        if not plans:
            self._message('今天暂无康复计划。可先做评估，再使用下方自动安排或训练计划库。');return
        if plans[0].get('record_origin')=='assessment_rules': self.legacy._open_automatic_plan()
        else: self.legacy._open_plan_library()

    def _start_existing_training(self):
        if not self.legacy.start_button.isEnabled():
            self._message('请先通过原训练准备流程打开输入并确认条件。');return
        self._show_rehab_scope(True)
        self.legacy.start_button.click();self._message('已请求开始训练，请查看实时训练状态。')

    def _show_training_action(self):
        plans=self._rehab_data('rehab.get_training_plan')
        if not plans:
            self._rehab_action('assessment');self._message('暂无下一项计划，可在动作目录查看动作。');return
        progress=plans[0]['progress'];item=next((i for i in plans[0]['items'] if i['key']==progress['next_key']),None)
        if item and self._rehab_action('assessment'):
            self.legacy._choose_catalog_exercise(item['exercise_id']);self._message('已打开动作说明；此入口查看评估动作，不绕过训练准备。')
        elif not item: self._message('当前计划已全部完成。')

    def _plan_library(self):
        if self._rehab_action('plans'): self.legacy._open_plan_library()

    def _automatic_plan(self):
        if self._rehab_action('plans'): self.legacy._open_automatic_plan()

    def _plan_detail(self):
        plans=self._rehab_data('rehab.get_training_plan');r=self.rehab_tables['训练计划'].currentRow()
        if not 0<=r<len(plans): self._message('请先选择训练计划。');return
        p=plans[r];self._detail('训练计划详情',[p['name'],'创建时间：'+str(p.get('created_utc') or '未记录'),
            '周期：当前未提供按周排期；下面是保存的项目安排。',
            *[i['exercise_label']+' · '+('左侧' if i['side']=='left' else '右侧' if i['side']=='right' else '双侧 / 不分侧')+' · '+self._plan_settings(i['settings']) for i in p['items']]],
            [('进入原计划库',self._plan_library)])

    def _rehab_tab_changed(self,index):
        # Summary tabs are navigation only; actual work starts via existing actions.
        if self._rehab_locked():
            self.rehab_tabs.blockSignals(True);self.rehab_tabs.setCurrentIndex(self.last_rehab_tab);self.rehab_tabs.blockSignals(False)
        else: self.last_rehab_tab=index

    def _rehab_locked(self):
        return self.legacy.busy or self.legacy._camera_testing or self.legacy.state in ('CONNECTING','PREVIEW','ONLINE','SAVE_FAILED')

    def _show_rehab_scope(self,workspace):
        if not workspace and self._rehab_locked():
            self._message('请先结束并保存当前任务，关闭摄像头测试，再返回概览。')
            return False
        self.rehab_overview_collapsed=workspace
        self.rehab_sections.setCurrentIndex(1 if workspace else 0)
        self.interface_buttons['rehabOverview'].setText('展开概览' if workspace else '收起概览')
        return True

    def _return_recovery(self):
        if self._show_rehab_scope(False):
            self.rehab_tabs.setCurrentIndex(0)
            if not self.pending:self._request('snapshot')
            else:self.refresh_needed=True
            self._message('已返回今日恢复，正在读取已保存的训练和反馈。')

    def _toggle_rehab_overview(self):
        collapsed=not getattr(self,'rehab_overview_collapsed',False)
        if self._show_rehab_scope(collapsed):
            self._message('已进入原康复工作区，可使用评估、训练及摄像头设置。' if collapsed else '已返回康复概览。')

    def _rehab_data(self,key):
        return self.snapshot.get('rehabilitation_ui',self.snapshot.get('rehabilitation',{})).get(key,{}).get('records',[])

    def _rehab_detail(self,kind):
        records=self._rehab_data('rehab.get_recent_assessments' if kind=='assessment' else 'rehab.get_training_history')
        r=self.rehab_tables['康复评估' if kind=='assessment' else '康复进度'].currentRow()
        if not 0<=r<len(records): self._message('请先选择记录。');return
        self._open_original_report(records[r].get('session_id') or records[r].get('id'))

    def _open_original_report(self,sid):
        source=self.active_page
        if not sid or not self._rehab_action('history'): return
        self._remember_return(source)
        self.legacy._send('report',id=sid);self._message('正在打开原康复报告，包含测量条件、反馈及已有导出入口。')

    def _history_detail(self):
        r=self.timeline.currentRow()
        if not 0<=r<len(self.filtered_entries):self._message('请先选择记录。');return
        entry=self.filtered_entries[r]
        actions=[]
        if entry[3] in ('康复','评估') and len(entry)>4:
            record=entry[4];sid=record.get('session_id') or record.get('id')
            actions=[('查看原报告 / 测量条件 / 反馈',lambda:self._open_original_report(sid))]
        self._detail('记录详情',[str(v) for v in entry[:3]],actions)

    def _history_report(self):
        r=self.timeline.currentRow()
        if 0<=r<len(self.filtered_entries) and self.filtered_entries[r][3] in ('康复','评估'):
            record=self.filtered_entries[r][4]
            self._open_original_report(record.get('session_id') or record.get('id'))
        elif self.history_filter.currentText() in ('康复','评估'):
            self._message('请先选择康复或评估记录，再打开对应报告。')
        else:self.history_tabs.setCurrentIndex(1)

    def _history_trends(self):
        r=self.timeline.currentRow()
        if self.history_filter.currentText() in ('康复','评估') or 0<=r<len(self.filtered_entries) and self.filtered_entries[r][3] in ('康复','评估'):
            if not 0<=r<len(self.filtered_entries):self._message('请先选择康复记录作为趋势基准。');return
            record=self.filtered_entries[r][4]
            if self._rehab_action('history'):
                self.rehab_trend_anchor=record.get('session_id') or record.get('id')
                self._remember_return('history')
        else:self.history_tabs.setCurrentIndex(1)

    def _health_detail(self):
        r=self.health_timeline.currentRow()
        if not 0<=r<len(getattr(self,'visible_health_events',[])):self._message('请先选择健康记录。');return
        e=self.visible_health_events[r]
        lines=['记录时间：'+e['timestamp'],'来源：'+self._source_label(e['source']),self._event_summary(e)]
        value=e.get('observation') or e.get('measurement') or e.get('labResult') or {}
        lines.append('可见性：仅本人' if value.get('visibility')=='private' else '可用于允许共享的摘要')
        self._detail('健康记录详情',lines,[('在管家中更正记录',lambda:self.navigate('assistant'))])

    def _export_timeline(self):
        filename,_=QFileDialog.getSaveFileName(self,'导出当前筛选记录','记录.txt','文本 (*.txt)')
        if filename:
            lines=['当前用户：'+self.owner,'筛选：'+self.history_filter.currentText()]
            lines += [' | '.join(str(v) for v in row[:3]) for row in self.filtered_entries]
            self._request('ui.file.write',{'path':filename,'text':'\n'.join(lines)})

    def _filter_timeline(self):
        selected=self.history_filter.currentText()
        self.filtered_entries=[e for e in self.timeline_entries if selected=='全部' or e[3]==selected or selected=='康复' and e[3]=='评估']
        rows(self.timeline,[e[:3] for e in self.filtered_entries],keys=[e[3]+':'+str(e[4].get('session_id') or e[4].get('id')) for e in self.filtered_entries])
        if hasattr(self,'history_empty'): self.history_empty.setVisible(not self.filtered_entries)

    def _filter_health(self):
        selected=self.health_filter.currentText();values=[];self.visible_health_events=[]
        for e in self.health_entries:
            category='用药' if e['type']=='observation' and 'medicationMissed' in e['observation'].get('tags',[]) else {'observation':'身体感受','measurement':'健康指标','labResult':'检验结果'}[e['type']]
            if selected=='全部' or selected==category:
                values.append((e['timestamp'],category+' · '+self._source_label(e['source']),self._event_summary(e)))
                self.visible_health_events.append(e)
        rows(self.health_timeline,values,keys=[e['id'] for e in self.visible_health_events]);self.health_empty.setVisible(not values)

    def _render_notifications(self):
        if not hasattr(self,'notification_filter'): return
        selection=self.notification_filter.currentText()
        state=self.snapshot.get('state',{});findings={f['id']:f for f in state.get('findings',[])}
        self.visible_notifications=[n for n in self.snapshot.get('notifications',[]) if selection=='全部' or (n['lifecycle']=='acknowledged')==(selection=='已确认')]
        values=[]
        for n in self.visible_notifications:
            finding=findings.get(n['findingId'],{});med='药' in n.get('title','') or 'medication' in str(finding.get('type',''))
            values.append((n.get('createdAt',''),n.get('title','照护通知'),'用药' if med else '健康 / 家庭照护',
                {'unavailable':'渠道未启用','pending':'待派发','accepted':'渠道已接受','sent':'已发送','delivered':'已送达','failed':'发送失败'}.get(n['phase'],'状态待核对'),
                '已确认' if n['lifecycle']=='acknowledged' else '未确认'))
        rows(self.notifications,values,keys=[n['findingId'] for n in self.visible_notifications]);self.notification_empty.setVisible(not values)

    def _selected_notification(self):
        r=self.notifications.currentRow();entries=getattr(self,'visible_notifications',[])
        if not 0<=r<len(entries): self._message('请先选择通知。');return None
        return entries[r]

    def _ack_notification(self):
        n=self._selected_notification()
        if n: self._request('notification.ack',{'id':n['findingId']})

    def _notification_detail(self):
        n=self._selected_notification()
        if n:
            r=self.notifications.currentRow()
            self._detail('通知详情',[self.notifications.horizontalHeaderItem(c).text()+'：'+self.notifications.item(r,c).text() for c in range(5)],
                [('进入对应业务',self._notification_business),('本人确认已查看',self._ack_notification)])

    def _notification_business(self):
        n=self._selected_notification()
        if n and self.navigate('medication' if '药' in n.get('title','') else 'health'):
            if getattr(self,'last_detail',None):self.last_detail.close()
            self._remember_return('notifications')

    @staticmethod
    def _source_label(value):
        return {'chat':'本人对话','manual':'本人填写','device':'设备记录','healthkit':'Apple Health','photo':'图片识别','import':'导入','demo':'演示数据'}.get(value,'来源待核对')

    @staticmethod
    def _plan_settings(settings):
        return ' · '.join(f'{title}：{settings[key]}' for key,title in [('sets','组数'),('target_reps','次数'),('reps','次数'),('rest_seconds','休息秒数'),('target_deg','目标角度')] if settings.get(key) is not None) or '按原计划准备时核对'

    @staticmethod
    def _sharing_record(record):
        action={'family.grant':'允许家庭共享','family.revoke':'撤销家庭共享','family.bind':'确认绑定','family.unbind':'解除绑定'}.get(record.get('action'),'记录共享操作')
        return str(record.get('timestamp') or record.get('time') or '')+' · '+action+'；允许查看不等于发送或送达。'

    def _completion_render(self):
        if not hasattr(self,'page_states'): return
        s=self.snapshot;state=s['state'];profile=s['profile']['profile'];plans=self._rehab_data('rehab.get_training_plan')
        training=self._rehab_data('rehab.get_training_history');assessments=self._rehab_data('rehab.get_recent_assessments')
        today=datetime.now().astimezone().date()
        def today_record(record):
            try:return datetime.fromisoformat(record.get('end_utc','').replace('Z','+00:00')).astimezone().date()==today
            except (ValueError,TypeError):return False
        completed=sum(today_record(r) and r.get('summary',{}).get('plan_completed') is True and r.get('status') in ('FINISHED','COMPLETED') for r in training)
        self.tile_values['plan'].setText(f'今天已完成 {completed} 次训练' if plans or training else '今天暂无康复计划')
        med=profile.get('medicationRecords',[]);active=[m for m in med if m['status']=='active']
        self.tile_values['medication'].setText(self.medication_today.text() if active else '暂无用药安排')
        pending=[t for t in state['tasks'] if t['status'] in ('pending','in_progress')]
        self.tasks_empty.setText('今天没有待完成任务' if not pending else f'还有 {len(pending)} 项待完成任务')
        self.tile_values['tasks'].setText(f'{len(pending)} 项待完成' if pending else '今天没有待完成任务')
        self.tile_values['health'].setText('已有记录，可查看当前摘要' if state['events'] else '暂无健康记录')
        p=plans[0] if plans else None;progress=p['progress'] if p else {};next_item=next((i for i in p['items'] if i['key']==progress.get('next_key')),None) if p else None
        self._visual_progress(progress)
        self.next_training.setText(('下一项：'+next_item['exercise_label']+' · '+self._plan_settings(next_item['settings'])+
            '\n计划累计完成 '+str(progress['completed'])+'/'+str(progress['total'])+' 项（非按日排期）。') if next_item else '当前计划全部完成，可查看反馈与报告。' if p else '今天暂无康复计划')
        if p and not p.get('next_available') and p.get('availability_reason'):
            self.next_training.setText(self.next_training.text()+'\n暂不能继续：'+p['availability_reason'])
        def item_state(item):
            value=next((v for v in progress.get('items',[]) if v['key']==item['key']),{})
            return '已完成' if value.get('done') else '当前下一项' if item['key']==progress.get('next_key') else '已记录，未完成' if value.get('session_id') else '未开始'
        rows(self.rehab_tables['今日恢复'],[(i['exercise_label'],item_state(i),self._plan_settings(i['settings'])) for i in p['items']] if p else [],keys=[i['key'] for i in p['items']] if p else [])
        scope=self.legacy._body_scope_key()
        self.rehab_summary['今日恢复'].setText('今天的恢复\n数据范围：'+SOURCES.get(scope['source_kind'],scope['source_kind'])+' / '+CONTEXTS.get(scope['usage_context'],scope['usage_context'])+'\n'+self.next_training.text()+f'\n今日完成 {completed} 次训练；计划项目状态按累计记录显示。')
        self._render_recovery(training,assessments,p,today)
        rows(self.rehab_tables['训练计划'],[(p['name'],f"{p['progress']['completed']}/{p['progress']['total']}",p.get('created_utc','未记录')) for p in plans],keys=[p['id'] for p in plans])
        self.rehab_summary['训练计划'].setText('当前保存的计划，无按周排期接口；动作目标及接受 / 准备由原计划窗口核对。' if plans else '暂无训练计划，可先评估再安排。')
        rows(self.rehab_tables['康复评估'],[(r.get('end_utc',''),r['exercise_label']+' · '+{'left':'左侧','right':'右侧'}.get(r.get('side'),'不分侧'),{'ASSESSED':'已评估','UNAVAILABLE':'数据不足','INCOMPARABLE':'条件不可比'}.get(r.get('status'),'需查看报告')) for r in assessments],keys=[r['session_id'] for r in assessments])
        self.rehab_summary['康复评估'].setText('查看原报告可核对测量条件，或打开身体档案查看汇总。' if assessments else '暂无评估记录，请先完成新评估。')
        rows(self.rehab_tables['康复进度'],[(r.get('end_utc',''),r['exercise_label'],f"完成 {r.get('summary',{}).get('completed','未记录')} 次；"+self._feedback_text(r.get('training_feedback',{}))) for r in training],keys=[r['id'] for r in training])
        self.rehab_summary['康复进度'].setText(f'已保存 {len(training)} 次训练。数据变化不等于临床改善，条件比较见原康复历史。' if training else '暂无训练记录，完成训练并反馈后会显示。')
        rows(self.today_medications,[(m['name'],m.get('dose') or '未填写',m.get('times') or '未填写','在用') for m in active],keys=[m['id'] for m in active])
        if not active:self.medication_today.setText('暂无用药安排')
        self.medication_empty.setVisible(not med);self.med_history_empty.setVisible(self.medication_history.rowCount()==0)
        missed=[e for e in state['events'] if e['type']=='observation' and 'medicationMissed' in e['observation'].get('tags',[])]
        rows(self.missed_medications,[(e['timestamp'],'漏服记录',self._event_summary(e)) for e in missed]);self.med_missed_empty.setVisible(not missed)
        self.health_entries=sorted(state['events'],key=lambda e:e['timestamp'],reverse=True);self._filter_health()
        self.health_rehab_summary.setText(f'康复相关资料：{len(assessments)} 项评估，{len(training)} 次训练；查看康复可核对条件与反馈。')
        self.health_metric_summary.setText('近期指标：\n'+'\n'.join(' · '.join(self.metrics.item(r,c).text() for c in (0,1,2)) for r in range(min(3,self.metrics.rowCount()))) if self.metrics.rowCount() else '暂无健康指标，可进入指标页面记录数值。')
        self.archive_empty.setVisible(not s['attachments'])
        link=s['family'].get('familyLink');allowed=s['projection']['canViewSharedDetail']
        rows(self.family_members,[(profile.get('familyContact') or '已绑定家属','家庭照护联系人','已绑定' if link and link['status']=='active' else '未绑定','已允许共享摘要' if allowed else '尚未开放')] if profile.get('familyContact') or link else [])
        self.family_empty.setVisible(self.family_members.rowCount()==0)
        self._render_notifications();self._filter_timeline()
        for key,field in self.page_states.items():field.setText('资料已更新。' if self.owner else '请先建立个人资料。')

    @staticmethod
    def _feedback_text(feedback):
        return '；'.join(f'{title}：{feedback[key]}' for key,title in [('pain','疼痛评分'),('fatigue','疲劳评分'),('notes','本人说明')] if feedback.get(key) is not None) or '反馈尚未填写'

    def _render_recovery(self,training,assessments,plan,today):
        def day(record):
            try:return datetime.fromisoformat(record.get('end_utc','').replace('Z','+00:00')).astimezone().date()
            except (TypeError,ValueError):return None
        dated=[r for r in training if day(r) is not None]
        week=[r for r in dated if today-timedelta(days=today.weekday())<=day(r)<=today]
        finished=lambda r:r.get('status') in ('FINISHED','COMPLETED') and r.get('summary',{}).get('plan_completed') is True
        latest=training[0] if training else None
        feedback=(latest or {}).get('training_feedback') or {}
        self.recovery_fields['flow'].setText(
            ('查看计划 → 准备下一项 → 训练 → 训练后反馈 → 返回今日恢复' if plan else '还没有训练计划：先做评估，或在训练计划页建立安排。')+
            ('\n最近训练反馈：已保存。' if feedback.get('revision') else '\n最近训练反馈：尚未填写，可从历史训练打开。' if latest else '\n训练后会在这里显示保存结果和反馈。'))
        self.recovery_fields['result'].setText(
            latest['exercise_label']+' · '+display_time(latest.get('end_utc'))+'\n'+
            f"已记录 {latest.get('summary',{}).get('completed','未记录')} 次；"+
            ('已完成计划目标' if finished(latest) else '计划目标未完成或未能核实')+'\n'+self._feedback_text(feedback)
            if latest else '暂无训练结果。完成训练并保存后显示，不以准备或打开摄像头计为完成。')
        recent=assessments[0] if assessments else None
        if recent:
            matching=[r for r in assessments[1:] if (r.get('exercise_id'),r.get('side'))==(recent.get('exercise_id'),recent.get('side'))]
            def reading(r):
                value=(r.get('motion_range') or {}).get('range_deg')
                return f'{value:g}°' if isinstance(value,(int,float)) and r.get('status')=='ASSESSED' else '未取得有效幅度'
            previous=matching[0] if matching else None
            text=recent['exercise_label']+' · '+display_time(recent.get('end_utc'))+'\n最近幅度：'+reading(recent)
            if previous:text+='；上次幅度：'+reading(previous)+'（'+display_time(previous.get('end_utc'))+'）'
            else:text+='；暂无同动作同侧的上一次记录。'
            text+='\n测量条件与可比性请在评估详情 / 原历史中核对；数值变化不代表临床改善。'
        else:text='暂无评估记录。可进入康复评估开始新评估，或查看身体档案。'
        self.recovery_fields['assessment'].setText(text)
        completion=sum(finished(r) for r in week)
        trend=f'本周已保存 {len(week)} 次训练，涉及 {len({day(r) for r in week})} 天；完成目标 {completion} 次。'
        trend+=f'\n本周已保存训练的目标完成率：{completion/len(week):.0%}。' if week else '\n本周暂无训练数据，尚无完成率。'
        for key,title in [('pain','疼痛评分'),('fatigue','疲劳评分')]:
            rated=[r for r in training if (r.get('training_feedback') or {}).get(key) is not None]
            if len(rated)>1:trend+=f"\n{title}（本人反馈）：{rated[1]['training_feedback'][key]} → {rated[0]['training_feedback'][key]}。"
            elif rated:trend+=f"\n{title}：{rated[0]['training_feedback'][key]}；暂无上一次反馈。"
            else:trend+=f'\n暂无{title}反馈数据。'
        self.recovery_fields['trend'].setText(trend+'\n评估变化见最近评估，完整训练记录见康复进度。')

    def _completion_clear(self):
        if not hasattr(self,'page_states'):return
        self._visual_progress({})
        for widget in [self.today_medications,self.missed_medications,self.family_members,*self.rehab_tables.values()]:rows(widget,[])
        self.health_entries=[];self.filtered_entries=[];self.visible_notifications=[]
        self.page_feedback.clear();self.rehab_save_marker=None
        self.return_context=None;self.context_return.hide()
        self.chat_input.clear()
        self.health_metric_summary.setText('正在读取当前用户指标…')
        self.metric_value.setValue(0);self.metric_shared.setChecked(False)
        self.health_status_sections.setCurrentIndex(0);self.med_today_sections.setCurrentIndex(0)
        self._show_rehab_scope(False)
        self.rehab_trend_anchor=None
        self._manual_extension_refresh=False
        # Open original reports and editors are owned by the previous participant too.
        for name in ('feedback_dialog','participant_dialog','batch_dialog','plan_library_dialog','automatic_dialog','longitudinal_dialog','events_dialog','silver_dialog'):
            dialog=getattr(self.legacy,name,None)
            if dialog:dialog.close()
        for dialog in self.legacy.report_windows:dialog.close()
        self.legacy.body_detail_dialog.hide()
        self.next_training.setText('正在读取当前用户计划…');self.health_rehab_summary.setText('正在读取当前用户资料…')
        for field in self.rehab_summary.values():field.setText('正在读取…')
        for field in self.recovery_fields.values():field.setText('正在读取当前用户资料…')
        for field in self.page_states.values():field.setText('正在读取当前用户资料…')
        if getattr(self,'last_detail',None):self.last_detail.close()

    def _visual_progress(self,progress):
        total=max(0,int(progress.get('total',0)))
        completed=max(0,min(total,int(progress.get('completed',0))))
        for bar in (self.home_progress,self.rehab_progress):
            bar.setRange(0,max(1,total));bar.setValue(completed)
            bar.setAccessibleDescription(f'当前计划累计完成 {completed}/{total}' if total else '暂无计划，尚无进度')
            bar.setToolTip(bar.accessibleDescription())

    def _completion_controls(self):
        if not hasattr(self,'page_states'):return
        busy=bool(self.pending)
        focus=self.active_page=='rehab' and self.legacy.scene=='rehab' and self.legacy.submode.currentData()=='training' and self.legacy.state in ('ONLINE','SAVE_FAILED')
        self.product_sidebar.setVisible(not focus);self.product_top.setVisible(not focus)
        self.interface_buttons['globalAssistant'].setVisible(not focus)
        self.assistant_shortcut.setEnabled(not focus)
        if focus:self.assistant_dock.hide()
        voice=self.extension_status.get('voice',{})
        phase=self.backend.voice.live_status()['phase']
        voice_busy=busy and self.last_operation=='voice.input'
        dictating=getattr(self,'dictation_active',False)
        finishing=getattr(self,'dictation_stopping',False) or getattr(self,'dictation_cancelled',False)
        self.dictation_cancel.setVisible(dictating)
        self.interface_buttons['voiceCancel'].setVisible(dictating)
        self.voice_level.setVisible(dictating)
        self.private_turn.setEnabled(not voice_busy);self.dock_private.setEnabled(not voice_busy)
        for item in self.product_action_buttons():
            kind=item.property('actionKind');reason=item.property('unavailableReason')
            enabled=not reason and (kind=='B' or bool(self.owner) and not busy)
            if item.property('actionTarget')=='profile.save':enabled=not busy
            key=item.property('actionId')
            if key in ('voiceInput','voiceOutput','voiceCancel'):enabled=enabled and bool(self.extension_status.get('voice',{}).get('available'))
            if key in ('voiceInput','assistantVoiceEntry'):
                enabled=bool(self.owner) and ((dictating and phase in ('opening','recording') and not finishing) or not busy and not dictating)
                if key=='voiceInput' and not dictating:enabled=enabled and bool(voice.get('available'))
                item.setText('结束录音' if dictating else '开始录音' if key=='voiceInput' else '语音输入')
                item.setToolTip('点击开始录音，再点结束；文字可修改后发送。' if voice.get('available') else voice.get('detail','语音输入尚未配置。'))
            if key=='voiceOutput':
                enabled=enabled and bool(voice.get('outputAvailable',voice.get('available')))
                item.setToolTip('朗读已保存的管家回复' if enabled else '当前语音宿主尚未接入朗读功能。')
            if key in ('voiceCancel','dictationCancel'):
                enabled=dictating and not getattr(self,'dictation_cancelled',False)
                item.setToolTip('取消当前录音或识别，本轮不发送。' if enabled else '当前没有正在进行的录音或识别。')
            if key=='voiceFinish':
                enabled=dictating and phase in ('opening','recording') and not finishing
                item.setToolTip('结束录音，将识别文字填入草稿。' if enabled else '仅在录音期间可以结束录音。')
            if item.property('actionTarget')=='image.parse':
                enabled=enabled and bool(self.snapshot.get('capabilities',{}).get('imageRecognitionAvailable'))
                item.setToolTip('将图片发送至已配置服务，上传前须确认。' if enabled else '图片识别服务尚未配置；附件存档仍可用。')
            if key in ('healthkitImport','healthkitDiagnostics'):enabled=enabled and bool(self.extension_status.get('healthkit'))
            if key=='devicePull':enabled=enabled and bool(self.extension_status.get('devices'))
            if str(key).startswith('sync'):enabled=enabled and bool(self.extension_status.get('syncAvailable'))
            if str(key).startswith('sync'):item.setToolTip('使用已配置的跨设备连接' if enabled else '跨设备接口已支持；当前未配置远程设备与可信身份。')
            if key=='rehabStart':
                enabled=enabled and self.legacy.start_button.isEnabled() and self.legacy.submode.currentData()=='training'
                item.setToolTip('开始已经确认的训练。' if enabled else '先点击“继续训练”，选择计划、打开输入并确认准备后，才能开始。')
            if key=='rehabWorkspaceBack':
                enabled=enabled and not self._rehab_locked()
                item.setToolTip('先结束并保存当前任务、关闭摄像头测试后返回。' if not enabled else '返回概览，保留已保存数据和工作区设置。')
            if key=='contextReturn':
                enabled=enabled and not self._rehab_locked()
                item.setToolTip('先结束并保存当前任务后返回。' if not enabled else '返回来源页面，保留筛选和所选记录。')
            if item is self.image_confirm:enabled=enabled and bool(self.pending_image and self.image_candidates.rowCount())
            item.setEnabled(enabled)
        self.user_select.setEnabled(not busy and not self.legacy.busy and not self.legacy._camera_testing and self.legacy.state not in ('CONNECTING','PREVIEW','ONLINE','SAVE_FAILED'))
        if busy:
            self.page_states[self.active_page].setText('正在处理语音，内容尚未发送。' if dictating else '正在读取或保存，请稍候。')
        elif self.active_page in self.page_feedback:
            self.page_states[self.active_page].setText(self.page_feedback[self.active_page])
        else:
            self.page_states[self.active_page].setText('资料已更新。' if self.snapshot else '请先建立个人资料。')
        # Keep one receipt in the header instead of repeating it inside core pages.
        if self.active_page in self.page_states:
            field=self.page_states[self.active_page]
            field.setVisible(not self.notice.isVisible() and (busy or not self.snapshot or self.active_page in self.page_feedback))
        self.rehab_tabs.setEnabled(not self.legacy.busy and self.legacy.state not in ('CONNECTING','PREVIEW','ONLINE','SAVE_FAILED'))
        status=self.extension_status
        camera='已连接，输入已打开' if self.legacy.state in ('PREVIEW','ONLINE') else '未连接 / 尚未开启'
        rows(self.devices_table,[('康复摄像头',camera,'原摄像头测试、双摄与回放'),
            ('通用健康设备','数据来源已配置，未做实机验收' if status.get('devices') else '接口已支持但未配置','设备文件导入 / 已配置数据读取'),
            ('Apple Health','外部数据来源已配置，未做实机验收' if status.get('healthkit') else 'Windows 不直接授权；外部来源未配置','由 iPhone 请求权限后导入'),
            ('特殊硬件','当前平台无独立厂商连接驱动','保留通用数据接口，不模拟实体硬件')])

    def _refresh_rehab_after_save(self):
        if not self.owner or self.pending or self.legacy.busy:return
        dialog_open=bool(self.legacy.feedback_dialog or self.legacy.plan_library_dialog or self.legacy.automatic_dialog)
        if getattr(self,'rehab_dialog_was_open',False) and not dialog_open:
            self.refresh_needed=True
        self.rehab_dialog_was_open=dialog_open
        marker=self.legacy._latest_report_id
        if marker and marker!=self.rehab_save_marker:
            self.rehab_save_marker=marker;self._request('snapshot')

    def product_action_buttons(self):
        return [b for b in self.findChildren(QPushButton) if b.property('actionId')]

    def _register_existing_actions(self):
        # Old controls keep their original callbacks; annotate the final result for coverage.
        route={'首页','AI 康复管家','康复','健康','用药','家庭','记录','通知','设置','记录身体感受 / 更正记录','查看原康复历史与评估趋势'}
        operations={'我需要帮助':'emergency.contacts','新建用户':'profile.save','发送':'chat','我的训练计划':'chat',
            '最近的评估结果':'chat','记录用药情况':'ui.chat.draft','记录数值':'health.record','添加资料 / 图片 / 视频':'archive.save',
            '导出所选附件':'archive.read','识别健康图片':'image.parse','确认识别结果并记录':'image.confirm',
            '编辑联系人':'profile.save','生成本机邀请码':'family.invite','确认绑定':'family.bind',
            '授权家庭共享':'family.grant','撤销共享':'family.revoke','解绑':'family.unbind','刷新家属摘要':'family.summary',
            '导出健康报告':'ui.file.write','核对可共享通知并建立台账':'notification.plan','确认所选通知':'notification.ack'}
        interface_routes={'globalAssistant','silverRehab','silverFamily','cameraSettings','settingsDevices','familySettings','notificationSettings','deviceConnect'}
        interface_operations={'assistantAttachment':'archive.save','assistantImage':'image.parse','voiceInput':'ui.voice.transcribe','voiceOutput':'voice.output',
            'voiceCancel':'voice.cancel','deviceRefresh':'extensions.status','deviceImport':'device.import','devicePull':'device.pull',
            'healthkitImport':'healthkit.import','healthkitDiagnostics':'healthkit.diagnostics','syncStart':'sync.start',
            'syncStatus':'sync.status','syncPoll':'sync.poll','syncPublish':'sync.publish','syncClose':'sync.close',
            'settingsRefresh':'extensions.status','dockSend':'chat','familySOS':'emergency.contacts'}
        for index,item in enumerate(self.findChildren(QPushButton)):
            parent=item
            while parent and parent is not self.legacy:parent=parent.parentWidget()
            if parent is self.legacy or item.property('actionId'):continue
            key=next((k for k,b in self.interface_buttons.items() if b is item),None)
            if key:
                item.setProperty('actionId',key);item.setProperty('actionKind','B' if key in interface_routes else 'D' if key in ('syncPublish','voiceInput','deviceImport','assistantImage') else 'A')
                item.setProperty('actionTarget',interface_operations.get(key,key));continue
            text=item.text()
            if text in route or text in operations:
                item.setProperty('actionId','product-'+str(STABLE_ACTION_IDS.get(text,index)));item.setProperty('actionKind','B' if text in route else 'D' if text in ('授权家庭共享','撤销共享','解绑','确认绑定','核对可共享通知并建立台账','确认识别结果并记录','识别健康图片') else 'A')
                item.setProperty('actionTarget',operations.get(text,text))

    def button_audit(self):
        return [dict(id=b.property('actionId'),button=b.text(),category='C' if not b.isEnabled() and not self.pending else b.property('actionKind'),
            action=b.property('actionTarget'),enabled=b.isEnabled(),reason=b.property('unavailableReason') or b.toolTip() or ('当前平台未接入或条件未满足' if not b.isEnabled() else ''),
            feedback='页面 / 详情切换' if b.property('actionKind')=='B' else '界面提示成功 / 失败或确认后执行') for b in self.product_action_buttons()]
