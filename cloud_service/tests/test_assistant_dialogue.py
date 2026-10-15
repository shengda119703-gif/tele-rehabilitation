"""Fictitious text and in-process providers only; no paid requests."""
import json

import pytest

from cloud_service import assistant, assistant_dialogue as dialogue
from cloud_service.ai_usage import receipts
from cloud_service.tests.test_assistant import setup, forbid_external_requests, configured, body, post, provider_answer, stored
from cloud_service.tests.test_workbench import path
from sqlalchemy import func, select


def output(**changes):
    return json.dumps({"reply":"先暂停会加重疼痛的训练，我先了解具体情况。",
                       "questions":[dialogue.SCALE_QUESTION, dialogue.SAFETY_QUESTION],
                       "advice":[],"next_step":"先补充必要信息，再安排线上评估。",**changes}, ensure_ascii=False)


def test_formatted_symptom_answer_has_real_questions_without_generic_preface(setup):
    _, calls, (aid, _, alice, _, _) = configured(setup, lambda *_: provider_answer(output()))
    result = post(alice, aid, body("我健身后腰疼"))
    answer = result["turn"]["answer"]
    assert result["source"] == "deepseek" and len(calls) == 1
    assert "先确认" in answer and dialogue.SCALE_QUESTION in answer and "需要留意" not in answer
    assert len(answer) < 500 and all(word not in answer for word in ("尚未允许", "肩部等", "一般解释（", "**", "```"))
    assert result["turn"]["actions"] == []
    payload = json.loads(calls[0].split("\n", 1)[1])
    assert payload["dialogue"]["mode"] == "SYMPTOM" and payload["authorized_context"] == {}
    assert result["turn"]["context_versions"]["dialogue_protocol"] == dialogue.VERSION
    assert result["receipt"]["usage"]["total_tokens"] == 150


def test_follow_up_uses_recent_answers_without_writing_a_medical_record(setup):
    _, calls, (aid, _, alice, _, _) = configured(setup, lambda *_: provider_answer(output()))
    post(alice, aid, body("我健身后腰疼"))
    second = post(alice, aid, body("硬拉后开始的，疼痛三分，没有腿麻，也没有大小便异常"))
    payload = json.loads(calls[-1].split("\n",1)[1])
    assert payload["dialogue"]["mode"] == "SYMPTOM"
    assert payload["recent_dialogue"][-1]["user"] == "我健身后腰疼"
    assert "0–10" in payload["recent_dialogue"][-1]["assistant"]
    assert "不重启一遍问卷" in calls[-1]
    assert payload['dialogue']['already_answered']['pain_score'] is True
    assert dialogue.SCALE_QUESTION not in second['turn']['answer']
    assert dialogue.SCALE_QUESTION not in payload['example_response']['questions']
    assert "先确认" not in second['turn']['answer']
    assert second['turn']['actions'][0]['kind'] == 'assessment_plan'


@pytest.mark.parametrize("text", ["腰痛，而且现在尿不出来", "腰疼，开始小便失禁", "背痛伴会阴麻木", "腰疼而且双腿明显无力"])
def test_positive_urgent_back_symptoms_skip_provider_and_do_not_offer_training(setup, text):
    _, calls, (aid, _, alice, _, _) = configured(setup)
    result = post(alice, aid, body(text))
    assert result["source"] == "local" and result["state"] == "LOCAL" and not calls
    assert "立即到急诊" in result["turn"]["answer"] and "receipt" not in result
    assert all(action["kind"] == "doctor_review" for action in result["turn"]["actions"])
    with setup[1].engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(receipts)) == 0


@pytest.mark.parametrize("text", ["腰疼，但没有尿失禁", "腰痛，没有腿麻，没有排尿困难", "腰痛如果出现尿失禁怎么办", "腰痛，尿失禁是什么意思", "腰痛，以前尿失禁，现在没有"])
def test_negative_or_hypothetical_text_does_not_assert_an_emergency(text):
    assert not dialogue.urgent_back_symptoms(text, [])


