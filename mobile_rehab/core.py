from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / 'rehab_codex_single_camera_v2_1'
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

from app.exercises import EXERCISE_IDS, exercise_spec
from app.exercise_instructions import exercise_instructions, JOINT_LABELS


def catalog():
    result = []
    for eid in EXERCISE_IDS:
        spec = exercise_spec(eid)
        backend = spec['backend']
        available = (CORE / 'assets/models/yolo11n-pose.pt').exists() if backend == 'yolo' else (
            (CORE / '.venv-landmarks/Scripts/python.exe').exists() or
            (CORE / '.venv-landmarks/bin/python').exists())
        result.append(dict(id=eid, label=spec['label'], joint=spec['joint'],
                           joint_label=JOINT_LABELS[spec['joint']], view=spec['view'],
                           experimental=spec['experimental'], backend=backend,
                           available=available, instructions=exercise_instructions(eid)))
    return result
