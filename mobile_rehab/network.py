"""Host-approved RTSP cameras. No arbitrary URL fetch API or network discovery."""
import asyncio
import ipaddress
import json
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import HTTPException, Request
from fastapi.responses import Response


def validate_url(url):
    try:
        parsed = urlsplit(url)
        address = ipaddress.ip_address(parsed.hostname or '')
        if parsed.scheme != 'rtsp' or parsed.fragment or parsed.port == 0:
            raise ValueError()
        allowed = [ipaddress.ip_network(s) for s in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')]
        if not any(address in subnet for subnet in allowed):
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError('摄像头需使用可信局域网内的 RTSP IPv4 地址')
    return url


class NetworkCameras:
    def __init__(self, config):
        self.config = Path(config)

    def entries(self):
        if not self.config.exists():
            return []
        raw = json.loads(self.config.read_text(encoding='utf-8-sig'))
        if not isinstance(raw, list) or len(raw) > 8:
            raise ValueError('网络摄像头配置格式不正确')
        result = []
        for item in raw:
            if (not isinstance(item,dict) or not isinstance(item.get('id'),str)
                    or not re.fullmatch('[a-zA-Z0-9_-]{1,40}',item['id'])
                    or not isinstance(item.get('name'),str) or not 1 <= len(item['name']) <= 60):
                raise ValueError('网络摄像头名称或编号不正确')
            result.append(dict(id=item['id'],name=item['name'],url=validate_url(item.get('url'))))
        if len({x['id'] for x in result}) != len(result):
            raise ValueError('网络摄像头编号重复')
        return result

    def get(self, ident):
        item = next((x for x in self.entries() if x['id']==ident), None)
        if not item:
            raise HTTPException(404, '电脑尚未配置这台摄像头')
        return item

    def command(self, ident):
        from imageio_ffmpeg import get_ffmpeg_exe
        return [get_ffmpeg_exe(), '-nostdin', '-hide_banner', '-loglevel', 'error',
                '-rtsp_transport','tcp','-rw_timeout','8000000','-i',self.get(ident)['url']]

    def snapshot(self, ident):
        # Explicit user test only, no hidden continuous capture.
        try:
            proc = subprocess.run(self.command(ident)+['-an','-frames:v','1','-vf','scale=640:-2',
                '-f','image2pipe','-vcodec','mjpeg','pipe:1'], capture_output=True, timeout=12,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            if proc.returncode or not proc.stdout or len(proc.stdout)>1024*1024:
                raise ValueError()
            return proc.stdout
        except (subprocess.TimeoutExpired, ValueError):
            raise HTTPException(503, '摄像头未连接，请检查电源、地址和电脑端配置')

    def record(self, jobs, item):
        folder = jobs.folder(item)
        command = self.command(item['camera_id'])+['-an','-t',str(item['record_seconds']),
            '-vf','scale=1280:-2','-r','15','-c:v','libx264','-preset','ultrafast','-crf','23','-fs','250000000',
            '-pix_fmt','yuv420p','-movflags','+faststart','-y',str(folder/'video.mp4')]
        with jobs.lock:
            if jobs.closed:
                raise ValueError('服务已停止')
            jobs.process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0,
                start_new_session=os.name!='nt')
            proc = jobs.process
        try:
            if proc.wait(timeout=item['record_seconds']+25):
                raise ValueError('摄像头录像失败，请检查网络后重试')
        except subprocess.TimeoutExpired:
            jobs.stop_process(proc)
            raise ValueError('摄像头录像超时，请检查连接')
        finally:
            with jobs.lock:
                jobs.process = None
        path = folder/'video.mp4'
        if not path.exists() or path.stat().st_size<32:
            raise ValueError('摄像头未返回有效录像')
        jobs.update(item['id'], size_bytes=path.stat().st_size, media_type='video/mp4',
                    message='录像完成，正在分析')


def install_network(app, data_dir, jobs, owner, small_json):
    cameras = NetworkCameras(data_dir/'network-cameras.json')
    jobs.cameras = cameras
    app.state.network_preview_busy = False

    @app.get('/api/cameras')
    def listing(request: Request):
        owner(request)
        return [dict(id=x['id'],name=x['name']) for x in cameras.entries()]

    @app.post('/api/cameras/{ident}/test')
    async def snapshot(ident: str, request: Request):
        owner(request)
        if app.state.network_preview_busy:
            raise HTTPException(429, '正在测试摄像头，请稍候')
        app.state.network_preview_busy = True
        try:
            return Response(await asyncio.to_thread(cameras.snapshot,ident), media_type='image/jpeg')
        finally:
            app.state.network_preview_busy = False

    @app.post('/api/cameras/{ident}/record')
    async def record(ident: str, request: Request):
        from .core import EXERCISE_IDS
        from .posture import TASKS
        from .fitness import EXERCISES
        uid, data = owner(request), await small_json(request)
        cameras.get(ident)
        mode = data.get('mode','assessment')
        allowed = {'assessment':EXERCISE_IDS,'posture':TASKS,'fitness':EXERCISES}.get(mode, ())
        seconds = data.get('seconds',15)
        if (data.get('exercise') not in allowed or data.get('side') not in ('left','right')
                or data.get('consent') is not True or type(seconds) is not int or not 5 <= seconds <= 60):
            raise HTTPException(400, '请选择动作和侧别，同意保存录像，录制时长为5–60秒')
        # A configured shared camera cannot record for two owners at once.
        with jobs.lock:
            if any(j.get('camera_id')==ident and j['state'] in ('uploading','queued','analyzing') for j in jobs.items.values()):
                raise HTTPException(409, '这台摄像头正在录制或分析，请稍后再试')
            item = jobs.reserve(uid,data['exercise'],data['side'])
            jobs.update(item['id'],mode=mode,camera_id=ident,record_seconds=seconds,
                        capture_source='NETWORK_CAMERA',capture_timebase='ffmpeg_resampled_15fps',message='等待开始录制')
            jobs.enqueue(item['id'])
        return dict(id=item['id'])
