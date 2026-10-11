"""TEST-only independent reference fixtures, never actual professional labels."""
from __future__ import annotations

import copy
from itertools import combinations
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.rehab_ml import temporal_evaluation as e
from tools.rehab_ml.common import write_json
from tools.rehab_ml.professional_annotations import BOUNDARIES, record_template, repetition_template
from tools.rehab_ml.verify_all import regression_cases
from tools.rehab_ml.verify_storage_recheck import cases_for


class TemporalEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = dict(sample_id='TEST-1', subject_group='TEST-person-1', video_sha256='a'*64,
            exercise_id='shoulder_abduction', protocol_version='rehab-protocol-2.0', split='test',
            time_basis='stream_relative_media_pts', duration_s=5., timeline_ref='timeline.json', view='frontal')
        write_json(self.root/'timeline.json', dict(presentation_s=[i*.25 for i in range(21)]))
        self.label = record_template(self.source, 'REVIEW')
        self.label['side'] = 'left'
        self.label.update(observable_count=1, observable_count_mask=True)
        rep = repetition_template()
        rep.update(rep_id='TEST-rep', boundaries=dict(zip(BOUNDARIES, map(float, range(6)))),
                   observable_completion=True)
        rep['label_masks']['phase'] = dict.fromkeys(BOUNDARIES, True)
        rep['label_masks']['observable_completion'] = True
        self.label['repetitions'] = [rep]
        self.prediction = dict(sample_id='TEST-1', video_sha256='a'*64, exercise_id='shoulder_abduction',
            side='left', protocol_version='rehab-protocol-2.0', split='test',
            time_basis='stream_relative_media_pts', status='completed', completed_count=1,
            boundary_events={key: [dict(event_id='TEST-'+key, time_s=float(i), evidence_kind='observed')]
                             for i, key in enumerate(BOUNDARIES)})

    def manifest(self, prediction=None):
        return dict(schema_version=e.PREDICTION_SCHEMA, origin='declared_backend_export',
                    reference_used_for_predictions=False, implementation_sha256='b'*64,
                    model_sha256='c'*64, config_sha256='d'*64,
                    samples=[copy.deepcopy(prediction or self.prediction)])

    def validate(self, manifest):
        return e.validate_predictions(manifest, [self.source], {'TEST-1': self.label}, self.root)

    def score(self, label=None, prediction=None):
        return e.score_sample(label or self.label, prediction or self.prediction, .25)

    def test_nearest_greedy_cannot_lose_second_match(self):
        # Greedy consumes .3 for .25, leaving .5 unmatched; DP matches both.
        self.assertEqual(e.match_events([.25, .5], [0., .3], .25), [(0, 0), (1, 1)])

    def test_matcher_agrees_with_exhaustive_small_ordered_assignments(self):
        arrays = [[], [0.], [.2, .4], [0., .3, .5], [.1, .2, .2, .6]]
        for reference in arrays:
            for prediction in arrays:
                possibilities = [(0, 0.)]
                for size in range(1, min(len(reference), len(prediction))+1):
                    for left in combinations(range(len(reference)), size):
                        for right in combinations(range(len(prediction)), size):
                            errors = [abs(reference[i]-prediction[j]) for i, j in zip(left, right)]
                            if all(error <= .25 for error in errors):
                                possibilities.append((size, -sum(errors)))
                matched = e.match_events(reference, prediction, .25)
                actual = (len(matched), -sum(abs(reference[i]-prediction[j]) for i, j in matched))
                expected = max(possibilities)
                self.assertEqual(actual[0], expected[0])
                self.assertAlmostEqual(actual[1], expected[1])

    def test_maximum_cardinality_before_minimum_error(self):
        self.assertEqual(e.match_events([.2, .4], [0., .25], .25), [(0, 0), (1, 1)])

    def test_minimum_total_error_at_equal_cardinality(self):
        self.assertEqual(e.match_events([1.], [.8, 1.1], .25), [(0, 1)])

    def test_one_prediction_cannot_match_two_references(self):
        self.assertEqual(len(e.match_events([1., 1.1], [1.05], .25)), 1)

    def test_empty_and_inclusive_tolerance(self):
        self.assertEqual(e.match_events([], [1.], .25), [])
        self.assertEqual(e.match_events([1.], [1.25], .25), [(0, 0)])
        self.assertEqual(e.match_events([1.], [1.251], .25), [])

    def test_invalid_tolerance_times_and_quotas(self):
        for tolerance in (0, -1, float('nan'), True, 2):
            with self.assertRaises(ValueError):
                e.match_events([], [], tolerance)
        for times in ([float('nan')], [True], [-1.], [2., 1.], [0.]*501):
            with self.assertRaises(ValueError):
                e.match_events(times, [], .25)

    def test_valid_declared_manifest(self):
        self.assertEqual(len(self.validate(self.manifest())), 1)

    def test_no_reference_prefill_or_human_prediction_origin(self):
        for key, value in (('reference_used_for_predictions', True), ('origin', 'independent_human_review')):
            manifest = self.manifest()
            manifest[key] = value
            with self.assertRaises(ValueError):
                self.validate(manifest)

    def test_missing_unlabeled_cohort_row_is_not_allowed(self):
        with self.assertRaisesRegex(ValueError, 'complete_requested_split'):
            e.validate_predictions(self.manifest(), [self.source, dict(self.source, sample_id='TEST-2')],
                                   {'TEST-1': self.label}, self.root)

    def test_source_clock_protocol_side_and_split_cannot_change(self):
        for key, value in (('video_sha256', 'z'*64), ('time_basis', 'nominal_30fps'),
                           ('split', 'train'), ('protocol_version', 'legacy'), ('side', 'right')):
            manifest = self.manifest()
            manifest['samples'][0][key] = value
            with self.assertRaises(ValueError):
                self.validate(manifest)

    def test_prediction_counts_are_not_bool_or_nonfinite(self):
        for count in (True, -1, 501, 1.0, float('inf')):
            manifest = self.manifest()
            manifest['samples'][0]['completed_count'] = count
            with self.assertRaises(ValueError):
                self.validate(manifest)

    def test_failed_result_keeps_all_tasks_null_not_zero(self):
        prediction = dict(self.prediction, status='failed', completed_count=None,
                          boundary_events=dict.fromkeys(BOUNDARIES))
        self.validate(self.manifest(prediction))
        prediction['completed_count'] = 0
        with self.assertRaisesRegex(ValueError, 'failed_prediction'):
            self.validate(self.manifest(prediction))

    def test_predicted_events_cannot_confirm_observed_facts(self):
        manifest = self.manifest()
        manifest['samples'][0]['boundary_events']['end_s'][0]['evidence_kind'] = 'predicted'
        with self.assertRaisesRegex(ValueError, 'observed_prediction'):
            self.validate(manifest)

    def test_duplicate_unordered_and_non_frame_events_rejected(self):
        key = 'outbound_start_s'
        for entries in ([dict(event_id='same', time_s=1., evidence_kind='observed')]*2,
                        [dict(event_id='a', time_s=2., evidence_kind='observed'),
                         dict(event_id='b', time_s=1., evidence_kind='observed')],
                        [dict(event_id='a', time_s=1.01, evidence_kind='observed')]):
            manifest = self.manifest()
            manifest['samples'][0]['boundary_events'][key] = entries
            with self.assertRaises(ValueError):
                self.validate(manifest)

    def test_exact_count_and_phase(self):
        scored = self.score()
        self.assertEqual(scored['count_error'], 0)
        self.assertTrue(all(row['true_positive'] == 1 for row in scored['boundaries'].values()))

    def test_unknown_count_not_zero_reference(self):
        label = copy.deepcopy(self.label)
        label.update(observable_count=None, observable_count_mask=False)
        self.assertIsNone(self.score(label)['count_error'])

    def test_explicit_zero_count_not_missing(self):
        label = copy.deepcopy(self.label)
        label.update(observable_count=0, observable_count_mask=True, repetitions=[])
        self.assertEqual(self.score(label)['count_error'], 1)
        self.assertEqual(self.score(label)['overcount'], 1)
        self.assertEqual(self.score(label)['boundaries']['end_s']['unmatched_prediction_unassessable'], 1)

    def test_known_missing_prediction_preserves_denominator(self):
        prediction = dict(self.prediction, status='failed', completed_count=None,
                          boundary_events=dict.fromkeys(BOUNDARIES))
        summary = e.aggregate([self.score(prediction=prediction)], 3)
        self.assertEqual(summary['known_count_reference_videos'], 1)
        self.assertEqual(summary['missing_count_predictions'], 1)
        self.assertEqual(summary['count_coverage'], 0)
        self.assertEqual(summary['known_count_reference_coverage'], 1/3)
        self.assertIsNone(summary['count_mae'])
        self.assertEqual(summary['boundaries']['end_s']['false_negative'], 1)

    def test_masked_boundary_not_false_negative_or_negative_reference(self):
        label = copy.deepcopy(self.label)
        label['repetitions'][0]['boundaries']['end_s'] = None
        label['repetitions'][0]['label_masks']['phase']['end_s'] = False
        boundary = self.score(label)['boundaries']['end_s']
        self.assertEqual(boundary['false_negative'], 0)
        self.assertEqual(boundary['false_positive'], 0)
        self.assertEqual(boundary['unmatched_prediction_unassessable'], 1)

    def test_unmatched_prediction_only_negative_if_boundary_inventory_known(self):
        prediction = copy.deepcopy(self.prediction)
        prediction['boundary_events']['end_s'] = [dict(event_id='early', time_s=1., evidence_kind='observed')]
        boundary = self.score(prediction=prediction)['boundaries']['end_s']
        self.assertEqual(boundary['false_positive'], 1)
        self.assertEqual(boundary['false_negative'], 1)

    def test_boundary_types_never_cross_match(self):
        prediction = copy.deepcopy(self.prediction)
        prediction['boundary_events']['end_s'] = prediction['boundary_events']['outbound_start_s']
        self.assertEqual(self.score(prediction=prediction)['boundaries']['end_s']['true_positive'], 0)

    def test_timing_errors_and_precision_uncertainty(self):
        prediction = copy.deepcopy(self.prediction)
        prediction['boundary_events']['outbound_start_s'][0]['time_s'] = 1.25
        scored = self.score(prediction=prediction)
        result = e.aggregate([scored], 2)
        self.assertEqual(result['boundaries']['outbound_start_s']['timing']['bias_s'], .25)
        label = copy.deepcopy(self.label)
        label['repetitions'][0]['label_masks']['phase']['end_s'] = False
        label['repetitions'][0]['boundaries']['end_s'] = None
        uncertain = e.aggregate([self.score(label)], 1)['boundaries']['end_s']
        self.assertEqual(uncertain['precision_lower_bound'], 0)
        self.assertIsNone(uncertain['precision_on_assessable'])

    def test_signed_count_error_and_over_under_separate(self):
        for predicted, error, over, under in ((0, -1, 0, 1), (3, 2, 2, 0)):
            scored = self.score(prediction=dict(self.prediction, completed_count=predicted))
            self.assertEqual((scored['count_error'], scored['overcount'], scored['undercount']), (error, over, under))

    def test_empty_aggregate_has_null_metrics_not_perfect_scores(self):
        summary = e.aggregate([], 5)
        self.assertIsNone(summary['count_mae'])
        self.assertIsNone(summary['boundaries']['end_s']['recall'])
        self.assertEqual(summary['approved_reference_coverage'], 0)

    def test_bundle_without_supervision_rejected_before_predictions(self):
        path = self.root/'bundle.json'
        write_json(path, dict(schema_version='rehab-independent-review-bundle-1'))
        with patch.object(e, 'audit_bundle', return_value=dict(status='pending_human_review')):
            with self.assertRaisesRegex(ValueError, 'blocked_missing_independent'):
                e.evaluate(path, self.root/'does-not-exist.json', self.root/'must-not-exist', split='test')
        self.assertFalse((self.root/'must-not-exist').exists())

    def test_qualified_bundle_must_be_explicitly_imported(self):
        path = self.root/'bundle.json'
        write_json(path, dict(schema_version='rehab-independent-review-bundle-1'))
        with patch.object(e, 'audit_bundle', return_value=dict(status='qualified')):
            with self.assertRaisesRegex(ValueError, 'explicit_imported'):
                e.verified_reference(path)

    def test_train_split_never_used_for_independent_evaluation(self):
        with self.assertRaisesRegex(ValueError, 'validation_or_test'):
            e.evaluate('not-read', 'not-read', 'not-created', split='train')

    def imported(self):
        second = dict(self.source, sample_id='TEST-2', subject_group='TEST-person-2')
        cohort = [self.source, second]
        path = self.root/'reference.json'
        bundle = self.root/'bundle.json'
        reference = dict(schema_version='rehab-reviewed-temporal-reference-1', origin='independent_human_review',
            bundle_ref=str(bundle), bundle_sha256='e'*64, forms_sha256={'A': 'f'*64},
            samples=[self.label], cohort=cohort, pending_sample_ids=['TEST-2'], excluded_sample_ids=[],
            all_source_samples=2, excluded_samples=0, training_scope='offline_temporal_research_only',
            pose_supervision=False, product_enabled=False, diagnosis_or_dosage_allowed=False,
            created_at='TEST-fixture-not-real-review', implementation_sha256='0'*64)
        write_json(path, reference)
        write_json(bundle, dict(samples=cohort))
        audit = dict(status='qualified_partial', bundle_sha256='e'*64, forms_sha256={'A': 'f'*64},
                     approved_rows=[self.label], pending_sample_ids=['TEST-2'], excluded_sample_ids=[],
                     samples=2, excluded=0)
        return path, reference, audit

    def test_imported_reference_rebinds_to_current_professional_resolution(self):
        path, reference, audit = self.imported()
        with patch.object(e, 'audit_bundle', return_value=audit):
            self.assertEqual(e.verified_reference(path), reference)
            reference = copy.deepcopy(reference)
            reference['samples'][0]['observable_count'] = 99
            write_json(path, reference)
            with self.assertRaisesRegex(ValueError, 'no_longer_matches'):
                e.verified_reference(path)

    def test_stale_form_digest_cannot_survive_new_review(self):
        path, _, audit = self.imported()
        audit['forms_sha256'] = {'A': '1'*64}
        with patch.object(e, 'audit_bundle', return_value=audit):
            with self.assertRaisesRegex(ValueError, 'no_longer_matches'):
                e.verified_reference(path)

    def test_partial_reference_full_cohort_and_pending_subject_preserved(self):
        path, _, audit = self.imported()
        second = dict(self.prediction, sample_id='TEST-2', side=None, status='failed', completed_count=None,
                      boundary_events=dict.fromkeys(BOUNDARIES))
        manifest = self.manifest()
        manifest['samples'].append(second)
        pred = self.root/'predictions.json'
        write_json(pred, manifest)
        output = self.root/'evaluation'
        def owned_output(value):
            self.assertEqual(Path(value), output)
            output.mkdir()
            return output
        with patch.object(e, 'audit_bundle', return_value=audit), patch.object(e, '_new_output', side_effect=owned_output):
            result = e.evaluate(path, pred, output, split='test')
        self.assertEqual(result['aggregate']['cohort_videos'], 2)
        self.assertEqual(result['aggregate']['approved_reference_videos'], 1)
        self.assertEqual(result['pending_sample_ids'], ['TEST-2'])
        self.assertEqual(result['by_subject']['TEST-person-2']['approved_reference_videos'], 0)
        self.assertIsNone(result['by_subject']['TEST-person-2']['count_mae'])
        self.assertFalse(result['product_enabled'])
        self.assertTrue(Path(result['artifact']).is_file())

    def test_reference_mutation_during_evaluation_creates_no_output(self):
        path, reference, _ = self.imported()
        manifest = self.manifest()
        manifest['samples'].append(dict(self.prediction, sample_id='TEST-2', side=None, status='failed',
            completed_count=None, boundary_events=dict.fromkeys(BOUNDARIES)))
        pred = self.root/'predictions.json'
        write_json(pred, manifest)
        changed = dict(reference, created_at='TEST-changed')
        with patch.object(e, 'verified_reference', side_effect=[reference, changed]):
            with self.assertRaisesRegex(ValueError, 'changed_during_evaluation'):
                e.evaluate(path, pred, self.root/'must-not-created', split='test')
        self.assertFalse((self.root/'must-not-created').exists())

    def test_full_regression_uses_same_four_cases_without_substitution(self):
        cases = cases_for('full', self.root)
        self.assertEqual(cases, regression_cases(self.root))
        self.assertEqual([row[0] for row in cases], ['new_backend', 'legacy_rehab', 'legacy_mobile', 'scope'])
        self.assertEqual(len(cases_for('subset', self.root)), 3)
        with self.assertRaises(ValueError):
            cases_for('renamed-subset', self.root)


if __name__ == '__main__':
    unittest.main()
