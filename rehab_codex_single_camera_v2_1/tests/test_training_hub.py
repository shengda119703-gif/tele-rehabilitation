import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import copy
import pytest
from PySide6.QtWidgets import QApplication
from app.settings import default_plan
from app.ui.training_hub import TrainingHub


@pytest.fixture(scope='module')
def qt_app():
    return QApplication.instance() or QApplication([])


SCOPE = dict(participant_id='test-person', source_kind='SYNTHETIC', usage_context='TEST')


def plan():
    result = default_plan('shoulder_abduction')
    result.update(submode='training', participant_id='test-person', side='left')
    result['assessment_reference'] = dict(SCOPE, status='ASSESSED', session_id='test-1',
                                          exercise_id='shoulder_abduction', side='left')
    return result


def test_hub_does_not_invent_a_plan(qt_app):
    hub = TrainingHub()
    hub.set_plan({}, SCOPE)
    assert not hub.has_reference and hub.resume.isHidden()
    assert not hub.plan_details.text()
    received = []
    hub.assessment_requested.connect(lambda: received.append('assessment'))
    hub.records_requested.connect(lambda: received.append('records'))
    hub.assess.click()
    hub.records.click()
    assert received == ['assessment', 'records']


def test_hub_offers_explicit_isolated_demo_generation(qt_app):
    hub = TrainingHub()
    received = []
    hub.demo_requested.connect(lambda: received.append('demo'))
    hub.demo.click()
    assert received == ['demo']
    assert '合成评估' in hub.demo.toolTip()


def test_hub_shows_only_current_preparation_and_never_confirms_plan(qt_app):
    hub = TrainingHub()
    current = plan()
    before = copy.deepcopy(current)
    hub.set_plan(current, SCOPE)
    assert hub.has_reference and '待确认' in hub.plan_details.text()
    assert '左侧' in hub.plan_title.text()
    assert current == before


@pytest.mark.parametrize('key,value', [('participant_id', 'someone-else'), ('source_kind', 'LIVE_CAMERA'),
                                      ('usage_context', 'SELF_USE'), ('side', 'right'),
                                      ('exercise_id', 'wrist_flexion'), ('status', 'UNAVAILABLE')])
def test_hub_rejects_mismatched_or_unavailable_reference(qt_app, key, value):
    hub = TrainingHub()
    current = plan()
    current['assessment_reference'][key] = value
    hub.set_plan(current, SCOPE)
    assert not hub.has_reference and hub.resume.isHidden()
