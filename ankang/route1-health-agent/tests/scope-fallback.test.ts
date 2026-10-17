import test from 'node:test';
import assert from 'node:assert/strict';
import { resolveScopeFallback } from '../src/runtime/scopeFallback';
import type { SemanticTurn } from '../src/runtime/semanticRouter';

function semantic(route: SemanticTurn['route'], goal = '处理当前请求'): SemanticTurn {
  return {
    version: 1, route, goal, mentions: [], events: [], relations: [], uncertain: [],
    suggested_tool: null, intents: [], tool_requests: [],
  };
}

test('explicit diagnosis and treatment decisions request clinician review across health routes', () => {
  for (const route of ['other', 'health', 'rehab'] as const) {
    const result = resolveScopeFallback(semantic(route), '请帮我诊断一下并决定治疗方案');
    assert.equal(result?.kind, 'clinical_handoff', route);
    assert.match(result?.reply ?? '', /不能替医生诊断|需要医生/);
    assert.doesNotMatch(result?.reply ?? '', /已经联系|已预约/);
  }
});

test('out-of-scope appointment requests do not pretend to execute', () => {
  const result = resolveScopeFallback(semantic('other'), '帮我预约医生');
  assert.equal(result?.kind, 'unsupported_operation');
  assert.match(result?.reply ?? '', /还没有执行/);
});

test('unrelated requests receive a bounded scope explanation, not a false doctor referral', () => {
  const result = resolveScopeFallback(semantic('other'), '帮我写一个股票交易机器人');
  assert.equal(result?.kind, 'out_of_scope');
  assert.match(result?.reply ?? '', /超出安康康复助手当前的功能范围/);
  assert.doesNotMatch(result?.reply ?? '', /必须马上就医/);
});

test('in-scope routes and ordinary symptoms remain with their existing handlers', () => {
  assert.equal(resolveScopeFallback(semantic('chat'), '陪我聊聊'), null);
  assert.equal(resolveScopeFallback(semantic('health'), '我今天有点头晕'), null);
  assert.equal(resolveScopeFallback(semantic('rehab'), '我膝盖训练后酸'), null);
});

test('negated clinical and external-operation mentions do not trigger handoff or operation refusal', () => {
  assert.equal(resolveScopeFallback(semantic('health'), '我不需要你诊断，只想知道诊断这个词是什么意思'), null);
  assert.equal(resolveScopeFallback(semantic('other'), '不要帮我预约医生')?.kind, 'out_of_scope');
});

test('disease-specific plan generation is not routed to generic activity-plan adoption', () => {
  const request = '我有腰椎间盘突出，帮我制定一套在家的训练计划';
  for (const route of ['rehab','health','other'] as const) {
    const turn = {
      ...semantic(route,'制定腰椎间盘突出居家训练计划'),
      intents:[{type:'plan_generation' as const,route:'rehab' as const,goal:'制定居家训练计划',evidence:request}],
      mentions:[{kind:'other' as const,text:'腰椎间盘突出',evidence:request}],
    };
    const result = resolveScopeFallback(turn,request);
    assert.equal(result?.kind,'clinical_handoff',route);
    assert.match(result?.reply ?? '',/不能据此生成腰椎间盘突出|专业人员/);
  }
});
