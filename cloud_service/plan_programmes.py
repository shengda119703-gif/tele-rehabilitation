"""Immutable phased schedules; suspension is an explicit separate clinical action."""
from datetime import datetime, timedelta, timezone
import time

from fastapi import Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Boolean, Column, ForeignKey, Integer, JSON, String, Table, select

from .database import metadata, patients
from .security import DomainError, audited

programmes = Table("care_plan_programmes", metadata, Column("plan_id", String(36), ForeignKey("workbench_plans.id"), primary_key=True),
                   Column("document", JSON, nullable=False))
stops = Table("care_plan_stops", metadata, Column("plan_id", String(36), ForeignKey("workbench_plans.id"), primary_key=True),
              Column("reason", String(1000), nullable=False), Column("stopped_at", Integer, nullable=False), Column("actor_id", String(36), nullable=False))


def day_today():
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def validate_programme(document):
    if document is None:
        return None
    from .workbench import PlanInput, plan_document
    if not isinstance(document, dict) or set(document) != {"start_date", "phases"} or not isinstance(document["phases"], list) or not 1 <= len(document["phases"]) <= 12:
        raise DomainError(422, "PROGRAMME_INVALID", "请填写开始日期和1至12个训练阶段")
    def date(text):
        try:
            if not isinstance(text, str) or datetime.strptime(text, "%Y-%m-%d").strftime("%Y-%m-%d") != text:
                raise ValueError()
            return datetime.strptime(text, "%Y-%m-%d").date()
        except (TypeError, ValueError):
            raise DomainError(422, "PROGRAMME_INVALID", "阶段日期需使用 YYYY-MM-DD") from None
    start = date(document["start_date"])
    previous = start - timedelta(days=1)
    clean = []
    for phase in document["phases"]:
        if not isinstance(phase, dict) or set(phase) != {"name", "until_date", "weekdays", "items", "equipment", "load", "manual_only"}:
            raise DomainError(422, "PROGRAMME_INVALID", "阶段需包含日期、训练日、动作顺序、器材和负重说明")
        end = date(phase["until_date"])
        days = phase["weekdays"]
        if end <= previous or (end-start).days > 365 or not isinstance(days, list) or not days or len(set(days)) != len(days) or any(type(d) is not int or d not in range(1,8) for d in days):
            raise DomainError(422, "PROGRAMME_INVALID", "阶段日期需递增，训练日使用周一1至周日7")
        if any(not isinstance(phase[k], str) or len(phase[k]) > 500 for k in ("name", "equipment", "load")) or not phase["name"].strip() or type(phase["manual_only"]) is not bool:
            raise DomainError(422, "PROGRAMME_INVALID", "阶段名称、器材和负重说明无效")
        if phase["load"].strip() and not phase["manual_only"]:
            raise DomainError(422, "PROGRAMME_UNSUPPORTED_LOAD", "软件尚不能核验负重处方；负重阶段须标记仅人工执行")
        supported = {"", "无附加器材", "稳固椅", "无轮稳固椅", "稳定桌面", "硬床", "垫", "滑布", "稳定支撑"}
        if phase["equipment"].strip() not in supported and not phase["manual_only"]:
            raise DomainError(422, "PROGRAMME_UNSUPPORTED_EQUIPMENT", "软件不能核验这个器材变体；请标记仅人工执行并由医生核对")
        try:
            value = PlanInput(operation_id="00000000-0000-0000-0000-000000000001", title=phase["name"], summary="", items=phase["items"])
            normalized = plan_document(value)["items"]
        except (ValueError, TypeError):
            raise DomainError(422, "PROGRAMME_INVALID", "阶段动作与本机支持情况不一致") from None
        # Retain normalized public settings; PlanItem input shape is rebuilt when
        # a programme is edited, never trust keys supplied by an old client.
        clean.append({**phase, "items": normalized, "from_date": (previous + timedelta(days=1)).isoformat()})
        previous = end
    return {"start_date": start.isoformat(), "phases": clean}


def enrich(connection, plan, execution=False):
    plan = dict(plan)
    stopped = connection.execute(select(stops).where(stops.c.plan_id == plan["id"])).mappings().first()
    stored = connection.scalar(select(programmes.c.document).where(programmes.c.plan_id == plan["id"]))
    if stopped:
        plan["execution_status"] = "STOPPED"
        plan["stop_reason"] = stopped["reason"]
        plan["stopped_at"] = stopped["stopped_at"]
    if stored:
        plan["programme"] = stored
        if execution:
            today = day_today()
            phase = next((p for p in stored["phases"] if p["from_date"] <= today <= p["until_date"]), None)
            plan["execution_date"] = today
            plan["all_items"] = plan["items"]
            if not phase or datetime.fromisoformat(today).isoweekday() not in phase["weekdays"]:
                plan["items"] = []
                plan.setdefault("execution_status", "REST_DAY")
            else:
                plan["items"] = phase["items"]
                plan["phase_name"] = phase["name"]
                plan.setdefault("execution_status", "MANUAL_ONLY" if phase["manual_only"] else "READY")
    return plan


def save_programme(connection, plan_id, document):
    if document is not None:
        connection.execute(programmes.insert().values(plan_id=plan_id, document=document))


class Stop(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=1000)


def install_programmes(app, db, caller, patient_scope, base):
    @app.post(base + "/patients/{ident}/plans/{plan_id}/stop")
    def stop(ident: str, plan_id: str, value: Stop, request: Request):
        from .workbench import get_plan
        with db.transaction() as connection:
            actor, _ = caller(request, connection, write=True, doctor=True)
            connection.execute(select(patients.c.id).where(patients.c.id == ident).with_for_update()).first()
            patient_scope(connection, actor, ident)
            plan = get_plan(connection, ident, plan_id, lock=True)
            if plan["version"] != value.expected_version:
                raise DomainError(412, "REVISION_MISMATCH", "方案已更新，请刷新")
            if plan["status"] != "PUBLISHED":
                raise DomainError(409, "PLAN_NOT_PUBLISHED", "只有已发布方案需要停用")
            if not connection.execute(select(stops).where(stops.c.plan_id == plan_id)).first():
                if not value.reason.strip():
                    raise DomainError(422, "VALIDATION_ERROR", "请填写停用原因")
                connection.execute(stops.insert().values(plan_id=plan_id, reason=value.reason.strip(), stopped_at=int(time.time()), actor_id=actor["id"]))
                audited(connection, actor["id"], "plan.stop", plan_id)
            return {"status": "COMMITTED", "plan": enrich(connection, plan)}
