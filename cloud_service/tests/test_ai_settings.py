"""Isolated credential/gateway tests. All keys/providers here are fictional."""
import json
import os
from pathlib import Path

import pytest
from sqlalchemy import select

from cloud_service.app import BASE, create_app
from cloud_service.ai_settings import AISettings, SettingsInput
from cloud_service.ai_usage import AIConfig, provider
from cloud_service.database import audit
from cloud_service.security import DomainError
from cloud_service.tests.test_workbench import setup, people, path
from cloud_service.tests.test_accounts import client
from cloud_service.tests.test_beta import answer

SETTINGS = BASE + "/care/ai/settings"
CHECK = BASE + "/care/ai/check"
KEY = "sk-TEST-NOT-A-REAL-CREDENTIAL-123456"


def configured_app(setup, tmp_path, **extra):
    return create_app(setup[2], setup[1], ai_settings_path=tmp_path / "private" / "settings.json",
                      ai_dispatch=lambda *_: answer(), ai_probe=lambda *_: True, **extra)


def test_doctor_only_csrf_and_no_secret_in_schema(setup, tmp_path):
    app = configured_app(setup, tmp_path)
    _, _, alice, _, doctor = people((app, *setup[1:]))
    assert client(app).get(SETTINGS).status_code == 401
    assert alice.get(SETTINGS).status_code == 403
    assert alice.put(SETTINGS, json={"key": KEY}).status_code == 403
    assert alice.post(CHECK, json={}).status_code == 403
    assert doctor.put(SETTINGS, json={"key": KEY}, headers={"X-CSRF-Token": "wrong"}).status_code == 403
    assert KEY not in doctor.get(BASE + "/openapi.json").text


def test_atomic_save_reload_disable_and_audit_without_secret(setup, tmp_path):
    app = configured_app(setup, tmp_path)
    aid, _, alice, _, doctor = people((app, *setup[1:]))
    status = doctor.put(SETTINGS, json={"key": KEY, "model": "deepseek-flash"})
    assert status.is_success and status.json()["configured"]
    assert KEY not in status.text and "key" not in status.json()
    private = tmp_path / "private" / "settings.json"
    assert private.is_file() and not list(private.parent.glob(".settings-*"))
    if os.name == "posix":
        assert private.stat().st_mode & 0o777 == 0o600
        assert private.parent.stat().st_mode & 0o777 == 0o700
    assert doctor.get(BASE + "/capabilities").json()["text_ai_gateway"]["configured"]
    assert alice.get(path(aid, "/ai/usage")).json()["enabled"]
    # New application process picks up the credential without a redeployment.
    restarted = configured_app(setup, tmp_path)
    assert restarted.state.text_ai_settings.config().key == KEY
    assert doctor.put(SETTINGS, json={"model": "deepseek-v4-pro"}).json()["configured"]
    assert app.state.text_ai_settings.config().key == KEY
    assert doctor.put(SETTINGS, json={"key": ""}).json()["configured"] is False
    assert restarted.state.text_ai_settings.config().key == ""
    with setup[1].engine.connect() as connection:
        assert KEY not in str(list(connection.execute(select(audit)).mappings()))


def test_probe_only_checks_models_and_chat_marks_actual_success(setup, tmp_path):
    from uuid import uuid4
    app = configured_app(setup, tmp_path)
    aid, _, alice, _, doctor = people((app, *setup[1:]))
    assert doctor.post(CHECK, json={}).status_code == 503
    doctor.put(SETTINGS, json={"key": KEY})
    status = doctor.post(CHECK, json={}).json()
    assert status["provider_connection"] == "MODELS_VERIFIED" and status["last_checked_at"]
    assert alice.get(path(aid, "/ai/usage")).json()["usage"]["calls"] == 0
    assert alice.post(path(aid, "/ai/requests"), json={"operation_id": str(uuid4()), "text": "TEST 你好"}).json()["state"] == "SUCCEEDED"
    assert doctor.get(SETTINGS).json()["provider_connection"] == "CHAT_VERIFIED"
    doctor.put(SETTINGS, json={"model": "deepseek-v4-pro"})
    assert doctor.get(SETTINGS).json()["provider_connection"] == "NOT_VERIFIED"


