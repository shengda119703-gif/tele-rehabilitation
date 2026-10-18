"""Pure body-guide commands, never observations or labels of an output video.

A/D/E retain the existing body-controller v1 timing and shoulder trajectories.
B, C and F are separate command recipes. They do not establish that a generated
person follows a command, completes an action, or has a clinical quality issue.
No media, pose model, rendering, registry or human annotation is produced here.
"""
from __future__ import annotations

import copy
import math
import random

from tools.rehab_ml.common import canonical_hash
from . import control

VERSION = 'rehab_synthetic_motion/v1'
SCENARIOS = tuple('ABCDEF')
COMMAND_FIELDS = {'shoulder_angle_deg', 'elbow_bend_deg'}
NON_GT_FLAGS = ('is_GT', 'training_reference_eligible',
    'controller_timestamps_are_generated_video_labels', 'commands_are_output_labels',
    'creates_human_annotations')


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _parameters(scenario, initial_angle, seed, source_group_id, frames):
    if not isinstance(scenario, str) or scenario not in SCENARIOS:
        raise ValueError('motion_scenario_A_through_F_required')
    if not _number(initial_angle) or not -20 <= initial_angle <= 45:
        raise ValueError('finite_relaxed_down_initial_shoulder_angle_required')
    if (type(seed) is not int or not 0 <= seed < 2**32
            or not isinstance(source_group_id, str) or not source_group_id.strip()):
        raise ValueError('bounded_motion_seed_and_explicit_source_group_required')
    if type(frames) is not int or not 241 <= frames <= 1000 or (frames-1) % 8:
        raise ValueError('native_8n_plus_1_frames_at_least_241_and_at_most_1000_required')


def _command(shoulder, elbow=0.):
    return dict(shoulder_angle_deg=shoulder, elbow_bend_deg=elbow)


def _check_command(command):
    if (not isinstance(command, dict) or set(command) != COMMAND_FIELDS
            or not _number(command['shoulder_angle_deg'])
            or not -20 <= command['shoulder_angle_deg'] <= 90
            or not _number(command['elbow_bend_deg'])
            or not 0 <= command['elbow_bend_deg'] <= 70):
        raise ValueError('finite_bounded_shoulder_and_elbow_command_required')


