"""Build a private, read-only motion review from preserved software exports.

No model inference, account writes or clinical upload. Generated media/data stay
outside Git. Body and bar mechanics are copied, not recomputed by this viewer.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import statistics

import numpy as np

VERSION = "1.0.0"
UI = Path(__file__).parent / "ui"
CROPS = {
    "01": [300, 0, 950, 720], "02": [400, 0, 1010, 720],
    "03": [330, 0, 980, 720], "04": [300, 0, 1050, 720],
    "05": [200, 0, 1090, 720], "06": [220, 0, 840, 720],
}


def finite(v):
    return type(v) in (int, float) and math.isfinite(v)


def valid(values):
    return [float(v) for v in values if finite(v)]


def med(values):
    vs = valid(values)
    return statistics.median(vs) if vs else None


def extent(values):
    vs = valid(values)
    return max(vs) - min(vs) if vs else None


def sha(path):
    with Path(path).open("rb") as stream:
        h = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, allow_nan=False,
                                    separators=(",", ":")), encoding="utf-8")


def pixel(points, key):
    p = points.get(key)
    return np.array(p[:2], dtype=float) * [1280, 720] if p is not None else None


def angle(a, b, c):
    if any(p is None for p in (a, b, c)):
        return None
    u, v = a - b, c - b
    den = float(np.linalg.norm(u) * np.linalg.norm(v))
    return math.degrees(math.acos(float(np.clip(np.dot(u, v) / den, -1, 1)))) if den > 1e-8 else None


def tilt(a, b):
    if a is None or b is None or np.linalg.norm(a - b) < 1e-8:
        return None
    return math.degrees(math.atan2(float(a[0] - b[0]), abs(float(a[1] - b[1]))))


def line_tilt(a, b):
    if a is None or b is None or np.linalg.norm(a - b) < 1e-8:
        return None
    return math.degrees(math.atan2(abs(float(a[1] - b[1])), abs(float(a[0] - b[0]))))


def knee_alignment(points, scale):
    ankles = [pixel(points, s + "_ankle") for s in ("left", "right")]
    if any(p is None for p in ankles):
        return {}
    center = (ankles[0][0] + ankles[1][0]) / 2
    result = {}
    for s in ("left", "right"):
        h, k, a, heel, toe = [pixel(points, s + "_" + n)
                             for n in ("hip", "knee", "ankle", "heel", "foot_index")]
        if any(p is None for p in (h, k, a, heel, toe)) or a[1] - h[1] <= 25:
            continue
        sign = 1 if a[0] > center else -1
        xline = h[0] + np.clip((k[1] - h[1]) / (a[1] - h[1]), 0, 1) * (a[0] - h[0])
        result[s + "_inward"] = float(max(0., sign * (xline - k[0])) * scale * 100)
        edge = max(sign * p[0] for p in (a, heel, toe))
        result[s + "_outward"] = float(max(0., sign * k[0] - edge) * scale * 100)
    return result


def smooth(rows, times, i, key, seconds=.32):
    """Causal display median. Never carries across a missing current sample."""
    if not finite(rows[i].get(key)):
        return None
    start = i
    while start > 0 and times[i] - times[start - 1] <= seconds:
        if times[start] - times[start - 1] > .30 or not finite(rows[start - 1].get(key)):
            break
        start -= 1
    return med(r.get(key) for r in rows[start:i + 1])


def local_residual(rows, times, i, key):
    start = bisect.bisect_left(times, times[i] - .56)
    seq = [(times[j], rows[j].get(key)) for j in range(start, i + 1)]
    if len(seq) < 4 or any(not finite(y) for _, y in seq) or any(b[0] - a[0] > .30 for a, b in zip(seq, seq[1:])):
        return None
    x = np.array([t - times[i] for t, _ in seq]); y = np.array([y for _, y in seq])
    return float(np.sqrt(np.mean((y - np.polyval(np.polyfit(x, y, 2), x)) ** 2)))


def motion_segments(series, threshold=.03):
    """Observed, bounded moving intervals; truncated or gapped intervals stay partial."""
    result = []
    i = 0
    while i < len(series):
        v = series[i].get("velocity_m_s")
        direction = 1 if finite(v) and v > threshold else -1 if finite(v) and v < -threshold else 0
        if direction == 0:
            i += 1
            continue
        start = i
        while i + 1 < len(series):
            nxt = series[i + 1].get("velocity_m_s")
            if series[i + 1]["t"] - series[i]["t"] > .30 or not finite(nxt) or direction * nxt <= threshold:
                break
            i += 1
        end = i
        duration = series[end]["t"] - series[start]["t"]
        travel = extent(r.get("height_m") for r in series[start:end + 1])
        before = series[start - 1] if start else None
        after = series[end + 1] if end + 1 < len(series) else None
        bounded = (before is not None and after is not None
                   and finite(before.get("velocity_m_s")) and finite(after.get("velocity_m_s"))
                   and series[start]["t"] - before["t"] <= .30
                   and after["t"] - series[end]["t"] <= .30)
        if duration >= .24 and finite(travel) and travel >= .025:
            speeds = valid(r.get("velocity_m_s") for r in series[start:end + 1])
            result.append(dict(direction=direction, start=start, end=end,
                               start_s=series[start]["t"], end_s=series[end]["t"],
                               duration_s=duration, travel_m=travel,
                               mean_speed_m_s=statistics.mean(abs(v) for v in speeds),
                               bounded=bool(bounded)))
        i += 1
    return result


def phase_metrics(series, rows, times):
    segments = motion_segments(series)
    ups = [s for s in segments if s["direction"] == 1 and s["bounded"]]
    downs = [s for s in segments if s["direction"] == -1 and s["bounded"]]
    ratios = []
    for a, b in zip(segments, segments[1:]):
        if a["bounded"] and b["bounded"] and a["direction"] == -1 and b["direction"] == 1 and b["start_s"] - a["end_s"] <= 1:
            ratios.append(a["duration_s"] / b["duration_s"])
    sync = []
    for s in ups:
        crossings = []
        for side in ("left", "right"):
            vals = [rows[j].get(side + "_knee") for j in range(s["start"], s["end"] + 1)]
            if not vals or any(not finite(v) for v in vals) or max(vals) - vals[0] < 8:
                break
            target = vals[0] + .2 * (max(vals) - vals[0])
            crossings.append(next(times[s["start"] + k] for k, v in enumerate(vals) if v >= target))
        if len(crossings) == 2:
            sync.append(crossings[0] - crossings[1])
    change = None
    if len(ups) >= 2 and .7 <= ups[-1]["travel_m"] / ups[0]["travel_m"] <= 1.3:
        change = (ups[-1]["mean_speed_m_s"] / ups[0]["mean_speed_m_s"] - 1) * 100
    return dict(rise_time=med(s["duration_s"] for s in ups),
                lower_time=med(s["duration_s"] for s in downs), tempo=med(ratios),
                synchrony=med(sync), speed_change=change), segments


def metric(key, label, unit, decimals=1, primary=False, group="动作表现", method="2D_GEOMETRY"):
    return dict(key=key, label=label, unit=unit, decimals=decimals,
                primary=primary, group=group, method=method)


def feedback(text, kind="good"):
    return dict(text=text, kind=kind)


def build_clip(entry, root, destination):
    src = root / entry["folder"]
    calc = root / "v3_75kg180cm" / entry["folder"]
    original = src / "软件原始结果.json"
    poses = src / "逐帧关键点与动作阶段.json"
    geo_file = calc / "分析数据.json"
    body_file = calc / "人体模型计算.json"
    bar_file = calc / "器械跟踪与计算.json"
    source_paths = [original, poses, geo_file, body_file] + ([bar_file] if bar_file.exists() else [])
    hashes = {str(p): sha(p) for p in source_paths}
    doc = read(original); frames = read(poses)["frames"]
    geometry = read(geo_file)["series"]; bm = read(body_file); body = bm["series"]
    bar_doc = read(bar_file) if bar_file.exists() else None
    bar = bar_doc["series"] if bar_doc else None
    video = Path(doc["input"]["path"])
    assert sha(video) == entry["source_sha256"], "Source video changed"
    times = [r["t"] for r in frames]
    assert all(a < b for a, b in zip(times, times[1:])), "Non-monotonic observations"
    assert len(frames) == len(body) == len(geometry)
    assert all(abs(t - r["t"]) < 1e-6 for t, r in zip(times, body))
    if bar:
        assert len(bar) == len(frames) and all(abs(t - r["t"]) < 1e-6 for t, r in zip(times, bar))
    front = entry["view"] == "frontal"
    walking = entry["exercise"].startswith("posture")
    deadlift = entry["exercise"] == "fitness_deadlift"
    side = entry["side"]
    scale = bm["calibration"]["meter_per_pixel"]
    rows = []
    for i, f in enumerate(frames):
        p = f["points"]; row = {}
        for s in ("left", "right"):
            shoulder, hip, knee, ankle = [pixel(p, s + "_" + n) for n in ("shoulder", "hip", "knee", "ankle")]
            row[s + "_knee"] = angle(hip, knee, ankle)
            row[s + "_hip"] = angle(shoulder, hip, knee)
            tr = tilt(shoulder, hip)
            row[s + "_torso"] = abs(tr) if finite(tr) else None
        ls, rs, lh, rh = [pixel(p, n) for n in ("left_shoulder", "right_shoulder", "left_hip", "right_hip")]
        row["shoulder_line"] = line_tilt(ls, rs)
        row["pelvis_line"] = line_tilt(lh, rh)
        row["lateral"] = tilt((ls + rs) / 2, (lh + rh) / 2) if all(a is not None for a in (ls, rs, lh, rh)) else None
        row.update(knee_alignment(p, scale) if front and not walking else {})
        head = f.get("raw", {})
        row["head_offset"] = head.get("head_offset") if isinstance(head, dict) and not front else None
        row["hip_height"] = float((pixel(p, side + "_knee")[1] - pixel(p, side + "_hip")[1]) * scale * 100) if pixel(p, side + "_knee") is not None and pixel(p, side + "_hip") is not None else None
        row["body_x"] = body[i]["pelvis_center_px"][0] * scale * 100 if body[i].get("pelvis_center_px") else None
        rows.append(row)
    definitions = []
    if walking:
        if front:
            definitions += [metric("shoulder", "双肩高低差", "°", primary=True), metric("pelvis", "骨盆高低差", "°", primary=True)]
        definitions += [metric("sway", "骨盆上下起伏", "cm", primary=True),
                        metric("torso", "上身侧倾" if front else "上身前倾", "°", primary=True)]
        if not front:
            definitions.append(metric("head", "耳肩前移比例", "%", primary=True))
    elif deadlift:
        definitions += [metric("hip", "髋部投影角" if front else "髋部夹角", "°", primary=True),
                        metric("torso", "上身侧倾" if front else "上身前倾", "°", primary=True),
                        metric("bar_path", "杠铃水平偏移", "cm", primary=True, method="PLATE_IMAGE_TRACK"),
                        metric("speed", "杠铃提升速度", "m/s", 2, True, method="EXTERNAL_LOAD_MODEL"),
                        metric("power", "杠铃输出功率", "W", 0, True, method="EXTERNAL_LOAD_MODEL")]
        if front:
            definitions.append(metric("symmetry", "左右屈膝角度差", "°"))
    elif front:
        definitions += [metric("symmetry", "左右屈膝角度差", "°", primary=True),
                        metric("inward", "膝部向内偏移", "cm", primary=True),
                        metric("outward", "膝部向外偏移", "cm", primary=True),
                        metric("torso", "上身侧倾", "°", primary=True),
                        metric("power", "人体模型功率", "W", 0, True, method="PELVIS_POINT_MASS_MODEL")]
    else:
        definitions += [metric("knee", "屈膝角度", "°", primary=True),
                        metric("depth", "髋膝高度差", "cm", primary=True),
                        metric("torso", "上身前倾", "°", primary=True),
                        metric("speed", "起身速度", "m/s", 2, True, method="PELVIS_POINT_MASS_MODEL"),
                        metric("power", "人体模型功率", "W", 0, True, method="PELVIS_POINT_MASS_MODEL")]
    definitions.append(metric("sway_x", "骨盆左右幅度" if front else "骨盆前后位移", "cm", group="轨迹与控制"))
    if not walking:
        definitions += [metric("smoothness", "关节角度波动", "°", group="轨迹与控制")]
        if not front:
            definitions.append(metric("coordination", "起身前倾变化", "°", group="轨迹与控制"))
        definitions += [metric("rise_time", "提升用时", "s", 2, group="动作节奏", method="BOUNDED_VELOCITY_SEGMENTS"),
                        metric("lower_time", "下放用时", "s", 2, group="动作节奏", method="BOUNDED_VELOCITY_SEGMENTS"),
                        metric("tempo", "下放 / 提升用时", "倍", 2, group="动作节奏", method="PAIRED_BOUNDED_SEGMENTS"),
                        metric("speed_change", "前后提升速度变化", "%", 1, group="动作节奏", method="MATCHED_TRAVEL_SEGMENTS")]
        if front:
            definitions.append(metric("synchrony", "左右起身时间差", "s", 2, group="动作节奏", method="KNEE_20_PERCENT_CROSSING"))
    motion = bar if bar else body
    phase, segments = phase_metrics(motion, rows, times) if not walking else ({}, [])
    samples = []
    for i, f in enumerate(frames):
        t = times[i]; a = bisect.bisect_left(times, t - 1.2)
        s = lambda key: smooth(rows, times, i, key)
        g = {}; fb = {}; l, r = s("left_knee"), s("right_knee")
        g["symmetry"] = abs(l - r) if finite(l) and finite(r) else None
        fb["symmetry"] = feedback("左右屈膝很对称") if finite(g["symmetry"]) and g["symmetry"] < 8 else feedback("左腿屈膝偏多" if finite(l) and finite(r) and l < r else "右腿屈膝偏多", "attention")
        g["hip"] = s(side + "_hip")
        fb["hip"] = feedback("髋部角度已跟踪", "neutral")
        for direction, key, threshold in (("inward", "inward", 2.5), ("outward", "outward", 4)):
            candidates = [(s(x + "_" + key), x) for x in ("left", "right")]
            candidates = [(v, x) for v, x in candidates if finite(v)]
            value, which = max(candidates) if candidates else (None, "")
            g[direction] = value
            sufficient = i >= 3 and all(finite(gv) for gv in (l, r)) and 180 - (l + r) / 2 >= 25
            recent = [rows[j].get(which + "_" + key) for j in range(bisect.bisect_left(times, t - .32), i + 1)]
            alert = sufficient and finite(value) and value > threshold and sum(finite(v) and v > threshold for v in recent) >= 3
            fb[direction] = feedback(("左膝" if which == "left" else "右膝") + ("向内偏多" if key == "inward" else "向外偏多"), "attention") if alert else feedback("膝部对齐较好") if sufficient else feedback("屈膝片段评价对齐", "neutral")
        g["knee"] = 180 - s(side + "_knee") if finite(s(side + "_knee")) else None
        g["depth"] = s("hip_height")
        fb["depth"] = feedback("平行深蹲幅度到位") if finite(g["depth"]) and g["depth"] <= 15 * scale * 100 and finite(g["knee"]) and g["knee"] >= 50 else feedback("最低位置查看下蹲幅度", "neutral")
        residual = local_residual(rows, times, i, side + ("_hip" if deadlift else "_knee"))
        fb["hip"] = feedback("髋部收放较平顺") if not finite(residual) or residual <= 4 else feedback("髋部角度波动偏大", "attention")
        g["smoothness"] = residual
        fb["smoothness"] = feedback("关节运动较平顺") if finite(residual) and residual <= 4 else feedback("局部角度波动较明显", "attention")
        fb["knee"] = feedback("膝部角度控制较好") if not finite(residual) or residual <= 4 else feedback("屈膝角度波动偏大", "attention")
        lat = s("lateral"); g["torso"] = abs(lat) if front and finite(lat) else s(side + "_torso") if not front else None
        prior = max(0, bisect.bisect_right(times, t - .48) - 1)
        prior_torso = smooth(rows, times, prior, side + "_torso")
        change = g["torso"] - prior_torso if not front and finite(g["torso"]) and finite(prior_torso) else None
        recent_start = bisect.bisect_left(times, t - .32)
        body_speed = med(r.get("velocity_m_s") for r in body[recent_start:i + 1])
        load_speed = med(r.get("velocity_m_s") for r in motion[recent_start:i + 1])
        pelvis_rise = body[i].get("height_m") - body[prior].get("height_m") if finite(body[i].get("height_m")) and finite(body[prior].get("height_m")) else None
        rising = finite(body_speed) and body_speed > .05 and finite(pelvis_rise) and pelvis_rise > .02 and finite(load_speed) and load_speed > .03
        g["coordination"] = change if rising else None
        if front:
            fb["torso"] = feedback("躯干左右控制稳定") if finite(lat) and abs(lat) < 5 else feedback("上身向画面右侧偏多" if finite(lat) and lat > 0 else "上身向画面左侧偏多", "attention")
        else:
            warning = finite(g["coordination"]) and g["coordination"] > 6
            fb["torso"] = feedback("起身时前倾偏多", "attention") if warning else feedback("上身前倾偏多", "attention") if walking and finite(g["torso"]) and g["torso"] > 15 else feedback("上身姿态控制较好" if walking else "躯干配合较稳定")
        fb["coordination"] = feedback("起身时前倾增加", "attention") if finite(g["coordination"]) and g["coordination"] > 6 else feedback("髋与躯干配合较好")
        g["shoulder"] = s("shoulder_line"); g["pelvis"] = s("pelvis_line")
        for key, noun, limit in (("shoulder", "双肩", 4), ("pelvis", "骨盆", 5)):
            fb[key] = feedback(noun + "高度较平稳") if finite(g[key]) and g[key] < limit else feedback(noun + "左右高低差增大", "attention")
        # Range windows remain unknown if there is a gap or missing position.
        uninterrupted = i - a >= 3 and all(times[j] - times[j - 1] <= .30 for j in range(a + 1, i + 1))
        heights = [v.get("height_m") for v in body[a:i + 1]]
        xs = [v.get("body_x") for v in rows[a:i + 1]]
        g["sway"] = extent(heights) * 100 if uninterrupted and all(finite(x) for x in heights) else None
        g["sway_x"] = extent(xs) if uninterrupted and all(finite(x) for x in xs) else None
        for key, noun in (("sway", "骨盆上下"), ("sway_x", "骨盆左右" if front else "骨盆前后")):
            baseline = [body[j].get("height_m") * 100 if key == "sway" and finite(body[j].get("height_m")) else rows[j].get("body_x") if key == "sway_x" else None for j in range(len(times)) if .12 <= times[j] <= 1.32]
            base = extent(baseline)
            # Baseline is only used after it has actually been observed.
            warning = t >= 1.4 and finite(base) and finite(g[key]) and g[key] > base + 1.5
            fb[key] = feedback(noun + "位移已跟踪", "neutral") if key == "sway_x" and not front else feedback(noun + "幅度较开头增大", "attention") if warning else feedback(noun + "控制较平稳")
        g["head"] = s("head_offset")
        first_head = med(rows[j].get("head_offset") for j in range(i + 1) if times[j] <= min(1.32, t))
        fb["head"] = feedback("头部前移较开头增加", "attention") if t >= 1.4 and finite(first_head) and finite(g["head"]) and g["head"] > first_head + 5 else feedback("耳肩位置较平稳")
        g["power"] = motion[i].get("power_w")
        g["speed"] = motion[i].get("velocity_m_s")
        fit = motion[i].get("fit_residual_m" if bar else "fit_rms_m")
        fb["power"] = feedback("本段轨迹较平顺") if finite(fit) and fit <= .015 else feedback("局部轨迹波动偏大", "attention")
        direction = "提升" if finite(g["speed"]) and g["speed"] > .03 else "下放" if finite(g["speed"]) and g["speed"] < -.03 else "转换"
        fb["speed"] = feedback(direction + "过程较平顺") if finite(fit) and fit <= .015 else feedback("局部轨迹波动偏大", "attention")
        if bar:
            current = bar[i].get("point_px"); initial = bar[0].get("point_px")
            g["bar_path"] = (current[0] - initial[0]) * bar_doc["meter_per_pixel"] * 100 if current and initial else None
            fb["bar_path"] = feedback("杠铃路径较集中") if finite(g["bar_path"]) and abs(g["bar_path"]) <= 5 else feedback("杠铃向画面左侧偏移" if finite(g["bar_path"]) and g["bar_path"] < 0 else "杠铃向画面右侧偏移", "attention")
        output = {}; cues = {}
        for d in definitions:
            k = d["key"]
            if k in phase:
                continue  # Full-clip statistics never masquerade as current data.
            v = g.get(k); output[k] = v
            cues[k] = fb.get(k, feedback("数据已跟踪", "neutral")) if finite(v) else feedback("起身阶段评价配合" if k == "coordination" else "片段积累中", "neutral")
        samples.append(dict(t=t, values=output, feedback=cues, points=f["points"],
                            bar_point=bar[i].get("point_px") if bar else None,
                            bar_diameter_px=bar[i].get("diameter_px") if bar else None))
    for d in definitions:
        k = d["key"]
        if k in phase:
            value = phase[k]
            tempo_cue = "上下节奏较均匀" if finite(phase.get("tempo")) and .8 <= phase["tempo"] <= 1.2 else "下放慢于提升" if finite(phase.get("tempo")) and phase["tempo"] > 1.2 else "下放快于提升"
            cues = {"rise_time": "起身阶段用时" if not bar else "杠铃提升用时", "lower_time": "下放阶段用时", "tempo": tempo_cue,
                    "synchrony": "左右起身较同步" if finite(value) and abs(value) <= .10 else "左侧起身较早" if finite(value) and value < 0 else "右侧起身较早",
                    "speed_change": "后段提升速度下降" if finite(value) and value < -10 else "前后速度较接近" if finite(value) and abs(value) <= 10 else "后段提升速度增加"}
            d.update(value=value, statistic="全段", cue=cues[k] if finite(value) else "等待完整起落片段", kind="neutral", time=None)
            continue
        vals = [(i, s["values"].get(k)) for i, s in enumerate(samples) if finite(s["values"].get(k)) and (k not in ("inward", "outward") or s["feedback"][k]["kind"] != "neutral")]
        if not vals:
            d.update(value=None, statistic="全段", cue="片段积累中", kind="neutral", time=None)
            continue
        # Dedicated summary rule: signed forward/back path uses max absolute deviation.
        selector = min if k == "depth" else max
        idx, value = selector(vals, key=(lambda pair: abs(pair[1])) if k == "bar_path" else lambda pair: pair[1])
        d.update(value=value, statistic="最低位置" if k == "depth" else "最大偏移" if k == "bar_path" else "峰值" if k in ("power", "speed") else "最大值",
                 cue=samples[idx]["feedback"][k]["text"], kind=samples[idx]["feedback"][k]["kind"],
                 time=times[idx], min=min(v for _, v in vals), max=max(v for _, v in vals))
    if not walking:
        powers = valid(m.get("power_w") for m in motion if finite(m.get("velocity_m_s")) and m["velocity_m_s"] > .03)
        definitions.append(dict(**metric("mean_power", "提升平均功率", "W", 0, group="输出表现", method="EXTERNAL_LOAD_MODEL" if bar else "PELVIS_POINT_MASS_MODEL"), value=statistics.mean(powers) if powers else None, statistic="提升平均", cue="提升阶段整体输出", kind="neutral", time=None))
    highlights = []
    for d in definitions:
        if d.get("kind") == "attention" and d.get("time") is not None:
            highlights.append(dict(t=d["time"], text=d["cue"], key=d["key"]))
    seen = set(); highlights = [h for h in highlights if not (h["text"] in seen or seen.add(h["text"]))]
    if not highlights:
        preferred = next((d for d in definitions if d["key"] in ("symmetry", "shoulder", "torso") and finite(d.get("value"))), definitions[0])
        highlights = [dict(t=preferred.get("time") or 0, text=preferred["cue"], key=preferred["key"])]
    clip_id = entry["file"][:2]
    folder = destination / clip_id; folder.mkdir()
    shutil.copy2(video, folder / "video.mp4")
    title = "步行" if walking else "硬拉" if deadlift else "深蹲"
    view = "正面" if front else "侧面"
    clip = dict(id=clip_id, title=title, view=view, duration=305 / 30,
                crop=CROPS[clip_id], source_size=[1280, 720], source_note="AI生成样片",
                source_sha256=entry["source_sha256"], sample_interval=med(b - a for a, b in zip(times, times[1:])),
                body=dict(mass_kg=bm["body_mass_kg"], height_cm=bm["body_height_m"] * 100),
                bar_load_kg=bar_doc["load_kg"] if bar_doc else None,
                methods=dict(geometry="二维关键点几何；角度显示用最近0.32秒中位数。", symmetry="左右角度与时序对称性。", power="人体：骨盆中心75kg集中质量点；杠铃：60kg外部负重。P=m(g+a)v。", scale="身高180cm；杠铃片直径45cm。", phases="速度阈值0.03m/s，连续时段至少0.24秒、位移2.5cm；完整起落才计算节奏。", source="正面与侧面为独立生成片段，分别分析。", rules="评价用展示阈值描述变化，不是临床诊断阈值。"),
                metrics=definitions, samples=samples, highlights=highlights,
                trajectory=[dict(t=r["t"], x=(r["point_px"][0] - bar[0]["point_px"][0]) * bar_doc["meter_per_pixel"] * 100, y=r.get("height_m") * 100 if finite(r.get("height_m")) else None) for r in bar if r.get("point_px")] if bar else [],
                csv="metrics.csv", video="video.mp4")
    write(folder / "data.json", clip)
    with (folder / "metrics.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream); writer.writerow(["时间(s)"] + [d["label"] + "(" + d["unit"] + ")" for d in definitions if d["key"] not in phase and d["key"] != "mean_power"])
        keys = [d["key"] for d in definitions if d["key"] not in phase and d["key"] != "mean_power"]
        for s in samples:
            writer.writerow([s["t"]] + [s["values"].get(k) for k in keys])
    with (folder / "summary.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream); writer.writerow(["指标", "值", "单位", "统计", "评价", "定位时间(s)"])
        for d in definitions:
            writer.writerow([d["label"], d.get("value"), d["unit"], d.get("statistic"), d.get("cue"), d.get("time")])
    assert hashes == {str(p): sha(p) for p in source_paths}, "Source analysis changed"
    assert sha(folder / "video.mp4") == entry["source_sha256"]
    return dict(id=clip_id, title=title, view=view, data=clip_id + "/data.json"), dict(id=clip_id, source_hashes=hashes, source_video_sha256=entry["source_sha256"], samples=len(samples), metrics=len(definitions), segments=segments, phase_metrics=phase, source_unchanged=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    # Refuse existing destinations: earlier videos/reports are never overwritten.
    args.output.mkdir(parents=True, exist_ok=False)
    for file in UI.iterdir():
        if file.is_file():
            shutil.copy2(file, args.output / file.name)
    batch = read(args.analysis / "分析批次.json"); clips = []; audit = []
    for entry in batch["items"]:
        clip, record = build_clip(entry, args.analysis, args.output)
        clips.append(clip); audit.append(record)
    write(args.output / "manifest.json", dict(version=VERSION, clips=clips))
    write(args.output / "provenance.json", dict(version=VERSION, scope="Local review only; no changes to APK, cloud, patient records or original inference.", repeated_counts_displayed=False, crop_policy="Fixed subject-protecting ROI; source video remains byte-identical.", missing="null retained; current sample held at most0.30s; no bridging across observation gaps.", references=[dict(title="Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents", authors="Timothy Kassis; Vinayak Agarwal; Yuhuan He; Darshil Patel; Aubrey M. Brueckner", year=2026, doi="https://doi.org/10.48550/arXiv.2609.00065")], clips=audit))
    print(json.dumps(dict(output=str(args.output), clips=len(clips), metrics=[a["metrics"] for a in audit]), ensure_ascii=False))


if __name__ == "__main__":
    main()
