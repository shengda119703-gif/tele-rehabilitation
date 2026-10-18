"""Synthetic contract TEST fixtures; these are never genuine human references."""
from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.rehab_ml.synthetic import contracts as c


def sample(key='p0', *, group=None, split='train', stage='pilot', scenario='A'):
    digest = lambda suffix: hashlib.sha256((key+suffix).encode()).hexdigest()
    group = group or 'group-'+key
    return dict(sample_id=key, source_group_id=group, reference_group_id='ref-'+group,
        lineage_ids=['motion-'+group], split=split, stage=stage, scenario=scenario,
        exercise_id='shoulder_abduction', side='left', view='frontal', status='pending',
        video=dict(path=key+'.mp4', sha256=digest('video'), width=640, height=384,
                   frame_count=9, timeline_path=key+'-pts.json', timeline_sha256=digest('pts')),
        generation=dict(prompt_version='TEST-v1', seed=1, model_sha256=digest('model'),
                        workflow_sha256=digest('workflow'), prompt_sha256=digest('prompt')))


def timeline(row):
    return dict(schema_version=c.SCHEMA_VERSION, video_sha256=row['video']['sha256'],
        frame_count=9, width=640, height=384, time_basis='stream_relative_media_pts',
        presentation_s=[x*.125 for x in range(9)],
        provenance=dict(origin='decoded_video', decoder='TEST-decode-fixture',
                        video_stream_index=0, stream_start_time_s=0.))


def acceptance(row):
    return dict(reviewer_id='TEST-human-placeholder', reviewer_role='human_operator',
                full_video_watched=True, reviewed_video_sha256=row['video']['sha256'],
                reviewed_frame_count=row['video']['frame_count'], watched_at='TEST-ONLY')


def accepted(row):
    row = copy.deepcopy(row)
    row.update(status='accepted', acceptance=acceptance(row))
    return row


def manifest(rows, frozen=None):
    return dict(schema_version=c.SCHEMA_VERSION, dataset_id='TEST-fixture-not-real-data',
                split_freeze=frozen, samples=rows)


def known_zero(row):
    result = c.prepare_review(row, timeline(row), reviewer_id='TEST-human-placeholder')
    result.update(review={k: v for k, v in acceptance(row).items()
                          if k not in ('reviewer_id', 'reviewer_role')},
                  side='left', side_mask=True, observable_count=0, observable_count_mask=True)
    return result


