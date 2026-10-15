"""Whole-video EAAQ regression from original-YOLO predictions, offline only."""
from __future__ import annotations

import importlib.metadata
import os
from pathlib import Path
import platform
import random
import re
import time
from uuid import uuid4

import numpy as np

from .common import ROOT, canonical_hash, file_hash, git, paths, read_json, utc_now, write_json
from .mobiphysio_pose import FEATURE_SCHEMA, verified_download
from .mobiphysio_rgb import SEED, STUDY
from .resource_gate import heavy_compute

CONFIG = dict(experiment='mobiphysio_e01_front_fl_video_eaaq_regression_v1',
    seed=SEED, feature_schema=FEATURE_SCHEMA, label_scope='whole_video', prediction_point='declared_video_end',
    models=['train_median', 'standardized_ridge', 'causal_tcn'], ridge_alpha=1.,
    tcn_channels=32, dropout=.1, dilations=[1, 2, 4, 8], kernel_size=3, convs_per_block=2,
    optimizer='AdamW', lr=.001, weight_decay=.0001, max_epochs=30, patience=6,
    selection='validation_video_mae', clip_grad_norm=1., cpu_threads=4,
    enabled_heads=['whole_video_eaaq'], disabled_heads=['phase', 'keypoint', 'visibility', 'error', 'cue', 'pain', 'prescription'],
    product_enabled=False)


def metrics(reference, prediction):
    reference, prediction = np.asarray(reference, float), np.asarray(prediction, float)
    if (reference.ndim != 1 or reference.shape != prediction.shape or len(reference) == 0
            or not np.isfinite(reference).all() or not np.isfinite(prediction).all()):
        raise ValueError('Nonempty finite paired video scores required')
    error = prediction-reference
    variance = float(((reference-reference.mean())**2).sum())
    return dict(videos=len(reference), mae=float(np.abs(error).mean()), rmse=float(np.sqrt((error**2).mean())),
                r2=1.-float((error**2).sum())/variance if variance > 0 else None,
                score_units='EAAQ points on 0–100 scale', clipped_predictions=False)


