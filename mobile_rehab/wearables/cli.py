"""Local administrator diagnostics. No public owner override and no secret/raw fact output."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
import time
from .contracts import HealthError
from .service import WearableService


def main():
    parser=argparse.ArgumentParser(description='Wearable background diagnostics (local administrator only)')
    parser.add_argument('command',choices=['doctor','inspect-capabilities','inspect-sync','sync-once','reconcile','export-compatibility','backup'])
    parser.add_argument('--data-dir',type=Path,required=True,help='The running phone-service data directory, not the rehab database')
    parser.add_argument('--owner',help='Existing paired owner; not a viewed patient or vendor ID')
    parser.add_argument('--connection-id')
    parser.add_argument('--job-id')
    parser.add_argument('--output',type=Path,help='New private backup file; never overwrite')
    args=parser.parse_args()
    if args.command=='backup':
        path=args.data_dir/'wearables/wearables.sqlite3'
        if not path.is_file() or args.output is None or args.output.exists() or args.output.resolve()==path.resolve():
            parser.error('Provide an existing wearable database and a NEW private backup output file')
        args.output.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as source, sqlite3.connect(args.output) as dest:
            source.backup(dest)
        print(json.dumps(dict(status='backed_up',path=str(args.output.resolve()),contains_private_health_data=True)))
        return 0
    service=None
    try:
        service=WearableService(args.data_dir/'wearables')
        if args.command in ('doctor','inspect-capabilities','export-compatibility'):
            result=service.capabilities()
            if args.command=='doctor':
                with service.store.db() as db:
                    result['database_check']=db.execute('PRAGMA quick_check').fetchone()[0]
                    result['database_version']=db.execute('PRAGMA user_version').fetchone()[0]
                result['token_key_configured']=service.store.cipher is not None
        else:
            if not args.owner:
                parser.error('--owner is required; CLI is only for the local administrator')
            if args.command=='inspect-sync':
                if not args.job_id:parser.error('--job-id required')
                job=service.store.job(args.owner,args.job_id)
            else:
                if not args.connection_id:parser.error('--connection-id required')
                result=service.sync(args.owner,args.connection_id)
                deadline=time.monotonic()+120
                while time.monotonic()<deadline:
                    job=service.store.job(args.owner,result['job_id'])
                    if job['status'] not in ('queued','running'):break
                    time.sleep(.2)
            result={k:v for k,v in job.items() if k not in ('owner','worker_holder','lease_until')}
        print(json.dumps(result,ensure_ascii=False,allow_nan=False))
        return 0
    except HealthError as exc:
        print(json.dumps(dict(code=exc.code,rehab_can_continue=True)))
        return 2
    finally:
        if service:service.close()


if __name__=='__main__':
    sys.exit(main())
