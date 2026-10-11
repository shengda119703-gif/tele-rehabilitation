"""TEST official metadata contracts, not evidence of real dataset access."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.rehab_ml.common import canonical_hash, file_hash, write_json
from tools.rehab_ml.dataverse import BASE, PIDS, inspect_published, load_verified_audit, metadata_file_specs


def fixture():
    return dict(status='OK', data=dict(id=2, datasetId=1,
        datasetPersistentId=PIDS['sumedipose'], versionState='RELEASED',
        versionNumber=1, versionMinorNumber=0, releaseTime='2024-10-27T00:00:00Z',
        license=dict(name='CC BY-NC-SA 4.0', uri='http://creativecommons.org/licenses/by-nc-sa/4.0'),
        files=[dict(label='TEST.json', restricted=False, dataFile=dict(id=10,
            filename='TEST.json', filesize=20, checksum=dict(type='MD5', value='a'*32),
            fileAccessRequest=True, tabularData=False))]))


class DataverseMetadataTests(unittest.TestCase):
    def inspect(self, latest=None, pinned=None, root=None):
        self.urls = []
        values = [root or dict(status='OK', data=dict(id=1, guestbookId=0,
                      latestVersion=dict(versionState='DRAFT'))),
                  latest if latest is not None else fixture(),
                  pinned if pinned is not None else deepcopy(latest) if latest is not None else fixture()]
        def get(url):
            self.urls.append(url)
            return values.pop(0)
        return inspect_published('sumedipose', get)

    def test_latest_draft_never_selected_and_numeric_version_pinned(self):
        result = self.inspect()
        self.assertIn('/versions/:latest-published?', self.urls[1])
        self.assertIn('/versions/1.0?', self.urls[2])
        self.assertEqual(result['published']['version'], '1.0')
        self.assertEqual(result['metadata_status'], 'published_version_pinned')
        self.assertEqual(result['file_count'], 1)
        self.assertEqual(result['total_file_bytes'], 20)
        self.assertFalse(result['download_authorized'])
        self.assertFalse(result['training_authorized'])
        self.assertFalse(result['product_enabled'])

    def test_nc_sa_is_explicit_eligibility_block_not_unverified(self):
        result = self.inspect()
        self.assertEqual(result['license_status'], 'verified_nc_sa_metadata_requires_eligibility')
        self.assertEqual(result['resolved_status'], 'blocked_requires_eligibility_confirmation')

    def test_supported_access_requests_not_mistaken_for_restricted(self):
        result = self.inspect()
        item = result['published']['files'][0]
        self.assertEqual(item['access_status'], 'unrestricted_metadata')
        self.assertEqual(item['access_url'], BASE+'/access/datafile/10')
        self.assertTrue(item['access_request_supported'])

    def test_draft_or_deaccessioned_version_rejected(self):
        for state in ('DRAFT', 'DEACCESSIONED'):
            value = fixture()
            value['data']['versionState'] = state
            with self.subTest(state=state), self.assertRaises(ValueError):
                self.inspect(value)

    def test_different_dataset_or_registry_identity_rejected(self):
        value = fixture()
        value['data']['datasetPersistentId'] = PIDS['mobiphysio']
        with self.assertRaises(ValueError):
            self.inspect(value)
        with self.assertRaises(ValueError):
            self.inspect(root=dict(status='OK', data=dict(id=99)))

    def test_changed_pinned_file_or_terms_rejected(self):
        for field in ('checksum', 'terms'):
            changed = fixture()
            if field == 'checksum':
                changed['data']['files'][0]['dataFile']['checksum']['value'] = 'b'*32
            else:
                changed['data']['termsOfUse'] = 'Changed official terms'
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.inspect(pinned=changed)

    def test_missing_restricted_flag_is_unknown_not_unrestricted(self):
        value = fixture()
        del value['data']['files'][0]['restricted']
        result = self.inspect(value)
        self.assertEqual(result['file_access_counts']['unknown'], 1)
        self.assertFalse(result['download_authorized'])

    def test_guestbook_and_embargo_are_recorded_without_post(self):
        value = fixture()
        value['data']['files'][0]['embargo'] = dict(dateAvailable='2099-01-01')
        result = self.inspect(value, root=dict(status='OK', data=dict(id=1, guestbookId=12)))
        self.assertEqual(result['guestbook_status'], 'configured')
        self.assertEqual(result['file_access_counts']['embargoed'], 1)
        self.assertEqual(len(self.urls), 3)

    def test_duplicate_missing_empty_or_invalid_file_metadata_rejected(self):
        variants = []
        value = fixture(); value['data']['files'] *= 2; variants.append(value)
        value = fixture(); value['data']['files'] = []; variants.append(value)
        value = fixture(); value['data']['files'][0]['dataFile']['checksum'] = {}; variants.append(value)
        value = fixture(); value['data']['files'][0]['dataFile']['filesize'] = True; variants.append(value)
        for value in variants:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.inspect(value)

    def test_other_or_missing_license_does_not_authorize_usage(self):
        for license_value in (None, dict(name='CC BY 4.0', uri='https://creativecommons.org/licenses/by/4.0/')):
            value = fixture(); value['data']['license'] = license_value
            result = self.inspect(value)
            self.assertEqual(result['resolved_status'], 'blocked_license_and_task_review')
            self.assertFalse(result['training_authorized'])

    def test_envelope_or_version_types_refused(self):
        with self.assertRaises(ValueError):
            self.inspect(root=dict(status='ERROR', message='not public'))
        value = fixture(); value['data']['versionNumber'] = '1'
        with self.assertRaises(ValueError):
            self.inspect(value)

    def cc0_audit(self):
        value = fixture()
        value['data']['license'] = dict(name='CC0 1.0', uri='http://creativecommons.org/publicdomain/zero/1.0')
        result = self.inspect(value)
        result['dataset'] = 'mobiphysio'
        result['published']['persistent_id'] = PIDS['mobiphysio']
        result['published_inventory_sha256'] = canonical_hash(result['published'])
        return result

    def test_cc0_small_documentation_uses_pinned_real_id_not_arbitrary_url(self):
        result = self.cc0_audit()
        self.assertEqual(metadata_file_specs(result, [10])[0]['url'], BASE+'/access/datafile/10')
        self.assertFalse(result['training_authorized'])
        with self.assertRaises(ValueError):
            metadata_file_specs(result, [11])

    def test_cc0_metadata_is_not_general_video_download_or_training_permission(self):
        result = self.cc0_audit()
        self.assertEqual(result['license_status'], 'verified_cc0_metadata_pending_access_and_task_review')
        self.assertEqual(result['resolved_status'], 'blocked_access_and_task_review')
        self.assertFalse(result['download_authorized'])
        self.assertFalse(result['training_authorized'])

    def retained_audit(self, run_root):
        root = run_root / 'dataverse-mobiphysio-12345678'
        root.mkdir()
        value = fixture()
        value['data']['datasetPersistentId'] = PIDS['mobiphysio']
        values = [dict(status='OK', data=dict(id=1)), value, deepcopy(value)]
        result = inspect_published('mobiphysio', lambda url: values.pop(0))
        snapshot = root / 'response-03.json'
        write_json(snapshot, value)
        result['requests'] = [dict(url=BASE+'/datasets/:persistentId/versions/1.0?persistentId=TEST',
                                   snapshot=str(snapshot), snapshot_sha256=file_hash(snapshot))]
        write_json(root / 'summary.json', result)
        return root, result, snapshot

    def test_retained_numeric_snapshot_is_rechecked_before_fetch(self):
        with tempfile.TemporaryDirectory() as temporary:
            run_root = Path(temporary).resolve()
            root, result, snapshot = self.retained_audit(run_root)
            with patch('tools.rehab_ml.dataverse.paths', return_value={'run': run_root}):
                self.assertEqual(load_verified_audit(root)[1]['published'], result['published'])
                write_json(snapshot, dict(status='ERROR'))
                with self.assertRaises(ValueError):
                    load_verified_audit(root)

    def test_modified_summary_cannot_replace_official_numeric_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            run_root = Path(temporary).resolve()
            root, result, _ = self.retained_audit(run_root)
            result['published']['files'][0]['bytes'] += 1
            result['published_inventory_sha256'] = canonical_hash(result['published'])
            write_json(root / 'summary.json', result)
            with patch('tools.rehab_ml.dataverse.paths', return_value={'run': run_root}):
                with self.assertRaises(ValueError):
                    load_verified_audit(root)

    def test_snapshot_outside_owned_run_is_refused_even_with_matching_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            run_root = Path(temporary).resolve()
            root, result, snapshot = self.retained_audit(run_root)
            outside = run_root / 'not-owned.json'
            write_json(outside, dict(status='OK'))
            result['requests'][0].update(snapshot=str(outside), snapshot_sha256=file_hash(outside))
            write_json(root / 'summary.json', result)
            with patch('tools.rehab_ml.dataverse.paths', return_value={'run': run_root}):
                with self.assertRaises(ValueError):
                    load_verified_audit(root)

    def test_documentation_fetch_refuses_other_license_terms_and_guestbook(self):
        for kind in ('license', 'terms', 'guestbook'):
            result = self.cc0_audit()
            if kind == 'license':
                result['published']['license']['uri'] = 'http://creativecommons.org/licenses/by-nc-sa/4.0'
            elif kind == 'terms':
                result['published']['terms']['termsOfUse'] = 'Requires approval'
            else:
                result['guestbook_id'] = 1
            result['published_inventory_sha256'] = canonical_hash(result['published'])
            with self.subTest(kind=kind), self.assertRaises(PermissionError):
                metadata_file_specs(result, [10])

    def test_documentation_fetch_refuses_rgb_and_oversized_or_unsafe_files(self):
        for name, size in (('clip.mp4', 20), ('TEST.json', 3*1024*1024), ('../TEST.json', 20), ('CON.txt', 20)):
            result = self.cc0_audit()
            result['published']['files'][0].update(filename=name, bytes=size)
            result['published_inventory_sha256'] = canonical_hash(result['published'])
            with self.subTest(name=name, size=size), self.assertRaises(ValueError):
                metadata_file_specs(result, [10])

    def test_documentation_fetch_refuses_missing_access_or_tabular_conversion(self):
        for field, value in (('restricted', True), ('tabular_data', True), ('access_status', 'unknown')):
            result = self.cc0_audit()
            result['published']['files'][0][field] = value
            result['published_inventory_sha256'] = canonical_hash(result['published'])
            with self.subTest(field=field), self.assertRaises(PermissionError):
                metadata_file_specs(result, [10])

    def test_documentation_fetch_refuses_modified_inventory_or_duplicate_selection(self):
        result = self.cc0_audit()
        result['published']['files'][0]['bytes'] += 1
        with self.assertRaises(ValueError):
            metadata_file_specs(result, [10])
        with self.assertRaises(ValueError):
            metadata_file_specs(self.cc0_audit(), [10, 10])


if __name__ == '__main__':
    unittest.main()
