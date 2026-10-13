"""Verify encrypted dump in a clean isolated database, without replacing production."""
from pathlib import Path
import subprocess
import tempfile


def pg(command, *args, **kwargs):
    return subprocess.run(["runuser", "-u", "postgres", "--", command, *args], check=True, **kwargs)


def main():
    root = Path("/var/backups/ankang-cloud")
    backups = sorted(root.glob("*.dump.enc"))
    if not backups:
        raise SystemExit("No encrypted cloud backup exists")
    target = "ankang_cloud_restore_check"
    # Never delete a preexisting database, even with this dedicated check name.
    existing = pg("psql", "--no-psqlrc", "-At", "-d", "postgres", "-c",
                  "SELECT count(*) FROM pg_database WHERE datname='ankang_cloud_restore_check'", capture_output=True, text=True)
    if existing.stdout.strip() != "0":
        raise SystemExit("Restore-check database already exists; refusing overwrite")
    with tempfile.TemporaryFile() as plain:
        subprocess.run(["openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-iter", "200000",
                        "-in", str(backups[-1]), "-pass", "file:/etc/ankang-cloud/backup.key"], stdout=plain, check=True)
        plain.seek(0)
        pg("createdb", target)
        pg("pg_restore", "--exit-on-error", "--dbname", target, stdin=plain)
        checked = pg("psql", "--no-psqlrc", "-At", "-d", target, "-c",
            "SELECT (SELECT version FROM cloud_schema) IN (1,2,3) AND (SELECT count(*) FROM accounts WHERE role='DOCTOR_ADMIN')=1 AND (SELECT count(*) FROM cloud_audit)>0",
            capture_output=True, text=True)
        if checked.stdout.strip() != "t":
            raise SystemExit("Restored facts did not match expected foundation")
    # Leave the verified isolated database for inspection; no destructive cleanup.
    print("Encrypted backup restored into separate database; schema, shared account and audit verified")


if __name__ == "__main__":
    main()
