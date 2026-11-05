"""Immutable formal-generation plans and source preflight; no generation or GT.

Drafts describe requested targets. Freezing verifies saved human pilot reviews,
not generation quality, actual scenario coverage, or readiness to train. Pending
and reference-only provenance has its own origin graph, without fake video SHA.
"""
from __future__ import annotations

from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import re

from . import contracts as c
from . import review

VERSION='rehab_synthetic_formal_plan/v1'
FREEZE_VERSION='rehab_synthetic_formal_freeze/v1'
REGISTRY_VERSION='rehab_synthetic_source_registry/v1'
ASSETS=('reference_png','reference_video','pose_prediction','control_trajectory','control_video','raw_video')
KINDS=('reference','pending','pose','control','raw')
BINDINGS=('job_name','reference_file','control_file','conditioning_key','seed')
GUIDE_MODES=('none','endpoint_reference','pose_video','pose_video_endpoint_reference')
_GLOBAL=re.compile(r'^(algorithm|model|model_sha256|prompt|workflow|version|controller_version|style)(:|/|=)',re.I)


def _id(value):
    if not isinstance(value,str) or re.fullmatch(r'[A-Za-z0-9_.:-]{1,192}',value) is None:
        raise ValueError('bounded_source_identifier_required')
    return value


def _text(value):
    if not isinstance(value,str) or not value.strip() or len(value)>100000:
        raise ValueError('nonempty_bounded_text_required')
    return value


def _sha(value):
    if not isinstance(value,str) or re.fullmatch(r'[0-9a-f]{64}',value) is None:
        raise ValueError('explicit_sha256_required')
    return value


def _ids(values,*,nonempty=False):
    if not isinstance(values,(list,tuple)) or (nonempty and not values):
        raise ValueError('explicit_source_identifier_list_required')
    result=[_id(value) for value in values]
    if len(set(result))!=len(result):raise ValueError('unique_source_identifiers_required')
    if any(_GLOBAL.match(value) for value in result):
        raise ValueError('global_algorithm_model_prompt_versions_are_not_source_lineage')
    return result


def _receipt(value):
    if not isinstance(value,dict) or set(value)!={'path','sha256'}:
        raise ValueError('explicit_file_receipt_path_and_sha_required')
    _text(value['path']);_sha(value['sha256'])


def _recipe(recipe):
    required={'version','prompt_version','seed','model_sha256','model_receipt','config','scenarios'}
    if not isinstance(recipe,dict) or set(recipe)!=required:
        raise ValueError('explicit_generation_recipe_fields_required')
    _text(recipe['version']);_text(recipe['prompt_version']);_sha(recipe['model_sha256'])
    if type(recipe['seed']) is not int or not 0<=recipe['seed']<2**32:
        raise ValueError('bounded_recipe_seed_required')
    _receipt(recipe['model_receipt']);_receipt(recipe['config'])
    if not isinstance(recipe['scenarios'],dict) or set(recipe['scenarios'])!=set(c.SCENARIOS):
        raise ValueError('generation_recipe_A_through_F_required')
    for spec in recipe['scenarios'].values():
        if not isinstance(spec,dict) or set(spec)!={'prompt','workflow_template','late_bindings','guide_mode','guide_version'}:
            raise ValueError('explicit_scenario_template_and_declared_bindings_required')
        _text(spec['prompt']);_text(spec['guide_version'])
        if spec['guide_mode'] not in GUIDE_MODES or not isinstance(spec['workflow_template'],dict) or not spec['workflow_template']:
            raise ValueError('explicit_guidance_mode_and_nonempty_workflow_template_required')
        if not isinstance(spec['late_bindings'],list):raise ValueError('declared_late_bindings_list_required')
        positions=[]
        for binding in spec['late_bindings']:
            if not isinstance(binding,dict) or set(binding)!={'node_id','input_name','binding'}:
                raise ValueError('declared_late_binding_fields_required')
            node=binding['node_id'];name=binding['input_name'];_text(node);_text(name)
            if (binding['binding'] not in BINDINGS or node not in spec['workflow_template']
                    or name not in spec['workflow_template'][node].get('inputs',{})):
                raise ValueError('late_binding_must_name_an_existing_template_input')
            positions.append((node,name))
        if len(set(positions))!=len(positions):raise ValueError('unique_late_binding_positions_required')
    c.canonical_hash(recipe)  # Reject non-JSON or nonfinite configuration values.


