"""Recorded-clock contract tests, not human timing or recovery accuracy."""
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'rehab_codex_single_camera_v2_1'))
from app.domain import digest
from app.rehab_v2.evidence import EvidenceFrame, MetricEvidence
from app.rehab_v2.rounds import TrainingRounds
from app.rehab_v2.sessions import SessionError
from app.rehab_v2.timing_comparison import compare_timing, METRICS
from mobile_rehab.rehab_v2.service import SessionService
from tools.rehab_ml.common import paths
from test_protocols import Replay
from test_timing import shoulder_cycle
from http_finish import finish_http


def observed_cycle(replay, baseline=0.):
    if replay.engine.spec['exercise_id'] == 'sit_to_stand':
        for value, count in ((90., 30), (40., 8), (5., 30), (40., 8), (90., 30)):
            replay.feed(value, count)
    elif baseline:
        for value, count in ((baseline, 30), (70., 24), (baseline, 10)):
            replay.feed(value, count)
    else:
        shoulder_cycle(replay)


def fact(eid='shoulder_abduction', **settings):
    replay = Replay(eid, participant_id='TEST-person', submode='assessment', target_angle_deg=60., **settings)
    observed_cycle(replay)
    replay.engine.finish()
    return dict(frozen_plan=dict(plan=deepcopy(replay.engine.plan), protocol=deepcopy(replay.engine.spec)),
                source=dict(source_kind='SYNTHETIC', usage_context='TEST'), snapshot=deepcopy(replay.engine.summary()))


def timing(item, index=0):
    return item['snapshot']['repetitions'][index]['movement_timing']


