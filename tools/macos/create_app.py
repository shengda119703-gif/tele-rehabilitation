"""Create a local .app launcher using an already prepared Python/Node install."""
import argparse
from pathlib import Path
import plistlib
import shlex
import shutil
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--destination', type=Path, default=Path.home() / 'Desktop')
    parser.add_argument('--python', type=Path, default=Path(sys.executable))
    parser.add_argument('--node', type=Path, default=Path(shutil.which('node') or 'node'))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    python, node = args.python.absolute(), args.node.absolute()
    if not python.is_file() or not node.is_file():
        parser.error('请指定可用的 Python 和 Node 可执行文件')
    bundle = args.destination / '安康康复（竖屏版）.app'
    executable = bundle / 'Contents/MacOS/Ankang'
    resources = bundle / 'Contents/Resources'
    executable.parent.mkdir(parents=True, exist_ok=True)
    resources.mkdir(parents=True, exist_ok=True)
    runtime = root / '.runtime'
    runtime.mkdir(exist_ok=True)
    executable.write_text('\n'.join([
        '#!/bin/zsh',
        f'cd {shlex.quote(str(root))} || exit 1',
        f'export ANKANG_NODE={shlex.quote(str(node))}',
        f'exec {shlex.quote(str(python))} -m mobile_rehab.portrait "$@" >> {shlex.quote(str(runtime / "portrait.log"))} 2>&1',
        '',
    ]))
    executable.chmod(0o755)
    info = dict(CFBundleName='安康康复', CFBundleDisplayName='安康康复（竖屏版）',
        CFBundleIdentifier='cn.ankang.rehab.portrait', CFBundleExecutable='Ankang',
        CFBundlePackageType='APPL', CFBundleShortVersionString='0.25.2', CFBundleVersion='1',
        CFBundleIconFile='Ankang.icns', NSHighResolutionCapable=True,
        NSCameraUsageDescription='仅在你主动开始动作评估或训练时使用摄像头。',
        NSMicrophoneUsageDescription='仅在你主动选择语音输入时使用麦克风。')
    (bundle / 'Contents/Info.plist').write_bytes(plistlib.dumps(info))
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
    from PIL import Image
    renderer = QSvgRenderer(str(root / 'mobile_rehab/static/icon.svg'))
    with tempfile.TemporaryDirectory() as tmp:
        image = QImage(1024, 1024, QImage.Format_ARGB32)
        image.fill(0)
        painter = QPainter(image)
        renderer.render(painter, QRectF(0, 0, 1024, 1024))
        painter.end()
        png = Path(tmp) / 'icon.png'
        image.save(str(png))
        Image.open(png).save(resources / 'Ankang.icns', format='ICNS')
    print(bundle)


if __name__ == '__main__':
    main()
