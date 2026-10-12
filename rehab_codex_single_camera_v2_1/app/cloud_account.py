"""Independent native cloud adapter. Never changes Runtime's measurement facts."""
from __future__ import annotations

import ctypes
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


class CloudError(Exception):
    def __init__(self, message, status=0, code=''):
        super().__init__(message)
        self.status, self.code = status, code


class TokenVault:
    """DPAPI current-user encryption on Windows; memory-only elsewhere."""
    def __init__(self, path):
        self.path = Path(path)
        self.memory = None

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
        if os.name != 'nt':
            self.memory = value
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + '.tmp')
        temporary.write_bytes(self._crypt(json.dumps(value).encode(), True))
        os.replace(temporary, self.path)

    def clear(self):
        self.memory = None
        self.path.unlink(missing_ok=True)


def transport(path, method='GET', body=None, token=None):
    # No arbitrary URL/redirect: bearer credentials only go to this exact host.
    if not re.fullmatch(r'/auth/(register|password/login|refresh|me|logout)|/patients/[a-f0-9-]{36}(?:/(?:record-events|records(?:\?offset=\d+&limit=\d+)?|doctor-access))?', path):
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
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / 'cloud-outbox-v1.sqlite3'
        self.request = request
        self.vault = vault or TokenVault(self.directory / 'cloud-session.dpapi')
        self.lock = threading.RLock()
        self.client_kind = client_kind
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1):
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
        return self.vault.read()

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
                self.vault.write(value)
            except Exception:
                self.request('/auth/logout', 'POST', {}, value['access_token'])
                raise
            return {k: value[k] for k in ('account_id', 'patient_id', 'username', 'role')}

    def call(self, path, method='GET', body=None):
        with self.lock:
            session = self.session()
            if not session:
                raise CloudError('请先登录云账号', 401)
            try:
                return self.request(path, method, body, session['access_token'])
            except CloudError as exc:
                if exc.status != 401 or exc.code not in ('AUTH_REQUIRED', ''):
                    raise
            try:
                rotated = self.request('/auth/refresh', 'POST', {'refresh_token': session['refresh_token']})
            except CloudError as exc:
                if exc.status == 401:
                    self.vault.clear()
                raise
            session.update(rotated)
            self.vault.write(session)
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
                self.vault.clear()

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
        return self.call(f'/patients/{patient}/records?offset={offset}&limit=10')['items']

    def grant(self, enabled):
        with self.lock:
            patient = self.me()['patient_id']
            current = self.call('/patients/' + patient)
            return self.call('/patients/' + patient + '/doctor-access', 'PUT',
                             {'enabled': enabled, 'expected_version': current['grant_version']})


def desktop_record(snapshot, local_id):
    if snapshot.get('participant_id') != local_id or snapshot.get('status') not in ('FINISHED', 'INTERRUPTED'):
        raise CloudError('请选择本人已保存的结束记录')
    if snapshot.get('source_kind') == 'SYNTHETIC' or snapshot.get('synthetic') or snapshot.get('usage_context') in ('DEMO','CONTROLLED_DEMO','TEST'):
        raise CloudError('展示记录不自动写入个人云档案')
    keep = ('id', 'participant_id', 'scene_id', 'submode', 'exercise_id', 'side', 'source_kind', 'usage_context',
            'start_utc', 'end_utc', 'status', 'stop_reason', 'summary', 'training_feedback', 'rule_version', 'model_manifest_id')
    value = {key: snapshot[key] for key in keep if key in snapshot}
    from .domain import EXERCISES, SCENES
    title = EXERCISES.get(snapshot.get('exercise_id'), SCENES.get(snapshot.get('scene_id'), '康复记录'))
    return {'schema': 'ankang-result-1', 'title': title,
            'kind': snapshot.get('submode', snapshot.get('scene_id')), 'source': snapshot.get('source_kind'),
            'measured_at': snapshot.get('end_utc'), 'result': value}
