from __future__ import annotations

import os

import numpy as np

from .common import canonical_hash, file_hash, read_json, write_json
from .data import JOINTS, load_prepared

FEATURE_VERSION = 'kinect25-shoulder-causal20hz-1'
SUBSET = ['ShoulderLeft', 'ElbowLeft', 'WristLeft', 'HipLeft', 'KneeLeft', 'AnkleLeft',
          'ShoulderRight', 'ElbowRight', 'WristRight', 'HipRight', 'KneeRight', 'AnkleRight']
INDICES = [JOINTS.index(j) for j in SUBSET]


def causal_features(coordinates, observed_mask, times, states, *, side, hz=20.):
    """Current-frame normalization, backward differences, zero/mask on missing.

    No full-clip statistics or future interpolation in the temporal input. Time
    is nominal for IRDS, not a measurement of actual capture cadence/latency.
    """
    if len(times) < 2 or np.any(np.diff(times) <= 0):
        raise ValueError('Nonmonotonic sample times')
    grid = np.arange(times[0], times[-1]+1e-9, 1./hz)
    ids = np.searchsorted(times, grid, side='right')-1
    coords = coordinates[ids][:, INDICES, :].copy()
    masks = observed_mask[ids][:, INDICES].copy()
    left, right = coordinates[ids, 4], coordinates[ids, 8]
    root = (left+right)/2
    scale = np.linalg.norm(left-right, axis=1)
    root_valid = observed_mask[ids, 4] & observed_mask[ids, 8] & (scale > .03) & np.isfinite(scale)
    masks &= root_valid[:, None]
    coords = (coords-root[:, None, :])/np.maximum(np.nan_to_num(scale, nan=1.), .03)[:, None, None]
    coords[~masks] = 0.
    coords = np.nan_to_num(coords, nan=0., posinf=0., neginf=0.)
    velocity = np.zeros_like(coords)
    velocity_mask = np.zeros_like(masks)
    for i in range(1, len(grid)):
        dt = times[ids[i]]-times[ids[i-1]]
        if dt > 0:
            velocity_mask[i] = masks[i] & masks[i-1]
            velocity[i] = (coords[i]-coords[i-1])/dt
            velocity[i][~velocity_mask[i]] = 0.
    velocities = np.clip(velocity, -20., 20.)
    angles, angle_mask = [], []
    for offset in (0, 6):
        arm = coords[:, offset+1]-coords[:, offset]
        norm = np.linalg.norm(arm, axis=1)
        valid = masks[:, offset] & masks[:, offset+1] & (norm > 1e-6)
        angle = np.arccos(np.clip(-arm[:, 1]/np.maximum(norm, 1e-6), -1., 1.))/np.pi
        angle[~valid] = 0.
        angles.append(angle)
        angle_mask.append(valid.astype(np.float32))
    source_age = (grid-times[ids])[:, None]
    fresh = np.r_[True, ids[1:] != ids[:-1]][:, None]
    tracking_known = np.ones_like(masks, dtype=np.float32)
    source_state = states[ids][:, INDICES].astype(np.float32)/2.
    action_side = np.tile([1., 0.] if side == 'left' else [0., 1.], (len(grid), 1))
    features = np.concatenate([coords.reshape(len(grid), -1), velocities.reshape(len(grid), -1),
                               masks.astype(np.float32), velocity_mask.astype(np.float32),
                               tracking_known, source_state, np.stack(angles, axis=1),
                               np.stack(angle_mask, axis=1), source_age, fresh.astype(np.float32),
                               action_side], axis=1).astype(np.float32)
    return features, grid


def build_features(domain):
    if domain != 'kinect_3d':
        raise ValueError('Unsupported training input domain; no Kinect-to-RGB coercion')
    directory, manifest = load_prepared()
    split = read_json(directory / 'split.json')
    if split['data_fingerprint'] != manifest['data_fingerprint']:
        raise ValueError('Stale split')
    output = directory / 'features'
    output.mkdir(exist_ok=True)
    items = []
    for sample in manifest['samples']:
        if not sample['quality_label_mask']:
            continue
        source = directory / sample['npz']
        if file_hash(source) != sample['npz_sha256']:
            raise ValueError('Prepared sample changed')
        with np.load(source, allow_pickle=False) as archive:
            features, times = causal_features(archive['coordinates'], archive['observed_mask'],
                                              archive['time_s'], archive['tracking_state'], side=sample['side'])
        target = output / (sample['sample_id'] + '.npz')
        temporary = target.with_name(target.name + '.part')
        with temporary.open('wb') as stream:
            np.savez_compressed(stream, features=features, time_s=times)
        os.replace(temporary, target)
        items.append(dict(sample_id=sample['sample_id'], file=target.name,
                          sha256=file_hash(target), steps=len(features), dimensions=features.shape[1]))
    fingerprint = canonical_hash(dict(data=manifest['data_fingerprint'], split=split['split_hash'],
                                      version=FEATURE_VERSION, input_domain=domain,
                                      files=[(i['sample_id'], i['sha256']) for i in items]))
    value = dict(feature_version=FEATURE_VERSION, input_domain=domain, coordinate_space='kinect_camera_3d',
                 data_fingerprint=manifest['data_fingerprint'], split_hash=split['split_hash'],
                 feature_fingerprint=fingerprint, hz=20, files=items,
                 normalization='per-current-frame-shoulder-midpoint-and-width',
                 velocity='backward-observed-difference-with-mask',
                 missing='zero-value-explicit-mask-state-age-not-observed',
                 timing='nominal_30fps_causal_floor_to20hz', after_end_head_only=True,
                 disabled_heads=['phase', 'bodypart_error', 'cue_timing'], product_enabled=False)
    write_json(output / 'manifest.json', value)
    return dict(path=str(output / 'manifest.json'), fingerprint=fingerprint, samples=len(items),
                dimensions=items[0]['dimensions'])


def full_clip_statistics(features):
    """Offline, after repetition end only. Never emitted as a realtime metric."""
    return np.concatenate([features.mean(0), features.std(0), features.min(0), features.max(0),
                           np.quantile(features, .5, axis=0), np.quantile(features, .9, axis=0),
                           features[-1]-features[0], np.array([len(features)/20.])]).astype(np.float32)
