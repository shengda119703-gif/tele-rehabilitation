"""Frozen formal candidates; serial source preflight before every Comfy job.

No command runs on import. A formal freeze and explicit group/control/reference
inputs are mandatory. Guidance is experimental, never proof of actual movement.
"""
from __future__ import annotations

import copy
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import math

from . import contracts as c,formal_plan as fp,generation as g,video
from .guidance import validate_decoded_result
from .pose_guidance import POSE_LORA_NAME,OFFICIAL_EVIDENCE,pose_guidance_contract

VERSION='rehab_synthetic_formal_generation/v1'
REFERENCE_VERSION='rehab_synthetic_formal_reference/v1'
REFERENCE_PREFIX=('A stationary camera far away, about five metres from one fictional adult in a large plain room. ')
REFERENCE_SUFFIX=(' Seen directly from the front, standing quietly with both arms relaxed down beside the thighs. '
    'The whole person occupies only the central sixty percent of image height, with generous clear floor around '
    'both feet and empty wall above the head and on both sides. Fixed distant camera, realistic anatomy, '
    'plain unmarked clothes and walls, no text or graphics. Remain quietly standing throughout.')


def _hash(value):return c.canonical_hash(value)


def _inside(root,path):
    root=Path(root).resolve()
    path=Path(path);path=path.resolve() if path.is_absolute() else (root/path).resolve()
    if not path.is_relative_to(root):raise ValueError('formal_output_or_source_outside_dataset_root')
    return path


def _read_receipt(root,receipt):
    path=Path(receipt['path']);path=path.resolve() if path.is_absolute() else (root/path).resolve()
    if g.digest(path)!=receipt['sha256']:raise ValueError('frozen_recipe_file_bytes_changed')
    return c._read_json(path)


def _bindings(*,reference=False):
    result=[dict(node_id='3',input_name='name',binding='conditioning_key'),
        dict(node_id='19',input_name='name',binding='job_name'),dict(node_id='18',input_name='name',binding='job_name'),
        dict(node_id='11',input_name='noise_seed',binding='seed')]
    if not reference:
        result.extend([dict(node_id='21',input_name='image',binding='reference_file'),
                       dict(node_id='32',input_name='file',binding='control_file')])
    return result


def reference_recipe_spec():
    """Pure reference template; store this object in the hash-pinned config."""
    return dict(version=REFERENCE_VERSION,prompt_prefix=REFERENCE_PREFIX,prompt_suffix=REFERENCE_SUFFIX,
        frames=97,workflow_template=g.workflow('BIND_KEY','BIND_JOB',0,97),late_bindings=_bindings(reference=True))


def build_generation_recipe(*,model_receipt,config,seed,version=VERSION,prompt_version=VERSION,prompts=None):
    """Pure A-F templates. D is pose-only; others also request the first photo.

    model_receipt = {path,sha256,model_sha256}; config = {path,sha256}.
    Returned model_receipt excludes model_sha256 to match formal_plan's schema.
    """
    if not isinstance(model_receipt,dict) or set(model_receipt)!={'path','sha256','model_sha256'}:
        raise ValueError('model_receipt_path_sha_and_base_model_sha_required')
    fp._receipt({k:model_receipt[k] for k in ('path','sha256')});fp._sha(model_receipt['model_sha256']);fp._receipt(config)
    prompts={s:g.prompt('shoulder_abduction',s) for s in c.SCENARIOS} if prompts is None else prompts
    if not isinstance(prompts,dict) or set(prompts)!=set(c.SCENARIOS):raise ValueError('explicit_A_F_prompts_required')
    scenarios={}
    for scenario in c.SCENARIOS:
        endpoint=scenario!='D'
        template=g.workflow('BIND_KEY','BIND_JOB',0,241,'BIND_REFERENCE.png',pose_file='BIND_CONTROL.mp4',
                            **({'pose_endpoint':True} if endpoint else {}))
        scenarios[scenario]=dict(prompt=prompts[scenario],workflow_template=template,late_bindings=_bindings(),
            guide_mode='pose_video_endpoint_reference' if endpoint else 'pose_video',
            guide_version=pose_guidance_contract(endpoint_reference=endpoint)['version'])
    recipe=dict(version=version,prompt_version=prompt_version,seed=seed,model_sha256=model_receipt['model_sha256'],
        model_receipt={k:model_receipt[k] for k in ('path','sha256')},config=copy.deepcopy(config),scenarios=scenarios)
    fp._recipe(recipe)
    return recipe


