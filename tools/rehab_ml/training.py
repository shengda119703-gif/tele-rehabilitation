from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import time
from uuid import uuid4

import numpy as np
import yaml

from .common import ROOT, canonical_hash, file_hash, git, paths, read_json, write_json
from .data import load_prepared
from .features import FEATURE_VERSION, full_clip_statistics


def metrics(labels, probabilities):
    y = np.asarray(labels, dtype=int)
    p = np.asarray(probabilities, dtype=float)
    predicted = (p >= .5).astype(int)
    confusion = np.zeros((2, 2), dtype=int)
    for actual, estimate in zip(y, predicted):
        confusion[actual, estimate] += 1
    f1, recall, precision = [], [], []
    for cls in (0, 1):
        tp = confusion[cls, cls]
        fp = confusion[:, cls].sum()-tp
        fn = confusion[cls, :].sum()-tp
        f1.append(float(2*tp/max(1, 2*tp+fp+fn)))
        recall.append(float(tp/max(1, tp+fn)))
        precision.append(float(tp/max(1, tp+fp)))
    positive, negative = p[y == 1], p[y == 0]
    auc = (float(((positive[:, None] > negative[None, :]).sum()
                  + .5*(positive[:, None] == negative[None, :]).sum())/(len(positive)*len(negative)))
           if len(positive) and len(negative) else None)
    return dict(samples=len(y), confusion_matrix=confusion.tolist(), classes=['correct', 'incorrect'],
                positive_class='incorrect', macro_f1=float(np.mean(f1)),
                balanced_accuracy=float(np.mean(recall)) if len(positive) and len(negative) else None,
                accuracy=float(np.mean(predicted == y)), precision_incorrect=precision[1],
                recall_incorrect=recall[1], f1_incorrect=f1[1], roc_auc=auc,
                decision_threshold=.5)


def evaluation_report(records, probabilities, majority, seed):
    labels = [record['quality_label'] for record in records]
    result = dict(overall=metrics(labels, probabilities),
                  majority_baseline=metrics(labels, [float(majority)]*len(records)),
                  subjects={}, cohort={}, posture={},
                  uncertainty_method='subject-cluster bootstrap 500 draws; not clinical validation')
    for field, key in [('subject_id', 'subjects'), ('cohort', 'cohort'), ('posture', 'posture')]:
        for value in sorted({record[field] for record in records}):
            ids = [i for i, record in enumerate(records) if record[field] == value]
            result[key][value] = metrics([labels[i] for i in ids], [probabilities[i] for i in ids])
    rng = np.random.default_rng(seed)
    subjects = sorted(result['subjects'])
    boot = []
    for _ in range(500):
        drawn = rng.choice(subjects, size=len(subjects), replace=True)
        indices = [i for subject in drawn for i, record in enumerate(records) if record['subject_id'] == subject]
        boot.append(metrics([labels[i] for i in indices], [probabilities[i] for i in indices])['macro_f1'])
    result['macro_f1_subject_bootstrap_95_interval'] = np.quantile(boot, [.025, .975]).tolist()
    return result


def load_dataset():
    directory, data = load_prepared()
    split = read_json(directory / 'split.json')
    features = read_json(directory / 'features/manifest.json')
    if (features['feature_version'] != FEATURE_VERSION or features['input_domain'] != 'kinect_3d'
            or split['data_fingerprint'] != data['data_fingerprint']
            or features['split_hash'] != split['split_hash']):
        raise ValueError('Dataset/preprocess/split fingerprint mismatch')
    by_id = {sample['sample_id']: sample for sample in data['samples']}
    arrays = {}
    for item in features['files']:
        path = directory / 'features' / item['file']
        if file_hash(path) != item['sha256']:
            raise ValueError('Feature checksum changed')
        with np.load(path, allow_pickle=False) as archive:
            arrays[item['sample_id']] = archive['features'].copy()
    groups = {name: [by_id[sid] for sid in ids] for name, ids in split['samples'].items()}
    for name, samples in groups.items():
        if any(not sample['quality_label_mask'] or sample['quality_label'] not in (0, 1) for sample in samples):
            raise ValueError('Unlabeled sample cannot train or evaluate the supervised quality head')
    return data, split, features, groups, arrays


def standardizer(values):
    mean, std = values.mean(0), values.std(0)
    std = np.where(std < 1e-5, 1., std)
    return mean.astype(np.float32), std.astype(np.float32)


def probability(values):
    return 1./(1.+np.exp(-np.clip(values, -40., 40.)))


