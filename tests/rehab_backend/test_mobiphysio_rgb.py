"""TEST fixed cohort/split gates, not downloaded video or medical accuracy."""
from copy import deepcopy
import unittest

from tools.rehab_ml.common import canonical_hash
from tools.rehab_ml.mobiphysio_rgb import MAX_BYTES, select_cohort


def fixture(n=24):
    groups, files = [], []
    for i in range(1, n+1):
        name = f'E01_P{i:02}_AF_VFL_GM'
        checksum = dict(algorithm='md5', value='a'*32)
        files.append(dict(file_id=i, filename=name+'.mp4', bytes=100,
                          checksum=checksum, restricted=False, embargo=None,
                          access_status='unrestricted_metadata', tabular_data=False))
        groups.append(dict(status='verified_video_score', exercise='E01', camera_view='front',
                           variation='FL', video_name=name, subject_id=f'P{i:02}', file_id=i,
                           video_checksum=checksum, video_bytes=100, published_average=80.))
    return groups, dict(files=files)


class MobiPhysioRGBTests(unittest.TestCase):
    def test_entire_reviewed_cohort_and_people_split_are_frozen(self):
        samples, splits = select_cohort(*fixture())
        self.assertEqual(len(samples), 24)
        self.assertEqual({name: len(people) for name, people in splits.items()}, dict(train=14, val=5, test=5))
        self.assertFalse(set(splits['train']) & set(splits['val']))
        self.assertFalse(set(splits['train']) & set(splits['test']))
        self.assertFalse(set(splits['val']) & set(splits['test']))
        self.assertTrue(all(row['label']['granularity'] == 'whole_video_eaaq' for row in samples))
        self.assertTrue(all(row['affected_side'] is None for row in samples))

    def test_reordered_input_does_not_change_selection_or_split_hash(self):
        groups, published = fixture()
        first = select_cohort(groups, published)
        self.assertEqual(canonical_hash(first), canonical_hash(select_cohort(groups[::-1], published)))

    def test_scores_are_not_used_to_choose_people_or_split(self):
        groups, published = fixture()
        _, initial = select_cohort(groups, published)
        for i, group in enumerate(groups): group['published_average'] = float(i)
        self.assertEqual(select_cohort(groups, published)[1], initial)

    def test_quarantine_or_other_action_view_variation_not_selected(self):
        groups, published = fixture()
        added = deepcopy(groups[0]); added.update(status='quarantined', published_average=0.)
        groups += [added, dict(status='verified_video_score', exercise='E08', camera_view='front', variation='FL'),
                   dict(status='verified_video_score', exercise='E01', camera_view='left_view', variation='FL'),
                   dict(status='verified_video_score', exercise='E01', camera_view='front', variation='LL')]
        self.assertEqual(len(select_cohort(groups, published)[0]), 24)

    def test_duplicate_person_is_not_silently_deduplicated(self):
        groups, published = fixture(); groups.append(deepcopy(groups[0]))
        with self.assertRaises(ValueError): select_cohort(groups, published)

    def test_identity_or_inventory_changes_refused(self):
        for kind in ('name', 'person', 'checksum', 'size', 'id'):
            groups, published = fixture()
            if kind == 'name': groups[0]['video_name'] = 'E01_P01_AL_VFL_GM'
            elif kind == 'person': groups[0]['subject_id'] = 'P09'
            elif kind == 'checksum': groups[0]['video_checksum'] = dict(algorithm='md5', value='b'*32)
            elif kind == 'size': groups[0]['video_bytes'] += 1
            else: groups[0]['file_id'] = 99
            with self.subTest(kind=kind), self.assertRaises(ValueError): select_cohort(groups, published)

    def test_access_restrictions_never_become_rgb_permission(self):
        for key, value in (('restricted', True), ('restricted', None), ('embargo', {'date': '2099'}),
                           ('tabular_data', True), ('access_status', 'unknown')):
            groups, published = fixture(); published['files'][0][key] = value
            with self.subTest(key=key), self.assertRaises(PermissionError): select_cohort(groups, published)

    def test_per_file_and_total_size_budgets_do_not_silently_shrink_scope(self):
        groups, published = fixture()
        groups[0]['video_bytes'] = published['files'][0]['bytes'] = 150_000_001
        with self.assertRaises(ValueError): select_cohort(groups, published)
        groups, published = fixture()
        for group, item in zip(groups, published['files']): group['video_bytes'] = item['bytes'] = MAX_BYTES // 20
        with self.assertRaises(ValueError): select_cohort(groups, published)

    def test_small_cohort_or_invalid_seed_is_refused(self):
        with self.assertRaises(ValueError): select_cohort(*fixture(9))
        for seed in (True, -1, '20261011', 2**32):
            with self.subTest(seed=seed), self.assertRaises(ValueError): select_cohort(*fixture(), seed=seed)


if __name__ == '__main__':
    unittest.main()
