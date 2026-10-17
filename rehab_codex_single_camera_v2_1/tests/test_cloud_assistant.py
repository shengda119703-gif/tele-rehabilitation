"""Isolated client/worker contracts; fictitious accounts, no provider or network."""
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.cloud_account import CloudAccount, CloudError, ORIGIN, transport
from app.product.backend import ProductBackend
from test_cloud_account import MemoryVault
from test_product_window import desktop


@pytest.fixture
def assistant(tmp_path):
    vault = MemoryVault()
    vault.write(dict(origin=ORIGIN, role='PATIENT', account_id=str(uuid4()), patient_id=str(uuid4()),
                     username='TEST client', access_token='TEST access', refresh_token='TEST refresh'))
    cloud = SimpleNamespace(calls=[], turns=[], assessment_plans=[], preferences={'version': 0, 'health_context': False}, failure=None)

    def request(path, method='GET', body=None, token=None):
        if path == '/auth/me':
            return {key: vault.value[key] for key in ('role', 'account_id', 'patient_id')}
        cloud.calls.append((path, method, deepcopy(body)))
        assert path.startswith('/patients/' + vault.value['patient_id'] + '/')
        if cloud.failure:
            raise cloud.failure
        if path.endswith('/assistant/assessment-plans'):
            assert method == 'GET' and body is None
            return {'items': deepcopy(cloud.assessment_plans)}
        if '/assistant/assessment-plans/' in path and path.endswith('/cancel'):
            assert method == 'POST' and body == {}
            return {'status': 'CANCELLED'}
        if path.endswith('/assistant/preferences'):
            if method == 'PUT':
                assert body['expected_version'] == cloud.preferences['version']
                cloud.preferences = {'version': body['expected_version'] + 1, 'health_context': body['health_context']}
            return deepcopy(cloud.preferences)
        if '/assistant/conversation?' in path:
            from urllib.parse import parse_qs, urlsplit
            after = int(parse_qs(urlsplit(path).query)['after'][0])
            rows = [row for row in cloud.turns if row['sequence'] > after]
            return {'items': deepcopy(rows[:30]), 'has_more': len(rows) > 30,
                    'next_after': rows[min(29, len(rows) - 1)]['sequence'] if rows else after}
        if path.endswith('/assistant/turns'):
            turn = next((row for row in cloud.turns if row['operation_id'] == body['operation_id']), None)
            if not turn:
                turn = dict(id=str(uuid4()), operation_id=body['operation_id'], sequence=len(cloud.turns) + 1,
                    text=body['text'], answer='TEST server answer', source='local', actions=[], created_at=1)
                cloud.turns.append(turn)
            return {'turn': deepcopy(turn), 'source': 'local', 'summary': {}, 'health_context_enabled': cloud.preferences['health_context']}
        if path.endswith('/rehab-workflow'):
            return {'profile_version': 0, 'profile': None}
        if path.endswith('/rehab-workflow/profile'):
            return {'profile_version': 1, 'profile': body}
        if path.endswith('/rehab-candidates'):
            return {'state': 'PENDING_REVIEW'}
        raise AssertionError('Unexpected isolated RPC: ' + path)

    client = CloudAccount(tmp_path / 'cloud-account', request, vault)
    return client, cloud, vault


def pending(client):
    with client.db() as db:
        return [dict(row) for row in db.execute('SELECT * FROM assistant_pending')]


def test_unbound_assistant_preferences_and_original_question_do_not_upload_records(assistant):
    client, cloud, _ = assistant
    assert client.assistant_preferences() == {'version': 0, 'health_context': False}
    assert client.assistant_preferences({'expected_version': 0, 'health_context': True})['health_context'] is True
    client.assistant_turn('查看我已有的肩部康复记录')
    assert cloud.calls[-1][2]['text'] == '查看我已有的肩部康复记录'
    assert set(cloud.calls[-1][2]) == {'text', 'operation_id'}
    assert not any('/record-events' in path or '/doctor-access' in path for path, _, _ in cloud.calls)
    assert pending(client) == []


@pytest.mark.parametrize('text', ['不要记录我的训练结果', '别保存这次聊天', '不要告诉家人我的情况'])
def test_private_turn_never_calls_cloud_assistant(assistant, text):
    client, cloud, _ = assistant
    with pytest.raises(CloudError, match='仅在本机'):
        client.assistant_turn(text)
    assert cloud.calls == []


