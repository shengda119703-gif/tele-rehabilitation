"""Offline ASR child: no model download, UI, domain writes or stored audio."""
import base64
import json
import sys


def main():
    import numpy as np
    from faster_whisper import WhisperModel
    raw=sys.stdin.buffer.read(4*1024*1024+1)
    if len(raw)>4*1024*1024:raise ValueError('Audio exceeds bounded capture')
    request=json.loads(raw)
    samples=np.frombuffer(base64.b64decode(request['audio'],validate=True),dtype='<f4')
    if not 4000<=samples.size<=480000 or not np.isfinite(samples).all():raise ValueError('Invalid audio')
    model=WhisperModel(request['model'],device='cpu',compute_type='int8',cpu_threads=2,
        num_workers=1,local_files_only=True)
    segments,_=model.transcribe(samples,language='zh',beam_size=3,vad_filter=True,
        condition_on_previous_text=False,without_timestamps=True)
    text=''.join(s.text.strip() for s in segments if s.no_speech_prob<.6 and s.avg_logprob> -1).strip()
    sys.stdout.write(json.dumps({'text':text},ensure_ascii=False))


if __name__=='__main__':main()
