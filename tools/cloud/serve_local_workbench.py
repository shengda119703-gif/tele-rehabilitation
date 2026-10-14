"""Empty loopback workbench: no patient seeds, provider mocks or production env."""
import argparse
import json
import os
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'rehab_codex_single_camera_v2_1')]

from app.cloud_account import TokenVault
from cloud_service.ai_usage import AIConfig
from cloud_service.app import create_app
from cloud_service.config import Settings
from cloud_service.database import Database
from cloud_service.security import bootstrap_doctor
from fastapi.responses import Response
import uvicorn


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--port', type=int, default=14924)
    args = parser.parse_args()
    if os.name != 'nt':
        parser.error('This desktop-only helper requires Windows current-user encryption')
    directory = args.directory.resolve()
    if not directory.is_relative_to(ROOT / '.runtime') or directory.exists() or not 1024 <= args.port <= 65535:
        parser.error('Use a fresh private directory under .runtime and a loopback port')
    directory.mkdir(parents=True)
    settings = Settings('sqlite:///' + (directory / 'local.sqlite3').as_posix(),
                        secrets.token_urlsafe(40),
                        (f'http://127.0.0.1:{args.port}', f'http://localhost:{args.port}'), 'development')
    db = Database(settings.database_url)
    db.migrate()
    password = secrets.token_urlsafe(32)
    (directory / 'administrator.dpapi').write_bytes(TokenVault._crypt(json.dumps({'password': password}).encode(), True))
    bootstrap_doctor(db, settings, password)
    # Deliberately disable external model calls rather than inject sample receipts.
    app = create_app(settings, db, ai_config=AIConfig())

    @app.middleware('http')
    async def local_note(request, call_next):
        response = await call_next(request)
        if response.headers.get('content-type', '').startswith('text/html'):
            body = b''.join([part async for part in response.body_iterator]).decode('utf-8')
            body = body.replace('<header>', '<p class="local-connection-note" role="note">本地工作台 · 尚未连接公网数据</p><header>', 1)
            headers = {k: v for k, v in response.headers.items() if k.lower() != 'content-length'}
            return Response(body, status_code=response.status_code, headers=headers)
        return response

    print(f'Empty local workbench listening on 127.0.0.1:{args.port}; no patients or model receipts created.', flush=True)
    uvicorn.run(app, host='127.0.0.1', port=args.port)


if __name__ == '__main__':
    main()
