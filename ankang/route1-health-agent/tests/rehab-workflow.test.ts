import test from 'node:test';
import assert from 'node:assert/strict';
import { catalogue } from '../src/rehab/catalogue';
import { parseRehabToolSelection, validateRehabPlan, type RehabCandidatePlan } from '../src/rehab/workflow';

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
