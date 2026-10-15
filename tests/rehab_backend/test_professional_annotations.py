"""TEST-only hand-authored records; no professional or patient truth claims."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.rehab_ml.common import canonical_hash, file_hash, write_json
from tools.rehab_ml import professional_annotations as p


class ProfessionalAnnotations(unittest.TestCase):
    def setUp(self):
        self.sample = dict(sample_id='TEST-sample-1', exercise_id='shoulder_abduction',
                           duration_s=5., video_sha256='a'*64, split='train')
        self.times = [float(i) for i in range(6)]

    def completed(self, role='A', person='TEST-A'):
        row = p.record_template(self.sample, role)
        row['side'] = 'left'
        row['annotation'].update(annotator=person, annotation_version='TEST-1',
                                 independently_performed=True, video_reviewed=True,
                                 inventory_complete=True, status='completed')
        rep = p.repetition_template()
        rep['rep_id'] = 'TEST-rep-1'
        rep['boundaries'] = dict(zip(p.BOUNDARIES, self.times))
        rep['label_masks']['phase'] = {key: True for key in p.BOUNDARIES}
        rep['observable_completion'] = True
        rep['label_masks']['observable_completion'] = True
        row['repetitions'] = [rep]
        return row

    def quality(self, row):
        problem = dict(problem_id='elbow_flexion', state='unknown', assessable=None,
                       state_mask=False, assessability_mask=False, start_s=1., end_s=2.,
                       acceptable_variation_conditions=None)
        row['repetitions'][0]['quality_problems'] = [problem]
        return problem

    def check(self, row, role='A'):
        return p.validate_record(row, self.sample, self.times, role)

    def test_pending_blank_has_no_supervision(self):
        self.assertEqual(self.check(p.record_template(self.sample)), 0)

    def test_completed_observable_reference(self):
        self.assertEqual(self.check(self.completed()), 7)

    def test_missing_side_cannot_be_inferred_from_view(self):
        row = self.completed()
        row['side'] = None
        with self.assertRaisesRegex(ValueError, 'and_side'):
            self.check(row)

    def test_model_or_rule_origin_rejected(self):
        for origin in ('predicted', 'filtered', 'pseudo', 'llm'):
            row = self.completed()
            row['annotation']['origin'] = origin
            with self.assertRaisesRegex(ValueError, 'human_annotation'):
                self.check(row)

    def test_pending_known_labels_rejected(self):
        row = self.completed()
        row['annotation']['status'] = 'pending'
        with self.assertRaisesRegex(ValueError, 'completed_annotation'):
            self.check(row)

    def test_no_whole_video_claim_without_inventory(self):
        row = self.completed()
        row['annotation']['inventory_complete'] = False
        with self.assertRaisesRegex(ValueError, 'whole_recording'):
            self.check(row)

    def test_masks_are_strict_booleans(self):
        row = self.completed()
        row['repetitions'][0]['label_masks']['observable_completion'] = 1
        with self.assertRaisesRegex(ValueError, 'mask_mismatch'):
            self.check(row)

    def test_null_not_false_completion(self):
        row = self.completed()
        row['repetitions'][0]['physical_completion'] = False
        with self.assertRaisesRegex(ValueError, 'mask_mismatch'):
            self.check(row)

    def test_partial_phase_mask_remains_unknown(self):
        row = self.completed()
        row['repetitions'][0]['observable_completion'] = None
        row['repetitions'][0]['label_masks']['observable_completion'] = False
        row['repetitions'][0]['boundaries']['end_s'] = None
        row['repetitions'][0]['label_masks']['phase']['end_s'] = False
        self.assertEqual(self.check(row), 5)

    def test_hidden_turn_cannot_be_completed(self):
        row = self.completed()
        rep = row['repetitions'][0]
        rep['boundaries']['endpoint_start_s'] = None
        rep['label_masks']['phase']['endpoint_start_s'] = False
        with self.assertRaisesRegex(ValueError, 'visible_lifecycle'):
            self.check(row)

    def test_one_frame_cannot_prove_complete_lifecycle(self):
        row = self.completed()
        row['repetitions'][0]['boundaries'] = {key: 0. for key in p.BOUNDARIES}
        with self.assertRaisesRegex(ValueError, 'distinct_ordered'):
            self.check(row)

    def test_sit_to_stand_needs_no_invented_return(self):
        self.sample['exercise_id'] = 'sit_to_stand'
        row = self.completed()
        for key in ('endpoint_end_s', 'return_start_s', 'end_s'):
            row['repetitions'][0]['boundaries'][key] = None
            row['repetitions'][0]['label_masks']['phase'][key] = False
        self.assertEqual(self.check(row), 4)

    def test_non_frame_negative_nan_and_late_times(self):
        for value in (-1., .5, 6., float('nan'), True):
            row = self.completed()
            row['repetitions'][0]['boundaries']['outbound_start_s'] = value
            with self.assertRaises(ValueError):
                self.check(row)

    def test_order_and_overlap_rejected(self):
        row = self.completed()
        row['repetitions'][0]['boundaries']['endpoint_start_s'] = 0.
        with self.assertRaisesRegex(ValueError, 'out_of_order'):
            self.check(row)
        row = self.completed()
        row['repetitions'].append(copy.deepcopy(row['repetitions'][0]))
        row['repetitions'][-1]['rep_id'] = 'TEST-rep-2'
        with self.assertRaisesRegex(ValueError, 'overlap'):
            self.check(row)

    def test_known_physical_reference_requires_visible_evidence(self):
        row = self.completed()
        rep = row['repetitions'][0]
        rep['physical_completion'] = True
        rep['label_masks']['physical_completion'] = True
        with self.assertRaisesRegex(ValueError, 'physical_reference_required'):
            self.check(row)
        rep['physical_reference'] = dict(kind='same_video_visible', evidence_sha256='a'*64,
                                         alignment_note='TEST same visible lifecycle')
        self.assertEqual(self.check(row), 8)
        rep['observable_completion'] = False
        with self.assertRaisesRegex(ValueError, 'hidden_physical'):
            self.check(row)

    def test_external_physical_view_requires_separate_qualification(self):
        row = self.completed()
        rep = row['repetitions'][0]
        rep.update(physical_completion=True, physical_reference=dict(kind='synchronized_view',
                   evidence_sha256='b'*64, alignment_note='TEST unqualified'))
        rep['label_masks']['physical_completion'] = True
        with self.assertRaisesRegex(ValueError, 'separate_qualification'):
            self.check(row)

    def test_unassessable_is_not_negative(self):
        row = self.completed()
        problem = self.quality(row)
        problem.update(assessable=False, assessability_mask=True)
        self.assertEqual(self.check(row), 8)
        problem['state'] = 'absent'
        with self.assertRaisesRegex(ValueError, 'not_negative'):
            self.check(row)

    def test_quality_negative_requires_reviewed_conditions(self):
        row = self.completed()
        problem = self.quality(row)
        problem.update(state='absent', state_mask=True, assessability_mask=True, assessable=True)
        with self.assertRaisesRegex(ValueError, 'assessable_review'):
            self.check(row)
        problem['acceptable_variation_conditions'] = 'TEST explicitly reviewed interval and conditions'
        self.assertEqual(self.check(row), 9)

    def test_intervention_not_inferred(self):
        row = self.completed()
        cue = dict(start_s=1., end_s=2., category='keep_trunk_stable', priority=40,
                   label_mask=True, actually_received=None, later_improved=None, intervention_evidence=None)
        row['repetitions'][0]['cue_opportunities'] = [cue]
        self.assertEqual(self.check(row), 8)
        cue['later_improved'] = True
        with self.assertRaisesRegex(ValueError, 'separately_qualified'):
            self.check(row)

    def test_source_identity_schema_and_self_approval_rejected(self):
        for mutate in (lambda r: r['source'].update(split='test'),
                       lambda r: r.update(video_score=90),
                       lambda r: r['review'].update(status='approved')):
            row = self.completed()
            mutate(row)
            with self.assertRaises(ValueError):
                self.check(row)

    def test_exact_disagreement_includes_mask(self):
        a, b = self.completed(), self.completed()
        b['repetitions'][0]['label_masks']['physical_completion'] = True
        self.assertEqual(p.differences(p._label_payload(a), p._label_payload(b)),
                         ['/repetitions/0/label_masks/physical_completion'])

    def test_duplicate_json_nonfinite_and_row_budget(self):
        for text in ('{"a":1,"a":2}', '{"a":NaN}'):
            with self.assertRaises(ValueError):
                p._json(text)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'TEST.jsonl'
            path.write_text('{}\n'*65, encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'quota'):
                p.read_rows(path)

    def test_three_actions_keep_same_label_contract(self):
        for exercise in p.EXERCISES:
            self.sample['exercise_id'] = exercise
            self.assertEqual(self.check(self.completed()), 7)

    def make_audit(self, root, *, completed=False):
        timeline = root/'pts.json'
        write_json(timeline, dict(presentation_s=self.times))
        self.sample['timeline_ref'] = timeline.name
        forms = {'A': 'A.jsonl', 'B': 'B.jsonl', 'REVIEW': 'REVIEW.jsonl'}
        rows = {role: (self.completed(role, 'TEST-'+role) if completed else p.record_template(self.sample, role))
                for role in forms}
        if completed:
            rows['REVIEW']['review'].update(status='approved', reviewer_qualification='TEST fixture only',
                final_resolution='TEST same labels', disagreement_paths=[],
                input_digests={role: canonical_hash(rows[role]) for role in ('A', 'B')})
        for role, name in forms.items():
            p._rows_write(root/name, [rows[role]])
        bundle = root/'bundle.json'
        write_json(bundle, dict(samples=[self.sample]))
        return bundle, dict(samples=[self.sample], forms=forms), rows

    def test_all_blank_import_refused_before_output_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path, manifest, _ = self.make_audit(root)
            with patch.object(p, '_bundle', return_value=(path, manifest)):
                self.assertEqual(p.audit_bundle(path)['pending'], 1)
                output = root/'not-created'
                with self.assertRaisesRegex(ValueError, 'blocked_missing'):
                    p.import_reviewed(path, output)
                self.assertFalse(output.exists())

    def test_stale_review_or_same_person_rejected(self):
        for same_person in (False, True):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                path, manifest, rows = self.make_audit(root, completed=True)
                role = 'B'
                if same_person:
                    rows[role]['annotation']['annotator'] = rows['A']['annotation']['annotator']
                    rows['REVIEW']['review']['input_digests'][role] = canonical_hash(rows[role])
                    (root/'REVIEW.jsonl').write_text(json.dumps(rows['REVIEW'])+'\n', encoding='utf-8')
                else:
                    rows[role]['annotation']['annotation_version'] = 'TEST-2'
                (root/'B.jsonl').write_text(json.dumps(rows[role])+'\n', encoding='utf-8')
                with patch.object(p, '_bundle', return_value=(path, manifest)):
                    with self.assertRaisesRegex(ValueError, 'bound_professional'):
                        p.audit_bundle(path)

    def test_qualified_TEST_fixture_import_and_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path, manifest, _ = self.make_audit(root, completed=True)
            with patch.object(p, '_bundle', return_value=(path, manifest)), \
                    patch.object(p, 'paths', return_value={'run': root}):
                result = p.import_reviewed(path, root/'TEST-import')
            reference = json.loads(Path(result['artifact']).read_text(encoding='utf-8'))
            self.assertEqual(reference['cohort'][0]['sample_id'], 'TEST-sample-1')
            self.assertFalse(reference['product_enabled'])
            self.assertFalse(reference['pose_supervision'])
            self.assertEqual(file_hash(result['artifact']), result['reference_sha256'])

    def test_cohort_missing_row_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path, manifest, _ = self.make_audit(root)
            (root/'B.jsonl').write_text('{"sample_id":"wrong"}\n', encoding='utf-8')
            with patch.object(p, '_bundle', return_value=(path, manifest)):
                with self.assertRaisesRegex(ValueError, 'frozen_cohort'):
                    p.audit_bundle(path)

    def test_partial_import_retains_pending_cohort_not_negative_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path, manifest, rows = self.make_audit(root, completed=True)
            pending = dict(self.sample, sample_id='TEST-sample-2', split='val')
            manifest['samples'].append(pending)
            write_json(path, dict(samples=manifest['samples']))
            for role, name in manifest['forms'].items():
                text = '\n'.join(json.dumps(row) for row in (rows[role], p.record_template(pending, role)))+'\n'
                (root/name).write_text(text, encoding='utf-8')
            with patch.object(p, '_bundle', return_value=(path, manifest)), \
                    patch.object(p, 'paths', return_value={'run': root}):
                result = p.import_reviewed(path, root/'TEST-partial')
            reference = json.loads(Path(result['artifact']).read_text(encoding='utf-8'))
            self.assertEqual(result['status'], 'qualified_partial')
            self.assertEqual(len(reference['samples']), 1)
            self.assertEqual(len(reference['cohort']), 2)
            self.assertEqual(reference['pending_sample_ids'], ['TEST-sample-2'])
            self.assertEqual(reference['cohort'][1]['split'], 'val')

    def test_disagreement_must_be_explicitly_resolved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path, manifest, rows = self.make_audit(root, completed=True)
            rows['B']['side'] = 'right'
            rows['REVIEW']['review']['input_digests']['B'] = canonical_hash(rows['B'])
            for role in ('B', 'REVIEW'):
                (root/manifest['forms'][role]).write_text(json.dumps(rows[role])+'\n', encoding='utf-8')
            with patch.object(p, '_bundle', return_value=(path, manifest)):
                with self.assertRaisesRegex(ValueError, 'bound_professional'):
                    p.audit_bundle(path)
                rows['REVIEW']['review']['disagreement_paths'] = ['/side']
                (root/'REVIEW.jsonl').write_text(json.dumps(rows['REVIEW'])+'\n', encoding='utf-8')
                self.assertEqual(p.audit_bundle(path)['approved'], 1)

    def test_empty_review_cannot_be_approved_as_zero_ground_truth(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path, manifest, rows = self.make_audit(root, completed=True)
            rows['REVIEW']['repetitions'] = []
            (root/'REVIEW.jsonl').write_text(json.dumps(rows['REVIEW'])+'\n', encoding='utf-8')
            with patch.object(p, '_bundle', return_value=(path, manifest)):
                with self.assertRaisesRegex(ValueError, 'nonempty_independent'):
                    p.audit_bundle(path)

    def test_excluded_sample_does_not_export_supervision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path, manifest, rows = self.make_audit(root, completed=True)
            rows['REVIEW']['review']['status'] = 'excluded'
            (root/'REVIEW.jsonl').write_text(json.dumps(rows['REVIEW'])+'\n', encoding='utf-8')
            with patch.object(p, '_bundle', return_value=(path, manifest)):
                with self.assertRaisesRegex(ValueError, 'cannot_contribute'):
                    p.audit_bundle(path)
                rows['REVIEW']['repetitions'] = []
                (root/'REVIEW.jsonl').write_text(json.dumps(rows['REVIEW'])+'\n', encoding='utf-8')
                result = p.audit_bundle(path)
                self.assertEqual(result['approved'], 0)
                self.assertEqual(result['excluded_sample_ids'], ['TEST-sample-1'])

    def test_explicit_reviewed_zero_inventory_is_not_unlabeled_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path, manifest, rows = self.make_audit(root, completed=True)
            for role, row in rows.items():
                row.update(repetitions=[], observable_count=0, observable_count_mask=True)
            rows['REVIEW']['review']['input_digests'] = {role: canonical_hash(rows[role]) for role in ('A', 'B')}
            for role, name in manifest['forms'].items():
                (root/name).write_text(json.dumps(rows[role])+'\n', encoding='utf-8')
            with patch.object(p, '_bundle', return_value=(path, manifest)), \
                    patch.object(p, 'paths', return_value={'run': root}):
                result = p.import_reviewed(path, root/'TEST-explicit-zero')
            reference = json.loads(Path(result['artifact']).read_text(encoding='utf-8'))
            self.assertEqual(result['known_labels'], 1)
            self.assertEqual(reference['samples'][0]['observable_count'], 0)
            self.assertTrue(reference['samples'][0]['observable_count_mask'])

    def test_inventory_count_never_silently_counts_unknown_as_negative(self):
        row = self.completed()
        row.update(observable_count=1, observable_count_mask=True)
        self.assertEqual(self.check(row), 8)
        row['observable_count'] = 0
        with self.assertRaisesRegex(ValueError, 'complete_explicit'):
            self.check(row)
        rep = row['repetitions'][0]
        rep['observable_completion'] = None
        rep['label_masks']['observable_completion'] = False
        with self.assertRaisesRegex(ValueError, 'complete_explicit'):
            self.check(row)
        row = self.completed()
        row['observable_count'] = 0
        with self.assertRaisesRegex(ValueError, 'unmasked_observable'):
            self.check(row)

    def test_new_output_preserves_existing_forms(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(p, 'paths', return_value={'run': root}):
                for target in (root, root/'..'/'outside'):
                    with self.assertRaisesRegex(ValueError, 'explicit_new'):
                        p._new_output(target)


if __name__ == '__main__':
    unittest.main()
