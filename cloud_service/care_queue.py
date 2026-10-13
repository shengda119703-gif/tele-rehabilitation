"""One-hour first human response measured only inside configured work intervals."""
from datetime import datetime, timedelta, timezone
import time
from uuid import UUID

from fastapi import Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import Column, ForeignKey, Integer, JSON, String, Table, select, update

from .database import grants, metadata, patients
from .security import DomainError, audited

calendar = Table("care_work_calendar", metadata, Column("id", Integer, primary_key=True),
                 Column("version", Integer, nullable=False), Column("document", JSON, nullable=False))
cases = Table("care_response_cases", metadata, Column("patient_id", String(36), ForeignKey("patients.id"), primary_key=True),
              Column("first_sequence", Integer, nullable=False), Column("opened_at", Integer, nullable=False),
              Column("calendar", JSON), Column("due_at", Integer), Column("closed_sequence", Integer, nullable=False))


class WorkCalendar(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_version: int = Field(ge=0)
    # ISO weekday 1..7 -> disjoint [start,end] minute-of-day pairs. UTC+8.
    intervals: dict[str, list[list[int]]]
    holidays: list[str] = Field(default_factory=list, max_length=400)

    @model_validator(mode="after")
    def check(self):
        if not self.intervals or set(self.intervals) - set("1234567"):
            raise ValueError("请配置每周工作时间")
        total = 0
        for parts in self.intervals.values():
            end = -1
            for pair in parts:
                if len(pair) != 2 or any(type(x) is not int for x in pair) or not 0 <= pair[0] < pair[1] <= 1440 or pair[0] < end:
                    raise ValueError("工作时段需顺序排列且不能重叠")
                end = pair[1]
                total += pair[1] - pair[0]
        if total < 60:
            raise ValueError("每周需至少60分钟工作时段")
        for day in self.holidays:
            if datetime.strptime(day, "%Y-%m-%d").strftime("%Y-%m-%d") != day:
                raise ValueError("假日需使用 YYYY-MM-DD")
        return self


def deadline(start, document, minutes=60):
    zone = timezone(timedelta(hours=8))
    begin = datetime.fromtimestamp(start, zone)
    remaining = minutes * 60
    for offset in range(740):
        day = begin.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=offset)
        if day.strftime("%Y-%m-%d") in document["holidays"]:
            continue
        for lo, hi in document["intervals"].get(str(day.isoweekday()), []):
            opening = max(start, int((day + timedelta(minutes=lo)).timestamp()))
            closing = int((day + timedelta(minutes=hi)).timestamp())
            available = max(0, closing - opening)
            if available >= remaining:
                return opening + remaining
            remaining -= available
    raise DomainError(422, "CALENDAR_NO_CAPACITY", "工作日历缺少可用时段，请检查假日配置")


def opened(connection, item):
    if item["author_role"] != "PATIENT":
        return
    existing = connection.execute(select(cases).where(cases.c.patient_id == item["patient_id"])).mappings().first()
    if existing and existing["first_sequence"] > existing["closed_sequence"]:
        return  # Supplementary messages never reset the first response timer.
    config = connection.execute(select(calendar).where(calendar.c.id == 1)).mappings().first()
    document = {**config["document"], "version": config["version"]} if config else None
    values = {"first_sequence": item["sequence"], "opened_at": item["created_at"], "calendar": document,
              "due_at": deadline(item["created_at"], document) if document else None}
    if existing:
        connection.execute(update(cases).where(cases.c.patient_id == item["patient_id"]).values(**values))
    else:
        connection.execute(cases.insert().values(patient_id=item["patient_id"], closed_sequence=0, **values))


