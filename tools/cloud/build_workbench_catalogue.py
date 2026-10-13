"""Export existing pure measurement contracts; this does not execute models."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def catalogue():
    path = ROOT / "rehab_codex_single_camera_v2_1/app/exercises.py"
    spec = importlib.util.spec_from_file_location("workbench_source_exercises", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = []
    for ident in module.EXERCISE_IDS:
        source = module.exercise_spec(ident)
        result.append({"action_id": ident, "exercise_id": ident, "name": source["label"],
            "measurement_contract": source["measurement_contract"], "description": source["guide"],
            "experimental": source["experimental"], "measurement_type": source["measurement_type"],
            "clinical_rom": source["clinical_rom"]})
    return {"schema": "ankang-existing-exercises-1", "source": "app/exercises.py", "items": result}


if __name__ == "__main__":
    target = ROOT / "cloud_service/exercises.json"
    target.write_text(json.dumps(catalogue(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Existing measurement contracts exported")
