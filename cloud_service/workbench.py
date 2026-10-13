"""Authorized text follow-up and immutable clinician plan publications.

Acceptance records a patient's current professional plan. It never activates a
camera exercise, changes a local assessment, or invokes an LLM.
"""
from functools import lru_cache
from datetime import datetime
import json
import math
from pathlib import Path
import time
from uuid import UUID, uuid4

from fastapi import Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    CheckConstraint, Column, ForeignKey, Integer, JSON, String, Table, Text,
    UniqueConstraint, func, select, update,
)

from .database import accounts, grants, metadata, patients, records
from .security import DomainError, audited, digest

messages = Table("workbench_messages", metadata,
    Column("id", String(36), primary_key=True),
    Column("patient_id", String(36), ForeignKey("patients.id"), nullable=False, index=True),
    Column("sequence", Integer, nullable=False),
    Column("author_id", String(36), ForeignKey("accounts.id"), nullable=False),
    Column("author_role", String(20), nullable=False),
    Column("text", Text, nullable=False),
    Column("created_at", Integer, nullable=False),
    UniqueConstraint("patient_id", "sequence"),
)
plans = Table("workbench_plans", metadata,
    Column("id", String(36), primary_key=True),
    Column("patient_id", String(36), ForeignKey("patients.id"), nullable=False, index=True),
    Column("author_id", String(36), ForeignKey("accounts.id"), nullable=False),
    Column("parent_plan_id", String(36), ForeignKey("workbench_plans.id")),
    Column("title", String(80), nullable=False),
    Column("summary", Text, nullable=False),
    Column("items", JSON, nullable=False),
    Column("status", String(12), nullable=False),
    Column("version", Integer, nullable=False),
    Column("publication_sequence", Integer),
    Column("created_at", Integer, nullable=False),
    Column("updated_at", Integer, nullable=False),
    Column("published_at", Integer),
    CheckConstraint("status IN ('DRAFT', 'PUBLISHED')"),
    UniqueConstraint("patient_id", "publication_sequence"),
)
current_plans = Table("workbench_current_plans", metadata,
    Column("patient_id", String(36), ForeignKey("patients.id"), primary_key=True),
    Column("plan_id", String(36), ForeignKey("workbench_plans.id"), nullable=False),
    Column("accepted_version", Integer, nullable=False),
    Column("revision", Integer, nullable=False),
    Column("accepted_at", Integer, nullable=False),
    Column("local_validation", JSON, nullable=False),
)
message_reads = Table("workbench_message_reads", metadata,
    Column("patient_id", String(36), ForeignKey("patients.id"), primary_key=True),
    Column("actor_id", String(36), ForeignKey("accounts.id"), primary_key=True),
    Column("cursor", Integer, nullable=False),
    Column("read_at", Integer, nullable=False),
)
record_heads = Table("workbench_record_heads", metadata,
    Column("patient_id", String(36), ForeignKey("patients.id"), primary_key=True),
    Column("installation_id", String(100), primary_key=True),
    Column("record_key", String(100), primary_key=True),
    Column("revision", Integer, nullable=False),
    Column("record_id", String(36), ForeignKey("patient_record_events.id"), nullable=False),
    Column("kind", String(20), nullable=False),
)
operations = Table("workbench_operations", metadata,
    Column("actor_id", String(36), ForeignKey("accounts.id"), primary_key=True),
    Column("operation_id", String(36), primary_key=True),
    Column("patient_id", String(36), ForeignKey("patients.id"), nullable=False),
    Column("kind", String(30), nullable=False),
    Column("digest", String(64), nullable=False),
    Column("result", JSON, nullable=False),
    Column("created_at", Integer, nullable=False),
)


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class MessageInput(Input):
    operation_id: UUID = Field(strict=False)
    text: str = Field(min_length=1, max_length=4000)


