"""Production desktop shell. Every page reads a real product or rehabilitation service."""
import html
import json
import mimetypes
import queue
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (QMainWindow, QWidget, QFrame, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QComboBox, QStackedWidget, QScrollArea, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QListWidget, QListWidgetItem,
    QTextBrowser, QPlainTextEdit, QLineEdit, QDoubleSpinBox, QCheckBox, QTabWidget,
    QFileDialog, QMessageBox, QDialog, QInputDialog)

from ..settings import ROOT
from ..participants import legacy_participant
from ..product.backend import ProductBackend
from .product_rehab import ProductRehabWindow
from .product_theme import ProductTheme
from .product_theme import rehab_product_style
from .product_dialogs import ProductProfileDialog, MedicationDialog
from .product_interfaces import ProductInterfaces
from .product_completion import ProductCompletion
from .product_assistant import build_assistant, show_section, back, refresh_summary, refresh_record_review
from .product_widgets import label, button, card, table, rows, visual, conversation_html, display_time

NAVIGATION = [('home','首页','home'),('assistant','AI 康复管家','assistant'),('rehab','康复','tasks'),
              ('health','健康','health'),('medication','用药','medication'),('family','家庭','profile'),
              ('history','记录','report')]
METRIC_LABELS = {'steps':('活动步数','步'),'walkSpeed':('步行速度','m/s'),'sleepHours':('睡眠时长','小时'),
    'nightWakes':('夜间醒来','次'),'restingHr':('静息心率','bpm'),'weight':('体重','kg'),
    'spo2':('血氧','%'),'systolic':('收缩压','mmHg'),'diastolic':('舒张压','mmHg'),'bloodGlucose':('血糖','mmol/L')}
STATUS_LABELS = {'pending':'待确认','in_progress':'进行中','completed':'已完成','dismissed':'已跳过 / 未确认',
    'unknown':'数据不足','stable':'相对稳定','declining':'近期下降','improving':'近期上升',
    'denied':'未授权','ask':'待确认','granted':'已授权','active':'在用','stopped':'已停用'}
escape = lambda text: html.escape(str(text))












