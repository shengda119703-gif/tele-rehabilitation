"""Install a local runtime outside Desktop/Documents; keep a desktop entry."""
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import time


def main():
    source = Path(__file__).resolve().parents[2]
    home = Path.home()
    runtime = home / 'Library/Application Support/AnkangPortrait'
    name = '安康康复（竖屏版）.app'
    desktop = home / 'Desktop' / name
    if desktop.exists() and not desktop.is_symlink():
        info = plistlib.loads((desktop / 'Contents/Info.plist').read_bytes())
        if info.get('CFBundleIdentifier') != 'cn.ankang.rehab.portrait':
            raise RuntimeError('桌面有同名的其他应用，未覆盖。')

    from PySide6.QtCore import QLockFile
    lock = QLockFile(str(source / 'rehab_codex_single_camera_v2_1/data/application.lock'))
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        raise RuntimeError('请先保存并退出当前安康窗口，再重新安装。')
    try:
        def ignore(folder, names):
            skipped = {'__pycache__', '.pytest_cache', '.runtime', 'qa-output', 'tests'}
            if Path(folder) == source / 'rehab_codex_single_camera_v2_1':
                skipped.add('data')
            return skipped.intersection(names)

        for part in ('mobile_rehab', 'rehab_codex_single_camera_v2_1', 'ankang', 'bridges',
                     'configs', 'cloud_service', 'public_web', '.venv'):
            shutil.copytree(source / part, runtime / part, dirs_exist_ok=True,
                            symlinks=True, ignore=ignore)
        data = runtime / 'rehab_codex_single_camera_v2_1/data'
        if not data.exists():
            shutil.copytree(source / 'rehab_codex_single_camera_v2_1/data', data,
                            ignore=shutil.ignore_patterns('application.lock'))
    finally:
        lock.unlock()

    applications = home / 'Applications'
    subprocess.run([sys.executable, str(Path(__file__).with_name('create_app.py')),
        '--project-root', str(runtime), '--python', str(runtime / '.venv/bin/python'),
        '--destination', str(applications)], check=True)
    if desktop.is_symlink():
        desktop.unlink()
    elif desktop.exists():
        backups = runtime / 'backups'
        backups.mkdir(exist_ok=True)
        shutil.move(str(desktop), str(backups / f'desktop-launcher-{time.time_ns()}.app'))
    desktop.symlink_to(applications / name, target_is_directory=True)
    print(f'桌面入口：{desktop}\n运行目录：{runtime}')


if __name__ == '__main__':
    main()
