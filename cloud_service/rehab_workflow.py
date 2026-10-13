"""Shared resource filters and clinician review requests, without model calls.

Uploaded assessments remain client-declared evidence. Actual plan adoption and
camera start use the device's existing, stricter assessment/measurement rules.
"""
from functools import lru_cache
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Literal
from uuid import UUID, uuid4

from fastapi import Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Column, ForeignKey, Integer, JSON, String, Table, UniqueConstraint, select, update

from .database import grants, metadata, patients
from .security import DomainError, audited, digest
from .real_data import synthetic
from .workbench import action_library, latest_records, current, get_plan

preferences = Table("care_rehab_preferences", metadata, Column("patient_id", String(36), ForeignKey("patients.id"), primary_key=True),
                    Column("version", Integer, nullable=False), Column("document", JSON, nullable=False))
candidates = Table("care_rehab_candidates", metadata, Column("id", String(36), primary_key=True),
                   Column("patient_id", String(36), ForeignKey("patients.id"), nullable=False, index=True),
                   Column("operation_id", String(36), nullable=False), Column("fingerprint", String(64), nullable=False),
                   Column("document", JSON, nullable=False), Column("state", String(20), nullable=False),
                   Column("created_at", Integer, nullable=False), Column("reviewed_at", Integer),
                   UniqueConstraint("patient_id", "operation_id"))


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_version: int = Field(ge=0)
    goal: str = Field(min_length=1, max_length=500)
    region: Literal["肩", "肘", "腕", "髋", "膝", "踝", "颈", "躯干", "一般活动"]
    level: int = Field(ge=0, le=3)
    equipment: list[str] = Field(max_length=20)
    restrictions: list[str] = Field(max_length=20)
    screening_confirmed: bool


class CandidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    operation_id: UUID = Field(strict=False)
    kind: Literal["STARTER", "PROGRESSION"] = "STARTER"


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    decision: Literal["REVIEWED", "REJECTED"]


@lru_cache(maxsize=1)
def resources():
    return json.loads(Path(__file__).with_name("rehab_resources.json").read_text(encoding="utf-8"))


def workflow(connection, ident):
    profile = connection.execute(select(preferences).where(preferences.c.patient_id == ident)).mappings().first()
    real = [r for r in latest_records(connection, ident) if not synthetic(r["payload"])]
    assessments = [r for r in real if r["payload"].get("kind") == "assessment"]
    active = current(connection, ident)
    programme = get_plan(connection, ident, active["plan_id"]) if active else None
    if programme:
        from .plan_programmes import enrich
        programme = enrich(connection, programme, execution=True)
    region = profile["document"]["region"] if profile else None
    suggested = [r for r in action_library().values() if region and region in r["name"] and not r["experimental"]]
    return {"profile": profile["document"] if profile else None, "profile_version": profile["version"] if profile else 0,
            "suggested_assessments": suggested, "assessment_records": assessments[:20], "assessment_record_count": len(assessments),
            "current_plan": programme, "read_only": True, "automatic_execution": False,
            "steps": ["填写或复用目标、器材和限制", "本人确认后在原康复页面评估", "保存真实评估并同步", "查看规则候选并由医生核对", "本人采用后按原训练规则开始"],
            "assessment_note": "仅描述已有二维测量；不推断肌力、疾病或专业临床等级。当前方案优先，不由问答覆盖。"}


