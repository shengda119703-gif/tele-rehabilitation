from app.runtime import Runtime
from app.storage import Storage
from app.silver_store import SilverStore
from test_automatic_plans import SCOPE, measured
from test_training_runtime import response


def test_real_queue_save_reopen_retract_no_clinical_mutation(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('self reports must stay local')
    monkeypatch.setattr('app.agent_conversation.complete', forbidden)
    store = Storage(tmp_path/'home_rehab.sqlite3')
    store.save_session(measured())
    original = store.list_sessions()
    store.close()
    runtime = Runtime(tmp_path)
    try:
        assert runtime.ready.wait(5)
        def turn(text='', **kw):
            payload = dict(scope=SCOPE, text=text, request_id='test', conversation_id='window1')
            payload.update(kw)
            messages = response(runtime, 'rehab_agent', **payload)
            assert not [m for m in messages if m['kind'] == 'error'], messages
            return next(m['result'] for m in messages if m['kind'] == 'rehab_agent')
        for text in ('昨天妈妈头晕', '我今天没头晕', '我刚才说错了'):
            assert not turn(text)['proposed_actions']
        result = turn('我今天头晕')
        token = result['proposed_actions'][0]['id']
        assert not (tmp_path/'silver_support.sqlite3').exists()
        result = turn(operation='act', action_id=token)
        assert result['receipt']['status'] == 'saved'
        care = SilverStore(tmp_path/'silver_support.sqlite3')
        assert len(care.records(SCOPE, 'agent_self_report')) == 1
        response(runtime, 'rehab_agent', operation='reset', conversation_id='window1')
        result = turn('我刚才说错了', conversation_id='window2')
        assert not result['proposed_actions']
        result = turn('查看自报记录', conversation_id='window2')
        assert '头晕' in result['record_summary']
        token = result['proposed_actions'][0]['id']
        result = turn(operation='act', action_id=token, conversation_id='window2')
        assert result['receipt']['status'] == 'retracted'
        assert care.records(SCOPE, 'agent_self_report')[0]['status'] == 'RETRACTED'
        assert runtime.camera.worker is None
        assert not care.records(SCOPE, 'request') and not care.records(SCOPE, 'feedback')
        messages = response(runtime, 'rehab_agent', scope=dict(SCOPE, participant_id='other'),
                            conversation_id='window2', operation='act', action_id=token, request_id='wrong')
        assert any(m['kind'] == 'error' for m in messages)
    finally:
        response(runtime, 'shutdown')
        runtime.thread.join(5)
    store = Storage(tmp_path/'home_rehab.sqlite3')
    try:
        assert store.list_sessions() == original
        assert not store.list_training_plans(SCOPE)
    finally:
        store.close()
