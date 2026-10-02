"""Synthetic DB only. The local model is a protocol fixture, not an LLM quality evaluation."""
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.demo_training_plan import install_demo_plan, DEMO_SCOPE
from app.rehab_read_tools import RehabReadTools, TOOLS
from app.storage import Storage


@pytest.fixture
def rehab_db(tmp_path):
    path = tmp_path / 'synthetic.sqlite3'
    store = Storage(path)
    try:
        demo = install_demo_plan(store)
        entry = demo['plan']['items'][0]
        store.save_session(dict(DEMO_SCOPE, id='synthetic-training', scene_id='rehab', submode='training',
            exercise_id=entry['exercise_id'], side=entry['side'], status='FINISHED',
            start_utc='2026-10-01T08:00:00+00:00', end_utc='2026-10-01T08:10:00+00:00',
            measurement_mode='auto_observed', summary={'completed': 3, 'plan_completed': True},
            saved_plan_reference=dict(id=demo['plan']['id'], revision=demo['plan']['revision'], entry_key=entry['key']),
            repetitions=[], config_snapshot={}))
        store.save_training_feedback('synthetic-training',
                                    {'pain': 0, 'fatigue': 2, 'notes': '合成反馈', 'reason': 'not_recorded'}, expected_revision=0)
    finally:
        store.close()
    return path


def test_three_real_readers_and_no_database_changes(rehab_db):
    before = hashlib.sha256(rehab_db.read_bytes()).hexdigest()
    tools = RehabReadTools(rehab_db, DEMO_SCOPE)
    plan, assessment, history = [tools(name, {}) for name in TOOLS]
    assert plan['records'][0]['progress']['completed'] == 1
    assert plan['records'][0]['has_next']
    assert len(assessment['records']) == 4
    assert all(r['conditions']['measurement_contract'] for r in assessment['records'])
    assert not assessment['comparison_performed']
    shoulder = tools(TOOLS[1], {'joint': 'shoulder'})
    assert len(shoulder['records']) == 2
    assert history['records'][0]['summary']['completed'] == 3
    assert history['records'][0]['training_feedback']['notes'] == '合成反馈'
    assert hashlib.sha256(rehab_db.read_bytes()).hexdigest() == before


def test_scope_empty_and_no_model_owner_override(rehab_db, tmp_path):
    for change in ({'participant_id': 'another'}, {'source_kind': 'LIVE_CAMERA'}, {'usage_context': 'SELF_USE'}):
        tools = RehabReadTools(rehab_db, {**DEMO_SCOPE, **change})
        assert all(tools(name, {})['status'] == 'empty' for name in TOOLS)
    tools = RehabReadTools(rehab_db, DEMO_SCOPE)
    with pytest.raises(ValueError):
        tools(TOOLS[0], {'participant_id': 'another'})
    with pytest.raises(ValueError):
        tools('rehab.start_training', {})
    absent = tmp_path / 'not-created.sqlite3'
    assert RehabReadTools(absent, DEMO_SCOPE)(TOOLS[0], {})['status'] == 'empty'
    assert not absent.exists()


def test_expired_plan_is_not_recommended_as_available(rehab_db):
    from datetime import datetime, timezone
    store = Storage(rehab_db)
    try:
        install_demo_plan(store, now=datetime(2020, 1, 1, tzinfo=timezone.utc))
    finally:
        store.close()
    plan = RehabReadTools(rehab_db, DEMO_SCOPE)(TOOLS[0], {})['records'][0]
    assert not plan['next_available'] and '过期' in plan['availability_reason']


