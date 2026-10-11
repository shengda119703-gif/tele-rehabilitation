"""Real fixed CC0 package + TEST contract/tamper checks, no invented labels."""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.rehab_ml.common import canonical_hash, file_hash, paths, read_json, write_json
from tools.rehab_ml.professional_annotations import read_rows, _rows_write


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    root = paths()['run']/('professional-annotation-audit-'+uuid4().hex[:8])
    root.mkdir()
    summary = dict(run_dir=str(root), source_receipt_sha256=file_hash(args.receipt), commands=[],
                   implementation_sha256={str(path.relative_to(ROOT)): file_hash(path) for path in
                       (Path(__file__), ROOT/'tools/rehab_ml/professional_annotations.py',
                        ROOT/'tools/rehab_ml/cli.py', ROOT/'tests/rehab_backend/test_professional_annotations.py')},
                   product_environment=sys.executable, product_enabled=False, training_performed=False,
                   independent_labels_available=False)
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
                       PYTHONPATH=str(ROOT)+os.pathsep+str(ROOT/'rehab_codex_single_camera_v2_1'))

    def run(name, arguments, expected=0, json_result=False):
        started = time.perf_counter()
        log = root/(name+'.txt')
        with log.open('x', encoding='utf-8') as stream:
            proc = subprocess.run([sys.executable, '-X', 'utf8', '-B', *arguments], cwd=ROOT,
                env=environment, stdout=stream, stderr=subprocess.STDOUT, timeout=120)
        row = dict(name=name, arguments=arguments, exit_code=proc.returncode, expected_exit=expected,
                   elapsed_s=time.perf_counter()-started, log=str(log), log_sha256=file_hash(log))
        summary['commands'].append(row)
        write_json(root/'summary.json', summary)
        if proc.returncode != expected:
            raise RuntimeError('Unexpected exit: '+name+'; evidence='+str(log))
        return json.loads(log.read_text(encoding='utf-8'))['result'] if json_result else row

    try:
        for name in ('prepare-annotations', 'validate-annotations', 'import-annotations'):
            run(name+'-help', ['tools/rehab_ml/cli.py', name, '--help'])
        run('unit', ['-m', 'unittest', 'discover', '-s', 'tests/rehab_backend',
                     '-p', 'test_professional_annotations.py', '-v'])
        prepared = run('prepare', ['tools/rehab_ml/cli.py', 'prepare-annotations', '--receipt', str(args.receipt),
                                   '--output-dir', str(root/'cohort')], json_result=True)
        bundle = Path(prepared['bundle'])
        validation = run('validate', ['tools/rehab_ml/cli.py', 'validate-annotations', '--bundle', str(bundle),
                                     '--output-dir', str(root/'validation')], json_result=True)
        if (prepared['samples'] != 24 or prepared['split_counts'] != {'train': 14, 'val': 5, 'test': 5}
                or validation['pending'] != 24 or validation['known_labels'] != 0
                or validation['approved'] != 0 or validation['pose_labels_available'] is not False):
            raise RuntimeError('Actual cohort or empty supervision expectation changed')
        run('blank-import-refused', ['tools/rehab_ml/cli.py', 'import-annotations', '--bundle', str(bundle),
                                    '--output-dir', str(root/'must-not-import')], expected=1)
        if (root/'must-not-import').exists():
            raise RuntimeError('Refused import created a reference output')
        original_hashes = {str(path.relative_to(bundle.parent)): file_hash(path)
                           for path in bundle.parent.iterdir() if path.is_file()}
        for attack in ('score-prefill', 'split-change', 'rewritten-timeline'):
            target = root/('TEST-'+attack)
            shutil.copytree(bundle.parent, target)
            manifest = read_json(target/'bundle.json')
            if attack == 'score-prefill':
                form = target/'annotator-A.jsonl'
                rows = read_rows(form)
                rows[0]['video_score'] = 99
                form.unlink()  # only this freshly-created owned TEST copy
                _rows_write(form, rows)
            elif attack == 'split-change':
                manifest['samples'][0]['split'] = 'train'
            else:
                sample = manifest['samples'][0]
                timeline = target/sample['timeline_ref']
                media = read_json(timeline)
                media['presentation_s'][1] += .0001
                write_json(timeline, media)
                sample['timeline_sha256'] = file_hash(timeline)
            if attack != 'score-prefill':
                manifest.pop('manifest_digest')
                manifest['manifest_digest'] = canonical_hash(manifest)
                write_json(target/'bundle.json', manifest)
            run(attack+'-refused', ['tools/rehab_ml/cli.py', 'validate-annotations',
                '--bundle', str(target/'bundle.json'), '--output-dir', str(root/('must-not-'+attack))], expected=1)
            if (root/('must-not-'+attack)).exists():
                raise RuntimeError('Rejected TEST mutation created a qualified output')
        after = {str(path.relative_to(bundle.parent)): file_hash(path)
                 for path in bundle.parent.iterdir() if path.is_file()}
        if after != original_hashes:
            raise RuntimeError('Original annotation forms changed during TEST checks')
        run('scope', ['tools/rehab_ml/cli.py', 'verify-scope', '--baseline',
                      'reports/rehab_backend/protected_files.json'])
        if any(file_hash(ROOT/relative) != expected for relative, expected in summary['implementation_sha256'].items()):
            raise RuntimeError('Implementation changed during verification')
        summary.update(passed=True, prepared=prepared,
                       validation={key: value for key, value in validation.items() if key != 'disagreements'},
                       original_bundle_files_unchanged=True, reference_generated=False,
                       actual_video_count=24, actual_video_bytes=680355016,
                       pending_professional_review=24, mutation_rejections=3)
    except Exception as exc:
        summary.update(passed=False, error_type=type(exc).__name__, error=str(exc))
    write_json(root/'summary.json', summary)
    public = copy.deepcopy(summary)
    public['summary_sha256'] = file_hash(root/'summary.json')
    public['artifact'] = str(root/'summary.json')
    write_json(ROOT/'reports/rehab_backend/professional_annotation_verification.json', public)
    print(json.dumps(public, ensure_ascii=False, allow_nan=False))
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
