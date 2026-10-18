"""CPU-media CLI gates; no real pose inference, training, or human references."""
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import av
import numpy as np

from tools.rehab_ml.common import canonical_hash,file_hash,write_json
from tools.rehab_ml.synthetic import contracts as c
from tools.rehab_ml.synthetic import experiment as e
from tools.rehab_ml.synthetic import generation,video


def tiny_video(path):
    path.parent.mkdir(parents=True,exist_ok=True)
    with av.open(str(path),'w') as container:
        stream=container.add_stream('libx264',rate=30)
        stream.width=64;stream.height=64;stream.pix_fmt='yuv420p'
        stream.options={'preset':'ultrafast','crf':'18'}
        for i in range(9):
            image=np.zeros((64,64,3),np.uint8);image[:,:,1]=30+i*10
            frame=av.VideoFrame.from_ndarray(image,format='rgb24')
            for packet in stream.encode(frame):container.mux(packet)
        for packet in stream.encode():container.mux(packet)


class SyntheticExperimentTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='synthetic-experiment-TEST-')
        self.root=Path(self.temporary.name);generation.initialize(self.root)

    def tearDown(self):self.temporary.cleanup()

    def pending_source(self):
        sid='TEST-pending';source=self.root/'raw'/str(sid+'.mp4');tiny_video(source)
        index=self.root/'manifests/timelines'/str(sid+'.json')
        timeline=video.probe_video(source,timeline_path=index)
        sample=dict(sample_id=sid,source_group_id='TEST-person',reference_group_id='TEST-reference',
            lineage_ids=['TEST-person'],split='train',stage='pilot',scenario='A',exercise_id='shoulder_abduction',
            side='unknown',view='frontal',status='pending',video=dict(path=str(source),sha256=file_hash(source),
                width=64,height=64,frame_count=9,timeline_path=str(index),timeline_sha256=file_hash(index)),
            generation=dict(prompt_version='TEST-only',seed=7,model_sha256='a'*64,workflow_sha256='b'*64,prompt_sha256='c'*64))
        write_json(self.root/'manifests/dataset.json',dict(schema_version=c.SCHEMA_VERSION,dataset_id='TEST-only',split_freeze=None,samples=[sample]))
        return sample,timeline

    @staticmethod
    def fake_extract(source,manifest,output,*,sample_id,backend,timeout_s):
        output=Path(output);output.mkdir(parents=True,exist_ok=False)
        write_json(output/'frame-manifest.json',manifest)
        result=dict(schema_version='rehab_synthetic_pose/v1',status='completed',sample_id=sample_id,backend=backend,
            source_sha256=file_hash(source),source_size=manifest['source_size'],model=dict(sha256='f'*64),
            frame_manifest_sha256=canonical_hash(manifest),frame_manifest_path=str(output/'frame-manifest.json'),
            frames=[dict(frame_index=r['frame_index'],pts=r['pts'],time_base=r['time_base'],timestamp_s=r['timestamp_s'],
                pose_detected=False,track_id=None,joints={}) for r in manifest['frames']],is_ground_truth=False)
        write_json(output/'pose.json',result)
        return dict(result,result_path=str(output/'pose.json'),result_sha256=file_hash(output/'pose.json'))

    @staticmethod
    def formal_snapshot():
        """Pure TEST contract objects; no file or genuine human label is made."""
        groups={'TEST-group-'+str(i):'train' if i<6 else 'val' if i<8 else 'test' for i in range(10)}
        rows=[];timelines={};annotations=[]
        for group,split in groups.items():
            for scenario in 'ABCDEF':
                sid=group+'-'+scenario
                digest=lambda suffix:hashlib.sha256((sid+suffix).encode()).hexdigest()
                row=dict(sample_id=sid,source_group_id=group,reference_group_id='TEST-ref-'+group,
                    lineage_ids=['TEST-identity-'+group],split=split,stage='formal',scenario=scenario,
                    exercise_id='shoulder_abduction',side='left',view='frontal',status='accepted',
                    video=dict(path=sid+'.mp4',sha256=digest('video'),width=64,height=64,frame_count=5,
                        timeline_path=sid+'-pts.json',timeline_sha256=digest('timeline')),
                    generation=dict(prompt_version='TEST-only',seed=7,model_sha256=digest('model'),
                        workflow_sha256=digest('workflow'),prompt_sha256=digest('prompt')))
                acceptance=dict(reviewer_id='TEST-placeholder-not-a-real-review',reviewer_role='human_operator',
                    full_video_watched=True,reviewed_video_sha256=row['video']['sha256'],reviewed_frame_count=5,watched_at='TEST-ONLY')
                row['acceptance']=acceptance
                timeline=dict(schema_version=c.SCHEMA_VERSION,video_sha256=row['video']['sha256'],frame_count=5,
                    width=64,height=64,time_basis='stream_relative_media_pts',presentation_s=[i/30 for i in range(5)],
                    provenance=dict(origin='decoded_video',decoder='TEST-engineered-contract-object',video_stream_index=0,stream_start_time_s=0.))
                annotation=c.prepare_review(row,timeline,reviewer_id=acceptance['reviewer_id'])
                annotation.update(side='left',side_mask=True,observable_count=0,observable_count_mask=True,
                    review={k:v for k,v in acceptance.items() if k not in ('reviewer_id','reviewer_role')},
                    phase_intervals=[dict(phase='rest_or_other',start_s=0.,end_s=4/30,label_mask=True)])
                rows.append(row);timelines[sid]=timeline;annotations.append(annotation)
        manifest=dict(schema_version=c.SCHEMA_VERSION,dataset_id='TEST-only-contract-not-media',samples=rows,split_freeze=c.freeze_splits(groups))
        return dict(manifest=manifest,timelines=timelines,annotations=annotations)

    def test_validate_empty_pilot_is_not_a_formal_dataset_or_training_claim(self):
        output=io.StringIO()
        with redirect_stdout(output):code=e.main(['validate','--root',str(self.root)])
        self.assertEqual(code,0)
        result=json.loads(output.getvalue());self.assertEqual(result['sample_count'],0)
        self.assertEqual(result['eligible_annotations'],0);self.assertFalse(result['training_performed'])
        self.assertFalse(result['real_pts_verified']);self.assertEqual(result['verified_video_count'],0)
        self.assertEqual(result['scenario_coverage_basis'],'requested_generation_targets_only')
        self.assertEqual(result['observed_scenario_coverage'],'not_established_by_this_command')
        with redirect_stdout(io.StringIO()):code=e.main(['validate','--root',str(self.root),'--require-formal-complete'])
        self.assertEqual(code,2)

    def test_train_without_formal60_human_reference_rejects_before_optimizer_or_output(self):
        self.pending_source()
        with patch.object(e.temporal,'train') as trainer,redirect_stdout(io.StringIO()):
            code=e.main(['train','--root',str(self.root),'--run-id','TEST-train'])
        self.assertEqual(code,2);trainer.assert_not_called()
        self.assertFalse((self.root/'runs/TEST-train').exists())

    def test_existing_run_is_rejected_before_reading_or_changing_its_artifacts(self):
        target=self.root/'runs/TEST-used';target.mkdir()
        marker=target/'TEST-original.txt';marker.write_text('retained',encoding='utf-8')
        with patch.object(e.review,'load_reviewed') as loader:
            with self.assertRaisesRegex(ValueError,'no_overwrite'):e.extract(self.root,'TEST-used')
            with self.assertRaisesRegex(ValueError,'no_overwrite'):e.train(self.root,'TEST-used')
        loader.assert_not_called();self.assertEqual(marker.read_text(),'retained')

    def test_output_path_traversal_is_rejected_before_sources_or_compute(self):
        with patch.object(e.review,'load_reviewed') as loader,redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit):e.main(['extract','--root',str(self.root),'--run-id','../outside'])
        loader.assert_not_called()

    def test_pending_sources_extract_both_backends_on_same_actual_frames_without_gt(self):
        sample,_=self.pending_source()
        with patch.object(e.pose,'extract_pose',side_effect=self.fake_extract) as extractor:
            result=e.extract(self.root,'TEST-extract',backend='all')
        self.assertEqual(result['status'],'completed');self.assertEqual(extractor.call_count,2)
        calls=extractor.call_args_list
        self.assertEqual(canonical_hash(calls[0].args[1]),canonical_hash(calls[1].args[1]))
        self.assertEqual({r.kwargs['backend'] for r in calls},{'yolo17','mediapipe33'})
        self.assertFalse(result['labels_generated']);self.assertFalse(result['training_performed'])
        self.assertFalse(list((self.root/'annotations').iterdir()))
        for backend in e.BACKENDS:
            target=self.root/('pose_'+backend)/sample['sample_id']/'pose.json'
            self.assertTrue(target.is_file())
            base=json.loads((Path(result['run_dir'])/('baseline_'+backend+'.json')).read_text())
            self.assertIsNone(base['samples'][0]['completed_count'])
            self.assertEqual(base['samples'][0]['reason'],'analyzed_anatomical_side_not_predeclared')

    def test_explicit_analysis_side_runs_B0_but_empty_pose_does_not_become_zero(self):
        self.pending_source()
        with patch.object(e.pose,'extract_pose',side_effect=self.fake_extract):
            result=e.extract(self.root,'TEST-side',backend='yolo17',baseline_side='left')
        base=json.loads((Path(result['run_dir'])/'baseline_yolo17.json').read_text())
        self.assertEqual(base['samples'][0]['status'],'unavailable')
        self.assertIsNone(base['samples'][0]['completed_count'])
        self.assertEqual(base['samples'][0]['coverage']['observable_frames'],0)

    def test_existing_pose_requires_explicit_reuse_before_any_new_inference(self):
        sample,_=self.pending_source()
        (self.root/'pose_yolo17'/sample['sample_id']).mkdir(parents=True)
        with patch.object(e.pose,'extract_pose') as extractor:
            with self.assertRaisesRegex(ValueError,'reuse_existing'):
                e.extract(self.root,'TEST-no-overwrite',backend='all')
        extractor.assert_not_called();self.assertFalse((self.root/'runs/TEST-no-overwrite').exists())

    def test_actual_video_hash_change_rejects_extract_before_inference(self):
        sample,_=self.pending_source();Path(sample['video']['path']).write_bytes(b'TEST corrupt original')
        with patch.object(e.pose,'extract_pose') as extractor:
            with self.assertRaisesRegex(ValueError,'hash_changed'):e.extract(self.root,'TEST-changed')
        extractor.assert_not_called()

    def test_default_training_config_is_the_versioned_CPU_configuration(self):
        args=e.parser().parse_args(['train','--run-id','TEST-run'])
        self.assertEqual(args.config,e.DEFAULT_CONFIG)
        config=json.loads(args.config.read_text())
        self.assertEqual(config['device'],'cpu');self.assertEqual(config['hz'],15.)

    def test_formal_gate_requires_all60_qualified_references_not_only_source_count(self):
        fixture=self.formal_snapshot()
        sources,annotations,audit=e._formal_sources(fixture)
        self.assertEqual(len(sources),60);self.assertEqual(len(annotations),60)
        self.assertEqual(audit['scenario_coverage_basis'],'requested_generation_targets_only')
        self.assertEqual(audit['observed_scenario_coverage'],'not_established_by_this_command')
        fixture['annotations'].pop()
        with self.assertRaisesRegex(ValueError,'sixty_formal_sources_require_saved_human'):
            e._formal_sources(fixture)

    def test_ai_draft_and_count_only_reference_cannot_unlock_phase_training(self):
        fixture=self.formal_snapshot();fixture['annotations'][-1]['reviewer_role']='ai_draft'
        with self.assertRaisesRegex(ValueError,'sixty_formal_sources_require_saved_human'):
            e._formal_sources(fixture)
        fixture=self.formal_snapshot();fixture['annotations'][-1]['phase_intervals']=[]
        with self.assertRaisesRegex(ValueError,'phase_intervals_not_count_only'):
            e._formal_sources(fixture)

    def test_P0_gate_rejects_other_exercise_or_side_camera_without_silently_filtering(self):
        for field,value in (('exercise_id','elbow_flexion'),('view','sagittal')):
            fixture=self.formal_snapshot();fixture['manifest']['samples'][-1][field]=value
            with self.assertRaisesRegex(ValueError,'P0_frontal_shoulder_abduction_only'):
                e._formal_sources(fixture)
        fixture=self.formal_snapshot();fixture['manifest']['samples'][-1]['view']='front'
        self.assertEqual(len(e._formal_sources(fixture)[0]),60)

    def test_failed_backend_outputs_are_retained_but_CLI_returns_failure(self):
        self.pending_source()
        def failed(*args,**kwargs):
            result=self.fake_extract(*args,**kwargs);result['status']='failed'
            write_json(Path(result['result_path']),{k:v for k,v in result.items() if k not in ('result_path','result_sha256')})
            return result
        output=io.StringIO()
        with patch.object(e.pose,'extract_pose',side_effect=failed),redirect_stdout(output):
            code=e.main(['extract','--root',str(self.root),'--run-id','TEST-failed','--backend','yolo17'])
        self.assertEqual(code,2)
        result=json.loads(output.getvalue());self.assertEqual(result['status'],'failed')
        self.assertTrue((self.root/'runs/TEST-failed/result.json').exists())
        baseline=json.loads((self.root/'runs/TEST-failed/baseline_yolo17.json').read_text())
        self.assertIsNone(baseline['samples'][0]['completed_count'])


if __name__=='__main__':unittest.main()
