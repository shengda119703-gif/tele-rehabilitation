"""Reconcile saved RGB experiment evidence; never rerun held-out model inference."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.rehab_ml.common import ROOT, canonical_hash, file_hash, paths, read_json, utc_now, write_json
from tools.rehab_ml.mobiphysio_quality import CONFIG, load_extraction


def check_metrics(reference, predicted, recorded):
    y, p = np.asarray(reference, float), np.asarray(predicted, float)
    if y.ndim != 1 or p.shape != y.shape or not len(y) or not np.isfinite([y, p]).all():
        raise ValueError('Finite paired saved video predictions required')
    absolute = np.abs(p-y)
    squared = (p-y)**2
    variance = float(np.square(y-y.mean()).sum())
    values = dict(videos=len(y), mae=float(absolute.sum()/len(y)),
                  rmse=float(np.sqrt(squared.sum()/len(y))),
                  r2=1.-float(squared.sum())/variance if variance > 0 else None)
    for key, expected in values.items():
        actual = recorded.get(key)
        if expected is None:
            if actual is not None:
                raise ValueError('Undefined R2 must stay null')
        elif isinstance(actual, bool) or not isinstance(actual, (int, float)) or not np.isclose(actual, expected, rtol=1e-9, atol=1e-9):
            raise ValueError('Saved metric does not reconcile: '+key)
    if recorded.get('clipped_predictions') is not False or recorded.get('score_units') != 'EAAQ points on 0–100 scale':
        raise ValueError('Score units or clipping contract changed')
    return values


def verify(experiment, failed_extraction, interrupted_download):
    import torch
    experiment = Path(experiment).resolve()
    if (experiment.name != 'summary.json' or not experiment.parent.is_relative_to(paths()['run'])
            or not re.fullmatch(r'mobiphysio-quality-[0-9a-f]{8}', experiment.parent.name)):
        raise ValueError('Owned completed quality experiment required')
    result = read_json(experiment)
    if result['status'] != 'completed_offline_video_quality' or result['product_enabled'] is not False:
        raise ValueError('Experiment is incomplete or enabled')
    config = read_json(result['artifacts']['config']['path'])
    if config != CONFIG or canonical_hash(config) != result['config_sha256']:
        raise ValueError('Frozen configuration changed')
    for artifact in result['artifacts'].values():
        path = Path(artifact['path']).resolve()
        if path.parent != experiment.parent or file_hash(path) != artifact['sha256']:
            raise ValueError('Owned model, prediction, log or configuration artifact changed')
    extraction_path, extraction, samples = load_extraction(result['source_extraction'])
    if file_hash(extraction_path) != result['extraction_sha256']:
        raise ValueError('Extraction fingerprint changed')
    rows = read_json(result['artifacts']['predictions']['path'])
    if len(rows) != len(samples):
        raise ValueError('Saved prediction population is incomplete')
    for row, sample in zip(rows, samples):
        meta = sample['meta']
        if (row['video_name'] != meta['video_name'] or row['subject_id'] != meta['subject_id']
                or row['split'] != meta['split'] or row['reference_video_eaaq'] != sample['y']):
            raise ValueError('Saved predictions are not paired with the official video label')
    metrics = {}
    for model in config['models']:
        metrics[model] = {}
        for split in ('train', 'val', 'test'):
            selected = [row for row in rows if row['split'] == split]
            metrics[model][split] = check_metrics([row['reference_video_eaaq'] for row in selected],
                [row['predicted'][model] for row in selected], result['results'][model][split])
    if result['test_evaluations_this_run'] != 1:
        raise ValueError('Held-out test evaluation count changed')
    checkpoint = torch.load(result['artifacts']['tcn']['path'], weights_only=True, map_location='cpu')
    train = [sample for sample in samples if sample['meta']['split'] == 'train']
    frame_rows = np.concatenate([s['x'][s['mask']] for s in train])
    expected_mean, expected_std = frame_rows.mean(0), frame_rows.std(0)
    expected_std = np.where(expected_std < 1e-6, 1., expected_std)
    np.testing.assert_allclose(checkpoint['mean'].numpy(), expected_mean, rtol=0, atol=0)
    np.testing.assert_allclose(checkpoint['std'].numpy(), expected_std, rtol=0, atol=0)
    train_scores = np.asarray([s['y'] for s in train])
    if checkpoint['target_mean'] != train_scores.mean() or checkpoint['target_std'] != max(train_scores.std(), 1.):
        raise ValueError('Target normalization did not use training people only')
    logs = read_json(result['artifacts']['training_log']['path'])
    best = min(logs, key=lambda row: row['validation']['mae'])
    if best['epoch'] != checkpoint['epoch'] or best['epoch'] != result['tcn_best_epoch'] or len(logs) != result['epochs_run']:
        raise ValueError('Selected epoch does not match validation log')
    if not np.isclose(best['validation']['mae'], result['results']['causal_tcn']['val']['mae'], atol=1e-5, rtol=0):
        raise ValueError('Frozen checkpoint validation score does not reconcile')
    latencies = []
    for sample in samples:
        detail = read_json(sample['meta']['detail'])
        frames = detail['frames']
        if len(frames) != len(sample['x']) or detail['independent_keypoint_reference'] is not False:
            raise ValueError('Raw prediction granularity changed')
        latencies.extend(row['worker_ms'] for row in frames)
    failed_extraction = [Path(path).resolve() for path in failed_extraction]
    interrupted_download = Path(interrupted_download).resolve()
    failures, interrupted = [read_json(path) for path in failed_extraction], read_json(interrupted_download)
    if not failures or any(f['status'] != 'failed_pose_extraction' or f['owned_release']['confirmed'] is not True for f in failures):
        raise ValueError('Original failed extractions were not preserved')
    if interrupted['status'] != 'running' or interrupted['verified_file_bytes'] >= interrupted['expected_bytes']:
        raise ValueError('Interrupted receipt must not be rewritten as success')
    receipt = Path(extraction['source_receipt'])
    plan = Path(extraction['plan'])
    source_files = dict(plan=plan, complete_download=receipt, interrupted_download=interrupted_download,
        extraction=extraction_path, experiment=experiment)
    source_files.update({f'original_failed_extraction_{i}': path for i, path in enumerate(failed_extraction, 1)})
    source_files.update({name: Path(artifact['path']) for name, artifact in result['artifacts'].items()})
    report = dict(schema_version='mobiphysio-rgb-evidence-audit-1', status='reconciled', audited_at=utc_now(),
        study='exploratory_offline_video_eaaq_regression_not_clinical_validation',
        evidence={f'E{i:03}': dict(name=name, path=str(path), sha256=file_hash(path),
                    agent_checked=True, human_verification='pending', verified_by=None)
                  for i, (name, path) in enumerate(source_files.items(), 1)},
        numeric_facts=dict(N001=dict(videos=len(samples), people=len(samples), splits=result['splits']),
            N002=dict(verified_rgb_bytes=read_json(receipt)['verified_file_bytes']),
            N003=dict(decoded_frames=sum(s['meta']['decoded_frames'] for s in samples),
                      sampled_frames=sum(s['meta']['sampled_frames'] for s in samples),
                      usable_frames=sum(s['meta']['usable_frames'] for s in samples),
                      explicit_discard_packets=sum(s['meta']['explicit_discard_packets'] for s in samples),
                      leading_negative_pts_skipped=sum(s['meta']['skipped_negative_pts'] for s in samples)),
            N004=dict(worker_roundtrip_ms_p50=float(np.quantile(latencies, .5)),
                      worker_roundtrip_ms_p95=float(np.quantile(latencies, .95)),
                      includes_cold=True, includes_decode=False, phone_performance=False)),
        methods=dict(M001='fixed official whole-video labels, all 24 E01 AF VFL people, split before extraction',
            M002='actual PyAV frame PTS matched to non-discard packet PTS relative to explicit stream origin; no nominal repair',
            M003='original YOLO, explicit coordinate transform and unknown masks, causal69 features',
            M004='train-only normalization, validation epoch selection, held-out test predicted once'),
        results=metrics, epochs_run=result['epochs_run'], best_epoch=result['tcn_best_epoch'],
        frozen_config_sha256=result['config_sha256'],
        failures_retained=dict(original_extraction_errors=[f['error'] for f in failures],
                              original_download_verified_bytes=interrupted['verified_file_bytes'],
                              original_download_handle_missing=True),
        safety=dict(product_enabled=False, pose_finetuning=False, independent_2d_reference=False,
                    clinical_accuracy=None, raw_videos_or_keypoints_in_git=False),
        report_gates=dict(submission_ready=False, human_source_verification='pending',
            venue='not_requested_engineering_report', official_reporting_adherence='not_claimed',
            ethics_and_consent='no new human collection; original source statements not independently attested'),
        limitations=result['limitations'])
    write_json(ROOT/'reports/rehab_backend/mobiphysio_rgb_experiment.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', type=Path, required=True)
    parser.add_argument('--failed-extraction', type=Path, required=True, nargs='+')
    parser.add_argument('--interrupted-download', type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.experiment, args.failed_extraction, args.interrupted_download)
    print(json.dumps(dict(status=result['status'], numeric_facts=result['numeric_facts'], results=result['results']), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
