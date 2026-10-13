"""All actors, provider responses and records in this module are fictional."""
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import select

from cloud_service.app import BASE, create_app
from cloud_service.ai_usage import AIConfig, receipts
from cloud_service.care_queue import deadline
from cloud_service.tests.test_workbench import setup, people, path
from cloud_service.tests.test_workbench import plan_body, publish, adoption


def configured(setup, dispatch, **config):
    app, db, settings = setup
    return create_app(settings, db, ai_config=AIConfig(key="TEST-NOT-A-REAL-KEY", **config), ai_dispatch=dispatch)


def answer(*args):
    return {"id": "TEST-receipt", "choices": [{"message": {"content": "TEST 一般问答，不作医嘱"}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150,
                      "prompt_cache_hit_tokens": 20, "prompt_cache_miss_tokens": 80}}


def test_receipt_idempotent_and_actual_tariff(setup):
    calls = []
    def dispatch(*args):
        calls.append(args)
        return answer()
    app = configured(setup, dispatch, tariff={"version": "TEST-flat", "currency": "CNY", "cache_hit": "0.1", "cache_miss": "1", "output": "2"})
    aid, bid, alice, bob, doctor = people((app, *setup[1:]))
    body = {"operation_id": str(uuid4()), "text": "TEST 什么是训练反馈"}
    first = alice.post(path(aid, "/ai/requests"), json=body)
    assert first.is_success, first.text
    assert first.json()["estimated_cost"] == "0.000182"
    assert first.json()["state"] == "SUCCEEDED"
    assert alice.post(path(aid, "/ai/requests"), json=body).json() == first.json()
    assert len(calls) == 1
    assert alice.post(path(aid, "/ai/requests"), json={**body, "text": "不同问题"}).status_code == 409
    assert bob.get(path(aid, "/ai/usage")).status_code == 404
    assert doctor.post(path(aid, "/ai/requests"), json=body).status_code == 403
    use = alice.get(path(aid, "/ai/usage")).json()
    assert use["usage"]["total_tokens"] == 150
    assert use["remaining_tokens"] == 199850
    assert use["usage"]["estimated_cost_by_currency"] == {"CNY": "0.000182"}
    assert len(doctor.get(BASE + "/care/beta-users").json()["items"]) == 2
    assert alice.get(BASE + "/care/beta-users").status_code == 403


def test_timeout_not_free_or_redispatched(setup):
    calls = []
    def dispatch(*args):
        calls.append(1)
        raise TimeoutError("TEST")
    app = configured(setup, dispatch)
    aid, _, alice, _, _ = people((app, *setup[1:]))
    body = {"operation_id": str(uuid4()), "text": "TEST"}
    assert alice.post(path(aid, "/ai/requests"), json=body).json()["state"] == "UNKNOWN"
    assert alice.post(path(aid, "/ai/requests"), json=body).json()["estimated_cost"] is None
    assert len(calls) == 1
    usage = alice.get(path(aid, "/ai/usage")).json()["usage"]
    assert usage["reserved_tokens"] > 0 and usage["uncertain_calls"] == 1


def test_missing_usage_and_quota_fail_closed(setup):
    app = configured(setup, lambda *_: {"choices": [{"message": {"content": "TEST"}}]}, monthly_calls=1)
    aid, _, alice, _, _ = people((app, *setup[1:]))
    response = alice.post(path(aid, "/ai/requests"), json={"operation_id": str(uuid4()), "text": "TEST"})
    assert response.json()["state"] == "UNMETERED"
    assert response.json()["estimated_cost"] is None
    assert alice.post(path(aid, "/ai/requests"), json={"operation_id": str(uuid4()), "text": "TEST"}).status_code == 429


def test_disabled_gateway_does_not_create_usage(setup):
    aid, _, alice, _, _ = people(setup)
    response = alice.post(path(aid, "/ai/requests"), json={"operation_id": str(uuid4()), "text": "TEST"})
    assert response.status_code == 503
    with setup[1].engine.connect() as connection:
        assert not connection.execute(select(receipts)).first()


def test_lunch_weekend_holiday_calendar():
    zone = timezone(timedelta(hours=8))
    def timestamp(value):
        return int(datetime.fromisoformat(value).replace(tzinfo=zone).timestamp())
    calendar = {"intervals": {str(i): [[540, 720], [840, 1080]] for i in range(1, 6)}, "holidays": ["2026-10-19"]}
    assert deadline(timestamp("2026-10-13T11:30:00"), calendar) == timestamp("2026-10-13T14:30:00")
    assert deadline(timestamp("2026-10-16T17:30:00"), calendar) == timestamp("2026-10-20T09:30:00")


def test_effective_reply_supplements_and_scope(setup):
    aid, _, alice, bob, doctor = people(setup)
    body = {"expected_version": 0, "intervals": {str(i): [[0, 1440]] for i in range(1, 8)}, "holidays": []}
    assert doctor.put(BASE + "/care/calendar", json=body).is_success
    assert doctor.put(BASE + "/care/calendar", json=body).status_code == 412
    def send(client, text):
        response = client.post(path(aid, "/messages"), json={"operation_id": str(uuid4()), "text": text})
        assert response.is_success, response.text
        return response.json()["item"]
    send(alice, "TEST 首个问题")
    before = doctor.get(BASE + "/care/queue").json()["items"][0]
    send(alice, "TEST 补充说明")
    after = doctor.get(BASE + "/care/queue").json()["items"][0]
    assert after["first_sequence"] == before["first_sequence"] and after["due_at"] == before["due_at"]
    reply = send(doctor, "TEST 人工有效回答")
    assert doctor.get(BASE + "/care/queue").json()["total"] == 1
    endpoint = path(aid, "/messages/" + reply["id"] + "/effective-response")
    assert alice.post(endpoint, json={}).status_code == 403
    send(alice, "TEST 回复后又问的新问题")
    assert doctor.post(endpoint, json={}).is_success
    assert doctor.get(BASE + "/care/queue").json()["total"] == 1
    new_reply = send(doctor, "TEST 第二次有效回答")
    endpoint = path(aid, "/messages/" + new_reply["id"] + "/effective-response")
    assert doctor.post(endpoint, json={}).is_success
    assert doctor.post(endpoint, json={}).is_success
    assert doctor.get(BASE + "/care/queue").json()["total"] == 0
    send(alice, "TEST 新问题")
    assert doctor.get(BASE + "/care/queue").json()["total"] == 1


def test_reports_owner_sharing_and_revoke(setup):
    import base64
    aid, _, alice, bob, doctor = people(setup)
    body = {"operation_id": str(uuid4()), "filename": "TEST-不是病历.pdf", "mime": "application/pdf",
            "data": base64.b64encode(b"%PDF-1.4\nTEST-NOT-A-MEDICAL-REPORT").decode(), "shared": False}
    response = alice.post(path(aid, "/reports"), json=body)
    assert response.status_code == 201, response.text
    report = response.json()["item"]
    assert alice.post(path(aid, "/reports"), json=body).json()["idempotent"]
    assert doctor.get(path(aid, "/reports")).json()["items"] == []
    original = path(aid, "/reports/" + report["id"] + "/original")
    assert doctor.get(original).status_code == 404
    assert bob.get(original).status_code == 404
    shared = path(aid, "/reports/" + report["id"] + "/sharing")
    assert alice.put(shared, json={"expected_version": 1, "shared": True}).is_success
    download = doctor.get(original)
    assert download.is_success and download.content.startswith(b"%PDF-")
    assert download.headers["content-disposition"].startswith("attachment;")
    assert download.headers["cache-control"] == "no-store"
    assert alice.put(shared, json={"expected_version": 2, "shared": False}).is_success
    assert doctor.get(original).status_code == 404
    assert alice.post(path(aid, "/reports"), json={**body, "data": "bad!"}).status_code == 422


def test_programme_today_rest_day_suspend_and_no_chat_mutation(setup):
    from cloud_service.plan_programmes import day_today
    aid, _, alice, _, doctor = people(setup)
    today = day_today()
    items = plan_body()["items"]
    weekday = datetime.fromisoformat(today).isoweekday()
    phase = {"name": "TEST 仅用于规则验证", "until_date": today, "weekdays": [weekday], "items": items,
             "equipment": "稳定支撑", "load": "", "manual_only": False}
    plan = publish(doctor, aid, plan_body(programme={"start_date": today, "phases": [phase]}))
    patient_plan = alice.get(path(aid, "/plans")).json()["items"][0]
    assert patient_plan["execution_status"] == "READY" and patient_plan["execution_date"] == today
    accepted = alice.post(path(aid, "/plans/" + plan["id"] + "/accept"), json=adoption(patient_plan))
    assert accepted.is_success, accepted.text
    alice.post(path(aid, "/messages"), json={"operation_id": str(uuid4()), "text": "TEST 聊天不能把次数改到99"})
    assert alice.get(path(aid, "/plans/current")).json()["plan"]["items"][0]["settings"]["target_reps"] == 2
    endpoint = path(aid, "/plans/" + plan["id"] + "/stop")
    assert alice.post(endpoint, json={"expected_version": plan["version"], "reason": "TEST"}).status_code == 403
    assert doctor.post(endpoint, json={"expected_version": plan["version"], "reason": "TEST 停用，不用于人体"}).is_success
    assert alice.get(path(aid, "/plans/current")).json()["plan"]["execution_status"] == "STOPPED"
    assert alice.post(path(aid, "/plans/" + plan["id"] + "/accept"), json=adoption(patient_plan, revision=1)).status_code == 409
    rest = {**phase, "weekdays": [weekday % 7 + 1]}
    newer = publish(doctor, aid, plan_body(programme={"start_date": today, "phases": [rest]}))
    row = next(p for p in alice.get(path(aid, "/plans")).json()["items"] if p["id"] == newer["id"])
    assert row["execution_status"] == "REST_DAY" and row["items"] == []


def test_programme_rejects_unsupported_load_and_preserves_published_versions(setup):
    from cloud_service.plan_programmes import day_today
    aid, _, _, _, doctor = people(setup)
    today = day_today()
    phase = {"name": "TEST", "until_date": today, "weekdays": [1,2,3,4,5,6,7], "items": plan_body()["items"],
             "equipment": "", "load": "TEST 5kg", "manual_only": False}
    response = doctor.post(path(aid, "/plans"), json=plan_body(programme={"start_date": today, "phases": [phase]}))
    assert response.status_code == 422
    assert response.json()["code"] == "PROGRAMME_UNSUPPORTED_LOAD"


def test_production_record_filter_does_not_promote_fixtures(setup):
    from cloud_service.database import records
    from cloud_service.real_data import real_record_condition, synthetic
    aid, _, alice, _, _ = people(setup)
    bodies = [{"text": "TEST representation of a real record", "synthetic": False},
              {"schema": "old", "synthetic": True}, {"result": {"source_kind": "SYNTHETIC"}},
              {"result": {"synthetic": {"invalid": "marker"}}}, {"result": {"fixture": "TEST"}}, {"result": {"usage_context": "TEST"}}]
    for index, payload in enumerate(bodies):
        assert alice.post(path(aid, "/record-events"), json={"operation_id": str(uuid4()), "source_event_id": "TEST-filter-"+str(index),
            "installation_id": "TEST", "source_kind": "SELF_REPORT", "payload": payload}).is_success
    with setup[1].engine.connect() as c:
        rows = c.execute(select(records.c.payload).where(real_record_condition(records))).scalars().all()
    assert rows == [bodies[0]]
    assert not synthetic(bodies[0]) and all(synthetic(p) for p in bodies[1:])


def test_workflow_reuses_preferences_and_requires_saved_evidence_and_review(setup):
    aid, _, alice, bob, doctor = people(setup)
    profile = {"expected_version": 0, "goal": "TEST 流程验证，不用于人体", "region": "膝", "level": 0,
               "equipment": ["稳固椅"], "restrictions": [], "screening_confirmed": True}
    response = alice.put(path(aid, "/rehab-workflow/profile"), json=profile)
    assert response.is_success, response.text
    assert response.json()["profile_version"] == 1
    assert alice.put(path(aid, "/rehab-workflow/profile"), json=profile).status_code == 412
    assert bob.get(path(aid, "/rehab-workflow")).status_code == 404
    assert doctor.get(path(aid, "/rehab-workflow")).json()["profile"]["equipment"] == ["稳固椅"]
    operation = {"operation_id": str(uuid4()), "kind": "STARTER"}
    assert alice.post(path(aid, "/rehab-candidates"), json=operation).status_code == 409
    record = {"operation_id": str(uuid4()), "source_event_id": "TEST-assessment", "installation_id": "TEST",
              "source_kind": "DESKTOP_LOCAL", "payload": {"schema": "ankang-workbench-record-1", "source": "DESKTOP_LOCAL",
              "patient_id": aid, "kind": "assessment", "record_key": "TEST-result", "revision": 1, "owner_id": "TEST-local-owner",
              "captured_at": datetime.now(timezone.utc).isoformat(), "title": "TEST assessment representation, no person",
              "result": {"exercise_id": "knee_extension", "side": "left", "end_utc": datetime.now(timezone.utc).isoformat(), "status": "FINISHED"}}}
    assert alice.post(path(aid, "/record-events"), json=record).is_success
    response = alice.post(path(aid, "/rehab-candidates"), json=operation)
    assert response.is_success, response.text
    candidate = response.json()
    assert candidate["state"] == "PENDING_REVIEW" and candidate["document"]["model_calls"] == 0
    assert not candidate["document"]["automatic_execution"]
    assert alice.post(path(aid, "/rehab-candidates"), json=operation).json()["id"] == candidate["id"]
    assert alice.get(path(aid, "/plans/current")).json()["plan"] is None
    review = path(aid, "/rehab-candidates/" + candidate["id"] + "/review")
    assert alice.post(review, json={"decision": "REVIEWED"}).status_code == 403
    assert doctor.post(review, json={"decision": "REVIEWED"}).is_success
    assert doctor.post(review, json={"decision": "REJECTED"}).status_code == 409
    assert alice.get(path(aid, "/plans/current")).json()["plan"] is None


def test_empty_workbench_is_empty_and_no_fictional_users_seeded(setup):
    from cloud_service.tests.test_accounts import client, login
    doctor = client(setup[0])
    assert login(doctor, "doctor").is_success
    result = doctor.get(BASE + "/care/beta-users").json()
    assert result["total"] == 0 and result["items"] == []
    assert doctor.get(BASE + "/care/queue").json()["items"] == []


def test_sixty_beta_users_pagination_does_not_grant_medical_access(setup):
    import time
    from cloud_service.database import accounts, patients
    from cloud_service.tests.test_accounts import client, login
    app, db, _ = setup
    with db.engine.begin() as connection:
        password = connection.execute(select(accounts.c.password_hash)).scalar_one()
        for number in range(61):
            account_id, patient_id = str(uuid4()), str(uuid4())
            connection.execute(accounts.insert().values(id=account_id, username=f"TEST-beta-{number:03}",
                password_hash=password, role="PATIENT", active=True, created_at=int(time.time())))
            connection.execute(patients.insert().values(id=patient_id, account_id=account_id,
                display_name=f"TEST 隔离用户 {number:03}", created_at=int(time.time())))
    doctor = client(app)
    assert login(doctor, "doctor").is_success
    first = doctor.get(BASE + "/care/beta-users?limit=60").json()
    second = doctor.get(BASE + "/care/beta-users?offset=60&limit=60").json()
    assert first["total"] == 61 and len(first["items"]) == 60 and len(second["items"]) == 1
    assert {p["id"] for p in first["items"]}.isdisjoint({p["id"] for p in second["items"]})
    assert not any(p["doctor_access"] for p in first["items"])
    assert doctor.get(BASE + "/care/patients").json()["total"] == 0
