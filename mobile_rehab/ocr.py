import asyncio
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

from fastapi import HTTPException, Request
from .core import ROOT


class DocumentOCR:
    def __init__(self,root):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.lock=threading.Lock()

    def status(self):
        return dict(available=importlib.util.find_spec('rapidocr') is not None,local=True)

    def read(self,raw):
        if not self.status()['available']:raise HTTPException(503,'本地文字识别尚未安装')
        if not self.lock.acquire(blocking=False):raise HTTPException(429,'另一份资料正在识别，请稍后重试')
        try:
            with tempfile.TemporaryDirectory(prefix='ocr-',dir=self.root) as folder:
                path=Path(folder)/'document.image';path.write_bytes(raw)
                try:
                    result=subprocess.run([sys.executable,'-m','mobile_rehab.ocr_worker',str(path)],cwd=ROOT,
                        stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=90,
                        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                    if result.returncode:raise HTTPException(400,'图片无法识别，请使用清晰的 JPG 或 PNG 资料')
                    data=json.loads(result.stdout.decode('utf-8'))
                    if not data.get('text'):raise HTTPException(400,'没有识别到清晰文字')
                    return data
                except subprocess.TimeoutExpired:raise HTTPException(504,'识别超时，请换更小的图片') from None
                except (UnicodeError,ValueError,KeyError,TypeError):raise HTTPException(502,'识别结果未能读取') from None
        finally:self.lock.release()


def install_ocr(app,data_dir,owner):
    service=DocumentOCR(data_dir/'ocr-temp');app.state.document_ocr=service

    @app.get('/api/product-ocr')
    def status(request: Request):
        owner(request);return service.status()

    @app.post('/api/product-ocr/{ident}')
    async def recognize(ident: str,request: Request):
        uid=owner(request)
        # Source bytes must belong to this browser profile; no arbitrary URLs or host paths.
        result=await asyncio.to_thread(app.state.product.call,uid,'archive.read',dict(id=ident))
        if result['mediaType'] not in ('image/png','image/jpeg'):raise HTTPException(400,'目前只识别 JPG 或 PNG 图片资料')
        return await asyncio.to_thread(service.read,bytes(result['bytes']))
