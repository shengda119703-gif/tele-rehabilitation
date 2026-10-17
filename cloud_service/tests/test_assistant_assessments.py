"""Fictitious accounts and uploads only; no external provider calls."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
import json
import threading
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update

from cloud_service import assistant, assistant_assessments as appointments, assistant_dialogue as dialogue
from cloud_service.database import records
from cloud_service.rehab_workflow import candidates
from cloud_service.tests.test_assistant import setup, forbid_external_requests, body as legacy_body, post, configured, upload, provider_answer
from cloud_service.tests.test_workbench import people, path
from cloud_service.tests.test_accounts import client, login


def body(text="今天练什么", **options):
    return legacy_body(text, assessment_contract="ordered-video-1", **options)


def listing(c, ident):
    r = c.get(path(ident, "/assistant/assessment-plans"))
    assert r.is_success, r.text
    return r.json()["items"]


def test_one_followup_schedules_online_assessment_and_no_training_or_measurements(setup):
    aid, _, alice, bob, doctor = people(setup)
    first = post(alice, aid, body("我硬拉后腰疼"))
    assert first["turn"]["actions"] == []
    assert listing(alice, aid) == []
    second = post(alice, aid, body("疼痛三分，没有腿麻，也没有大小便异常"))
    assert "先确认" not in second["turn"]["answer"] and "已加入我的计划" in second["turn"]["answer"]
    assert "线下" not in second["turn"]["answer"]
    plans = listing(alice, aid)
    assert len(plans) == 1 and plans[0]["status"] == "PLANNED"
    assert [item["exercise_id"] for item in plans[0]["items"]] == ["sit_to_stand", "knee_extension"]
    assert plans[0]["routing_version"] == appointments.VERSION
    assert plans[0]["items"][0]["record_id"] is None
    assert plans[0]["id"] == second["turn"]["actions"][0]["plan_id"]
    assert post(alice, aid, {"operation_id":second["turn"]["operation_id"], "text":second["turn"]["text"], "assessment_contract":"ordered-video-1"}) == second
    assert len(listing(alice, aid)) == 1
    for outsider in (bob, doctor):
        assert outsider.get(path(aid, "/assistant/assessment-plans")).status_code == 404
        assert outsider.post(path(aid, "/assistant/assessment-plans/"+plans[0]["id"]+"/cancel"), json={}).status_code == 404
    with setup[1].engine.connect() as c:
        assert c.scalar(select(func.count()).select_from(records)) == 0
        assert c.scalar(select(func.count()).select_from(candidates)) == 0


def test_explicit_assessment_has_only_supported_tasks_reuses_pending_and_cross_device_reads(setup):
    aid, _, alice, _, _ = people(setup)
    post(alice, aid, body("帮我安排左肩的线上评估"))
    first = listing(alice, aid)
    assert len(first) == 1 and first[0]["items"] and all(item["side"] == "left" for item in first[0]["items"])
    post(alice, aid, body("帮我安排左肩的线上评估"))
    assert listing(alice, aid) == first
    other = client(setup[0]); assert login(other, "test-alice").is_success
    assert listing(other, aid) == first
    ident = first[0]["id"]
    url = path(aid, "/assistant/assessment-plans/"+ident+"/cancel")
    assert alice.post(url, json={}, headers={"X-CSRF-Token":"wrong"}).status_code == 403
    assert alice.post(url, json={}).json() == {"id":ident,"status":"CANCELLED"}
    assert alice.post(url, json={}).json()["status"] == "CANCELLED"
    assert listing(alice, aid)[0]["status"] == "CANCELLED"
    post(alice, aid, body("帮我安排左肩的线上评估"))
    assert len(listing(alice, aid)) == 2


@pytest.mark.parametrize("text", [
    "腰疼，现在尿不出来", "腰疼，没有腿麻，但大小便异常", "肩痛并且胸痛", "腰疼而且双腿明显无力",
    "腰疼，疼痛八分，没有腿麻没有大小便异常", "膝盖痛，摔伤后无法正常活动",
])
def test_risk_or_severe_symptoms_do_not_schedule_a_motion_test(setup, text):
    aid, _, alice, _, _ = people(setup)
    result = post(alice, aid, body(text))
    assert listing(alice, aid) == []
    assert all(a["kind"] == "doctor_review" for a in result["turn"]["actions"])


def test_unanswered_safety_goes_to_online_clinician_not_endless_questionnaire(setup):
    aid, _, alice, _, _ = people(setup)
    post(alice, aid, body("腰痛"))
    answer = post(alice, aid, body("三分"))["turn"]["answer"]
    assert "先确认" not in answer and "App内康复医师" in answer and "线下" not in answer
    assert listing(alice, aid) == []


def test_model_cannot_override_online_route_or_start_training(setup):
    output = json.dumps({"reply":"需要线下评估后才能安排。", "questions":[], "advice":[], "next_step":"先去医院。"}, ensure_ascii=False)
    _, calls, (aid, _, alice, _, _) = configured(setup, lambda *_:provider_answer(output))
    result = post(alice, aid, body("帮我安排肩部评估"))
    assert result["source"] == "local" and len(calls) == 1
    assert "线下" not in result["turn"]["answer"] and "已加入我的计划" in result["turn"]["answer"]
    assert len(listing(alice, aid)) == 1
    assert result["receipt"]["usage"]["total_tokens"] == 150


def test_private_turn_and_unrelated_chat_never_schedule_or_inherit_old_region(setup):
    aid, _, alice, _, _ = people(setup)
    post(alice, aid, body("左肩评估", private=True))
    assert listing(alice, aid) == []
    post(alice, aid, body("你好"))
    assert listing(alice, aid) == []
    old = [{"text":"腰痛", "answer":"TEST", "created_at":1}]
    assert dialogue.protocol("三分", "CHAT", old)["mode"] != "SYMPTOM"


def test_legacy_only_real_subsequent_matching_completed_assessments_finish_appointment(setup):
    aid, _, alice, _, _ = people(setup)
    post(alice, aid, legacy_body("安排左膝评估"))
    plan = listing(alice, aid)[0]
    assert plan["routing_version"] == "online-assessment-routing-1"
    assert len(plan["items"]) == 1
    assert plan["items"][0]["exercise_id"] == "knee_extension"
    def result(exercise="knee_extension", side="left", at=None, count=1):
        return {"exercise_id":exercise,"side":side,"end_utc":at or datetime.now(timezone.utc).isoformat(), "summary":{"completed":count}}
    upload(alice, aid, key="TEST-old", result=result(at="2000-01-01T00:00:00Z"))
    upload(alice, aid, key="TEST-other-side", result=result(side="right"))
    upload(alice, aid, key="TEST-not-completed", result=result(count=0))
    upload(alice, aid, key="TEST-synthetic", synthetic=True, result=result())
    assert listing(alice, aid)[0]["status"] == "PLANNED"
    upload(alice, aid, key="TEST-real", result=result())
    completed = listing(alice, aid)[0]
    assert completed["status"] == "COMPLETED" and completed["items"][0]["record_id"]


def test_current_ordered_assessment_requires_real_account_result_and_idempotent_link(setup):
    aid, _, alice, bob, doctor = people(setup)
    post(alice, aid, body("安排左膝评估"))
    plan = listing(alice, aid)[0]
    assert [i["exercise_id"] for i in plan["items"]] == ["knee_extension", "knee_flexion"]
    endpoint = path(aid, "/assistant/assessment-plans/"+plan["id"]+"/results")
    def save(exercise, **changes):
        facts = {"exercise_id":exercise, "side":"left", "analysis_state":"done",
                 "measurement_version":"android-local-projection-1",
                 "end_utc":datetime.now(timezone.utc).isoformat(),
                 "summary":{"completed":2,"valid_ratio":.9,"motion_range":{"max_deg":80,"min_deg":10,"range_deg":70}}, **changes}
        key = "TEST-ordered-"+str(uuid4())
        upload(alice, aid, key=key, result=facts)
        with setup[1].engine.connect() as c:
            return next(r.id for r in c.execute(select(records.c.id,records.c.payload)) if r.payload.get("record_key")==key)
    invalid = save("knee_extension", analysis_state="analyzing")
    assert alice.post(endpoint,json={"item_index":0,"record_id":invalid}).status_code == 422
    second = save("knee_flexion")
    assert alice.post(endpoint,json={"item_index":1,"record_id":second}).status_code == 409
    first = save("knee_extension")
    assert listing(alice,aid)[0]["status"] == "PLANNED"  # Upload alone never claims plan completion.
    value = {"item_index":0,"record_id":first}
    for outsider in (bob,doctor):
        assert outsider.post(endpoint,json=value).status_code == 404
    assert alice.post(endpoint,json=value,headers={"X-CSRF-Token":"wrong"}).status_code == 403
    for _ in range(2):
        receipt=alice.post(endpoint,json=value)
        assert receipt.is_success, receipt.text
        assert receipt.json()["plan"]["next_index"] == 1
    assert alice.post(endpoint,json={"item_index":0,"record_id":second}).status_code == 409
    done=alice.post(endpoint,json={"item_index":1,"record_id":second})
    assert done.is_success, done.text
    assert done.json()["plan"]["status"] == "COMPLETED"
    assert done.json()["plan"]["items"][0]["result"]["range_deg"] == 70
    assert listing(alice,aid)[0]["status"] == "COMPLETED"
    with setup[1].engine.connect() as c:
        assert c.scalar(select(func.count()).select_from(candidates)) == 0


def test_concurrent_different_operations_reuse_one_pending_appointment(setup):
    aid, _, alice, _, _ = people(setup)
    with ThreadPoolExecutor(2) as executor:
        results = list(executor.map(lambda _:post(alice, aid, body("安排右肩评估")), range(2)))
    assert len(listing(alice, aid)) == 1
    assert results[0]["turn"]["actions"][0]["plan_id"] == results[1]["turn"]["actions"][0]["plan_id"]


def test_frozen_v2_uses_its_original_validator():
    spec = {"version":"rehab-dialogue-2", "mode":"SYMPTOM", "back_related":True,
            "already_answered":{"pain_score":False}, "urgent_back_symptoms":False}
    output = json.dumps({"reply":"先暂停不适动作。", "questions":[dialogue.SCALE_QUESTION], "advice":[], "next_step":"请先补充。"}, ensure_ascii=False)
    assert dialogue.render(output, spec) and "需要留意" in dialogue.render(output, spec)
    prompt = 'Old frozen rules\n' + json.dumps({"dialogue":spec})
    assert assistant.dialogue_spec(prompt) == spec


def test_provider_urgent_warning_is_not_suppressed_by_online_preference(setup):
    output = json.dumps({"reply":"请停止动作测试，立即到急诊寻求帮助。", "questions":[], "advice":[], "next_step":"不要等待测量。"}, ensure_ascii=False)
    _, calls, (aid, _, alice, _, _) = configured(setup, lambda *_:provider_answer(output))
    result = post(alice, aid, body("帮我安排肩部评估"))
    assert listing(alice, aid) == []
    assert "急诊" in result["turn"]["answer"] and len(calls) == 1
    assert all(a["kind"] == "doctor_review" for a in result["turn"]["actions"])


def test_quota_failure_does_not_prematurely_create_an_appointment(setup):
    _, calls, (aid, _, alice, _, _) = configured(setup, monthly_calls=1)
    post(alice, aid, body("你好"))
    response = alice.post(path(aid, "/assistant/turns"), json=body("安排肩部评估"))
    assert response.status_code == 429 and len(calls) == 1
    assert listing(alice, aid) == []


@pytest.mark.parametrize("text", ["现在尿不出来是不是正常", "没有腿麻而且尿不出来", "没有腿麻，但大小便异常"])
def test_new_current_warning_overrides_old_negative_screen(text):
    history=[{"text":"腰痛三分，没有腿麻也没有大小便异常", "answer":"TEST"}]
    assert dialogue.protocol(text, "CHAT", history)["intake_stage"] == "URGENT"


@pytest.mark.parametrize("reply, expected", [
    ("请立刻到急诊", "URGENT"), ("请去急诊接受检查", "URGENT"),
    ("目前不需要立即急诊", None), ("如果以后出现胸痛，请立即急诊就医", None),
])
def test_model_escalation_handles_synonyms_negation_and_hypothetical(reply, expected):
    assert dialogue.model_escalation(json.dumps({"reply":reply})) == expected


@pytest.mark.parametrize("reply", ["你的肩部恢复率为百分之八十", "建议口服布洛芬", "可以把降压药加半粒"])
def test_v3_rejects_spelled_out_measurements_and_drug_orders(reply):
    answer=json.dumps({"reply":reply,"questions":[],"advice":[],"next_step":"查看已有记录。"})
    assert dialogue.render(answer,dialogue.protocol("肩部评估", "ASSESSMENT_GUIDANCE", [])) is None


def test_no_pain_and_thanks_do_not_restart_symptom_intake():
    spec=dialogue.protocol("我没有疼痛，安排左肩评估", "ASSESSMENT_GUIDANCE", [])
    assert spec["assessment_ready"] and not spec["missing_questions"]
    history=[{"text":"腰痛三分，没有腿麻也没有大小便异常", "answer":"TEST"}]
    assert not dialogue.protocol("谢谢", "CHAT", history)["assessment_ready"]


def test_persistent_warning_survives_new_turns_and_explicit_reported_review_is_audited(setup):
    aid, _, alice, _, _ = people(setup)
    post(alice, aid, body("肩痛并且胸痛"))
    for _ in range(7):post(alice, aid, body("谢谢"))
    result=post(alice, aid, body("安排肩部评估"))
    assert listing(alice, aid) == [] and "医疗核对" in result["turn"]["answer"]
    result=post(alice, aid, body("已去急诊看过医生，医生说可以恢复康复活动，请安排肩部线上评估"))
    assert len(listing(alice, aid)) == 1


def test_slow_old_answer_cannot_schedule_after_new_urgent_warning(setup):
    entered,release=threading.Event(),threading.Event()
    def dispatch(*args):
        entered.set();assert release.wait(10)
        return provider_answer()
    _, calls, (aid, _, alice, _, _) = configured(setup,dispatch)
    with ThreadPoolExecutor(2) as pool:
        slow=pool.submit(post,alice,aid,body("安排肩部评估"))
        try:
            assert entered.wait(10)
            post(alice, aid, body("现在肩痛并且胸痛"))
        finally:release.set()
        result=slow.result()
    assert listing(alice, aid) == [] and "不再安排动作测试" in result["turn"]["answer"]
    assert result["receipt"]["usage"]["total_tokens"] == 150 and len(calls) == 1


def test_new_region_drops_old_region_from_model_context_and_routing():
    history=[{"text":"左肩练中痛，练后加重伴无力", "answer":"TEST 肩部追问", "private":False}]
    prompt=assistant.frozen_prompt("硬拉后腰疼", "CHAT", {}, history, {"cards":[]})
    payload=json.loads(prompt.split('\n',1)[1])
    assert payload['recent_dialogue']==[] and payload['dialogue_excerpt']==''
    assert '肩部追问' not in prompt and payload['dialogue']['region']=='躯干'
