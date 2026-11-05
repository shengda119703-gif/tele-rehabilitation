"""Read-only job/monitor cost audit; sampled extrema are not continuous peaks.

Comfy event timestamps are Unix milliseconds, memory-monitor timestamps are
Unix seconds, and nvidia-smi's local CSV timestamps are Asia/Shanghai (UTC+08
for the supported dates since 1992). No per-node/stage timing is inferred.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import re

VERSION = 'rehab_synthetic_costs/v1'
SHANGHAI = timezone(timedelta(hours=8), 'Asia/Shanghai')


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _snapshot(path):
    path = Path(path).resolve()
    if not path.is_file():
        return None, dict(path=str(path), exists=False, captured_bytes=0, snapshot_sha256=None)
    raw = path.read_bytes()
    return raw, dict(path=str(path), exists=True, captured_bytes=len(raw),
                     snapshot_sha256=hashlib.sha256(raw).hexdigest())


def parse_gpu_timestamp(value):
    stamp = datetime.fromisoformat(value.strip().replace('/', '-'))
    if stamp.tzinfo is not None or stamp.year < 1992:
        raise ValueError('gpu_csv_requires_local_Asia_Shanghai_timestamp_since_1992')
    return stamp.replace(tzinfo=SHANGHAI).timestamp()


def _quantity(value, unit=''):
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r'\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*'+re.escape(unit)+r'\s*', value)
    number = float(match[1]) if match else None
    return number if number is not None and math.isfinite(number) and number >= 0 else None


def read_gpu_samples(path):
    raw, source = _snapshot(path)
    result, rejected = [], []
    if raw is not None:
        reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
        for line, row in enumerate(reader, 2):
            row = {(key or '').strip():value for key,value in row.items()}
            try:
                stamp = parse_gpu_timestamp(row['timestamp'])
            except (ValueError, TypeError, KeyError):
                rejected.append(line)
                continue
            result.append(dict(unix_time=stamp,
                gpu_memory_mib=_quantity(row.get('memory.used [MiB]'), 'MiB'),
                gpu_utilization_percent=_quantity(row.get('utilization.gpu [%]'), '%'),
                gpu_temperature_c=_quantity(row.get('temperature.gpu')),
                gpu_power_w=_quantity(row.get('power.draw [W]'), 'W')))
    source.update(valid_timestamp_rows=len(result), rejected_rows=rejected,
                  timezone='Asia/Shanghai', utc_offset='+08:00',
                  snapshot_of_possibly_appending_file=True)
    return result, source


def read_memory_samples(path):
    raw, source = _snapshot(path)
    result, rejected = [], []
    if raw is not None:
        for line, text in enumerate(raw.decode('utf-8-sig').splitlines(), 1):
            if not text.strip():
                continue
            try:
                row = json.loads(text)
                stamp = row['unix_time']
                if not _finite(stamp):
                    raise ValueError('finite_unix_seconds_required')
            except (json.JSONDecodeError, TypeError, KeyError, ValueError):
                rejected.append(line)
                continue
            result.append(dict(unix_time=stamp, **{key:row.get(key) if _finite(row.get(key))
                    and row[key] >= 0 else None for key in
                    ('server_rss_gib','available_physical_gib','available_commit_gib')}))
    source.update(valid_timestamp_rows=len(result), rejected_rows=rejected, timezone='Unix seconds',
                  snapshot_of_possibly_appending_file=True)
    return result, source


def classify_job(job):
    nodes = list(job.get('workflow', {}).values())
    classes = {node.get('class_type') for node in nodes}
    lengths = {node.get('inputs',{}).get('length') for node in nodes
               if node.get('class_type') == 'EmptyLTXVLatentVideo'}
    if 'CLIPTextEncode' in classes and 'LabSaveConditioning' in classes and not lengths:
        return 'text_conditioning', None
    if 'LabSaveMP4' in classes and len(lengths) == 1:
        frames = next(iter(lengths))
        return {97:'reference_97',241:'action_241'}.get(frames,'other_video'), frames
    return 'unknown', None


def job_timing(job):
    created, finished = job.get('created_unix'), job.get('finished_unix')
    observer = finished-created if _finite(created) and _finite(finished) and finished >= created else None
    history = job.get('history') or {}
    events = history.get('status',{}).get('messages', [])
    prompt_id = job.get('prompt_id')
    messages = defaultdict(set)
    ignored = 0
    for event in events:
        if not isinstance(event, list) or len(event) != 2 or not isinstance(event[1], dict):
            ignored += 1
            continue
        name, details = event
        if name not in ('execution_start','execution_success','execution_error','execution_interrupted'):
            continue
        if not prompt_id or details.get('prompt_id') != prompt_id or not _finite(details.get('timestamp')):
            ignored += 1
            continue
        messages[name].add(details['timestamp']/1000.)
    starts = messages['execution_start']
    terminals = [(kind, stamp) for kind in ('execution_success','execution_error','execution_interrupted')
                 for stamp in messages[kind]]
    reason = None
    start = next(iter(starts)) if len(starts) == 1 else None
    terminal = terminals[0] if len(terminals) == 1 else None
    if start is None:
        reason = 'missing_or_ambiguous_execution_start'
    elif terminal is None:
        reason = 'missing_or_ambiguous_execution_terminal'
    elif terminal[1] < start:
        reason = 'execution_terminal_precedes_start'
    valid = reason is None
    return dict(created_unix=created if _finite(created) else None,
                finished_unix=finished if _finite(finished) else None,
                observer_wall_seconds=observer,
                execution_start_unix=start,
                execution_end_unix=terminal[1] if terminal else None,
                execution_end_event=terminal[0] if terminal else None,
                execution_wall_seconds=terminal[1]-start if valid else None,
                execution_window_verified=valid, unavailable_reason=reason,
                ignored_execution_events=ignored)


def observed_resources(timing, gpu, memory):
    if timing['execution_window_verified']:
        start, end = timing['execution_start_unix'], timing['execution_end_unix']
        gpu = [row for row in gpu if start <= row['unix_time'] <= end]
        memory = [row for row in memory if start <= row['unix_time'] <= end]
    else:
        gpu, memory = [], []
    def stat(rows, field, method):
        values = [row[field] for row in rows if _finite(row.get(field))]
        return dict(value=method(values) if values else None, samples=len(values))
    def coverage(rows):
        stamps = sorted(row['unix_time'] for row in rows)
        return dict(samples=len(rows), first_sample_unix=stamps[0] if stamps else None,
                    last_sample_unix=stamps[-1] if stamps else None,
                    max_observed_sampling_gap_s=max((b-a for a,b in zip(stamps,stamps[1:])),default=None))
    return dict(gpu_window_samples=coverage(gpu), memory_window_samples=coverage(memory),
                max_observed_gpu_memory_mib=stat(gpu,'gpu_memory_mib',max),
                max_observed_gpu_utilization_percent=stat(gpu,'gpu_utilization_percent',max),
                max_observed_gpu_temperature_c=stat(gpu,'gpu_temperature_c',max),
                max_observed_gpu_power_w=stat(gpu,'gpu_power_w',max),
                max_observed_server_rss_gib=stat(memory,'server_rss_gib',max),
                min_observed_available_physical_gib=stat(memory,'available_physical_gib',min),
                min_observed_available_commit_gib=stat(memory,'available_commit_gib',min))


def build_report(root, *, lab=Path('E:/ai-video-lab'), gpu_csv=None, memory_jsonl=None):
    """Snapshot existing files, include unfinished jobs, and do not mutate inputs."""
    root, lab = Path(root).resolve(), Path(lab).resolve()
    gpu, gpu_source = read_gpu_samples(gpu_csv or root/'reports/gpu-monitor.csv')
    memory, memory_source = read_memory_samples(memory_jsonl or lab/'memory-monitor.jsonl')
    jobs, invalid = [], []
    for path in sorted((root/'manifests/jobs').glob('*.json')):
        raw, source = _snapshot(path)
        try:
            job = json.loads(raw.decode('utf-8-sig'))
            if not isinstance(job,dict):
                raise ValueError('job_object_required')
            category, frames = classify_job(job)
            timing = job_timing(job)
            jobs.append(dict(name=job.get('name',path.stem), prompt_id=job.get('prompt_id'),
                status=job.get('status'), category=category, requested_frames=frames,
                job_snapshot=source, timing=timing,
                resources=observed_resources(timing,gpu,memory),
                stage_seconds=dict(model_loading=None,text_encoding=None,sampling=None,vae_decode=None,
                                   saving=None,reason='no_trusted_per_node_or_stage_timing_in_history')))
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            invalid.append(dict(job_snapshot=source,error_type=type(error).__name__,error=str(error)))
    groups = {}
    for category in sorted({job['category'] for job in jobs}):
        selected = [job for job in jobs if job['category']==category]
        groups[category] = dict(jobs=len(selected), completed_success=sum(job['status']=='success' for job in selected))
        for key in ('observer_wall_seconds','execution_wall_seconds'):
            values = [job['timing'][key] for job in selected if job['timing'][key] is not None]
            groups[category][key] = dict(measured_jobs=len(values), total=sum(values) if values else None,
                                        min=min(values) if values else None, max=max(values) if values else None,
                                        mean=sum(values)/len(values) if values else None)
    return dict(schema_version=VERSION, captured_at_utc=datetime.now(timezone.utc).isoformat(),
                root=str(root), sources=dict(gpu=gpu_source,memory=memory_source),
                job_count=len(jobs), invalid_job_snapshots=invalid, jobs=jobs, categories=groups,
                interpretation=dict(sampled_extrema_are_continuous_peaks=False,
                    gpu_scope='nvidia-smi machine GPU totals including other applications',
                    memory_scope='server_rss_gib from monitor; available memory is machine-wide',
                    timestamp_alignment='Comfy milliseconds /1000; memory Unix seconds; GPU Asia/Shanghai UTC+08:00',
                    observer_wall='created_unix to finished_unix includes submission, queue and polling observation delay',
                    execution_wall='matched Comfy execution_start to execution_success/error/interrupted events',
                    stage_breakdown='unknown without trusted per-node timings; no resolution/frame-count extrapolation',
                    category_scope='workflow configuration buckets, not actual movement labels',
                    missing_samples='null statistics; no inferred extrema or peak',
                    incomplete_jobs='retained with unknown execution window; no partial-window resource attribution'))


def write_report(report, output):
    path = Path(output).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(report,stream,ensure_ascii=False,allow_nan=False,indent=2)
        stream.write('\n')
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--lab',type=Path,default=Path('E:/ai-video-lab'))
    parser.add_argument('--gpu-csv',type=Path)
    parser.add_argument('--memory-jsonl',type=Path)
    parser.add_argument('--output',type=Path,required=True,help='New JSON file; existing files are never replaced')
    args = parser.parse_args()
    report = build_report(args.root,lab=args.lab,gpu_csv=args.gpu_csv,memory_jsonl=args.memory_jsonl)
    target = write_report(report,args.output)
    print(json.dumps(dict(report=str(target),job_count=report['job_count'],categories=report['categories']),ensure_ascii=True))


if __name__ == '__main__':
    main()