def bind_workflow(spec,bindings):
    """Replace only declared input positions; there are no arbitrary graph edits."""
    if not isinstance(bindings,dict):raise ValueError('explicit_late_binding_values_required')
    required={row['binding'] for row in spec['late_bindings']}
    if set(bindings)!=required:raise ValueError('exact_declared_late_binding_values_required')
    for key,value in bindings.items():
        if key=='seed':
            if type(value) is not int or not 0<=value<2**32:raise ValueError('bounded_execution_seed_required')
        else:
            if not isinstance(value,str) or re.fullmatch(r'[A-Za-z0-9_.-]{1,180}',value) is None:
                raise ValueError('safe_Comfy_basename_or_job_name_required')
            if key=='reference_file' and not value.lower().endswith('.png'):raise ValueError('reference_PNG_basename_required')
            if key=='control_file' and not value.lower().endswith('.mp4'):raise ValueError('control_MP4_basename_required')
    graph=copy.deepcopy(spec['workflow_template']);positions=[]
    for row in spec['late_bindings']:
        node,name=row['node_id'],row['input_name'];position=(node,name)
        if position in positions or node not in graph or name not in graph[node].get('inputs',{}):
            raise ValueError('invalid_or_repeated_template_binding_position')
        positions.append(position);graph[node]['inputs'][name]=bindings[row['binding']]
    return graph


def validate_execution_graph(spec,graph,bindings):
    expected=bind_workflow(spec,bindings)
    if graph!=expected:raise ValueError('execution_graph_differs_outside_declared_late_bindings')
    return dict(workflow_template_sha256=_hash(spec['workflow_template']),workflow_sha256=_hash(graph),
                late_bindings=copy.deepcopy(bindings))


def _verify_models(root,lab,loaded,config):
    recipe=loaded['plan']['generation_recipe'];receipt=_read_receipt(root,recipe['model_receipt'])
    lock_path=lab/'models.lock.json';lock=c._read_json(lock_path)
    if not isinstance(lock,list) or receipt.get('lock_sha256')!=g.digest(lock_path):
        raise ValueError('actual_generator_lock_differs_from_verified_receipt')
    if not isinstance(receipt.get('models'),list) or not receipt['models']:
        raise ValueError('complete_frozen_generator_model_receipt_required')
    locked={(str(Path(row['target']).resolve()),row['sha256']) for row in lock}
    verified={(str(Path(row['path']).resolve()),row['sha256']) for row in receipt['models']}
    if locked!=verified or len(locked)!=len(lock) or len(verified)!=len(receipt['models']):
        raise ValueError('generator_model_receipt_must_match_actual_locked_paths_and_hashes')
    needed={'diffusion_models/ltx-2-19b-distilled_Q4_K_M.gguf',
        'text_encoders/gemma-3-12b-it-Q4_K_M.gguf',
        'text_encoders/ltx-2-19b-embeddings_connector_distill_bf16.safetensors',
        'vae/LTX2_video_vae_bf16.safetensors','vae/LTX2_audio_vae_bf16.safetensors'}
    expected_paths={str((lab/'ComfyUI/models'/name).resolve()) for name in needed}
    if not expected_paths<={path for path,sha in locked}:raise ValueError('actual_workflow_model_paths_missing_from_lock')
    base=str((lab/'ComfyUI/models/diffusion_models/ltx-2-19b-distilled_Q4_K_M.gguf').resolve())
    if (base,recipe['model_sha256']) not in locked:raise ValueError('frozen_base_model_must_match_actual_GGUF_loader_path')
    for row in receipt['models']:
        path=Path(row['path']).resolve()
        if not path.is_file() or g.digest(path)!=row['sha256']:
            raise ValueError('frozen_generator_model_weight_bytes_changed')
    if recipe['model_sha256'] not in {row['sha256'] for row in receipt['models']}:
        raise ValueError('frozen_base_model_missing_from_actual_verified_weights')
    control_receipt=config['control_model_receipt'];control=_read_receipt(root,control_receipt);model=control['model']
    path=Path(model['path']).resolve();expected=(lab/'ComfyUI/models/loras'/POSE_LORA_NAME).resolve()
    if (path!=expected or model['sha256']!=OFFICIAL_EVIDENCE['model_sha256']
            or path.stat().st_size!=OFFICIAL_EVIDENCE['model_bytes'] or g.digest(path)!=OFFICIAL_EVIDENCE['model_sha256']):
        raise ValueError('full_pinned_19B_pose_LoRA_bytes_required_before_Comfy_API')
    if control.get('lock_path') and g.digest(Path(control['lock_path']))!=control['lock_sha256']:
        raise ValueError('separate_pose_control_model_lock_changed')
    return dict(model_sha256=recipe['model_sha256'],model_receipt_sha256=recipe['model_receipt']['sha256'],
        pose_lora_sha256=model['sha256'],control_model_receipt_path=control_receipt['path'],
        control_model_receipt_sha256=control_receipt['sha256'])