def test_pending_question_survives_lost_reply_reopen_and_conflicting_question(assistant):
    client, cloud, vault = assistant
    cloud.failure = CloudError('TEST lost response')
    with pytest.raises(CloudError):
        client.assistant_turn('TEST original')
    original = pending(client)[0]
    reopened = CloudAccount(client.directory, client.request, vault)
    with pytest.raises(CloudError, match='原管家提问'):
        reopened.assistant_turn('TEST different')
    cloud.failure = None
    reopened.assistant_turn()
    assert cloud.calls[-1][2] == {'operation_id': original['operation_id'], 'text': original['text']}
    assert pending(client) == []


@pytest.mark.parametrize('code', ['AI_BUSY', 'AI_NOT_CONFIGURED', 'AI_QUOTA_EXHAUSTED', 'AI_REJECTED'])
def test_no_dispatch_error_retires_only_own_assistant_operation(assistant, code):
    client, cloud, _ = assistant
    cloud.failure = CloudError('TEST no dispatch', 503, code)
    with pytest.raises(CloudError):
        client.assistant_turn('TEST original')
    assert pending(client) == []


def test_assistant_conversation_fetches_multiple_pages_and_next_device_sees_same_turns(assistant):
    client, cloud, vault = assistant
    for sequence in range(1, 76):
        cloud.turns.append(dict(id=str(uuid4()), sequence=sequence, text='TEST user', answer='TEST answer', actions=[], source='local', created_at=1))
    read = client.assistant_conversation()
    assert len(read['items']) == 75
    assert [item['sequence'] for item in read['items']] == list(range(1, 76))
    other = CloudAccount(client.directory.parent / 'TEST-second-device', client.request, vault)
    assert other.assistant_conversation()['items'] == read['items']
    assert len([path for path, _, _ in cloud.calls if '/assistant/conversation?' in path]) == 6


def test_assistant_transport_accepts_only_own_fixed_pagination_path(monkeypatch):
    import urllib.request
    seen = []

    class Reply:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, size): return b'{"items":[]}'

    class Opener:
        def open(self, request, timeout):
            seen.append((request.full_url, timeout))
            return Reply()

    monkeypatch.setattr(urllib.request, 'build_opener', lambda *args: Opener())
    patient = str(uuid4())
    transport('/patients/' + patient + '/assistant/conversation?after=30&limit=30')
    transport('/patients/' + patient + '/assistant/turns', 'POST', {'text': 'TEST'})
    assert seen[1][1] == 35
    with pytest.raises(CloudError):
        transport('/patients/' + patient + '/assistant/conversation?after=0&limit=30&patient=other')


class Bridge:
    def __init__(self):
        self.calls = []
        self.cloud_conversation = True
        self._process = SimpleNamespace(poll=lambda: None)

    def product(self, operation, owner, payload, **kwargs):
        self.calls.append((operation, deepcopy(payload)))
        snapshot = {'ownerId': owner, 'state': {'chat': []}, 'profile': {'ownerId': owner, 'profile': {}}}
        if operation == 'chat':
            snapshot['state']['chat'] = [{'id': 'TEST local private', 'role': 'elder', 'text': payload['text'], 'persisted': False}]
            return {'turn': {'reply': {'text': 'TEST local', 'persisted': False}}, 'snapshot': snapshot}
        return snapshot

    def close(self): pass
    def terminate(self): pass


def worker(assistant, monkeypatch):
    client, cloud, vault = assistant
    with client.db() as db:
        db.execute('INSERT INTO bindings VALUES (?,?)', ('TEST-owner', vault.value['patient_id']))
    monkeypatch.setattr('app.cloud_account.CloudAccount', lambda *args: client)
    bridge = Bridge()
    return ProductBackend(client.directory.parent, lambda: bridge), bridge


def test_product_worker_bypasses_local_chat_for_public_questions_and_deduplicates_history(assistant, monkeypatch):
    client, cloud, _ = assistant
    backend, bridge = worker(assistant, monkeypatch)
    try:
        result = backend.call('chat', 'TEST-owner', {'text': '查看我已有的肩部结果'})
        assert cloud.turns[0]['text'] == '查看我已有的肩部结果'
        assert not any(operation == 'chat' for operation, _ in bridge.calls)
        assert bridge.cloud_conversation is False
        assert result['turn']['reply']['text'] == 'TEST server answer'
        assert len(result['snapshot']['state']['chat']) == 2
        assert len(backend.call('snapshot', 'TEST-owner')['state']['chat']) == 2
        assert not client.consent('TEST-owner')
    finally:
        backend.close()