def draft_formal_plan(*,cohort12,profiles,group_splits,generation_recipe):
    """Pure draft: caller supplies twelve sample IDs, ten profiles and a recipe.

    profiles[group] = {prompt, identity_ids, lineage_ids}; source stage/split
    cannot be overridden here or in slots. Recipe scenarios carry templates,
    never a claim that an as-yet unbound execution graph has been generated.
    """
    cohort=_ids(cohort12,nonempty=True)
    if len(cohort)!=12:raise ValueError('twelve_explicit_unique_pilot_sample_ids_required')
    frozen=c.freeze_splits(group_splits)
    if not isinstance(profiles,dict) or set(profiles)!=set(group_splits):
        raise ValueError('ten_profiles_must_match_frozen_source_groups')
    for group,profile in profiles.items():
        if not isinstance(group,str) or re.fullmatch(r'[A-Za-z0-9_-]{1,96}',group) is None:
            raise ValueError('safe_formal_group_filename_required')
        if not isinstance(profile,dict) or set(profile)!={'prompt','identity_ids','lineage_ids'}:
            raise ValueError('profile_prompt_identity_and_lineage_only_no_split_override')
        _text(profile['prompt']);_ids(profile['identity_ids'],nonempty=True);_ids(profile['lineage_ids'])
    _recipe(generation_recipe)
    recipe_sha=c.canonical_hash(generation_recipe)
    slots=[]
    for group in sorted(profiles):
        for scenario in c.SCENARIOS:
            spec=generation_recipe['scenarios'][scenario]
            seed=int(c.canonical_hash(dict(seed=generation_recipe['seed'],group=group,scenario=scenario))[:8],16)
            slots.append(dict(slot_id=group+':'+scenario,source_group_id=group,reference_group_id=group,
                stage='formal',split=frozen['formal_group_splits'][group],scenario=scenario,
                exercise_id='shoulder_abduction',view='front',seed=seed,prompt=spec['prompt'],
                prompt_version=generation_recipe['prompt_version'],prompt_sha256=hashlib.sha256(spec['prompt'].encode()).hexdigest(),
                frames=241,fps=30,width=640,height=384,guide_mode=spec['guide_mode'],guide_version=spec['guide_version'],
                workflow_template_sha256=c.canonical_hash(spec['workflow_template']),
                late_bindings=copy.deepcopy(spec['late_bindings']),recipe_sha256=recipe_sha,
                model_sha256=generation_recipe['model_sha256'],model_receipt=copy.deepcopy(generation_recipe['model_receipt']),
                config_sha256=generation_recipe['config']['sha256']))
    plan=dict(schema_version=VERSION,status='draft',cohort12=cohort,profiles=copy.deepcopy(profiles),
        split_freeze=frozen,generation_recipe=copy.deepcopy(generation_recipe),recipe_sha256=recipe_sha,slots=slots,
        scenario_coverage_basis='requested_generation_targets_only',observed_scenario_coverage='not_established_by_this_command',
        labels_generated=False,training_performed=False,generation_submitted=False,product_enabled=False)
    plan['plan_sha256']=c.canonical_hash(plan)
    return plan


def validate_plan(plan):
    if not isinstance(plan,dict):raise ValueError('explicit_formal_plan_required')
    expected=draft_formal_plan(cohort12=plan.get('cohort12'),profiles=plan.get('profiles'),
        group_splits=plan.get('split_freeze',{}).get('formal_group_splits'),generation_recipe=plan.get('generation_recipe'))
    if plan!=expected:raise ValueError('formal_plan_hash_or_derived_slots_changed')
    return dict(plan_sha256=plan['plan_sha256'],source_groups=10,source_groups_per_split=dict(Counter(
        plan['split_freeze']['formal_group_splits'].values())),requested_slots=60,
        requested_slots_per_split=dict(Counter(slot['split'] for slot in plan['slots'])),
        scenario_coverage_basis=plan['scenario_coverage_basis'],observed_scenario_coverage=plan['observed_scenario_coverage'])


def source_registry_entry(plan,*,entry_id,source_group_id,kind,identity_ids=(),lineage_ids=(),assets=None,parents=()):
    """Create a planned source row; stage/split are exclusively freeze-derived."""
    validate_plan(plan);_id(entry_id)
    groups=plan['split_freeze']['formal_group_splits']
    if source_group_id not in groups or kind not in KINDS:raise ValueError('known_formal_group_and_source_kind_required')
    if assets is None:assets={}
    if not isinstance(assets,dict) or set(assets)-set(ASSETS):raise ValueError('concrete_source_asset_types_only_no_model_or_config')
    for value in assets.values():_sha(value)
    return dict(schema_version=REGISTRY_VERSION,entry_id=entry_id,source_group_id=source_group_id,
        reference_group_id=source_group_id,stage='formal',split=groups[source_group_id],kind=kind,
        identity_ids=_ids(identity_ids),lineage_ids=_ids(lineage_ids),assets=copy.deepcopy(assets),parents=_ids(parents))


