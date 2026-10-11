"""TEST saved-metric reconciliation, not actual therapist accuracy."""
import unittest

from tools.rehab_ml.verify_mobiphysio import check_metrics


def recorded():
    return dict(videos=2, mae=2., rmse=2., r2=.84,
                score_units='EAAQ points on 0–100 scale', clipped_predictions=False)


class MobiPhysioEvidenceTests(unittest.TestCase):
    def test_saved_values_reconcile_with_paired_video_labels(self):
        result = check_metrics([80, 90], [82, 88], recorded())
        self.assertEqual(result['videos'], 2)
        self.assertEqual(result['mae'], 2.)

    def test_wrong_denominator_or_residual_metric_is_refused(self):
        for change in (dict(videos=3), dict(mae=1), dict(rmse=3), dict(r2=.99)):
            with self.subTest(change=change), self.assertRaises(ValueError):
                check_metrics([80, 90], [82, 88], dict(recorded(), **change))

    def test_undefined_r2_is_null_not_claimed_as_one(self):
        value = dict(recorded(), mae=0., rmse=0., r2=None)
        self.assertIsNone(check_metrics([80, 80], [80, 80], value)['r2'])
        with self.assertRaises(ValueError): check_metrics([80, 80], [80, 80], dict(value, r2=1))

    def test_units_clipping_or_boolean_number_changes_are_refused(self):
        for change in (dict(score_units='percent_accuracy'), dict(clipped_predictions=True), dict(videos=True)):
            with self.subTest(change=change), self.assertRaises(ValueError):
                check_metrics([80, 90], [82, 88], dict(recorded(), **change))

    def test_empty_nonfinite_or_wrong_shape_is_refused(self):
        for y, p in (([], []), ([1], []), ([1], [float('nan')]), ([[1]], [[1]])):
            with self.subTest(y=y), self.assertRaises(ValueError): check_metrics(y, p, recorded())

    def test_over_range_prediction_is_not_silently_clipped(self):
        result = check_metrics([80], [120], dict(recorded(), videos=1, mae=40., rmse=40., r2=None))
        self.assertEqual(result['mae'], 40.)


if __name__ == '__main__':
    unittest.main()
