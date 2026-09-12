"""Export the complete action-image manifest used by the desktop UI."""
from __future__ import annotations

import csv
import sys
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.exercise_instructions import JOINT_LABELS, exercise_instructions  # noqa: E402
from app.exercises import EXERCISE_IDS  # noqa: E402


SIDES = (("left", "左侧"), ("right", "右侧"))
PHASES = (
    ("start", "准备姿势", "start.png"),
    ("move", "完成动作", "move.png"),
    ("return", "返回起点", "return.png"),
)
FIELDNAMES = (
    "序号",
    "动作ID",
    "动作名称",
    "身体部位",
    "测试侧",
    "阶段",
    "建议原图文件名",
    "项目目标路径",
    "画面内容提示",
    "拍摄要求",
    "待导入图片路径",
    "匹配状态",
    "备注",
)


def build_rows() -> list[dict[str, str | int]]:
    rows: list[dict[str, str | int]] = []
    for exercise_id in EXERCISE_IDS:
        info = exercise_instructions(exercise_id)
        for side_id, side_label in SIDES:
            for phase_id, phase_label, target_name in PHASES:
                rows.append({
                    "序号": len(rows) + 1,
                    "动作ID": exercise_id,
                    "动作名称": info["label"],
                    "身体部位": JOINT_LABELS[info["joint"]],
                    "测试侧": side_label,
                    "阶段": phase_label,
                    "建议原图文件名": (
                        f"{exercise_id}_{side_id}_{phase_id}_{info['label']}_{side_label}_{phase_label}.png"
                    ),
                    "项目目标路径": (
                        f"rehab_codex_single_camera_v2_1/assets/exercise-guides/"
                        f"{exercise_id}/{side_id}/{target_name}"
                    ),
                    "画面内容提示": info[{"start": "start", "move": "move", "return": "return"}[phase_id]],
                    "拍摄要求": info["camera"],
                    "待导入图片路径": "",
                    "匹配状态": "待提供",
                    "备注": "",
                })
    expected = len(EXERCISE_IDS) * len(SIDES) * len(PHASES)
    if len(rows) != expected:
        raise RuntimeError(f"图片清单数量异常：{len(rows)} != {expected}")
    return rows


def main() -> None:
    output = REPO_ROOT / "docs" / "assets" / "EXERCISE_IMAGE_MANIFEST.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = build_rows()
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    print(f"已生成 {output}：{len(EXERCISE_IDS)} 个动作，共 {len(rows)} 张图片。")


if __name__ == "__main__":
    main()
