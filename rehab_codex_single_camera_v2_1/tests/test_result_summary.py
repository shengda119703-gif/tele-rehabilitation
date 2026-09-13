import copy
import pytest
from app.reports import render_result_summary, render_report
from app.settings import default_setup, default_plan


def snapshot(eid='neck_flexion'):
    setup = default_setup()
    setup['plan'] = default_plan(eid)
    setup['view'] = 'sagittal'
    return dict(id='saved-example', scene_id='rehab', exercise_id=eid, submode='assessment', side='left',
                source_kind='SYNTHETIC', usage_context='TEST', status='FINISHED', config_snapshot=setup,
                summary=dict(completed=2, partial=1, invalid=1, valid_ratio=.75, valid_s=9., observed_span_s=12.,
                             motion_range=dict(min_deg=0., max_deg=25., range_deg=25.), valid_sample_count=6),
                repetitions=[dict(number=1, completion_status='COMPLETE', target_status='NOT_SET',
                                  movement_timing=dict(outbound_s=dict(value=2., valid=True),
                                                       return_s=dict(value=99., valid=False)), issues=[])])


def test_plain_language_numbers_and_limits_are_in_dialog_and_export():
    s = snapshot()
    before = copy.deepcopy(s)
    for html in (render_result_summary(s), render_report(s)):
        for text in ('25.0°', '2 次', '75.0 %', '2.0 秒（1 次记录的中位数）', '未设置目标 1 次',
                     '不要求髋部入镜', '不是识别准确率', '不是临床关节活动度', '不等于动作完全正常'):
            assert text in html
        assert '99.0 秒' not in html
    assert s == before


@pytest.mark.parametrize('ratio,range_value', [(0., dict(min_deg=0., max_deg=25., range_deg=25.)),
                                              (.75, None), (.75, dict(min_deg=0., max_deg=float('nan'), range_deg=20.))])
def test_invalid_range_is_absent_not_zero(ratio, range_value):
    s = snapshot()
    s['summary'].update(valid_ratio=ratio, motion_range=range_value)
    html = render_result_summary(s)
    assert '暂无可解释的角度范围' in html
    assert '不是活动幅度为零' in html


def test_strings_are_escaped_and_unverified_issue_not_called_diagnosis():
    s = snapshot()
    s['summary']['primary_metric_label'] = '<script>alert(1)</script>'
    s['repetitions'][0]['issues'] = [dict(rule_id='elbow_flexion', evidence_valid=False)]
    html = render_result_summary(s)
    assert '<script>' not in html and '&lt;script&gt;' in html
    assert '抬举时可见屈肘' not in html
    s['dual_camera'] = {'primary_view': 'sagittal'}
    assert '不是两路角度平均' in render_result_summary(s)


def test_patient_dual_explanation_matches_saved_policy_and_keeps_detailed_evidence():
    s = snapshot()
    s['dual_camera'] = {'primary_view': 'sagittal', 'validity_policy': 'primary-with-auxiliary-identity-1',
                        'summary': {'primary_used_observations': 12, 'main_only_observations': 3}}
    before = copy.deepcopy(s)
    overview = render_result_summary(s)
    detail = render_report(s)
    assert '辅助指标缺测只表示那一项无法评价' in overview
    assert '主测量实际纳入 12 帧' in detail and '其中辅助整体缺测 3 帧' in detail
    assert s == before
    del s['dual_camera']['validity_policy']
    assert '沿用保存时的双摄有效性规则' in render_result_summary(s)
    assert '辅助指标缺测只表示' not in render_result_summary(s)


def test_new_dual_focus_policy_explains_nonblocking_people_and_auxiliary_view():
    s = snapshot()
    s['dual_camera'] = {'primary_view': 'sagittal', 'secondary_view': 'frontal',
                        'validity_policy': 'primary-focus-with-auxiliary-1',
                        'summary': {'primary_used_observations': 12, 'main_only_observations': 3}}
    assert '陪同者入镜不阻止任务' in render_result_summary(s)
    detail = render_report(s)
    assert '启动不以人数、关节可见' in detail
    assert '主机位实际纳入' in detail and '辅助指标整体缺测' in detail
