"""Native-guide graph and tiny CPU tensor tests; no Comfy import or GPU.

Local native methods are read with AST and executed with mock conditioning/IO.
No VAE/model weights are loaded; no generated motion is approved by these tests.
"""
import ast
import copy
from pathlib import Path
from types import SimpleNamespace
import unittest

import torch

from tools.rehab_ml.synthetic.generation import workflow
from tools.rehab_ml.synthetic.guidance import (with_first_last_reference,
    guidance_contract,validate_decoded_result)

NATIVE=Path('E:/ai-video-lab/ComfyUI/comfy_extras/nodes_lt.py')


class GuidanceGraphTests(unittest.TestCase):
    def test_same_reference_pins_start_and_guides_last_with_both_conditionings(self):
        for frames in (241,305):
            original=workflow('TEST-text','TEST-guided',17,frames,'TEST-adult-reference.png')
            frozen=copy.deepcopy(original)
            graph=with_first_last_reference(original,frames=frames)
            self.assertEqual(original,frozen)
            guide=graph['23']['inputs']
            self.assertEqual(guide['frame_idx'],frames-1)
            self.assertEqual(guide['image'],graph['22']['inputs']['image'])
            self.assertEqual(guide['latent'],['22',0])
            self.assertEqual(graph['10']['inputs']['positive'],['23',0])
            self.assertEqual(graph['10']['inputs']['negative'],['23',1])
            self.assertEqual(guide['positive'],['5',0]);self.assertEqual(guide['negative'],['5',1])
            self.assertEqual(graph['9']['inputs']['video_latent'],['23',2])
            self.assertEqual(graph['9']['inputs']['audio_latent'],['8',0])
            self.assertEqual(graph['8']['inputs']['frames_number'],frames)
            self.assertEqual(graph['6']['inputs']['length'],frames)
            self.assertEqual(graph['18']['inputs']['crop_height'],0)

    def test_sampled_AV_is_separated_before_crop_then_cache_and_decode(self):
        graph=with_first_last_reference(workflow('TEST','TEST',7,241,'TEST.png'))
        self.assertEqual(graph['14']['inputs']['latent_image'],['9',0])
        self.assertEqual(graph['15']['inputs']['av_latent'],['14',0])
        self.assertEqual(graph['24']['class_type'],'LTXVCropGuides')
        self.assertEqual(graph['24']['inputs'],dict(positive=['23',0],negative=['23',1],latent=['15',0]))
        self.assertEqual(graph['19']['inputs']['samples'],['24',2])
        self.assertEqual(graph['17']['inputs']['samples'],['19',0])
        self.assertFalse(any(word in node['class_type'].lower() for node in graph.values() for word in ('loop','repeat','reverse','interpolat')))

    def test_contract_counts_appended_guide_and_restored_original_length_without_GT_claim(self):
        for frames,latent in ((241,31),(305,39)):
            contract=guidance_contract(frames)
            self.assertEqual(contract['original_video_latent_frames'],latent)
            self.assertEqual(contract['sampled_video_latent_frames'],latent+1)
            self.assertEqual(contract['cropped_video_latent_frames'],latent)
            self.assertEqual(contract['expected_decoded_frames'],frames)
            self.assertFalse(contract['action_completion_guaranteed'])
            self.assertFalse(contract['creates_labels'])

    def test_missing_reference_double_transform_or_AV_attached_first_is_rejected(self):
        with self.assertRaises(ValueError):with_first_last_reference(workflow('TEST','TEST',7,241))
        graph=with_first_last_reference(workflow('TEST','TEST',7,241,'TEST.png'))
        with self.assertRaises(ValueError):with_first_last_reference(graph)
        graph=workflow('TEST','TEST',7,241,'TEST.png');graph['22']['inputs']['latent']=['9',0]
        with self.assertRaisesRegex(ValueError,'edges'):with_first_last_reference(graph)

    def test_invalid_frame_count_strength_or_mismatched_requested_frames_rejected(self):
        for value in (0,240,304,True):
            with self.assertRaises(ValueError):guidance_contract(value)
        for strength in (0,-1,1.1,float('nan'),True):
            with self.assertRaises(ValueError):guidance_contract(241,strength=strength)
        with self.assertRaisesRegex(ValueError,'disagree'):
            with_first_last_reference(workflow('TEST','TEST',7,241,'TEST.png'),frames=305)

    def test_final_verification_requires_actual_full_decode_geometry_and_pts(self):
        probe=dict(width=640,height=384,frame_count=241,presentation_s=[i/30 for i in range(241)],
                   provenance=dict(full_decode_verified=True))
        result=validate_decoded_result(probe,frames=241)
        self.assertEqual(result['actual_decoded_frames'],241)
        self.assertFalse(result['action_correctness_verified'])
        for field,value in (('frame_count',249),('height',400),('provenance',{})):
            with self.assertRaises(ValueError):validate_decoded_result(dict(probe,**{field:value}),frames=241)
        altered=copy.deepcopy(probe);altered['presentation_s'][3]+=.01
        with self.assertRaises(ValueError):validate_decoded_result(altered,frames=241)