def _debug_entry(row):
    if (not isinstance(row,dict) or row.get('stage')!='pilot' or row.get('split')!='train'):
        raise ValueError('debug_inventory_must_preserve_explicit_pilot_train_origin')
    sid=_id(row['sample_id']);group=_id(row['source_group_id']);ref=_id(row['reference_group_id'])
    assets={}
    if row.get('video',{}).get('sha256') is not None:assets['raw_video']=_sha(row['video']['sha256'])
    if row.get('image_sha256') is not None:assets['reference_png']=_sha(row['image_sha256'])
    generation=row.get('generation',{})
    control=generation.get('pose_control',{})
    for source,key in (('pose_source_sha256','pose_prediction'),('trajectory_sha256','control_trajectory'),
                       ('control_video_sha256','control_video')):
        if source in control:assets[key]=_sha(control[source])
    # Preserve the original sample ID in the common origin namespace even when
    # its registry entry needs a separate debug: identifier.
    lineage=list(dict.fromkeys([sid,*_ids(row['lineage_ids'])]))
    if generation.get('reference_sha256') is not None:
        lineage=list(dict.fromkeys(lineage+['reference:'+_sha(generation['reference_sha256'])]))
    return dict(schema_version=REGISTRY_VERSION,entry_id='debug:'+sid,source_group_id=group,reference_group_id=ref,
        stage='pilot',split='train',kind='debug',identity_ids=[],lineage_ids=lineage,assets=assets,parents=[])


def validate_registry(plan,entries,*,debug_sources=()):
    """Validate all origins before submission, including reference-only sources.

    Every concrete source SHA shares one namespace across asset types. Algorithm,
    prompt, workflow, config and model receipts never become origin edges.
    """
    validate_plan(plan)
    if not isinstance(entries,(list,tuple)) or not isinstance(debug_sources,(list,tuple)):
        raise ValueError('explicit_registry_and_debug_source_lists_required')
    rows=[]
    for group,profile in sorted(plan['profiles'].items()):
        rows.append(dict(schema_version=REGISTRY_VERSION,entry_id='profile:'+group,source_group_id=group,
            reference_group_id=group,stage='formal',split=plan['split_freeze']['formal_group_splits'][group],
            kind='profile',identity_ids=profile['identity_ids'],lineage_ids=profile['lineage_ids'],assets={},parents=[]))
    for row in entries:
        if not isinstance(row,dict):raise ValueError('explicit_registry_entry_required')
        expected=source_registry_entry(plan,entry_id=row.get('entry_id'),source_group_id=row.get('source_group_id'),
            kind=row.get('kind'),identity_ids=row.get('identity_ids'),lineage_ids=row.get('lineage_ids'),
            assets=row.get('assets'),parents=row.get('parents'))
        if row!=expected:raise ValueError('registry_stage_split_or_source_fields_changed')
        rows.append(copy.deepcopy(row))
    rows.extend(_debug_entry(row) for row in debug_sources)
    ids=[row['entry_id'] for row in rows]
    if len(set(ids))!=len(ids):raise ValueError('unique_registry_entry_ids_required')
    by_id={row['entry_id']:row for row in rows}
    for row in rows:
        if any(parent not in by_id or parent==row['entry_id'] for parent in row['parents']):
            raise ValueError('registry_parent_must_be_another_known_entry')
    visiting=set();visited=set()
    def visit(key):
        if key in visiting:raise ValueError('acyclic_source_ancestry_required')
        if key in visited:return
        visiting.add(key)
        for parent in by_id[key]['parents']:visit(parent)
        visiting.remove(key);visited.add(key)
    for key in ids:visit(key)
    parent={}
    def find(key):
        parent.setdefault(key,key)
        if parent[key]!=key:parent[key]=find(parent[key])
        return parent[key]
    def union(a,b):
        a,b=find(a),find(b)
        if a!=b:parent[max(a,b)]=min(a,b)
    for row in rows:
        anchor='entry:'+row['entry_id']
        origins=[row['entry_id'],row['source_group_id'],row['reference_group_id'],*row['lineage_ids']]
        origins.extend(row['identity_ids'])
        origins.extend('identity:'+value for value in row['identity_ids'])
        for origin in origins:
            union(anchor,'origin:'+origin)
            # Prefixed source hashes cannot evade a cross-type direct asset edge.
            candidate=origin.rsplit(':',1)[-1]
            if re.fullmatch(r'[0-9a-f]{64}',candidate):union(anchor,'sha256:'+candidate)
        for sha in row['assets'].values():union(anchor,'sha256:'+sha)
        for ancestor in row['parents']:union(anchor,'entry:'+ancestor)
    # Reuse the existing materialized-source closure. No missing raw asset is
    # replaced by a fabricated video hash to make pending rows fit its contract.
    materialized=[]
    for row in rows:
        if 'raw_video' in row['assets']:
            materialized.append(dict(sample_id=row['entry_id'],source_group_id=row['source_group_id'],
                reference_group_id=row['reference_group_id'],lineage_ids=row['lineage_ids'],
                video=dict(sha256=row['assets']['raw_video'])))
    for component in c.source_components(materialized):
        for key in component[1:]:union('entry:'+component[0],'entry:'+key)
    components={}
    for row in rows:components.setdefault(find('entry:'+row['entry_id']),[]).append(row)
    for component in components.values():
        formal={row['source_group_id'] for row in component if row['stage']=='formal'}
        if len({row['split'] for row in component})>1:
            raise ValueError('source_registry_cross_split_or_debug_to_heldout_leakage')
        if len(formal)>1:raise ValueError('ten_formal_source_groups_must_be_independent')
    inventory=sorted(rows,key=lambda row:row['entry_id'])
    return dict(schema_version=REGISTRY_VERSION,registry_sha256=c.canonical_hash(inventory),entries=inventory,
        components=sorted(sorted(row['entry_id'] for row in group) for group in components.values()),
        formal_source_groups=10,debug_sources=len(debug_sources),source_independence_is_provenance_based_not_identity_verification=True)


