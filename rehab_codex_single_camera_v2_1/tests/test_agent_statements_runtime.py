from statement_fixtures import CONFIG, transport
from statement_fixtures import interpretation
import json
from app.runtime import Runtime
from app.storage import Storage
from app.silver_store import SilverStore
from test_automatic_plans import SCOPE, measured
from test_training_runtime import response


def test_real_queue_save_reopen_retract_no_clinical_mutation(tmp_path, monkeypatch):
    monkeypatch.setattr('app.agent_extraction.complete', transport)
    store = Storage(tmp_path/'home_rehab.sqlite3')
    store.save_session(measured())
    original = store.list_sessions()
    store.close()
    runtime = Runtime(tmp_path)
    try:
        assert runtime.ready.wait(5)
        def turn(text='', **kw):
            payload = dict(scope=SCOPE, text=text, request_id='test', conversation_id='window1', config=CONFIG)
            if text == '查看自报记录':
                payload['operation'] = 'list'
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


def test_unavailable_extraction_keeps_local_queries_and_never_creates_support_db(tmp_path, monkeypatch):
    from app.agent_conversation import ModelError
    def down(*args, **kwargs):
        raise ModelError('network unavailable')
    monkeypatch.setattr('app.agent_extraction.complete', down)
    runtime = Runtime(tmp_path)
    try:
        assert runtime.ready.wait(5)
        for config in (None, CONFIG):
            messages = response(runtime, 'rehab_agent', scope=SCOPE, text='请查看我的评估结果',
                                config=config, request_id='offline', conversation_id='offline')
            result = next(m['result'] for m in messages if m['kind'] == 'rehab_agent')
            assert '暂不可用' in result['main_text'] and result['local_text']
            assert result['actions'] and not result['proposed_actions']
            assert result['privacy_status']['network'] == ('not_sent' if config is None else 'may_have_been_sent')
        messages = response(runtime, 'rehab_agent', scope=SCOPE, text='我今天发烧',
                            config=CONFIG, request_id='failed-health', conversation_id='offline')
        result = next(m['result'] for m in messages if m['kind'] == 'rehab_agent')
        assert '暂不可用' in result['main_text'] and not result['local_text']
        assert not result['proposed_actions']
        assert runtime.camera.worker is None
        assert not (tmp_path/'silver_support.sqlite3').exists()
    finally:
        response(runtime, 'shutdown')
        runtime.thread.join(5)


def test_reset_and_scope_change_destroy_runtime_refs_and_tokens(tmp_path, monkeypatch):
    packets = []
    target = [None]
    def provider(config, messages):
        packet = json.loads(messages[-1]['content'])
        packets.append(packet)
        text = packet['current']['raw_text']
        value = interpretation(text, act='correction', target=target[0]) if target[0] else interpretation(text)
        return json.dumps(value)
    monkeypatch.setattr('app.agent_extraction.complete', provider)
    runtime = Runtime(tmp_path)
    try:
        assert runtime.ready.wait(5)
        def call(**changes):
            payload = dict(scope=SCOPE, text='测试文字', config=CONFIG, request_id='test', conversation_id='window')
            payload.update(changes)
            return response(runtime, 'rehab_agent', **payload)
        first = next(m['result'] for m in call() if m['kind'] == 'rehab_agent')
        token = first['proposed_actions'][0]['id']
        target[0] = first['understanding'][0]['id']
        response(runtime, 'rehab_agent', operation='reset', conversation_id='window')
        failed = next(m['result'] for m in call() if m['kind'] == 'rehab_agent')
        assert failed['extraction_status'] == 'needs_clarification'
        assert not packets[-1]['context']['events']
        assert any(m['kind'] == 'error' for m in call(operation='act', action_id=token))
        assert any(m['kind'] == 'error' for m in call(scope=dict(SCOPE, participant_id='other')))
        assert not (tmp_path/'silver_support.sqlite3').exists()
    finally:
        response(runtime, 'shutdown')
        runtime.thread.join(5)