class SyntheticContractTests(unittest.TestCase):
    def rejects(self, reason, function, *args, **kwargs):
        with self.assertRaisesRegex(c.SyntheticContractError, reason):
            function(*args, **kwargs)

    def test_empty_pilot_inventory_and_pending_source_are_allowed(self):
        self.assertEqual(c.validate_manifest(manifest([]))['sample_count'], 0)
        self.assertEqual(c.validate_manifest(manifest([sample()]))['pending_sample_ids'], ['p0'])

    def test_template_does_not_claim_review_count_phase_or_training_eligibility(self):
        row = sample()
        form = c.prepare_review(row, timeline(row))
        self.assertIsNone(form['observable_count'])
        self.assertFalse(form['observable_count_mask'])
        self.assertEqual(form['phase_intervals'], [])
        self.assertFalse(form['review']['full_video_watched'])
        self.assertFalse(c.validate_annotation(form, row, timeline(row))['eligible_for_training'])

    def test_explicit_zero_after_full_review_is_valid_but_empty_unknown_is_not_zero(self):
        row = accepted(sample())
        zero = known_zero(row)
        self.assertTrue(c.validate_annotation(zero, row, timeline(row))['eligible_for_training'])
        zero['observable_count_mask'] = False
        self.rejects('unknown_must_be_null', c.validate_annotation, zero, row, timeline(row))

    def test_ai_draft_can_be_saved_but_is_never_eligible(self):
        row = accepted(sample())
        draft = known_zero(row)
        draft['reviewer_role'] = 'ai_draft'
        self.assertIn('ai_draft_not_human_reference', c.validate_annotation(draft, row, timeline(row))['reasons'])
        self.assertEqual(c.load_eligible_annotations([draft], manifest([row]), {'p0': timeline(row)}), [])

    def test_pending_or_unwatched_source_cannot_be_eligible(self):
        row = sample()
        form = known_zero(row)
        self.assertFalse(c.validate_annotation(form, row, timeline(row))['eligible_for_training'])
        row = accepted(row)
        form['review']['full_video_watched'] = False
        self.assertFalse(c.validate_annotation(form, row, timeline(row))['eligible_for_training'])

    def test_bilateral_fact_can_be_saved_but_is_not_single_side_training_reference(self):
        row = accepted(sample())
        form = known_zero(row)
        form['side'] = 'bilateral'
        result = c.validate_annotation(form, row, timeline(row))
        self.assertFalse(result['eligible_for_training'])
        self.assertIn('require_side_specific_temporal_reference', result['reasons'])
        self.assertEqual(c.load_eligible_annotations([form], manifest([row]), {'p0': timeline(row)}), [])

    def test_human_acceptance_requires_full_original_video(self):
        row = accepted(sample())
        row['acceptance']['reviewed_frame_count'] -= 1
        self.rejects('complete_review', c.validate_manifest, manifest([row]))
        row['acceptance'] = acceptance(row)
        row['acceptance']['reviewer_role'] = 'ai_draft'
        self.rejects('requires_human', c.validate_manifest, manifest([row]))

    def test_review_hash_and_missing_human_identity_are_not_accepted(self):
        row = accepted(sample())
        form = known_zero(row)
        form['review']['reviewed_video_sha256'] = 'b'*64
        self.rejects('complete_review', c.validate_annotation, form, row, timeline(row))
        form = known_zero(row)
        form['reviewer_id'] = None
        self.assertFalse(c.validate_annotation(form, row, timeline(row))['eligible_for_training'])

    def test_raw_hash_and_complete_pts_index_are_mandatory(self):
        for key in ('sha256', 'timeline_path', 'timeline_sha256', 'frame_count'):
            row = sample()
            row['video'].pop(key)
            self.rejects('original_video', c.validate_manifest, manifest([row]))

    def test_generation_hashes_and_versions_are_mandatory(self):
        for key in ('prompt_version', 'seed', 'model_sha256', 'workflow_sha256', 'prompt_sha256'):
            row = sample()
            row['generation'].pop(key)
            self.rejects('generation_versions', c.validate_manifest, manifest([row]))

    def test_timeline_rejects_reconstructed_missing_duplicate_or_mismatched_pts(self):
        row = sample()
        edits = [('time_basis', 'fps_reconstruction'), ('frame_count', 8),
                 ('video_sha256', 'b'*64), ('presentation_s', [0.]*9),
                 ('presentation_s', [0., .5]), ('presentation_s', [float('nan')]*9)]
        for key, value in edits:
            times = timeline(row)
            times[key] = value
            with self.subTest(key=key, value=value):
                self.assertRaises(c.SyntheticContractError, c.validate_timeline, times, row)

    def test_unknown_source_and_duplicate_ids_rejected(self):
        row = sample()
        self.rejects('duplicate_sample', c.validate_manifest, manifest([row, copy.deepcopy(row)]))
        form = known_zero(accepted(row))
        form['sample_id'] = 'unknown'
        self.rejects('unknown_or_duplicate', c.load_eligible_annotations, [form], manifest([row]), {'p0': timeline(row)})

    def test_pilot_direct_validation_or_test_split_rejected(self):
        for split in ('val', 'test'):
            self.rejects('pilot_sources_train_only', c.validate_manifest, manifest([sample(split=split)]))

    def frozen(self):
        return c.freeze_splits({f'g{i}': ('train' if i < 6 else 'val' if i < 8 else 'test') for i in range(10)})

    def test_split_freeze_requires_ten_groups_and_6_2_2_and_detects_edits(self):
        self.rejects('ten_groups', c.freeze_splits, {'g0': 'train'})
        frozen = self.frozen()
        frozen['formal_group_splits']['g0'] = 'test'
        self.assertRaises(c.SyntheticContractError, c.validate_manifest, manifest([], frozen))
        frozen = self.frozen()
        frozen['frozen'] = False
        self.rejects('not_frozen', c.validate_manifest, manifest([], frozen))

    def test_formal_sample_must_match_pre_frozen_group(self):
        row = sample(stage='formal', group='g8', split='train')
        self.rejects('frozen_split', c.validate_manifest, manifest([row], self.frozen()))

    def test_transitive_lineage_leakage_is_rejected(self):
        a = sample('a')
        b = sample('b')
        d = sample('d', stage='formal', group='g8', split='test')
        a['lineage_ids'] = ['shared-motion-a']
        b['lineage_ids'] = ['shared-motion-a', 'shared-motion-b']
        d['lineage_ids'] = ['shared-motion-b']
        self.rejects('transitive_source_leakage', c.validate_manifest, manifest([a, b, d], self.frozen()))

    def test_shared_reference_or_raw_hash_joins_even_with_new_names(self):
        for field in ('reference', 'hash', 'derived_sample'):
            a, b = sample('a'), sample('b', group='g8', split='test', stage='formal')
            if field == 'reference':
                b['reference_group_id'] = a['reference_group_id']
            elif field == 'hash':
                b['video']['sha256'] = a['video']['sha256']
            else:
                b['lineage_ids'] = [a['sample_id']]
            with self.subTest(field=field):
                self.rejects('transitive_source_leakage', c.validate_manifest, manifest([a, b], self.frozen()))

    def test_ten_claimed_groups_must_really_be_independent(self):
        a = sample('a', group='g0', stage='formal')
        b = sample('b', group='g1', stage='formal')
        b['reference_group_id'] = a['reference_group_id']
        self.rejects('not_independent', c.validate_manifest, manifest([a, b], self.frozen()))

    def test_same_raw_video_renamed_cannot_inflate_source_count(self):
        a, b = sample('a'), sample('b')
        b['video']['sha256'] = a['video']['sha256']
        self.rejects('duplicate_raw_video', c.validate_manifest, manifest([a, b]))

    def formal_rows(self, *, approve=True):
        rows = []
        for group, split in self.frozen()['formal_group_splits'].items():
            for scenario in c.SCENARIOS:
                row = sample(group+scenario, group=group, split=split, stage='formal', scenario=scenario)
                rows.append(accepted(row) if approve else row)
        return rows

    def test_formal_complete_means_60_human_accepted_36_12_12_and_all_scenarios(self):
        value = manifest(self.formal_rows(), self.frozen())
        summary = c.validate_manifest(value, require_formal_complete=True)
        self.assertEqual(summary['accepted_formal_splits'], dict(train=36, val=12, test=12))
        self.rejects('sixty_human_accepted', c.validate_manifest,
                     manifest(self.formal_rows(approve=False), self.frozen()), require_formal_complete=True)
        value['samples'][0]['scenario'] = 'B'
        self.rejects('sixty_human_accepted', c.validate_manifest, value, require_formal_complete=True)

    def test_masked_phase_requires_real_pts_and_nonoverlap(self):
        row = accepted(sample())
        form = known_zero(row)
        form['phase_intervals'] = [dict(phase='outbound', start_s=.125, end_s=.5, label_mask=True)]
        self.assertTrue(c.validate_annotation(form, row, timeline(row))['eligible_for_training'])
        form['phase_intervals'][0]['start_s'] = .1
        self.rejects('phase_start_known', c.validate_annotation, form, row, timeline(row))
        form['phase_intervals'] = [dict(phase='outbound', start_s=.125, end_s=.5, label_mask=True),
                                   dict(phase='return', start_s=.25, end_s=.75, label_mask=True)]
        self.rejects('nonoverlapping', c.validate_annotation, form, row, timeline(row))

    def test_unknown_phase_remains_null_and_does_not_become_rest(self):
        row = accepted(sample())
        form = known_zero(row)
        form['phase_intervals'] = [dict(phase='outbound', start_s=None, end_s=None, label_mask=False)]
        self.assertTrue(c.validate_annotation(form, row, timeline(row))['eligible_for_training'])
        form['phase_intervals'][0]['start_s'] = 0.
        self.rejects('unknown_must_be_null', c.validate_annotation, form, row, timeline(row))

    def test_unknown_completion_inventory_cannot_set_count_to_zero(self):
        row = accepted(sample())
        form = known_zero(row)
        form['repetitions'] = [c.repetition_template('rep1')]
        self.rejects('unknown_completion_inventory', c.validate_annotation, form, row, timeline(row))

    def test_complete_shoulder_rep_requires_roundtrip_and_count_consistency(self):
        row = accepted(sample())
        form = known_zero(row)
        rep = c.repetition_template('rep1')
        rep.update(observable_completion=True, observable_completion_mask=True)
        form['repetitions'] = [rep]
        form['observable_count'] = 1
        self.rejects('roundtrip_requires_all', c.validate_annotation, form, row, timeline(row))
        rep['boundaries'] = dict(zip(c.PHASES, [0., .125, .375, .625, 1.]))
        rep['boundary_masks'] = dict.fromkeys(c.PHASES, True)
        self.assertTrue(c.validate_annotation(form, row, timeline(row))['eligible_for_training'])
        form['observable_count'] = 0
        self.rejects('count_must_match', c.validate_annotation, form, row, timeline(row))

    def quality(self, **changes):
        row = dict(problem_id='TEST-trunk', kind='clinical_quality', state='unknown',
                   label_mask=False, assessable=None, assessability_mask=False,
                   start_s=None, end_s=None, professional_review=None)
        row.update(changes)
        return row

    def test_clinical_quality_without_qualified_review_must_remain_unknown(self):
        row = accepted(sample())
        form = known_zero(row)
        form['quality'] = [self.quality()]
        self.assertTrue(c.validate_annotation(form, row, timeline(row))['eligible_for_training'])
        form['quality'] = [self.quality(state='present', label_mask=True, assessable=True,
                                      assessability_mask=True, start_s=0., end_s=1.)]
        self.rejects('qualified_review', c.validate_annotation, form, row, timeline(row))
        form['quality'][0]['kind'] = 'observable_change'
        self.assertTrue(c.validate_annotation(form, row, timeline(row))['eligible_for_training'])

    def test_absent_requires_assessable_and_unknown_cannot_be_negative(self):
        row = accepted(sample())
        form = known_zero(row)
        form['quality'] = [self.quality(kind='observable_change', state='absent')]
        self.rejects('remain_unknown', c.validate_annotation, form, row, timeline(row))
        form['quality'][0].update(label_mask=True, start_s=0., end_s=1.)
        self.rejects('requires_assessable', c.validate_annotation, form, row, timeline(row))

    def test_load_manifest_verifies_both_files_and_never_trusts_path_alone(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            row = sample()
            (root/'p0.mp4').write_bytes(b'TEST-not-a-real-video-file')
            row['video']['sha256'] = hashlib.sha256((root/'p0.mp4').read_bytes()).hexdigest()
            (root/'p0-pts.json').write_text(json.dumps(timeline(row)), encoding='utf-8')
            row['video']['timeline_sha256'] = hashlib.sha256((root/'p0-pts.json').read_bytes()).hexdigest()
            path = root/'manifest.json'
            path.write_text(json.dumps(manifest([row])), encoding='utf-8')
            with patch('tools.rehab_ml.synthetic.video.probe_video', return_value=timeline(row)):
                self.assertEqual(c.load_manifest(path)['samples'][0]['sample_id'], 'p0')
            (root/'p0.mp4').write_bytes(b'changed')
            self.rejects('hash_mismatch', c.load_manifest, path)

    def test_verified_load_rejects_forged_self_consistent_pts_without_real_video(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            row = sample()
            (root/'p0.mp4').write_bytes(b'TEST-invalid-mp4')
            row['video']['sha256'] = hashlib.sha256((root/'p0.mp4').read_bytes()).hexdigest()
            (root/'p0-pts.json').write_text(json.dumps(timeline(row)), encoding='utf-8')
            row['video']['timeline_sha256'] = hashlib.sha256((root/'p0-pts.json').read_bytes()).hexdigest()
            path = root/'manifest.json'
            path.write_text(json.dumps(manifest([row])), encoding='utf-8')
            self.assertRaises(c.SyntheticContractError, c.load_manifest, path)

    def test_full_loader_accepts_actual_small_video_and_rejects_pts_forgery(self):
        import av
        import numpy as np
        from tools.rehab_ml.synthetic.video import probe_video
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root/'p0.mp4'
            with av.open(str(path), mode='w') as container:
                stream = container.add_stream('libx264', rate=8)
                stream.width, stream.height, stream.pix_fmt = 640, 384, 'yuv420p'
                for i in range(9):
                    frame = av.VideoFrame.from_ndarray(np.full((384, 640, 3), i*20, dtype=np.uint8), format='rgb24')
                    for packet in stream.encode(frame):
                        container.mux(packet)
                for packet in stream.encode():
                    container.mux(packet)
            row = sample()
            actual = probe_video(path, timeline_path=root/'p0-pts.json')
            row['video'].update(sha256=actual['video_sha256'], timeline_sha256=actual['timeline_sha256'])
            document = root/'manifest.json'
            document.write_text(json.dumps(manifest([row])), encoding='utf-8')
            self.assertEqual(c.load_manifest(document)['samples'][0]['sample_id'], 'p0')
            pts = json.loads((root/'p0-pts.json').read_text(encoding='utf-8'))
            pts['presentation_s'][1] += .001
            (root/'p0-pts.json').write_text(json.dumps(pts), encoding='utf-8')
            row['video']['timeline_sha256'] = hashlib.sha256((root/'p0-pts.json').read_bytes()).hexdigest()
            document.write_text(json.dumps(manifest([row])), encoding='utf-8')
            self.rejects('disagrees_with_actual_decode', c.load_manifest, document)

    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'manifest.json'
            path.write_text('{"samples":[],"samples":[]}', encoding='utf-8')
            self.rejects('duplicate_json_key', c.load_manifest, path)


if __name__ == '__main__':
    unittest.main()
