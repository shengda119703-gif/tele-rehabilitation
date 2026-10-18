"""Render body-only pose conditioning, never human references or video labels.

Initial geometry is bound to a frozen pose prediction on the actual reference.
Controller times/angles command a guide; they say nothing about the resulting
diffusion video's movement, anatomical correctness or observed completion.
"""
# Body rendering palette/topology and rasterization adapted from Fannovel16's
# comfyui_controlnet_aux dwpose/util.py, commit a587a4c1594524c1d2de5cd1a86cd868ff448e1c.
# Apache-2.0; copy and attribution: docs/dependencies/THIRD_PARTY_NOTICES.md.
# Changes: named original-pixel joints, rigid command geometry, source/PTS/RGB
# verification, fixed CPU RGB rendering; no upstream pose detector is imported.
from __future__ import annotations

import argparse
import ast
import copy
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import random
import re

import numpy as np

from tools.rehab_ml.common import canonical_hash, file_hash
from .pose import validate_pose
from .video import _new_json, probe_video

VERSION = 'rehab_synthetic_body_control/v1'
STYLE_COMMIT = 'a587a4c1594524c1d2de5cd1a86cd868ff448e1c'
STYLE_URL = 'https://github.com/Fannovel16/comfyui_controlnet_aux/blob/'+STYLE_COMMIT+'/src/custom_controlnet_aux/dwpose/util.py'
STYLE_SHA256 = 'e6050a00f0cd2173e37f1da41a7f9ad3ea5cd57d73388bcd0e91cf0e393d5d3c'
DEFAULT_STYLE_SOURCE = Path('E:/ai-video-lab/sources/dwpose_util_a587a4c15945.py')
OPENPOSE18 = ('nose','neck','right_shoulder','right_elbow','right_wrist',
    'left_shoulder','left_elbow','left_wrist','right_hip','right_knee','right_ankle',
    'left_hip','left_knee','left_ankle','right_eye','left_eye','right_ear','left_ear')
# Functional topology/color tables verified against the pinned DWpose source.
EDGES = ((2,3),(2,6),(3,4),(4,5),(6,7),(7,8),(2,9),(9,10),(10,11),
         (2,12),(12,13),(13,14),(2,1),(1,15),(15,17),(1,16),(16,18))
COLORS = ((255,0,0),(255,85,0),(255,170,0),(255,255,0),(170,255,0),(85,255,0),
          (0,255,0),(0,255,85),(0,255,170),(0,255,255),(0,170,255),(0,85,255),
          (0,0,255),(85,0,255),(170,0,255),(255,0,255),(255,0,170),(255,0,85))


def verify_style_source(path=DEFAULT_STYLE_SOURCE):
    """Verify pinned source bytes and literal body tables without importing it."""
    path = Path(path).resolve()
    if not path.is_file() or file_hash(path) != STYLE_SHA256:
        raise ValueError('pinned_official_dwpose_render_source_required')
    tree = ast.parse(path.read_text(encoding='utf-8'))
    function = next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='draw_bodypose')
    tables = {}
    for node in function.body:
        if isinstance(node,ast.Assign):
            for target in node.targets:
                if isinstance(target,ast.Name) and target.id in ('limbSeq','colors'):
                    tables[target.id] = ast.literal_eval(node.value)
    if (tuple(map(tuple,tables.get('limbSeq',()))) != EDGES
            or tuple(map(tuple,tables.get('colors',()))) != COLORS):
        raise ValueError('dwpose_body_topology_or_rgb_colors_disagree_with_pinned_source')
    return dict(source_url=STYLE_URL,commit=STYLE_COMMIT,path=str(path),sha256=STYLE_SHA256,
                order=list(OPENPOSE18),edges_1_based=EDGES,colors_rgb=COLORS,
                black_rgb_background=True,limb_half_width_px=4,limb_color_scale=.6,
                joint_radius_px=4,xinsr_stick_scaling=False,body_only=True,
                face_and_hand_detail_not_available=True,
                body_only_vs_official_all_enabled_example='conditioning_distribution_difference_requires_generation_test')