def video_statistics(features):
    """Offline summaries; coordinate placeholders do not become measured zeros."""
    features = np.asarray(features, float)
    if features.ndim != 2 or features.shape[1] != 69 or not len(features) or not np.isfinite(features).all():
        raise ValueError('Finite causal69 sequence required')
    summaries = []
    for column in range(69):
        values = features[:, column]
        if column < 34:
            values = values[features[:, 34+column//2] == 1]
        summaries.extend([float(values.mean()), float(values.std()), *np.quantile(values, [.1, .5, .9]).tolist()]
                         if len(values) else [0.]*5)
    return np.asarray(summaries, dtype=np.float64)


def fit_ridge(x, y, alpha=1.):
    x, y = np.asarray(x, float), np.asarray(y, float)
    if (x.ndim != 2 or y.shape != (len(x),) or not len(x) or not np.isfinite(x).all() or not np.isfinite(y).all()
            or type(alpha) not in (int, float) or not np.isfinite(alpha) or alpha <= 0):
        raise ValueError('Finite training rows and labels required')
    mean, std = x.mean(0), x.std(0)
    std = np.where(std < 1e-6, 1., std)
    target_mean = float(y.mean())
    scaled = (x-mean)/std
    # Dual form keeps the actual small-cohort problem bounded by people, not 345 features.
    coefficient = scaled.T @ np.linalg.solve(scaled @ scaled.T + alpha*np.eye(len(x)), y-target_mean)
    return dict(mean=mean, std=std, target_mean=target_mean, coefficient=coefficient)


def predict_ridge(state, x):
    return (np.asarray(x)-state['mean'])/state['std'] @ state['coefficient'] + state['target_mean']


def load_extraction(extraction_path):
    extraction_path = Path(extraction_path).resolve()
    if (extraction_path.name != 'summary.json' or not extraction_path.parent.is_relative_to(paths()['run'])
            or not re.fullmatch(r'mobiphysio-pose-[0-9a-f]{8}', extraction_path.parent.name)):
        raise ValueError('Explicit owned pose extraction required')
    source = read_json(extraction_path)
    if (source.get('schema_version') != 'mobiphysio-pose-extraction-1' or source.get('status') != 'completed_pose_extraction'
            or source.get('feature_schema') != FEATURE_SCHEMA or source.get('study') != STUDY
            or source.get('owned_release', {}).get('confirmed') is not True):
        raise ValueError('Completed exact feature schema and confirmed worker release required')
    receipt_path, _, plan_path, plan = verified_download(source['source_receipt'])
    if (source['receipt_sha256'] != file_hash(receipt_path) or source['plan_sha256'] != file_hash(plan_path)
            or source['subject_splits'] != plan['subject_splits'] or len(source['samples']) != len(plan['samples'])):
        raise ValueError('Source permission, full cohort or subject split changed')
    expected = {row['video_name']: row for row in plan['samples']}
    loaded, seen = [], set()
    for row in source['samples']:
        sample = expected.get(row['video_name'])
        if (sample is None or row['video_name'] in seen or row['subject_id'] != sample['subject_id']
                or row['split'] != sample['split'] or row['score'] != sample['label']
                or row.get('decoded_full_presentable_video') is not True
                or row['decoded_frames'] != row['expected_presentable_frames']
                or row['decoded_frames']+row['explicit_discard_packets'] != row['advertised_frames']):
            raise ValueError('Prediction sequence identity or independent video label changed')
        seen.add(row['video_name'])
        arrays = Path(row['npz']).resolve()
        detail = Path(row['detail']).resolve()
        if (arrays.parent != extraction_path.parent or detail.parent != extraction_path.parent
                or file_hash(arrays) != row['npz_sha256'] or file_hash(detail) != row['detail_sha256']):
            raise ValueError('Owned predictions or feature bytes changed')
        with np.load(arrays, allow_pickle=False) as content:
            x, stamps, mask = (content[key].copy() for key in ('features', 'time_s', 'prediction_mask'))
        if (x.ndim != 2 or x.shape[1] != 69 or stamps.shape != (len(x),) or mask.shape != (len(x),)
                or mask.dtype != np.bool_ or not mask.any() or not np.isfinite(x).all()
                or not np.isfinite(stamps).all() or not (np.diff(stamps) > 0).all()
                or row['sampled_frames'] != len(x) or row['usable_frames'] != int(mask.sum())):
            raise ValueError('Invalid temporal arrays or usable-prediction mask')
        loaded.append(dict(meta=row, x=x.astype(np.float32), mask=mask, y=float(row['score']['value'])))
    return extraction_path, source, loaded


def train_quality(extraction_path):
    with heavy_compute():
        output = paths()['run'] / ('mobiphysio-quality-'+uuid4().hex[:8])
        output.mkdir()
        write_json(output/'status.json', dict(status='running', source_extraction=str(extraction_path),
                                             product_enabled=False, started_at=utc_now()))
        try:
            result = _train_quality(extraction_path, output)
            write_json(output/'status.json', dict(status='completed_offline_video_quality', completed_at=utc_now()))
            return result
        except BaseException as exc:
            write_json(output/'status.json', dict(status='failed_offline_quality', error_type=type(exc).__name__,
                                                 error=str(exc), product_enabled=False, completed_at=utc_now()))
            raise


def _train_quality(extraction_path, output):
    import torch
    from torch import nn
    from .models import CausalTCN
    path, source, samples = load_extraction(extraction_path)
    torch.set_num_threads(CONFIG['cpu_threads'])
    torch.manual_seed(SEED); np.random.seed(SEED); random.seed(SEED)
    write_json(output/'resolved_config.json', CONFIG)
    fingerprint = file_hash(path)
    provenance = dict(git_commit=git('rev-parse', 'HEAD'), source_extraction=str(path), extraction_sha256=fingerprint,
        config_sha256=canonical_hash(CONFIG), model_input='only prediction-derived causal69 features, masks and dt; no identity/filename/score as input',
        label_source='official three-therapist whole-video EAAQ, not frame correctness or clinical dose',
        subject_splits=source['subject_splits'], python=platform.python_version(), device='cpu', seed=SEED,
        dependencies={name: importlib.metadata.version(name) for name in ('numpy', 'torch', 'opencv-python', 'ultralytics', 'av')},
        source_sha256={str(p): file_hash(p) for p in
            (Path(__file__), ROOT/'tools/rehab_ml/models.py', ROOT/'tools/rehab_ml/mobiphysio_pose.py')},
        started_at=utc_now(), product_enabled=False)
    write_json(output/'provenance.json', provenance)
    groups = {name: [i for i, row in enumerate(samples) if row['meta']['split'] == name] for name in ('train', 'val', 'test')}
    if any(len(indices) < 2 for indices in groups.values()):
        raise ValueError('Training, validation and held-out test need at least two independent people each')
    stats = np.stack([video_statistics(row['x']) for row in samples])
    y = np.asarray([row['y'] for row in samples])
    train, val, test = (groups[name] for name in ('train', 'val', 'test'))
    median = float(np.median(y[train]))
    ridge = fit_ridge(stats[train], y[train], CONFIG['ridge_alpha'])
    np.savez_compressed(output/'ridge.npz', **ridge)
    # Population statistics use only training people and usable body-scale frames.
    train_frames = np.concatenate([samples[i]['x'][samples[i]['mask']] for i in train])
    mean, std = train_frames.mean(0), train_frames.std(0)
    std = np.where(std < 1e-6, 1., std)
    target_mean, target_std = float(y[train].mean()), max(float(y[train].std()), 1.)
    targets = torch.tensor((y-target_mean)/target_std, dtype=torch.float32)
    batches = {}
    for name, indices in groups.items():
        max_steps = max(len(samples[i]['x']) for i in indices)
        inputs = torch.zeros((len(indices), max_steps, 69), dtype=torch.float32)
        masks = torch.zeros((len(indices), max_steps), dtype=torch.bool)
        for local, i in enumerate(indices):
            row = samples[i]
            inputs[local, :len(row['x'])] = torch.from_numpy((row['x']-mean)/std)
            masks[local, :len(row['x'])] = torch.from_numpy(row['mask'])
        batches[name] = inputs, masks
    model = CausalTCN(69, channels=CONFIG['tcn_channels'], dropout=CONFIG['dropout'])
    model.head = nn.Linear(CONFIG['tcn_channels'], 1)
    optimizer = torch.optim.AdamW(model.parameters(), lr=CONFIG['lr'], weight_decay=CONFIG['weight_decay'])
    best, stale, logs = float('inf'), 0, []
    best_path = output/'tcn-best.pt'
    started = time.perf_counter()
    for epoch in range(1, CONFIG['max_epochs']+1):
        model.train(); optimizer.zero_grad(set_to_none=True)
        prediction = model(*batches['train']).squeeze(-1)
        loss = ((prediction-targets[train])**2).mean()  # exactly one target per whole video
        if not torch.isfinite(loss): raise ValueError('Nonfinite training loss')
        loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(), CONFIG['clip_grad_norm']); optimizer.step()
        model.eval()
        with torch.inference_mode():
            val_scores = model(*batches['val']).squeeze(-1).numpy()*target_std+target_mean
        val_metrics = metrics(y[val], val_scores)
        logs.append(dict(epoch=epoch, train_video_mse_normalized=float(loss.detach()), validation=val_metrics))
        if val_metrics['mae'] < best:
            best, stale = val_metrics['mae'], 0
            torch.save(dict(state_dict=model.state_dict(), input_dim=69, channels=CONFIG['tcn_channels'], epoch=epoch,
                            mean=torch.from_numpy(mean), std=torch.from_numpy(std), target_mean=target_mean,
                            target_std=target_std, config_sha256=canonical_hash(CONFIG), extraction_sha256=fingerprint), best_path)
        else: stale += 1
        write_json(output/'training_log.json', logs)
        if stale >= CONFIG['patience']: break
    checkpoint = torch.load(best_path, map_location='cpu', weights_only=True)
    model.load_state_dict(checkpoint['state_dict'], strict=True); model.eval()
    # No test prediction was computed above; both configurations were frozen beforehand.
    tcn_scores = np.empty(len(samples))
    with torch.inference_mode():
        for name, indices in groups.items():
            tcn_scores[indices] = model(*batches[name]).squeeze(-1).numpy()*target_std+target_mean
    predictions = dict(train_median=np.full(len(samples), median), standardized_ridge=predict_ridge(ridge, stats), causal_tcn=tcn_scores)
    summary = dict(schema_version='mobiphysio-quality-experiment-1', status='completed_offline_video_quality', run_id=output.name,
        config_sha256=canonical_hash(CONFIG), extraction_sha256=fingerprint, source_extraction=str(path),
        feature_schema=FEATURE_SCHEMA, dataset_version='3.0', videos=len(samples), subject_splits=source['subject_splits'],
        splits={name: len(indices) for name, indices in groups.items()},
        results={name: {split: metrics(y[indices], pred[indices]) for split, indices in groups.items()}
                 for name, pred in predictions.items()},
        tcn_best_epoch=checkpoint['epoch'], epochs_run=len(logs), stopped='early_stopping' if stale >= CONFIG['patience'] else 'max_epochs',
        elapsed_training_s=time.perf_counter()-started, test_evaluations_this_run=1,
        artifacts={name: dict(path=str(p), sha256=file_hash(p)) for name, p in
                   (('ridge', output/'ridge.npz'), ('tcn', best_path), ('training_log', output/'training_log.json'),
                    ('config', output/'resolved_config.json'), ('provenance', output/'provenance.json'))},
        clinical_accuracy=None, product_enabled=False, no_pose_finetuning=True,
        limitations=['24-person single front/full-light slice, one video per person; not a patient validation cohort.',
                     'Uses model predictions, no independent 2D or visibility reference; no pose accuracy metric.',
                     'Offline video-end score, not real-time phase/error/cue, diagnosis, pain or prescription.',
                     'Same fixed test must not be reused to tune this experiment.',
                     'Original YOLO pretraining overlap with this public source has not been independently verified.'])
    rows = [dict(video_name=row['meta']['video_name'], subject_id=row['meta']['subject_id'], split=row['meta']['split'],
                 reference_video_eaaq=row['y'], predicted={name: float(pred[i]) for name, pred in predictions.items()})
            for i, row in enumerate(samples)]
    write_json(output/'predictions.json', rows)
    summary['artifacts']['predictions'] = dict(path=str(output/'predictions.json'), sha256=file_hash(output/'predictions.json'))
    write_json(output/'model-card.json', dict(task='whole_video_eaaq_regression', domain='rgb2d_model_predictions',
        supported='MobiPhysio E01 AF VFL only', license='CC0-1.0; privacy/publicity rights not waived',
        affected_side='unknown', source_annotations='independent video-level therapist CSV',
        forbidden=['clinical diagnosis', 'dose change', 'keypoint truth', 'frame/rep quality', 'cue benefit'],
        product_enabled=False, limitations=summary['limitations']))
    summary['artifacts']['model_card'] = dict(path=str(output/'model-card.json'), sha256=file_hash(output/'model-card.json'))
    if file_hash(path) != fingerprint: raise ValueError('Extraction changed during training')
    summary['completed_at'] = utc_now()
    write_json(output/'summary.json', summary)
    return summary