def install_workflow(app, db, caller, patient_scope, base):
    def authorize(connection, request, ident, write=False, owner=False):
        actor, _ = caller(request, connection, write=write)
        if write:
            connection.execute(select(patients.c.id).where(patients.c.id == ident).with_for_update()).first()
        patient_scope(connection, actor, ident)
        if owner and actor["role"] != "PATIENT":
            raise DomainError(403, "PATIENT_REQUIRED", "请由本人填写或请求评估核对")
        return actor

    @app.get(base + "/patients/{ident}/rehab-workflow")
    def get_workflow(ident: str, request: Request):
        with db.transaction() as connection:
            authorize(connection, request, ident)
            return workflow(connection, ident)

    @app.put(base + "/patients/{ident}/rehab-workflow/profile")
    def save_profile(ident: str, value: Profile, request: Request):
        if not value.goal.strip() or any(not s.strip() or len(s) > 500 for s in value.equipment + value.restrictions):
            raise DomainError(422, "VALIDATION_ERROR", "目标、器材和限制填写无效")
        with db.transaction() as connection:
            actor = authorize(connection, request, ident, True, True)
            previous = connection.execute(select(preferences).where(preferences.c.patient_id == ident)).mappings().first()
            version = previous["version"] if previous else 0
            if version != value.expected_version:
                raise DomainError(412, "REVISION_MISMATCH", "资料已经更新，请刷新复用最新资料")
            changes = {"version": version + 1, "document": value.model_dump(exclude={"expected_version"})}
            if previous:
                connection.execute(update(preferences).where(preferences.c.patient_id == ident).values(**changes))
            else:
                connection.execute(preferences.insert().values(patient_id=ident, **changes))
            audited(connection, actor["id"], "rehab.preferences", ident)
            return workflow(connection, ident)

    @app.post(base + "/patients/{ident}/rehab-candidates")
    def propose(ident: str, value: CandidateRequest, request: Request):
        with db.transaction() as connection:
            actor = authorize(connection, request, ident, True, True)
            fingerprint = digest(json.dumps(value.model_dump(mode="json"), sort_keys=True))
            old = connection.execute(select(candidates).where(candidates.c.patient_id == ident, candidates.c.operation_id == str(value.operation_id))).mappings().first()
            if old:
                if old["fingerprint"] != fingerprint:
                    raise DomainError(409, "IDEMPOTENCY_CONFLICT", "原候选请求已有不同内容")
                return dict(old)
            state = workflow(connection, ident)
            p = state["profile"]
            if not p or not p["screening_confirmed"]:
                raise DomainError(409, "PROFILE_REQUIRED", "请先填写目标、器材和限制，并核对适用条件")
            if p["restrictions"]:
                raise DomainError(409, "PROFESSIONAL_REVIEW_REQUIRED", "已填写限制，程序不能判断兼容性，请先联系医生")
            if not state["assessment_records"]:
                raise DomainError(409, "ASSESSMENT_REQUIRED", "请先在原康复页面完成并同步本人评估，不补造结果")
            if not connection.scalar(select(grants.c.enabled).where(grants.c.patient_id == ident)):
                raise DomainError(403, "DOCTOR_ACCESS_REQUIRED", "请先授权医生查看，再提交候选核对")
            if value.kind == "PROGRESSION" and not state["current_plan"]:
                raise DomainError(409, "CURRENT_PLAN_REQUIRED", "进阶需先有本人采用的医生方案")
            library = resources()
            matching = [r for r in library["rules"] if p["region"] in r["regions"] and r["level"] <= p["level"] and any(all(e in p["equipment"] for e in group) for group in r["equipmentAny"])]
            cards = [c for c in library["cards"] if any(r["id"] == c["id"] for r in matching) and c["complete"]]
            if not cards:
                raise DomainError(409, "NO_RULE_MATCH", "当前没有已映射的起始版本或器材，请联系医生安排")
            document = {"kind": value.kind, "engine": "shared-resource-rules-2", "profile_version": state["profile_version"],
                        "profile": p, "cards": cards[:3], "variants": matching, "assessment_record_ids": [r["id"] for r in state["assessment_records"]],
                        "parent_plan_id": state["current_plan"]["id"] if state["current_plan"] else None,
                        "automatic_execution": False, "model_calls": 0,
                        "note": "候选条件和源剂量范围，尚非个人处方。进阶不自动增加负重；医生需核对真实评估、反馈和动作支持后另建并发布方案。"}
            row = {"id": str(uuid4()), "patient_id": ident, "operation_id": str(value.operation_id), "fingerprint": fingerprint,
                   "document": document, "state": "PENDING_REVIEW", "created_at": int(time.time()), "reviewed_at": None}
            connection.execute(candidates.insert().values(**row))
            audited(connection, actor["id"], "rehab.candidate", row["id"])
            return row

    @app.get(base + "/patients/{ident}/rehab-candidates")
    def list_candidates(ident: str, request: Request, offset: int = 0):
        if offset < 0:
            raise DomainError(422, "VALIDATION_ERROR", "查询范围无效")
        with db.transaction() as connection:
            authorize(connection, request, ident)
            return {"items": [dict(r) for r in connection.execute(select(candidates).where(candidates.c.patient_id == ident).order_by(candidates.c.created_at.desc(), candidates.c.id).offset(offset).limit(30)).mappings()]}

    @app.post(base + "/patients/{ident}/rehab-candidates/{candidate_id}/review")
    def review(ident: str, candidate_id: str, value: Review, request: Request):
        with db.transaction() as connection:
            actor = authorize(connection, request, ident, True)
            if actor["role"] != "DOCTOR_ADMIN":
                raise DomainError(403, "DOCTOR_REQUIRED", "仅医生可核对候选")
            row = connection.execute(select(candidates).where(candidates.c.patient_id == ident, candidates.c.id == candidate_id)).mappings().first()
            if not row:
                raise DomainError(404, "RESOURCE_NOT_FOUND", "找不到候选")
            if row["state"] != "PENDING_REVIEW":
                if row["state"] == value.decision:
                    return {"status": "COMMITTED", "state": row["state"]}
                raise DomainError(409, "REVIEW_IMMUTABLE", "核对结论已保存，请提交新的候选")
            connection.execute(update(candidates).where(candidates.c.id == candidate_id).values(state=value.decision, reviewed_at=int(time.time())))
            audited(connection, actor["id"], "rehab.candidate." + value.decision.lower(), candidate_id)
            return {"status": "COMMITTED", "state": value.decision, "automatic_execution": False}
