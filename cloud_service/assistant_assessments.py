"""Owner-scoped measurement appointments, never diagnoses or training doses.

The model cannot choose arbitrary task IDs or write results. Only the frozen
server dialogue route creates appointments; completion is a projection of real
subsequent uploads. Scheduling never enables a camera or changes a prescription.
"""
from datetime import datetime
import time
import math
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field
from uuid import UUID

from sqlalchemy import CheckConstraint, Column, ForeignKey, Integer, JSON, String, Table, select, update

from .database import metadata, records as record_events
from .real_data import synthetic
from .security import DomainError, audited
from .workbench import action_library, latest_records

VERSION = "online-assessment-routing-2"
plans = Table("assistant_assessment_plans", metadata,
    Column("id", String(36), primary_key=True),
    Column("patient_id", String(36), ForeignKey("patients.id"), nullable=False, index=True),
    Column("source_turn_id", String(36), ForeignKey("assistant_turns.id"), nullable=False, unique=True),
    Column("title", String(100), nullable=False),
    Column("region", String(20), nullable=False),
    Column("items", JSON, nullable=False),
    Column("baseline_record_ids", JSON, nullable=False),
    Column("status", String(20), nullable=False),
    Column("routing_version", String(60), nullable=False),
    Column("created_at", Integer, nullable=False),
    CheckConstraint("status IN ('PLANNED','CANCELLED')"))

# Explicit supported mappings, not names guessed by the provider. These are
# low-load observations within a comfortable range, not provocative testing.
LEGACY_TASKS = {
    "肩": ("shoulder_abduction", "shoulder_flexion"),
    "肘": ("elbow_flexion", "elbow_extension"),
    "腕": ("wrist_flexion", "wrist_extension"),
    "髋": ("hip_flexion",), "膝": ("knee_extension",),
    "踝": ("ankle_dorsiflexion",), "颈": ("neck_lateral_flexion",),
    "躯干": ("sit_to_stand",),
}
TASKS = {**LEGACY_TASKS, "躯干":("sit_to_stand", "knee_extension", "ankle_dorsiflexion"),
         "髋":("hip_flexion", "hip_abduction"), "膝":("knee_extension", "knee_flexion"),
         "踝":("ankle_dorsiflexion", "ankle_plantarflexion")}