def initial_geometry(joints, *, confidence_min=.5):
    """Keep predicted source pixels; only neck is a declared shoulder midpoint."""
    points = {}
    for name in OPENPOSE18:
        if name == 'neck':
            continue
        point = joints.get(name,{})
        values = [point.get('x'),point.get('y'),point.get('confidence')]
        valid = all(type(v) in (int,float) and math.isfinite(v) for v in values)
        points[name] = dict(x=float(values[0]),y=float(values[1]),draw_score=float(values[2]),
                            origin='frozen_pose_prediction') if valid and values[2]>=confidence_min else None
    for name in ('nose','left_shoulder','right_shoulder','left_elbow','right_elbow',
                 'left_wrist','right_wrist','left_hip','right_hip','left_knee','right_knee','left_ankle','right_ankle'):
        if points[name] is None:
            raise ValueError('observable_initial_body_joint_required:'+name)
    left,right = points['left_shoulder'],points['right_shoulder']
    points['neck'] = dict(x=(left['x']+right['x'])/2,y=(left['y']+right['y'])/2,
                          draw_score=min(left['draw_score'],right['draw_score']),
                          origin='controller_derived_shoulder_midpoint')
    return {name:points[name] for name in OPENPOSE18}


def _xy(point):
    return np.array([point['x'],point['y']],dtype=np.float64)


def arm_geometry(initial, side='left'):
    if side not in ('left','right'):
        raise ValueError('explicit_single_controller_side_required')
    shoulder,elbow,wrist = (_xy(initial[side+'_'+part]) for part in ('shoulder','elbow','wrist'))
    other = _xy(initial[('right' if side=='left' else 'left')+'_shoulder'])
    direction = 1 if shoulder[0]>other[0] else -1
    upper,fore = elbow-shoulder,wrist-elbow
    lengths = float(np.linalg.norm(upper)),float(np.linalg.norm(fore))
    if min(lengths)<5 or abs(shoulder[0]-other[0])<10:
        raise ValueError('stable_frontal_arm_lengths_and_shoulder_separation_required')
    angle = math.degrees(math.atan2(direction*upper[0],upper[1]))
    if not -20 <= angle <= 45 or upper[1]<=0:
        raise ValueError('initial_relaxed_down_arm_projection_required')
    return dict(side=side,outward_image_direction=direction,upper_arm_px=lengths[0],forearm_px=lengths[1],
                initial_outward_angle_deg=angle,
                elbow_angle_preserved_from_prediction=True,
                angle_kind='controller_upper_arm_vs_image_down_axis_not_clinical_ROM')


def controller_schedule(scenario, initial_angle, *, seed=20261019, source_group_id='unspecified'):
    if scenario not in ('A','D','E'):
        raise ValueError('controller_scenario_A_D_or_E_required')
    if type(seed) is not int or not 0<=seed<2**32 or not isinstance(source_group_id,str) or not source_group_id:
        raise ValueError('bounded_controller_seed_and_source_group_required')
    derived = int(canonical_hash(dict(version=VERSION,seed=seed,source_group_id=source_group_id,scenario=scenario))[:16],16)
    rng = random.Random(derived)
    preparation,outbound,hold,return_duration = rng.uniform(.8,1.25),rng.uniform(1.7,2.35),rng.uniform(.55,1.2),rng.uniform(1.7,2.35)
    target = rng.uniform(70.,85.) if scenario=='A' else max(initial_angle+8,rng.uniform(35.,50.)) if scenario=='D' else initial_angle
    if scenario!='E' and target<=initial_angle+5:
        raise ValueError('controller_target_must_exceed_initial_projected_angle')
    end_outbound = preparation+outbound
    times = ([0.,preparation,end_outbound,end_outbound+hold,end_outbound+hold+return_duration,8.]
             if scenario=='A' else [0.,preparation,end_outbound,8.] if scenario=='D' else [0.,8.])
    angles = ([initial_angle,initial_angle,target,target,initial_angle,initial_angle] if scenario=='A'
              else [initial_angle,initial_angle,target,target] if scenario=='D'
              else [initial_angle]*2)
    return dict(scenario=scenario,seed=seed,derived_schedule_seed=derived,source_group_id=source_group_id,
                keyframe_controller_times_s=times,keyframe_angles_deg=angles,
                timing_and_angle_variation='seeded_by_source_group_and_scenario_not_shared_absolute_boundaries',
                interpolation='quintic_smoothstep_command_only',
                controller_timestamps_are_generated_video_labels=False,
                requested_motion={'A':'raise_hold_return','D':'raise_and_remain_partial','E':'remain_still'}[scenario])


