"""Account/patient foundation, deliberately independent of PhoneHost/Runtime."""
import hmac
import json
from pathlib import Path
import secrets
import time
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, func, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import __version__
from .browser import install_public_web
from .config import Settings
from .database import Database, accounts, grants, patients, records, sessions
from .dossier import validate_dossier
from .downloads import install_downloads
from .security import (
    DomainError, audited, csrf, digest, password, password_hash,
    throttle, username, verify_password,
)

BASE = "/api/cloud/v1"
ROOT = Path(__file__).resolve().parent.parent


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Registration(Input):
    username: str = Field(max_length=64)
    password: str = Field(max_length=128)
    display_name: str = Field(default="", max_length=80)


class Login(Input):
    username: str = Field(max_length=64)
    password: str = Field(max_length=128)
    client_kind: Literal["WEB", "APK", "DESKTOP"] = "WEB"


class Refresh(Input):
    refresh_token: str = Field(max_length=100)


class ChangePassword(Input):
    current_password: str = Field(max_length=128)
    new_password: str = Field(max_length=128)


class Grant(Input):
    enabled: bool
    expected_version: int = Field(ge=0)


class Record(Input):
    operation_id: UUID = Field(strict=False)
    source_event_id: str = Field(min_length=1, max_length=100)
    installation_id: str = Field(min_length=1, max_length=100)
    source_kind: Literal["WEB_LOCAL", "APK_LOCAL", "DESKTOP_LOCAL", "SELF_REPORT", "IMPORT"]
    payload: dict


class LimitedBody:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in {"POST", "PATCH", "PUT"}:
            return await self.app(scope, receive, send)
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > 262144:
                return await JSONResponse({"code": "PAYLOAD_TOO_LARGE", "message": "提交内容过大"},
                    status_code=413, headers={"Cache-Control": "no-store"})(scope, receive, send)
            if not message.get("more_body", False):
                break
        delivered = False

        async def replay():
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        return await self.app(scope, replay, send)


