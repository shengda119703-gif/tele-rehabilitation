"""Pure local generation orchestration tests; no Comfy submission or GPU.

The media probe is mocked where testing provenance, so fake fixture bytes are
never claimed to be playable videos or independently human-reviewed actions.
"""
import json
from contextlib import contextmanager
from fractions import Fraction
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import urllib.error

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.rehab_ml.synthetic import generation as g


class GenerationJobTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='synthetic-job-TEST-')
        self.root=Path(self.temporary.name)
        self.graph=g.workflow('TEST-conditioning','TEST-candidate',7,241,'TEST-reference.png')
        self.handle='TEST-prompt-handle'

    def tearDown(self): self.temporary.cleanup()

    def state(self,**updates):
        state=dict(name='TEST-job',workflow_sha256=g.canonical(self.graph),workflow=self.graph,
                   created_unix=1.,status='submitted',prompt_id=self.handle)
        state.update(updates)
        path=self.root/'manifests/jobs/TEST-job.json'
        g.write_new(path,state)
        return path

    def success(self):
        return {self.handle:dict(status=dict(status_str='success'),outputs={})}

    def test_same_handle_reobservation_never_submits_again(self):
        posts=[];histories=[]
        def fake_api(base,route,payload=None):
            if route=='/prompt': posts.append(payload);return dict(prompt_id=self.handle)
            if route=='/history/'+self.handle: histories.append(route);return self.success()
            self.fail('Unexpected API route: '+route)
        with patch.object(g,'api',side_effect=fake_api),patch.object(g.time,'sleep'):
            first=g.execute('TEST://comfy',self.root,'TEST-job',self.graph)
            second=g.execute('TEST://comfy',self.root,'TEST-job',self.graph)
        self.assertEqual(first['prompt_id'],second['prompt_id'])
        self.assertEqual(len(posts),1)
        self.assertGreaterEqual(len(histories),1)

    def test_observation_timeout_reconnects_same_id_while_it_is_queued(self):
        self.state(); calls=[];history_count=0
        def fake_api(base,route,payload=None):
            nonlocal history_count
            calls.append(route)
            if route=='/history/'+self.handle:
                history_count+=1
                if history_count==1: raise urllib.error.URLError(TimeoutError('TEST observation timed out'))
                if history_count==2:return {}
                return self.success()
            if route=='/queue': return dict(queue_running=[[42,self.handle,{}]],queue_pending=[])
            self.fail('A reconnect must not submit a new prompt: '+route)
        with patch.object(g,'api',side_effect=fake_api),patch.object(g.time,'sleep') as pause:
            result=g.execute('TEST://comfy',self.root,'TEST-job',self.graph)
        self.assertEqual(result['prompt_id'],self.handle)
        self.assertEqual(history_count,3)
        self.assertNotIn('/prompt',calls)
        self.assertGreaterEqual(pause.call_count,2)

    def test_unknown_submission_outcome_is_retained_and_never_auto_resubmitted(self):
        with patch.object(g,'api',side_effect=urllib.error.URLError('TEST reply lost after possible acceptance')) as api:
            with self.assertRaises(urllib.error.URLError):g.execute('TEST://comfy',self.root,'TEST-job',self.graph)
            with self.assertRaisesRegex(RuntimeError,'unknown|inspect'):
                g.execute('TEST://comfy',self.root,'TEST-job',self.graph)
        self.assertEqual(api.call_count,1)
        state=json.loads((self.root/'manifests/jobs/TEST-job.json').read_text())
        self.assertEqual(state['status'],'submission_pending')
        self.assertFalse(state.get('prompt_id'))

    def test_missing_submission_ack_handle_cannot_trigger_a_second_post(self):
        with patch.object(g,'api',return_value={}) as api:
            with self.assertRaises((KeyError,RuntimeError,ValueError)):
                g.execute('TEST://comfy',self.root,'TEST-job',self.graph)
            with self.assertRaisesRegex(RuntimeError,'unknown|inspect'):
                g.execute('TEST://comfy',self.root,'TEST-job',self.graph)
        self.assertEqual(api.call_count,1)

    def test_queue_observation_timeout_does_not_destroy_live_handle(self):
        self.state(); histories=0;calls=[]
        def fake_api(base,route,payload=None):
            nonlocal histories
            calls.append(route)
            if route=='/history/'+self.handle:
                histories+=1
                return {} if histories==1 else self.success()
            if route=='/queue':raise TimeoutError('TEST queue observation timed out')
            self.fail('Unexpected new submission: '+route)
        with patch.object(g,'api',side_effect=fake_api),patch.object(g.time,'sleep'):
            result=g.execute('TEST://comfy',self.root,'TEST-job',self.graph)
        self.assertEqual(result['prompt_id'],self.handle)
        self.assertNotIn('/prompt',calls)

    def test_missing_handle_is_terminal_evidence_for_inspection_not_resubmission(self):
        self.state(); calls=[]
        def fake_api(base,route,payload=None):
            calls.append(route)
            if route.startswith('/history/'): return {}
            if route=='/queue': return dict(queue_running=[],queue_pending=[])
            self.fail('Missing handles must not be restarted: '+route)
        with patch.object(g,'api',side_effect=fake_api),patch.object(g.time,'sleep'):
            with self.assertRaisesRegex(RuntimeError,'absent|inspect'):
                g.execute('TEST://comfy',self.root,'TEST-job',self.graph)
        state=json.loads((self.root/'manifests/jobs/TEST-job.json').read_text())
        self.assertEqual(state['prompt_id'],self.handle)
        self.assertNotIn('/prompt',calls)

    def test_failed_history_keeps_diagnostics_and_same_id_on_retry(self):
        path=self.state()
        failure={self.handle:dict(status=dict(status_str='error',messages=[['execution_error',{'TEST':'failure'}]]))}
        with patch.object(g,'api',return_value=failure) as api,patch.object(g.time,'sleep'):
            for _ in range(2):
                with self.assertRaisesRegex(RuntimeError,'failed'):
                    g.execute('TEST://comfy',self.root,'TEST-job',self.graph)
        self.assertTrue(all(call.args[1]=='/history/'+self.handle for call in api.call_args_list))
        saved=json.loads(path.read_text())
        self.assertEqual(saved['status'],'error')
        self.assertEqual(saved['history'],failure[self.handle])

    def test_different_workflow_cannot_reuse_existing_job_name(self):
        self.state();different=g.workflow('TEST-other-text','TEST-candidate',7,241,'TEST-reference.png')
        with patch.object(g,'api') as api:
            with self.assertRaisesRegex(ValueError,'different workflow'):
                g.execute('TEST://comfy',self.root,'TEST-job',different)
        api.assert_not_called()

    def test_live_observer_lock_rejects_second_owner_then_releases_on_exit(self):
        path=self.root/'manifests/generation.lock'
        with g.generation_lock(self.root):
            first=json.loads(path.read_text())
            with self.assertRaisesRegex(RuntimeError,'live generation observer'):
                with g.generation_lock(self.root):self.fail('Second live observer acquired the lock')
            self.assertEqual(json.loads(path.read_text()),first)
        self.assertFalse(path.exists())

    def test_dead_observer_lock_is_replaced_and_only_new_owned_lock_is_released(self):
        import psutil
        path=self.root/'manifests/generation.lock';g.write_new(path,dict(pid=999999,create_time=1.))
        current=SimpleNamespace(pid=12345,create_time=lambda:50.,is_running=lambda:True)
        def process(pid=None):
            if pid is None:return current
            raise psutil.NoSuchProcess(pid)
        with patch('psutil.Process',side_effect=process):
            with g.generation_lock(self.root):
                self.assertEqual(json.loads(path.read_text()),dict(pid=12345,create_time=50.))
        self.assertFalse(path.exists())

    def test_reused_pid_with_different_creation_time_is_not_a_live_old_owner(self):
        path=self.root/'manifests/generation.lock';g.write_new(path,dict(pid=12345,create_time=1.))
        current=SimpleNamespace(pid=12345,create_time=lambda:50.,is_running=lambda:True)
        with patch('psutil.Process',return_value=current):
            with g.generation_lock(self.root):self.assertEqual(json.loads(path.read_text())['create_time'],50.)
        self.assertFalse(path.exists())

    def test_reconnect_queue_only_uses_saved_root_handle_and_never_frees_or_posts(self):
        self.state();queue=dict(queue_running=[[0,self.handle,{}]],queue_pending=[])
        with patch.object(g,'api',return_value=queue) as api,patch.object(g,'execute') as execute:
            g.reconnect_queue('TEST://comfy',self.root)
        api.assert_called_once_with('TEST://comfy','/queue')
        execute.assert_called_once_with('TEST://comfy',self.root,'TEST-job',self.graph)

    def test_reconnect_queue_rejects_unowned_handle_before_even_observing_owned_work(self):
        self.state();queue=dict(queue_running=[[0,self.handle,{}]],queue_pending=[[1,'TEST-unowned',{}]])
        with patch.object(g,'api',return_value=queue) as api,patch.object(g,'execute') as execute:
            with self.assertRaisesRegex(RuntimeError,'unowned'):g.reconnect_queue('TEST://comfy',self.root)
        api.assert_called_once_with('TEST://comfy','/queue');execute.assert_not_called()


