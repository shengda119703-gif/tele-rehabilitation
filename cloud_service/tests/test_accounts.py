from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, select

from cloud_service.app import BASE, create_app
from cloud_service.config import Settings
from cloud_service.database import Database, accounts, audit, patients, records
from cloud_service.security import DomainError, bootstrap_doctor

ORIGIN = "http://testserver"


@pytest.fixture
def setup(tmp_path):
    settings = Settings("sqlite:///" + str(tmp_path / "cloud.sqlite3"), "x" * 40, (ORIGIN,), "test")
    db = Database(settings.database_url)
    db.migrate()
    bootstrap_doctor(db, settings, "1")
    app = create_app(settings, db)
    yield app, db, settings
    db.engine.dispose()


def client(app):
    return TestClient(app, headers={"Origin": ORIGIN})


def register(c, name="alice", pw="1", **extra):
    return c.post(BASE + "/auth/register", json={"username": name, "password": pw, **extra})


def login(c, name="alice", pw="1", kind="WEB"):
    r = c.post(BASE + "/auth/password/login", json={"username": name, "password": pw, "client_kind": kind})
    if r.is_success and kind == "WEB":
        c.headers["X-CSRF-Token"] = r.json()["csrf_token"]
    return r


def test_simple_password_and_private_blank_profile(setup):
    app, db, _ = setup
    c = client(app)
    r = register(c)
    assert r.status_code == 201
    assert login(c).status_code == 200
    assert c.get(BASE + "/auth/me").json()["role"] == "PATIENT"
    profile = c.get(BASE + "/patients/" + r.json()["patient_id"]).json()
    assert not profile["doctor_access"]
    with db.engine.connect() as conn:
        hashes = conn.execute(select(accounts.c.password_hash)).scalars().all()
        assert all(x.startswith("$argon2id$") and x != "1" for x in hashes)


@pytest.mark.parametrize("pw", ["123", "abc", "口令", " ", "1" * 128])
def test_no_complexity_rules(setup, pw):
    c = client(setup[0])
    assert register(c, pw=pw).status_code == 201
    assert login(c, pw=pw).status_code == 200


@pytest.mark.parametrize("extra", [{"role": "DOCTOR_ADMIN"}, {"account_id": "someone"}, {"team_id": "staff"}])
def test_registration_cannot_escalate(setup, extra):
    c = client(setup[0])
    assert register(c, **extra).status_code == 422
    assert register(c, "doctor").status_code == 409


def test_empty_password_and_error_redaction(setup):
    c = client(setup[0])
    for pw in ["", "SECRET" * 100]:
        r = register(c, pw=pw)
        assert r.status_code == 422
        assert pw == "" or pw not in r.text
    r = register(c, role="DOCTOR_ADMIN", password_note="SENSITIVE")
    assert "SENSITIVE" not in r.text


def test_same_username_no_replacement(setup):
    c = client(setup[0])
    assert register(c, "Alice").status_code == 201
    assert register(c, "alice", "2").status_code == 409
    assert login(c, "ALICE").status_code == 200
    assert login(c, "alice", "2").status_code == 401


def test_patient_isolation_and_list_authorization(setup):
    a, b, doctor = [client(setup[0]) for _ in range(3)]
    aid = register(a, "alice").json()["patient_id"]
    bid = register(b, "bob").json()["patient_id"]
    login(a); login(b, "bob"); login(doctor, "doctor")
    assert a.get(BASE + "/patients/" + bid).status_code == 404
    assert b.get(BASE + "/patients/" + aid).status_code == 404
    assert a.get(BASE + "/care/patients").status_code == 403
    assert doctor.get(BASE + "/care/patients").json()["total"] == 0
    assert doctor.get(BASE + "/patients/" + aid).status_code == 404
    assert a.put(BASE + "/patients/" + aid + "/doctor-access", json={"enabled": True, "expected_version": 0}).status_code == 200
    assert doctor.get(BASE + "/care/patients").json()["total"] == 1
    assert doctor.get(BASE + "/patients/" + aid).status_code == 200
    assert doctor.get(BASE + "/patients/" + bid).status_code == 404
    assert doctor.put(BASE + "/patients/" + bid + "/doctor-access", json={"enabled": True, "expected_version": 0}).status_code == 404
    assert a.put(BASE + "/patients/" + aid + "/doctor-access", json={"enabled": False, "expected_version": 0}).status_code == 412
    assert a.put(BASE + "/patients/" + aid + "/doctor-access", json={"enabled": False, "expected_version": 1}).status_code == 200
    assert doctor.get(BASE + "/patients/" + aid).status_code == 404
    assert doctor.get(BASE + "/care/patients").json()["total"] == 0


def test_csrf_and_external_origin(setup):
    c = client(setup[0]); pid = register(c).json()["patient_id"]; login(c)
    c.headers.pop("X-CSRF-Token")
    assert c.post(BASE + "/auth/logout", json={}).status_code == 403
    assert c.put(BASE + "/patients/" + pid + "/doctor-access", json={"enabled": True, "expected_version": 0}).status_code == 403
    c.headers["Origin"] = "https://attacker.invalid"
    assert login(c).status_code == 403
    c.headers["Origin"] = ORIGIN
    c.headers["X-CSRF-Token"] = c.get(BASE + "/auth/me").json()["csrf_token"]
    assert c.post(BASE + "/auth/logout", json={}).status_code == 200
    assert c.get(BASE + "/auth/me").status_code == 401


