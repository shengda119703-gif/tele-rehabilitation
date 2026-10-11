"""TEST causal feature semantics and incomplete-download gate, no human error rate."""
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from tools.rehab_ml.mobiphysio_pose import frame_features, verified_download, presentation_timeline


def points():
    xy = np.full((17, 2), 55., dtype=float)
    xy[5], xy[6] = [50., 50.], [60., 50.]
    return xy, np.ones(17)


class MobiPhysioPoseTests(unittest.TestCase):
    def test_container_discard_flags_are_not_displayable_frames(self):
        rows = [dict(pts_s=t, corrupt=False, discard=discard) for t, discard in
                ((.2, False), (.0, False), (.3, True), (.1, False))]
        self.assertEqual(presentation_timeline(rows, 4), ([0., .1, .2], 1))

    def test_missing_packet_inventory_not_accepted_as_discard(self):
        row = dict(pts_s=0., corrupt=False, discard=False)
        with self.assertRaises(ValueError): presentation_timeline([row], 2)

    def test_corrupt_duplicate_or_nonfinite_presentation_is_refused(self):
        row = dict(pts_s=0., corrupt=False, discard=False)
        for rows in ([row, row], [dict(row, corrupt=True)], [dict(row, pts_s=float('nan'))]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                presentation_timeline(rows, len(rows))

    def test_no_displayable_frames_or_outside_duration_is_refused(self):
        row = dict(pts_s=0., corrupt=False, discard=True)
        for rows in ([], [row], [dict(row, pts_s=181., discard=False)]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                presentation_timeline(rows, len(rows))

    def test_features_are_69_current_values_with_masks_and_real_dt(self):
        features, mask, valid = frame_features(*points(), (100, 100), .3)
        self.assertEqual(features.shape, (69,))
        self.assertTrue(valid)
        self.assertTrue(mask.all())
        self.assertAlmostEqual(float(features[-1]), .3)
        self.assertEqual(features.dtype, np.float32)

    def test_uniform_pixel_scaling_keeps_body_normalized_features(self):
        xy, conf = points()
        one = frame_features(xy, conf, (100, 100), .25)[0]
        two = frame_features(xy*2, conf, (200, 200), .25)[0]
        np.testing.assert_array_equal(one, two)

    def test_weak_prediction_is_placeholder_plus_false_mask_not_ground_truth(self):
        xy, conf = points(); conf[9] = .2
        features, mask, valid = frame_features(xy, conf, (100, 100), .25)
        self.assertTrue(valid)
        self.assertFalse(mask[9])
        np.testing.assert_array_equal(features[18:20], [0., 0.])
        self.assertEqual(features[34+9], 0.)
        self.assertAlmostEqual(float(features[51+9]), .2)

    def test_missing_body_scale_invalidates_normalized_coordinates(self):
        xy, conf = points(); conf[5] = .1
        features, mask, valid = frame_features(xy, conf, (100, 100), .25)
        self.assertFalse(valid); self.assertFalse(mask.any())
        np.testing.assert_array_equal(features[:51], np.zeros(51))

    def test_unknown_nonfinite_or_outside_frame_never_becomes_usable(self):
        for value in ((np.nan, 20.), (-1., 20.), (100., 20.)):
            xy, conf = points(); xy[9] = value
            features, mask, _ = frame_features(xy, conf, (100, 100), .25)
            self.assertFalse(mask[9]); self.assertTrue(np.isfinite(features).all())

    def test_degenerate_shoulders_refused_as_body_scale(self):
        xy, conf = points(); xy[6] = xy[5]
        self.assertFalse(frame_features(xy, conf, (100, 100), .25)[2])

    def test_schema_or_bad_clock_is_not_nominally_repaired(self):
        xy, conf = points()
        for dt in (-1., np.nan, np.inf):
            with self.subTest(dt=dt), self.assertRaises(ValueError): frame_features(xy, conf, (100, 100), dt)
        with self.assertRaises(ValueError): frame_features(xy[:16], conf, (100, 100), .25)

    def test_future_frame_does_not_change_current_feature(self):
        xy, conf = points(); original = frame_features(xy, conf, (100, 100), .25)[0]
        future = xy.copy(); future[9] += 20
        frame_features(future, conf, (100, 100), .25)
        np.testing.assert_array_equal(original, frame_features(xy, conf, (100, 100), .25)[0])

    def test_partial_or_failed_receipt_cannot_start_the_experiment(self):
        for status in ('running', 'blocked_rgb_download'):
            value = dict(plan='E:/TEST/plan.json', schema_version='mobiphysio-rgb-download-1', status=status)
            with patch('tools.rehab_ml.mobiphysio_pose.read_json', return_value=value), \
                 patch('tools.rehab_ml.mobiphysio_pose.load_plan', return_value=(Path('E:/TEST/plan.json'), {})), \
                 self.assertRaises(ValueError):
                verified_download(Path('E:/TEST/download-12345678.json'))


if __name__ == '__main__':
    unittest.main()