class PlanItem(Input):
    exercise_id: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=200)
    side: str = Field(pattern="^(left|right)$")
    measurement_contract: str = Field(min_length=1, max_length=80)
    settings: dict
    dose: str = Field(default="", max_length=2000)
    caution: str = Field(default="", max_length=2000)


class PlanInput(Input):
    programme: dict | None = None
    operation_id: UUID = Field(strict=False)
    title: str = Field(min_length=1, max_length=80)
    summary: str = Field(default="", max_length=8000)
    items: list[PlanItem] = Field(min_length=1, max_length=40)
    parent_plan_id: str | None = Field(default=None, max_length=36)


class PlanUpdate(PlanInput):
    expected_version: int = Field(ge=1)


class PlanTransition(Input):
    operation_id: UUID = Field(strict=False)
    expected_version: int = Field(ge=1)


class LocalScope(Input):
    participant_id: str = Field(min_length=1, max_length=100)
    source_kind: str = Field(pattern="^(LIVE_CAMERA|REPLAY_FILE|PHONE_LOCAL)$")
    usage_context: str = Field(pattern="^SELF_USE$")


class AssessmentReference(Input):
    key: str = Field(min_length=1, max_length=80)
    session_id: str = Field(min_length=1, max_length=100)
    measurement_contract: str = Field(min_length=1, max_length=80)


class LocalValidation(Input):
    local_plan_id: str = Field(min_length=1, max_length=100)
    local_revision: int = Field(ge=1)
    scope: LocalScope
    validation_policy: str = Field(pattern="^existing-local-assessment-1$")
    assessment_references: list[AssessmentReference] = Field(min_length=1, max_length=40)
    validated_at: str = Field(min_length=1, max_length=50)


class PlanAcceptance(PlanTransition):
    expected_current_revision: int = Field(ge=0)
    local_validation: LocalValidation


class MessageRead(Input):
    operation_id: UUID = Field(strict=False)
    cursor: int = Field(ge=0)


SETTINGS_FIELDS = (
    "target_reps", "target_sets", "rest_between_sets_s", "target_angle_deg",
    "allowed_elbow_flexion_deg", "allowed_trunk_tilt_deg", "lowering_tempo_min_s",
    "lowering_tempo_max_s", "use_of_hands", "needs_companion", "sound_enabled", "timing_plan",
)
TIMING_FIELDS = ("outbound_min_s", "outbound_max_s", "return_min_s", "return_max_s", "hold_min_s")


@lru_cache(maxsize=1)
def action_library():
    source = Path(__file__).with_name("exercises.json")
    value = json.loads(source.read_text(encoding="utf-8"))
    if value["schema"] != "ankang-existing-exercises-1":
        raise RuntimeError("Unsupported measurement contract manifest")
    return {row["exercise_id"]: row for row in value["items"]}


def action_public(row):
    return {**row, "settings_fields": list(SETTINGS_FIELDS)}