def train_baseline(config, groups, arrays, run):
    matrix = {name: np.stack([full_clip_statistics(arrays[s['sample_id']]) for s in records])
              for name, records in groups.items()}
    mean, std = standardizer(matrix['train'])
    matrix = {name: (value-mean)/std for name, value in matrix.items()}
    y = np.array([s['quality_label'] for s in groups['train']], dtype=np.float32)
    counts = np.bincount(y.astype(int), minlength=2)
    if not counts.all():
        raise ValueError('Both classes required in train partition')
    weights = len(y)/(2*counts)
    sample_weights = weights[y.astype(int)]
    w, b = np.zeros(matrix['train'].shape[1]), 0.
    m, v, mb, vb = np.zeros_like(w), np.zeros_like(w), 0., 0.
    best, best_epoch, patience, history = -1., 0, 0, []
    for epoch in range(1, config['max_epochs']+1):
        p = probability(matrix['train']@w+b)
        error = (p-y)*sample_weights
        gradient = matrix['train'].T@error/len(y)+config['l2']*w
        gb = float(error.mean())
        m, v = .9*m+.1*gradient, .999*v+.001*gradient**2
        mb, vb = .9*mb+.1*gb, .999*vb+.001*gb**2
        w -= config['learning_rate']*(m/(1-.9**epoch))/(np.sqrt(v/(1-.999**epoch))+1e-8)
        b -= config['learning_rate']*(mb/(1-.9**epoch))/(np.sqrt(vb/(1-.999**epoch))+1e-8)
        val_probability = probability(matrix['val']@w+b)
        val = metrics([s['quality_label'] for s in groups['val']], val_probability)
        loss = float((-sample_weights*(y*np.log(p+1e-8)+(1-y)*np.log(1-p+1e-8))).mean()
                     + .5*config['l2']*(w*w).sum())
        history.append(dict(epoch=epoch, loss=loss, val_macro_f1=val['macro_f1']))
        if val['macro_f1'] > best+1e-8:
            best, best_epoch, patience = val['macro_f1'], epoch, 0
            np.savez(run / 'checkpoint.npz', weights=w, bias=np.array(b), mean=mean, std=std)
        else:
            patience += 1
        if patience >= config['patience']:
            break
    return dict(history=history, best_epoch=best_epoch, val_macro_f1=best,
                stop_reason='early_stopping' if patience >= config['patience'] else 'max_epochs',
                checkpoint='checkpoint.npz', class_weights=weights.tolist(), device='cpu_numpy')


def make_batches(records, arrays, mean, std, batch_size, device, *, rng=None):
    import torch
    order = list(range(len(records)))
    if rng:
        rng.shuffle(order)
    for start in range(0, len(order), batch_size):
        chosen = [records[i] for i in order[start:start+batch_size]]
        sequences = [(arrays[s['sample_id']]-mean)/std for s in chosen]
        lengths = [len(s) for s in sequences]
        padded = np.zeros((len(chosen), max(lengths), len(mean)), dtype=np.float32)
        mask = np.zeros((len(chosen), max(lengths)), dtype=bool)
        for i, sequence in enumerate(sequences):
            padded[i, :len(sequence)], mask[i, :len(sequence)] = sequence, True
        yield chosen, torch.from_numpy(padded).to(device), torch.from_numpy(mask).to(device)


def tcn_predict(model, records, arrays, mean, std, device):
    import torch
    model.eval()
    result = []
    with torch.inference_mode():
        for _, batch, mask in make_batches(records, arrays, mean, std, 16, device):
            result.extend(torch.softmax(model(batch, mask), 1)[:, 1].cpu().tolist())
    return result


