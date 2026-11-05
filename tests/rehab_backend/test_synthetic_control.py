"""Pure geometry/style/receipt checks; no pose models or generated GT."""
from copy import deepcopy
import hashlib
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from tools.rehab_ml.synthetic import control
from tools.rehab_ml.synthetic.video import _new_json


def initial():
    xy = dict(nose=(320,45),right_eye=(316,41),left_eye=(324,41),right_ear=(309,45),left_ear=(331,45),
        right_shoulder=(290,90),right_elbow=(282,145),right_wrist=(280,198),
        left_shoulder=(350,90),left_elbow=(360,145),left_wrist=(364,198),
        right_hip=(300,200),left_hip=(340,200),right_knee=(300,280),left_knee=(340,280),
        right_ankle=(300,355),left_ankle=(340,355))
    return control.initial_geometry({name:dict(x=float(x),y=float(y),confidence=.99) for name,(x,y) in xy.items()})


class SyntheticControlTests(unittest.TestCase):
    def test_initial_rejects_missing_formal_and_heldout_origin_before_pose_or_source_reads(self):
        invalid=({},dict(stage='pilot'),dict(split='train'),dict(stage=None,split='train'),
                 dict(stage='formal',split='train'),dict(stage='formal',split='val'),
                 dict(stage='formal',split='test'),dict(stage='pilot',split='val'),
                 dict(stage='pilot',split='test'))
        with tempfile.TemporaryDirectory(prefix='synthetic-control-TEST-') as temporary:
            root=Path(temporary)
            for index,origin in enumerate(invalid):
                with self.subTest(origin=origin):
                    reference=root/f'reference-{index}.json';_new_json(reference,origin)
                    with patch.object(control,'validate_pose') as pose,patch.object(control,'file_hash') as hashes,\
                            patch('PIL.Image.open') as image:
                        with self.assertRaisesRegex(ValueError,'explicit_pilot_train_source'):
                            control.load_initial(root/'MUST-NOT-READ-pose.json',reference)
                    pose.assert_not_called();hashes.assert_not_called();image.assert_not_called()

    def test_initial_preserves_explicit_pilot_train_source_and_bound_source_hashes(self):
        from PIL import Image
        with tempfile.TemporaryDirectory(prefix='synthetic-control-TEST-') as temporary:
            root=Path(temporary);image=root/'reference.png';movie=root/'TEST-reference.mp4';pose=root/'TEST-pose.json'
            Image.new('RGB',(640,384)).save(image)
            movie.write_bytes(b'TEST source fixture; not a playable video or reviewed movement')
            _new_json(pose,dict(TEST='validate_pose is mocked; no pose model is run'))
            reference=root/'reference.json'
            _new_json(reference,dict(stage='pilot',split='train',source_group_id='TEST-pilot',
                reference_group_id='TEST-pilot',lineage_ids=['identity:TEST-pilot'],
                image_path=str(image),image_sha256=control.file_hash(image),
                video=dict(path=str(movie),sha256=control.file_hash(movie))))
            points=initial()
            joints={name:dict(x=p['x'],y=p['y'],confidence=p['draw_score'])
                    for name,p in points.items() if name!='neck'}
            with Image.open(image) as original:
                pixel_sha256=hashlib.sha256(original.convert('RGB').tobytes()).hexdigest()
            prediction=dict(status='completed',source_sha256=control.file_hash(movie),
                frame_manifest_path=str(root/'TEST-mocked-frame-manifest.json'),source_size=[640,384],
                backend='yolo17',model=dict(TEST='mocked validator boundary'),
                frames=[dict(frame_index=0,pose_detected=True,joints=joints,pts=0,time_base=[1,30],
                    timestamp_s=0.,track_id='TEST-person',
                    decoded_rgb_sha256=pixel_sha256)])
            with patch.object(control,'validate_pose',side_effect=[deepcopy(prediction),deepcopy(prediction)]) as validator:
                geometry,source=control.load_initial(pose,reference)
            self.assertEqual(geometry,points)
            self.assertEqual((source['stage'],source['split']),('pilot','train'))
            self.assertEqual(source['source_group_id'],'TEST-pilot')
            for path_key,sha_key in (('reference_record','reference_record_sha256'),
                                     ('reference_image','reference_image_sha256'),
                                     ('reference_video','reference_video_sha256'),
                                     ('source_pose_path','source_pose_sha256')):
                self.assertEqual(source[sha_key],control.file_hash(source[path_key]))
            self.assertEqual(validator.call_count,2)
            self.assertEqual(validator.call_args.kwargs['frame_manifest'],prediction['frame_manifest_path'])

    def test_rigid_arm_only_changes_named_elbow_wrist_and_preserves_lengths(self):
        source=initial();geometry=control.arm_geometry(source,'left')
        for angle in (geometry['initial_outward_angle_deg'],35.,70.,85.):
            changed=control.control_frame(source,geometry,angle)
            for name in source:
                if name not in ('left_elbow','left_wrist'):
                    self.assertEqual(source[name],changed[name])
            shoulder,elbow,wrist=(control._xy(changed['left_'+part]) for part in ('shoulder','elbow','wrist'))
            self.assertAlmostEqual(float(np.linalg.norm(elbow-shoulder)),geometry['upper_arm_px'],places=10)
            self.assertAlmostEqual(float(np.linalg.norm(wrist-elbow)),geometry['forearm_px'],places=10)
        self.assertEqual(source,control.control_frame(source,geometry,geometry['initial_outward_angle_deg']))

    def test_A_returns_D_stays_raised_E_stays_static_without_becoming_labels(self):
        source=initial();geometry=control.arm_geometry(source)
        start=geometry['initial_outward_angle_deg']
        schedules={s:control.controller_schedule(s,start,seed=123,source_group_id='TEST') for s in ('A','D','E')}
        self.assertEqual(control.commanded_angle(schedules['A'],0),start)
        self.assertEqual(control.commanded_angle(schedules['A'],8),start)
        self.assertTrue(70<=max(schedules['A']['keyframe_angles_deg'])<=85)
        self.assertGreater(control.commanded_angle(schedules['D'],8),start+5)
        self.assertTrue(all(control.commanded_angle(schedules['E'],i/30)==start for i in range(241)))
        for schedule in schedules.values():
            self.assertFalse(schedule['controller_timestamps_are_generated_video_labels'])
            self.assertNotIn('observable_count',schedule)

    def test_group_and_seed_change_schedule_without_changing_group_determinism(self):
        a=control.controller_schedule('A',10.,seed=42,source_group_id='TEST-A')
        self.assertEqual(a,control.controller_schedule('A',10.,seed=42,source_group_id='TEST-A'))
        self.assertNotEqual(a['keyframe_controller_times_s'],control.controller_schedule('A',10.,seed=42,source_group_id='TEST-B')['keyframe_controller_times_s'])
        self.assertNotEqual(a['keyframe_angles_deg'],control.controller_schedule('A',10.,seed=43,source_group_id='TEST-A')['keyframe_angles_deg'])

    def test_global_algorithm_version_never_becomes_shared_source_lineage(self):
        source={'lineage_ids':['identity:TEST','reference_image:'+'a'*64]}
        lineage=control.control_lineage(source,'b'*64,'c'*64)
        self.assertEqual(lineage[-2:],['controller_trajectory:'+'b'*64,'controller_video:'+'c'*64])
        self.assertNotIn('controller:'+control.VERSION,lineage)

    def test_openpose_neck_and_rgb_joint_color_do_not_swap_anatomical_sides(self):
        points=initial()
        self.assertEqual(points['neck']['x'],320.)
        image=control.render_body18(points)
        self.assertEqual(list(image.shape),[384,640,3])
        for name,index in [('left_wrist',7),('right_wrist',4)]:
            p=points[name]
            self.assertEqual(image[int(p['y']),int(p['x'])].tolist(),list(control.COLORS[index]))
        self.assertEqual(image[0,0].tolist(),[0,0,0])
        self.assertEqual(control.OPENPOSE18[2:8],('right_shoulder','right_elbow','right_wrist','left_shoulder','left_elbow','left_wrist'))

    def test_unknown_source_arm_joint_and_non_down_initial_arm_are_rejected(self):
        points=initial()
        joints={name:dict(x=p['x'],y=p['y'],confidence=p['draw_score']) for name,p in points.items() if name!='neck'}
        joints['left_wrist']['confidence']=.1
        with self.assertRaisesRegex(ValueError,'initial_body_joint'):
            control.initial_geometry(joints)
        points=initial();points['left_elbow']['y']=40
        with self.assertRaisesRegex(ValueError,'relaxed_down'):
            control.arm_geometry(points)

    def test_receipt_never_accepts_GT_or_wrong_group_scenario_reference(self):
        base=dict(schema_version=control.VERSION,controller_version=control.VERSION,scenario='A',is_GT=False,
            training_reference_eligible=False,controller_timestamps_are_generated_video_labels=False,
            width=640,height=384,frames=241,fps=30,seed=42,
            source=dict(source_group_id='TEST',reference_image_sha256='a'*64,stage='pilot',split='train'))
        with tempfile.TemporaryDirectory(prefix='synthetic-control-TEST-') as temporary:
            p=Path(temporary)/'receipt.json';_new_json(p,base)
            self.assertEqual(control.load_control(p,verify=False,expected_source_group_id='TEST')['scenario'],'A')
            for expected in ({'expected_source_group_id':'other'},{'expected_scenario':'D'},
                             {'expected_reference_image_sha256':'b'*64}):
                with self.assertRaisesRegex(ValueError,'group_scenario_or_reference'):
                    control.load_control(p,verify=False,**expected)
            changed=deepcopy(base);changed['is_GT']=True
            q=Path(temporary)/'false-GT.json';_new_json(q,changed)
            with self.assertRaisesRegex(ValueError,'non_GT'):
                control.load_control(q,verify=False)

    def test_receipt_even_without_verification_requires_explicit_pilot_train_source(self):
        invalid=(None,{},dict(stage='pilot'),dict(split='train'),dict(stage='formal',split='train'),
                 dict(stage='formal',split='val'),dict(stage='formal',split='test'),
                 dict(stage='pilot',split='val'),dict(stage='pilot',split='test'))
        base=dict(schema_version=control.VERSION,controller_version=control.VERSION,scenario='A',is_GT=False,
            training_reference_eligible=False,controller_timestamps_are_generated_video_labels=False,
            width=640,height=384,frames=241,fps=30,seed=42)
        with tempfile.TemporaryDirectory(prefix='synthetic-control-TEST-') as temporary:
            for index,source in enumerate(invalid):
                receipt=deepcopy(base)
                if source is not None:receipt['source']=source
                path=Path(temporary)/f'receipt-{index}.json';_new_json(path,receipt)
                for verify in (False,True):
                    with self.subTest(source=source,verify=verify),patch.object(control,'file_hash') as hashes,\
                            patch.object(control,'load_initial') as initial_loader,\
                            patch.object(control,'validate_pose') as pose,patch.object(control,'probe_video') as probe:
                        with self.assertRaisesRegex(ValueError,'explicit_pilot_train_source'):
                            control.load_control(path,verify=verify)
                        hashes.assert_not_called();initial_loader.assert_not_called()
                        pose.assert_not_called();probe.assert_not_called()


if __name__=='__main__':unittest.main()