def plan_settings(value, exercise_id):
    """Check engineering input ranges; local assessment gates remain mandatory."""
    if not isinstance(value, dict) or set(value) - set(SETTINGS_FIELDS):
        raise DomainError(422, "PLAN_SETTINGS_INVALID", "计划设置含未知字段")
    result = {key: value.get(key) for key in SETTINGS_FIELDS}
    for key, maximum in (("target_reps", 999), ("target_sets", 20)):
        if type(result[key]) is not int or not 1 <= result[key] <= maximum:
            raise DomainError(422, "PLAN_SETTINGS_INVALID", "请明确填写有效次数与组数")
    # Null denotes an unspecified goal, never a guessed therapeutic target.
    if not {"rest_between_sets_s", "target_angle_deg"} <= set(value):
        raise DomainError(422, "PLAN_SETTINGS_INVALID", "请明确填写休息与目标，未指定的目标留空")
    for key, maximum in (("rest_between_sets_s", 1800), ("target_angle_deg", 180),
        ("allowed_elbow_flexion_deg", 180), ("allowed_trunk_tilt_deg", 90),
        ("lowering_tempo_min_s", 60), ("lowering_tempo_max_s", 60)):
        number = result[key]
        if number is not None and (type(number) not in (int, float) or not math.isfinite(number) or not 0 <= number <= maximum):
            raise DomainError(422, "PLAN_SETTINGS_INVALID", "角度或时间无效，请核对填写范围")
    low, high = result["lowering_tempo_min_s"], result["lowering_tempo_max_s"]
    if low is not None and high is not None and low > high:
        raise DomainError(422, "PLAN_SETTINGS_INVALID", "最短时间不能超过最长时间")
    if exercise_id != "sit_to_stand" and (low is not None or high is not None):
        raise DomainError(422, "PLAN_SETTINGS_INVALID", "下降节奏仅适用于坐站")
    result["use_of_hands"] = value.get("use_of_hands", "not_recorded")
    if result["use_of_hands"] not in ("not_recorded", "allowed", "not_allowed", "used_hands"):
        raise DomainError(422, "PLAN_SETTINGS_INVALID", "扶物设置无效")
    for key in ("needs_companion", "sound_enabled"):
        result[key] = value.get(key, False)
        if type(result[key]) is not bool:
            raise DomainError(422, "PLAN_SETTINGS_INVALID", "陪同和提示音须为明确开关")
    timing = value.get("timing_plan", {})
    if timing is None:
        timing = {}
    if not isinstance(timing, dict) or set(timing) - set(TIMING_FIELDS):
        raise DomainError(422, "PLAN_SETTINGS_INVALID", "时间安排含未知字段")
    timing = {key: timing.get(key) for key in TIMING_FIELDS}
    for number in timing.values():
        if number is not None and (type(number) not in (int, float) or not math.isfinite(number) or not 0 <= number <= 300):
            raise DomainError(422, "PLAN_SETTINGS_INVALID", "动作时间应为0至300秒或留空")
    for phase in ("outbound", "return"):
        lo, hi = timing[phase + "_min_s"], timing[phase + "_max_s"]
        if lo is not None and hi is not None and lo > hi:
            raise DomainError(422, "PLAN_SETTINGS_INVALID", "动作最短时间不能超过最长时间")
    if timing["hold_min_s"] and result["target_angle_deg"] is None and exercise_id != "sit_to_stand":
        raise DomainError(422, "PLAN_SETTINGS_INVALID", "保持目标需要先填写人工角度目标")
    if exercise_id == "sit_to_stand":
        for bound in ("min", "max"):
            key, legacy = "return_" + bound + "_s", result["lowering_tempo_" + bound + "_s"]
            if timing[key] is None:
                timing[key] = legacy
            elif legacy is not None and legacy != timing[key]:
                raise DomainError(422, "PLAN_SETTINGS_INVALID", "下降节奏与回程时间不一致")
    result["timing_plan"] = timing
    return result


def text(value, label):
    value = value.strip()
    if not value or any(ord(c) < 32 and c not in "\n\t" for c in value):
        raise DomainError(422, "VALIDATION_ERROR", "请填写有效的" + label)
    return value


def plan_document(value):
    library = action_library()
    result = []
    used = set()
    for item in value.items:
        card = library.get(item.exercise_id)
        if not card or item.name != card["name"]:
            raise DomainError(422, "ACTION_NOT_FOUND", "请选择现有训练动作，保留原动作名称")
        key = item.exercise_id + ":" + item.side
        if key in used:
            raise DomainError(422, "DUPLICATE_ACTION", "同一动作请在剂量内说明，不要重复添加")
        if item.measurement_contract != card["measurement_contract"]:
            raise DomainError(422, "MEASUREMENT_CONTRACT_MISMATCH", "测量定义已变化，请重新选择动作")
        used.add(key)
        result.append({"key": key, "exercise_id": item.exercise_id, "name": card["name"], "side": item.side,
            "measurement_contract": card["measurement_contract"], "settings": plan_settings(item.settings, item.exercise_id),
            "dose": item.dose.strip(), "caution": item.caution.strip(), "measurement_type": "2d_projection",
            "clinical_rom": False, "experimental": card["experimental"]})
    return {"title": text(value.title, "方案标题"), "summary": value.summary.strip(), "items": result}


