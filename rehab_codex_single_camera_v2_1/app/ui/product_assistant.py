"""Progressive disclosure for the existing assistant; no domain or voice implementation."""
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QStackedWidget, QSizePolicy, QFrame, QProgressBar, QTextBrowser, QPlainTextEdit, QCheckBox, QToolButton, QDialog, QDialogButtonBox)
from ..settings import ROOT
from .product_theme import SPACING, METRICS
from .product_widgets import label, button, core_card, visual, EntryButton
from .product_record_review import record_review


# Explicit identities keep the old published controls independent of widget order.
ASSISTANT_NAV_ACTIONS = {
    'assistantModuleConversation','assistantModuleVoice','assistantModuleMaterials','assistantModuleRecords',
    'assistantBackConversation','assistantBackVoice','assistantBackMaterials','assistantBackReference',
    'assistantReferenceEntry','assistantMaterialsEntry','assistantVoiceSettings','assistantVoiceText','assistantArchiveEntry',
}


def build_assistant(window):
    w=window
    box=w._page('assistant')
    w.assistant_sections=QStackedWidget()
    w.assistant_views={}
    w.assistant_view_history=['overview']
    box.addWidget(w.assistant_sections,1)

    def page(key,title=None,*,show_title=True):
        item=QWidget();area=QVBoxLayout(item)
        area.setContentsMargins(0,0,0,0);area.setSpacing(SPACING['md'])
        w.assistant_views[key]=item;w.assistant_sections.addWidget(item)
        if title:
            top=QHBoxLayout()
            back=w._action(top,'assistantBack'+key.title(),'返回',w._assistant_back,target='AI 康复管家/上一模块')
            visual(back,appearance='ghost');back.setToolTip('返回上一模块，对话和输入草稿保留')
            if show_title:top.addWidget(visual(label(title),typography='section'),1)
            else:top.addStretch()
            area.addLayout(top)
            return area,top
        return area,None

    portal,_=page('overview')
    portal.addWidget(visual(label('把今天的感受，说清楚、记下来。'),typography='display'))
    portal.addWidget(visual(label('对话会形成可查看的理解与记录结果；需要澄清的内容会继续向你确认。'),typography='secondary'))
    portal.addSpacing(20)
    w.assistant_portal_status=visual(label('选择一个模块开始。'),typography='secondary')
    portal.addWidget(w.assistant_portal_status)
    grid=QGridLayout();grid.setSpacing(SPACING['lg'])
    w.assistant_module_buttons={}
    definitions=[('Conversation','开始对话','记录今天的感受，或继续已有对话。','conversation','assistant'),
        ('Voice','语音交流','点击查看语音输入和朗读的接入状态。','voice','microphone'),
        ('Materials','资料与图片','上传健康资料、图片或视频。','materials','health'),
        ('Records','我的康复记录','查看康复记录与管家参考资料。','reference','report')]
    for index,(name,title,description,key,icon) in enumerate(definitions):
        item=EntryButton(title,description)
        action='assistantModule'+name;item.setObjectName(action)
        item.setProperty('actionId',action);item.setProperty('actionKind','B')
        item.setProperty('actionTarget','AI 康复管家/'+key)
        item.setProperty('fluentAppearance','module');item.setProperty('moduleLead',index==0)
        item.setMinimumHeight(104 if index==0 else 78)
        item.setIcon(QIcon(str(ROOT/'assets/ui/ankang'/f'{icon}.svg')));item.setIconSize(QSize(24,24));item.setProperty('iconName',icon)
        item.clicked.connect(lambda checked=False,k=key:w._show_assistant_section(k))
        w.interface_buttons[action]=item;w.assistant_module_buttons[key]=item
        grid.addWidget(item,index,0)
    portal.addLayout(grid);portal.addStretch()

    conversation,top=page('conversation','康复管家',show_title=False)
    w.interface_buttons['assistantBackConversation'].setText('更多')
    visual(w._action(top,'assistantVoiceSettings','语音与设备',lambda:w._show_assistant_section('voice'),target='AI 康复管家/voice'),appearance='ghost')
    visual(w._action(top,'assistantReferenceEntry','查看参考资料',
        lambda:w._show_assistant_section('reference'),target='AI 康复管家/reference'),appearance='ghost')
    item,area=core_card();area.setContentsMargins(0,16,0,0);area.setSpacing(10)
    w.agent_status=visual(label('正在读取助手状态…','productMuted'),typography='secondary')
    w.assistant_status_toggle=QToolButton();w.assistant_status_toggle.setObjectName('assistantStatusToggle')
    w.assistant_status_toggle.setText('助手状态');w.assistant_status_toggle.setCheckable(True)
    w.assistant_status_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon);w.assistant_status_toggle.setArrowType(Qt.RightArrow)
    w.assistant_status_toggle.setAccessibleName('展开助手能力与连接状态')
    top.addWidget(w.assistant_status_toggle)
    w.assistant_status_details=QWidget();details=QVBoxLayout(w.assistant_status_details)
    details.setContentsMargins(0,0,0,0);details.setSpacing(SPACING['sm']);details.addWidget(w.agent_status)
    w.assistant_connection=visual(label(''),typography='caption');details.addWidget(w.assistant_connection)
    area.addWidget(w.assistant_status_details);w.assistant_status_details.hide()
    w.assistant_status_toggle.toggled.connect(w.assistant_status_details.setVisible)
    w.assistant_status_toggle.toggled.connect(lambda opened:w.assistant_status_toggle.setArrowType(Qt.DownArrow if opened else Qt.RightArrow))
    w.record_receipt=visual(label('表达 → 理解 → 需要时澄清 → 记录 → 后续追踪'),typography='caption')
    area.addWidget(w.record_receipt);w.record_receipt.hide()
    w.record_disclosure=QToolButton();w.record_disclosure.setText('查看理解与记录结果')
    w.record_disclosure.setToolButtonStyle(Qt.ToolButtonTextOnly)
    w.record_disclosure.setAccessibleName('展开最近一次理解与记录结果')
    w.record_disclosure.hide()
    area.removeWidget(w.record_receipt)
    receipt_row=QHBoxLayout();receipt_row.addWidget(w.record_receipt,1);receipt_row.addWidget(w.record_disclosure);area.addLayout(receipt_row)
    w.record_dialog=QDialog(w);w.record_dialog.setWindowTitle('理解与记录结果');w.record_dialog.resize(620,480)
    review_layout=QVBoxLayout(w.record_dialog)
    w.record_review=QTextBrowser();w.record_review.setAccessibleName('结构化理解与实际保存回执')
    review_layout.addWidget(w.record_review)
    close=QDialogButtonBox(QDialogButtonBox.Close);close.button(QDialogButtonBox.Close).setText('关闭');close.rejected.connect(w.record_dialog.close);review_layout.addWidget(close)
    w.record_disclosure.clicked.connect(w.record_dialog.show)
    w.chat=QTextBrowser();w.chat.setOpenExternalLinks(False);w.chat.setProperty('readingSurface',True)
    w.chat.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Ignored)
    w.chat.setAccessibleName('与康复管家的对话历史');w.chat.setMinimumHeight(METRICS['chat_minimum'])
    area.addWidget(w.chat,1)
    quick=QHBoxLayout();quick.setSpacing(SPACING['sm'])
    for text in ('我的训练计划','最近的评估结果'):
        quick.addWidget(visual(button(text,lambda checked=False,t=text:w._send_chat(t)),appearance='ghost'))
    medication=visual(button('记录用药情况',w._prepare_medication_draft),appearance='ghost')
    medication.setToolTip('先填写用药情况，检查后发送；已有草稿会保留。')
    quick.addWidget(medication)
    quick.addStretch();area.addLayout(quick)
    composer=QFrame();composer.setObjectName('assistantComposer')
    compose=QVBoxLayout(composer);compose.setContentsMargins(16,12,16,12);compose.setSpacing(8)
    w.chat_input=QPlainTextEdit();w.chat_input.setObjectName('assistantEditor')
    w.chat_input.setPlaceholderText('说说今天的状态，或查询已经保存的康复记录。')
    w.chat_input.setAccessibleName('给康复管家发送消息')
    w.chat_input.setMinimumHeight(METRICS['input_minimum']);w.chat_input.setMaximumHeight(METRICS['input_maximum'])
    compose.addWidget(w.chat_input)
    w.dictation_status=visual(label(''),typography='caption');w.dictation_status.hide()
    compose.addWidget(w.dictation_status)
    w.voice_level=QProgressBar();w.voice_level.setRange(0,100);w.voice_level.setValue(0)
    w.voice_level.setTextVisible(False);w.voice_level.setFixedHeight(4);w.voice_level.hide()
    w.voice_level.setAccessibleName('麦克风输入电平');compose.addWidget(w.voice_level)
    row=QHBoxLayout()
    visual(w._action(row,'assistantMaterialsEntry','添加资料',lambda:w._show_assistant_section('materials'),
        target='AI 康复管家/materials'),appearance='ghost')
    mic=w._action(row,'assistantVoiceEntry','语音输入',w._voice_input,kind='A',target='本机听写草稿')
    mic.setIcon(QIcon(str(ROOT/'assets/ui/ankang/microphone.svg')));mic.setIconSize(QSize(20,20));mic.setProperty('iconName','microphone')
    mic.setToolTip('点击录音，再次点击结束，识别结果可修改后发送。')
    w.dictation_cancel=w._action(row,'dictationCancel','取消',w._voice_cancel,kind='A',target='取消本轮听写')
    w.dictation_cancel.hide()
    w.private_turn=QCheckBox('本轮不记录');row.addWidget(w.private_turn);row.addStretch()
    w.chat_send=visual(button('发送',lambda:w._send_chat(),True),appearance='primary');w.chat_send.setToolTip('发送消息（Ctrl+Enter）；Enter 换行');row.addWidget(w.chat_send)
    compose.addLayout(row);area.addWidget(composer)
    item.setMaximumWidth(880)
    centered=QHBoxLayout();centered.addStretch(1);centered.addWidget(item,1000);centered.addStretch(1)
    conversation.addLayout(centered,1)

    materials,_=page('materials','资料与图片')
    item,material_tools=core_card('添加健康资料')
    materials.addWidget(item)
    materials.addStretch()

    voice,_=page('voice','语音输入')
    voice.addStretch()
    item,voice_tools=core_card('说出你想记录的事');voice_card=item
    item.setMaximumWidth(760)
    centered_voice=QHBoxLayout();centered_voice.addStretch(1);centered_voice.addWidget(item,1000);centered_voice.addStretch(1)
    voice.addLayout(centered_voice)
    voice_tools.addWidget(visual(label('点一下开始，再点一下结束。文字会放回对话框，由你修改和发送。'),typography='secondary'))
    w.voice_meter=QProgressBar();w.voice_meter.setRange(0,100);w.voice_meter.setValue(0)
    w.voice_meter.setTextVisible(False);w.voice_meter.setFixedHeight(6);w.voice_meter.setAccessibleName('麦克风输入电平')
    w.voice_meter.setFixedWidth(220);voice_tools.addWidget(w.voice_meter,0,Qt.AlignHCenter)
    voice_tools.addWidget(visual(label('本机识别 · 录音不保存 · 最长 2 分钟'),typography='caption'))
    voice.addStretch()

    reference,_=page('reference','康复记录与参考资料')
    item,w.assistant_tools=core_card('当前用户的参考资料')
    reference.addWidget(item);reference.addStretch()
    # Original controls are constructed once, in their appropriate modules.
    w._voice_controls(material_tools,voice_tools,w.assistant_tools)
    visual(w.interface_buttons['assistantAttachment'],appearance='primary')
    visual(w._action(material_tools,'assistantArchiveEntry','查看健康档案',lambda:w._health_tab(2),
        target='健康/健康档案'),appearance='ghost')
    voice_footer=QHBoxLayout();voice_footer.addStretch();voice_tools.addLayout(voice_footer)
    visual(w._action(voice_footer,'voiceRefresh','重新检测麦克风',w._refresh_extensions,kind='A',target='extensions.status'),appearance='ghost')
    visual(w._action(voice_footer,'assistantVoiceText','文字输入',lambda:w._show_assistant_section('conversation'),
        target='AI 康复管家/conversation'),appearance='ghost')
    voice_footer.addStretch()
    from PySide6.QtWidgets import QLabel
    for field in voice_card.findChildren(QLabel):field.setAlignment(Qt.AlignCenter)
    w.assistant_sections.setCurrentWidget(w.assistant_views['conversation'])
    w.assistant_view_history=['overview','conversation']


