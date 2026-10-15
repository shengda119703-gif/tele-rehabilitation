"""Account-scoped family relationships; linking is never sharing consent."""
import secrets
import time

from fastapi import Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Column, ForeignKey, Integer, JSON, String, Table, delete, or_, select, text, update

from .database import accounts, metadata, patients
from .security import DomainError, audited, digest, throttle

invites = Table("account_family_invites", metadata,
    Column("owner", String(36), ForeignKey("patients.id"), primary_key=True),
    Column("code_hash", String(64), nullable=False, unique=True),
    Column("expires_at", Integer, nullable=False),
    Column("used_by", String(36), ForeignKey("patients.id")),
)
links = Table("account_family_links", metadata,
    Column("owner", String(36), ForeignKey("patients.id"), primary_key=True),
    Column("member", String(36), ForeignKey("patients.id"), primary_key=True),
    Column("categories", JSON, nullable=False),
    Column("changed_at", Integer, nullable=False),
)
summaries = Table("account_family_summaries", metadata,
    Column("owner", String(36), ForeignKey("patients.id"), primary_key=True),
    Column("document", JSON, nullable=False),
    Column("changed_at", Integer, nullable=False),
)
CATEGORIES = {"health", "rehab", "medication"}
MAX_MEMBERS = 10


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Bind(Input):
    code: str = Field(min_length=8, max_length=8, pattern=r"^[A-Fa-f0-9]{8}$")


class Member(Input):
    member: str = Field(pattern=r"^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$")


class Grant(Member):
    categories: list[str] = Field(max_length=3)


class SummaryRow(Input):
    timestamp: str = Field(max_length=40)
    text: str = Field(max_length=300)


class DoseRow(Input):
    medName: str = Field(max_length=100)
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    time: str = Field(pattern=r"^\d{2}:\d{2}$")
    status: str = Field(pattern=r"^(taken|skipped|unrecorded)$")


class Summary(Input):
    name: str = Field(max_length=40)
    health: list[SummaryRow] = Field(max_length=10)
    rehab: list[SummaryRow] = Field(max_length=10)
    doses: list[DoseRow] = Field(max_length=10)


def mutation_lock(connection):
    # Serializes low-volume relation changes across workers, including first-link
    # races and invite replacement. SQLite transactions already use BEGIN IMMEDIATE.
    if connection.dialect.name == "postgresql":
        connection.execute(text("SELECT pg_advisory_xact_lock(74321020)"))


def permitted_summary(connection, owner, document):
    permitted = set()
    for row in connection.execute(select(links.c.categories).where(links.c.owner == owner)):
        permitted.update(row[0])
    return {"name": document.get("name", ""),
        **{key: document.get(key, []) if category in permitted else []
           for key, category in (("health", "health"), ("rehab", "rehab"), ("doses", "medication"))}}


def prune_summary(connection, owner):
    document = connection.scalar(select(summaries.c.document).where(summaries.c.owner == owner))
    if document is not None:
        connection.execute(update(summaries).where(summaries.c.owner == owner).values(
            document=permitted_summary(connection, owner, document), changed_at=int(time.time())))


