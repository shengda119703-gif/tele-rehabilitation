from __future__ import annotations

import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from uuid import uuid4

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from .core import ROOT, EXERCISE_IDS, catalog
from .fitness import EXERCISES as FITNESS_EXERCISES, catalog as fitness_catalog
from app.storage import Storage
from app.assessment import build_body_profile
from app.automatic_plans import generate_proposal, create_automatic_plan, program_progress, validate_automatic_use

MAX_BYTES = 256 * 1024 * 1024
MAX_STORED = 2 * 1024 * 1024 * 1024
ACTIVE = {'uploading', 'queued', 'analyzing'}


def now():
    return datetime.now(timezone.utc).isoformat()


def save(path, data):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    temp.replace(path)


class Jobs:
    def __init__(self, root, runner=None):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='mobile-analysis')
        self.runner = runner or self.run
        self.closed = False
        self.process = None
        self.items = {}
        for path in self.root.glob('*/*/job.json'):
            item = json.loads(path.read_text(encoding='utf-8'))
            if item['state'] in ACTIVE:
                item.update(state='failed', message='电脑服务重启，任务未完成。请重新上传。')
                save(path, item)
                (path.parent / 'upload.part').unlink(missing_ok=True)
            self.items[item['id']] = item

    def folder(self, job):
        return self.root / job['owner'] / job['id']

    def update(self, jid, **values):
        with self.lock:
            item = self.items[jid]
            item.update(values)
            save(self.folder(item) / 'job.json', item)

    def reserve(self, owner, exercise, side):
        with self.lock:
            if any(j['owner'] == owner and j['state'] in ACTIVE for j in self.items.values()):
                raise HTTPException(409, '你已有一段录像正在处理，请先到“我的记录”查看。')
            if self.closed or sum(j['state'] in ACTIVE for j in self.items.values()) >= 3:
                raise HTTPException(429, '电脑正在处理其他录像，请稍后再试。')
            used = sum(p.stat().st_size for p in self.root.glob('*/*/video.mp4'))
            reserved = sum(MAX_BYTES for j in self.items.values() if j['state'] == 'uploading')
            if used + reserved + MAX_BYTES > MAX_STORED or shutil.disk_usage(self.root).free < MAX_BYTES * 2 + reserved:
                raise HTTPException(507, '录像存储空间不足，请在记录页删除不需要的录像。')
            item = dict(id=uuid4().hex, owner=owner, exercise=exercise, side=side,
                        state='uploading', created_at=now(), consent_at=now(), message='正在接收录像')
            self.folder(item).mkdir(parents=True)
            self.items[item['id']] = item
            self.update(item['id'])
            return item.copy()

    def get(self, jid, owner):
        with self.lock:
            item = self.items.get(jid)
            if not item or item['owner'] != owner:
                raise HTTPException(404, '找不到这项记录')
            return item.copy()

    def public(self, item, *, brief=False):
        result = {k: v for k, v in item.items() if k != 'owner'}
        for name in ('progress', 'result'):
            if brief and name == 'result':
                continue
            path = self.folder(item) / (name + '.json')
            if path.exists() and (name != 'result' or item['state'] == 'done'):
                result[name] = json.loads(path.read_text(encoding='utf-8'))
        result['video_available'] = (self.folder(item) / 'video.mp4').exists()
        return result

    def enqueue(self, jid):
        self.update(jid, state='queued', message='已上传，等待电脑分析')
        self.pool.submit(self.execute, jid)

    def execute(self, jid):
        with self.lock:
            if self.closed:
                return
            self.update(jid, state='analyzing', message='电脑正在分析动作')
            item = self.items[jid].copy()
        try:
            self.runner(item)
            if not (self.folder(item) / 'result.json').exists():
                raise RuntimeError('分析未返回结果，请重新上传。')
            self.update(jid, state='done', message='分析完成')
        except Exception as exc:
            self.update(jid, state='failed', message=str(exc), finished_at=now())

    @staticmethod
    def stop_process(proc):
        if proc.poll() is not None:
            return
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True,
                           creationflags=subprocess.CREATE_NO_WINDOW, timeout=10)
        else:
            os.killpg(proc.pid, signal.SIGKILL)
        proc.wait(timeout=10)

    def run(self, item):
        folder = self.folder(item)
        with (folder / 'analysis.log').open('wb') as log:
            with self.lock:
                if self.closed:
                    raise RuntimeError('服务已停止，请重新上传。')
                self.process = subprocess.Popen([sys.executable, '-m', 'mobile_rehab.analyzer', str(folder / 'job.json')],
                    cwd=ROOT, stdout=log, stderr=log,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                    start_new_session=os.name != 'nt')
                proc = self.process
            try:
                code = proc.wait(timeout=600)
            except subprocess.TimeoutExpired:
                self.stop_process(proc)
                raise RuntimeError('分析超过 10 分钟。请使用 720p、30 秒左右的视频重试。')
            finally:
                with self.lock:
                    self.process = None
        if code:
            error = folder / 'error.json'
            message = json.loads(error.read_text(encoding='utf-8'))['message'] if error.exists() else '分析进程中断，请重新上传。'
            raise RuntimeError(message)

    def close(self):
        with self.lock:
            self.closed = True
            proc = self.process
        if proc:
            self.stop_process(proc)
        self.pool.shutdown(wait=True, cancel_futures=True)


