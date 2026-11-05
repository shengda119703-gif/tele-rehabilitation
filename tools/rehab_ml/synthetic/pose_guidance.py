"""Pure native-node adapter for the pinned LTX-2 19B pose IC-LoRA.

This is a single-stage adaptation of the official two-stage distilled graph.
Quantized GGUF inference, 8GB memory use and generated motion quality still need
independent local execution. A rendered skeleton video is a requested control,
never an observed action label or ground truth for the output video.
"""
from __future__ import annotations

import copy
import math
import re

from .guidance import with_first_last_reference,validate_decoded_result

VERSION='rehab_ltx19_pose_video_guidance/v1'
ENDPOINT_VERSION='rehab_ltx19_pose_video_guidance/v2'
POSE_LORA_NAME='ltx-2-19b-ic-lora-pose-control.safetensors'
DISTILLED_SIGMAS=(1.,.99375,.9875,.98125,.975,.909375,.725,.421875,0.)
OFFICIAL_EVIDENCE=dict(
    model_repo='Lightricks/LTX-2-19b-IC-LoRA-Pose-Control',
    model_revision='ecdabfb03acd2e807c90ea260ccc136140e7ac80',
    model_sha256='61816bf0985d4470c456160deec65df69188ae45d553e5aa8f1252fc543bc8aa',
    model_bytes=654465256,
    workflow_repo='Lightricks/ComfyUI-LTXVideo',
    workflow_revision='44c8a36b7c31ee00b4271daed11dc2a4aa481140',
    workflow_path='example_workflows/2.0/LTX-2_ICLoRA_All_Distilled.json',
    workflow_sha256='de937be1e8375729a18125712284fafde4b32de1fca6ae73fccecf2864468671',
    pose_sampler_subgraph_id='86f813ec-498a-443f-a54c-53a2ee60365e',
    pose_sampler_subgraph_index=2,
    model_card_url='https://huggingface.co/Lightricks/LTX-2-19b-IC-LoRA-Pose-Control',
    workflow_url='https://github.com/Lightricks/ComfyUI-LTXVideo/blob/44c8a36b7c31ee00b4271daed11dc2a4aa481140/example_workflows/2.0/LTX-2_ICLoRA_All_Distilled.json')


def _control_file(value):
    if not isinstance(value,str) or re.fullmatch(r'[A-Za-z0-9_.-]+\.mp4',value,re.IGNORECASE) is None:
        raise ValueError('verified_control_mp4_basename_inside_Comfy_input_required')
    return value


def pose_guidance_contract(frames=241,*,control_file=None,control_sha256=None,lora_name=POSE_LORA_NAME,
                           lora_strength=1.,guide_strength=1.,endpoint_reference=False):
    if type(endpoint_reference) is not bool:
        raise ValueError('explicit_boolean_endpoint_reference_required')
    if type(frames) is not int or not 9<=frames<=1000 or (frames-1)%8:
        raise ValueError('native_LTX_8n_plus_1_motion_frame_count_required')
    if lora_name!=POSE_LORA_NAME:raise ValueError('pinned_LTX2_19B_pose_IC_LoRA_only_no_2_5_substitution')
    for name,value,maximum in (('lora_strength',lora_strength,2.),('guide_strength',guide_strength,1.)):
        if type(value) not in (int,float) or not math.isfinite(value) or not 0<value<=maximum:
            raise ValueError('bounded_positive_'+name+'_required')
    if control_file is not None:_control_file(control_file)
    if control_sha256 is not None and (not isinstance(control_sha256,str) or re.fullmatch(r'[0-9a-f]{64}',control_sha256) is None):
        raise ValueError('control_source_sha256_required_when_supplied')
    latent=(frames-1)//8+1
    result=dict(version=VERSION,experimental=True,requested_frames=frames,control_file=control_file,
        control_sha256=control_sha256,lora_name=lora_name,lora_strength=float(lora_strength),
        guide_strength=float(guide_strength),guide_frame_index=0,reference_downscale_factor=1,
        original_video_latent_frames=latent,appended_guide_latent_frames=latent,
        sampled_video_latent_frames=2*latent,cropped_video_latent_frames=latent,
        expected_decoded_frames=frames,frame_rate=30,
        sampler='euler',sigmas=list(DISTILLED_SIGMAS),cfg=1.,
        official_evidence=copy.deepcopy(OFFICIAL_EVIDENCE),
        adaptation='single_stage_640x384_no_official_upscale_refine_pass',
        official_workflow_has_two_stages=True,official_BF16_distilled_graph_evidence=True,
        local_GGUF_pose_inference_verified=False,local_8GB_memory_verified=False,
        guide_representation='pre_rendered_OpenPose_DWPose_style_RGB_video_on_black',
        body_only_control_quality_verified=False,
        extra_weights=[POSE_LORA_NAME],extra_plugins_required=False,
        native_nodes=['LoraLoaderModelOnly','LoadVideo','GetVideoComponents','LTXVAddGuide','LTXVCropGuides'],
        decoded_frames_must_be_independently_verified=True,control_is_requested_not_observed=True,
        output_action_completion_guaranteed=False,creates_labels=False,independent_motion_ground_truth=False,
        loop_reverse_splice_or_interpolation=False)
    if endpoint_reference:
        result.update(version=ENDPOINT_VERSION,endpoint_reference=True,
            same_reference_for_first_and_last=True,
            endpoint_reference_image='same_LoadImage_21_used_for_first_frame',
            endpoint_guide_frame_index=frames-1,endpoint_guide_strength=1.,
            pose_guide_latent_frames=latent,endpoint_guide_latent_frames=1,
            appended_guide_latent_frames=latent+1,sampled_video_latent_frames=2*latent+1,
            endpoint_fade_fix_guaranteed=False,local_endpoint_reference_inference_verified=False,
            ordering='pose_guide_then_same_reference_endpoint_then_AV_merge_then_sample_then_video_separate_then_crop_then_cache_decode')
    return result


