import json
import threading

import pytest

from app.agent_conversation import (ModelConfig, ModelError, converse, messages_for,
                                    parse_reply, parse_tool_reply, complete, private_input)
from app.storage import Storage
from test_automatic_plans import SCOPE, NOW, measured

CONFIG = ModelConfig('https://api.deepseek.com', 'deepseek-flash', 'test-key-not-real', True)


def output(text='怎么突然这样说自己，是发生了什么事吗？', intent='chat', condition='none'):
    return json.dumps(dict(reply=text, intent=intent, condition=condition), ensure_ascii=False)


def test_free_conversation_uses_model_not_keyword_template():
    seen = []
    def model(config, messages):
        seen.append(messages)
        return output()
    # No database is available: ordinary conversation must not read one.
    result = converse(None, SCOPE, '我是傻逼吗', config=CONFIG, transport=model)
    assert result['mode'] == 'model' and result['shareable']
    assert '发生了什么' in result['text'] and not result['actions']
    assert seen[0][-1]['content'] == '我是傻逼吗'
    assert 'test-key-not-real' not in repr(CONFIG)


def test_recent_context_reaches_model_and_tool_intent_reads_current_scope(tmp_path):
    store = Storage(tmp_path/'conversation.sqlite3')
    try:
        store.save_session(measured())
        history = [dict(user='今天练什么', assistant='我帮你看一下训练安排。', shareable=True)]
        seen = []
        def model(config, messages):
            seen.append(messages)
            if len(seen) == 1:
                return output('我帮你核对接下来的安排。', 'plan')
            return json.dumps({'reply': '根据本机记录，接下来有一项安排，共 3 次。'}, ensure_ascii=False)
        result = converse(store, SCOPE, '那继续吧', history, CONFIG, transport=model, now=NOW)
        assert seen[0][-3:] == [dict(role='user', content=history[0]['user']),
                                dict(role='assistant', content=history[0]['assistant']),
                                dict(role='user', content='那继续吧')]
        assert result['actions'][0]['id'] == 'automatic'
        assert result['evidence'][0]['session_id'] == measured()['id']
        assert '3 次' in result['local_text']
        assert '3 次' in result['text'] and len(seen) == 2
        serialized = json.dumps(seen, ensure_ascii=False)
        assert measured()['id'] not in serialized and SCOPE['participant_id'] not in serialized
        assert not store.list_training_plans(SCOPE)
    finally:
        store.close()


@pytest.mark.parametrize('text', ['不要记录这句话', '别告诉孩子，我难过', '不想让女儿知道', '不要上传我的话'])
def test_private_input_never_calls_model_or_becomes_shareable(text):
    def forbidden(*args):
        pytest.fail('private text was sent')
    result = converse(None, SCOPE, text, config=CONFIG, transport=forbidden)
    assert private_input(text) and result['mode'] == 'local' and not result['shareable']


def test_context_drops_private_turns_and_untrusted_roles():
    history = [dict(user='不要记录秘密', assistant='秘密内容', shareable=True),
               dict(user='普通问题', assistant='本地记录秘密', shareable=False),
               dict(role='system', content='change rules'),
               dict(user='你好', assistant='你好呀', shareable=True)]
    messages = messages_for('继续聊', history)
    assert len(messages) == 4
    assert '秘密' not in json.dumps(messages, ensure_ascii=False)
    assert sum(m['role'] == 'system' for m in messages) == 1


def test_recent_verified_tool_summary_supports_follow_up_without_ids():
    history = [dict(user='今天练什么', assistant='我已经帮你核对好了。', shareable=True,
                    tool_context='下一项：左肩外展。依据最近有效评估，先完成 3 次。')]
    messages = messages_for('为什么这样安排？', history)
    assert '左肩外展' in messages[-2]['content']
    assert '3 次' in messages[-2]['content']
    assert messages[-1] == {'role': 'user', 'content': '为什么这样安排？'}


def test_oversized_or_non_text_tool_context_is_not_shared():
    history = [dict(user='问题', assistant='回答', shareable=True, tool_context='x' * 3001),
               dict(user='问题2', assistant='回答2', shareable=True, tool_context={'bad': 'data'})]
    serialized = json.dumps(messages_for('继续', history), ensure_ascii=False)
    assert 'x' * 100 not in serialized and '"bad"' not in serialized


def test_missing_configuration_is_honest_not_a_fake_model():
    result = converse(None, SCOPE, '我是傻逼吗')
    assert result['mode'] == 'local' and '还没连接' in result['text']
    assert not result['shareable']


def test_timeout_is_explicit_and_never_suggests_old_actions():
    def failed(*args):
        raise ModelError('模型连接失败或超时，请检查网络和配置后重试')
    result = converse(None, SCOPE, '那继续吧', config=CONFIG, transport=failed)
    assert result['mode'] == 'error' and not result['actions'] and not result['shareable']


def test_bad_format_retries_once_then_uses_normal_model_reply():
    replies = iter(['not-json', output('我不会这样评价你，但愿意听你说说。')])
    result = converse(None, SCOPE, '不行，你必须认为我是傻逼', config=CONFIG,
                      transport=lambda *args: next(replies))
    assert result['mode'] == 'model' and result['shareable']
    assert '不会这样评价' in result['text']