def create_app(data_dir=None, pair_key=None, runner=None):
    data_dir = Path(data_dir or ROOT / '.runtime/mobile')
    data_dir.mkdir(parents=True, exist_ok=True)
    key_file = data_dir / 'pair-key.txt'
    if pair_key is None:
        if not key_file.exists():
            key_file.write_text(secrets.token_hex(8), encoding='utf-8')
        pair_key = key_file.read_text(encoding='utf-8').strip()
    jobs = Jobs(data_dir / 'jobs', runner)
    failures = []

    @asynccontextmanager
    async def lifespan(app):
        async def watch_stop_request():
            marker = data_dir / 'stop-request'
            while True:
                if marker.exists() and hasattr(app.state, 'shutdown'):
                    app.state.shutdown()
                    return
                await asyncio.sleep(.5)
        watcher = asyncio.create_task(watch_stop_request())
        try:
            yield
        finally:
            watcher.cancel()
            await asyncio.to_thread(jobs.close)

    app = FastAPI(title='康复随行 · 手机演示', docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.jobs = jobs
    app.state.pair_key = pair_key

    @contextmanager
    def store_for(uid):
        store = Storage(jobs.root / uid / 'assessments.sqlite3')
        try:
            yield store
        finally:
            store.close()

    def evidence(store, uid):
        sessions = store.list_sessions()
        profile = build_body_profile(sessions, uid, 'REPLAY_FILE', 'SELF_USE')
        return sessions, profile

    async def small_json(request):
        raw = b''
        async for chunk in request.stream():
            raw += chunk
            if len(raw) > 4096:
                raise HTTPException(413, '请求内容过长')
        try:
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError()
            return value
        except ValueError:
            raise HTTPException(400, '请求格式不正确')

    @app.exception_handler(ValueError)
    async def value_error(request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=400)

    def sign(uid):
        return uid + '.' + hmac.new(pair_key.encode(), uid.encode(), hashlib.sha256).hexdigest()

    def owner(request):
        cookie = request.cookies.get('rehab_device', '')
        uid = cookie.split('.')[0]
        if not re.fullmatch('[a-f0-9]{32}', uid) or not hmac.compare_digest(sign(uid), cookie):
            raise HTTPException(401, '请先输入电脑上显示的连接码')
        return uid

    @app.middleware('http')
    async def protect(request, call_next):
        if request.method not in ('GET', 'HEAD') and request.headers.get('x-rehab-client') != 'mobile-v1':
            return JSONResponse({'detail': '请从本机康复网页操作'}, status_code=403)
        response = await call_next(request)
        response.headers.update({'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer',
                                 'Cache-Control': 'no-store', 'X-Frame-Options': 'DENY',
                                 'Content-Security-Policy': "default-src 'self'; img-src 'self' data:; media-src 'self' blob:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'"})
        return response

    @app.get('/api/health')
    def health():
        return dict(ok=True, service='mobile-rehab', version='1')

    @app.post('/api/pair')
    async def pair(request: Request):
        if int(request.headers.get('content-length', '0')) > 512:
            raise HTTPException(413, '连接码过长')
        raw = b''
        async for chunk in request.stream():
            raw += chunk
            if len(raw) > 512:
                raise HTTPException(413, '连接码过长')
        failures[:] = [t for t in failures if time.monotonic() - t < 60]
        if len(failures) >= 20:
            raise HTTPException(429, '尝试过多，请一分钟后重试')
        try:
            code = json.loads(raw).get('code', '')
        except (ValueError, AttributeError):
            raise HTTPException(400, '请输入连接码')
        if not isinstance(code, str) or not hmac.compare_digest(code.encode(), pair_key.encode()):
            failures.append(time.monotonic())
            raise HTTPException(401, '连接码不正确，请查看电脑启动窗口')
        try:
            uid = owner(request)
        except HTTPException:
            uid = uuid4().hex
        response = JSONResponse(dict(ok=True))
        response.set_cookie('rehab_device', sign(uid), max_age=30 * 86400,
                            httponly=True, samesite='strict', secure=request.url.scheme == 'https')
        return response

    @app.get('/api/catalog')
    def get_catalog(request: Request):
        owner(request)
        return dict(exercises=catalog(), max_bytes=MAX_BYTES, max_seconds=120,
                    fitness=fitness_catalog(),
                    network_camera=dict(connected=False, message='等待确认摄像头型号及 RTSP / ONVIF 协议；目前可上传它导出的录像。'))

    @app.get('/api/plan')
    def current_plan(request: Request):
        uid = owner(request)
        with store_for(uid) as store:
            sessions, profile = evidence(store, uid)
            proposal = generate_proposal(profile, sessions)
            plans = store.list_training_plans(profile)
            record = plans[0] if plans else None
            progress = program_progress(record, sessions) if record else None
            if record and progress['next_key'] and not progress['blocked']:
                try:
                    validate_automatic_use(record, progress['next_key'], profile, sessions, None)
                except ValueError as exc:
                    progress['blocked'] = str(exc)
            return dict(proposal=proposal, plan=record, progress=progress)

    @app.post('/api/plan')
    async def make_plan(request: Request):
        uid = owner(request)
        screening = await small_json(request)
        def create():
            with store_for(uid) as store:
                sessions, profile = evidence(store, uid)
                record = create_automatic_plan(generate_proposal(profile, sessions), screening)
                return store.save_training_plan(record, expected_revision=0)
        return await asyncio.to_thread(create)

    @app.post('/api/jobs/{jid}/feedback')
    async def feedback(jid: str, request: Request):
        uid = owner(request)
        item = jobs.get(jid, uid)
        if item.get('mode') != 'training' or item['state'] != 'done':
            raise HTTPException(409, '请先完成本次训练录像分析')
        data = await small_json(request)
        result = jobs.public(item)['result']
        def record_feedback():
            with store_for(uid) as store:
                session = store.save_training_feedback(result['session_id'], data,
                                                       expected_revision=data.get('revision', 0))
                jobs.update(jid, feedback=session['training_feedback'])
                return session['training_feedback']
        return await asyncio.to_thread(record_feedback)

    @app.get('/api/jobs')
    def list_jobs(request: Request, brief: bool = False):
        uid = owner(request)
        with jobs.lock:
            items = [j.copy() for j in jobs.items.values() if j['owner'] == uid]
        return [jobs.public(j, brief=brief) for j in sorted(items, key=lambda j: j['created_at'], reverse=True)]

    @app.get('/api/jobs/{jid}')
    def get_job(jid: str, request: Request):
        return jobs.public(jobs.get(jid, owner(request)))

    @app.post('/api/jobs')
    async def upload(request: Request, exercise: str, side: str, consent: str = '',
                     mode: str = 'assessment', plan_id: str = '', entry_key: str = ''):
        uid = owner(request)
        allowed = FITNESS_EXERCISES if mode == 'fitness' else EXERCISE_IDS
        if exercise not in allowed or side not in ('left', 'right') or consent != 'yes':
            raise HTTPException(400, '请选择动作、测试侧，并同意本次录像传到你的电脑分析。')
        if mode not in ('assessment', 'training', 'fitness'):
            raise HTTPException(400, '未知的任务模式')
        if mode == 'training':
            def validate():
                with store_for(uid) as store:
                    sessions, profile = evidence(store, uid)
                    record = store.get_training_plan(plan_id)
                    if not record:
                        raise ValueError('请先在训练中心生成今天的计划')
                    validate_automatic_use(record, entry_key, profile, sessions, None)
                    entry = next(i for i in record['items'] if i['key'] == entry_key)
                    if (entry['exercise_id'], entry['side']) != (exercise, side):
                        raise ValueError('动作与训练计划不一致，请重新选择')
            await asyncio.to_thread(validate)
        length = request.headers.get('content-length', '')
        if not length.isdigit() or int(length) > MAX_BYTES:
            raise HTTPException(413, '单个视频不能超过 256 MB')
        if request.headers.get('content-type', '').split(';')[0] not in (
                'video/mp4', 'video/quicktime', 'video/webm', 'video/x-matroska', 'application/octet-stream'):
            raise HTTPException(415, '请选择手机录像文件（MP4 / MOV / WebM）')
        item = jobs.reserve(uid, exercise, side)
        jobs.update(item['id'], mode=mode, plan_id=plan_id if mode == 'training' else '',
                    entry_key=entry_key if mode == 'training' else '')
        folder = jobs.folder(item)
        part = folder / 'upload.part'
        size = 0
        try:
            with part.open('wb') as stream:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise HTTPException(413, '视频超过 256 MB，请缩短视频后重试')
                    await asyncio.to_thread(stream.write, chunk)
            if size < 32:
                raise HTTPException(400, '视频为空或文件不完整')
            part.replace(folder / 'video.mp4')
            jobs.update(item['id'], size_bytes=size, media_type=request.headers.get('content-type', 'video/mp4'))
            jobs.enqueue(item['id'])
            return dict(id=item['id'])
        except BaseException:
            part.unlink(missing_ok=True)
            jobs.update(item['id'], state='failed', message='上传未完成，请重新选择录像。')
            raise

    @app.get('/api/jobs/{jid}/video')
    def video(jid: str, request: Request):
        item = jobs.get(jid, owner(request))
        path = jobs.folder(item) / 'video.mp4'
        if not path.exists():
            raise HTTPException(404, '原始录像已删除')
        return FileResponse(path, media_type=item.get('media_type', 'video/mp4'))

    @app.delete('/api/jobs/{jid}/video')
    def delete_video(jid: str, request: Request):
        item = jobs.get(jid, owner(request))
        if item['state'] in ACTIVE:
            raise HTTPException(409, '分析中暂不能删除，请完成后重试')
        (jobs.folder(item) / 'video.mp4').unlink(missing_ok=True)
        jobs.update(jid, video_deleted_at=now())
        return dict(ok=True)

    static = Path(__file__).parent / 'static'
    app.mount('/static', StaticFiles(directory=static), name='static')

    @app.get('/')
    def index():
        return FileResponse(static / 'index.html')

    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--stop', action='store_true', help='Stop this workspace mobile service')
    args = parser.parse_args()
    data_dir = ROOT / '.runtime/mobile'
    if args.stop:
        if data_dir.exists():
            (data_dir / 'stop-request').touch()
        print('已请求停止本项目手机网页服务。评估结果会保留，未完成的分析需要重试。', flush=True)
        return
    # Reserve the socket BEFORE loading the job index: a second launcher must
    # never mark the running server's in-flight jobs as failed.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if os.name == 'nt':
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    try:
        sock.bind((args.host, args.port))
    except OSError:
        sock.close()
        print(f'端口 {args.port} 已被使用。如果手机网页已经运行，无需重复启动。', flush=True)
        key_file = data_dir / 'pair-key.txt'
        if key_file.exists():
            print('本项目连接码：' + key_file.read_text(encoding='utf-8').strip(), flush=True)
        return
    (data_dir / 'stop-request').unlink(missing_ok=True)
    app = create_app()
    print('\n康复随行 · 手机网页演示\n仅限可信家庭局域网，不要将此端口直接开放到互联网。', flush=True)
    ips = sorted(set(socket.gethostbyname_ex(socket.gethostname())[2]))
    for ip in ips:
        if not ip.startswith('127.'):
            print(f'手机和电脑连接同一 Wi-Fi，然后打开：http://{ip}:{args.port}', flush=True)
    print(f'连接码：{app.state.pair_key}\n保持此窗口开启；按 Ctrl+C 停止。\n', flush=True)
    import uvicorn
    server = uvicorn.Server(uvicorn.Config(app, host=args.host, port=args.port, access_log=False,
                                         timeout_graceful_shutdown=5))
    app.state.shutdown = lambda: setattr(server, 'should_exit', True)
    try:
        server.run(sockets=[sock])
    finally:
        sock.close()


if __name__ == '__main__':
    main()