def _preflight(root,lab):
    loaded=fp.load_frozen_plan(root)  # This must precede ANY network observation.
    plan=loaded['plan'];recipe=plan['generation_recipe'];config=_read_receipt(root,recipe['config'])
    if config.get('reference_spec')!=reference_recipe_spec():raise ValueError('frozen_reference_recipe_template_changed')
    implementations=config.get('implementations')
    if not isinstance(implementations,list):raise ValueError('frozen_implementation_receipts_required')
    required={Path(__file__).with_name(name).resolve() for name in ('generation.py','formal_generation.py','formal_plan.py',
        'formal_control.py','pose_guidance.py','control.py','motion.py','video.py','pose.py')}
    paths=set()
    for receipt in implementations:
        path=Path(receipt['path']).resolve();paths.add(path)
        if g.digest(path)!=receipt['sha256']:raise ValueError('frozen_generation_implementation_bytes_changed')
    if not required<=paths:raise ValueError('actual_generation_module_paths_and_hashes_required')
    expected=build_generation_recipe(model_receipt={**recipe['model_receipt'],'model_sha256':recipe['model_sha256']},
        config=recipe['config'],seed=recipe['seed'],version=recipe['version'],prompt_version=recipe['prompt_version'],
        prompts={s:recipe['scenarios'][s]['prompt'] for s in c.SCENARIOS})
    if recipe!=expected:raise ValueError('frozen_formal_workflow_templates_or_guide_modes_changed')
    models=_verify_models(root,lab,loaded,config)
    manifest=c._read_json(root/'manifests/dataset.json')
    if manifest.get('split_freeze') not in (None,loaded['split_freeze']):raise ValueError('dataset_split_freeze_differs_from_formal_plan')
    return loaded,config,models


def _register(root,loaded,additions=()):
    path=_inside(root,'manifests/formal-source-registry.json');entries=[]
    history_dir=_inside(root,'manifests/formal-registry-history');history=[]
    for candidate in sorted(history_dir.glob('*.json')):
        candidate=_inside(root,candidate);value=c._read_json(candidate)
        if (value.get('frozen_sha')!=loaded['frozen_sha'] or not isinstance(value.get('entries'),list)
                or value.get('entries_sha256')!=_hash(value['entries'])
                or candidate.name!=str(len(value['entries'])).zfill(6)+'_'+value['entries_sha256']+'.json'):
            raise ValueError('immutable_formal_registry_history_changed')
        history.append(value)
    if path.exists():
        saved=c._read_json(path)
        if (saved.get('frozen_sha')!=loaded['frozen_sha'] or saved.get('entries_sha256')!=_hash(saved.get('entries'))):
            raise ValueError('formal_source_registry_changed_or_wrong_freeze')
        entries=saved['entries']
        if saved not in history:raise ValueError('current_formal_registry_must_match_immutable_history')
    if history and max(len(row['entries']) for row in history)>len(entries):
        raise ValueError('formal_source_registry_rollback_or_missing_latest_version')
    original_entries=copy.deepcopy(entries)
    by_id={row['entry_id']:row for row in entries}
    if len(by_id)!=len(entries):raise ValueError('duplicate_persistent_registry_entry')
    for row in additions:
        if row['entry_id'] in by_id and by_id[row['entry_id']]!=row:raise ValueError('immutable_formal_source_entry_changed')
        if row['entry_id'] not in by_id:entries.append(copy.deepcopy(row));by_id[row['entry_id']]=row
    frozen_entries=[row for row in loaded['registry']['entries'] if row['stage']=='formal' and row['kind']!='profile']
    frozen_ids={row['entry_id']:row for row in frozen_entries}
    for row in entries:
        if row['entry_id'] in frozen_ids and row!=frozen_ids[row['entry_id']]:raise ValueError('registry_conflicts_with_frozen_source_entry')
        frozen_ids[row['entry_id']]=row
    audit=fp.validate_registry(loaded['plan'],list(frozen_ids.values()),debug_sources=loaded['debug_sources'])
    value=dict(schema_version=fp.REGISTRY_VERSION,frozen_sha=loaded['frozen_sha'],entries=entries,
               entries_sha256=_hash(entries),validated_registry_sha256=audit['registry_sha256'])
    # A fresh debug inventory is checked above. With no source additions its
    # changing audit SHA does not rewrite the immutable source registration.
    if not path.exists() or entries!=original_entries:
        history=_inside(root,'manifests/formal-registry-history/'+str(len(entries)).zfill(6)+'_'+_hash(entries)+'.json')
        g.immutable_json(history,value);g.replace_json(path,value)
    return audit


def _attempt(value):
    g.revision(value)
    return f'r{value:02d}'


def _group(loaded,group):
    if group not in loaded['plan']['profiles']:raise ValueError('explicit_frozen_formal_source_group_required')
    return loaded['plan']['profiles'][group]


