"""Explicit migrations/bootstrap. Real passwords never become command arguments."""
import argparse
import getpass
import json
from pathlib import Path

from .config import Settings
from .database import Database
from .security import DomainError, bootstrap_doctor


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["migrate", "bootstrap-doctor", "openapi"])
    parser.add_argument("--password-file", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    settings = Settings.from_env()
    database = Database(settings.database_url)
    if args.command == "migrate":
        database.migrate()
        from .database import SCHEMA_VERSION
        print(f"Cloud workbench schema v{SCHEMA_VERSION} ready")
    elif args.command == "bootstrap-doctor":
        plain = args.password_file.read_text(encoding="utf-8").rstrip("\r\n") if args.password_file else getpass.getpass("医生共用账号密码：")
        try:
            bootstrap_doctor(database, settings, plain)
        except DomainError as exc:
            parser.exit(1, exc.message + "\n")
        print("Doctor account initialized; password not printed")
    else:
        if not args.output:
            parser.error("--output is required")
        from .app import create_app
        args.output.write_text(json.dumps(create_app(settings, database).openapi(), ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
