"""Bounded official CC0 E01 RGB cohort, split before any pose or features."""
from __future__ import annotations

import csv
from pathlib import Path
import random
import re
import shutil
from uuid import uuid4

from .common import ROOT, canonical_hash, file_hash, git, paths, read_json, utc_now, write_json
from .dataverse import BASE, load_verified_audit, metadata_file_specs
from .mobiphysio import parse_scores, video_identity

SEED = 20261011
MAX_BYTES = 800_000_000
RESERVE_BYTES = 256_000_000
DERIVED_BUDGET_BYTES = 128_000_000
STUDY = 'mobiphysio_e01_front_fl_video_quality_v1'


def select_cohort(groups, published, *, seed=SEED):
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError('A bounded integer split seed is required')
    files = {row['file_id']: row for row in published['files']}
    selected, subjects = [], set()
    for row in groups:
        if (row.get('status') != 'verified_video_score' or row.get('exercise') != 'E01'
                or row.get('camera_view') != 'front' or row.get('variation') != 'FL'):
            continue
        identity = video_identity(row['video_name'])
        if (identity['exercise'] != 'E01' or identity['camera_view'] != 'front'
                or identity['variation'] != 'FL' or row['subject_id'] != identity['subject_id']):
            raise ValueError('Score identity does not match the reviewed video name')
        item = files.get(row.get('file_id'))
        if (item is None or item['filename'] != row['video_name']+'.mp4'
                or item['checksum'] != row.get('video_checksum') or item['bytes'] != row.get('video_bytes')):
            raise ValueError('Scored video differs from the fixed official inventory')
        if (item.get('restricted') is not False or item.get('embargo')
                or item.get('access_status') != 'unrestricted_metadata' or item.get('tabular_data') is not False):
            raise PermissionError('No restricted, embargoed or converted RGB files')
        if (not 0 < item['bytes'] <= 150_000_000 or item['checksum']['algorithm'] != 'md5'
                or re.fullmatch(r'E01_P\d{2}_AF_VFL_G[MF]\.mp4', item['filename']) is None):
            raise ValueError('RGB filename, checksum or per-file size budget not verified')
        if identity['subject_id'] in subjects:
            raise ValueError('One scored front-FL video per subject is required')
        subjects.add(identity['subject_id'])
        selected.append(dict(video_name=row['video_name'], subject_id=identity['subject_id'],
            exercise='E01', camera_view='front', variation='FL', affected_side=None,
            file_id=item['file_id'], filename=item['filename'], bytes=item['bytes'],
            md5=item['checksum']['value'], url=f'{BASE}/access/datafile/{item["file_id"]}',
            label=dict(value=row['published_average'], mask=True, granularity='whole_video_eaaq',
                       source='official_three_physiotherapist_score_csv'),
            unavailable_labels=['phase', 'keypoint_reference', 'visibility_reference', 'error_timing', 'pain']))
    if not 10 <= len(selected) <= 64 or sum(row['bytes'] for row in selected) > MAX_BYTES:
        raise ValueError('Cohort requires 10–64 people and at most 800 MB; no silent subsampling')
    people = sorted(subjects)
    random.Random(seed).shuffle(people)
    train_n, val_n = round(.6*len(people)), round(.2*len(people))
    splits = {person: 'train' if i < train_n else 'val' if i < train_n+val_n else 'test'
              for i, person in enumerate(people)}
    for row in selected:
        row['split'] = splits[row['subject_id']]
    return sorted(selected, key=lambda row: row['subject_id']), {name: sorted(p for p, s in splits.items() if s == name)
                                                               for name in ('train', 'val', 'test')}


