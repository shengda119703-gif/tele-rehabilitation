"""Independent native cloud adapter. Never changes Runtime's measurement facts."""
from __future__ import annotations

import ctypes
import hashlib
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
import urllib.error
import urllib.request
from uuid import UUID, uuid4

ORIGIN = 'https://139.224.216.18'
BASE = '/api/cloud/v1'
_DIRECTORY_LOCKS = {}
_DIRECTORY_LOCKS_GUARD = threading.Lock()


def directory_lock(directory, kind='operation'):
    """Every in-process client for one resolved account directory shares rotation/write ownership."""
    key = (os.path.normcase(str(Path(directory).resolve())), kind)
    with _DIRECTORY_LOCKS_GUARD:
        return _DIRECTORY_LOCKS.setdefault(key, threading.RLock())


class CloudError(Exception):
    def __init__(self, message, status=0, code=''):
        super().__init__(message)
        self.status, self.code = status, code


class TokenVault:
    """DPAPI current-user encryption on Windows; memory-only elsewhere."""
    def __init__(self, path):
        self.path = Path(path)
        self.memory = None
        self.lock = directory_lock(self.path.parent, 'token-file')

    @staticmethod
    def _crypt(raw, encrypt):
        class Blob(ctypes.Structure):
            _fields_ = [('size', ctypes.c_uint32), ('data', ctypes.POINTER(ctypes.c_ubyte))]
        buffer = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
        source, target = Blob(len(raw), buffer), Blob()
        api = ctypes.windll.crypt32.CryptProtectData if encrypt else ctypes.windll.crypt32.CryptUnprotectData
        if not api(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
            raise CloudError('无法保存登录状态，请重新登录')
        try:
            return ctypes.string_at(target.data, target.size)
        finally:
            ctypes.windll.kernel32.LocalFree(target.data)

    def read(self):
        with self.lock:
            return self._read()

    def _read(self):
        if os.name != 'nt':
            return self.memory
        if not self.path.exists():
            return None
        try:
            value = json.loads(self._crypt(self.path.read_bytes(), False))
            if value['origin'] != ORIGIN or value.get('role') != 'PATIENT':
                raise ValueError()
            UUID(value['patient_id'])
            return value
        except Exception:
            raise CloudError('原登录状态无法读取，请重新登录；本机记录未改动') from None

    def write(self, value):
        with self.lock:
            if os.name != 'nt':
                self.memory = value
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_name(self.path.name + '.' + uuid4().hex + '.tmp')
            try:
                temporary.write_bytes(self._crypt(json.dumps(value).encode(), True))
                os.replace(temporary, self.path)
            finally:
                temporary.unlink(missing_ok=True)

    def clear(self):
        with self.lock:
            self.memory = None
            self.path.unlink(missing_ok=True)


def transport(path, method='GET', body=None, token=None):
    # No arbitrary URL/redirect: bearer credentials only go to this exact host.
    if not re.fullmatch(r'/auth/(register|password/login|refresh|me|logout)|/patients/[a-f0-9-]{36}(?:/(?:record-events|records(?:/latest)?(?:\?offset=\d+&limit=\d+)?|doctor-access|messages(?:/read|\?after=\d+&limit=50&latest=true|\?before=\d+&limit=50)?|plans(?:\?offset=\d+&limit=5|/current|/[a-f0-9-]{36}/accept)?))?', path):
        raise CloudError('云接口地址无效')
    headers = {'Content-Type': 'application/json', 'X-Ankang-Client': 'native'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    data = None if body is None else json.dumps(body, ensure_ascii=False, allow_nan=False).encode()
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    try:
        with urllib.request.build_opener(NoRedirect()).open(
                urllib.request.Request(ORIGIN + BASE + path, data=data, method=method, headers=headers), timeout=12) as reply:
            raw = reply.read(512 * 1024 + 1)
            if len(raw) > 512 * 1024:
                raise CloudError('云回复过大，请稍后重试')
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        try:
            error = json.loads(exc.read(16384))
        except Exception:
            error = {}
        raise CloudError(error.get('message', '云请求未完成'), exc.code, error.get('code', '')) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise CloudError('暂时无法连接云端，本机记录保留') from None


class CloudAccount:
    def __init__(self, directory, request=transport, vault=None, client_kind='DESKTOP'):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / 'cloud-outbox-v1.sqlite3'
        self.request = request
        self.vault = vault or TokenVault(self.directory / 'cloud-session.dpapi')
        self.lock = directory_lock(self.directory)
        self.token_lock = directory_lock(self.directory, 'token-file')
        self.client_kind = client_kind
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1, 2):
                raise CloudError('云上传队列版本不兼容，原记录未覆盖')
            if version == 0:
                if db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone():
                    raise CloudError('云上传队列结构不兼容，原记录未覆盖')
                db.execute('CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
                db.execute('CREATE TABLE bindings(local_id TEXT PRIMARY KEY,patient_id TEXT NOT NULL)')
                db.execute('''CREATE TABLE outbox(patient_id TEXT NOT NULL,local_id TEXT NOT NULL,event_id TEXT NOT NULL,
                      document TEXT NOT NULL,resource_id TEXT,PRIMARY KEY(patient_id,event_id))''')
                db.execute('PRAGMA user_version=1')
                db.execute('INSERT INTO meta VALUES (?,?)', ('installation', str(uuid4())))
            db.execute('CREATE TABLE IF NOT EXISTS message_outbox(patient_id TEXT, operation_id TEXT, text TEXT, resource_id TEXT, PRIMARY KEY(patient_id,operation_id))')
            db.execute('CREATE TABLE IF NOT EXISTS message_cache(patient_id TEXT, sequence INTEGER, document TEXT, PRIMARY KEY(patient_id,sequence))')
            db.execute('CREATE TABLE IF NOT EXISTS plan_acceptance(patient_id TEXT, cloud_id TEXT, cloud_version INTEGER, local_id TEXT, document TEXT, receipt TEXT, PRIMARY KEY(patient_id,cloud_id,cloud_version))')
            db.execute('PRAGMA user_version=2')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def session(self):
        with self.token_lock:
            return self.vault.read()

    def _write_session(self, value):
        with self.token_lock:
            self.vault.write(value)

    def _clear_session(self):
        with self.token_lock:
            self.vault.clear()

    def register(self, username, password):
        return self.request('/auth/register', 'POST', {'username': username, 'password': password, 'display_name': username})

    def login(self, username, password):
        with self.lock:
            value = self.request('/auth/password/login', 'POST', {'username': username, 'password': password, 'client_kind': self.client_kind})
            if value.get('role') != 'PATIENT':
                self.request('/auth/logout', 'POST', {}, value.get('access_token'))
                raise CloudError('请使用普通用户账号；医生请使用医生网页')
            value['origin'] = ORIGIN
            try:
                self._write_session(value)
            except Exception:
                self.request('/auth/logout', 'POST', {}, value['access_token'])
                raise
            return {k: value[k] for k in ('account_id', 'patient_id', 'username', 'role')}

    def call(self, path, method='GET', body=None):
        with self.lock:
            session = self.session()
            if not session:
                raise CloudError('请先登录云账号', 401)
            if path.startswith('/patients/') and path.split('/')[2] != session['patient_id']:
                raise CloudError('账号已变化，请重新打开当前本人工作台')
            try:
                return self.request(path, method, body, session['access_token'])
            except CloudError as exc:
                if exc.status != 401 or exc.code not in ('AUTH_REQUIRED', ''):
                    raise
            try:
                rotated = self.request('/auth/refresh', 'POST', {'refresh_token': session['refresh_token']})
            except CloudError as exc:
                if exc.status == 401:
                    self._clear_session()
                raise
            session.update(rotated)
            self._write_session(session)
            return self.request(path, method, body, session['access_token'])

    def me(self):
        with self.lock:
            value = self.call('/auth/me')
            if value.get('role') != 'PATIENT' or value['patient_id'] != self.session()['patient_id']:
                raise CloudError('账号身份已变化，请重新登录')
            return value

    def logout(self):
        with self.lock:
            try:
                if self.session():
                    self.call('/auth/logout', 'POST', {})
            finally:
                self._clear_session()

    def bind(self, local_id):
        with self.lock:
            patient = self.me()['patient_id']
            with self.db() as db:
                previous = db.execute('SELECT patient_id FROM bindings WHERE local_id=?', (local_id,)).fetchone()
                if previous and previous[0] != patient:
                    raise CloudError('该本机档案已绑定其他账号，请先在首页切换或新建本人档案')
                db.execute('INSERT OR IGNORE INTO bindings VALUES (?,?)', (local_id, patient))
            return patient

    def queue(self, local_id, event_id, payload, source_kind='DESKTOP_LOCAL'):
        with self.lock:
            session = self.session()
            if not session:
                raise CloudError('请先登录云账号')
            patient = session['patient_id']
            with self.db() as db:
                binding = db.execute('SELECT patient_id FROM bindings WHERE local_id=?', (local_id,)).fetchone()
                if not binding or binding[0] != patient:
                    raise CloudError('请先确认这份本机档案属于当前云账号')
                prior = db.execute('SELECT document FROM outbox WHERE patient_id=? AND event_id=?', (patient, event_id)).fetchone()
                if prior:
                    if json.loads(prior[0])['payload'] != payload:
                        raise CloudError('这条结果上传后已有本机修改，云原记录保留；请单独导出补充内容')
                    return json.loads(prior[0])
                installation = db.execute("SELECT value FROM meta WHERE key='installation'").fetchone()[0]
                document = dict(operation_id=str(uuid4()), source_event_id=event_id, installation_id=installation,
                                source_kind=source_kind, payload=payload)
                text = json.dumps(document, ensure_ascii=False, allow_nan=False)
                if len(text.encode()) > 32768:
                    raise CloudError('结果过大，请分项导出；本机原记录保留')
                db.execute('INSERT INTO outbox VALUES (?,?,?,?,NULL)', (patient, local_id, event_id, text))
                return document

    def sync(self):
        with self.lock:
            patient = self.me()['patient_id']
            with self.db() as db:
                pending = db.execute('SELECT * FROM outbox WHERE patient_id=? AND resource_id IS NULL', (patient,)).fetchall()
            count = 0
            for row in pending:
                result = self.call('/patients/' + patient + '/record-events', 'POST', json.loads(row['document']))
                if result.get('status') != 'COMMITTED':
                    raise CloudError('云端尚未确认保存，记录留在待上传队列')
                UUID(result['resource_id'])
                with self.db() as db:
                    db.execute('UPDATE outbox SET resource_id=? WHERE patient_id=? AND event_id=? AND resource_id IS NULL',
                               (result['resource_id'], patient, row['event_id']))
                count += 1
            return {'uploaded': count, 'records': self.records()}

    def records(self, offset=0):
        patient = self.me()['patient_id']
        return self.call(f'/patients/{patient}/records/latest?offset={offset}&limit=30')['items']

    def grant(self, enabled):
        with self.lock:
            patient = self.me()['patient_id']
            current = self.call('/patients/' + patient)
            return self.call('/patients/' + patient + '/doctor-access', 'PUT',
                             {'enabled': enabled, 'expected_version': current['grant_version']})

    def patient_call(self, suffix, method='GET', body=None):
        with self.lock:
            patient = self.me()['patient_id']
            return self.call('/patients/' + patient + suffix, method, body)

    def messages(self, before=0):
        session = self.session()
        if not session:
            raise CloudError('请先登录云账号', 401)
        patient = session['patient_id']
        try:
            if self.me()['patient_id'] != patient:
                raise CloudError('账号已变化')
            suffix = '/messages?before=' + str(int(before)) + '&limit=50' if before else '/messages?after=0&limit=50&latest=true'
            value = self.call('/patients/' + patient + suffix)
        except CloudError:
            current = self.session()
            if not current or current['patient_id'] != patient:
                raise
            with self.db() as db:
                rows = db.execute('SELECT document FROM message_cache WHERE patient_id=? ORDER BY sequence DESC LIMIT 50', (patient,)).fetchall()
            if not rows:
                raise
            return {'items': [json.loads(r[0]) for r in reversed(rows)], 'offline': True, 'unread_count': None}
        with self.db() as db:
            for item in value['items']:
                db.execute('INSERT OR REPLACE INTO message_cache VALUES (?,?,?)', (patient, item['sequence'], json.dumps(item, ensure_ascii=False)))
        return value

    def send(self, operation_id, text):
        patient = self.session()['patient_id'] if self.session() else None
        text = text.strip()
        if not patient or not text or len(text) > 4000:
            raise CloudError('请先登录，并填写 1–4000 字的文字')
        operation_id = str(UUID(operation_id))
        with self.db() as db:
            old = db.execute('SELECT text FROM message_outbox WHERE patient_id=? AND operation_id=?', (patient, operation_id)).fetchone()
            if old and old[0] != text:
                raise CloudError('消息编号已用于不同内容')
            db.execute('INSERT OR IGNORE INTO message_outbox VALUES (?,?,?,NULL)', (patient, operation_id, text))
        return self.sync_messages()

    def sync_messages(self):
        patient = self.me()['patient_id']
        with self.db() as db:
            rows = db.execute('SELECT operation_id,text FROM message_outbox WHERE patient_id=? AND resource_id IS NULL ORDER BY rowid', (patient,)).fetchall()
        for operation_id, text in rows:
            receipt = self.call('/patients/' + patient + '/messages', 'POST', {'operation_id': operation_id, 'text': text})
            if receipt.get('status') != 'COMMITTED':
                raise CloudError('医生消息尚未保存，已保留待发送文字')
            UUID(receipt['resource_id'])
            with self.db() as db:
                db.execute('UPDATE message_outbox SET resource_id=? WHERE patient_id=? AND operation_id=?', (receipt['resource_id'], patient, operation_id))
        return self.messages()

    def mark_read(self, cursor):
        return self.patient_call('/messages/read', 'POST', {'operation_id': str(uuid4()), 'cursor': int(cursor)})

    def plans(self, offset=0):
        if type(offset) is not int or offset < 0:
            raise CloudError('方案页码无效')
        return self.patient_call(f'/plans?offset={offset}&limit=5')

    def current(self):
        return self.patient_call('/plans/current')

    def accept(self, plan, revision, operation_id, local_validation):
        return self.patient_call('/plans/' + str(UUID(plan['id'])) + '/accept', 'POST',
            {'operation_id': str(UUID(operation_id)), 'expected_version': plan['version'], 'expected_current_revision': revision, 'local_validation': local_validation})

    def consent(self, local_id, enabled=None):
        """Upload consent is local-profile/account scoped and does not grant doctor access."""
        with self.token_lock:
            session = self.session()
            if not session:
                return False
            with self.db() as db:
                row = db.execute('SELECT patient_id FROM bindings WHERE local_id=?', (local_id,)).fetchone()
                if not row or row[0] != session['patient_id']:
                    return False
                key = 'upload-consent:' + local_id + ':' + session['patient_id']
                if enabled is not None:
                    db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (key, '1' if enabled else '0'))
                row = db.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
                return bool(row and row[0] == '1')

    def queue_fact(self, local_id, record_key, payload):
        with self.lock:
            session = self.session()
            if not session or not self.consent(local_id):
                raise CloudError('请先确认本人档案并开启康复记录同步')
            patient = session['patient_id']
            result_digest = hashlib.sha256(json.dumps(payload['result'], ensure_ascii=False, sort_keys=True, allow_nan=False).encode()).hexdigest()
            key = 'fact:' + patient + ':' + record_key
            with self.db() as db:
                db.execute('BEGIN IMMEDIATE')
                old = db.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
                old = json.loads(old[0]) if old else None
                if old and old['digest'] == result_digest:
                    return
                revision = old['revision'] + 1 if old else 1
                stable = 'record:' + hashlib.sha256(record_key.encode()).hexdigest()[:32]
                payload.update(record_key=stable, revision=revision)
                installation = db.execute("SELECT value FROM meta WHERE key='installation'").fetchone()[0]
                document = dict(operation_id=str(uuid4()), source_event_id=stable + ':r' + str(revision), installation_id=installation, source_kind='DESKTOP_LOCAL', payload=payload)
                encoded = json.dumps(document, ensure_ascii=False, allow_nan=False)
                if len(encoded.encode()) > 32768:
                    raise CloudError('单项康复结果过大，本机原件保留')
                db.execute('INSERT INTO outbox VALUES (?,?,?,?,NULL)', (patient, local_id, document['source_event_id'], encoded))
                db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (key, json.dumps({'revision': revision, 'digest': result_digest})))

    def queue_product(self, local_id, snapshot):
        patient = self.session()['patient_id']
        for key, payload in desktop_product_records(snapshot, local_id, patient):
            self.queue_fact(local_id, key, payload)

    def queue_rehab(self, local_id, store):
        from .assessment import session_value, session_conditions
        from .domain import utc_now
        patient = self.session()['patient_id']
        for session in store.list_sessions():
            if session_value(session, 'participant_id') != local_id or session.get('scene_id') != 'rehab':
                continue
            try:
                value = desktop_record(session, local_id)
            except CloudError:
                continue
            kind = session_value(session, 'submode')
            if kind not in ('assessment', 'training'):
                continue
            value['result']['conditions'] = {k: v for k, v in session_conditions(session).items() if k not in ('source_ref', 'profile_id')}
            value['result']['saved_plan_reference'] = session_value(session, 'saved_plan_reference')
            value['result']['measurement_mode'] = session.get('measurement_mode')
            value.update(schema='ankang-workbench-record-1', kind=kind, source='DESKTOP_LOCAL', owner_id=local_id, patient_id=patient, captured_at=utc_now())
            self.queue_fact(local_id, 'session:' + session['id'], value)
        for source in ('LIVE_CAMERA', 'REPLAY_FILE'):
            scope = {'participant_id': local_id, 'source_kind': source, 'usage_context': 'SELF_USE'}
            for plan in store.list_training_plans(scope, include_archived=True):
                self.queue_fact(local_id, 'plan:' + plan['id'], {'schema': 'ankang-workbench-record-1', 'title': plan['name'], 'kind': 'rehab_plan', 'source': 'DESKTOP_LOCAL', 'owner_id': local_id, 'patient_id': patient, 'captured_at': utc_now(), 'result': plan})

    def adopt(self, plan, current_revision, local_id, scope, store):
        """Validate against the actual latest local assessments, then save a reusable local plan."""
        from .assessment import build_body_profile, session_value
        from .training_plans import new_training_plan, prepare_training_plan, item_from_plan
        from .exercises import exercise_spec
        from .domain import utc_now
        from datetime import datetime, timezone
        if scope.get('participant_id') != local_id or scope.get('source_kind') not in ('LIVE_CAMERA', 'REPLAY_FILE') or scope.get('usage_context') != 'SELF_USE':
            raise CloudError('请选择本人真实摄像头或录像范围，展示数据不能采用医生方案')
        patient = self.bind(local_id)
        if plan.get('status') != 'PUBLISHED' or not plan.get('items'):
            raise CloudError('只能采用医生已发布的方案')
        items = []
        for item in plan['items']:
            spec = exercise_spec(item['exercise_id'])
            if item['measurement_contract'] != spec['measurement_contract']:
                raise CloudError('医生方案测量定义与本机不一致，请联系医生重新制定')
            items.append(item_from_plan({**item['settings'], 'exercise_id': item['exercise_id'], 'side': item['side']}))
        with self.db() as db:
            old = db.execute('SELECT * FROM plan_acceptance WHERE patient_id=? AND cloud_id=? AND cloud_version=?', (patient, plan['id'], plan['version'])).fetchone()
        def references(record):
            sessions = [s for s in store.list_sessions() if all(session_value(s, k) == v for k, v in scope.items())]
            body = build_body_profile(sessions, **scope)
            result = []
            for item in items:
                prepared = prepare_training_plan({**record, 'status': 'ACTIVE'}, item['key'], body)
                reference = prepared['assessment_reference']
                timestamp = reference.get('end_utc') or next((s.get('end_utc') for s in sessions if s['id'] == reference['session_id']), None)
                if not timestamp or not 0 <= (datetime.now(timezone.utc) - datetime.fromisoformat(timestamp.replace('Z', '+00:00'))).total_seconds() <= 7 * 86400:
                    raise CloudError('该动作最新本人评估已过期，请先补测')
                result.append({'key': item['key'], 'session_id': reference['session_id'], 'measurement_contract': item['measurement_contract']})
            return result
        if not old:
            record = new_training_plan(scope, plan['title'][:80], items)
            record['doctor_publication'] = {'id': plan['id'], 'version': plan['version']}
            validation = {'local_plan_id': record['id'], 'local_revision': 1, 'scope': scope, 'validation_policy': 'existing-local-assessment-1', 'assessment_references': references(record), 'validated_at': utc_now()}
            document = {'operation_id': str(uuid4()), 'expected_version': plan['version'], 'expected_current_revision': current_revision, 'local_validation': validation}
            intent = {'body': document, 'pending_record': record}
            with self.db() as db:
                db.execute('INSERT INTO plan_acceptance VALUES (?,?,?,?,?,NULL)', (patient, plan['id'], plan['version'], record['id'], json.dumps(intent, ensure_ascii=False)))
        else:
            intent = json.loads(old['document'])
            document = intent['body']
            if intent['pending_record']['items'] != items or intent['pending_record']['participant_id'] != local_id:
                raise CloudError('待确认方案内容或归属已变化')
        record = store.get_training_plan(intent['pending_record']['id'])
        if not record:
            record = store.save_training_plan(intent['pending_record'], expected_revision=0, status='PENDING_DOCTOR')
        if record['revision'] != document['local_validation']['local_revision'] or record['items'] != items:
            raise CloudError('本地方案版本已变化，请重新核对')
        try:
            receipt = json.loads(old['receipt']) if old and old['receipt'] else self.call('/patients/' + patient + '/plans/' + plan['id'] + '/accept', 'POST', document)
        except CloudError as exc:
            if exc.status in (403, 404, 409, 412, 422):
                with self.db() as db:
                    db.execute('DELETE FROM plan_acceptance WHERE patient_id=? AND cloud_id=? AND cloud_version=?', (patient, plan['id'], plan['version']))
            raise
        if receipt.get('status') != 'COMMITTED':
            raise CloudError('方案仍待确认，云端未提交；本机不会开始该方案')
        with self.db() as db:
            db.execute('UPDATE plan_acceptance SET receipt=? WHERE patient_id=? AND cloud_id=? AND cloud_version=?', (json.dumps(receipt, ensure_ascii=False), patient, plan['id'], plan['version']))
        active = self.current()
        if not active.get('plan') or active['plan']['id'] != plan['id'] or active['current_revision'] != receipt['current_revision']:
            return {**receipt, 'local_status': 'SUPERSEDED'}
        try:
            references(record)
        except (CloudError, ValueError):
            return {**receipt, 'local_status': 'NEEDS_REVIEW'}
        store.activate_pending_training_plan(record['id'], scope, expected_revision=record['revision'])
        receipt = {**receipt, 'local_status': 'ACTIVE'}
        return receipt