def commanded_angle(schedule, timestamp):
    times,angles = schedule['keyframe_controller_times_s'],schedule['keyframe_angles_deg']
    if not math.isfinite(timestamp) or timestamp<times[0] or timestamp>times[-1]+1e-10:
        raise ValueError('controller_time_outside_fixed_schedule')
    for index,end in enumerate(times[1:]):
        if timestamp<=end:
            start = times[index]
            u = (timestamp-start)/(end-start)
            smooth = u*u*u*(10+u*(-15+6*u))
            return angles[index]+(angles[index+1]-angles[index])*smooth
    return angles[-1]


def control_frame(initial, geometry, angle):
    """Rotate the rigid two-segment chain; all other source points stay fixed."""
    result = copy.deepcopy(initial)
    delta = angle-geometry['initial_outward_angle_deg']
    if abs(delta)<1e-12:
        return result
    side = geometry['side']
    shoulder = _xy(initial[side+'_shoulder'])
    theta = math.radians(delta)
    c,s = math.cos(theta),math.sin(theta)*geometry['outward_image_direction']
    rotation = np.array([[c,s],[-s,c]],dtype=np.float64)
    for part in ('elbow','wrist'):
        name = side+'_'+part
        position = shoulder+rotation@(_xy(initial[name])-shoulder)
        result[name].update(x=float(position[0]),y=float(position[1]),origin='programmatic_rigid_arm_control')
    return result


def render_body18(points, *, width=640,height=384):
    """DWpose RGB palette/topology on black; no reference image alteration."""
    import cv2
    canvas = np.zeros((height,width,3),dtype=np.uint8)
    for (one,two),color in zip(EDGES,COLORS):
        a,b = points[OPENPOSE18[one-1]],points[OPENPOSE18[two-1]]
        if a is None or b is None:
            continue
        x1,y1,x2,y2 = a['x'],a['y'],b['x'],b['y']
        polygon = cv2.ellipse2Poly((int((x1+x2)/2),int((y1+y2)/2)),
            (int(math.hypot(x1-x2,y1-y2)/2),4),
            int(math.degrees(math.atan2(y1-y2,x1-x2))),0,360,1)
        cv2.fillConvexPoly(canvas,polygon,[int(value*.6) for value in color])
    for name,color in zip(OPENPOSE18,COLORS):
        point = points[name]
        if point is not None:
            cv2.circle(canvas,(int(point['x']),int(point['y'])),4,color,thickness=-1)
    return canvas


def _require_pilot_train_source(source):
    if not isinstance(source,dict) or source.get('stage')!='pilot' or source.get('split')!='train':
        raise ValueError('controller_requires_explicit_pilot_train_source')


def load_initial(pose_path, reference_record, *, frame_index=0):
    """Require actual reference prediction and hash-bound original PNG/video."""
    from PIL import Image
    reference_record,pose_path = Path(reference_record).resolve(),Path(pose_path).resolve()
    reference = json.loads(reference_record.read_text(encoding='utf-8'))
    _require_pilot_train_source(reference)
    prediction = validate_pose(pose_path)
    if prediction.get('status')!='completed' or prediction.get('source_sha256')!=reference['video']['sha256']:
        raise ValueError('actual_reference_pose_required_not_motion_clip_prediction')
    manifest = prediction['frame_manifest_path']
    prediction = validate_pose(prediction,frame_manifest=manifest)
    if prediction['source_size']!=[640,384]:
        raise ValueError('controller_requires_native_640x384_reference_no_implicit_resize')
    image,source = Path(reference['image_path']),Path(reference['video']['path'])
    if file_hash(image)!=reference['image_sha256'] or file_hash(source)!=reference['video']['sha256']:
        raise ValueError('reference_image_or_video_sha256_changed')
    frames = [frame for frame in prediction['frames'] if frame['frame_index']==frame_index]
    if len(frames)!=1 or not frames[0]['pose_detected']:
        raise ValueError('explicit_detected_reference_frame_required')
    frame = frames[0]
    if frame_index!=0 or hashlib.sha256(Image.open(image).convert('RGB').tobytes()).hexdigest()!=frame['decoded_rgb_sha256']:
        raise ValueError('initial_reference_png_must_equal_selected_actual_frame0_rgb')
    return initial_geometry(frame['joints']),dict(reference_record=str(reference_record),
        reference_record_sha256=file_hash(reference_record),reference_image=str(image),
        reference_image_sha256=file_hash(image),reference_video=str(source),reference_video_sha256=file_hash(source),
        source_group_id=reference['source_group_id'],reference_group_id=reference['reference_group_id'],
        lineage_ids=list(reference['lineage_ids'])+['reference_image:'+file_hash(image),
            'reference_video:'+file_hash(source),'pose_prediction:'+file_hash(pose_path)],
        source_pose_path=str(pose_path),source_pose_sha256=file_hash(pose_path),
        source_pose_backend=prediction['backend'],source_pose_model=prediction['model'],
        source_frame_index=frame_index,source_pts=frame['pts'],source_time_base=frame['time_base'],
        source_timestamp_s=frame['timestamp_s'],source_decoded_rgb_sha256=frame['decoded_rgb_sha256'],
        source_track_id=frame['track_id'],split=reference['split'],stage=reference['stage'])


