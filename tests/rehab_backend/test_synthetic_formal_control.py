"""Temporary TEST media/poses/freezes only; no real labels, model or GPU."""
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import av
import numpy as np
from PIL import Image

from tools.rehab_ml.synthetic import control, formal_control as fc, formal_plan as fp, generation as g
from tools.rehab_ml.synthetic.video import _new_json, probe_video


def fixture(root):
    groups = {f'TEST-formal{i}': 'train' if i < 6 else 'val' if i < 8 else 'test' for i in range(10)}
    recipe = dict(version='TEST', prompt_version='TEST', seed=7, model_sha256='a'*64,
        model_receipt=dict(path='TEST-model.json', sha256='b'*64),
        config=dict(path='TEST-config.json', sha256='c'*64), scenarios={s: dict(prompt='TEST '+s,
            workflow_template={'1': dict(inputs=dict(seed=0), class_type='TEST')}, late_bindings=[],
            guide_mode='none', guide_version='TEST') for s in 'ABCDEF'})
    profiles = {k: dict(prompt='TEST '+k, identity_ids=[k], lineage_ids=[]) for k in groups}
    plan = fp.draft_formal_plan(cohort12=[f'TEST-pilot{i}-{s}' for i in range(4) for s in 'ADE'],
        profiles=profiles, group_splits=groups, generation_recipe=recipe)
    loaded = dict(plan=plan, split_freeze=plan['split_freeze'], frozen_sha='d'*64)
    group = 'TEST-formal6'  # Exercise held-out split: derived from the TEST freeze.
    media = root/'TEST-reference.mp4'
    with av.open(str(media), 'w') as container:
        stream = container.add_stream('libx264rgb', rate=30)
        stream.width, stream.height, stream.pix_fmt = 640, 384, 'rgb24'
        stream.options = dict(crf='0', preset='ultrafast')
        for i in range(97):
            pixels = np.full((384,640,3), 150+i%3, np.uint8)
            frame = av.VideoFrame.from_ndarray(pixels, format='rgb24')
            frame.pts, frame.time_base = i, Fraction(1,30)
            for packet in stream.encode(frame): container.mux(packet)
        for packet in stream.encode(): container.mux(packet)
    actual = probe_video(media)
    image = root/'TEST-reference.png'
    Image.new('RGB',(640,384),(150,150,150)).save(image)
    xy = dict(nose=(320,45), right_eye=(316,41), left_eye=(324,41), right_ear=(309,45), left_ear=(331,45),
        right_shoulder=(290,90), right_elbow=(282,145), right_wrist=(280,198),
        left_shoulder=(350,90), left_elbow=(360,145), left_wrist=(364,198),
        right_hip=(300,200), left_hip=(340,200), right_knee=(300,280), left_knee=(340,280),
        right_ankle=(300,355), left_ankle=(340,355))
    joints = {k:dict(x=float(x),y=float(y),confidence=.99) for k,(x,y) in xy.items()}
    frame = dict(actual['frames'][0], joints=joints, pose_detected=True, track_id='TEST-track')
    prediction = dict(status='completed', backend='yolo17', source_sha256=g.digest(media), source_size=[640,384],
        frame_manifest_path=str(root/'TEST-frame-manifest.json'), model=dict(TEST='mocked-model-validator'), frames=[frame])
    pose = root/'TEST-pose.json'
    _new_json(pose, dict(TEST='mocked frozen pose validator boundary, never genuine predictions'))
    reference = root/'TEST-reference.json'
    _new_json(reference, dict(schema_version=fc.REFERENCE_VERSION, stage='formal', split='val',
        source_group_id=group, reference_group_id=group, freeze_sha256=loaded['frozen_sha'], reference_attempt=1,
        registry_entry_id=group+':reference:r01', lineage_ids=[group], image_path=str(image), image_sha256=g.digest(image),
        video=dict(path=str(media),sha256=g.digest(media),width=640,height=384,frame_count=97)))
    return loaded, pose, reference, prediction


