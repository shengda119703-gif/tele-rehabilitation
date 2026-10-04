"""Recovery dashboard semantics and cross-page state; explicit TEST inputs only."""
from datetime import datetime, timedelta
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from test_product_window import desktop, wait
from app.ui.product_widgets import rows


def test_recovery_does_not_count_interrupted_or_missing_measurements(desktop):
    w,app=desktop
    today=datetime.now().astimezone().date()
    stamp=datetime.now().astimezone().isoformat()
    training=[dict(id='TEST-ok',exercise_label='TEST 肩',end_utc=stamp,status='FINISHED',
                   summary=dict(completed=5,plan_completed=True),training_feedback=dict(pain=0,fatigue=2,revision=1)),
              dict(id='TEST-interrupted',exercise_label='TEST 肩',end_utc=stamp,status='INTERRUPTED',
                   summary=dict(completed=1,plan_completed=False),training_feedback=dict(pain=3,fatigue=4,revision=1))]
    assessment=[dict(exercise_id='shoulder_abduction',exercise_label='TEST 肩',side='left',end_utc=stamp,
                     status='UNAVAILABLE',motion_range=None),
                dict(exercise_id='shoulder_abduction',exercise_label='TEST 肩',side='left',end_utc=stamp,
                     status='ASSESSED',motion_range=dict(range_deg=77))]
    w._render_recovery(training,assessment,None,today)
    assert '完成目标 1 次' in w.recovery_fields['trend'].text()
    assert '50%' in w.recovery_fields['trend'].text()
    assert '3 → 0' in w.recovery_fields['trend'].text()
    assert '最近幅度：未取得有效幅度' in w.recovery_fields['assessment'].text()
    assert '上次幅度：77°' in w.recovery_fields['assessment'].text()
    w._render_recovery([],[],None,today)
    assert '尚无完成率' in w.recovery_fields['trend'].text()
    assert '暂无训练结果' in w.recovery_fields['result'].text()
    assert '暂无评估记录' in w.recovery_fields['assessment'].text()


def test_week_counts_use_record_local_dates_and_exclude_future(desktop):
    w,app=desktop;today=datetime.now().astimezone().date()
    monday=today-timedelta(days=today.weekday())
    records=[dict(exercise_label='TEST 肩',end_utc=str(day)+'T12:00:00+08:00',status='FINISHED',
                  summary=dict(completed=1,plan_completed=True)) for day in (monday-timedelta(days=1),monday,today+timedelta(days=1))]
    w._render_recovery(records,[],None,today)
    assert '本周已保存 1 次训练' in w.recovery_fields['trend'].text()


def test_refresh_preserves_selected_record_and_deleted_record_clears_selection(desktop):
    w,app=desktop
    values=[('TEST-a','first',''),('TEST-b','second','')]
    rows(w.timeline,values);w.timeline.selectRow(1)
    rows(w.timeline,list(reversed(values)))
    assert w.timeline.currentRow()==0 and w.timeline.item(0,0).text()=='TEST-b'
    rows(w.timeline,[values[0]])
    assert w.timeline.currentRow()==-1


def test_refresh_uses_record_ids_when_display_values_are_identical(desktop):
    w,app=desktop
    values=[('TEST-same-time','TEST duplicate',''),('TEST-same-time','TEST duplicate','')]
    rows(w.timeline,values,keys=['TEST-a','TEST-b']);w.timeline.selectRow(1)
    rows(w.timeline,values,keys=['TEST-b','TEST-a'])
    assert w.timeline.currentRow()==0
    rows(w.timeline,[values[0]],keys=['TEST-a'])
    assert w.timeline.currentRow()==-1


def test_notifications_return_keeps_filter_and_selected_notification(desktop):
    w,app=desktop;w.navigate('notifications');wait(app,lambda:not w.pending)
    notification=dict(id='TEST-note',findingId='TEST-finding',title='TEST 健康提示',createdAt='TEST-time',
                      phase='sent',lifecycle='acknowledged')
    w.snapshot['notifications']=[notification];w.notification_filter.setCurrentText('已确认');w._render_notifications()
    w.notifications.selectRow(0)
    w.refresher.stop()
    # Hold the synthetic rendered snapshot in this unit test; business dispatch is covered separately.
    w._notification_business()
    assert w.active_page=='health' and w.context_return.text()=='返回通知'
    assert w.return_context==('notifications','health')
    QTest.mouseClick(w.context_return,Qt.LeftButton)
    assert w.active_page=='notifications' and w.notification_filter.currentText()=='已确认'
    assert w.return_context is None
    wait(app,lambda:not w.pending)


def test_training_focus_preserves_camera_pause_end_and_save_failure_guards(desktop):
    w,app=desktop;w.navigate('rehab');wait(app,lambda:not w.pending)
    w._show_rehab_scope(True);w.legacy._select_rehab('training')
    for state in ('ONLINE','SAVE_FAILED'):
        w.legacy.state=state;w.legacy._buttons();w._completion_controls();app.processEvents()
        assert not w.product_sidebar.isVisible() and not w.product_top.isVisible()
        assert not w.legacy.setup_tabs.isVisible()
        assert not w.legacy.device.parentWidget().isVisible()
        assert w.legacy.training_panel.isVisible()
        assert not w.interface_buttons['rehabWorkspaceBack'].isEnabled()
        if state=='ONLINE':
            assert w.legacy.stop_button.isVisible() and w.legacy.video_pair.isVisible()
            w.legacy._last_coach_view=dict(guidance=dict(instruction='TEST 请回到起点',status='TEST 等待回程',level='normal'))
            w.legacy._refresh_guidance_visibility()
            assert w.legacy.feedback.isVisible() and 'TEST 请回到起点' in w.legacy.feedback.text()
        else:assert w.legacy.retry_button.isVisible() and w.legacy.backup_button.isVisible()
    w.legacy.state='UNSELECTED';w.legacy._buttons();w._completion_controls();app.processEvents()
    assert w.product_sidebar.isVisible() and w.product_top.isVisible()
    assert w.legacy.setup_tabs.isVisible()
