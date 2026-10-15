from pathlib import Path
import os
import sys
import tempfile
import unittest
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.rehab_ml.common import paths, write_json
from tools.rehab_ml.socket_recovery_audit import audit, validated_run, WORKLOAD


class SocketRecoveryTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt', 'actual owned Windows native handles required')
    def test_original_host_actual_TCP_loss_retry_and_second_server_recovery(self):
        result = audit()
        self.assertTrue(result['passed'], result)
        self.assertEqual(len(result['checks']), 22)
        self.assertTrue(all(result['checks'].values()))
        self.assertEqual([row['forced_requested'] for row in result['hosts']], [True, False])
        self.assertTrue(all(not row['fallback_cleanup_required'] for row in result['hosts']))
        self.assertIsNone(result['clinical_accuracy'])

    def test_normal_workspace_or_missing_declaration_cannot_be_child_target(self):
        with self.assertRaises(ValueError):
            validated_run(ROOT, 0)
        with tempfile.TemporaryDirectory(prefix='socket-recovery-'+uuid4().hex[:8], dir=paths()['run']) as folder:
            with self.assertRaises(ValueError):
                validated_run(Path(folder), 0)

    def test_declared_fresh_child_refuses_reused_ready_and_invalid_index(self):
        run = paths()['run']/('socket-recovery-'+uuid4().hex[:8])
        run.mkdir()
        write_json(run/'predeclared.json', dict(workload=WORKLOAD))
        self.assertEqual(validated_run(run, 0), run)
        write_json(run/'TEST-ready-0.json', dict(TEST=True))
        with self.assertRaises(ValueError):
            validated_run(run, 0)
        with self.assertRaises(ValueError):
            validated_run(run, 2)


if __name__ == '__main__':
    unittest.main()
