"""Local cross-device handoff and revocable, read-only report sharing.

Linking changes the browser identity; it never merges two people's records.
Tokens are random capabilities, stored only as hashes, never put in URLs by API.
"""
import hashlib
import json
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from uuid import uuid4

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse


class CareStore:
    def __init__(self, path):
        self.path = path
        self.lock = threading.RLock()
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS capabilities (
                    id TEXT PRIMARY KEY, digest TEXT UNIQUE, owner TEXT, kind TEXT,
                    expires REAL, revoked INTEGER DEFAULT 0, payload TEXT);
                CREATE TABLE IF NOT EXISTS notes (
                    id TEXT PRIMARY KEY, share_id TEXT, created REAL, author TEXT, text TEXT);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def digest(token):
        if not isinstance(token, str) or len(token) > 100:
            raise HTTPException(400, '连接码格式不正确')
        return hashlib.sha256(token.encode()).hexdigest()

    def issue(self, uid, kind, ttl, payload=None):
        token, ident, expires = secrets.token_urlsafe(24), uuid4().hex, time.time()+ttl
        with self.lock, self.connect() as db:
            # Only one outstanding link code per profile. Shares are separately revocable.
            if kind == 'link':
                db.execute('UPDATE capabilities SET revoked=1 WHERE owner=? AND kind=?', (uid, kind))
            db.execute('INSERT INTO capabilities VALUES (?,?,?,?,?,0,?)',
                       (ident, self.digest(token), uid, kind, expires, json.dumps(payload, ensure_ascii=False)))
        return dict(id=ident, code=token, expires=expires)

    def resolve(self, token, kind, consume=False):
        with self.lock, self.connect() as db:
            row = db.execute('SELECT id,owner,expires,revoked,payload FROM capabilities WHERE digest=? AND kind=?',
                             (self.digest(token), kind)).fetchone()
            if not row or row[3] or row[2] <= time.time():
                raise HTTPException(404, '连接码已失效，请重新生成')
            if consume:
                db.execute('UPDATE capabilities SET revoked=1 WHERE id=?', (row[0],))
            return dict(id=row[0], owner=row[1], payload=json.loads(row[4]))

    def notes(self, ident):
        with self.connect() as db:
            return [dict(id=r[0], created=r[1], author=r[2], text=r[3]) for r in db.execute(
                'SELECT id,created,author,text FROM notes WHERE share_id=? ORDER BY created', (ident,))]


def body_summary(jobs, uid):
    from .core import catalog
    from .posture import catalog as postures
    from .fitness import catalog as fitness
    labels = {x['id']:x['label'] for x in catalog()+postures()+fitness()}
    with jobs.lock:
        items = sorted((j.copy() for j in jobs.items.values() if j['owner'] == uid and j['state'] == 'done'),
                       key=lambda j: j['created_at'], reverse=True)
    latest, records, training = {}, [], []
    for item in items:
        public = jobs.public(item)
        result = public.get('result', {})
        mode = item.get('mode', 'assessment')
        row = dict(id=item['id'], exercise=item['exercise'], side=item['side'], mode=mode,
                   label=labels.get(item['exercise'],item['exercise']),
                   created_at=item['created_at'], summary=result.get('summary', {}),
                   quality=result.get('quality'), feedback=item.get('feedback'),
                   conditions=result.get('conditions'), rule_version=result.get('rule_version'),
                   source_kind=result.get('source_kind', 'REPLAY_FILE'))
        records.append(row)
        if mode == 'training':
            training.append(row)
        if mode in ('assessment', 'posture'):
            latest.setdefault((mode,item['exercise'],item['side']), row)
    recent = training[0] if training else None
    feedback = (recent or {}).get('feedback') or {}
    if not recent:
        next_step = dict(status='assess', title='先完成评估，再开始训练')
    elif not feedback:
        next_step = dict(status='feedback', title='补充上次训练感受', job_id=recent['id'])
    elif feedback.get('pain', 0) > 0 or feedback.get('fatigue', 0) >= 5:
        next_step = dict(status='rest', title='先休息，暂不增加训练量', job_id=recent['id'])
    elif not recent['summary'].get('plan_completed'):
        next_step = dict(status='review', title='回看上次训练，按原计划继续', job_id=recent['id'])
    else:
        next_step = dict(status='continue', title='查看下一项安排，不自动增加训练量')
    return dict(latest=list(latest.values()), records=records[:100], total=len(records),
                training_count=len(training), next_step=next_step,
                note='体态、健身与康复分开保存；不同机位的角度不直接比较。')


