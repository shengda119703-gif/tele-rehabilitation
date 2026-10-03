"""Optional bounded local microphone/ASR host for the original ProductService VoicePort.

No domain logic, audio persistence, network transcription or implicit model downloads.
Stop completes capture; cancellation interrupts both capture and the ASR child process.
"""
import base64
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

from ..settings import ROOT

MODEL_PATH = ROOT/'.runtime/voice/whisper-base'


class NativeVoiceHost:
    def __init__(self, model_path=None):
        self.model_path=Path(model_path or os.environ.get('ANKANG_VOICE_MODEL',MODEL_PATH))
        self.finished=threading.Event();self.cancelled=threading.Event()
        self.lock=threading.RLock();self.process=None
        self.state=dict(available=False,phase='unavailable',outputAvailable=False,detail='正在核对语音输入')

    def status(self):
        if self.state['phase'] in ('opening','recording','transcribing'):return self.live_status()
        ready=False;detail='';microphone=''
        try:
            if os.environ.get('ANKANG_VOICE_DISABLED')=='1':raise RuntimeError('当前平台未接入语音服务（隔离验收环境）')
            if not all(importlib.util.find_spec(name) for name in ('sounddevice','faster_whisper')):
                raise RuntimeError('语音输入待配置：尚未安装本地语音组件')
            if not all((self.model_path/f).is_file() for f in ('model.bin','config.json','tokenizer.json','vocabulary.txt')):
                raise RuntimeError('语音输入待配置：尚未准备中文识别模型')
            import sounddevice as sd
            device=sd.query_devices(kind='input');microphone=device['name']
            sd.check_input_settings(channels=1,samplerate=16000,dtype='float32')
            ready=True;detail='中文语音输入已就绪 · 本机识别，录音不保存；朗读尚未接入'
        except Exception as error:detail=str(error) or '找不到可用麦克风，请检查系统麦克风权限和默认设备'
        with self.lock:self.state.update(available=ready,phase='idle' if ready else 'unavailable',detail=detail,microphone=microphone)
        return self.live_status()

    def live_status(self):
        with self.lock:return dict(self.state)

    def prepare(self):
        # Runs at submit time, before a queued host call; early cancellation cannot be lost.
        self.finished.clear();self.cancelled.clear()
        with self.lock:self.state['phase']='opening'

    def stop(self):self.finished.set()

    def cancel(self):
        with self.lock:
            active=self.state['phase'] in ('opening','recording','transcribing')
            self.cancelled.set();self.finished.set()
            if self.process is not None and self.process.poll() is None:
                try:self.process.terminate()
                except OSError:pass
        return active

    def _check_cancelled(self):
        if self.cancelled.is_set():raise RuntimeError('语音已取消，本轮未发送')

    def handle(self,name,args):
        if name=='voice.cancel':self.cancel();return {'cancelled':True}
        if name!='voice.recognize':raise RuntimeError('当前语音宿主尚不支持朗读')
        import numpy as np
        import sounddevice as sd
        frames=[];samples=None
        try:
            self._check_cancelled()
            with sd.InputStream(samplerate=16000,channels=1,dtype='float32') as stream:
                with self.lock:self.state['phase']='recording'
                deadline=time.monotonic()+30
                while not self.finished.is_set() and time.monotonic()<deadline:
                    chunk,overflow=stream.read(1024)
                    if overflow:raise RuntimeError('麦克风输入中断，请重试')
                    frames.append(chunk.copy())
            self._check_cancelled()
            samples=np.concatenate(frames,axis=0).reshape(-1)[:480000] if frames else np.array([],dtype=np.float32)
            if samples.size<4000 or not np.isfinite(samples).all() or float(np.sqrt(np.mean(samples*samples)))<.001:
                raise RuntimeError('未听到清晰语音，请检查麦克风后重试')
            with self.lock:self.state['phase']='transcribing'
            result=self.transcribe(samples)
            self._check_cancelled()
            if not result.strip():raise RuntimeError('未识别到清晰语音，请重试')
            return {'text':result}
        except sd.PortAudioError as error:
            raise RuntimeError('无法打开麦克风，请检查系统麦克风权限、默认输入设备或是否被占用') from error
        finally:
            frames.clear();samples=None
            with self.lock:self.state['phase']='idle' if self.state['available'] else 'unavailable'

    def transcribe(self,samples):
        """Cancellable CPU worker. Only memory buffers cross stdin, never a recorded file."""
        message=json.dumps({'model':str(self.model_path),'audio':base64.b64encode(samples.astype('<f4').tobytes()).decode('ascii')})
        env=dict(os.environ,HF_HUB_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1')
        process=subprocess.Popen([sys.executable,'-m','app.product.voice_transcribe'],cwd=ROOT,
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        with self.lock:self.process=process
        deadline=time.monotonic()+90
        try:
            first=True
            while True:
                self._check_cancelled()
                if time.monotonic()>deadline:raise RuntimeError('语音识别超时，请缩短语音后重试')
                try:
                    output,error=process.communicate(message.encode('utf-8') if first else None,timeout=.15)
                    break
                except subprocess.TimeoutExpired:first=False
            self._check_cancelled()
            if process.returncode:raise RuntimeError('语音识别失败，请检查本地语音组件和模型')
            return json.loads(output.decode('utf-8'))['text']
        finally:
            if process.poll() is None:process.terminate()
            process.communicate(timeout=5)
            with self.lock:self.process=None

    def close(self):self.cancel()
