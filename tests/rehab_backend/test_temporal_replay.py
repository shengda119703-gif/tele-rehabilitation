"""TEST-only export semantics; these fixtures are not professional references."""
from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.rehab_ml import temporal_replay as r
from tools.rehab_ml.common import write_json
from tools.rehab_ml.temporal_evaluation import validate_predictions, PREDICTION_SCHEMA


class TemporalReplayTests(unittest.TestCase):
    def transitions(self, old, new, repetitions=None):
        return r.transition_events(dict(phase=old, repetitions=[]),
            dict(phase=new, repetitions=repetitions or []), 7, 1.25)

    def test_departure_uses_current_confirmation_not_earlier_ready_time(self):
        self.assertEqual(self.transitions('REST', 'RAISING'), [('outbound_start_s', 7, 1.25)])

    def test_initial_ready_is_not_per_rep_preparation(self):
        self.assertEqual(self.transitions('WAIT_READY', 'REST'), [])

    def test_turn_confirmation_is_return_not_invented_peak(self):
        self.assertEqual(self.transitions('RAISING', 'LOWERING'), [('return_start_s', 7, 1.25)])

    def test_complete_return_emits_end(self):
        rep = dict(completion_status='COMPLETE', end_time_s=1.25)
        self.assertEqual(self.transitions('LOWERING', 'REST', [rep]), [('end_s', 7, 1.25)])

    def test_partial_recovery_never_emits_completed_end(self):
        self.assertEqual(self.transitions('LOWERING', 'WAIT_READY',
            [dict(completion_status='UNASSESSABLE', end_time_s=1.25)]), [])

    def test_prior_repetitions_do_not_emit_again(self):
        rep = dict(completion_status='COMPLETE', end_time_s=1.)
        self.assertEqual(r.transition_events(dict(phase='REST', repetitions=[rep]),
            dict(phase='REST', repetitions=[rep]), 7, 1.25), [])

    def test_current_event_cannot_use_retrospective_other_time(self):
        with self.assertRaisesRegex(ValueError, 'current_observed_pts'):
            self.transitions('LOWERING', 'REST', [dict(completion_status='COMPLETE', end_time_s=1.)])

    def test_unimplemented_endpoint_and_prep_are_null_not_empty_negatives(self):
        inventory = r.event_inventory()
        for key in ('preparation_confirmed_s', 'endpoint_start_s', 'endpoint_end_s'):
            self.assertIsNone(inventory[key])
        for key in r.SUPPORTED:
            self.assertEqual(inventory[key], [])

    def test_events_are_filtered_current_observations(self):
        inventory = r.event_inventory()
        r.append_events(inventory, [('outbound_start_s', 7, 1.25)])
        self.assertEqual(inventory['outbound_start_s'],
            [dict(event_id='outbound_start_s-7', time_s=1.25, evidence_kind='filtered')])

    def test_unknown_nonfinite_old_and_quota_events_rejected(self):
        for event in [('endpoint_start_s', 7, 1.), ('end_s', True, 1.), ('end_s', 7, float('nan')),
                      ('end_s', 7, -1.)]:
            with self.assertRaises(ValueError):
                r.append_events(r.event_inventory(), [event])
        inventory = r.event_inventory()
        r.append_events(inventory, [('end_s', 1, 1.)])
        with self.assertRaises(ValueError):
            r.append_events(inventory, [('end_s', 2, 1.)])
        inventory['end_s'] = [dict(time_s=i*.1) for i in range(500)]
        with self.assertRaises(ValueError):
            r.append_events(inventory, [('end_s', 501, 51.)])

    def test_failure_missing_count_is_not_zero(self):
        source = dict(sample_id='TEST-1', video_sha256='a'*64, exercise_id='shoulder_abduction',
            protocol_version='rehab-protocol-2.0', split='test', time_basis='stream_relative_media_pts')
        row = r.missing_row(source, 'right')
        self.assertEqual(row['side'], 'right')
        self.assertIsNone(row['completed_count'])
        self.assertTrue(all(value is None for value in row['boundary_events'].values()))

    def test_actual_export_schema_can_enter_existing_evaluator_without_gt_prefill(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = dict(sample_id='TEST-1', video_sha256='a'*64, exercise_id='shoulder_abduction',
                protocol_version='rehab-protocol-2.0', split='test', time_basis='stream_relative_media_pts',
                timeline_ref='TEST-timeline.json', duration_s=2.)
            write_json(root/source['timeline_ref'], dict(presentation_s=[i*.25 for i in range(9)]))
            row = r.missing_row(source, 'left')
            row.update(status='completed', completed_count=0, boundary_events=r.event_inventory())
            manifest = dict(schema_version=PREDICTION_SCHEMA, origin='declared_backend_export',
                reference_used_for_predictions=False, implementation_sha256='b'*64,
                model_sha256='c'*64, config_sha256='d'*64, samples=[row])
            self.assertEqual(validate_predictions(manifest, [source], {}, root), [row])
            row['status'], row['completed_count'] = 'failed', None
            row['boundary_events'] = dict.fromkeys(r.BOUNDARIES)
            self.assertEqual(len(validate_predictions(manifest, [source], {}, root)), 1)

    def test_invalid_split_side_fails_before_source_reads(self):
        with patch.object(r, '_source_samples') as source:
            for split, side in [('train', 'left'), ('test', None), ('test', 'affected')]:
                with self.assertRaises(ValueError):
                    r.replay('not-read', 'not-created', split=split, side=side)
            source.assert_not_called()


if __name__ == '__main__':
    unittest.main()