def _conditioning(root,lab,base,text,version,key):
    cache=lab/'ComfyUI/output/conditioning'/(key+'.pt');receipt=root/'manifests/formal-conditioning'/(key+'.json')
    graph={'101':dict(class_type='DualCLIPLoaderGGUF',inputs=dict(clip_name1='gemma-3-12b-it-Q4_K_M.gguf',
        clip_name2='ltx-2-19b-embeddings_connector_distill_bf16.safetensors',type='ltxv')),
        '102':dict(class_type='CLIPTextEncode',inputs=dict(clip=['101',0],text=text)),
        '103':dict(class_type='LabSaveConditioning',inputs=dict(conditioning=['102',0],name=key))}
    if receipt.exists():
        saved=c._read_json(receipt)
        if saved!=dict(prompt_version=version,prompt_sha256=hashlib.sha256(text.encode()).hexdigest(),
                       workflow_sha256=_hash(graph),cache_sha256=g.digest(cache)):
            raise ValueError('formal_conditioning_cache_changed')
        return
    if cache.exists() and not (root/'manifests/jobs'/(key+'.json')).exists():
        raise ValueError('unrecorded_formal_conditioning_cache_cannot_be_trusted')
    g.api(base,'/free',{'unload_models':True,'free_memory':True})
    g.execute(base,root,key,graph)
    value=dict(prompt_version=version,prompt_sha256=hashlib.sha256(text.encode()).hexdigest(),
               workflow_sha256=_hash(graph),cache_sha256=g.digest(cache))
    g.immutable_json(receipt,value)
    g.api(base,'/free',{'unload_models':True,'free_memory':True})


def _conditioning_state(root,cache,key,text,version):
    cache=Path(cache).resolve();receipt=_inside(root,'manifests/formal-conditioning/'+key+'.json')
    saved=c._read_json(receipt)
    graph={'101':dict(class_type='DualCLIPLoaderGGUF',inputs=dict(clip_name1='gemma-3-12b-it-Q4_K_M.gguf',
        clip_name2='ltx-2-19b-embeddings_connector_distill_bf16.safetensors',type='ltxv')),
        '102':dict(class_type='CLIPTextEncode',inputs=dict(clip=['101',0],text=text)),
        '103':dict(class_type='LabSaveConditioning',inputs=dict(conditioning=['102',0],name=key))}
    sha=g.digest(cache)
    if saved!=dict(prompt_version=version,prompt_sha256=hashlib.sha256(text.encode()).hexdigest(),
                   workflow_sha256=_hash(graph),cache_sha256=sha):
        raise ValueError('formal_conditioning_cache_or_receipt_changed')
    _verify_job(root,key,graph)
    return dict(conditioning_key=key,cache_path=str(cache),cache_sha256=sha,receipt_path=str(receipt),receipt_sha256=g.digest(receipt))


def _pin_conditioning(root,name,state,*,create=False):
    path=_inside(root,'manifests/formal-jobs/'+name+'.conditioning.json')
    if create:g.immutable_json(path,state)
    elif c._read_json(path)!=state:raise ValueError('actual_job_conditioning_bytes_changed')
    return state


def _copy_input(lab,path,sha,suffix):
    if g.digest(path)!=sha:raise ValueError('formal_input_source_bytes_changed')
    target=lab/'ComfyUI/input'/('formal_'+sha[:24]+suffix)
    target.parent.mkdir(parents=True,exist_ok=True)
    if not target.exists():shutil.copy2(path,target)
    if g.digest(target)!=sha:raise ValueError('formal_Comfy_input_copy_changed')
    return target.name


def _copy_probe(root,lab,name,destination,frames):
    source=lab/'ComfyUI/output/sports'/(name+'.mp4');destination=_inside(root,destination)
    destination.parent.mkdir(parents=True,exist_ok=True)
    if not destination.exists():shutil.copy2(source,destination)
    if source.exists() and g.digest(source)!=g.digest(destination):raise ValueError('formal_immutable_video_copy_changed')
    timeline=_inside(root,'manifests/formal-timelines/'+name+'.json');probe=video.probe_video(destination)
    validate_decoded_result(probe,frames=frames)
    if timeline.exists():
        if not g.same_media_timeline(c._read_json(timeline),probe):raise ValueError('formal_actual_source_PTS_or_RGB_changed')
    else:g.write_new(timeline,probe)
    return dict(path=str(destination),sha256=g.digest(destination),width=probe['width'],height=probe['height'],
        frame_count=probe['frame_count'],timeline_path=str(timeline),timeline_sha256=g.digest(timeline)),probe


def _verify_job(root,name,graph):
    path=_inside(root,'manifests/jobs/'+name+'.json');job=c._read_json(path)
    start,end=job.get('created_unix'),job.get('finished_unix')
    if (job.get('name')!=name or job.get('workflow_sha256')!=_hash(graph) or job.get('workflow')!=graph
            or job.get('status')!='success' or job.get('history',{}).get('status',{}).get('status_str')!='success'
            or not isinstance(job.get('prompt_id'),str) or not job['prompt_id'].strip()
            or type(start) not in (int,float) or type(end) not in (int,float)
            or not math.isfinite(start) or not math.isfinite(end) or end<start):
        raise ValueError('durable_successful_formal_job_and_exact_workflow_required_no_resubmission')
    return dict(workflow_job_path=str(path),prompt_id=job['prompt_id'],generation_wall_seconds=end-start)


