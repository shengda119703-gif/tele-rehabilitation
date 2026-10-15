"""Local isolated browser check; never loads the production environment."""
import argparse
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from cloud_service.app import create_app
from cloud_service.config import Settings
from cloud_service.database import Database
from cloud_service.security import bootstrap_doctor
import uvicorn


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--port", type=int, default=14910)
    args = parser.parse_args()
    directory = args.directory.resolve()
    if not directory.is_relative_to(ROOT / ".runtime") or not 1024 <= args.port <= 65535:
        parser.error("Use a private local QA directory and unprivileged port")
    directory.mkdir(parents=True, exist_ok=True)
    settings = Settings("sqlite:///" + (directory / "qa.sqlite3").as_posix(), secrets.token_urlsafe(40),
                        ("http://127.0.0.1:" + str(args.port),), "test")
    db = Database(settings.database_url)
    db.migrate()
    bootstrap_doctor(db, settings, "1")
    uvicorn.run(create_app(settings, db, web_assets=ROOT / "public_web" / "build"), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
