import copy
from dataclasses import replace
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'rehab_codex_single_camera_v2_1'))
from app.rehab_v2.compatibility import comparable, comparison_contract
from app.rehab_v2.evidence import MetricEvidence
from tools.rehab_ml.cli import parser
from test_protocols import Replay


class ContractTests(unittest.TestCase):
    def test_cli_arguments_are_scoped_to_their_command(self):
        p = parser()
        self.assertEqual(p.parse_args(['evaluate', '--run-id', 'actual', '--split', 'test']).split, 'test')
        self.assertEqual(p.parse_args(['train-pose', '--config', 'config.yaml']).command, 'train-pose')
        self.assertEqual(p.parse_args(['extract-pose', '--video', 'video.mp4', '--exercise', 'rehab_squat',
                            '--side', 'left', '--analysis-consent', 'yes']).command, 'extract-pose')

    def test_inconsistent_evidence_age_is_unobservable(self):
        evidence = MetricEvidence(20., 'degree', True, None, 'observed', 1., 2., 0., ('left_knee',))
        self.assertFalse(evidence.observable(500.))

    def test_new_source_identity_is_not_a_comparability_break(self):
        replay = Replay()
        replay.cycle()
        item = dict(session_id='one', source_epoch='one', snapshot=copy.deepcopy(replay.engine.summary()),
            source=dict(source_kind='REPLAY_FILE', usage_context='TEST'), frozen_plan={'plan': replay.engine.plan})
        other = copy.deepcopy(item)
        other['session_id'], other['source_epoch'] = 'two', 'two'
        other['snapshot']['measurement_contract']['signature'] = ('another-video', *replay.engine.signature[1:])
        self.assertTrue(comparable(item, other)['comparable'])
        self.assertNotEqual(comparison_contract(item)['evidence_fingerprint'], comparison_contract(other)['evidence_fingerprint'])
        other['snapshot']['baseline']['raw_value'] = 5.
        self.assertTrue(comparable(item, other, measure='absolute_metric')['comparable'])
        self.assertFalse(comparable(item, other, measure='relative_excursion')['comparable'])
        other['snapshot']['protocol']['view'] = 'sagittal'
        self.assertFalse(comparable(item, other)['comparable'])

    def test_C07_uniform_scaling_and_mirror_preserve_anatomical_geometry(self):
        from app.domain import Context, PoseFrame, PosePerson
        from app.rehab_v2.evidence import EvidenceAdapter
        names = ('nose', 'left_eye', 'right_eye', 'left_ear', 'right_ear', 'left_shoulder',
                 'right_shoulder', 'left_elbow', 'right_elbow', 'left_wrist', 'right_wrist',
                 'left_hip', 'right_hip', 'left_knee', 'right_knee', 'left_ankle', 'right_ankle')
        xy = [[0, 0] for _ in names]
        conf = [0.] * len(names)
        for name, point in [('left_shoulder', [200., 100.]), ('left_elbow', [280., 240.]),
                             ('right_shoulder', [400., 100.]), ('right_elbow', [320., 240.])]:
            xy[names.index(name)], conf[names.index(name)] = point, .9
        def pose(points, size=(640, 480)):
            return PoseFrame(Context(1, 'rehab', 'TEST', 'SYNTHETIC', 'TEST'), 1, .1, size,
                [PosePerson('one', [50, 50, size[0]-50, size[1]-50], points, conf)], model_manifest_id='original')
        angle = EvidenceAdapter('shoulder_abduction', 'left').analyze(pose(xy)).metrics['raise_deg'].value
        mirrored = [[640-x, y] for x, y in xy]
        doubled = [[x*2, y*2] for x, y in xy]
        self.assertAlmostEqual(EvidenceAdapter('shoulder_abduction', 'left').analyze(pose(mirrored)).metrics['raise_deg'].value, angle)
        self.assertAlmostEqual(EvidenceAdapter('shoulder_abduction', 'left').analyze(pose(doubled, (1280, 960))).metrics['raise_deg'].value, angle)
        self.assertAlmostEqual(EvidenceAdapter('shoulder_abduction', 'right').analyze(pose(xy)).metrics['raise_deg'].value, angle)


if __name__ == '__main__':
    unittest.main()
