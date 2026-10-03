"""Explicit isolated hardware QA; plays a public CC-BY-4.0 Chinese test utterance.

No user audio is saved. File ASR and actual speaker -> microphone ASR are separate.
Temporary profiles/bridge records are discarded; only public fixture observations remain.
"""
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import threading
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT.parent)]
from app.product.native_voice import NativeVoiceHost
from app.ui.product_dialogs import blank_health
from bridges.ankang.client import AgentBridge

REVISION='70bb2e84b976b7e960aa89f1c648e09c59f894dd'
BASE=f'https://huggingface.co/datasets/google/fleurs/resolve/{REVISION}/data/cmn_hans_cn/'


def main():
    import numpy as np
    import sounddevice as sd
    from faster_whisper.audio import decode_audio
    output=ROOT/'qa-output/voice-native';output.mkdir(parents=True,exist_ok=True)
    cached=output/'public-fixture.json';audio_file=output/'public-fixture.wav'
    if cached.is_file() and audio_file.is_file():
        fixture=json.loads(cached.read_text(encoding='utf-8'));filename=fixture['filename'];metadata=fixture['metadata']
        public_audio=audio_file.read_bytes()
    else:
        with urllib.request.urlopen(BASE+'test.tsv',timeout=60) as stream:metadata=stream.read(2*1024*1024).decode('utf-8')
        with urllib.request.urlopen(BASE+'audio/test.tar.gz',timeout=90) as stream,tarfile.open(fileobj=stream,mode='r|gz') as archive:
            for member in archive:
                if member.isfile() and member.name.endswith('.wav'):
                    if member.size>2*1024*1024:raise ValueError('Fixture exceeds QA bound')
                    public_audio=archive.extractfile(member).read()
                    filename=Path(member.name).name;break
            else:raise RuntimeError('No public fixture')
        audio_file.write_bytes(public_audio)
        cached.write_text(json.dumps(dict(filename=filename,metadata=metadata,source=BASE,license='CC-BY-4.0')),encoding='utf-8')
    reference=next(line for line in metadata.splitlines() if filename in line)
    samples=decode_audio(io.BytesIO(public_audio),sampling_rate=16000)
    if samples.size>480000:raise ValueError('Fixture too long')
    host=NativeVoiceHost();state=host.status()
    assert state['available'],state
    file_text=host.transcribe(samples)
    assert file_text and any('\u4e00'<=c<='\u9fff' for c in file_text),file_text
    print(json.dumps(dict(fileAsr=file_text,fixture=filename),ensure_ascii=True),flush=True)
    capture_stats={}
    recognize=host.transcribe
    def measured_recognize(audio):
        capture_stats.update(samples=int(audio.size),rms=float(np.sqrt(np.mean(audio*audio))),peak=float(np.max(np.abs(audio))))
        print(json.dumps(dict(capture=capture_stats)),flush=True)
        return recognize(audio)
    host.transcribe=measured_recognize
    # Public speaker playback, then real default microphone. Not a replaced audio stream.
    with tempfile.TemporaryDirectory(prefix='native-voice-test-') as directory:
        with AgentBridge(data_dir=Path(directory),voice_host=host,timeout=150) as bridge:
            bridge.product('profile.save','test-microphone',dict(profile=blank_health('TEST 公开中文声源'),dataMode='demo'))
            received=[];errors=[]
            host.prepare()
            def listen():
                try:received.append(bridge.product('voice.input','test-microphone'))
                except Exception as error:errors.append(str(error))
            worker=threading.Thread(target=listen);worker.start()
            deadline=time.monotonic()+10
            while host.live_status()['phase']!='recording' and time.monotonic()<deadline:time.sleep(.03)
            assert host.live_status()['phase']=='recording',(host.live_status(),errors)
            time.sleep(.5)
            peak=float(np.max(np.abs(samples)))
            sd.play(samples*(.7/max(.01,peak)),samplerate=16000);sd.wait()
            time.sleep(.4);host.stop();worker.join(120)
            assert not worker.is_alive(),'Hardware QA timed out'
            if errors:
                result=dict(source='Google FLEURS, CC-BY-4.0, public speaker playback',revision=REVISION,
                    fixture=filename,fileAsr=file_text,status=state,capture=capture_stats,error=errors,
                    realMicrophone=True,realProductChat=False,rawMicrophoneSaved=False,humanSpeakerAcceptance=False)
                (output/'observations.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
                raise RuntimeError('Physical playback QA failed: '+str(errors))
            snapshot=received[0].get('snapshot',received[0])
            microphone_text=next(m['text'] for m in snapshot['state']['chat'] if m['role']=='elder')
            assert snapshot['state']['chat'][-1]['role']=='agent'
            assert len(set(file_text)&set(microphone_text))>=5,(file_text,microphone_text)
            result=dict(source='Google FLEURS, CC-BY-4.0, public speaker playback',revision=REVISION,
                fixture=filename,reference=reference,fileAsr=file_text,microphoneAsr=microphone_text,
                status=state,capture=capture_stats,realMicrophone=True,realProductChat=True,rawMicrophoneSaved=False,
                humanSpeakerAcceptance=False)
            (output/'observations.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(result,ensure_ascii=True),flush=True)


if __name__=='__main__':main()