def reviewed_sources(index_run, audit_run):
    audit_run, audit = load_verified_audit(audit_run)
    if audit['published']['version'] != '3.0':
        raise ValueError('Only reviewed MobiPhysio 3.0 is enabled')
    document_specs = metadata_file_specs(audit, [13453294, 13453292])
    index_run = Path(index_run).resolve()
    if not index_run.is_relative_to(paths()['run']) or not re.fullmatch(r'mobiphysio-index-[0-9a-f]{8}', index_run.name):
        raise ValueError('Explicit owned score index required')
    summary = read_json(index_run / 'summary.json')
    index_path = (index_run / 'video_score_index.json').resolve()
    if (summary.get('schema_version') != 'mobiphysio-score-audit-1'
            or summary.get('dataset') != 'mobiphysio' or summary.get('published_version') != '3.0'
            or summary.get('audit_summary_sha256') != file_hash(audit_run / 'summary.json')
            or summary.get('official_inventory_sha256') != audit['published_inventory_sha256']
            or summary.get('index_sha256') != file_hash(index_path)):
        raise ValueError('Score index does not match the fixed audit')
    docs = {Path(path).suffix.lower(): Path(path).resolve() for path in summary['source_files_sha256']
            if Path(path).suffix.lower() in ('.md', '.csv')}
    if set(docs) != {'.md', '.csv'} or docs['.md'].parent != docs['.csv'].parent:
        raise ValueError('Both original documentation files required')
    root = docs['.md'].parent
    if (not root.is_relative_to(paths()['data'] / 'mobiphysio' / '3.0')
            or not re.fullmatch(r'metadata-[0-9a-f]{8}', root.name)
            or file_hash(root / 'manifest.json') != summary['source_manifest_sha256']):
        raise ValueError('Documentation ownership or manifest fingerprint changed')
    for spec in document_specs:
        path = root / spec['name']
        if (path.stat().st_size != spec['bytes'] or file_hash(path, 'md5') != spec['md5']
                or file_hash(path) != summary['source_files_sha256'].get(str(path))):
            raise ValueError('Official documentation bytes changed')
    with docs['.csv'].open(encoding='utf-8-sig', newline='') as stream:
        parsed, _ = parse_scores(csv.reader(stream))
    official_scores = {row['video_name']: row for row in parsed if row['status'] == 'verified_video_score'}
    index = read_json(index_path)
    if index.get('schema_version') != 'mobiphysio-video-eaaq-1' or index.get('label_scope') != 'whole_video':
        raise ValueError('Unexpected label granularity')
    for row in index['groups']:
        if row.get('status') == 'verified_video_score':
            source = official_scores.get(row['video_name'])
            if source is None or source['published_average'] != row['published_average']:
                raise ValueError('Index score does not equal the independently reread official table')
    return audit_run, audit, index_run, summary, index


def plan_cohort(index_run, audit_run):
    audit_run, audit, index_run, summary, index = reviewed_sources(index_run, audit_run)
    selected, splits = select_cohort(index['groups'], audit['published'])
    root = paths()['data'] / 'mobiphysio' / '3.0' / ('rgb-e01-front-fl-'+uuid4().hex[:8])
    root.mkdir(parents=True)
    total = sum(row['bytes'] for row in selected)
    available = shutil.disk_usage(root).free
    if available < total+RESERVE_BYTES+DERIVED_BUDGET_BYTES:
        raise OSError('Insufficient space for all selected videos, derived budget and 256 MB reserve')
    result = dict(schema_version='mobiphysio-rgb-cohort-1', study=STUDY, status='planned',
        published_version='3.0', source_audit=str(audit_run), source_index=str(index_run),
        audit_summary_sha256=file_hash(audit_run / 'summary.json'), score_summary_sha256=file_hash(index_run / 'summary.json'),
        score_index_sha256=summary['index_sha256'], official_inventory_sha256=audit['published_inventory_sha256'],
        selection='all eligible E01, AF front, VFL full-light; exactly one video per person; not chosen by score or prediction',
        seed=SEED, split_before_features=True, subject_splits=splits, samples=selected,
        expected_bytes=total, disk_free_before=available, max_download_bytes=MAX_BYTES,
        reserve_bytes=RESERVE_BYTES, derived_budget_bytes=DERIVED_BUDGET_BYTES,
        license=audit['published']['license'], usage_scope='offline_video_eaaq_research',
        training_heads_allowed=['whole_video_eaaq'], product_enabled=False,
        forbidden_uses=['phase_truth', 'pose_ground_truth', 'cue_timing', 'pain', 'prescription', 'diagnosis'],
        implementation_sha256={str(path): file_hash(path) for path in
            (Path(__file__), ROOT/'tools/rehab_ml/mobiphysio.py', ROOT/'tools/rehab_ml/dataverse.py')},
        git_commit=git('rev-parse', 'HEAD'), created_at=utc_now())
    target = root / 'plan.json'
    write_json(target, result)
    return dict(plan=str(target), plan_sha256=file_hash(target), videos=len(selected), expected_bytes=total,
                splits={name: len(people) for name, people in splits.items()}, product_enabled=False)


