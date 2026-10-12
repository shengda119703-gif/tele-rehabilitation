"""Isolated real hosted adapter for flow QA; never starts the user's service."""
import argparse
import json
import os
from pathlib import Path
import socket
import sqlite3
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'rehab_codex_single_camera_v2_1'))
os.environ['PYTHONPATH'] = os.pathsep.join([str(ROOT), str(ROOT / 'rehab_codex_single_camera_v2_1'), os.environ.get('PYTHONPATH', '')])

import uvicorn
from fastapi.responses import Response
from mobile_rehab.server import create_app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--unreadable-upload-reply', action='store_true')
    parser.add_argument('--seed-from-native-run', type=Path)
    parser.add_argument('--unreadable-practice-finish-reply', action='store_true')
    parser.add_argument('--saved-manual-arrangement-fixture', action='store_true')
    parser.add_argument('--manual-sequence-fixture', action='store_true')
    parser.add_argument('--unreadable-practice-continue-reply', action='store_true')
    args = parser.parse_args()
    args.data.mkdir(parents=True, exist_ok=False)
    seed_owner = None
    if args.seed_from_native_run:
        source = args.seed_from_native_run.resolve()
        if not source.is_relative_to(Path('D:/RehabFrontendFlowVerification').resolve()):
            raise ValueError('Only an isolated native-flow QA receipt can seed this QA host')
        receipt = json.loads((source / 'result.json').read_text(encoding='utf-8'))
        if receipt.get('kind') != 'actual-hosted-browser-flow' or receipt.get('job_state') != 'done' or receipt.get('saved_session') is not True:
            raise ValueError('A successful actual native-flow receipt is required')
        databases = list((source / 'host-data/jobs').glob('*/assessments.sqlite3'))
        if len(databases) != 1 or not re.fullmatch('[a-f0-9]{32}', databases[0].parent.name):
            raise ValueError('Expected exactly one isolated owned assessment database')
        seed_owner = databases[0].parent.name
        target = args.data / 'jobs' / seed_owner / 'assessments.sqlite3'
        target.parent.mkdir(parents=True)
        with sqlite3.connect(f'file:{databases[0].as_posix()}?mode=ro', uri=True) as original, sqlite3.connect(target) as copied:
            original.backup(copied)
    app = create_app(args.data, pair_key='TEST-frontend-isolated-host')
    if args.saved_manual_arrangement_fixture or args.manual_sequence_fixture:
        if args.seed_from_native_run:
            raise ValueError('The no-assessment manual fixture must not reuse an assessment database')
        from uuid import uuid4
        from contextlib import closing
        from app.storage import Storage
        from app.settings import default_plan
        from app.training_plans import item_from_plan, new_training_plan
        seed_owner = uuid4().hex
        settings = default_plan('shoulder_abduction')
        settings.update(side='left', target_reps=7, target_sets=2, target_angle_deg=None)
        scope = dict(participant_id=seed_owner, source_kind='REPLAY_FILE', usage_context='SELF_USE')
        entries = [item_from_plan(settings)]
        if args.manual_sequence_fixture:
            settings.update(target_reps=3, rest_between_sets_s=3)
            second = default_plan('knee_extension')
            second.update(side='right', target_reps=2, target_sets=1, needs_companion=True)
            entries = [item_from_plan(settings), item_from_plan(second)]
        record = new_training_plan(scope, 'TEST 已有人工安排', entries)
        with closing(Storage(app.state.jobs.root / seed_owner / 'assessments.sqlite3')) as store:
            store.save_training_plan(record, expected_revision=0)
            if store.list_sessions():
                raise ValueError('No measured assessment may be injected into this fixture')
    if args.unreadable_upload_reply or args.unreadable_practice_finish_reply or args.unreadable_practice_continue_reply:
        @app.middleware('http')
        async def response_fault(request, call_next):
            response = await call_next(request)
            upload_fault = args.unreadable_upload_reply and request.url.path == '/api/jobs'
            finish_fault = args.unreadable_practice_finish_reply and request.url.path.startswith('/api/practice/') and request.url.path.endswith('/finish')
            continue_fault = args.unreadable_practice_continue_reply and request.url.path.startswith('/api/practice/') and request.url.path.endswith('/continue')
            if request.method == 'POST' and (upload_fault or finish_fault or continue_fault) and response.status_code == 200:
                return Response(b'TEST intentionally unreadable receipt', media_type='text/plain')
            return response
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=0, log_level='warning'))
    app.state.shutdown = lambda: setattr(server, 'should_exit', True)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        sock.listen(128)
        print(json.dumps({'port': sock.getsockname()[1], 'isolated': True, 'seed_owner': seed_owner}), flush=True)
        server.run(sockets=[sock])


if __name__ == '__main__':
    main()
