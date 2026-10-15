"""Read-only B03/B04 contract tests. TEST envelopes are not motion evidence."""
from copy import deepcopy
from threading import RLock
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.rehab_v2.cues import CueEvents
from mobile_rehab.rehab_v2.service import SessionService


def projection_service():
    cue = dict(cue_id='TEST-cue', session_id='TEST-session', exercise_id='shoulder_abduction',
               side='left', calibration_epoch=1, valid_phases=['START'],
               expires_at_source_s=2., ttl_after_emission_ms=2000,
               evidence_refs=[dict(seq=1)], instruction='TEST original instruction')
    cues = CueEvents('TEST-session')
    cues.current, cues.last_emission = deepcopy(cue), 100.
    fact = dict(session_id='TEST-session', current_cue=cue,
                frozen_plan=dict(plan=dict(submode='assessment')))
    runtime = SimpleNamespace(lock=RLock(), cues=cues, started=99.,
                              engine=SimpleNamespace(last_t=1.5, phase='START', calibration_epoch=1))
    service = SessionService.__new__(SessionService)
    alive = SimpleNamespace(is_alive=lambda: True)
    service.worker = service.report_worker = service.finish_worker = alive
    service.worker_failure = service.report_worker_failure = service.last_storage_fault = None
    service.resources_released = False
    service.internal_replay = True
    service.runtimes = {'TEST-session': runtime}
    service._report_execution_contract = lambda: dict(mode='TEST-projection-only')
    service.repository = SimpleNamespace(get=lambda owner, sid: deepcopy(fact),
                                         plan_contribution=lambda owner, sid: None)
    return service, runtime, fact


def test_remaining_ttl_uses_original_shorter_source_budget_without_writing_fact():
    service, runtime, fact = projection_service()
    before = deepcopy(fact)
    with patch('mobile_rehab.rehab_v2.service.time.monotonic', return_value=100.25):
        result = service.get('TEST-owner', 'TEST-session')
    assert result['current_cue']['remaining_ttl_ms'] == pytest.approx(500.)
    assert 'remaining_ttl_ms' not in runtime.cues.current
    assert fact == before


@pytest.mark.parametrize('change', ['source_expired', 'emission_expired', 'phase_changed', 'epoch_changed'])
def test_original_cue_invalidations_do_not_expose_a_new_ttl(change):
    service, runtime, fact = projection_service()
    now = 100.25
    if change == 'source_expired':
        runtime.engine.last_t = 2.1
    elif change == 'emission_expired':
        now = 102.1
    elif change == 'phase_changed':
        runtime.engine.phase = 'RETURN'
    else:
        runtime.engine.calibration_epoch = 2
    with patch('mobile_rehab.rehab_v2.service.time.monotonic', return_value=now):
        assert service.get('TEST-owner', 'TEST-session')['current_cue'] is None
    assert 'remaining_ttl_ms' not in fact['current_cue']


def test_history_mode_is_read_from_original_plan_not_zero_contribution():
    service, _, _ = projection_service()
    stored = dict(items=[dict(session_id='TEST-assessment', contribution=dict(completed_reps=0)),
                         dict(session_id='TEST-training', contribution=dict(completed_reps=0))],
                  next_cursor=None)
    modes = {'TEST-assessment': 'assessment', 'TEST-training': 'training'}
    service.repository.history = lambda owner, **options: deepcopy(stored)
    service.repository.get = lambda owner, sid: dict(frozen_plan=dict(plan=dict(submode=modes[sid])))
    result = service.history('TEST-owner')
    assert [i['submode'] for i in result['items']] == ['assessment', 'training']
    assert all('submode' not in i for i in stored['items'])
    assert all(i['contribution']['completed_reps'] == 0 for i in result['items'])
