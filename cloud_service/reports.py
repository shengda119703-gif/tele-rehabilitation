"""Patient-selected originals, without OCR, sent only with explicit sharing."""
import base64
import binascii
import time
from uuid import UUID, uuid4

from fastapi import Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Boolean, Column, ForeignKey, Integer, LargeBinary, String, Table, UniqueConstraint, select, update

from .database import metadata, patients
from .security import DomainError, audited, digest

reports = Table("care_report_originals", metadata,
    Column("id", String(36), primary_key=True), Column("patient_id", String(36), ForeignKey("patients.id"), nullable=False, index=True),
    Column("operation_id", String(36), nullable=False), Column("filename", String(120), nullable=False),
    Column("mime", String(40), nullable=False), Column("content", LargeBinary, nullable=False),
    Column("size", Integer, nullable=False), Column("sha256", String(64), nullable=False),
    Column("shared", Boolean, nullable=False), Column("version", Integer, nullable=False),
    Column("original_sharing", Boolean, nullable=False),
    Column("created_at", Integer, nullable=False), UniqueConstraint("patient_id", "operation_id"))


class Upload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    operation_id: UUID = Field(strict=False)
    filename: str = Field(min_length=1, max_length=120)
    mime: str
    data: str = Field(max_length=2800000)
    shared: bool


class Sharing(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_version: int = Field(ge=1)
    shared: bool


def report_metadata(row):
    return {k: row[k] for k in ("id", "filename", "mime", "size", "sha256", "shared", "version", "created_at")}


def install_reports(app, db, caller, patient_scope, base):
    def actor_for(connection, request, ident, write=False, owner=False):
        actor, _ = caller(request, connection, write=write)
        patient_scope(connection, actor, ident, write=write)
        if owner and actor["role"] != "PATIENT":
            raise DomainError(403, "PATIENT_REQUIRED", "请由患者本人选择并授权原件")
        return actor

    @app.post(base + "/patients/{ident}/reports", status_code=201)
    def upload(ident: str, value: Upload, request: Request):
        try:
            raw = base64.b64decode(value.data, validate=True)
        except (ValueError, binascii.Error):
            raise DomainError(422, "REPORT_INVALID", "报告原件编码无效") from None
        signatures = {"application/pdf": b"%PDF-", "image/png": b"\x89PNG\r\n\x1a\n", "image/jpeg": b"\xff\xd8\xff"}
        if not 0 < len(raw) <= 2 * 1024 * 1024 or value.mime not in signatures or not raw.startswith(signatures[value.mime]):
            raise DomainError(422, "REPORT_INVALID", "请选择不超过2MB的 PDF、PNG 或 JPEG 原件")
        if any(ord(c) < 32 or c in '/\\' for c in value.filename) or not value.filename.strip():
            raise DomainError(422, "REPORT_INVALID", "原件名称无效")
        import hashlib
        sha = hashlib.sha256(raw).hexdigest()
        with db.transaction() as connection:
            actor = actor_for(connection, request, ident, True, True)
            connection.execute(select(patients.c.id).where(patients.c.id == ident).with_for_update()).first()
            previous = connection.execute(select(reports).where(reports.c.patient_id == ident, reports.c.operation_id == str(value.operation_id))).mappings().first()
            if previous:
                if previous["sha256"] != sha or previous["filename"] != value.filename or previous["mime"] != value.mime or previous["original_sharing"] != value.shared:
                    raise DomainError(409, "IDEMPOTENCY_CONFLICT", "这次上传已有不同原件")
                return {"status": "COMMITTED", "item": report_metadata(previous), "idempotent": True}
            # Hard cap until retention/storage policy is configured. No unbounded
            # medical blob uploads into the existing production database.
            from sqlalchemy import func
            if connection.scalar(select(func.count()).select_from(reports).where(reports.c.patient_id == ident)) >= 50:
                raise DomainError(409, "REPORT_CAPACITY", "已达到50份原件上限，请联系工作台")
            row = {"id": str(uuid4()), "patient_id": ident, "operation_id": str(value.operation_id), "filename": value.filename,
                   "mime": value.mime, "content": raw, "size": len(raw), "sha256": sha, "shared": value.shared,
                   "version": 1, "original_sharing": value.shared, "created_at": int(time.time())}
            connection.execute(reports.insert().values(**row))
            audited(connection, actor["id"], "report.upload", row["id"])
            return {"status": "COMMITTED", "item": report_metadata(row), "idempotent": False}

    @app.get(base + "/patients/{ident}/reports")
    def list_reports(ident: str, request: Request):
        with db.transaction() as connection:
            actor = actor_for(connection, request, ident)
            condition = reports.c.patient_id == ident
            if actor["role"] != "PATIENT":
                condition &= reports.c.shared.is_(True)
            rows = connection.execute(select(*(c for c in reports.c if c.name != "content")).where(condition).order_by(reports.c.created_at.desc(), reports.c.id)).mappings()
            return {"items": [report_metadata(r) for r in rows]}

    @app.put(base + "/patients/{ident}/reports/{report_id}/sharing")
    def sharing(ident: str, report_id: UUID, value: Sharing, request: Request):
        with db.transaction() as connection:
            actor = actor_for(connection, request, ident, True, True)
            row = connection.execute(select(reports).where(reports.c.patient_id == ident, reports.c.id == str(report_id)).with_for_update()).mappings().first()
            if not row:
                raise DomainError(404, "RESOURCE_NOT_FOUND", "找不到原件")
            if row["version"] != value.expected_version:
                raise DomainError(412, "REVISION_MISMATCH", "原件授权已变化，请刷新")
            connection.execute(update(reports).where(reports.c.id == str(report_id)).values(shared=value.shared, version=row["version"] + 1))
            audited(connection, actor["id"], "report.sharing", str(report_id))
            return {"status": "COMMITTED", "shared": value.shared, "version": row["version"] + 1}

    @app.get(base + "/patients/{ident}/reports/{report_id}/original")
    def original(ident: str, report_id: UUID, request: Request):
        from urllib.parse import quote
        with db.transaction() as connection:
            actor = actor_for(connection, request, ident)
            row = connection.execute(select(reports).where(reports.c.patient_id == ident, reports.c.id == str(report_id))).mappings().first()
            if not row or (actor["role"] != "PATIENT" and not row["shared"]):
                raise DomainError(404, "RESOURCE_NOT_FOUND", "找不到已授权原件")
            audited(connection, actor["id"], "report.download", str(report_id))
            return Response(row["content"], media_type=row["mime"], headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(row["filename"], safe=""), "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox; default-src 'none'"})
