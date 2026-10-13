"""Host-side checks. Outputs statuses, never credentials or patient payloads."""
import json
import os
from pathlib import Path
import subprocess

from sqlalchemy import text
from cloud_service.database import Database


def load_env(path):
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            os.environ[key] = value


def main():
    load_env("/etc/ankang-cloud/service.env")
    database = Database(os.environ["CLOUD_DATABASE_URL"])
    with database.engine.connect() as connection:
        result = {
            "ready": database.ready(),
            "application_not_superuser": not connection.scalar(text("SELECT rolsuper FROM pg_roles WHERE rolname=current_user")),
            "application_not_table_owner": connection.scalar(text("SELECT tableowner FROM pg_tables WHERE tablename='accounts'")) != "ankang_app",
            "audit_update_denied": not connection.scalar(text("SELECT has_table_privilege(current_user,'cloud_audit','UPDATE')")),
            "audit_delete_denied": not connection.scalar(text("SELECT has_table_privilege(current_user,'cloud_audit','DELETE')")),
            "audit_insert_allowed": connection.scalar(text("SELECT has_table_privilege(current_user,'cloud_audit','INSERT')")),
            "account_hashes_argon2id": connection.scalar(text("SELECT count(*) FROM accounts WHERE password_hash NOT LIKE '$argon2id$%'")) == 0,
        }
    database.engine.dispose()
    print(json.dumps(result, ensure_ascii=False))
    if not all(result.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
