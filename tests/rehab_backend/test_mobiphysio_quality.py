"""TEST video-end metrics/fit and causal head; no real therapist-score result."""
import unittest

import numpy as np

from tools.rehab_ml.mobiphysio_quality import CONFIG, fit_ridge, metrics, predict_ridge, video_statistics


class MobiPhysioQualityTests(unittest.TestCase):
    def test_video_metrics_preserve_score_units_and_unclipped_predictions(self):
        result = metrics([80, 90], [82, 88])
        self.assertEqual(result['videos'], 2)
        self.assertEqual(result['mae'], 2.)
        self.assertEqual(result['rmse'], 2.)
        self.assertFalse(result['clipped_predictions'])
        self.assertGreater(metrics([80], [120])['mae'], 0.)

    def test_constant_reference_r2_is_null_not_perfect_accuracy(self):
        self.assertIsNone(metrics([80, 80], [80, 80])['r2'])

    def test_empty_nonfinite_or_unpaired_metrics_are_refused(self):
        for truth, pred in (([], []), ([1], []), ([1], [np.nan]), ([np.inf], [1])):
            with self.subTest(truth=truth), self.assertRaises(ValueError): metrics(truth, pred)

    def test_offline_coordinate_stats_ignore_masked_placeholder(self):
        data = np.ones((3, 69)); data[:, 0] = [2., 4., 99.]; data[2, 34] = 0.
        stats = video_statistics(data)
        self.assertEqual(stats.shape, (345,))
        self.assertEqual(stats[0], 3.)
        self.assertEqual(stats[1], 1.)

    def test_missing_coordinate_summary_is_explicit_zero_with_coverage_channel(self):
        data = np.ones((3, 69)); data[:, 34] = 0.; data[:, 0] = 99.
        stats = video_statistics(data)
        np.testing.assert_array_equal(stats[:5], np.zeros(5))
        self.assertEqual(stats[34*5], 0.)

    def test_ridge_uses_training_statistics_and_never_refits_for_test(self):
        x = np.asarray([[0., 1.], [1., 1.], [2., 1.]])
        state = fit_ridge(x, [70., 80., 90.])
        np.testing.assert_array_equal(state['mean'], [1., 1.])
        np.testing.assert_array_equal(state['std'][1:], [1.])
        frozen = state['mean'].copy()
        self.assertTrue(np.isfinite(predict_ridge(state, [[1000., 1.]])).all())
        np.testing.assert_array_equal(state['mean'], frozen)

    def test_frozen_config_has_only_whole_video_loss_and_no_product_activation(self):
        self.assertEqual(CONFIG['enabled_heads'], ['whole_video_eaaq'])
        self.assertEqual(CONFIG['prediction_point'], 'declared_video_end')
        self.assertFalse(CONFIG['product_enabled'])
        self.assertIn('phase', CONFIG['disabled_heads'])
        self.assertIn('prescription', CONFIG['disabled_heads'])

    def test_invalid_training_rows_or_regularizer_are_refused(self):
        for alpha in (True, -1, 0, float('nan')):
            with self.subTest(alpha=alpha), self.assertRaises(ValueError): fit_ridge([[1]], [80], alpha)
        with self.assertRaises(ValueError): fit_ridge([[np.nan]], [80])

    def test_regression_head_does_not_allow_future_input_into_prefix(self):
        import torch
        from torch import nn
        from tools.rehab_ml.models import CausalTCN
        torch.manual_seed(20261011)
        model = CausalTCN(69, channels=32, dropout=.1).eval()
        model.head = nn.Linear(32, 1)
        data = torch.randn(1, 80, 69)
        changed = data.clone(); changed[:, 40:] += 100
        with torch.inference_mode():
            before = model.encode(data)[:, :40]
            after = model.encode(changed)[:, :40]
        torch.testing.assert_close(before, after, rtol=0, atol=0)

    def test_padding_does_not_enter_video_end_score(self):
        import torch
        from torch import nn
        from tools.rehab_ml.models import CausalTCN
        torch.manual_seed(20261011)
        model = CausalTCN(69, channels=32, dropout=.1).eval()
        model.head = nn.Linear(32, 1)
        data = torch.randn(1, 40, 69)
        padded = torch.cat((data, torch.randn(1, 20, 69)*100), dim=1)
        mask = torch.ones(1, 40, dtype=torch.bool)
        longer = torch.cat((mask, torch.zeros(1, 20, dtype=torch.bool)), dim=1)
        with torch.inference_mode():
            torch.testing.assert_close(model(data, mask), model(padded, longer), rtol=1e-6, atol=1e-6)


if __name__ == '__main__':
    unittest.main()