def desktop_product_records(snapshot, local_id, patient_id):
    """Publish selected real facts, never chat, family data, attachments or credentials."""
    profile = snapshot.get('profile', {})
    if snapshot.get('ownerId') != local_id or profile.get('ownerId') != local_id or profile.get('dataMode') != 'personal':
        raise CloudError('请选择本人真实档案，展示档案不上传')
    from datetime import datetime, timezone
    captured = datetime.now(timezone.utc).isoformat()
    p = profile.get('profile', {})
    selected = [('profile', '康复资料', {**{k: p.get(k) for k in ('name', 'age', 'conditions', 'mobility', 'usesCane')}, 'rehabGoal': profile.get('rehabGoal', ''), 'currentState': profile.get('currentState', '')})]
    for kind, title, result in selected:
        if result is None or result == []:
            continue
        yield (kind + ':' + local_id, {'schema': 'ankang-workbench-record-1', 'title': title, 'kind': kind,
            'source': 'DESKTOP_LOCAL', 'owner_id': local_id, 'patient_id': patient_id,
            'captured_at': captured, 'result': result})


def desktop_record(snapshot, local_id):
    from .assessment import session_value
    if session_value(snapshot, 'participant_id') != local_id or snapshot.get('status') not in ('FINISHED', 'INTERRUPTED', 'COMPLETED'):
        raise CloudError('请选择本人已保存的结束记录')
    if session_value(snapshot, 'source_kind') == 'SYNTHETIC' or snapshot.get('synthetic') or session_value(snapshot, 'usage_context') != 'SELF_USE':
        raise CloudError('展示记录不自动写入个人云档案')
    keep = ('id', 'participant_id', 'scene_id', 'submode', 'exercise_id', 'side', 'source_kind', 'usage_context',
            'start_utc', 'end_utc', 'status', 'stop_reason', 'summary', 'training_feedback', 'rule_version', 'model_manifest_id')
    value = {key: snapshot[key] for key in keep if key in snapshot}
    for key in ('participant_id', 'submode', 'exercise_id', 'side', 'source_kind', 'usage_context'):
        value[key] = session_value(snapshot, key)
    from .domain import EXERCISES, SCENES
    title = EXERCISES.get(snapshot.get('exercise_id'), SCENES.get(snapshot.get('scene_id'), '康复记录'))
    return {'schema': 'ankang-result-1', 'title': title,
            'kind': snapshot.get('submode', snapshot.get('scene_id')), 'source': snapshot.get('source_kind'),
            'measured_at': snapshot.get('end_utc'), 'result': value}