class TimingComparisonTests(unittest.TestCase):
    def test_three_actions_compare_complete_durations_with_explicit_denominators(self):
        for eid in ('shoulder_abduction', 'rehab_squat', 'sit_to_stand'):
            with self.subTest(eid=eid):
                item = fact(eid)
                before = deepcopy(item)
                result = compare_timing(item, deepcopy(item))
                for metric in METRICS:
                    row = result['metrics'][metric]
                    self.assertTrue(row['comparable'], row)
                    self.assertEqual(row['right_minus_left_median_s'], 0.)
                    self.assertEqual(row['left']['valid_complete_repetitions'], 1)
                    self.assertEqual(row['left']['excluded_repetitions'], 0)
                self.assertEqual(item, before)
                self.assertFalse(result['clinical_comparable'])
                self.assertFalse(result['improvement_assessed'])
                self.assertFalse(result['significance_assessed'])
                self.assertFalse(result['sampling_invariance_validated'])
                self.assertEqual(timing(item)['comparison_context']['source_epoch'], 'epoch')
                self.assertEqual(timing(item)['comparison_context']['source_ref'], 'internal-replay')
                json.dumps(result, allow_nan=False)

    def test_fact_identity_and_new_calibration_identity_do_not_change_meaning(self):
        a, b = fact(), fact()
        rep = b['snapshot']['repetitions'][0]
        context = timing(b)['comparison_context']
        rep['calibration_epoch'] = context['calibration_epoch'] = 77
        context['source_epoch'] = 'TEST-new-recording'
        for ref in timing(b)['evidence_refs'].values():
            if isinstance(ref, dict) and 'source_epoch' in ref:
                ref.update(source_epoch='TEST-new-recording', seq=ref['seq']+100, time_s=ref['time_s']+300.)
        b['snapshot'].update(session_id='TEST-independent-session', source_epoch='TEST-new-recording')
        b['canonical_commit'] = dict(commit_id='TEST-new-commit')
        b['source']['source_ref'] = 'TEST-different-file'
        for row in compare_timing(a,b)['metrics'].values():
            self.assertTrue(row['comparable'], row)
            self.assertEqual(row['left_contract_digests'], row['right_contract_digests'])

    def test_median_difference_is_not_index_pairing_or_an_improvement_score(self):
        a, b = fact(), fact()
        a['snapshot']['repetitions'] *= 3
        b['snapshot']['repetitions'] *= 2
        a['snapshot']['repetitions'] = deepcopy(a['snapshot']['repetitions'])
        b['snapshot']['repetitions'] = deepcopy(b['snapshot']['repetitions'])
        # TEST-only numeric perturbations, not persisted measured facts.
        for item, values in ((a,(0.,1.,8.)), (b,(2.,4.))):
            for index, value in enumerate(values):
                rep = deepcopy(item['snapshot']['repetitions'][index])
                rep['movement_timing']['outbound_s']['value'] = value
                item['snapshot']['repetitions'][index] = rep
        row = compare_timing(a,b)['metrics']['outbound_s']
        self.assertTrue(row['comparable'], row)
        self.assertEqual(row['left']['median_s'], 1.)
        self.assertEqual(row['right']['median_s'], 3.)
        self.assertEqual(row['right_minus_left_median_s'], 2.)

    def test_changed_domain_protocol_baseline_support_target_and_goal_are_not_comparable(self):
        original = fact()
        for field, value in (('schema_id','other-schema'), ('model_manifest_id','other-model'),
                             ('frame_size',[640,360]), ('coordinate_space','other-axis'),
                             ('preprocess_version','other-filter')):
            with self.subTest(field=field):
                other = deepcopy(original)
                timing(other)['comparison_context']['domain'][field] = value
                row = compare_timing(original,other)['metrics']['outbound_s']
                self.assertEqual(row['reason'], 'contract_changed')
                self.assertIn('domain', row['changed_fields'])
                self.assertIsNone(row['right_minus_left_median_s'])
        for field, value in (('target_angle_deg',70.), ('ready_s',1.2), ('participant_id','TEST-other-person'),
                             ('use_of_hands','not_allowed'), ('needs_companion',True)):
            with self.subTest(field=field):
                other = deepcopy(original)
                other['frozen_plan']['plan'][field] = value
                context = timing(other)['comparison_context']
                if field == 'ready_s': context['parameters'][field] = value
                elif field in ('use_of_hands','needs_companion'): context['support'][field] = value
                else: context[field] = value
                self.assertEqual(compare_timing(original,other)['metrics']['outbound_s']['reason'], 'contract_changed')
        for field, value in (('side','right'), ('view','sagittal'), ('metric_version','new-metric')):
            other = deepcopy(original)
            other['frozen_plan']['protocol'][field] = timing(other)['comparison_context']['protocol'][field] = value
            self.assertEqual(compare_timing(original,other)['metrics']['outbound_s']['reason'], 'contract_changed')
        for field in ('baseline','timing_plan','source'):
            other = deepcopy(original)
            if field == 'baseline': timing(other)['comparison_context']['baseline']['raw_value'] += 1.
            elif field == 'timing_plan':
                other['frozen_plan']['plan']['timing_plan']['hold_min_s'] = .7
                timing(other)['comparison_context']['timing_plan']['hold_min_s'] = .7
            else: other['source']['source_kind'] = 'REPLAY_FILE'
            self.assertEqual(compare_timing(original,other)['metrics']['outbound_s']['reason'], 'contract_changed')

    def test_source_clock_conditions_differ_and_nominal_time_is_not_measured_time(self):
        a, b = fact(), fact()
        timing(b)['time_basis'] = timing(b)['comparison_context']['domain']['time_basis'] = 'opencv_media_pts'
        self.assertEqual(compare_timing(a,b)['metrics']['outbound_s']['reason'], 'contract_changed')
        timing(b)['time_basis'] = timing(b)['comparison_context']['domain']['time_basis'] = 'nominal_video_seconds'
        row = compare_timing(a,b)['metrics']['outbound_s']
        self.assertEqual(row['right']['exclusion_reasons'], {'unsupported_or_nominal_time_basis':1})
        self.assertIsNone(row['right_minus_left_median_s'])

    def test_legacy_context_is_not_backfilled_and_bad_binding_is_excluded(self):
        a = fact()
        for field in ('comparison_context','evidence_refs','algorithm_version','count_gate'):
            with self.subTest(field=field):
                b = deepcopy(a)
                timing(b).pop(field)
                before = deepcopy(b)
                for row in compare_timing(a,b)['metrics'].values():
                    self.assertFalse(row['comparable'])
                    self.assertIsNone(row['right']['median_s'])
                self.assertEqual(b,before)
        for field, value in (('calibration_epoch',None), ('source_epoch',None), ('target_angle_deg',90.)):
            b = deepcopy(a)
            timing(b)['comparison_context'][field] = value
            self.assertFalse(compare_timing(a,b)['metrics']['outbound_s']['comparable'])

    def test_bad_numeric_durations_never_turn_into_zero_or_delta(self):
        a = fact()
        for value in (None,True,-1.,float('nan'),float('inf'),2**2048):
            b = deepcopy(a)
            timing(b)['outbound_s']['value'] = value
            row = compare_timing(a,b)['metrics']['outbound_s']
            self.assertFalse(row['comparable'])
            self.assertIsNone(row['right']['median_s'])
            self.assertIsNone(row['right_minus_left_median_s'])
            json.dumps(row, allow_nan=False)

    def test_unsupported_algorithm_phase_count_semantics_or_bad_evidence_are_not_compared(self):
        a = fact()
        for key,value in (('version','old-envelope'),('algorithm_version','other-algorithm'),
                          ('method','other-phase'),('phase_timing_mode','other-mode'),('count_gate',True)):
            b = deepcopy(a)
            timing(b)[key] = value
            self.assertFalse(compare_timing(a,b)['metrics']['outbound_s']['comparable'])
        for key,value in (('seq',-1),('seq',True),('time_s',-1.),('time_s',float('inf')),('source_epoch','other')):
            b = deepcopy(a)
            timing(b)['evidence_refs']['latest'][key] = value
            self.assertFalse(compare_timing(a,b)['metrics']['outbound_s']['comparable'])
        b = deepcopy(a)
        timing(b)['evidence_refs']['latest']['seq'] = 0
        row = compare_timing(a,b)['metrics']['outbound_s']
        self.assertEqual(row['right']['exclusion_reasons'], {'invalid_timing_evidence_order':1})

    def test_training_dose_is_a_condition_and_cannot_be_missing_or_changed(self):
        a = fact()
        # TEST contract fixture; no manufactured durations enter any database.
        plan = a['frozen_plan']['plan']
        plan.update(submode='training',target_reps=2,target_sets=1,rest_between_sets_s=None)
        context = timing(a)['comparison_context']
        context.update(submode='training',dose={key:plan[key] for key in ('target_reps','target_sets','rest_between_sets_s')})
        self.assertTrue(compare_timing(a,deepcopy(a))['metrics']['outbound_s']['comparable'])
        for field,value in (('target_reps',3),('target_sets',2),('rest_between_sets_s',30.)):
            b = deepcopy(a)
            b['frozen_plan']['plan'][field] = timing(b)['comparison_context']['dose'][field] = value
            row = compare_timing(a,b)['metrics']['outbound_s']
            self.assertEqual(row['reason'],'contract_changed')
            self.assertIn('dose',row['changed_fields'])
        b = deepcopy(a)
        timing(b)['comparison_context']['dose'].pop('target_reps')
        self.assertFalse(compare_timing(a,b)['metrics']['outbound_s']['comparable'])

    def test_partial_hold_is_lower_bound_not_full_hold_even_when_count_complete(self):
        a, b = fact(), fact()
        timing(b)['partial_observation'] = True
        row = compare_timing(a,b)['metrics']['target_hold_s']
        self.assertFalse(row['comparable'])
        self.assertEqual(row['right']['exclusion_reasons'], {'partial_hold_is_observed_lower_bound':1})
        self.assertTrue(compare_timing(a,b)['metrics']['outbound_s']['comparable'])

    def test_incomplete_attempts_stay_in_denominators_and_invalid_complete_blocks_delta(self):
        a, b = fact(), fact()
        rep = deepcopy(b['snapshot']['repetitions'][0])
        rep['completion_status'] = 'UNASSESSABLE'
        b['snapshot']['repetitions'].append(rep)
        row = compare_timing(a,b)['metrics']['outbound_s']
        self.assertTrue(row['comparable'])
        self.assertEqual(row['right']['attempts'], 2)
        self.assertEqual(row['right']['exclusion_reasons'], {'repetition_not_complete':1})
        rep['completion_status'] = 'COMPLETE'
        rep['movement_timing']['outbound_s'].update(valid=False,value=None,reason='missing_interval')
        row = compare_timing(a,b)['metrics']['outbound_s']
        self.assertEqual(row['reason'], 'incomplete_timing_coverage')
        self.assertIsNone(row['right_minus_left_median_s'])

    def test_standing_finish_can_compare_observed_rise_but_cannot_invent_return_or_hold(self):
        replay = Replay('sit_to_stand', participant_id='TEST-person', submode='assessment')
        replay.feed(90.,30)
        replay.feed(40.,8)
        replay.feed(5.,30)
        replay.engine.finish()
        item = dict(frozen_plan=dict(plan=replay.engine.plan,protocol=replay.engine.spec),
                    source=dict(source_kind='SYNTHETIC',usage_context='TEST'),snapshot=replay.engine.summary())
        result = compare_timing(item,deepcopy(item))['metrics']
        self.assertTrue(result['outbound_s']['comparable'])
        self.assertFalse(result['return_s']['comparable'])
        self.assertFalse(result['target_hold_s']['comparable'])
        self.assertIsNone(result['return_s']['left']['median_s'])

    def test_actual_two_sets_keep_per_rep_baseline_without_reinterpreting_first_set(self):
        replay = Replay('rehab_squat')
        replay.engine = TrainingRounds(dict(exercise_id='rehab_squat',participant_id='TEST-person',submode='training',
            target_reps=1,target_sets=2,target_angle_deg=60.,use_of_hands='allowed',needs_companion=False),
            source_epoch='epoch',session_id='TEST-two-sets')
        # Stop feeding at the prescribed set boundary, as a real caller must.
        def run(start):
            for value,count in ((start,30),(70.,24),(start,10)):
                for _ in range(count):
                    if replay.engine.training_stage in ('RESTING','COMPLETE'): return
                    replay.feed(value,1)
        run(0.)
        first = deepcopy(replay.engine.repetitions[0]['movement_timing']['comparison_context'])
        self.assertEqual(replay.engine.training_stage,'RESTING')
        replay.engine.resume(source_time_s=replay.t)
        run(5.)
        self.assertEqual(replay.engine.completed,2)
        self.assertEqual(replay.engine.repetitions[0]['movement_timing']['comparison_context'],first)
        replay.engine.finish()
        item = dict(frozen_plan=dict(plan=replay.engine.plan,protocol=replay.engine.spec),
                    source=dict(source_kind='SYNTHETIC',usage_context='TEST'),snapshot=replay.engine.summary())
        row = compare_timing(item,deepcopy(item))['metrics']['outbound_s']
        self.assertEqual(row['reason'],'heterogeneous_recorded_conditions')
        self.assertEqual(row['left']['distinct_condition_count'],2)


class TimingComparisonServiceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=paths()['run'])
        self.database = Path(self.directory.name)/'timing-comparison.sqlite3'
        self.owner = 'TEST-timing-owner'
        self.service = SessionService(self.database, lambda o,p: None, internal_replay=True)
        self.counter = 0

    def tearDown(self):
        self.service.close()
        self.directory.cleanup()

    def assess(self, eid='shoulder_abduction', finish=True):
        self.counter += 1
        payload = dict(idempotency_key='assessment-'+str(self.counter),consent=True,submode='assessment',
                       exercise_id=eid,side='left',view='frontal' if eid=='shoulder_abduction' else 'sagittal')
        deadline = time.monotonic()+3.
        while True:
            try:
                sid = self.service.create(self.owner,payload)['session_id']
                break
            except SessionError as error:
                if error.code != 'rehab_compute_resource_busy' or time.monotonic() >= deadline: raise
                time.sleep(.01)
        replay = Replay(eid)
        values = ((90.,30),(40.,8),(5.,30),(40.,8),(90.,30)) if eid=='sit_to_stand' else ((0.,30),(70.,24),(0.,10))
        for value,count in values:
            for _ in range(count):
                replay.feed(value,1)
                self.service.submit_evidence(self.owner,sid,'frame-'+str(replay.seq),replay.frame)
        if finish:
            self.service.finish(self.owner,sid,dict(idempotency_key='finish',expected_revision=0,reason='completed'))
        return sid

    def compare(self, a,b,owner=None):
        return self.service.compare_timing(owner or self.owner,dict(left_session_id=a,right_session_id=b))

    def test_persisted_three_actions_use_real_context_and_final_receipt_digest(self):
        for eid in ('shoulder_abduction','rehab_squat','sit_to_stand'):
            with self.subTest(eid=eid):
                a,b = self.assess(eid),self.assess(eid)
                result = self.compare(a,b)
                self.assertTrue(result['metrics']['outbound_s']['comparable'],result)
                self.assertEqual(result['left']['commit_id'],self.service.commit(self.owner,a)['receipt']['commit_id'])
                self.assertEqual(result['left']['visual_snapshot_digest'],digest(self.service.get(self.owner,a)['snapshot']))

    def test_read_only_after_feedback_report_failure_restart_and_repeat_read(self):
        self.service.report_builder = lambda item: (_ for _ in ()).throw(RuntimeError('TEST-report-failure'))
        a,b = self.assess(),self.assess()
        snapshots = [self.service.get(self.owner,sid)['snapshot'] for sid in (a,b)]
        receipts = [self.service.commit(self.owner,sid)['receipt'] for sid in (a,b)]
        contributions = [self.service.repository.plan_contribution(self.owner,sid) for sid in (a,b)]
        before = self.compare(a,b)
        self.service.feedback(self.owner,a,dict(idempotency_key='feedback',expected_revision=0,
            feedback=dict(pain=2,fatigue=2,reason='discomfort')))
        self.assertEqual(self.compare(a,b),before)
        self.service.close()
        self.service = SessionService(self.database,lambda o,p:None,internal_replay=True)
        self.assertEqual(self.compare(a,b),before)
        for index,sid in enumerate((a,b)):
            self.assertEqual(self.service.get(self.owner,sid)['snapshot'],snapshots[index])
            self.assertEqual(self.service.commit(self.owner,sid)['receipt'],receipts[index])
            self.assertEqual(self.service.repository.plan_contribution(self.owner,sid),contributions[index])
            self.assertEqual(self.service.repository.audit_view(self.owner,sid)['repetitions'],snapshots[index]['repetitions'])

    def test_owner_distinct_ids_finalization_and_exact_payload_remain_required(self):
        a,b = self.assess(),self.assess(finish=False)
        with self.assertRaisesRegex(SessionError,'requires_finalized'): self.compare(a,b)
        with self.assertRaisesRegex(SessionError,'session_not_found'): self.compare(a,b,owner='TEST-other-owner')
        with self.assertRaisesRegex(SessionError,'distinct_timing'): self.compare(a,a)
        for payload in ({},dict(left_session_id=a,right_session_id=b,owner=self.owner),[],
                        dict(left_session_id=a,right_session_id=1)):
            with self.assertRaises(SessionError): self.service.compare_timing(self.owner,payload)

    def test_tampered_visual_fact_is_rejected_before_any_duration_comparison(self):
        a,b = self.assess(),self.assess()
        original = self.service.get(self.owner,b)
        changed = deepcopy(original)
        timing(changed)['outbound_s']['value'] = 999.
        self.service.storage._call(lambda c:c.execute('UPDATE rehab_v2_sessions SET payload=? WHERE id=?',(json.dumps(changed),b)))
        try:
            with self.assertRaisesRegex(SessionError,'fact_digest_mismatch'): self.compare(a,b)
        finally:
            self.service.storage._call(lambda c:c.execute('UPDATE rehab_v2_sessions SET payload=? WHERE id=?',(json.dumps(original),b)))
        self.assertTrue(self.compare(a,b)['metrics']['outbound_s']['comparable'])