def install_care(app, data_dir, jobs, owner, sign, small_json):
    store = CareStore(data_dir/'care.sqlite3')
    app.state.care = store

    @app.get('/api/body')
    def body(request: Request):
        return body_summary(jobs, owner(request))

    @app.post('/api/account/link-code')
    def link_code(request: Request):
        return store.issue(owner(request), 'link', 600)

    @app.post('/api/account/link')
    async def link(request: Request):
        uid = owner(request)  # First pair this browser with the host.
        data = await small_json(request)
        if data.get('confirm_switch') is not True:
            raise HTTPException(400, '请确认切换到另一设备的档案；当前记录不会合并或删除')
        with jobs.lock:
            if any(j['owner'] == uid and j['state'] in ('uploading','queued','analyzing') for j in jobs.items.values()):
                raise HTTPException(409, '请等待当前任务处理完成后再切换档案')
        record = store.resolve(data.get('code'), 'link', consume=True)
        response = JSONResponse(dict(ok=True))
        response.set_cookie('rehab_device', sign(record['owner']), max_age=30*86400, httponly=True,
                            samesite='strict', secure=request.url.scheme == 'https')
        return response

    @app.post('/api/care/shares')
    async def share(request: Request):
        uid, data = owner(request), await small_json(request)
        if data.get('consent') is not True:
            raise HTTPException(400, '请确认分享本次报告摘要；不包含原始录像')
        payload = body_summary(jobs, uid)
        if not payload['records']:
            raise HTTPException(400, '还没有可以分享的报告')
        return store.issue(uid, 'share', 7*86400, payload)

    @app.get('/api/care/shares')
    def shares(request: Request):
        uid = owner(request)
        with store.connect() as db:
            rows = db.execute('SELECT id,expires,revoked FROM capabilities WHERE owner=? AND kind=? ORDER BY expires DESC',
                              (uid, 'share')).fetchall()
        return [dict(id=r[0], expires=r[1], active=not r[2] and r[1]>time.time(), notes=store.notes(r[0])) for r in rows]

    @app.delete('/api/care/shares/{ident}')
    def revoke(ident: str, request: Request):
        uid = owner(request)
        with store.lock, store.connect() as db:
            changed = db.execute('UPDATE capabilities SET revoked=1 WHERE id=? AND owner=? AND kind=?',
                                 (ident,uid,'share')).rowcount
        if not changed:
            raise HTTPException(404, '找不到这项分享')
        return dict(ok=True)

    @app.post('/api/care/view')
    async def view(request: Request):
        data = await small_json(request)
        record = store.resolve(data.get('code'), 'share')
        return dict(report=record['payload'], notes=store.notes(record['id']), snapshot=True)

    @app.post('/api/care/note')
    async def note(request: Request):
        data = await small_json(request)
        author, text = data.get('author', ''), data.get('text', '')
        if not isinstance(author, str) or not isinstance(text, str) or not 1 <= len(author.strip()) <= 40 or not 1 <= len(text.strip()) <= 1000:
            raise HTTPException(400, '请填写称呼（40字以内）和留言（1000字以内）')
        # Resolve and save in the same lock so revocation cannot race a write.
        with store.lock:
            record = store.resolve(data.get('code'), 'share')
            with store.connect() as db:
                count = db.execute('SELECT COUNT(*) FROM notes WHERE share_id=?', (record['id'],)).fetchone()[0]
                if count >= 30:
                    raise HTTPException(429, '本次分享最多保留30条留言')
                db.execute('INSERT INTO notes VALUES (?,?,?,?,?)',
                           (uuid4().hex, record['id'], time.time(), author.strip(), text.strip()))
        return dict(ok=True)
