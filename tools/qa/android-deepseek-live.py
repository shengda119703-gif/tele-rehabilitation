"""Real native transport QA, restricted to our dedicated empty emulator."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
ADB = Path(os.environ['LOCALAPPDATA'])/'AnkangAndroid/sdk/platform-tools/adb.exe'
SERIAL = 'emulator-5560'
REMOTE = '/data/local/tmp/ankang-deepseek-qa-key'

def adb(*args, timeout=30):
    return subprocess.run([str(ADB), '-s', SERIAL, *args], capture_output=True, timeout=timeout)

def main():
    name = adb('shell', 'getprop', 'ro.boot.qemu.avd_name').stdout.decode().strip()
    if name != 'AnkangDeepSeekQA':
        raise RuntimeError('Refuse credential transfer outside the dedicated TEST emulator')
    key = json.loads((Path(os.environ['APPDATA'])/'tele-rehabilitation/deepseek.json').read_text(encoding='utf-8'))['api_key']
    fd, temporary = tempfile.mkstemp(prefix='ankang-android-qa-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(key)
        if adb('push', temporary, REMOTE).returncode or adb('shell', 'chmod', '600', REMOTE).returncode:
            raise RuntimeError('QA transfer failed')
        result = adb('shell', 'am', 'instrument', '-w',
                     'cn.tele.rehabilitation.offline.agentqa/cn.tele.rehabilitation.offline.qa.DeepSeekSmoke', timeout=180)
        # Logs never include credential values, even on a failed test.
        output = result.stdout.decode('utf-8', errors='replace').replace(key, '[REDACTED]')
        (ROOT/'qa-output/android-deepseek-native-r1.log').write_text(output, encoding='utf-8')
        passed = result.returncode == 0 and 'liveCalls' in output and 'passed' in output and 'failure=' not in output
        print(json.dumps({'completed': passed, 'native': True, 'liveCalls': 4 if passed else 0}))
        if not passed:
            raise RuntimeError('Native TEST failed; inspect sanitized QA log')
    finally:
        Path(temporary).unlink(missing_ok=True)
        adb('shell', 'rm', '-f', REMOTE)

if __name__ == '__main__':
    main()