def build_schedule(scenario, initial_angle, *, seed, source_group_id, frames=241):
    """Build a deterministic 30 Hz command recipe whose motion fits in 8 s.

    Longer native clips add a static tail; they never stretch the v1 trajectory.
    Command seconds and the declared 1/30 time base are not decoded media PTS.
    F's elbow command is an additional rigid forearm rotation from the source
    prediction, not an anatomical elbow-angle measurement or a quality label.
    """
    _parameters(scenario, initial_angle, seed, source_group_id, frames)
    derived = int(canonical_hash(dict(version=VERSION, seed=seed,
        source_group_id=source_group_id, scenario=scenario))[:16], 16)
    rng = random.Random(derived)
    legacy = None
    if scenario in ('A', 'D', 'E'):
        legacy = control.controller_schedule(scenario, initial_angle,
            seed=seed, source_group_id=source_group_id)
        times = list(legacy['keyframe_controller_times_s'])
        commands = [_command(angle) for angle in legacy['keyframe_angles_deg']]
    else:
        # B has the same shoulder amplitude as A for the same group and seed;
        # both movement durations are strictly longer, including peak speed.
        base = control.controller_schedule('A', initial_angle,
            seed=seed, source_group_id=source_group_id)
        source_times = base['keyframe_controller_times_s']
        target = max(base['keyframe_angles_deg'])
        if scenario == 'B':
            preparation = rng.uniform(.65, .95)
            outbound = source_times[2]-source_times[1]+rng.uniform(.30, .45)
            hold = rng.uniform(.55, .80)
            returning = source_times[4]-source_times[3]+rng.uniform(.30, .45)
            times = [0., preparation, preparation+outbound,
                preparation+outbound+hold, preparation+outbound+hold+returning, 8.]
            commands = [_command(angle) for angle in
                (initial_angle, initial_angle, target, target, initial_angle, initial_angle)]
        elif scenario == 'C':
            preparation, outbound = rng.uniform(.65, .95), rng.uniform(1.55, 1.95)
            hold, returning = rng.uniform(1.80, 2.20), rng.uniform(1.55, 1.95)
            times = [0., preparation, preparation+outbound,
                preparation+outbound+hold, preparation+outbound+hold+returning, 8.]
            commands = [_command(angle) for angle in
                (initial_angle, initial_angle, target, target, initial_angle, initial_angle)]
        else:  # F: same upper-arm trajectory as A, only added forearm bend.
            times = list(source_times)
            bend = rng.uniform(45., 70.)
            commands = [_command(angle, flexion) for angle, flexion in
                zip(base['keyframe_angles_deg'], (0., 0., bend, bend, 0., 0.))]
    duration = (frames-1)/30
    if duration > 8.:
        times.append(duration)
        commands.append(copy.deepcopy(commands[-1]))
    result = dict(schema_version=VERSION, recipe_version=VERSION,
        scenario=scenario, seed=seed, source_group_id=source_group_id,
        derived_schedule_seed=legacy['derived_schedule_seed'] if legacy else derived,
        initial_shoulder_angle_deg=initial_angle,
        frames=frames, fps=30, time_base=[1, 30],
        time_basis='controller_command_time_not_media_PTS',
        motion_end_s=8., duration_s=duration,
        keyframe_controller_times_s=times, keyframe_commands=commands,
        interpolation='quintic_smoothstep_command_only',
        timing_and_angle_variation='seeded_by_source_group_and_scenario_not_shared_absolute_boundaries',
        shoulder_angle_kind='controller_upper_arm_vs_image_down_axis_not_clinical_ROM',
        elbow_bend_kind='additional_forearm_rotation_toward_head_not_clinical_elbow_angle',
        requested_motion=dict(A='raise_hold_return', B='slower_raise_hold_return',
            C='raise_two_second_hold_return', D='raise_and_remain_partial',
            E='remain_still', F='raise_bend_forearm_return')[scenario],
        **dict.fromkeys(NON_GT_FLAGS, False))
    if legacy:
        result['legacy_recipe_version'] = control.VERSION
    _validate_schedule(result)
    return result


def _validate_schedule(schedule):
    if not isinstance(schedule, dict):
        raise ValueError('motion_schedule_object_required')
    _parameters(schedule.get('scenario'), schedule.get('initial_shoulder_angle_deg'),
        schedule.get('seed'), schedule.get('source_group_id'), schedule.get('frames'))
    duration = (schedule['frames']-1)/30
    if (schedule.get('schema_version') != VERSION or schedule.get('recipe_version') != VERSION
            or schedule.get('fps') != 30 or schedule.get('time_base') != [1, 30]
            or schedule.get('time_basis') != 'controller_command_time_not_media_PTS'
            or schedule.get('motion_end_s') != 8.
            or not _number(schedule.get('duration_s')) or schedule['duration_s'] != duration
            or type(schedule.get('derived_schedule_seed')) is not int
            or not 0 <= schedule['derived_schedule_seed'] < 2**64
            or schedule.get('interpolation') != 'quintic_smoothstep_command_only'
            or any(schedule.get(flag) is not False for flag in NON_GT_FLAGS)):
        raise ValueError('explicit_non_GT_native_motion_command_schedule_required')
    times, commands = schedule.get('keyframe_controller_times_s'), schedule.get('keyframe_commands')
    if (not isinstance(times, list) or not isinstance(commands, list)
            or len(times) < 2 or len(times) != len(commands)
            or any(not _number(t) or not 0 <= t <= duration for t in times)
            or times[0] != 0. or times[-1] != duration
            or any(b <= a for a, b in zip(times, times[1:])) or 8. not in times):
        raise ValueError('finite_strictly_increasing_complete_command_times_required')
    for command in commands:
        _check_command(command)
    at_eight = commands[times.index(8.)]
    if any(command != at_eight for time, command in zip(times, commands) if time > 8.):
        raise ValueError('post_eight_second_tail_must_preserve_final_pose')
    initial = _command(schedule['initial_shoulder_angle_deg'])
    if commands[0] != initial:
        raise ValueError('motion_must_start_at_original_pose')
    if schedule['scenario'] != 'D' and at_eight != initial:
        raise ValueError('complete_or_still_motion_must_return_to_original_pose')
    if schedule['scenario'] == 'E' and any(command != initial for command in commands):
        raise ValueError('still_command_must_not_move_any_arm_segment')
    if schedule['scenario'] != 'F' and any(command['elbow_bend_deg'] != 0. for command in commands):
        raise ValueError('forearm_bending_is_only_supported_by_F_recipe')
    return times, commands


