"""Pilot/train-only distinct endpoint photos, bound to actual parent pixels.

This experiment conditions a new video on a frame from an existing D candidate.
It never labels either video or verifies that the generated movement is correct.
The live generator's same-reference D prohibition is deliberately unchanged.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil

from . import contracts as c, control, generation as g
from .guidance import validate_decoded_result
from .pose_guidance import pose_guidance_contract
from .video import probe_video

VERSION = 'rehab_synthetic_endpoint/v1'
GUIDANCE_VERSION = 'rehab_synthetic_distinct_endpoint_guidance/v1'
FLAGS = dict(is_GT=False, training_reference_eligible=False, creates_human_annotations=False,
    endpoint_frame_is_output_label=False, endpoint_pose_correctness_verified=False)


def _within(root, value):
    path = Path(value)
    path = path.resolve() if path.is_absolute() else (root/path).resolve()
    if not path.is_relative_to(root):
        raise ValueError('endpoint_asset_outside_declared_dataset_root')
    return path


def _json(path):
    return c._read_json(Path(path))


def _snapshot(paths):
    return {str(path.resolve()): g.digest(path) for path in paths}


def _unchanged(snapshot):
    if any(g.digest(Path(path)) != sha for path, sha in snapshot.items()):
        raise ValueError('endpoint_source_asset_changed_during_operation')


def _png(path):
    from PIL import Image
    with Image.open(path) as image:
        if image.format != 'PNG' or image.mode != 'RGB' or image.size != (640, 384) or getattr(image, 'n_frames', 1) != 1:
            raise ValueError('single_original_640x384_RGB_PNG_required')
        return hashlib.sha256(image.tobytes()).hexdigest()


def _frame(video, index, row):
    import av
    with av.open(str(video)) as container:
        for number, frame in enumerate(container.decode(video=0)):
            if number == index:
                rgb = frame.to_ndarray(format='rgb24')
                if (frame.pts != row['pts'] or [frame.time_base.numerator, frame.time_base.denominator] != row['time_base']
                        or hashlib.sha256(rgb.tobytes()).hexdigest() != row['decoded_rgb_sha256']):
                    raise ValueError('endpoint_selected_frame_PTS_or_RGB_changed')
                return frame.to_image()
    raise ValueError('endpoint_selected_frame_not_decoded')


def _parent(root, sample_id):
    """Verify completed durable generation plus full original-media evidence."""
    manifest = c.load_manifest(root/'manifests/dataset.json', verify_files=True)
    selected = [row for row in manifest['samples'] if row['sample_id'] == sample_id]
    if len(selected) != 1:
        raise ValueError('one_existing_endpoint_parent_sample_required')
    parent = selected[0]
    if (parent.get('stage') != 'pilot' or parent.get('split') != 'train' or parent.get('scenario') != 'D'
            or parent.get('exercise_id') != 'shoulder_abduction' or parent.get('view') not in ('front', 'frontal')):
        raise ValueError('endpoint_parent_requires_explicit_pilot_train_frontal_shoulder_D')
    record_path = _within(root, root/'manifests'/(sample_id+'.json'))
    if _json(record_path) != parent:
        raise ValueError('endpoint_parent_completed_record_disagrees_with_inventory')
    movie, timeline = (_within(root, parent['video'][key]) for key in ('path', 'timeline_path'))
    job_path = _within(root, parent['generation']['workflow_job_path'])
    job = _json(job_path)
    if (job.get('name') != sample_id or not job.get('prompt_id') or job.get('status') != 'success'
            or job.get('history', {}).get('status', {}).get('status_str') != 'success'
            or job.get('workflow_sha256') != parent['generation']['workflow_sha256']
            or g.canonical(job.get('workflow')) != job['workflow_sha256']):
        raise ValueError('endpoint_parent_requires_authoritative_completed_generation_job')
    actual = probe_video(movie)
    saved = _json(timeline)
    validate_decoded_result(actual, frames=241)
    if not g.same_media_timeline(saved, actual):
        raise ValueError('endpoint_parent_full_actual_timeline_changed')
    if not parent['generation'].get('pose_control'):
        raise ValueError('endpoint_parent_requires_bound_pose_control_provenance')
    return parent, actual, [record_path, movie, timeline, job_path]


def _control(root, path, parent):
    path = _within(root, path)
    metadata = parent['generation']['pose_control']
    if (path != _within(root, metadata['receipt_path']) or g.digest(path) != metadata['receipt_sha256']):
        raise ValueError('endpoint_control_must_be_same_bound_parent_controller')
    receipt = control.load_control(path, verify=True,
        expected_source_group_id=parent['source_group_id'], expected_scenario='D')
    source = receipt['source']
    if (source.get('reference_group_id') != parent['reference_group_id']
            or source.get('stage') != 'pilot' or source.get('split') != 'train'
            or receipt['video_sha256'] != metadata['control_video_sha256']
            or receipt['controller_trajectory_sha256'] != metadata['trajectory_sha256']
            or source['source_pose_sha256'] != metadata['pose_source_sha256']
            or not set(receipt['lineage_ids']) <= set(parent['lineage_ids'])):
        raise ValueError('endpoint_parent_control_group_reference_or_source_lineage_mismatch')
    ref_path = _within(root, source['reference_record'])
    reference = _json(ref_path)
    if (reference.get('source_group_id') != parent['source_group_id']
            or reference.get('reference_group_id') != parent['reference_group_id']
            or reference.get('stage') != 'pilot' or reference.get('split') != 'train'
            or reference.get('image_sha256') != source['reference_image_sha256']
            or reference.get('structural_review',{}).get('status') != 'usable_as_initial_condition'
            or 'reference:'+source['reference_image_sha256'] not in parent['lineage_ids']):
        raise ValueError('endpoint_initial_reference_must_have_same_pilot_train_origin')
    assets = [path, ref_path]
    for owner, keys in ((receipt, ('video', 'actual_pts_timeline', 'controller_trajectory', 'initial_source_path')),
                        (source, ('reference_image', 'reference_video', 'source_pose_path'))):
        assets.extend(_within(root, owner[key]) for key in keys)
    # The style is an externally pinned, independently verified implementation;
    # it is snapshotted as provenance, never inserted into source lineage.
    assets.append(Path(receipt['style']['path']).resolve())
    return receipt, reference, assets


def create_endpoint(root, parent_sample_id, frame_index, output_dir, *, pose_control):
    """Extract one actual D frame as an immutable PNG plus a source receipt.

    Writes only to the caller's new directory inside this dataset. It does not
    submit a job, annotate a video, approve a sample, or change the manifest.
    """
    root = Path(root).resolve()
    parent, timeline, assets = _parent(root, parent_sample_id)
    controller, reference, control_assets = _control(root, pose_control, parent)
    if type(frame_index) is not int or not 1 <= frame_index < timeline['frame_count']:
        raise ValueError('explicit_nonfirst_actual_endpoint_frame_index_required')
    output = _within(root, output_dir)
    relative = output.relative_to(root)
    if not relative.parts or relative.parts[0] not in ('features','conditioning-endpoints'):
        raise ValueError('new_endpoint_output_inside_features_or_conditioning_endpoints_required')
    if output.exists():
        raise ValueError('new_endpoint_directory_required_no_overwrite')
    before = _snapshot(assets+control_assets)
    row = timeline['frames'][frame_index]
    image = _frame(_within(root, parent['video']['path']), frame_index, row)
    if hashlib.sha256(image.tobytes()).hexdigest() == _png(_within(root, reference['image_path'])):
        raise ValueError('distinct_endpoint_must_not_equal_initial_reference_pixels')
    _unchanged(before)
    output.mkdir(parents=True, exist_ok=False)
    png = output/'endpoint.png'
    with png.open('xb') as stream:
        image.save(stream, format='PNG')
    receipt = dict(schema_version=VERSION, parent_sample_id=parent_sample_id,
        source_group_id=parent['source_group_id'], reference_group_id=parent['reference_group_id'],
        stage='pilot', split='train', scenario='D',
        parent_video=copy.deepcopy(parent['video']), parent_record_sha256=before[str(assets[0].resolve())],
        parent_workflow_sha256=parent['generation']['workflow_sha256'],
        control_receipt_path=str(_within(root, pose_control)), control_receipt_sha256=g.digest(_within(root, pose_control)),
        frame=copy.deepcopy(row), image=dict(path=str(png), sha256=g.digest(png), width=640, height=384,
            decoded_rgb_sha256=_png(png)),
        lineage_ids=list(dict.fromkeys([*parent['lineage_ids'], parent_sample_id,
            'endpoint_parent_video:'+parent['video']['sha256'], 'endpoint_png:'+g.digest(png)])),
        **FLAGS)
    path = output/'endpoint.json'
    g.write_new(path, receipt)
    _unchanged(before)
    return validate_endpoint(root, path, pose_control=pose_control)


def validate_endpoint(root, receipt_path, *, pose_control, source_group_id=None):
    """Read-only full source/PTS/pixel/controller verification; no trust flag."""
    root = Path(root).resolve()
    path = _within(root, receipt_path)
    receipt = _json(path)
    external = receipt.get('schema_version') == 'rehab_synthetic_endpoint_image/v1'
    if external:
        parent, actual, assets = _parent(root, receipt.get('source_sample_id'))
        receipt, extra_assets = _normalize_external(root, receipt, parent, actual, pose_control, assets)
    else:
        extra_assets = []
    if (receipt.get('schema_version') != VERSION
            or any(receipt.get(key) is not value for key, value in FLAGS.items())
            or (receipt.get('stage'), receipt.get('split'), receipt.get('scenario')) != ('pilot', 'train', 'D')):
        raise ValueError('explicit_non_GT_pilot_train_D_endpoint_receipt_required')
    if not external:
        parent, actual, assets = _parent(root, receipt['parent_sample_id'])
    controller, reference, control_assets = _control(root, pose_control, parent)
    if (receipt['source_group_id'] != parent['source_group_id']
            or receipt['reference_group_id'] != parent['reference_group_id']
            or source_group_id is not None and receipt['source_group_id'] != source_group_id
            or receipt['parent_video'] != parent['video']
            or receipt['parent_record_sha256'] != g.digest(assets[0])
            or receipt['parent_workflow_sha256'] != parent['generation']['workflow_sha256']
            or _within(root, receipt['control_receipt_path']) != _within(root, pose_control)
            or receipt['control_receipt_sha256'] != g.digest(_within(root, pose_control))):
        raise ValueError('endpoint_parent_group_reference_control_or_original_binding_changed')
    image = receipt['image'];png = _within(root, image['path'])
    before = _snapshot([path,png,*assets,*control_assets,*extra_assets])
    frame = receipt['frame'];index = frame.get('frame_index')
    if type(index) is not int or not 1 <= index < actual['frame_count'] or frame != actual['frames'][index]:
        raise ValueError('endpoint_exact_actual_frame_PTS_index_and_RGB_binding_required')
    _frame(_within(root, parent['video']['path']), index, frame)
    if (g.digest(png) != image['sha256'] or (image.get('width'), image.get('height')) != (640,384)
            or _png(png) != image['decoded_rgb_sha256'] or _png(png) != frame['decoded_rgb_sha256']):
        raise ValueError('endpoint_PNG_must_equal_bound_original_decoded_RGB_frame')
    if image['sha256'] == reference['image_sha256'] or _png(png) == _png(_within(root, reference['image_path'])):
        raise ValueError('distinct_endpoint_must_not_equal_initial_reference_pixels')
    expected = list(dict.fromkeys([*parent['lineage_ids'], parent['sample_id'],
        'endpoint_parent_video:'+parent['video']['sha256'], 'endpoint_png:'+image['sha256']]))
    if receipt.get('lineage_ids') != expected:
        raise ValueError('endpoint_parent_and_derived_source_lineage_changed')
    _unchanged(before)
    return dict(receipt=copy.deepcopy(receipt), receipt_path=str(path), receipt_sha256=g.digest(path),
        parent=copy.deepcopy(parent), control=copy.deepcopy(controller), reference=copy.deepcopy(reference),
        verified_asset_sha256=before, original_pixels_and_PTS_verified=True,
        reviewer_identity_is_verified=False, human_reference_created=False)


def _normalize_external(root, value, parent, actual, pose_control, assets):
    """Verify the earlier extraction receipt without rewriting its bytes."""
    if (value.get('requested_scenario') != 'D'
            or value.get('requested_scenario_is_a_label') is not False
            or value.get('image_RGB_unchanged_from_decoded_source') is not True
            or any(value.get(key) is not False for key in ('source_edited','crop_resize_or_retouch_performed',
                'is_GT','human_review','training_reference_eligible','creates_human_annotations','product_enabled'))
            or (value.get('stage'),value.get('split')) != ('pilot','train')
            or (value.get('source_group_id'),value.get('reference_group_id')) !=
                (parent['source_group_id'],parent['reference_group_id'])
            or _within(root,value['source_video']) != _within(root,parent['video']['path'])
            or value.get('source_video_sha256') != parent['video']['sha256']
            or value.get('source_sha256') != parent['video']['sha256']):
        raise ValueError('legacy_endpoint_requires_bound_unedited_non_GT_pilot_D_source')
    index=value.get('source_frame_index')
    if type(index) is not int or not 1 <= index < actual['frame_count']:
        raise ValueError('endpoint_exact_actual_frame_PTS_index_and_RGB_binding_required')
    frame=actual['frames'][index]
    for key,field in (('source_frame_pts','pts'),('source_frame_time_base','time_base'),
                      ('source_frame_timestamp_s','timestamp_s'),('source_decoded_rgb_sha256','decoded_rgb_sha256')):
        if value.get(key) != frame[field]:
            raise ValueError('legacy_endpoint_actual_frame_PTS_or_RGB_binding_changed')
    if value.get('RGB_sha256') != frame['decoded_rgb_sha256']:
        raise ValueError('legacy_endpoint_actual_frame_PTS_or_RGB_binding_changed')
    snapshot=_within(root,value['source_manifest_snapshot'])
    timeline=_within(root,value['actual_full_pts_timeline'])
    if (g.digest(snapshot) != value['source_manifest_snapshot_sha256'] or _json(snapshot) != parent
            or g.digest(timeline) != value['actual_full_pts_timeline_sha256']
            or not g.same_media_timeline(_json(timeline),actual)):
        raise ValueError('legacy_endpoint_parent_snapshot_or_full_PTS_changed')
    expected=list(dict.fromkeys([*parent['lineage_ids'],
        'endpoint_source_video:'+parent['video']['sha256'],'endpoint_image:'+value['image_sha256']]))
    if value.get('lineage_ids') != expected:
        raise ValueError('legacy_endpoint_parent_source_lineage_changed')
    normalized=dict(schema_version=VERSION,parent_sample_id=parent['sample_id'],
        source_group_id=parent['source_group_id'],reference_group_id=parent['reference_group_id'],
        stage='pilot',split='train',scenario='D',parent_video=copy.deepcopy(parent['video']),
        parent_record_sha256=g.digest(assets[0]),parent_workflow_sha256=parent['generation']['workflow_sha256'],
        control_receipt_path=str(_within(root,pose_control)),control_receipt_sha256=g.digest(_within(root,pose_control)),
        frame=copy.deepcopy(frame),image=dict(path=value['image_path'],sha256=value['image_sha256'],
            width=value['width'],height=value['height'],decoded_rgb_sha256=value['source_decoded_rgb_sha256']),
        lineage_ids=list(dict.fromkeys([*parent['lineage_ids'],parent['sample_id'],
            'endpoint_parent_video:'+parent['video']['sha256'],'endpoint_png:'+value['image_sha256']])),**FLAGS)
    return normalized,[snapshot,timeline]


def with_distinct_endpoint(graph, endpoint_file, *, frames=241):
    """Only replace node36's image by a new LoadImage37 after a strict v2 graph."""
    if type(frames) is not int or frames != 241:
        raise ValueError('distinct_endpoint_experiment_requires_241_native_frames')
    if not isinstance(endpoint_file,str) or re.fullmatch(r'[A-Za-z0-9_.-]+\.png',endpoint_file,re.I) is None:
        raise ValueError('immutable_endpoint_PNG_basename_inside_Comfy_input_required')
    try:
        expected = g.workflow(graph['3']['inputs']['name'], graph['18']['inputs']['name'],
            graph['11']['inputs']['noise_seed'], frames, graph['21']['inputs']['image'],
            pose_file=graph['32']['inputs']['file'], pose_endpoint=True)
    except (KeyError,TypeError) as error:
        raise ValueError('complete_original_pose_endpoint_v2_graph_required') from error
    if graph != expected or endpoint_file == graph['21']['inputs']['image']:
        raise ValueError('unmodified_pose_endpoint_v2_graph_and_distinct_photo_required')
    result = copy.deepcopy(graph)
    result['37'] = dict(class_type='LoadImage', inputs=dict(image=endpoint_file))
    result['36']['inputs']['image'] = ['37',0]
    return result


