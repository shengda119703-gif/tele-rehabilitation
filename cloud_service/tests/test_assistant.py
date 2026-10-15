"""Fictional accounts/records/providers only. Every external URL open is blocked."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import threading
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update

from cloud_service import assistant
from cloud_service.app import BASE, create_app
from cloud_service.ai_usage import AIConfig, receipts, request_labels
from cloud_service.config import Settings
from cloud_service.database import Database, records
from cloud_service.rehab_workflow import candidates, resources
from cloud_service.security import bootstrap_doctor
from cloud_service.tests.test_accounts import client, login
from cloud_service.tests.test_workbench import people, path, publish, adoption


@pytest.fixture
def setup(tmp_path):
    settings = Settings("sqlite:///"+str(tmp_path/"assistant.sqlite3"),"x"*40,("http://testserver",),"test")
    db = Database(settings.database_url)
    db.migrate()
    bootstrap_doctor(db,settings,"1")
    assets = tmp_path/"isolated-no-public-assets"
    app = create_app(settings,db,web_assets=assets)
    app.state.assistant_test_assets = assets
    yield app, db, settings
    db.engine.dispose()


@pytest.fixture(autouse=True)
def forbid_external_requests(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("TEST forbids external provider/network requests")
    monkeypatch.setattr("urllib.request.OpenerDirector.open", forbidden)


def provider_answer(text=None):
    if text is None:
        text = json.dumps({"reply":"我可以结合已有资料帮你梳理。", "questions":["你现在最想了解哪个部位？"], "advice":[], "next_step":"说说你想先解决的问题。"}, ensure_ascii=False)
    return {"id":"TEST-provider-receipt","choices":[{"message":{"content":text}}],
            "usage":{"prompt_tokens":100,"completion_tokens":50,"total_tokens":150,
                     "prompt_cache_hit_tokens":20,"prompt_cache_miss_tokens":80}}


def configured(setup, dispatch=None, **options):
    calls = []
    def fake_provider(config, prompt):
        calls.append(prompt)
        return dispatch(config,prompt) if dispatch else provider_answer()
    app = create_app(setup[2],setup[1],web_assets=setup[0].state.assistant_test_assets,
                     ai_config=AIConfig(key="TEST-FICTIONAL-KEY-ONLY",**options),ai_dispatch=fake_provider)
    return app, calls, people((app,*setup[1:]))


def body(text="今天练什么", **options):
    return {"operation_id":str(uuid4()),"text":text,**options}


def post(alice, ident, value=None):
    response = alice.post(path(ident,"/assistant/turns"),json=value or body())
    assert response.is_success, response.text
    return response.json()


def enable(alice, ident, enabled=True, expected=0):
    response = alice.put(path(ident,"/assistant/preferences"),json={"expected_version":expected,"health_context":enabled})
    assert response.is_success, response.text
    return response.json()


def upload(alice, ident, kind="assessment", exercise="shoulder_abduction", side="left", revision=1, key=None, **extra):
    payload = {"schema":"ankang-workbench-record-1","source":"DESKTOP_LOCAL","patient_id":ident,"kind":kind,
               "record_key":key or f"TEST-{kind}-{exercise}-{side}","revision":revision,"owner_id":"TEST-local-owner",
               "captured_at":"2026-10-15T00:00:00Z","title":"TEST isolated record, no real person",
               "result":{"exercise_id":exercise,"side":side,"summary":{"motion_range":{"max_deg":0}},
                         "training_feedback":{"pain":0,"fatigue":None}},**extra}
    response = alice.post(path(ident,"/record-events"),json={"operation_id":str(uuid4()),"source_event_id":str(uuid4()),
                          "installation_id":"TEST-device","source_kind":"DESKTOP_LOCAL","payload":payload})
    assert response.is_success, response.text
    return payload


def goal(alice, ident, version=0, text="TEST 本人肩部目标"):
    response = alice.put(path(ident,"/rehab-workflow/profile"),json={"expected_version":version,"goal":text,"region":"肩",
                        "level":0,"equipment":["稳固椅"],"restrictions":[],"screening_confirmed":True})
    assert response.is_success, response.text


def stored(db, operation):
    with db.engine.connect() as connection:
        return dict(connection.execute(select(assistant.turns).where(assistant.turns.c.operation_id == operation)).mappings().one())


def test_preferences_default_owner_only_version_and_csrf(setup):
    aid, _, alice, bob, doctor = people(setup)
    url = path(aid,"/assistant/preferences")
    assert alice.get(url).json() == {"version":0,"health_context":False}
    assert client(setup[0]).get(url).status_code == 401
    assert bob.get(url).status_code == 404
    assert doctor.get(url).status_code == 404  # A care grant never exposes private assistant dialogue.
    assert alice.put(url,json={"expected_version":0,"health_context":True},headers={"X-CSRF-Token":"wrong"}).status_code == 403
    assert enable(alice,aid) == {"version":1,"health_context":True}
    assert alice.put(url,json={"expected_version":0,"health_context":False}).status_code == 412
    assert enable(alice,aid,False,1) == {"version":2,"health_context":False}


@pytest.mark.parametrize("invalid",[
    {"text":""},{"text":"   "},{"text":"x"*1901},{"operation_id":"not-a-uuid"},
    {"purpose":"ARBITRARY"},{"private":"true"},{"unexpected":"value"},
])
def test_strict_turn_validation(setup, invalid):
    aid, _, alice, _, _ = people(setup)
    assert alice.post(path(aid,"/assistant/turns"),json={**body(),**invalid}).status_code == 422


def test_no_key_local_turn_persists_original_text_and_stable_replay_without_receipt(setup):
    aid, _, alice, bob, doctor = people(setup)
    value = body("  今天练什么  ")
    first = post(alice,aid,value)
    assert first["state"] == "LOCAL" and first["source"] == "local" and "receipt" not in first
    assert first["turn"]["receipt_id"] is None and first["turn"]["text"] == value["text"]
    assert first["turn"]["sequence"] == 1 and first["summary"]["kind"] == "DIALOGUE_EXCERPT"
    assert first["summary"]["version"] == 1 and "不是临床事实" in first["summary"]["text"]
    assert post(alice,aid,value) == first
    for change in ({"text":"different"},{"private":True},{"purpose":"CANDIDATE_PLAN"}):
        assert alice.post(path(aid,"/assistant/turns"),json={**value,**change}).status_code == 409
    for outsider in (bob,doctor):
        assert outsider.get(path(aid,"/assistant/conversation")).status_code == 404
        assert outsider.post(path(aid,"/assistant/turns"),json=body()).status_code == 404
    with setup[1].engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(receipts)) == 0


def test_no_consent_never_reads_health_context_but_gateway_is_server_side(setup, monkeypatch):
    _, calls, (aid, _, alice, _, _) = configured(setup)
    def forbidden(*args):
        raise AssertionError("Private health context read without consent")
    monkeypatch.setattr(assistant,"health_context",forbidden)
    result = post(alice,aid,body("肩膀恢复"))
    assert result["source"] == "deepseek" and len(calls) == 1
    assert '"authorized_context":{}' in calls[0]
    assert result["turn"]["purpose"] == "RESULT_EXPLANATION"
    assert result["receipt"]["operation_id"] == result["turn"]["operation_id"]
    assert "answer" not in result["receipt"]


def test_no_key_real_data_plan_zero_and_feedback_without_automatic_writes(setup):
    aid, _, alice, _, doctor = people(setup)
    goal(alice,aid); upload(alice,aid); upload(alice,aid,"training")
    plan = publish(doctor,aid)
    assert alice.post(path(aid,"/plans/"+plan["id"]+"/accept"),json=adoption(plan)).is_success
    enable(alice,aid)
    first = post(alice,aid,body("今天练什么，肩膀恢复情况"))
    answer = first["turn"]["answer"]
    assert first["state"] == "LOCAL" and "TEST 本人肩部目标" in answer
    assert "2次 × 1组" in answer and "0度" in answer and "疼痛0" in answer and "疲劳未记录" in answer
    assert "仍须" in answer and "新训练处方" in answer
    versions = first["turn"]["context_versions"]
    assert versions["current_plan"]["id"] == plan["id"] and versions["workflow_profile"] == 1
    with setup[1].engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(candidates)) == 0
        assert connection.scalar(select(func.count()).select_from(records)) == 2


def test_matching_shoulder_records_both_sides_exclude_synthetic_other_patients_and_knees(setup):
    _, calls, (aid, bid, alice, bob, _) = configured(setup)
    upload(alice,aid,side="left"); upload(alice,aid,side="right")
    upload(alice,aid,exercise="knee_extension"); upload(alice,aid,exercise="knee_flexion")
    upload(alice,aid,synthetic=True,key="TEST-synthetic")
    upload(bob,bid,result={"exercise_id":"shoulder_abduction","conditions":["TEST-OTHER-PATIENT-SECRET"]})
    upload(alice,aid,"profile",result={"conditions":["TEST-OWN-CONDITION"],"family":{"conditions":"TEST-FAMILY-SECRET"},"key":"TEST-KEY-SECRET"})
    enable(alice,aid)
    result = post(alice,aid,body("肩膀恢复"))
    prompt = json.loads(calls[0].split("\n",1)[1])
    evidence = prompt["authorized_context"]["records"]
    assessments = [r for r in evidence if r["kind"] == "assessment"]
    assert {r["facts"]["side"] for r in assessments} == {"left","right"}
    assert all(r["facts"]["exercise_id"] == "shoulder_abduction" for r in assessments)
    assert "TEST-OWN-CONDITION" in calls[0]
    assert all(secret not in calls[0] for secret in ("TEST-OTHER-PATIENT-SECRET","TEST-FAMILY-SECRET","TEST-KEY-SECRET","knee_extension","knee_flexion"))
    assert len(result["turn"]["context_versions"]["records"]) == len(evidence)


def test_new_operations_refresh_versions_retry_keeps_frozen_prompt_and_receipt(setup):
    _, calls, (aid, _, alice, _, _) = configured(setup)
    goal(alice,aid); upload(alice,aid); enable(alice,aid)
    value = body("肩膀恢复")
    first = post(alice,aid,value)
    original = stored(setup[1],value["operation_id"])["prompt"]
    goal(alice,aid,1,"TEST 新目标"); upload(alice,aid,revision=2)
    assert post(alice,aid,value) == first and len(calls) == 1
    second = post(alice,aid,body("肩膀恢复"))
    assert len(calls) == 2 and calls[0] == original and calls[1] != original
    assert second["turn"]["context_versions"]["workflow_profile"] == 2
    assert second["turn"]["context_versions"]["snapshot"] != first["turn"]["context_versions"]["snapshot"]


def test_pending_quota_retry_uses_once_frozen_context_and_original_operation(setup):
    app, calls, (aid, _, alice, _, _) = configured(setup,monthly_calls=1)
    enable(alice,aid); goal(alice,aid)
    post(alice,aid,body("先问一个问题"))
    value = body("肩膀恢复")
    assert alice.post(path(aid,"/assistant/turns"),json=value).status_code == 429
    frozen = stored(setup[1],value["operation_id"])
    goal(alice,aid,1,"TEST LATER GOAL NOT IN RETRY")
    app.state.text_ai_settings.fallback = replace(app.state.text_ai_settings.fallback,monthly_calls=5)
    result = post(alice,aid,value)
    assert result["turn"]["id"] == frozen["id"] and calls[-1] == frozen["prompt"]
    assert "TEST LATER GOAL NOT IN RETRY" not in calls[-1]
    assert result["receipt"]["operation_id"] == value["operation_id"]


def test_consent_revocation_blocks_unsent_frozen_health_prompt(setup):
    _, calls, (aid, _, alice, _, _) = configured(setup,monthly_calls=1)
    enable(alice,aid)
    post(alice,aid)
    value = body("肩膀恢复")
    assert alice.post(path(aid,"/assistant/turns"),json=value).status_code == 429
    enable(alice,aid,False,1)
    response = alice.post(path(aid,"/assistant/turns"),json=value)
    assert response.status_code == 409 and response.json()["code"] == "ASSISTANT_CONTEXT_CHANGED"
    assert len(calls) == 1


def test_unknown_provider_receipt_never_redispatches_or_claims_free(setup):
    def timeout(*args):
        raise TimeoutError("TEST no real request")
    _, calls, (aid, _, alice, _, _) = configured(setup,timeout)
    value = body(); first = post(alice,aid,value)
    assert first["state"] == "UNKNOWN" and first["receipt"]["state"] == "UNKNOWN"
    assert "不自动重发或视为免费" in first["turn"]["answer"]
    assert post(alice,aid,value) == first and len(calls) == 1


def test_private_local_only_is_saved_but_never_forwarded_or_summarized(setup):
    _, calls, (aid, _, alice, _, _) = configured(setup)
    enable(alice,aid)
    secret = "TEST-PRIVATE-DIALOGUE"
    result = post(alice,aid,body(secret,private=True))
    assert result["state"] == "LOCAL" and not calls and not result["health_context_enabled"]
    assert result["turn"]["text"] == secret and secret not in result["summary"]["text"]
    post(alice,aid,body("继续一般说明"))
    assert secret not in calls[-1]
    assert alice.get(path(aid,"/assistant/conversation")).json()["items"][0]["text"] == secret


@pytest.mark.parametrize("unsafe",["已恢复到180度","你已确诊肩周炎","请服用一片药","请访问 https://untrusted.invalid/path"])
def test_provider_cannot_create_measurements_diagnoses_medication_or_url_actions(setup, unsafe):
    _, _, (aid, _, alice, _, _) = configured(setup,lambda *_:provider_answer(unsafe))
    result = post(alice,aid,body("肩膀恢复"))
    assert result["source"] == "local" and result["receipt"]["state"] == "SUCCEEDED"
    assert unsafe not in result["turn"]["answer"] and "answer" not in result["receipt"]
    assert all(a["kind"] in {"assessment","plan","candidate","doctor_review"} and "url" not in a for a in result["turn"]["actions"])
    with setup[1].engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(records)) == 0
        assert connection.scalar(select(func.count()).select_from(candidates)) == 0


def test_candidates_are_confirmation_only_and_purpose_uses_same_gateway_usage(setup):
    _, calls, (aid, _, alice, _, _) = configured(setup)
    result = post(alice,aid,body("请生成起始候选"))
    candidate = next(a for a in result["turn"]["actions"] if a["kind"] == "candidate")
    assert candidate == {"kind":"candidate","candidate_kind":"STARTER","label":"提交候选供医师核对","requires_confirmation":True}
    assert result["turn"]["purpose"] == "CANDIDATE_PLAN" and len(calls) == 1
    with setup[1].engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(candidates)) == 0
        assert connection.scalar(select(request_labels.c.purpose)) == "CANDIDATE_PLAN"
    usage = alice.get(path(aid,"/ai/usage")).json()
    assert usage["usage"]["calls"] == 1 and usage["usage"]["total_tokens"] == 150


def test_guideline_no_key_no_health_consent_full_conditions_sources_and_steps(setup):
    aid, _, alice, _, _ = people(setup)
    result = post(alice,aid,body("肩外旋怎么做"))
    answer = result["turn"]["answer"]
    refs = result["turn"]["context_versions"]["guidelines"]["cards"]
    assert result["state"] == "LOCAL" and not result["health_context_enabled"] and refs
    library = {c["id"]:c for c in resources()["cards"]}
    for ref in refs:
        card = library[ref["id"]]
        assert card["version"] == ref["version"] and card["sourceRefs"] == ref["sourceRefs"]
        assert card["stopConditions"] in answer and card["startConditions"] in answer and card["sourceDose"] in answer
    assert "操作步骤" in answer and "来源引用" in answer and "不从资料卡自动启动" in answer
    assert "尚未允许助手读取" not in answer


def test_guidelines_and_max_length_question_stay_bounded_and_model_cannot_override_versions(setup):
    _, calls, (aid, _, alice, _, _) = configured(setup)
    text = "肩外旋怎么做 " + "资料问题"*400
    result = post(alice,aid,body(text[:1900]))
    assert len(calls[0]) <= 12000
    payload = json.loads(calls[0].split("\n",1)[1])
    assert payload["guideline_context"]["cards"] and payload["authorized_context"] == {}
    for card in payload["guideline_context"]["cards"]:
        assert card["stopConditions"] and card["version"]
    assert result["turn"]["context_versions"]["guidelines"]["schema"] == resources()["schema"]


def test_gateway_operation_collision_is_not_replaced_or_billed_twice(setup):
    _, calls, (aid, _, alice, _, _) = configured(setup)
    value = body("同一操作")
    assert alice.post(path(aid,"/ai/requests"),json=value).is_success
    assert alice.post(path(aid,"/assistant/turns"),json=value).status_code == 409
    assert len(calls) == 1


def test_conversation_cross_device_chronology_and_bounded_deterministic_memory(setup):
    aid, _, alice, _, _ = people(setup)
    first = post(alice,aid,body("TEST-first"))
    for i in range(8):
        post(alice,aid,body(("TEST-question-"+str(i)+"x"*1850)[:1900]))
    another = client(setup[0]); assert login(another,"test-alice").is_success
    result = another.get(path(aid,"/assistant/conversation?after=0&limit=3")).json()
    assert [t["sequence"] for t in result["items"]] == [1,2,3]
    assert result["has_more"] and result["next_after"] == 3 and result["latest_sequence"] == 9
    assert result["summary"]["kind"] == "DIALOGUE_EXCERPT" and len(result["summary"]["text"]) <= 1800
    assert "TEST-first" not in result["summary"]["text"] and result["summary"]["through_sequence"] == 9
    assert all("prompt" not in t and "local_answer" not in t and "fingerprint" not in t for t in result["items"])
    assert another.get(path(aid,"/assistant/conversation?after=3&limit=3")).json()["items"][0]["sequence"] == 4
    assert first["summary"]["version"] < result["summary"]["version"]
    assert another.get(path(aid,"/assistant/conversation?after=-1")).status_code == 422


def test_concurrent_same_operation_uses_one_provider_receipt_and_no_deadlock(setup):
    entered, release = threading.Event(), threading.Event()
    def slow(*args):
        entered.set(); assert release.wait(10)
        return provider_answer()
    _, calls, (aid, _, alice, _, _) = configured(setup,slow)
    value = body("TEST concurrent")
    with ThreadPoolExecutor(max_workers=2) as executor:
        pending = executor.submit(alice.post,path(aid,"/assistant/turns"),json=value)
        try:
            assert entered.wait(10)
            running = post(alice,aid,value)
            assert running["state"] == "RUNNING" and running["turn"]["answer"] is None
        finally:
            release.set()
        final = pending.result(timeout=15)
    assert final.is_success, final.text
    replay = post(alice,aid,value)
    assert replay == final.json() and len(calls) == 1
    assert replay["turn"]["receipt_id"] == running["turn"]["receipt_id"]


def test_large_chinese_history_stays_below_native_transport_limit(setup):
    aid, _, alice, _, _ = people(setup)
    post(alice, aid, body('TEST long history'))
    with setup[1].transaction() as connection:
        original = dict(connection.execute(select(assistant.turns)).mappings().one())
        connection.execute(update(assistant.turns).values(answer='中'*8000))
        for sequence in range(2, 31):
            connection.execute(assistant.turns.insert().values(**{**original,'id':str(uuid4()),'operation_id':str(uuid4()),'sequence':sequence,'answer':'中'*8000}))
    seen, after = [], 0
    while True:
        response=alice.get(path(aid,f'/assistant/conversation?after={after}&limit=30'))
        assert response.is_success and len(response.content)<512*1024
        result=response.json();seen.extend(row['id'] for row in result['items'])
        if not result['has_more']:break
        assert result['next_after']>after
        after=result['next_after']
    assert len(seen)==len(set(seen))==30