def test_semantic_opt_in_selects_the_bound_account_bridge_not_the_old_turn_endpoint(assistant, monkeypatch):
    monkeypatch.setenv('ANKANG_SEMANTIC_ROUTING_ENABLED', '1')
    _, cloud, _ = assistant
    backend, bridge = worker(assistant, monkeypatch)
    try:
        backend.call('chat', 'TEST-owner', {'text': 'TEST semantic request'})
        assert bridge.cloud_conversation is True
        assert any(operation == 'chat' for operation, _ in bridge.calls)
        assert not any(path.endswith('/assistant/turns') for path, _, _ in cloud.calls)
    finally:
        backend.close()


@pytest.mark.parametrize('payload', [{'text': 'TEST private', 'private': True}, {'text': '不要记录我的训练结果'}])
def test_semantic_opt_in_still_keeps_private_turns_local(assistant, monkeypatch, payload):
    monkeypatch.setenv('ANKANG_SEMANTIC_ROUTING_ENABLED', '1')
    _, cloud, _ = assistant
    backend, bridge = worker(assistant, monkeypatch)
    try:
        backend.call('chat', 'TEST-owner', payload)
        assert bridge.cloud_conversation is False
        assert not any(path.endswith(('/assistant/turns', '/ai/requests')) for path, _, _ in cloud.calls)
    finally:
        backend.close()


@pytest.mark.parametrize('payload', [{'text': 'TEST private', 'private': True}, {'text': '不要记录我的训练结果'}, {'text': '不要告诉家人我的训练'}])
def test_product_private_path_never_sends_text_to_assistant_server(assistant, monkeypatch, payload):
    _, cloud, _ = assistant
    backend, bridge = worker(assistant, monkeypatch)
    try:
        backend.call('chat', 'TEST-owner', payload)
        assert not any(path.endswith('/assistant/turns') for path, _, _ in cloud.calls)
        assert bridge.cloud_conversation is False
        assert bridge.calls[0][0] == 'chat'
    finally:
        backend.close()


def test_worker_wrappers_reuse_server_preferences_workflow_and_candidate_contract(assistant, monkeypatch):
    _, cloud, _ = assistant
    backend, _ = worker(assistant, monkeypatch)
    try:
        assert backend.call('workbench.assistantPreferences', 'TEST-owner')['health_context'] is False
        assert backend.call('workbench.assistantPreferences', 'TEST-owner', {'expected_version': 0, 'health_context': True})['health_context'] is True
        assert backend.call('workbench.workflow', 'TEST-owner')['profile_version'] == 0
        operation = str(uuid4())
        assert backend.call('workbench.candidate', 'TEST-owner', {'kind': 'STARTER', 'operation_id': operation})['state'] == 'PENDING_REVIEW'
        assert cloud.calls[-1][2]['operation_id'] == operation
    finally:
        backend.close()


def test_assessment_plan_worker_uses_bound_account_transport_without_node_or_record_writes(assistant, monkeypatch):
    client, cloud, vault = assistant
    backend, bridge = worker(assistant, monkeypatch)
    identity = {key: vault.value[key] for key in ('patient_id', 'account_id')}
    ident = str(uuid4())
    cloud.assessment_plans = [{'id': ident, 'status': 'PLANNED', 'items': []}]
    try:
        assert backend.call('workbench.assessmentPlans', 'TEST-owner', identity)['items'][0]['id'] == ident
        assert backend.call('workbench.assessmentPlanCancel', 'TEST-owner', dict(identity, plan_id=ident))['status'] == 'CANCELLED'
        assert cloud.calls[-1] == ('/patients/' + identity['patient_id'] + '/assistant/assessment-plans/' + ident + '/cancel', 'POST', {})
        assert bridge.calls == []
        for bad in ({}, dict(identity, account_id=str(uuid4())), dict(identity, patient_id=str(uuid4()))):
            with pytest.raises(RuntimeError, match='变化'):
                backend.call('workbench.assessmentPlans', 'TEST-owner', bad)
        with pytest.raises(RuntimeError, match='编号无效'):
            backend.call('workbench.assessmentPlanCancel', 'TEST-owner', dict(identity, plan_id='../other'))
        assert len(cloud.calls) == 2
    finally:
        backend.close()