class GenerationWorkflowTests(unittest.TestCase):
    def test_timeline_decoder_version_is_provenance_but_media_pixels_and_origin_are_fixed(self):
        import copy
        original=dict(schema_version='rehab_synthetic/v1',video_sha256='a'*64,width=640,height=384,
            frame_count=2,time_basis='stream_relative_media_pts',presentation_s=[0.,1/30],
            frames=[dict(pts=0,decoded_rgb_sha256='b'*64),dict(pts=1,decoded_rgb_sha256='c'*64)],
            provenance=dict(decoder='pyav',decoder_version='19.0.1',origin='decoded_video',stream_start_pts=0,
                            stream_time_base=[1,30],video_stream_index=0,full_decode_verified=True))
        other=copy.deepcopy(original);other['provenance']['decoder_version']='16.0.1'
        self.assertTrue(g.same_media_timeline(original,other))
        for field in ('pixel','pts','origin'):
            changed=copy.deepcopy(other)
            if field=='pixel':changed['frames'][1]['decoded_rgb_sha256']='d'*64
            elif field=='pts':changed['presentation_s'][1]=.04
            else:changed['provenance']['stream_start_pts']=1
            self.assertFalse(g.same_media_timeline(original,changed),field)

    def test_native_training_shape_rate_frames_no_crop_or_interpolation(self):
        graph=g.workflow('TEST-text','TEST-native',20261019,241,'TEST-reference.png')
        self.assertEqual(graph['6']['inputs'],dict(width=640,height=384,length=241,batch_size=1))
        self.assertEqual(graph['5']['inputs']['frame_rate'],30.)
        self.assertEqual(graph['8']['inputs']['frame_rate'],30.)
        self.assertEqual(graph['8']['inputs']['frames_number'],241)
        self.assertEqual(graph['18']['inputs']['fps'],30)
        self.assertEqual(graph['18']['inputs']['crop_height'],0)
        self.assertEqual(graph['21']['inputs']['image'],'TEST-reference.png')
        self.assertEqual(graph['22']['inputs']['latent'],['6',0])
        self.assertEqual(graph['9']['inputs']['video_latent'],['22',0])
        self.assertEqual(graph['22']['inputs']['strength'],1.)
        self.assertFalse(graph['22']['inputs']['bypass'])
        kinds=[r['class_type'].lower() for r in graph.values()]
        self.assertFalse(any(any(token in kind for token in ('interpolat','repeat','upscale','resize')) for kind in kinds))

    def test_reference_preview_is_distinct_unlabelled_initial_condition(self):
        graph=g.workflow('TEST-profile-text','TEST-reference',7,97)
        self.assertNotIn('21',graph);self.assertNotIn('22',graph)
        self.assertEqual(graph['9']['inputs']['video_latent'],['6',0])
        first=g.prompt('shoulder_abduction','A',g.PROFILES['pilot01'])
        second=g.prompt('shoulder_abduction','A',g.PROFILES['pilot02'])
        self.assertNotEqual(first,second)
        self.assertIn('Stand quietly',first)
        self.assertNotIn('Raise only the anatomical LEFT arm',first)

    def test_requested_motion_prompts_have_distinct_processes(self):
        prompts={key:g.prompt('shoulder_abduction',key) for key in ('A','D','E')}
        self.assertEqual(len(set(prompts.values())),3)
        self.assertIn('back to the starting position',prompts['A'])
        self.assertIn('does not return',prompts['D'])
        self.assertIn('Both arms remain relaxed down',prompts['E'])
        self.assertTrue(all('No cuts' in text and 'no counters' in text for text in prompts.values()))


class GenerationProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='synthetic-generation-TEST-')
        self.base=Path(self.temporary.name);self.root=self.base/'dataset';self.lab=self.base/'lab'
        for folder in ('ComfyUI/input','ComfyUI/output/conditioning','ComfyUI/output/sports'):
            (self.lab/folder).mkdir(parents=True)
        g.initialize(self.root)
        weight=self.lab/'TEST-weight.bin';weight.write_bytes(b'TEST frozen generator weights')
        stat=weight.stat()
        g.write_new(self.root/'manifests/model-verification.json',dict(models=[dict(path=str(weight),
            sha256=g.digest(weight),size=stat.st_size,mtime_ns=stat.st_mtime_ns)]))
        for group in ('pilot01','pilot02'):
            image=self.root/'references'/(group+'.png');image.write_bytes(('TEST image bytes '+group).encode())
            g.write_new(self.root/'references'/(group+'.json'),dict(image_path=str(image),image_sha256=g.digest(image),
                structural_review=dict(status='usable_as_initial_condition',role='TEST-structural-screen'),
                video=dict(sha256=('a' if group=='pilot01' else 'b')*64)))
        self.jobs=[]

    def tearDown(self):self.temporary.cleanup()

    def execute(self,base,root,name,graph):
        self.jobs.append((name,graph))
        for node in graph.values():
            if node['class_type']=='LabSaveConditioning':
                (self.lab/'ComfyUI/output/conditioning'/(node['inputs']['name']+'.pt')).write_bytes(b'TEST conditioning')
            if node['class_type']=='LabSaveMP4':
                (self.lab/'ComfyUI/output/sports'/(node['inputs']['name']+'.mp4')).write_bytes(('TEST fake movie '+name).encode())
        return dict(prompt_id='TEST-'+name,status='success',created_unix=1.,finished_unix=3.)

    @staticmethod
    def probe(video,*,timeline_path=None):
        video=Path(video)
        count=97 if '_reference_' in video.name else 241
        value=dict(schema_version='rehab_synthetic/v1',video_sha256=g.digest(video),width=640,height=384,
            frame_count=count,presentation_s=[k/30 for k in range(count)],time_basis='stream_relative_media_pts')
        if timeline_path is not None:g.write_new(timeline_path,value)
        return value

    def contexts(self):
        return (patch.object(g,'execute',side_effect=self.execute),
                patch.object(g,'api',return_value={}),
                patch('tools.rehab_ml.synthetic.video.probe_video',side_effect=self.probe))

    def test_text_cache_changes_with_motion_and_same_motion_across_refs_uses_same_text(self):
        first,second,third=self.contexts()
        with first,second,third:
            a1=g.generate(self.lab,self.root,'TEST://comfy','pilot01','A')
            a2=g.generate(self.lab,self.root,'TEST://comfy','pilot02','A')
            other=g.generate(self.lab,self.root,'TEST://comfy','pilot01','E')
        self.assertEqual(a1['generation']['conditioning_key'],a2['generation']['conditioning_key'])
        self.assertEqual(a1['generation']['prompt_sha256'],a2['generation']['prompt_sha256'])
        self.assertNotEqual(a1['generation']['conditioning_key'],other['generation']['conditioning_key'])
        clips=[graph for _,graph in self.jobs if any(n['class_type']=='LabSaveMP4' for n in graph.values())]
        self.assertNotEqual(clips[0]['21']['inputs']['image'],clips[1]['21']['inputs']['image'])
        self.assertEqual(clips[0]['3']['inputs']['name'],clips[1]['3']['inputs']['name'])
        self.assertNotEqual(a1['generation']['workflow_sha256'],a2['generation']['workflow_sha256'])
        encoded=[graph for _,graph in self.jobs if any(n['class_type']=='CLIPTextEncode' for n in graph.values())]
        self.assertEqual(len(encoded),2)

    def test_target_scenario_is_never_a_human_label_or_zero_count(self):
        first,second,third=self.contexts()
        with first,second,third:
            record=g.generate(self.lab,self.root,'TEST://comfy','pilot01','E')
        self.assertEqual(record['status'],'pending')
        self.assertEqual(record['side'],'unknown')
        self.assertTrue(record['requested_scenario_is_not_a_label'])
        for field in ('observable_count','observable_count_mask','repetitions','phase_intervals','label','phase_labels','quality'):
            self.assertNotIn(field,record)
        self.assertFalse(list((self.root/'annotations').iterdir()))
        manifest=json.loads((self.root/'manifests/dataset.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['samples'][0]['status'],'pending')
        self.assertFalse(json.loads((self.root/'manifests/generation_protocol.json').read_text())['training_labels_from_prompts'])

    def test_endpoint_trial_has_own_artifact_same_seed_text_and_lineage_not_repeated_video(self):
        first,second,third=self.contexts()
        with first,second,third,patch('tools.rehab_ml.synthetic.guidance.validate_decoded_result') as decoded:
            original=g.generate(self.lab,self.root,'TEST://comfy','pilot01','A')
            guided=g.generate(self.lab,self.root,'TEST://comfy','pilot01','A',end_guide=True)
        self.assertNotEqual(original['sample_id'],guided['sample_id'])
        self.assertEqual(original['generation']['seed'],guided['generation']['seed'])
        self.assertEqual(original['generation']['conditioning_key'],guided['generation']['conditioning_key'])
        self.assertEqual(original['source_group_id'],guided['source_group_id'])
        self.assertEqual(original['lineage_ids'],guided['lineage_ids'])
        graph=self.jobs[-1][1]
        self.assertEqual(graph['23']['inputs']['frame_idx'],240)
        self.assertEqual(graph['10']['inputs']['positive'],['23',0])
        self.assertEqual(graph['19']['inputs']['samples'],['24',2])
        decoded.assert_called_once()
        self.assertTrue(guided['generation']['guidance']['experimental'])
        self.assertFalse(guided['generation']['guidance']['action_completion_guaranteed'])
        self.assertEqual(guided['status'],'pending')

    def test_endpoint_guidance_cannot_be_used_without_a_reference(self):
        with patch.object(g,'api') as api,patch.object(g,'execute') as execute:
            with self.assertRaisesRegex(ValueError,'screened reference'):
                g.generate(self.lab,self.root,'TEST://comfy','pilot01',end_guide=True)
        api.assert_not_called();execute.assert_not_called()

    def test_prompt_version_is_part_of_conditioning_cache_identity(self):
        first,second,third=self.contexts()
        with first,second,third:
            original=g.generate(self.lab,self.root,'TEST://comfy','pilot01','A')
            with patch.object(g,'VERSION','TEST-new-prompt-version'):
                changed=g.generate(self.lab,self.root,'TEST://comfy','pilot02','A')
        self.assertEqual(original['generation']['prompt'],changed['generation']['prompt'])
        self.assertNotEqual(original['generation']['conditioning_key'],changed['generation']['conditioning_key'])

    def test_existing_completed_candidate_is_reused_without_any_new_submit(self):
        first,second,third=self.contexts()
        with first,second,third:
            previous=g.generate(self.lab,self.root,'TEST://comfy','pilot01','A')
        with patch.object(g,'api') as api,patch.object(g,'execute') as execute,patch('tools.rehab_ml.synthetic.video.probe_video',side_effect=self.probe) as probe:
            recovered=g.generate(self.lab,self.root,'TEST://comfy','pilot01','A')
        self.assertEqual(recovered,previous)
        api.assert_not_called();execute.assert_not_called()
        probe.assert_called_once_with(previous['video']['path'])

    def test_completed_candidate_prompt_version_change_is_rejected_before_any_submit(self):
        first,second,third=self.contexts()
        with first,second,third:
            record=g.generate(self.lab,self.root,'TEST://comfy','pilot01','A')
        original=Path(record['video']['path']).read_bytes()
        with patch.object(g,'VERSION','TEST-different-version'),patch.object(g,'api') as api,patch.object(g,'execute') as execute:
            with self.assertRaisesRegex(ValueError,'changed|revision'):
                g.generate(self.lab,self.root,'TEST://comfy','pilot01','A')
        api.assert_not_called();execute.assert_not_called()
        self.assertEqual(Path(record['video']['path']).read_bytes(),original)

    def test_completed_candidate_changed_source_bytes_cannot_be_silently_reused(self):
        first,second,third=self.contexts()
        with first,second,third:
            record=g.generate(self.lab,self.root,'TEST://comfy','pilot01','A')
        Path(record['video']['path']).write_bytes(b'TEST changed original movie bytes')
        with patch.object(g,'api') as api,patch.object(g,'execute') as execute:
            with self.assertRaisesRegex(ValueError,'changed|revision'):
                g.generate(self.lab,self.root,'TEST://comfy','pilot01','A')
        api.assert_not_called();execute.assert_not_called()

    def test_completed_candidate_self_consistent_forged_timeline_is_rejected_by_probe(self):
        first,second,third=self.contexts()
        with first,second,third:
            record=g.generate(self.lab,self.root,'TEST://comfy','pilot01','A')
        timeline=Path(record['video']['timeline_path']);saved=json.loads(timeline.read_text())
        saved['presentation_s'][3]+=.001;timeline.write_text(json.dumps(saved),encoding='utf-8')
        record_path=self.root/'manifests'/(record['sample_id']+'.json')
        record['video']['timeline_sha256']=g.digest(timeline);record_path.write_text(json.dumps(record),encoding='utf-8')
        with patch.object(g,'api') as api,patch.object(g,'execute') as execute,patch('tools.rehab_ml.synthetic.video.probe_video',side_effect=self.probe):
            with self.assertRaisesRegex(ValueError,'timeline changed'):
                g.generate(self.lab,self.root,'TEST://comfy','pilot01','A')
        api.assert_not_called();execute.assert_not_called()

    def test_saved_timeline_survives_interrupted_dataset_publish_and_is_recovered(self):
        real_replace=g.replace_json
        def interrupt(path,value):
            if path==self.root/'manifests/dataset.json': raise InterruptedError('TEST crash after timeline publication')
            return real_replace(path,value)
        first,second,third=self.contexts()
        with first,second,third,patch.object(g,'replace_json',side_effect=interrupt):
            with self.assertRaises(InterruptedError):g.generate(self.lab,self.root,'TEST://comfy','pilot01','A')
        paths=list((self.root/'manifests/timelines').glob('*.json'));self.assertEqual(len(paths),1)
        original=paths[0].read_bytes()
        first,second,third=self.contexts()
        with first,second,third:
            result=g.generate(self.lab,self.root,'TEST://comfy','pilot01','A')
        self.assertEqual(paths[0].read_bytes(),original)
        manifest=json.loads((self.root/'manifests/dataset.json').read_text(encoding='utf-8'))
        self.assertEqual([r['sample_id'] for r in manifest['samples']],[result['sample_id']])
        sampled=[(name,g.canonical(graph)) for name,graph in self.jobs if '18' in graph]
        self.assertEqual(len(set(sampled)),1)

    def test_existing_dataset_row_survives_interruption_before_final_result_without_duplicate(self):
        real_write=g.write_new
        def interrupt(path,value):
            if path.parent==self.root/'manifests' and path.name.startswith('rehab_'):
                raise InterruptedError('TEST crash after dataset row publication')
            return real_write(path,value)
        first,second,third=self.contexts()
        with first,second,third,patch.object(g,'write_new',side_effect=interrupt):
            with self.assertRaises(InterruptedError):g.generate(self.lab,self.root,'TEST://comfy','pilot01','D')
        first,second,third=self.contexts()
        with first,second,third:
            result=g.generate(self.lab,self.root,'TEST://comfy','pilot01','D')
        manifest=json.loads((self.root/'manifests/dataset.json').read_text(encoding='utf-8'))
        self.assertEqual(len(manifest['samples']),1)
        self.assertEqual(manifest['samples'][0],result)

    def test_reference_attempt_changes_image_identity_and_motion_attempt_is_separate(self):
        image=self.root/'references/pilot01_r02.png';image.write_bytes(b'TEST second reference pixels')
        g.write_new(self.root/'references/pilot01_r02.json',dict(image_path=str(image),image_sha256=g.digest(image),
            structural_review=dict(status='usable_as_initial_condition',role='TEST-structural-screen'),video=dict(sha256='c'*64)))
        first,second,third=self.contexts()
        with first,second,third:
            initial=g.generate(self.lab,self.root,'TEST://comfy','pilot01','A',reference_attempt=1)
            other_ref=g.generate(self.lab,self.root,'TEST://comfy','pilot01','A',reference_attempt=2)
            other_motion=g.generate(self.lab,self.root,'TEST://comfy','pilot01','A',attempt=2,reference_attempt=1)
        self.assertEqual(len({r['sample_id'] for r in (initial,other_ref,other_motion)}),3)
        self.assertEqual(initial['generation']['seed'],other_ref['generation']['seed'])
        self.assertEqual(other_motion['generation']['seed']-initial['generation']['seed'],10000)
        self.assertIn('_r02_ref',other_motion['sample_id'])
        self.assertNotEqual(initial['generation']['workflow_sha256'],other_ref['generation']['workflow_sha256'])
        self.assertEqual(initial['generation']['conditioning_key'],other_ref['generation']['conditioning_key'])
        self.assertEqual(initial['generation']['conditioning_key'],other_motion['generation']['conditioning_key'])
        self.assertEqual(initial['source_group_id'],other_ref['source_group_id'])
        self.assertIn('identity:pilot01',other_ref['lineage_ids'])
        for record in (initial,other_ref,other_motion):self.assertEqual(record['status'],'pending')

    def test_reference_r02_and_existing_png_recover_without_overwriting_initial_image(self):
        import numpy as np
        from PIL import Image
        image=Image.new('RGB',(640,384),(40,80,120))
        frame=SimpleNamespace(pts=0,time_base=Fraction(1,30),to_image=lambda:image,
            to_ndarray=lambda **kwargs:np.asarray(image))
        @contextmanager
        def fake_open(*args,**kwargs):yield SimpleNamespace(decode=lambda **kwargs:iter([frame]))
        # Simulate an interrupted r02 reference run after PNG was saved but
        # before the immutable record. It must not replace the original image.
        before=(self.root/'references/pilot01.png').read_bytes()
        image.save(self.root/'references/pilot01_r02.png')
        saved=(self.root/'references/pilot01_r02.png').read_bytes()
        first,second,third=self.contexts()
        with first,second,third,patch('av.open',side_effect=fake_open):
            result=g.generate(self.lab,self.root,'TEST://comfy','pilot01',attempt=2)
        self.assertEqual(Path(result['image_path']).name,'pilot01_r02.png')
        self.assertEqual(Path(result['image_path']).read_bytes(),saved)
        self.assertEqual((self.root/'references/pilot01.png').read_bytes(),before)
        self.assertTrue((self.root/'references/pilot01_r02.json').is_file())
        self.assertNotEqual(result['generation']['prompt'],g.prompt('shoulder_abduction','A',g.PROFILES['pilot01']))
        self.assertEqual(result['structural_review']['status'],'pending')

    def test_unreviewed_reference_cannot_proceed_to_motion_sampling(self):
        reference=self.root/'references/pilot01.json'
        data=json.loads(reference.read_text());data['structural_review']['status']='pending'
        reference.write_text(json.dumps(data),encoding='utf-8')
        first,second,third=self.contexts()
        with first,second,third:
            with self.assertRaisesRegex(ValueError,'structural'):
                g.generate(self.lab,self.root,'TEST://comfy','pilot01','A')
        self.assertEqual(self.jobs,[])


if __name__=='__main__':unittest.main()
