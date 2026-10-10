"""Publish only non-identifying validation summaries, never private RGB/keypoints."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.rehab_ml.common import file_hash, paths, read_json, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('results', nargs='+', type=Path)
    args = parser.parse_args()
    rows = []
    for path in args.results:
        path = path.resolve()
        if not path.is_relative_to(paths()['run']) or path.name != 'result.json':
            raise ValueError('Only an explicit local analysis result under the run root is accepted')
        value = read_json(path)
        if value['training_authorized'] is not False or value['professional_labels_available'] is not False:
            raise ValueError('This summary is only for unannotated, analysis-only private replay')
        rows.append(dict(result_file_sha256=file_hash(path), video_sha256=value['video_sha256'],
            exercise_id=value['exercise_id'], side=value['side'], frames=value['frames'],
            observable_frames=value['observable_frames'], observed_fraction=value['observed_fraction'],
            v2_completed=value['v2_summary']['completed'],
            legacy_completed=value['legacy_summary']['completed'] if value['legacy_summary'] else None,
            baseline_available=value['v2_summary']['baseline'] is not None,
            input_timing=value['input_timing'], elapsed_s=value['elapsed_s'], latency_ms=value['latency_ms'],
            model_manifest_id=value['model_manifest_id'], training_authorized=False,
            professional_labels_available=False, clinical_accuracy=None, count_accuracy=None,
            status='pipeline_completed_not_accuracy_acceptance'))
    print(write_json(ROOT / 'reports/rehab_backend/target_replay_summary.json',
        dict(results=rows, private_RGB_and_keypoints_published=False,
            limitation='Two clips without a stable observed baseline or adequate knee evidence; no independent reference or real-world accuracy estimate')))


if __name__ == '__main__':
    main()
