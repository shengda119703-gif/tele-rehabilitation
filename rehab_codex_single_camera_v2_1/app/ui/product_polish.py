"""Presentation composition over the frozen five-page controls and handlers."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QFrame, QVBoxLayout, QScrollArea, QTabWidget, QLabel, QSizePolicy
from .product_widgets import visual, ResponsiveGrid


def polish_product(window):
    home = window.home_sections.widget(0).layout()
    conversation = QFrame(); conversation.setObjectName('careConversation')
    area = QVBoxLayout(conversation); area.setContentsMargins(24, 24, 24, 24); area.setSpacing(16)
    for _ in range(3):
        area.addWidget(home.takeAt(0).widget())
    home.insertWidget(0, conversation)
    home.setSpacing(22)
    home.setAlignment(Qt.AlignTop)
    window.home_sections.parentWidget().setMaximumWidth(900)
    today=QWidget();today.setObjectName('careToday')
    today_box=QVBoxLayout(today);today_box.setContentsMargins(16,12,0,0);today_box.setSpacing(18)
    while home.count()>1:
        item=home.takeAt(1)
        if item.widget():today_box.addWidget(item.widget())
        elif item.layout():today_box.addLayout(item.layout())
    today_box.addStretch()
    home.removeWidget(conversation)
    composition=ResponsiveGrid(columns=2,threshold=860)
    composition.add(conversation);composition.add(today)
    home.addWidget(composition);home.addStretch()
    area.addStretch()
    conversation.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Maximum)
    composition.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Maximum)
    window.home_sections.parentWidget().setMaximumWidth(1060)
    window.home_schedule.setProperty('careSchedule',True)
    window.product_sidebar.setFixedWidth(190)

    # The next action has its own reading surface; management and date controls
    # remain the original widgets, signals, enabled states and identities.
    plan_area=window.plan_overview.layout()
    next_surface=QFrame();next_surface.setObjectName('careNext')
    next_box=QVBoxLayout(next_surface);next_box.setContentsMargins(24,24,24,24);next_box.setSpacing(16)
    for item in (window.plan_next,window.plan_hint,window.interface_buttons['planPractice']):
        plan_area.removeWidget(item);next_box.addWidget(item)
    next_box.setAlignment(window.interface_buttons['planPractice'],Qt.AlignLeft)
    plan_area.insertWidget(0,next_surface)
    window.plan_hint.setProperty('careInstruction',True)
    window.interface_buttons['planManageToggle'].setProperty('fluentAppearance','ghost')
    window.plan_tools.setObjectName('carePlanTools')
    plan_area.setSpacing(20)
    window.home_attention.setProperty('fluentType', 'secondary')
    window.family_sections.parentWidget().setMaximumWidth(980)
    window.family_sections.parentWidget().layout().setAlignment(Qt.AlignTop)
    window.family_sections.setProperty('activeHeightOnly', True)
    window.family_sections._fit_height()
    window.product_top.setMaximumWidth(980)
    window.product_meta.setMaximumWidth(980)
    window.notice.setMaximumWidth(980)
    window.rehab_sections.widget(0).setMaximumWidth(980)
    for scroll in window.rehab_tabs.findChildren(QScrollArea):
        scroll.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        if scroll.widget():
            scroll.widget().setMaximumWidth(980)

    # The archive reads as a document: title, personal summary, then its tools.
    archive = window.health_tabs.widget(0).layout()
    archive.removeWidget(window.health_archive_profile)
    archive.insertWidget(1, window.health_archive_profile)
    archive.setSpacing(20)
    window.health_archive_profile.setProperty('careSummary', True)
    actions=None
    for index in range(archive.count()):
        entry=archive.itemAt(index)
        if entry.layout() and entry.layout().indexOf(window.interface_buttons['healthUpload'])>=0:
            actions=archive.takeAt(index).layout();break
    if actions:
        profile_actions=QWidget();action_box=QVBoxLayout(profile_actions)
        action_box.setContentsMargins(0,0,0,0);action_box.setSpacing(10)
        action_grid=ResponsiveGrid(columns=2,threshold=0)
        while actions.count():
            entry=actions.takeAt(0)
            if entry.widget():
                entry.widget().setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
                action_grid.add(entry.widget())
        action_box.addWidget(action_grid)
        action_box.addStretch()
        archive.removeWidget(window.health_archive_profile)
        profile_grid=ResponsiveGrid(columns=2,threshold=860)
        profile_grid.add(window.health_archive_profile);profile_grid.add(profile_actions)
        archive.insertWidget(1,profile_grid)
    window.health_metric_summary.setProperty('careSummary',True)
    # Prompt Bar's empty/charged feedback; sending and pending gates remain
    # entirely with the existing controller. There is no new stop capability.
    window.chat_send.setProperty('careSend',True)
    def charged():
        window.chat_send.setProperty('careCharged',bool(window.chat_input.toPlainText().strip()))
        window.chat_send.style().unpolish(window.chat_send)
        window.chat_send.style().polish(window.chat_send)
        window.chat_send.update()
    window.chat_input.textChanged.connect(charged)
    charged()
    window.current_plan_text.setProperty('careSummary', True)
    window.plan_hint.setProperty('fluentType', 'secondary')
    for empty in (window.linked_empty, window.dose_empty, window.schedule_empty):
        empty.setProperty('careEmpty', True)
    window.family_attention.setProperty('fluentType', 'secondary')

    primary = {'planPractice', 'familyReadOnly', 'familyLocalBind'}
    quiet = {'homeScheduleDetail','homeInitialProfile','healthRehabRecords','healthMetricsEntry',
             'healthRecord','rehabLibrary','rehabPlanDetail','scheduleMove','scheduleRemove',
             'doseReset','doseManage','familyCategories','familyDisconnect','familyOldTools'}
    for key in primary:
        visual(window.interface_buttons[key], appearance='primary')
    for key in quiet:
        visual(window.interface_buttons[key], appearance='ghost')
    for tabs in window.findChildren(QTabWidget):
        if window.legacy.isAncestorOf(tabs):
            continue
        tabs.setDocumentMode(True)
    # A wrapping QLabel's natural narrow width must not dictate the width of
    # the whole short settings pane while heightForWidth assumes full width.
    for text in window.settings_tabs.findChildren(QLabel):
        if text.wordWrap():
            text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    # All behavior and labels are still owned by the original page adapters.
