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
    assert '需要个体判断时建议联系康复医师' in sent[1]['messages'][0]['content']
