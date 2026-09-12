from datetime import datetime, timedelta, timezone

import pytest

from app.runtime import Runtime
from app.storage import Storage
from test_automatic_plans import measured, SCREEN, SCOPE
from test_training_runtime import response


def output(runtime, command, kind, **kwargs):
    replies = response(runtime, command, **kwargs)
    errors = [m for m in replies if m['kind'] == 'error']
    assert not errors, errors
    return next(m for m in replies if m['kind'] == kind)


def test_real_runtime_propose_accept_prepare_feedback_resume_without_camera(tmp_path):
    store = Storage(tmp_path/'home_rehab.sqlite3')
    now = datetime.now(timezone.utc)
    for eid in ('shoulder_abduction', 'knee_extension'):
        store.save_session(measured(eid, start_utc=(now-timedelta(minutes=2)).isoformat(),
                                    end_utc=(now-timedelta(minutes=1)).isoformat()))
    store.close()
    r = Runtime(tmp_path)
    try:
        assert r.ready.wait(5)
        p = output(r, 'automatic_proposal', 'automatic_proposal', scope=SCOPE)['proposal']
        assert len(p['candidates']) == 2
        msg = output(r, 'accept_automatic_plan', 'automatic_progress', scope=SCOPE,
                     fingerprint=p['fingerprint'], screening=SCREEN)
        record = msg['record']
        key = msg['progress']['next_key']
        args = dict(scope=SCOPE, id=record['id'], revision=record['revision'], entry_key=key)
        plan = output(r, 'prepare_automatic_item', 'automatic_item_prepared', **args)['plan']
        assert plan['training_plan_confirmed'] is True
        assert plan['calibration'] == plan['joint_baseline'] == {}
        assert plan['assessment_reference']['session_id'] == measured()['id']
        assert r.camera.worker is None
        # The regular library cannot edit automatic doses or bypass sequencing.
        replies = response(r, 'save_training_plan', scope=SCOPE, plan=record, expected_revision=record['revision'])
        assert any(m['kind'] == 'error' for m in replies)
        msg = output(r, 'automatic_proposal', 'automatic_proposal', scope=SCOPE)
        assert msg['record']['id'] == record['id']
        replies = response(r, 'accept_automatic_plan', scope=SCOPE, fingerprint='stale', screening=SCREEN)
        assert any(m['kind'] == 'error' and '刷新' in m['text'] for m in replies)
    finally:
        response(r, 'shutdown')
        r.thread.join(5)
        assert not r.thread.is_alive()
    store = Storage(tmp_path/'home_rehab.sqlite3')
    try:
        assert store.get_training_plan(record['id'])['automatic']['screening'] == SCREEN
        assert len(store.list_sessions()) == 2  # no invented training run
    finally:
        store.close()


def test_controller_accepts_canonical_auto_plan_but_rejects_tampered_dose(tmp_path):
    from test_app_joint_expansion_flow import SyntheticSession
    from app.assessment import build_body_profile
    from app.automatic_plans import generate_proposal, create_automatic_plan
    from app.training_plans import prepare_training_plan
    task = SyntheticSession(tmp_path, 'ankle_dorsiflexion', 'left')
    c = task.controller
    try:
        task.calibrate()
        c.start()
        task.feed(0.)
        task.feed(30.)
        task.feed(0.)
        c.stop('user_stop')
        sessions = task.store.list_sessions()
        scope = dict(participant_id='participant-local', source_kind='SYNTHETIC', usage_context='TEST')
        profile = build_body_profile(sessions, **scope)
        p = generate_proposal(profile, sessions)
        assert len(p['candidates']) == 1, p
        record = task.store.save_training_plan(create_automatic_plan(p, SCREEN), expected_revision=0)
        plan = prepare_training_plan(record, record['items'][0]['key'], profile)
        plan['training_plan_confirmed'] = True
        task.open(plan['assessment_reference'])
        task.calibrate()
        c.setup['plan'].update({k: v for k, v in plan.items() if k not in ('joint_baseline', 'calibration')})
        c.setup['plan']['target_reps'] += 1
        with pytest.raises(ValueError, match='参数已改变'):
            c.start()
        c.setup['plan']['target_reps'] -= 1
        c.start()
        task.feed(0.)
        task.feed(30.)
        task.feed(0.)
        sid = c.session['id']
        c.stop('user_stop')
        saved = task.store.get_session(sid)
        assert saved['saved_plan_reference']['record_origin'] == 'assessment_rules'
        assert saved['summary']['plan_completed'] is True
        assert saved['summary']['observed_quality']['observed_goals_met'] == 1
        from app.reports import render_report
        report = render_report(saved)
        assert '根据评估自动安排' in report and 'general-activity-rules-1' in report
    finally:
        task.close()