class ResultLink(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    item_index: int = Field(ge=0, le=3)
    record_id: UUID = Field(strict=False)


def appointment_items(spec, text):
    library = action_library()
    if "assessment_items" in spec:
        frozen = spec["assessment_items"]
        if not isinstance(frozen, list) or len(frozen) > 4:
            return []
        return [dict(item) for item in frozen if isinstance(item, dict) and item.get("exercise_id") in library and not library[item["exercise_id"]]["experimental"]]
    side = "left" if "左" in text and "右" not in text else "right" if "右" in text and "左" not in text else "choose"
    items = []
    mapping = LEGACY_TASKS if spec.get("version") in {"rehab-dialogue-2", "rehab-dialogue-3"} else TASKS
    for ident in mapping.get(spec.get("region"), ()):
        card = library.get(ident)
        if card and not card["experimental"]:
            items.append({"exercise_id": ident, "name": card["name"],
                          "side": "choose" if ident == "sit_to_stand" else side,
                          "instruction": "仅在舒适、不加重不适的范围观察；不负重、不追求最大幅度。不适加重就停止。",
                          "record_id": None})
    return items


def schedule(connection, patient_id, turn_id, spec, text, now=None):
    if not spec.get("assessment_ready") or spec.get("intake_stage") != "ONLINE_ASSESSMENT":
        return None
    items = appointment_items(spec, text)
    if not items:
        return None
    # Repeated questions reuse the same unfinished appointment. A cancelled or
    # actually completed appointment is not silently resurrected.
    rows = connection.execute(select(plans).where(plans.c.patient_id == patient_id, plans.c.status == "PLANNED")
                              .order_by(plans.c.created_at.desc()).limit(100)).mappings()
    records = None
    for row in rows:
        shape = lambda entries:[{**entry,"record_id":None} for entry in entries]
        if row["region"] == spec["region"] and row["routing_version"] == spec.get("assessment_routing_version",VERSION) and shape(row["items"]) == shape(items):
            records = latest_records(connection, patient_id) if records is None else records
            if document(row, records)["status"] != "COMPLETED":
                return dict(row)
    value = {"id": str(uuid4()), "patient_id": patient_id, "source_turn_id": turn_id,
             "title": spec["region"] + "线上评估", "region": spec["region"], "items": items,
             "baseline_record_ids": [record["id"] for record in latest_records(connection, patient_id)],
             "status": "PLANNED", "routing_version": spec.get("assessment_routing_version", "online-assessment-routing-1" if spec.get("version") == "rehab-dialogue-3" else VERSION), "created_at": int(time.time()) if now is None else now}
    connection.execute(plans.insert().values(**value))
    return value


def _timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result.timestamp() if result.tzinfo else None
    except (ValueError, OverflowError):
        return None


def valid_record(row, item, record):
    if record["id"] in row["baseline_record_ids"]:
        return False
    payload = record["payload"]
    facts = payload.get("result") or {}
    if (not isinstance(facts, dict) or record["patient_id"] != row["patient_id"]
            or payload.get("patient_id") != row["patient_id"] or payload.get("schema") != "ankang-workbench-record-1"
            or payload.get("kind") != "assessment" or synthetic(payload) or synthetic(facts)
            or facts.get("exercise_id") != item["exercise_id"]
            or facts.get("side") not in ({"left", "right", "bilateral"} if item["side"] == "choose" else {item["side"]})):
        return False
    end = _timestamp(facts.get("end_utc"));summary = facts.get("summary") or {}
    if (end is None or end < row["created_at"] or end > time.time()+5 or record["received_at"] < row["created_at"] or not isinstance(summary,dict)):
        return False
    count = summary.get("completed");ratio=summary.get("valid_ratio")
    if (type(count) not in {int,float} or not math.isfinite(count) or count <= 0 or int(count) != count
            or facts.get("status") not in {None,"ASSESSED","COMPLETED","DONE","done"}
            or type(ratio) in {int,float} and (not math.isfinite(ratio) or ratio <= 0)):
        return False
    if row["routing_version"] == VERSION:
        # Current appointments only accept the existing completed video engine,
        # not a self-reported number or a chat-generated estimate.
        if (record["source_kind"] not in {"APK_LOCAL","WEB_LOCAL","DESKTOP_LOCAL"}
                or facts.get("analysis_state") != "done"
                or facts.get("measurement_version") != "android-local-projection-1"):
            return False
    return True


def document(row, records):
    # record_heads is for latest displays; explicit links keep their immutable
    # event even if a later unrelated upload revises that record key.
    records=[{**r,"patient_id":r.get("patient_id",r["payload"].get("patient_id"))} for r in records]
    items = []
    for item in row["items"]:
        record_id = None
        for record in records:
            if row["routing_version"] == VERSION:
                if record["id"] != item.get("record_id") or not valid_record(row,item,record):
                    continue
                record_id=record["id"]
                break
            if record["id"] in row["baseline_record_ids"]:
                continue
            payload = record["payload"]
            facts = payload.get("result") or {}
            if (not isinstance(facts, dict) or payload.get("patient_id") != row["patient_id"]
                    or payload.get("schema") != "ankang-workbench-record-1" or payload.get("kind") != "assessment"
                    or synthetic(payload) or synthetic(facts) or facts.get("exercise_id") != item["exercise_id"]
                    or facts.get("side") not in ({"left", "right", "bilateral"} if item["side"] == "choose" else {item["side"]})):
                continue
            end = _timestamp(facts.get("end_utc"))
            summary = facts.get("summary") or {}
            # Upload order, not a client-supplied future date, proves that this
            # result arrived after scheduling. It is still client-declared data.
            if (end is None or end < row["created_at"] or end > time.time() + 5
                    or record.get("received_at", 0) < row["created_at"] or not isinstance(summary, dict)):
                continue
            count = summary.get("completed")
            if (type(count) not in {int, float} or not math.isfinite(count) or count <= 0 or int(count) != count
                    or facts.get("status") not in {None, "ASSESSED", "COMPLETED", "DONE", "done"}
                    or type(summary.get("valid_ratio")) in {int, float} and summary["valid_ratio"] <= 0):
                continue
            record_id = record["id"]
            break
        result = None
        if record_id:
            record = next(r for r in records if r["id"] == record_id)
            summary = record["payload"]["result"]["summary"]
            motion = summary.get("motion_range") or {}
            motion = motion if isinstance(motion,dict) else {}
            result = {"completed":summary["completed"], "angle_kind":"2D_PROJECTED"}
            for key in ("max_deg","min_deg","range_deg"):
                value = motion.get(key)
                result[key] = value if type(value) in {int,float} and math.isfinite(value) else None
        items.append({**item, "record_id": record_id, "result": result})
    status = row["status"]
    if status == "PLANNED" and items and all(item["record_id"] for item in items):
        status = "COMPLETED"
    return {key: row[key] for key in ("id", "title", "source_turn_id", "created_at", "routing_version")} | {"status": status, "items": items, "next_index":next((i for i,item in enumerate(items) if not item["record_id"]),None)}


def plan_records(connection, ident, rows):
    values={r["id"]:r for r in latest_records(connection,ident)}
    linked={item.get("record_id") for row in rows for item in row["items"] if item.get("record_id")}
    if linked:
        for record in connection.execute(select(record_events).where(record_events.c.patient_id==ident,record_events.c.id.in_(linked))).mappings():
            values[record["id"]]=dict(record)
    return list(values.values())


def pause_pending(connection, patient_id):
    rows = list(connection.execute(select(plans).where(plans.c.patient_id == patient_id, plans.c.status == "PLANNED")).mappings())
    records = plan_records(connection, patient_id, rows)
    ids = [row["id"] for row in rows if document(row, records)["status"] != "COMPLETED"]
    if ids:
        connection.execute(update(plans).where(plans.c.id.in_(ids)).values(status="CANCELLED"))


def install(app, db, authorize, base):
    from fastapi import Request

    @app.get(base + "/patients/{ident}/assistant/assessment-plans")
    def listing(ident: str, request: Request):
        with db.transaction() as connection:
            authorize(connection, request, ident)
            rows = list(connection.execute(select(plans).where(plans.c.patient_id == ident)
                                      .order_by(plans.c.created_at.desc(), plans.c.id).limit(100)).mappings())
            records = plan_records(connection, ident, rows)
            return {"items": [document(row, records) for row in rows]}

    @app.post(base + "/patients/{ident}/assistant/assessment-plans/{plan_id}/cancel")
    def cancel(ident: str, plan_id: str, request: Request):
        with db.transaction() as connection:
            actor = authorize(connection, request, ident, True)
            row = connection.execute(select(plans).where(plans.c.id == plan_id, plans.c.patient_id == ident)
                                     .with_for_update()).mappings().first()
            if not row:
                raise DomainError(404, "NOT_FOUND", "评估计划不存在")
            if row["status"] != "CANCELLED":
                connection.execute(update(plans).where(plans.c.id == plan_id).values(status="CANCELLED"))
                audited(connection, actor["id"], "assistant.assessment.cancel", plan_id)
            return {"id": plan_id, "status": "CANCELLED"}

    @app.post(base + "/patients/{ident}/assistant/assessment-plans/{plan_id}/results")
    def link_result(ident: str, plan_id: str, value: ResultLink, request: Request):
        from .assistant import memory as assistant_memory
        with db.transaction() as connection:
            actor=authorize(connection,request,ident,True)
            row=connection.execute(select(plans).where(plans.c.id==plan_id,plans.c.patient_id==ident).with_for_update()).mappings().first()
            if not row:
                raise DomainError(404,"NOT_FOUND","评估计划不存在")
            if value.item_index >= len(row["items"]):
                raise DomainError(409,"ASSESSMENT_PLAN_CHANGED","评估计划已取消或项目已变化")
            items=[dict(item) for item in row["items"]];item=items[value.item_index];record_id=str(value.record_id)
            if item.get("record_id"):
                if item["record_id"] != record_id:
                    raise DomainError(409,"ASSESSMENT_RESULT_CONFLICT","此项已有不同评估结果")
            else:
                if row["status"] != "PLANNED":
                    raise DomainError(409,"ASSESSMENT_PLAN_CHANGED","评估计划已取消")
                if value.item_index != next((i for i,part in enumerate(items) if not part.get("record_id")),None):
                    raise DomainError(409,"ASSESSMENT_ORDER_REQUIRED","请先完成上一项评估并保存结果")
                hold=connection.scalar(select(assistant_memory.c.document).where(assistant_memory.c.patient_id==ident)) or {}
                if hold.get("safety_hold"):
                    raise DomainError(409,"ASSESSMENT_SAFETY_REVIEW","当前需要先完成医疗核对，暂不继续动作评估")
                record=connection.execute(select(record_events).where(record_events.c.id==record_id,record_events.c.patient_id==ident)).mappings().first()
                if not record or not valid_record(row,item,record):
                    raise DomainError(422,"ASSESSMENT_RESULT_INVALID","需要本项已完成的真实视频分析结果，不能用自述、旧结果或其他动作替代")
                item["record_id"]=record_id
                connection.execute(update(plans).where(plans.c.id==plan_id).values(items=items))
                audited(connection,actor["id"],"assistant.assessment.result",plan_id)
            saved={**row,"items":items}
            linked=list(connection.execute(select(record_events).where(record_events.c.patient_id==ident,record_events.c.id.in_([part['record_id'] for part in items if part.get('record_id')]))).mappings())
            return {"status":"COMMITTED","record_id":record_id,"plan":document(saved,linked)}