def create_app(settings: Settings, database=None, *, web_assets=None, download_assets=None):
    db = database or Database(settings.database_url)
    app = FastAPI(title="安康统一云服务", version=__version__, docs_url=None, redoc_url=None,
                  openapi_url=BASE + "/openapi.json")
    app.state.database = db
    app.state.settings = settings
    app.state.public_web = False
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=sorted({urlsplit(x).hostname for x in settings.origins}))
    app.add_middleware(LimitedBody)

    @app.exception_handler(DomainError)
    async def domain_error(request, exc):
        headers = {"Retry-After": "60"} if exc.status == 429 else {}
        return JSONResponse({"code": exc.code, "message": exc.message}, status_code=exc.status, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def input_error(request, exc):
        # Pydantic's default response includes raw inputs, including passwords.
        return JSONResponse({"code": "VALIDATION_ERROR", "message": "请检查填写内容"}, status_code=422)

    @app.exception_handler(SQLAlchemyError)
    async def dependency_error(request, exc):
        return JSONResponse({"code": "DEPENDENCY_UNAVAILABLE", "message": "服务暂时无法保存，请稍后再试"}, status_code=503)

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return JSONResponse({"code": "REQUEST_FAILED", "message": "请求无法完成"}, status_code=exc.status_code)

    @app.middleware("http")
    async def secure_headers(request, next_call):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            if origin is not None and origin not in settings.origins:
                return JSONResponse({"code": "ORIGIN_FORBIDDEN", "message": "请从正式入口重新打开"}, status_code=403)
            if request.method != "DELETE" and request.headers.get("content-type", "").split(";")[0] != "application/json":
                return JSONResponse({"code": "UNSUPPORTED_MEDIA_TYPE", "message": "请使用正确的提交格式"}, status_code=415)
        response = await next_call(request)
        policy = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        if app.state.public_web and request.url.path in {"/", "/capture"}:
            policy = "default-src 'self'; script-src 'self' blob: 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self' blob:; worker-src 'self' blob:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        response.headers.update({
            "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY",
            "Content-Security-Policy": policy,
        })
        return response

    def anonymous_origin(request):
        if request.headers.get("origin") in settings.origins:
            return
        # Native clients do not have a browser Origin. This header grants no authority.
        if request.headers.get("X-Ankang-Client") == "native" and not request.headers.get("origin"):
            return
        raise DomainError(403, "ORIGIN_REQUIRED", "请从正式入口打开登录页面")

    def caller(request, connection, *, write=False, doctor=False):
        authorization = request.headers.get("authorization", "")
        native = bool(authorization)
        if native:
            if not authorization.startswith("Bearer "):
                raise DomainError(401, "AUTH_REQUIRED", "请先登录")
            token = authorization[7:]
        else:
            token = request.cookies.get(settings.cookie_name, "")
        if not 40 <= len(token) <= 100:
            raise DomainError(401, "AUTH_REQUIRED", "请先登录")
        row = connection.execute(select(
            sessions.c.id.label("session_id"), sessions.c.client_kind,
            accounts.c.id, accounts.c.username, accounts.c.role, accounts.c.password_hash,
        ).join(accounts, sessions.c.account_id == accounts.c.id).where(
            sessions.c.token_hash == digest(token), sessions.c.revoked.is_(False),
            sessions.c.expires_at > int(time.time()), accounts.c.active.is_(True),
        )).mappings().first()
        if not row or native and row["client_kind"] == "WEB" or not native and row["client_kind"] != "WEB":
            raise DomainError(401, "AUTH_REQUIRED", "登录已失效，请重新登录")
        if write and not native:
            if request.headers.get("origin") not in settings.origins or not hmac.compare_digest(
                request.headers.get("X-CSRF-Token", "").encode(), csrf(settings.secret, token).encode()):
                raise DomainError(403, "CSRF_REQUIRED", "页面已更新，请刷新后再试")
        if doctor and row["role"] != "DOCTOR_ADMIN":
            raise DomainError(403, "FORBIDDEN", "此账号不能进入医生工作台")
        return dict(row), token

    def patient_scope(connection, actor, ident, *, write=False):
        patient = connection.execute(select(patients).where(patients.c.id == ident)).mappings().first()
        if patient and patient["account_id"] == actor["id"]:
            return patient
        if patient and not write and actor["role"] == "DOCTOR_ADMIN":
            grant = connection.scalar(select(grants.c.enabled).where(grants.c.patient_id == ident))
            if grant:
                return patient
        raise DomainError(404, "RESOURCE_NOT_FOUND", "找不到可访问的档案")

    def public_account(connection, actor):
        patient = connection.scalar(select(patients.c.id).where(patients.c.account_id == actor["id"]))
        return {"account_id": actor["id"], "username": actor["username"], "role": actor["role"], "patient_id": patient}

    @app.get("/health/live")
    def live():
        return {"ok": True, "version": __version__, "server_models": False}

    @app.get("/health/ready")
    def ready():
        if not db.ready():
            raise DomainError(503, "INITIALIZATION_REQUIRED", "服务正在准备")
        return {"ok": True}

    @app.get(BASE + "/capabilities")
    def capabilities():
        return {"version": __version__, "registration": "public_password", "password_complexity": False,
            "doctor_identity": "shared_admin", "mfa_required": False, "server_models": False,
            "providers": {name: {"enabled": False, "available": False, "execution_location": "DISABLED"}
                          for name in ("llm", "asr", "tts", "ocr", "sms", "push")},
            "plans": False, "voice_messages": False, "calls": False, "incremental_sync": False,
            "public_user_web": app.state.public_web, "browser_analysis": "LOCAL_CPU" if app.state.public_web else None}

    @app.post(BASE + "/auth/register", status_code=201)
    def register(value: Registration, request: Request):
        anonymous_origin(request)
        if not db.ready():
            raise DomainError(503, "INITIALIZATION_REQUIRED", "服务正在准备")
        normalized = username(value.username)
        if normalized == username(settings.doctor_username):
            raise DomainError(409, "ACCOUNT_UNAVAILABLE", "这个账号暂不可使用")
        throttle(db, settings.secret, [("register:" + request.client.host, 10, 3600)])
        encoded = password_hash(value.password)
        account_id, patient_id = str(uuid4()), str(uuid4())
        try:
            with db.transaction() as connection:
                connection.execute(accounts.insert().values(id=account_id, username=normalized,
                    password_hash=encoded, role="PATIENT", active=True, created_at=int(time.time())))
                connection.execute(patients.insert().values(id=patient_id, account_id=account_id,
                    display_name=value.display_name.strip() or normalized, created_at=int(time.time())))
                audited(connection, account_id, "account.register", patient_id)
        except IntegrityError:
            raise DomainError(409, "ACCOUNT_UNAVAILABLE", "这个账号暂不可使用") from None
        return {"account_id": account_id, "patient_id": patient_id, "status": "COMMITTED"}

    @app.post(BASE + "/auth/password/login")
    def login(value: Login, request: Request, response: Response):
        anonymous_origin(request)
        normalized = username(value.username)
        throttle(db, settings.secret, [("login-ip:" + request.client.host, 20, 60),
            ("login-account:" + normalized, 30, 600)])
        # Expensive hash verification is outside the transaction; recheck under lock.
        with db.engine.connect() as connection:
            account = connection.execute(select(accounts).where(accounts.c.username == normalized)).mappings().first()
        if not verify_password(account["password_hash"] if account else None, value.password) or not account or not account["active"]:
            raise DomainError(401, "LOGIN_FAILED", "账号或密码不正确")
        now = int(time.time())
        token = secrets.token_urlsafe(32)
        refresh_token = secrets.token_urlsafe(32) if value.client_kind != "WEB" else None
        session_id = str(uuid4())
        with db.transaction() as connection:
            current = connection.execute(select(accounts).where(accounts.c.id == account["id"]).with_for_update()).mappings().first()
            if not current["active"] or current["password_hash"] != account["password_hash"]:
                raise DomainError(401, "LOGIN_FAILED", "账号或密码不正确")
            connection.execute(sessions.insert().values(id=session_id, account_id=account["id"],
                token_hash=digest(token), refresh_hash=digest(refresh_token) if refresh_token else None,
                client_kind=value.client_kind, expires_at=now + (28800 if value.client_kind == "WEB" else 900),
                refresh_expires_at=now + 2592000 if refresh_token else now + 28800,
                revoked=False, created_at=now))
            audited(connection, account["id"], "session.login", session_id)
            result = public_account(connection, account)
        if value.client_kind == "WEB":
            response.set_cookie(settings.cookie_name, token, max_age=28800, secure=settings.production,
                                httponly=True, samesite="strict", path="/")
            result["csrf_token"] = csrf(settings.secret, token)
        else:
            result.update(access_token=token, refresh_token=refresh_token, expires_in=900)
        return result

    @app.post(BASE + "/auth/refresh")
    def refresh(value: Refresh, request: Request):
        anonymous_origin(request)
        throttle(db, settings.secret, [("refresh:" + request.client.host, 30, 60)])
        token, next_refresh = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with db.transaction() as connection:
            row = connection.execute(select(sessions).where(
                sessions.c.refresh_hash == digest(value.refresh_token), sessions.c.revoked.is_(False),
                sessions.c.refresh_expires_at > int(time.time()), sessions.c.client_kind != "WEB",
            ).with_for_update()).mappings().first()
            if not row or not connection.scalar(select(accounts.c.active).where(accounts.c.id == row["account_id"])):
                raise DomainError(401, "AUTH_REQUIRED", "请重新登录")
            connection.execute(update(sessions).where(sessions.c.id == row["id"]).values(
                token_hash=digest(token), refresh_hash=digest(next_refresh), expires_at=int(time.time()) + 900))
            audited(connection, row["account_id"], "session.refresh", row["id"])
        return {"access_token": token, "refresh_token": next_refresh, "expires_in": 900}

    @app.get(BASE + "/auth/me")
    def me(request: Request):
        with db.transaction() as connection:
            actor, token = caller(request, connection)
            result = public_account(connection, actor)
            if actor["client_kind"] == "WEB":
                result["csrf_token"] = csrf(settings.secret, token)
            return result

    @app.post(BASE + "/auth/logout")
    def logout(request: Request, response: Response):
        with db.transaction() as connection:
            actor, _ = caller(request, connection, write=True)
            connection.execute(update(sessions).where(sessions.c.id == actor["session_id"]).values(revoked=True))
            audited(connection, actor["id"], "session.logout", actor["session_id"])
        response.delete_cookie(settings.cookie_name, path="/", secure=settings.production, httponly=True, samesite="strict")
        return {"status": "COMMITTED"}

    @app.post(BASE + "/auth/password/change")
    def change_password(value: ChangePassword, request: Request, response: Response):
        with db.transaction() as connection:
            actor, _ = caller(request, connection, write=True)
        throttle(db, settings.secret, [("change:" + actor["id"], 5, 600)])
        if not verify_password(actor["password_hash"], value.current_password):
            raise DomainError(401, "PASSWORD_MISMATCH", "原密码不正确")
        encoded = password_hash(value.new_password)
        with db.transaction() as connection:
            fresh, _ = caller(request, connection, write=True)
            updated = connection.execute(update(accounts).where(accounts.c.id == actor["id"],
                accounts.c.password_hash == actor["password_hash"]).values(password_hash=encoded))
            if updated.rowcount != 1:
                raise DomainError(409, "ACCOUNT_CHANGED", "账号已更新，请重新登录")
            connection.execute(update(sessions).where(sessions.c.account_id == actor["id"]).values(revoked=True))
            audited(connection, actor["id"], "account.password_changed", actor["id"])
        response.delete_cookie(settings.cookie_name, path="/", secure=settings.production)
        return {"status": "COMMITTED", "login_required": True}

    @app.get(BASE + "/auth/devices")
    def devices(request: Request):
        with db.transaction() as connection:
            actor, _ = caller(request, connection)
            rows = connection.execute(select(sessions.c.id, sessions.c.client_kind, sessions.c.created_at,
                sessions.c.revoked).where(sessions.c.account_id == actor["id"]).order_by(sessions.c.created_at.desc()).limit(100)).mappings()
            return {"items": [dict(row) for row in rows], "current_session_id": actor["session_id"]}

    @app.post(BASE + "/auth/devices/{ident}/revoke")
    def revoke(ident: str, request: Request):
        with db.transaction() as connection:
            actor, _ = caller(request, connection, write=True)
            row = connection.execute(update(sessions).where(sessions.c.id == ident,
                sessions.c.account_id == actor["id"]).values(revoked=True))
            if row.rowcount != 1:
                raise DomainError(404, "RESOURCE_NOT_FOUND", "找不到这台设备")
            audited(connection, actor["id"], "session.revoked", ident)
        return {"status": "COMMITTED"}

    @app.get(BASE + "/patients/{ident}")
    def profile(ident: str, request: Request):
        with db.transaction() as connection:
            actor, _ = caller(request, connection)
            patient = patient_scope(connection, actor, ident)
            grant = connection.execute(select(grants).where(grants.c.patient_id == ident)).mappings().first()
            return {"patient_id": ident, "display_name": patient["display_name"],
                    "doctor_access": bool(grant and grant["enabled"]), "grant_version": grant["version"] if grant else 0}

    @app.put(BASE + "/patients/{ident}/doctor-access")
    def doctor_access(ident: str, value: Grant, request: Request):
        with db.transaction() as connection:
            actor, _ = caller(request, connection, write=True)
            patient_scope(connection, actor, ident, write=True)
            # Lock stable patient, including the first grant creation race.
            connection.execute(select(patients.c.id).where(patients.c.id == ident).with_for_update()).first()
            old = connection.execute(select(grants).where(grants.c.patient_id == ident)).mappings().first()
            version = old["version"] if old else 0
            if version != value.expected_version:
                raise DomainError(412, "REVISION_MISMATCH", "授权已更新，请刷新后再试")
            values = dict(enabled=value.enabled, version=version + 1, changed_at=int(time.time()))
            if old:
                connection.execute(update(grants).where(grants.c.patient_id == ident).values(**values))
            else:
                connection.execute(grants.insert().values(patient_id=ident, **values))
            audited(connection, actor["id"], "doctor_access.enabled" if value.enabled else "doctor_access.revoked", ident)
        return {"status": "COMMITTED", "grant_version": version + 1}

    @app.get(BASE + "/care/patients")
    def care_patients(request: Request, offset: int = 0, limit: int = 30, search: str = ""):
        if offset < 0 or not 1 <= limit <= 100 or len(search) > 80:
            raise DomainError(422, "VALIDATION_ERROR", "查询范围无效")
        with db.transaction() as connection:
            caller(request, connection, doctor=True)
            permitted = patients.join(grants, patients.c.id == grants.c.patient_id)
            condition = and_(grants.c.enabled.is_(True), patients.c.display_name.contains(search, autoescape=True))
            total = connection.scalar(select(func.count()).select_from(permitted).where(condition))
            rows = connection.execute(select(patients.c.id, patients.c.display_name).select_from(permitted)
                .where(condition).order_by(patients.c.id).offset(offset).limit(limit)).mappings()
            return {"items": [dict(row) for row in rows], "total": total, "offset": offset, "limit": limit}

    @app.post(BASE + "/patients/{ident}/record-events", status_code=201)
    def append_record(ident: str, value: Record, request: Request):
        document = value.model_dump(mode="json")
        encoded = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if len(encoded.encode()) > 32768:
            raise DomainError(413, "PAYLOAD_TOO_LARGE", "单条记录内容过大")
        content_digest = digest(encoded)
        with db.transaction() as connection:
            actor, _ = caller(request, connection, write=True)
            patient_scope(connection, actor, ident, write=True)
            validate_dossier(document, actor, ident)
            connection.execute(select(patients.c.id).where(patients.c.id == ident).with_for_update()).first()
            prior = connection.execute(select(records).where(records.c.submitted_by == actor["id"],
                records.c.operation_id == str(value.operation_id))).mappings().first()
            if prior:
                if prior["digest"] != content_digest or prior["patient_id"] != ident:
                    raise DomainError(409, "IDEMPOTENCY_CONFLICT", "这条操作已有不同内容，请保留原记录")
                return {"status": "COMMITTED", "resource_id": prior["id"], "idempotent": True}
            duplicate = connection.execute(select(records).where(records.c.patient_id == ident,
                records.c.installation_id == value.installation_id, records.c.source_event_id == value.source_event_id)).mappings().first()
            if duplicate:
                raise DomainError(409, "SOURCE_EVENT_EXISTS", "这条来源记录已保存，请核对原记录")
            record_id = str(uuid4())
            connection.execute(records.insert().values(id=record_id, patient_id=ident, submitted_by=actor["id"],
                operation_id=str(value.operation_id), source_event_id=value.source_event_id,
                installation_id=value.installation_id, source_kind=value.source_kind,
                payload=value.payload, digest=content_digest, received_at=int(time.time())))
            audited(connection, actor["id"], "patient_record.append", record_id)
        return {"status": "COMMITTED", "resource_id": record_id, "idempotent": False}

    @app.get(BASE + "/patients/{ident}/records")
    def read_records(ident: str, request: Request, offset: int = 0, limit: int = 30):
        if offset < 0 or not 1 <= limit <= 100:
            raise DomainError(422, "VALIDATION_ERROR", "查询范围无效")
        with db.transaction() as connection:
            actor, _ = caller(request, connection)
            patient_scope(connection, actor, ident)
            rows = connection.execute(select(records.c.id, records.c.source_kind, records.c.attribution_state, records.c.payload,
                records.c.received_at).where(records.c.patient_id == ident).order_by(records.c.received_at.desc(),
                records.c.id).offset(offset).limit(limit)).mappings()
            return {"items": [dict(row) for row in rows], "offset": offset, "limit": limit}

    # Models are public browser assets only; never import a server execution API.
    shared = ROOT / "mobile_rehab" / "static"
    def fixed_static(name):
        def static_file():
            return FileResponse(shared / name)
        return static_file
    def browser_account(request):
        with db.transaction() as connection:
            actor, _ = caller(request, connection)
            if actor["client_kind"] != "WEB":
                raise DomainError(401, "AUTH_REQUIRED", "请在网页登录")
            return public_account(connection, actor)

    app.state.public_web = install_public_web(app, Path(web_assets) if web_assets is not None else ROOT / "public_web" / "build", browser_account)
    for name in (() if app.state.public_web else ("unified.css", "unified-polish.css", "controls.css", "icon.svg")):
        app.add_api_route("/static/" + name, fixed_static(name), methods=["GET"], include_in_schema=False)
    app.mount("/cloud-static", StaticFiles(directory=ROOT / "cloud_service" / "static"), name="cloud-static")
    install_downloads(app, Path(download_assets) if download_assets is not None else ROOT / "cloud_service" / "static",
                      ROOT / "cloud_service" / "static")

    @app.get("/account", include_in_schema=False)
    @app.get("/care", include_in_schema=False)
    def portal():
        return FileResponse(ROOT / "cloud_service" / "static" / "index.html")

    if not app.state.public_web:
        app.add_api_route("/", portal, methods=["GET"], include_in_schema=False)

    return app


def from_env():
    return create_app(Settings.from_env())
