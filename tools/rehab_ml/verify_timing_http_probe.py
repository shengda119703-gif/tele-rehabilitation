"""Audit explicit saved TEST runs, retaining the unexplained original failure.

No rerun, camera, model training, normal database or latest-directory lookup.
Only aggregate results and evidence hashes are published; raw traces stay local.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import re
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.rehab_ml.common import file_hash, paths, read_json, utc_now, write_json

PRODUCTION = ('mobile_rehab/rehab_v2/service.py',
              'rehab_codex_single_camera_v2_1/app/rehab_v2/engine.py')


def require(condition, label):
    if not condition:
        raise ValueError(label)


def load_run(run_id):
    require(bool(re.fullmatch(r'[a-z0-9-]+', run_id)), 'invalid_explicit_run_id')
    root = paths()['run']/run_id
    result = read_json(root/'summary.json')
    return root, result


def load_artifact(root, summary, name):
    item = summary['artifacts'][name]
    path = Path(item['path']).resolve()
    require(path == (root/name).resolve(), 'artifact_path_outside_owned_run')
    require(file_hash(path) == item['sha256'], 'artifact_hash_mismatch')
    return read_json(path)


def trace_result(trace, *, complete, recorded=False):
    groups = {}
    for row in trace['frames']:
        groups.setdefault(row['session_id'], []).append(row)
    require(len(groups) == (2 if complete else 1), 'unexpected_session_denominator')
    maximum = 0.
    for rows in groups.values():
        require([r['seq'] for r in rows] == list(range(1,65)), 'missing_or_reordered_processed_frame')
        previous = None
        for row in rows:
            metric = row['metric']
            require(row['accepted'] is True, 'engine_rejected_frame')
            require(metric['valid'] is True and metric['evidence_kind'] == 'observed', 'not_TEST_observed_metric')
            require(metric['observed_at_s'] == row['time_s'] and metric['age_ms'] == 0., 'bad_TEST_metric_clock')
            require(metric['value'] == (0. if row['seq']<=30 or row['seq']>54 else 70.), 'changed_TEST_angle_recipe')
            if previous is not None:
                dt = row['time_s']-previous
                require(dt>0. and abs(dt-row['dt_s'])<1e-9, 'bad_recorded_dt')
                maximum = max(maximum,dt)
            if recorded:
                require(abs(row['time_s']-row['seq']*.05)<1e-9, 'recorded_clock_not_declared_fixture')
            previous = row['time_s']
        last = rows[-1]['after']
        require(last['completed'] == (1 if complete else 0), 'wrong_confirmation_count')
        require(len(last['repetitions']) == 1, 'wrong_repetition_denominator')
        rep = last['repetitions'][0]
        require(rep['completion_status'] == ('COMPLETE' if complete else 'UNASSESSABLE'), 'wrong_completion_status')
        if not complete:
            require(rep['reason'] == 'long_evidence_gap', 'missing_gap_reason')
            require(rows[54]['before']['phase'] == 'RAISING', 'gap_not_at_observed_return_boundary')
            require(rows[54]['dt_s']>.65, 'real_gap_not_injected')
    if complete:
        require(not trace['invalidations'] and maximum<=.5, 'positive_fixture_has_unqualified_gap')
    else:
        require(len(trace['invalidations'])==1 and trace['invalidations'][0]['reason']=='long_evidence_gap'
                and trace['invalidations'][0]['after_seq']==54, 'unexpected_invalidation_boundary')
    return dict(sessions=len(groups), processed_frames=len(trace['frames']), max_dt_s=maximum,
                completed_per_session=1 if complete else 0,
                repetition_status='COMPLETE' if complete else 'UNASSESSABLE')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('natural','known-gap','recorded','host-gap','regression'):
        parser.add_argument('--'+name, required=True, help='Exact saved run ID, not latest')
    args = parser.parse_args()
    root = paths()['run']/('timing-http-audit-'+uuid4().hex[:8])
    root.mkdir()
    result = dict(run_id=root.name, created_at=utc_now(), passed=False, cases={}, sources={},
                  original_failure_root_cause_proven=False, human_verification='pending',
                  submission_ready=False, clinical_accuracy=None, candidate_enabled=False,
                  scope='TEST evidence clocks, actual authenticated HTTP lifecycle and saved regression logs')
    try:
        for index, (name, run_id, complete, recorded, success) in enumerate((
            ('natural',args.natural,True,False,True),
            ('known_gap',args.known_gap,False,False,False),
            ('recorded',args.recorded,True,True,True),
            ('host_gap',args.host_gap,False,False,True)), start=1):
            case_root, summary = load_run(run_id)
            trace = load_artifact(case_root,summary,'trace.json')
            load_artifact(case_root,summary,'test_output.json')
            checked = trace_result(trace,complete=complete,recorded=recorded)
            require(summary['test_success'] is success and summary['errors']==0, 'unexpected_test_verdict')
            require(abs(summary['max_dt_s']-checked['max_dt_s'])<1e-9, 'summary_dt_disagrees_with_trace')
            require(all(item['closed'] and item['resources_released'] and item['inference_process_released']
                        and item['report_process_released'] for item in summary['resources']), 'owned_resources_not_released')
            require(all(summary['source_sha256'][p]==file_hash(ROOT/p) for p in PRODUCTION), 'production_rules_changed')
            if name in ('recorded','host_gap'):
                require(summary['source_sha256']['tests/rehab_backend/test_timing_comparison.py']==
                        file_hash(ROOT/'tests/rehab_backend/test_timing_comparison.py'), 'current_test_source_changed')
            result['cases'][name] = dict(run_id=run_id, expected_test_success=success, **checked)
            result['sources']['E00'+str(index)] = dict(run_id=run_id, summary_sha256=file_hash(case_root/'summary.json'),
                                                      artifacts=summary['artifacts'], agent_checked=True, human_verified=False)
        # Audit must reject altered facts; these are explicit local TEST mutations,
        # not additional independently executed HTTP cases or test-count padding.
        positive_root, positive_summary = load_run(args.recorded)
        positive = load_artifact(positive_root,positive_summary,'trace.json')
        rejected = []
        for label in ('count','timestamp','observed_kind'):
            changed = copy.deepcopy(positive)
            if label=='count': changed['frames'][63]['after']['completed']=0
            elif label=='timestamp': changed['frames'][54]['time_s']=0.
            else: changed['frames'][54]['metric']['evidence_kind']='predicted'
            try:
                trace_result(changed,complete=True,recorded=True)
            except ValueError:
                rejected.append(label)
        require(rejected==['count','timestamp','observed_kind'], 'audit_did_not_reject_mutation')
        result['audit_self_checks']=dict(rejected_TEST_mutations=rejected, not_additional_HTTP_runs=True)
        old_root, old = load_run('verification-f28dac51')
        old_command = old['commands'][0]
        require(old_command['exit_code']==1 and not old['passed'], 'original_failure_not_retained')
        require(file_hash(old_root/'new_backend.txt')==old_command['log_sha256'], 'original_failure_log_changed')
        result['sources']['E005'] = dict(run_id=old_root.name, summary_sha256=file_hash(old_root/'summary.json'),
                                        log_sha256=old_command['log_sha256'], original_failed_test=True,
                                        missing_per_frame_clock_trace=True, human_verified=False)
        regression_root, regression = load_run(args.regression)
        require(regression['passed'] and len(regression['commands'])==4, 'full_regression_not_passed')
        counts = {}
        for command in regression['commands']:
            log = Path(command['log']).resolve()
            require(log.parent==regression_root.resolve() and file_hash(log)==command['log_sha256'], 'regression_log_changed')
            require(command['exit_code']==0, 'regression_command_failed')
            text = log.read_text(encoding='utf-8')
            matched = re.search(r'Ran (\d+) tests|\b(\d+) passed',text)
            if matched: counts[command['name']]=int(next(v for v in matched.groups() if v is not None))
        require(counts==dict(new_backend=456,legacy_rehab=12,legacy_mobile=19), 'unexpected_current_regression_counts')
        result['regression']=dict(run_id=args.regression, counts=counts, summary_sha256=file_hash(regression_root/'summary.json'))
        result['production_sha256']={p:file_hash(ROOT/p) for p in PRODUCTION}
        result['passed']=True
    except Exception as error:
        result['error']=dict(type=type(error).__name__,message=str(error))
    write_json(root/'summary.json',result)
    write_json(ROOT/'reports/rehab_backend/timing_http_clock_verification.json',result)
    print(json.dumps(result,ensure_ascii=False))
    return 0 if result['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
