"""Generated APK paths must be readable by Android AssetManager."""
import subprocess
import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'tools' / 'normalize_apk.py'

class PackagingTest(unittest.TestCase):
    def test_release_lin_assets_keep_official_ui_and_exclude_private_qa_files(self):
        root = SCRIPT.parents[2]
        apk = root/'android_offline/dist/tele-rehabilitation-mobile-0.2.1.apk'
        self.assertTrue(apk.is_file(), 'Build 0.2.1 before running release QA')
        with zipfile.ZipFile(apk) as archive:
            names = archive.namelist()
            self.assertFalse(any('\\' in n or '..' in n.split('/') for n in names))
            self.assertFalse(any(n.endswith(('.mp4', '.sqlite3', '.db', '.jks', '.dpapi')) or
                                 n.endswith(('smoke.js', 'lin-smoke.js')) for n in names))
            locked = json.loads(archive.read('assets/ui-lock.json'))
            for name, digest in locked.items():
                self.assertEqual(hashlib.sha256(archive.read('assets/static/'+name)).hexdigest(), digest)
                self.assertEqual(hashlib.sha256((root/'mobile_rehab/static'/name).read_bytes()).hexdigest(), digest)
            fixture = json.loads(archive.read('assets/lin-profile.json'))
            self.assertEqual(fixture['schema'], 'test-lin-apk-v1')
            self.assertTrue(fixture['synthetic'])
            self.assertEqual(len(fixture['data']['jobs']), 24)
            self.assertEqual(len(fixture['attachments']), 3)
            self.assertTrue(all(j['synthetic'] and not j['video_available'] for j in fixture['data']['jobs']))

    def test_windows_asset_paths_keep_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            src, dst = Path(folder) / 'before.apk', Path(folder) / 'after.apk'
            with zipfile.ZipFile(src, 'w') as archive:
                entry = zipfile.ZipInfo()
                entry.filename = 'assets/models\\pose.task'
                archive.writestr(entry, b'exact-model-bytes')
            # Python 3.13 normalizes names on read; inspect actual ZIP header bytes.
            self.assertIn(b'assets/models\\pose.task', src.read_bytes())
            subprocess.run([sys.executable, str(SCRIPT), str(src), str(dst)], check=True, capture_output=True)
            with zipfile.ZipFile(dst) as archive:
                self.assertEqual(archive.read('assets/models/pose.task'), b'exact-model-bytes')
            self.assertNotIn(b'assets/models\\pose.task', dst.read_bytes())

    def test_duplicate_and_traversal_rejected(self):
        for names in [('assets/a\\b', 'assets/a/b'), ('assets/../bad',)]:
            with self.subTest(names=names), tempfile.TemporaryDirectory() as folder:
                src, dst = Path(folder) / 'before.apk', Path(folder) / 'after.apk'
                with zipfile.ZipFile(src, 'w') as archive:
                    for name in names:
                        entry = zipfile.ZipInfo()
                        entry.filename = name
                        archive.writestr(entry, b'test')
                result = subprocess.run([sys.executable, str(SCRIPT), str(src), str(dst)], capture_output=True)
                self.assertNotEqual(result.returncode, 0)

if __name__ == '__main__':
    unittest.main()
