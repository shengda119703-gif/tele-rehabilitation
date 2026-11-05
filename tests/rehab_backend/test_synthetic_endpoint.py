"""Real CPU media/PTS/RGB tests; control-loader boundary is explicitly mocked.

Fixture control receipts are not real motion sources, model verification, human
reviews, or generated GT. No actual dataset, HTTP server or GPU is touched.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import av
import numpy as np

from tools.rehab_ml.synthetic import endpoint as e, generation as g, video


class EndpointGraphTests(unittest.TestCase):
    def test_adapter_changes_only_new_image37_and_endpoint36_image_edge(self):
        graph=g.workflow('TEST-text','TEST-output',17,241,'TEST-first.png',
            pose_file='TEST-control.mp4',pose_endpoint=True)
        before=deepcopy(graph)
        result=e.with_distinct_endpoint(graph,'TEST-endpoint.png')
        self.assertEqual(graph,before)
        self.assertEqual(result['37'],dict(class_type='LoadImage',inputs=dict(image='TEST-endpoint.png')))
        self.assertEqual(result['36']['inputs']['image'],['37',0])
        expected=deepcopy(graph);expected['37']=result['37'];expected['36']['inputs']['image']=['37',0]
        self.assertEqual(result,expected)
        self.assertEqual(result['36']['inputs']['frame_idx'],240)
        self.assertEqual(result['9']['inputs']['video_latent'],['36',2])
        self.assertEqual(result['35']['inputs']['positive'],['36',0])
        self.assertEqual(result['19']['inputs']['samples'],['35',2])
        self.assertEqual(result['6']['inputs']['length'],241)

    def test_invalid_paths_same_initial_image_pretransformed_or_missing_pose_graph_reject(self):
        graph=g.workflow('TEST','TEST',17,241,'TEST-first.png',pose_file='TEST-control.mp4',pose_endpoint=True)
        for filename in ('../outside.png','dir/image.png','C:/image.png','image.jpg','TEST-first.png',None):
            with self.subTest(filename=filename),self.assertRaises(ValueError):e.with_distinct_endpoint(graph,filename)
        for changed in ({},g.workflow('TEST','TEST',17,241,'TEST-first.png',pose_file='TEST-control.mp4'),
                        e.with_distinct_endpoint(graph,'TEST-endpoint.png')):
            with self.assertRaises(ValueError):e.with_distinct_endpoint(changed,'TEST-other.png')
        with self.assertRaises(ValueError):e.with_distinct_endpoint(graph,'TEST-endpoint.png',frames=305)
        changed=deepcopy(graph);changed['35']['inputs']['latent']=['14',0]
        with self.assertRaises(ValueError):e.with_distinct_endpoint(changed,'TEST-endpoint.png')

    def test_live_same_reference_D_prohibition_remains_intact(self):
        with patch.object(g,'api') as api,patch.object(g,'execute') as execute:
            with self.assertRaisesRegex(ValueError,'scenario A or E'):
                g.generate(Path('TEST-lab'),Path('TEST-root'),'TEST://comfy','pilot01','D',
                    pose_control=Path('TEST-control.json'),pose_endpoint=True)
        api.assert_not_called();execute.assert_not_called()


class EndpointMediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.media_temp=tempfile.TemporaryDirectory(prefix='endpoint-media-TEST-')
        cls.addClassCleanup(cls.media_temp.cleanup)
        cls.cached=Path(cls.media_temp.name)/'TEST-parent.mp4'
        with av.open(str(cls.cached),'w') as container:
            stream=container.add_stream('libx264',rate=30);stream.width=640;stream.height=384
            stream.pix_fmt='yuv420p';stream.options={'preset':'ultrafast','crf':'18'}
            for index in range(241):
                pixels=np.zeros((384,640,3),dtype=np.uint8);pixels[:]=[20+index//2,60,index//3]
                pixels[80:250,250:390]=[180,index%200,100]
                for packet in stream.encode(av.VideoFrame.from_ndarray(pixels,format='rgb24')):container.mux(packet)
            for packet in stream.encode():container.mux(packet)
        cls.probe=video.probe_video(cls.cached)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='endpoint-source-TEST-');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);g.initialize(self.root)
        self.sid='TEST-pilot-D-completed';self.group='TEST-pilot'
        movie=self.root/'raw/TEST-parent.mp4';shutil.copy2(self.cached,movie)
        timeline=self.root/'manifests/timelines/TEST-parent.json';g.write_new(timeline,self.probe)
        self.control_path=self.root/'features/TEST-control/receipt.json'
        folder=self.control_path.parent;folder.mkdir(parents=True)
        files={}
        for name in ('control.mp4','trajectory.json','initial.json','timeline.json','pose.json','style.py','reference.mp4'):
            path=folder/name;path.write_bytes(('TEST mocked control-loader asset '+name).encode());files[name]=path
        image=self.root/'references/TEST-first.png'
        e._frame(movie,0,self.probe['frames'][0]).save(image)
        self.reference_path=self.root/'references/TEST-pilot.json'
        self.reference=dict(source_group_id=self.group,reference_group_id=self.group,stage='pilot',split='train',
            structural_review=dict(status='usable_as_initial_condition'),
            image_path=str(image),image_sha256=g.digest(image),video=dict(path=str(files['reference.mp4']),sha256=g.digest(files['reference.mp4'])))
        g.write_new(self.reference_path,self.reference)
        self.controller=dict(video=str(files['control.mp4']),video_sha256=g.digest(files['control.mp4']),
            actual_pts_timeline=str(files['timeline.json']),controller_trajectory=str(files['trajectory.json']),
            controller_trajectory_sha256=g.digest(files['trajectory.json']),initial_source_path=str(files['initial.json']),
            style=dict(path=str(files['style.py'])),lineage_ids=['identity:'+self.group,'TEST-controller-origin'],
            source=dict(source_group_id=self.group,reference_group_id=self.group,stage='pilot',split='train',
                reference_record=str(self.reference_path),reference_image=str(image),reference_image_sha256=g.digest(image),
                reference_video=str(files['reference.mp4']),source_pose_path=str(files['pose.json']),source_pose_sha256=g.digest(files['pose.json'])))
        g.write_new(self.control_path,dict(TEST='mocked load_control boundary; not a verified real control'))
        text='TEST-only requested D command, never a human label'
        key='rehab_'+hashlib.sha256(('TEST-prompt-v1'+text).encode()).hexdigest()[:24]
        graph=g.workflow(key,self.sid,17,241,'rehab_ref_'+g.digest(image)[:20]+'.png',pose_file='TEST-control.mp4')
        job_path=self.root/'manifests/jobs'/str(self.sid+'.json')
        g.write_new(job_path,dict(name=self.sid,prompt_id='TEST-durable-handle',status='success',
            workflow=graph,workflow_sha256=g.canonical(graph),history=dict(status=dict(status_str='success'))))
        self.parent=dict(schema_version='rehab_synthetic/v1',sample_id=self.sid,source_group_id=self.group,
            reference_group_id=self.group,lineage_ids=[*self.controller['lineage_ids'],'reference:'+g.digest(image)],
            stage='pilot',split='train',scenario='D',exercise_id='shoulder_abduction',side='unknown',view='front',status='pending',
            video=dict(path=str(movie),sha256=g.digest(movie),timeline_path=str(timeline),timeline_sha256=g.digest(timeline),
                width=640,height=384,frame_count=241),
            generation=dict(prompt_version='TEST-prompt-v1',prompt=text,conditioning_key=key,seed=17,model_sha256='a'*64,
                prompt_sha256=hashlib.sha256(text.encode()).hexdigest(),
                workflow_sha256=g.canonical(graph),workflow_job_path=str(job_path),pose_control=dict(
                    receipt_path=str(self.control_path),receipt_sha256=g.digest(self.control_path),
                    control_video_sha256=self.controller['video_sha256'],trajectory_sha256=self.controller['controller_trajectory_sha256'],
                    pose_source_sha256=self.controller['source']['source_pose_sha256'])))
        g.write_new(self.root/'manifests'/str(self.sid+'.json'),self.parent)
        manifest=dict(schema_version='rehab_synthetic/v1',dataset_id='TEST-endpoint-only',split_freeze=None,samples=[self.parent])
        g.replace_json(self.root/'manifests/dataset.json',manifest)
        self.loader=patch.object(e.control,'load_control',side_effect=lambda *args,**kwargs:deepcopy(self.controller)).start()
        self.addCleanup(patch.stopall)

    def create(self):
        return e.create_endpoint(self.root,self.sid,150,self.root/'features/TEST-endpoint',pose_control=self.control_path)

    def rewrite(self,path,value):
        Path(path).write_text(json.dumps(value),encoding='utf-8')

    def test_extraction_binds_real_frame_PTS_original_RGB_and_train_lineage_without_GT(self):
        original=(self.root/'manifests/dataset.json').read_bytes()
        checked=self.create();receipt=checked['receipt']
        self.assertEqual(receipt['frame'],self.probe['frames'][150])
        self.assertEqual(receipt['frame']['timestamp_s'],5.)
        self.assertEqual(e._png(Path(receipt['image']['path'])),self.probe['frames'][150]['decoded_rgb_sha256'])
        self.assertEqual((receipt['stage'],receipt['split']),('pilot','train'))
        self.assertTrue(set(self.parent['lineage_ids'])<=set(receipt['lineage_ids']))
        self.assertIn(self.sid,receipt['lineage_ids'])
        for flag in e.FLAGS:self.assertIs(receipt[flag],False)
        self.assertFalse(checked['human_reference_created'])
        self.assertEqual((self.root/'manifests/dataset.json').read_bytes(),original)
        self.assertFalse(list((self.root/'annotations').iterdir()))
        self.loader.assert_called_with(self.control_path.resolve(),verify=True,expected_source_group_id=self.group,expected_scenario='D')
        result=e.endpoint_contract(checked)
        self.assertEqual((result['sampled_video_latent_frames'],result['cropped_video_latent_frames'],result['expected_decoded_frames']),(63,31,241))
        self.assertFalse(result['same_reference_for_first_and_last']);self.assertFalse(result['creates_labels'])
        self.assertFalse(result['endpoint_fade_fix_guaranteed'])

    def test_same_content_revalidation_and_existing_output_never_overwrite(self):
        checked=self.create();path=Path(checked['receipt_path']);before=path.read_bytes()
        again=e.validate_endpoint(self.root,path,pose_control=self.control_path,source_group_id=self.group)
        self.assertEqual(again,checked)
        with self.assertRaisesRegex(ValueError,'no_overwrite'):self.create()
        self.assertEqual(path.read_bytes(),before)

    def test_other_group_or_different_controller_receipt_cannot_be_used(self):
        checked=self.create();path=checked['receipt_path']
        with self.assertRaisesRegex(ValueError,'binding_changed'):
            e.validate_endpoint(self.root,path,pose_control=self.control_path,source_group_id='TEST-other')
        other=self.root/'features/TEST-other-controller.json';shutil.copy2(self.control_path,other)
        with self.assertRaisesRegex(ValueError,'same_bound_parent_controller'):
            e.validate_endpoint(self.root,path,pose_control=other)
        self.controller['source']['reference_group_id']='TEST-other'
        with self.assertRaisesRegex(ValueError,'source_lineage_mismatch'):
            e.validate_endpoint(self.root,path,pose_control=self.control_path)

    def test_edited_image_with_self_consistent_new_hash_is_still_not_bound_RGB(self):
        checked=self.create();receipt=checked['receipt'];png=Path(receipt['image']['path'])
        from PIL import Image
        Image.new('RGB',(640,384),(250,0,0)).save(png)
        receipt['image'].update(sha256=g.digest(png),decoded_rgb_sha256=e._png(png))
        self.rewrite(checked['receipt_path'],receipt)
        with self.assertRaisesRegex(ValueError,'decoded_RGB_frame'):
            e.validate_endpoint(self.root,checked['receipt_path'],pose_control=self.control_path)

    def test_PTS_index_lineage_and_GT_forgery_are_rejected(self):
        checked=self.create();original=checked['receipt'];path=checked['receipt_path']
        for field in ('pts','time_base','timestamp_s','decoded_rgb_sha256','frame_index'):
            changed=deepcopy(original)
            changed['frame'][field]={'pts':-1,'time_base':[1,30],'timestamp_s':4.,'decoded_rgb_sha256':'f'*64,'frame_index':149}[field]
            self.rewrite(path,changed)
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'frame_PTS_index'):
                e.validate_endpoint(self.root,path,pose_control=self.control_path)
        for changed in (dict(original,lineage_ids=['TEST-unbound-origin']),dict(original,is_GT=True)):
            self.rewrite(path,changed)
            with self.assertRaises(ValueError):e.validate_endpoint(self.root,path,pose_control=self.control_path)

    def test_parent_failed_job_changed_raw_or_record_and_heldout_origin_reject(self):
        job_path=Path(self.parent['generation']['workflow_job_path']);job=e._json(job_path)
        job['status']='error';self.rewrite(job_path,job)
        with self.assertRaisesRegex(ValueError,'authoritative_completed'):self.create()
        job['status']='success';self.rewrite(job_path,job)
        movie=Path(self.parent['video']['path']);original=movie.read_bytes();movie.write_bytes(b'TEST changed raw')
        with self.assertRaises(ValueError):self.create()
        movie.write_bytes(original)
        self.parent['split']='test';self.rewrite(self.root/'manifests'/str(self.sid+'.json'),self.parent)
        manifest=e._json(self.root/'manifests/dataset.json');manifest['samples'][0]=self.parent
        self.rewrite(self.root/'manifests/dataset.json',manifest)
        with self.assertRaises(ValueError):self.create()

    def test_cross_root_and_first_frame_extraction_reject_without_output(self):
        for index in (0,-1,241,True,150.):
            with self.subTest(index=index),self.assertRaisesRegex(ValueError,'nonfirst_actual'):
                e.create_endpoint(self.root,self.sid,index,self.root/'features/TEST-endpoint',pose_control=self.control_path)
        with self.assertRaisesRegex(ValueError,'outside_declared'):
            e.create_endpoint(self.root,self.sid,150,self.root.parent/'MUST-NOT-WRITE',pose_control=self.control_path)
        self.assertFalse((self.root/'features/TEST-endpoint').exists())

    def test_source_mutation_during_extraction_is_detected_before_publication(self):
        actual=e._frame
        def mutate(*args):
            image=actual(*args)
            Path(self.controller['source']['source_pose_path']).write_bytes(b'TEST changed during extraction')
            return image
        with patch.object(e,'_frame',side_effect=mutate):
            with self.assertRaisesRegex(ValueError,'changed_during_operation'):self.create()
        self.assertFalse((self.root/'features/TEST-endpoint').exists())

    def external(self,checked):
        native=checked['receipt'];row=native['frame'];folder=Path(checked['receipt_path']).parent
        snapshot=folder/'source-manifest.snapshot.json';g.write_new(snapshot,self.parent)
        timeline=folder/'timeline.json';g.write_new(timeline,self.probe)
        value=dict(schema_version='rehab_synthetic_endpoint_image/v1',source_group_id=self.group,reference_group_id=self.group,
            stage='pilot',split='train',source_sample_id=self.sid,source_video=self.parent['video']['path'],
            source_video_sha256=self.parent['video']['sha256'],source_sha256=self.parent['video']['sha256'],
            source_frame_index=150,source_frame_pts=row['pts'],source_frame_time_base=row['time_base'],
            source_frame_timestamp_s=row['timestamp_s'],source_decoded_rgb_sha256=row['decoded_rgb_sha256'],
            image_path=native['image']['path'],image_sha256=native['image']['sha256'],width=640,height=384,
            image_RGB_unchanged_from_decoded_source=True,RGB_sha256=row['decoded_rgb_sha256'],
            source_edited=False,crop_resize_or_retouch_performed=False,source_manifest_snapshot=str(snapshot),
            source_manifest_snapshot_sha256=g.digest(snapshot),actual_full_pts_timeline=str(timeline),
            actual_full_pts_timeline_sha256=g.digest(timeline),lineage_ids=[*self.parent['lineage_ids'],
                'endpoint_source_video:'+self.parent['video']['sha256'],'endpoint_image:'+native['image']['sha256']],
            requested_scenario='D',requested_scenario_is_a_label=False,is_GT=False,human_review=False,
            training_reference_eligible=False,creates_human_annotations=False,product_enabled=False)
        path=folder/'legacy-receipt.json';g.write_new(path,value)
        return path,value

    def test_existing_extractor_receipt_is_verified_read_only_and_normalized(self):
        checked=self.create();path,external=self.external(checked);before=path.read_bytes()
        result=e.validate_endpoint(self.root,path,pose_control=self.control_path)
        self.assertEqual(result['receipt'],checked['receipt'])
        self.assertEqual(result['receipt_sha256'],g.digest(path))
        self.assertEqual(path.read_bytes(),before)
        external['source_frame_pts']+=1;self.rewrite(path,external)
        with self.assertRaisesRegex(ValueError,'actual_frame_PTS'):
            e.validate_endpoint(self.root,path,pose_control=self.control_path)

    def generation_setup(self):
        """Tiny fake weight receipts and mock verification boundary, no model."""
        self.lab=self.root/'TEST-lab'
        for name in ('ComfyUI/input','ComfyUI/output/conditioning','ComfyUI/output/sports'):
            (self.lab/name).mkdir(parents=True)
        weight=self.lab/'TEST-weight.bin';weight.write_bytes(b'TEST bytes, not model weights')
        self.parent['generation']['model_sha256']=g.digest(weight)
        self.rewrite(self.root/'manifests'/str(self.sid+'.json'),self.parent)
        manifest=e._json(self.root/'manifests/dataset.json');manifest['samples'][0]=self.parent
        self.rewrite(self.root/'manifests/dataset.json',manifest)
        g.write_new(self.root/'manifests/model-verification.json',dict(models=[dict(path=str(weight),sha256=g.digest(weight))]))
        lora=self.lab/'TEST-LoRA.bin';lora.write_bytes(b'TEST mocked additive verification boundary')
        lock=self.lab/'TEST-lock.json';g.write_new(lock,dict(TEST=True))
        model_receipt=self.root/'manifests/TEST-additive-receipt.json'
        g.write_new(model_receipt,dict(model=dict(path=str(lora),sha256=g.digest(lora)),lock_path=str(lock),lock_sha256=g.digest(lock)))
        (self.lab/'ComfyUI/output/conditioning'/str(self.parent['generation']['conditioning_key']+'.pt')).write_bytes(b'TEST cached text')
        self.metadata=dict(self.parent['generation']['pose_control'],model_receipt_path=str(model_receipt),
            model_receipt_sha256=g.digest(model_receipt))
        def prepare(*args):
            self.assertEqual(args[3:5],(self.group,'D'))
            target=self.lab/'ComfyUI/input/TEST-control.mp4'
            if not target.exists():shutil.copy2(self.controller['video'],target)
            return deepcopy(self.controller),'TEST-control.mp4',deepcopy(self.metadata)
        self.prepare=patch.object(g,'prepare_pose_control',side_effect=prepare).start()
        return self.create()

    def api(self,base,route,payload=None):
        self.routes.append(route)
        if route in ('/free','/queue'):
            return dict(queue_running=[],queue_pending=[]) if route=='/queue' else {}
        if route=='/prompt':
            graph=payload['prompt'];name=graph['18']['inputs']['name']
            # Valid fixture media with a distinct container SHA. This simulates
            # an execution response, not successful diffusion or motion quality.
            (self.lab/'ComfyUI/output/sports'/str(name+'.mp4')).write_bytes(self.cached.read_bytes()+name.encode())
            return dict(prompt_id='TEST-endpoint-durable-job')
        if route=='/history/TEST-endpoint-durable-job':
            return {'TEST-endpoint-durable-job':dict(status=dict(status_str='success'),outputs={})}
        self.fail('Unexpected route '+route)

    def test_independent_generation_keeps_parent_seed_text_and_recovers_without_new_POST(self):
        checked=self.generation_setup();self.routes=[]
        with patch.object(g,'api',side_effect=self.api):
            result=e.generate(self.lab,self.root,'TEST://comfy',checked['receipt_path'],pose_control=self.control_path)
        self.assertIn('_endphoto'+checked['receipt']['image']['sha256'][:12],result['sample_id'])
        self.assertEqual(result['generation']['seed'],self.parent['generation']['seed'])
        self.assertEqual(result['generation']['prompt'],self.parent['generation']['prompt'])
        self.assertEqual(result['generation']['conditioning_key'],self.parent['generation']['conditioning_key'])
        self.assertEqual((result['stage'],result['split'],result['status']),('pilot','train','pending'))
        self.assertEqual(result['side'],'unknown')
        self.assertFalse(list((self.root/'annotations').iterdir()))
        self.assertEqual(self.routes.count('/prompt'),1)
        job=e._json(Path(result['generation']['workflow_job_path']))
        self.assertEqual(job['workflow']['36']['inputs']['image'],['37',0])
        self.assertEqual(job['workflow']['37']['class_type'],'LoadImage')
        self.assertEqual(job['workflow_sha256'],g.canonical(job['workflow']))
        with patch.object(g,'api') as api:
            recovered=e.generate(self.lab,self.root,'TEST://comfy',checked['receipt_path'],pose_control=self.control_path)
        self.assertEqual(recovered,result);api.assert_not_called()
        self.assertEqual(len(e._json(self.root/'manifests/dataset.json')['samples']),2)
        self.assertFalse((self.root/'manifests/generation.lock').exists())

    def test_failed_submission_receipt_cannot_resubmit_same_endpoint_job(self):
        import io
        import urllib.error
        checked=self.generation_setup();posts=[]
        def rejected(base,route,payload=None):
            if route=='/queue':return dict(queue_running=[],queue_pending=[])
            if route=='/prompt':
                posts.append(payload)
                raise urllib.error.HTTPError('TEST://comfy',400,'TEST',{},io.BytesIO(b'TEST schema failed'))
            self.fail('Unexpected route '+route)
        with patch.object(g,'api',side_effect=rejected):
            with self.assertRaisesRegex(RuntimeError,'HTTP error'):
                e.generate(self.lab,self.root,'TEST://comfy',checked['receipt_path'],pose_control=self.control_path)
            with self.assertRaisesRegex(RuntimeError,'unknown|inspect'):
                e.generate(self.lab,self.root,'TEST://comfy',checked['receipt_path'],pose_control=self.control_path)
        self.assertEqual(len(posts),1)
        self.assertEqual(len(e._json(self.root/'manifests/dataset.json')['samples']),1)

    def test_completed_job_missing_or_changed_is_rejected_without_recreation_or_POST(self):
        checked=self.generation_setup();self.routes=[]
        with patch.object(g,'api',side_effect=self.api):
            result=e.generate(self.lab,self.root,'TEST://comfy',checked['receipt_path'],pose_control=self.control_path)
        path=Path(result['generation']['workflow_job_path']);original=path.read_bytes()
        with patch.object(g,'api') as api:
            path.unlink()
            with self.assertRaisesRegex(ValueError,'durable_job_missing_or_changed'):
                e.generate(self.lab,self.root,'TEST://comfy',checked['receipt_path'],pose_control=self.control_path)
            self.assertFalse(path.exists());path.write_bytes(original)
            job=e._json(path);job['history']['status']['status_str']='error';self.rewrite(path,job)
            with self.assertRaisesRegex(ValueError,'durable_job_missing_or_changed'):
                e.generate(self.lab,self.root,'TEST://comfy',checked['receipt_path'],pose_control=self.control_path)
        api.assert_not_called()

    def test_completed_conditioning_cache_or_receipt_change_reject_without_POST(self):
        checked=self.generation_setup();self.routes=[]
        with patch.object(g,'api',side_effect=self.api):
            result=e.generate(self.lab,self.root,'TEST://comfy',checked['receipt_path'],pose_control=self.control_path)
        receipt=Path(result['generation']['conditioning_receipt_path'])
        self.assertEqual(g.digest(receipt),result['generation']['conditioning_receipt_sha256'])
        cache=Path(e._json(receipt)['conditioning_path']);original=cache.read_bytes()
        self.assertEqual(g.digest(cache),result['generation']['conditioning_sha256'])
        with patch.object(g,'api') as api:
            cache.write_bytes(b'TEST changed text cache')
            with self.assertRaisesRegex(ValueError,'conditioning_receipt_missing_or_changed'):
                e.generate(self.lab,self.root,'TEST://comfy',checked['receipt_path'],pose_control=self.control_path)
            cache.write_bytes(original);receipt.unlink()
            with self.assertRaisesRegex(ValueError,'conditioning_receipt_missing_or_changed'):
                e.generate(self.lab,self.root,'TEST://comfy',checked['receipt_path'],pose_control=self.control_path)
            self.assertFalse(receipt.exists())
        api.assert_not_called()

    def test_source_change_during_simulated_sampling_prevents_publication(self):
        checked=self.generation_setup();self.routes=[]
        def changed(base,route,payload=None):
            result=self.api(base,route,payload)
            if route.startswith('/history/'):
                Path(self.controller['source']['source_pose_path']).write_bytes(b'TEST mutation after sampling')
            return result
        with patch.object(g,'api',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'changed_during_operation'):
                e.generate(self.lab,self.root,'TEST://comfy',checked['receipt_path'],pose_control=self.control_path)
        self.assertEqual(len(e._json(self.root/'manifests/dataset.json')['samples']),1)
        self.assertEqual(len(list((self.root/'raw').glob('*.mp4'))),1)


if __name__=='__main__':unittest.main()
