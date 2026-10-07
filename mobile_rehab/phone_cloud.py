"""Optional APK companion hub. Does not open or mutate desktop patient databases."""
import argparse
from collections import defaultdict, deque
from contextlib import contextmanager
import hashlib
import hmac
import json
from pathlib import Path
import re
import secrets
import sqlite3
import time
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse


def create_cloud(folder, join_code=None):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    codefile = folder / 'join-code.txt'
    if join_code is None:
        if not codefile.exists():
            codefile.write_text(secrets.token_hex(12), encoding='utf-8')
        join_code = codefile.read_text(encoding='utf-8').strip()
    dbfile = folder / 'phone-cloud.sqlite3'
    @contextmanager
    def db():
        with sqlite3.connect(dbfile, timeout=15) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute('PRAGMA foreign_keys=ON')
            yield connection
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS devices(id TEXT PRIMARY KEY, client TEXT UNIQUE, token_hash TEXT UNIQUE, summary TEXT);
        CREATE TABLE IF NOT EXISTS invites(code TEXT PRIMARY KEY, owner TEXT, expires REAL);
        CREATE TABLE IF NOT EXISTS links(owner TEXT, member TEXT, categories TEXT NOT NULL DEFAULT '[]', PRIMARY KEY(owner,member));
        CREATE TABLE IF NOT EXISTS backups(owner TEXT PRIMARY KEY, revision INTEGER, document TEXT, digest TEXT, saved REAL);
        ''')
    app = FastAPI(title='安康 · 手机云端辅助', docs_url=None, redoc_url=None, openapi_url=None)
    app.state.join_code = join_code
    attempts = defaultdict(deque)
    def limit(key):
        now = time.monotonic()
        q = attempts[key]
        while q and now-q[0]>60: q.popleft()
        if len(q)>=20: raise HTTPException(429, '尝试过多，请稍后再试')
        q.append(now)
        # Bound unauthenticated address accounting, no unbounded flood storage.
        if len(attempts)>1000:
            for k in list(attempts)[:500]: attempts.pop(k, None)
    async def payload(request, maximum=32768):
        raw=bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw)>maximum: raise HTTPException(413, '请求过大')
        try:
            value=json.loads(raw)
            if not isinstance(value,dict): raise ValueError()
            return value
        except (ValueError,UnicodeError): raise HTTPException(400, '请求格式错误')
    def owner(request):
        auth=request.headers.get('Authorization','')
        if not re.fullmatch('Bearer [A-Za-z0-9_-]{40,100}',auth): raise HTTPException(401, '请重新连接云端')
        with db() as c:
            row=c.execute('SELECT id FROM devices WHERE token_hash=?',(hashlib.sha256(auth[7:].encode()).hexdigest(),)).fetchone()
        if not row: raise HTTPException(401, '连接已失效')
        return row['id']
    @app.middleware('http')
    async def headers(request, next_call):
        response=await next_call(request)
        response.headers.update({'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer'})
        return response
    @app.get('/v1/health')
    def health(): return {'ok':True,'version':'phone-cloud-1','capabilities':['private-backup','family-categories','no-desktop-required']}
    @app.post('/v1/enroll')
    async def enroll(request: Request):
        limit('enroll:'+request.client.host)
        p=await payload(request,1024)
        if not isinstance(p.get('code'),str) or not hmac.compare_digest(p['code'].encode(),join_code.encode()): raise HTTPException(401, '云端连接码不正确')
        if not re.fullmatch('[a-f0-9-]{36}',str(p.get('client_id',''))): raise HTTPException(400, '设备编号无效')
        ident=str(uuid4());token=secrets.token_urlsafe(32)
        with db() as c:
            # Joining never selects or overwrites somebody else's identity.
            if c.execute('SELECT id FROM devices WHERE client=?',(p['client_id'],)).fetchone(): raise HTTPException(409, '设备已注册，请保留已有连接；重新连接请使用新设备编号')
            c.execute('INSERT INTO devices VALUES(?,?,?,?)',(ident,p['client_id'],hashlib.sha256(token.encode()).hexdigest(),'{}'))
        return {'owner':ident,'token':token}
    @app.put('/v1/summary')
    async def summary(request: Request):
        uid=owner(request);p=await payload(request)
        if set(p)!={'name','health','rehab','doses'} or not isinstance(p['name'],str) or len(p['name'])>40: raise HTTPException(400,'摘要字段无效')
        for kind in ['health','rehab']:
            if not isinstance(p[kind],list) or len(p[kind])>30 or any(not isinstance(r,dict) or set(r)!={'text','timestamp'} or not isinstance(r['text'],str) or len(r['text'])>300 or not isinstance(r['timestamp'],str) or len(r['timestamp'])>40 for r in p[kind]): raise HTTPException(400,'摘要记录无效')
        if not isinstance(p['doses'],list) or len(p['doses'])>30 or any(not isinstance(d,dict) or set(d)!={'medName','date','time','status'} or any(not isinstance(v,str) or len(v)>100 for v in d.values()) or d['status'] not in ['taken','skipped','unrecorded'] for d in p['doses']): raise HTTPException(400,'用药摘要无效')
        with db() as c: c.execute('UPDATE devices SET summary=? WHERE id=?',(json.dumps(p,ensure_ascii=False),uid))
        return {'ok':True}
    @app.get('/v1/family')
    def family(request: Request):
        uid=owner(request);members=[];grants={}
        with db() as c:
            for link in c.execute('SELECT * FROM links WHERE owner=?',(uid,)).fetchall():
                member=link['member'];grants[member]=json.loads(link['categories'])
                incoming=c.execute('SELECT categories FROM links WHERE owner=? AND member=?',(member,uid)).fetchone()
                cats=json.loads(incoming[0]) if incoming else []
                s=json.loads(c.execute('SELECT summary FROM devices WHERE id=?',(member,)).fetchone()[0])
                members.append({'ownerId':member,'name':s.get('name','家人'),'categories':cats,'health':s.get('health',[]) if 'health' in cats else [],'rehab':s.get('rehab',[]) if 'rehab' in cats else [],'doses':s.get('doses',[]) if 'medication' in cats else []})
        return {'familyMembers':members,'grants':grants,'fetchedAt':time.time()}
    @app.post('/v1/family/{operation}')
    async def change_family(operation: str, request: Request):
        uid=owner(request);limit('family:'+uid);p=await payload(request,1024)
        with db() as c:
            if operation=='invite':
                code=secrets.token_hex(4).upper();c.execute('DELETE FROM invites WHERE expires<? OR owner=?',(time.time(),uid));c.execute('INSERT INTO invites VALUES(?,?,?)',(code,uid,time.time()+900));return {'code':code}
            if operation=='bind':
                record=c.execute('SELECT * FROM invites WHERE code=? AND expires>?',(str(p.get('code','')).upper(),time.time())).fetchone()
                if not record or record['owner']==uid: raise HTTPException(400,'邀请码无效或已过期')
                member=record['owner'];c.execute('INSERT OR IGNORE INTO links VALUES(?,?,?)',(uid,member,'[]'));c.execute('INSERT OR IGNORE INTO links VALUES(?,?,?)',(member,uid,'[]'));c.execute('DELETE FROM invites WHERE code=?',(record['code'],))
            elif operation in ['grant','unbind']:
                member=p.get('member')
                if not c.execute('SELECT 1 FROM links WHERE owner=? AND member=?',(uid,member)).fetchone(): raise HTTPException(404,'家庭关系不存在')
                if operation=='grant':
                    cats=p.get('categories');
                    if not isinstance(cats,list) or len(cats)>3 or any(x not in ['health','rehab','medication'] for x in cats): raise HTTPException(400,'共享范围无效')
                    c.execute('UPDATE links SET categories=? WHERE owner=? AND member=?',(json.dumps(sorted(set(cats))),uid,member))
                else: c.execute('DELETE FROM links WHERE (owner=? AND member=?) OR (owner=? AND member=?)',(uid,member,member,uid))
            else: raise HTTPException(404,'未知操作')
        return {'dailyReceipt':True}
    @app.get('/v1/backup')
    def backup_get(request: Request):
        uid=owner(request)
        with db() as c: row=c.execute('SELECT * FROM backups WHERE owner=?',(uid,)).fetchone()
        if not row: raise HTTPException(404,'没有本人的云端备份')
        return {'revision':row['revision'],'savedAt':row['saved'],'document':json.loads(row['document']),'digest':row['digest']}
    @app.put('/v1/backup')
    async def backup_put(request: Request):
        uid=owner(request);p=await payload(request,12*1048576)
        if p.get('consent') is not True or not isinstance(p.get('revision'),int) or isinstance(p['revision'],bool) or not isinstance(p.get('document'),dict) or p['document'].get('kind')!='ankang-phone-backup' or p['document'].get('version')!=2: raise HTTPException(400,'请确认本人备份')
        document=json.dumps(p['document'],ensure_ascii=False,sort_keys=True,separators=(',',':'));digest=hashlib.sha256(document.encode()).hexdigest()
        with db() as c:
            row=c.execute('SELECT * FROM backups WHERE owner=?',(uid,)).fetchone();revision=row['revision'] if row else 0
            if row and row['digest']==digest: return {'revision':revision,'digest':digest,'idempotent':True}
            if p['revision']!=revision: raise HTTPException(409,'云端备份已变化，请先读取最新备份')
            c.execute('INSERT OR REPLACE INTO backups VALUES(?,?,?,?,?)',(uid,revision+1,document,digest,time.time()))
        return {'revision':revision+1,'digest':digest}
    @app.delete('/v1/device')
    def revoke_device(request: Request):
        uid=owner(request)
        with db() as c:
            c.execute('DELETE FROM links WHERE owner=? OR member=?',(uid,uid));c.execute('DELETE FROM invites WHERE owner=?',(uid,));c.execute('DELETE FROM backups WHERE owner=?',(uid,));c.execute('DELETE FROM devices WHERE id=?',(uid,))
        return {'ok':True}
    return app


def main():
    parser=argparse.ArgumentParser(description='Optional cloud companion for standalone APK')
    parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',type=int,default=8770);parser.add_argument('--data-dir',type=Path,default=Path('.runtime/phone-cloud'))
    args=parser.parse_args();app=create_cloud(args.data_dir)
    print(f'手机云端辅助：http://{args.host}:{args.port}\n连接码：{app.state.join_code}\n异地部署请使用 HTTPS 反向代理；不直接开放患者库。',flush=True)
    import uvicorn
    uvicorn.run(app,host=args.host,port=args.port,access_log=False)

if __name__=='__main__': main()
