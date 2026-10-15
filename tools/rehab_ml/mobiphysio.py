"""Verified MobiPhysio 3.0 inventory + video-level EAAQ, not frame supervision."""
from __future__ import annotations

from collections import Counter
import csv
import math
from pathlib import Path
import re
from uuid import uuid4

from .common import ROOT, file_hash, paths, read_json, utc_now, write_json
from .dataverse import load_verified_audit, metadata_file_specs

NAME = re.compile(r'E(0[1-9])_P(\d{2})_A([FLR])_V(FL|ML|LL|LJ|HJ|O|LR)_G([MF])')
HEADER = ['Video Name', 'Judges', 'Primary Factors', '', '', '', 'Control Factors', '', '', 'Assesment Score', '', '', '']
SUBHEADER = ['', '', '1', '2', '3', '4', '1', '2', '3', 'Total Mark', 'On scale of 100', 'Average Score', 'Rounding to 2 Decimal']
NUMERIC_TOLERANCE = 1e-5  # serialization reconciliation, not a clinical cutoff


def video_identity(stem):
    match = NAME.fullmatch(stem)
    if match is None:
        raise ValueError('Video name does not match the reviewed official naming schema')
    exercise, person, view, variation, gender = match.groups()
    if person == '00':
        raise ValueError('Invalid participant code')
    return dict(video_name=stem, exercise='E'+exercise, subject_id='P'+person,
                camera_view={'F': 'front', 'L': 'left_view', 'R': 'right_view'}[view],
                variation=variation, gender_code=gender, affected_side=None,
                protocol_hint='shoulder_abduction' if exercise == '01' else None)


def _number(value, maximum):
    try:
        result = float(value)
    except (ValueError, TypeError) as exc:
        raise ValueError('missing_or_invalid_number') from exc
    if not math.isfinite(result) or not 0 <= result <= maximum:
        raise ValueError('nonfinite_or_out_of_range_number')
    return result


def parse_scores(rows):
    """Retain every group; unknown/inconsistent rows are quarantined, never repaired."""
    rows = iter(rows)
    if next(rows, None) != HEADER or next(rows, None) != SUBHEADER:
        raise ValueError('Unexpected two-row official score-table header')
    groups, current, blank_rows = [], None, 0
    for line, raw in enumerate(rows, 3):
        if not raw or not any(field.strip() for field in raw):
            blank_rows += 1
            continue
        if len(raw) != 13:
            raise ValueError(f'Unexpected score-table width on line {line}')
        row = [field.strip() for field in raw]
        if row[0]:
            current = dict(video_name=row[0], first_line=line, raw_rows=[], reasons=[])
            groups.append(current)
        if current is None:
            raise ValueError('Judge continuation has no preceding video')
        current['raw_rows'].append(row)
    counts = Counter(group['video_name'] for group in groups)
    for group in groups:
        raw_rows, reasons = group.pop('raw_rows'), group['reasons']
        try:
            group.update(video_identity(group['video_name']))
        except ValueError:
            reasons.append('invalid_video_name')
        if counts[group['video_name']] != 1:
            reasons.append('duplicate_video_group')
        judges = [row[1] for row in raw_rows]
        group['judge_count'] = len(raw_rows)
        if len(raw_rows) != 3 or len(set(judges)) != 3 or any(not judge for judge in judges):
            reasons.append('three_distinct_judges_required')
        try:
            parsed = []
            for offset, row in enumerate(raw_rows):
                factors = [_number(value, 1) for value in row[2:9]]
                mark, score = _number(row[9], 7), _number(row[10], 100)
                if abs(sum(factors)-mark) > NUMERIC_TOLERANCE:
                    reasons.append('factor_sum_disagrees_with_total')
                if abs(mark*100/7-score) > NUMERIC_TOLERANCE:
                    reasons.append('scaled_score_disagrees_with_total')
                if offset and (row[11] or row[12]):
                    reasons.append('unexpected_average_on_continuation')
                parsed.append(dict(judge=row[1], primary_factors=factors[:4],
                                   control_factors=factors[4:], total=mark, score=score))
            average = _number(raw_rows[0][11], 100)
            rounded = _number(raw_rows[0][12], 100)
            if abs(sum(item['score'] for item in parsed)/len(parsed)-average) > NUMERIC_TOLERANCE:
                reasons.append('judge_mean_disagrees_with_published_average')
            if abs(average-rounded) > .005+NUMERIC_TOLERANCE:
                reasons.append('rounded_score_disagrees_with_average')
            group.update(judge_scores=parsed, published_average=average, published_rounded=rounded)
        except ValueError as exc:
            reasons.append(str(exc))
        group['reasons'] = sorted(set(reasons))
        group['status'] = 'quarantined' if reasons else 'verified_video_score'
    return groups, blank_rows


