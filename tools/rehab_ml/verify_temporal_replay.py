"""Actual original RGB inference and saved-evidence replay; no GT invented."""
from __future__ import annotations

from dataclasses import asdict
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.rehab_ml.common import canonical_hash, file_hash, paths, write_json
from tools.rehab_ml.professional_annotations import _bundle, _read
from tools.rehab_ml.temporal_replay import (append_events, event_inventory, source_fingerprints,
                                          transition_events)
from tools.rehab_ml.temporal_evaluation import validate_predictions


def audit_replay(summary_path, bundle_path, split):
    """Recompute unchanged adapter/protocol from saved original pose output.

    This proves internal saved-evidence consistency, not clinical pose accuracy
    or cryptographic attestation of the original camera/inference execution.
    """
    sys.path.insert(0, str(ROOT/'rehab_codex_single_camera_v2_1'))
    from app.domain import Context, PoseFrame, PosePerson, clean_json
    from app.rehab_v2.engine import ProtocolEngine
    from app.rehab_v2.evidence import EvidenceAdapter
    summary_path = Path(summary_path).resolve()
    summary, config = _read(summary_path), _read(summary_path.with_name('config.json'))
    bundle_path, bundle = _bundle(bundle_path)  # sources/timelines only, never editable labels
    cohort = [row for row in bundle['samples'] if row['split'] == split]
    predictions = _read(summary['predictions'])
    if (summary['status'] != 'completed' or summary['owned_release'].get('confirmed') is not True
            or summary['implementation'] != source_fingerprints()
            or summary['config_sha256'] != canonical_hash(config)
            or summary['predictions_sha256'] != file_hash(summary['predictions'])
            or predictions['implementation_sha256'] != canonical_hash(summary['implementation'])
            or predictions['config_sha256'] != canonical_hash(config)
            or predictions['model_sha256'] != summary['model_sha256']):
        raise ValueError('saved_replay_source_config_model_or_release_contract_changed')
    validate_predictions(predictions, cohort, {}, bundle_path.parent)
    details = {row['sample_id']: row for row in summary['samples']}
    checked = []
    for source, predicted in zip(cohort, predictions['samples']):
        detail = details[source['sample_id']]
        trace, result = Path(detail['trace']), Path(detail['result'])
        if (trace.parent != summary_path.parent or result.parent != summary_path.parent
                or file_hash(trace) != detail['trace_sha256'] or file_hash(result) != detail['result_sha256']):
            raise ValueError('saved_actual_trace_changed_or_outside_owned_run')
        timeline = _read(bundle_path.parent/source['timeline_ref'])['presentation_s']
        wanted_seq, next_sample = [], None
        for seq, stamp in enumerate(timeline, 1):
            if next_sample is None or stamp+1e-9 >= next_sample:
                wanted_seq.append(seq)
                next_sample = stamp+config['sampling_period_s']
        events, seqs, engine, adapter = event_inventory(), [], None, None
        with trace.open(encoding='utf-8') as stream:
            for line in stream:
                row = json.loads(line)
                seqs.append(row['seq'])
                if row['time_s'] != timeline[row['seq']-1]:
                    raise ValueError('trace_pts_not_original_presentation_frame')
                pose = row['pose']
                context = Context(**pose['context'])
                pose = PoseFrame(**dict(pose, context=context,
                    size=tuple(pose['size']), people=[PosePerson(**person) for person in pose['people']]))
                if (pose.seq != row['seq'] or pose.time_s != row['time_s']
                        or context.source_ref != source['video_sha256']
                        or pose.model_manifest_id != predictions['model_sha256']):
                    raise ValueError('saved_pose_original_source_identity_changed')
                if engine is None:
                    engine = ProtocolEngine(config['plan'], source_epoch=context.epoch,
                                            session_id=source['sample_id'])
                    adapter = EvidenceAdapter(source['exercise_id'], config['analyzed_side'],
                                              max_gap_s=engine.plan['max_gap_s'])
                evidence = adapter.analyze(pose, processing_age_ms=0., time_basis='mapped_source_seconds')
                if clean_json(asdict(evidence)) != row['metrics'] or row['phase_before'] != engine.phase:
                    raise ValueError('saved_adapter_evidence_or_phase_prefix_changed')
                before = dict(phase=engine.phase, repetitions=list(engine.repetitions))
                if not engine.process(evidence):
                    raise ValueError('saved_actual_pose_rejected_by_unchanged_protocol')
                after = dict(phase=engine.phase, repetitions=list(engine.repetitions))
                transitions = transition_events(before, after, pose.seq, pose.time_s)
                if (clean_json(transitions) != row['emitted_events'] or row['phase_after'] != engine.phase
                        or row['completed'] != engine.completed):
                    raise ValueError('saved_confirmation_trace_does_not_replay')
                append_events(events, transitions)
        if seqs != wanted_seq or len(seqs) != detail['sampled_frames']:
            raise ValueError('missing_or_extra_sampled_trace_prefix')
        engine.finish('offline_original_video_ended')
        if (clean_json(engine.summary()) != _read(result) or engine.completed != predicted['completed_count']
                or events != predicted['boundary_events']):
            raise ValueError('saved_prediction_does_not_match_actual_protocol_trace')
        checked.append(dict(sample_id=source['sample_id'], sampled_frames=len(seqs),
            completed_count=engine.completed, trace_sha256=file_hash(trace),
            emitted_events={key: None if value is None else len(value) for key, value in events.items()}))
    return dict(split=split, checked_videos=len(checked), samples=checked,
                saved_evidence_consistent=True, clinical_accuracy=None, no_human_forms_read=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--pending-bundle', type=Path, required=True)
    args = parser.parse_args()
    bundle = args.pending_bundle.resolve()
    frozen = {str(path): file_hash(path) for path in bundle.parent.iterdir() if path.is_file()}
    root = paths()['run']/('temporal-replay-audit-'+uuid4().hex[:8])
    root.mkdir()
    summary = dict(scope='actual_original_RGB_YOLO_protocol_and_TEST_export_contract',
        product_environment=sys.executable, implementation=source_fingerprints(),
        verifier_sha256=file_hash(__file__), commands=[], audits=[], product_enabled=False,
        independent_accuracy_evaluation_performed=False, training_performed=False)
    cases = [('help', ['tools/rehab_ml/cli.py', 'replay-mobiphysio-temporal', '--help'], 0, 60),
        ('unit', ['-m', 'unittest', 'discover', '-s', 'tests/rehab_backend',
                  '-p', 'test_temporal_replay.py', '-v'], 0, 60)]
    for split in ('val', 'test'):
        cases.append((split, ['tools/rehab_ml/cli.py', 'replay-mobiphysio-temporal',
            '--receipt', str(args.receipt.resolve()), '--split', split, '--side', 'left',
            '--output-dir', str(root/split)], 0, 240))
    for name, arguments, expected, timeout in cases:
        log, started = root/(name+'.txt'), perf_counter()
        with log.open('x', encoding='utf-8') as stream:
            result = subprocess.run([sys.executable, '-X', 'utf8', '-B', *arguments], cwd=ROOT,
                env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=str(ROOT)),
                stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
        summary['commands'].append(dict(name=name, arguments=arguments, exit_code=result.returncode,
            expected_exit=expected, elapsed_s=perf_counter()-started, log=str(log), log_sha256=file_hash(log)))
        write_json(root/'summary.json', summary)
        if result.returncode == 0 and name in ('val', 'test'):
            summary['audits'].append(audit_replay(root/name/'summary.json', bundle, name))
        print(f"Temporal replay check {name}: exit {result.returncode}", flush=True)
    summary.update(original_annotation_bundle_unchanged=all(file_hash(path) == sha for path, sha in frozen.items()),
        implementation_unchanged=summary['implementation'] == source_fingerprints(),
        verifier_unchanged=summary['verifier_sha256'] == file_hash(__file__))
    summary['passed'] = (all(row['exit_code'] == row['expected_exit'] for row in summary['commands'])
        and len(summary['audits']) == 2 and all(summary[key] for key in
        ('original_annotation_bundle_unchanged', 'implementation_unchanged', 'verifier_unchanged')))
    write_json(root/'summary.json', summary)
    summary.update(artifact=str(root/'summary.json'), summary_sha256=file_hash(root/'summary.json'))
    write_json(ROOT/'reports/rehab_backend/temporal_replay_verification.json', summary)
    print(json.dumps(summary, ensure_ascii=False, allow_nan=False))
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
