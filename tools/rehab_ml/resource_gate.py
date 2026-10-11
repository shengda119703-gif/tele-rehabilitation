"""Lightweight import bridge for actual offline work, including Python 3.12."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
CORE = str(ROOT / 'rehab_codex_single_camera_v2_1')
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from app.rehab_v2.resources import ComputeLease


def heavy_compute():
    # Never use REHAB_RUN_ROOT here: output isolation must not bypass capacity.
    return ComputeLease('heavy')
