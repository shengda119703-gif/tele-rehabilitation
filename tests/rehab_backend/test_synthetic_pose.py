"""Small CPU media/mapping checks; no model inference, network, or human labels."""
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import av
import numpy as np

from tools.rehab_ml.common import canonical_hash, file_hash
from tools.rehab_ml.synthetic import pose, video


def clip(path, pts=None):
    points = list(range(9)) if pts is None else pts
    with av.open(str(path), 'w') as container:
        stream = container.add_stream('libx264', rate=30)
        stream.width, stream.height, stream.pix_fmt = 64, 64, 'yuv420p'
        stream.options = {'crf':'18', 'preset':'ultrafast'}
        for index, stamp in enumerate(points):
            image = np.zeros((64, 64, 3), dtype=np.uint8)
            image[:, :, 0] = 30 + index * 10
            image[:, index:index+8, 1] = 220
            frame = av.VideoFrame.from_ndarray(image, format='rgb24')
            frame.pts = stamp
            frame.time_base = Fraction(1, 30)
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    return path


class SyntheticVideoTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='synthetic-pose-TEST-')
        self.root = Path(self.temporary.name)
        self.source = clip(self.root/'source.mp4')

    def tearDown(self):
        self.temporary.cleanup()

    def test_full_real_pts_and_pixel_fingerprints(self):
        timeline = video.probe_video(self.source, timeline_path=self.root/'timeline.json')
        self.assertEqual(timeline['frame_count'], 9)
        self.assertEqual(timeline['presentation_s'], [i/30 for i in range(9)])
        self.assertEqual(timeline['video_sha256'], file_hash(self.source))
        self.assertEqual(timeline['width'], 64)
        self.assertEqual(timeline['height'], 64)
        self.assertTrue(timeline['provenance']['full_decode_verified'])
        self.assertEqual(timeline['timeline_sha256'], file_hash(self.root/'timeline.json'))
        self.assertEqual(len({f['decoded_rgb_sha256'] for f in timeline['frames']}), 9)
        with self.assertRaises(FileExistsError):
            video.probe_video(self.source, timeline_path=self.root/'timeline.json')

    def test_shared_selection_has_unique_real_frames_and_exact_pixels(self):
        manifest = video.create_frame_manifest(self.source, self.root/'frames.json', sampling_hz=15.)
        self.assertEqual([f['frame_index'] for f in manifest['frames']], [0,2,4,6,8])
        self.assertFalse(manifest['interpolation'])
        self.assertFalse(manifest['nominal_fps_used'])
        self.assertEqual(video.validate_frame_manifest(self.root/'frames.json', verify_decode=True), manifest)
        rows = list(video.iter_selected_rgb(self.source, manifest))
        self.assertEqual(len(rows), 5)
        for row, rgb in rows:
            self.assertEqual(row['decoded_rgb_sha256'], hashlib.sha256(rgb.tobytes()).hexdigest())
            self.assertEqual(list(rgb.shape), [64,64,3])

    def test_vfr_samples_arrived_frames_without_future_or_nominal_repair(self):
        source = clip(self.root/'vfr.mp4', [3,4,6,7,8,10])
        timeline = video.probe_video(source)
        self.assertAlmostEqual(timeline['provenance']['stream_start_time_s'], .1)
        self.assertEqual(timeline['presentation_s'], [0,1/30,3/30,4/30,5/30,7/30])
        manifest = video.create_frame_manifest(source, sampling_hz=15., probe=timeline)
        self.assertEqual([f['frame_index'] for f in manifest['frames']], [0,1,3,4])
        for frame in manifest['frames']:
            self.assertLessEqual(frame['timestamp_s'], frame['sample_grid_time_s'] + 1e-10)
            self.assertGreaterEqual(frame['sample_age_s'], 0)
        self.assertGreater(manifest['frames'][1]['sample_age_s'], .03)

    def test_changed_source_is_rejected_before_reuse(self):
        manifest = video.create_frame_manifest(self.source)
        self.source.write_bytes(self.source.read_bytes() + b'changed')
        with self.assertRaisesRegex(ValueError, 'source_sha256'):
            video.validate_frame_manifest(manifest)

    def test_forged_pts_or_pixel_fingerprints_are_rejected(self):
        manifest = video.create_frame_manifest(self.source)
        wrong_pts = deepcopy(manifest)
        wrong_pts['frames'][1]['timestamp_s'] += .01
        with self.assertRaisesRegex(ValueError, 'real_frame_pts'):
            video.validate_frame_manifest(wrong_pts)
        wrong_pixel = deepcopy(manifest)
        wrong_pixel['frames'][1]['decoded_rgb_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'actual_decode'):
            video.validate_frame_manifest(wrong_pixel, verify_decode=True)
        with self.assertRaisesRegex(ValueError, 'pixel_fingerprint'):
            list(video.iter_selected_rgb(self.source, wrong_pixel))

    def test_decoder_version_provenance_is_separate_from_all_media_semantics(self):
        actual_probe = video.probe_video(self.source)
        producer_probe = deepcopy(actual_probe)
        producer_probe['provenance']['decoder_version'] = 'TEST-another-decoder-version'
        actual = video.create_frame_manifest(self.source, probe=actual_probe)
        producer = video.create_frame_manifest(self.source, probe=producer_probe)
        self.assertNotEqual(actual['full_timeline_sha256'], producer['full_timeline_sha256'])
        self.assertEqual(actual['semantic_timeline_sha256'], producer['semantic_timeline_sha256'])
        self.assertEqual(producer['full_timeline_sha256'], canonical_hash(producer_probe))
        self.assertEqual(video.validate_frame_manifest(producer, verify_decode=True), producer)
        forged = deepcopy(producer)
        forged['timeline_provenance']['stream_start_pts'] = 1
        with self.assertRaisesRegex(ValueError, 'provenance_media_facts'):
            video.validate_frame_manifest(forged, verify_decode=True)
        forged = deepcopy(producer)
        forged['semantic_timeline_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'actual_decode'):
            video.validate_frame_manifest(forged, verify_decode=True)

    def test_shared_jpeg_pixels_are_identical_and_unscaled(self):
        row, rgb = next(video.iter_selected_rgb(self.source, video.create_frame_manifest(self.source)))
        one, first = pose._jpeg_input(rgb)
        two, second = pose._jpeg_input(rgb)
        self.assertEqual(one, two)
        self.assertEqual(first, second)
        self.assertEqual(first['jpeg_sha256'], hashlib.sha256(one).hexdigest())
        self.assertNotEqual(row['decoded_rgb_sha256'], first['inference_rgb_sha256'])


class SyntheticPoseMappingTests(unittest.TestCase):
    def setUp(self):
        self.base = dict(frame_index=2, pts=2048, time_base=[1,30720], timestamp_s=2/30,
                         decoded_rgb_sha256='a'*64, sample_grid_time_s=2/30, sample_age_s=0.)

    def test_yolo_names_zero_mask_and_confidence_semantics(self):
        person = SimpleNamespace(track_key='TEST:7', bbox=[1,2,60,62],
            xy=[[10.,20.]]*16+[[0.,0.]], conf=[.9]*16+[.2])
        row = pose._yolo_frame(SimpleNamespace(people=[person]), self.base, 2.)
        self.assertEqual(len(row['joints']), 17)
        self.assertEqual(row['track_id'], 'TEST:7')
        self.assertEqual(row['joints']['left_shoulder']['x'], 10.)
        self.assertIsNone(row['joints']['right_ankle']['x'])
        self.assertIsNone(row['joints']['right_ankle']['y'])
        self.assertEqual(row['joints']['right_ankle']['confidence'], .2)
        self.assertIsNone(row['joints']['right_ankle']['visibility'])
        self.assertIsNone(row['joints']['right_ankle']['presence'])

    def test_missing_or_ambiguous_person_does_not_fabricate_joints(self):
        person = SimpleNamespace(track_key=None, bbox=[0,0,64,64], xy=[[10.,20.]]*17, conf=[.9]*17)
        for people, reason in [([], 'no_person'), ([person,person], 'multiple_people')]:
            row = pose._yolo_frame(SimpleNamespace(people=people), self.base, 2.)
            self.assertFalse(row['pose_detected'])
            self.assertEqual(row['joints'], {})
            self.assertIsNone(row['track_id'])
            self.assertEqual(row['missing_reason'], reason)
            self.assertEqual(len(row['people']), len(people))

    def test_mediapipe_preserves_33_names_presence_visibility_and_pixels(self):
        landmarks = [SimpleNamespace(x=.25,y=.5,z=.01,visibility=.8,presence=.7) for _ in range(33)]
        detected = SimpleNamespace(pose_landmarks=[landmarks])
        row, previous = pose._mediapipe_frame(detected, self.base, SimpleNamespace(), None,
            pose.MODEL_HASHES['mediapipe33'], [640,384], 3.)
        self.assertEqual(len(row['joints']), 33)
        joint = row['joints']['left_foot_index']
        self.assertEqual(joint['x'], 160.)
        self.assertEqual(joint['y'], 192.)
        self.assertEqual(joint['visibility'], .8)
        self.assertEqual(joint['presence'], .7)
        self.assertEqual(joint['confidence'], .7)
        self.assertIsNotNone(previous)
        missing, previous = pose._mediapipe_frame(SimpleNamespace(pose_landmarks=[]), self.base,
            SimpleNamespace(), previous, pose.MODEL_HASHES['mediapipe33'], [640,384], 3.)
        self.assertFalse(missing['pose_detected'])
        self.assertEqual(missing['joints'], {})
        self.assertIsNone(previous)


class SyntheticPoseExtractionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='synthetic-extract-TEST-')
        self.root = Path(self.temporary.name)
        self.source = clip(self.root/'source.mp4')
        self.manifest = video.create_frame_manifest(self.source)

    def tearDown(self):
        self.temporary.cleanup()

    def test_no_detection_is_a_complete_prediction_not_zero_joints_or_reference(self):
        model_path = self.root/'TEST-model.bin'
        model_path.write_bytes(b'TEST no inference')
        fingerprint = file_hash(model_path)
        model = dict(path=str(model_path),sha256=fingerprint,device='cpu')
        rows = [pose._missing(row, 'no_person') for row in self.manifest['frames']]
        with patch.dict(pose.MODEL_HASHES, yolo17=fingerprint), \
             patch.object(pose, '_model_contract', return_value=model), \
             patch.object(pose, '_yolo_predictions', return_value=(rows, {'TEST':True})):
            result = pose.extract_pose(self.source, self.manifest, self.root/'output',
                                       sample_id='TEST-synthetic', backend='yolo17')
            self.assertEqual(result['status'], 'completed')
            self.assertEqual(result['detected_frames'], 0)
            self.assertEqual(len(result['frames']), 5)
            self.assertFalse(result['is_ground_truth'])
            pose.validate_pose(result, frame_manifest=self.manifest)
            changed = deepcopy(result)
            changed['frames'][1]['decoded_rgb_sha256'] = 'f'*64
            with self.assertRaisesRegex(ValueError, 'pixel_binding'):
                pose.validate_pose(changed, frame_manifest=self.manifest)
            with self.assertRaises(FileExistsError):
                pose.extract_pose(self.source, self.manifest, self.root/'output', sample_id='TEST-synthetic')

    def test_backend_failure_is_preserved_and_never_success(self):
        with patch.object(pose, '_model_contract', return_value={'sha256':pose.MODEL_HASHES['yolo17']}), \
             patch.object(pose, '_yolo_predictions', side_effect=TimeoutError('TEST timeout')):
            result = pose.extract_pose(self.source, self.manifest, self.root/'failed', sample_id='TEST-failed')
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['failure_type'], 'TimeoutError')
        self.assertEqual(len(result['frames']), 5)
        self.assertTrue(all(not row['pose_detected'] and row['joints'] == {} for row in result['frames']))
        saved = json.loads(Path(result['result_path']).read_text(encoding='utf-8'))
        self.assertEqual(saved['status'], 'failed')

    def test_source_or_frame_tampering_is_rejected_before_worker(self):
        changed = deepcopy(self.manifest)
        changed['frames'][0]['decoded_rgb_sha256'] = '0'*64
        with patch.object(pose, '_yolo_predictions') as worker, self.assertRaises(ValueError):
            pose.extract_pose(self.source, changed, self.root/'must-not-exist', sample_id='TEST-forged')
        worker.assert_not_called()
        self.assertFalse((self.root/'must-not-exist').exists())


if __name__ == '__main__':
    unittest.main()