class ProductWindow(ProductCompletion, ProductInterfaces, QMainWindow):
    def __init__(self, data_dir=None, runtime=None, backend=None):
        super().__init__()
        self.setObjectName('productWindow')
        self.setWindowTitle('安康 · 居家康复助手')
        self.resize(1440,940)
        self.setMinimumSize(1024,720)
        self.legacy = ProductRehabWindow(runtime=runtime,data_dir=data_dir)
        self.legacy.setStyleSheet(rehab_product_style(self.legacy.styleSheet()))
        self.legacy.setWindowFlags(Qt.Widget)
        self.legacy.setMinimumSize(0,0)
        self.legacy.setParent(self)
        self.legacy.findChild(QFrame,'sidebar').hide()
        self.legacy.findChild(QFrame,'personBar').hide()
        self.legacy.training_hub.demo.hide()  # Keep the synthetic helper outside the formal user flow.
        self.backend = backend or ProductBackend(self.legacy.runtime.data_dir)
        self.owner = ''
        self.snapshot = {}
        self.profiles = []
        self.active_page = 'home'
        self.page_widgets = {}
        self.nav_buttons = {}
        self.pending = 0
        self.pending_export = None
        self.pending_image = None
        self.interface_buttons = {}
        self.extension_status = {}
        self.timeline_entries = []
        self.closing = False
        self.mutation_pending = False
        self.last_operation = ''
        self.refresh_needed = False
        self._build()
        self._completion_setup()
        self.product_theme=ProductTheme(self)
        self.chat_shortcut=QShortcut(QKeySequence('Ctrl+Return'),self.chat_input)
        self.chat_shortcut.setContext(Qt.WidgetShortcut);self.chat_shortcut.activated.connect(self._send_chat)
        self.developer = QShortcut(QKeySequence('Ctrl+Shift+D'),self)
        self.developer.activated.connect(self._developer)
        self.poller = QTimer(self)
        self.poller.timeout.connect(self._poll)
        self.poller.start(35)
        self.refresher = QTimer(self)
        self.refresher.timeout.connect(lambda: self._request('snapshot') if self.owner and not self.pending else None)
        self.refresher.start(45000)
        self._request('profile.list')

    def _build(self):
        central = QWidget()
        central.setObjectName('productRoot')
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0,0,0,0)
        root.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName('productSidebar')
        self.product_sidebar=sidebar
        sidebar.setFixedWidth(216)
        nav = QVBoxLayout(sidebar)
        nav.setContentsMargins(18,30,18,22)
        nav.addWidget(label('安康','productBrand'))
        nav.addWidget(label('居家康复助手','productBrandSub'))
        nav.addSpacing(28)
        for key,title,icon in NAVIGATION:
            item = button(title,lambda checked=False,k=key:self.navigate(k))
            item.setIcon(QIcon(str(ROOT/'assets/ui/ankang'/f'{icon}.svg')))
            item.setIconSize(QSize(22,22));item.setProperty('iconName',icon)
            item.setCheckable(True)
            item.setObjectName('productNav')
            self.nav_buttons[key] = item
            nav.addWidget(item)
        nav.addStretch()
        sos = button('我需要帮助',self._contacts)
        sos.setObjectName('productDanger')
        nav.addWidget(sos)
        nav.addWidget(label('本机资料 · 自主共享','productBrandSub'))
        root.addWidget(sidebar)
        main = QVBoxLayout()
        main.setContentsMargins(24,22,24,18)
        main.setSpacing(16)
        top = QHBoxLayout()
        self.title = label('首页','productTitle')
        top.addWidget(self.title,1)
        self.user_select = QComboBox()
        self.user_select.setMinimumWidth(170)
        self.user_select.setAccessibleName('当前产品用户')
        self.user_select.currentIndexChanged.connect(self._user_changed)
        top.addWidget(self.user_select)
        top.addWidget(button('新建用户',lambda:self._profile(new=True)))
        top.addWidget(button('通知',lambda:self.navigate('notifications')))
        top.addWidget(button('设置',lambda:self.navigate('settings')))
        top.setContentsMargins(0,0,0,0)
        self.product_top=QWidget();self.product_top.setLayout(top);main.addWidget(self.product_top)
        self.context_return=button('返回',self._return_context)
        self.context_return.setProperty('actionId','contextReturn')
        self.context_return.setProperty('actionKind','B')
        self.context_return.setProperty('actionTarget','返回来源页面')
        self.context_return.hide();main.addWidget(self.context_return)
        self.return_context=None
        meta = QHBoxLayout()
        self.date_label = label(datetime.now().strftime('%Y年%m月%d日'),'productMuted')
        meta.addWidget(self.date_label,1)
        self.storage_label = label('正在连接本机服务…','productMuted')
        meta.addWidget(self.storage_label)
        main.addLayout(meta)
        self.notice = label('', 'productNotice')
        self.notice.hide()
        main.addWidget(self.notice)
        self.pages = QStackedWidget()
        main.addWidget(self.pages,1)
        root.addLayout(main,1)
        self._home_page()
        self._assistant_page()
        self._rehab_page()
        self._health_page()
        self._medication_page()
        self._family_page()
        self._history_page()
        self._notifications_page()
        self._settings_page()
        self._build_global_assistant(main)
        self._render_extensions({})
        self.navigate('home')

    def _page(self,key):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        content.setProperty('visualScope','core')
        box = QVBoxLayout(content)
        box.setContentsMargins(0,0,8,0)
        box.setSpacing(16)
        scroll.setWidget(content)
        self.pages.addWidget(scroll)
        self.page_widgets[key] = scroll
        return box


    def _assistant_page(self):
        build_assistant(self)

    def _show_assistant_section(self,key):
        show_section(self,key)

    def _assistant_back(self):
        back(self)

    def _render_conversation(self):
        theme=getattr(self,'product_theme',None)
        if not theme:return
        content=conversation_html(self.snapshot.get('state',{}).get('chat',[]),theme.colors)
        for view in (self.chat,self.dock_chat):
            if view.property('renderedConversation')==content:continue
            bar=view.verticalScrollBar();position=bar.value();follow=position>=bar.maximum()-4
            view.setHtml(content);view.setProperty('renderedConversation',content)
            bar.setValue(bar.maximum() if follow or self.last_operation in ('chat','voice.input') else position)


    def _health_page(self):
        box = self._page('health')
        tabs = QTabWidget()
        self.health_tabs = tabs
        box.addWidget(tabs)
        status = QWidget()
        layout = QVBoxLayout(status)
        self.health_status_sections=QStackedWidget();layout.addWidget(self.health_status_sections)
        summary=QWidget();summary_box=QVBoxLayout(summary)
        twin,area = card('我的健康 · 当前状态')
        self.twin_text = label('等待真实资料；状态不等于临床诊断。')
        area.addWidget(self.twin_text)
        self.concerns = QListWidget()
        self.concerns.setMinimumHeight(60);self.concerns.setMaximumHeight(110)
        area.addWidget(self.concerns)
        summary_box.addWidget(twin)
        self.health_metric_summary=label('暂无健康指标，可进入指标页面记录数值。')
        summary_box.addWidget(self.health_metric_summary)
        self._action(summary_box,'healthMetricsEntry','查看 / 记录健康指标',lambda:self.health_status_sections.setCurrentIndex(1),target='健康指标详情')
        summary_box.addStretch();self.health_status_sections.addWidget(summary)
        detail=QWidget();detail_box=QVBoxLayout(detail)
        self._action(detail_box,'healthMetricsBack','返回当前健康状态',lambda:self.health_status_sections.setCurrentIndex(0),target='当前健康状态')
        metric,area = card('健康指标')
        self.metrics = table(['指标','最近记录','时间','来源'])
        area.addWidget(self.metrics)
        row = QHBoxLayout()
        self.metric_select = QComboBox()
        for key,(title,unit) in METRIC_LABELS.items():
            self.metric_select.addItem(title+' · '+unit,key)
        row.addWidget(self.metric_select)
        self.metric_value = QDoubleSpinBox()
        self.metric_value.setRange(0,100000)
        self.metric_value.setDecimals(2)
        row.addWidget(self.metric_value)
        self.metric_shared = QCheckBox('可用于已授权的家属摘要')
        row.addWidget(self.metric_shared)
        row.addWidget(button('记录数值',self._record_metric,True))
        area.addLayout(row)
        detail_box.addWidget(metric);self.health_status_sections.addWidget(detail)
        tabs.addTab(status,'状态与指标')
        record_page = QWidget()
        records = QVBoxLayout(record_page)
        self.health_timeline = table(['时间','事件 / 来源','内容'])
        records.addWidget(self.health_timeline)
        records.addWidget(button('记录身体感受 / 更正记录',lambda:self.navigate('assistant')))
        tabs.addTab(record_page,'健康记录')
        archive = QWidget()
        layout = QVBoxLayout(archive);layout.setAlignment(Qt.AlignTop)
        self.attachments = table(['资料名称','分类','类型','保存时间','可见性'])
        layout.addWidget(self.attachments)
        row = QHBoxLayout()
        row.addWidget(button('添加资料 / 图片 / 视频',self._add_attachment,True))
        row.addWidget(button('导出所选附件',self._export_attachment))
        row.addWidget(button('识别健康图片',self._parse_image))
        layout.addLayout(row)
        self.image_status = label('图片识别先产生候选结果，经本人确认才写入健康记录。','productMuted')
        layout.addWidget(self.image_status)
        self.image_candidates = table(['识别项目','候选值','单位'])
        layout.addWidget(self.image_candidates)
        self.image_confirm = button('确认识别结果并记录',lambda:self._request('image.confirm',{'confirmed':True}))
        self.image_confirm.setEnabled(False)
        layout.addWidget(self.image_confirm)
        tabs.addTab(archive,'健康档案与附件')
        self._devices_tab(tabs)
        box.addStretch()


    def _family_page(self):
        box = self._page('family')
        summary,layout = card('家属可见 · 需要关注什么')
        layout.addWidget(label('先看获准共享的近况与待处理事项，再管理联系人和共享范围。','productMuted'))
        self.family_summary = QTextBrowser();self.family_summary.setMinimumHeight(100);self.family_summary.setMaximumHeight(280)
        layout.addWidget(self.family_summary)
        layout.addWidget(button('刷新家属摘要',lambda:self._request('family.summary')))
        box.addWidget(summary)
        management=QWidget();self.family_management_layout=QVBoxLayout(management)
        self.family_management_layout.setContentsMargins(0,0,0,0)
        box.addWidget(management)
        item,layout = card('我的照护圈')
        self.family_state = label('绑定与授权分开确认。')
        layout.addWidget(self.family_state)
        self.contact_state = label('尚未填写家庭联系人。')
        layout.addWidget(self.contact_state)
        layout.addWidget(button('编辑联系人',self._profile))
        self._interface_button(layout,'familySOS','紧急联系人 / 求助信息',self._contacts)
        self._interface_button(layout,'silverFamily','活动照护 / 家庭回应 / 整改',self._open_silver)
        row = QHBoxLayout()
        row.addWidget(button('生成本机邀请码',lambda:self._request('family.invite')))
        self.invite_input = QLineEdit()
        self.invite_input.setPlaceholderText('输入本机生成的邀请码')
        row.addWidget(self.invite_input)
        row.addWidget(button('确认绑定',self._bind_family))
        layout.addLayout(row)
        self.invite_hint = label('绑定与共享授权分别确认；跨设备连接状态见设置。','productMuted')
        layout.addWidget(self.invite_hint)
        row = QHBoxLayout()
        row.addWidget(button('授权家庭共享',lambda:self._consent(True)))
        row.addWidget(button('撤销共享',lambda:self._consent(False)))
        row.addWidget(button('解绑',self._unbind_family))
        layout.addLayout(row)
        self.family_management_layout.addWidget(item)
        box.addStretch()

    def _history_page(self):
        box = self._page('history')
        tabs = QTabWidget()
        box.addWidget(tabs)
        timeline = QWidget()
        layout = QVBoxLayout(timeline)
        self.timeline = table(['时间','事件 / 来源','内容'])
        self.history_filter = QComboBox()
        self.history_filter.addItems(['全部','康复','健康','用药','评估'])
        self.history_filter.currentTextChanged.connect(self._filter_timeline)
        layout.addWidget(self.history_filter)
        layout.addWidget(self.timeline)
        layout.addWidget(button('查看原康复历史与评估趋势',lambda:self._rehab_action('history')))
        tabs.addTab(timeline,'统一历史')
        report = QWidget()
        layout = QVBoxLayout(report)
        self.report = QTextBrowser()
        self.report.setMinimumHeight(320)
        layout.addWidget(self.report)
        self.trends = table(['指标','最近均值','已有比较']);self.trends.setProperty('compactSummary',True)
        layout.addWidget(label('比较最近 3 天与已有个人基线；缺测不补零，变化不直接解释为临床改善。','productMuted'))
        layout.addWidget(self.trends)
        self.trend_empty=label('暂无可比较的近期指标。可先在健康页记录数值，再查看趋势。');layout.addWidget(self.trend_empty)
        layout.addWidget(button('导出健康报告',self._export_report))
        tabs.addTab(report,'报告与趋势')
        box.addStretch()

    def _notifications_page(self):
        box = self._page('notifications')
        item,layout = card('通知与确认')
        self.notification_status = label('正在读取外部通知渠道状态。','productMuted')
        layout.addWidget(self.notification_status)
        self.notifications = table(['时间','事项','渠道状态','确认状态'])
        layout.addWidget(self.notifications)
        row = QHBoxLayout()
        row.addWidget(button('核对可共享通知并建立台账',self._plan_notifications))
        row.addWidget(button('确认所选通知',self._ack_notification))
        layout.addLayout(row)
        self.audit_view = QTextBrowser()
        self.audit_view.setMinimumHeight(100);self.audit_view.setMaximumHeight(160)
        layout.addWidget(self.audit_view)
        box.addWidget(item)
        box.addStretch()


    def navigate(self,key,*,refresh=True):
        if key != 'rehab' and (self.legacy.state in ('CONNECTING','PREVIEW','ONLINE','SAVE_FAILED') or self.legacy._camera_testing or self.active_page=='rehab' and self.legacy.busy):
            self._message('请先结束并保存当前康复任务，再离开监护页面。')
            return False
        if key!=self.active_page:
            self.notice.clear();self.notice.hide()
        self.active_page = key
        if self.return_context and key!=self.return_context[1]:
            self.return_context=None;self.context_return.hide()
        if key=='assistant':self._show_assistant_section('overview')
        if key=='rehab' and not self._rehab_locked():self._show_rehab_scope(False)
        if key=='health':self.health_status_sections.setCurrentIndex(0)
        if key=='medication':self.med_today_sections.setCurrentIndex(0)
        self.pages.setCurrentWidget(self.page_widgets[key])
        self.title.setText(dict((k,t) for k,t,_ in NAVIGATION).get(key,{'settings':'设置','notifications':'通知'}.get(key,key)))
        if hasattr(self,'assistant_context'):
            self.assistant_context.setText('当前页面：'+self.title.text()+'。使用同一用户及已保存数据；页面内容尚不自动传给模型。')
        for name,nav in self.nav_buttons.items():
            nav.setChecked(name == key)
        if self.owner and not self.pending and refresh:
            self._request('snapshot')
        elif self.owner and self.pending and refresh:
            self.refresh_needed = True
        return True

    def _remember_return(self,source):
        if source in ('history','notifications') and source!=self.active_page:
            self.return_context=(source,self.active_page)
            self.context_return.setText('返回'+('记录' if source=='history' else '通知'))
            self.context_return.show()

    def _return_context(self):
        if self.return_context:self.navigate(self.return_context[0])

    def _message(self,text,*,severity='info'):
        self.notice.setText(text)
        self.notice.setVisible(bool(text))
        visual(self.notice,status=severity)
        if hasattr(self,'page_states') and text:
            self.page_states[self.active_page].setText(text)
            self.page_feedback[self.active_page]=text

    def _request(self,operation,payload=None,owner=None):
        selected = self.owner if owner is None else owner
        if not selected and operation not in ('profile.list','profile.save','capabilities'):
            self._message('请先建立或选择健康档案。')
            return False
        read = operation in ('profile.list','snapshot','extensions.status','family.summary','emergency.contacts','healthkit.diagnostics','sync.status')
        if not read and self.mutation_pending:
            self._message('当前操作正在完成，请勿重复提交。')
            return False
        if not read:
            self.mutation_pending = True
        self.last_operation = operation
        self.pending += 1
        self.chat_send.setEnabled(False)
        self.storage_label.setText('正在读取 / 保存…')
        scope = dict(self.legacy._body_scope_key())
        scope['participant_id'] = selected
        token={'owner':selected,'scope':scope}
        if operation=='chat':
            sent=(payload or {}).get('text','')
            token['drafts']={key:view.toPlainText() for key,view in (('chat',self.chat_input),('dock',self.dock_input))
                if view.toPlainText().strip() and sent in (view.toPlainText().strip(),'不要记录：'+view.toPlainText().strip())}
            self.record_receipt.setText('正在理解与处理记录，请稍候…')
        self.backend.submit(operation,selected,payload,scope if selected else None,token=token)
        self._completion_controls()
        return True

    def _poll(self):
        self._voice_live()
        while not self.backend.results.empty():
            operation,owner,token,result,error = self.backend.results.get_nowait()
            self.pending = max(0,self.pending-1)
            if operation not in ('profile.list','snapshot','extensions.status','family.summary','emergency.contacts','healthkit.diagnostics','sync.status'):
                self.mutation_pending = False
            self.chat_send.setEnabled(self.pending == 0)
            if owner and owner != self.owner and operation != 'profile.save':
                continue
            if error:
                if operation == 'extensions.status':self._manual_extension_refresh=False
                self.storage_label.setText('本机操作未完成')
                self._message(error,severity='info' if '语音已取消' in error else 'danger')
                if operation in ('chat','voice.input'):self.record_receipt.setText('本轮操作未完成 · 输入保留，请核对错误后重试')
                if operation=='voice.input':self._request('extensions.status')
                self.pending_export = None
                continue
            self.storage_label.setText('已连接本机数据')
            if isinstance(result,dict) and result.get('fileExport'):
                self.pending_export = None
                self._message('已导出到所选本机文件。',severity='success')
                continue
            if self._interface_result(operation,result):
                continue
            if operation == 'profile.list':
                self.profiles = result
                self._refresh_users()
                if not self.profiles:
                    self._message('首次使用：点击“建立 / 编辑资料”，可复用已有康复用户。')
                    self.onboarding_needed = not getattr(self,'onboarding_shown',False)
                elif not self.owner:
                    self._select_owner(self.profiles[0]['ownerId'])
                continue
            if operation == 'profile.save':
                if self.owner != owner:
                    self._clear_views()
                    self.image_confirm.setEnabled(False)
                self.owner = owner
                stored = result['profile']
                self.profiles = [p for p in self.profiles if p['ownerId'] != owner]+[stored]
                self._align_rehab(stored)
                self._refresh_users()
            if operation == 'family.invite':
                self.invite_input.setText(result['code'])
                self.invite_hint.setText('本机邀请码：'+result['code']+'。绑定后仍需单独授权共享。')
                self._message('已生成邀请码。请在家庭页确认绑定，绑定不等于允许共享。')
                continue
            if operation == 'family.summary':
                self._render_family_summary(result)
                self._message('已刷新当前允许查看的家庭摘要。')
                continue
            if operation == 'emergency.contacts':
                QMessageBox.information(self,'需要帮助',f"急救电话：{result['emergency']}\n家属：{result['familyName'] or '未填写'}\n电话：{result['familyPhone'] or '未填写'}\n社区医生：{result['communityDoctorPhone'] or '未填写'}\n\n请使用电话联系；软件没有自动拨号或发送求助。")
                continue
            if operation == 'image.parse':
                self.pending_image = result
                values = [(METRIC_LABELS.get(m['metric'],(m['metric'],''))[0],m['value'],m['unit']) for m in result['measurements']]
                values += [(m['name'],m['value'],m['unit']) for m in result['labResults']]
                rows(self.image_candidates,values)
                self.image_confirm.setEnabled(bool(values))
                self.image_status.setText('识别结果尚未保存。请对照原图核对后确认；不确定时不要记录。')
                if self.navigate('health'):
                    self.health_tabs.setCurrentIndex(2)
                continue
            if operation == 'archive.read':
                self._write_file(self.pending_export,bytes(result['bytes']))
                self.pending_export = None
                continue
            if operation == 'lifecycle.export':
                self._write_file(self.pending_export,json.dumps(result,ensure_ascii=False,indent=2).encode('utf-8'))
                self.pending_export = None
                continue
            snapshot = result.get('snapshot',result)
            if 'state' in snapshot:
                current_scope=dict(self.legacy._body_scope_key(),participant_id=self.owner)
                if isinstance(token,dict) and token.get('scope')!=current_scope:
                    self.refresh_needed=True
                    self._message('数据来源或使用情境已变化，正在重新读取当前范围。')
                    continue
                if operation.startswith('family.') or not snapshot['projection']['canViewSharedDetail']:
                    self.family_summary.clear()
                self.snapshot = snapshot
                self._render()
                if operation in ('chat','voice.input'):
                    if isinstance(result.get('turn'),dict):refresh_record_review(self,result['turn'])
                    for key,view in (('chat',self.chat_input),('dock',self.dock_input)):
                        sent=(token or {}).get('drafts',{}).get(key)
                        if sent is not None and view.toPlainText()==sent:view.clear()
                    if operation=='voice.input' and self.active_page=='assistant':self._show_assistant_section('conversation')
                if operation in ('image.confirm','lifecycle.clear'):
                    self.pending_image = None
                    self.image_confirm.setEnabled(False)
                    rows(self.image_candidates,[])
                if operation not in ('snapshot','extensions.status'):
                    self._message('管家已回复。' if operation in ('chat','voice.input') else '操作已完成，已刷新本机资料。',severity='success')
                # Uploading from the assistant must keep its visible Back control
                # and the unsent conversation available. Archive entry is explicit.
                if operation in ('archive.save','media.import') and self.active_page != 'assistant' and self.navigate('health',refresh=False):
                    self.health_tabs.setCurrentIndex(2)
        if not self.owner and self.profiles and not self.pending and not self.legacy.busy and not self.closing:
            self._select_owner(self.profiles[0]['ownerId'])
        if getattr(self,'onboarding_needed',False) and not self.pending and not self.legacy.busy and not self.closing:
            self.onboarding_needed = False
            self.onboarding_shown = True
            QTimer.singleShot(0,self._profile)
        if self.closing and self.legacy._allow_close:
            self.close()
        self._completion_controls()
        if getattr(self,'rehab_trend_anchor',None) and not self.legacy.busy:
            anchor,self.rehab_trend_anchor=self.rehab_trend_anchor,None
            for i,session in enumerate(self.legacy.sessions):
                if session['id']==anchor:
                    self.legacy.table.clearSelection();self.legacy.table.selectRow(i)
                    self.legacy._open_longitudinal();break
            else:self._message('当前范围中未找到所选康复记录，请刷新后重试。')
        if self.refresh_needed and not self.pending and not self.closing:
            self.refresh_needed = False
            self._request('snapshot')
        self._refresh_rehab_after_save()

    def _refresh_users(self):
        self.user_select.blockSignals(True)
        self.user_select.clear()
        for p in self.profiles:
            self.user_select.addItem(p['profile']['name'],p['ownerId'])
        self.user_select.setCurrentIndex(self.user_select.findData(self.owner))
        self.user_select.blockSignals(False)

    def _user_changed(self):
        selected = self.user_select.currentData()
        if selected and selected != self.owner:
            self._select_owner(selected)

    def _select_owner(self,owner):
        if self.pending or self.legacy.busy or self.legacy.state in ('CONNECTING','PREVIEW','ONLINE','SAVE_FAILED'):
            self._refresh_users()
            self._message('请先等待操作完成，并结束保存当前任务，再切换用户。')
            return
        stored = next((p for p in self.profiles if p['ownerId'] == owner),None)
        if not stored:
            return
        self.owner = owner
        self.snapshot = {}
        self._clear_views()
        self.pending_image = None
        for dialog in (getattr(self,'last_detail',None),self.legacy.silver_dialog):
            if dialog:dialog.close()
        self.image_confirm.setEnabled(False)
        rows(self.image_candidates,[])
        self._align_rehab(stored)
        self.chat.clear()
        self.family_summary.clear()
        self._refresh_users()
        self._request('snapshot')

    def _clear_views(self):
        # No old-owner data remains visible while the new owner is loading or a read fails.
        for grid in (self.plan_table,self.metrics,self.attachments,self.medications,self.timeline,
                     self.trends,self.notifications,self.image_candidates,self.health_timeline,self.medication_history):
            rows(grid,[])
        for view in (self.chat,self.family_summary,self.report,self.audit_view,self.dock_chat):
            view.clear();view.setProperty('renderedConversation',None)
        self.dock_input.clear()
        self.timeline_entries = []
        self.record_receipt.setText('正在读取当前用户资料…');self.record_review.clear()
        self.record_dialog.close();self.record_disclosure.hide()
        self.assistant_reference.setText('正在读取当前用户资料…')
        self._render_extensions({})
        self.tasks.clear()
        self.concerns.clear()
        for field in (self.greeting,self.today_note,self.home_status,self.twin_text,self.medication_today,
                      self.family_state,self.contact_state,self.profile_summary):
            field.setText('正在读取当前用户资料…')
        for field in self.tile_values.values():
            field.setText('正在读取…')
        self.invite_input.clear()
        self.invite_hint.setText('绑定与共享授权分别确认；跨设备连接状态见设置。')
        self._completion_clear()
        self._show_assistant_section('overview')
        self.assistant_portal_status.setText('正在读取当前用户资料…')
        self.assistant_module_buttons['reference'].setDescription('等待当前用户的康复记录。')

    def _align_rehab(self,stored):
        owner = stored['ownerId']
        if owner not in self.legacy.participant_records:
            p = legacy_participant(owner)
            p['display_name'] = stored['profile']['name']
            self.legacy.participant_records[owner] = p
        self.legacy.participant.setText(owner)
        self.legacy._apply_participant()
        self.legacy._refresh_participant_controls()

    def _profile(self,checked=False,new=False):
        if self.pending or self.legacy.busy or self.legacy._camera_testing or self.legacy.state in ('CONNECTING','PREVIEW','ONLINE','SAVE_FAILED'):
            self._message('请先等待本机操作完成，并结束保存当前康复任务。')
            return
        stored = None if new else next((p for p in self.profiles if p['ownerId'] == self.owner),None)
        dialog = ProductProfileDialog(stored,list(self.legacy.participant_records.values()),self)
        if dialog.exec() == QDialog.Accepted:
            payload = dict(dialog.value)
            owner = payload.pop('ownerId')
            self._request('profile.save',payload,owner)
        dialog.deleteLater()

    def _rehab_action(self,target):
        if self.legacy.busy or self.legacy._camera_testing or self.legacy.state in ('CONNECTING','PREVIEW','ONLINE','SAVE_FAILED'):
            self._message('请先结束并保存当前任务，关闭摄像头测试，再切换康复功能。')
            return False
        if not self.navigate('rehab'):
            return False
        self.rehab_tabs.blockSignals(True)
        self.rehab_tabs.setCurrentIndex({'training':0,'assessment':1,'body':1,'plans':2,'history':3}.get(target,0))
        self.rehab_tabs.blockSignals(False)
        self.last_rehab_tab=self.rehab_tabs.currentIndex()
        {'assessment':self.legacy._show_catalog,'training':self.legacy._show_training_hub,
         'body':self.legacy._show_body,'history':self.legacy._history,'plans':self.legacy._show_training_hub}[target]()
        self._show_rehab_scope(True)
        self._message('已打开康复工作区，请按实际评估 / 训练流程继续；完成后可返回康复概览。')
        return True

    def _send_chat(self,text=None,*,inline=False):
        if self.pending:
            self._message('上一条操作正在完成，请稍候。')
            return
        text = text if isinstance(text,str) else self.chat_input.toPlainText().strip()
        if text:
            if not inline and not self.navigate('assistant',refresh=False):
                return
            if not inline:self._show_assistant_section('conversation')
            self._request('chat',{'text':('不要记录：'+text) if self.private_turn.isChecked() else text})
        else:
            self._message('请先输入想对管家说的话。')

    def _open_silver(self):
        if self.navigate('rehab'):
            self._show_rehab_scope(True)
            self.legacy._show_silver()

    def _open_devices(self):
        if self.navigate('health'):
            self.health_tabs.setCurrentIndex(3)


    def _task_status(self,status):
        item = self.tasks.currentItem()
        if item and item.data(Qt.UserRole):
            self._request('task.status',{'id':item.data(Qt.UserRole),'status':status})
        else:
            self._message('请先选择一项今日任务。')

    def _record_metric(self):
        self._request('health.record',{'metric':self.metric_select.currentData(),'value':self.metric_value.value(),
                                     'visibility':'family_ok' if self.metric_shared.isChecked() else 'private'})

    def _medication_edit(self,edit=False):
        if not self.owner:
            self._message('请先建立健康档案。')
            return
        entries = self.snapshot.get('profile',{}).get('profile',{}).get('medicationRecords',[])
        r = self.medications.currentRow()
        if edit and not 0 <= r < len(entries):
            self._message('请先选择药物。')
            return
        dialog = MedicationDialog(entries[r] if edit else None,self)
        if dialog.exec() == QDialog.Accepted:
            self._request('medication.save',{'record':dialog.value})
        dialog.deleteLater()

    def _medication_status(self):
        entries = self.snapshot.get('profile',{}).get('profile',{}).get('medicationRecords',[])
        r = self.medications.currentRow()
        if 0 <= r < len(entries):
            record = entries[r]
            if QMessageBox.question(self,'修改药物档案状态','仅修改档案状态，不代表医嘱调整。确认继续？') == QMessageBox.Yes:
                self._request('medication.status',{'id':record['id'],'status':'stopped' if record['status']=='active' else 'active'})
        else:
            self._message('请先选择药物。')

    def _confirm_medication(self):
        task = next((t for t in self.snapshot.get('state',{}).get('tasks',[]) if t['kind']=='medication_check'),None)
        if task:
            self._request('task.status',{'id':task['id'],'status':'completed'})
        else:
            self._message('尚无今日用药核对任务，请先填写已有医嘱药物。')

    def _consent(self,grant):
        if QMessageBox.question(self,'修改家庭共享','绑定家属将可查看允许共享的摘要，私密记录不开放。确认允许共享？' if grant else '确认撤销家庭共享？家属摘要将不再开放。') != QMessageBox.Yes:
            return
        self._request('family.grant' if grant else 'family.revoke')

    def _bind_family(self):
        if QMessageBox.question(self,'确认家庭绑定','使用所填本机邀请码建立家庭绑定？绑定后仍须单独授权，才允许查看共享摘要。') == QMessageBox.Yes:
            self._request('family.bind',{'code':self.invite_input.text()})

    def _contacts(self):
        self._request('emergency.contacts')

    def _add_attachment(self):
        filename,_ = QFileDialog.getOpenFileName(self,'添加本机健康资料','','资料 (*.pdf *.png *.jpg *.jpeg *.webp *.mp4 *.avi *.mov *.txt);;所有文件 (*)')
        if not filename:
            return
        path = Path(filename)
        category,accepted = QInputDialog.getItem(self,'资料分类','选择分类', ['体检报告','就诊记录','检验检查','影像资料','病历资料','其他资料'],0,False)
        if accepted:
            self._request('archive.save',{'name':path.stem,'fileName':path.name,'category':category,
                'mediaType':mimetypes.guess_type(path.name)[0] or 'application/octet-stream',
                '_local_file':str(path),'visibility':'private'})

    def _export_attachment(self):
        if self.pending:
            self._message('请等待当前操作完成，再导出附件。')
            return
        entries = self.snapshot.get('attachments',[])
        r = self.attachments.currentRow()
        if 0 <= r < len(entries):
            entry = entries[r]
            filename,_ = QFileDialog.getSaveFileName(self,'导出附件',Path(entry['fileName']).name)
            if filename:
                self.pending_export = filename
                self._request('archive.read',{'id':entry['id'],'_local_export_path':filename})
        else:
            self._message('请先选择要导出的附件。')

    def _parse_image(self):
        if not self.snapshot.get('capabilities',{}).get('imageRecognitionAvailable'):
            self._message('尚未配置既有图片识别代理服务。可先添加图片附件或手动记录指标。')
            return
        filename,_ = QFileDialog.getOpenFileName(self,'选择健康图片','','图片 (*.png *.jpg *.jpeg *.webp)')
        if filename and QMessageBox.question(self,'识别图片','将所选图片发送到已配置的图片识别服务，识别后还需你核对确认。是否继续？') == QMessageBox.Yes:
            path = Path(filename)
            self._request('image.parse',{'_local_file':str(path),'mediaType':mimetypes.guess_type(path.name)[0],
                                        'kind':'report','consent':True})

    def _backup(self):
        if self.pending:
            self._message('请等待当前操作完成，再导出备份。')
            return
        filename,_ = QFileDialog.getSaveFileName(self,'导出本人本地备份','安康本机备份.json','JSON (*.json)')
        if filename:
            self.pending_export = filename
            self._request('lifecycle.export',{'_local_export_path':filename})

    def _clear(self):
        if not self.owner or self.legacy.state in ('CONNECTING','PREVIEW','ONLINE','SAVE_FAILED'):
            self._message('请先选择用户，并结束保存当前康复任务。')
            return
        if QMessageBox.warning(self,'清除本人数据','清除当前用户的健康事件、聊天、附件、家庭授权和通知（含本机旧备份）。保留个人资料、药物档案和康复记录。建议先导出备份。',QMessageBox.Yes|QMessageBox.No,QMessageBox.No) == QMessageBox.Yes:
            self._request('lifecycle.clear',{'confirmOwner':self.owner})

    def _write_file(self,filename,content):
        if not filename:
            return
        self._request('ui.file.write',{'path':filename,'bytes':list(content)})

    def _export_report(self):
        report = self.snapshot.get('history',{}).get('report',{})
        filename,_ = QFileDialog.getSaveFileName(self,'导出健康报告','安康健康周报.txt','文本 (*.txt)')
        if filename:
            text = [report.get('rangeText','')]
            for section in report.get('sections',[]):
                text.extend(['',section['title'],*section['lines']])
            self._write_file(filename,'\n'.join(text).encode('utf-8'))

    def _developer(self):
        from .deepseek_developer import DeepSeekDeveloperDialog
        if self.pending:
            self._message('请等待当前操作完成。')
            return
        dialog = DeepSeekDeveloperDialog(self)
        if dialog.exec() == QDialog.Accepted:
            # New product bridge recreates sessions with the same local persisted health data.
            self.backend.close()
            self.backend = ProductBackend(self.legacy.runtime.data_dir)
            if self.owner:
                self._request('snapshot')
        dialog.key_input.clear()
        dialog.deleteLater()

    def _render(self):
        s = self.snapshot
        state = s['state']
        stored = s['profile']
        profile = stored['profile']
        self.profiles = [stored if p['ownerId']==self.owner else p for p in self.profiles]
        self.greeting.setText(profile['name']+'，一起安排好今天')
        self.today_note.setText('当前目标：'+(stored.get('rehabGoal') or '尚未填写，可在设置中补充'))
        rehab = s.get('rehabilitation_ui',s.get('rehabilitation',{}))
        plans = rehab.get('rehab.get_training_plan',{}).get('records',[])
        self.tile_values['plan'].setText(f'{len(plans)} 项已保存' if plans else '先完成评估')
        medications = profile.get('medicationRecords',[])
        med_tasks = [t for t in state['tasks'] if t['kind']=='medication_check']
        self.tile_values['medication'].setText(STATUS_LABELS.get(med_tasks[0]['status'],'待核对') if med_tasks else '尚未录入')
        self.tile_values['tasks'].setText(str(sum(t['status'] in ('pending','in_progress') for t in state['tasks']))+' 项待办')
        self.tile_values['health'].setText(str(len(state['events']))+' 条记录')
        rows(self.plan_table,[(p.get('name','已保存计划'),'可核对继续' if p.get('next_available') else p.get('availability_reason') or '请核对评估依据') for p in plans])
        self.tasks.clear()
        for task in state['tasks']:
            item = QListWidgetItem(f"{STATUS_LABELS.get(task['status'],task['status'])} · {task['title']}\n{task['description']}")
            item.setData(Qt.UserRole,task['id'])
            self.tasks.addItem(item)
        if not state['tasks']:
            self.tasks.addItem('当前没有待办。用药和健康照护任务会依据已填写资料与记录生成。')
        concerns = s['twin']['personTwin'].get('activeConcerns',[])
        self.home_status.setText('；'.join(concerns) if concerns else '已有 '+str(len(state['events']))+' 条健康记录；暂未形成需关注的摘要。数据不足时不能判断整体健康状态。')
        self.agent_status.setText('健康管理与康复记录查询可用。' if s.get('modelAvailable') else '基础健康对话与记录可用；康复记录查询尚未配置。')
        self._render_conversation()
        twin = s['twin']['personTwin']
        self.twin_text.setText(' · '.join(title+'：'+STATUS_LABELS.get(twin[key],twin[key]) for key,title in [('activity','活动'),('mobility','行动'),('sleep','睡眠'),('nightActivity','夜间活动')])+'\n数据更新时间：'+display_time(s['twin'].get('dataUpdatedAt'))+'\n这是已有资料的状态摘要，不是诊断。')
        self.concerns.clear()
        self.concerns.addItems(twin.get('activeConcerns',[])+twin.get('safetyRelevantChanges',[]) or ['资料不足，暂无明确状态变化。'])
        measurements = s['history']['measurements']
        latest = {}
        for m in sorted(measurements,key=lambda m:m['timestamp']):
            latest[m['metric']] = m
        rows(self.metrics,[(METRIC_LABELS[k][0],str(m['value'])+' '+m['unit'],display_time(m['timestamp']),self._source_label(m['source'])) for k,m in latest.items()])
        rows(self.attachments,[(a['name'],a['category'],a['mediaType'],display_time(a['date']),'仅本人' if a['visibility']=='private' else '可共享') for a in s['attachments']],keys=[a['id'] for a in s['attachments']])
        if not self.pending_image:
            self.image_status.setText('既有识别代理已配置，上传前需要本人许可。' if s['capabilities']['imageRecognitionAvailable'] else '图片 / 视频附件可保存。图片识别代理尚未配置，不会生成假识别结果。')
        rows(self.medications,[(m['name'],m.get('dose') or '未填写',m.get('purpose') or '未填写',m.get('times') or '未填写',STATUS_LABELS[m['status']]) for m in medications],keys=[m['id'] for m in medications])
        self.medication_today.setText('；'.join(STATUS_LABELS[t['status']]+' · '+t['title'].removeprefix('💊 ').strip() for t in med_tasks) or '尚无今日用药核对任务。')
        family = s['family']
        link = family.get('familyLink')
        self.family_state.setText(('已绑定本机家属' if link and link['status']=='active' else '尚未绑定家属')+' · '+STATUS_LABELS[family['familySharing']])
        self.contact_state.setText('家庭联系人：'+(profile.get('familyContact') or '未填写')+' · '+(profile.get('familyPhone') or '未填写电话'))
        self._render_family_summary({'canViewSharedDetail':s['projection']['canViewSharedDetail'],'projection':s['projection']})
        timeline = [(e['timestamp'],{'observation':'身体感受','measurement':'健康指标','labResult':'检验结果'}.get(e['type'],'健康记录')+' · '+self._source_label(e['source']),self._event_summary(e),
            '用药' if e['type']=='observation' and 'medicationMissed' in e['observation'].get('tags',[]) else '健康',e) for e in state['events']]
        timeline += [(t['dueDate'],'用药核对' if t['kind']=='medication_check' else '照护任务',t['title']+' · '+STATUS_LABELS[t['status']],
            '用药' if t['kind']=='medication_check' else '健康',t) for t in s.get('taskHistory',[])]
        training_records = rehab.get('rehab.get_training_history',{}).get('records',[])
        assessments = rehab.get('rehab.get_recent_assessments',{}).get('records',[])
        timeline += [(r.get('end_utc',''),'康复训练',r.get('exercise_label','')+' · '+str(r.get('summary',{}).get('completed','未记录'))+
            ' · '+self._feedback_text(r.get('training_feedback',{})),'康复',r) for r in training_records]
        timeline += [(r.get('end_utc',''),'康复评估',r.get('exercise_label','')+' · '+{'ASSESSED':'已评估','UNAVAILABLE':'数据不足'}.get(r.get('status'),'请查看测量条件'),'评估',r) for r in assessments]
        self.timeline_entries = sorted(timeline,key=lambda r:r[0] or '',reverse=True)
        self._filter_timeline()
        rows(self.medication_history,[entry[:3] for entry in self.timeline_entries if entry[3]=='用药'])
        self.assistant_reference.setText(f"当前数据参考范围：{len(state['events'])} 条健康记录，{len(plans)} 项已保存计划，{len(assessments)} 项最近评估，{len(training_records)} 条最近训练，{len(medications)} 项药物档案，{len(state['tasks'])} 项今日任务。\n康复记录按当前用户 / 来源 / 情境读取；实际调用以管家回复为准。")
        report = s['history']['report']
        content = '<h2>'+escape(report['rangeText'])+'</h2>'
        for section in report['sections']:
            content += '<h3>'+escape(section['title'])+'</h3><p>'+'<br>'.join(escape(line) for line in section['lines'])+'</p>'
        self.report.setHtml(content)
        rows(self.trends,[(METRIC_LABELS[k][0],v['recent'] if v['recent'] is not None else '数据不足',v['deltaText'] or ('未形成明显比例变化，见报告中的个人基线' if v.get('baseline') else '暂无足够个人基线')) for k,v in s['trends'].items() if v['recent'] is not None])
        self.trend_empty.setVisible(self.trends.rowCount()==0)
        audits = s.get('audits',[])
        self.audit_view.setPlainText('共享记录\n'+'\n'.join(self._sharing_record(a) for a in audits) if audits else '当前没有已记录的共享操作；允许查看不等于已经发送或送达。')
        self.profile_summary.setText(profile['name']+' · '+(str(profile['age'])+' 岁' if profile['age'] else '年龄未填')+'\n当前状态：'+(stored.get('currentState') or '未填写')+'\n康复目标：'+(stored.get('rehabGoal') or '未填写'))
        self.capabilities_text.setText('康复、健康自报、用药、家庭授权、附件、健康状态、记录与报告已接本机业务。\n图片识别：'+('代理已配置' if s['capabilities']['imageRecognitionAvailable'] else '待配置代理')+'\n语音、设备、同步及外部通知状态见下方与健康设备页。')
        self._completion_render()
        refresh_summary(self)
        self._request('extensions.status')

    def _event_summary(self,event):
        if event['type']=='observation':
            return event['observation']['text']
        if event['type']=='measurement':
            m = event['measurement']
            return METRIC_LABELS[m['metric']][0]+f" {m['value']} {m['unit']}"
        m = event['labResult']
        return f"{m['name']} {m['value']} {m['unit']}"

    def _render_family_summary(self,result):
        if not result.get('canViewSharedDetail'):
            self.family_summary.setMaximumHeight(110)
            self.family_summary.setHtml('<h3>摘要尚未开放</h3><p>需要本机家属绑定与本人共享授权。私密资料始终不进入家属摘要。</p>')
            return
        projection = result['projection']
        content = '<h3>当前授权范围内的摘要</h3>'
        content += '<p>可见健康记录：'+str(len(projection.get('selfEvents',[])))+' 条 · 照护任务：'+str(len(projection['tasks']))+' 项</p>'
        content += '<h3>需要关注</h3>'
        content += ''.join('<p>'+escape(f['title'])+'：'+escape(f.get('familyMessage') or '')+'</p>' for f in projection['findings']) or '<p>暂无获准共享的关注提示；不代表已排除健康风险。</p>'
        pending=[t for t in projection['tasks'] if t.get('status') in ('pending','in_progress')]
        content += '<h3>需要处理</h3>'
        content += ''.join('<p>'+escape(t['title'])+' · '+escape(STATUS_LABELS.get(t.get('status'),'待核对'))+'<br>'+escape(t.get('description',''))+'</p>' for t in pending) or '<p>暂无获准共享的待处理事项。</p>'
        content += '<h3>最近共享记录</h3>'
        recent=sorted(projection.get('selfEvents',[]),key=lambda e:e.get('timestamp',''),reverse=True)[:3]
        content += ''.join('<p>'+escape(self._event_summary(e))+' · '+escape(display_time(e.get('timestamp')))+'</p>' for e in recent) or '<p>暂无可见记录。</p>'
        content += ''.join('<p>家人近况：'+escape(e['text'])+'</p>' for e in projection['familyEvents'])
        content += '<p>这是本机获准阅读的视图；不表示已发送到家属设备。</p>'
        self.family_summary.setMaximumHeight(280)
        self.family_summary.setHtml(content)

    def closeEvent(self,event):
        self.backend.voice.cancel()
        if self.legacy._allow_close:
            self.backend.close()
            self.poller.stop()
            self.refresher.stop()
            event.accept()
        else:
            event.ignore()
            self.closing = True
            self._message('正在停止采集并保存本次康复任务…')
            self.legacy.close()