def control_lineage(source, trajectory_sha256, video_sha256):
    # A shared algorithm/version is metadata, never a shared motion source.
    return list(dict.fromkeys(source['lineage_ids']+['controller_trajectory:'+trajectory_sha256,
                                                   'controller_video:'+video_sha256]))


def load_control(path, *, verify=True, expected_source_group_id=None, expected_scenario=None,
                 expected_reference_image_sha256=None):
    """Load a conditioning receipt; full verification never loads pose models."""
    path = Path(path).resolve()
    receipt = json.loads(path.read_text(encoding='utf-8'))
    if (receipt.get('schema_version')!=VERSION or receipt.get('controller_version')!=VERSION
            or receipt.get('scenario') not in ('A','D','E') or receipt.get('is_GT') is not False
            or receipt.get('training_reference_eligible') is not False
            or receipt.get('controller_timestamps_are_generated_video_labels') is not False
            or (receipt.get('width'),receipt.get('height'),receipt.get('frames'),receipt.get('fps'))!=(640,384,241,30)
            or type(receipt.get('seed')) is not int or not 0<=receipt['seed']<2**32):
        raise ValueError('explicit_non_GT_native_control_receipt_required')
    source = receipt.get('source')
    _require_pilot_train_source(source)
    for actual,expected in ((source.get('source_group_id'),expected_source_group_id),
                            (receipt['scenario'],expected_scenario),
                            (source.get('reference_image_sha256'),expected_reference_image_sha256)):
        if expected is not None and actual!=expected:
            raise ValueError('control_group_scenario_or_reference_image_mismatch')
    if verify:
        for ref,sha in ((receipt['video'],receipt['video_sha256']),
                        (receipt['actual_pts_timeline'],receipt['timeline_sha256']),
                        (receipt['controller_trajectory'],receipt['controller_trajectory_sha256']),
                        (receipt['initial_source_path'],receipt['initial_source_sha256'])):
            if file_hash(ref)!=sha:
                raise ValueError('control_media_trajectory_or_initial_source_hash_changed')
        initial,actual_source = load_initial(source['source_pose_path'],source['reference_record'])
        if canonical_hash(actual_source)!=canonical_hash(source):
            raise ValueError('control_reference_pose_source_changed')
        geometry = arm_geometry(initial,receipt['geometry']['side'])
        schedule = controller_schedule(receipt['scenario'],geometry['initial_outward_angle_deg'],
                                       seed=receipt['seed'],source_group_id=source['source_group_id'])
        if canonical_hash(geometry)!=canonical_hash(receipt['geometry']) or canonical_hash(schedule)!=canonical_hash(receipt['schedule']):
            raise ValueError('controller_seed_group_schedule_or_geometry_changed')
        style = verify_style_source(receipt['style']['path'])
        if canonical_hash(style)!=canonical_hash(receipt['style']):
            raise ValueError('official_body18_render_style_changed')
        probe = probe_video(receipt['video'])
        timeline = json.loads(Path(receipt['actual_pts_timeline']).read_text(encoding='utf-8'))
        if (probe['frame_count']!=241 or (probe['width'],probe['height'])!=(640,384)
                or any(abs(t-i/30)>1e-10 for i,t in enumerate(probe['presentation_s']))
                or any(probe[key]!=timeline[key] for key in ('video_sha256','frame_count','width','height','time_basis','presentation_s','frames'))):
            raise ValueError('control_full_actual_pts_or_rgb_timeline_changed')
        trajectory = json.loads(Path(receipt['controller_trajectory']).read_text(encoding='utf-8'))
        if (trajectory.get('is_GT') is not False or trajectory.get('controller_timestamps_are_generated_video_labels') is not False
                or trajectory.get('scenario')!=receipt['scenario'] or trajectory.get('seed')!=receipt['seed']
                or canonical_hash(trajectory.get('source'))!=canonical_hash(source)
                or len(trajectory.get('frames',[]))!=241):
            raise ValueError('controller_trajectory_source_seed_or_non_GT_contract_changed')
        if receipt.get('lineage_ids')!=control_lineage(source,receipt['controller_trajectory_sha256'],receipt['video_sha256']):
            raise ValueError('controller_instance_lineage_hashes_changed')
        for index,(row,decoded) in enumerate(zip(trajectory['frames'],probe['frames'])):
            timestamp = index/30
            angle = commanded_angle(schedule,timestamp)
            expected_points = control_frame(initial,geometry,angle)
            if (row.get('frame_index')!=index or row.get('controller_timestamp_s')!=timestamp
                    or row.get('commanded_angle_deg')!=angle
                    or canonical_hash(row.get('openpose18'))!=canonical_hash(expected_points)
                    or row.get('rendered_rgb_sha256')!=decoded['decoded_rgb_sha256']
                    or hashlib.sha256(render_body18(expected_points).tobytes()).hexdigest()!=decoded['decoded_rgb_sha256']):
                raise ValueError('controller_rigid_chain_times_or_decoded_pixels_changed')
    return receipt