@pytest.mark.parametrize("bad", [
    output(reply="你已确诊腰椎间盘突出"), output(reply="已恢复到180度"), output(advice=["请服用一片药"]),
    output(next_step="请访问 https://untrusted.invalid"), output(questions=["请发验证码给我"] , extra="unexpected"),
    output(advice=["继续做负重训练就可以"]), output(reply="**先继续训练**"), "```json\n{}\n```", "不按格式的很长回复"*300,
])
def test_invalid_or_unsafe_model_reply_uses_short_local_fallback_without_retry(setup, bad):
    _, calls, (aid, _, alice, _, _) = configured(setup, lambda *_: provider_answer(bad))
    result = post(alice, aid, body("我健身后腰疼"))
    assert result["source"] == "local" and len(calls) == 1
    assert "先确认" in result["turn"]["answer"] and len(result["turn"]["answer"]) < 500
    assert result["receipt"]["state"] == "SUCCEEDED" and result["receipt"]["usage"]["total_tokens"] == 150
    assert post(alice, aid, {"operation_id":result["turn"]["operation_id"],"text":"我健身后腰疼"}) == result
    assert len(calls) == 1


def test_later_action_question_is_not_forced_into_a_symptom_intake():
    history = [{"text":"之前腰疼", "answer":"TEST"}]
    assert dialogue.mode_for("肩外旋怎么做", "CHAT", history) == "ACTION"
    assert dialogue.mode_for("今天练什么", "CHAT", []) == "PLAN"


@pytest.mark.parametrize('text,answered', [('疼痛三分', True), ('疼痛3分', True), ('痛了三分钟', False), ('三分', True), ('疼痛大约十分', True)])
def test_reported_score_is_dialogue_only_and_not_confused_with_minutes(text, answered):
    assert dialogue.protocol(text,'CHAT',[{'text':'我腰痛','answer':'TEST'}])['already_answered']['pain_score'] is answered


def test_worsening_symptoms_allow_rechecking_a_previous_score():
    spec=dialogue.protocol('腰痛比之前加重了','CHAT',[{'text':'疼痛三分','answer':'TEST'}])
    assert spec['already_answered']['pain_score'] is False


def test_freeze_keeps_whole_conditions_and_bounds_history():
    history = [{"text":"TEST"*100, "answer":"TEST"*1000, "private":False} for _ in range(6)]
    prompt = assistant.frozen_prompt("TEST"*475, "CHAT", {}, history, {"cards":[]})
    assert len(prompt) <= assistant.PROMPT_LIMIT
    assert json.loads(prompt.split("\n",1)[1])["dialogue"]["version"] == dialogue.VERSION


def test_old_frozen_prompts_are_not_rewritten_or_forced_into_new_json():
    old = 'Legacy instruction\n{"question":"TEST original"}'
    assert assistant.dialogue_spec(old) is None
    assert assistant.safe_explanation("请先在原页面核对安排")


def test_provider_uses_official_json_mode_only_for_server_protocol(monkeypatch):
    from cloud_service.ai_usage import provider, AIConfig
    observed = []
    class Reply:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self, _): return json.dumps(provider_answer(output())).encode()
    class Opener:
        def open(self, request, **kwargs):
            observed.append(json.loads(request.data))
            return Reply()
    monkeypatch.setattr('cloud_service.ai_usage.build_opener', lambda *_: Opener())
    provider(AIConfig(key='TEST-NOT-A-KEY'), assistant.frozen_prompt('TEST 腰疼', 'CHAT', {}, [], {'cards':[]}))
    assert observed[-1]['response_format'] == {'type':'json_object'}
    assert observed[-1]['temperature'] == 0.4 and observed[-1]['thinking'] == {'type':'disabled'}
    provider(AIConfig(key='TEST-NOT-A-KEY'), 'TEST ordinary direct question')
    assert 'response_format' not in observed[-1]
