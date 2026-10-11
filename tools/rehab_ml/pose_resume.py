"""Explicit epoch-boundary recovery for owned offline runs, never warm-start."""
from __future__ import annotations

import os
from pathlib import Path
import platform
import random
import sys

from tools.rehab_ml.common import ROOT, file_hash, read_json, write_json
from tools.rehab_ml.pose_dataset import _json

VERSION = 'rehab-pose-resume-1'
IMPLEMENTATIONS = ('tools/rehab_ml/pose_training.py', 'tools/rehab_ml/pose_resume.py',
                   'tools/rehab_ml/pose_masked_loss.py', 'tools/rehab_ml/pose_dataset.py',
                   'tools/rehab_ml/pose_cpu_gradients.py', 'tools/rehab_ml/common.py')


def implementation_hashes():
    return {name: file_hash(ROOT/name) for name in IMPLEMENTATIONS}


def environment(config):
    import torch
    from tools.rehab_ml.pose_cpu_gradients import VERSION as GRADIENT_VERSION, OPTIMIZER_VERSION, ACTIVATION_VERSION
    return dict(python=sys.version, platform=platform.platform(), torch=str(torch.__version__),
                device=config['device'], threads=config['threads'],
                cpu_training_backend='aten_no_mkldnn' if config['device'] == 'cpu' else 'not_cpu',
                autograd_multithreading=False, gradient_norm_accumulation='float64_fixed_order_l2',
                criterion_lifetime='epoch_local',
                optimizer_implementation=OPTIMIZER_VERSION if config['device'] == 'cpu' else 'AdamW_foreach_false_fused_false',
                cpu_conv_weight_gradient=GRADIENT_VERSION if config['device'] == 'cpu' else 'native_autograd',
                cpu_silu=ACTIVATION_VERSION if config['device'] == 'cpu' else 'native_silu',
                numerical_environment={key: os.environ.get(key) for key in
                    ('MKL_CBWR', 'MKL_DYNAMIC', 'OMP_DYNAMIC', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')},
                cuda=torch.version.cuda, cudnn=torch.backends.cudnn.version(),
                cublas_workspace_config=os.environ.get('CUBLAS_WORKSPACE_CONFIG'))


def prepare_resume(run, config, reference_hash):
    """Read-only preflight. Caller must hold the live training/compute leases."""
    from tools.rehab_ml.pose_training import VERSION as TRAIN_VERSION, owned_output
    source = owned_output(run)
    if source == owned_output(config['output_dir']):
        raise ValueError('resume_requires_new_output_never_overwrite_source')
    if any((source/name).exists() for name in
           ('result.json', 'model-card.json', 'test-started.json', 'baseline-test', 'candidate-test')):
        raise ValueError('resume_forbidden_after_test_or_completed_run')
    state = _json(source/'status.json')[1]
    terminal_receipt_hash = None
    receipt_path = source/'provenance.json'
    if receipt_path.is_file():
        terminal_receipt_hash = file_hash(receipt_path)
    if state.get('phase') not in ('failed', 'cancelled'):
        # Status alone cannot prove death. The caller holds the actual OS
        # leases; additionally require the parent's confirmed abnormal exit
        # receipt bound to this exact source request, source and child log.
        if (state.get('phase') not in ('baseline_validation', 'resume_loading', 'training',
                                      'checkpoint', 'validation', 'reload_selected_checkpoint')
                or terminal_receipt_hash is None):
            raise ValueError('explicit_failed_or_cancelled_source_required')
        receipt = _json(receipt_path)[1]
        arguments = receipt.get('arguments')
        if (receipt.get('version') != TRAIN_VERSION or receipt.get('owned_exit_confirmed') is not True
                or type(receipt.get('exit_code')) is not int or receipt['exit_code'] == 0
                or not isinstance(arguments, list) or len(arguments) < 2
                or not all(isinstance(item, str) for item in arguments)
                or arguments[-1] != str(source/'request.json')
                or receipt.get('implementation_sha256') != implementation_hashes()
                or receipt.get('child_log_sha256') != file_hash(source/'child.log')):
            raise ValueError('confirmed_owned_abnormal_exit_receipt_required')
    request, frozen = _json(source/'request.json')[1], _json(source/'resolved-config.json')[1]
    if (request.get('version') != TRAIN_VERSION or request.get('output_dir') != str(source)
            or frozen.get('output_dir') != str(source)
            or request.get('resolved_config_sha256') != file_hash(source/'resolved-config.json')
            or request.get('reference_sha256') != reference_hash):
        raise ValueError('resume_frozen_source_provenance_mismatch')
    # No change in data, split, dose-independent optimizer, stopping rule or
    # evaluation policy. A fresh attempt can have a new output/time budget.
    ignored = {'output_dir', 'timeout_s'}
    if ({k: v for k, v in frozen.items() if k not in ignored}
            != {k: v for k, v in config.items() if k not in ignored}):
        raise ValueError('resume_algorithm_config_mismatch')
    manifest_path = source/'resume-manifest.json'
    manifest = _json(manifest_path)[1]
    if (set(manifest) != {'version', 'checkpoint', 'sha256', 'epoch', 'optimizer_steps'}
            or manifest['version'] != VERSION or manifest['checkpoint'] not in ('resume-a.pt', 'resume-b.pt')
            or type(manifest['epoch']) is not int or not 1 <= manifest['epoch'] < config['max_epochs']
            or type(manifest['optimizer_steps']) is not int or manifest['optimizer_steps'] < 1):
        raise ValueError('validated_epoch_resume_manifest_required')
    checkpoint = source/manifest['checkpoint']
    if checkpoint.resolve().parent != source:
        raise ValueError('resume_checkpoint_must_stay_inside_owned_source')
    if not 0 < checkpoint.stat().st_size <= 64*1024*1024 or file_hash(checkpoint) != manifest['sha256']:
        raise ValueError('resume_checkpoint_size_or_hash_mismatch')
    return dict(source_run=str(source), manifest_sha256=file_hash(manifest_path),
                checkpoint=manifest['checkpoint'], checkpoint_sha256=manifest['sha256'],
                source_config_sha256=request['config_sha256'], epoch=manifest['epoch'],
                optimizer_steps=manifest['optimizer_steps'], terminal_receipt_sha256=terminal_receipt_hash)


def rng_snapshot(generator, device):
    import numpy as np
    import torch
    name, keys, pos, gaussian, cached = np.random.get_state()
    return dict(local_python=generator.getstate(), global_python=random.getstate(),
                numpy=dict(name=name, keys=torch.tensor(keys.astype('int64')), pos=pos,
                           gaussian=gaussian, cached=cached),
                cuda=torch.cuda.get_rng_state_all() if device != 'cpu' else [])


def restore_rng(saved, generator, device):
    import numpy as np
    import torch
    state = saved['resume_state']['rng']
    generator.setstate(state['local_python'])
    random.setstate(state['global_python'])
    value = state['numpy']
    np.random.set_state((value['name'], value['keys'].cpu().numpy().astype('uint32'),
                         value['pos'], value['gaussian'], value['cached']))
    torch.set_rng_state(saved['torch_rng_state'].cpu())
    if device != 'cpu':
        if len(state['cuda']) != torch.cuda.device_count():
            raise ValueError('resume_cuda_rng_device_count_mismatch')
        torch.cuda.set_rng_state_all([item.cpu() for item in state['cuda']])
    elif state['cuda']:
        raise ValueError('resume_cpu_checkpoint_has_cuda_rng')


def load_resume(spec, config, reference_hash, model, optimizer):
    import torch
    from tools.rehab_ml.pose_training import BASE_SHA256, VERSION as TRAIN_VERSION, selection_score
    from tools.rehab_ml.pose_masked_smoke import _tensor_digest
    if prepare_resume(spec['source_run'], config, reference_hash) != spec:
        raise ValueError('resume_source_changed_after_parent_preflight')
    checkpoint = Path(spec['source_run'])/spec['checkpoint']
    saved = torch.load(checkpoint, map_location='cpu', weights_only=True)
    if (file_hash(checkpoint) != spec['checkpoint_sha256']
            or file_hash(checkpoint.parent/'resume-manifest.json') != spec['manifest_sha256']):
        raise ValueError('resume_checkpoint_changed_during_load')
    if (saved.get('version') != TRAIN_VERSION or saved.get('base_sha256') != BASE_SHA256
            or saved.get('config_sha256') != spec['source_config_sha256']
            or saved.get('reference_sha256') != reference_hash
            or saved.get('fixture_only') is not (config['mode'] == 'engineering_test')
            or saved.get('product_enabled') is not False
            or saved.get('epoch') != spec['epoch'] or saved.get('optimizer_steps') != spec['optimizer_steps']):
        raise ValueError('resume_checkpoint_provenance_mismatch')
    state = saved['resume_state']
    if (state['version'] != VERSION or state['implementation_sha256'] != implementation_hashes()
            or state['environment'] != environment(config)):
        raise ValueError('resume_implementation_or_environment_mismatch')
    history = state['history']
    if config['mode'] == 'research' and selection_score(state['baseline_validation_summary'])[0] >= 1.:
        raise ValueError('resume_baseline_problem_gate_not_met')
    if not isinstance(history, list) or len(history) != spec['epoch']:
        raise ValueError('resume_validated_history_required')
    best, best_epoch, bad = None, None, 0
    for epoch, row in enumerate(history, 1):
        score = selection_score(row['validation_summary'])
        improved = best is None or score > best
        if (row['epoch'] != epoch or row['validation_score'] != list(score)
                or row['best_updated'] is not improved):
            raise ValueError('resume_validation_history_inconsistent')
        if improved:
            best, best_epoch, bad = score, epoch, 0
        else:
            bad += 1
    if (state['best_score'] != list(best) or state['best_epoch'] != best_epoch
            or state['bad_epochs'] != bad or bad >= config['patience']
            or history[-1]['optimizer_steps'] != spec['optimizer_steps']
            or _tensor_digest(state['best_state_dict'].items()) != state['best_state_digest']):
        raise ValueError('resume_selection_state_inconsistent_or_already_stopped')
    expected = model.state_dict()
    for tensors in (saved['state_dict'], state['best_state_dict']):
        if set(tensors) != set(expected) or any(
                item.shape != expected[key].shape or item.dtype != expected[key].dtype
                or not torch.isfinite(item).all() for key, item in tensors.items()):
            raise ValueError('resume_model_state_shape_dtype_or_finiteness_mismatch')
    wanted, given = optimizer.state_dict()['param_groups'], saved['optimizer_state']['param_groups']
    if (len(given) != len(wanted) or any(group != expected_group for group, expected_group in zip(given, wanted))):
        raise ValueError('resume_optimizer_groups_mismatch')
    model.load_state_dict(saved['state_dict'], strict=True)
    optimizer.load_state_dict(saved['optimizer_state'])
    for parameter, values in optimizer.state.items():
        if (set(values) != {'step', 'exp_avg', 'exp_avg_sq'}
                or values['step'].numel() != 1 or not torch.isfinite(values['step']).all()
                or values['step'].item() < 1 or any(values[name].shape != parameter.shape
                    or not torch.isfinite(values[name]).all() for name in ('exp_avg', 'exp_avg_sq'))):
            raise ValueError('resume_optimizer_moments_invalid')
        # Materialize owned native tensors rather than retain serialized
        # storage views. Values/dtypes are unchanged, never rounded.
        for name, value in list(values.items()):
            values[name] = value.clone(memory_format=torch.preserve_format)
    return saved


def save_boundary(output, model, optimizer, metadata, state):
    """Alternating slots: only the atomic JSON pointer commits a safe boundary.

    A write failure cannot destroy the previous pointed checkpoint. Embedded
    best weights avoid a mutable best.pt invalidating that previous boundary.
    """
    from tools.rehab_ml.pose_training import _checkpoint
    previous = read_json(output/'resume-manifest.json') if (output/'resume-manifest.json').exists() else None
    name = 'resume-b.pt' if previous and previous['checkpoint'] == 'resume-a.pt' else 'resume-a.pt'
    fingerprint = _checkpoint(output/name, model, optimizer, dict(metadata, resume_state=state))
    write_json(output/'resume-manifest.json', dict(version=VERSION, checkpoint=name, sha256=fingerprint,
               epoch=metadata['epoch'], optimizer_steps=metadata['optimizer_steps']))
    return name, fingerprint
