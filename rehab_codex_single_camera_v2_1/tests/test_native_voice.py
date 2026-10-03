"""Host/bridge cancellation and data isolation; synthetic host is NOT hardware acceptance."""
import threading
import time
import numpy as np
import pytest
from PySide6.QtWidgets import QMessageBox
from test_product_window import desktop,wait
from app.product.native_voice import NativeVoiceHost
from app.ui.product_dialogs import blank_health
from bridges.ankang.client import AgentBridge


class TestVoice(NativeVoiceHost):
    __test__=False
    def __init__(self,text='TEST 今天身体感觉还好',blocked=False):
        super().__init__();self.text=text;self.blocked=blocked;self.calls=[]
        self.state.update(available=True,phase='idle',outputAvailable=False,detail='TEST 合成语音宿主')
    def status(self):return self.live_status()
    def handle(self,name,args):
        self.calls.append(name)
        if name=='voice.cancel':return super().handle(name,args)
        self.state['phase']='recording'
        while self.blocked and not self.finished.wait(.02):pass
        try:
            self._check_cancelled();return {'text':self.text}
        finally:self.state['phase']='idle'


def test_original_product_voice_port_uses_host_then_real_chat_without_second_agent(tmp_path,monkeypatch):
    monkeypatch.setenv('ANKANG_PRODUCT_DISABLE_MODEL','1');host=TestVoice()
    with AgentBridge(data_dir=tmp_path,voice_host=host) as bridge:
        bridge.product('profile.save','test-person',{'profile':blank_health('TEST 语音用户')})
        result=bridge.product('voice.input','test-person')
        result=result.get('snapshot',result)
        assert host.calls==['voice.recognize']
        assert any(m['text']==host.text for m in result['state']['chat'])
        assert result['state']['chat'][-1]['role']=='agent'
        with pytest.raises(RuntimeError,match='朗读'):bridge.product('voice.output','test-person',{'id':result['state']['chat'][-1]['id']})


def test_capture_stop_closes_input_and_transcription_receives_only_memory(monkeypatch):
    host=NativeVoiceHost();host.state['available']=True;host.prepare();seen=[]
    class Stream:
        def __enter__(self):return self
        def __exit__(self,*args):seen.append('closed')
        def read(self,size):
            time.sleep(.005);return np.full((size,1),.05,dtype=np.float32),False
    sounddevice=pytest.importorskip('sounddevice',reason='Optional microphone dependency')
    monkeypatch.setattr(sounddevice,'InputStream',lambda **kw:Stream())
    monkeypatch.setattr(host,'transcribe',lambda audio:seen.append(audio.size) or 'TEST 明确文字')
    timer=threading.Timer(.06,host.stop);timer.start()
    result=host.handle('voice.recognize',{});timer.join()
    assert result=={'text':'TEST 明确文字'} and seen[0]=='closed' and seen[1]>=4000
    assert host.live_status()['phase']=='idle' and host.process is None


def test_early_cancel_and_silence_never_run_asr_or_send(monkeypatch):
    host=NativeVoiceHost();host.state['available']=True;host.prepare();host.cancel()
    with pytest.raises(RuntimeError,match='取消'):host.handle('voice.recognize',{})
    host.prepare();host.stop()
    class Stream:
        def __enter__(self):return self
        def __exit__(self,*args):pass
    sounddevice=pytest.importorskip('sounddevice',reason='Optional microphone dependency')
    monkeypatch.setattr(sounddevice,'InputStream',lambda **kw:Stream())
    monkeypatch.setattr(host,'transcribe',lambda _:pytest.fail('Silence reached ASR'))
    with pytest.raises(RuntimeError,match='清晰语音'):host.handle('voice.recognize',{})


def test_cancel_at_recognition_boundary_never_returns_committed_text(monkeypatch):
    sounddevice=pytest.importorskip('sounddevice',reason='Optional microphone dependency')
    host=NativeVoiceHost();host.state['available']=True;host.prepare()
    class Stream:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,size):
            host.stop();return np.full((4096,1),.05,dtype=np.float32),False
    monkeypatch.setattr(sounddevice,'InputStream',lambda **kw:Stream())
    def cancel_before_commit(audio):
        assert host.cancel();return 'TEST 不能发送'
    monkeypatch.setattr(host,'transcribe',cancel_before_commit)
    with pytest.raises(RuntimeError,match='取消'):host.handle('voice.recognize',{})
    host.prepare();monkeypatch.setattr(host,'transcribe',lambda _: 'TEST 已提交文字')
    assert host.handle('voice.recognize',{})=={'text':'TEST 已提交文字'}
    assert not host.cancel()  # No promise to withdraw a result after its atomic commit.


def test_ui_cancel_is_available_while_backend_busy_and_prevents_domain_write(desktop,monkeypatch):
    w,app=desktop;host=TestVoice(blocked=True)
    w.backend.voice=host;w.backend.bridge.voice_host=host
    w._request('extensions.status');wait(app,lambda:not w.pending)
    w.navigate('assistant');wait(app,lambda:not w.pending);w._show_assistant_section('voice')
    monkeypatch.setattr(QMessageBox,'question',lambda *a:QMessageBox.Yes)
    w.interface_buttons['voiceInput'].click()
    wait(app,lambda:host.live_status()['phase']=='recording')
    w._completion_controls()
    assert w.pending and w.interface_buttons['voiceCancel'].isEnabled()
    assert w.interface_buttons['voiceFinish'].isEnabled() and not w.interface_buttons['voiceInput'].isEnabled()
    assert not w.interface_buttons['voiceOutput'].isEnabled()
    assert not w.private_turn.isEnabled() and not w.dock_private.isEnabled() and not w.user_select.isEnabled()
    assert not w._request('voice.input')
    w.interface_buttons['voiceCancel'].click();wait(app,lambda:not w.pending)
    assert not w.snapshot['state']['chat'] and '取消' in w.notice.text()
    assert w.notice.property('fluentStatus')=='info'
    w.interface_buttons['voiceInput'].click();wait(app,lambda:host.live_status()['phase']=='recording')
    w._completion_controls();w.interface_buttons['voiceFinish'].click();wait(app,lambda:not w.pe