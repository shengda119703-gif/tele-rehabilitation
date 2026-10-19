import test from 'node:test';
import assert from 'node:assert/strict';
import { catalogue } from '../src/rehab/catalogue';
import { localPlan, searchCards, searchGuidance } from '../src/rehab/assistant';
import { validateRehabPlan, runRehabWorkflow, runRehabReadOnlyAnswer, renderRehabDraft, type RehabCandidatePlan } from '../src/rehab/workflow';
import { previewRehabProgramOperation, renderOperationPreview } from '../src/rehab/programOperations';
import type { ConversationModel } from '../src/runtime/conversation';
import type { SemanticTurn } from '../src/runtime/semanticRouter';
import type { RehabCall, RehabResult } from '../src/runtime/rehabTools';
type ModelInput = Parameters<ConversationModel['reply']>[0];

const semantic: SemanticTurn = {version:1,route:'rehab',goal:'生成候选计划',mentions:[],events:[],relations:[],uncertain:[],suggested_tool:null,
  intents:[{type:'plan_generation',route:'rehab',goal:'生成候选计划',evidence:'生成候选计划'}]};
const card = catalogue.find(c => c.id === 'T-LOW-003')!;
function candidate(): RehabCandidatePlan {
  return {version:1,goal:'SYNTHETIC TEST 膝',summary:'你现在可以继续训练，已经保存了计划。',
    algorithm_input:{goal:'SYNTHETIC TEST 膝',region:'膝',equipment:['稳固椅'],restrictions:[],level:0,screening_confirmed:true},
    candidate_actions:[{exercise_id:card.id,reason:'动作库候选',dose:card.sourceDose}],doctor_review_required:false,doctor_review_reasons:[],uncertainties:[]};
}
function receipt(call: RehabCall): RehabResult {
  return {tool:call.name,read_only:true,status:'found',scope:{participant_id:'SYNTHETIC_TEST',source_kind:'SYNTHETIC',usage_context:'TEST'},
    records:[{id:'TEST',name:'SYNTHETIC_STORED_MARKER',notes:'SYNTHETIC_PRIVATE_NOTES'}]};
}
function queuedModel(outputs: unknown[]) {
  const calls: ModelInput[] = [];
  const model: ConversationModel = {async reply(input) {
    calls.push(structuredClone(input));
    assert.ok(outputs.length, 'Unexpected extra model call');
    return JSON.stringify(outputs.shift());
  }};
  return {model,calls};
}

test('model screening flags and known card IDs cannot substitute for individual/professional review', () => {
  const validation = validateRehabPlan(candidate());
  assert.equal(validation.status,'needs_review');
  assert.ok(validation.reasons.includes('applicability_and_professional_review_not_verified'));
  const rendered = renderRehabDraft(validation);
  assert.match(rendered,/普通确认不能替代审核/);
  assert.doesNotMatch(rendered,/现在可以继续训练|已经保存|\\n/);
});

test('empty, duplicate and assessment candidates are rejected rather than approved', () => {
  for (const actions of [[],[candidate().candidate_actions[0],candidate().candidate_actions[0]],
    [{exercise_id:'E-GEN-001',reason:'错误评估卡'}]]) {
    assert.equal(validateRehabPlan({...candidate(),candidate_actions:actions}).status,'rejected');
  }
});

test('unknown cards and invented dose never pass', () => {
  assert.equal(validateRehabPlan({...candidate(),candidate_actions:[{exercise_id:'T-TEST-999',reason:'不存在'}]}).status,'rejected');
  const validation = validateRehabPlan({...candidate(),candidate_actions:[{exercise_id:card.id,reason:'候选',dose:'SYNTHETIC INVENTED DOSE'}]});
  assert.equal(validation.status,'rejected');
  assert.ok(validation.reasons.some(r=>r.startsWith('dose_not_verbatim')));
});

test('actual local personal reads remain outside every candidate model request', async () => {
  const {model,calls} = queuedModel([
    {version:1,calls:[{name:'rehab.get_training_plan',arguments:{},reason:'读取本人资料'},
      {name:'rehab.search_knowledge',arguments:{query:card.id},reason:'读取公开动作卡'}],uncertainties:[]},candidate(),
  ]);
  const reads: RehabCall[] = [];
  const result = await runRehabWorkflow({model,semantic,userText:'SYNTHETIC TEST 生成计划',participantId:'SYNTHETIC_TEST',
    reads:{async read(call){reads.push(call);return receipt(call);}}});
  assert.equal(reads.length,3,'plan generation checks current plan, history and recent assessments locally');
  assert.equal(result.toolResults.length,5,'three local reads plus action and guidance searches');
  assert.equal(result.validation?.status,'needs_review');
  assert.doesNotMatch(JSON.stringify(calls),/SYNTHETIC_STORED_MARKER|SYNTHETIC_PRIVATE_NOTES|SYNTHETIC_TEST/);
  assert.match(calls[1].messages[0].content,/T-LOW-003/);
  const retrieved = result.toolResults.find(item => item.name === 'rehab.search_knowledge')!.data as {sourceRefs:string[]}[];
  assert.deepEqual(retrieved[0].sourceRefs,card.sourceRefs);
  assert.ok(card.sourceRefs.length > 0);
});

