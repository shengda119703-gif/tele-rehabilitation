"""Formal orchestration TEST fixtures; CPU media, mocked models/API, no GPU."""
from contextlib import redirect_stdout
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

import av
import numpy as np

from tools.rehab_ml.synthetic import contracts as c,formal_control as fc,formal_generation as f,formal_plan as fp,generation as g


def encode(path,frames):
    path.parent.mkdir(parents=True,exist_ok=True)
    with av.open(str(path),'w') as container:
        stream=container.add_stream('libx264',rate=30);stream.width=640;stream.height=384;stream.pix_fmt='yuv420p'
        stream.options={'preset':'ultrafast','crf':'18'}
        image=np.zeros((384,640,3),np.uint8);image[:]=[50,90,130 if frames==97 else 170]
        for i in range(frames):
            frame=av.VideoFrame.from_ndarray(image,format='rgb24')
            for packet in stream.encode(frame):container.mux(packet)
        for packet in stream.encode():container.mux(packet)


class FormalGenerationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='formal-generation-TEST-');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'dataset';self.lab=Path(self.temp.name)/'lab';g.initialize(self.root)
        for path in ('ComfyUI/input','ComfyUI/output/sports','ComfyUI/output/conditioning'):(self.lab/path).mkdir(parents=True)
        self.model_receipt=self.root/'manifests/TEST-model.json';g.write_new(self.model_receipt,dict(models=[dict(sha256='a'*64)]))
        self.config=dict(reference_spec=f.reference_recipe_spec(),control_model_receipt=dict(path='TEST-no-real-model',sha256='d'*64),
            implementations=[dict(path=str(Path(f.__file__).with_name(name)),sha256=g.digest(Path(f.__file__).with_name(name)))
                for name in ('generation.py','formal_generation.py','formal_plan.py','formal_control.py','pose_guidance.py',
                             'control.py','motion.py','video.py','pose.py')])
        self.config_path=self.root/'manifests/TEST-config.json';g.write_new(self.config_path,self.config)
        self.recipe=f.build_generation_recipe(model_receipt=dict(path=str(self.model_receipt),sha256=g.digest(self.model_receipt),model_sha256='a'*64),
            config=dict(path=str(self.config_path),sha256=g.digest(self.config_path)),seed=42)
        groups={'TEST-formal'+str(i):'train' if i<6 else 'val' if i<8 else 'test' for i in range(10)}
        self.request=dict(cohort12=['TEST-pilot'+str(i)+'-'+s for i in range(4) for s in 'ADE'],
            profiles={group:dict(prompt='TEST fictional reference '+group,identity_ids=[group],lineage_ids=[]) for group in groups},
            group_splits=groups,generation_recipe=self.recipe)
        self.plan=fp.draft_formal_plan(**self.request)
        self.loaded=dict(plan=self.plan,split_freeze=self.plan['split_freeze'],registry=fp.validate_registry(self.plan,[]),
                         debug_sources=[],pilot_audit=dict(TEST='loader is mocked, no genuine human signs'),frozen_sha='f'*64)
        self.models=dict(model_sha256='a'*64,model_receipt_sha256=g.digest(self.model_receipt),
            pose_lora_sha256=f.OFFICIAL_EVIDENCE['model_sha256'],control_model_receipt_path='TEST-model-receipt',
            control_model_receipt_sha256='d'*64)
        self.calls=[]

    def execute(self,base,root,name,graph):
        self.calls.append((name,copy.deepcopy(graph)))
        if '103' in graph:
            (self.lab/'ComfyUI/output/conditioning'/(name+'.pt')).write_bytes(b'TEST mocked CLIP output, not a real embedding')
        else:encode(self.lab/'ComfyUI/output/sports'/(name+'.mp4'),graph['6']['inputs']['length'])
        job=dict(name=name,prompt_id='TEST-'+name,status='success',workflow=copy.deepcopy(graph),workflow_sha256=g.canonical(graph),
                 created_unix=1.,finished_unix=2.,history=dict(status=dict(status_str='success')))
        g.immutable_json(root/'manifests/jobs'/(name+'.json'),job)
        return job

    def contexts(self):
        return (patch.object(fp,'load_frozen_plan',return_value=self.loaded),patch.object(f,'_verify_models',return_value=self.models),
                patch.object(g,'api',return_value={}),patch.object(g,'reconnect_queue'),patch.object(g,'execute',side_effect=self.execute))

    def reference(self):
        a,b,d,e,z=self.contexts()
        with a,b,d,e,z:
            record=f.generate_reference(self.lab,self.root,'TEST://comfy','TEST-formal6')
            path=Path(record['image_path']).with_suffix('.json')
            screen=f.record_reference_screen(self.root,path,status='usable_as_initial_condition',reviewer_role='ai_structural_screen',
                                              reviewer_id='TEST structural fixture, not human GT')
        return record,path,Path(screen['receipt_path'])

    def control(self,reference,scenario='A'):
        group=reference['source_group_id'];control_id=group+':control:'+scenario+':r01:'+'e'*12
        pose_id=group+':pose:r01:'+'b'*12
        record=dict(video_sha256='e'*64,lineage_ids=['TEST-specific-control-source'])
        metadata=dict(registry_entry_id=control_id,receipt_sha256='c'*64,controller_is_ground_truth_for_output=False,creates_human_annotations=False)
        entries=[fp.source_registry_entry(self.plan,entry_id=pose_id,source_group_id=group,kind='pose',
            assets=dict(pose_prediction='b'*64),parents=[reference['registry_entry_id']]),
            fp.source_registry_entry(self.plan,entry_id=control_id,source_group_id=group,kind='control',
            assets=dict(control_video='e'*64,control_trajectory='c'*64),parents=[pose_id])]
        return record,'TEST-control.mp4',metadata,entries

    def test_pure_recipe_names_templates_and_only_declared_bindings_change(self):
        for scenario in 'ABCDEF':
            spec=self.recipe['scenarios'][scenario];frozen=copy.deepcopy(spec)
            bindings=dict(job_name='TEST-job',conditioning_key='TEST-key',seed=43,reference_file='TEST-ref.png',control_file='TEST-control.mp4')
            graph=f.bind_workflow(spec,bindings);audit=f.validate_execution_graph(spec,graph,bindings)
            self.assertEqual(spec,frozen);self.assertNotEqual(audit['workflow_template_sha256'],audit['workflow_sha256'])
            self.assertEqual('36' in graph,scenario!='D')
            graph['18']['inputs']['crop_height']=64
            with self.assertRaisesRegex(ValueError,'outside_declared'):f.validate_execution_graph(spec,graph,bindings)
        self.assertEqual(fc.attempt_seed(self.plan['slots'][0]['seed'],1),self.plan['slots'][0]['seed'])
        self.assertNotEqual(fc.attempt_seed(self.plan['slots'][0]['seed'],2),self.plan['slots'][0]['seed'])

    def test_missing_actual_human_freeze_blocks_reference_and_motion_before_any_Comfy_API(self):
        with patch.object(g,'api') as api,patch.object(g,'execute') as execute,patch.object(g,'reconnect_queue') as queue:
            for call in (lambda:f.generate_reference(self.lab,self.root,'TEST://comfy','TEST-formal6'),
                         lambda:f.generate_motion(self.lab,self.root,'TEST://comfy','TEST-formal6','A',
                            reference_record_path='missing',reference_screen_path='missing',control_path='missing')):
                with self.assertRaises(ValueError):call()
        api.assert_not_called();execute.assert_not_called();queue.assert_not_called()

    def test_actual_native_reference_raw_and_resume_keep_split_originals_and_no_GT(self):
        reference,path,screen=self.reference();self.assertEqual(reference['split'],'val');self.assertEqual(reference['reference_attempt'],1)
        self.assertEqual(reference['video']['frame_count'],97)
        verified=self.control(reference);a,b,d,e,z=self.contexts()
        with a,b,d,e,z,patch.object(fc,'prepare_control',return_value=copy.deepcopy(verified)) as prepare:
            first=f.generate_motion(self.lab,self.root,'TEST://comfy','TEST-formal6','A',reference_record_path=path,
                reference_screen_path=screen,control_path='TEST-explicit-control')
            requests=len(self.calls)
            second=f.generate_motion(self.lab,self.root,'TEST://comfy','TEST-formal6','A',reference_record_path=path,
                reference_screen_path=screen,control_path='TEST-explicit-control')
        self.assertEqual(first,second);self.assertEqual(len(self.calls),requests);self.assertEqual(prepare.call_count,4)
        self.assertEqual((first['stage'],first['split'],first['status']),('formal','val','pending'))
        self.assertEqual(first['video']['frame_count'],241);self.assertEqual(first['side'],'unknown')
        self.assertFalse(first['creates_labels']);self.assertNotIn('observable_count',first)
        self.assertFalse(first['generation']['guidance']['output_action_completion_guaranteed'])
        self.assertEqual(first['generation']['generation_wall_seconds'],1.)
        self.assertTrue(first['generation']['prompt_id'].startswith('TEST-formal_'))
        self.assertTrue(Path(first['generation']['workflow_job_path']).is_file())
        manifest=c._read_json(self.root/'manifests/dataset.json');self.assertEqual(c.validate_manifest(manifest)['sample_count'],1)
        self.assertEqual(manifest['split_freeze'],self.plan['split_freeze'])
        self.assertFalse(list((self.root/'annotations').iterdir()))

    def test_unscreened_or_changed_reference_rejects_before_control_or_API(self):
        reference,path,screen=self.reference();changed=c._read_json(screen);changed['status']='rejected'
        screen.write_text(json.dumps(changed),encoding='utf-8');a,b,d,e,z=self.contexts()
        with a,b,d as api,e as queue,z as execute,patch.object(fc,'prepare_control') as control:
            with self.assertRaisesRegex(ValueError,'bound_structural_screen'):
                f.generate_motion(self.lab,self.root,'TEST://comfy','TEST-formal6','A',reference_record_path=path,
                    reference_screen_path=screen,control_path='TEST-explicit')
        api.assert_not_called();queue.assert_not_called();execute.assert_not_called();control.assert_not_called()

    def test_pending_control_origin_leak_is_rejected_before_queue_text_or_free(self):
        reference,path,screen=self.reference();verified=self.control(reference)
        self.loaded['debug_sources']=[dict(sample_id='TEST-debug',source_group_id='TEST-debug',reference_group_id='TEST-debug',
            stage='pilot',split='train',lineage_ids=['TEST-debug'],video=dict(sha256='a'*64),
            generation=dict(pose_control=dict(trajectory_sha256='c'*64)))]
        a,b,d,e,z=self.contexts()
        with a,b,d as api,e as queue,z as execute,patch.object(fc,'prepare_control',return_value=verified):
            with self.assertRaisesRegex(ValueError,'cross_split'):
                f.generate_motion(self.lab,self.root,'TEST://comfy','TEST-formal6','A',reference_record_path=path,
                    reference_screen_path=screen,control_path='TEST-explicit')
        api.assert_not_called();queue.assert_not_called();execute.assert_not_called()

    def test_unknown_raw_submission_is_not_automatically_posted_twice(self):
        reference,path,screen=self.reference();verified=self.control(reference)
        actual_execute=g.execute
        def execute(base,root,name,graph):
            return self.execute(base,root,name,graph) if '103' in graph else actual_execute(base,root,name,graph)
        def api_reply(base,route,payload=None):
            if route=='/prompt':raise urllib.error.URLError('TEST lost acknowledgment')
            return {}
        with patch.object(fp,'load_frozen_plan',return_value=self.loaded),patch.object(f,'_verify_models',return_value=self.models),\
                patch.object(fc,'prepare_control',return_value=verified),patch.object(g,'reconnect_queue'),\
                patch.object(g,'execute',side_effect=execute),patch.object(g,'api',side_effect=api_reply) as api:
            with self.assertRaises(urllib.error.URLError):
                f.generate_motion(self.lab,self.root,'TEST://comfy','TEST-formal6','A',reference_record_path=path,
                    reference_screen_path=screen,control_path='TEST-explicit')
            with self.assertRaisesRegex(RuntimeError,'unknown|inspect'):
                f.generate_motion(self.lab,self.root,'TEST://comfy','TEST-formal6','A',reference_record_path=path,
                    reference_screen_path=screen,control_path='TEST-explicit')
        self.assertEqual(sum(call.args[1]=='/prompt' for call in api.call_args_list),1)
        self.assertEqual(c._read_json(self.root/'manifests/dataset.json')['samples'],[])

    def test_wrong_same_basename_implementation_receipt_and_model_bytes_block_API(self):
        other=Path(self.temp.name)/'other';other.mkdir();fake=other/'generation.py';fake.write_text('TEST wrong source copy')
        changed=copy.deepcopy(self.config)
        changed['implementations']=[row for row in changed['implementations'] if Path(row['path']).name!='generation.py']
        changed['implementations'].append(dict(path=str(fake),sha256=g.digest(fake)))
        self.config_path.write_text(json.dumps(changed),encoding='utf-8')
        changed_recipe=f.build_generation_recipe(model_receipt={**self.recipe['model_receipt'],'model_sha256':'a'*64},
            config=dict(path=str(self.config_path),sha256=g.digest(self.config_path)),seed=42)
        self.request['generation_recipe']=changed_recipe;self.loaded['plan']=fp.draft_formal_plan(**self.request)
        with patch.object(fp,'load_frozen_plan',return_value=self.loaded),patch.object(g,'api') as api:
            with self.assertRaisesRegex(ValueError,'actual_generation_module_paths'):f._preflight(self.root,self.lab)
        api.assert_not_called()
        lock=self.lab/'models.lock.json';g.write_new(lock,[])
        with patch.object(fp,'load_frozen_plan',return_value=self.loaded),patch.object(g,'api') as api:
            with self.assertRaisesRegex(ValueError,'actual_generator_lock'):
                f._verify_models(self.root,self.lab,self.loaded,self.config)
        api.assert_not_called()

    def test_full_actual_model_lock_paths_and_base_bytes_then_pose_bytes_are_required(self):
        paths=['diffusion_models/ltx-2-19b-distilled_Q4_K_M.gguf','text_encoders/gemma-3-12b-it-Q4_K_M.gguf',
            'text_encoders/ltx-2-19b-embeddings_connector_distill_bf16.safetensors',
            'vae/LTX2_video_vae_bf16.safetensors','vae/LTX2_audio_vae_bf16.safetensors']
        lock=[];models=[]
        for relative in paths:
            path=self.lab/'ComfyUI/models'/relative;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(('TEST fake weight '+relative).encode());sha=g.digest(path)
            lock.append(dict(target=str(path),sha256=sha));models.append(dict(path=str(path),sha256=sha))
        g.write_new(self.lab/'models.lock.json',lock)
        receipt=dict(lock_sha256=g.digest(self.lab/'models.lock.json'),models=models)
        model_file=self.root/'manifests/TEST-full-model-receipt.json';g.write_new(model_file,receipt)
        loaded=copy.deepcopy(self.loaded);recipe=loaded['plan']['generation_recipe']
        recipe['model_receipt']=dict(path=str(model_file),sha256=g.digest(model_file));recipe['model_sha256']=models[0]['sha256']
        pose=self.lab/'ComfyUI/models/loras'/f.POSE_LORA_NAME;pose.parent.mkdir(parents=True)
        pose.write_bytes(b'TEST tiny fake pose weight, not the official LoRA')
        control_receipt=self.root/'manifests/TEST-control-model.json'
        g.write_new(control_receipt,dict(model=dict(path=str(pose),sha256=f.OFFICIAL_EVIDENCE['model_sha256'])))
        config=dict(control_model_receipt=dict(path=str(control_receipt),sha256=g.digest(control_receipt)))
        with patch.object(g,'api') as api:
            with self.assertRaisesRegex(ValueError,'full_pinned_19B_pose_LoRA_bytes'):
                f._verify_models(self.root,self.lab,loaded,config)
            Path(models[0]['path']).write_bytes(b'TEST corrupted base file')
            with self.assertRaisesRegex(ValueError,'generator_model_weight_bytes_changed'):
                f._verify_models(self.root,self.lab,loaded,config)
        api.assert_not_called()

    def test_registered_reference_media_and_durable_job_cannot_be_bypassed_by_JSON(self):
        reference,path,screen=self.reference();verified=self.control(reference)
        registry_path=self.root/'manifests/formal-source-registry.json';original=registry_path.read_bytes()
        registry=c._read_json(registry_path)
        asset=next(row for row in registry['entries'] if row['entry_id'].endswith(':media'))
        asset['assets']['reference_png']='9'*64;registry['entries_sha256']=g.canonical(registry['entries'])
        registry_path.write_text(json.dumps(registry),encoding='utf-8')
        a,b,d,e,z=self.contexts()
        with a,b,d as api,e as queue,z as execute,patch.object(fc,'prepare_control',return_value=verified) as control:
            with self.assertRaisesRegex(ValueError,'registered_generated_media_assets'):
                f.generate_motion(self.lab,self.root,'TEST://comfy','TEST-formal6','A',reference_record_path=path,
                    reference_screen_path=screen,control_path='TEST-explicit')
        api.assert_not_called();queue.assert_not_called();execute.assert_not_called();control.assert_not_called()
        registry_path.write_bytes(original)
        Path(reference['generation']['workflow_job_path']).unlink()
        a,b,d,e,z=self.contexts()
        with a,b,d as api,e as queue,z as execute,patch.object(fc,'prepare_control') as control:
            with self.assertRaisesRegex(ValueError,'unreadable_json'):
                f.generate_motion(self.lab,self.root,'TEST://comfy','TEST-formal6','A',reference_record_path=path,
                    reference_screen_path=screen,control_path='TEST-explicit')
        api.assert_not_called();queue.assert_not_called();execute.assert_not_called();control.assert_not_called()

    def test_completed_raw_missing_durable_success_refuses_without_resubmitting(self):
        reference,path,screen=self.reference();verified=self.control(reference);a,b,d,e,z=self.contexts()
        with a,b,d,e,z,patch.object(fc,'prepare_control',return_value=verified):
            record=f.generate_motion(self.lab,self.root,'TEST://comfy','TEST-formal6','A',reference_record_path=path,
                reference_screen_path=screen,control_path='TEST-explicit')
        original=Path(record['video']['path']).read_bytes();Path(record['generation']['workflow_job_path']).unlink()
        a,b,d,e,z=self.contexts()
        with a,b,d as api,e as queue,z as execute,patch.object(fc,'prepare_control',return_value=verified):
            with self.assertRaisesRegex(ValueError,'unreadable_json'):
                f.generate_motion(self.lab,self.root,'TEST://comfy','TEST-formal6','A',reference_record_path=path,
                    reference_screen_path=screen,control_path='TEST-explicit')
        api.assert_not_called();queue.assert_not_called();execute.assert_not_called()
        self.assertEqual(Path(record['video']['path']).read_bytes(),original)

    def test_draft_CLI_writes_only_an_explicit_draft_not_sources_or_labels(self):
        request=self.root/'manifests/TEST-request.json';g.write_new(request,self.request)
        with patch.object(g,'api') as api,redirect_stdout(io.StringIO()):
            code=f.main(['draft','--root',str(self.root),'--request',str(request)])
        self.assertEqual(code,0);api.assert_not_called()
        plan=c._read_json(self.root/'manifests/formal-plan-draft.json');self.assertEqual(plan,self.plan)
        self.assertEqual(c._read_json(self.root/'manifests/dataset.json')['samples'],[])
        self.assertFalse((self.root/'manifests/formal-plan-freeze.json').exists())
        with patch.object(g,'api') as api,redirect_stdout(io.StringIO()):
            code=f.main(['freeze','--root',str(self.root),'--plan','manifests/formal-plan-draft.json'])
        self.assertEqual(code,2);api.assert_not_called()
        self.assertFalse((self.root/'manifests/formal-plan-freeze.json').exists())

    def test_registry_history_blocks_pointer_tamper_and_rollback_without_API(self):
        first=fp.source_registry_entry(self.plan,entry_id='TEST-first',source_group_id='TEST-formal6',kind='pending')
        second=fp.source_registry_entry(self.plan,entry_id='TEST-second',source_group_id='TEST-formal6',kind='pending',parents=['TEST-first'])
        f._register(self.root,self.loaded,[first]);path=self.root/'manifests/formal-source-registry.json'
        older=path.read_bytes();f._register(self.root,self.loaded,[second]);newer=path.read_bytes()
        with patch.object(g,'api') as api:
            path.write_bytes(older)
            with self.assertRaisesRegex(ValueError,'rollback'):f._register(self.root,self.loaded)
            path.write_bytes(newer);tampered=c._read_json(path);tampered['validated_registry_sha256']='0'*64
            path.write_text(json.dumps(tampered),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'match_immutable_history'):f._register(self.root,self.loaded)
            path.write_bytes(newer);f._register(self.root,self.loaded,[second])
        api.assert_not_called();self.assertEqual(path.read_bytes(),newer)

    def test_actual_Comfy_first_image_and_conditioning_bytes_are_rechecked_after_sampling(self):
        reference,path,screen=self.reference();verified=self.control(reference)
        for target in ('first_image','conditioning'):
            with self.subTest(target=target):
                def execute(base,root,name,graph):
                    result=self.execute(base,root,name,graph)
                    if '21' in graph:
                        if target=='first_image':
                            (self.lab/'ComfyUI/input'/graph['21']['inputs']['image']).write_bytes(b'TEST changed actual LoadImage source')
                        else:
                            (self.lab/'ComfyUI/output/conditioning'/(graph['3']['inputs']['name']+'.pt')).write_bytes(b'TEST changed CLIP bytes')
                    return result
                a,b,d,e,_=self.contexts()
                with a,b,d,e,patch.object(g,'execute',side_effect=execute),patch.object(fc,'prepare_control',return_value=verified):
                    with self.assertRaisesRegex(ValueError,'Comfy_reference_copy_changed|conditioning_cache_or_receipt_changed'):
                        f.generate_motion(self.lab,self.root,'TEST://comfy','TEST-formal6','A',reference_record_path=path,
                            reference_screen_path=screen,control_path='TEST-explicit')
                self.assertEqual(c._read_json(self.root/'manifests/dataset.json')['samples'],[])
                # Restore TEST input/cache solely to exercise the second distinct
                # mutation in the same root; durable failed candidates remain.
                if target=='first_image':
                    for file in (self.lab/'ComfyUI/input').glob('formal_*.png'):
                        file.write_bytes(Path(reference['image_path']).read_bytes())


if __name__=='__main__':unittest.main()
