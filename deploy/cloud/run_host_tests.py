"""Run synthetic QA on an isolated DB; never use production DB as test fixture."""
import os
from pathlib import Path
import secrets
import subprocess


def main():
    credentials = Path("/etc/ankang-cloud/qa.env")
    if not credentials.exists():
        password = secrets.token_urlsafe(32)
        created = subprocess.run(["runuser", "-u", "postgres", "--", "psql", "--no-psqlrc", "-q",
                                  "-v", "ON_ERROR_STOP=1", "-d", "postgres"],
            input=f"CREATE ROLE ankang_qa_owner LOGIN PASSWORD '{password}';\nCREATE DATABASE ankang_cloud_qa OWNER ankang_qa_owner;\n",
            text=True, capture_output=True)
        if created.returncode:
            raise SystemExit("QA database initialization failed; refusing overwrite")
        fd = os.open(credentials, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(f"postgresql+psycopg://ankang_qa_owner:{password}@127.0.0.1/ankang_cloud_qa")
    environment = dict(os.environ, CLOUD_TEST_DATABASE_URL=credentials.read_text(encoding="utf-8"),
        PYTHONPATH="/opt/ankang-cloud/venv/lib/python3.10/site-packages:/opt/ankang-cloud/current")
    command = ["/opt/ankang-cloud/qa-venv/bin/python", "-m", "pytest", "cloud_service/tests", "-q",
               "--junitxml=/opt/ankang-cloud/qa-results.xml"]
    raise SystemExit(subprocess.run(command, cwd="/opt/ankang-cloud/current", env=environment).returncode)


if __name__ == "__main__":
    main()