def load_plan(plan_path):
    plan_path = Path(plan_path).resolve()
    if (plan_path.name != 'plan.json' or not plan_path.parent.is_relative_to(paths()['data']/'mobiphysio'/'3.0')
            or not re.fullmatch(r'rgb-e01-front-fl-[0-9a-f]{8}', plan_path.parent.name)):
        raise ValueError('Explicit owned RGB cohort plan required')
    plan = read_json(plan_path)
    if (plan.get('schema_version') != 'mobiphysio-rgb-cohort-1' or plan.get('study') != STUDY
            or plan.get('seed') != SEED or plan.get('split_before_features') is not True
            or plan.get('published_version') != '3.0' or plan.get('status') != 'planned'
            or plan.get('max_download_bytes') != MAX_BYTES or plan.get('reserve_bytes') != RESERVE_BYTES
            or plan.get('derived_budget_bytes') != DERIVED_BUDGET_BYTES
            or plan.get('training_heads_allowed') != ['whole_video_eaaq']):
        raise ValueError('Unexpected study, scope or split contract')
    _, audit, _, summary, index = reviewed_sources(plan['source_index'], plan['source_audit'])
    selected, splits = select_cohort(index['groups'], audit['published'])
    if (selected != plan['samples'] or splits != plan['subject_splits']
            or sum(row['bytes'] for row in selected) != plan['expected_bytes']
            or plan.get('official_inventory_sha256') != audit['published_inventory_sha256']
            or plan.get('license') != audit['published']['license']
            or summary['index_sha256'] != plan['score_index_sha256']
            or file_hash(Path(plan['source_index'])/'summary.json') != plan['score_summary_sha256']
            or file_hash(Path(plan['source_audit'])/'summary.json') != plan['audit_summary_sha256']
            or plan.get('usage_scope') != 'offline_video_eaaq_research'
            or plan.get('product_enabled') is not False):
        raise ValueError('Immutable selection, score or group split changed')
    return plan_path, plan


def fetch_cohort(plan_path):
    from .download import download_file
    plan_path, plan = load_plan(plan_path)
    receipt = plan_path.parent / ('download-'+uuid4().hex[:8]+'.json')
    result = dict(schema_version='mobiphysio-rgb-download-1', status='running',
                  plan=str(plan_path), plan_sha256=file_hash(plan_path), files=[], expected_bytes=plan['expected_bytes'],
                  verified_file_bytes=0, network_bytes=None, product_enabled=False, training_performed=False,
                  started_at=utc_now(), implementation_sha256=file_hash(__file__))
    write_json(receipt, result)
    try:
        for sample in plan['samples']:
            result['current_file_id'] = sample['file_id']
            write_json(receipt, result)
            row = download_file(sample, plan_path.parent / sample['filename'])
            result['files'].append(dict(file_id=sample['file_id'], subject_id=sample['subject_id'],
                                        split=sample['split'], **row))
            result['verified_file_bytes'] = sum(item['bytes'] for item in result['files'])
            write_json(receipt, result)
            print(f"RGB verified {len(result['files'])}/{len(plan['samples'])}: {sample['filename']}", flush=True)
        result['status'] = 'verified_rgb_download'
    except Exception as exc:
        result.update(status='blocked_rgb_download', error_type=type(exc).__name__, error=str(exc))
    result.update(receipt=str(receipt), completed_at=utc_now())
    write_json(receipt, result)
    return result