def _pilot_audit(snapshot,cohort):
    samples={row['sample_id']:row for row in snapshot['manifest']['samples']}
    annotations={row['sample_id']:row for row in snapshot['annotations']}
    if not set(cohort)<=set(samples):raise ValueError('all_twelve_selected_pilot_sources_must_exist')
    groups={};decisions=Counter();phase=count=0;selected=[]
    for sid in cohort:
        sample=samples[sid];annotation=annotations.get(sid)
        if (sample['stage']!='pilot' or sample['split']!='train' or sample.get('exercise_id')!='shoulder_abduction'
                or sample.get('view') not in ('front','frontal') or sample.get('scenario') not in ('A','D','E')):
            raise ValueError('selected_cohort_requires_P0_pilot_train_A_D_E_sources')
        groups.setdefault(sample['source_group_id'],[]).append(sample['scenario'])
        if annotation is None:raise ValueError('all_twelve_require_saved_human_full_video_review')
        audit=c.validate_annotation(annotation,sample,snapshot['timelines'][sid])
        watched=annotation['review']
        if (annotation.get('reviewer_role')!='human_operator' or not annotation.get('reviewer_id')
                or watched.get('full_video_watched') is not True or sample.get('status') not in ('accepted','excluded')):
            raise ValueError('all_twelve_require_human_identity_fullwatch_and_final_decision')
        if sample['status']=='accepted':
            has_phase=any(item['label_mask'] for item in annotation['phase_intervals'])
            if not audit['eligible_for_training'] or not (has_phase or annotation['observable_count_mask']):
                raise ValueError('accepted_pilot_requires_actual_usable_phase_or_count_supervision')
            phase+=has_phase
            count+=annotation['observable_count_mask']
        elif not sample.get('exclusion_reason'):raise ValueError('excluded_pilot_requires_reason')
        decisions[sample['status']]+=1
        selected.append(dict(sample=copy.deepcopy(sample),annotation=copy.deepcopy(annotation),
            timeline_sha256=c.canonical_hash(snapshot['timelines'][sid])))
    if len(groups)!=4 or any(Counter(values)!=Counter(A=1,D=1,E=1) for values in groups.values()):
        raise ValueError('pilot_cohort_requires_four_groups_each_A_D_E_once')
    return dict(selected=selected,cohort_sha256=c.canonical_hash(selected),decisions=dict(decisions),
        accepted_sources=decisions['accepted'],excluded_sources=decisions['excluded'],
        accepted_with_known_phase_intervals=phase,accepted_with_known_count=count,
        phase_supervision_coverage='present' if phase else 'not_established',
        workflow_readiness='unproven',training_ready=False,reviewer_identity_is_verified=False)


