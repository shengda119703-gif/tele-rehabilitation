"""Owner-only, server-saved assistant dialogue; never a clinical record writer.

Import registers additive tables on database.metadata. The application owns
migration/installation and supplies its exact metered dispatch_text_ai gateway.
private=True means cloud-saved/local-only, not an unsaved or incognito turn.
"""
import json
import math
import re
import time
from typing import Literal
from uuid import UUID, uuid4

from fastapi import Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    Boolean, CheckConstraint, Column, ForeignKey, Integer, JSON, String, Table,
    Text, UniqueConstraint, func, select, update,
)

from .ai_usage import TextRequest
from .database import metadata, patients
from .real_data import synthetic
from .rehab_workflow import resources, workflow
from .security import DomainError, audited, digest
from .workbench import action_library, latest_records
from . import assistant_dialogue as dialogue
from . import assistant_assessments

Purpose = Literal["CHAT", "RESULT_EXPLANATION", "CANDIDATE_PLAN", "ASSESSMENT_GUIDANCE", "REASSESSMENT"]
PROMPT_LIMIT = 12000
CONTEXT_LIMIT = 3600
GUIDELINE_LIMIT = 3200
SUMMARY_LIMIT = 1800

preferences = Table("assistant_preferences", metadata,
    Column("patient_id", String(36), ForeignKey("patients.id"), primary_key=True),
    Column("version", Integer, nullable=False),
    Column("allow_health_context", Boolean, nullable=False),
    CheckConstraint("version >= 1"))
memory = Table("assistant_memory", metadata,
    Column("patient_id", String(36), ForeignKey("patients.id"), primary_key=True),
    Column("document", JSON, nullable=False))
turns = Table("assistant_turns", metadata,
    Column("id", String(36), primary_key=True),
    Column("patient_id", String(36), ForeignKey("patients.id"), nullable=False, index=True),
    Column("actor_id", String(36), ForeignKey("accounts.id"), nullable=False),
    Column("operation_id", String(36), nullable=False),
    Column("sequence", Integer, nullable=False),
    Column("fingerprint", String(64), nullable=False),
    Column("text", Text, nullable=False),
    Column("purpose", String(40), nullable=False),
    Column("private", Boolean, nullable=False),
    Column("health_context_enabled", Boolean, nullable=False),
    Column("context_versions", JSON, nullable=False),
    Column("prompt", Text, nullable=False),
    Column("local_answer", Text, nullable=False),
    Column("answer", Text),
    Column("actions", JSON, nullable=False),
    Column("state", String(20), nullable=False),
    Column("source", String(12), nullable=False),
    Column("receipt_id", String(36)),
    Column("receipt", JSON),
    Column("summary", JSON, nullable=False),
    Column("created_at", Integer, nullable=False),
    Column("completed_at", Integer),
    UniqueConstraint("actor_id", "operation_id"),
    UniqueConstraint("patient_id", "sequence"),
    CheckConstraint("sequence >= 1"),
    CheckConstraint("state IN ('PENDING','LOCAL','RUNNING','SUCCEEDED','UNMETERED','UNKNOWN')"))


class PreferencesInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_version: int = Field(ge=0, le=2147483646)
    health_context: bool


class TurnInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    operation_id: UUID = Field(strict=False)
    text: str = Field(min_length=1, max_length=1900)
    private: bool = False
    purpose: Purpose | None = None
    assessment_contract: Literal["ordered-video-1"] | None = None


