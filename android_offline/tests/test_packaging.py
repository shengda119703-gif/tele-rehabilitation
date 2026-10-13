"""Generated APK paths must be readable by Android AssetManager."""
import subprocess
import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'tools' / 'normalize_apk.py'

class PackagingTest(unittest.TestCase):
    def test_automatic_tracking_is_bundled_and_manual_markers_are_removed(self):
        root = SCRIPT.parents[2]
        manifest = ET.parse(root/'android_offline/AndroidManifest.xml').getroot()
        version = manifest.attrib['{http://schemas.android.com/apk/res/android}versionName']
        with zipfile.ZipFile(root/f'android_offline/dist/tele-rehabilitation-mobile-{version}.apk') as archive:
            for source, target in [('mobile_rehab/static/automatic-motion.js', 'assets/static/automatic-motion.js'),
                                   ('android_offline/web/motion.js', 'assets/local/motion.js'),
                                   ('android_offline/web/worker.js', 'assets/local/worker.js')]:
                self.assertEqual(archive.read(target), (root/source).read_bytes())
            renderer = archive.read('assets/static/barbell.js').decode('utf-8')
            self.assertIn('function readBarCalibration(){return null;}', renderer)
            self.assertNotIn('id="bar-confirm"', renderer)
            self.assertNotIn('id="bar-frame"', renderer)
            self.assertIn('/static/automatic-motion.js', archive.read('assets/local/motion.js').decode('utf-8'))

    def test_merged_release_metadata_and_both_local_adapters_stay_connected(self):
        root = SCRIPT.parents[2]
        manifest = ET.parse(root/'android_offline/AndroidManifest.xml').getroot()
        namespace = '{http://schemas.android.com/apk/res/android}'
        version = manifest.attrib[namespace+'versionName']
        self.assertGreater(int(manifest.attrib[namespace+'versionCode']), 31)
        package = json.loads((root/'android_offline/package.json').read_text(encoding='utf-8'))
        lock = json.loads((root/'android_offline/package-lock.json').read_text(encoding='utf-8'))
        self.assertEqual(package['version'], version)
        self.assertEqual(lock['version'], version)
        self.assertEqual(lock['packages']['']['version'], version)
        with zipfile.ZipFile(root/f'android_offline/dist/tele-rehabilitation-mobile-{version}.apk') as archive:
            for page in ('index.html', 'capture.html'):
                html = archive.read('assets/'+page).decode('utf-8')
                for adapter in ('product.js', 'model-policy.js', 'deepseek.js', 'practice.js'):
                    self.assertLess(html.index('/local/'+adapter), html.index('/local/local-api.js'))
            local = archive.read('assets/local/local-api.js').decode('utf-8')
            self.assertIn('PhonePractice.createPort', local)
            self.assertIn('PhoneDeepSeek?.conversationModel()', local)
            self.assertIn('PhoneDeepSeek?.agentModel()', local)
            for method in (b'deepSeekConfigured', b'deepSeekRequest', b'guidanceCancel'):
                self.assertIn(method, archive.read('classes.dex'))

    def test_release_lin_assets_keep_official_ui_and_exclude_private_qa_files(self):
        root = SCRIPT.parents[2]
        manifest = ET.parse(root/'android_offline/AndroidManifest.xml').getroot()
        version = manifest.attrib['{http://schemas.android.com/apk/res/android}versionName']
        apk = root/f'android_offline/dist/tele-rehabilitation-mobile-{version}.apk'
        self.assertTrue(apk.is_file(), f'Build {version} before running release QA')
        with zipfile.ZipFile(apk) as archive:
            names = archive.namelist()
            self.assertFalse(any('\\' in n or '..' in n.split('/') for n in names))
            self.assertFalse(any(n.endswith(('.mp4', '.sqlite3', '.db', '.jks', '.dpapi')) or
                                 n.endswith(('smoke.js', 'lin-smoke.js')) for n in names))
            for name in ('practice.js', 'local-api.js', 'store.js', 'deepseek.js'):
                self.assertEqual(archive.read('assets/local/'+name),
                                 (root/'android_offline/web'/name).read_bytes())
            capture = archive.read('assets/capture.html').decode('utf-8')
            self.assertLess(capture.index('/static/guidance-scheduler.js'), capture.index('/static/app.js'))
            self.assertIn('/static/guidance-scheduler.js', capture)
            for method in (b'guidanceSpeak', b'guidanceCancel', b'guidancePrepare'):
                self.assertIn(method, archive.read('classes.dex'))
            self.assertLess(capture.index('/local/practice.js'), capture.index('/local/local-api.js'))
            self.assertIn('/static/practice-flow.js', capture)
            self.assertIn('/static/formal-feedback.js', capture)
            self.assertIn('/static/formal-training.js', capture)
            self.assertIn('/static/formal-practice-camera.js', capture)
            self.assertLess(capture.index('/static/formal-measurement.js'), capture.index('/static/formal-training.js'))
            self.assertLess(capture.index('/static/formal-training.js'), capture.index('/static/formal-practice-camera.js'))
            self.assertLess(capture.index('/static/formal-feedback.js'), capture.index('/static/formal-measurement.js'))
            self.assertLess(capture.index('/static/practice-feedback.js'), capture.index('/static/practice-flow.js'))
            self.assertIn('assets/local/deepseek.js', names)
            self.assertIn('assets/local/model-policy.js', names)
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