def test_assessment_plan_client_rejects_binding_and_late_session_changes(assistant):
    client, cloud, vault = assistant
    identity = (vault.value['patient_id'], vault.value['account_id'])
    with pytest.raises(CloudError, match='变化'):
        client.assistant_assessment_plans('TEST-owner', *identity)
    assert cloud.calls == []
    client.bind('TEST-owner')
    original = client.request
    def changed(path, method='GET', body=None, token=None):
        result = original(path, method, body, token)
        if path.endswith('/assistant/assessment-plans'):
            vault.value['account_id'] = str(uuid4())
        return result
    client.request = changed
    with pytest.raises(CloudError, match='变化'):
        client.assistant_assessment_plans('TEST-owner', *identity)


def test_default_product_worker_disables_native_model_even_when_not_logged_in(tmp_path, monkeypatch):
    import bridges.ankang.client
    seen = []
    bridge = Bridge()

    def construct(**kwargs):
        seen.append(kwargs)
        return bridge

    monkeypatch.setattr(bridges.ankang.client, 'AgentBridge', construct)
    backend = ProductBackend(tmp_path)
    try:
        backend.call('chat', 'TEST-local', {'text': 'TEST ordinary anonymous question'})
        assert seen[0]['env']['ANKANG_PRODUCT_DISABLE_MODEL'] == '1'
        assert bridge.cloud_conversation is False
        assert bridge.calls[0][0] == 'chat'
    finally:
        backend.close()


def test_late_assistant_reply_after_account_change_cannot_clear_pending(assistant):
    client, cloud, vault = assistant
    request = client.request

    def changed(path, method='GET', body=None, token=None):
        result = request(path, method, body, token)
        if path.endswith('/assistant/turns'):
            vault.value['account_id'] = str(uuid4())
        return result

    client.request = changed
    with pytest.raises(CloudError, match='账号已变化'):
        client.assistant_turn('TEST original')
    assert pending(client)[0]['text'] == 'TEST original'


def test_worker_sync_does_not_skip_intervening_turns_from_another_device(assistant, monkeypatch):
    _, cloud, _ = assistant
    backend, _ = worker(assistant, monkeypatch)
    try:
        backend.call('chat', 'TEST-owner', {'text': 'TEST first'})
        cloud.turns.append(dict(id=str(uuid4()), operation_id=str(uuid4()), sequence=2, text='TEST second device', answer='TEST other answer', actions=[], source='local', created_at=2))
        result = backend.call('chat', 'TEST-owner', {'text': 'TEST third'})
        assert [row['text'] for row in result['snapshot']['state']['chat'] if row['role'] == 'elder'] == ['TEST first', 'TEST second device', 'TEST third']
    finally:
        backend.close()


def test_actual_pyside_bound_account_chat_uses_server_history_and_private_turn_stays_local(desktop, assistant, monkeypatch):
    from test_product_window import wait
    window, app = desktop
    client, cloud, vault = assistant
    with client.db() as db:
        db.execute('INSERT INTO bindings VALUES (?,?)', (window.owner, vault.value['patient_id']))
    monkeypatch.setattr('app.cloud_account.CloudAccount', lambda *args: client)
    window._request('snapshot')
    wait(app, lambda: not window.pending)
    assert window.snapshot['cloudAssistant']['patient_id'] == vault.value['patient_id']
    window.navigate('assistant')
    wait(app, lambda: not window.pending)
    window._send_chat('查看我已有的肩部结果')
    wait(app, lambda: not window.pending)
    assert cloud.turns[-1]['text'] == '查看我已有的肩部结果'
    assert 'TEST server answer' in window.chat.toPlainText()
    count = len(cloud.turns)
    window.private_turn.setChecked(True)
    window._send_chat('TEST 本次不记录的肩部问题')
    wait(app, lambda: not window.pending)
    assert len(cloud.turns) == count
    assert 'TEST 本次不记录的肩部问题' in window.chat.toPlainText()
    assert not any('/record-events' in path or '/doctor-access' in path for path, _, _ in cloud.calls)
