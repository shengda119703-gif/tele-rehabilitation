"""Actual command loop with injected synthetic streams, never hardware capture."""
import queue
import time

from app.dual_camera import make_dual_source
from app.settings import default_setup
from app.storage import Storage
from test_dual_runtime_integration import runtime, checked_command, wait_view
from test_dual_camera import REFS


def test_actual_countdown_loop_keeps_preview_until_final_manual_confirm_and_saves_binding(runtime, tmp_path):
    r = runtime
    setup = default_setup()
    setup.update(participant_confirmed=True, dual_camera=dict(primary_view='frontal', same_participant_confirmed=True))
    checked_command(r, 'open', source=make_dual_source(REFS, 'frontal', 'TEST'), setup=setup)
    data = wait_view(r, lambda v: v.get('current_measurement_valid'))
    checked_command(r, 'prepare_sample', sample='joint_baseline', position='rest', expected_context=data['context'])
    assert r.controller.state == 'PREVIEW' and r.controller.session is None
    deadline, baseline = time.monotonic()+6., None
    while time.monotonic() < deadline:
        message = r.messages.get(timeout=6)
        assert message['kind'] != 'fatal'
        if message['kind'] == 'joint_baseline':
            baseline = message['baseline']
        if message['kind'] == 'preparation' and not message['active']:
            assert '已记录' in message['text'], message
            break
    assert baseline is not None and not r.controller.confirmed
    assert r.controller.state == 'PREVIEW' and r.store.list_sessions() == []
    setup['plan']['joint_baseline'] = baseline
    checked_command(r, 'confirm', setup=setup)
    checked_command(r, 'start')
    data = wait_view(r, lambda v: v['state'] == 'ONLINE' and v.get('current_measurement_valid'))
    assert data['guidance']['level'] == 'action'
    sid = r.controller.session['id']
    checked_command(r, 'stop')
    reader = Storage(tmp_path/'home_rehab.sqlite3')
    saved = reader.get_session(sid)
    reader.close()
    assert saved['config_snapshot']['plan']['joint_baseline'] == baseline
    assert saved['dual_camera']['validity_policy'] == 'primary-focus-with-auxiliary-1'


def test_actual_countdown_cancel_remains_responsive_without_starting_a_session(runtime):
    r = runtime
    setup = default_setup()
    checked_command(r, 'open', source=make_dual_source(REFS, 'frontal', 'TEST'), setup=setup)
    data = wait_view(r, lambda v: v.get('current_measurement_valid'))
    checked_command(r, 'prepare_sample', sample='joint_baseline', position='rest', expected_context=data['context'])
    checked_command(r, 'cancel_preparation')
    assert r.preparation is None and not r.controller.live_joint_baseline
    assert r.controller.state == 'PREVIEW' and r.store.list_sessions() == []
    checked_command(r, 'stop')
    assert r.camera.worker is None
