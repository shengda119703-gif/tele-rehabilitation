"""Check a built review against its immutable mechanics and source files."""
import argparse
import hashlib
import json
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args()
    root = args.root
    audit = read(root / "provenance.json")
    checks = []
    for record in audit["clips"]:
        for file, digest in record["source_hashes"].items():
            assert sha(file) == digest, file
        clip = read(root / record["id"] / "data.json")
        assert sha(root / record["id"] / "video.mp4") == record["source_video_sha256"]
        files = record["source_hashes"]
        mechanics = next((file for file in files if file.endswith("器械跟踪与计算.json")), None)
        mechanics = mechanics or next(file for file in files if file.endswith("人体模型计算.json"))
        series = read(mechanics)["series"]
        compared = 0
        for sample, original in zip(clip["samples"], series):
            assert sample["t"] == original["t"]
            for key, source_key in (("power", "power_w"), ("speed", "velocity_m_s")):
                if key in sample["values"]:
                    assert sample["values"][key] == original.get(source_key)
                    compared += 1
        assert all("completed" not in m["key"] for m in clip["metrics"])
        if clip["view"] == "侧面":
            assert next(m for m in clip["metrics"] if m["key"] == "sway_x")["label"] == "骨盆前后位移"
        for sample in clip["samples"]:
            for side in ("left", "right"):
                for name in ("hip", "knee", "ankle"):
                    point = sample["points"].get(side + "_" + name)
                    if point:
                        x0, y0, x1, y1 = clip["crop"]
                        assert x0 <= point[0] * 1280 <= x1
                        assert y0 <= point[1] * 720 <= y1
        checks.append(dict(id=clip["id"], raw_hashes_unchanged=True,
                           video_hash_unchanged=True, mechanics_values_compared=compared,
                           pose_in_crop=True, repetitions_not_exposed=True))
    print(json.dumps(dict(clips=checks, passed=True), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