def show_section(window,key,*,remember=True):
    w=window
    if key not in w.assistant_views:raise ValueError('Unknown assistant section')
    if key not in ('conversation','voice') and getattr(w,'dictation_active',False):w._voice_cancel()
    history=w.assistant_view_history
    if key=='overview':history[:]=['overview']
    elif remember:
        if key in history:history[:]=history[:history.index(key)+1]
        else:history.append(key)
    for name,view in w.assistant_views.items():
        view.setSizePolicy(QSizePolicy.Preferred,QSizePolicy.Preferred if name==key else QSizePolicy.Ignored)
    w.assistant_sections.setCurrentWidget(w.assistant_views[key])
    w.assistant_sections.updateGeometry()
    w.page_widgets['assistant'].widget().setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Ignored if key=='conversation' else QSizePolicy.Preferred)
    w.page_widgets['assistant'].verticalScrollBar().setValue(0)
    if key=='conversation':w.chat_input.setFocus()
    if hasattr(w,'page_states'):w._completion_controls()


def back(window):
    if len(window.assistant_view_history)>1:window.assistant_view_history.pop()
    show_section(window,window.assistant_view_history[-1],remember=False)


def refresh_summary(window):
    """Read existing snapshot/status only; no extra calls or inferred AI capabilities."""
    w=window;s=w.snapshot
    if not s:
        w.assistant_portal_status.setText('请选择用户，或等待当前用户资料读取完成。')
        w.assistant_module_buttons['reference'].setDescription('等待当前用户的康复记录。')
    else:
        w.assistant_portal_status.setText('文字健康记录可用 · 康复记录查询'+('已配置' if s.get('modelAvailable') else '待配置'))
        plans=len(w._rehab_data('rehab.get_training_plan'))
        training=len(w._rehab_data('rehab.get_training_history'))
        w.assistant_module_buttons['reference'].setDescription(f'当前范围：{plans} 项计划、{training} 条训练记录。')
    available=bool(w.extension_status.get('voice',{}).get('available'))
    w.assistant_module_buttons['voice'].setDescription('点击录音，再点结束；文字可修改后发送。' if available else '语音服务尚未接入，点击查看状态。')


def refresh_record_review(window,turn):
    title,content=record_review(turn)
    changed=window.record_review.property('receiptSource')!=content
    window.record_review.setProperty('receiptSource',content)
    window.record_receipt.setText(title);window.record_receipt.show()
    window.record_review.setHtml(content)
    window.record_disclosure.show()
    if changed:
        from .product_motion import reveal_receipt
        reveal_receipt(window.record_receipt)
