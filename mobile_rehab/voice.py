"""Short phone recordings, local-only ASR. No desktop mic or automatic chat send."""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

from fastapi import HTTPException, Request
from .core import ROOT


class PhoneVoice:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.model = Path(os.environ.get('REHAB_ASR_MODEL', str(ROOT/'rehab_codex_single_camera_v2_1/.runtime/voice/whisper-base')))
        self.lock = threading.Lock()

    def status(self):
        available = importlib.util.find_spec('faster_whisper') is not None and all(
            (self.model/name).is_file() for name in ('config.json','model.bin','tokenizer.json','vocabulary.txt'))
        return dict(available=available,local=True,max_bytes=8*1024*1024,max_seconds=30)

    def recognize(self, raw):
        if not self.status()['available']:
            raise HTTPException(503, '本地语音模型未安装，可使用手机键盘语音输入')
        if not self.lock.acquire(blocking=False):
            raise HTTPException(429, '另一段录音正在识别，请稍后再试')
        try:
            with tempfile.TemporaryDirectory(prefix='asr-',dir=self.root) as folder:
                path = Path(folder)/'recording.audio'
                path.write_bytes(raw)
                try:
                    result = subprocess.run([sys.executable,'-m','mobile_rehab.voice_worker',str(path),str(self.model)],
                        cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=90,
                        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                    if result.returncode:
                        raise HTTPException(400,'录音无法识别，请选择 30 秒内的清晰短录音')
                    text=json.loads(result.stdout.decode('utf-8'))['text'].strip()
                    if not text:
                        raise HTTPException(400,'没有听清，请重新录音或输入文字')
                    return dict(text=text[:1900],automatic_send=False)
                except subprocess.TimeoutExpired:
                    raise HTTPException(504,'录音识别超时，请换更短的录音') from None
                except (UnicodeError, ValueError, KeyError, TypeError):
                    raise HTTPException(502,'语音结果未能读取，请重新录音') from None
        finally:
            self.lock.release()


def install_voice(app,data_dir,owner):
    voice=PhoneVoice(data_dir/'voice-temp')
    app.state.phone_voice=voice

    @app.get('/api/product-voice')
    def status(request: Request):
        owner(request)
        return voice.status()

    @app.post('/api/product-voice')
    async def recognize(request: Request):
        owner(request)
        if not voice.status()['available']:
            raise HTTPException(503,'本地语音模型未安装，可使用手机键盘语音输入')
        raw=bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw)>8*1024*1024: raise HTTPException(413,'录音最多 8 MB')
        if not raw: raise HTTPException(400,'录音为空')
        return await asyncio.to_thread(voice.recognize, bytes(raw))