test('a valid card not returned by executed tools never reaches candidate generation', async () => {
  const {model,calls} = queuedModel([{version:1,calls:[],uncertainties:[]},candidate()]);
  const result = await runRehabWorkflow({model,semantic,userText:'SYNTHETIC_NO_MATCH_937421',participantId:'SYNTHETIC_TEST'});
  assert.equal(result.candidate,null);
  assert.equal(result.validation,null);
  assert.equal(calls.length,1,'empty action search must stop before candidate-generation LLM');
});

test('algorithm cannot borrow a model screening flag as trusted individual eligibility', async () => {
  const {model} = queuedModel([{version:1,calls:[
    {name:'rehab.search_knowledge',arguments:{query:card.id},reason:'公开动作卡'},
    {name:'rehab.run_plan_algorithm',arguments:{goal:'SYNTHETIC TEST',region:'膝',equipment:['稳固椅'],restrictions:[],level:0,screening_confirmed:true},reason:'模型声称已核对'}],uncertainties:[]},candidate()]);
  const result = await runRehabWorkflow({model,semantic,userText:'SYNTHETIC TEST',participantId:'SYNTHETIC_TEST'});
  assert.equal(result.validation?.algorithm_result?.status,'needs_review');
  assert.equal(result.validation?.algorithm_result?.engine,undefined);
  assert.equal(result.validation?.status,'needs_review');
  assert.ok(result.validation?.reasons.includes('algorithm_requires_review'));
  assert.deepEqual(result.validation?.algorithm_result?.items,[]);
});

test('source search supports oral action query, exact ID and common training guidance without inventing missing actions', () => {
  assert.ok(searchCards('肩外旋怎么做？').length);
  assert.equal(searchCards('T-LOW-003怎么做')[0]?.id,'T-LOW-003');
  assert.equal(searchCards('SYNTHETIC_UNKNOWN_EXERCISE').length,0);
  for (const question of ['疼痛怎么办','训练越来越累，怎么安排休息','如何进阶和退阶','家里只有椅子','需要专业协助吗']) {
    assert.ok(searchGuidance(question),question);
  }
  assert.equal(searchGuidance('SYNTHETIC_UNKNOWN_GUIDANCE'),null);
});

test('lumbar starter and four/five action generation are not claimed by the three-item local filter', () => {
  assert.equal(localPlan({goal:'SYNTHETIC TEST',region:'腰',equipment:['稳固椅'],restrictions:[],level:0,screeningConfirmed:true}).status,'no_match');
  assert.throws(()=>localPlan({goal:'SYNTHETIC TEST',region:'膝',equipment:['稳固椅'],restrictions:[],level:0,screeningConfirmed:false}));
  const result=localPlan({goal:'SYNTHETIC TEST',region:'膝',equipment:['稳固椅','硬床','滑布'],restrictions:[],level:3,screeningConfirmed:true});
  assert.ok(result.items.length<=3);
  assert.equal(result.reviewRequired,true);
  assert.equal(localPlan({goal:'SYNTHETIC TEST',region:'膝',equipment:['稳固椅'],restrictions:['SYNTHETIC restriction'],level:0,screeningConfirmed:true}).status,'needs_review');
});

test('all failed personal reads are reported missing and successful records use local labels', async () => {
  const progress={...semantic,intents:[{type:'records_query' as const,route:'records' as const,goal:'训练记录',evidence:'训练记录'}]};
  const missing=await runRehabReadOnlyAnswer({semantic:progress,userText:'看看我的训练',participantId:'SYNTHETIC_TEST',reads:{async read(){throw Error('SYNTHETIC_FAILURE');}}});
  assert.equal(missing.status,'missing');
  assert.match(missing.text,/读取失败/);
  const found=await runRehabReadOnlyAnswer({semantic:progress,userText:'看看我的训练',participantId:'SYNTHETIC_TEST',reads:{async read(call){return receipt(call);}}});
  assert.equal(found.status,'found');
  assert.match(found.text,/名称：SYNTHETIC_STORED_MARKER/);
  assert.doesNotMatch(found.text,/"id"|"notes"|\\n/);
});

test('operation planning performs proper local reads but blocks external record disclosure and writes', async () => {
  const {model,calls}=queuedModel([{version:1,calls:[{name:'rehab.get_training_plan',arguments:{},reason:'需要版本'},
    {name:'rehab.get_schedule',arguments:{},reason:'需要安排'}],uncertainties:[]}]);
  const reads: RehabCall[]=[];const operations:string[]=[];
  const result=await previewRehabProgramOperation({model,semantic,userText:'SYNTHETIC TEST 把训练改到明天晚上八点',
    reads:{async read(call){reads.push(call);return receipt(call);}},operations:{async call(name){operations.push(name);return {records:[{name:'SYNTHETIC_PRIVATE_SCHEDULE'}]};}}});
  assert.deepEqual(reads,[{name:'rehab.get_training_plan',arguments:{}}]);
  assert.deepEqual(operations,['rehab.get_schedule']);
  assert.equal(calls.length,1);
  assert.doesNotMatch(JSON.stringify(calls),/SYNTHETIC_STORED_MARKER|SYNTHETIC_PRIVATE_NOTES|SYNTHETIC_PRIVATE_SCHEDULE/);
  assert.deepEqual(result.plan?.operations,[]);
  assert.deepEqual(result.previews,[]);
  assert.match(renderOperationPreview(result.plan,result.previews),/尚未执行|未授权/);
});