def test_probe_failure_does_not_echo_exception(setup, tmp_path):
    def broken(*_):
        raise RuntimeError(KEY)
    app = create_app(setup[2], setup[1], ai_settings_path=tmp_path / "private" / "settings.json", ai_probe=broken)
    *_, doctor = people((app, *setup[1:]))
    doctor.put(SETTINGS, json={"key": KEY})
    response = doctor.post(CHECK, json={})
    assert response.json()["provider_connection"] == "FAILED" and KEY not in response.text


@pytest.mark.parametrize("body", [{"key": "short"}, {"key": KEY + "\n"}, {"key": "密钥" * 20}, {"model": "arbitrary-model"}, {"unexpected": KEY}])
def test_invalid_settings_are_redacted_and_original_retained(setup, tmp_path, body):
    app = configured_app(setup, tmp_path)
    *_, doctor = people((app, *setup[1:]))
    doctor.put(SETTINGS, json={"key": KEY})
    response = doctor.put(SETTINGS, json=body)
    assert response.status_code == 422 and KEY not in response.text
    assert app.state.text_ai_settings.config().key == KEY


def test_corrupt_settings_fail_closed_and_symlink_not_followed(tmp_path):
    file = tmp_path / "private.json"
    file.write_text("{broken", encoding="utf-8")
    file.chmod(0o600)
    with pytest.raises(DomainError):
        AISettings(AIConfig(key=KEY), file)
    if os.name == "posix":
        file.unlink()
        file.symlink_to(tmp_path / "missing.json")
        with pytest.raises(DomainError):
            AISettings(AIConfig(key=KEY), file)


def test_isolated_saved_key_cannot_dispatch_real_provider(setup, tmp_path, monkeypatch):
    from uuid import uuid4
    monkeypatch.setattr("cloud_service.ai_usage.provider", lambda *_: pytest.fail("Live provider called"))
    app = create_app(setup[2], setup[1], ai_settings_path=tmp_path / "private" / "settings.json")
    aid, _, alice, _, doctor = people((app, *setup[1:]))
    doctor.put(SETTINGS, json={"key": KEY})
    response = alice.post(path(aid, "/ai/requests"), json={"operation_id": str(uuid4()), "text": "TEST"})
    assert response.json()["state"] == "UNKNOWN"
    assert doctor.post(CHECK, json={}).json()["provider_connection"] == "FAILED"


def test_no_thinking_or_tools_or_records_in_provider_request(monkeypatch):
    observed = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self, _): return json.dumps(answer()).encode()
    class Opener:
        def open(self, request, **kwargs):
            observed.append(request)
            return Response()
    monkeypatch.setattr("cloud_service.ai_usage.build_opener", lambda *_: Opener())
    provider(AIConfig(key=KEY), "TEST 提交的文字")
    body = json.loads(observed[0].data)
    assert body["thinking"] == {"type": "disabled"}
    assert "tools" not in body and "records" not in body
    assert body["messages"][-1] == {"role": "user", "content": "TEST 提交的文字"}


def test_model_price_snapshot_is_durable_and_not_reused_for_another_model(setup, tmp_path):
    app = configured_app(setup, tmp_path)
    *_, doctor = people((app, *setup[1:]))
    tariff = {"version":"TEST-manual-price", "currency":"CNY", "cache_hit":"0.1", "cache_miss":"1", "output":"2"}
    assert doctor.put(SETTINGS,json={"key":KEY,"tariff":tariff}).json()['tariff'] == tariff
    assert configured_app(setup,tmp_path).state.text_ai_settings.config().tariff == tariff
    assert doctor.put(SETTINGS,json={"tariff":{**tariff,'output':'NaN'}}).status_code == 422
    assert doctor.get(SETTINGS).json()['tariff'] == tariff
    assert doctor.put(SETTINGS,json={"model":"deepseek-v4-pro"}).json()['tariff'] is None


def test_legacy_file_does_not_inherit_other_model_prices(tmp_path):
    tariff={"version":"TEST", "currency":"CNY", "cache_hit":"0.1", "cache_miss":"1", "output":"2"}
    path=tmp_path/'legacy.json';path.write_text(json.dumps({'version':1,'key':KEY,'model':'deepseek-v4-pro'}));path.chmod(0o600)
    assert AISettings(AIConfig(model='deepseek-flash',tariff=tariff),path).config().tariff is None