def command_at(schedule, t):
    """Interpolate only commands; no future video or pose data is consulted."""
    times, commands = _validate_schedule(schedule)
    if not _number(t) or not times[0] <= t <= times[-1]+1e-10:
        raise ValueError('finite_command_time_inside_schedule_required')
    for index, end in enumerate(times[1:]):
        if t <= end:
            start = times[index]
            u = (t-start)/(end-start)
            smooth = u*u*u*(10+u*(-15+6*u))
            return {field: commands[index][field]+(commands[index+1][field]-commands[index][field])*smooth
                for field in ('shoulder_angle_deg', 'elbow_bend_deg')}
    return copy.deepcopy(commands[-1])


def frame_at(initial, geometry, command):
    """Return OpenPose18 with only the selected arm rigidly articulated.

    The upper arm uses the existing controller. Positive elbow bend rotates the
    forearm toward image-up at the raised position, for either anatomical side
    and either image ordering of the shoulders. Segment lengths never change.
    """
    _check_command(command)
    if not isinstance(initial, dict) or set(initial) != set(control.OPENPOSE18):
        raise ValueError('named_OpenPose18_initial_geometry_required')
    for point in initial.values():
        if point is not None and (not isinstance(point, dict)
                or not _number(point.get('x')) or not _number(point.get('y'))
                or ('draw_score' in point and (not _number(point['draw_score'])
                    or not 0 <= point['draw_score'] <= 1))):
            raise ValueError('finite_original_pixel_geometry_required')
    if not isinstance(geometry, dict) or geometry.get('side') not in ('left', 'right'):
        raise ValueError('explicit_single_arm_geometry_required')
    side = geometry['side']
    if any(initial.get(name) is None for name in
            (side+'_shoulder', side+'_elbow', side+'_wrist',
             ('right' if side == 'left' else 'left')+'_shoulder')):
        raise ValueError('observable_selected_arm_and_both_shoulders_required')
    actual = control.arm_geometry(initial, side)
    if (type(geometry.get('outward_image_direction')) is not int
            or geometry['outward_image_direction'] != actual['outward_image_direction']
            or any(not _number(geometry.get(key))
                or not math.isclose(geometry[key], actual[key], rel_tol=0., abs_tol=1e-8)
                for key in ('upper_arm_px', 'forearm_px', 'initial_outward_angle_deg'))):
        raise ValueError('arm_geometry_must_match_unmodified_source_pixels')
    result = control.control_frame(initial, geometry, command['shoulder_angle_deg'])
    bend = command['elbow_bend_deg']
    if bend == 0.:
        return result
    elbow, wrist = result[side+'_elbow'], result[side+'_wrist']
    dx, dy = wrist['x']-elbow['x'], wrist['y']-elbow['y']
    angle = math.radians(bend)
    c, s = math.cos(angle), math.sin(angle)*actual['outward_image_direction']
    wrist.update(x=elbow['x']+c*dx+s*dy, y=elbow['y']-s*dx+c*dy,
        origin='programmatic_rigid_forearm_bend_control')
    return result
