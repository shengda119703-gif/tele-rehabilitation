"""Isolated TEST resume gates, RNG and atomic checkpoint pointer semantics."""
import copy
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

from tools.rehab_ml.common import file_hash, paths, read_json, write_json
from tools.rehab_ml.pose_training import VERSION as TRAIN_VERSION, train_pose
from tools.rehab_ml.pose_resume import (VERSION, environment, implementation_hashes, load_resume,
                                        prepare_resume, restore_rng, rng_snapshot, save_boundary)
from tools.rehab_ml.pose_masked_smoke import BASE_SHA256, _tensor_digest
from test_pose_training import test_config
from test_pose_masked_loss import fixture


class PoseResumeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=paths()['run'])
        self.root = Path(self.temporary.name)
        self.reference, _ = fixture(self.root)
        self.config_file, self.config = test_config(self.root, self.reference)
        self.config.update(max_epochs=4, patience=4)
        write_json(self.config_file, self.config)
        self.source = self.root/'source'
        self.source.mkdir()
        frozen = dict(self.config, output_dir=str(self.source))
        frozen_path = write_json(self.source/'resolved-config.json', frozen)
        self.request = dict(version=TRAIN_VERSION, output_dir=str(self.source), config_sha256='a'*64,
                            reference_sha256=file_hash(self.reference), resolved_config_sha256=file_hash(frozen_path))
        write_json(self.source/'request.json', self.request)
        write_json(self.source/'status.json', dict(phase='cancelled'))
        checkpoint = self.source/'resume-a.pt'
        checkpoint.write_bytes(b'TEST-not-a-native-checkpoint-preflight-only')
        self.manifest = dict(version=VERSION, checkpoint=checkpoint.name, sha256=file_hash(checkpoint), epoch=1, optimizer_steps=1)
        write_json(self.source/'resume-manifest.json', self.manifest)

    def tearDown(self):
        self.temporary.cleanup()

    def prepare(self):
        return prepare_resume(self.source, self.config, file_hash(self.reference))

    def test_preflight_is_readonly_and_new_output_required(self):
        before = {p.name: file_hash(p) for p in self.source.iterdir()}
        self.assertEqual(self.prepare()['epoch'], 1)
        self.assertEqual(before, {p.name: file_hash(p) for p in self.source.iterdir()})
        self.config['output_dir'] = str(self.source)
        with self.assertRaisesRegex(ValueError, 'never_overwrite'):
            self.prepare()

    def test_test_fence_or_completed_result_forbids_resume(self):
        for name in ('test-started.json', 'result.json', 'model-card.json', 'baseline-test', 'candidate-test'):
            target = self.source/name
            target.write_text('TEST', encoding='utf-8')
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'after_test_or_completed'):
                self.prepare()
            target.unlink()

    def test_active_or_unknown_state_not_assumed_terminal(self):
        for phase in ('training', 'validation', 'completed', 'unknown'):
            write_json(self.source/'status.json', dict(phase=phase))
            with self.subTest(phase=phase), self.assertRaisesRegex(ValueError, 'failed_or_cancelled'):
                self.prepare()

    def exit_receipt(self):
        """TEST preflight fixture only, not proof of a real native process."""
        (self.source/'child.log').write_text('TEST preflight abnormal exit', encoding='utf-8')
        return dict(version=TRAIN_VERSION, owned_exit_confirmed=True, exit_code=27,
                    arguments=['TEST', '--child-request', str(self.source/'request.json')],
                    child_log_sha256=file_hash(self.source/'child.log'), implementation_sha256=implementation_hashes())

    def test_stale_status_requires_exact_confirmed_abnormal_exit_receipt(self):
        write_json(self.source/'status.json', dict(phase='validation'))
        receipt = self.exit_receipt()
        path = write_json(self.source/'provenance.json', receipt)
        self.assertEqual(self.prepare()['terminal_receipt_sha256'], file_hash(path))
        for change in (dict(owned_exit_confirmed=False), dict(owned_exit_confirmed=1), dict(exit_code=0),
                       dict(exit_code=True), dict(version='old'), dict(arguments=['TEST','another-request']),
                       dict(child_log_sha256='0'*64), dict(implementation_sha256={})):
            write_json(path, dict(receipt, **change))
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'abnormal_exit_receipt'):
                self.prepare()

    def test_receipt_change_after_preflight_rejected_before_torch_load(self):
        import torch
        model, optimizer = self.tiny_bundle()
        write_json(self.source/'status.json', dict(phase='validation'))
        receipt = self.exit_receipt()
        path = write_json(self.source/'provenance.json', receipt)
        spec = self.prepare()
        write_json(path, dict(receipt, elapsed_s=5.))
        with patch('torch.load') as load:
            with self.assertRaisesRegex(ValueError, 'changed_after_parent'):
                load_resume(spec, self.config, file_hash(self.reference), model, optimizer)
            load.assert_not_called()

    def test_algorithm_changes_rejected_but_attempt_timeout_allowed(self):
        for key, value in (('seed', 1), ('max_epochs', 5), ('patience', 1), ('device', 'cuda:0'),
                           ('brightness', .1), ('batch_size', 1), ('pck_threshold', .1)):
            changed = dict(self.config, **{key: value})
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'algorithm_config'):
                prepare_resume(self.source, changed, file_hash(self.reference))
        self.config['timeout_s'] = 240.
        self.assertEqual(self.prepare()['epoch'], 1)

    def test_reference_or_frozen_request_hash_change_rejected(self):
        with self.assertRaisesRegex(ValueError, 'frozen_source'):
            prepare_resume(self.source, self.config, 'b'*64)
        write_json(self.source/'resolved-config.json', dict(self.config, output_dir=str(self.source), seed=1))
        with self.assertRaisesRegex(ValueError, 'frozen_source'):
            self.prepare()

    def test_manifest_cannot_choose_arbitrary_path_or_finished_epoch(self):
        for change in (dict(checkpoint='../outside.pt'), dict(epoch=4), dict(epoch=True), dict(optimizer_steps=0),
                       dict(version='old'), dict(extra=True)):
            write_json(self.source/'resume-manifest.json', dict(self.manifest, **change))
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'epoch_resume_manifest'):
                self.prepare()

    def test_byte_tampering_or_legacy_no_manifest_refused(self):
        (self.source/'resume-a.pt').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'size_or_hash'):
            self.prepare()
        (self.source/'resume-manifest.json').unlink()
        with self.assertRaisesRegex(ValueError, 'bounded_json_file_required'):
            self.prepare()

    def test_invalid_resume_refused_before_output_or_spawn(self):
        (self.source/'test-started.json').write_text('TEST', encoding='utf-8')
        with patch('tools.rehab_ml.pose_training.subprocess.Popen') as spawn:
            with self.assertRaisesRegex(ValueError, 'after_test_or_completed'):
                train_pose(self.config_file, resume_run=self.source)
            spawn.assert_not_called()
        self.assertFalse(Path(self.config['output_dir']).exists())

    def test_formal_compute_blocks_resume_before_output_or_spawn(self):
        from app.rehab_v2.resources import ComputeLease, ResourceBusy
        with ComputeLease('formal'), patch('tools.rehab_ml.pose_training.subprocess.Popen') as spawn:
            with self.assertRaises(ResourceBusy):
                train_pose(self.config_file, resume_run=self.source)
            spawn.assert_not_called()
        self.assertFalse(Path(self.config['output_dir']).exists())

    def test_resume_rechecks_training_permission_before_reading_checkpoint(self):
        reference = read_json(self.reference)
        reference['permissions']['training'] = False
        write_json(self.reference, reference)
        with patch('tools.rehab_ml.pose_training.subprocess.Popen') as spawn:
            with self.assertRaisesRegex(ValueError, 'training_permission'):
                train_pose(self.config_file, resume_run=self.source)
            spawn.assert_not_called()
        self.assertFalse(Path(self.config['output_dir']).exists())

    def test_rng_roundtrip_restores_local_global_numpy_and_torch(self):
        import numpy as np
        import torch
        local = random.Random(23)
        random.seed(27)
        np.random.seed(29)
        torch.manual_seed(31)
        saved = dict(torch_rng_state=torch.get_rng_state(), resume_state=dict(rng=rng_snapshot(local, 'cpu')))
        expected = local.random(), random.random(), np.random.random(), torch.rand(3)
        local.random(), random.random(), np.random.random(), torch.rand(9)
        restore_rng(saved, local, 'cpu')
        self.assertEqual(local.random(), expected[0])
        self.assertEqual(random.random(), expected[1])
        self.assertEqual(np.random.random(), expected[2])
        self.assertTrue(torch.equal(torch.rand(3), expected[3]))

    def test_clipping_uses_finite_high_precision_norm_without_changing_dtype(self):
        import torch
        from tools.rehab_ml.pose_training import clip_gradients
        parameters = [torch.nn.Parameter(torch.zeros(2)), torch.nn.Parameter(torch.zeros(1))]
        parameters[0].grad = torch.tensor([3., 4.])
        parameters[1].grad = torch.tensor([12.])
        self.assertEqual(clip_gradients(parameters, 6.5), 13.)
        self.assertTrue(torch.allclose(parameters[0].grad, torch.tensor([1.5, 2.]), atol=1e-6))
        self.assertEqual(parameters[0].grad.dtype, torch.float32)
        parameters[0].grad[0] = float('nan')
        with self.assertRaisesRegex(RuntimeError, 'finite_gradient_norm'):
            clip_gradients(parameters, 6.5)

    def test_alternating_pointer_keeps_previous_checkpoint_on_pointer_write_failure(self):
        import torch
        model = torch.nn.Linear(2, 1)
        optimizer = torch.optim.AdamW(model.parameters())
        output = self.root/'boundary'
        output.mkdir()
        metadata = dict(epoch=1, optimizer_steps=1)
        first, fingerprint = save_boundary(output, model, optimizer, metadata, dict(TEST=True))
        pointer_hash = file_hash(output/'resume-manifest.json')
        with patch('tools.rehab_ml.pose_resume.write_json', side_effect=OSError('TEST pointer write')):
            with self.assertRaises(OSError):
                save_boundary(output, model, optimizer, dict(epoch=2, optimizer_steps=2), dict(TEST=True))
        self.assertEqual(file_hash(output/'resume-manifest.json'), pointer_hash)
        self.assertEqual(file_hash(output/first), fingerprint)
        second, _ = save_boundary(output, model, optimizer, dict(epoch=2, optimizer_steps=2), dict(TEST=True))
        self.assertNotEqual(first, second)
        third, _ = save_boundary(output, model, optimizer, dict(epoch=3, optimizer_steps=3), dict(TEST=True))
        self.assertEqual(first, third)

    def tiny_bundle(self):
        """Controlled linear TEST checkpoint, not a native pose/model claim."""
        import torch
        model = torch.nn.Linear(2, 1)
        optimizer = torch.optim.AdamW(model.parameters(), lr=self.config['learning_rate'], weight_decay=self.config['weight_decay'], foreach=False, fused=False)
        model(torch.ones(1, 2)).sum().backward()
        optimizer.step()
        summary = dict(coordinate_reference_count=1, pck_all_coordinate_references=0., coordinate_coverage=0.)
        history = [dict(epoch=1, optimizer_steps=1, validation_summary=summary, validation_score=[0., 0.], best_updated=True)]
        best = copy.deepcopy(model.state_dict())
        state = dict(version=VERSION, implementation_sha256=implementation_hashes(), environment=environment(self.config),
            history=history, best_score=[0., 0.], best_epoch=1, bad_epochs=0,
            best_state_dict=best, best_state_digest=_tensor_digest(best.items()),
            rng=rng_snapshot(random.Random(1), 'cpu'), initial_parameter_digest='a'*64,
            baseline_validation_summary=summary)
        from tools.rehab_ml.pose_training import _checkpoint
        fingerprint = _checkpoint(self.source/'resume-a.pt', model, optimizer, dict(version=TRAIN_VERSION,
            config_sha256=self.request['config_sha256'], reference_sha256=file_hash(self.reference), base_sha256=BASE_SHA256,
            fixture_only=True, product_enabled=False, epoch=1, optimizer_steps=1, resume_state=state))
        write_json(self.source/'resume-manifest.json', dict(self.manifest, sha256=fingerprint))
        return model, optimizer

    def test_weights_only_restore_validates_history_environment_and_optimizer(self):
        import torch
        model, optimizer = self.tiny_bundle()
        spec = self.prepare()
        target = torch.nn.Linear(2, 1)
        target_optimizer = torch.optim.AdamW(target.parameters(), lr=self.config['learning_rate'], weight_decay=self.config['weight_decay'], foreach=False, fused=False)
        saved = load_resume(spec, self.config, file_hash(self.reference), target, target_optimizer)
        self.assertTrue(all(torch.equal(model.state_dict()[name], value) for name, value in target.state_dict().items()))
        self.assertEqual(saved['epoch'], 1)
        self.assertEqual(len(target_optimizer.state), len(optimizer.state))
        with patch('tools.rehab_ml.pose_resume.environment', return_value={'TEST': 'changed environment'}):
            with self.assertRaisesRegex(ValueError, 'environment_mismatch'):
                load_resume(spec, self.config, file_hash(self.reference), target, target_optimizer)
        bad_optimizer = torch.optim.AdamW(target.parameters(), lr=1e-3, weight_decay=self.config['weight_decay'])
        with self.assertRaisesRegex(ValueError, 'optimizer_groups'):
            load_resume(spec, self.config, file_hash(self.reference), target, bad_optimizer)

    def test_post_preflight_source_change_rejected_before_checkpoint_load(self):
        import torch
        model, optimizer = self.tiny_bundle()
        spec = self.prepare()
        write_json(self.source/'resume-manifest.json', dict(read_json(self.source/'resume-manifest.json'), epoch=2))
        with patch('torch.load') as load:
            with self.assertRaisesRegex(ValueError, 'changed_after_parent'):
                load_resume(spec, self.config, file_hash(self.reference), model, optimizer)
            load.assert_not_called()
