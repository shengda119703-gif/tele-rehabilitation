"""Audit arithmetic tests. Actual native HTTP load is a separate CLI run."""
import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.rehab_ml.session_load_audit import WORKLOAD, fact, reconcile
from tools.rehab_ml.cli import parser


class LoadAuditTests(unittest.TestCase):
    def setUp(self):
        self.item = dict(accepted_count=3, processed_count=1, accepted_last_seq=8,
                         processed_last_seq=2, persisted_evidence_seq=2,
                         dropped_intervals=[dict(from_seq=5, to_seq=5, reason='replaced'),
                                            dict(from_seq=8, to_seq=8, reason='timeout')])
        self.audit = dict(frames=[dict(seq=2, status='processed', reason=None),
                                 dict(seq=5, status='dropped', reason='replaced'),
                                 dict(seq=8, status='unprocessed', reason='timeout')],
                          audit=[dict(kind='finalize'), dict(kind='plan_contribution')])

    def test_noncontiguous_sequences_are_not_full_coverage(self):
        result = reconcile(self.item, self.audit)
        self.assertTrue(all(result['checks'].values()))
        self.assertEqual(result['status_counts'], dict(processed=1, dropped=1, unprocessed=1))

    def test_high_water_mark_cannot_replace_processed_count(self):
        self.item['processed_count'] = 8
        self.assertFalse(reconcile(self.item, self.audit)['checks']['processed_count_matches_rows'])

    def test_pending_or_unknown_status_not_terminal_success(self):
        self.audit['frames'][2]['status'] = 'accepted'
        self.assertFalse(reconcile(self.item, self.audit)['checks']['no_pending_after_terminal'])
        self.audit['frames'][2]['status'] = 'invented'
        self.assertFalse(reconcile(self.item, self.audit)['checks']['known_statuses'])

    def test_omitted_or_fabricated_exclusion_fails(self):
        self.item['dropped_intervals'].pop()
        self.assertFalse(reconcile(self.item, self.audit)['checks']['exclusions_explicit'])
        self.item['dropped_intervals'].append(dict(from_seq=7, to_seq=8, reason='timeout'))
        self.assertFalse(reconcile(self.item, self.audit)['checks']['exclusions_explicit'])

    def test_duplicate_finalization_or_contribution_fails(self):
        self.audit['audit'].append(dict(kind='finalize'))
        self.assertFalse(reconcile(self.item, self.audit)['checks']['one_finalize'])
        self.audit['audit'].append(dict(kind='plan_contribution'))
        self.assertFalse(reconcile(self.item, self.audit)['checks']['one_contribution'])

    def test_fact_projection_excludes_report_but_preserves_evidence(self):
        keys = ('canonical_commit', 'snapshot', 'accepted_count', 'processed_count',
                'accepted_last_seq', 'processed_last_seq', 'persisted_evidence_seq',
                'terminal_epoch', 'dropped_intervals', 'plan_contribution')
        before = {key: {} for key in keys}
        after = copy.deepcopy(before)
        after['derived_report_state'] = 'pending'
        self.assertEqual(fact(before), fact(after))
        after['snapshot']['completed'] = 1
        self.assertNotEqual(fact(before), fact(after))

    def test_cli_is_fixed_workload_not_best_fragment_selection(self):
        self.assertEqual(parser().parse_args(['benchmark-session-load']).command, 'benchmark-session-load')
        self.assertGreater(WORKLOAD['frames'], WORKLOAD['finish_after_sent'])
        self.assertEqual(WORKLOAD['cold_warmup_frames'], 1)
        self.assertEqual(WORKLOAD['concurrent_finish_requests'], 4)


if __name__ == '__main__':
    unittest.main()