def _generation(loaded,recipe,text,seed,graph,spec,models,job,conditioning):
    return dict(prompt_version=recipe['prompt_version'],prompt=text,prompt_sha256=hashlib.sha256(text.encode()).hexdigest(),
        seed=seed,model_sha256=models['model_sha256'],workflow_sha256=_hash(graph),
        workflow_template_sha256=_hash(spec['workflow_template']),recipe_sha256=loaded['plan']['recipe_sha256'],
        freeze_sha256=loaded['frozen_sha'],model_receipts=copy.deepcopy(models),conditioning=copy.deepcopy(conditioning),**job,
        scenario_coverage_basis='requested_generation_targets_only',observed_scenario_coverage='not_established_by_this_command')


def generate_reference(lab,root,base,group,*,attempt=1):
    root=Path(root).resolve();lab=Path(lab).resolve();revision=_attempt(attempt)
    with g.generation_lock(root):
        loaded,config,models=_preflight(root,lab);profile=_group(loaded,group)
        spec=config['reference_spec'];recipe=loaded['plan']['generation_recipe']
        text=spec['prompt_prefix']+profile['prompt']+spec['prompt_suffix']
        seed=int(_hash(dict(version=REFERENCE_VERSION,plan_sha256=loaded['plan']['plan_sha256'],group=group,attempt=attempt))[:8],16)
        name='formal_ref_'+loaded['plan']['plan_sha256'][:10]+'_'+_hash(group)[:10]+'_'+revision
        key='formal_text_'+hashlib.sha256((spec['version']+text).encode()).hexdigest()[:24]
        graph=bind_workflow(spec,dict(job_name=name,conditioning_key=key,seed=seed));validate_execution_graph(spec,graph,
            dict(job_name=name,conditioning_key=key,seed=seed))
        entry_id=group+':reference:'+revision
        planned=fp.source_registry_entry(loaded['plan'],entry_id=entry_id,source_group_id=group,kind='reference',
            identity_ids=profile['identity_ids'],lineage_ids=profile['lineage_ids'])
        _register(root,loaded,[planned])
        descriptor=dict(frozen_sha=loaded['frozen_sha'],group=group,reference_attempt=attempt,prompt=text,
            seed=seed,workflow_sha256=_hash(graph),workflow_template_sha256=_hash(spec['workflow_template']),models=models)
        g.immutable_json(_inside(root,'manifests/formal-jobs/'+name+'.json'),descriptor)
        result_path=_inside(root,'references/formal/'+group+'/'+revision+'.json')
        if not result_path.exists():
            g.reconnect_queue(base,root)
            _conditioning(root,lab,base,text,spec['version'],key)
            _pin_conditioning(root,name,_conditioning_state(root,lab/'ComfyUI/output/conditioning'/(key+'.pt'),key,text,spec['version']),create=True)
            g.execute(base,root,name,graph)
        job=_verify_job(root,name,graph)
        conditioning=_pin_conditioning(root,name,_conditioning_state(root,lab/'ComfyUI/output/conditioning'/(key+'.pt'),key,text,spec['version']))
        media,probe=_copy_probe(root,lab,name,'references/formal/'+group+'/'+revision+'.mp4',97)
        image_path=result_path.with_suffix('.png')
        import av
        from PIL import Image
        with av.open(media['path']) as container:
            first=next(container.decode(video=0));rgb=first.to_ndarray(format='rgb24')
            if image_path.exists():
                with Image.open(image_path) as existing:
                    if existing.convert('RGB').tobytes()!=rgb.tobytes():raise ValueError('immutable_formal_reference_pixels_changed')
            else:first.to_image().save(image_path)
        if _preflight(root,lab)[0]['frozen_sha']!=loaded['frozen_sha']:raise ValueError('formal_freeze_changed_during_reference_generation')
        actual=fp.source_registry_entry(loaded['plan'],entry_id=entry_id+':media',source_group_id=group,kind='reference',
            assets=dict(reference_png=g.digest(image_path),reference_video=media['sha256']),parents=[entry_id])
        _register(root,loaded,[actual])
        record=dict(schema_version=REFERENCE_VERSION,stage='formal',split=loaded['split_freeze']['formal_group_splits'][group],
            sample_id=name,source_group_id=group,reference_group_id=group,reference_attempt=attempt,registry_entry_id=entry_id,
            lineage_ids=list(dict.fromkeys([*profile['identity_ids'],*profile['lineage_ids'],entry_id])),
            image_path=str(image_path),image_sha256=g.digest(image_path),video=media,freeze_sha256=loaded['frozen_sha'],
            source_frame_index=0,source_frame_pts=probe['frames'][0]['pts'],source_decoded_rgb_sha256=probe['frames'][0]['decoded_rgb_sha256'],
            structural_review=dict(status='pending'),generation=_generation(loaded,dict(prompt_version=spec['version']),text,seed,graph,spec,models,job,conditioning),
            creates_labels=False,training_reference_eligible=False)
        g.immutable_json(result_path,record)
        return record