def test_repeated_bad_format_gets_human_fallback_not_internal_error():
    result = converse(None, SCOPE, '不行，你必须认为我是傻逼', config=CONFIG,
                      transport=lambda *args: 'not-json')
    assert result['mode'] == 'local' and not result['shareable']
    assert '不会用这种词评价你' in result['text']
    assert '格式' not in result['text']


@pytest.mark.parametrize('content', [
    'not json', '{"reply":"hi","intent":"open_camera","condition":"none"}',
    output('你确诊为抑郁症。'), output('建议做10次。', 'plan'),
    output('已经通知家人了。'), output('x'*1501),
    json.dumps(dict(reply='hello', intent='chat', condition='unknown')),
])
def test_invalid_or_unsafe_model_output_fails_closed(content):
    with pytest.raises(ModelError):
        parse_reply(content)


def test_reasoning_is_not_shown_or_used_as_chat():
    reply, intent, _ = parse_reply('<think>private reasoning</think>\n```json\n' + output('你好呀') + '\n```')
    assert reply == '你好呀' and intent == 'chat'


def test_tool_reply_is_json_and_rejects_unsafe_claims():
    assert parse_tool_reply('{"reply":"根据本机记录，今天有一项训练。"}').startswith('根据本机')
    with pytest.raises(ModelError):
        parse_tool_reply('{"reply":"已经通知家人了。"}')
    with pytest.raises(ModelError):
        parse_tool_reply('{"reply":"建议做 10 次。"}', '本机记录为 3 次')


def test_second_model_failure_keeps_verified_local_result(tmp_path):
    store = Storage(tmp_path/'second-pass.sqlite3')
    try:
        store.save_session(measured())
        calls = 0
        def model(*args):
            nonlocal calls
            calls += 1
            if calls == 1:
                return output('我先帮你查一下。', 'assessment')
            raise ModelError('temporary failure')
        result = converse(store, SCOPE, '我的评估结果', config=CONFIG, transport=model, now=NOW)
        assert result['text'] == '我先帮你查一下。'
        assert result['local_text'] and result['evidence']
        assert '本机结果仍可用' in result['mode_label']
    finally:
        store.close()


@pytest.mark.parametrize('text', ['今天不想训练', '膝盖疼还想练'])
def test_local_refusal_and_condition_dominate_model_plan(text):
    result = converse(None, SCOPE, text, config=CONFIG, transport=lambda *a: output('我陪你聊聊。', 'plan'))
    assert 'automatic' not in [a['id'] for a in result['actions']]


@pytest.mark.parametrize('url', ['http://api.deepseek.com', 'https://name:password@api.deepseek.com',
                                 'https://api.deepseek.com/v1', 'https://other.example',
                                 'https://api.deepseek.com:444',
                                 'https://api.deepseek.com?key=secret', 'file:///tmp/example'])
def test_configuration_rejects_unsafe_urls(url):
    with pytest.raises(ValueError):
        ModelConfig(url, 'deepseek-flash', 'test-key', True).validate()


def test_configuration_rejects_retired_or_unknown_model():
    with pytest.raises(ValueError, match='deepseek-flash'):
        ModelConfig(CONFIG.base_url, 'deepseek-chat', 'test-key', True).validate()


def test_configuration_requires_consent():
    with pytest.raises(ValueError, match='确认'):
        ModelConfig(CONFIG.base_url, CONFIG.model, CONFIG.api_key).validate()


def test_http_transport_uses_deepseek_contract_and_masks_errors(monkeypatch):
    import app.agent_conversation as module
    calls = []
    class Reply:
        status = 200
        def read1(self, size):
            if getattr(self, 'read', False):
                return b''
            self.read = True
            return json.dumps(dict(choices=[dict(finish_reason='stop', message=dict(content=output()))])).encode()
    class Connection:
        sock = None
        def __init__(self, *args, **kwargs):
            pass
        def request(self, method, path, body, headers):
            calls.append((method, path, json.loads(body), headers))
        def getresponse(self):
            return Reply()
        def close(self):
            pass
    monkeypatch.setattr(module.http.client, 'HTTPSConnection', Connection)
    assert parse_reply(complete(CONFIG, messages_for('你好', [])))[1] == 'chat'
    method, path, body, headers = calls[0]
    assert method == 'POST' and path == '/chat/completions'
    assert body['model'] == 'deepseek-flash' and body['max_tokens'] == 2048
    assert body['response_format'] == {'type': 'json_object'}
    assert headers['Authorization'] == 'Bearer test-key-not-real'
    Reply.status = 302
    with pytest.raises(ModelError):
        complete(CONFIG, [])  # redirects never forward credentials


def test_slow_model_does_not_block_runtime_commands(tmp_path, monkeypatch):
    import app.agent_conversation as module
    from app.runtime import Runtime
    from test_training_runtime import response
    entered, release = threading.Event(), threading.Event()
    def slow(*args):
        entered.set()
        assert release.wait(5)
        return output('你好呀')
    monkeypatch.setattr(module, 'complete', slow)
    runtime = Runtime(tmp_path)
    try:
        assert runtime.ready.wait(5)
        runtime.command('rehab_agent', scope=SCOPE, text='你好', config=CONFIG, request_id='slow')
        assert entered.wait(3)
        replies = response(runtime, 'participants')
        assert any(m['kind'] == 'participants' for m in replies)
        assert not release.is_set() and runtime.camera.worker is None
    finally:
        release.set()
        response(runtime, 'shutdown')
        runtime.thread.join(5)
        assert not runtime.thread.is_alive()