def train_tcn(config, groups, arrays, run):
    os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
    import torch
    from .models import CausalTCN, masked_cross_entropy
    if (config['channels'] != 64 or config['dilations'] != [1, 2, 4, 8]
            or config['receptive_field_steps'] != 61 or config['normalization'] != 'per_timestep_layer_norm'):
        raise ValueError('Unreviewed temporal architecture configuration')
    torch.manual_seed(config['seed'])
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(min(4, os.cpu_count() or 1))
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    values = np.concatenate([arrays[s['sample_id']] for s in groups['train']])
    mean, std = standardizer(values)
    model = CausalTCN(len(mean), config['channels'], config['dropout']).to(device)
    counts = np.bincount([s['quality_label'] for s in groups['train']], minlength=2)
    if not counts.all():
        raise ValueError('Both classes required in train partition')
    class_weights = len(groups['train'])/(2*counts)
    weights = torch.tensor(class_weights, dtype=torch.float32, device=device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=config['learning_rate'], weight_decay=config['weight_decay'])
    rng = random.Random(config['seed'])
    best, best_epoch, patience, history = -1., 0, 0, []
    for epoch in range(1, config['max_epochs']+1):
        model.train()
        losses = []
        for chosen, batch, mask in make_batches(groups['train'], arrays, mean, std, config['batch_size'], device, rng=rng):
            labels = torch.tensor([s['quality_label'] for s in chosen], dtype=torch.long, device=device)
            label_mask = torch.tensor([s['quality_label_mask'] for s in chosen], dtype=torch.bool, device=device)
            optimizer.zero_grad(set_to_none=True)
            logits = model(batch, mask)
            loss = masked_cross_entropy(logits, labels, label_mask, weights)
            if not torch.isfinite(loss):
                raise ValueError('Nonfinite training loss')
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), config['grad_clip'])
            optimizer.step()
            losses.append(float(loss.detach().cpu()))
        predictions = tcn_predict(model, groups['val'], arrays, mean, std, device)
        val = metrics([s['quality_label'] for s in groups['val']], predictions)
        history.append(dict(epoch=epoch, loss=float(np.mean(losses)), val_macro_f1=val['macro_f1']))
        if val['macro_f1'] > best+1e-8:
            best, best_epoch, patience = val['macro_f1'], epoch, 0
            torch.save(dict(state_dict={k: v.detach().cpu() for k, v in model.state_dict().items()},
                            input_dim=len(mean), mean=torch.from_numpy(mean), std=torch.from_numpy(std)), run / 'checkpoint.pt')
        else:
            patience += 1
        # Incremental logs survive interruption; test partition is not touched during training.
        write_json(run / 'training-progress.json', dict(epoch=epoch, best_epoch=best_epoch, history=history))
        if patience >= config['patience']:
            break
    return dict(history=history, best_epoch=best_epoch, val_macro_f1=best,
                stop_reason='early_stopping' if patience >= config['patience'] else 'max_epochs',
                checkpoint='checkpoint.pt', class_weights=class_weights.tolist(), device=device,
                device_name=torch.cuda.get_device_name(0) if device == 'cuda' else 'CPU',
                peak_allocated_bytes=torch.cuda.max_memory_allocated() if device == 'cuda' else None,
                parameters=sum(p.numel() for p in model.parameters()), receptive_field_steps=61)


def train(config_path):
    with Path(config_path).open(encoding='utf-8') as stream:
        config = yaml.safe_load(stream)
    if (config['input_domain'] != 'kinect_3d' or config['product_enabled']
            or not config['after_end_only'] or config['disabled_heads'] != ['phase', 'bodypart_error', 'cue_timing']):
        raise ValueError('Unsupported task/domain or unsafe product activation')
    random.seed(config['seed'])
    np.random.seed(config['seed'])
    data, split, feature_manifest, groups, arrays = load_dataset()
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+config['model']+'-'+uuid4().hex[:8]
    run = paths()['run'] / run_id
    run.mkdir()
    started = time.perf_counter()
    write_json(run / 'resolved-config.json', config)
    with (run / 'environment.lock.txt').open('w', encoding='utf-8') as lock:
        subprocess.run([sys.executable, '-m', 'pip', 'freeze'], stdout=lock,
                       check=True, text=True, timeout=30)
    record = dict(run_id=run_id, git_commit=git('rev-parse', 'HEAD'),
                  dirty_paths=git('status', '--porcelain', '-uall').splitlines(),
                  config_sha256=file_hash(config_path), seed=config['seed'], model=config['model'],
                  data_fingerprint=data['data_fingerprint'], split_hash=split['split_hash'],
                  feature_fingerprint=feature_manifest['feature_fingerprint'],
                  feature_version=FEATURE_VERSION, environment_lock_sha256=file_hash(run / 'environment.lock.txt'),
                  python=sys.executable, source_archive_sha256=data['source_archive_sha256'],
                  subject_groups=split['subject_groups'],
                  split_class_counts={name: dict(Counter(str(s['quality_label']) for s in samples))
                                      for name, samples in groups.items()},
                  majority_class=int(np.bincount([s['quality_label'] for s in groups['train']]).argmax()),
                  license=data['license'], attribution=data['attribution'], product_enabled=False)
    record['source_code_hashes'] = {name: file_hash(ROOT / name) for name in (
        'tools/rehab_ml/common.py', 'tools/rehab_ml/data.py', 'tools/rehab_ml/features.py',
        'tools/rehab_ml/models.py', 'tools/rehab_ml/training.py')}
    write_json(run / 'provenance.json', record)
    try:
        result = train_baseline(config, groups, arrays, run) if config['model'] == 'logistic_regression' else train_tcn(config, groups, arrays, run)
        result['elapsed_s'] = time.perf_counter()-started
        write_json(run / 'training.json', result)
        checkpoint = run / result['checkpoint']
        card = dict(model_id=run_id, role='rep_quality_candidate', model=config['model'],
                    artifact=result['checkpoint'], artifact_sha256=file_hash(checkpoint),
                    input_domain='kinect_3d', schema_id='kinect25-v1', coordinate_space='kinect_camera_3d',
                    feature_version=FEATURE_VERSION, data_fingerprint=record['data_fingerprint'],
                    split_hash=record['split_hash'], after_end_only=True, product_enabled=False,
                    deployment_status='offline_research_only', license=record['license'],
                    license_status='verified_dataset_license', attribution=record['attribution'],
                    actions=['shoulder_abduction'], sides=['left', 'right'],
                    camera_views=['kinect_recording_only'], protocol_versions=['irds-rep-label-1'],
                    unavailable_heads=['phase', 'bodypart_error', 'cue_timing'],
                    limitations=['No YOLO/MediaPipe/mobile domain validation',
                                 'Whole-repetition correctness is not clinical quality or diagnosis',
                                 'Small grouped test set; class and posture/cohort confounding'],
                    training=result)
        write_json(run / 'model-card.json', card)
        artifact_dir = paths()['model'] / run_id
        artifact_dir.mkdir()
        import shutil
        shutil.copy2(checkpoint, artifact_dir / checkpoint.name)
        write_json(artifact_dir / 'model-card.json', card)
        return dict(run_id=run_id, path=str(run), checkpoint_sha256=card['artifact_sha256'],
                    training={k: v for k, v in result.items() if k != 'history'}, product_enabled=False)
    except Exception as exc:
        write_json(run / 'failure.json', dict(error_type=type(exc).__name__, error=str(exc),
                                             elapsed_s=time.perf_counter()-started))
        raise