def index_scores(metadata_manifest, audit_run):
    audit_run, audit = load_verified_audit(audit_run)
    if audit['published']['version'] != '3.0':
        raise ValueError('This adapter has only reviewed published MobiPhysio 3.0')
    manifest_path = Path(metadata_manifest).resolve()
    owned_root = paths()['data'] / 'mobiphysio' / '3.0'
    if (not manifest_path.parent.is_relative_to(owned_root) or manifest_path.name != 'manifest.json'
            or not re.fullmatch(r'metadata-[0-9a-f]{8}', manifest_path.parent.name)):
        raise ValueError('Select an explicit owned documentation manifest')
    manifest = read_json(manifest_path)
    if (manifest.get('schema_version') != 'dataverse-documentation-fetch-1'
            or manifest.get('status') != 'verified_documentation_download'
            or manifest.get('dataset') != 'mobiphysio' or manifest.get('version') != '3.0'
            or manifest.get('audit_run') != audit_run.name
            or manifest.get('audit_summary_sha256') != file_hash(audit_run / 'summary.json')
            or manifest.get('official_inventory_sha256') != audit['published_inventory_sha256']):
        raise ValueError('Documentation manifest does not match the intact published audit')
    entries = manifest.get('files') or []
    specs = metadata_file_specs(audit, [row['file_id'] for row in entries])
    documents = {}
    for row, spec in zip(entries, specs):
        document = Path(row['path']).resolve()
        if (document.parent != manifest_path.parent or document.name != spec['name']
                or row['filename'] != spec['name'] or document.stat().st_size != spec['bytes']
                or file_hash(document) != row['sha256'] or file_hash(document, 'md5') != spec['md5']):
            raise ValueError('Downloaded documentation bytes or hashes changed')
        suffix = document.suffix.lower()
        if suffix in documents:
            raise ValueError('Duplicate documentation type')
        documents[suffix] = document
    if set(documents) != {'.md', '.csv'}:
        raise ValueError('Both verified README and official score CSV are required')
    with documents['.csv'].open(encoding='utf-8-sig', newline='') as stream:
        groups, blank_rows = parse_scores(csv.reader(stream))
    videos, identities, unknown_inventory = {}, {}, []
    for item in audit['published']['files']:
        if Path(item['filename']).suffix.lower() != '.mp4':
            continue
        stem = Path(item['filename']).stem
        if stem in videos:
            raise ValueError('Ambiguous duplicate official video filename')
        videos[stem] = item
        try:
            identities[stem] = video_identity(stem)
        except ValueError:
            unknown_inventory.append(dict(file_id=item['file_id'], filename=item['filename'],
                                          reason='unreviewed_video_naming_code'))
    for group in groups:
        item = videos.get(group['video_name'])
        if item is None:
            group['reasons'].append('video_missing_from_pinned_inventory')
            group['status'] = 'quarantined'
        else:
            group['file_id'] = item['file_id']
            group['video_checksum'] = item['checksum']
            group['video_bytes'] = item['bytes']
    eligible = [group for group in groups if group['status'] == 'verified_video_score']
    missing_scores = sorted(set(videos)-{group['video_name'] for group in groups})
    root = paths()['run'] / ('mobiphysio-index-'+uuid4().hex[:8])
    root.mkdir()
    index_path = root / 'video_score_index.json'
    write_json(index_path, dict(schema_version='mobiphysio-video-eaaq-1',
                               label_scope='whole_video', groups=groups, missing_scores=missing_scores,
                               unreviewed_inventory=unknown_inventory))
    summary = dict(schema_version='mobiphysio-score-audit-1', run_id=root.name,
                   dataset='mobiphysio', published_version='3.0', readme_declared_version='1.1',
                   official_video_count=len(videos), csv_video_groups=len(groups),
                   reviewed_inventory_count=len(identities), unreviewed_inventory_count=len(unknown_inventory),
                   eligible_video_scores=len(eligible), quarantined_groups=len(groups)-len(eligible),
                   missing_video_scores=len(missing_scores), blank_rows=blank_rows,
                   reviewed_inventory_by_exercise=dict(sorted(Counter(row['exercise'] for row in identities.values()).items())),
                   eligible_by_exercise=dict(sorted(Counter(row['exercise'] for row in eligible).items())),
                   quarantine_reasons=dict(sorted(Counter(reason for row in groups for reason in row['reasons']).items())),
                   eligible_subject_count=len({row['subject_id'] for row in eligible}),
                   reviewed_inventory_subject_count=len({row['subject_id'] for row in identities.values()}),
                   numeric_tolerance=NUMERIC_TOLERANCE, score_scale=[0, 100], label_scope='whole_video',
                   independent_labels_available=['video_eaaq'],
                   unavailable_labels=['2d_keypoint_reference', 'visibility_reference', 'phase', 'error_timing', 'affected_side'],
                   video_downloaded=False, split_created=False, training_performed=False, product_enabled=False,
                   source_manifest_sha256=file_hash(manifest_path),
                   audit_summary_sha256=file_hash(audit_run / 'summary.json'),
                   official_inventory_sha256=audit['published_inventory_sha256'],
                   source_files_sha256={str(path): file_hash(path) for path in
                                        (documents['.md'], documents['.csv'], Path(__file__), ROOT / 'tools/rehab_ml/dataverse.py')},
                   index_path=str(index_path), index_sha256=file_hash(index_path), completed_at=utc_now())
    write_json(root / 'summary.json', summary)
    return summary
