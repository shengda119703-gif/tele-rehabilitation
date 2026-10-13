"""Audited operator-only identity for cross-client QA, never a real patient's account."""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import time
from uuid import uuid4

from sqlalchemy import select, update
from cloud_service.database import Database, accounts, patients, sessions, grants
from cloud_service.security import audited, password_hash
from .check_database import load_env


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('create', 'disable'))
    parser.add_argument('--credential-file', type=Path, required=True)
    args = parser.parse_args()
    path = args.credential_file.resolve()
    if os.getuid() != 0 or path.parent != Path('/var/lib/ankang-cloud/qa-clients') or not re.fullmatch(r'qa-client-[a-f0-9]{10}\.json', path.name):
        raise SystemExit('Exact restricted QA path and operator identity required')
    load_env('/etc/ankang-cloud/service.env')
    db = Database(os.environ['CLOUD_DATABASE_URL'])
    if args.action == 'create':
        username, secret = path.stem, secrets.token_urlsafe(24)
        account, patient = str(uuid4()), str(uuid4())
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        document = dict(username=username, password=secret,
                        identity=dict(account_id=account, patient_id=patient, username=username, role='PATIENT'))
        # Exclusive creation, mode 0600 before any secret bytes are written.
        with os.fdopen(os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600), 'w') as output:
            json.dump(document, output)
        with db.transaction() as connection:
            connection.execute(accounts.insert().values(id=account, username=username, password_hash=password_hash(secret),
                role='PATIENT', active=True, created_at=int(time.time())))
            connection.execute(patients.insert().values(id=patient, account_id=account, display_name=username, created_at=int(time.time())))
            audited(connection, None, 'operations.client_check_account', patient)
        print('Isolated PATIENT created by operator; credentials not printed')
    else:
        value = json.loads(path.read_text())
        with db.transaction() as connection:
            row = connection.execute(select(accounts.c.id).join(patients, patients.c.account_id==accounts.c.id)
                .where(accounts.c.username==path.stem, accounts.c.role=='PATIENT', accounts.c.id==value['identity']['account_id'],
                       patients.c.id==value['identity']['patient_id']).with_for_update()).first()
            if not row:
                raise SystemExit('QA identity mismatch; nothing changed')
            connection.execute(update(accounts).where(accounts.c.id==row.id).values(active=False))
            connection.execute(update(sessions).where(sessions.c.account_id==row.id).values(revoked=True))
            connection.execute(update(grants).where(grants.c.patient_id==value['identity']['patient_id']).values(enabled=False,version=grants.c.version+1,changed_at=int(time.time())))
            audited(connection, None, 'operations.disable_client_check_account', row.id)
        print('Exact QA account disabled; real users, facts and audit retained')
    db.engine.dispose()


if __name__ == '__main__':
    main()