def record_reference_screen(root,reference_record_path,*,status,reviewer_role,reviewer_id,notes='',revision=1):
    root=Path(root).resolve();loaded=fp.load_frozen_plan(root);path=_inside(root,reference_record_path);record=c._read_json(path)
    _verify_reference(root,loaded,record)
    if status not in ('usable_as_initial_condition','rejected') or reviewer_role not in ('ai_structural_screen','human_operator'):
        raise ValueError('explicit_structural_screen_status_and_role_required')
    fp._text(reviewer_id)
    value=dict(schema_version='rehab_synthetic_reference_screen/v1',reference_record_sha256=g.digest(path),
        image_sha256=record['image_sha256'],video_sha256=record['video']['sha256'],freeze_sha256=loaded['frozen_sha'],
        status=status,reviewer_role=reviewer_role,reviewer_id=reviewer_id,notes=notes,creates_labels=False)
    output=path.with_name(path.stem+'.screen.'+_attempt(revision)+'.json');g.immutable_json(output,value)
    return dict(value,receipt_path=str(output))


def _verify_reference(root,loaded,record):
    group=record['source_group_id'];_group(loaded,group)
    if (record.get('schema_version')!=REFERENCE_VERSION or record.get('stage')!='formal'
            or record.get('split')!=loaded['split_freeze']['formal_group_splits'][group]
            or record.get('reference_group_id')!=group or record.get('freeze_sha256')!=loaded['frozen_sha']
            or record.get('registry_entry_id')!=group+':reference:'+_attempt(record.get('reference_attempt'))):
        raise ValueError('formal_reference_origin_or_freeze_changed')
    for ref,sha in ((record['image_path'],record['image_sha256']),(record['video']['path'],record['video']['sha256'])):
        if g.digest(_inside(root,ref))!=sha:raise ValueError('formal_reference_source_bytes_changed')
    profile=loaded['plan']['profiles'][group]
    if not set(profile['identity_ids']+profile['lineage_ids']).issubset(record['lineage_ids']):
        raise ValueError('formal_reference_lost_frozen_profile_origin')
    config=_read_receipt(root,loaded['plan']['generation_recipe']['config']);spec=config['reference_spec']
    text=spec['prompt_prefix']+profile['prompt']+spec['prompt_suffix'];attempt=record['reference_attempt']
    seed=int(_hash(dict(version=REFERENCE_VERSION,plan_sha256=loaded['plan']['plan_sha256'],group=group,attempt=attempt))[:8],16)
    name='formal_ref_'+loaded['plan']['plan_sha256'][:10]+'_'+_hash(group)[:10]+'_'+_attempt(attempt)
    if record.get('sample_id')!=name:raise ValueError('formal_reference_job_identity_changed')
    key='formal_text_'+hashlib.sha256((spec['version']+text).encode()).hexdigest()[:24]
    graph=bind_workflow(spec,dict(job_name=name,conditioning_key=key,seed=seed));job=_verify_job(root,name,graph)
    generation=record['generation']
    expected_descriptor=dict(frozen_sha=loaded['frozen_sha'],group=group,reference_attempt=attempt,prompt=text,
        seed=seed,workflow_sha256=_hash(graph),workflow_template_sha256=_hash(spec['workflow_template']),models=generation['model_receipts'])
    if c._read_json(_inside(root,'manifests/formal-jobs/'+name+'.json'))!=expected_descriptor:
        raise ValueError('formal_reference_generation_descriptor_changed')
    conditioning=_pin_conditioning(root,name,_conditioning_state(root,generation['conditioning']['cache_path'],key,text,spec['version']))
    if generation!=_generation(loaded,dict(prompt_version=spec['version']),text,seed,graph,spec,generation['model_receipts'],job,conditioning):
        raise ValueError('formal_reference_execution_provenance_changed')
    registry=c._read_json(_inside(root,'manifests/formal-source-registry.json'))
    if registry.get('frozen_sha')!=loaded['frozen_sha'] or registry.get('entries_sha256')!=_hash(registry.get('entries')):
        raise ValueError('formal_reference_registry_changed')
    asset=fp.source_registry_entry(loaded['plan'],entry_id=record['registry_entry_id']+':media',source_group_id=group,
        kind='reference',assets=dict(reference_png=record['image_sha256'],reference_video=record['video']['sha256']),
        parents=[record['registry_entry_id']])
    if [row for row in registry['entries'] if row['entry_id']==asset['entry_id']]!=[asset]:
        raise ValueError('formal_reference_must_match_registered_generated_media_assets')
    probe=video.probe_video(_inside(root,record['video']['path']));validate_decoded_result(probe,frames=97)
    from PIL import Image
    with Image.open(_inside(root,record['image_path'])) as image:
        pixel_sha=hashlib.sha256(image.convert('RGB').tobytes()).hexdigest()
    if (record.get('source_frame_index')!=0 or pixel_sha!=probe['frames'][0]['decoded_rgb_sha256']
            or record.get('source_decoded_rgb_sha256')!=pixel_sha or record.get('source_frame_pts')!=probe['frames'][0]['pts']):
        raise ValueError('formal_reference_PNG_must_equal_original_decoded_frame_zero')


