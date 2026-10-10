"""Deterministic clock/evidence checks, not clinical timing accuracy."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'rehab_codex_single_camera_v2_1'))
sys.path.insert(0, str(ROOT))
from app.rehab_v2.cues import CueEvents
from app.rehab_v2.engine import ProtocolEngine
from app.rehab_v2.rounds import TrainingRounds
from app.rehab_v2.sessions import SessionError
from mobile_rehab.rehab_v2.service import SessionService
from tools.rehab_ml.common import paths
from test_protocols import Replay
from test_sessions import request


def shoulder_cycle(replay):
    replay.feed(0., 30)
    for value in (10., 20., 30., 40., 50., 60.):
        replay.feed(value, 3)
    replay.feed(70., 24)
    for value in (60., 50., 40., 30., 20., 10., 0.):
        replay.feed(value, 3)
    replay.feed(0., 8)


class TimingTests(unittest.TestCase):
    def test_explicit_plan_validation_and_legacy_lowering_alias(self):
        engine = ProtocolEngine(dict(exercise_id='sit_to_stand', lowering_tempo_min_s=2.), source_epoch='epoch')
        self.assertEqual(engine.plan['timing_plan']['return_min_s'], 2.)
        invalid = [dict(hold_min_s=1.), dict(outbound_min_s=3., outbound_max_s=2.),
                   dict(return_min_s=True), dict(hold_min_s=float('nan')), dict(unrecognized=1.)]
        for timing in invalid:
            with self.subTest(timing=timing), self.assertRaises(ValueError):
                ProtocolEngine(dict(exercise_id='shoulder_abduction', timing_plan=timing), source_epoch='epoch')
        with self.assertRaises(ValueError):
            ProtocolEngine(dict(exercise_id='sit_to_stand', lowering_tempo_min_s=2.,
                                timing_plan=dict(return_min_s=1.)), source_epoch='epoch')

    def test_complete_cycle_phase_times_and_goal_failure_never_change_count(self):
        replay = Replay(target_angle_deg=60., timing_plan=dict(outbound_min_s=20., return_max_s=.01, hold_min_s=20.))
        shoulder_cycle(replay)
        self.assertEqual(replay.engine.completed, 1)
        rep = replay.engine.repetitions[0]
        timing = rep['movement_timing']
        self.assertEqual(rep['target_status'], 'MET')
        self.assertEqual(timing['goals'], {'outbound': 'NOT_MET', 'return': 'NOT_MET', 'hold': 'NOT_MET'})
        self.assertEqual(timing['version'], 'rehab-observed-timing-2')
        self.assertEqual(timing['algorithm_version'], 'observed-timing-1')
        self.assertEqual(timing['time_basis'], replay.frame.time_basis)
        self.assertEqual(timing['phase_timing_mode'], 'after_observed_cycle')
        self.assertTrue(timing['cycle_complete'])
        self.assertFalse(timing['count_gate'])
        self.assertLess(timing['evidence_refs']['first']['seq'], timing['evidence_refs']['latest']['seq'])
        for key in ('outbound_s', 'endpoint_dwell_s', 'return_s', 'target_hold_s'):
            self.assertTrue(timing[key]['valid'], timing)
            self.assertGreater(timing[key]['value'], 0.)
        json.dumps(replay.engine.summary(), allow_nan=False)

    def test_live_hold_is_causal_and_requires_reached_target(self):
        replay = Replay(target_angle_deg=60., timing_plan=dict(hold_min_s=1.))
        replay.feed(0., 30)
        replay.feed(30., 10)
        cues = CueEvents('session')
        self.assertEqual(cues.update(replay.engine, replay.frame, emission_monotonic=10.)['cue_key'], 'move')
        replay.feed(70., 8)
        self.assertEqual(cues.update(replay.engine, replay.frame, emission_monotonic=11.)['cue_key'], 'hold')
        captured = deepcopy(replay.engine.summary())
        self.assertFalse(captured['current']['movement_timing']['outbound_s']['valid'])
        self.assertAlmostEqual(captured['movement_timing_live']['hold_elapsed_s'], .35)
        replay.feed(70., 24)
        self.assertEqual(cues.update(replay.engine, replay.frame, emission_monotonic=12.)['cue_key'], 'return')
        self.assertAlmostEqual(captured['movement_timing_live']['hold_elapsed_s'], .35)
        self.assertEqual(replay.engine.completed, 0)  # Hold alone is not a repetition.

    def test_short_missing_gap_restarts_hold_but_keeps_observed_cycle(self):
        replay = Replay(target_angle_deg=60., timing_plan=dict(hold_min_s=.7))
        replay.feed(0., 30)
        replay.feed(70., 10)
        replay.feed(None, 2, valid=False)
        self.assertIsNone(replay.engine.summary()['movement_timing_live'])
        replay.feed(70., 10)
        self.assertAlmostEqual(replay.engine.timing_live()['hold_elapsed_s'], .45)
        replay.feed(0., 10)
        self.assertEqual(replay.engine.completed, 1)
        timing = replay.engine.repetitions[0]['movement_timing']
        # Ten observations are nine source-clock intervals, not ten periods.
        self.assertAlmostEqual(timing['target_hold_s']['value'], .45)
        self.assertEqual(timing['goals']['hold'], 'UNASSESSABLE')
        self.assertIsNone(timing['outbound_s']['value'])
        self.assertEqual(timing['outbound_s']['reason'], 'missing_interval')

    def test_stale_predicted_or_wrong_contract_do_not_hold(self):
        for invalid in ('predicted', 'stale', 'contract'):
            with self.subTest(invalid=invalid):
                replay = Replay(target_angle_deg=60., timing_plan=dict(hold_min_s=.7))
                replay.feed(0., 30)
                replay.feed(70., 8)
                if invalid == 'contract':
                    frame = replace(replay.frame, seq=replay.seq+1, time_s=replay.t+.05,
                                    metrics={replay.engine.spec['metric']: replace(
                                        replay.frame.metrics[replay.engine.spec['metric']], unit='metre')})
                    replay.engine.process(frame)
                else:
                    replay.feed(70., 2, kind='predicted' if invalid == 'predicted' else 'observed',
                                age=900. if invalid == 'stale' else 0.)
                self.assertIsNone(replay.engine.timing_live())
                replay.feed(70., 8)
                self.assertLess(replay.engine.timing_live()['hold_elapsed_s'], .7)

    def test_replaced_latest_frame_breaks_at_its_prefix_not_earlier_inflight(self):
        replay = Replay(target_angle_deg=60., timing_plan=dict(hold_min_s=.7))
        replay.feed(0., 30)
        replay.feed(70., 8)
        pending_seq = replay.seq+2
        replay.engine.note_input_gap(pending_seq, replay.t+.1, 'latest_frame_replaced')
        before = deepcopy(replay.engine.current['movement_timing'])
        self.assertIsNone(replay.engine.timing_live())
        replay.feed(70., 1)  # Earlier in-flight frame is valid, no future gap yet.
        self.assertEqual(replay.engine.timing.gaps, [])
        self.assertGreater(replay.engine.current['movement_timing']['target_hold_s']['value'],
                           before['target_hold_s']['value'])
        replay.seq += 1
        replay.t += .05
        replay.feed(70., 1)  # First surviving frame beyond the missing prefix.
        self.assertEqual(replay.engine.timing_live()['hold_elapsed_s'], 0.)
        self.assertTrue(replay.engine.current['movement_timing']['partial_observation'])
        replay.feed(0., 10)
        self.assertEqual(replay.engine.completed, 1)  # Turn was observed after restoration.
        self.assertEqual(replay.engine.repetitions[0]['movement_timing']['outbound_s']['reason'], 'latest_frame_replaced')
        hidden = Replay(target_angle_deg=60., timing_plan=dict(hold_min_s=.7))
        hidden.feed(0., 30)
        hidden.feed(70., 8)
        hidden.engine.note_input_gap(hidden.seq+1, hidden.t+.05, 'latest_frame_replaced')
        hidden.seq += 1
        hidden.t += .05
        hidden.feed(0., 10)
        self.assertEqual(hidden.engine.completed, 0)  # Here the turn was inside the gap.

    def test_pause_and_long_gap_cannot_carry_hold_or_return(self):
        for boundary in ('pause', 'gap', 'person', 'size'):
            with self.subTest(boundary=boundary):
                replay = Replay(target_angle_deg=60., timing_plan=dict(hold_min_s=.7))
                replay.feed(0., 30)
                replay.feed(70., 8)
                if boundary == 'pause':
                    replay.engine.pause()
                    replay.t += 10.
                    self.assertIsNone(replay.engine.timing_live())
                    replay.engine.resume()
                elif boundary == 'gap':
                    replay.t += 10.
                    replay.feed(70., 1)
                elif boundary == 'person':
                    replay.feed(70., 1, track='other')
                else:
                    replay.engine.process(replace(replay.frame, seq=replay.seq+1, time_s=replay.t+.05, size=(640, 360)))
                self.assertEqual(replay.engine.completed, 0)
                self.assertIsNone(replay.engine.timing_live())
                self.assertEqual(replay.engine.repetitions[-1]['completion_status'], 'UNASSESSABLE')
                self.assertLess(replay.engine.repetitions[-1]['movement_timing']['target_hold_s']['value'], .7)

    def test_standing_finish_preserves_count_without_inventing_return(self):
        replay = Replay('sit_to_stand', timing_plan=dict(hold_min_s=1., return_min_s=1.))
        replay.feed(90., 30)
        replay.feed(40., 8)
        replay.feed(5., 30)
        self.assertEqual(replay.engine.completed, 1)
        self.assertGreater(replay.engine.timing_live()['hold_elapsed_s'], 1.)
        replay.engine.finish()
        rep = replay.engine.repetitions[0]
        self.assertEqual(rep['completion_status'], 'COMPLETE')
        self.assertIsNone(rep['lowering_time_s'])
        self.assertEqual(rep['movement_timing']['goals']['return'], 'UNASSESSABLE')
        self.assertTrue(rep['movement_timing']['outbound_s']['valid'])
        self.assertIsNone(replay.engine.timing_live())

    def test_squat_hold_uses_shared_policy_without_seated_template(self):
        replay = Replay('rehab_squat', target_angle_deg=60., timing_plan=dict(hold_min_s=.7))
        cues = CueEvents('session')
        replay.feed(0., 30)
        event = cues.update(replay.engine, replay.frame, emission_monotonic=10.)
        self.assertIn('屈膝', event['instruction'])
        replay.feed(70., 8)
        self.assertEqual(cues.update(replay.engine, replay.frame, emission_monotonic=11.)['cue_key'], 'hold')
        replay.feed(70., 12)
        event = cues.update(replay.engine, replay.frame, emission_monotonic=12.)
        self.assertEqual(event['cue_key'], 'return')
        self.assertIn('站姿', event['instruction'])


class TimingPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=paths()['run'])
        self.database = Path(self.directory.name)/'timing.sqlite3'
        def resolver(owner, payload):
            return dict(plan_id='TEST-plan', plan_revision=7, entry_key='sit_to_stand:left',
                        reference=dict(owner=owner, fixture=True),
                        plan=dict(exercise_id='sit_to_stand', side='left', submode='training',
                                  target_reps=1, target_sets=1, timing_plan=dict(return_min_s=.2, hold_min_s=.3)))
        self.resolver = resolver
        self.service = SessionService(self.database, resolver, internal_replay=True)
        self.owner = 'TEST-owner'
        self.sid = self.service.create(self.owner, request())['session_id']
        self.replay = Replay('sit_to_stand')

    def tearDown(self):
        self.service.close()
        self.directory.cleanup()

    def feed(self, value, count):
        for _ in range(count):
            self.replay.feed(value, 1)
            self.service.submit_evidence(self.owner, self.sid, 'frame-'+str(self.replay.seq), self.replay.frame)

    def stand(self):
        self.feed(90., 30)
        self.feed(40., 8)
        self.feed(5., 15)

    def test_return_extends_draft_timing_not_confirmed_rep_and_freezes_atomically(self):
        self.stand()
        draft = self.service.repository.audit_view(self.owner, self.sid)['repetitions']
        self.assertEqual(len(draft), 1)
        self.assertIsNone(draft[0]['movement_timing']['return_s']['value'])
        self.feed(40., 8)
        self.feed(90., 10)
        snapshot = self.service.get(self.owner, self.sid)['snapshot']
        audit = self.service.repository.audit_view(self.owner, self.sid)['repetitions']
        self.assertEqual(audit, snapshot['repetitions'])
        self.assertTrue(audit[0]['movement_timing']['return_s']['valid'])
        self.assertEqual(audit[0]['movement_timing']['goals']['return'], 'MET')
        receipt = self.service.finish(self.owner, self.sid, dict(idempotency_key='finish', expected_revision=0, reason='completed'))
        self.assertEqual(receipt['completed_reps'], 1)
        self.assertEqual(self.service.repository.audit_view(self.owner, self.sid)['repetitions'], audit)
        self.service.close()
        self.service = SessionService(self.database, self.resolver, internal_replay=True)
        self.assertEqual(self.service.repository.audit_view(self.owner, self.sid)['repetitions'], audit)
        self.assertEqual(self.service.commit(self.owner, self.sid)['receipt'], receipt)
        self.assertEqual(self.service.repository.plan_contribution(self.owner, self.sid)['completed_reps'], 1)
        self.service.repository.checkpoint(self.owner, self.sid, dict(snapshot, repetitions=[]))
        self.assertEqual(self.service.repository.audit_view(self.owner, self.sid)['repetitions'], audit)

    def test_pause_ending_standing_and_crash_cannot_add_return_time(self):
        self.stand()
        self.service.control(self.owner, self.sid, 'pause', dict(idempotency_key='pause', expected_revision=0))
        item = self.service.get(self.owner, self.sid)
        self.assertIsNone(item['snapshot']['movement_timing_live'])
        self.assertIsNone(item['snapshot']['repetitions'][0]['lowering_time_s'])
        self.assertEqual(self.service.repository.audit_view(self.owner, self.sid)['repetitions'], item['snapshot']['repetitions'])
        self.service.close(graceful=False)
        self.service = SessionService(self.database, self.resolver, internal_replay=True)
        recovered = self.service.get(self.owner, self.sid)
        self.assertEqual(recovered['end_reason'], 'interrupted')
        self.assertEqual(recovered['snapshot']['completed'], 1)
        self.assertIsNone(recovered['snapshot']['movement_timing_live'])
        self.assertIsNone(recovered['snapshot']['repetitions'][0]['lowering_time_s'])

    def test_draft_timing_update_cannot_change_confirmed_count_fact(self):
        self.stand()
        item = self.service.get(self.owner, self.sid)
        summary = deepcopy(item['snapshot'])
        summary['repetitions'][0]['completion_status'] = 'UNASSESSABLE'
        summary['completed'] = 0
        with self.assertRaisesRegex(SessionError, 'confirmed_repetition_fact_changed'):
            self.service.repository.checkpoint(self.owner, self.sid, summary)
        self.assertEqual(self.service.get(self.owner, self.sid)['snapshot'], item['snapshot'])
        summary = deepcopy(item['snapshot'])
        summary['completed'] = 0
        with self.assertRaisesRegex(SessionError, 'confirmed_repetition_count_mismatch'):
            self.service.repository.checkpoint(self.owner, self.sid, summary)
        self.assertEqual(self.service.get(self.owner, self.sid)['snapshot'], item['snapshot'])


if __name__ == '__main__':
    unittest.main()