def test_real_bridge_three_questions_and_scope_isolation(rehab_db, monkeypatch, capsys, tmp_path):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from bridges.ankang.client import AgentBridge
    questions = ['我今天练什么？', '我最近肩膀怎么样？', '我上次训练完成得怎么样？']
    requests = []

    class ModelFixture(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            assert payload['model'] == 'deepseek-flash'
            data = json.loads(payload['messages'][-1]['content'])
            requests.append(data)
            if 'result' not in data:
                name = TOOLS[questions.index(data['text'])] if data['text'] in questions else None
                answer = json.dumps({'name': name, 'arguments': {'joint': 'shoulder'} if name == TOOLS[1] else {}})
            else:
                result = data['result']
                assert result['scope'] == DEMO_SCOPE
                row = result['records'][0]
                if result['tool'] == TOOLS[0]:
                    answer = '合成测试计划：' + row['name'] + '；下一项：' + str(row['progress']['next_key'])
                elif result['tool'] == TOOLS[1]:
                    answer = '合成测试评估：' + '、'.join(r['exercise_label'] for r in result['records']) + '；未作临床改善判断。'
                else:
                    answer = f"合成测试训练：{row['exercise_label']}；完成 {row['summary']['completed']} 次；反馈：{row['training_feedback']['notes']}"
            body = json.dumps({'choices': [{'message': {'content': answer}}]}, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(('127.0.0.1', 0), ModelFixture)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    # The production URL/model stay fixed. Only this child-process fetch transport is intercepted.
    hook = tmp_path/'model-fixture.cjs'
    hook.write_text('const realFetch = globalThis.fetch;\n'
        'globalThis.fetch = (url, init) => {\n'
        'if (String(url) !== "https://api.deepseek.com/chat/completions") throw new Error("Unexpected model URL");\n'
        f'return realFetch("http://127.0.0.1:{server.server_port}/chat/completions", init);\n'
        '};\n', encoding='utf-8')
    monkeypatch.setenv('NODE_OPTIONS', '--require '+json.dumps(str(hook)))
    monkeypatch.setenv('APPDATA', str(tmp_path/'private-config'))
    monkeypatch.setenv('ANKANG_REHAB_LLM_API_KEY', 'TEST-protocol-fixture')
    scope = dict(DEMO_SCOPE)
    profile = dict(name='用户', age=0, conditions=[], medications=[], familyContact='', familyPhone='',
                   mobility='unknown', usesCane=False, nightVision='unknown', cognition='unknown', familySharing='denied')
    bridge = AgentBridge()
    before = hashlib.sha256(rehab_db.read_bytes()).hexdigest()
    try:
        assert bridge.open_session('test-original', profile, rehab_tools=True)['rehabToolsAvailable']
        for index, question in enumerate(questions):
            result = bridge.process_turn('test-original', question, tool_handler=RehabReadTools(rehab_db, scope))
            assert result['rehab']['data']['status'] == 'found'
            assert result['rehab']['call']['name'] == TOOLS[index]
            assert result['revision'] == index + 1
            assert result['snapshot']['events'] == []
            with capsys.disabled():
                print('\nPython bridge ->', question, '\nAgent ->', result['reply']['text'])
        # Different scopes bind separate sessions/read capabilities; formal ProductWindow UI is tested separately.
        scope['source_kind'] = 'LIVE_CAMERA'
        bridge.open_session('test-source', profile, rehab_tools=True)
        result = bridge.process_turn('test-source', questions[0], tool_handler=RehabReadTools(rehab_db, scope))
        assert result['revision'] == 1
        assert '没有找到' in result['reply']['text']
        scope.update(DEMO_SCOPE, participant_id='synthetic-other')
        bridge.open_session('test-other', profile, rehab_tools=True)
        result = bridge.process_turn('test-other', questions[0], tool_handler=RehabReadTools(rehab_db, scope))
        assert result['revision'] == 1
        assert '没有找到' in result['reply']['text']
        result = bridge.process_turn('test-other', '你好', tool_handler=RehabReadTools(rehab_db, scope))
        assert result['revision'] == 2 and 'rehab' not in result
        assert hashlib.sha256(rehab_db.read_bytes()).hexdigest() == before
    finally:
        bridge.close()
        server.shutdown()
        server.server_close()
        thread.join(2)
    assert bridge._process.poll() is not None
