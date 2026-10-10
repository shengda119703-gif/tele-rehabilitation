"""Actual CLI round trip on explicitly synthetic fixtures, not human accuracy."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.rehab_ml.common import ROOT, file_hash, paths, read_json, write_json
from tools.rehab_ml.pose_dataset import JOINTS, REFERENCE_VERSION


def main():
    from PIL import Image
    root = paths()['run']/('pose-tools-'+uuid4().hex[:8])
    root.mkdir()
    evidence = root/'TEST-permission.txt'
    evidence.write_text('SYNTHETIC TOOL FIXTURE. No human footage, training or clinical validation.', encoding='utf-8')
    reference = dict(schema_version=REFERENCE_VERSION, schema_id='coco17-v1', coordinate_space='raw_image_pixels',
        keypoint_order=list(JOINTS), dataset_id='TEST-cli-pose-tools', usage_context='TEST',
        permissions=dict(analysis=True, training=True, verified_by='TEST-reviewer',
                         evidence_ref=evidence.name, evidence_sha256=file_hash(evidence)), samples=[])
    for index, split in enumerate(('train', 'val', 'test')):
        image = root/(split+'.png')
        Image.new('RGB', (64, 64), (200+index*10,)*3).save(image)
        reference['samples'].append(dict(sample_id='TEST-'+split, subject_group='TEST-person-'+split,
            recording_id='TEST-recording-'+split, split=split, exercise_id='shoulder_abduction', side='left', view='front',
            image_ref=image.name, image_sha256=file_hash(image), frame_seq=0, source_time_s=0.,
            time_basis='synthetic_test_time', frame_size=[64, 64], bbox_xyxy_px=[0., 0., 64., 64.],
            bbox_origin='fixture_box', xy=[[10.+i, 15.+i%3] for i in range(17)], visibility=[2]*17,
            annotation_mask=[True]*17, annotations=dict(origin='synthetic_fixture', annotator='TEST-annotator',
                reviewer='TEST-reviewer', version='TEST-v1', independently_reviewed=True)))
    source = Path(write_json(root/'reference.json', reference))
    reference['samples'][0]['xy'][0] = reference['samples'][0]['visibility'][0] = None
    reference['samples'][0]['annotation_mask'][0] = False
    partial = Path(write_json(root/'partial-reference.json', reference))
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
        PYTHONPATH=os.pathsep.join((str(ROOT/'tests/rehab_backend'), str(ROOT/'rehab_codex_single_camera_v2_1'), str(ROOT))))
    temporary = root/'process-temp'
    temporary.mkdir()
    environment.update(TEMP=str(temporary), TMP=str(temporary))
    cli = ['tools/rehab_ml/cli.py']
    steps = [
        ('unit', ['-m', 'unittest', '-v', 'test_pose_dataset'], 0),
        ('masked', cli+['build-pose-dataset', '--reference', str(source), '--target-schema', 'coco17',
                       '--output-dir', str(root/'masked')], 0),
        ('yolo', cli+['build-pose-dataset', '--reference', str(source), '--target-schema', 'coco17',
                     '--output-format', 'yolo_pose', '--output-dir', str(root/'yolo')], 0),
        ('baseline', cli+['infer-pose-reference', '--reference', str(source), '--split', 'test',
                         '--output-dir', str(root/'baseline')], 0),
        ('evaluation', cli+['evaluate-pose', '--reference', str(source), '--predictions', str(root/'baseline/predictions.json'),
                           '--split', 'test', '--output-dir', str(root/'evaluation')], 0),
        ('reject_partial_stock_yolo', cli+['build-pose-dataset', '--reference', str(partial), '--target-schema', 'coco17',
                                         '--output-format', 'yolo_pose', '--output-dir', str(root/'must-not-exist')], 1),
        ('reject_unqualified_training', cli+['train-pose', '--config', 'configs/rehab_ml/backend.yaml'], 1),
    ]
    summary = dict(run_id=root.name, evidence_scope='synthetic_tool_verification_not_target_accuracy',
                   commands=[], artifact_hashes={}, training_performed=False, clinical_accuracy=None)
    summary['implementation_sha256'] = {relative: file_hash(ROOT/relative) for relative in (
        'tools/rehab_ml/pose_dataset.py', 'tools/rehab_ml/pose_inference.py', 'tools/rehab_ml/cli.py',
        'tools/rehab_ml/target_domain.py', 'tools/rehab_ml/verify_pose_tools.py',
        'tests/rehab_backend/test_pose_dataset.py', 'configs/rehab_ml/pose-reference-template.json')}
    try:
        for name, arguments, expected in steps:
            started = time.perf_counter()
            process = subprocess.run([sys.executable, '-X', 'utf8', '-B', *arguments], cwd=ROOT, env=environment,
                                     capture_output=True, text=True, encoding='utf-8', timeout=60)
            log = root/(name+'.txt')
            log.write_text(process.stdout+process.stderr, encoding='utf-8')
            summary['commands'].append(dict(name=name, arguments=arguments, exit_code=process.returncode,
                expected_exit_code=expected, passed=process.returncode == expected, elapsed_s=time.perf_counter()-started,
                log=str(log), log_sha256=file_hash(log), tail=(process.stdout+process.stderr)[-700:]))
            if process.returncode != expected:
                raise RuntimeError('pose_tool_step_failed:'+name)
        evaluation = read_json(root/'evaluation/evaluation.json')
        if (evaluation['summary']['coordinate_coverage'] != 0.
                or evaluation['summary']['mean_euclidean_error_px'] is not None
                or (root/'must-not-exist').exists()):
            raise RuntimeError('unobserved_or_unannotated_fixture_was_treated_as_measurement')
        for relative in ('reference.json', 'masked/conversion.json', 'yolo/conversion.json', 'yolo/dataset.yaml',
                         'baseline/predictions.json', 'evaluation/evaluation.json'):
            summary['artifact_hashes'][relative] = file_hash(root/relative)
        summary.update(passed=True, unobserved_fixture_coverage=evaluation['summary']['coordinate_coverage'])
    except Exception as error:
        summary.update(passed=False, failure_type=type(error).__name__, failure=str(error))
    write_json(root/'verification.json', summary)
    path = write_json(ROOT/'reports/rehab_backend/pose_tools_verification.json', summary)
    print(json.dumps(dict(path=path, passed=summary['passed'], run_id=root.name, clinical_accuracy=None)))
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
