"""Synthetic protocol checks; no live model or patient records."""
import json
from uuid import uuid4

from cloud_service.ai_usage import AIConfig, provider
from cloud_service.tests.test_beta import answer, configured
from cloud_service.tests.test_workbench import setup, people, path


def test_understanding_purpose_is_bound_to_idempotency_and_identity(setup):
    calls = []
    def dispatch(*args):
        calls.append(args)
        return answer()
    app = configured(setup, dispatch)
    aid, _, alice, bob, _ = people((app, *setup[1:]))
    body = {"operation_id": str(uuid4()), "text": "TEST JSON schema", "purpose": "understanding"}
    first = alice.post(path(aid, "/ai/requests"), json=body)
    assert first.is_success and first.json()['state'] == 'SUCCEEDED'
    assert calls[0][2] == 'understanding'
    assert alice.post(path(aid, "/ai/requests"), json=body).json() == first.json()
    assert len(calls) == 1
    assert alice.post(path(aid, "/ai/requests"), json={**body, 'purpose': 'reply'}).status_code == 409
    assert alice.post(path(aid, "/ai/requests"), json={**body, 'purpose': 'execute'}).status_code == 422
    assert alice.post(path(aid, "/ai/requests"), json={**body, 'system': 'FORGED'}).status_code == 422
    assert bob.post(path(aid, "/ai/requests"), json=body).status_code == 404
    assert len(calls) == 1


def test_provider_uses_json_system_for_understanding_only(monkeypatch):
    sent = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self, _): return json.dumps(answer()).encode()
    class Opener:
        def open(self, request, timeout):
            sent.append(json.loads(request.data))
            return Response()
    monkeypatch.setattr('cloud_service.ai_usage.build_opener', lambda *_: Opener())
    config = AIConfig(key='TEST_ONLY')
    provider(config, 'TEST schema', 'understanding')
    assert sent[0]['response_format'] == {'type': 'json_object'}
    assert '语言理解解析器' in sent[0]['messages'][0]['content']
    provider(config, 'TEST ordinary')
    assert 'response_format' not in sent[1]
    # Preserve the deployed concise dialogue policy, not the branch's older prose.
    assert '康复管家' in sent[1]['messages'][0]['content']
    assert '不要诊断' in sent[1]['messages'][0]['content']


def test_explicit_reply_and_legacy_chat_share_one_metered_operation(setup):
    calls = []
    app = configured(setup, lambda *args: (calls.append(args), answer())[1])
    aid, _, alice, _, _ = people((app, *setup[1:]))
    body = {'operation_id': str(uuid4()), 'text': 'TEST legacy retry'}
    first = alice.post(path(aid, '/ai/requests'), json=body)
    assert first.is_success
    assert alice.post(path(aid, '/ai/requests'), json={**body, 'purpose': 'reply'}).json() == first.json()
    assert len(calls) == 1 and len(calls[0]) == 2


def test_understanding_incomplete_answer_keeps_authoritative_usage(setup):
    raw = answer()
    raw['choices'][0]['finish_reason'] = 'length'
    app = configured(setup, lambda *args: raw)
    aid, _, alice, _, _ = people((app, *setup[1:]))
    result = alice.post(path(aid, '/ai/requests'), json={
        'operation_id': str(uuid4()), 'text': 'TEST truncated JSON', 'purpose': 'understanding'})
    assert result.is_success
    # Existing metering marks an incomplete provider response UNKNOWN, not free.
    assert result.json()['state'] == 'UNKNOWN'
    assert result.json()['usage'] == raw['usage']
