"""Private actual-video smoke run. Does not touch patient databases or services."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mobile_rehab.fitness_analyzer import analyze


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--video', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    original = hashlib.sha256(args.video.read_bytes()).hexdigest()
    args.output.mkdir(parents=True, exist_ok=False)
    shutil.copy2(args.video, args.output/'video.mp4')
    job = dict(id='private-automatic-motion-verification', exercise='fitness_squat', side='left', mode='fitness')
    (args.output/'job.json').write_text(json.dumps(job), encoding='utf-8')
    started = time.monotonic()
    analyze(args.output/'job.json')
    result = json.loads((args.output/'result.json').read_text(encoding='utf-8'))
    assert hashlib.sha256(args.video.read_bytes()).hexdigest() == original
    assert result['equipment_analysis']['mode'] == 'automatic'
    bar = result['barbell']
    assert bar is not None and bar['automatic'] and not bar['synthetic']
    assert bar['calibration']['mass_kg'] is None
    summary = dict(source_sha256=original, processed_frames=result['processed_frames'],
                   completed=result['summary']['completed'], automatic=True, manual_marks=0,
                   measurement=bar['measurement'], trajectory_summary=bar['summary'],
                   elapsed_s=round(time.monotonic()-started, 3))
    (args.output/'verification.json').write_text(json.dumps(summary, ensure_ascii=False, allow_nan=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
