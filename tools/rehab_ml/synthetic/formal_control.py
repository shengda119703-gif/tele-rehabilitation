"""Frozen formal A--F conditioning, never output observations or annotations.

The old pilot-only controller remains unchanged. This entry requires an actual
human-review freeze before reading formal pose inputs or creating guide media.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import shutil

from . import control as body
from . import formal_plan as fp
from . import generation as g
from . import motion
from .pose import validate_pose
from .video import _new_json, probe_video

VERSION = 'rehab_synthetic_formal_body_control/v1'
REFERENCE_VERSION = 'rehab_synthetic_formal_reference/v1'
SEED_VERSION = 'rehab_formal_attempt_seed/v1'


def attempt_seed(slot_seed, attempt=1):
    if (type(slot_seed) is not int or not 0 <= slot_seed < 2**32
            or type(attempt) is not int or not 1 <= attempt <= 99):
        raise ValueError('bounded_frozen_slot_seed_and_attempt_required')
    if attempt == 1:
        return slot_seed
    return int(g.canonical(dict(version=SEED_VERSION, slot_seed=slot_seed, attempt=attempt))[:8], 16)


def _inside(root, path):
    value = Path(path)
    value = value.resolve() if value.is_absolute() else (root / value).resolve()
    if not value.is_relative_to(root):
        raise ValueError('formal_control_asset_must_remain_inside_dataset_root')
    return value


def _slot(loaded, group, scenario):
    selected = [s for s in loaded['plan']['slots'] if s['source_group_id'] == group and s['scenario'] == scenario]
    if len(selected) != 1:
        raise ValueError('known_frozen_formal_group_and_scenario_required')
    return selected[0]


def _reference_origin(loaded, record):
    groups = loaded['split_freeze']['formal_group_splits']
    group = record.get('source_group_id')
    attempt = record.get('reference_attempt')
    if (record.get('schema_version') != REFERENCE_VERSION or record.get('stage') != 'formal'
            or group not in groups or record.get('reference_group_id') != group
            or record.get('split') != groups[group] or record.get('freeze_sha256') != loaded['frozen_sha']
            or type(attempt) is not int or not 1 <= attempt <= 99
            or record.get('registry_entry_id') != f'{group}:reference:r{attempt:02d}'):
        raise ValueError('reference_must_belong_to_verified_formal_freeze_and_derived_split')
    lineage = fp._ids(record.get('lineage_ids'), nonempty=True)
    profile = loaded['plan']['profiles'][group]
    if not set(profile['identity_ids'] + profile['lineage_ids']).issubset(lineage):
        raise ValueError('reference_must_preserve_frozen_profile_origin')
    return group


def load_initial(pose_path, reference_record, *, root, loaded=None):
    """Bind actual frame zero, the PNG, frozen model prediction and source PTS."""
    from PIL import Image
    root = Path(root).resolve()
    verified = fp.load_frozen_plan(root)  # Fail before any pose/source reads.
    if loaded is not None and loaded['frozen_sha'] != verified['frozen_sha']:
        raise ValueError('formal_freeze_changed')
    reference_record, pose_path = _inside(root, reference_record), _inside(root, pose_path)
    record = json.loads(reference_record.read_text(encoding='utf-8'))
    group = _reference_origin(verified, record)
    image, video = _inside(root, record['image_path']), _inside(root, record['video']['path'])
    if g.digest(image) != record['image_sha256'] or g.digest(video) != record['video']['sha256']:
        raise ValueError('formal_reference_original_bytes_changed')
    actual = probe_video(video)
    if (actual['width'], actual['height'], actual['frame_count']) != (640, 384, 97):
        raise ValueError('formal_reference_native_640x384_97_frames_required')
    prediction = validate_pose(pose_path)
    prediction = validate_pose(prediction, frame_manifest=prediction['frame_manifest_path'])
    if (prediction.get('status') != 'completed' or prediction['backend'] != 'yolo17'
            or prediction['source_sha256'] != actual['video_sha256'] or prediction['source_size'] != [640, 384]):
        raise ValueError('frozen_yolo17_prediction_on_actual_formal_reference_required')
    frames = [f for f in prediction['frames'] if f['frame_index'] == 0 and f['pose_detected']]
    if len(frames) != 1:
        raise ValueError('one_detected_actual_reference_frame0_required')
    frame = frames[0]
    with Image.open(image) as original:
        rgb = original.convert('RGB')
        image_rgb = hashlib.sha256(rgb.tobytes()).hexdigest()
        if rgb.size != (640, 384):
            raise ValueError('unresized_original_reference_png_required')
    decoded = actual['frames'][0]
    if (image_rgb != decoded['decoded_rgb_sha256'] or image_rgb != frame['decoded_rgb_sha256']
            or any(frame[key] != decoded[key] for key in ('frame_index', 'pts', 'time_base', 'timestamp_s'))):
        raise ValueError('reference_png_pose_and_actual_frame0_pts_rgb_must_agree')
    source = dict(reference_record=str(reference_record), reference_record_sha256=g.digest(reference_record),
        reference_image=str(image), reference_image_sha256=g.digest(image),
        reference_video=str(video), reference_video_sha256=g.digest(video),
        source_group_id=group, reference_group_id=group, stage='formal', split=record['split'],
        freeze_sha256=verified['frozen_sha'], reference_registry_entry_id=record['registry_entry_id'],
        reference_attempt=record['reference_attempt'], source_pose_path=str(pose_path),
        source_pose_sha256=g.digest(pose_path), source_pose_backend=prediction['backend'],
        source_pose_model=prediction['model'], source_frame_index=0, source_pts=frame['pts'],
        source_time_base=frame['time_base'], source_timestamp_s=frame['timestamp_s'],
        source_decoded_rgb_sha256=image_rgb, source_track_id=frame['track_id'],
        lineage_ids=list(dict.fromkeys(record['lineage_ids'] + ['reference_image:' + g.digest(image),
            'reference_video:' + g.digest(video), 'pose_prediction:' + g.digest(pose_path)])))
    return body.initial_geometry(frame['joints']), source


def _rows(initial, geometry, schedule):
    for index in range(241):
        command = motion.command_at(schedule, index / 30)
        points = motion.frame_at(initial, geometry, command)
        if any(p is not None and not (5 <= p['x'] < 635 and 5 <= p['y'] < 379) for p in points.values()):
            raise ValueError('formal_control_joint_outside_safe_original_canvas')
        rgb = body.render_body18(points)
        yield dict(frame_index=index, controller_timestamp_s=index / 30,
            command=command, openpose18=points, rendered_rgb_sha256=hashlib.sha256(rgb.tobytes()).hexdigest()), rgb


def render_controls(pose_path, reference_record, output_dir, *, root, scenarios=tuple('ABCDEF'),
                    side='left', attempt=1, style_source=body.DEFAULT_STYLE_SOURCE):
    """Write native lossless guides, with seed exclusively from frozen slots."""
    import av
    root = Path(root).resolve()
    loaded = fp.load_frozen_plan(root)
    if side != 'left':
        raise ValueError('formal_v1_recipe_requests_anatomical_left_only')
    if not scenarios or len(set(scenarios)) != len(scenarios) or set(scenarios) - set('ABCDEF'):
        raise ValueError('unique_formal_scenarios_A_through_F_required')
    output = _inside(root, output_dir)
    if output.exists():
        raise FileExistsError('Use a new output directory; controller artifacts are immutable')
    initial, source = load_initial(pose_path, reference_record, root=root, loaded=loaded)
    geometry = body.arm_geometry(initial, side)
    style = body.verify_style_source(style_source)
    schedules = {s: motion.build_schedule(s, geometry['initial_outward_angle_deg'],
        seed=attempt_seed(_slot(loaded, source['source_group_id'], s)['seed'], attempt),
        source_group_id=source['source_group_id']) for s in scenarios}
    # Check all geometry before writing any media.
    for schedule in schedules.values():
        for _ in _rows(initial, geometry, schedule):
            pass
    output.mkdir(parents=True)
    original = output / 'initial-source.json'
    _new_json(original, dict(source=source, initial_openpose18=initial, geometry=geometry, style=style,
        controller_version=VERSION, motion_version=motion.VERSION, is_GT=False))
    receipts = []
    for scenario, schedule in schedules.items():
        folder = output / scenario
        folder.mkdir()
        video = folder / 'body18-control.mp4'
        rows = []
        with av.open(str(video), 'w') as container:
            stream = container.add_stream('libx264rgb', rate=30)
            stream.width, stream.height, stream.pix_fmt = 640, 384, 'rgb24'
            stream.options = dict(crf='0', preset='fast')
            for row, rgb in _rows(initial, geometry, schedule):
                rows.append(row)
                frame = av.VideoFrame.from_ndarray(rgb, format='rgb24')
                frame.pts, frame.time_base = row['frame_index'], Fraction(1, 30)
                for packet in stream.encode(frame):
                    container.mux(packet)
            for packet in stream.encode():
                container.mux(packet)
        timeline = folder / 'timeline.json'
        actual = probe_video(video, timeline_path=timeline)
        if ((actual['width'], actual['height'], actual['frame_count']) != (640, 384, 241)
                or [r['rendered_rgb_sha256'] for r in rows] != [f['decoded_rgb_sha256'] for f in actual['frames']]
                or any(abs(t - i / 30) > 1e-10 for i, t in enumerate(actual['presentation_s']))):
            raise ValueError('formal_guide_lossless_rgb_or_pts_roundtrip_failed')
        trajectory = folder / 'trajectory.json'
        _new_json(trajectory, dict(schema_version=VERSION, source=source, schedule=schedule, frames=rows,
            is_GT=False, controller_timestamps_are_generated_video_labels=False))
        receipt = dict(schema_version=VERSION, controller_version=VERSION, motion_version=motion.VERSION,
            source=source, scenario=scenario, attempt=attempt, seed=schedule['seed'], schedule=schedule,
            geometry=geometry, style=style, width=640, height=384, frames=241, fps=30,
            video=str(video), video_sha256=g.digest(video), actual_pts_timeline=str(timeline),
            timeline_sha256=g.digest(timeline), controller_trajectory=str(trajectory),
            controller_trajectory_sha256=g.digest(trajectory), initial_source_path=str(original),
            initial_source_sha256=g.digest(original), controller_implementation_sha256=g.digest(Path(__file__)),
            motion_implementation_sha256=g.digest(Path(motion.__file__)), is_GT=False,
            training_reference_eligible=False, controller_timestamps_are_generated_video_labels=False,
            commands_are_output_labels=False, creates_human_annotations=False, product_enabled=False,
            generated_person_video_motion_verified=False, source_reference_image_edited=False,
            lossless_rgb_roundtrip_verified=True, video_codec='libx264rgb_crf0_rgb24')
        receipt['lineage_ids'] = body.control_lineage(source, receipt['controller_trajectory_sha256'], receipt['video_sha256'])
        target = folder / 'receipt.json'
        _new_json(target, receipt)
        receipts.append(str(target))
    # Reverify original inputs and freeze after the complete CPU operation.
    _, after = load_initial(pose_path, reference_record, root=root, loaded=loaded)
    if source != after:
        raise ValueError('formal_reference_changed_during_controller_render')
    return receipts


def load_control(path, *, root, expected_source_group_id=None, expected_scenario=None,
                 expected_reference_image_sha256=None):
    root = Path(root).resolve()
    loaded = fp.load_frozen_plan(root)
    path = _inside(root, path)
    receipt = json.loads(path.read_text(encoding='utf-8'))
    if (receipt.get('schema_version') != VERSION or receipt.get('controller_version') != VERSION
            or receipt.get('motion_version') != motion.VERSION
            or (receipt.get('width'), receipt.get('height'), receipt.get('frames'), receipt.get('fps')) != (640, 384, 241, 30)
            or any(receipt.get(k) is not False for k in ('is_GT', 'training_reference_eligible',
                'controller_timestamps_are_generated_video_labels', 'commands_are_output_labels',
                'creates_human_annotations', 'product_enabled', 'source_reference_image_edited'))):
        raise ValueError('explicit_non_GT_formal_native_control_receipt_required')
    source = receipt['source']
    initial, actual_source = load_initial(source['source_pose_path'], source['reference_record'], root=root, loaded=loaded)
    if source != actual_source:
        raise ValueError('formal_control_source_changed')
    for value, expected in ((source['source_group_id'], expected_source_group_id),
            (receipt['scenario'], expected_scenario), (source['reference_image_sha256'], expected_reference_image_sha256)):
        if expected is not None and value != expected:
            raise ValueError('formal_control_group_scenario_or_reference_mismatch')
    slot = _slot(loaded, source['source_group_id'], receipt['scenario'])
    geometry = body.arm_geometry(initial, 'left')
    seed = attempt_seed(slot['seed'], receipt['attempt'])
    schedule = motion.build_schedule(receipt['scenario'], geometry['initial_outward_angle_deg'],
        seed=seed, source_group_id=source['source_group_id'])
    if receipt['geometry'] != geometry or receipt['seed'] != seed or receipt['schedule'] != schedule:
        raise ValueError('formal_control_geometry_seed_or_schedule_changed')
    if g.canonical(body.verify_style_source(receipt['style']['path'])) != g.canonical(receipt['style']):
        raise ValueError('formal_control_pinned_style_changed')
    for field, sha in (('video', 'video_sha256'), ('actual_pts_timeline', 'timeline_sha256'),
            ('controller_trajectory', 'controller_trajectory_sha256'), ('initial_source_path', 'initial_source_sha256')):
        if g.digest(_inside(root, receipt[field])) != receipt[sha]:
            raise ValueError('formal_control_artifact_bytes_changed')
    for module, key in ((Path(__file__), 'controller_implementation_sha256'),
                        (Path(motion.__file__), 'motion_implementation_sha256')):
        if g.digest(module) != receipt[key]:
            raise ValueError('formal_controller_implementation_changed')
    original = json.loads(Path(receipt['initial_source_path']).read_text(encoding='utf-8'))
    if (original.get('source') != source or original.get('initial_openpose18') != initial
            or original.get('geometry') != geometry or original.get('is_GT') is not False):
        raise ValueError('formal_initial_source_payload_changed')
    actual = probe_video(receipt['video'])
    if (actual['width'], actual['height'], actual['frame_count']) != (640, 384, 241):
        raise ValueError('formal_control_actual_native_geometry_required')
    saved = json.loads(Path(receipt['actual_pts_timeline']).read_text(encoding='utf-8'))
    if (not g.same_media_timeline(saved, actual) or actual['frame_count'] != 241
            or any(abs(t - i / 30) > 1e-10 for i, t in enumerate(actual['presentation_s']))):
        raise ValueError('formal_control_actual_pts_or_pixels_changed')
    trajectory = json.loads(Path(receipt['controller_trajectory']).read_text(encoding='utf-8'))
    expected_rows = [row for row, _ in _rows(initial, geometry, schedule)]
    if (trajectory != dict(schema_version=VERSION, source=source, schedule=schedule, frames=expected_rows,
            is_GT=False, controller_timestamps_are_generated_video_labels=False)
            or [r['rendered_rgb_sha256'] for r in expected_rows] != [f['decoded_rgb_sha256'] for f in actual['frames']]
            or receipt['lineage_ids'] != body.control_lineage(source, receipt['controller_trajectory_sha256'], receipt['video_sha256'])):
        raise ValueError('formal_trajectory_commands_source_or_rendered_rgb_changed')
    return receipt


def prepare_control(root, loaded_freeze, group, scenario, reference_record, *, control_path, lab, attempt=1):
    """Verify/copy an explicit CPU-rendered guide; caller verifies the LoRA."""
    root, lab = Path(root).resolve(), Path(lab).resolve()
    loaded = fp.load_frozen_plan(root)
    if loaded['frozen_sha'] != loaded_freeze['frozen_sha']:
        raise ValueError('formal_freeze_changed')
    _reference_origin(loaded, reference_record)
    control_path = _inside(root, control_path)
    receipt = load_control(control_path, root=root, expected_source_group_id=group,
        expected_scenario=scenario, expected_reference_image_sha256=reference_record['image_sha256'])
    if (receipt['attempt'] != attempt
            or json.loads(Path(receipt['source']['reference_record']).read_text(encoding='utf-8')) != reference_record):
        raise ValueError('formal_control_attempt_or_reference_record_changed')
    source = receipt['source']
    filename = 'rehab_formal_control_' + receipt['video_sha256'][:20] + '.mp4'
    target = lab / 'ComfyUI/input' / filename
    if not target.exists():
        shutil.copy2(receipt['video'], target)
    if g.digest(target) != receipt['video_sha256']:
        raise ValueError('formal_control_comfy_copy_changed')
    metadata = dict(receipt_path=str(Path(control_path).resolve()), receipt_sha256=g.digest(Path(control_path)),
        controller_version=VERSION, controller_seed=receipt['seed'], source_group_id=group,
        reference_image_sha256=source['reference_image_sha256'], reference_video_sha256=source['reference_video_sha256'],
        control_video_path=receipt['video'], control_video_sha256=receipt['video_sha256'],
        trajectory_sha256=receipt['controller_trajectory_sha256'], pose_source_sha256=source['source_pose_sha256'],
        controller_is_ground_truth_for_output=False, creates_human_annotations=False)
    pose_id = f"{group}:pose:r{source['reference_attempt']:02d}:" + source['source_pose_sha256'][:12]
    control_id = f'{group}:control:{scenario}:r{attempt:02d}:' + receipt['video_sha256'][:12]
    make = lambda **kw: fp.source_registry_entry(loaded['plan'], source_group_id=group, **kw)
    entries = [make(entry_id=pose_id, kind='pose', lineage_ids=source['lineage_ids'],
        assets=dict(pose_prediction=source['source_pose_sha256']), parents=[source['reference_registry_entry_id']]),
        make(entry_id=control_id, kind='control', lineage_ids=receipt['lineage_ids'],
            assets=dict(control_trajectory=receipt['controller_trajectory_sha256'], control_video=receipt['video_sha256']),
            parents=[pose_id])]
    metadata['registry_entry_id'] = control_id
    return receipt, filename, metadata, entries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'pose', 'reference-record', 'output-dir'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--scenarios', nargs='+', choices=tuple('ABCDEF'), default=list('ABCDEF'))
    parser.add_argument('--attempt', type=int, default=1)
    parser.add_argument('--style-source', type=Path, default=body.DEFAULT_STYLE_SOURCE)
    args = parser.parse_args()
    print(json.dumps(render_controls(args.pose, args.reference_record, args.output_dir, root=args.root,
        scenarios=args.scenarios, attempt=args.attempt, style_source=args.style_source)))


if __name__ == '__main__':
    main()
