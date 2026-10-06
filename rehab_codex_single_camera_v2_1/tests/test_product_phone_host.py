import sys
import time
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from test_product_window import desktop, wait
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
import httpx


def test_phone_dialog_does_not_lock_window_and_stops_without_closing_backend(desktop):
    w, app = desktop
    seen=[]
    def close_dialog():
        dialog=QApplication.activeModalWidget()
        seen.append(dialog.windowTitle())
        dialog.accept()
    QTimer.singleShot(120,close_dialog)
    w._connect_phone()
    host=w.phone_host
    try:
        assert seen==['连接我的手机']
        deadline=time.monotonic()+12
        while not host.error and not (host.server and host.server.started) and time.monotonic()<deadline:
            app.processEvents()
            time.sleep(.01)  # Release GIL for first-time HTTP framework imports.
        assert host.error or host.server and host.server.started
        assert not host.error
        assert QApplication.activeModalWidget() is None and w.isEnabled()
        if sys.platform=='win32' and app.platformName()=='windows':
            import ctypes
            enabled=ctypes.windll.user32.IsWindowEnabled
            enabled.argtypes=[ctypes.c_void_p];enabled.restype=ctypes.c_bool
            assert enabled(int(w.winId()))
        with httpx.Client(base_url=f'http://127.0.0.1:{host.port}',headers={'X-Rehab-Client':'mobile-v1'}) as client:
            assert client.get('/api/unified').status_code==401
            assert client.post('/api/pair',json={'code':host.code}).status_code==200
            assert client.get('/api/unified').json()['snapshot']['profile']['ownerId']==w.owner
            host.close()
            assert host.shared.revoked
        w._request('snapshot');wait(app,lambda:not w.pending)
        assert w.snapshot['profile']['ownerId']==w.owner
    finally:
        host.close();host.thread.join(8)
        assert not host.thread.is_alive()