def record_projection(connection, ident, value, record_id):
    if value.payload.get("schema") != "ankang-workbench-record-1":
        return
    document = value.payload
    condition = (record_heads.c.patient_id == ident) & (record_heads.c.installation_id == value.installation_id) & (record_heads.c.record_key == document["record_key"])
    old = connection.execute(select(record_heads).where(condition)).mappings().first()
    if record_id is None:
        if old and document["revision"] <= old["revision"]:
            raise DomainError(409, "RECORD_REVISION_CONFLICT", "记录修订已更新，请保留本机内容并核对最新版本")
        return
    changes = {"revision": document["revision"], "record_id": record_id, "kind": document["kind"]}
    if old:
        connection.execute(update(record_heads).where(condition).values(**changes))
    else:
        connection.execute(record_heads.insert().values(patient_id=ident, installation_id=value.installation_id,
            record_key=document["record_key"], **changes))


def latest_records(connection, ident):
    return [dict(row) for row in connection.execute(select(records.c.id, records.c.source_kind,
        records.c.attribution_state, records.c.payload, records.c.received_at).join(record_heads,
            records.c.id == record_heads.c.record_id).where(record_heads.c.patient_id == ident)
        .order_by(records.c.received_at.desc(), records.c.id)).mappings()]


def read_status(connection, actor, ident):
    cursor = connection.scalar(select(message_reads.c.cursor).where(message_reads.c.patient_id == ident,
        message_reads.c.actor_id == actor["id"])) or 0
    unread = connection.scalar(select(func.count()).select_from(messages).where(messages.c.patient_id == ident,
        messages.c.author_id != actor["id"], messages.c.sequence > cursor))
    return {"read_cursor": cursor, "unread_count": unread}


def validate_adoption(plan, local):
    try:
        timestamp = datetime.fromisoformat(local.validated_at.replace("Z", "+00:00"))
    except ValueError:
        raise DomainError(422, "LOCAL_VALIDATION_REQUIRED", "本地核验时间无效") from None
    if timestamp.tzinfo is None:
        raise DomainError(422, "LOCAL_VALIDATION_REQUIRED", "本地核验时间须带时区")
    references = {r.key: r for r in local.assessment_references}
    if len(references) != len(local.assessment_references) or set(references) != {i["key"] for i in plan["items"]}:
        raise DomainError(422, "LOCAL_VALIDATION_REQUIRED", "须逐项保留本人有效评估的核验引用")
    if any(references[i["key"]].measurement_contract != i["measurement_contract"] for i in plan["items"]):
        raise DomainError(422, "LOCAL_VALIDATION_REQUIRED", "本地评估与发布方案的测量定义不一致")
    return {**local.model_dump(mode="json"), "cloud_plan_id": plan["id"], "cloud_version": plan["version"],
        "attribution_state": "CLIENT_DECLARED", "automatic_execution": False}


def operation_digest(kind, ident, resource, value):
    body = value.model_dump(mode="json")
    if body.get("programme", "ABSENT") is None:
        del body["programme"]  # Preserve receipts from pre-programme clients.
    return digest(json.dumps({"kind": kind, "patient_id": ident, "resource_id": resource,
        "body": body}, sort_keys=True, ensure_ascii=False, separators=(",", ":")))


