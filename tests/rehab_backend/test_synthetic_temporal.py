"""TEST-only engineered trajectories/labels, never synthetic human ground truth."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import torch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.rehab_ml.synthetic.temporal import (COCO17,MP33,PHASES,BOUNDARIES,PhaseTCN,
    causal_features,phase_targets,sequence_loss,collate_sequences,decode_phases,
    validate_records,train,predict_run,replay_baseline)
from tools.rehab_ml.synthetic.evaluation import compare,validate_predictions,baseline_manifest


def fixture_pose(sample='TEST-train',backend='yolo17',frames=20,offset=0.):
    names=COCO17 if backend=='yolo17' else MP33
    rows=[]
    for i in range(frames):
        joints={name:dict(x=320.,y=200.,confidence=.9,visibility=.9,presence=.9) for name in names}
        joints['left_shoulder'].update(x=280.,y=120.)
        joints['right_shoulder'].update(x=360.,y=120.)
        joints['left_elbow'].update(x=280.-60.*np.sin(i*.1+offset),y=120.+60.*np.cos(i*.1+offset))
        joints['right_elbow'].update(x=360.,y=180.)
        joints['left_hip'].update(x=290.,y=260.); joints['right_hip'].update(x=350.,y=260.)
        rows.append(dict(frame_index=i,pts=i,time_base=[1,15],timestamp_s=i/15,
                         pose_detected=True,track_id='TEST-track-1',joints=joints))
    return dict(schema_version='rehab_synthetic_pose/v1',sample_id=sample,backend=backend,
        source_sha256=__import__('hashlib').sha256(sample.encode()).hexdigest(),source_size=[640,384],
        model=dict(sha256='a'*64),frames=rows)


def fixture_records():
    result=[]
    for split in ('train','val','test'):
        sid='TEST-'+split; pose=fixture_pose(sid)
        annotation=dict(sample_id=sid,reviewer_role='ai_draft',reviewer_id='TEST-engineer',
            phase_intervals=[dict(phase=phase,start_s=i*.2,end_s=(i+1)*.2,label_mask=True)
                             for i,phase in enumerate(PHASES)],
            repetitions=[],observable_count=0,observable_count_mask=True)
        result.append(dict(sample_id=sid,split=split,source_group_id='TEST-person-'+split,
                           pose=pose,annotation=annotation,side='left'))
    return result


def manifest(rows,kind='B2',*,count=0):
    return dict(schema_version='rehab_synthetic_predictions/v1',kind=kind,reference_used_for_predictions=False,
        engineering_test=True,samples=[dict(sample_id=r['sample_id'],backend='yolo17',split=r['split'],
            source_sha256=r['pose']['source_sha256'],status='completed',completed_count=count,
            boundary_events={key:None if key=='endpoint_end_s' else [] for key in BOUNDARIES}) for r in rows])


class SyntheticTemporalTests(unittest.TestCase):
    def test_two_native_backends_keep_names_and_absolute_amplitude(self):
        for backend in ('yolo17','mediapipe33'):
            pose=fixture_pose(backend=backend)
            out=causal_features(pose)
            self.assertEqual(out['features'].shape[1],7*len(out['joint_names'])+10)
            self.assertEqual(len(out['joint_names']),17 if backend=='yolo17' else 33)
            self.assertAlmostEqual(out['angle_deg'][0],0.)
            self.assertAlmostEqual(out['angle_deg'][10],np.degrees(1.))
            short=causal_features(dict(pose,frames=pose['frames'][:6]))
            np.testing.assert_array_equal(out['features'][:len(short['features'])],short['features'])
        self.assertNotIn('left_heel',causal_features(fixture_pose())['joint_names'])

    def test_future_perturbation_does_not_change_past(self):
        pose=fixture_pose(); altered=copy.deepcopy(pose)
        for row in altered['frames'][10:]: row['joints']['left_elbow'].update(x=10.,y=10.)
        first,second=causal_features(pose),causal_features(altered)
        np.testing.assert_array_equal(first['features'][:10],second['features'][:10])
        self.assertTrue(np.all(first['source_time_s']<=first['time_s']))

    def test_missing_age_fresh_and_track_reset_do_not_impute_future(self):
        pose=fixture_pose(frames=3)
        for row,stamp in zip(pose['frames'],[0.,.2,.8]): row['timestamp_s']=stamp
        pose['frames'][-1]['track_id']='TEST-track-2'
        out=causal_features(pose,max_age_s=.3)
        self.assertTrue((out['source_age_s']>.3).any())
        self.assertTrue(np.all(~out['prediction_mask'][out['source_age_s']>.3]))
        self.assertTrue(np.any(~out['fresh']))
        idx=np.flatnonzero(out['source_time_s']==.8)[0]
        self.assertTrue(out['track_reset'][idx])
        np.testing.assert_array_equal(out['features'][idx,34:68],0.)
        pose['frames'][1]['pose_detected']=False; pose['frames'][1]['joints']={}
        out=causal_features(pose)
        self.assertFalse(out['prediction_mask'][3])

    def test_invalid_pts_rejected_instead_of_nominal_repair(self):
        for key,value in [('timestamp_s',0.),('pts',None),('time_base',None)]:
            pose=fixture_pose(); pose['frames'][1][key]=value
            with self.assertRaises(ValueError): causal_features(pose)
        pose=fixture_pose();pose['status']='failed'
        with self.assertRaisesRegex(ValueError,'failed_or_running'):causal_features(pose)

    def test_unknown_intervals_and_gaps_remain_unlabelled(self):
        annotation=dict(phase_intervals=[dict(phase='ready',start_s=0.,end_s=.2,label_mask=True),
            dict(phase='outbound',start_s=None,end_s=None,label_mask=False)])
        labels,mask=phase_targets([0.,.1,.2,.3,.4,.5],annotation)
        np.testing.assert_array_equal(mask,[True,True,False,False,False,False])
        annotation['phase_intervals'][1].update(start_s=.1,end_s=.4,label_mask=True)
        with self.assertRaises(ValueError):phase_targets([.1],annotation)

    def test_tcn_prefix_and_future_causality(self):
        torch.manual_seed(7); model=PhaseTCN(8,32,.1).eval(); x=torch.randn(1,20,8)
        with torch.inference_mode():
            full=model(x)
            for end in (1,3,10,19): torch.testing.assert_close(model(x[:,:end]),full[:,:end])
            other=x.clone(); other[:,12:]+=100
            torch.testing.assert_close(model(other)[:,:12],full[:,:12])
        self.assertEqual(full.shape,(1,20,5))

    def test_unknown_padding_gradients_are_zero(self):
        logits=torch.randn(1,4,5,requires_grad=True); labels=torch.tensor([[1,2,3,4]])
        loss=sequence_loss(logits,labels,torch.tensor([[True,False,True,True]]),torch.tensor([[True,True,False,False]]))
        loss.backward(); self.assertGreater(float(logits.grad[0,0].abs().sum()),0.)
        self.assertEqual(float(logits.grad[0,1:].abs().sum()),0.)
        empty=torch.randn(1,2,5,requires_grad=True)
        sequence_loss(empty,torch.zeros((1,2),dtype=torch.long),torch.zeros((1,2),dtype=torch.bool),torch.ones((1,2),dtype=torch.bool)).backward()
        self.assertEqual(float(empty.grad.abs().sum()),0.)

    def test_collate_whole_sources_padding_does_not_supervise(self):
        items=[dict(features=np.ones((n,3),np.float32),labels=np.ones(n,np.int64),label_mask=np.ones(n,bool)) for n in (2,4)]
        _,_,known,padding=collate_sequences(items,np.zeros(3),np.ones(3))
        self.assertFalse(padding[0,2:].any());self.assertFalse(known[0,2:].any())

    def test_count_memory_spans_long_hold_and_requires_whole_lifecycle(self):
        phases=['ready','outbound']+['endpoint_or_hold']*100+['return','ready']
        decoded=decode_phases(phases,np.arange(len(phases))/15)
        self.assertEqual(decoded['completed_count'],1)
        self.assertIsNone(decoded['boundary_events']['endpoint_end_s'])
        self.assertEqual(decode_phases(['outbound','endpoint_or_hold','return','ready'],[0.,1.,2.,3.])['completed_count'],0)
        self.assertEqual(decode_phases(['ready','outbound','endpoint_or_hold','return','rest_or_other'],range(5))['completed_count'],1)
        reset=[False]*len(phases);reset[-2]=True
        self.assertEqual(decode_phases(phases,np.arange(len(phases)),track_reset=reset)['completed_count'],0)
        missing=[True]*len(phases);missing[-2]=False
        self.assertEqual(decode_phases(phases,np.arange(len(phases)),available=missing)['completed_count'],0)
        self.assertIsNone(decode_phases(['ready'],[0.],available=[False])['completed_count'])
        # Several grid ticks using one arrived frame cannot invent a motion.
        self.assertEqual(decode_phases(['ready','outbound','endpoint_or_hold','return','ready'],[0.,0.,0.,0.,1.])['completed_count'],0)

    def test_ai_drafts_cannot_train_and_TEST_cannot_impersonate_real(self):
        records=fixture_records()
        with self.assertRaisesRegex(ValueError,'human_review'):validate_records(records)
        records[0]['sample_id']='real';records[0]['pose']['sample_id']='real';records[0]['annotation']['sample_id']='real'
        with self.assertRaisesRegex(ValueError,'TEST_sources'):validate_records(records,engineering_test=True)

    def test_source_group_derived_and_backend_leakage(self):
        records=fixture_records();records[-1]['source_group_id']=records[0]['source_group_id']
        with self.assertRaisesRegex(ValueError,'leakage'):validate_records(records,engineering_test=True)
        records=fixture_records();records[-1]['related_source_groups']=[records[0]['source_group_id']]
        with self.assertRaisesRegex(ValueError,'leakage'):validate_records(records,engineering_test=True)
        records=fixture_records();records[-1]['pose']['source_sha256']=records[0]['pose']['source_sha256']
        with self.assertRaisesRegex(ValueError,'leakage'):validate_records(records,engineering_test=True)
        records=fixture_records();records[-1]['pose']=fixture_pose('TEST-test','mediapipe33')
        with self.assertRaisesRegex(ValueError,'separate_backend'):validate_records(records,engineering_test=True)

    def test_shared_reference_cannot_cross_splits_even_without_related_groups_hint(self):
        records=fixture_records()
        for row in (records[0],records[2]):
            row['sample']=dict(reference_group_id='TEST-shared-virtual-person',lineage_ids=[])
        with self.assertRaisesRegex(ValueError,'reference_or_lineage_source_split_leakage'):
            validate_records(records,engineering_test=True)

    def test_lineage_transitivity_and_role_renaming_cannot_bypass_splits(self):
        records=fixture_records()
        # No train/test pair shares a direct identifier: the middle reference
        # bridges them. It is not sufficient to compare adjacent source IDs.
        records[1]['split']='train'
        records[0]['sample']=dict(reference_group_id='TEST-ref-a',lineage_ids=['TEST-motion-a'])
        records[1]['sample']=dict(reference_group_id='TEST-motion-a',lineage_ids=['TEST-motion-b'])
        records[2]['sample']=dict(reference_group_id='TEST-ref-c',lineage_ids=['TEST-motion-b'])
        with self.assertRaisesRegex(ValueError,'reference_or_lineage_source_split_leakage'):
            validate_records(records,engineering_test=True)
        records[2]['split']='train'
        self.assertEqual(validate_records(records,engineering_test=True),'yolo17')

    def test_explicit_shared_reference_fingerprint_cannot_cross_splits(self):
        records=fixture_records()
        for row in (records[0],records[2]):
            row['sample']=dict(reference_group_id='TEST-ref-'+row['split'],lineage_ids=[],
                generation=dict(reference_sha256='e'*64))
        with self.assertRaisesRegex(ValueError,'reference_or_lineage_source_split_leakage'):
            validate_records(records,engineering_test=True)

    def test_cpu_TEST_training_fixed_predictions_and_no_reference_in_inference(self):
        records=fixture_records()
        with tempfile.TemporaryDirectory() as root:
            result=train(records,Path(root)/'run',dict(max_epochs=2,patience=1),engineering_test=True)
            self.assertTrue(result['engineering_test']);self.assertFalse(result['product_enabled'])
            cfg=json.loads((Path(root)/'run/config.json').read_text())
            self.assertEqual(cfg['standardization_train_sample_ids'],['TEST-train'])
            record=dict(records[-1]);record.pop('annotation')
            prediction=predict_run(Path(root)/'run',[record],Path(root)/'other',engineering_test=True)
            self.assertFalse(json.loads(Path(prediction['path']).read_text())['reference_used_for_predictions'])
            checkpoint=torch.load(Path(root)/'run/checkpoint.pt',weights_only=True)
            expected=causal_features(records[0]['pose'])['features'].mean(0)
            np.testing.assert_allclose(checkpoint['mean'].numpy(),expected)

    def test_failed_or_missing_predictions_retain_denominator_and_never_become_zero(self):
        records=fixture_records();pred=manifest(records[-1:])
        pred['samples'][0].update(status='failed',completed_count=None,boundary_events=dict.fromkeys(BOUNDARIES))
        _,rows=validate_predictions(pred,records[-1:],kind='B2')
        self.assertIsNone(rows[0]['completed_count'])
        pred['samples'][0]['completed_count']=0
        with self.assertRaisesRegex(ValueError,'failed_prediction'):validate_predictions(pred,records[-1:],kind='B2')
        with tempfile.TemporaryDirectory() as root:
            b0=manifest(records,'B0');b2=manifest(records)
            b2['samples']=[r for r in b2['samples'] if r['split']!='test']
            report=compare(records,b0,b2,Path(root)/'evaluation',engineering_test=True)
            doc=json.loads(Path(report['path']).read_text())
            self.assertEqual(doc['B2']['missing_count_predictions'],1)
            self.assertEqual(doc['B2']['cohort_videos'],1)
            self.assertEqual(doc['verdict'],'evidence_insufficient')

    def test_prediction_events_must_be_actual_pts_and_source_identity_cannot_change(self):
        records=fixture_records()[-1:];pred=manifest(records)
        pred['samples'][0]['boundary_events']['outbound_start_s']=[dict(event_id='TEST-event',time_s=.12345,evidence_kind='filtered')]
        with self.assertRaisesRegex(ValueError,'actual_pts'):validate_predictions(pred,records,kind='B2')
        pred=manifest(records);pred['samples'][0]['source_sha256']='f'*64
        with self.assertRaisesRegex(ValueError,'source_backend'):validate_predictions(pred,records,kind='B2')

    def test_wrong_prediction_split_is_rejected_before_filter_not_hidden_as_missing(self):
        records=fixture_records();pred=manifest(records)
        pred['samples'][-1]['split']='train'
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ValueError,'fixed_split_changed'):
                compare(records,manifest(records,'B0'),pred,Path(root)/'must-not-exist',engineering_test=True)
            self.assertFalse((Path(root)/'must-not-exist').exists())

    def test_unavailable_boundary_is_not_an_empty_predicted_inventory(self):
        records=fixture_records()[-1:];row=records[0]
        row['annotation']['repetitions']=[dict(rep_id='TEST-rep',boundaries={p:i/15 for i,p in enumerate(PHASES)},
            boundary_masks={p:True for p in PHASES},observable_completion=True,observable_completion_mask=True)]
        row['annotation']['observable_count']=1
        with tempfile.TemporaryDirectory() as root:
            result=compare(records,manifest(records,'B0'),manifest(records),Path(root)/'report',engineering_test=True)
            report=json.loads(Path(result['path']).read_text())
            self.assertEqual(report['B2']['boundaries']['endpoint_end_s']['prediction_missing_videos'],1)
            self.assertEqual(report['B2']['boundaries']['endpoint_start_s']['prediction_available_videos'],1)

    def test_frozen_B0_saved_pose_replay_returns_explicit_unsupported_boundaries(self):
        result=replay_baseline(fixture_pose())
        self.assertEqual(result['status'],'completed')
        self.assertIsNone(result['boundary_events']['endpoint_start_s'])
        self.assertIsNone(result['boundary_events']['endpoint_end_s'])
        self.assertIsInstance(result['completed_count'],int)

    def test_B0_no_person_is_missing_output_not_zero_repetitions(self):
        pose=fixture_pose()
        for frame in pose['frames']:
            frame.update(pose_detected=False,track_id=None,joints={})
        result=replay_baseline(pose)
        self.assertEqual(result['status'],'unavailable')
        self.assertIsNone(result['completed_count'])
        self.assertTrue(all(v is None for v in result['boundary_events'].values()))
        self.assertEqual(result['coverage']['processed_frames'],len(pose['frames']))
        self.assertEqual(result['coverage']['observable_frames'],0)
        self.assertEqual(result['coverage']['observable_fraction'],0.)
        self.assertTrue(result['coverage']['entirely_unobservable'])

    def test_B0_detected_but_unobservable_arm_retains_zero_metric_coverage(self):
        pose=fixture_pose()
        for frame in pose['frames']:
            frame['joints']['left_elbow'].update(x=None,y=None,confidence=.1)
        result=replay_baseline(pose)
        self.assertEqual(result['status'],'unavailable')
        self.assertIsNone(result['completed_count'])
        self.assertEqual(result['coverage']['pose_detected_frames'],len(pose['frames']))
        self.assertEqual(result['coverage']['observable_frames'],0)

    def test_B0_unobservable_video_remains_in_count_missing_denominator_and_report(self):
        records=fixture_records()[-1:];pose=records[0]['pose']
        for frame in pose['frames']:frame.update(pose_detected=False,track_id=None,joints={})
        baseline=baseline_manifest(records,engineering_test=True)
        self.assertIsNone(baseline['samples'][0]['completed_count'])
        self.assertEqual(baseline['samples'][0]['coverage']['observable_frames'],0)
        with tempfile.TemporaryDirectory() as root:
            result=compare(records,baseline,manifest(records),Path(root)/'report',engineering_test=True)
            report=json.loads(Path(result['path']).read_text())
            self.assertEqual(report['B0']['cohort_videos'],1)
            self.assertEqual(report['B0']['missing_count_predictions'],1)
            self.assertEqual(report['B0']['available_count_predictions'],0)
            self.assertIsNone(report['B0']['count_mae'])
            self.assertEqual(report['per_sample'][0]['B0']['input_pose_coverage']['observable_frames'],0)


if __name__=='__main__':unittest.main()
