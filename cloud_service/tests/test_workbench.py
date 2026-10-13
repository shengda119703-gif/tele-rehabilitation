"""Isolated synthetic workbench contracts, never production patient records."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update

from cloud_service.app import BASE, create_app
from cloud_service.config import Settings
from cloud_service.database import Database, accounts, audit, metadata, records, schema
from cloud_service.security import bootstrap_doctor
from cloud_service.workbench import (
    action_library, current_plans, message_reads, messages, operations, plans, record_heads,
)
from cloud_service.tests.test_accounts import client, login, register


@pytest.fixture
def setup(tmp_path):
    settings = Settings("sqlite:///" + str(tmp_path / "workbench.sqlite3"), "x" * 40, ("http://testserver",), "test")
    db = Database(settings.database_url)
    db.migrate()
    bootstrap_doctor(db, settings, "1")
    app = create_app(settings, db)
    yield app, db, settings
    db.engine.dispose()


def people(setup):
    app = setup[0]
    alice, bob, doctor = [client(app) for _ in range(3)]
    aid = register(alice, "test-alice").json()["patient_id"]
    bid = register(bob, "test-bob").json()["patient_id"]
    assert login(alice, "test-alice").is_success
    assert login(bob, "test-bob").is_success
    assert login(doctor, "doctor").is_success
    assert alice.put(BASE + "/patients/" + aid + "/doctor-access", json={"enabled": True, "expected_version": 0}).is_success
    return aid, bid, alice, bob, doctor


def path(ident, suffix):
    return BASE + "/patients/" + ident + suffix


def plan_body(**extra):
    card = action_library()["shoulder_abduction"]
    return {"operation_id": str(uuid4()), "title": "TEST 专业人员安排", "summary": "合成测试，不用于人体训练",
        "items": [{"exercise_id": card["exercise_id"], "name": card["name"], "side": "left",
            "measurement_contract": card["measurement_contract"],
            "settings": {"target_reps": 2, "target_sets": 1, "rest_between_sets_s": 30, "target_angle_deg": None},
            "caution": "TEST 有不适停止"}], **extra}


def publish(doctor, aid, body=None):
    response = doctor.post(path(aid, "/plans"), json=body or plan_body())
    assert response.status_code == 201, response.text
    draft = response.json()["plan"]
    response = doctor.post(path(aid, "/plans/" + draft["id"] + "/publish"),
        json={"operation_id": str(uuid4()), "expected_version": draft["version"]})
    assert response.status_code == 200, response.text
    return response.json()["plan"]


def adoption(plan, revision=0, **extra):
    return {"operation_id": str(uuid4()), "expected_version": plan["version"], "expected_current_revision": revision,
        "local_validation": {"local_plan_id": uuid4().hex, "local_revision": 1,
            "scope": {"participant_id": "TEST-local-owner", "source_kind": "LIVE_CAMERA", "usage_context": "SELF_USE"},
            "validation_policy": "existing-local-assessment-1",
            "assessment_references": [{"key": item["key"], "session_id": "TEST-assessment", "measurement_contract": item["measurement_contract"]} for item in plan["items"]],
            "validated_at": datetime.now(timezone.utc).isoformat()}, **extra}


def test_manifest_matches_existing_53_measurement_contracts():
    from tools.cloud.build_workbench_catalogue import catalogue
    expected = catalogue()
    assert len(expected["items"]) == 53
    assert list(action_library().values()) == expected["items"]
    assert all(not card["clinical_rom"] for card in expected["items"])


def test_additive_schema_1_migration_preserves_accounts_and_history(setup):
    aid, _, alice, _, doctor = people(setup)
    alice.post(path(aid, "/record-events"), json={"operation_id": str(uuid4()), "source_event_id": "TEST-original",
        "installation_id": "TEST-device", "source_kind": "SELF_REPORT", "payload": {"text": "original"}})
    db = setup[1]
    with db.engine.begin() as conn:
        identifiers = list(conn.execute(select(accounts.c.id)).scalars())
        original = dict(conn.execute(select(records)).mappings().first())
        # Recreate the actual schema-1 shape without touching any real database.
        for table in (operations, message_reads, current_plans, plans, messages, record_heads):
            table.drop(conn)
        conn.execute(update(schema).values(version=1))
    db.migrate()
    db.migrate()
    with db.engine.connect() as conn:
        assert conn.scalar(select(schema.c.version)) == 3
        assert list(conn.execute(select(accounts.c.id)).scalars()) == identifiers
        assert dict(conn.execute(select(records)).mappings().first()) == original
        assert conn.scalar(select(func.count()).select_from(messages)) == 0
    assert doctor.get(path(aid, "/records")).json()["items"][0]["payload"] == {"text": "original"}


def test_message_isolation_unread_retries_and_monotonic_read(setup):
    aid, bid, alice, bob, doctor = people(setup)
    body = {"operation_id": str(uuid4()), "text": "TEST 本人消息"}
    response = alice.post(path(aid, "/messages"), json=body)
    assert response.status_code == 201
    retry = alice.post(path(aid, "/messages"), json=body).json()
    assert retry["resource_id"] == response.json()["resource_id"] and retry["idempotent"]
    assert alice.post(path(aid, "/messages"), json={**body, "text": "changed"}).status_code == 409
    assert bob.get(path(aid, "/messages")).status_code == 404
    assert bob.post(path(aid, "/messages"), json=body).status_code == 404
    assert doctor.get(path(bid, "/messages")).status_code == 404
    view = doctor.get(path(aid, "/messages?latest=true")).json()
    assert view["unread_count"] == 1 and view["read_cursor"] == 0
    assert alice.get(path(aid, "/messages")).json()["unread_count"] == 0
    read = {"operation_id": str(uuid4()), "cursor": view["next_cursor"]}
    assert doctor.post(path(aid, "/messages/read"), json=read).json()["unread_count"] == 0
    assert doctor.post(path(aid, "/messages/read"), json=read).json()["idempotent"]
    assert doctor.post(path(aid, "/messages/read"), json={"operation_id": str(uuid4()), "cursor": 0}).json()["read_cursor"] == 1
    assert doctor.post(path(aid, "/messages/read"), json={"operation_id": str(uuid4()), "cursor": 99}).status_code == 422
    doctor.post(path(aid, "/messages"), json={"operation_id": str(uuid4()), "text": "TEST 医生回复"})
    assert alice.get(path(aid, "/messages?after=1")).json()["items"][0]["sequence"] == 2
    assert alice.get(path(aid, "/messages")).json()["unread_count"] == 1
    with setup[1].engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(messages)) == 2


def test_message_recent_and_older_paging_do_not_mark_unseen_read(setup):
    aid, _, alice, _, doctor = people(setup)
    for index in range(6):
        assert alice.post(path(aid, "/messages"), json={"operation_id": str(uuid4()), "text": "TEST " + str(index)}).is_success
    latest = doctor.get(path(aid, "/messages?latest=true&limit=3")).json()
    assert [m["sequence"] for m in latest["items"]] == [4, 5, 6]
    assert latest["has_older"] and latest["read_cursor"] == 0 and latest["unread_count"] == 6
    older = doctor.get(path(aid, "/messages?before=4&limit=3")).json()
    assert [m["sequence"] for m in older["items"]] == [1, 2, 3]
    forward = doctor.get(path(aid, "/messages?after=2&limit=3")).json()
    assert [m["sequence"] for m in forward["items"]] == [3, 4, 5] and forward["has_more"]


def test_revocation_blocks_existing_doctor_session_all_workbench_routes(setup):
    aid, _, alice, _, doctor = people(setup)
    plan = publish(doctor, aid)
    alice.put(path(aid, "/doctor-access"), json={"enabled": False, "expected_version": 1})
    for suffix in ("/messages", "/plans", "/plans/current", "/records/latest", "/rehab-summary"):
        assert doctor.get(path(aid, suffix)).status_code == 404
    assert doctor.post(path(aid, "/messages"), json={"operation_id": str(uuid4()), "text": "TEST"}).status_code == 404
    assert doctor.post(path(aid, "/plans"), json=plan_body()).status_code == 404
    assert alice.post(path(aid, "/messages"), json={"operation_id": str(uuid4()), "text": "TEST"}).status_code == 403
    assert alice.post(path(aid, "/plans/" + plan["id"] + "/accept"), json=adoption(plan)).status_code == 403
    # A patient's own published history remains theirs after contact revocation.
    assert alice.get(path(aid, "/plans")).json()["total"] == 1


def test_draft_visibility_edit_conflict_immutable_publish_and_explicit_adoption(setup):
    aid, _, alice, _, doctor = people(setup)
    body = plan_body()
    created = doctor.post(path(aid, "/plans"), json=body).json()
    draft = created["plan"]
    assert doctor.post(path(aid, "/plans"), json=body).json()["idempotent"]
    assert alice.get(path(aid, "/plans")).json()["items"] == []
    edit = {**body, "operation_id": str(uuid4()), "expected_version": 1, "title": "TEST 修订"}
    changed = doctor.put(path(aid, "/plans/" + draft["id"]), json=edit).json()["plan"]
    assert changed["version"] == 2
    assert doctor.put(path(aid, "/plans/" + draft["id"]), json={**edit, "operation_id": str(uuid4())}).status_code == 412
    transition = {"operation_id": str(uuid4()), "expected_version": 2}
    result = doctor.post(path(aid, "/plans/" + draft["id"] + "/publish"), json=transition).json()
    plan = result["plan"]
    assert plan["status"] == "PUBLISHED" and plan["version"] == 3
    assert doctor.post(path(aid, "/plans/" + draft["id"] + "/publish"), json=transition).json()["idempotent"]
    assert doctor.put(path(aid, "/plans/" + draft["id"]), json={**edit, "operation_id": str(uuid4()), "expected_version": 3}).status_code == 409
    assert alice.get(path(aid, "/plans/current")).json()["plan"] is None
    invalid = {"operation_id": str(uuid4()), "expected_version": 3, "expected_current_revision": 0}
    assert alice.post(path(aid, "/plans/" + plan["id"] + "/accept"), json=invalid).status_code == 422
    body = adoption(plan)
    result = alice.post(path(aid, "/plans/" + plan["id"] + "/accept"), json=body)
    assert result.status_code == 200, result.text
    assert result.json()["current_revision"] == 1
    assert result.json()["local_validation"]["attribution_state"] == "CLIENT_DECLARED"
    assert not result.json()["local_validation"]["automatic_execution"]
    assert alice.post(path(aid, "/plans/" + plan["id"] + "/accept"), json=body).json()["idempotent"]
    assert doctor.post(path(aid, "/plans/" + plan["id"] + "/accept"), json=adoption(plan)).status_code == 403
    assert alice.get(path(aid, "/plans/current")).json()["plan"]["id"] == plan["id"]


def test_old_publication_and_stale_current_revision_cannot_replace_current(setup):
    aid, _, alice, _, doctor = people(setup)
    old = publish(doctor, aid)
    assert alice.post(path(aid, "/plans/" + old["id"] + "/accept"), json=adoption(old)).is_success
    new = publish(doctor, aid, plan_body(parent_plan_id=old["id"]))
    assert alice.post(path(aid, "/plans/" + old["id"] + "/accept"), json=adoption(old, 1)).status_code == 412
    assert alice.post(path(aid, "/plans/" + new["id"] + "/accept"), json=adoption(new, 0)).status_code == 412
    assert alice.get(path(aid, "/plans/current")).json()["plan"]["id"] == old["id"]
    assert alice.post(path(aid, "/plans/" + new["id"] + "/accept"), json=adoption(new, 1)).is_success


@pytest.mark.parametrize("mutation", [
    {"exercise_id": "T-LOW-003"}, {"name": "invented"}, {"side": "both"},
    {"measurement_contract": "old"}, {"settings": {"target_reps": 2}},
    {"settings": {"target_reps": True, "target_sets": 1, "rest_between_sets_s": 30, "target_angle_deg": None}},
    {"settings": {"target_reps": 2, "target_sets": 1, "rest_between_sets_s": 30, "target_angle_deg": 181}},
])
def test_invalid_executable_items_cannot_publish(setup, mutation):
    aid, _, _, _, doctor = people(setup)
    body = plan_body()
    body["items"][0].update(mutation)
    assert doctor.post(path(aid, "/plans"), json=body).status_code == 422
    assert doctor.get(path(aid, "/plans")).json()["total"] == 0


@pytest.mark.parametrize("mutate", [
    lambda v: v["scope"].update(usage_context="TEST"),
    lambda v: v["assessment_references"][0].update(key="other:right"),
    lambda v: v["assessment_references"][0].update(measurement_contract="old"),
    lambda v: v.update(validated_at="2026-10-13T12:00:00"),
])
def test_adoption_rejects_unvalidated_scope_or_measurement(setup, mutate):
    aid, _, alice, _, doctor = people(setup)
    plan = publish(doctor, aid)
    value = adoption(plan)
    mutate(value["local_validation"])
    assert alice.post(path(aid, "/plans/" + plan["id"] + "/accept"), json=value).status_code == 422
    assert alice.get(path(aid, "/plans/current")).json()["plan"] is None


def record_body(aid, revision, score):
    return {"operation_id": str(uuid4()), "source_event_id": "TEST-assessment:r" + str(revision), "installation_id": "TEST-device",
        "source_kind": "DESKTOP_LOCAL", "payload": {"schema": "ankang-workbench-record-1", "kind": "assessment",
            "title": "TEST 保存评估", "patient_id": aid, "owner_id": "TEST-local", "captured_at": "2026-10-13T00:00:00Z",
            "source": "DESKTOP_LOCAL", "record_key": "assessment:TEST-1", "revision": revision, "result": {"score": score}}}


def test_actual_record_revision_projection_preserves_originals_and_latest(setup):
    aid, bid, alice, bob, doctor = people(setup)
    first = record_body(aid, 1, 0)
    original = alice.post(path(aid, "/record-events"), json=first)
    assert original.status_code == 201, original.text
    assert alice.post(path(aid, "/record-events"), json=first).json()["idempotent"]
    second = record_body(aid, 2, None)
    assert alice.post(path(aid, "/record-events"), json=second).status_code == 201
    stale = record_body(aid, 1, 99)
    stale["source_event_id"] = "TEST-stale-attempt"
    assert alice.post(path(aid, "/record-events"), json=stale).status_code == 409
    wrong_owner = record_body(bid, 3, 99)
    assert alice.post(path(aid, "/record-events"), json=wrong_owner).status_code == 422
    assert bob.get(path(aid, "/records/latest")).status_code == 404
    current = doctor.get(path(aid, "/records/latest")).json()
    assert current["total"] == 1 and current["items"][0]["payload"]["revision"] == 2
    assert current["items"][0]["payload"]["result"]["score"] is None
    summary = doctor.get(path(aid, "/rehab-summary")).json()
    assert len(summary["assessment"]) == 1 and summary["training"] == []
    history = alice.get(path(aid, "/records")).json()["items"]
    assert len(history) == 2 and any(r["payload"]["result"]["score"] == 0 for r in history)


def test_concurrent_lost_message_reply_and_current_plan_race(setup):
    aid, _, alice, _, doctor = people(setup)
    app = setup[0]
    # Native sessions allow parallel clients without copying browser cookies.
    signed = login(alice, "test-alice", kind="DESKTOP").json()
    from fastapi.testclient import TestClient
    headers = {"X-Ankang-Client": "native", "Authorization": "Bearer " + signed["access_token"]}
    body = {"operation_id": str(uuid4()), "text": "TEST 丢回执后重试"}
    def send(_):
        with TestClient(app, headers=headers) as c:
            reply = c.post(path(aid, "/messages"), json=body)
            assert reply.status_code == 201, reply.text
            return reply.json()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(send, range(4)))
    assert len({r["resource_id"] for r in results}) == 1 and sum(not r["idempotent"] for r in results) == 1
    plan = publish(doctor, aid)
    def accept(_):
        with TestClient(app, headers=headers) as c:
            return c.post(path(aid, "/plans/" + plan["id"] + "/accept"), json=adoption(plan)).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(accept, range(2)))
    assert sorted(statuses) == [200, 412]
    with setup[1].engine.connect() as conn:
        assert conn.scalar(select(current_plans.c.revision)) == 1
