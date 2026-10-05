"""Presentation composition over the frozen five-page controls and handlers."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QVBoxLayout, QScrollArea, QTabWidget, QLabel, QSizePolicy
from .product_widgets import visual


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
