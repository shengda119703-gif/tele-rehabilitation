"""Run once as root on the assigned host. Generate secrets on host, never print."""
import argparse
import grp
import os
from pathlib import Path
import secrets
import subprocess
import sys
from urllib.parse import urlsplit

from cloud_service.config import Settings
from cloud_service.database import Database
from cloud_service.security import bootstrap_doctor


def postgres(sql, database="postgres"):
    result = subprocess.run(["runuser", "-u", "postgres", "--", "psql", "--no-psqlrc",
        "-v", "ON_ERROR_STOP=1", "-q", "-d", database], input=sql, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError("Database initialization failed; no secrets printed")


def private_file(path, text, group=None):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(text)
    if group:
        os.chown(path, 0, grp.getgrnam(group).gr_gid)
        os.chmod(path, 0o640)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--origin", required=True)
    args = parser.parse_args()
    if os.geteuid() != 0 or not args.origin.startswith("https://"):
        parser.error("Root and an exact HTTPS origin are required")
    folder = Path("/etc/ankang-cloud")
    folder.mkdir(mode=0o750, exist_ok=True)
    os.chown(folder, 0, grp.getgrnam("ankang-cloud").gr_gid)
    if (folder / "service.env").exists() or (folder / "migration.env").exists():
        parser.exit(1, "Already initialized; refusing to overwrite secrets\n")
    app_pass, owner_pass = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    secret = secrets.token_urlsafe(48)
    doctor_password = f"{secrets.randbelow(10**8):08d}"
    # Fixed internal identifiers and generated URL-safe secrets, not user SQL input.
    postgres(f"CREATE ROLE ankang_owner LOGIN PASSWORD '{owner_pass}';\n"
             f"CREATE ROLE ankang_app LOGIN PASSWORD '{app_pass}';\n"
             "CREATE DATABASE ankang_cloud OWNER ankang_owner;\n"
             "REVOKE ALL ON DATABASE ankang_cloud FROM PUBLIC;\n"
             "GRANT CONNECT ON DATABASE ankang_cloud TO ankang_app;\n")
    postgres("REVOKE ALL ON SCHEMA public FROM PUBLIC;\n"
             "GRANT USAGE, CREATE ON SCHEMA public TO ankang_owner;\n"
             "GRANT USAGE ON SCHEMA public TO ankang_app;\n", "ankang_cloud")
    owner_url = f"postgresql+psycopg://ankang_owner:{owner_pass}@127.0.0.1/ankang_cloud"
    runtime_url = f"postgresql+psycopg://ankang_app:{app_pass}@127.0.0.1/ankang_cloud"
    settings = Settings(owner_url, secret, (args.origin,))
    db = Database(owner_url)
    db.migrate()
    bootstrap_doctor(db, settings, doctor_password)
    db.engine.dispose()
    postgres("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ankang_app;\n"
             "REVOKE UPDATE, DELETE, TRUNCATE ON cloud_audit FROM ankang_app;\n", "ankang_cloud")
    common = f"CLOUD_ENV=production\nCLOUD_ORIGINS={args.origin}\nCLOUD_SECRET={secret}\nCLOUD_DOCTOR_USERNAME=doctor\n"
    private_file(folder / "migration.env", common + f"CLOUD_DATABASE_URL={owner_url}\n")
    private_file(folder / "service.env", common + f"CLOUD_DATABASE_URL={runtime_url}\n", "ankang-cloud")
    private_file(folder / "doctor-password.txt", doctor_password + "\n")
    private_file(folder / "backup.key", secrets.token_urlsafe(48) + "\n")
    private_file(folder / "login-info.txt", f"患者入口：{args.origin}/\n医生入口：{args.origin}/care\n医生共用账号：doctor\n初始密码：{doctor_password}\n请妥善保存；患者自行注册自己的账号。\n")
    print("Cloud database, least-privilege application role and shared doctor initialized")


if __name__ == "__main__":
    main()