class FormalControlTests(unittest.TestCase):
    def test_attempt_seed_is_deterministic_bounded_and_first_matches_frozen_slot(self):
        self.assertEqual(fc.attempt_seed(42,1),42)
        self.assertEqual(fc.attempt_seed(42,2),fc.attempt_seed(42,2))
        self.assertNotEqual(fc.attempt_seed(42,2),42)
        for seed, attempt in ((True,1),(-1,1),(2**32,1),(1,False),(1,0),(1,100)):
            with self.assertRaises(ValueError):fc.attempt_seed(seed,attempt)

    def test_missing_human_freeze_fails_before_pose_media_or_comfy_reads(self):
        with tempfile.TemporaryDirectory(prefix='formal-control-TEST-') as tmp:
            root=Path(tmp)
            with patch.object(fc.fp,'load_frozen_plan',side_effect=ValueError('TEST-human-freeze-missing')), \
                    patch.object(fc,'validate_pose') as pose,patch.object(fc,'probe_video') as media,patch.object(g,'api') as api:
                for fn in (lambda:fc.load_initial(root/'pose',root/'ref',root=root),
                        lambda:fc.render_controls(root/'pose',root/'ref',root/'out',root=root),
                        lambda:fc.load_control(root/'receipt',root=root),
                        lambda:fc.prepare_control(root,{},'TEST','A',{},control_path=root/'receipt',lab=root)):
                    with self.assertRaisesRegex(ValueError,'human-freeze-missing'):fn()
                pose.assert_not_called();media.assert_not_called();api.assert_not_called()

    def test_origin_does_not_accept_pilot_wrong_freeze_wrong_split_or_missing_profile(self):
        with tempfile.TemporaryDirectory(prefix='formal-control-TEST-') as tmp:
            loaded,pose,reference,prediction=fixture(Path(tmp))
            record=json.loads(reference.read_text())
            self.assertEqual(fc._reference_origin(loaded,record),'TEST-formal6')
            for changes in (dict(stage='pilot'),dict(split='train'),dict(freeze_sha256='e'*64),
                    dict(reference_attempt=2),dict(reference_group_id='TEST-formal0'),dict(lineage_ids=['TEST-other'])):
                with self.subTest(changes=changes),self.assertRaises(ValueError):fc._reference_origin(loaded,dict(record,**changes))

    def test_actual_reference_png_must_equal_raw_frame0_and_model_pts(self):
        with tempfile.TemporaryDirectory(prefix='formal-control-TEST-') as tmp:
            root=Path(tmp);loaded,pose,reference,prediction=fixture(root)
            with patch.object(fc.fp,'load_frozen_plan',return_value=loaded),patch.object(fc,'validate_pose',return_value=prediction):
                initial,source=fc.load_initial(pose,reference,root=root)
                self.assertEqual(source['split'],'val');self.assertEqual(source['source_frame_index'],0)
                self.assertEqual(source['source_decoded_rgb_sha256'],prediction['frames'][0]['decoded_rgb_sha256'])
                wrong=deepcopy(prediction);wrong['frames'][0]['pts']+=1
                with patch.object(fc,'validate_pose',return_value=wrong),self.assertRaisesRegex(ValueError,'frame0_pts_rgb'):
                    fc.load_initial(pose,reference,root=root)
                Image.new('RGB',(640,384),(151,150,150)).save(root/'TEST-reference.png')
                record=json.loads(reference.read_text());record['image_sha256']=g.digest(root/'TEST-reference.png')
                reference.write_text(json.dumps(record))
                with self.assertRaisesRegex(ValueError,'frame0_pts_rgb'):fc.load_initial(pose,reference,root=root)

    def test_lossless_B_C_F_and_D_guides_verify_all_frames_and_reject_rehashed_command_tampering(self):
        with tempfile.TemporaryDirectory(prefix='formal-control-TEST-') as tmp:
            root=Path(tmp);loaded,pose,reference,prediction=fixture(root)
            style=dict(path='TEST-pinned-style',TEST='mocked only pinned upstream source-byte lookup')
            with patch.object(fc.fp,'load_frozen_plan',return_value=loaded),patch.object(fc,'validate_pose',return_value=prediction), \
                    patch.object(control,'verify_style_source',return_value=style):
                paths=fc.render_controls(pose,reference,root/'out',root=root,scenarios=('B','C','D','F'))
                records=[fc.load_control(p,root=root) for p in paths]
                for record in records:
                    self.assertEqual(record['source']['split'],'val');self.assertEqual(record['frames'],241)
                    self.assertFalse(record['is_GT']);self.assertFalse(record['commands_are_output_labels'])
                    slot=fc._slot(loaded,'TEST-formal6',record['scenario'])
                    self.assertEqual(record['seed'],slot['seed'])
                b,c,d,f=records
                self.assertEqual(d['schedule']['keyframe_commands'][-1]['elbow_bend_deg'],0.)
                self.assertGreater(max(v['elbow_bend_deg'] for v in f['schedule']['keyframe_commands']),45.)
                self.assertGreaterEqual(c['schedule']['keyframe_controller_times_s'][3]-c['schedule']['keyframe_controller_times_s'][2],1.8)
                with self.assertRaises(FileExistsError):fc.render_controls(pose,reference,root/'out',root=root)
                actual_probe=fc.probe_video
                def wrong_geometry(path):
                    result=actual_probe(path)
                    if Path(path)==Path(f['video']):result.update(width=320,height=768)
                    return result
                # Flattened RGB hashes alone do not establish original geometry.
                with patch.object(fc,'probe_video',side_effect=wrong_geometry),self.assertRaisesRegex(ValueError,'actual_native_geometry'):
                    fc.load_control(paths[-1],root=root)
                trajectory=Path(f['controller_trajectory']);value=json.loads(trajectory.read_text())
                value['frames'][100]['command']['elbow_bend_deg']+=1
                trajectory.write_text(json.dumps(value));f['controller_trajectory_sha256']=g.digest(trajectory)
                f['lineage_ids']=control.control_lineage(f['source'],f['controller_trajectory_sha256'],f['video_sha256'])
                Path(paths[-1]).write_text(json.dumps(f))
                with self.assertRaisesRegex(ValueError,'trajectory_commands'):fc.load_control(paths[-1],root=root)

    def test_prepare_control_returns_origin_parents_and_checks_copy_and_attempt(self):
        with tempfile.TemporaryDirectory(prefix='formal-control-TEST-') as tmp:
            root=Path(tmp);loaded,pose,reference,prediction=fixture(root)
            lab=root/'TEST-lab';(lab/'ComfyUI/input').mkdir(parents=True)
            with patch.object(fc.fp,'load_frozen_plan',return_value=loaded),patch.object(fc,'validate_pose',return_value=prediction), \
                    patch.object(control,'verify_style_source',return_value=dict(path='TEST-style')):
                paths=fc.render_controls(pose,reference,root/'out',root=root,scenarios=('E',))
                ref=json.loads(reference.read_text())
                record,name,metadata,entries=fc.prepare_control(root,loaded,'TEST-formal6','E',ref,control_path=paths[0],lab=lab)
                self.assertEqual(entries[0]['parents'],[ref['registry_entry_id']])
                self.assertEqual(entries[1]['parents'],[entries[0]['entry_id']])
                refentry=fp.source_registry_entry(loaded['plan'],entry_id=ref['registry_entry_id'],
                    source_group_id='TEST-formal6',kind='reference',assets=dict(reference_png=ref['image_sha256'],reference_video=ref['video']['sha256']))
                fp.validate_registry(loaded['plan'],[refentry,*entries])
                self.assertEqual(g.digest(lab/'ComfyUI/input'/name),record['video_sha256'])
                self.assertEqual(metadata['registry_entry_id'],entries[1]['entry_id'])
                relative=Path(paths[0]).resolve().relative_to(root.resolve())
                self.assertEqual(fc.prepare_control(root,loaded,'TEST-formal6','E',ref,control_path=relative,lab=lab),
                    (record,name,metadata,entries))
                with self.assertRaisesRegex(ValueError,'attempt_or_reference'):fc.prepare_control(root,loaded,'TEST-formal6','E',ref,control_path=paths[0],lab=lab,attempt=2)
                (lab/'ComfyUI/input'/name).write_bytes(b'TEST altered copy')
                with self.assertRaisesRegex(ValueError,'comfy_copy'):fc.prepare_control(root,loaded,'TEST-formal6','E',ref,control_path=paths[0],lab=lab)


if __name__=='__main__':unittest.main()
