"""Validate the portable image handoff against its source documents and files."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import struct
import sys
from collections import Counter
from pathlib import Path, PurePosixPath, PureWindowsPath

try:
    from PIL import Image
except ImportError:
    Image = None


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FIELDS = {
    "region": "区域", "level": "等级", "objective": "目标",
    "equipment": "器材", "start_conditions": "开始条件",
    "preparation": "准备与起始位", "instructions": "操作步骤",
    "key_points": "关键要领", "common_errors": "常见错误",
    "source_dose": "试做与候选剂量／评估协议", "regression": "退阶",
    "progression": "进阶", "stop_conditions": "停止或调整条件",
    "camera": "机位与画面", "observable": "视觉可以观察",
    "not_observable": "视觉不能直接判定", "insufficient_observation": "观察不足时",
    "action_sources": "动作出处与对应原文", "evidence_scope": "证据性质与适用范围",
    "basis": "依据",
}
OPTIONAL_FIELDS = {
    "single_person": "单人适用", "vision_module": "视觉模块",
    "reassessment": "复评与训练成果", "design_trace": "设计与见习追溯",
}


class ValidationError(Exception):
    pass


def check(condition, message):
    if not condition:
        raise ValidationError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest().upper()


def repository_path(value, *, allow_empty=False):
    if value == "" and allow_empty:
        return None
    check(isinstance(value, str) and bool(value), f"Missing repository path: {value!r}")
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    check(not posix.is_absolute() and not windows.drive and not windows.root,
          f"Absolute path is not portable: {value}")
    check("\\" not in value and ".." not in posix.parts and ":" not in value,
          f"Unsafe or nonportable path: {value}")
    resolved = (ROOT / value).resolve()
    check(resolved.is_relative_to(ROOT), f"Path escapes the repository: {value}")
    return resolved


def document_sections(text, heading_pattern, maximum_level):
    """Read sections line by line so heading boundaries are independently checked."""
    sections = []
    active = None
    body = []
    for line in text.splitlines():
        heading = re.match(r"^(#{1,6}) ", line)
        if heading and len(heading[1]) <= maximum_level:
            if active is not None:
                sections.append((active, "\n".join(body)))
                active, body = None, []
            match = re.fullmatch(heading_pattern, line)
            if match:
                active = match.groups()
        elif active is not None:
            body.append(line)
    if active is not None:
        sections.append((active, "\n".join(body)))
    return sections


def source_cards(text):
    result = {}
    for (action_id, name), raw_body in document_sections(
            text, r"#### ([ET]-[A-Z]+-\d+)｜(.+)", 4):
        lines = raw_body.splitlines()
        while lines and (not lines[-1].strip() or lines[-1].strip() == "---"
                         or re.fullmatch(r'<a id="[^"]+"></a>', lines[-1].strip())):
            lines.pop()
        content = "\n".join(lines).strip()
        markers = list(re.finditer(r"\*\*([^*\n]+)\*\*", content))
        fields = {}
        for index, marker in enumerate(markers):
            label = marker[1].rstrip("：:")
            end = markers[index + 1].start() if index + 1 < len(markers) else len(content)
            value = content[marker.end():end]
            if value.startswith(("：", ":")):
                value = value[1:]
            fields.setdefault(label, []).append(value.strip())
        check(action_id not in result, f"Repeated source card: {action_id}")
        result[action_id] = {"name": name.strip(), "content": content,
                             "fields": {label: "\n\n".join(values) for label, values in fields.items()}}
    return result


def image_plans(text):
    result = {}
    for (sequence, action_id, name), body in document_sections(
            text, r"### (\d{3}) ([ET]-[A-Z]+-\d+)｜(.+)", 3):
        count = re.search(r"首轮示范图：\*\*(\d+)\s*张\*\*", body)
        check(count is not None, f"Missing planned frame count: {sequence}")
        frames = []
        for line in body.splitlines():
            row = re.fullmatch(r"\|\s*(\d{2})\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|", line)
            if row:
                frames.append((int(row[1]), row[2].strip(), row[3].strip()))
        check(len(frames) == int(count[1]), f"Plan row/count mismatch: {sequence}")
        check([row[0] for row in frames] == list(range(1, len(frames) + 1)),
              f"Plan frame sequence mismatch: {sequence}")
        line_fields = {}
        for line in body.splitlines():
            if "：" in line:
                label, value = line.split("：", 1)
                line_fields.setdefault(label, []).append(value.strip())
        line_fields = {label: "\n".join(values) for label, values in line_fields.items()}
        image_type = re.search(r"示范类型：([^\n]+)", body)
        check(sequence not in result, f"Repeated plan sequence: {sequence}")
        result[sequence] = {
            "id": action_id, "name": name.strip(), "frames": frames,
            "content": body.strip(), "image_type": image_type[1].strip() if image_type else "",
            "image_version_camera": line_fields.get("基础版本与机位", ""),
            "sequence_reuse": line_fields.get("顺序／复用", ""),
            "extensions": line_fields.get("扩展版本（不计入首轮）", ""),
        }
    return result


def csv_text(value):
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def validate_csv(catalogue, folder):
    tables = {
        "actions": [{**action, "overview_path": action["overview"]["image_path"],
                     "step_paths": [step["image_path"] for step in action["steps"]]}
                    for action in catalogue["actions"]],
        "steps": [step for action in catalogue["actions"] for step in action["steps"]],
        "image_manifest": catalogue["images"],
        "image_candidates": catalogue["candidates"],
    }
    check(set(catalogue["csv_columns"]) == set(tables), "Unexpected CSV table mapping")
    cells = 0
    for table_name, expected_rows in tables.items():
        columns = catalogue["csv_columns"][table_name]
        labels = [label for _, label in columns]
        check(len(labels) == len(set(labels)), f"Duplicate CSV headers: {table_name}")
        with (folder / f"{table_name}.csv").open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            check(reader.fieldnames == labels, f"CSV column mismatch: {table_name}")
            rows = list(reader)
        check(len(rows) == len(expected_rows), f"CSV row count mismatch: {table_name}")
        for row_number, (row, expected) in enumerate(zip(rows, expected_rows), start=2):
            check(None not in row and all(value is not None for value in row.values()),
                  f"Malformed CSV record: {table_name}/{row_number}")
            for key, label in columns:
                check(row[label] == csv_text(expected.get(key)),
                      f"CSV value mismatch: {table_name}/{row_number}/{key}")
                cells += 1
    return cells


def validate(catalogue_file, require_complete):
    catalogue = json.loads(catalogue_file.read_text(encoding="utf-8"))
    check(catalogue["schema_version"] == 1, "Unsupported handoff schema")
    check(catalogue["repository_relative_paths"] is True, "Relative-path declaration missing")
    asset_root = catalogue["asset_root"]
    repository_path(asset_root)
    repository_path(catalogue["docs_root"])
    snapshots = {}
    for label in ("action_document", "image_plan"):
        source = catalogue["sources"][label]
        data = repository_path(source["path"]).read_bytes()
        check(sha256(data) == source["sha256"], f"Source snapshot hash mismatch: {label}")
        snapshots[label] = data.decode("utf-8").replace("\r\n", "\n")
    current_source = ROOT / "docs/rehab-library/SOURCE_v1.0.md"
    check(sha256(current_source.read_bytes()) == catalogue["sources"]["action_document"]["sha256"],
          "Action snapshot does not match the repository source")
    originals = source_cards(snapshots["action_document"])
    plans = image_plans(snapshots["image_plan"])
    check(len(originals) == len(plans) == 185, "Expected 185 source cards and plans")
    expected_sequences = [f"{number:03d}" for number in range(1, 186)]
    check(sorted(plans) == expected_sequences, "Plan does not contain sequences 001-185")

    actions = catalogue["actions"]
    check(len(actions) == 185, "Expected 185 action records")
    check([action["sequence"] for action in actions] == expected_sequences,
          "Action sequences must be unique three-digit numbers 001-185")
    check(len({action["action_id"] for action in actions}) == 185, "Duplicate action IDs")
    check({action["action_id"] for action in actions} == set(originals), "Source/action ID mismatch")
    check(Counter(action["kind"] for action in actions) == {"assessment": 63, "training": 122},
          "Expected 63 assessment cards and 122 training cards")
    all_steps = []
    for action in actions:
        sequence, action_id = action["sequence"], action["action_id"]
        original, plan = originals[action_id], plans[sequence]
        check(plan["id"] == action_id and plan["name"] == original["name"] == action["action_name"],
              f"Action source/plan identity mismatch: {sequence}")
        kind = "assessment" if action_id.startswith("E-") else "training"
        check(action["kind"] == kind, f"Action kind does not match ID: {action_id}")
        check(action["category"] in catalogue["categories"], f"Unknown category: {sequence}")
        check(action["category_label"] == catalogue["categories"][action["category"]],
              f"Category label mismatch: {sequence}")
        for key, label in {**REQUIRED_FIELDS, **OPTIONAL_FIELDS}.items():
            expected = original["fields"].get(label, "")
            check(key not in REQUIRED_FIELDS or bool(expected), f"Required source field missing: {action_id}/{label}")
            check(action.get(key) == expected, f"Source field was changed or lost: {action_id}/{label}")
        check(action["introduction"] == original["fields"]["目标"], f"Introduction changed: {action_id}")
        check(action["source_content"] == original["content"], f"Full source card changed: {action_id}")
        refs = list(dict.fromkeys(re.findall(r"\[([A-Z]+-S\d+)\]", original["content"])))
        check(action["source_refs"] == refs, f"Source references changed or lost: {action_id}")
        card = repository_path(action["source_card_path"]).read_text(encoding="utf-8")
        expected_card = f"# {sequence} {action_id}｜{original['name']}\n\n{original['content']}\n"
        check(card == expected_card, f"Per-action Markdown card changed: {action_id}")
        check(action["image_plan_content"] == plan["content"], f"Full image plan changed: {sequence}")
        for key in ("image_type", "image_version_camera", "sequence_reuse", "extensions"):
            check(action[key] == plan[key], f"Image plan field changed: {sequence}/{key}")
        check(action["expected_steps"] == len(action["steps"]) == len(plan["frames"]),
              f"Action frame count mismatch: {sequence}")
        action_directory = f"{asset_root}/{kind}/{action['category']}/{sequence}_{action_id}"
        check(action["steps_directory"] == f"{action_directory}/steps",
              f"Action directory classification mismatch: {sequence}")
        repository_path(action["steps_directory"])
        check(action["overview"]["expected_image_path"] == f"{action_directory}/overview.png",
              f"Overview directory mismatch: {sequence}")
        for step, (number, description, points) in zip(action["steps"], plan["frames"]):
            check(step["step_number"] == number and step["step_id"] == f"s{number:02d}",
                  f"Step numbering mismatch: {sequence}/{number}")
            check(step["frame_description"] == description and step["check_points"] == points,
                  f"Step description/check points changed: {sequence}/{number}")
            check(all(step[key] == action[key] for key in ("sequence", "action_id", "action_name", "kind", "category")),
                  f"Step/action identity mismatch: {sequence}/{number}")
            check(step["slot_id"] == f"{sequence}_{action_id}_s{number:02d}",
                  f"Step slot mismatch: {sequence}/{number}")
            check(step["expected_image_path"] == f"{action_directory}/steps/{step['slot_id']}.png",
                  f"Step directory mismatch: {sequence}/{number}")
        available = sum(step["file_status"] == "present" for step in action["steps"])
        missing = [step["step_id"] for step in action["steps"] if step["file_status"] != "present"]
        check(action["available_steps"] == available and action["missing_steps"] == missing,
              f"Incorrect availability summary: {sequence}")
        complete = available == len(action["steps"]) and action["overview"]["file_status"] == "present"
        check(action["file_status"] == ("complete" if complete else "incomplete"),
              f"Incorrect action completion status: {sequence}")
        all_steps.extend(action["steps"])
    check(len(all_steps) == 471, "Expected 471 planned steps")
    by_sequence = {action["sequence"]: action for action in actions}
    for sequence, groups in {
            "055": ["I", "Y", "T", "W"], "158": ["I", "Y", "T", "W"],
            "116": ["dorsiflexion", "plantarflexion", "inversion", "eversion"]}.items():
        steps = by_sequence[sequence]["steps"]
        check(len(steps) == 8, f"Independent route plan requires eight frames: {sequence}")
        check([step["group_id"] for step in steps] == [group for group in groups for _ in range(2)],
              f"Independent routes are not paired correctly: {sequence}")
        check(len({step["group_label"] for step in steps}) == 4 and
              all(steps[i]["group_label"] == steps[i + 1]["group_label"] for i in range(0, 8, 2)),
              f"Independent route labels do not form four pairs: {sequence}")

    images = catalogue["images"]
    check(Counter(image["role"] for image in images) == {"step": 471, "overview": 185},
          "Expected 471 step slots and 185 overview slots")
    image_by_slot = {image["slot_id"]: image for image in images}
    check(len(image_by_slot) == len(images), "Duplicate image slots")
    for action in actions:
        for step in action["steps"]:
            check(image_by_slot.get(step["slot_id"]) == {**step, "role": "step"},
                  f"Flattened step manifest differs: {step['slot_id']}")
        overview = action["overview"]
        check(overview["slot_id"] == f"{action['sequence']}_{action['action_id']}_overview",
              f"Overview slot mismatch: {action['sequence']}")
        expected = {key: action[key] for key in ("sequence", "action_id", "action_name", "kind", "category")}
        expected.update({"role": "overview", "step_number": 0, **overview})
        check(image_by_slot.get(overview["slot_id"]) == expected,
              f"Flattened overview manifest differs: {overview['slot_id']}")

    png_cache = {}

    def validate_png(record, path_key):
        relative = record[path_key]
        actual = repository_path(relative)
        check(actual.suffix.lower() == ".png", f"Image must be PNG: {relative}")
        if relative not in png_cache:
            data = actual.read_bytes()
            check(data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 33 and data[12:16] == b"IHDR",
                  f"Invalid PNG header: {relative}")
            width, height = struct.unpack(">II", data[16:24])
            check(width > 0 and height > 0, f"Invalid PNG dimensions: {relative}")
            if Image is not None:
                with Image.open(io.BytesIO(data)) as image:
                    check(image.format == "PNG" and image.size == (width, height),
                          f"PNG decoder/header mismatch: {relative}")
                    image.verify()
                with Image.open(io.BytesIO(data)) as image:
                    image.load()
            png_cache[relative] = {"sha256": sha256(data), "bytes": len(data), "width": width, "height": height}
        check(all(record[key] == value for key, value in png_cache[relative].items()),
              f"PNG hash/size/dimensions mismatch: {relative}")

    candidates = catalogue["candidates"]
    candidate_by_source = {candidate["source_path"]: candidate for candidate in candidates}
    check(len(candidate_by_source) == len(candidates), "Candidate sources are not unique")
    check(len({candidate["packaged_path"] for candidate in candidates}) == len(candidates),
          "Candidate packaged paths are not one-to-one")
    selected_sources = set()
    archived = 0
    for candidate in candidates:
        check(type(candidate["selected"]) is bool, "Candidate selected flag must be a boolean")
        check(candidate["sequence"] in by_sequence and
              by_sequence[candidate["sequence"]]["action_id"] == candidate["action_id"],
              f"Candidate/action identity mismatch: {candidate['source_path']}")
        check(PurePosixPath(candidate["source_path"]).name == candidate["source_filename"],
              f"Candidate source filename mismatch: {candidate['source_path']}")
        validate_png(candidate, "packaged_path")
        if candidate["selected"]:
            check(not candidate.get("archive_path") and
                  not candidate["packaged_path"].startswith(f"{asset_root}/archive/"),
                  f"Selected candidate is archived: {candidate['source_path']}")
            selected_sources.add(candidate["source_path"])
        else:
            expected_archive = f"{asset_root}/archive/{candidate['source_path']}"
            check(candidate.get("archive_path") == candidate["packaged_path"] == expected_archive,
                  f"Candidate archive path was lost or changed: {candidate['source_path']}")
            check(candidate["selection_basis"] == "archived_not_for_runtime",
                  f"Archived candidate lacks its exclusion status: {candidate['source_path']}")
            archived += 1
    used_sources = []
    missing_images = []
    for image in images:
        repository_path(image["expected_image_path"])
        if image["file_status"] == "present":
            check(image["image_path"] == image["expected_image_path"], f"Selected image path mismatch: {image['slot_id']}")
            validate_png(image, "image_path")
            candidate = candidate_by_source.get(image["selected_source"])
            check(candidate is not None and candidate["selected"] is True,
                  f"Selected image has no selected candidate: {image['slot_id']}")
            check(candidate["slot_id"] == image["slot_id"] and candidate["packaged_path"] == image["image_path"],
                  f"Selected candidate slot/path mismatch: {image['slot_id']}")
            check(all(candidate[key] == image[key] for key in ("sha256", "bytes", "width", "height", "selection_basis", "selection_evidence")),
                  f"Selected image/candidate evidence mismatch: {image['slot_id']}")
            check(candidate.get("selection_note", "") == image.get("selection_note", ""),
                  f"Selected image/candidate note mismatch: {image['slot_id']}")
            used_sources.append(image["selected_source"])
        else:
            check(image["file_status"] in ("missing", "selection_pending"), f"Unknown file status: {image['slot_id']}")
            check(not image["image_path"] and not image["selected_source"] and not image["sha256"] and
                  all(image[key] == 0 for key in ("bytes", "width", "height")),
                  f"Unavailable image was reported as selected: {image['slot_id']}")
            matching = [candidate for candidate in candidates if candidate["slot_id"] == image["slot_id"]]
            check(image["file_status"] == ("selection_pending" if matching else "missing"),
                  f"Unavailable image reason is inaccurate: {image['slot_id']}")
            missing_images.append({"slot_id": image["slot_id"], "reason": image["file_status"]})
    check(len(used_sources) == len(set(used_sources)) and set(used_sources) == selected_sources,
          "Selected candidates and selected image slots are not one-to-one")
    for reference in catalogue["reference_images"]:
        validate_png(reference, "image_path")

    measured = {
        "actions": len(actions), "assessment": 63, "training": 122, "expected_steps": len(all_steps),
        "selected_steps": sum(step["file_status"] == "present" for step in all_steps),
        "missing_steps": sum(step["file_status"] != "present" for step in all_steps),
        "selected_overviews": sum(image["role"] == "overview" and image["file_status"] == "present" for image in images),
        "source_image_files": len(candidates), "archived_candidates": archived,
        "reference_images": len(catalogue["reference_images"]),
    }
    check(catalogue["counts"] == measured, "Catalogue counts do not match actual records")
    cells = validate_csv(catalogue, catalogue_file.parent)
    result = {
        "validation": "failed_incomplete" if require_complete and missing_images
        else "passed_with_missing" if missing_images else "passed",
        "counts": measured, "csv_cells_checked": cells,
        "png_files_checked": len(png_cache),
        "png_validation": "Pillow verify and complete pixel decoding" if Image is not None
        else "PNG header, SHA256, byte count and dimensions only; Pillow is unavailable",
        "missing": missing_images,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    check(not require_complete or not missing_images,
          "--require-complete failed: missing or undecided image slots remain")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalogue", type=Path,
                        default=ROOT / "docs/rehab-library/image-handoff/catalogue.json")
    parser.add_argument("--require-complete", action="store_true",
                        help="Fail when any planned step or overview is unavailable.")
    options = parser.parse_args()
    try:
        validate(options.catalogue.resolve(), options.require_complete)
    except (ValidationError, OSError, ValueError, KeyError, TypeError) as error:
        print(f"Handoff validation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
