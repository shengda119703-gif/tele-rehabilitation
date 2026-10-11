"""TEST bounded Windows sharing retry; isolated temporary outputs only."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.rehab_ml.common import file_hash, paths, read_json, write_json


class AtomicJSONTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=paths()['run'])
        self.root = Path(self.temporary.name)
        self.path = self.root/'status.json'
        write_json(self.path, dict(TEST='old'))
        self.before = file_hash(self.path)

    def tearDown(self):
        self.temporary.cleanup()

    def locked(self):
        error = PermissionError('TEST Windows sharing error')
        error.winerror = 32
        return error

    def test_transient_sharing_keeps_old_until_actual_atomic_replace(self):
        actual = os.replace
        attempts = []
        def replace(source, target):
            attempts.append(source)
            self.assertEqual(file_hash(target), self.before)
            if len(attempts) < 3:
                raise self.locked()
            actual(source, target)
        with patch('tools.rehab_ml.common.os.replace', side_effect=replace), patch('tools.rehab_ml.common.time.sleep') as sleep:
            write_json(self.path, dict(TEST='new'))
        self.assertEqual(read_json(self.path), dict(TEST='new'))
        self.assertEqual(len(attempts), 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [.01, .02])
        self.assertFalse(list(self.root.glob('*.part')))

    def test_permanent_sharing_is_bounded_not_success_and_cleans_owned_temporary(self):
        with patch('tools.rehab_ml.common.os.replace', side_effect=self.locked()) as replace, patch('tools.rehab_ml.common.time.sleep') as sleep:
            with self.assertRaises(PermissionError):
                write_json(self.path, dict(TEST='new'))
        self.assertEqual(replace.call_count, 4)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [.01, .02, .04])
        self.assertEqual(file_hash(self.path), self.before)
        self.assertFalse(list(self.root.glob('*.part')))

    def test_other_io_error_not_retried_and_original_preserved(self):
        for error in (OSError('TEST full disk'), PermissionError('TEST non-Windows permission')):
            with self.subTest(type=type(error).__name__):
                with patch('tools.rehab_ml.common.os.replace', side_effect=error) as replace, patch('tools.rehab_ml.common.time.sleep') as sleep:
                    with self.assertRaises(OSError):
                        write_json(self.path, dict(TEST='new'))
                self.assertEqual(replace.call_count, 1)
                sleep.assert_not_called()
                self.assertEqual(file_hash(self.path), self.before)
                self.assertFalse(list(self.root.glob('*.part')))

    def test_nonfinite_payload_rejected_before_replace_without_leaked_partial(self):
        with patch('tools.rehab_ml.common.os.replace') as replace:
            with self.assertRaises(ValueError):
                write_json(self.path, dict(TEST=float('nan')))
        replace.assert_not_called()
        self.assertEqual(file_hash(self.path), self.before)
        self.assertFalse(list(self.root.glob('*.part')))
