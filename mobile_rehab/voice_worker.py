"""Partner Whisper-base settings, adapted to uploaded phone audio instead of mic."""
import json
import sys


def main():
    from faster_whisper import WhisperModel
    from faster_whisper.audio import decode_audio
    import numpy as np
    audio=decode_audio(sys.argv[1],sampling_rate=16000)
    if not 4000<=audio.size<=480000 or not np.isfinite(audio).all():
        raise ValueError('Short recording required')
    model=WhisperModel(sys.argv[2],device='cpu',compute_type='int8',cpu_threads=2,
                      num_workers=1,local_files_only=True)
    segments,_=model.transcribe(audio,language='zh',beam_size=3,vad_filter=True,
        condition_on_previous_text=False,without_timestamps=True)
    text=''.join(s.text.strip() for s in segments if s.no_speech_prob<.6 and s.avg_logprob> -1).strip()
    sys.stdout.write(json.dumps({'text':text},ensure_ascii=False))


if __name__=='__main__':main()
