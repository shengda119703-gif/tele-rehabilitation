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
    def test_assessment_covers_are_packaged_with_the_same_code_and_images(self):
        root = SCRIPT.parents[2]
        version = ET.parse(root/'android_offline/AndroidManifest.xml').getroot().attrib['{http://schemas.android.com/apk/res/android}versionName']
        static = root/'mobile_rehab/static'
        metadata = json.loads((static/'assets/assessment-artwork-v1/provenance.json').read_text(encoding='utf-8'))
        with zipfile.ZipFile(root/f'android_offline/dist/tele-rehabilitation-mobile-{version}.apk') as archive:
            for file in ('assessment-artwork.js', 'assessment-artwork.css', 'rehab-v51.js'):
                self.assertEqual(archive.read('assets/static/'+file), (static/file).read_bytes())
            for file in ('index.html', 'capture.html'):
                html = archive.read('assets/'+file).decode('utf-8')
                self.assertLess(html.index('/static/assessment-artwork.js'), html.index('/static/rehab-v51.js'))
            self.assertEqual(len(metadata['assets']), 9)
            for asset in metadata['assets']:
                file = 'assets/static/assets/assessment-artwork-v1/'+asset['file']
                self.assertEqual(hashlib.sha256(archive.read(file)).hexdigest(), asset['sha256'])

    def test_public_action_library_is_packaged_without_internal_proposals(self):
        root = SCRIPT.parents[2]
        version = ET.parse(root/'android_offline/AndroidManifest.xml').getroot().attrib['{http://schemas.android.com/apk/res/android}versionName']
        with zipfile.ZipFile(root/f'android_offline/dist/tele-rehabilitation-mobile-{version}.apk') as archive:
            prefix = 'assets/static/assets/rehab-library-v1/'
            catalogue = json.loads(archive.read(prefix+'catalogue.json'))
            self.assertEqual(len(catalogue['actions']), 185)
            self.assertFalse(catalogue['measurement_bindings'])
            self.assertEqual(sum(n.startswith(prefix) and n.endswith('.webp') for n in archive.namelist()), 656)
            for image in catalogue['images'].values():
                name = 'assets'+image['url']
                self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), image['sha256'])
            self.assertNotIn('专业介绍待完善', archive.read('assets/static/rehab-v51-capture.js').decode('utf-8'))

    def test_workbench_and_motion_coexist_without_retired_ocr_loader(self):
        root = SCRIPT.parents[2]
        source = (root/'android_offline/src/cn/tele/rehabilitation/offline/MainActivity.java').read_text(encoding='utf-8')
        self.assertIn('"运动与心率","联系康复医师"', source)
        self.assertIn('if(which==10){web.evaluateJavascript("PhoneAccount.open()",null);return;}', source)
        self.assertIn('if(which==9)motionPanel.open();', source)
        version = ET.parse(root/'android_offline/AndroidManifest.xml').getroot().attrib[
            '{http://schemas.android.com/apk/res/android}versionName']
        with zipfile.ZipFile(root/f'android_offline/dist/tele-rehabilitation-mobile-{version}.apk') as archive:
            for page in ('index.html', 'capture.html'):
                html = archive.read('assets/'+page).decode('utf-8')
                for adapter in ('practice.js', 'account.js'):
                    self.assertLess(html.index('/local/'+adapter), html.index('/local/local-api.js'))
                self.assertNotIn('/local/ocr.js', html)
                self.assertNotIn('/ocr/tesseract.min.js', html)
            self.assertEqual(archive.read('assets/local/account.js'), (root/'android_offline/web/account.js').read_bytes())
            self.assertFalse(any(name.startswith('assets/ocr/') for name in archive.namelist()))
            for method in (b'accountRequest', b'accountLogin', b'motionRead', b'motionBind'):
                self.assertIn(method, archive.read('classes.dex'))

    def test_motion_service_is_private_and_does_not_request_silent_background_location(self):
        root = SCRIPT.parents[2]
        manifest = ET.parse(root/'android_offline/AndroidManifest.xml').getroot()
        ns = '{http://schemas.android.com/apk/res/android}'
        permissions = {v.attrib[ns+'name'] for v in manifest.findall('uses-permission')}
        for name in ('ACTIVITY_RECOGNITION', 'ACCESS_FINE_LOCATION', 'BLUETOOTH_SCAN',
                     'BLUETOOTH_CONNECT', 'FOREGROUND_SERVICE_HEALTH',
                     'FOREGROUND_SERVICE_LOCATION', 'FOREGROUND_SERVICE_CONNECTED_DEVICE'):
            self.assertIn('android.permission.'+name, permissions)
        self.assertNotIn('android.permission.ACCESS_BACKGROUND_LOCATION', permissions)
        self.assertNotIn('android.permission.RECEIVE_BOOT_COMPLETED', permissions)
        self.assertNotIn('android.permission.BODY_SENSORS', permissions)
        service = manifest.find('application/service')
        self.assertEqual(service.attrib[ns+'name'], '.MotionService')
        self.assertEqual(service.attrib[ns+'exported'], 'false')
        self.assertEqual(set(service.attrib[ns+'foregroundServiceType'].split('|')),
                         {'health', 'location', 'connectedDevice'})

    def test_release_contains_sensor_reader_but_no_sensor_history_or_test_harness(self):
        root = SCRIPT.parents[2]
        version = ET.parse(root/'android_offline/AndroidManifest.xml').getroot().attrib[
            '{http://schemas.android.com/apk/res/android}versionName']
        with zipfile.ZipFile(root/f'android_offline/dist/tele-rehabilitation-mobile-{version}.apk') as archive:
            dex = archive.read('classes.dex')
            for name in (b'MotionService', b'MotionPanel', b'MotionDb', b'pace_s_km',
                         b'motionBind', b'motionRead', b'motionSettings'):
                self.assertIn(name, dex)
            self.assertNotIn(b'MotionSmoke', dex)
            self.assertFalse(any(n.endswith(('.db', '.sqlite3')) for n in archive.namelist()))
            local = archive.read('assets/local/local-api.js').decode('utf-8')
            self.assertIn('!PhoneLin.isLin(store)', local)
            self.assertIn("route==='/device-motion'", local)

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
            self.assertNotIn('assets/lin-profile.json', names)
            self.assertFalse(any('/rehab-candidates-v10/' in n for n in names))

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