def compact(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def excerpt(text, limit=160):
    return " ".join(str(text or "").split())[:limit]


def preference_document(connection, ident):
    row = connection.execute(select(preferences).where(preferences.c.patient_id == ident)).mappings().first()
    return {"version": row["version"], "health_context": row["allow_health_context"]} if row else {"version": 0, "health_context": False}


def empty_summary():
    return {"kind": "DIALOGUE_EXCERPT", "version": 0, "text": "", "through_sequence": 0}


def saved_summary(connection, ident):
    return connection.scalar(select(memory.c.document).where(memory.c.patient_id == ident)) or empty_summary()


def safety_hold(connection, ident, level, turn_id=None):
    doc = dict(saved_summary(connection, ident))
    doc["version"] += 1
    if level:
        doc["safety_hold"] = {"level":level, "turn_id":turn_id, "created_at":int(time.time())}
        assistant_assessments.pause_pending(connection, ident)
    else:
        doc.pop("safety_hold", None)
    if connection.scalar(select(memory.c.patient_id).where(memory.c.patient_id == ident)):
        connection.execute(update(memory).where(memory.c.patient_id == ident).values(document=doc))
    else:
        connection.execute(memory.insert().values(patient_id=ident,document=doc))


def block_for_hold(spec):
    spec.update(assessment_ready=False, intake_stage="ONLINE_REVIEW", missing_questions=[], max_questions=0, safety_hold=True,
                workflow_next_step="先完成之前危险症状的医疗核对；当前仍有这些症状请立即急诊，不先做动作测试。")


def dialogue_excerpt(rows):
    lines = [f"本人说：{excerpt(r['text'],120)}；助手答：{excerpt(r['answer'],120)}" for r in rows if r["answer"] and not r["private"]]
    return ("对话摘录（仅为对话原文节选，不是临床事实）：\n" + "\n".join(lines))[:SUMMARY_LIMIT] if lines else ""


# Explicit keys prevent accidentally including family profiles, reports, chat,
# attachments, provider secrets, or identifiers from arbitrary uploaded objects.
FACT_FIELDS = frozenset({
    "age", "conditions", "mobility", "usesCane", "rehabGoal", "currentState",
    "goal", "region", "equipment", "restrictions", "cautions", "profile",
    "exercise_id", "side", "status", "source_kind", "start_utc", "end_utc",
    "summary", "completed", "valid_ratio", "observed_span_s", "motion_range",
    "max_deg", "min_deg", "range_deg", "metrics", "label", "value", "max", "min", "unit", "valid",
    "feedback", "training_feedback", "pain", "fatigue", "plan_completed", "reason",
})


def selected_facts(value, depth=0):
    if depth > 5:
        return None
    if isinstance(value, dict):
        if synthetic(value) or value.get("dataMode") in {"demo", "synthetic"}:
            return None
        result = {}
        for key in sorted(value.keys() & FACT_FIELDS):
            part = selected_facts(value[key], depth + 1)
            candidate = {**result, key: part}
            if len(compact(candidate)) <= 1500:
                result = candidate
        return result
    if isinstance(value, list):
        return [selected_facts(item, depth + 1) for item in value[:4]]
    if isinstance(value, str):
        return excerpt(value, 160)
    if value is None or type(value) in {int, bool} or isinstance(value, float) and math.isfinite(value):
        return value
    return None


def health_context(connection, ident, question=""):
    """Read only latest, real client-declared records and the adopted workflow.

    The caller must authorize the owner and check opt-in before entering here.
    Every new operation rebuilds this snapshot; retries use the stored prompt.
    """
    state = workflow(connection, ident)
    profile = state["profile"] if state["profile"] and not synthetic(state["profile"]) else None
    context = {"kind": "AUTHORIZED_CLIENT_DECLARED_RECORDS", "workflow_profile_version": state["profile_version"],
               "workflow": selected_facts(profile) if profile else None, "records": [], "current_plan": None}
    plan = state["current_plan"]
    if plan and not synthetic(plan):
        context["current_plan"] = {
            "id": plan["id"], "version": plan["version"], "title": excerpt(plan["title"],80),
            "execution_status": plan.get("execution_status", "REQUIRES_LOCAL_VALIDATION"),
            "execution_date": plan.get("execution_date"), "phase_name": excerpt(plan.get("phase_name"),80),
            "items": [{"exercise_id": item["exercise_id"], "side": item["side"],
                       "settings": {k: item.get("settings",{}).get(k) for k in ("target_reps", "target_sets", "rest_between_sets_s", "target_angle_deg")},
                       "caution": excerpt(item.get("caution"),120)} for item in plan["items"][:4]],
        }
    library = action_library()
    region = dialogue.region_for(question)
    explicit = {key for key in library if key in question}
    relevant = explicit or {key for key,card in library.items() if region and region in card["name"]}
    context["requested_scope"] = {"region":region,"exercise_ids":sorted(relevant)}
    records = [record for record in latest_records(connection, ident)
               if not synthetic(record["payload"]) and record["payload"].get("patient_id") == ident
               and record["payload"].get("schema") == "ankang-workbench-record-1"]
    if relevant:
        first, later, seen = [], [], set()
        for record in records:
            payload = record["payload"]
            facts = payload.get("result")
            if payload.get("kind") == "profile":
                later.append(record)
            elif isinstance(facts,dict) and isinstance(facts.get("exercise_id"),str) and facts["exercise_id"] in relevant:
                side_value = facts.get("side") if facts.get("side") in ("left","right","bilateral") else None
                side = (payload.get("kind"),side_value)
                (later if side in seen else first).append(record)
                seen.add(side)
        records = first + later
    counts = {}
    for record in records:
        payload = record["payload"]
        kind = payload.get("kind")
        if (synthetic(payload) or payload.get("patient_id") != ident or kind not in {"profile", "assessment", "training"}
                or counts.get(kind,0) >= 2 or payload.get("schema") != "ankang-workbench-record-1"):
            continue
        item = {"id": record["id"], "kind": kind, "revision": payload.get("revision"),
                "captured_at": excerpt(payload.get("captured_at"),50), "source": record["source_kind"],
                "facts": selected_facts(payload.get("result"))}
        candidate = {**context, "records": context["records"] + [item]}
        if len(compact(candidate)) <= CONTEXT_LIMIT:
            context = candidate
            counts[kind] = counts.get(kind,0) + 1
    # These are provenance references, not new thresholds, diagnoses or rules.
    versions = {"workflow_profile": state["profile_version"],
                "records": [{"id": r["id"], "revision": r["revision"]} for r in context["records"]],
                "current_plan": {k: context["current_plan"][k] for k in ("id","version","execution_status","execution_date")} if context["current_plan"] else None,
                "snapshot": digest(compact(context))}
    return context, versions


def purpose_for(text):
    if any(word in text for word in ("重新评估", "复测", "再评估", "reassessment")):
        return "REASSESSMENT"
    if any(word in text for word in ("候选", "制定计划", "康复方案", "康复计划", "生成方案", "康复安排", "调整计划", "进阶", "candidate")):
        return "CANDIDATE_PLAN"
    if any(word in text for word in ("评估", "怎么测", "assessment")):
        return "ASSESSMENT_GUIDANCE"
    if any(word in text for word in ("结果", "恢复", "result")):
        return "RESULT_EXPLANATION"
    return "CHAT"


def guideline_context(text):
    """Public server-owned cards need no consent to read private health facts.

    Keep complete selected fields, especially start/stop conditions. If a whole
    card does not fit, omit it instead of truncating a safety condition.
    """
    library = resources()
    instructional = any(word in text.lower() for word in ("怎么做","怎么练","动作","步骤","注意","指南","方法","how"))
    ranked = []
    for card in library["cards"]:
        name = card["name"]
        exact = card["id"] in text or name in text
        if not exact and not instructional:
            continue
        overlap = max((size for size in range(2,min(len(name),12)+1)
                       if any(name[i:i+size] in text for i in range(len(name)-size+1))),default=0)
        if exact or overlap >= 3:
            ranked.append((100 if exact else overlap,card))
    result = {"schema":library["schema"],"source":library["source"],"cards":[]}
    for _,card in sorted(ranked,key=lambda item:(-item[0],item[1]["id"])):
        if not card.get("complete"):
            continue
        selected = {key:card[key] for key in ("id","name","version","sourceRefs","startConditions","sourceDose","stopConditions","equipment")}
        sections = re.findall(r"\*\*(准备与起始位[：:]?|操作步骤)\*\*(.*?)(?=\n\*\*|\Z)",card["content"],re.S)
        selected["instructions"] = "\n".join(name + body for name,body in sections).strip()
        if len(compact({**result,"cards":result["cards"]+[selected]})) <= GUIDELINE_LIMIT:
            result["cards"].append(selected)
        if len(result["cards"]) == 2:
            break
    ids = {card["id"] for card in result["cards"]}
    versions = {"schema":library["schema"],"source":library["source"],
                "cards":[{key:card[key] for key in ("id","version","sourceRefs")} for card in result["cards"]],
                "rule_refs":[{"card_id":rule["id"],"digest":digest(compact(rule))} for rule in library["rules"] if rule["id"] in ids]}
    return result, versions


def guideline_explanation(guidelines):
    lines = []
    for card in guidelines["cards"]:
        lines.extend(["动作资料："+card["name"]+"（"+card["id"]+"，版本 "+card["version"]+"）",
                      "以下是现有资料卡原文节选，不是为本人新增或启用的训练安排。",
                      "器材："+card["equipment"],"开始条件："+card["startConditions"],
                      card["instructions"],"原资料试做／候选剂量（须按本人计划核对）："+card["sourceDose"],
                      "停止或调整条件："+card["stopConditions"],"来源引用："+"、".join(card["sourceRefs"]),
                      "资料库："+guidelines["source"]+"；可执行动作仍须在原页面核验是否有映射，不从资料卡自动启动。"])
    return "\n".join(lines)


def suggested_actions(text, purpose, context):
    region = next((r for r in ("肩", "肘", "腕", "髋", "膝", "踝", "颈", "躯干") if r in text), None)
    region = region or (context.get("workflow") or {}).get("region")
    library = action_library()
    matches = sorted((v for v in library.values() if region and region in v["name"] and not v["experimental"]), key=lambda v:v["exercise_id"])
    # Keep the established shoulder assessment stable across devices.
    exercise = "shoulder_abduction" if region == "肩" and "shoulder_abduction" in library else matches[0]["exercise_id"] if matches else None
    actions = []
    if exercise:
        actions.append({"kind": "assessment", "exercise_id": exercise, "label": "重新评估" if purpose == "REASSESSMENT" else "查看本人评估"})
    actions.append({"kind": "plan", "label": "查看训练安排"})
    if purpose == "CANDIDATE_PLAN":
        progression = bool(context.get("current_plan")) and "进阶" in text
        actions.append({"kind": "candidate", "candidate_kind": "PROGRESSION" if progression else "STARTER",
                        "label": "提交候选供医师核对", "requires_confirmation": True})
    actions.append({"kind": "doctor_review", "label": "联系康复医师核对"})
    return actions


def local_explanation(text, context, enabled, guidelines):
    guide = guideline_explanation(guidelines)
    if guide and not any(word in text for word in ("今天","恢复","适合我","我的","计划")):
        return guide
    if not enabled:
        return (guide + "\n" if guide else "") + ("尚未允许助手读取本人健康资料，未据此推断个人训练或恢复情况。可在助手设置开启资料使用，"
                "或直接打开已有训练安排。肩部等恢复程度需核对已保存评估与训练感受，不能从聊天推断。")
    lines = ["以下仅说明云端已保存的本人资料，不是新测量、临床结论或新训练处方。"]
    profile = context.get("workflow") or {}
    if profile.get("goal"):
        lines.append("已保存目标（本人填写）：" + excerpt(profile["goal"]))
    if profile.get("restrictions"):
        lines.append("已记录活动限制，请先联系康复医师核对，不自动增加训练。")
    plan = context.get("current_plan")
    if not plan:
        lines.append("云端尚无本人已采用的医生训练安排；候选需医师核对，发布后仍须本人确认采用。")
    elif plan["execution_status"] == "STOPPED":
        lines.append("当前采用的训练安排已停用，请联系医师核对，不能据此开始训练。")
    elif plan["execution_status"] == "REST_DAY":
        lines.append("当前采用的分阶段安排今天没有训练项目；请按原安排休息并在训练页面核对。")
    elif plan["execution_status"] == "MANUAL_ONLY":
        lines.append("当前安排仅供人工执行，需与医师核对，不能由助手启动。")
    else:
        lines.append("已采用安排：" + plan["title"] + "。项目的今日可执行性仍须在原训练页面核验并由本人确认。")
        for item in plan["items"]:
            card = action_library().get(item["exercise_id"])
            if card:
                settings = item["settings"]
                dose = "；已保存剂量：" + str(settings["target_reps"]) + "次 × " + str(settings["target_sets"]) + "组" if settings.get("target_reps") is not None and settings.get("target_sets") is not None else "；剂量未记录"
                lines.append(card["name"] + dose)
    assessments = [r for r in context["records"] if r["kind"] == "assessment"]
    if not assessments:
        lines.append("尚无可用的本人已同步评估；不能推断肩膀等部位的恢复程度。请在原评估页面完成并保存真实结果。")
    for record in assessments[:1]:
        facts = record["facts"] if isinstance(record["facts"],dict) else {}
        card = action_library().get(facts["exercise_id"]) if isinstance(facts.get("exercise_id"),str) else None
        summary = facts.get("summary") or {}
        motion = summary.get("motion_range") if isinstance(summary,dict) else None
        observed = motion.get("max_deg") if isinstance(motion,dict) else None
        lines.append("已同步评估：" + (card["name"] if card else "项目未记录") + "（客户端声明来源，不等于临床认证）。"
                     + ("保存的二维最大投影角为" + str(observed) + "度，不等于临床关节活动度。" if type(observed) in {int,float} else "二维角度未记录。"))
    for record in [r for r in context["records"] if r["kind"] == "training"][:1]:
        facts = record["facts"] if isinstance(record["facts"],dict) else {}
        feedback = facts.get("training_feedback") or facts.get("feedback") or {}
        if isinstance(feedback,dict):
            lines.append("最近已保存训练感受（本人填写）：" + "；".join(label + (str(feedback[key]) if type(feedback.get(key)) in {int,float} else "未记录") for key,label in (("pain","疼痛"),("fatigue","疲劳"))))
    return (guide + "\n" if guide else "") + "\n".join(lines)


def frozen_prompt(text, purpose, context, history, guidelines, spec=None):
    history = dialogue.history_for(text, history)
    payload = {"purpose": purpose, "question": text, "authorized_context": context, "guideline_context": guidelines,
               "dialogue_excerpt": dialogue_excerpt(history), "dialogue": spec or dialogue.protocol(text, purpose, history),
               "recent_dialogue": [{"user": excerpt(r["text"], 300), "assistant": excerpt(r["answer"], 400)} for r in history[-4:]]}
    spec = payload["dialogue"]
    if spec.get("assessment_ready"):
        payload["online_assessment_plan"] = {"routing_version":spec.get("assessment_routing_version", assistant_assessments.VERSION),
                                             "items":assistant_assessments.appointment_items(spec, text)}
    example_reply = ("先暂缓会加重不适的负重。我们先在线上把活动情况测清楚，再确定训练安排。" if spec["mode"] == "SYMPTOM" else
                     "先在App完成线上评估，再依据实际结果确定训练安排。" if spec["assessment_ready"] else
                     "我会结合已有资料，帮你确定下一步。")
    payload["example_response"] = {"reply":example_reply,
                                   "questions":spec["missing_questions"], "advice":[], "next_step":spec["workflow_next_step"]}
    payload["follow_up_constraint"] = "只使用missing_questions；已回答的信息不重问，下一步采用冻结的线上路径，不默认转向线下。"
    prompt = dialogue.RULES + "\n" + compact(payload)
    # Bound history, never cut a selected card's safety conditions or the question.
    while len(prompt) > PROMPT_LIMIT and payload["recent_dialogue"]:
        payload["recent_dialogue"].pop(0)
        prompt = dialogue.RULES + "\n" + compact(payload)
    if len(prompt) > PROMPT_LIMIT:
        payload["dialogue_excerpt"] = ""
        prompt = dialogue.RULES + "\n" + compact(payload)
    if len(prompt) > PROMPT_LIMIT:
        raise DomainError(422, "ASSISTANT_CONTEXT_TOO_LARGE", "资料范围过大，请缩小问题范围")
    return prompt


def dialogue_spec(prompt):
    """Old pending requests keep their original prompt and legacy validator."""
    try:
        spec = json.loads(prompt.split("\n", 1)[1]).get("dialogue")
        return spec if isinstance(spec, dict) and spec.get("version") in dialogue.SUPPORTED_VERSIONS else None
    except (ValueError, IndexError, AttributeError):
        return None


def saved_facts(context, enabled, mode):
    """Only code, never provider text, renders personal quantitative records."""
    if mode not in {"RECORDS", "PLAN"}:
        return ""
    if not enabled:
        return "要查看你的评估和安排，请先在使用说明中允许管家使用云端康复资料。"
    lines = []
    profile = context.get("workflow") or {}
    if profile.get("goal"):
        lines.append("已保存目标：" + excerpt(profile["goal"], 100))
    if profile.get("restrictions"):
        lines.append("已有活动限制，请先与康复医师核对。")
    plan = context.get("current_plan")
    if plan:
        state = plan["execution_status"]
        if state in {"STOPPED", "REST_DAY", "MANUAL_ONLY"}:
            lines.append({"STOPPED": "当前方案已停用。", "REST_DAY": "今天是方案中的休息日。", "MANUAL_ONLY": "当前方案需人工执行。"}[state])
        else:
            lines.append("已采用方案：" + plan["title"])
            for item in plan["items"][:4]:
                card = action_library().get(item["exercise_id"])
                s = item["settings"]
                if card:
                    dose = str(s["target_reps"]) + "次 × " + str(s["target_sets"]) + "组" if s.get("target_reps") is not None and s.get("target_sets") is not None else "剂量未记录"
                    lines.append(card["name"] + "：" + dose)
    else:
        lines.append("云端还没有已采用的训练方案。")
    assessments = [r for r in context.get("records", []) if r["kind"] == "assessment"]
    if not assessments:
        lines.append("云端还没有已同步的评估结果。")
    for record in assessments[:1]:
        facts = record["facts"] or {}
        card = action_library().get(facts.get("exercise_id"))
        summary = facts.get("summary") or {}
        motion = (summary.get("motion_range") or {}) if isinstance(summary, dict) else {}
        angle = motion.get("max_deg") if isinstance(motion, dict) else None
        if card and type(angle) in {int, float}:
            lines.append("已保存评估：" + card["name"] + "，二维最大投影角" + str(angle) + "度。")
    for record in [r for r in context.get("records", []) if r["kind"] == "training"][:1]:
        facts = record["facts"] or {}
        feedback = facts.get("training_feedback") or facts.get("feedback") or {}
        if isinstance(feedback, dict):
            lines.append("本人上次反馈：" + "；".join(label + (str(feedback[k]) if type(feedback.get(k)) in {int, float} else "未记录") for k, label in (("pain", "疼痛"), ("fatigue", "疲劳"))))
    return "已有记录\n" + "\n".join(lines) + "\n以上不是新训练处方；开始仍须在训练页核对。"


def safe_explanation(answer):
    # Quantitative/clinical claims stay in the deterministic record explanation.
    # Provider prose cannot create measurements, diagnoses, prescriptions or URLs.
    forbidden = r"[0-9０-９]|[零一二三四五六七八九十百两]+\s*(?:度|次|组|毫克|片|天)|https?://|www\.|[a-z]+://|\]\(|<[^>]+>|测得|检测到|确诊|诊断为|你患有|已恢复|恢复到|恢复了|服用|停药|加药|减药|药量|处方剂量"
    return isinstance(answer,str) and 0 < len(answer.strip()) <= 4000 and not re.search(forbidden,answer,re.I)


def public_turn(row):
    return {key: row[key] for key in ("id","operation_id","sequence","text","answer","actions","receipt_id","created_at",
                                     "state","purpose","private","source","context_versions")}


def turn_response(row):
    result = {"turn": public_turn(row), "summary": row["summary"], "health_context_enabled": row["health_context_enabled"],
              "source": row["source"], "state": row["state"]}
    if row["receipt"] is not None:
        result["receipt"] = row["receipt"]
    return result


def install_assistant(app, db, caller, patient_scope, base):
    """Register owner-only routes; never migrate or replace the shared gateway."""
    def authorize(connection, request, ident, write=False):
        actor, _ = caller(request, connection, write=write)
        patient_scope(connection, actor, ident, write=True)  # Doctor grants never expose private dialogue.
        if actor["role"] != "PATIENT":
            raise DomainError(403, "PATIENT_REQUIRED", "仅本人可访问助手对话与偏好")
        if write:
            connection.execute(select(patients.c.id).where(patients.c.id == ident).with_for_update()).first()
        return actor

    assistant_assessments.install(app, db, authorize, base)

    @app.get(base + "/patients/{ident}/assistant/preferences")
    def get_preferences(ident: str, request: Request):
        with db.transaction() as connection:
            authorize(connection,request,ident)
            return preference_document(connection,ident)

    @app.put(base + "/patients/{ident}/assistant/preferences")
    def put_preferences(ident: str, value: PreferencesInput, request: Request):
        with db.transaction() as connection:
            actor = authorize(connection,request,ident,True)
            old = preference_document(connection,ident)
            if old["version"] != value.expected_version:
                raise DomainError(412,"REVISION_MISMATCH","助手偏好已更新，请刷新后重试")
            changes = {"version":old["version"]+1,"allow_health_context":value.health_context}
            if old["version"]:
                connection.execute(update(preferences).where(preferences.c.patient_id == ident).values(**changes))
            else:
                connection.execute(preferences.insert().values(patient_id=ident,**changes))
            audited(connection,actor["id"],"assistant.preferences",ident)
            return {"version":changes["version"],"health_context":value.health_context}

    @app.get(base + "/patients/{ident}/assistant/conversation")
    def conversation(ident: str, request: Request, after: int = 0, limit: int = 30):
        if not 0 <= after <= 2147483647 or not 1 <= limit <= 100:
            raise DomainError(422,"VALIDATION_ERROR","对话查询范围无效")
        with db.transaction() as connection:
            authorize(connection,request,ident)
            rows = list(connection.execute(select(turns).where(turns.c.patient_id == ident,turns.c.sequence > after)
                        .order_by(turns.c.sequence).limit(limit+1)).mappings())
            # Native clients cap replies at 512 KiB. Count-only paging can
            # exceed that with long, Chinese-language grounded answers.
            visible, size = [], 0
            for row in rows[:limit]:
                item_size = len(compact(public_turn(row)).encode('utf-8'))
                if visible and size + item_size > 384 * 1024:
                    break
                visible.append(row)
                size += item_size
            latest = connection.scalar(select(func.max(turns.c.sequence)).where(turns.c.patient_id == ident)) or 0
            return {"items":[public_turn(row) for row in visible],"summary":saved_summary(connection,ident),
                    "health_context_enabled":preference_document(connection,ident)["health_context"],
                    "has_more":len(rows)>len(visible),"next_after":visible[-1]["sequence"] if visible else after,"latest_sequence":latest}

    @app.post(base + "/patients/{ident}/assistant/turns")
    def submit(ident: str, value: TurnInput, request: Request):
        if not value.text.strip():
            raise DomainError(422,"VALIDATION_ERROR","请输入问题")
        fingerprint_value = value.model_dump(mode="json")
        if value.assessment_contract is None:
            fingerprint_value.pop("assessment_contract")  # Preserve old pending-operation fingerprints.
        fingerprint = digest(compact(fingerprint_value))
        with db.transaction() as connection:
            actor = authorize(connection,request,ident,True)
            pref = preference_document(connection,ident)
            row = connection.execute(select(turns).where(turns.c.actor_id == actor["id"],turns.c.operation_id == str(value.operation_id))).mappings().first()
            if row:
                if row["patient_id"] != ident or row["fingerprint"] != fingerprint:
                    raise DomainError(409,"IDEMPOTENCY_CONFLICT","原提问已有不同内容，请保留原操作编号与文字")
                row = dict(row)
                if row["completed_at"] is not None:
                    return turn_response(row)
                if row["health_context_enabled"] and pref["version"] != row["context_versions"]["assistant_preferences"]:
                    raise DomainError(409,"ASSISTANT_CONTEXT_CHANGED","资料使用偏好已变更，旧问题未重新发送；请以新操作重新提问")
            else:
                enabled = pref["health_context"] and not value.private
                context, versions = health_context(connection,ident,value.text) if enabled else ({}, {})
                guidelines, guide_versions = guideline_context(value.text)
                versions["guidelines"] = guide_versions
                versions["assistant_preferences"] = pref["version"]
                versions["dialogue_protocol"] = dialogue.VERSION
                purpose = value.purpose or purpose_for(value.text)
                history_query = select(turns).where(turns.c.patient_id == ident,turns.c.private.is_(False),turns.c.answer.is_not(None))
                if not enabled:
                    history_query = history_query.where(turns.c.health_context_enabled.is_(False))
                history = list(reversed(list(connection.execute(history_query.order_by(turns.c.sequence.desc()).limit(6)).mappings())))
                spec = dialogue.protocol(value.text, purpose, [] if value.private else history,
                                         default_region=(context.get("workflow") or {}).get("region"))
                hold = saved_summary(connection, ident).get("safety_hold")
                if hold and dialogue.reported_professional_clearance(value.text) and not dialogue.urgent_signal(value.text, spec["back_related"]):
                    safety_hold(connection, ident, None)
                    audited(connection, actor["id"], "assistant.safety.user_reported_review", ident)
                    # This is an explicit self-report, not a verified diagnosis.
                    spec = dialogue.protocol(value.text, purpose, [], default_region=(context.get("workflow") or {}).get("region"))
                    hold = None
                if hold and (spec["assessment_ready"] or spec["mode"] in {"SYMPTOM", "PLAN", "RECORDS"}) and not spec["urgent_back_symptoms"]:
                    block_for_hold(spec)
                if context.get("current_plan") and spec["mode"] == "PLAN" and purpose == "CHAT":
                    spec.update(assessment_ready=False, workflow_next_step="打开已采用的训练安排，按今天的项目执行；有新不适时先暂缓并说明情况。")
                if (context.get("workflow") or {}).get("restrictions") and spec["assessment_ready"]:
                    spec.update(assessment_ready=False, intake_stage="ONLINE_REVIEW", missing_questions=[], max_questions=0,
                                workflow_next_step="已有活动限制，先通过App内康复医师核对，再安排合适的线上评估。")
                # Older APKs/desktop do not have the explicit result-link outbox.
                # Keep their frozen v1 appointments functional during rolling updates.
                if value.assessment_contract is None:
                    spec["version"] = "rehab-dialogue-3"
                    spec["assessment_routing_version"] = "online-assessment-routing-1"
                else:
                    spec["assessment_routing_version"] = assistant_assessments.VERSION
                versions["dialogue_protocol"] = spec["version"]
                spec["assessment_items"] = assistant_assessments.appointment_items(spec, value.text) if spec["assessment_ready"] else []
                prompt = frozen_prompt(value.text, purpose, context, [] if value.private else history, guidelines, spec)
                facts = saved_facts(context, enabled, spec["mode"])
                local = (local_explanation(value.text, context, enabled, guidelines) if spec["mode"] == "ACTION" and guidelines["cards"]
                         else dialogue.fallback(spec) + ("\n\n" + facts if facts else ""))
                if spec["intake_stage"] in {"URGENT", "ONLINE_REVIEW"}:
                    actions = [{"kind": "doctor_review", "label": "联系康复医师"}]
                elif spec["mode"] == "SYMPTOM" and not spec["assessment_ready"]:
                    actions = []
                else:
                    actions = suggested_actions(value.text, purpose, context)
                    # Routine online navigation does not always need a doctor CTA.
                    actions = [action for action in actions if action["kind"] != "doctor_review"]
                now = int(time.time())
                row = {"id":str(uuid4()),"patient_id":ident,"actor_id":actor["id"],"operation_id":str(value.operation_id),
                       "sequence":(connection.scalar(select(func.max(turns.c.sequence)).where(turns.c.patient_id == ident)) or 0)+1,
                       "fingerprint":fingerprint,"text":value.text,"purpose":purpose,"private":value.private,
                       "health_context_enabled":enabled,"context_versions":versions,
                       "prompt":prompt,"local_answer":local,"answer":None,
                       "actions":actions,"state":"PENDING","source":"local",
                       "receipt_id":None,"receipt":None,"summary":saved_summary(connection,ident),"created_at":now,"completed_at":None}
                connection.execute(turns.insert().values(**row))
                if not value.private and spec["urgent_back_symptoms"]:
                    safety_hold(connection, ident, "URGENT", row["id"])
                audited(connection,actor["id"],"assistant.turn",row["id"])
        # Never hold a patient/SQLite lock across the gateway: it authenticates,
        # reserves budget and commits its own idempotent receipt transaction.
        receipt = None
        escalation = None
        spec = dialogue_spec(row["prompt"])
        if row["private"] or spec and spec["urgent_back_symptoms"]:
            answer, source, state = row["local_answer"], "local", "LOCAL"
        else:
            dispatcher = getattr(app.state,"dispatch_text_ai",None)
            if dispatcher is None:
                raise DomainError(503,"ASSISTANT_UNAVAILABLE","助手服务尚未准备，请稍后重试原问题")
            try:
                receipt = dispatcher(ident,TextRequest(operation_id=value.operation_id,text=row["prompt"],purpose=row["purpose"]),request)
            except DomainError as exc:
                if exc.code != "AI_NOT_CONFIGURED":
                    raise
                answer, source, state = row["local_answer"], "local", "LOCAL"
            else:
                if (not isinstance(receipt,dict) or receipt.get("state") not in {"RUNNING","SUCCEEDED","UNMETERED","UNKNOWN"}
                        or not isinstance(receipt.get("id"),str) or len(receipt["id"]) > 36
                        or str(receipt.get("operation_id")) != row["operation_id"]):
                    raise DomainError(503,"ASSISTANT_RECEIPT_INVALID","问答回执尚待核对，请保留原操作重试")
                state, source, answer = receipt["state"], "deepseek", None
                if state in {"SUCCEEDED","UNMETERED"}:
                    if spec:
                        if spec.get("version") in {dialogue.VERSION,"rehab-dialogue-3"}:
                            escalation = dialogue.model_escalation(receipt.get("answer"))
                        formatted = dialogue.render(receipt.get("answer"), spec)
                        if escalation:
                            source = "local"
                            answer = ("请先停止训练和动作测试，立即寻求急诊帮助，不要等待线上测量。" if escalation == "URGENT" else
                                      "先暂缓动作测试，通过App内康复医师核对后，再决定合适的评估安排。")
                        elif formatted:
                            payload = json.loads(row["prompt"].split("\n", 1)[1])
                            facts = saved_facts(payload["authorized_context"], row["health_context_enabled"], spec["mode"])
                            answer = formatted + ("\n\n" + facts if facts else "")
                        else:
                            source, answer = "local", row["local_answer"]
                    elif safe_explanation(receipt.get("answer")):
                        answer = row["local_answer"] + "\n一般解释（不作为测量事实）：" + receipt["answer"].strip()
                    else:
                        source, answer = "local", row["local_answer"] + "\n模型内容未作为个人事实采纳，请以已有记录和医师核对为准。"
                elif state == "UNKNOWN":
                    answer = row["local_answer"] + "\n模型请求的结果与用量尚待核对，不自动重发或视为免费。"
                # Accounting only: the displayed answer is turn.answer, never receipt.answer.
                receipt = {key:receipt[key] for key in ("id","operation_id","state","model","provider_id","usage","pricing","estimated_cost","created_at","completed_at") if key in receipt}
        with db.transaction() as connection:
            authorize(connection,request,ident,True)
            saved = dict(connection.execute(select(turns).where(turns.c.id == row["id"])).mappings().one())
            if saved["completed_at"] is not None:
                return turn_response(saved)
            if saved["receipt_id"] and (not receipt or saved["receipt_id"] != receipt["id"]):
                raise DomainError(503,"ASSISTANT_RECEIPT_INVALID","原问题回执需核对，请保留原操作")
            changes = {"answer":answer,"state":state,"source":source,"receipt":receipt,
                       "receipt_id":receipt["id"] if receipt else None,"completed_at":int(time.time()) if state != "RUNNING" else None}
            hold = saved_summary(connection, ident).get("safety_hold")
            if escalation == "URGENT":
                safety_hold(connection, ident, escalation, row["id"])
            elif hold and spec and spec.get("assessment_ready"):
                # A later warning wins over an old slow response; keep its
                # provider receipt and prompt, but never schedule from it.
                escalation = "ONLINE_REVIEW"
                changes["answer"] = "你之后补充了需要优先核对的症状。这份旧提问不再安排动作测试，请先完成医疗核对；当前仍有危险症状时立即急诊。"
                changes["source"] = "local"
            if escalation:
                changes["actions"] = [{"kind":"doctor_review", "label":"联系康复医师"}]
            elif state in {"LOCAL", "SUCCEEDED", "UNMETERED"} and not row["private"] and spec and spec.get("version") in {dialogue.VERSION,"rehab-dialogue-3"}:
                plan = assistant_assessments.schedule(connection, ident, row["id"], spec, row["text"])
                if plan:
                    changes["actions"] = [{"kind":"assessment_plan", "label":"查看评估计划", "plan_id":plan["id"]}] + [a for a in row["actions"] if a["kind"] not in {"assessment", "candidate"}]
                    changes["answer"] += "\n\n评估顺序\n" + " → ".join(item["name"] for item in plan["items"]) + "\n已加入我的计划 → 评估计划。"
            connection.execute(update(turns).where(turns.c.id == saved["id"]).values(**changes))
            if changes["completed_at"] is not None:
                old_summary = saved_summary(connection,ident)
                recent = list(reversed(list(connection.execute(select(turns).where(turns.c.patient_id == ident,
                    turns.c.private.is_(False),turns.c.answer.is_not(None),turns.c.completed_at.is_not(None))
                    .order_by(turns.c.sequence.desc()).limit(6)).mappings())))
                summary = {"kind":"DIALOGUE_EXCERPT","version":old_summary["version"]+1,
                           "text":dialogue_excerpt(recent),"through_sequence":max((r["sequence"] for r in recent),default=0)}
                if old_summary.get("safety_hold"):
                    summary["safety_hold"] = old_summary["safety_hold"]
                if connection.scalar(select(memory.c.patient_id).where(memory.c.patient_id == ident)):
                    connection.execute(update(memory).where(memory.c.patient_id == ident).values(document=summary))
                else:
                    connection.execute(memory.insert().values(patient_id=ident,document=summary))
                changes["summary"] = summary
                connection.execute(update(turns).where(turns.c.id == saved["id"]).values(summary=summary))
            return turn_response({**saved,**changes})
