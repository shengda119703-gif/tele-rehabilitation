"""Synthetic mathematical fixtures; no participant or generated video data."""
import importlib.util
from pathlib import Path
import unittest

import numpy as np

spec = importlib.util.spec_from_file_location("review_builder", Path(__file__).with_name("build.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class MetricsTests(unittest.TestCase):
    def test_finite_does_not_accept_bool_or_nan(self):
        for v in (None, True, False, float("nan"), float("inf"), "1"):
            self.assertFalse(m.finite(v))
        self.assertTrue(m.finite(-1.2))

    def test_angles_and_aspect_ratio(self):
        self.assertAlmostEqual(m.angle(np.array([0, 1]), np.array([0, 0]), np.array([1, 0])), 90)
        self.assertAlmostEqual(m.angle(np.array([0, -1]), np.array([0, 0]), np.array([0, 1])), 180)
        self.assertIsNone(m.angle(None, np.array([0, 0]), np.array([1, 0])))
        self.assertIsNone(m.angle(np.zeros(2), np.zeros(2), np.ones(2)))
        self.assertEqual(m.pixel({"a": [.5, .5]}, "a").tolist(), [640, 360])

    def test_smoothing_is_causal_and_gap_aware(self):
        rows = [{"v": 1}, {"v": 3}, {"v": None}, {"v": 100}, {"v": 200}]
        times = [0, .1, .2, .3, 1.2]
        self.assertEqual(m.smooth(rows, times, 1, "v"), 2)
        self.assertIsNone(m.smooth(rows, times, 2, "v"))
        self.assertEqual(m.smooth(rows, times, 3, "v"), 100)
        self.assertEqual(m.smooth(rows, times, 4, "v"), 200)

    def test_residual_preserves_missing(self):
        rows = [{"v": i * i} for i in range(6)]
        times = [i * .1 for i in range(6)]
        self.assertLess(m.local_residual(rows, times, 5, "v"), 1e-10)
        rows[3]["v"] = None
        self.assertIsNone(m.local_residual(rows, times, 5, "v"))

    @staticmethod
    def series(speeds, times=None):
        height = 0
        rows = []
        for i, speed in enumerate(speeds):
            height += speed * .1 if m.finite(speed) else 0
            rows.append(dict(t=times[i] if times else i * .1, velocity_m_s=speed, height_m=height))
        return rows

    def test_moving_interval_needs_observed_boundaries(self):
        rows = self.series([0] + [.5] * 5 + [0])
        seg = m.motion_segments(rows)
        self.assertEqual(len(seg), 1)
        self.assertTrue(seg[0]["bounded"])
        self.assertAlmostEqual(seg[0]["duration_s"], .4)
        self.assertFalse(m.motion_segments(self.series([None] + [.5] * 5 + [0]))[0]["bounded"])
        self.assertFalse(m.motion_segments(self.series([0] + [.5] * 5))[0]["bounded"])

    def test_small_travel_not_a_segment(self):
        self.assertEqual(m.motion_segments(self.series([0] + [.04] * 5 + [0])), [])

    def test_gap_breaks_interval(self):
        rows = self.series([0] + [.5] * 6 + [0], [0, .1, .2, .3, 2, 2.1, 2.2, 2.3])
        self.assertEqual(m.motion_segments(rows), [])

    def test_phase_values_remain_unknown_for_static_or_partial(self):
        rows = self.series([0] * 10)
        result, _ = m.phase_metrics(rows, [{"left_knee": 90, "right_knee": 90}] * 10, [r["t"] for r in rows])
        self.assertTrue(all(value is None for value in result.values()))

    def test_knee_alignment_is_zero_on_straight_vertical_legs(self):
        p = {}
        for side, x in (("left", .3), ("right", .7)):
            p.update({side + "_hip": [x, .3], side + "_knee": [x, .6], side + "_ankle": [x, .9], side + "_heel": [x, .9], side + "_foot_index": [x, .9]})
        values = m.knee_alignment(p, .003)
        self.assertTrue(all(v == 0 for v in values.values()))
        p["left_knee"][0] += .03
        inward = m.knee_alignment(p, .003)["left_inward"]
        self.assertGreater(inward, 0)
        self.assertTrue(m.finite(inward))
        self.assertEqual(m.knee_alignment({}, .003), {})


if __name__ == "__main__":
    unittest.main()
