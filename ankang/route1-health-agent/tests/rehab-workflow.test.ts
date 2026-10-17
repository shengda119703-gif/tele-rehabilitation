import test from 'node:test';
import assert from 'node:assert/strict';
import { catalogue } from '../src/rehab/catalogue';
import { mapKnowledgeActionToApp } from '../src/rehab/exerciseMapping';
import { parseRehabToolSelection, selectRehabTools, validateRehabPlan, rehabAnswerTask, runRehabReadOnlyAnswer, type RehabCandidatePlan } from '../src/rehab/workflow';

test('rehab tool selection accepts only registered tools', () => {
  const ok = parseRehabToolSelection(JSON.stringify({
    version: 1,
    calls: [
      { name: 'rehab.get_training_plan', arguments: {}, reason: '需要当前计划' },
      { name: 'rehab.search_knowledge', arguments: { query: '膝关节训练' }, reason: '需要动作库' },
      { name: 'rehab.search_guidance', arguments: { query: '剂量和进阶' }, reason: '需要训练原则' }
    ],
    uncertainties: []
  }));
  assert.equal(ok?.calls.length, 3);

  const bad = parseRehabToolSelection(JSON.stringify({
    version: 1,
    calls: [{ name: 'rehab.delete_plan', arguments: {}, reason: '不允许' }],
    uncertainties: []
  }));
  assert.equal(bad, null);
});

test('rehab candidate rejects an action that is not a real training card', () => {
  const candidate: RehabCandidatePlan = {
    version: 1,
    goal: '膝部训练',
    summary: '候选方案',
    algorithm_input: {
      goal: '膝部训练',
      region: '膝',
      equipment: ['无轮稳固椅'],
      restrictions: [],
      level: 0,
      screening_confirmed: false,
    },
    candidate_actions: [{ exercise_id: 'T-NOT-999', reason: '模型自造动作' }],
    doctor_review_required: false,
    doctor_review_reasons: [],
    uncertainties: [],
  };
  const result = validateRehabPlan(candidate, catalogue);
  assert.equal(result.status, 'rejected');
});

test('rehab candidate remains reviewable before screening confirmation', () => {
  const card = catalogue.find(c => c.kind === 'training' && c.complete);
  assert.ok(card);
  const candidate: RehabCandidatePlan = {
    version: 1,
    goal: '康复训练',
    summary: '候选方案',
    algorithm_input: {
      goal: '康复训练',
      region: card.region,
      equipment: [card.equipment],
      restrictions: [],
      level: 0,
      screening_confirmed: false,
    },
    candidate_actions: [{ exercise_id: card.id, reason: '动作库中存在' }],
    doctor_review_required: false,
    doctor_review_reasons: [],
    uncertainties: [],
  };
  const result = validateRehabPlan(candidate, catalogue);
  assert.equal(result.status, 'needs_review');
  assert.ok(result.reasons.includes('screening_not_confirmed'));
});

test('exercise guidance returns registered references without generating a plan', async () => {
  const semantic = {version:1 as const,route:'rehab' as const,goal:'肩外旋怎么做',
    mentions:[],events:[],relations:[],uncertain:[],suggested_tool:null,
    intents:[{type:'exercise_guidance' as const,route:'rehab' as const,goal:'肩外旋怎么做',evidence:'肩外旋怎么做'}]};
  assert.equal(rehabAnswerTask(semantic),'exercise_guidance');
  const answer = await runRehabReadOnlyAnswer({semantic,userText:'肩外旋怎么做',participantId:'TEST'});
  assert.equal(answer.status,'found');
  assert.ok(answer.source_ids.length>0);
  assert.match(answer.text,/开始条件|停止条件/);
});

test('plan generation is distinct from ordinary rehab questions', () => {
  const semantic = {version:1 as const,route:'rehab' as const,goal:'生成计划',
    mentions:[],events:[],relations:[],uncertain:[],suggested_tool:null,
    intents:[{type:'plan_generation' as const,route:'rehab' as const,goal:'生成计划',evidence:'生成计划'}]};
  assert.equal(rehabAnswerTask(semantic),'plan_generation');
});

test('real-model tool selection may omit a search query; host fills it from the user request', () => {
  const parsed = parseRehabToolSelection(JSON.stringify({
    version: 1,
    calls: [
      {name:'rehab.search_guidance',arguments:{},reason:'需要相关训练原则'},
      {name:'rehab.search_knowledge',arguments:{query:''},reason:'查找动作卡'},
    ],
    uncertainties: [],
  }), '腰椎间盘突出 居家训练计划');
  assert.equal(parsed?.calls.length,2);
  assert.equal(parsed?.calls[0].arguments.query,'腰椎间盘突出 居家训练计划');
  assert.equal(parsed?.calls[1].arguments.query,'腰椎间盘突出 居家训练计划');
});

test('missing search query without any grounded fallback is rejected', () => {
  const parsed = parseRehabToolSelection(JSON.stringify({
    version:1,
    calls:[{name:'rehab.search_guidance',arguments:{},reason:'查资料'}],
    uncertainties:[],
  }));
  assert.equal(parsed,null);
});

test('tool planner integration fills an omitted query before host execution', async () => {
  const semantic = {
    version:1 as const, route:'rehab' as const, goal:'制定腰椎居家训练计划',
    mentions:[{kind:'body_region' as const,text:'腰椎',evidence:'腰椎'}],
    events:[], relations:[], uncertain:[], suggested_tool:null,
    intents:[{type:'plan_generation' as const,route:'rehab' as const,goal:'制定居家训练计划',evidence:'制定一套在家的训练计划'}],
  };
  const model = {reply:async()=>JSON.stringify({
    version:1,
    calls:[{name:'rehab.search_guidance',arguments:{},reason:'需要训练原则'}],
    uncertainties:['缺少个人筛查信息'],
  })};
  const selected = await selectRehabTools(model,semantic,'我有腰椎间盘突出，帮我制定一套在家的训练计划。');
  assert.equal(selected?.calls[0].name,'rehab.search_guidance');
  assert.match(selected?.calls[0].arguments.query ?? '',/腰椎|训练计划/);
});

test('only explicitly reviewed knowledge cards map to executable app movements', () => {
  assert.equal(mapKnowledgeActionToApp('T-LOW-003')?.app_exercise_id,'knee_extension');
  assert.equal(mapKnowledgeActionToApp('T-LOW-017')?.app_exercise_id,'sit_to_stand');
  assert.equal(mapKnowledgeActionToApp('T-LOW-002'),null);
  assert.equal(mapKnowledgeActionToApp('T-AXU-022'),null);
  assert.equal(mapKnowledgeActionToApp('T-LOW-046'),null);
});