def endpoint_contract(verified):
    receipt, controller = verified['receipt'], verified['control']
    result = pose_guidance_contract(241, control_sha256=controller['video_sha256'], endpoint_reference=True)
    result.update(version=GUIDANCE_VERSION, same_reference_for_first_and_last=False,
        endpoint_reference_image='LoadImage37_actual_RGB_frame_from_bound_pilot_D_parent',
        endpoint_receipt_sha256=verified['receipt_sha256'], endpoint_png_sha256=receipt['image']['sha256'],
        endpoint_parent_sample_id=receipt['parent_sample_id'], endpoint_source_frame=copy.deepcopy(receipt['frame']),
        ordering='pose_guide_then_distinct_parent_frame_endpoint_then_AV_merge_then_sample_then_crop_then_cache_decode',
        **FLAGS)
    return result


def _input_copy(source, directory, filename, expected):
    target = directory/filename
    if not target.exists():
        with Path(source).open('rb') as incoming, target.open('xb') as outgoing:
            shutil.copyfileobj(incoming, outgoing)
    if g.digest(target) != expected:
        raise ValueError('immutable_endpoint_Comfy_input_copy_changed')
    return target


def _model_assets(root, parent):
    path = root/'manifests/model-verification.json'
    receipt = _json(path)
    if not receipt.get('models') or receipt['models'][0]['sha256'] != parent['generation']['model_sha256']:
        raise ValueError('endpoint_parent_generator_model_receipt_changed')
    paths = [path]
    for model in receipt['models']:
        source = Path(model['path']).resolve()
        if g.digest(source) != model['sha256']:
            raise ValueError('endpoint_pinned_generator_model_bytes_changed')
        paths.append(source)
    return paths


