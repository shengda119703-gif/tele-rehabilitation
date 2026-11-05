"""TEST-only plans, real tiny media and mock human declarations; no model/GPU.

All review identities below are unit fixtures, never genuine human references.
Only temporary roots are frozen; the user's actual dataset is never changed.
"""
from collections import Counter
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import av
import numpy as np
from PIL import Image

from tools.rehab_ml.synthetic import contracts as c,formal_plan as f,review,video


def inputs():
    groups={'TEST-formal'+str(i):'train' if i<6 else 'val' if i<8 else 'test' for i in range(10)}
    profiles={group:dict(prompt='TEST fictional reference '+group,identity_ids=[group],lineage_ids=[])
              for group in groups}
    recipe=dict(version='TEST-template-v1',prompt_version='TEST-prompt-v1',seed=42,model_sha256='a'*64,
        model_receipt=dict(path='manifests/TEST-model-receipt.json',sha256='b'*64),
        config=dict(path='manifests/TEST-generation-config.json',sha256='c'*64),scenarios={})
    for scenario in c.SCENARIOS:
        recipe['scenarios'][scenario]=dict(prompt='TEST requested motion '+scenario,
            workflow_template={'1':dict(class_type='TEST-no-execution',inputs=dict(reference='$reference',seed=0))},
            late_bindings=[dict(node_id='1',input_name='reference',binding='reference_file'),
                           dict(node_id='1',input_name='seed',binding='seed')],guide_mode='none',guide_version='TEST-none-v1')
    return dict(cohort12=['TEST-pilot'+str(i)+'-'+s for i in range(4) for s in 'ADE'],
                profiles=profiles,group_splits=groups,generation_recipe=recipe)


def tiny_video(path,index):
    path.parent.mkdir(parents=True,exist_ok=True)
    with av.open(str(path),'w') as container:
        stream=container.add_stream('libx264',rate=30)
        stream.width=64;stream.height=64;stream.pix_fmt='yuv420p'
        stream.options={'preset':'ultrafast','crf':'18'}
        for frame_index in range(3):
            image=np.zeros((64,64,3),np.uint8);image[:]=[10+index*8,40+frame_index*35,100]
            frame=av.VideoFrame.from_ndarray(image,format='rgb24')
            for packet in stream.encode(frame):container.mux(packet)
        for packet in stream.encode():container.mux(packet)


