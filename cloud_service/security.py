"""Slow password hashes, transactional throttles, no raw credential logging."""
import hashlib
import hmac
import threading
import time
import unicodedata
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .database import accounts, attempts, audit

hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
hash_slots = threading.BoundedSemaphore(2)
DUMMY_HASH = hasher.hash("not-a-login-password-" + str(uuid4()))


class DomainError(Exception):
    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message


def username(value):
    if not isinstance(value, str):
        raise DomainError(422, "VALIDATION_ERROR", "请输入账号")
    result = unicodedata.normalize("NFKC", value).strip().casefold()
    if not 1 <= len(result) <= 64 or not all(c.isalnum() or c in "_.-" for c in result):
        raise DomainError(422, "VALIDATION_ERROR", "账号可使用文字、数字、下划线或短横线")
    return result


def password(value):
    # User requested no complexity or minimum-length policy. Never trim passwords.
    if not isinstance(value, str) or not 1 <= len(value) <= 128 or len(value.encode("utf-8")) > 512:
        raise DomainError(422, "VALIDATION_ERROR", "请输入密码（最多128个字符）")
    return value


def password_hash(value):
    if not hash_slots.acquire(timeout=2):
        raise DomainError(429, "RATE_LIMITED", "请求较多，请稍后再试")
    try:
        return hasher.hash(password(value))
    finally:
        hash_slots.release()


def verify_password(encoded, value):
    if not hash_slots.acquire(timeout=2):
        raise DomainError(429, "RATE_LIMITED", "请求较多，请稍后再试")
    try:
        return hasher.verify(encoded or DUMMY_HASH, password(value))
    except (VerificationError, InvalidHashError):
        return False
    finally:
        hash_slots.release()


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def csrf(secret, token):
    return hmac.new(secret.encode(), ("csrf:" + token).encode(), hashlib.sha256).hexdigest()


def throttle(database, secret, keys):
    """Shared DB counters, not process-local or spoofable forwarded-address maps."""
    now = int(time.time())
    with database.transaction() as connection:
        connection.execute(delete(attempts).where(attempts.c.expires_at < now))
        insert = pg_insert if connection.dialect.name == "postgresql" else sqlite_insert
        for label, maximum, seconds in keys:
            key = hmac.new(secret.encode(), label.encode(), hashlib.sha256).hexdigest()
            window = now // seconds
            statement = insert(attempts).values(key=key, window=window, count=1, expires_at=(window + 1) * seconds)
            statement = statement.on_conflict_do_update(
                index_elements=[attempts.c.key, attempts.c.window], set_={"count": attempts.c.count + 1})
            connection.execute(statement)
            count = connection.scalar(select(attempts.c.count).where(attempts.c.key == key, attempts.c.window == window))
            if count > maximum:
                raise DomainError(429, "RATE_LIMITED", "尝试较多，请稍后再试")


def audited(connection, actor, action, resource=None):
    connection.execute(audit.insert().values(id=str(uuid4()), actor_id=actor,
        action=action, resource_id=resource, created_at=int(time.time())))


def bootstrap_doctor(database, settings, plain_password):
    """Local controlled initialization only. No public privilege-creation endpoint."""
    encoded = password_hash(plain_password)
    ident = str(uuid4())
    with database.transaction() as connection:
        if connection.dialect.name == "postgresql":
            connection.exec_driver_sql("SELECT pg_advisory_xact_lock(74321002)")
        if connection.scalar(select(accounts.c.id).where(accounts.c.role == "DOCTOR_ADMIN")):
            raise DomainError(409, "ALREADY_INITIALIZED", "医生共用账号已存在，不会覆盖原密码")
        connection.execute(accounts.insert().values(id=ident, username=username(settings.doctor_username),
            password_hash=encoded, role="DOCTOR_ADMIN", active=True, created_at=int(time.time())))
        audited(connection, ident, "doctor.bootstrap", ident)
    return ident