@unittest.skipUnless(NATIVE.is_file(),'pinned local Comfy native source unavailable; structural tests remain portable')
class LocalNativeGuideTensorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree=ast.parse(NATIVE.read_text(encoding='utf-8'))
        namespace=dict(torch=torch,io=SimpleNamespace(NodeOutput=lambda *values:values),
            node_helpers=SimpleNamespace(conditioning_set_values=lambda cond,values:{**cond,**values}),
            conditioning_get_any_value=lambda cond,key,default=None:cond.get(key,default))
        for name in ('get_noise_mask','get_keyframe_idxs'):
            node=copy.deepcopy(next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name))
            exec(compile(ast.Module(body=[node],type_ignores=[]),str(NATIVE),'exec'),namespace)
        def native(class_name,name):
            parent=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==class_name)
            node=copy.deepcopy(next(n for n in parent.body if isinstance(n,ast.FunctionDef) and n.name==name))
            node.decorator_list=[]
            scope=dict(namespace)
            exec(compile(ast.Module(body=[node],type_ignores=[]),str(NATIVE),'exec'),scope)
            return scope[name]
        cls.append=staticmethod(native('LTXVAddGuide','append_keyframe'))
        cls.crop=staticmethod(native('LTXVCropGuides','execute'))
        cls.index=staticmethod(native('LTXVAddGuide','get_latent_index'))

    def test_native_append_then_crop_restores_241_and305_latents_and_clears_metadata(self):
        def index_condition(cond,frame_idx,guide,scale_factors,downscale_factor=1,causal_fix=None):
            tokens=guide.shape[2]*guide.shape[3]*guide.shape[4]
            coords=torch.zeros((1,3,tokens,2));coords[:,0,:,0]=frame_idx
            return dict(cond,keyframe_idxs=coords)
        mock_cls=SimpleNamespace(add_keyframe_index=index_condition)
        for frames in (241,305):
            latent_length=(frames-1)//8+1
            samples=torch.zeros((1,128,latent_length,2,2),device='cpu')
            noise=torch.ones((1,1,latent_length,1,1),device='cpu');noise[:,:,0]=0.
            guide=torch.ones((1,128,1,2,2),device='cpu')
            positive,negative,appended,mask=self.append(mock_cls,{}, {},frames-1,samples,noise,guide,1.,(8,32,32))
            self.assertIn('keyframe_idxs',positive);self.assertIn('keyframe_idxs',negative)
            self.assertEqual(appended.shape[2],latent_length+1)
            self.assertEqual(float(mask[:,:,-1].sum()),0.)
            pos,neg,clean=self.crop(None,positive,negative,dict(samples=appended,noise_mask=mask))
            self.assertEqual(clean['samples'].shape,samples.shape)
            torch.testing.assert_close(clean['samples'],samples)
            torch.testing.assert_close(clean['noise_mask'],noise)
            self.assertIsNone(pos['keyframe_idxs']);self.assertIsNone(neg['keyframe_idxs'])
            self.assertEqual((clean['samples'].shape[2]-1)*8+1,frames)

    def test_native_last_single_image_index_is_final_original_frame(self):
        for frames in (241,305):
            latent=(frames-1)//8+1
            shape=(1,128,latent,2,2)
            resolved,index=self.index(None,{},latent,1,-1,(8,32,32),latent_shape=shape)
            self.assertEqual(resolved,frames-1);self.assertEqual(index,latent-1)

    def test_native_guide_rejects_combined_AV_channels(self):
        with self.assertRaisesRegex(ValueError,'combined AV'):
            self.append(SimpleNamespace(),{}, {},240,torch.zeros((1,129,31,2,2)),
                torch.ones((1,1,31,1,1)),torch.ones((1,128,1,2,2)),1.,(8,32,32))


if __name__=='__main__':unittest.main()
