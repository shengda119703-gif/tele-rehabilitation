"""Experimental native LTX first/last-reference graph transform (no execution).

The first frame retains the lab's validated ImgToVideoInplace path. One native
AddGuide appends the SAME reference as an endpoint condition, before AV merge.
After sampling, separate video before cropping its appended guide latent.

This encourages an endpoint appearance; it does not guarantee a return, one
arm, stable anatomy or any correct action. It creates neither labels nor GT.
It never repeats, reverses, splices or interpolates decoded video frames.
"""
from __future__ import annotations

import copy
import math

VERSION='rehab_ltx_first_last_reference/v1'
REQUIRED_NATIVE_NODES=('LTXVImgToVideoInplace','LTXVAddGuide','LTXVCropGuides',
                       'LTXVConcatAVLatent','LTXVSeparateAVLatent')


def guidance_contract(frames,*,strength=1.):
    if type(frames) is not int or not 9<=frames<=1000 or (frames-1)%8:
        raise ValueError('native_LTX_8n_plus_1_motion_frame_count_required')
    if type(strength) not in (int,float) or not math.isfinite(strength) or not 0<strength<=1:
        raise ValueError('bounded_positive_endpoint_reference_strength_required')
    latent=(frames-1)//8+1
    return dict(version=VERSION,experimental=True,requested_frames=frames,
        first_frame='existing_LTXVImgToVideoInplace',last_frame='native_LTXVAddGuide',
        guide_frame_index=frames-1,guide_strength=float(strength),same_reference_for_first_and_last=True,
        original_video_latent_frames=latent,appended_guide_latent_frames=1,
        sampled_video_latent_frames=latent+1,cropped_video_latent_frames=latent,
        expected_decoded_frames=(latent-1)*8+1,decoded_frames_must_be_independently_verified=True,
        required_native_nodes=list(REQUIRED_NATIVE_NODES),
        conditioning='guide_positive_and_negative_both_reach_CFGGuider',
        ordering='video_guide_then_AV_merge_then_sample_then_video_separate_then_crop_then_cache_decode',
        creates_labels=False,independent_motion_ground_truth=False,action_completion_guaranteed=False,
        postprocessing_repeat_reverse_loop_or_interpolation=False)


def with_first_last_reference(graph,*,frames=None,strength=1.):
    """Return a new graph for the pinned lab topology; refuse ambiguous variants.

    Input is ``generation.workflow(..., image=<reference>)``. Positive/negative
    output slots 0/1 from the guide must reach CFGGuider; latent slot 2 enters
    AV concatenation. CropGuides consumes separated VIDEO and the same guide
    metadata, and only cropped latent slot 2 reaches cache/decode.
    """
    if not isinstance(graph,dict):raise ValueError('explicit_workflow_graph_required')
    result=copy.deepcopy(graph)
    def inputs(number,kind):
        node=result.get(str(number),{})
        if node.get('class_type')!=kind or not isinstance(node.get('inputs'),dict):
            raise ValueError('pinned_lab_workflow_node_required:'+str(number)+':'+kind)
        return node['inputs']
    video=inputs(6,'EmptyLTXVLatentVideo');start=inputs(22,'LTXVImgToVideoInplace')
    image=inputs(21,'LoadImage');condition=inputs(5,'LTXVConditioning')
    audio=inputs(8,'LTXVEmptyLatentAudio');concat=inputs(9,'LTXVConcatAVLatent')
    guider=inputs(10,'CFGGuider');sampler=inputs(14,'SamplerCustomAdvanced')
    separate=inputs(15,'LTXVSeparateAVLatent');cache=inputs(19,'LabCacheLatent')
    decode=inputs(17,'VAEDecodeTiled');save=inputs(18,'LabSaveMP4')
    inputs(16,'VAELoader')
    count=video.get('length')
    if frames is not None and frames!=count:raise ValueError('requested_frames_disagree_with_latent_graph')
    guidance_contract(count,strength=strength)
    if any(node.get('class_type') in ('LTXVAddGuide','LTXVCropGuides') for node in result.values()):
        raise ValueError('guide_transform_requires_unguided_workflow_no_double_append')
    if '23' in result or '24' in result:raise ValueError('guide_node_ids_23_24_already_in_use')
    checks=(
        (start.get('latent'),['6',0]),(start.get('image'),['21',0]),(start.get('vae'),['16',0]),
        (concat.get('video_latent'),['22',0]),(concat.get('audio_latent'),['8',0]),
        (guider.get('positive'),['5',0]),(guider.get('negative'),['5',1]),
        (sampler.get('latent_image'),['9',0]),(sampler.get('guider'),['10',0]),
        (separate.get('av_latent'),['14',0]),(cache.get('samples'),['15',0]),
        (decode.get('samples'),['19',0]),(save.get('images'),['17',0]))
    if any(actual!=expected for actual,expected in checks):
        raise ValueError('guide_transform_requires_original_video_AV_sampling_and_decode_edges')
    if (not image.get('image') or start.get('bypass') is not False or start.get('strength')!=1.
            or audio.get('frames_number')!=count or condition.get('frame_rate')!=30.
            or audio.get('frame_rate')!=30. or save.get('fps')!=30 or save.get('crop_height')!=0):
        raise ValueError('native_first_frame_reference_and_30fps_uncropped_output_required')
    result['23']=dict(class_type='LTXVAddGuide',inputs=dict(positive=['5',0],negative=['5',1],
        vae=['16',0],latent=['22',0],image=['21',0],frame_idx=count-1,strength=float(strength)))
    concat['video_latent']=['23',2]
    guider['positive'],guider['negative']=['23',0],['23',1]
    result['24']=dict(class_type='LTXVCropGuides',inputs=dict(positive=['23',0],negative=['23',1],latent=['15',0]))
    cache['samples']=['24',2]
    return result


def validate_decoded_result(probe,*,frames,width=640,height=384):
    """Check a fresh ``video.probe_video`` full decode, not a generated claim.

    This pure function does not decode media itself. The caller must obtain the
    probe by fully decoding the immutable output before using this result.
    """
    guidance_contract(frames)
    if probe.get('provenance',{}).get('full_decode_verified') is not True:
        raise ValueError('fresh_full_decode_probe_required_not_nominal_frame_math')
    if (probe.get('width'),probe.get('height'),probe.get('frame_count'))!=(width,height,frames):
        raise ValueError('guided_decoded_geometry_or_frame_count_changed')
    stamps=probe.get('presentation_s')
    if (not isinstance(stamps,list) or len(stamps)!=frames
            or any(type(t) not in (int,float) or not math.isfinite(t) or t<0 for t in stamps)
            or any(abs((b-a)-1/30)>1e-6 for a,b in zip(stamps,stamps[1:]))):
        raise ValueError('guided_output_requires_actual_complete_30fps_pts')
    return dict(version=VERSION,actual_decoded_frames=frames,width=width,height=height,
        fps_verified_from_real_pts=30,action_correctness_verified=False,labels_created=False)
