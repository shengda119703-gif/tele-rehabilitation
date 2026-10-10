from __future__ import annotations

from collections import Counter
import hashlib
from io import StringIO
import json
import os
from pathlib import Path
import random
import re
import zipfile

import numpy as np

from .common import canonical_hash, file_hash, load_registry, paths, read_json, write_json
from .download import checked_zip, verify

PREPARE_VERSION = 'irds-kinect25-raw-status-nominal30-1'
JOINTS = ['SpineBase', 'SpineMid', 'Neck', 'Head', 'ShoulderLeft', 'ElbowLeft',
          'WristLeft', 'HandLeft', 'ShoulderRight', 'ElbowRight', 'WristRight', 'HandRight',
          'HipLeft', 'KneeLeft', 'AnkleLeft', 'FootLeft', 'HipRight', 'KneeRight',
          'AnkleRight', 'FootRight', 'SpineShoulder', 'HandTipLeft', 'ThumbLeft',
          'HandTipRight', 'ThumbRight']
STATUS = {'NotTracked': 0, 'Inferred': 1, 'Tracked': 2}
FILENAME = re.compile(r'^(\d+)_(\d+)_(\d+)_(\d+)_(\d+)_(.+)\.txt$')


def dataset_root(dataset='intellirehabds'):
    record = load_registry()[dataset]
    return paths()['data'] / dataset / record['version']


def load_prepared():
    directory = dataset_root() / 'prepared'
    value = read_json(directory / 'manifest.json')
    return directory, value


def verify_joint_order(readme):
    match = re.search(r'###Simplified folder(.*?)###DepthImages', readme, flags=re.S)
    if not match:
        raise ValueError('Official joint order section not found')
    names = [line.strip() for line in match[1].splitlines() if line.strip() in JOINTS]
    if names != JOINTS:
        raise ValueError('Official joint order changed; manual mapping review required')


def parse_raw(text):
    lines = text.splitlines()
    if not lines or lines[0].strip() != 'Version0.1':
        raise ValueError('Unknown IRDS RawData schema')
    states, coordinates, source_stamps = [], [], []
    for line in lines[1:]:
        if not line.strip():
            continue
        chunks = re.findall(r'\(([^)]+)\)', line)
        entries = [chunk.split(',') for chunk in chunks]
        if len(entries) != 25 or [entry[0] for entry in entries] != JOINTS:
            raise ValueError('RawData named joint order mismatch')
        if any(len(entry) != 7 or entry[1] not in STATUS for entry in entries):
            raise ValueError('Unknown RawData tracking state or coordinate schema')
        states.append([STATUS[entry[1]] for entry in entries])
        coordinates.append([[float(v) for v in entry[2:5]] for entry in entries])
        # Preserve the raw header; the published README does not define its unit/clock.
        source_stamps.append(line.split(',(', 1)[0].split(','))
    return np.asarray(coordinates, dtype=np.float32), np.asarray(states, dtype=np.uint8), source_stamps


