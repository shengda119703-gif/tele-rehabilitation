"""Explicit TEST geometry and a blank-video native smoke, not patient accuracy."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch, MagicMock

from app.domain import Context
from tools.rehab_ml.common import file_hash, paths, read_json, write_json
from tools.rehab_ml.mediapipe_video import VideoClock, encode_pose, extract_mediapipe, model_contract
from tools.rehab_ml.pose_video_compare import compare_video_inputs


class MediaPipeVideoTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='TEST-mp-video-',dir=paths()['run'])
        self.root=Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_media_clock_retains_seconds_and_bounded_negative_preroll(self):
        clock=VideoClock()
        self.assertIsNone(clock.accept(-.034))
        self.assertEqual(clock.accept(.03447777777777778),34)
        self.assertEqual(clock.previous,.03447777777777778)
        self.assertEqual(clock.leading_skipped,1)
        self.assertEqual(clock.last_skipped_raw_time_s,-.034)

    def test_clock_does_not_repair_nonfinite_duplicate_backward_or_ms_collision(self):
        for stamp in (float('nan'),float('inf'),True,-.3):
            with self.subTest(stamp=stamp),self.assertRaises(ValueError):
                VideoClock().accept(stamp)
        for stamp in (.1,.099,.1001,-.01):
            clock=VideoClock(); clock.accept(.1)
            with self.subTest(stamp=stamp),self.assertRaises(ValueError): clock.accept(stamp)
        clock=VideoClock()
        for _ in range(4): self.assertIsNone(clock.accept(-.01))
        with self.assertRaises(ValueError): clock.accept(-.01)

    def _landmarks(self):
        return SimpleNamespace(pose_landmarks=[[SimpleNamespace(x=.2,y=.3,z=-.1,visibility=.8,presence=.7)
                                                 for _ in range(33)]])

    def test_encoding_preserves_original_axes_presence_visibility_and_image_z(self):
        context=Context(1,'rehab','TEST','REPLAY_FILE','TEST','TEST')
        pose,previous,raw=encode_pose(self._landmarks(),context,1,0.,(720,1280),'a'*64,10.,None)
        self.assertEqual(pose.people[0].xy[0],[144.,384.])
        self.assertEqual(pose.people[0].conf[0],.7)
        self.assertEqual(raw[0]['visibility'][0],.8)
        self.assertEqual(raw[0]['presence'][0],.7)
        self.assertEqual(raw[0]['image_z'][0],-.1)
        self.assertEqual(pose.coordinate_space,'raw_image_pixels')
        self.assertEqual(pose.schema_id,'mediapipe33-v1')
        self.assertNotIn('world_landmarks',raw[0])

    def test_empty_or_jump_breaks_spatial_identity_not_biometric_claim(self):
        context=Context(1,'rehab','TEST','REPLAY_FILE','TEST','TEST')
        _,prev,_=encode_pose(self._landmarks(),context,1,0.,(100,100),'a'*64,1.,None)
        pose,next_prev,_=encode_pose(self._landmarks(),context,2,.1,(100,100),'a'*64,1.,prev)
        self.assertEqual(pose.people[0].track_key,prev[2])
        empty,unknown,_=encode_pose(SimpleNamespace(pose_landmarks=[]),context,3,.2,(100,100),'a'*64,1.,next_prev)
        self.assertFalse(empty.people); self.assertIsNone(unknown)
        pose,_,_=encode_pose(self._landmarks(),context,4,1.,(100,100),'a'*64,1.,prev)
        self.assertNotEqual(pose.people[0].track_key,prev[2])

    def test_pose_count_and_shape_are_not_silently_accepted(self):
        context=Context(1,'rehab','TEST','REPLAY_FILE','TEST','TEST')
        for value in (SimpleNamespace(pose_landmarks=[[],[]]),SimpleNamespace(pose_landmarks=[[]])):
            with self.assertRaises(ValueError): encode_pose(value,context,1,0.,(100,100),'a'*64,1.,None)

    def test_model_contract_actual_local_build_and_sdk_difference(self):
        model,contract=model_contract()
        self.assertEqual(file_hash(model),contract['weights_sha256'])
        self.assertEqual(contract['apk_javascript_sdk_locked'],'0.10.32')
        self.assertEqual(contract['python_sdk_required'],'1.0.1')
        self.assertTrue(contract['phone_performance_not_measured'])
        self.assertTrue(contract['installed_apk_weights_not_verified'])

    def test_parent_rejects_missing_permission_camera_and_unbounded_wait(self):
        with self.assertRaises(ValueError): extract_mediapipe('0','rehab_squat','left')
        with self.assertRaises(ValueError): extract_mediapipe('0','rehab_squat','left',analysis_consent=True)
        with self.assertRaises(ValueError): extract_mediapipe('0','rehab_squat','left',analysis_consent=True,timeout_s=float('nan'))
        with self.assertRaises(ValueError): extract_mediapipe('0','fitness_squat','left',analysis_consent=True)

    def test_parent_timeout_releases_only_owned_child(self):
        video=self.root/'TEST-placeholder.mp4';video.write_bytes(b'TEST')
        process=MagicMock(pid=123)
        process.wait.side_effect=[subprocess.TimeoutExpired('TEST',5),0]
        process.poll.side_effect=[None,0]
        with patch('tools.rehab_ml.mediapipe_video.subprocess.Popen',return_value=process),self.assertRaises(TimeoutError):
            extract_mediapipe(video,'rehab_squat','left',analysis_consent=True,output_dir=self.root/'timeout',timeout_s=5)
        process.terminate.assert_called_once();process.kill.assert_not_called()
        self.assertTrue(read_json(self.root/'timeout/failure.json')['owned_exit_confirmed'])

    def test_cancel_releases_child_and_does_not_claim_success(self):
        video=self.root/'TEST-placeholder.mp4';video.write_bytes(b'TEST')
        process=MagicMock(pid=123)
        process.wait.side_effect=[KeyboardInterrupt(),0]
        process.poll.side_effect=[None,0]
        with patch('tools.rehab_ml.mediapipe_video.subprocess.Popen',return_value=process),self.assertRaises(KeyboardInterrupt):
            extract_mediapipe(video,'rehab_squat','left',analysis_consent=True,output_dir=self.root/'cancel',timeout_s=5)
        self.assertEqual(read_json(self.root/'cancel/failure.json')['status'],'cancelled_or_wait_failed')
        self.assertFalse((self.root/'cancel/result.json').exists())

    def test_unconfirmed_owned_release_remains_failure(self):
        video=self.root/'TEST-placeholder.mp4';video.write_bytes(b'TEST')
        process=MagicMock(pid=123)
        process.wait.side_effect=subprocess.TimeoutExpired('TEST',5)
        process.poll.return_value=None
        with patch('tools.rehab_ml.mediapipe_video.subprocess.Popen',return_value=process),self.assertRaises(RuntimeError):
            extract_mediapipe(video,'rehab_squat','left',analysis_consent=True,output_dir=self.root/'unknown',timeout_s=5)
        process.terminate.assert_called_once();process.kill.assert_called_once()
        self.assertFalse(read_json(self.root/'unknown/failure.json')['owned_exit_confirmed'])

    def _pair(self):
        refs=[]
        for name,schema in (('yolo','coco17-v1'),('mp','mediapipe33-v1')):
            folder=self.root/name; folder.mkdir()
            rows=[]
            for seq in range(1,4):
                row=dict(seq=seq,time_s=seq/10,size=[100,100],schema_id=schema,coordinate_space='raw_image_pixels',
                    decoded_bgr_sha256=str(seq)*64,metrics={'knee_flexion_deg':dict(valid=True,value=20. if name=='yolo' else 30.)})
                row.update(people=[dict(xy=[[20.,30.]]*17,conf=[.8]*17)] if name=='yolo' else None,
                    raw_pose=[dict(xy=[[23.,34.]]*33,visibility=[.8]*33,presence=[.7]*33)] if name=='mp' else None)
                rows.append(row)
            frames=folder/'pose-frames.jsonl'
            frames.write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')
            result=dict(video_sha256='a'*64,exercise_id='rehab_squat',side='left',frames=3,training_authorized=False,
                        pose_file_sha256=file_hash(frames),v2_summary={'completed':0})
            result.update({'kind':'private_target_domain_backend_replay'} if name=='yolo' else
                          {'status':'python_video_approximation_not_apk_acceptance'})
            refs.append(Path(write_json(folder/'result.json',result)))
        return refs

    def _alter_rows(self,result,change):
        frames=result.parent/'pose-frames.jsonl'
        rows=[json.loads(line) for line in frames.read_text(encoding='utf-8').splitlines()]
        change(rows)
        frames.write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')
        value=read_json(result); value['pose_file_sha256']=file_hash(frames); write_json(result,value)

    def test_pixel_and_pts_match_yields_disagreement_not_accuracy(self):
        y,m=self._pair()
        result=compare_video_inputs(y,m,self.root/'compare')
        report=read_json(result['path'])
        self.assertEqual(report['frames']['timestamp_and_pixel_matched'],3)
        self.assertEqual(report['point_disagreement_px']['left_knee']['mean_absolute_disagreement'],5.)
        self.assertEqual(report['filtered_projected_angle_disagreement_deg']['knee_flexion_deg']['mean_absolute_disagreement'],10.)
        self.assertIsNone(report['clinical_accuracy']); self.assertIsNone(report['count_accuracy'])

    def test_same_pts_different_pixels_is_rejected(self):
        y,m=self._pair()
        self._alter_rows(m,lambda rows:rows[1].update(decoded_bgr_sha256='b'*64))
        with self.assertRaises(ValueError): compare_video_inputs(y,m,self.root/'compare')
        self.assertFalse((self.root/'compare').exists())

    def test_frame_sha_and_original_geometry_are_verified(self):
        y,m=self._pair()
        with (m.parent/'pose-frames.jsonl').open('a',encoding='utf-8') as stream: stream.write('{}\n')
        with self.assertRaises(ValueError): compare_video_inputs(y,m,self.root/'compare')
        value=read_json(m); value['pose_file_sha256']=file_hash(m.parent/'pose-frames.jsonl');write_json(m,value)
        with self.assertRaises(ValueError): compare_video_inputs(y,m,self.root/'compare')

    def test_missing_points_are_not_zero_disagreement(self):
        y,m=self._pair()
        self._alter_rows(m,lambda rows:[r.update(raw_pose=[],metrics={'knee_flexion_deg':dict(valid=False,value=None)}) for r in rows])
        report=read_json(compare_video_inputs(y,m,self.root/'compare')['path'])
        self.assertEqual(report['filtered_projected_angle_disagreement_deg']['knee_flexion_deg']['mediapipe_valid'],0)
        self.assertIsNone(report['point_disagreement_px']['left_knee']['mean_absolute_disagreement'])

    def test_source_action_side_and_training_scope_are_not_mixed(self):
        y,m=self._pair(); before=read_json(m)
        for field,value in [('video_sha256','b'*64),('side','right'),('exercise_id','sit_to_stand'),('training_authorized',True)]:
            changed=copy.deepcopy(before);changed[field]=value;write_json(m,changed)
            with self.subTest(field=field),self.assertRaises(ValueError): compare_video_inputs(y,m,self.root/'compare')
        write_json(m,before)

    def test_nonmonotonic_or_missing_pixel_identity_rejected(self):
        y,m=self._pair()
        self._alter_rows(m,lambda rows:rows[1].update(time_s=.1))
        with self.assertRaises(ValueError): compare_video_inputs(y,m,self.root/'compare')

    def test_real_video_native_smoke_is_blank_test_and_release_confirmed(self):
        import cv2
        import numpy as np
        video=self.root/'TEST-blank.avi'
        writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'MJPG'),10.,(64,64))
        self.assertTrue(writer.isOpened())
        try:
            for _ in range(4): writer.write(np.full((64,64,3),255,dtype=np.uint8))
        finally: writer.release()
        result=extract_mediapipe(video,'rehab_squat','left',analysis_consent=True,output_dir=self.root/'native')
        report=read_json(result['path'])
        self.assertEqual(result['frames'],4)
        self.assertEqual(result['observable_frames'],0)
        self.assertEqual(result['v2_completed'],0)
        self.assertTrue(result['owned_exit_confirmed'])
        self.assertFalse(report['training_authorized'])
        self.assertIsNone(report['clinical_accuracy'])
        self.assertEqual(report['model']['mode'],'VIDEO')


if __name__=='__main__': unittest.main()
