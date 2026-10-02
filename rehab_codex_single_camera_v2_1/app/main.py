from __future__ import annotations

import argparse
import multiprocessing
import os
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description='本地单摄像头居家康复辅助应用')
    parser.add_argument('--data-dir', type=Path, help='独立本地数据目录')
    parser.add_argument('--screenshot', type=Path, help='开发用：离屏 UI 截图并退出，不打开输入')
    args = parser.parse_args()
    from PySide6.QtCore import QTimer, QLockFile
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QApplication, QMessageBox
    from .ui.product_window import ProductWindow
    from .settings import ROOT
    app = QApplication(sys.argv[:1])
    app.setStyle('Fusion')
    # Offscreen QA does not discover Windows system fonts automatically.
    for filename in ('msyh.ttc', 'msyhbd.ttc', 'segoeui.ttf'):
        font_file = Path(os.environ.get('WINDIR', 'C:/Windows'))/'Fonts'/filename
        if font_file.is_file():
            QFontDatabase.addApplicationFont(str(font_file))
    app.setFont(QFont('Microsoft YaHei UI', 10))
    default_data = Path(os.environ.get('LOCALAPPDATA', str(Path.home())))/'HomeRehab' if getattr(sys, 'frozen', False) else ROOT/'data'
    data_dir = (args.data_dir or default_data).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    instance_lock = QLockFile(str(data_dir/'application.lock'))
    instance_lock.setStaleLockTime(0)
    if not instance_lock.tryLock(0):
        QMessageBox.information(None, '应用正在运行', '此数据目录的康复助手已经运行。请使用已打开的窗口。')
        return 1
    window = ProductWindow(data_dir=data_dir)
    window.show()
    if args.screenshot:
        def capture():
            args.screenshot.parent.mkdir(parents=True, exist_ok=True)
            try:
                window.grab().save(str(args.screenshot))
            finally:
                window.close()
        QTimer.singleShot(1800, capture)
    return app.exec()


if __name__ == '__main__':
    multiprocessing.freeze_support()
    raise SystemExit(main())
