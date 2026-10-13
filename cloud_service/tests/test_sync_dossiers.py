"""Isolated fixture acceptance. No production patient/doctor data is a fixture."""
from copy import deepcopy
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from cloud_service.app import BASE, create_app
from cloud_service.config import Settings
from cloud_service.database import Database
from cloud_service.security import bootstrap_doctor
from tools.cloud.seed_sync_dossiers import CASES, NAMES, document, fingerprint


@pytest.fixture
def app(tmp_path):
    db = Database("sqlite:///"+str(tmp_path/"qa.sqlite3"))
    db.migrate()
    settings = Settings(str(db.engine.url), "isolated-acceptance-secret-"*3, ("http://testserver",), "test")
    bootstrap_doctor(db, settings, "1")
    yield create_app(settings, db)
    db.engine.dispose()


def web(app, name, create=True):
    c = TestClient(app, headers={"Origin": "http://testserver"})
    if create:
        assert c.post(BASE+"/auth/register", json={"username": name, "password": "1"}).status_code == 201
    signed = c.post(BASE+"/auth/password/login", json={"username": name, "password": "1"}).json()
    c.headers["X-CSRF-Token"] = signed["csrf_token"]
    return c, signed


def test_five_dossiers_preserve_originals_and_match_all_client_kinds(app):
    patients = []
    for name in NAMES:
        c, identity = web(app, name)
        ident = identity["patient_id"]
        original = {"operation_id": str(uuid4()), "source_event_id": "actual-zero-result",
            "installation_id": "original", "source_kind": "WEB_LOCAL",
            "payload": {"schema": "ankang-result-1", "result": {"summary": {"completed": 0, "angle": None}}}}
        assert c.post(BASE+f"/patients/{ident}/record-events", json=original).status_code == 201
        before = c.get(BASE+f"/patients/{ident}/records").json()["items"]
        packet = document(name, ident)
        stored = c.post(BASE+f"/patients/{ident}/record-events", json=packet)
        assert stored.status_code == 201 and not stored.json()["idempotent"]
        again = c.post(BASE+f"/patients/{ident}/record-events", json=packet)
        assert again.status_code == 201 and again.json()["idempotent"]
        assert again.json()["resource_id"] == stored.json()["resource_id"]
        events = c.get(BASE+f"/patients/{ident}/records").json()["items"]
        assert len(events) == 2
        assert before[0] in events
        accepted = next(r for r in events if r["id"] == stored.json()["resource_id"])
        assert accepted["payload"] == packet["payload"]
        assert accepted["attribution_state"] == "DECLARED" and accepted["source_kind"] == "IMPORT"
        assert len(accepted["payload"]["sections"]) == 11
        assert c.put(BASE+f"/patients/{ident}/doctor-access", json={"enabled": True, "expected_version": 0}).status_code == 200
        for kind in ("APK", "DESKTOP"):
            n = TestClient(app, headers={"X-Ankang-Client": "native"})
            signed = n.post(BASE+"/auth/password/login", json={"username": name, "password": "1", "client_kind": kind}).json()
            n.headers["Authorization"] = "Bearer "+signed["access_token"]
            read = n.get(BASE+f"/patients/{ident}/records").json()["items"]
            assert read == events
            assert n.post(BASE+"/auth/logout", json={}).status_code == 200
        patients.append((c, ident, events))
    doctor, _ = web(app, "doctor", False)
    assert doctor.get(BASE+"/care/patients").json()["total"] == 5
    for c, ident, events in patients:
        assert doctor.get(BASE+f"/patients/{ident}/records").json()["items"] == events
        assert c.get(BASE+f"/patients/{next(p[1] for p in patients if p[1] != ident)}/records").status_code == 404
    c, ident, _ = patients[0]
    assert c.put(BASE+f"/patients/{ident}/doctor-access", json={"enabled": False, "expected_version": 1}).status_code == 200
    assert doctor.get(BASE+f"/patients/{ident}/records").status_code == 404
    assert doctor.get(BASE+"/care/patients").json()["total"] == 4


@pytest.mark.parametrize("mutation", ["source_kind", "synthetic", "read_only", "clinical_use", "execution_enabled", "patient_id", "username", "provenance", "sections"])
def test_missing_provenance_or_wrong_owner_never_appends(app, mutation):
    c, identity = web(app, NAMES[0])
    ident = identity["patient_id"]
    packet = deepcopy(document(NAMES[0], ident))
    if mutation == "source_kind":
        packet[mutation] = "WEB_LOCAL"
    else:
        del packet["payload"][mutation]
    assert c.post(BASE+f"/patients/{ident}/record-events", json=packet).status_code == 422
    assert c.get(BASE+f"/patients/{ident}/records").json()["items"] == []


@pytest.mark.parametrize("index", range(5))
def test_packet_is_stable_complete_under_size_limit_and_not_a_measured_result(index):
    packet = document(NAMES[index], str(uuid4()))
    assert document(NAMES[index], packet["payload"]["patient_id"]) == packet
    assert len(fingerprint(packet)) == 64
    import json
    assert len(json.dumps(packet, ensure_ascii=False).encode()) < 32768
    assert "measured_at" not in packet["payload"] and "result" not in packet["payload"]
    assert not packet["payload"]["execution_enabled"] and not packet["payload"]["clinical_use"]
    section = next(s for s in packet["payload"]["sections"] if s["key"] == "medications")
    assert any(r["value"] == CASES[index][7] for r in section["rows"])
