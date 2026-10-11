"""Saved-evidence consistency TEST fixtures, never RGB inference or human GT."""
from dataclasses import asdict
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools.rehab_ml.common import ROOT, canonical_hash, file_hash, write_json
from tools.rehab_ml.temporal_replay import event_inventory
from tools.rehab_ml.verify_temporal_replay import audit_replay
from tools.rehab_ml.temporal_evaluation import PREDICTION_SCHEMA
sys.path.insert(0, str(ROOT/'rehab_codex_single_camera_v2_1'))
from app.domain import Context, PoseFrame, clean_json
from app.rehab_v2.engine import ProtocolEngine
from app.rehab_v2.evidence import EvidenceAdapter


class TemporalReplayAuditTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.source = dict(sample_id='TEST-1', video_sha256='a'*64, exercise_id='shoulder_abduction',
            protocol_version='rehab-protocol-2.0', split='test', time_basis='stream_relative_media_pts',
            timeline_ref='TEST-pts.json', duration_s=.5)
        write_json(self.root/'TEST-pts.json', dict(presentation_s=[0., .25, .5]))
        config = dict(plan=dict(exercise_id='shoulder_abduction', side='left'), analyzed_side='left', sampling_period_s=.25)
        write_json(self.root/'config.json', config)
        context = Context(1, 'rehab', 'a'*64, 'REPLAY_FILE', 'TEST', 'TEST-run', epoch='TEST-epoch')
        engine, adapter = ProtocolEngine(config['plan'], source_epoch=context.epoch, session_id='TEST-1'), EvidenceAdapter('shoulder_abduction')
        self.lines = []
        for seq, stamp in enumerate([0., .25, .5], 1):
            pose = PoseFrame(context, seq, stamp, (640, 480), [], model_manifest_id='b'*64)
            evidence = adapter.analyze(pose, processing_age_ms=0., time_basis='mapped_source_seconds')
            old = engine.phase
            engine.process(evidence)
            self.lines.append(clean_json(dict(seq=seq, time_s=stamp, pose=asdict(pose), metrics=asdict(evidence),
                phase_before=old, phase_after=engine.phase, completed=0, emitted_events=[])))
        self.write_trace()
        engine.finish('offline_original_video_ended')
        write_json(self.root/'TEST-result.json', clean_json(engine.summary()))
        row = {**{key: self.source[key] for key in ('sample_id', 'video_sha256', 'exercise_id',
            'protocol_version', 'split', 'time_basis')}, 'side': 'left', 'status': 'completed',
            'completed_count': 0, 'boundary_events': event_inventory()}
        self.manifest = dict(schema_version=PREDICTION_SCHEMA, origin='declared_backend_export',
            reference_used_for_predictions=False, implementation_sha256=canonical_hash({}),
            model_sha256='b'*64, config_sha256=canonical_hash(config), samples=[row])
        write_json(self.root/'predictions.json', self.manifest)
        self.summary = dict(status='completed', owned_release=dict(confirmed=True), implementation={},
            config_sha256=canonical_hash(config), model_sha256='b'*64,
            predictions=str(self.root/'predictions.json'), predictions_sha256=file_hash(self.root/'predictions.json'),
            samples=[dict(sample_id='TEST-1', trace=str(self.root/'TEST-trace.jsonl'),
                trace_sha256=file_hash(self.root/'TEST-trace.jsonl'), result=str(self.root/'TEST-result.json'),
                result_sha256=file_hash(self.root/'TEST-result.json'), sampled_frames=3)])
        self.persist()

    def write_trace(self):
        (self.root/'TEST-trace.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in self.lines), encoding='utf-8')

    def persist(self):
        self.summary['samples'][0]['trace_sha256'] = file_hash(self.root/'TEST-trace.jsonl')
        self.summary['predictions_sha256'] = file_hash(self.root/'predictions.json')
        write_json(self.root/'summary.json', self.summary)

    def audit(self):
        with patch('tools.rehab_ml.verify_temporal_replay._bundle', return_value=(self.root/'TEST-bundle.json', dict(samples=[self.source]))), \
             patch('tools.rehab_ml.verify_temporal_replay.source_fingerprints', return_value={}):
            return audit_replay(self.root/'summary.json', self.root/'TEST-bundle.json', 'test')

    def test_current_saved_evidence_can_replay(self):
        self.assertTrue(self.audit()['saved_evidence_consistent'])

    def test_changed_trace_hash_rejected(self):
        self.lines[0]['completed'] = 1
        self.write_trace()
        with self.assertRaisesRegex(ValueError, 'trace_changed'):
            self.audit()

    def test_rehashed_false_count_still_fails_actual_protocol(self):
        self.lines[0]['completed'] = 1
        self.write_trace()
        self.persist()
        with self.assertRaisesRegex(ValueError, 'does_not_replay'):
            self.audit()

    def test_rehashed_metrics_cannot_replace_actual_adapter(self):
        self.lines[0]['metrics']['observation_status'] = 'observable'
        self.write_trace()
        self.persist()
        with self.assertRaisesRegex(ValueError, 'adapter_evidence'):
            self.audit()

    def test_missing_sample_does_not_silently_lower_denominator(self):
        self.lines.pop(1)
        self.write_trace()
        self.persist()
        with self.assertRaisesRegex(ValueError, 'sampled_trace_prefix'):
            self.audit()

    def test_rehashed_wrong_original_pose_model_is_rejected(self):
        self.lines[0]['pose']['model_manifest_id'] = 'c'*64
        self.write_trace()
        self.persist()
        with self.assertRaisesRegex(ValueError, 'source_identity'):
            self.audit()

    def test_rehashed_prediction_cannot_override_actual_zero_count(self):
        self.manifest['samples'][0]['completed_count'] = 1
        write_json(self.root/'predictions.json', self.manifest)
        self.persist()
        with self.assertRaisesRegex(ValueError, 'actual_protocol_trace'):
            self.audit()

    def test_unconfirmed_release_or_failed_execution_is_not_pass(self):
        self.summary['owned_release']['confirmed'] = False
        self.persist()
        with self.assertRaisesRegex(ValueError, 'release_contract'):
            self.audit()

    def test_changed_source_snapshot_cannot_be_rehashed_as_current(self):
        self.summary['implementation'] = {'TEST-old-source': 'c'*64}
        self.persist()
        with self.assertRaisesRegex(ValueError, 'source_config_model'):
            self.audit()


if __name__ == '__main__':
    unittest.main()
