"""Generated APK paths must be readable by Android AssetManager."""
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'tools' / 'normalize_apk.py'

class PackagingTest(unittest.TestCase):
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
