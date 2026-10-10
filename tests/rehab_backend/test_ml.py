import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'rehab_codex_single_camera_v2_1'))
from tools.rehab_ml.common import paths
from tools.rehab_ml.data import grouped_split, verify_joint_order
from tools.rehab_ml.download import checked_zip, download_file
from tools.rehab_ml.features import causal_features
from app.rehab_v2.temporal import ShadowSequence, supports


class FakeResponse:
    def __init__(self, content, status=200, headers=None):
        self.content, self.status_code, self.headers = content, status, headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def raise_for_status(self):
        pass

    def iter_content(self, size):
        yield self.content


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.headers = None

    def get(self, url, **kw):
        self.headers = kw['headers']
        return self.response


class DataSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=paths()['data'])
        self.directory = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def spec(self, content):
        return dict(url='https://official.test/file', bytes=len(content), md5=hashlib.md5(content).hexdigest())

    def test_range_ignored_200_restarts_not_appends(self):
        content = b'complete official file'
        target = self.directory / 'download.bin'
        (self.directory / 'download.bin.part').write_bytes(content[:5])
        session = FakeSession(FakeResponse(content))
        result = download_file(self.spec(content), target, session=session)
        self.assertEqual(target.read_bytes(), content)
        self.assertEqual(session.headers, {'Range': 'bytes=5-'})
        self.assertFalse(result['cached'])

    def test_range_valid_206_appends_from_exact_offset(self):
        content = b'complete official file'
        target = self.directory / 'download.bin'
        (self.directory / 'download.bin.part').write_bytes(content[:5])
        session = FakeSession(FakeResponse(content[5:], 206,
                                          {'Content-Range': f'bytes 5-{len(content)-1}/{len(content)}'}))
        download_file(self.spec(content), target, session=session)
        self.assertEqual(target.read_bytes(), content)

    def test_corrupt_complete_is_preserved_not_published(self):
        content = b'abcd'
        target = self.directory / 'download.bin'
        with self.assertRaises(ValueError):
            download_file(self.spec(content), target, session=FakeSession(FakeResponse(b'efgh')))
        self.assertFalse(target.exists())
        self.assertEqual(len(list(self.directory.glob('*.quarantine-*'))), 1)

    def test_zip_traversal_and_file_quota(self):
        target = self.directory / 'unsafe.zip'
        with zipfile.ZipFile(target, 'w') as archive:
            archive.writestr('../escape.txt', b'data')
        with self.assertRaises(ValueError):
            checked_zip(target)
        target = self.directory / 'too_many.zip'
        with zipfile.ZipFile(target, 'w') as archive:
            archive.writestr('a.txt', b'a')
            archive.writestr('b.txt', b'b')
        with self.assertRaises(ValueError):
            checked_zip(target, max_files=1)

    def test_subject_split_before_any_windows(self):
        samples = [dict(sample_id=f'{person}-{rep}', subject_id=str(person), cohort='control', quality_label_mask=True)
                   for person in range(1, 21) for rep in range(4)]
        value = grouped_split(samples, 20261011)
        groups = value['subject_groups']
        self.assertFalse(set(groups['train']) & set(groups['test']))
        self.assertFalse(set(groups['val']) & set(groups['test']))
        for person in range(1, 21):
            partitions = [name for name, ids in value['samples'].items() if f'{person}-0' in ids]
            self.assertEqual(len(partitions), 1)
            self.assertTrue(all(f'{person}-{rep}' in value['samples'][partitions[0]] for rep in range(4)))

    def test_zip_windows_aliases_and_reserved_names_rejected(self):
        for i, names in enumerate((['Sample.txt', 'sample.txt'], ['con.txt'], ['trailing.'])):
            with self.subTest(names=names):
                target = self.directory / ('windows-unsafe-'+str(i)+'.zip')
                with zipfile.ZipFile(target, 'w') as archive:
                    for name in names:
                        archive.writestr(name, b'data')
                with self.assertRaises(ValueError):
                    checked_zip(target)

    def test_C12_causal_feature_prefix_and_future_perturbation(self):
        rng = np.random.default_rng(24)
        coords = rng.normal(0, .03, (60, 25, 3)).astype(np.float32)
        coords[:, 4, 0], coords[:, 8, 0] = -.2, .2
        masks, states = np.ones((60, 25), dtype=bool), np.full((60, 25), 2, dtype=np.uint8)
        times = np.arange(60)/30
        full, grid = causal_features(coords, masks, times, states, side='left')
        for end in range(2, len(times)):
            prefix, _ = causal_features(coords[:end], masks[:end], times[:end], states[:end], side='left')
            np.testing.assert_allclose(prefix, full[:len(prefix)], atol=1e-6)
        changed = coords.copy()
        changed[40:] += 10
        other, _ = causal_features(changed, masks, times, states, side='left')
        np.testing.assert_allclose(other[grid < times[40]], full[grid < times[40]], atol=1e-6)

    def test_C21_domain_gate_never_coerces_kinect_to_rgb(self):
        card = dict(input_domain='kinect_3d', schema_id='kinect25-v1')
        ok, reason = supports(card, dict(input_domain='yolo_coco_2d', schema_id='coco17-v1'))
        self.assertFalse(ok)
        self.assertEqual(reason, 'unsupported_input_domain')

    def test_C13_shadow_cache_isolated_and_default_off(self):
        card = dict(model_id='offline', input_domain='kinect_3d', schema_id='kinect25-v1',
                    coordinate_space='kinect_camera_3d', feature_version='feature', actions=['shoulder_abduction'],
                    sides=['left'], camera_views=['kinect_recording_only'], protocol_versions=['irds-rep-label-1'],
                    role='rep_quality_candidate', license_status='verified_dataset_license', after_end_only=True)
        request = dict(input_domain='kinect_3d', schema_id='kinect25-v1', coordinate_space='kinect_camera_3d',
                       feature_version='feature', exercise_id='shoulder_abduction', side='left',
                       camera_view='kinect_recording_only', protocol_version='irds-rep-label-1')
        sequence = ShadowSequence(card, lambda values: sum(values), research_mode=True)
        sequence.begin('a', 0)
        sequence.append('a', 0, 1, 9)
        sequence.begin('b', 0)
        self.assertFalse(sequence.append('a', 0, 2, 10))
        sequence.append('b', 0, 1, 2)
        self.assertEqual(sequence.finish('b', 0, request)['output'], 2)
        sequence.research_mode = False
        self.assertEqual(sequence.finish('b', 0, request)['status'], 'offline_research_only')


