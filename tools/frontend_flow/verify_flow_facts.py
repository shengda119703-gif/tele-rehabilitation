"""Check the real hosted flow's saved facts without publishing private IDs/video."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'rehab_codex_single_camera_v2_1'))
from app.storage import Storage


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('flow', type=Path)
    args = parser.parse_args()
    receipt = json.loads((args.flow / 'result.json').read_text(encoding='utf-8'))
    jobs = list((args.flow / 'host-data/jobs').glob('*/*/job.json'))
    assert len(jobs) == receipt['owned_jobs'] == 1
    job = json.loads(jobs[0].read_text(encoding='utf-8'))
    result = json.loads((jobs[0].parent / 'result.json').read_text(encoding='utf-8'))
    store = Storage(jobs[0].parent.parent / 'assessments.sqlite3')
    try:
        sessions = store.list_sessions()
        session = store.get_session(result['session_id'])
    finally:
        store.close()
    assert session is not None and len(sessions) == 1
    assert session['participant_id'] == job['owner']
    assert session['exercise_id'] == 'shoulder_abduction' and session['side'] == 'left'
    assert session['source_kind'] == 'REPLAY_FILE' and session['submode'] == 'assessment'
    assert session['summary']['completed'] == result['summary']['completed'] == receipt['summary']['completed']
    assert hashlib.sha256((jobs[0].parent / 'video.mp4').read_bytes()).hexdigest() == receipt['input_sha256']
    verified = dict(kind='actual-owned-sqlite-verification',owned_jobs=1,saved_sessions=1,
                    source_kind=session['source_kind'],submode=session['submode'],
                    confirmed_count=session['summary']['completed'],video_hash_matches_original=True,
                    private_ids_published=False)
    (args.flow / 'facts-verified.json').write_text(json.dumps(verified, indent=2), encoding='utf-8')
    print(json.dumps(verified))


if __name__ == '__main__':
    main()
