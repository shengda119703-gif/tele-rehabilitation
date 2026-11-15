"""Phone-sized desktop host for the existing unified UI and ProductBackend."""
import argparse
from pathlib import Path
import sys
import time
from urllib.error import URLError
from urllib.request import Request, urlopen
import json

from .core import CORE
from .desktop import PhoneHost
from app.product.backend import ProductBackend


def main():
    parser = argparse.ArgumentParser(description='安康 · 竖屏桌面版')
    parser.add_argument('--data-dir', type=Path, default=CORE / 'data')
    args = parser.parse_args()
    from PySide6.QtCore import QEvent, QLockFile, QProcess, QTimer, QUrl
    from PySide6.QtGui import QDesktopServices, QFont, QIcon
    from PySide6.QtNetwork import QNetworkCookie
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog,
        QFormLayout, QInputDialog, QMainWindow, QMessageBox)
    from app.ui.product_dialogs import ProductProfileDialog

    app = QApplication(sys.argv[:1])
    app.setApplicationName('安康康复')
    app.setFont(QFont('PingFang SC', 12))
    app.setWindowIcon(QIcon(str(Path(__file__).parent / 'static/icon.svg')))
    data_dir = args.data_dir.resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(data_dir / 'application.lock'))
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        QMessageBox.information(None, '安康正在运行', '请使用已打开的安康窗口。')
        return 1

    backend = ProductBackend(data_dir)
    host = None
    desktop_requested = False
    try:
        profiles = backend.call('profile.list', '', timeout=20)
        if not profiles:
            dialog = ProductProfileDialog()
            dialog.resize(430, 690)
            for form in dialog.findChildren(QFormLayout):
                form.setRowWrapPolicy(QFormLayout.WrapAllRows)
                form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
            dialog.age.setMinimumWidth(110)
            if dialog.exec() != QDialog.Accepted:
                return 0
            value = dict(dialog.value)
            owner = value.pop('ownerId')
            backend.call('profile.save', owner, value, timeout=20)
        elif len(profiles) == 1:
            owner = profiles[0]['ownerId']
        else:
            labels = [f"{p['profile']['name']} · {p['ownerId']}" for p in profiles]
            selected, accepted = QInputDialog.getItem(None, '选择本人档案', '本次使用的档案', labels, 0, False)
            if not accepted:
                return 0
            owner = profiles[labels.index(selected)]['ownerId']

        # This window is a local client; it does not enable LAN sharing.
        host = PhoneHost(backend, owner, host='127.0.0.1')
        base = QUrl(f'http://127.0.0.1:{host.port}')

        class LocalPage(QWebEnginePage):
            def acceptNavigationRequest(self, url, kind, main_frame):
                if url.scheme() == 'about' or (url.scheme() == 'http' and url.host() == base.host() and url.port() == base.port()):
                    return True
                if kind == QWebEnginePage.NavigationTypeLinkClicked and url.scheme() in ('https', 'http', 'tel', 'mailto'):
                    QDesktopServices.openUrl(url)
                return False

        window = QMainWindow()
        window.setWindowTitle('安康 · 我的康复生活')
        view = QWebEngineView(window)
        profile = QWebEngineProfile(view)
        page = LocalPage(profile, view)
        view.setPage(page)
        window.setCentralWidget(view)
        window.setMinimumSize(360, 600)
        available = app.primaryScreen().availableGeometry()
        window.resize(430, min(860, available.height() - 50))
        window.move(available.center() - window.rect().center())

        def open_desktop():
            nonlocal desktop_requested
            state = host.server.config.app.state if host.server else None
            if state and (state.live.session or any(j['state'] in ('uploading', 'queued', 'analyzing')
                                                   for j in state.jobs.items.values())):
                QMessageBox.information(window, '请先结束当前任务', '请完成录像分析或停止实时指导后，再打开完整电脑端。')
                return
            desktop_requested = True
            app.quit()

        menu = window.menuBar().addMenu('工作区')
        menu.addAction('打开完整电脑端（实时评估与训练）', open_desktop)

        def permission(origin, feature):
            allowed = origin.host() == base.host() and origin.port() == base.port()
            if allowed:
                allowed = QMessageBox.question(window, '使用设备', '是否允许本次使用摄像头或麦克风？') == QMessageBox.Yes
            page.setFeaturePermission(origin, feature, QWebEnginePage.PermissionGrantedByUser if allowed
                                      else QWebEnginePage.PermissionDeniedByUser)

        page.featurePermissionRequested.connect(permission)

        def download(item):
            filename, _ = QFileDialog.getSaveFileName(window, '保存文件', item.downloadFileName())
            if filename:
                target = Path(filename)
                item.setDownloadDirectory(str(target.parent))
                item.setDownloadFileName(target.name)
                item.accept()
            else:
                item.cancel()

        profile.downloadRequested.connect(download)
        view.setHtml('<html lang="zh-CN"><body style="font-family:system-ui;padding:32px;background:#fafaf8">正在打开本人档案…</body></html>')
        window.show()
        started = time.monotonic()
        timer = QTimer(window)
        timer.setInterval(100)

        def cookie_added(cookie):
            if bytes(cookie.name()) == b'rehab_device':
                profile.cookieStore().cookieAdded.disconnect(cookie_added)
                view.load(base)

        def connect():
            if host.error:
                raise RuntimeError(host.error)
            if time.monotonic() - started > 30:
                raise RuntimeError('本机服务启动超时，请重新打开安康。')
            if not host.ready.is_set():
                return
            request = Request(base.toString() + '/api/pair',
                data=json.dumps({'code': host.code}).encode(),
                headers={'Content-Type': 'application/json', 'X-Rehab-Client': 'mobile-v1'})
            try:
                with urlopen(request, timeout=.3) as response:
                    cookies = QNetworkCookie.parseCookies(response.headers['Set-Cookie'].encode())
            except (URLError, TimeoutError):
                return  # The socket is reserved before uvicorn starts accepting.
            timer.stop()
            profile.cookieStore().cookieAdded.connect(cookie_added)
            profile.cookieStore().setCookie(cookies[0], base)

        def poll():
            try:
                connect()
            except Exception as error:
                timer.stop()
                QMessageBox.critical(window, '安康启动失败', str(error))
                window.close()

        timer.timeout.connect(poll)
        timer.start()
        result = app.exec()
        # The page must release its profile before Qt destroys the view.
        page.deleteLater()
        app.sendPostedEvents(None, QEvent.DeferredDelete)
    except Exception as error:
        QMessageBox.critical(None, '安康启动失败', str(error))
        return 1
    finally:
        if host:
            host.close()
            host.thread.join(timeout=6)
        backend.close()
        lock.unlock()
    if desktop_requested:
        started, _ = QProcess.startDetached(sys.executable,
            ['-m', 'app.main', '--data-dir', str(data_dir)], str(CORE))
        if not started:
            QMessageBox.critical(None, '电脑端启动失败', '请重新打开安康后再试。')
            return 1
    return result


if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    raise SystemExit(main())