def generate_motion(lab,root,base,group,scenario,*,reference_record_path,reference_screen_path,control_path,attempt=1):
    root=Path(root).resolve();lab=Path(lab).resolve();revision=_attempt(attempt)
    with g.generation_lock(root):
        loaded,config,models=_preflight(root,lab);profile=_group(loaded,group)
        slots=[row for row in loaded['plan']['slots'] if row['source_group_id']==group and row['scenario']==scenario]
        if len(slots)!=1:raise ValueError('explicit_frozen_formal_slot_required')
        slot=slots[0];reference_path=_inside(root,reference_record_path);reference=c._read_json(reference_path)
        _verify_reference(root,loaded,reference)
        if reference['source_group_id']!=group:raise ValueError('formal_reference_group_mismatch')
        screen=c._read_json(_inside(root,reference_screen_path))
        if (screen.get('schema_version')!='rehab_synthetic_reference_screen/v1'
                or screen.get('reviewer_role') not in ('ai_structural_screen','human_operator')
                or not isinstance(screen.get('reviewer_id'),str) or not screen['reviewer_id'].strip()
                or screen.get('creates_labels') is not False or screen.get('status')!='usable_as_initial_condition'
                or screen.get('reference_record_sha256')!=g.digest(reference_path)
                or screen.get('image_sha256')!=reference['image_sha256'] or screen.get('video_sha256')!=reference['video']['sha256']
                or screen.get('freeze_sha256')!=loaded['frozen_sha']):raise ValueError('formal_reference_requires_bound_structural_screen')
        from . import formal_control
        control,control_file,metadata,entries=formal_control.prepare_control(root,loaded,group,scenario,reference,
            control_path=control_path,lab=lab,attempt=attempt)
        metadata={**metadata,'model_sha256':models['pose_lora_sha256'],
            'model_receipt_path':models['control_model_receipt_path'],'model_receipt_sha256':models['control_model_receipt_sha256']}
        seed=formal_control.attempt_seed(slot['seed'],attempt)
        stamp=_hash(dict(freeze=loaded['frozen_sha'],reference=reference['image_sha256'],control=control['video_sha256']))[:10]
        name='formal_'+loaded['plan']['plan_sha256'][:10]+'_'+_hash(group)[:10]+'_'+scenario+'_'+revision+'_'+stamp
        spec=loaded['plan']['generation_recipe']['scenarios'][scenario];text=slot['prompt']
        key='formal_text_'+hashlib.sha256((slot['prompt_version']+text).encode()).hexdigest()[:24]
        reference_file=_copy_input(lab,_inside(root,reference['image_path']),reference['image_sha256'],'.png')
        bindings=dict(job_name=name,conditioning_key=key,seed=seed,reference_file=reference_file,control_file=control_file)
        graph=bind_workflow(spec,bindings);validate_execution_graph(spec,graph,bindings)
        if _hash(spec['workflow_template'])!=slot['workflow_template_sha256']:raise ValueError('frozen_slot_template_sha_changed')
        pending=fp.source_registry_entry(loaded['plan'],entry_id=group+':pending:'+scenario+':'+revision,source_group_id=group,
            kind='pending',lineage_ids=control['lineage_ids'],parents=[reference['registry_entry_id'],metadata['registry_entry_id']])
        _register(root,loaded,[*entries,pending])
        descriptor=dict(frozen_sha=loaded['frozen_sha'],slot_id=slot['slot_id'],attempt=attempt,seed=seed,
            reference_record_path=str(reference_path),reference_record_sha256=g.digest(reference_path),
            screen_sha256=g.digest(_inside(root,reference_screen_path)),control=metadata,models=models,
            workflow_sha256=_hash(graph),workflow_template_sha256=slot['workflow_template_sha256'])
        g.immutable_json(_inside(root,'manifests/formal-jobs/'+name+'.json'),descriptor)
        result_path=_inside(root,'manifests/formal-candidates/'+name+'.json')
        if not result_path.exists():
            g.reconnect_queue(base,root);_conditioning(root,lab,base,text,slot['prompt_version'],key)
            _pin_conditioning(root,name,_conditioning_state(root,lab/'ComfyUI/output/conditioning'/(key+'.pt'),key,text,slot['prompt_version']),create=True)
            g.execute(base,root,name,graph)
        job=_verify_job(root,name,graph)
        conditioning=_pin_conditioning(root,name,_conditioning_state(root,lab/'ComfyUI/output/conditioning'/(key+'.pt'),key,text,slot['prompt_version']))
        if g.digest(lab/'ComfyUI/input'/reference_file)!=reference['image_sha256']:
            raise ValueError('actual_Comfy_reference_copy_changed_during_sampling')
        media,probe=_copy_probe(root,lab,name,'raw/'+name+'.mp4',241)
        fresh,_,_=_preflight(root,lab)
        checked=formal_control.prepare_control(root,fresh,group,scenario,reference,control_path=control_path,lab=lab,attempt=attempt)
        if checked[0]!=control or checked[1]!=control_file or checked[2]!={k:v for k,v in metadata.items()
                if k not in ('model_sha256','model_receipt_path','model_receipt_sha256')}:
            raise ValueError('formal_control_changed_during_generation')
        actual=fp.source_registry_entry(loaded['plan'],entry_id=group+':raw:'+scenario+':'+revision,source_group_id=group,
            kind='raw',assets={'raw_video':media['sha256']},parents=[pending['entry_id']])
        _register(root,fresh,[actual])
        generation=_generation(loaded,dict(prompt_version=slot['prompt_version']),text,seed,graph,spec,models,job,conditioning)
        generation.update(pose_control=metadata,guidance=pose_guidance_contract(control_file=control_file,
            control_sha256=control['video_sha256'],endpoint_reference=scenario!='D'))
        record=dict(schema_version=c.SCHEMA_VERSION,sample_id=name,source_group_id=group,reference_group_id=group,
            lineage_ids=list(dict.fromkeys([*profile['identity_ids'],*profile['lineage_ids'],*reference['lineage_ids'],
                *control['lineage_ids'],'reference:'+reference['image_sha256'],'reference_video:'+reference['video']['sha256']])),
            split=slot['split'],stage='formal',scenario=scenario,status='pending',exercise_id='shoulder_abduction',
            side='unknown',view='front',requested_side='left',video=media,generation=generation,
            attempt=attempt,registry_entry_id=actual['entry_id'],requested_scenario_is_not_a_label=True,creates_labels=False)
        manifest_path=_inside(root,'manifests/dataset.json');manifest=c._read_json(manifest_path)
        manifest['split_freeze']=copy.deepcopy(loaded['split_freeze'])
        old=[row for row in manifest['samples'] if row['sample_id']==name]
        if old and old!=[record]:raise ValueError('immutable_formal_candidate_manifest_changed')
        if result_path.exists() and old!=[record]:raise ValueError('completed_formal_candidate_manifest_missing')
        if not old:manifest['samples'].append(record)
        c.validate_manifest(manifest)
        if not old:g.replace_json(manifest_path,manifest)
        g.immutable_json(result_path,record)
        return record


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    for name in ('draft','freeze','reference','motion','record-reference-screen'):
        item=sub.add_parser(name);item.add_argument('--root',type=Path,required=True)
        if name=='draft':
            item.add_argument('--request',type=Path,required=True);item.add_argument('--output',default='manifests/formal-plan-draft.json')
        elif name=='freeze':item.add_argument('--plan',type=Path,required=True)
        elif name=='record-reference-screen':
            item.add_argument('--reference-record',type=Path,required=True)
            item.add_argument('--status',choices=('usable_as_initial_condition','rejected'),required=True)
            item.add_argument('--reviewer-role',choices=('ai_structural_screen','human_operator'),required=True)
            item.add_argument('--reviewer-id',required=True);item.add_argument('--notes',default='');item.add_argument('--revision',type=int,default=1)
        else:
            item.add_argument('--lab',type=Path,default=Path('E:/ai-video-lab'));item.add_argument('--base',default='http://127.0.0.1:8188')
            item.add_argument('--group',required=True);item.add_argument('--attempt',type=int,default=1)
            if name=='motion':
                item.add_argument('--scenario',choices=tuple('ABCDEF'),required=True)
                for field in ('reference-record','reference-screen','control-path'):item.add_argument('--'+field,type=Path,required=True)
    args=parser.parse_args(argv);root=args.root.resolve()
    try:
        if args.command=='draft':
            plan=fp.draft_formal_plan(**c._read_json(args.request));target=_inside(root,args.output)
            g.immutable_json(target,plan);result=dict(command='draft',plan_path=str(target),**fp.validate_plan(plan),generation_submitted=False)
        elif args.command=='freeze':
            result=fp.freeze_formal_plan(root,c._read_json(_inside(root,args.plan)))
        elif args.command=='reference':result=generate_reference(args.lab,root,args.base,args.group,attempt=args.attempt)
        elif args.command=='motion':
            result=generate_motion(args.lab,root,args.base,args.group,args.scenario,reference_record_path=args.reference_record,
                reference_screen_path=args.reference_screen,control_path=args.control_path,attempt=args.attempt)
        else:result=record_reference_screen(root,args.reference_record,status=args.status,reviewer_role=args.reviewer_role,
            reviewer_id=args.reviewer_id,notes=args.notes,revision=args.revision)
        print(json.dumps(result,ensure_ascii=False,allow_nan=False));return 0
    except (ValueError,RuntimeError,OSError) as error:
        print(json.dumps(dict(status='rejected',command=args.command,error=str(error),generation_success_claimed=False),ensure_ascii=False));return 2


if __name__=='__main__':raise SystemExit(main())