class ModelSafetyTests(unittest.TestCase):
    def test_C12_tcn_all_prefixes_and_perturbed_future_are_causal(self):
        import torch
        from tools.rehab_ml.models import CausalTCN
        torch.manual_seed(20261011)
        torch.set_num_threads(2)
        model = CausalTCN(8).eval()
        inputs = torch.randn(1, 70, 8)
        with torch.inference_mode():
            full = model.encode(inputs)
            for end in range(1, 71):
                prefix = model.encode(inputs[:, :end])
                torch.testing.assert_close(prefix, full[:, :end], atol=3e-6, rtol=1e-5)
            other = inputs.clone()
            other[:, 35:] += 100
            torch.testing.assert_close(model.encode(other)[:, :35], full[:, :35], atol=3e-6, rtol=1e-5)
        self.assertEqual(model.receptive_field_steps, 61)

    def test_C22_unlabeled_loss_is_zero_and_has_no_gradient(self):
        import torch
        from tools.rehab_ml.models import masked_cross_entropy
        logits = torch.tensor([[1., 2.], [3., 4.]], requires_grad=True)
        loss = masked_cross_entropy(logits, torch.tensor([0, 1]), torch.tensor([False, False]))
        loss.backward()
        self.assertEqual(float(loss.detach()), 0.)
        self.assertEqual(float(logits.grad.abs().sum()), 0.)
        self.assertAlmostEqual(float(masked_cross_entropy(logits, torch.tensor([0, 1]), torch.tensor([True, False])).detach()),
                               float(torch.nn.functional.cross_entropy(logits[:1], torch.tensor([0])).detach()))


if __name__ == '__main__':
    unittest.main()