def prior_operation(connection, actor, ident, kind, resource, value):
    fingerprint = operation_digest(kind, ident, resource, value)
    prior = connection.execute(select(operations).where(operations.c.actor_id == actor["id"],
        operations.c.operation_id == str(value.operation_id))).mappings().first()
    if prior:
        if prior["digest"] != fingerprint:
            raise DomainError(409, "IDEMPOTENCY_CONFLICT", "这次操作已有不同内容，请刷新后重试")
        return {**prior["result"], "idempotent": True}, fingerprint
    return None, fingerprint


def commit_operation(connection, actor, ident, kind, value, fingerprint, result):
    result = {"status": "COMMITTED", **result, "idempotent": False}
    connection.execute(operations.insert().values(actor_id=actor["id"], operation_id=str(value.operation_id),
        patient_id=ident, kind=kind, digest=fingerprint, result=result, created_at=int(time.time())))
    audited(connection, actor["id"], "workbench." + kind, result.get("resource_id"))
    return result


def current(connection, ident):
    return connection.execute(select(current_plans).where(current_plans.c.patient_id == ident)).mappings().first()


def get_plan(connection, ident, plan_id, *, lock=False):
    statement = select(plans).where(plans.c.id == plan_id, plans.c.patient_id == ident)
    if lock:
        statement = statement.with_for_update()
    row = connection.execute(statement).mappings().first()
    if not row:
        raise DomainError(404, "RESOURCE_NOT_FOUND", "找不到这个方案")
    return dict(row)


