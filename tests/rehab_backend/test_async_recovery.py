"""C15/C18/C23: actual owned host exit, not a graceful close or fake status."""
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.rehab_ml import async_recovery as audit
from tools.rehab_ml.common import paths


class AsyncRecoveryTests(unittest.TestCase):
    def test_three_real_process_windows_recover_exactly_one_fact_and_contribution(self):
        result = audit.audit_async_recovery()
        self.assertTrue(result['passed'], str(result))
        self.assertEqual([row['case'] for row in result['cases']], list(audit.CASES))
        self.assertTrue(result['source_unchanged'])
        for row in result['cases']:
            self.assertTrue(row['actual_exit_confirmed'])
            self.assertTrue(all(row['checks'].values()), str(row))
            self.assertGreaterEqual(len(row['checks']), 30)

    def test_probe_refuses_existing_database_and_output(self):
        with tempfile.TemporaryDirectory(dir=paths()['run']) as folder:
            database = Path(folder)/'TEST-host.sqlite3'
            barrier = Path(folder)/'TEST-barrier.json'
            self.assertEqual(audit.validate_child_target(database, barrier, audit.CASES[0]), (database, barrier))
            database.touch()
            with self.assertRaisesRegex(ValueError, 'new_isolated_TEST'):
                audit.validate_child_target(database, barrier, audit.CASES[0])
            database.unlink()
            barrier.touch()
            with self.assertRaises(ValueError):
                audit.validate_child_target(database, barrier, audit.CASES[0])

    def test_probe_refuses_unknown_case_outside_run_or_mismatched_parent(self):
        with tempfile.TemporaryDirectory(dir=paths()['run']) as folder:
            database = Path(folder)/'TEST-host.sqlite3'
            barrier = Path(folder)/'TEST-barrier.json'
            for db, proof, case in ((database, barrier, 'not-a-case'),
                    (ROOT/'TEST-host.sqlite3', ROOT/'TEST-barrier.json', audit.CASES[0]),
                    (database, barrier.parent/'other'/'TEST-barrier.json', audit.CASES[0])):
                with self.subTest(case=case, path=str(db)), self.assertRaises(ValueError):
                    audit.validate_child_target(db, proof, case)

    def test_failed_audit_returns_nonzero_and_preserves_failure_result(self):
        with patch.object(audit, 'audit_async_recovery', return_value=dict(passed=False, cases=[])), redirect_stdout(StringIO()) as output:
            self.assertEqual(audit.main([]), 1)
            self.assertIn('"passed": false', output.getvalue())


if __name__ == '__main__':
    unittest.main()
