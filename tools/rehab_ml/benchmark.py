from __future__ import annotations

import os
import time

import numpy as np

from .common import ROOT, file_hash, paths, read_json, write_json
from .data import load_prepared
from .features import causal_features


def percentiles(values):
    if not values:
        return dict(n=0, p50_ms=None, p95_ms=None)
    return dict(n=len(values), p50_ms=float(np.quantile(values, .5)),
                p95_ms=float(np.quantile(values, .95)), max_ms=float(max(values)))


def benchmark(run_id):
    if run_id in ('latest', '.', '..') or '/' in run_id or '\\' in run_id:
        raise ValueError('Explicit run ID required')
    # Read declared budgets before running; never change them to match measurements.
    import yaml
    with (ROOT / 'configs/rehab_ml/backend.yaml').open(encoding='utf-8') as stream:
        declared = yaml.safe_load(stream)['performance_predeclared']
    import torch
    from .models import CausalTCN
    torch.set_num_threads(min(4, os.cpu_count() or 1))
    run = paths()['run'] / run_id
    card = read_json(run / 'model-card.json')
    checkpoint = run / card['artifact']
    if card['model'] != 'causal_tcn' or file_hash(checkpoint) != card['artifact_sha256']:
        raise ValueError('Verified causal TCN required')
    value = torch.load(checkpoint, map_location='cpu', weights_only=True)
    model = CausalTCN(value['input_dim']).eval()
    model.load_state_dict(value['state_dict'], strict=True)
    directory, prepared = load_prepared()
    # Deterministic small real sample, not chosen by measured timing/quality.
    sample = next(s for s in prepared['samples'] if s['quality_label_mask'])
    with np.load(directory / sample['npz'], allow_pickle=False) as arrays:
        coords, masks, stamps, states = (arrays[k] for k in ('coordinates', 'observed_mask', 'time_s', 'tracking_state'))
    feature_ms, model_ms, total_ms = [], [], []
    with torch.inference_mode():
        for index in range(110):
            started = time.perf_counter()
            features, times = causal_features(coords, masks, stamps, states, side=sample['side'])
            middle = time.perf_counter()
            normalized = (torch.from_numpy(features)-value['mean'])/value['std']
            model(normalized.unsqueeze(0), torch.ones((1, len(features)), dtype=torch.bool))
            ended = time.perf_counter()
            if index >= 10:
                feature_ms.append(1000*(middle-started))
                model_ms.append(1000*(ended-middle))
                total_ms.append(1000*(ended-started))
    from mobile_rehab.rehab_v2.service import SessionService
    import tempfile
    def resolver(owner, request):
        return dict(plan_id='TEST-benchmark', plan_revision=1, entry_key='shoulder_abduction:left',
                    reference=dict(record_origin='manual', fixture=True),
                    plan=dict(exercise_id='shoulder_abduction', target_reps=1, target_sets=1, submode='training'))
    with tempfile.TemporaryDirectory(dir=paths()['run']) as temporary:
        service = SessionService(os.path.join(temporary, 'benchmark.sqlite3'), resolver, internal_replay=True)
        try:
            sid = service.create('TEST-benchmark', dict(idempotency_key='create', consent=True))['session_id']
            revision = 0
            for i in range(40):
                for operation in ('pause', 'resume'):
                    response = service.control('TEST-benchmark', sid, operation,
                        dict(idempotency_key=operation+str(i), expected_revision=revision))
                    revision = response['revision']
            control = percentiles(service.latencies['control_ms'][1:])
        finally:
            service.close()
    import psutil
    result = dict(run_id=run_id, checkpoint_sha256=card['artifact_sha256'],
                  declared_budgets=declared, benchmark='isolated_cpu_full_rep_feature_and_small_tcn',
                  sample_id=sample['sample_id'], steps=len(features), dimensions=features.shape[1],
                  torch_version=torch.__version__, device='cpu', threads=torch.get_num_threads(),
                  feature=percentiles(feature_ms), temporal=percentiles(model_ms), total=percentiles(total_ms),
                  control=control, rss_bytes=psutil.Process().memory_info().rss,
                  feature_temporal_budget_met=np.quantile(total_ms, .95) <= declared['feature_plus_small_tcn_p95_ms'],
                  control_budget_met=control['p95_ms'] <= declared['control_response_p95_ms'],
                  exclusions=['phone_performance', 'camera_decode', 'pose_inference', 'network',
                              'many_clients', 'live_training_concurrency', 'clinical_accuracy'])
    # Convert NumPy scalar bools, not claiming a phone measurement.
    result['feature_temporal_budget_met'] = bool(result['feature_temporal_budget_met'])
    result['control_budget_met'] = bool(result['control_budget_met'])
    write_json(ROOT / 'reports/rehab_backend/performance.json', result)
    return result