def predict_run(run, records, arrays):
    config = read_json(run / 'resolved-config.json')
    card = read_json(run / 'model-card.json')
    checkpoint = run / card['artifact']
    if file_hash(checkpoint) != card['artifact_sha256']:
        raise ValueError('Checkpoint checksum mismatch')
    if config['model'] == 'logistic_regression':
        with np.load(checkpoint, allow_pickle=False) as value:
            features = np.stack([full_clip_statistics(arrays[s['sample_id']]) for s in records])
            return probability(((features-value['mean'])/value['std'])@value['weights']+value['bias']).tolist()
    import torch
    from .models import CausalTCN
    value = torch.load(checkpoint, map_location='cpu', weights_only=True)
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    model = CausalTCN(value['input_dim']).to(device)
    model.load_state_dict(value['state_dict'], strict=True)
    return tcn_predict(model, records, arrays, value['mean'].numpy(), value['std'].numpy(), device)


def evaluate(run_id, partition):
    if not run_id or Path(run_id).name != run_id or run_id in ('.', '..', 'latest'):
        raise ValueError('Explicit, safe run ID required')
    run = paths()['run'] / run_id
    provenance = read_json(run / 'provenance.json')
    data, split, feature_manifest, groups, arrays = load_dataset()
    if (provenance['data_fingerprint'] != data['data_fingerprint']
            or provenance['split_hash'] != split['split_hash']
            or provenance['feature_fingerprint'] != feature_manifest['feature_fingerprint']):
        raise ValueError('Evaluation does not match frozen run data/split/features')
    records = groups[partition]
    probabilities = predict_run(run, records, arrays)
    predictions = [dict(sample_id=sample['sample_id'], subject_id=sample['subject_id'],
                        label=sample['quality_label'], probability_incorrect=float(prob), predicted=int(prob >= .5),
                        cohort=sample['cohort'], posture=sample['posture'], side=sample['side'])
                   for sample, prob in zip(records, probabilities)]
    write_json(run / ('predictions-' + partition + '.json'), predictions)
    report = evaluation_report(records, probabilities, provenance['majority_class'], provenance['seed'])
    report.update(run_id=run_id, partition=partition, split_hash=split['split_hash'],
                  product_enabled=False, clinical_accuracy=None)
    write_json(run / ('evaluation-' + partition + '.json'), report)
    return dict(run_id=run_id, partition=partition, path=str(run / ('evaluation-' + partition + '.json')),
                overall=report['overall'], majority_baseline=report['majority_baseline'],
                macro_f1_subject_bootstrap_95_interval=report['macro_f1_subject_bootstrap_95_interval'],
                product_enabled=False)
