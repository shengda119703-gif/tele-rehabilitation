from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.rehab_ml.common import ROOT


def parser():
    result = argparse.ArgumentParser(description='Versioned rehabilitation backend and offline research tools')
    sub = result.add_subparsers(dest='command', required=True)
    sub.add_parser('doctor', help='Inspect environment without upgrading the product')
    item = sub.add_parser('inventory', help='Capture protected paths and run the legacy backend baseline once')
    item.add_argument('--scope', choices=['rehab-backend'], required=True)
    item = sub.add_parser('verify-scope', help='Verify all protected hashes and additions')
    item.add_argument('--baseline', type=Path, required=True)
    item = sub.add_parser('resolve', help='Resolve official metadata and record license/access blockers')
    item.add_argument('--registry', type=Path, default=ROOT / 'configs/rehab_ml/datasets.yaml')
    for name in ('fetch', 'verify'):
        item = sub.add_parser(name, help=name.capitalize() + ' a licensed, pinned official dataset')
        item.add_argument('--dataset', choices=['intellirehabds'], required=True)
        if name == 'fetch':
            item.add_argument('--subset', choices=['skeleton'], required=True)
    item = sub.add_parser('replay', help='Run deterministic backend invariants, not clinical accuracy')
    item.add_argument('--suite', choices=['rehab_core'], required=True)
    item = sub.add_parser('prepare', help='Adapt verified official skeleton data and independent label masks')
    item.add_argument('--dataset', choices=['intellirehabds'], required=True)
    item.add_argument('--actions', type=int, nargs='+', required=True)
    item = sub.add_parser('split', help='Split people before features, windows or augmentation')
    item.add_argument('--dataset', choices=['intellirehabds'], required=True)
    item.add_argument('--group', choices=['subject_id'], required=True)
    item.add_argument('--seed', type=int, required=True)
    item = sub.add_parser('build-features', help='Build causal, domain-specific skeleton features')
    item.add_argument('--dataset', choices=['intellirehabds'], required=True)
    item.add_argument('--domain', choices=['kinect_3d'], required=True)
    item = sub.add_parser('train', help='Train a real licensed grouped experiment; never auto-activate')
    item.add_argument('--config', type=Path, required=True)
    item = sub.add_parser('evaluate', help='Evaluate the frozen run, not an implicit latest checkpoint')
    item.add_argument('--run-id', required=True)
    item.add_argument('--split', choices=['val', 'test'], required=True)
    item = sub.add_parser('visual-audit', help='Render one licensed Kinect mapping sample for offline review only')
    item.add_argument('--output-dir', type=Path, help='New directory within backend reports or the dedicated run root')
    item = sub.add_parser('compare', help='Compare explicit frozen runs; domain-gated offline predictions only')
    item.add_argument('--suite', choices=['rehab_core'], required=True)
    item.add_argument('--baseline', required=True)
    item.add_argument('--candidate', required=True)
    item = sub.add_parser('build-pose-dataset', help='Convert verified independent RGB labels; unknown masks never become negatives')
    source = item.add_mutually_exclusive_group(required=True)
    source.add_argument('--dataset', choices=['rehab24_6', 'mobiphysio', 'sumedipose'])
    source.add_argument('--reference', type=Path, help='Consent-scoped RGB reference manifest, not model pseudo-labels')
    item.add_argument('--target-schema', choices=['coco17'], required=True)
    item.add_argument('--output-format', choices=['masked', 'yolo_pose'], default='masked')
    item.add_argument('--output-dir', type=Path)
    item = sub.add_parser('infer-pose-reference', help='Pinned original YOLO on authorized reference images; no training or camera')
    item.add_argument('--reference', type=Path, required=True)
    item.add_argument('--split', choices=['val', 'test'], required=True)
    item.add_argument('--output-dir', type=Path, required=True)
    item = sub.add_parser('evaluate-pose', help='Independent per-joint RGB error and coverage; missing predictions remain in denominators')
    item.add_argument('--reference', type=Path, required=True)
    item.add_argument('--predictions', type=Path, required=True)
    item.add_argument('--split', choices=['val', 'test'], required=True)
    item.add_argument('--confidence-min', type=float, default=.5)
    item.add_argument('--pck-threshold', type=float, default=.05)
    item.add_argument('--output-dir', type=Path, required=True)
    item = sub.add_parser('train-pose', help='Qualification gate: pose fine-tuning requires verified independent labels')
    item.add_argument('--config', type=Path, required=True)
    item = sub.add_parser('extract-pose', help='Analyze authorized local RGB video; does not grant training permission')
    item.add_argument('--video', type=Path, required=True)
    item.add_argument('--exercise', choices=['shoulder_abduction', 'sit_to_stand', 'rehab_squat'], required=True)
    item.add_argument('--side', choices=['left', 'right'], required=True)
    item.add_argument('--analysis-consent', choices=['yes'], required=True)
    item = sub.add_parser('extract-mediapipe-video', help='Offline Python VIDEO approximation using existing APK-matched model; not phone validation')
    item.add_argument('--video', type=Path, required=True)
    item.add_argument('--exercise', choices=['shoulder_abduction', 'sit_to_stand', 'rehab_squat'], required=True)
    item.add_argument('--side', choices=['left', 'right'], required=True)
    item.add_argument('--analysis-consent', choices=['yes'], required=True)
    item.add_argument('--output-dir', type=Path)
    item = sub.add_parser('compare-video-pose', help='Compare timestamp and decoded-pixel matched pose inputs; disagreement is not accuracy')
    item.add_argument('--yolo-result', type=Path, required=True)
    item.add_argument('--mediapipe-result', type=Path, required=True)
    item.add_argument('--output-dir', type=Path, required=True)
    sub.add_parser('supervision-status', help='Report missing license/target-domain supervision; never imply training success')
    item = sub.add_parser('verify-sessions', help='Run lifecycle, idempotency, crash and boundary tests on isolated databases')
    item.add_argument('--database-mode', choices=['isolated'], required=True)
    item = sub.add_parser('benchmark', help='Measure declared CPU/model/control budgets; not phone performance')
    item.add_argument('--run-id', required=True)
    item = sub.add_parser('benchmark-sessions', help='Measure isolated ASGI lifecycle and real baseline YOLO; no camera or accuracy claims')
    item.add_argument('--frames', type=int, choices=range(8, 61), default=20)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command in ('doctor', 'inventory', 'verify-scope'):
            from tools.rehab_ml.inventory import doctor, inventory, verify_scope
            value = (doctor() if args.command == 'doctor' else inventory()
                     if args.command == 'inventory' else verify_scope(args.baseline))
        elif args.command == 'visual-audit':
            from tools.rehab_ml.visual_audit import render
            value = render(args.output_dir)
        elif args.command == 'compare':
            from tools.rehab_ml.model_registry import compare
            value = compare(args.baseline, args.candidate)
        elif args.command == 'build-pose-dataset' and args.reference is not None:
            from tools.rehab_ml.pose_dataset import convert
            if args.output_dir is None:
                raise ValueError('Explicit new --output-dir required for private pose conversion')
            value = convert(args.reference, args.output_dir, output_format=args.output_format)
        elif args.command == 'infer-pose-reference':
            from tools.rehab_ml.pose_inference import infer_baseline
            value = infer_baseline(args.reference, args.output_dir, split=args.split)
        elif args.command == 'evaluate-pose':
            from tools.rehab_ml.pose_dataset import evaluate
            value = evaluate(args.reference, args.predictions, args.output_dir, split=args.split,
                             confidence_min=args.confidence_min, pck_threshold=args.pck_threshold)
        elif args.command in ('build-pose-dataset', 'train-pose'):
            from tools.rehab_ml.target_domain import supervision_status
            from tools.rehab_ml.common import write_json
            status = supervision_status()
            output = ROOT / 'reports/rehab_backend/pose_supervision_blocker.json'
            write_json(output, dict(status, requested_command=args.command,
                implemented='reference_conversion_and_evaluation_available_pose_training_refused'))
            raise RuntimeError('Pose training refused: verified target RGB permission and independent 2D/visibility labels missing; '+str(output))
        elif args.command == 'extract-mediapipe-video':
            from tools.rehab_ml.mediapipe_video import extract_mediapipe
            value = extract_mediapipe(args.video, args.exercise, args.side,
                analysis_consent=args.analysis_consent == 'yes', output_dir=args.output_dir)
        elif args.command == 'compare-video-pose':
            from tools.rehab_ml.pose_video_compare import compare_video_inputs
            value = compare_video_inputs(args.yolo_result, args.mediapipe_result, args.output_dir)
        elif args.command in ('extract-pose', 'supervision-status'):
            from tools.rehab_ml.target_domain import extract_pose, supervision_status
            value = extract_pose(args.video, args.exercise, args.side) if args.command == 'extract-pose' else supervision_status()
        elif args.command == 'benchmark':
            from tools.rehab_ml.benchmark import benchmark
            value = benchmark(args.run_id)
        elif args.command == 'benchmark-sessions':
            from tools.rehab_ml.session_benchmark import benchmark_sessions
            value = benchmark_sessions(args.frames)
        elif args.command in ('train', 'evaluate'):
            from tools.rehab_ml.training import train, evaluate
            value = train(args.config) if args.command == 'train' else evaluate(args.run_id, args.split)
        elif args.command in ('prepare', 'split', 'build-features'):
            from tools.rehab_ml.data import prepare, split
            from tools.rehab_ml.features import build_features
            value = (prepare(args.actions) if args.command == 'prepare' else split(args.seed)
                     if args.command == 'split' else build_features(args.domain))
        elif args.command in ('replay', 'verify-sessions'):
            import os
            import subprocess
            import time
            started = time.perf_counter()
            arguments = (['-m', 'unittest', 'discover', '-s', 'tests/rehab_backend', '-p', 'test_protocols.py', '-v']
                         if args.command == 'replay' else ['-m', 'unittest', '-v',
                                                          'test_sessions', 'test_progress', 'test_timing', 'test_isolation', 'test_report_isolation', 'test_storage_faults', 'test_telemetry', 'test_api'])
            environment = dict(os.environ)
            environment['PYTHONPATH'] = os.pathsep.join((str(ROOT/'tests/rehab_backend'),
                                                       str(ROOT/'rehab_codex_single_camera_v2_1'), str(ROOT)))
            proc = subprocess.run([sys.executable, '-X', 'utf8', *arguments], cwd=ROOT, env=environment,
                                  capture_output=True, text=True, encoding='utf-8', timeout=90)
            from tools.rehab_ml.common import paths, file_hash, write_json
            from uuid import uuid4
            log = paths()['run'] / ('replay-'+uuid4().hex[:8]) / ('protocols.txt' if args.command == 'replay' else 'sessions.txt')
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text(proc.stdout + proc.stderr, encoding='utf-8')
            value = dict(exit_code=proc.returncode, arguments=arguments, elapsed_s=time.perf_counter()-started,
                         log=str(log), log_sha256=file_hash(log), clinical_accuracy=None)
            write_json(ROOT / 'reports/rehab_backend' / ('protocol_replay.json' if args.command == 'replay'
                                                       else 'session_verification.json'), value)
            if proc.returncode:
                raise RuntimeError('Protocol replay failed: ' + str(log))
        else:
            from tools.rehab_ml.download import resolve, fetch, verify
            value = (resolve(args.registry) if args.command == 'resolve' else fetch(args.dataset)
                     if args.command == 'fetch' else verify(args.dataset))
        print(json.dumps(dict(ok=True, command=args.command, result=value), ensure_ascii=False, allow_nan=False))
        return 0
    except Exception as exc:
        print(json.dumps(dict(ok=False, command=args.command, error_type=type(exc).__name__, error=str(exc)),
                         ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