def test_login_generic_and_throttle_shared_across_apps(setup):
    app, db, settings = setup
    a = client(app); b = client(create_app(settings, db)); register(a)
    messages = set()
    for i in range(20):
        c = a if i % 2 else b
        r = login(c, "missing" if i % 2 else "alice", "wrong")
        assert r.status_code == 401
        messages.add(r.json()["message"])
    assert len(messages) == 1
    assert login(b).status_code == 429


def test_native_refresh_rotation_and_device_revoke(setup):
    c = client(setup[0]); register(c)
    signed = login(c, kind="APK").json()
    native = TestClient(setup[0], headers={"X-Ankang-Client": "native", "Authorization": "Bearer " + signed["access_token"]})
    assert native.get(BASE + "/auth/me").status_code == 200
    replacement = native.post(BASE + "/auth/refresh", json={"refresh_token": signed["refresh_token"]})
    assert replacement.status_code == 200
    assert native.get(BASE + "/auth/me").status_code == 401
    assert native.post(BASE + "/auth/refresh", json={"refresh_token": signed["refresh_token"]}).status_code == 401
    native.headers["Authorization"] = "Bearer " + replacement.json()["access_token"]
    device = native.get(BASE + "/auth/devices").json()["current_session_id"]
    assert native.post(BASE + "/auth/devices/" + device + "/revoke", json={}).status_code == 200
    assert native.get(BASE + "/auth/me").status_code == 401
    assert native.post(BASE + "/auth/refresh", json={"refresh_token": replacement.json()["refresh_token"]}).status_code == 401


def test_password_change_revokes_all_sessions(setup):
    a, b = client(setup[0]), client(setup[0]); register(a); login(a); login(b)
    assert a.post(BASE + "/auth/password/change", json={"current_password": "1", "new_password": "2"}).status_code == 200
    assert a.get(BASE + "/auth/me").status_code == 401
    assert b.get(BASE + "/auth/me").status_code == 401
    assert login(a).status_code == 401
    assert login(a, pw="2").status_code == 200


def test_records_idempotency_and_untrusted_source(setup):
    c = client(setup[0]); pid = register(c).json()["patient_id"]; login(c)
    path = BASE + "/patients/" + pid + "/record-events"
    payload = {"operation_id": str(uuid4()), "source_event_id": "actual-source-1", "installation_id": "test-instance",
               "source_kind": "SELF_REPORT", "payload": {"title": "本人记录", "text": "今天已练习"}}
    first = c.post(path, json=payload)
    assert first.status_code == 201, first.text
    repeat = c.post(path, json=payload)
    assert repeat.json()["resource_id"] == first.json()["resource_id"]
    assert repeat.json()["idempotent"]
    assert c.post(path, json={**payload, "payload": {"text": "changed"}}).status_code == 409
    assert c.post(path, json={**payload, "operation_id": str(uuid4())}).status_code == 409
    assert c.post(path, json={**payload, "source_kind": "CLINICIAN"}).status_code == 422
    with setup[1].engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(records)) == 1
        assert conn.scalar(select(func.count()).select_from(audit).where(audit.c.action == "patient_record.append")) == 1


def test_shared_admin_not_overwritten_and_singleton(setup):
    with pytest.raises(DomainError) as result:
        bootstrap_doctor(setup[1], setup[2], "2")
    assert result.value.code == "ALREADY_INITIALIZED"
    c = client(setup[0]); assert login(c, "doctor").status_code == 200


def test_bounded_body_and_static_file_allowlist(setup):
    c = client(setup[0])
    r = c.post(BASE + "/auth/register", content='{"password":"' + "x" * 270000 + '"}', headers={"Content-Type": "application/json"})
    assert r.status_code == 413
    assert c.get("/static/unified.css?name=../../AGENTS.md").text.startswith(":root")
    for path in ["/static/../../AGENTS.md", "/static/model.pt", "/api/rehab/v2/sessions", "/api/live"]:
        assert c.get(path).status_code == 404


def test_models_and_external_ports_are_absent(setup):
    c = client(setup[0]); cap = c.get(BASE + "/capabilities").json()
    assert not cap["server_models"] and all(not p["available"] for p in cap["providers"].values())
    assert not any(m.split('.')[0] in {"ultralytics", "torch", "mediapipe", "whisper", "mobile_rehab", "bridges"} for m in sys.modules)
    assert c.get("/health/ready").status_code == 200
    assert "/auth/register" in str(c.get(BASE + "/openapi.json").json())


def test_production_requires_https_postgres_and_secret():
    for url, key, origins in [("sqlite:///x.db", "x" * 40, ("https://cloud.invalid",)),
                              ("postgresql+psycopg://x", "short", ("https://cloud.invalid",)),
                              ("postgresql+psycopg://x", "x" * 40, ("http://cloud.invalid",))]:
        with pytest.raises(ValueError): Settings(url, key, origins)
