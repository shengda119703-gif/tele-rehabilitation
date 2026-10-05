"""Progressive disclosure for the existing assistant; no domain or voice implementation."""
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QStackedWidget, QCommandLinkButton, QTextBrowser, QPlainTextEdit, QCheckBox, QToolButton, QDialog, QDialogButtonBox)
from ..settings import ROOT
from .product_theme import SPACING, METRICS
from .product_widgets import label, button, core_card, visual
from .product_record_review import record_review


# Explicit identities keep the old published controls independent of widget order.
ASSISTANT_NAV_ACTIONS = {
    'assistantModuleConversation','assistantModuleVoice','assistantModuleMaterials','assistantModuleRecords',
    'assistantBackConversation','assistantBackVoice','assistantBackMaterials','assistantBackReference',
    'assistantReferenceEntry','assistantMaterialsEntry','assistantVoiceEntry','assistantVoiceText','assistantArchiveEntry',
}


def build_assistant(window):
    w=window
    box=w._page('assistant')
    w.assistant_sections=QStackedWidget()
    w.assistant_views={}
    w.assistant_view_history=['overview']
    box.addWidget(w.assistant_sections,1)

    def page(key,title=None):
        item=QWidget();area=QVBoxLayout(item)
        area.setContentsMargins(0,0,0,0);area.setSpacing(SPACING['md'])
        w.assistant_views[key]=item;w.assistant_sections.addWidget(item)
        if title:
            top=QHBoxLayout()
            back=w._action(top,'assistantBack'+key.title(),'返回',w._assistant_back,target='AI 康复管家/上一模块')
            visual(back,appearance='ghost');back.setToolTip('返回上一模块，对话和输入草稿保留')
            top.addWidget(visual(label(title),typography='section'),1)
            area.addLayout(top)
            return area,top
        return area,None

    portal,_=page('overview')
    portal.addWidget(visual(label('今天想让管家帮你做什么？'),typography='section'))
    w.assistant_portal_status=visual(label('选择一个模块开始。'),typography='secondary')
    portal.addWidget(w.assistant_portal_status)
    grid=QGridLayout();grid.setSpacing(SPACING['lg'])
    w.assistant_module_buttons={}
    definitions=[('Conversation','开始对话','记录今天的感受，或继续已有对话。','conversation','assistant'),
        ('Voice','语音交流','点击查看语音输入和朗读的接入状态。','voice','microphone'),
        ('Materials','资料与图片','上传健康资料、图片或视频。','materials','health'),
        ('Records','我的康复记录','查看康复记录与管家参考资料。','reference','report')]
    for index,(name,title,description,key,icon) in enumerate(definitions):
        item=QCommandLinkButton(title,description)
        action='assistantModule'+name;item.setObjectName(action)
        item.setProperty('actionId',action);item.setProperty('actionKind','B')
        item.setProperty('actionTarget','AI 康复管家/'+key)
        item.setProperty('fluentAppearance','module')
        item.setMinimumHeight(METRICS['module_minimum'])
        item.setIcon(QIcon(str(ROOT/'assets/ui/ankang'/f'{icon}.svg')));item.setIconSize(QSize(24,24));item.setProperty('iconName',icon)
        item.clicked.connect(lambda checked=False,k=key:w._show_assistant_section(k))
        w.interface_buttons[action]=item;w.assistant_module_buttons[key]=item
        grid.addWidget(item,index//2,index%2)
    portal.addLayout(grid);portal.addStretch()

    conversation,top=page('conversation','与康复管家对话')
    visual(w._action(top,'assistantReferenceEntry','查看参考资料',
        lambda:w._show_assistant_section('reference'),target='AI 康复管家/reference'),appearance='ghost')
    item,area=core_card();area.setContentsMargins(16,16,16,16);area.setSpacing(8)
    w.agent_status=visual(label('正在读取助手状态…','productMuted'),typography='secondary')
    area.addWidget(w.agent_status)
    w.record_receipt=visual(label('表达 → 理解 → 需要时澄清 → 记录 → 后续追踪'),typography='caption')
    area.addWidget(w.record_receipt)
    w.record_disclosure=QToolButton();w.record_disclosure.setText('查看最近一次理解与记录结果')
    w.record_disclosure.setToolButtonStyle(Qt.ToolButtonTextOnly)
    w.record_disclosure.setAccessibleName('展开最近一次理解与记录结果')
    w.record_disclosure.hide();top.addWidget(w.record_disclosure)
    w.record_dialog=QDialog(w);w.record_dialog.setWindowTitle('理解与记录结果');w.record_dialog.resize(620,480)
    review_layout=QVBoxLayout(w.record_dialog)
    w.record_review=QTextBrowser();w.record_review.setAccessibleName('结构化理解与实际保存回执')
    review_layout.addWidget(w.record_review)
    close=QDialogButtonBox(QDialogButtonBox.Close);close.button(QDialogButtonBox.Close).setText('关闭');close.rejected.connect(w.record_dialog.close);review_layout.addWidget(close)
    w.record_disclosure.clicked.connect(w.record_dialog.show)
    w.chat=QTextBrowser();w.chat.setOpenExternalLinks(False)
    w.chat.setAccessibleName('与康复管家的对话历史');w.chat.setMinimumHeight(METRICS['chat_minimum'])
    area.addWidget(w.chat,1)
    quick=QHBoxLayout();quick.setSpacing(SPACING['sm'])
    for text in ('我的训练计划','最近的评估结果','今天漏服了药'):
        quick.addWidget(visual(button(text,lambda checked=False,t=text:w._send_chat(t)),appearance='ghost'))
    area.addLayout(quick)
    w.chat_input=QPlainTextEdit()
    w.chat_input.setPlaceholderText('说说今天的状态，或查询已经保存的康复记录。')
    w.chat_input.setAccessibleName('给康复管家发送消息')
    w.chat_input.setMinimumHeight(METRICS['input_minimum']);w.chat_input.setMaximumHeight(METRICS['input_maximum'])
    area.addWidget(w.chat_input)
    row=QHBoxLayout()
    visual(w._action(row,'assistantMaterialsEntry','添加资料',lambda:w._show_assistant_section('materials'),
        target='AI 康复管家/materials'),appearance='ghost')
    mic=w._action(row,'assistantVoiceEntry','语音输入',lambda:w._show_assistant_section('voice'),target='AI 康复管家/voice')
    mic.setIcon(QIcon(str(ROOT/'assets/ui/ankang/microphone.svg')));mic.setIconSize(QSize(20,20));mic.setProperty('iconName','microphone')
    mic.setToolTip('查看语音输入状态；未接入时可返回文字输入')
    w.private_turn=QCheckBox('本轮不记录');row.addWidget(w.private_turn);row.addStretch()
    w.chat_send=visual(button('发送',lambda:w._send_chat(),True),appearance='primary');w.chat_send.setToolTip('发送消息（Ctrl+Enter）；Enter 换行');row.addWidget(w.chat_send)
    area.addLayout(row);conversation.addWidget(item,1)

    materials,_=page('materials','资料与图片')
    item,material_tools=core_card('添加健康资料')
    materials.addWidget(item)
    materials.addStretch()

    voice,_=page('voice','语音交流')
    item,voice_tools=core_card('语音输入与朗读')
    voice.addWidget(item)
    voice_tools.addWidget(visual(label('语音识别需先确认，会按当前规则处理并记录。本轮不记录时请使用文字输入。'),typography='secondary'))
    voice.addStretch()

    reference,_=page('reference','康复记录与参考资料')
    item,w.assistant_tools=core_card('当前用户的参考资料')
    reference.addWidget(item);reference.addStretch()
    # Original controls are constructed once, in their appropriate modules.
    w._voice_controls(material_tools,voice_tools,w.assistant_tools)
    visual(w.interface_buttons['assistantAttachment'],appearance='primary')
    visual(w._action(material_tools,'assistantArchiveEntry','查看健康档案',lambda:w._health_tab(2),
        target='健康/健康档案'),appearance='ghost')
    visual(w._action(voice_tools,'assistantVoiceText','文字输入',lambda:w._show_assistant_section('conversation'),
        target='AI 康复管家/conversation'),appearance='ghost')


def show_section(window,key,*,remember=True):
    w=window
    if key not in w.assistant_views:raise ValueError('Unknown assistant section')
    history=w.assistant_view_history
    if key=='overview':history[:]=['overview']
    elif remember:
        if key in history:history[:]=history[:history.index(key)+1]
        else:history.append(key)
    w.assistant_sections.setCurrentWidget(w.assistant_views[key])
    w.page_widgets['assistant'].verticalScrollBar().setValue(0)
    if key=='conversation':w.chat_input.setFocus()


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
    w.assistant_module_buttons['voice'].setDescription('语音服务已配置，进入后确认操作。' if available else '语音服务尚未接入，点击查看状态。')


def refresh_record_review(window,turn):
    title,content=record_review(turn)
    window.record_receipt.setText(title)
    window.record_review.setHtml(content)
    window.record_disclosure.show()
