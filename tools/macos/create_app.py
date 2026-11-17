"""Create a local .app launcher using an already prepared Python/Node install."""
import argparse
import json
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--destination', type=Path, default=Path.home() / 'Applications')
    parser.add_argument('--project-root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--python', type=Path, default=Path(sys.executable))
    parser.add_argument('--node', type=Path, default=Path(shutil.which('node') or 'node'))
    args = parser.parse_args()
    root = args.project_root.resolve()
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
    with tempfile.TemporaryDirectory() as tmp:
        config = Path(tmp) / 'config.h'
        config.write_text('\n'.join(f'#define {key} {json.dumps(str(value), ensure_ascii=False)}'
            for key, value in dict(ANKANG_ROOT=root, ANKANG_PYTHON=python, ANKANG_NODE=node).items()))
        native = Path(tmp) / 'Ankang'
        subprocess.run(['xcrun', 'clang', '-O2', '-mmacosx-version-min=11.0',
            '-framework', 'AppKit', '-include', str(config),
            str(Path(__file__).with_name('launcher.m')), '-o', str(native)], check=True)
        replacement = executable.with_suffix('.new')
        shutil.copy2(native, replacement)
        replacement.replace(executable)
    info = dict(CFBundleName='安康康复', CFBundleDisplayName='安康康复（竖屏版）',
        CFBundleIdentifier='cn.ankang.rehab.portrait', CFBundleExecutable='Ankang',
        CFBundlePackageType='APPL', CFBundleShortVersionString='0.25.2', CFBundleVersion='2',
        CFBundleGetInfoString='安康 0.25.2 · macOS 竖屏启动器 revision 2',
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
    # Finder metadata from an earlier generated bundle prevents bundle signing.
    for path in (bundle, *bundle.rglob('*')):
        attributes = subprocess.check_output(['xattr', str(path)], text=True).splitlines()
        for attribute in ('com.apple.FinderInfo', 'com.apple.ResourceFork'):
            if attribute in attributes:
                subprocess.run(['xattr', '-d', attribute, str(path)], check=True)
    subprocess.run(['codesign', '--force', '--sign', '-', '--timestamp=none', str(bundle)], check=True)
    print(bundle)


if __name__ == '__main__':
    main()