class TimingComparisonHttpTests(unittest.TestCase):
    def test_actual_authenticated_host_endpoint_and_default_off_routes(self):
        from fastapi.testclient import TestClient
        from PIL import Image
        from mobile_rehab.server import create_app
        endpoint = '/api/rehab/v2/timing-comparisons'
        with tempfile.TemporaryDirectory(dir=paths()['run']) as directory:
            app = create_app(directory,pair_key='TEST-timing-http',runner=lambda item:None,rehab_v2=True)
            with TestClient(app,headers={'X-Rehab-Client':'mobile-v1'}) as client:
                self.assertEqual(client.post(endpoint,json={}).status_code,401)
                client.post('/api/pair',json=dict(code='TEST-timing-http'))
                service = app.state.rehab_v2
                def provider(value,runtime):
                    seq,stamp = value['seq'],value['source_time_s']
                    angle = 0. if seq <=30 or seq>54 else 70.
                    metric = MetricEvidence(angle,'degree',True,None,'observed',stamp,stamp,0.,tuple(runtime.engine.spec['required_joints']))
                    return EvidenceFrame(seq,stamp,runtime.context.epoch,'TEST-person','coco17-v1',
                        'TEST-geometry-provider',(320,240),{runtime.engine.spec['metric']:metric},'VALID','browser-camera')
                service.inference_provider = provider  # TEST hook; not actual human camera evidence.
                stream = BytesIO()
                Image.new('RGB',(320,240),'white').save(stream,format='JPEG')
                encoded = stream.getvalue()
                ids = []
                base = '/api/rehab/v2/sessions'
                for index in range(2):
                    payload = dict(idempotency_key='assessment-'+str(index),consent=True,submode='assessment',
                                   exercise_id='shoulder_abduction',side='left',view='frontal')
                    deadline = time.monotonic()+3.
                    while True:
                        response = client.post(base,json=payload)
                        if response.status_code !=503 or response.json().get('detail')!='rehab_compute_resource_busy': break
                        if time.monotonic()>=deadline: self.fail(response.text)
                        time.sleep(.01)
                    self.assertEqual(response.status_code,200,response.text)
                    sid = response.json()['session_id']
                    for seq in range(1,65):
                        frame = client.post(base+'/'+sid+'/frames',content=encoded,headers={
                            'content-type':'image/jpeg','x-rehab-event-id':'frame-'+str(seq),'x-rehab-seq':str(seq)})
                        self.assertEqual(frame.status_code,200,frame.text)
                        deadline = time.monotonic()+5.
                        while client.get(base+'/'+sid).json()['processed_last_seq']<seq:
                            if time.monotonic()>=deadline: self.fail('owned TEST geometry result timeout')
                            time.sleep(.01)
                        time.sleep(.05)
                    finished = finish_http(client, base+'/'+sid, dict(idempotency_key='finish',expected_revision=0,reason='completed'))
                    self.assertEqual(finished['completed_reps'],1,finished)
                    ids.append(sid)
                payload = dict(left_session_id=ids[0],right_session_id=ids[1])
                result = client.post(endpoint,json=payload)
                self.assertEqual(result.status_code,200,result.text)
                self.assertTrue(result.json()['metrics']['outbound_s']['comparable'],result.text)
                self.assertFalse(service.internal_replay)
                self.assertEqual(client.post(endpoint,json=dict(payload,owner='TEST-forged')).status_code,400)
                self.assertEqual(client.post(endpoint,json=dict(left_session_id=ids[0],right_session_id=ids[0])).status_code,400)
                other = TestClient(app,headers={'X-Rehab-Client':'mobile-v1'})
                try:
                    other.post('/api/pair',json=dict(code='TEST-timing-http'))
                    self.assertEqual(other.post(endpoint,json=payload).status_code,404)
                finally:
                    other.close()
                client.cookies.clear()
                self.assertEqual(client.post(endpoint,json=payload).status_code,401)
        with tempfile.TemporaryDirectory(dir=paths()['run']) as directory:
            app = create_app(directory,pair_key='TEST-default-off',runner=lambda item:None)
            self.assertNotIn(endpoint,{r.path for r in app.routes})


if __name__=='__main__':
    unittest.main()
