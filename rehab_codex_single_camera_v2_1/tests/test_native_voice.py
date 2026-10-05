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
    monkeypatch.setattr(QMessageBox,'question',lambda *a:pytest.fail('Dictation must not show a confirmation dialog'))
    w.interface_buttons['voiceInput'].click()
    wait(app,lambda:host.live_status()['phase']=='recording')
    w._completion_controls()
    assert w.pending and w.interface_buttons['voiceCancel'].isEnabled()
    assert w.interface_buttons['voiceFinish'].isEnabled() and w.interface_buttons['voiceInput'].isEnabled()
    assert w.interface_buttons['voiceInput'].text()=='结束录音'
    assert not w.interface_buttons['voiceOutput'].isEnabled()
    assert w.private_turn.isEnabled() and w.dock_private.isEnabled() and not w.user_select.isEnabled()
    assert not w._request('voice.input')
    w.interface_buttons['voiceCancel'].click();wait(app,lambda:not w.pending)
    assert not w.snapshot['state']['chat'] and '取消' in w.notice.text()
    assert w.notice.property('fluentStatus')=='info'
    w.interface_buttons['voiceInput'].click();wait(app,lambda:host.live_status()['phase']=='recording')
    w._completion_controls();w.interface_buttons['voiceInput'].click();wait(app,lambda:not w.pending)
    assert not w.snapshot['state']['chat']
    assert host.text in w.chat_input.toPlainText() and w.assistant_sections.currentWidget() is w.assistant_views['conversation']
    w.private_turn.setChecked(True);w.chat_send.click();wait(app,lambda:not w.pending)
    assert host.text in w.chat.toPlainText() and not w.snapshot['state']['events']


def test_inline_dictation_preserves_edits_and_cancelled_queued_result(desktop,monkeypatch):
    w,app=desktop;host=TestVoice(blocked=True)
    w.backend.voice=host;w.backend.bridge.voice_host=host
    w._request('extensions.status');wait(app,lambda:not w.pending)
    w.navigate('assistant');wait(app,lambda:not w.pending)
    w.chat_input.setPlainText('TEST 原草稿')
    mic=w.interface_buttons['assistantVoiceEntry']
    mic.click();wait(app,lambda:host.state['phase']=='recording')
    assert w.assistant_sections.currentWidget() is w.assistant_views['conversation']
    w.chat_input.setPlainText('TEST 识别中修改的新草稿')
    mic.click();mic.click();wait(app,lambda:not w.pending)
    assert host.calls==['voice.recognize']
    assert w.chat_input.toPlainText()=='TEST 识别中修改的新草稿\n'+host.text
    assert not w.snapshot['state']['chat'] and not w.snapshot['state']['events']
    # Result already queued before cancellation: cancellation still discards the text.
    w.dictation_active=True;w.dictation_cancelled=False
    w._voice_cancel();before=w.chat_input.toPlainText()
    w._dictation_result({'text':'TEST 迟到结果'})
    assert w.chat_input.toPlainText()==before


def test_dictation_error_and_navigation_cancel_keep_draft(desktop):
    w,app=desktop;host=TestVoice(blocked=True)
    w.backend.voice=host;w.backend.bridge.voice_host=host
    w._request('extensions.status');wait(app,lambda:not w.pending)
    w.navigate('assistant');wait(app,lambda:not w.pending)
    w.chat_input.setPlainText('TEST 保留')
    w.interface_buttons['assistantVoiceEntry'].click();wait(app,lambda:host.state['phase']=='recording')
    w.navigate('health');wait(app,lambda:not w.pending)
    assert host.cancelled.is_set() and w.chat_input.toPlainText()=='TEST 保留'
    assert not w.snapshot['state']['chat']
    w._dictation_result(error='TEST 麦克风不可用')
    assert w.chat_input.toPlainText()=='TEST 保留'


def test_asr_child_returns_utf8_independent_of_windows_console_encoding(monkeypatch):
    import base64,io,json,sys
    from types import SimpleNamespace
    from app.product.voice_transcribe import main
    text='中文语音：今天感觉还好。'
    segment=SimpleNamespace(text=text,no_speech_prob=0,avg_logprob=0)
    model=SimpleNamespace(transcribe=lambda *a,**kw:([segment],None))
    monkeypatch.setitem(sys.modules,'faster_whisper',SimpleNamespace(WhisperModel=lambda *a,**kw:model))
    request={'model':'TEST','audio':base64.b64encode(np.zeros(4000,dtype='<f4').tobytes()).decode('ascii')}
    incoming=io.TextIOWrapper(io.BytesIO(json.dumps(request).encode('utf-8')),encoding='cp936')
    outgoing=io.TextIOWrapper(io.BytesIO(),encoding='cp936')
    monkeypatch.setattr(sys,'stdin',incoming);monkeypatch.setattr(sys,'stdout',outgoing)
    main();outgoing.flush()
    assert json.loads(outgoing.buffer.getvalue().decode('utf-8'))=={'text':text}