def _debug_sources(root,snapshot):
    rows=[copy.deepcopy(row) for row in snapshot['manifest']['samples'] if row['stage']=='pilot']
    # This includes quiet reference-only sources and every unselected attempt.
    for path in sorted((root/'references').glob('*.json')):
        if not path.resolve().is_relative_to(root):raise ValueError('reference_record_outside_dataset_root')
        row=c._read_json(path);_debug_entry(row)
        for ref,sha in ((row['image_path'],row['image_sha256']),(row['video']['path'],row['video']['sha256'])):
            source=review._within(root,ref)
            if review._hash(source)!=sha:raise ValueError('debug_reference_source_hash_changed')
        row['lineage_ids']=list(dict.fromkeys([row['sample_id'],*row['lineage_ids']]))
        row['sample_id']='reference-record:'+str(path.relative_to(root)).replace('\\','/').replace('/',':')
        row['debug_reference_record_sha256']=review._hash(path)
        rows.append(row)
    return rows


def _verify_recipe(root,recipe):
    for key in ('model_receipt','config'):
        receipt=recipe[key];path=Path(receipt['path'])
        path=path.resolve() if path.is_absolute() else (root/path).resolve()
        if review._hash(path)!=receipt['sha256']:raise ValueError('frozen_generation_'+key+'_hash_changed')
        value=c._read_json(path)
        if not isinstance(value,dict):raise ValueError('generation_recipe_file_must_be_JSON_object')
        if key=='model_receipt':
            hashes=[row.get('sha256') for row in value.get('models',[]) if isinstance(row,dict)]
            if recipe['model_sha256'] not in hashes:raise ValueError('recipe_model_not_in_verified_model_receipt')


def _history(root,debug):
    history=[]
    for sample in debug:
        key=hashlib.sha256(sample['sample_id'].encode()).hexdigest()
        for path in sorted((root/'annotations/review-versions'/key).glob('*.json')):
            if not path.resolve().is_relative_to(root):raise ValueError('pilot_history_outside_dataset_root')
            history.append(dict(path=str(path.relative_to(root)),sha256=review._hash(path)))
    return history


def _selected_versions(root,cohort):
    versions=[]
    for sid in cohort:
        key=hashlib.sha256(sid.encode()).hexdigest()
        files=sorted((root/'annotations/review-versions'/key).glob('*.json'))
        if not files:raise ValueError('saved_pilot_review_version_required')
        path=files[-1]
        if not path.resolve().is_relative_to(root):raise ValueError('pilot_history_outside_dataset_root')
        versions.append(dict(sample_id=sid,path=str(path.relative_to(root)),sha256=review._hash(path)))
    return versions


def _read_freeze(root):
    value=c._read_json(root/'manifests/formal-plan-freeze.json')
    expected=copy.deepcopy(value);sha=expected.pop('freeze_sha256',None)
    if (value.get('schema_version')!=FREEZE_VERSION or value.get('root')!=str(root)
            or sha!=c.canonical_hash(expected)):
        raise ValueError('immutable_formal_freeze_changed_or_tampered')
    validate_plan(value['plan'])
    if (value.get('plan_sha256')!=value['plan']['plan_sha256']
            or value.get('split_freeze')!=value['plan']['split_freeze']
            or value.get('recipe_sha256')!=value['plan']['recipe_sha256']):
        raise ValueError('frozen_plan_or_recipe_binding_changed')
    return value


