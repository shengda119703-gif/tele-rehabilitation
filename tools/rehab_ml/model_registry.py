from __future__ import annotations

from .common import ROOT, file_hash, paths, read_json, write_json


def checked_run(run_id):
    from pathlib import Path
    if not run_id or Path(run_id).name != run_id or run_id in ('.', '..', 'latest'):
        raise ValueError('Explicit safe model run ID required')
    run = paths()['run'] / run_id
    card = read_json(run / 'model-card.json')
    if card['model_id'] != run_id or Path(card['artifact']).name != card['artifact']:
        raise ValueError('Model manifest identity or artifact path mismatch')
    if file_hash(run / card['artifact']) != card['artifact_sha256']:
        raise ValueError('Model artifact checksum mismatch')
    if card['deployment_status'] != 'offline_research_only' or card['product_enabled'] is not False:
        raise ValueError('This harness only accepts explicitly offline packages')
    return run, card


def compare(baseline_id, candidate_id):
    """Frozen independent predictions, not a selection/tuning/activation tool."""
    from pathlib import Path
    import sys
    sys.path.insert(0, str(ROOT / 'rehab_codex_single_camera_v2_1'))
    from app.rehab_v2.temporal import ShadowSequence
    baseline, bcard = checked_run(baseline_id)
    candidate, ccard = checked_run(candidate_id)
    breport, creport = [read_json(run / 'evaluation-test.json') for run in (baseline, candidate)]
    if bcard['data_fingerprint'] != ccard['data_fingerprint'] or bcard['split_hash'] != ccard['split_hash']:
        raise ValueError('Different input data or subject split cannot be compared')
    bp, cp = [read_json(run / 'predictions-test.json') for run in (baseline, candidate)]
    if [(v['sample_id'], v['label']) for v in bp] != [(v['sample_id'], v['label']) for v in cp]:
        raise ValueError('Prediction sample/independent label identity mismatch')
    shadow = ShadowSequence(ccard, lambda frames: dict(probability_incorrect=cp[0]['probability_incorrect']),
                            research_mode=True)
    shadow.begin('TEST-offline-irds', 0)
    shadow.append('TEST-offline-irds', 0, 0, dict(sample_id=cp[0]['sample_id'], after_rep_end=True))
    request = dict(input_domain='kinect_3d', schema_id='kinect25-v1', coordinate_space='kinect_camera_3d',
        feature_version=ccard['feature_version'], exercise_id='shoulder_abduction', side='left',
        camera_view='kinect_recording_only', protocol_version='irds-rep-label-1')
    result = dict(baseline_id=baseline_id, candidate_id=candidate_id, partition='frozen_test',
        baseline=breport['overall'], candidate=creport['overall'],
        candidate_minus_baseline_macro_f1=creport['overall']['macro_f1']-breport['overall']['macro_f1'],
        disagreements=[dict(sample_id=a['sample_id'], baseline=a['predicted'], candidate=b['predicted'], label=a['label'])
                       for a, b in zip(bp, cp) if a['predicted'] != b['predicted']],
        domain_gate_match=shadow.finish('TEST-offline-irds', 0, request),
        rgb_rejection=shadow.finish('TEST-offline-irds', 0, dict(request, input_domain='yolo_2d')),
        product_enabled=False, model_activated=False, clinical_accuracy=None,
        selection_note='Fixed configurations were declared before test evaluation; no test-driven tuning or activation',
        artifacts={str(run.name)+'/'+name: file_hash(run / name) for run in (baseline, candidate)
                   for name in ('model-card.json', 'evaluation-test.json', 'predictions-test.json')})
    output = ROOT / 'reports/rehab_backend/model_comparison.json'
    write_json(output, result)
    return dict(path=str(output), disagreements=len(result['disagreements']),
                delta_macro_f1=result['candidate_minus_baseline_macro_f1'],
                matched_domain_status=result['domain_gate_match']['status'],
                rgb_status=result['rgb_rejection']['status'], product_enabled=False)
