"""CPU command/geometry checks; no video, labels, model inference or rendering."""
from copy import deepcopy
import json
import math
import unittest

from tools.rehab_ml.synthetic import control, motion


def initial(*, mirrored=False):
    xy = dict(nose=(320,45),right_eye=(316,41),left_eye=(324,41),
        right_ear=(309,45),left_ear=(331,45),right_shoulder=(290,90),
        right_elbow=(282,145),right_wrist=(280,198),left_shoulder=(350,90),
        left_elbow=(360,145),left_wrist=(364,198),right_hip=(300,200),
        left_hip=(340,200),right_knee=(300,280),left_knee=(340,280),
        right_ankle=(300,355),left_ankle=(340,355))
    return control.initial_geometry({name:dict(x=float(640-x if mirrored else x),
        y=float(y),confidence=.99) for name,(x,y) in xy.items()})


def length(a,b):
    return math.hypot(a['x']-b['x'],a['y']-b['y'])


def schedule(scenario, *, seed=42, group='TEST-A', frames=241, angle=10.):
    return motion.build_schedule(scenario,angle,seed=seed,source_group_id=group,frames=frames)


class MotionScheduleTests(unittest.TestCase):
    def test_A_D_E_commands_equal_legacy_at_all_native_frames_and_boundaries(self):
        for scenario in ('A','D','E'):
            for seed in (0,17,2**32-1):
                for start in (-20.,10.,45.):
                    with self.subTest(scenario=scenario,seed=seed,start=start):
                        old=control.controller_schedule(scenario,start,seed=seed,source_group_id='TEST')
                        new=motion.build_schedule(scenario,start,seed=seed,source_group_id='TEST')
                        self.assertEqual(new['legacy_recipe_version'],control.VERSION)
                        self.assertEqual(new['keyframe_controller_times_s'],old['keyframe_controller_times_s'])
                        self.assertEqual(new['derived_schedule_seed'],old['derived_schedule_seed'])
                        self.assertEqual([c['shoulder_angle_deg'] for c in new['keyframe_commands']],old['keyframe_angles_deg'])
                        for t in [i/30 for i in range(241)]+old['keyframe_controller_times_s']:
                            self.assertEqual(motion.command_at(new,t),dict(
                                shoulder_angle_deg=control.commanded_angle(old,t),elbow_bend_deg=0.))

    def test_B_has_same_amplitude_and_slower_outbound_and_return_than_A(self):
        for seed in range(20):
            for group in ('TEST-A','TEST-B'):
                with self.subTest(seed=seed,group=group):
                    a=schedule('A',seed=seed,group=group)
                    b=schedule('B',seed=seed,group=group)
                    self.assertEqual(a['keyframe_commands'],b['keyframe_commands'])
                    ta,tb=a['keyframe_controller_times_s'],b['keyframe_controller_times_s']
                    for lo,hi in ((1,2),(3,4)):
                        self.assertGreater(tb[hi]-tb[lo],ta[hi]-ta[lo]+.29)
                        # Same quintic path and amplitude means lower actual
                        # numerical peak command speed, not only a recipe name.
                        speeds=[]
                        for item,times in ((a,ta),(b,tb)):
                            mid=(times[lo]+times[hi])/2;step=1e-4
                            speeds.append(abs((motion.command_at(item,mid+step)['shoulder_angle_deg']-
                                motion.command_at(item,mid-step)['shoulder_angle_deg'])/(2*step)))
                        self.assertLess(speeds[1],speeds[0])
                    self.assertLess(tb[4],8.)
                    self.assertEqual(motion.command_at(b,0),motion.command_at(b,8))

    def test_C_has_real_two_second_constant_command_hold_longer_than_A(self):
        for seed in range(20):
            with self.subTest(seed=seed):
                a,c=schedule('A',seed=seed),schedule('C',seed=seed)
                ta,tc=a['keyframe_controller_times_s'],c['keyframe_controller_times_s']
                hold=tc[3]-tc[2]
                self.assertGreaterEqual(hold,1.8);self.assertLessEqual(hold,2.2)
                self.assertGreater(hold,ta[3]-ta[2])
                target=max(command['shoulder_angle_deg'] for command in c['keyframe_commands'])
                for fraction in (0.,.1,.5,.9,1.):
                    self.assertEqual(motion.command_at(c,tc[2]+fraction*hold),
                        dict(shoulder_angle_deg=target,elbow_bend_deg=0.))
                self.assertLess(tc[4],8.)
                self.assertEqual(motion.command_at(c,0),motion.command_at(c,8))

    def test_F_uses_A_shoulder_trajectory_with_45_to_70_degree_elbow_rotation(self):
        for seed in range(10):
            a,f=schedule('A',seed=seed),schedule('F',seed=seed)
            self.assertEqual(a['keyframe_controller_times_s'],f['keyframe_controller_times_s'])
            peak=max(command['elbow_bend_deg'] for command in f['keyframe_commands'])
            self.assertGreaterEqual(peak,45.);self.assertLessEqual(peak,70.)
            for t in [i/30 for i in range(241)]:
                self.assertEqual(motion.command_at(a,t)['shoulder_angle_deg'],
                    motion.command_at(f,t)['shoulder_angle_deg'])
            self.assertEqual(motion.command_at(f,0),motion.command_at(f,8))
            self.assertEqual(motion.command_at(f,8)['elbow_bend_deg'],0.)

    def test_D_stays_partial_and_E_stays_identical_at_every_frame(self):
        d,e=schedule('D'),schedule('E')
        self.assertGreater(motion.command_at(d,8)['shoulder_angle_deg'],18.)
        for index in range(241):
            self.assertEqual(motion.command_at(e,index/30),dict(shoulder_angle_deg=10.,elbow_bend_deg=0.))

    def test_group_seed_and_scenario_are_deterministic_without_shared_event_times(self):
        for scenario in motion.SCENARIOS:
            with self.subTest(scenario=scenario):
                original=schedule(scenario)
                self.assertEqual(original,schedule(scenario))
                other_group,other_seed=schedule(scenario,group='TEST-B'),schedule(scenario,seed=43)
                self.assertNotEqual(original['derived_schedule_seed'],other_group['derived_schedule_seed'])
                self.assertNotEqual(original['derived_schedule_seed'],other_seed['derived_schedule_seed'])
                if scenario != 'E':  # Stillness has no event boundary to randomize.
                    self.assertNotEqual(original['keyframe_controller_times_s'],other_group['keyframe_controller_times_s'])
                    self.assertNotEqual(original['keyframe_controller_times_s'],other_seed['keyframe_controller_times_s'])
                self.assertEqual(original,json.loads(json.dumps(original,allow_nan=False)))

    def test_native_longer_clips_add_only_a_static_tail_without_stretching(self):
        for scenario in motion.SCENARIOS:
            short,long=schedule(scenario),schedule(scenario,frames=305)
            self.assertEqual(long['time_base'],[1,30]);self.assertEqual(long['fps'],30)
            self.assertEqual(long['duration_s'],304/30)
            self.assertEqual(short['keyframe_controller_times_s'],long['keyframe_controller_times_s'][:-1])
            self.assertEqual(short['keyframe_commands'],long['keyframe_commands'][:-1])
            for t in [i/30 for i in range(241)]:
                self.assertEqual(motion.command_at(short,t),motion.command_at(long,t))
            for t in (8.,8.5,9.,304/30):
                self.assertEqual(motion.command_at(long,t),motion.command_at(short,8.))

    def test_schedule_has_explicit_non_GT_units_and_no_human_reference(self):
        for scenario in motion.SCENARIOS:
            item=schedule(scenario)
            self.assertEqual(item['schema_version'],motion.VERSION)
            self.assertEqual(item['recipe_version'],motion.VERSION)
            self.assertEqual(item['time_basis'],'controller_command_time_not_media_PTS')
            for flag in motion.NON_GT_FLAGS:self.assertIs(item[flag],False,flag)
            for field in ('observable_count','phase_intervals','repetitions','quality','annotations','clinical_ROM'):
                self.assertNotIn(field,item)

    def test_invalid_recipe_inputs_reject_before_command_creation(self):
        cases=(dict(scenario='G'),dict(scenario=None),dict(angle=math.nan),dict(angle=math.inf),
            dict(angle=-math.inf),dict(angle=True),dict(angle=46),dict(angle=-21),
            dict(seed=True),dict(seed=-1),dict(seed=2**32),dict(seed=1.5),dict(seed=math.nan),
            dict(group=''),dict(group=' '),dict(group=None),dict(frames=193),dict(frames=240),
            dict(frames=242),dict(frames=1001),dict(frames=True),dict(frames=241.),dict(frames=math.nan))
        for changed in cases:
            values=dict(scenario='A',seed=42,group='TEST-A',frames=241,angle=10.);values.update(changed)
            with self.subTest(changed=changed),self.assertRaises(ValueError):schedule(**values)

    def test_nonmonotonic_NaN_commands_and_forged_GT_or_tail_are_rejected(self):
        base=schedule('F')
        broken=[]
        for value in (base['keyframe_controller_times_s'][1],math.nan,math.inf,-1.):
            item=deepcopy(base);item['keyframe_controller_times_s'][2]=value;broken.append(item)
        item=deepcopy(base);item['keyframe_controller_times_s'].reverse();broken.append(item)
        for field,value in (('shoulder_angle_deg',math.nan),('elbow_bend_deg',math.inf),
                            ('elbow_bend_deg',71.),('shoulder_angle_deg',91.)):
            item=deepcopy(base);item['keyframe_commands'][2][field]=value;broken.append(item)
        for flag in motion.NON_GT_FLAGS:
            item=deepcopy(base);item[flag]=True;broken.append(item)
        item=deepcopy(base);item['derived_schedule_seed']=math.nan;broken.append(item)
        item=schedule('F',frames=305);item['keyframe_commands'][-1]['elbow_bend_deg']=1.;broken.append(item)
        item=deepcopy(base);item['keyframe_commands'][0]['elbow_bend_deg']=1.;broken.append(item)
        for index,item in enumerate(broken):
            with self.subTest(index=index),self.assertRaises(ValueError):motion.command_at(item,1.)
        for timestamp in (math.nan,math.inf,-math.inf,-.001,8.001,True,None,'1'):
            with self.subTest(timestamp=timestamp),self.assertRaises(ValueError):motion.command_at(base,timestamp)


