"""Explicit setup only. Partner pinned official model, verified Git/LFS hashes."""
import hashlib
import urllib.request
from .core import ROOT

REPOSITORY='Systran/faster-whisper-base'
REVISION='ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66'
FILES={'config.json':('git','867cf1a0fece1394e01d55e287ba2f09a577c046'),
       'model.bin':('sha256','d01c3014881c9c6f3133c182f3d2887eb6ca1c789a7538c5c007196857a0a6a9'),
       'tokenizer.json':('git','7818adb6de9fa3064d3ff81226fdd675be1f6344'),
       'vocabulary.txt':('git','c9074644d9d1205686f16d411564729461324b75')}


def digest(path,kind):
    h=hashlib.sha256() if kind=='sha256' else hashlib.sha1()
    if kind=='git':h.update(f'blob {path.stat().st_size}\0'.encode())
    with path.open('rb') as stream:
        for part in iter(lambda:stream.read(1024*1024),b''):h.update(part)
    return h.hexdigest()


def main():
    target=ROOT/'rehab_codex_single_camera_v2_1/.runtime/voice/whisper-base'
    target.mkdir(parents=True,exist_ok=True)
    for name,(kind,expected) in FILES.items():
        path=target/name
        if path.is_file() and digest(path,kind)==expected:continue
        pending=path.with_suffix(path.suffix+'.download')
        url=f'https://huggingface.co/{REPOSITORY}/resolve/{REVISION}/{name}'
        print('Preparing '+name,flush=True)
        with urllib.request.urlopen(url,timeout=60) as source,pending.open('wb') as output:
            while part:=source.read(1024*1024):output.write(part)
        if digest(pending,kind)!=expected:raise ValueError('Model verification failed: '+name)
        pending.replace(path)
    print('Local Chinese ASR model verified.')


if __name__=='__main__':main()