def install_queue(app, db, caller, patient_scope, base):
    def doctor(connection, request, write=False):
        actor, _ = caller(request, connection, write=write)
        if actor["role"] != "DOCTOR_ADMIN":
            raise DomainError(403, "DOCTOR_REQUIRED", "请使用工作台医生账号")
        return actor

    @app.get(base + "/care/calendar")
    def get_calendar(request: Request):
        with db.transaction() as connection:
            doctor(connection, request)
            row = connection.execute(select(calendar).where(calendar.c.id == 1)).mappings().first()
            return {"version": row["version"] if row else 0, "document": row["document"] if row else None,
                    "timezone": "Asia/Shanghai", "first_response_minutes": 60}

    @app.put(base + "/care/calendar")
    def configure(value: WorkCalendar, request: Request):
        with db.transaction() as connection:
            actor = doctor(connection, request, True)
            # Serialize calendar changes across processes with the shared doctor row.
            from .database import accounts
            connection.execute(select(accounts.c.id).where(accounts.c.id == actor["id"]).with_for_update()).first()
            old = connection.execute(select(calendar).where(calendar.c.id == 1)).mappings().first()
            version = old["version"] if old else 0
            if version != value.expected_version:
                raise DomainError(412, "REVISION_MISMATCH", "工作日历已更新，请刷新")
            document = value.model_dump(exclude={"expected_version"})
            deadline(int(time.time()), document)
            values = {"version": version + 1, "document": document}
            if old:
                connection.execute(update(calendar).where(calendar.c.id == 1).values(**values))
            else:
                connection.execute(calendar.insert().values(id=1, **values))
            audited(connection, actor["id"], "care.calendar.configure", str(version + 1))
            return values

    @app.get(base + "/care/queue")
    def queue(request: Request, offset: int = 0, limit: int = 60):
        if offset < 0 or not 1 <= limit <= 100:
            raise DomainError(422, "VALIDATION_ERROR", "查询范围无效")
        with db.transaction() as connection:
            doctor(connection, request)
            rows = connection.execute(select(cases, patients.c.display_name).join(patients, patients.c.id == cases.c.patient_id)
                    .join(grants, grants.c.patient_id == patients.c.id).where(grants.c.enabled.is_(True),
                    cases.c.first_sequence > cases.c.closed_sequence).order_by(cases.c.opened_at, cases.c.patient_id)).mappings()
            items = []
            now = int(time.time())
            for row in rows:
                warning = deadline(row["opened_at"], row["calendar"], minutes=45) if row["calendar"] else None
                status = "UNCONFIGURED" if row["due_at"] is None else "OVERDUE" if now > row["due_at"] else "WARNING" if now >= warning else "WAITING"
                items.append({**dict(row), "status": status})
            return {"items": items[offset:offset + limit], "total": len(items), "offset": offset, "limit": limit}

    @app.post(base + "/patients/{ident}/messages/{message_id}/effective-response")
    def effective(ident: str, message_id: UUID, request: Request):
        from .workbench import messages
        with db.transaction() as connection:
            actor = doctor(connection, request, True)
            connection.execute(select(patients.c.id).where(patients.c.id == ident).with_for_update()).first()
            patient_scope(connection, actor, ident)
            message = connection.execute(select(messages).where(messages.c.id == str(message_id), messages.c.patient_id == ident,
                       messages.c.author_id == actor["id"], messages.c.author_role == "DOCTOR_ADMIN")).mappings().first()
            if not message:
                raise DomainError(404, "RESOURCE_NOT_FOUND", "找不到本人发送的有效回复")
            case = connection.execute(select(cases).where(cases.c.patient_id == ident)).mappings().first()
            if case and case["first_sequence"] <= message["sequence"] and case["closed_sequence"] < message["sequence"]:
                connection.execute(update(cases).where(cases.c.patient_id == ident).values(closed_sequence=message["sequence"]))
                audited(connection, actor["id"], "care.effective_human_reply", str(message_id))
                following = connection.execute(select(messages).where(messages.c.patient_id == ident,
                    messages.c.author_role == "PATIENT", messages.c.sequence > message["sequence"]).order_by(messages.c.sequence).limit(1)).mappings().first()
                if following:
                    opened(connection, following)
            return {"status": "COMMITTED", "message_id": str(message_id)}
