"""TEST therapist score parser; no real-human accuracy or network access."""
from copy import deepcopy
import unittest

from tools.rehab_ml.mobiphysio import HEADER, SUBHEADER, parse_scores, video_identity


def table():
    return [HEADER.copy(), SUBHEADER.copy(),
            ['E01_P01_AF_VFL_GM', 'TEST judge A', '1', '1', '0', '0.9', '1', '1', '0', '4.9', '70', '79.52380952', '79.52'],
            ['', 'TEST judge B', '1', '1', '0', '0.9', '1', '1', '1', '5.9', '84.28571429', '', ''],
            ['', 'TEST judge C', '1', '1', '0', '0.9', '1', '1', '1', '5.9', '84.28571429', '', '']]


class MobiPhysioScoresTests(unittest.TestCase):
    def test_three_rows_make_one_video_score_not_three_reps(self):
        groups, blanks = parse_scores(table())
        self.assertEqual(len(groups), 1)
        self.assertEqual(blanks, 0)
        self.assertEqual(groups[0]['status'], 'verified_video_score')
        self.assertEqual(groups[0]['published_average'], 79.52380952)
        self.assertEqual(groups[0]['judge_count'], 3)
        self.assertEqual(groups[0]['protocol_hint'], 'shoulder_abduction')
        self.assertIsNone(groups[0]['affected_side'])

    def test_view_is_not_body_side_and_e08_is_not_squat(self):
        left = video_identity('E01_P01_AL_VO_GF')
        self.assertEqual(left['camera_view'], 'left_view')
        self.assertIsNone(left['affected_side'])
        self.assertIsNone(video_identity('E08_P02_AF_VFL_GM')['protocol_hint'])

    def test_unknown_variation_is_quarantined_not_remapped(self):
        rows = table(); rows[2][0] = 'E03_P41_AF_VP_GM'
        group = parse_scores(rows)[0][0]
        self.assertEqual(group['status'], 'quarantined')
        self.assertIn('invalid_video_name', group['reasons'])
        with self.assertRaises(ValueError):
            video_identity('E01_P00_AF_VFL_GM')

    def test_header_width_or_orphan_continuation_refused(self):
        changed = table(); changed[0][9] = 'Assessment Score'
        short = table(); short[2].pop()
        orphan = table(); orphan[2][0] = ''
        for rows in (changed, short, orphan):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                parse_scores(rows)

    def test_missing_or_duplicate_judge_is_quarantined(self):
        for kind in ('missing', 'duplicate', 'empty'):
            rows = table()
            if kind == 'missing': rows.pop()
            elif kind == 'duplicate': rows[3][1] = rows[2][1]
            else: rows[3][1] = ''
            group = parse_scores(rows)[0][0]
            self.assertIn('three_distinct_judges_required', group['reasons'])

    def test_duplicate_video_groups_are_both_quarantined(self):
        rows = table(); rows += deepcopy(rows[2:])
        groups = parse_scores(rows)[0]
        self.assertEqual(len(groups), 2)
        self.assertTrue(all('duplicate_video_group' in group['reasons'] for group in groups))

    def test_nonfinite_missing_and_out_of_range_values_never_become_labels(self):
        for value in ('nan', 'inf', '', '-1', '2'):
            rows = table(); rows[2][2] = value
            group = parse_scores(rows)[0][0]
            self.assertEqual(group['status'], 'quarantined')

    def test_factor_sum_scaled_score_and_average_each_reconciled(self):
        for index, value, reason in (
            (9, '4.8', 'factor_sum_disagrees_with_total'),
            (10, '71', 'scaled_score_disagrees_with_total'),
            (11, '80', 'judge_mean_disagrees_with_published_average'),
            (12, '78', 'rounded_score_disagrees_with_average')):
            rows = table(); rows[2][index] = value
            group = parse_scores(rows)[0][0]
            self.assertIn(reason, group['reasons'])
            self.assertEqual(group['published_average'], float(rows[2][11]))

    def test_averages_on_continuation_not_silently_overwritten(self):
        rows = table(); rows[3][11] = '80'
        group = parse_scores(rows)[0][0]
        self.assertIn('unexpected_average_on_continuation', group['reasons'])

    def test_blank_rows_preserved_as_count_and_unknown_not_normal(self):
        rows = table(); rows.insert(3, ['']*13)
        groups, blanks = parse_scores(rows)
        self.assertEqual(blanks, 1)
        self.assertEqual(groups[0]['status'], 'verified_video_score')
        rows[2][0] = 'not_a_video'
        self.assertEqual(parse_scores(rows)[0][0]['status'], 'quarantined')


if __name__ == '__main__':
    unittest.main()