def render_controls(pose_path, reference_record, output_dir, *, side='left',seed=20261019,
                    scenarios=('A','D','E'),style_source=DEFAULT_STYLE_SOURCE):
    """Create A/D/E 241-frame guides and full receipts; never overwrite files."""
    import av
    from PIL import Image
    style = verify_style_source(style_source)
    initial,source = load_initial(pose_path,reference_record)
    if re.fullmatch(r'[A-Za-z0-9_-]{1,96}',source['source_group_id']) is None:
        raise ValueError('safe_source_group_filename_required')
    geometry = arm_geometry(initial,side)
    if not scenarios or len(set(scenarios))!=len(scenarios) or any(item not in ('A','D','E') for item in scenarios):
        raise ValueError('unique_controller_scenarios_A_D_E_required')
    output = Path(output_dir).resolve()
    output.mkdir(parents=True,exist_ok=False)
    _new_json(output/'initial-source.json',dict(source=source,initial_openpose18=initial,geometry=geometry,
        style=style,controller_version=VERSION,seed=seed,independent_ground_truth=False,is_GT=False))
    receipts = []
    for scenario in scenarios:
        folder = output/scenario
        folder.mkdir()
        pngs = folder/'frames'
        pngs.mkdir()
        schedule = controller_schedule(scenario,geometry['initial_outward_angle_deg'],seed=seed,
                                       source_group_id=source['source_group_id'])
        path = folder/(source['source_group_id']+'_'+scenario+'_body18_control.mp4')
        rows,hashes = [],[]
        with av.open(str(path),'w') as container:
            stream = container.add_stream('libx264rgb',rate=30)
            stream.width,stream.height,stream.pix_fmt = 640,384,'rgb24'
            stream.options = {'crf':'0','preset':'fast'}
            for index in range(241):
                timestamp = index/30
                angle = commanded_angle(schedule,timestamp)
                points = control_frame(initial,geometry,angle)
                for point in points.values():
                    if point is not None and not (5<=point['x']<635 and 5<=point['y']<379):
                        raise ValueError('controller_joint_outside_safe_original_canvas')
                rgb = render_body18(points)
                fingerprint = hashlib.sha256(rgb.tobytes()).hexdigest()
                image_path = pngs/f'{index:05d}.png'
                Image.fromarray(rgb).save(image_path)
                hashes.append(fingerprint)
                rows.append(dict(frame_index=index,controller_timestamp_s=timestamp,commanded_angle_deg=angle,
                    openpose18=points,rendered_rgb_sha256=fingerprint,png_sha256=file_hash(image_path)))
                frame = av.VideoFrame.from_ndarray(rgb,format='rgb24')
                frame.pts,frame.time_base = index,Fraction(1,30)
                for packet in stream.encode(frame):
                    container.mux(packet)
            for packet in stream.encode():
                container.mux(packet)
        probe = probe_video(path,timeline_path=folder/'timeline.json')
        if (probe['frame_count']!=241 or [probe['width'],probe['height']]!=[640,384]
                or any(abs(t-i/30)>1e-10 for i,t in enumerate(probe['presentation_s']))
                or hashes!=[row['decoded_rgb_sha256'] for row in probe['frames']]):
            raise ValueError('control_video_roundtrip_pts_or_rgb_changed')
        trajectory = folder/'controller-trajectory.json'
        _new_json(trajectory,dict(schema_version=VERSION,scenario=scenario,source=source,
            commanded_side=side,side_basis='frozen_model_joint_name_not_human_reference',schedule=schedule,
            controller_timestamps_are_generated_video_labels=False,is_GT=False,seed=seed,frames=rows))
        receipt = dict(schema_version=VERSION,scenario=scenario,source=source,geometry=geometry,schedule=schedule,
            style=style,width=640,height=384,fps=30,frames=241,seed=seed,is_GT=False,
            video=str(path),video_sha256=file_hash(path),
            initial_source_path=str(output/'initial-source.json'),initial_source_sha256=file_hash(output/'initial-source.json'),
            video_codec='libx264rgb_crf0_rgb24',lossless_rgb_roundtrip_verified=True,
            actual_pts_timeline=str(folder/'timeline.json'),timeline_sha256=file_hash(folder/'timeline.json'),
            controller_trajectory=str(trajectory),controller_trajectory_sha256=file_hash(trajectory),
            png_frames_directory=str(pngs),controller_version=VERSION,controller_implementation_sha256=file_hash(__file__),
            source_reference_image_edited=False,created_human_annotations=False,
            control_coordinates_are_model_predictions_or_commands_not_independent_ground_truth=True,
            controller_timestamps_are_generated_video_labels=False,generated_person_video_motion_verified=False,
            training_reference_eligible=False,product_enabled=False)
        receipt['lineage_ids'] = control_lineage(source,receipt['controller_trajectory_sha256'],receipt['video_sha256'])
        _new_json(folder/'receipt.json',receipt)
        receipts.append(receipt)
        print(json.dumps(dict(control_ready=scenario,receipt=str(folder/'receipt.json'),video=str(path),is_GT=False)),flush=True)
    for path_key,hash_key in (('reference_image','reference_image_sha256'),('reference_video','reference_video_sha256'),
                              ('source_pose_path','source_pose_sha256'),('reference_record','reference_record_sha256')):
        if file_hash(source[path_key])!=source[hash_key]:
            raise ValueError('original_source_changed_during_controller_render:'+path_key)
    result = dict(schema_version=VERSION,status='rendered_control_guides_only',source=source,
                  scenarios=receipts,seed=seed,is_GT=False,independent_ground_truth=False,training_reference_eligible=False)
    _new_json(output/'receipt.json',result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pose',type=Path,required=True)
    parser.add_argument('--reference-record',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--side',choices=['left','right'],default='left')
    parser.add_argument('--seed',type=int,default=20261019)
    parser.add_argument('--scenarios',choices=['A','D','E'],nargs='+',default=['A','D','E'])
    parser.add_argument('--style-source',type=Path,default=DEFAULT_STYLE_SOURCE)
    args = parser.parse_args()
    result = render_controls(args.pose,args.reference_record,args.output_dir,side=args.side,seed=args.seed,
                             scenarios=args.scenarios,style_source=args.style_source)
    print(json.dumps(dict(status=result['status'],videos=[r['video'] for r in result['scenarios']],
                         independent_ground_truth=False),ensure_ascii=True))


if __name__=='__main__':
    main()