class MotionFrameTests(unittest.TestCase):
    def test_zero_elbow_bend_exactly_reuses_existing_rigid_controller_on_both_sides(self):
        for mirrored in (False,True):
            source=initial(mirrored=mirrored)
            for side in ('left','right'):
                geometry=control.arm_geometry(source,side)
                for angle in (geometry['initial_outward_angle_deg'],35.,70.,85.):
                    with self.subTest(mirrored=mirrored,side=side,angle=angle):
                        expected=control.control_frame(source,geometry,angle)
                        self.assertEqual(motion.frame_at(source,geometry,dict(
                            shoulder_angle_deg=angle,elbow_bend_deg=0.)),expected)

    def test_F_preserves_all_bone_lengths_non_test_joints_and_original_first_last_pose(self):
        for mirrored in (False,True):
            for side in ('left','right'):
                source=initial(mirrored=mirrored);before=deepcopy(source)
                geometry=control.arm_geometry(source,side)
                item=schedule('F',angle=geometry['initial_outward_angle_deg'])
                with self.subTest(mirrored=mirrored,side=side):
                    for index in range(241):
                        command=motion.command_at(item,index/30)
                        output=motion.frame_at(source,geometry,command)
                        straight=control.control_frame(source,geometry,command['shoulder_angle_deg'])
                        self.assertEqual(set(output),set(control.OPENPOSE18))
                        for name in source:
                            if name not in (side+'_elbow',side+'_wrist'):
                                self.assertEqual(output[name],source[name],name)
                        self.assertEqual(output[side+'_elbow'],straight[side+'_elbow'])
                        self.assertAlmostEqual(length(output[side+'_shoulder'],output[side+'_elbow']),geometry['upper_arm_px'],places=10)
                        self.assertAlmostEqual(length(output[side+'_elbow'],output[side+'_wrist']),geometry['forearm_px'],places=10)
                    self.assertEqual(motion.frame_at(source,geometry,motion.command_at(item,0.)),source)
                    self.assertEqual(motion.frame_at(source,geometry,motion.command_at(item,8.)),source)
                    self.assertEqual(source,before)

    def test_F_bends_forearm_toward_head_with_correct_matrix_for_either_image_side(self):
        for mirrored in (False,True):
            for side in ('left','right'):
                source=initial(mirrored=mirrored);geometry=control.arm_geometry(source,side)
                item=schedule('F',angle=geometry['initial_outward_angle_deg'])
                peak=item['keyframe_controller_times_s'][2]
                command=motion.command_at(item,peak)
                output=motion.frame_at(source,geometry,command)
                straight=control.control_frame(source,geometry,command['shoulder_angle_deg'])
                elbow=output[side+'_elbow'];bent=output[side+'_wrist'];flat=straight[side+'_wrist']
                with self.subTest(mirrored=mirrored,side=side):
                    self.assertLess(bent['y'],elbow['y'])
                    self.assertLess(bent['y'],flat['y'])
                    self.assertLess(math.hypot(bent['x']-source['nose']['x'],bent['y']-source['nose']['y']),
                        math.hypot(flat['x']-source['nose']['x'],flat['y']-source['nose']['y']))
                    u=(flat['x']-elbow['x'],flat['y']-elbow['y'])
                    v=(bent['x']-elbow['x'],bent['y']-elbow['y'])
                    bend=math.degrees(math.acos(max(-1.,min(1.,(u[0]*v[0]+u[1]*v[1])/
                        (math.hypot(*u)*math.hypot(*v))))))
                    self.assertAlmostEqual(bend,command['elbow_bend_deg'],places=10)
                    cross=u[0]*v[1]-u[1]*v[0]
                    self.assertLess(cross*geometry['outward_image_direction'],0.)
                    self.assertEqual(output[side+'_elbow'],straight[side+'_elbow'])

    def test_optional_missing_face_point_remains_unknown(self):
        source=initial();source['right_ear']=None
        geometry=control.arm_geometry(source)
        result=motion.frame_at(source,geometry,dict(shoulder_angle_deg=80.,elbow_bend_deg=60.))
        self.assertIsNone(result['right_ear'])

    def test_invalid_commands_and_changed_or_NaN_source_geometry_reject(self):
        source=initial();geometry=control.arm_geometry(source)
        for command in ({},dict(shoulder_angle_deg=math.nan,elbow_bend_deg=0.),
                dict(shoulder_angle_deg=80.,elbow_bend_deg=math.nan),
                dict(shoulder_angle_deg=80.,elbow_bend_deg=-1.),
                dict(shoulder_angle_deg=80.,elbow_bend_deg=71.),
                dict(shoulder_angle_deg=True,elbow_bend_deg=0.)):
            with self.subTest(command=command),self.assertRaises(ValueError):
                motion.frame_at(source,geometry,command)
        command=dict(shoulder_angle_deg=80.,elbow_bend_deg=60.)
        for field,value in (('upper_arm_px',math.nan),('forearm_px',100.),
                            ('initial_outward_angle_deg',15.),('outward_image_direction',-1),
                            ('outward_image_direction',True),('side','bilateral')):
            changed=deepcopy(geometry);changed[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):motion.frame_at(source,changed,command)
        for name in ('left_wrist','right_ankle','nose'):
            changed=deepcopy(source);changed[name]['x']=math.nan
            with self.subTest(name=name),self.assertRaises(ValueError):motion.frame_at(changed,geometry,command)
        changed=deepcopy(source);changed['nose']['draw_score']=math.nan
        with self.assertRaises(ValueError):motion.frame_at(changed,geometry,command)
        changed=deepcopy(source);del changed['nose']
        with self.assertRaises(ValueError):motion.frame_at(changed,geometry,command)
        changed=deepcopy(source);changed['left_wrist']=None
        with self.assertRaises(ValueError):motion.frame_at(changed,geometry,command)


if __name__=='__main__':unittest.main()