def freeze_formal_plan(root,plan,*,registry=()):
    """Verify actual media/review history and create one immutable root receipt.

    Does not edit dataset.json or any annotation/reference. Same-content resume
    is idempotent; changed plan, sources, reviews, registry or files are refused.
    """
    validate_plan(plan);root=Path(root).resolve()
    if not root.is_dir():raise ValueError('existing_dataset_root_required')
    destination=root/'manifests/formal-plan-freeze.json'
    if not destination.resolve().is_relative_to(root):raise ValueError('formal_freeze_output_outside_root')
    snapshot=review.load_reviewed(root)
    pilot=_pilot_audit(snapshot,plan['cohort12'])
    debug=_debug_sources(root,snapshot)
    sources=validate_registry(plan,registry,debug_sources=debug)
    _verify_recipe(root,plan['generation_recipe'])
    # All pilot rows, including previous attempts, remain part of the frozen
    # provenance inventory; no existing generation row or review is rewritten.
    history=_history(root,debug)
    frozen=dict(schema_version=FREEZE_VERSION,root=str(root),status='source_and_review_plan_frozen',
        plan=copy.deepcopy(plan),plan_sha256=plan['plan_sha256'],split_freeze=copy.deepcopy(plan['split_freeze']),
        recipe_sha256=plan['recipe_sha256'],pilot_audit=pilot,source_registry=sources,debug_sources=debug,
        selected_review_versions=_selected_versions(root,plan['cohort12']),
        pilot_inventory_sha256=c.canonical_hash(debug),review_history=history,review_history_sha256=c.canonical_hash(history),
        scenario_coverage_basis='requested_generation_targets_only',observed_scenario_coverage='not_established_by_this_command',
        workflow_readiness='unproven',training_ready=False,generation_submitted=False,labels_generated=False,product_enabled=False)
    frozen['freeze_sha256']=c.canonical_hash(frozen)
    if destination.exists():
        old=_read_freeze(root)
        if old!=frozen:raise ValueError('immutable_formal_freeze_changed_or_tampered')
    else:
        destination.parent.mkdir(parents=True,exist_ok=True)
        with destination.open('x',encoding='utf-8',newline='\n') as stream:
            json.dump(frozen,stream,ensure_ascii=False,indent=2,allow_nan=False)
            stream.write('\n')
    return copy.deepcopy(frozen)


def load_frozen_plan(root):
    """Reverify a freeze before any external queue, text or generation request.

    All original media are rehashed/decoded through load_reviewed. The selected
    twelve latest review versions and their labels remain fixed. Newly appended
    debug sources are checked against the ten groups without rewriting the old
    freeze; current_registry_sha256 therefore need not equal its frozen value.
    Model/config RECEIPT bytes are checked here; model inference and execution
    graph verification remain the caller's separate generation responsibilities.
    """
    root=Path(root).resolve();frozen=_read_freeze(root);plan=frozen['plan']
    snapshot=review.load_reviewed(root)
    pilot=_pilot_audit(snapshot,plan['cohort12'])
    if (pilot!=frozen['pilot_audit']
            or _selected_versions(root,plan['cohort12'])!=frozen['selected_review_versions']):
        raise ValueError('frozen_selected_pilot_sources_or_review_versions_changed')
    for row in frozen['review_history']:
        path=(root/row['path']).resolve()
        if not path.is_relative_to(root) or review._hash(path)!=row['sha256']:
            raise ValueError('frozen_pilot_review_history_changed')
    if c.canonical_hash(frozen['review_history'])!=frozen['review_history_sha256']:
        raise ValueError('frozen_pilot_review_history_index_changed')
    if c.canonical_hash(frozen['debug_sources'])!=frozen['pilot_inventory_sha256']:
        raise ValueError('frozen_debug_inventory_changed')
    entries=[row for row in frozen['source_registry']['entries'] if row['stage']=='formal' and row['kind']!='profile']
    original=validate_registry(plan,entries,debug_sources=frozen['debug_sources'])
    if original!=frozen['source_registry']:raise ValueError('frozen_source_registry_changed')
    debug=_debug_sources(root,snapshot)
    by_id={row['sample_id']:row for row in debug}
    for row in frozen['debug_sources']:
        if row['sample_id'] not in by_id or _debug_entry(row)!=_debug_entry(by_id[row['sample_id']]):
            raise ValueError('frozen_debug_source_disappeared_or_changed')
    current=validate_registry(plan,entries,debug_sources=debug)
    _verify_recipe(root,plan['generation_recipe'])
    return dict(schema_version=FREEZE_VERSION,plan=copy.deepcopy(plan),split_freeze=copy.deepcopy(plan['split_freeze']),
        registry=current,pilot_audit=copy.deepcopy(pilot),frozen_sha=frozen['freeze_sha256'],
        frozen_registry_sha256=original['registry_sha256'],current_registry_sha256=current['registry_sha256'],
        debug_sources=debug,selected_review_versions=copy.deepcopy(frozen['selected_review_versions']),
        original_media_and_reviews_reverified=True,model_receipt_and_config_reverified=True,
        model_weight_bytes_reverified_by_this_function=False,execution_graph_verified_by_this_function=False,
        workflow_readiness='unproven',training_ready=False)
