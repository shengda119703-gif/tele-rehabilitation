"""Disable precisely the synthetic account made by our public browser check."""
import argparse
import re
import time

from sqlalchemy import select, update

from cloud_service.database import Database, accounts, grants, patients, sessions
from cloud_service.security import audited
from .check_database import load_env
import os


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", required=True)
    parser.add_argument("--patient-id", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"qa-cloud-[a-f0-9]{10}", args.username):
        parser.error("Only our exact synthetic browser account can be disabled")
    load_env("/etc/ankang-cloud/service.env")
    db = Database(os.environ["CLOUD_DATABASE_URL"])
    with db.transaction() as connection:
        row = connection.execute(select(accounts.c.id).join(patients, patients.c.account_id == accounts.c.id)
            .where(accounts.c.username == args.username, accounts.c.role == "PATIENT", patients.c.id == args.patient_id)
            .with_for_update()).first()
        if not row:
            raise SystemExit("Synthetic account identity does not match; nothing changed")
        connection.execute(update(accounts).where(accounts.c.id == row.id).values(active=False))
        connection.execute(update(sessions).where(sessions.c.account_id == row.id).values(revoked=True))
        connection.execute(update(grants).where(grants.c.patient_id == args.patient_id).values(
            enabled=False, version=grants.c.version + 1, changed_at=int(time.time())))
        audited(connection, None, "operations.disable_synthetic_browser_check", row.id)
    db.engine.dispose()
    print("Only the exact synthetic account disabled; facts and audit retained")


if __name__ == "__main__":
    main()
