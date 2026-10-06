"""Explicit, revocable phone connection hosted by the running desktop."""
import secrets
import socket
import threading


class PhoneHost:
    def __init__(self, backend, owner, *, host='0.0.0.0', port=0):
        self.backend, self.owner = backend, owner
        self.code = secrets.token_hex(8)
        self.server = None
        self.error = ''
        self.ready = threading.Event()
        self.stopped = threading.Event()
        self.closing = threading.Event()
        self.shared = None
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.bind((host, port))
        self.socket.listen(128)
        self.port = self.socket.getsockname()[1]
        self.urls = []
        self.thread = threading.Thread(target=self.run, daemon=True, name='ankang-phone')
        self.thread.start()

    def run(self):
        try:
            import uvicorn
            from .server import create_app
            from .unified import SharedProduct
            import hashlib
            folder = hashlib.sha256(self.owner.encode()).hexdigest()[:32]
            self.shared = SharedProduct(self.backend, self.owner)
            app = create_app(self.backend.data_dir/'phone'/folder, self.code, shared=self.shared)
            # Enumerate interfaces locally. Hostname DNS on Windows can block
            # startup for many seconds when a DNS server is unavailable.
            from PySide6.QtNetwork import QNetworkInterface, QAbstractSocket
            addresses = sorted({ip.toString() for ip in QNetworkInterface.allAddresses()
                                if ip.protocol() == QAbstractSocket.IPv4Protocol and not ip.isLoopback()})
            self.urls = [f'http://{ip}:{self.port}' for ip in addresses] or [f'http://127.0.0.1:{self.port}']
            self.server = uvicorn.Server(uvicorn.Config(app, log_level='warning', log_config=None, access_log=False,
                                                      timeout_graceful_shutdown=3))
            self.ready.set()
            if not self.closing.is_set():
                self.server.run(sockets=[self.socket])
        except Exception as error:
            self.error = str(error)
            self.ready.set()
        finally:
            self.socket.close()
            self.stopped.set()

    def close(self):
        self.closing.set()
        if self.shared:
            self.shared.close()
        if self.server:
            self.server.should_exit = True
        # No join on the Qt thread: analysis teardown is allowed to finish off-UI.