def prepare(actions):
    if sorted(set(actions)) != [4, 5]:
        raise ValueError('First experiment is restricted to official shoulder actions 4/5')
    verify('intellirehabds')
    directory = dataset_root()
    record = load_registry()['intellirehabds']
    readme = (directory / 'raw/readme.txt').read_text(encoding='utf-8-sig')
    verify_joint_order(readme)
    archive_path = directory / 'raw/SkeletonData.zip'
    checked_zip(archive_path)
    output = directory / 'prepared'
    output.mkdir(parents=True, exist_ok=True)
    samples, excluded = [], []
    with zipfile.ZipFile(archive_path) as archive:
        available = set(archive.namelist())
        for member in sorted(available):
            if '/Simplified/' not in member or not member.endswith('.txt'):
                continue
            name = member.rsplit('/', 1)[-1]
            match = FILENAME.fullmatch(name)
            if not match:
                excluded.append(dict(member=member, reason='unrecognized_filename'))
                continue
            subject, date, action, repetition, label = map(int, match.groups()[:5])
            posture = match[6]
            if action not in actions:
                continue
            source = archive.read(member)
            source_sha = hashlib.sha256(source).hexdigest()
            sample_id = 'irds-' + source_sha[:16]
            raw_member = member.replace('/Simplified/', '/RawData/')
            if raw_member not in available:
                raise ValueError('RawData tracking evidence missing for ' + name)
            raw_bytes = archive.read(raw_member)
            coords = np.loadtxt(StringIO(source.decode('utf-8-sig')), delimiter=',', ndmin=2).astype(np.float32)
            if coords.shape[1] != 75 or len(coords) < 4:
                excluded.append(dict(member=member, source_sha256=source_sha, reason='invalid_or_too_short'))
                continue
            coords = coords.reshape(-1, 25, 3)
            raw_coords, states, raw_stamps = parse_raw(raw_bytes.decode('utf-8-sig'))
            if raw_coords.shape != coords.shape or not np.allclose(raw_coords, coords, atol=1e-6, equal_nan=True):
                raise ValueError('RawData/Simplified frame alignment mismatch: ' + name)
            valid = np.isfinite(coords).all(axis=2) & (states == STATUS['Tracked'])
            stamps = np.arange(len(coords), dtype=np.float64) / record['nominal_fps']
            quality = record['quality_mapping'].get(label)
            excluded_reason = None if quality is not None else 'unclassifiable_or_unknown_quality_label'
            # Masks keep inferred joints distinct from observed; no guessed confidence.
            target = output / (sample_id + '.npz')
            temporary = target.with_name(target.name + '.part')
            with temporary.open('wb') as stream:
                np.savez_compressed(stream, coordinates=coords, tracking_state=states,
                                    observed_mask=valid, time_s=stamps)
            os.replace(temporary, target)
            cohort = ('healthy_control' if 101 <= subject <= 107 or 301 <= subject <= 307
                      else 'patient' if 201 <= subject <= 216 else 'patient_partial_217'
                      if subject == 217 else 'unknown')
            sample = dict(sample_id=sample_id, dataset='intellirehabds', dataset_version=record['version'],
                          source_member=member, source_sha256=source_sha,
                          raw_member=raw_member, raw_sha256=hashlib.sha256(raw_bytes).hexdigest(),
                          subject_id=str(subject), recording_id=f'{subject}-{date}', camera_id='kinect-one',
                          source_group_id=f'irds-subject-{subject}', action_id=action,
                          exercise_id='shoulder_abduction', side='left' if action == 4 else 'right',
                          schema_id='kinect25-v1', joint_names=JOINTS, coordinate_space='kinect_camera_3d',
                          coordinate_unit='metre', image_size=None, source_time_basis='nominal_30fps',
                          raw_timestamp_headers_preserved=raw_stamps,
                          raw_timestamp_unit='not_verified', confidence_source='not_provided',
                          tracking_state_source='aligned_RawData_named_joints',
                          quality_label=quality, quality_label_mask=quality is not None,
                          upstream_quality_label=label, label_granularity='whole_repetition',
                          phase_label_mask=False, error_label_mask=False, cue_label_mask=False,
                          label_source='official_filename_CorrectLabel',
                          label_mapping_version='correct1-class0-incorrect2-class1-unknown3-quarantine-1',
                          mapping_version=PREPARE_VERSION, posture=posture, cohort=cohort,
                          posture_is_not_action=True, frames=len(coords), npz=target.name,
                          npz_sha256=file_hash(target), license=record['license'],
                          allowed_tasks=['rep_quality'] if quality is not None else [],
                          exclude_reason=excluded_reason)
            samples.append(sample)
    fingerprint = canonical_hash(dict(version=PREPARE_VERSION, archive_sha256=file_hash(archive_path),
                                      sample_sources=[(s['sample_id'], s['source_sha256'], s['raw_sha256']) for s in samples]))
    manifest = dict(prepare_version=PREPARE_VERSION, data_fingerprint=fingerprint,
                    source_archive_sha256=file_hash(archive_path), readme_sha256=file_hash(directory / 'raw/readme.txt'),
                    license=record['license'], attribution=record['attribution'],
                    samples=samples, excluded=excluded,
                    counts=dict(samples=len(samples), subjects=len({s['subject_id'] for s in samples}),
                                eligible=sum(s['quality_label_mask'] for s in samples),
                                quality_labels=dict(Counter(str(s['upstream_quality_label']) for s in samples)),
                                posture=dict(Counter(s['posture'] for s in samples))),
                    missing_supervision=['frame_phase', 'bodypart_error', 'cue_timing', 'target_RGB_2d_labels'])
    write_json(output / 'manifest.json', manifest)
    # Public source names, no private patient recordings, in this adapter.
    return dict(path=str(output / 'manifest.json'), fingerprint=fingerprint, counts=manifest['counts'],
                excluded=len(excluded), product_enabled=False)


def grouped_split(samples, seed):
    by_cohort = {}
    for sample in samples:
        by_cohort.setdefault(sample['cohort'], set()).add(sample['subject_id'])
    rng = random.Random(seed)
    groups = dict(train=[], val=[], test=[])
    for cohort, subjects in sorted(by_cohort.items()):
        subjects = sorted(subjects, key=int)
        rng.shuffle(subjects)
        # Stratify published cohort, not labels or observed test performance.
        n_test = max(1, round(len(subjects)*.2)) if len(subjects) >= 5 else 0
        n_val = max(1, round(len(subjects)*.2)) if len(subjects) >= 5 else 0
        groups['test'].extend(subjects[:n_test])
        groups['val'].extend(subjects[n_test:n_test+n_val])
        groups['train'].extend(subjects[n_test+n_val:])
    assignment = {subject: name for name, subjects in groups.items() for subject in subjects}
    partitions = {name: sorted(s['sample_id'] for s in samples if s['quality_label_mask']
                              and assignment[s['subject_id']] == name) for name in groups}
    if any(not values for values in partitions.values()):
        raise ValueError('Empty partition; insufficient subject diversity')
    return dict(seed=seed, group='subject_id', subject_groups=groups, samples=partitions,
                policy='cohort-stratified-fixed-subject-60-20-20-no-label-tuning-1')


def split(seed):
    directory, manifest = load_prepared()
    value = grouped_split(manifest['samples'], seed)
    value['data_fingerprint'] = manifest['data_fingerprint']
    value['split_hash'] = canonical_hash(value)
    write_json(directory / 'split.json', value)
    return dict(path=str(directory / 'split.json'), split_hash=value['split_hash'],
                subject_groups=value['subject_groups'], counts={k: len(v) for k, v in value['samples'].items()})