class FormalPlanPureTests(unittest.TestCase):
    def setUp(self):self.data=inputs();self.plan=f.draft_formal_plan(**self.data)

    def test_draft_freezes_10_groups_6_2_2_and_60_requested_slots_without_submission(self):
        original=copy.deepcopy(self.data)
        self.assertEqual(self.plan,f.draft_formal_plan(**self.data));self.assertEqual(self.data,original)
        audit=f.validate_plan(self.plan)
        self.assertEqual(audit['source_groups_per_split'],dict(train=6,val=2,test=2))
        self.assertEqual(audit['requested_slots_per_split'],dict(train=36,val=12,test=12))
        self.assertEqual(len(self.plan['slots']),60)
        self.assertEqual(Counter(slot['scenario'] for slot in self.plan['slots']),Counter({s:10 for s in 'ABCDEF'}))
        self.assertEqual(self.plan['observed_scenario_coverage'],'not_established_by_this_command')
        self.assertFalse(self.plan['generation_submitted']);self.assertFalse(self.plan['labels_generated'])
        for slot in self.plan['slots']:
            self.assertEqual((slot['frames'],slot['fps'],slot['width'],slot['height']),(241,30,640,384))
            self.assertEqual(slot['split'],self.data['group_splits'][slot['source_group_id']])
            self.assertEqual(slot['stage'],'formal');self.assertIn('workflow_template_sha256',slot)
            self.assertNotIn('workflow_sha256',slot)

    def test_plan_tampering_split_override_bad_bindings_and_non_independent_groups_reject(self):
        changed=copy.deepcopy(self.plan);changed['slots'][0]['split']='test'
        with self.assertRaisesRegex(ValueError,'derived_slots_changed'):f.validate_plan(changed)
        for mutate in (lambda x:x['profiles']['TEST-formal0'].update(split='test'),
                       lambda x:x['group_splits'].update({'TEST-formal0':'test'}),
                       lambda x:x['generation_recipe']['scenarios']['A']['late_bindings'][0].update(input_name='missing')):
            changed=copy.deepcopy(self.data);mutate(changed)
            with self.assertRaises(ValueError):f.draft_formal_plan(**changed)

    def test_registry_stage_split_is_derived_and_cannot_be_changed(self):
        row=f.source_registry_entry(self.plan,entry_id='TEST-ref',source_group_id='TEST-formal6',kind='reference',
                                    assets={'reference_png':'d'*64})
        self.assertEqual((row['stage'],row['split']),('formal','val'))
        with self.assertRaises(TypeError):
            f.source_registry_entry(self.plan,entry_id='TEST-ref',source_group_id='TEST-formal6',kind='reference',split='train')
        row['split']='train'
        with self.assertRaisesRegex(ValueError,'registry_stage_split'):f.validate_registry(self.plan,[row])

    def test_reference_only_cross_type_assets_and_transitive_ancestry_cannot_leak(self):
        def entry(key,group,**kw):return f.source_registry_entry(self.plan,entry_id=key,source_group_id=group,kind='pending',**kw)
        first=entry('TEST-reference','TEST-formal0',assets={'reference_png':'d'*64})
        second=entry('TEST-control','TEST-formal6',assets={'control_trajectory':'d'*64})
        with self.assertRaisesRegex(ValueError,'cross_split'):f.validate_registry(self.plan,[first,second])
        second=entry('TEST-derived','TEST-formal6',parents=['TEST-reference'])
        with self.assertRaisesRegex(ValueError,'cross_split'):f.validate_registry(self.plan,[first,second])
        second=entry('TEST-other-train','TEST-formal1',assets={'pose_prediction':'d'*64})
        with self.assertRaisesRegex(ValueError,'must_be_independent'):f.validate_registry(self.plan,[first,second])
        second=entry('TEST-lineage-alias','TEST-formal6',lineage_ids=['reference:'+'d'*64])
        with self.assertRaisesRegex(ValueError,'cross_split'):f.validate_registry(self.plan,[first,second])

    def test_all_debug_attempts_and_motion_ancestors_taint_heldout_but_train_reuse_is_allowed(self):
        debug=dict(sample_id='TEST-unselected-old-attempt',source_group_id='TEST-pilot-other',
            reference_group_id='TEST-ref-other',stage='pilot',split='train',lineage_ids=['TEST-motion-ancestor'],
            video=dict(sha256='a'*64),generation=dict(pose_control=dict(trajectory_sha256='b'*64)))
        for group in ('TEST-formal6','TEST-formal8'):
            row=f.source_registry_entry(self.plan,entry_id='TEST-new-control',source_group_id=group,kind='control',
                                        assets={'control_trajectory':'b'*64})
            with self.assertRaisesRegex(ValueError,'cross_split'):f.validate_registry(self.plan,[row],debug_sources=[debug])
        row=f.source_registry_entry(self.plan,entry_id='TEST-train-control',source_group_id='TEST-formal0',kind='control',
                                    lineage_ids=['TEST-motion-ancestor'])
        audit=f.validate_registry(self.plan,[row],debug_sources=[debug])
        self.assertEqual(audit['debug_sources'],1)
        self.assertFalse(any('video' in item for item in audit['entries']))

    def test_identity_and_original_pilot_sample_ids_share_the_origin_namespace(self):
        data=copy.deepcopy(self.data)
        data['profiles']['TEST-formal0']['identity_ids']=['TEST-shared-person']
        data['profiles']['TEST-formal6']['lineage_ids']=['TEST-shared-person']
        with self.assertRaisesRegex(ValueError,'cross_split'):
            f.validate_registry(f.draft_formal_plan(**data),[])
        debug=dict(sample_id='TEST-original-pilot-sample',source_group_id='TEST-debug-group',
            reference_group_id='TEST-debug-reference',lineage_ids=['TEST-other-ancestor'],
            stage='pilot',split='train',video=dict(sha256='d'*64))
        row=f.source_registry_entry(self.plan,entry_id='TEST-new-ref',source_group_id='TEST-formal6',kind='reference',
                                    lineage_ids=['TEST-original-pilot-sample'])
        with self.assertRaisesRegex(ValueError,'cross_split'):
            f.validate_registry(self.plan,[row],debug_sources=[debug])

    def test_global_weights_algorithms_and_prompt_are_recipe_not_lineage(self):
        for key in ('model:'+'a'*64,'algorithm:v1','prompt:v1','workflow:v1','controller_version:v1'):
            with self.assertRaisesRegex(ValueError,'not_source_lineage'):
                f.source_registry_entry(self.plan,entry_id='TEST',source_group_id='TEST-formal0',kind='control',lineage_ids=[key])
        with self.assertRaisesRegex(ValueError,'no_model_or_config'):
            f.source_registry_entry(self.plan,entry_id='TEST',source_group_id='TEST-formal0',kind='control',assets={'model':'a'*64})
        # Shared algorithm/model recipe is valid for all ten independent groups.
        self.assertEqual(f.validate_registry(self.plan,[])['formal_source_groups'],10)


class FormalPlanMediaGateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='synthetic-formal-TEST-');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.data=inputs();self.samples=[];self.timelines={}
        (self.root/'manifests').mkdir();(self.root/'references').mkdir()
        for index,sid in enumerate(self.data['cohort12']):
            source=self.root/'raw'/str(sid+'.mp4');tiny_video(source,index)
            path=self.root/'manifests/timelines'/str(sid+'.json')
            timeline=video.probe_video(source,timeline_path=path);group=sid.rsplit('-',1)[0]
            sample=dict(sample_id=sid,source_group_id=group,reference_group_id=group,lineage_ids=['identity:'+group],
                stage='pilot',split='train',scenario=sid[-1],exercise_id='shoulder_abduction',view='front',side='unknown',status='pending',
                video=dict(path=str(source),sha256=review._hash(source),timeline_path=str(path),timeline_sha256=review._hash(path),
                           width=64,height=64,frame_count=3),
                generation=dict(prompt_version='TEST-only',seed=index,model_sha256='a'*64,workflow_sha256='b'*64,prompt_sha256='c'*64))
            self.samples.append(sample);self.timelines[sid]=timeline
        self.manifest=dict(schema_version=c.SCHEMA_VERSION,dataset_id='TEST-no-real-human-labels',split_freeze=None,samples=self.samples)
        self.write_manifest()
        for key,name,value in (('model_receipt','TEST-model-receipt.json',dict(models=[dict(sha256='a'*64,TEST='model boundary only')])),
                               ('config','TEST-generation-config.json',dict(TEST='no inference or training'))):
            path=self.root/'manifests'/name;path.write_text(json.dumps(value),encoding='utf-8')
            self.data['generation_recipe'][key]=dict(path=str(path),sha256=review._hash(path))
        self.plan=f.draft_formal_plan(**self.data)

    def write_manifest(self):
        (self.root/'manifests/dataset.json').write_text(json.dumps(self.manifest),encoding='utf-8')

    def review_all(self,*,all_excluded=False,excluded_role='human_operator',excluded_watched=True):
        store=review.ReviewStore(self.root)
        for token,sid in list(store.tokens.items()):
            sample=store.by_id[sid];excluded=all_excluded or sample['scenario']=='E'
            form=c.prepare_review(sample,self.timelines[sid],reviewer_id='TEST-unit-fixture-not-a-real-human',
                                  reviewer_role=excluded_role if excluded else 'human_operator')
            form['sample_id']=token;form['review']['full_video_watched']=excluded_watched if excluded else True
            if not excluded:
                form.update(side='left',side_mask=True)
                if sample['scenario']=='A':
                    form['phase_intervals']=[dict(phase='rest_or_other',start_s=0.,end_s=2/30,label_mask=True)]
                else:form.update(observable_count=0,observable_count_mask=True)
            store.submit(dict(token=token,annotation=form,decision='excluded' if excluded else 'accepted',
                reason='TEST excluded fixture, no movement conclusion' if excluded else '',playback_coverage=[]))

    def test_zero_human_reviews_refuses_freeze_without_changing_dataset_or_creating_receipt(self):
        original=(self.root/'manifests/dataset.json').read_bytes()
        with self.assertRaisesRegex(ValueError,'saved_human_full_video_review'):f.freeze_formal_plan(self.root,self.plan)
        self.assertEqual((self.root/'manifests/dataset.json').read_bytes(),original)
        self.assertFalse((self.root/'manifests/formal-plan-freeze.json').exists())
        self.assertFalse((self.root/'annotations').exists())

    def test_real_media_mixed_decisions_freeze_and_resume_preserve_unknowns_and_all_history(self):
        self.review_all();original=(self.root/'manifests/dataset.json').read_bytes()
        freeze=f.freeze_formal_plan(self.root,self.plan)
        self.assertEqual(freeze,f.freeze_formal_plan(self.root,self.plan))
        audit=freeze['pilot_audit']
        self.assertEqual((audit['accepted_sources'],audit['excluded_sources']),(8,4))
        self.assertEqual((audit['accepted_with_known_phase_intervals'],audit['accepted_with_known_count']),(4,4))
        for row in audit['selected']:
            if row['sample']['status']=='excluded':
                self.assertIsNone(row['annotation']['observable_count']);self.assertFalse(row['annotation']['observable_count_mask'])
                self.assertEqual(row['annotation']['phase_intervals'],[])
        self.assertEqual(len(freeze['review_history']),12)
        loaded=f.load_frozen_plan(self.root)
        self.assertEqual(loaded['frozen_sha'],freeze['freeze_sha256']);self.assertFalse(loaded['training_ready'])
        self.assertEqual((self.root/'manifests/dataset.json').read_bytes(),original)

    def test_all_excluded_can_freeze_sources_but_not_quality_or_training_readiness(self):
        self.review_all(all_excluded=True)
        frozen=f.freeze_formal_plan(self.root,self.plan)
        self.assertEqual(frozen['pilot_audit']['accepted_sources'],0)
        self.assertEqual(frozen['pilot_audit']['phase_supervision_coverage'],'not_established')
        self.assertEqual(frozen['workflow_readiness'],'unproven');self.assertFalse(frozen['training_ready'])

    def test_AI_or_incomplete_excluded_review_cannot_unlock_freeze(self):
        self.review_all(all_excluded=True,excluded_role='ai_draft')
        with self.assertRaisesRegex(ValueError,'human_identity_fullwatch'):f.freeze_formal_plan(self.root,self.plan)
        self.review_all(all_excluded=True,excluded_watched=False)
        with self.assertRaisesRegex(ValueError,'human_identity_fullwatch'):f.freeze_formal_plan(self.root,self.plan)

    def test_missing_cohort_slot_and_count_unknown_accepted_are_not_pilot_evidence(self):
        self.review_all();changed=copy.deepcopy(self.data)
        changed['cohort12'][-1]='TEST-missing-source';plan=f.draft_formal_plan(**changed)
        with self.assertRaisesRegex(ValueError,'twelve_selected_pilot_sources'):f.freeze_formal_plan(self.root,plan)
        snapshot=review.load_reviewed(self.root)
        row=next(x for x in snapshot['annotations'] if x['sample_id'].endswith('-D'))
        row.update(observable_count=None,observable_count_mask=False)
        with patch.object(f.review,'load_reviewed',return_value=snapshot):
            with self.assertRaisesRegex(ValueError,'usable_phase_or_count'):f.freeze_formal_plan(self.root,self.plan)

    def test_old_unselected_attempt_and_reference_only_source_taint_are_checked(self):
        self.review_all()
        old=copy.deepcopy(self.samples[0]);old['sample_id']='TEST-old-unselected-attempt'
        source=self.root/'raw/old.mp4';tiny_video(source,15)
        path=self.root/'manifests/old-timeline.json';actual=video.probe_video(source,timeline_path=path)
        old['source_group_id']='TEST-old-debug';old['reference_group_id']='TEST-old-debug'
        old['lineage_ids']=['TEST-old-motion-source'];old['video'].update(path=str(source),sha256=review._hash(source),
            timeline_path=str(path),timeline_sha256=review._hash(path))
        self.samples.append(old);self.write_manifest()
        image=self.root/'references/TEST-reference-only.png';Image.new('RGB',(64,64)).save(image)
        ref=dict(sample_id='TEST-reference-only',source_group_id='TEST-ref-debug',reference_group_id='TEST-ref-debug',
                 lineage_ids=['TEST-private-reference-source'],stage='pilot',split='train',
                 image_path=str(image),image_sha256=review._hash(image),video=copy.deepcopy(old['video']))
        (self.root/'references/TEST-reference-only.json').write_text(json.dumps(ref),encoding='utf-8')
        for ancestor in ('TEST-old-motion-source','TEST-private-reference-source','TEST-reference-only'):
            row=f.source_registry_entry(self.plan,entry_id='TEST-heldout-pending',source_group_id='TEST-formal6',
                                        kind='pending',lineage_ids=[ancestor])
            with self.assertRaisesRegex(ValueError,'cross_split'):f.freeze_formal_plan(self.root,self.plan,registry=[row])
        frozen=f.freeze_formal_plan(self.root,self.plan)
        self.assertEqual(frozen['source_registry']['debug_sources'],14)

    def test_freeze_tamper_changed_recipe_and_new_review_version_refuse_resume(self):
        self.review_all();frozen=f.freeze_formal_plan(self.root,self.plan)
        path=self.root/'manifests/formal-plan-freeze.json';original=path.read_bytes()
        changed=copy.deepcopy(frozen);changed['pilot_audit']['accepted_sources']=100
        path.write_text(json.dumps(changed),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'tampered'):f.load_frozen_plan(self.root)
        path.write_bytes(original)
        config=Path(self.data['generation_recipe']['config']['path']);config_original=config.read_bytes()
        config.write_text('{"TEST":"changed"}',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'config_hash_changed'):f.load_frozen_plan(self.root)
        config.write_bytes(config_original)
        self.review_all()
        with self.assertRaisesRegex(ValueError,'review_versions_changed'):f.load_frozen_plan(self.root)
        self.assertEqual(path.read_bytes(),original)

    def test_frozen_plan_and_changed_original_media_are_never_silently_reused(self):
        self.review_all();f.freeze_formal_plan(self.root,self.plan)
        changed=copy.deepcopy(self.data);changed['generation_recipe']['seed']=43
        with self.assertRaisesRegex(ValueError,'immutable_formal_freeze'):
            f.freeze_formal_plan(self.root,f.draft_formal_plan(**changed))
        Path(self.samples[0]['video']['path']).write_bytes(b'TEST corrupted source bytes')
        with self.assertRaisesRegex(ValueError,'hash_changed'):f.load_frozen_plan(self.root)

    def test_loader_rechecks_new_unreviewed_debug_sources_without_rewriting_frozen_receipt(self):
        self.review_all();frozen=f.freeze_formal_plan(self.root,self.plan)
        receipt=self.root/'manifests/formal-plan-freeze.json';original=receipt.read_bytes()
        extra=copy.deepcopy(self.samples[0]);extra['sample_id']='TEST-debug-created-after-freeze'
        extra.update(source_group_id='TEST-new-debug',reference_group_id='TEST-new-debug',lineage_ids=['TEST-new-debug-source'])
        source=self.root/'raw/new-debug.mp4';tiny_video(source,14)
        path=self.root/'manifests/new-debug-timeline.json';video.probe_video(source,timeline_path=path)
        extra['video'].update(path=str(source),sha256=review._hash(source),timeline_path=str(path),timeline_sha256=review._hash(path))
        self.samples.append(extra);self.write_manifest()
        current=f.load_frozen_plan(self.root)
        self.assertEqual(current['frozen_sha'],frozen['freeze_sha256'])
        self.assertEqual(current['registry']['debug_sources'],13)
        self.assertNotEqual(current['current_registry_sha256'],current['frozen_registry_sha256'])
        self.assertEqual(receipt.read_bytes(),original)
        # Even an unreviewed new trial taints the heldout profile immediately.
        extra['lineage_ids'].append('identity:TEST-formal6');self.write_manifest()
        with self.assertRaisesRegex(ValueError,'cross_split'):f.load_frozen_plan(self.root)
        self.assertEqual(receipt.read_bytes(),original)


if __name__=='__main__':unittest.main()