def _conditioning(root, lab, name, key, prompt_sha, *, create=False):
    cache = lab/'ComfyUI/output/conditioning'/(key+'.pt')
    path = root/'manifests/endpoint-conditioning'/(name+'.json')
    if not cache.is_file():
        raise ValueError('endpoint_parent_conditioning_cache_missing')
    value = dict(version=VERSION, conditioning_key=key, prompt_sha256=prompt_sha,
        conditioning_path=str(cache), conditioning_sha256=g.digest(cache))
    if create:
        g.immutable_json(path, value)
    elif not path.is_file() or _json(path) != value:
        raise ValueError('immutable_endpoint_conditioning_receipt_missing_or_changed')
    return cache, dict(conditioning_receipt_path=str(path), conditioning_receipt_sha256=g.digest(path),
        conditioning_sha256=value['conditioning_sha256'])


def _completed_job(root, name, graph):
    path = root/'manifests/jobs'/(name+'.json')
    if not path.is_file():
        raise ValueError('completed_endpoint_durable_job_missing_or_changed')
    job = _json(path)
    if (job.get('name') != name or not job.get('prompt_id') or job.get('workflow') != graph
            or job.get('workflow_sha256') != g.canonical(graph) or job.get('status') != 'success'
            or job.get('history',{}).get('status',{}).get('status_str') != 'success'):
        raise ValueError('completed_endpoint_durable_job_missing_or_changed')
    return job