def install_workbench(app, db, caller, patient_scope, base):
    def authorized(connection, request, ident, *, write=False, doctor=False, contact=False):
        actor, _ = caller(request, connection, write=write, doctor=doctor)
        # The same stable row is locked by grant changes and all workbench writes.
        # A concurrent revocation cannot slip between authorization and a write.
        if write:
            connection.execute(select(patients.c.id).where(patients.c.id == ident).with_for_update()).first()
        patient_scope(connection, actor, ident)
        if contact and not connection.scalar(select(grants.c.enabled).where(grants.c.patient_id == ident)):
            raise DomainError(403, "DOCTOR_ACCESS_REQUIRED", "请先开启工作台医生授权")
        return actor

    @app.get(base + "/care/actions")
    def actions(request: Request, search: str = "", limit: int = 30, offset: int = 0):
        if len(search) > 80 or not 1 <= limit <= 100 or offset < 0:
            raise DomainError(422, "VALIDATION_ERROR", "查询范围无效")
        with db.transaction() as connection:
            caller(request, connection, doctor=True)
        query = search.strip().casefold()
        rows = [r for r in action_library().values() if query in (r["exercise_id"] + " " + r["name"]).casefold()]
        return {"items": [action_public(r) for r in rows[offset:offset + limit]], "total": len(rows),
            "offset": offset, "limit": limit, "source": "EXISTING_MEASUREMENT_CONTRACTS"}

    @app.get(base + "/patients/{ident}/messages")
    def read_messages(ident: str, request: Request, after: int = 0, limit: int = 50,
                      latest: bool = False, before: int | None = None):
        if after < 0 or not 1 <= limit <= 100 or before is not None and before < 1:
            raise DomainError(422, "VALIDATION_ERROR", "查询范围无效")
        with db.transaction() as connection:
            actor = authorized(connection, request, ident)
            statement = select(messages).where(messages.c.patient_id == ident)
            reverse = latest or before is not None
            if before is not None:
                statement = statement.where(messages.c.sequence < before)
            elif not latest:
                statement = statement.where(messages.c.sequence > after)
            statement = statement.order_by(messages.c.sequence.desc() if reverse else messages.c.sequence.asc()).limit(limit + 1)
            rows = [dict(row) for row in connection.execute(statement).mappings()]
            more = len(rows) > limit
            rows = rows[:limit]
            if reverse:
                rows.reverse()
            return {"items": rows, "next_cursor": rows[-1]["sequence"] if rows else after,
                "has_more": more if not reverse else False,
                "previous_cursor": rows[0]["sequence"] if rows else None,
                "has_older": more if reverse else False, **read_status(connection, actor, ident)}

    @app.post(base + "/patients/{ident}/messages/read")
    def mark_read(ident: str, value: MessageRead, request: Request):
        with db.transaction() as connection:
            actor = authorized(connection, request, ident, write=True)
            prior, fingerprint = prior_operation(connection, actor, ident, "message.read", None, value)
            if prior:
                return prior
            maximum = connection.scalar(select(func.max(messages.c.sequence)).where(messages.c.patient_id == ident)) or 0
            if value.cursor > maximum:
                raise DomainError(422, "READ_CURSOR_INVALID", "不能标记尚未收到的消息为已读")
            condition = (message_reads.c.patient_id == ident) & (message_reads.c.actor_id == actor["id"])
            old = connection.execute(select(message_reads).where(condition)).mappings().first()
            changes = {"cursor": max(value.cursor, old["cursor"] if old else 0), "read_at": int(time.time())}
            if old:
                connection.execute(update(message_reads).where(condition).values(**changes))
            else:
                connection.execute(message_reads.insert().values(patient_id=ident, actor_id=actor["id"], **changes))
            return commit_operation(connection, actor, ident, "message.read", value, fingerprint,
                {"resource_id": ident, **read_status(connection, actor, ident)})

    @app.get(base + "/patients/{ident}/records/latest")
    def projected_records(ident: str, request: Request, offset: int = 0, limit: int = 30):
        if offset < 0 or not 1 <= limit <= 100:
            raise DomainError(422, "VALIDATION_ERROR", "查询范围无效")
        with db.transaction() as connection:
            authorized(connection, request, ident)
            rows = latest_records(connection, ident)
            if app.state.settings.environment == "production":
                from .real_data import synthetic
                rows = [r for r in rows if not synthetic(r["payload"])]
            return {"items": rows[offset:offset + limit], "total": len(rows), "offset": offset, "limit": limit}

    @app.get(base + "/patients/{ident}/rehab-summary")
    def rehab_summary(ident: str, request: Request):
        with db.transaction() as connection:
            authorized(connection, request, ident)
            rows = latest_records(connection, ident)
            if app.state.settings.environment == "production":
                from .real_data import synthetic
                rows = [r for r in rows if not synthetic(r["payload"])]
            return {kind: [r for r in rows if r["payload"].get("kind") == kind]
                for kind in ("profile", "assessment", "training", "rehab_plan")}

    @app.post(base + "/patients/{ident}/messages", status_code=201)
    def send_message(ident: str, value: MessageInput, request: Request):
        clean_text = text(value.text, "消息")
        with db.transaction() as connection:
            actor = authorized(connection, request, ident, write=True, contact=True)
            prior, fingerprint = prior_operation(connection, actor, ident, "message.send", None, value)
            if prior:
                return prior
            sequence = (connection.scalar(select(func.max(messages.c.sequence)).where(messages.c.patient_id == ident)) or 0) + 1
            item = {"id": str(uuid4()), "patient_id": ident, "sequence": sequence,
                "author_id": actor["id"], "author_role": actor["role"], "text": clean_text, "created_at": int(time.time())}
            connection.execute(messages.insert().values(**item))
            from .care_queue import opened
            opened(connection, item)
            return commit_operation(connection, actor, ident, "message.send", value, fingerprint,
                {"resource_id": item["id"], "item": item})

    @app.get(base + "/patients/{ident}/plans")
    def read_plans(ident: str, request: Request, offset: int = 0, limit: int = 30):
        if offset < 0 or not 1 <= limit <= 100:
            raise DomainError(422, "VALIDATION_ERROR", "查询范围无效")
        with db.transaction() as connection:
            actor = authorized(connection, request, ident)
            condition = plans.c.patient_id == ident
            if actor["role"] != "DOCTOR_ADMIN":
                condition &= plans.c.status == "PUBLISHED"
            rows = connection.execute(select(plans).where(condition).order_by(plans.c.updated_at.desc(),
                plans.c.id).offset(offset).limit(limit)).mappings()
            active = current(connection, ident)
            from .plan_programmes import enrich
            return {"items": [enrich(connection, row, execution=actor["role"] == "PATIENT") for row in rows],
                "total": connection.scalar(select(func.count()).select_from(plans).where(condition)),
                "current_plan_id": active["plan_id"] if active else None,
                "current_revision": active["revision"] if active else 0, "offset": offset, "limit": limit}

    @app.get(base + "/patients/{ident}/plans/current")
    def current_plan(ident: str, request: Request):
        with db.transaction() as connection:
            authorized(connection, request, ident)
            active = current(connection, ident)
            from .plan_programmes import enrich
            return {"plan": enrich(connection, get_plan(connection, ident, active["plan_id"]), execution=True) if active else None,
                "current_revision": active["revision"] if active else 0,
                "accepted_at": active["accepted_at"] if active else None,
                "local_validation": active["local_validation"] if active else None}

    @app.post(base + "/patients/{ident}/plans", status_code=201)
    def create_plan(ident: str, value: PlanInput, request: Request):
        document = plan_document(value)
        from .plan_programmes import validate_programme, save_programme, enrich
        programme = validate_programme(value.programme)
        with db.transaction() as connection:
            actor = authorized(connection, request, ident, write=True, doctor=True)
            prior, fingerprint = prior_operation(connection, actor, ident, "plan.create", None, value)
            if prior:
                return prior
            if value.parent_plan_id:
                parent = get_plan(connection, ident, value.parent_plan_id)
                if parent["status"] != "PUBLISHED":
                    raise DomainError(409, "PLAN_NOT_PUBLISHED", "修改已发布方案时才创建新版本")
            now = int(time.time())
            plan = {"id": str(uuid4()), "patient_id": ident, "author_id": actor["id"],
                "parent_plan_id": value.parent_plan_id, **document, "status": "DRAFT", "version": 1,
                "publication_sequence": None, "created_at": now, "updated_at": now, "published_at": None}
            connection.execute(plans.insert().values(**plan))
            save_programme(connection, plan["id"], programme)
            plan = enrich(connection, plan)
            return commit_operation(connection, actor, ident, "plan.create", value, fingerprint,
                {"resource_id": plan["id"], "plan": plan})

    @app.put(base + "/patients/{ident}/plans/{plan_id}")
    def edit_plan(ident: str, plan_id: str, value: PlanUpdate, request: Request):
        document = plan_document(value)
        from .plan_programmes import validate_programme, save_programme, programmes, enrich
        programme = validate_programme(value.programme)
        with db.transaction() as connection:
            actor = authorized(connection, request, ident, write=True, doctor=True)
            prior, fingerprint = prior_operation(connection, actor, ident, "plan.edit", plan_id, value)
            if prior:
                return prior
            plan = get_plan(connection, ident, plan_id, lock=True)
            if plan["version"] != value.expected_version:
                raise DomainError(412, "REVISION_MISMATCH", "方案已更新，请刷新后再编辑")
            if plan["status"] != "DRAFT":
                raise DomainError(409, "PLAN_IMMUTABLE", "已发布方案保留原文，请创建新版本")
            if value.parent_plan_id != plan["parent_plan_id"]:
                raise DomainError(422, "PLAN_PARENT_IMMUTABLE", "方案来源不能在编辑时改变")
            changes = {**document, "version": plan["version"] + 1, "updated_at": int(time.time())}
            connection.execute(update(plans).where(plans.c.id == plan_id).values(**changes))
            from sqlalchemy import delete
            connection.execute(delete(programmes).where(programmes.c.plan_id == plan_id))
            save_programme(connection, plan_id, programme)
            plan.update(changes)
            plan = enrich(connection, plan)
            return commit_operation(connection, actor, ident, "plan.edit", value, fingerprint,
                {"resource_id": plan_id, "plan": plan})

    @app.post(base + "/patients/{ident}/plans/{plan_id}/publish")
    def publish_plan(ident: str, plan_id: str, value: PlanTransition, request: Request):
        with db.transaction() as connection:
            actor = authorized(connection, request, ident, write=True, doctor=True)
            prior, fingerprint = prior_operation(connection, actor, ident, "plan.publish", plan_id, value)
            if prior:
                return prior
            plan = get_plan(connection, ident, plan_id, lock=True)
            if plan["version"] != value.expected_version:
                raise DomainError(412, "REVISION_MISMATCH", "方案已更新，请刷新后再发布")
            if plan["status"] != "DRAFT":
                raise DomainError(409, "PLAN_IMMUTABLE", "这个方案已经发布")
            sequence = (connection.scalar(select(func.max(plans.c.publication_sequence)).where(plans.c.patient_id == ident)) or 0) + 1
            now = int(time.time())
            changes = {"status": "PUBLISHED", "version": plan["version"] + 1,
                "publication_sequence": sequence, "published_at": now, "updated_at": now}
            connection.execute(update(plans).where(plans.c.id == plan_id).values(**changes))
            plan.update(changes)
            from .plan_programmes import enrich
            plan = enrich(connection, plan)
            return commit_operation(connection, actor, ident, "plan.publish", value, fingerprint,
                {"resource_id": plan_id, "plan": plan})

    @app.post(base + "/patients/{ident}/plans/{plan_id}/accept")
    def accept_plan(ident: str, plan_id: str, value: PlanAcceptance, request: Request):
        with db.transaction() as connection:
            actor = authorized(connection, request, ident, write=True, contact=True)
            if actor["role"] != "PATIENT":
                raise DomainError(403, "PATIENT_REQUIRED", "请由本人确认采用方案")
            prior, fingerprint = prior_operation(connection, actor, ident, "plan.accept", plan_id, value)
            if prior:
                return prior
            plan = get_plan(connection, ident, plan_id, lock=True)
            from .plan_programmes import enrich
            plan = enrich(connection, plan, execution=True)
            if plan.get("execution_status") in {"STOPPED", "REST_DAY", "MANUAL_ONLY"}:
                raise DomainError(409, "PLAN_NOT_EXECUTABLE", "方案已停用、当前为休息日或需人工执行，请先联系医生核对")
            if plan["status"] != "PUBLISHED":
                raise DomainError(404, "RESOURCE_NOT_FOUND", "找不到可采用的方案")
            if plan["version"] != value.expected_version:
                raise DomainError(412, "REVISION_MISMATCH", "方案已更新，请刷新后确认")
            latest = connection.scalar(select(func.max(plans.c.publication_sequence)).where(plans.c.patient_id == ident))
            if plan["publication_sequence"] != latest:
                raise DomainError(412, "PLAN_SUPERSEDED", "医生已发布更新的方案，请先查看最新版")
            active = current(connection, ident)
            revision = active["revision"] if active else 0
            if revision != value.expected_current_revision:
                raise DomainError(412, "REVISION_MISMATCH", "当前方案已更新，请刷新后确认")
            changes = {"plan_id": plan_id, "accepted_version": plan["version"],
                "revision": revision + 1, "accepted_at": int(time.time()),
                "local_validation": validate_adoption(plan, value.local_validation)}
            if active:
                connection.execute(update(current_plans).where(current_plans.c.patient_id == ident).values(**changes))
            else:
                connection.execute(current_plans.insert().values(patient_id=ident, **changes))
            return commit_operation(connection, actor, ident, "plan.accept", value, fingerprint,
                {"resource_id": plan_id, "plan": plan, "current_revision": revision + 1,
                    "local_validation": changes["local_validation"]})
