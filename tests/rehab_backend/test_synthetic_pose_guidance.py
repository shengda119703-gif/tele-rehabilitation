"""Pure pose-control graph, verified source receipt and tiny CPU latent tests."""
import ast
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

import torch

from tools.rehab_ml.synthetic.generation import workflow
from tools.rehab_ml.synthetic.guidance import with_first_last_reference
from tools.rehab_ml.synthetic.pose_guidance import (with_pose_video,pose_guidance_contract,
    validate_control_probe,POSE_LORA_NAME,DISTILLED_SIGMAS,OFFICIAL_EVIDENCE)

NATIVE=Path('E:/ai-video-lab/ComfyUI/comfy_extras/nodes_lt.py')
OFFICIAL=Path('E:/ai-video-lab/sources/LTX-2_19B_ICLoRA_All_Distilled_44c8a36b7c31.json')


class PoseGuidanceGraphTests(unittest.TestCase):
    def test_v1_default_and_explicit_false_keep_frozen_graph_and_contract(self):
        # Frozen before introducing endpoint_reference; all v1 keys and edges
        # are covered, including values not otherwise asserted individually.
        golden={241:('22da66a3698be2f0c776514c040167bcf21948f2ac0c8f839d7ecfa827f4d115',
                     '8a0ecd3fbeb19b9615d5a170072abe6996a830913bafc11b05c1b7617d365ce3'),
                305:('65cd5764e2bd81efc0d60ed8f44c34fbbb017cdb4b83027cd93c2e5e533a8f16',
                     '7325562151cfa78d8e35e6d650076bc15d53998d317841f7d09e8c46e4106884')}
        for frames,(graph_sha,contract_sha) in golden.items():
            base=workflow('TEST-text','TEST-pose',7,frames,'TEST-person.png')
            graph=with_pose_video(base,'TEST-control.mp4',frames=frames)
            contract=pose_guidance_contract(frames,control_file='TEST-control.mp4',control_sha256='e'*64)
            self.assertEqual(graph,with_pose_video(base,'TEST-control.mp4',frames=frames,endpoint_reference=False))
            self.assertEqual(contract,pose_guidance_contract(frames,control_file='TEST-control.mp4',
                                                           control_sha256='e'*64,endpoint_reference=False))
            for value,expected in ((graph,graph_sha),(contract,contract_sha)):
                actual=hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
                self.assertEqual(actual,expected)
            self.assertNotIn('36',graph);self.assertNotIn('endpoint_reference',contract)

    def test_pose_endpoint_uses_same_photo_after_full_pose_before_AV_and_crop(self):
        for frames in (241,305):
            base=workflow('TEST','TEST',7,frames,'TEST-person.png');frozen=copy.deepcopy(base)
            legacy=with_pose_video(base,'TEST-control.mp4',frames=frames,lora_strength=.8,guide_strength=.6)
            graph=with_pose_video(base,'TEST-control.mp4',frames=frames,lora_strength=.8,guide_strength=.6,
                                  endpoint_reference=True)
            expected=copy.deepcopy(legacy)
            expected['36']=dict(class_type='LTXVAddGuide',inputs=dict(positive=['34',0],negative=['34',1],
                latent=['34',2],image=['21',0],vae=['16',0],frame_idx=frames-1,strength=1.))
            expected['9']['inputs']['video_latent']=['36',2]
            expected['10']['inputs'].update(positive=['36',0],negative=['36',1])
            expected['35']['inputs'].update(positive=['36',0],negative=['36',1])
            self.assertEqual(graph,expected);self.assertEqual(base,frozen)
            self.assertEqual(graph['35']['inputs']['latent'],['15',0])
            self.assertEqual(graph['15']['inputs']['av_latent'],['14',0])
            self.assertEqual(graph['19']['inputs']['samples'],['35',2])
            self.assertEqual(graph['17']['inputs']['samples'],['19',0])
            self.assertEqual(graph['18']['inputs']['fps'],30)
            self.assertEqual(graph['18']['inputs']['crop_height'],0)
            self.assertEqual(graph['34']['inputs']['strength'],.6)
            self.assertFalse(any(word in n['class_type'].lower() for n in graph.values()
                                 for word in ('repeat','loop','interpolat','reverse')))

    def test_pose_endpoint_contract_has_separate_version_context_counts_and_no_promises(self):
        for frames,latent in ((241,31),(305,39)):
            legacy=pose_guidance_contract(frames,control_file='TEST.mp4',control_sha256='e'*64)
            contract=pose_guidance_contract(frames,control_file='TEST.mp4',control_sha256='e'*64,endpoint_reference=True)
            expected=copy.deepcopy(legacy)
            expected.update(version='rehab_ltx19_pose_video_guidance/v2',endpoint_reference=True,
                same_reference_for_first_and_last=True,endpoint_reference_image='same_LoadImage_21_used_for_first_frame',
                endpoint_guide_frame_index=frames-1,endpoint_guide_strength=1.,pose_guide_latent_frames=latent,
                endpoint_guide_latent_frames=1,appended_guide_latent_frames=latent+1,
                sampled_video_latent_frames=2*latent+1,endpoint_fade_fix_guaranteed=False,
                local_endpoint_reference_inference_verified=False,
                ordering='pose_guide_then_same_reference_endpoint_then_AV_merge_then_sample_then_video_separate_then_crop_then_cache_decode')
            self.assertEqual(contract,expected)
            self.assertEqual(contract['cropped_video_latent_frames'],latent)
            self.assertEqual(contract['expected_decoded_frames'],frames)
            for key in ('endpoint_fade_fix_guaranteed','local_endpoint_reference_inference_verified',
                        'local_GGUF_pose_inference_verified','local_8GB_memory_verified','creates_labels',
                        'output_action_completion_guaranteed','independent_motion_ground_truth'):
                self.assertIs(contract[key],False)
            self.assertIs(contract['experimental'],True)
            self.assertIs(contract['decoded_frames_must_be_independently_verified'],True)

    def test_endpoint_flag_requires_bool_and_reserved_node_36_cannot_be_overwritten(self):
        base=workflow('TEST','TEST',7,241,'TEST.png')
        for value in (None,0,1,'false','true',[],{}):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError,'boolean_endpoint_reference'):
                    with_pose_video(base,'TEST.mp4',endpoint_reference=value)
                with self.assertRaisesRegex(ValueError,'boolean_endpoint_reference'):
                    pose_guidance_contract(endpoint_reference=value)
        changed=copy.deepcopy(base);changed['36']=dict(class_type='TEST-reserved',inputs={})
        for endpoint in (False,True):
            with self.assertRaisesRegex(ValueError,'node_id_36_already_in_use'):
                with_pose_video(changed,'TEST.mp4',endpoint_reference=endpoint)
        for guided in (with_first_last_reference(base),with_pose_video(base,'TEST.mp4'),
                       with_pose_video(base,'TEST.mp4',endpoint_reference=True)):
            with self.assertRaises(ValueError):with_pose_video(guided,'TEST.mp4',endpoint_reference=True)

    def test_pinned_model_lora_and_official_single_stage_sampling_are_explicit(self):
        original=workflow('TEST-text','TEST-pose',7,241,'TEST-person.png');frozen=copy.deepcopy(original)
        graph=with_pose_video(original,'TEST-control.mp4')
        self.assertEqual(original,frozen)
        self.assertEqual(graph['31'],dict(class_type='LoraLoaderModelOnly',inputs=dict(model=['1',0],lora_name=POSE_LORA_NAME,strength_model=1.)))
        self.assertEqual(graph['10']['inputs']['model'],['31',0])
        self.assertEqual(graph['10']['inputs']['cfg'],1.)
        self.assertEqual(graph['12']['inputs']['sampler_name'],'euler')
        self.assertEqual(tuple(float(v.strip()) for v in graph['13']['inputs']['sigmas'].split(',')),DISTILLED_SIGMAS)
        self.assertEqual(len(DISTILLED_SIGMAS)-1,8)

    def test_first_reference_is_separate_from_all_frame_skeleton_control(self):
        graph=with_pose_video(workflow('TEST','TEST',7,241,'TEST-person.png'),'TEST-control.mp4')
        self.assertEqual(graph['21']['inputs']['image'],'TEST-person.png')
        self.assertEqual(graph['22']['inputs']['image'],['21',0])
        self.assertEqual(graph['32'],dict(class_type='LoadVideo',inputs=dict(file='TEST-control.mp4')))
        self.assertEqual(graph['33'],dict(class_type='GetVideoComponents',inputs=dict(video=['32',0])))
        guide=graph['34']['inputs']
        self.assertEqual(guide['image'],['33',0]);self.assertEqual(guide['latent'],['22',0]);self.assertEqual(guide['frame_idx'],0)
        self.assertEqual(graph['9']['inputs']['video_latent'],['34',2])
        self.assertEqual(graph['10']['inputs']['positive'],['34',0])
        self.assertEqual(graph['10']['inputs']['negative'],['34',1])

    def test_only_separated_video_is_cropped_before_cache_for_241_and305(self):
        for frames in (241,305):
            graph=with_pose_video(workflow('TEST','TEST',7,frames,'TEST-person.png'),'TEST-control.mp4',frames=frames)
            self.assertEqual(graph['15']['inputs']['av_latent'],['14',0])
            self.assertEqual(graph['35']['inputs'],dict(positive=['34',0],negative=['34',1],latent=['15',0]))
            self.assertEqual(graph['19']['inputs']['samples'],['35',2])
            self.assertEqual(graph['17']['inputs']['samples'],['19',0])
            self.assertEqual(graph['18']['inputs']['crop_height'],0)
            self.assertEqual(graph['18']['inputs']['fps'],30)
            self.assertEqual(graph['6']['inputs']['length'],frames)
            self.assertEqual(graph['8']['inputs']['frames_number'],frames)
            self.assertFalse(any(word in n['class_type'].lower() for n in graph.values() for word in ('repeat','loop','interpolat','reverse')))

    def test_endpoint_guide_and_pose_control_cannot_be_silently_combined_or_applied_twice(self):
        base=workflow('TEST','TEST',7,241,'TEST.png')
        for incompatible in (with_first_last_reference(base),with_pose_video(base,'TEST.mp4')):
            with self.assertRaises(ValueError):with_pose_video(incompatible,'TEST.mp4')

    def test_wrong_model_or_control_paths_and_2_5_lora_are_rejected(self):
        base=workflow('TEST','TEST',7,241,'TEST.png')
        for filename in ('../TEST.mp4','C:/TEST.mp4','https://example.com/TEST.mp4','TEST.png'):
            with self.assertRaises(ValueError):with_pose_video(base,filename)
        with self.assertRaisesRegex(ValueError,'19B_pose'):
            with_pose_video(base,'TEST.mp4',lora_name='ltx-2.5-union-control.safetensors')
        changed=copy.deepcopy(base);changed['1']['inputs']['unet_name']='ltx-2.5.gguf'
        with self.assertRaisesRegex(ValueError,'19B_distilled'):with_pose_video(changed,'TEST.mp4')
        changed=copy.deepcopy(base);changed['6']['inputs'].update(width=1280,height=736)
        with self.assertRaisesRegex(ValueError,'640x384'):with_pose_video(changed,'TEST.mp4')
        with self.assertRaises(ValueError):with_pose_video(base,'TEST.mp4',frames=305)

    def test_metadata_is_control_request_not_GT_or_memory_and_quality_validation(self):
        for frames,latent in ((241,31),(305,39)):
            contract=pose_guidance_contract(frames,control_file='TEST.mp4',control_sha256='e'*64)
            self.assertEqual(contract['appended_guide_latent_frames'],latent)
            self.assertEqual(contract['sampled_video_latent_frames'],2*latent)
            self.assertEqual(contract['cropped_video_latent_frames'],latent)
            self.assertEqual(contract['expected_decoded_frames'],frames)
            self.assertFalse(contract['creates_labels']);self.assertFalse(contract['independent_motion_ground_truth'])
            self.assertFalse(contract['local_8GB_memory_verified']);self.assertFalse(contract['local_GGUF_pose_inference_verified'])
            self.assertTrue(contract['official_workflow_has_two_stages'])
            self.assertEqual(contract['official_evidence']['model_revision'],'ecdabfb03acd2e807c90ea260ccc136140e7ac80')

    def test_control_requires_real_full_RGB_decode_and_not_fps_header_or_BGR_swap(self):
        frames=241
        probe=dict(video_sha256='b'*64,width=640,height=384,frame_count=frames,
            presentation_s=[i/30 for i in range(frames)],
            frames=[dict(frame_index=i,timestamp_s=i/30,decoded_rgb_sha256='a'*64) for i in range(frames)],
            provenance=dict(full_decode_verified=True,pixel_format='rgb24'))
        self.assertEqual(validate_control_probe(probe)['control_sha256'],'b'*64)
        for mutate in (lambda p:p['provenance'].update(pixel_format='bgr24'),
                       lambda p:p['provenance'].update(full_decode_verified=False),
                       lambda p:p['presentation_s'].__setitem__(5,.5),
                       lambda p:p['frames'][5].update(decoded_rgb_sha256=None),
                       lambda p:p.update(frame_count=249)):
            changed=copy.deepcopy(probe);mutate(changed)
            with self.assertRaises(ValueError):validate_control_probe(changed)

    @unittest.skipUnless(OFFICIAL.is_file(),'pinned downloaded official workflow not available')
    def test_receipt_matches_downloaded_official_19B_pose_distilled_workflow(self):
        self.assertEqual(hashlib.sha256(OFFICIAL.read_bytes()).hexdigest(),OFFICIAL_EVIDENCE['workflow_sha256'])
        graph=json.loads(OFFICIAL.read_text(encoding='utf-8'))['definitions']['subgraphs'][2]
        self.assertEqual(graph['id'],OFFICIAL_EVIDENCE['pose_sampler_subgraph_id'])
        sigmas=[n['widgets_values'][0] for n in graph['nodes'] if n['type']=='ManualSigmas']
        self.assertTrue(any(tuple(map(float,entry.split(',')))==DISTILLED_SIGMAS for entry in sigmas))
        self.assertTrue(any(n['type']=='KSamplerSelect' and n['widgets_values']==['euler'] for n in graph['nodes']))