def with_pose_video(graph,control_file,frames=241,lora_name=POSE_LORA_NAME,lora_strength=1.,guide_strength=1.,
                    *,endpoint_reference=False):
    """Guide every original video frame and crop only appended latent context.

    The caller must verify the control video's SHA/geometry/RGB/real PTS before
    submitting this graph. The graph itself is only a pure, non-executing plan.
    The optional endpoint uses the same first-frame photo after the pose guide.
    Already transformed input graphs are refused, including endpoint-only ones.
    """
    _control_file(control_file)
    pose_guidance_contract(frames,control_file=control_file,lora_name=lora_name,
        lora_strength=lora_strength,guide_strength=guide_strength,endpoint_reference=endpoint_reference)
    # Reuse the strict original I2V/AV/cache topology validation. The endpoint
    # graph returned by this helper is deliberately NOT used or submitted.
    with_first_last_reference(graph,frames=frames,strength=guide_strength)
    result=copy.deepcopy(graph)
    if (result['6']['inputs'].get('width'),result['6']['inputs'].get('height'))!=(640,384):
        raise ValueError('pinned_single_stage_pose_control_profile_requires_640x384')
    if any(str(n) in result for n in range(31,36)):
        raise ValueError('pose_guidance_node_ids_31_through_35_already_in_use')
    if '36' in result:
        raise ValueError('pose_endpoint_node_id_36_already_in_use')
    model=result['1']
    if (model.get('class_type')!='LabLTXGGUFLoader'
            or model.get('inputs',{}).get('unet_name')!='ltx-2-19b-distilled_Q4_K_M.gguf'
            or result['10']['inputs'].get('model')!=['1',0]):
        raise ValueError('pinned_19B_distilled_GGUF_base_model_required')
    if result['12'].get('class_type')!='KSamplerSelect' or result['13'].get('class_type')!='ManualSigmas':
        raise ValueError('pinned_single_stage_distilled_sampler_nodes_required')
    result['31']=dict(class_type='LoraLoaderModelOnly',inputs=dict(model=['1',0],lora_name=lora_name,strength_model=float(lora_strength)))
    result['32']=dict(class_type='LoadVideo',inputs=dict(file=control_file))
    result['33']=dict(class_type='GetVideoComponents',inputs=dict(video=['32',0]))
    result['34']=dict(class_type='LTXVAddGuide',inputs=dict(positive=['5',0],negative=['5',1],
        vae=['16',0],latent=['22',0],image=['33',0],frame_idx=0,strength=float(guide_strength)))
    result['9']['inputs']['video_latent']=['34',2]
    result['10']['inputs'].update(model=['31',0],positive=['34',0],negative=['34',1],cfg=1.)
    result['12']['inputs']['sampler_name']='euler'
    result['13']['inputs']['sigmas']=', '.join(str(value) for value in DISTILLED_SIGMAS)
    result['35']=dict(class_type='LTXVCropGuides',inputs=dict(positive=['34',0],negative=['34',1],latent=['15',0]))
    result['19']['inputs']['samples']=['35',2]
    if endpoint_reference:
        result['36']=dict(class_type='LTXVAddGuide',inputs=dict(positive=['34',0],negative=['34',1],
            vae=['16',0],latent=['34',2],image=['21',0],frame_idx=frames-1,strength=1.))
        result['9']['inputs']['video_latent']=['36',2]
        result['10']['inputs'].update(positive=['36',0],negative=['36',1])
        result['35']['inputs'].update(positive=['36',0],negative=['36',1])
    return result


def validate_control_probe(probe,*,frames=241,width=640,height=384):
    """Validate a fresh actual RGB decode, never nominal FPS or control labels."""
    checked=validate_decoded_result(probe,frames=frames,width=width,height=height)
    if probe.get('provenance',{}).get('pixel_format')!='rgb24':
        raise ValueError('full_control_decode_must_preserve_RGB24_not_BGR_swapped_palette')
    source_sha=probe.get('video_sha256')
    if not isinstance(source_sha,str) or re.fullmatch(r'[0-9a-f]{64}',source_sha) is None:
        raise ValueError('actual_control_source_sha256_required')
    rows=probe.get('frames')
    if not isinstance(rows,list) or len(rows)!=frames:
        raise ValueError('complete_control_RGB_frame_inventory_required')
    for index,(row,stamp) in enumerate(zip(rows,probe['presentation_s'])):
        sha=row.get('decoded_rgb_sha256')
        if (row.get('frame_index')!=index or row.get('timestamp_s')!=stamp
                or not isinstance(sha,str) or re.fullmatch(r'[0-9a-f]{64}',sha) is None):
            raise ValueError('actual_control_RGB_fingerprints_and_pts_required')
    return dict(checked,control_sha256=source_sha,RGB_pixel_fingerprints_verified=True,
        body_motion_correctness_verified=False,control_is_not_output_ground_truth=True)
