"""Versioned, additive cloud schema. Migrate explicitly before API startup."""
from contextlib import contextmanager

from sqlalchemy import (
    Boolean, CheckConstraint, Column, ForeignKey, Index, Integer, JSON,
    MetaData, String, Table, Text, UniqueConstraint, create_engine, event, inspect, select, update,
)

metadata = MetaData()
SCHEMA_VERSION = 5
schema = Table("cloud_schema", metadata, Column("version", Integer, primary_key=True))
accounts = Table("accounts", metadata,
    Column("id", String(36), primary_key=True),
    Column("username", String(64), nullable=False, unique=True),
    Column("password_hash", Text, nullable=False),
    Column("role", String(20), nullable=False),
    Column("active", Boolean, nullable=False),
    Column("created_at", Integer, nullable=False),
    CheckConstraint("role IN ('PATIENT', 'DOCTOR_ADMIN')"),
)
Index("one_shared_doctor", accounts.c.role, unique=True,
      postgresql_where=accounts.c.role == "DOCTOR_ADMIN", sqlite_where=accounts.c.role == "DOCTOR_ADMIN")
patients = Table("patients", metadata,
    Column("id", String(36), primary_key=True),
    Column("account_id", String(36), ForeignKey("accounts.id"), nullable=False, unique=True),
    Column("display_name", String(80), nullable=False),
    Column("created_at", Integer, nullable=False),
)
sessions = Table("sessions", metadata,
    Column("id", String(36), primary_key=True),
    Column("account_id", String(36), ForeignKey("accounts.id"), nullable=False, index=True),
    Column("token_hash", String(64), nullable=False, unique=True),
    Column("refresh_hash", String(64), unique=True),
    Column("client_kind", String(12), nullable=False),
    Column("expires_at", Integer, nullable=False),
    Column("refresh_expires_at", Integer, nullable=False),
    Column("revoked", Boolean, nullable=False),
    Column("created_at", Integer, nullable=False),
)
grants = Table("doctor_grants", metadata,
    Column("patient_id", String(36), ForeignKey("patients.id"), primary_key=True),
    Column("enabled", Boolean, nullable=False),
    Column("version", Integer, nullable=False),
    Column("changed_at", Integer, nullable=False),
)
records = Table("patient_record_events", metadata,
    Column("id", String(36), primary_key=True),
    Column("patient_id", String(36), ForeignKey("patients.id"), nullable=False, index=True),
    Column("submitted_by", String(36), ForeignKey("accounts.id"), nullable=False),
    Column("operation_id", String(36), nullable=False),
    Column("source_event_id", String(100), nullable=False),
    Column("installation_id", String(100), nullable=False),
    Column("source_kind", String(20), nullable=False),
    Column("attribution_state", String(20), nullable=False, server_default="DECLARED"),
    Column("payload", JSON, nullable=False),
    Column("digest", String(64), nullable=False),
    Column("received_at", Integer, nullable=False),
    UniqueConstraint("submitted_by", "operation_id"),
    UniqueConstraint("patient_id", "installation_id", "source_event_id"),
)
audit = Table("cloud_audit", metadata,
    Column("id", String(36), primary_key=True),
    Column("actor_id", String(36)),
    Column("action", String(64), nullable=False),
    Column("resource_id", String(100)),
    Column("created_at", Integer, nullable=False),
)
attempts = Table("auth_attempts", metadata,
    Column("key", String(64), primary_key=True),
    Column("window", Integer, primary_key=True),
    Column("count", Integer, nullable=False),
    Column("expires_at", Integer, nullable=False, index=True),
)


class Database:
    def __init__(self, url):
        args = {"pool_pre_ping": True}
        if url.startswith("sqlite"):
            args["connect_args"] = {"check_same_thread": False, "timeout": 10}
        else:
            args.update(pool_size=4, max_overflow=2, pool_timeout=5,
                        connect_args={"connect_timeout": 5, "options": "-c statement_timeout=10000 -c lock_timeout=5000"})
        self.engine = create_engine(url, **args)
        if url.startswith("sqlite"):
            @event.listens_for(self.engine, "connect")
            def sqlite_settings(connection, _):
                connection.execute("PRAGMA foreign_keys=ON")

    @contextmanager
    def transaction(self):
        with self.engine.connect() as connection:
            if self.engine.dialect.name == "sqlite":
                connection.exec_driver_sql("BEGIN IMMEDIATE")
                try:
                    yield connection
                    connection.commit()
                except BaseException:
                    connection.rollback()
                    raise
            else:
                with connection.begin():
                    yield connection

    def migrate(self):
        # Register additive feature tables even when migration runs via manage.py.
        from . import workbench  # noqa: F401
        from . import ai_usage  # noqa: F401
        from . import care_queue  # noqa: F401
        from . import reports  # noqa: F401
        from . import plan_programmes  # noqa: F401
        from . import rehab_workflow  # noqa: F401
        from . import family  # noqa: F401
        with self.engine.begin() as connection:
            if self.engine.dialect.name == "postgresql":
                connection.exec_driver_sql("SELECT pg_advisory_xact_lock(74321001)")
            version = connection.scalar(select(schema.c.version)) if inspect(connection).has_table(schema.name) else None
            if version not in {None, 1, 2, 3, 4, SCHEMA_VERSION}:
                raise RuntimeError("Unsupported cloud schema version")
            metadata.create_all(connection)
            if version is None:
                connection.execute(schema.insert().values(version=SCHEMA_VERSION))
            elif version != SCHEMA_VERSION:
                connection.execute(update(schema).where(schema.c.version == version).values(version=SCHEMA_VERSION))

    def ready(self):
        with self.engine.connect() as connection:
            return connection.scalar(select(schema.c.version)) == SCHEMA_VERSION and bool(connection.scalar(
                select(accounts.c.id).where(accounts.c.role == "DOCTOR_ADMIN", accounts.c.active.is_(True))))