@unittest.skipUnless(NATIVE.is_file(),'pinned local native Comfy source unavailable')
class NativeFullVideoGuideTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree=ast.parse(NATIVE.read_text(encoding='utf-8'))
        base=dict(torch=torch,io=SimpleNamespace(NodeOutput=lambda *values:values),
            node_helpers=SimpleNamespace(conditioning_set_values=lambda cond,values:{**cond,**values}),
            conditioning_get_any_value=lambda cond,key,default=None:cond.get(key,default))
        for name in ('get_noise_mask','get_keyframe_idxs'):
            node=copy.deepcopy(next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name))
            exec(compile(ast.Module(body=[node],type_ignores=[]),str(NATIVE),'exec'),base)
        def extract(class_name,name):
            parent=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==class_name)
            node=copy.deepcopy(next(n for n in parent.body if isinstance(n,ast.FunctionDef) and n.name==name));node.decorator_list=[]
            scope=dict(base);exec(compile(ast.Module(body=[node],type_ignores=[]),str(NATIVE),'exec'),scope)
            return scope[name]
        cls.append=staticmethod(extract('LTXVAddGuide','append_keyframe'))
        cls.latent_index=staticmethod(extract('LTXVAddGuide','get_latent_index'))
        cls.crop=staticmethod(extract('LTXVCropGuides','execute'))

    def test_native_append_full_pose_guide_and_crop_returns_original_241_or305(self):
        def metadata(cond,frame_idx,guide,scale,*args,**kwargs):
            self.assertEqual(frame_idx,0)
            return dict(cond,keyframe_idxs=torch.zeros((1,3,guide.shape[2]*guide.shape[3]*guide.shape[4],2)))
        for frames in (241,305):
            latent=(frames-1)//8+1
            original=torch.randn((1,128,latent,2,2),device='cpu')
            guide=torch.randn_like(original);mask=torch.ones((1,1,latent,1,1),device='cpu');mask[:,:,0]=0
            positive,negative,sampled,noise=self.append(SimpleNamespace(add_keyframe_index=metadata),{}, {},0,original,mask,guide,1.,(8,32,32))
            self.assertEqual(sampled.shape[2],2*latent)
            self.assertEqual(float(noise[:,:,latent:].sum()),0.)
            pos,neg,result=self.crop(None,positive,negative,dict(samples=sampled,noise_mask=noise))
            torch.testing.assert_close(result['samples'],original)
            torch.testing.assert_close(result['noise_mask'],mask)
            self.assertEqual((result['samples'].shape[2]-1)*8+1,frames)
            self.assertIsNone(pos['keyframe_idxs']);self.assertIsNone(neg['keyframe_idxs'])

    def test_native_pose_then_photo_uses_original_endpoint_and_crops_both_contexts(self):
        calls=[]
        def metadata(cond,frame_idx,guide,scale,*args,**kwargs):
            calls.append(frame_idx)
            tokens=torch.full((1,3,guide.shape[2]*guide.shape[3]*guide.shape[4],2),float(frame_idx))
            previous=cond.get('keyframe_idxs')
            return dict(cond,keyframe_idxs=tokens if previous is None else torch.cat([previous,tokens],dim=2))
        owner=SimpleNamespace(add_keyframe_index=metadata)
        for frames in (241,305):
            latent=(frames-1)//8+1;scale=(8,32,32);calls.clear()
            original=torch.randn((1,128,latent,2,2),device='cpu')
            pose_guide=torch.randn_like(original)
            photo=torch.randn((1,128,1,2,2),device='cpu')
            mask=torch.ones((1,1,latent,1,1),device='cpu');mask[:,:,0]=0
            positive,negative,posed,noise=self.append(owner,{}, {},0,original,mask,pose_guide,1.,scale)
            # Actual native index code subtracts the already appended pose
            # keyframes; even -1 means the original video's last frame.
            for requested in (frames-1,-1):
                frame_idx,latent_idx=self.latent_index(None,positive,posed.shape[2],1,requested,scale,
                                                      latent_shape=posed.shape)
                self.assertEqual((frame_idx,latent_idx),(frames-1,latent-1))
            positive,negative,sampled,noise=self.append(owner,positive,negative,frames-1,posed,noise,photo,1.,scale)
            self.assertEqual(calls,[0,0,frames-1,frames-1])
            self.assertEqual(sampled.shape[2],2*latent+1)
            torch.testing.assert_close(sampled[:,:,:latent],original)
            torch.testing.assert_close(sampled[:,:,latent:2*latent],pose_guide)
            torch.testing.assert_close(sampled[:,:,-1:],photo)
            self.assertEqual(positive['keyframe_idxs'].shape[2],(latent+1)*4)
            self.assertEqual(negative['keyframe_idxs'].shape[2],(latent+1)*4)
            self.assertEqual(float(noise[:,:,latent:].sum()),0.)
            pos,neg,result=self.crop(None,positive,negative,dict(samples=sampled,noise_mask=noise))
            torch.testing.assert_close(result['samples'],original)
            torch.testing.assert_close(result['noise_mask'],mask)
            self.assertEqual((result['samples'].shape[2]-1)*8+1,frames)
            self.assertIsNone(pos['keyframe_idxs']);self.assertIsNone(neg['keyframe_idxs'])


if __name__=='__main__':unittest.main()
