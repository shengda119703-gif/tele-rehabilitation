import copy
import csv
import json

import pytest

from app.longitudinal import compare_conditions, condition_snapshot
from app.reports import export_session, render_report
from test_dual_controller import DualFixture


@pytest.fixture
def dual_session(tmp_path):
    f = DualFixture(tmp_path)
    try:
        ctx = f.start()
        f.cycle()
        f.c.stop('user_stop')
        return f.store.get_session(ctx.run_id)
    finally:
        f.close()


def test_report_and_csv_keep_two_sources_measured_delta_and_auxiliary_metric_validity(dual_session, tmp_path):
    out = export_session(dual_session, tmp_path/'dual-export')
    with (out/'dual-camera.csv').open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 60
    assert rows[0]['primary_view'] == 'frontal' and rows[0]['secondary_view'] == 'sagittal'
    assert float(rows[0]['receive_delta_s']) == pytest.approx(.02)
    assert float(rows[0]['aux_trunk_sagittal_deg']) > 40 and rows[0]['aux_trunk_sagittal_deg_valid'] == 'True'
    assert rows[0]['primary_source_ref'] != rows[0]['secondary_source_ref']
    assert rows[0]['validity_policy'] == 'primary-focus-with-auxiliary-1'
    assert rows[0]['primary_used'] == 'True' and rows[0]['identity_confirmed'] == 'True'
    metadata = json.loads((out/'session.json').read_text(encoding='utf-8'))
    assert metadata['capture_mode'] == 'dual'
    assert metadata['dual_camera']['summary'] == dual_session['dual_camera']['summary']
    html = (out/'report.html').read_text(encoding='utf-8')
    assert '双摄观察' in html and '接收时间' in html and '曝光同步' in html
    assert '躯干倾斜（侧面）' in html
    assert not (out/'poses.jsonl').exists()
    combined = ''.join(p.read_text(encoding='utf-8-sig') for p in out.iterdir())
    assert 'synthetic-path' not in combined and 'participant-local' not in combined
    assert 'device_ref' not in combined


def test_missing_auxiliary_metrics_are_empty_values_with_reasons_in_csv(dual_session, tmp_path):
    row = dual_session['dual_camera']['observations'][0]
    row['auxiliary_metrics']['aux_trunk_sagittal_deg'] = dict(value=None, valid=False, reason='low_confidence')
    row['auxiliary_status'], row['jointly_valid'] = 'UNKNOWN', False
    out = export_session(dual_session, tmp_path/'missing-export')
    with (out/'dual-camera.csv').open(encoding='utf-8-sig', newline='') as stream:
        first = next(csv.DictReader(stream))
    assert first['aux_trunk_sagittal_deg'] == '' and first['aux_trunk_sagittal_deg_valid'] == 'False'
    assert first['aux_trunk_sagittal_deg_reason'] == 'low_confidence'


def test_old_and_new_dual_validity_rules_are_different_comparison_conditions(dual_session):
    old = copy.deepcopy(dual_session)
    old['dual_camera'].pop('validity_policy')
    comparison = compare_conditions(dual_session, old)
    assert comparison['status'] != 'MATCH' and 'dual_camera' in comparison['differences']
    assert compare_conditions(old, copy.deepcopy(old))['status'] == 'MATCH'


def test_old_single_camera_report_does_not_acquire_dual_measurements(dual_session, tmp_path):
    dual_session.pop('dual_camera')
    dual_session.pop('capture_mode', None)
    dual_session['config_snapshot'].pop('dual_camera')
    dual_session['source_ref'] = 'camera:single-fixture'
    out = export_session(dual_session, tmp_path/'old-single')
    assert not (out/'dual-camera.csv').exists()
    assert '双摄观察' not in (out/'report.html').read_text(encoding='utf-8')


def test_comparison_keeps_exact_secondary_source_model_resolution_and_pairing_conditions(dual_session):
    assert compare_conditions(dual_session, copy.deepcopy(dual_session))['status'] == 'MATCH'
    for field, value in [('source_ref', 'changed-camera'), ('model_manifest_id', 'changed-model'),
                         ('schema_id', 'different-schema'), ('measurement_contract', 'changed-contract')]:
        other = copy.deepcopy(dual_session)
        other['dual_camera']['streams']['sagittal'][field] = value
        compared = compare_conditions(dual_session, other)
        assert compared['status'] == 'DIFFERENT' and 'dual_camera.sagittal' in compared['differences']
    other = copy.deepcopy(dual_session)
    other['dual_camera']['streams']['sagittal']['actual_capture']['size'] = [640, 480]
    assert compare_conditions(dual_session, other)['status'] == 'DIFFERENT'
    other = copy.deepcopy(dual_session)
    other['dual_camera']['max_receive_delta_s'] = .3
    assert compare_conditions(dual_session, other)['status'] == 'DIFFERENT'


def test_missing_secondary_conditions_are_unknown_on_both_sides(dual_session):
    for key in ('source_ref', 'schema_id', 'model_manifest_id'):
        missing = copy.deepcopy(dual_session)
        missing['dual_camera']['streams']['sagittal'].pop(key)
        assert 'dual_camera.sagittal' in condition_snapshot(missing)['missing']
        assert compare_conditions(missing, copy.deepcopy(missing))['status'] == 'UNKNOWN'


def test_missing_dual_payload_is_not_interpreted_as_legacy_single_camera(dual_session):
    broken = copy.deepcopy(dual_session)
    broken.pop('dual_camera')
    assert compare_conditions(broken, copy.deepcopy(broken))['status'] == 'UNKNOWN'


def test_single_and_dual_modes_do_not_compare_even_if_other_identifiers_are_copied(dual_session):
    single = copy.deepcopy(dual_session)
    single['capture_mode'] = 'single'
    single.pop('dual_camera')
    single['config_snapshot'].pop('dual_camera')
    single['source_ref'] = 'camera:single-fixture'
    result = compare_conditions(dual_session, single)
    assert result['status'] == 'DIFFERENT' and 'capture_mode' in result['differences']
