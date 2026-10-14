"""Explicit loopback-only dual-role acceptance; never included in cloud releases."""
import argparse
import base64
from datetime import datetime, timezone
from pathlib import Path
import secrets
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from fastapi.testclient import TestClient
from fastapi.responses import Response
import uvicorn
from cloud_service.app import BASE, create_app
from cloud_service.ai_usage import AIConfig
from cloud_service.config import Settings
from cloud_service.database import Database
from cloud_service.security import bootstrap_doctor
from cloud_service.workbench import action_library


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--port', type=int, default=14921)
    args = parser.parse_args()
    directory = args.directory.resolve()
    if not directory.is_relative_to(ROOT / '.runtime') or directory.exists() or not 1024 <= args.port <= 65535:
        parser.error('Use a fresh directory under .runtime and an unprivileged loopback port')
    directory.mkdir(parents=True)
    origin = f'http://127.0.0.1:{args.port}'
    settings = Settings('sqlite:///' + (directory / 'acceptance.sqlite3').as_posix(),
                        secrets.token_urlsafe(40), (origin, f'http://localhost:{args.port}'), 'test')
    db = Database(settings.database_url)
    db.migrate()
    bootstrap_doctor(db, settings, '1')
    def fake_provider(*_):
        return {'id': 'TEST-MOCK-NO-BILL', 'model': 'deepseek-flash',
                'choices': [{'message': {'content': 'TEST：这是隔离验收回复，不用于康复判断。'}}],
                'usage': {'prompt_tokens': 100, 'completion_tokens': 50, 'total_tokens': 150,
                          'prompt_cache_hit_tokens': 20, 'prompt_cache_miss_tokens': 80}}
    app = create_app(settings, db, ai_config=AIConfig(key='TEST-NOT-A-KEY', tariff={
        'version': 'TEST-MOCK-NOT-A-PRICE', 'currency': 'CNY', 'cache_hit': '0.1', 'cache_miss': '1', 'output': '2'}),
        ai_dispatch=fake_provider)
    @app.middleware('http')
    async def preview_note(request, call_next):
        response = await call_next(request)
        if response.headers.get('content-type', '').startswith('text/html'):
            body = b''.join([part async for part in response.body_iterator]).decode('utf-8')
            body = body.replace('<body', '<body', 1).replace('<header>',
                '<p role="note">隔离验收 · TEST 虚构账号与记录 · API用量为模拟回执 · 非公网正式服务</p><header>', 1)
            headers = {k: v for k, v in response.headers.items() if k.lower() != 'content-length'}
            return Response(body, status_code=response.status_code, headers=headers)
        return response
    with TestClient(app, headers={'Origin': origin}, base_url=origin) as patient, TestClient(app, headers={'Origin': origin}, base_url=origin) as doctor:
        def api(client, route, method='GET', body=None):
            response = client.request(method, BASE + route, json=body)
            response.raise_for_status()
            return response.json()
        api(patient, '/auth/register', 'POST', {'username': 'acceptance-patient', 'password': '1', 'display_name': '验收患者（TEST）'})
        for client, username in ((patient, 'acceptance-patient'), (doctor, 'doctor')):
            signed = api(client, '/auth/password/login', 'POST', {'username': username, 'password': '1'})
            client.headers['X-CSRF-Token'] = signed['csrf_token']
        ident = api(patient, '/auth/me')['patient_id']
        endpoint = '/patients/' + ident
        api(patient, endpoint + '/doctor-access', 'PUT', {'enabled': True, 'expected_version': 0})
        now = datetime.now(timezone.utc).isoformat()
        for kind, data in [('profile', {'goal': 'TEST 界面验收，非人体训练'}),
                           ('assessment', {'exercise_id': 'shoulder_abduction', 'side': 'left', 'status': 'FINISHED', 'summary': {'completed': 0}}),
                           ('training', {'exercise_id': 'shoulder_abduction', 'side': 'left', 'summary': {'completed': 0}, 'feedback': {'pain': 0, 'fatigue': 0}})]:
            api(patient, endpoint + '/record-events', 'POST', {'operation_id': str(uuid4()), 'source_event_id': 'TEST-' + kind,
                'installation_id': 'TEST-ACCEPTANCE', 'source_kind': 'WEB_LOCAL', 'payload': {'schema': 'ankang-workbench-record-1',
                'source': 'WEB_LOCAL', 'kind': kind, 'synthetic': True, 'owner_id': ident, 'patient_id': ident,
                'record_key': 'TEST-' + kind, 'revision': 1, 'captured_at': now, 'title': 'TEST ' + kind, 'result': data}})
        api(patient, endpoint + '/messages', 'POST', {'operation_id': str(uuid4()), 'text': 'TEST：你好，我想向康复医师咨询。这是隔离验收消息。'})
        api(doctor, endpoint + '/messages', 'POST', {'operation_id': str(uuid4()), 'text': 'TEST：你好，我可以看到你主动分享的资料。这里仅验收沟通流程。'})
        api(patient, endpoint + '/reports', 'POST', {'operation_id': str(uuid4()), 'filename': 'TEST-非医疗报告.pdf',
            'mime': 'application/pdf', 'shared': True, 'data': base64.b64encode(b'%PDF-1.4\nTEST-NOT-MEDICAL').decode()})
        card = action_library()['shoulder_abduction']
        draft = api(doctor, endpoint + '/plans', 'POST', {'operation_id': str(uuid4()), 'title': 'TEST 医生发布方案',
            'summary': '仅验收展示和采用门禁，不用于人体训练。', 'items': [{'exercise_id': card['exercise_id'], 'name': card['name'],
            'side': 'left', 'measurement_contract': card['measurement_contract'], 'settings': {'target_reps': 2, 'target_sets': 1,
            'rest_between_sets_s': 30, 'target_angle_deg': None}, 'caution': 'TEST 不执行人体训练'}]})['plan']
        api(doctor, endpoint + '/plans/' + draft['id'] + '/publish', 'POST', {'operation_id': str(uuid4()), 'expected_version': draft['version']})
        api(patient, endpoint + '/ai/requests', 'POST', {'operation_id': str(uuid4()), 'text': 'TEST 只验收每用户用量，不调用真实模型'})
    print(f'ISOLATED TEST: patient {origin}/account ; doctor http://localhost:{args.port}/care', flush=True)
    print('TEST credentials: acceptance-patient / 1 ; doctor / 1', flush=True)
    uvicorn.run(app, host='127.0.0.1', port=args.port)


if __name__ == '__main__':
    main()
