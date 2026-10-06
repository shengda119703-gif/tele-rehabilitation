"""User-approved information architecture; existing services and controls stay authoritative."""
from html import escape
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy, QFrame
from .product_widgets import label, visual, ResponsiveGrid
from .product_segments import SegmentTabs


def assemble(w):
    # Home owns the original history widgets; no duplicated report or persistence.
    history=w.page_widgets['history']
    w.health_tabs.removeTab(w.health_tabs.indexOf(history))
    w.home_history_index=w.home_sections.addWidget(history)
    back=w._action(history.widget().layout(),'recordsHome','返回首页',lambda:w.navigate('home'),target='首页')
    history.widget().layout().removeWidget(back);history.widget().layout().insertWidget(0,back)
    home=w.home_sections.widget(0).layout()
    records=QFrame();records.setObjectName('careJournal')
    box=QVBoxLayout(records);box.setContentsMargins(24,24,24,24);box.setSpacing(18)
    heading=QHBoxLayout();heading.addWidget(visual(label('我的记录与周报'),typography='section'));heading.addStretch()
    w._action(heading,'homeRecords','全部记录',lambda:open_records(w),target='首页/我的记录与周报')
    box.addLayout(heading)
    w.home_week_range=visual(label(''),typography='secondary');box.addWidget(w.home_week_range)
    w.home_week_preview=label('');w.home_week_preview.setObjectName('homeWeekPreview');box.addWidget(w.home_week_preview)
    links=QHBoxLayout()
    w._action(links,'homeWeeklyReport','查看本周周报',lambda:open_records(w,report=True),target='原健康周报')
    for key in ('healthRehabRecords','healthPhoneRecords'):
        links.addWidget(w.interface_buttons[key])
    links.addStretch();box.addLayout(links)
    home.insertWidget(home.count()-1,records)
    home.setSpacing(28)
    w.home_sections.parentWidget().setMaximumWidth(1200)
    w.product_sidebar.setFixedWidth(172)
    for item in (w.product_top,w.product_meta,w.notice):item.setMaximumWidth(1200)
    w.rehab_sections.widget(0).setMaximumWidth(1200)
    # A three-way native segmented navigator: keep original plan workspace intact.
    overview=w.rehab_sections.widget(0).layout()
    overview.removeWidget(w.rehab_tabs)
    w.rehab_modes=SegmentTabs();w.rehab_modes.setObjectName('rehabModes')
    w.rehab_modes.addTab(w.rehab_tabs,'训练')
    assess=QWidget();assess_box=QVBoxLayout(assess);assess_box.setContentsMargins(0,24,0,0)
    assessment_grid=ResponsiveGrid(threshold=700);assess_box.addWidget(assessment_grid);assess_box.addStretch()
    assessment_intro=QFrame();assessment_intro.setObjectName('careJournal')
    a=QVBoxLayout(assessment_intro);a.setContentsMargins(24,24,24,24);a.setSpacing(20)
    a.addWidget(visual(label('了解现在的活动情况'),typography='display'))
    a.addWidget(label('选择身体部位和动作，按指导完成评估。结果会保存在首页的“我的记录与周报”。'))
    a.addWidget(w.interface_buttons['rehabEvaluateNow'],0,Qt.AlignLeft)
    a.addStretch()
    assessment_grid.add(assessment_intro)
    preparation=QWidget();prep=QVBoxLayout(preparation);prep.setContentsMargins(24,12,24,12);prep.setSpacing(18)
    prep.addWidget(visual(label('开始前，核对这两项'),typography='section'))
    prep.addWidget(label('身体档案与测量条件\n查看已有身体部位资料，按原评估流程核对动作与测量条件。'))
    prep.addWidget(w.interface_buttons['rehabBody'],0,Qt.AlignLeft)
    prep.addWidget(label('个人康复信息\n确认正在为本人记录，结果按当前档案保存。'))
    w._action(prep,'assessmentProfile','个人康复信息',w.legacy._edit_participant,kind='A',target='原参与者档案')
    prep.addStretch();assessment_grid.add(preparation)
    w.rehab_modes.addTab(assess,'评估')
    fitness=QWidget();f=QVBoxLayout(fitness);f.setContentsMargins(24,24,24,24);f.setSpacing(20)
    f.addWidget(visual(label('选择适合自己的健身动作'),typography='display'))
    f.addWidget(label('在动作库查看做法，拍摄或选择视频进行分析。可以使用电脑浏览器，也可以连接自己的手机。'))
    w._action(f,'fitnessConnect','打开连接与健身工具',w._connect_phone,target='本人手机连接/现有健身工具')
    f.addWidget(visual(label('01  开启连接并复制连接码\n\n02  在浏览器连接本人档案，进入“康复 → 健身”\n\n03  选择动作、查看指导，再拍摄或选择视频'),typography='secondary'))
    f.addStretch();w.rehab_modes.addTab(fitness,'健身')
    overview.addWidget(w.rehab_modes)
    entry=w._action(w.plan_hint.parentWidget().layout(),'trainingAssessmentEntry','去做评估',lambda:w.rehab_modes.setCurrentIndex(1),target='康复/评估')
    visual(entry,appearance='primary')
    # Status belongs in an explicit disclosure, away from the primary composer.
    w.interface_buttons['assistantVoiceSettings'].setText('语音设置')
    w.interface_buttons['assistantReferenceEntry'].setText('记录与能力说明')
    w.assistant_status_toggle.setText('连接与能力')
    w.home_hello.setProperty('fluentType','section')
    for text in (w.home_intro,w.home_schedule):text.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Preferred)


def open_records(w,report=False,selected='全部'):
    if w.navigate('history'):
        w.history_filter.setCurrentText(selected)
        w.history_tabs.setCurrentIndex(1 if report else 0)


def refresh(w):
    w.interface_buttons['trainingAssessmentEntry'].setVisible(not bool(w._selected_plan()))
    report=w.snapshot.get('history',{}).get('report',{})
    w.home_week_range.setText(report.get('rangeText','本周暂无记录'))
    sections=report.get('sections',[])
    w.home_week_preview.setText('<br><br>'.join('<b>'+escape(s['title'])+'</b><br>'+escape('；'.join(s.get('lines',[])[:2])) for s in sections[:3]) or '记录身体情况或完成一次评估后，在这里回看。')
    w.assistant_status_toggle.setText('连接与能力')
    w.assistant_reference.setText(w.assistant_reference.text()+'\n这些是已保存记录的范围。上传原文件不自动成为模型上下文。' if '上传原文件' not in w.assistant_reference.text() else w.assistant_reference.text())