def generate(lab, root, base, endpoint_receipt, *, pose_control):
    """Run one distinct-photo D experiment with durable existing job semantics.

    All inputs are verified before any HTTP request and rehashed after sampling.
    The same parent seed/text/control is kept; the new name and graph are unique
    to the endpoint PNG. A failed or ambiguous job is never resubmitted.
    """
    lab, root = Path(lab).resolve(), Path(root).resolve()
    with g.generation_lock(root):
        checked = validate_endpoint(root, endpoint_receipt, pose_control=pose_control)
        parent, endpoint, reference = checked['parent'], checked['receipt'], checked['reference']
        provenance = parent['generation']
        text, key = provenance['prompt'], provenance['conditioning_key']
        if (hashlib.sha256(text.encode()).hexdigest() != provenance['prompt_sha256']
                or key != 'rehab_'+hashlib.sha256((provenance['prompt_version']+text).encode()).hexdigest()[:24]):
            raise ValueError('endpoint_parent_text_or_conditioning_cache_identity_changed')
        control_record, control_file, control_metadata = g.prepare_pose_control(lab, root, pose_control,
            parent['source_group_id'], 'D', reference)
        if control_record != checked['control']:
            raise ValueError('endpoint_verified_controller_changed_before_submission')
        image = endpoint['image']
        name = parent['sample_id']+'_endphoto'+image['sha256'][:12]
        if re.fullmatch(r'[A-Za-z0-9_.-]{1,190}', name) is None:
            raise ValueError('bounded_endpoint_job_name_required')
        input_dir = lab/'ComfyUI/input'
        first = _input_copy(_within(root, reference['image_path']), input_dir,
            'rehab_ref_'+reference['image_sha256'][:20]+'.png', reference['image_sha256'])
        last = _input_copy(_within(root, image['path']), input_dir,
            'rehab_endpoint_'+image['sha256'][:20]+'.png', image['sha256'])
        graph = with_distinct_endpoint(g.workflow(key, name, provenance['seed'], 241, first.name,
            pose_file=control_file, pose_endpoint=True), last.name)
        guidance = endpoint_contract(checked)
        guidance['control_file'] = control_file
        binding = dict(version=VERSION, receipt_path=checked['receipt_path'], receipt_sha256=checked['receipt_sha256'],
            parent_sample_id=parent['sample_id'], parent_video_sha256=parent['video']['sha256'],
            png_sha256=image['sha256'], source_frame=copy.deepcopy(endpoint['frame']), **FLAGS)
        assets = [Path(path) for path in checked['verified_asset_sha256']]
        assets += _model_assets(root, parent)
        model_receipt = Path(control_metadata['model_receipt_path'])
        additive = _json(model_receipt)
        assets += [model_receipt, Path(additive['model']['path']), Path(additive['lock_path']),
            first, last, input_dir/control_file]
        before = _snapshot(assets)
        intent = dict(version=VERSION, name=name, endpoint=binding, control=control_metadata,
            workflow_sha256=g.canonical(graph), immutable_asset_sha256=before,
            seed=provenance['seed'], conditioning_key=key, prompt_sha256=provenance['prompt_sha256'])
        intent_path = root/'manifests/endpoint-inputs'/(name+'.json')
        g.immutable_json(intent_path, intent)
        result_path = root/'manifests'/(name+'.json')
        if result_path.exists():
            _completed_job(root, name, graph)
            _, cache_binding = _conditioning(root, lab, name, key, provenance['prompt_sha256'])
            record = _json(result_path)
            if (record.get('sample_id') != name or record.get('stage') != 'pilot' or record.get('split') != 'train'
                    or record.get('status') != 'pending' or record['generation'].get('distinct_endpoint') != binding
                    or record['generation'].get('pose_control') != control_metadata
                    or record['generation'].get('guidance') != guidance
                    or record['generation']['workflow_sha256'] != g.canonical(graph)
                    or record['generation']['seed'] != provenance['seed']
                    or record['generation']['prompt_sha256'] != provenance['prompt_sha256']
                    or any(record['generation'].get(key) != value for key,value in cache_binding.items())):
                raise ValueError('completed_distinct_endpoint_candidate_changed')
            c.load_manifest(root/'manifests/dataset.json', verify_files=True)
            timeline = _within(root, record['video']['timeline_path'])
            if (g.digest(timeline) != record['video']['timeline_sha256']
                    or not g.same_media_timeline(_json(timeline), probe_video(_within(root, record['video']['path'])))
                    or [row for row in _json(root/'manifests/dataset.json')['samples'] if row['sample_id'] == name] != [record]):
                raise ValueError('completed_distinct_endpoint_source_or_timeline_changed')
            _unchanged(before)
            return record
        # Queue observation/reconnection is deferred until every local preflight
        # passes. execute() owns submission receipts and prohibits blind retries.
        g.reconnect_queue(base, root)
        conditioning = lab/'ComfyUI/output/conditioning'/(key+'.pt')
        if not conditioning.exists():
            g.api(base, '/free', dict(unload_models=True, free_memory=True))
            text_graph = {'101':dict(class_type='DualCLIPLoaderGGUF', inputs=dict(
                clip_name1='gemma-3-12b-it-Q4_K_M.gguf',
                clip_name2='ltx-2-19b-embeddings_connector_distill_bf16.safetensors', type='ltxv')),
                '102':dict(class_type='CLIPTextEncode', inputs=dict(clip=['101',0], text=text)),
                '103':dict(class_type='LabSaveConditioning', inputs=dict(conditioning=['102',0], name=key))}
            g.execute(base, root, key, text_graph)
            if not conditioning.exists():
                raise ValueError('durable_parent_text_cache_job_did_not_publish_conditioning')
            g.api(base, '/free', dict(unload_models=True, free_memory=True))
        conditioning, cache_binding = _conditioning(root, lab, name, key, provenance['prompt_sha256'], create=True)
        conditioning_sha = cache_binding['conditioning_sha256']
        job = g.execute(base, root, name, graph)
        _unchanged(before)
        if g.digest(conditioning) != conditioning_sha:
            raise ValueError('endpoint_conditioning_cache_changed_during_generation')
        after = validate_endpoint(root, endpoint_receipt, pose_control=pose_control)
        _, _, after_control = g.prepare_pose_control(lab, root, pose_control, parent['source_group_id'], 'D', reference)
        if after != checked or after_control != control_metadata:
            raise ValueError('endpoint_or_controller_provenance_changed_during_generation')
        source = lab/'ComfyUI/output/sports'/(name+'.mp4')
        destination = root/'raw'/(name+'.mp4')
        _input_copy(source, destination.parent, destination.name, g.digest(source))
        timeline = root/'manifests/timelines'/(name+'.json')
        actual = probe_video(destination, timeline_path=None if timeline.exists() else timeline)
        validate_decoded_result(actual, frames=241)
        if not g.same_media_timeline(_json(timeline), actual):
            raise ValueError('endpoint_output_actual_native_timeline_changed')
        record = dict(schema_version=c.SCHEMA_VERSION, sample_id=name,
            source_group_id=parent['source_group_id'], reference_group_id=parent['reference_group_id'],
            stage='pilot', split='train', scenario='D', status='pending', exercise_id='shoulder_abduction',
            side='unknown', view='front', anatomical_side='unknown', requested_side='left',
            camera='front', support_condition='unknown',
            lineage_ids=list(dict.fromkeys([*endpoint['lineage_ids'], *control_record['lineage_ids']])),
            video=dict(path=str(destination), sha256=g.digest(destination), width=640, height=384,
                frame_count=241, timeline_path=str(timeline), timeline_sha256=g.digest(timeline)),
            generation=dict(prompt_version=provenance['prompt_version'], prompt=text,
                prompt_sha256=provenance['prompt_sha256'], seed=provenance['seed'],
                conditioning_key=key, model_sha256=provenance['model_sha256'],
                model_verification_path=str(root/'manifests/model-verification.json'),
                workflow_sha256=g.canonical(graph), workflow_job_path=str(root/'manifests/jobs'/(name+'.json')),
                generation_wall_seconds=job['finished_unix']-job['created_unix'],
                distinct_endpoint=binding, pose_control=control_metadata, guidance=guidance, **cache_binding),
            requested_scenario_is_not_a_label=True)
        manifest_path = root/'manifests/dataset.json'
        manifest = _json(manifest_path)
        existing = [row for row in manifest['samples'] if row['sample_id'] == name]
        if existing and existing != [record]:
            raise ValueError('immutable_endpoint_candidate_manifest_entry_changed')
        if not existing:
            manifest['samples'].append(record)
            c.validate_manifest(manifest)
            g.replace_json(manifest_path, manifest)
        g.write_new(result_path, record)
        g.api(base, '/free', dict(unload_models=True, free_memory=True))
        return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('extract','validate','generate'))
    parser.add_argument('--root', type=Path, default=g.DEFAULT_ROOT)
    parser.add_argument('--lab', type=Path, default=Path('E:/ai-video-lab'))
    parser.add_argument('--base', default='http://127.0.0.1:8188')
    parser.add_argument('--pose-control', type=Path, required=True)
    parser.add_argument('--endpoint-receipt', type=Path)
    parser.add_argument('--parent-sample-id')
    parser.add_argument('--frame-index', type=int)
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    if args.command == 'extract':
        if args.parent_sample_id is None or args.frame_index is None or args.output_dir is None:
            parser.error('extract requires --parent-sample-id, --frame-index and new --output-dir')
        value = create_endpoint(args.root,args.parent_sample_id,args.frame_index,args.output_dir,pose_control=args.pose_control)
        print(json.dumps(dict(receipt_path=value['receipt_path'],receipt_sha256=value['receipt_sha256'],human_reference_created=False)))
    else:
        if args.endpoint_receipt is None:
            parser.error('validate/generate requires --endpoint-receipt')
        if args.command == 'validate':
            value = validate_endpoint(args.root,args.endpoint_receipt,pose_control=args.pose_control)
            print(json.dumps(dict(receipt_sha256=value['receipt_sha256'],source_group_id=value['receipt']['source_group_id'],
                original_pixels_and_PTS_verified=True,human_reference_created=False)))
        else:
            value = generate(args.lab,args.root,args.base,args.endpoint_receipt,pose_control=args.pose_control)
            print(json.dumps(dict(sample_id=value['sample_id'],video=value['video']['path'],human_review='pending')))


if __name__ == '__main__':
    main()