def install_family(app, db, caller, patient_scope, base, secret):
    prefix = base + "/patients/{ident}/family"

    def own(connection, request, ident, *, write=False):
        actor, _ = caller(request, connection, write=write)
        patient = patient_scope(connection, actor, ident, write=True)
        if actor["role"] != "PATIENT" or patient["account_id"] != actor["id"]:
            raise DomainError(404, "RESOURCE_NOT_FOUND", "找不到可访问的家庭资料")
        return actor

    def limit(request, ident, action, maximum):
        with db.transaction() as connection:
            actor = own(connection, request, ident, write=True)
        throttle(db, secret, [("family:" + action + ":" + actor["id"], maximum, 600)])

    @app.get(prefix)
    def family(ident: str, request: Request):
        with db.transaction() as connection:
            own(connection, request, ident)
            rows = connection.execute(select(links.c.member, links.c.categories, patients.c.display_name)
                .join(patients, links.c.member == patients.c.id).join(accounts, patients.c.account_id == accounts.c.id)
                .where(links.c.owner == ident, accounts.c.active.is_(True)).order_by(links.c.member)).mappings().all()
            members, grants = [], {}
            for row in rows[:MAX_MEMBERS]:
                member = row["member"]
                incoming = connection.scalar(select(links.c.categories).where(links.c.owner == member, links.c.member == ident))
                if incoming is None:
                    continue  # Never expose a half-relationship.
                document = connection.scalar(select(summaries.c.document).where(summaries.c.owner == member)) or {}
                grants[member] = row["categories"]
                name = document.get("name")
                if not name or name == "本机用户":
                    name = row["display_name"]
                members.append({"ownerId": member, "name": name,
                    "categories": incoming,
                    **{key: document.get(key, [])[-5:] if category in incoming else []
                       for key, category in (("health", "health"), ("rehab", "rehab"), ("doses", "medication"))}})
            return {"familyMembers": members, "grants": grants, "fetchedAt": time.time()}

    @app.post(prefix + "/invite")
    def invite(ident: str, value: Input, request: Request):
        limit(request, ident, "invite", 12)
        code = secrets.token_hex(4).upper()
        with db.transaction() as connection:
            actor = own(connection, request, ident, write=True)
            mutation_lock(connection)
            connection.execute(delete(invites).where(or_(invites.c.owner == ident, invites.c.expires_at <= int(time.time()))))
            connection.execute(invites.insert().values(owner=ident, code_hash=digest(code), expires_at=int(time.time()) + 900))
            audited(connection, actor["id"], "family.invite.created", ident)
        return {"code": code, "expires_in": 900}

    @app.post(prefix + "/bind")
    def bind(ident: str, value: Bind, request: Request):
        limit(request, ident, "bind", 20)
        with db.transaction() as connection:
            actor = own(connection, request, ident, write=True)
            mutation_lock(connection)
            invitation = connection.execute(select(invites).where(invites.c.code_hash == digest(value.code.upper()),
                invites.c.expires_at > int(time.time())).with_for_update()).mappings().first()
            def invalid():
                raise DomainError(400, "FAMILY_INVITE_INVALID", "邀请码无效或已过期，请向家人获取新码")
            if not invitation or invitation["owner"] == ident:
                invalid()
            member = invitation["owner"]
            enabled = connection.scalar(select(accounts.c.active).join(patients, patients.c.account_id == accounts.c.id)
                .where(patients.c.id == member))
            if not enabled:
                invalid()
            def exists(owner, other):
                return connection.execute(select(links.c.member).where(links.c.owner == owner, links.c.member == other)).first() is not None
            if invitation["used_by"]:
                if invitation["used_by"] == ident and exists(ident, member) and exists(member, ident):
                    return {"dailyReceipt": True, "idempotent": True}
                invalid()
            for owner, other in ((ident, member), (member, ident)):
                if not exists(owner, other):
                    count = len(connection.execute(select(links.c.member).where(links.c.owner == owner)).all())
                    if count >= MAX_MEMBERS:
                        raise DomainError(409, "FAMILY_LIMIT", "已达到家人关联数量上限，请先管理已有关系")
                    connection.execute(links.insert().values(owner=owner, member=other, categories=[], changed_at=int(time.time())))
            connection.execute(update(invites).where(invites.c.owner == member).values(used_by=ident))
            audited(connection, actor["id"], "family.link.created", member)
        return {"dailyReceipt": True}

    def relation(connection, ident, member):
        if not connection.execute(select(links.c.member).where(links.c.owner == ident, links.c.member == member)).first():
            raise DomainError(404, "FAMILY_NOT_LINKED", "家庭关系不存在，请刷新核对")

    @app.post(prefix + "/grant")
    def grant(ident: str, value: Grant, request: Request):
        if set(value.categories) - CATEGORIES or len(set(value.categories)) != len(value.categories):
            raise DomainError(422, "FAMILY_CATEGORIES_INVALID", "请核对家庭共享类别")
        limit(request, ident, "grant", 60)
        with db.transaction() as connection:
            actor = own(connection, request, ident, write=True)
            mutation_lock(connection)
            relation(connection, ident, value.member)
            connection.execute(update(links).where(links.c.owner == ident, links.c.member == value.member)
                .values(categories=sorted(value.categories), changed_at=int(time.time())))
            prune_summary(connection, ident)
            audited(connection, actor["id"], "family.categories.changed", value.member)
        return {"dailyReceipt": True}

    @app.post(prefix + "/unbind")
    def unbind(ident: str, value: Member, request: Request):
        limit(request, ident, "unbind", 30)
        with db.transaction() as connection:
            actor = own(connection, request, ident, write=True)
            mutation_lock(connection)
            relation(connection, ident, value.member)
            connection.execute(delete(links).where(or_((links.c.owner == ident) & (links.c.member == value.member),
                (links.c.owner == value.member) & (links.c.member == ident))))
            prune_summary(connection, ident)
            prune_summary(connection, value.member)
            audited(connection, actor["id"], "family.link.removed", value.member)
        return {"dailyReceipt": True}

    @app.put(prefix + "/summary")
    def summary(ident: str, value: Summary, request: Request):
        with db.transaction() as connection:
            own(connection, request, ident, write=True)
            mutation_lock(connection)
            document = permitted_summary(connection, ident, value.model_dump())
            existing = connection.scalar(select(summaries.c.owner).where(summaries.c.owner == ident))
            values = {"document": document, "changed_at": int(time.time())}
            if existing:
                connection.execute(update(summaries).where(summaries.c.owner == ident).values(**values))
            else:
                connection.execute(summaries.insert().values(owner=ident, **values))
        return {"ok": True}
