import test from 'node:test';
import assert from 'node:assert/strict';
import {
  parseRehabProgramPlan,
  isConfirmation,
  isCancellation,
  isRehabProgramIntent,
} from '../src/rehab/programOperations';

test('program operation proposal requires explicit confirmation and one operation', () => {
  const valid = parseRehabProgramPlan(JSON.stringify({
    version: 1,
    operations: [{
      name: 'rehab.plan.change',
      arguments: {
        plan_id: '0123456789abcdef0123456789abcdef',
        expected_revision: 2,
        patch: { remove: ['sit_to_stand:left'] },
      },
      evidence: '把左侧坐站删掉',
    }],
    requires_confirmation: true,
    summary: '删除左侧坐站训练',
    uncertainties: [],
  }));
  assert.ok(valid);

  const two = parseRehabProgramPlan(JSON.stringify({
    version: 1,
    operations: [
      {name:'rehab.plan.change',arguments:{plan_id:'0123456789abcdef0123456789abcdef',expected_revision:2,patch:{remove:['sit_to_stand:left']}},evidence:'删除'},
      {name:'rehab.schedule.remove',arguments:{id:'schedule-1'},evidence:'删安排'},
    ],
    requires_confirmation: true,
    summary: '两项修改',
    uncertainties: [],
  }));
  assert.equal(two, null);
});

test('confirmation phrases are narrow and do not match new instructions', () => {
  assert.equal(isConfirmation('确认'), true);
  assert.equal(isConfirmation('好的'), true);
  assert.equal(isConfirmation('确认后把时间改到8点'), false);
  assert.equal(isCancellation('取消'), true);
  assert.equal(isCancellation('先不要'), true);
});

test('rehab program intent is derived from semantic intent, not raw user keyword routing', () => {
  assert.equal(isRehabProgramIntent({
    version:1, route:'rehab', goal:'调整训练',
    mentions:[], events:[], relations:[], uncertain:[],
    suggested_tool:null, intents:[{
      type:'program_operation', route:'rehab', goal:'调整训练', evidence:'把计划改一下'
    }],
  }), true);
  assert.equal(isRehabProgramIntent({
    version:1, route:'chat', goal:'聊天',
    mentions:[], events:[], relations:[], uncertain:[],
    suggested_tool:null, intents:[],
  }), false);
});
