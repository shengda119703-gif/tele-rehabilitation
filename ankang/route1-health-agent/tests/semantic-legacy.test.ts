import test from 'node:test';
import assert from 'node:assert/strict';
import { ruleBasedAdapter } from '../src/engine/agent';
import { runDetection } from '../src/engine/detect';
import { understandElderInput } from '../src/engine/understanding';
import type { ElderTurnRequest } from '../src/engine/elderTurn';
import type { SemanticMention, SemanticTurn } from '../src/runtime/semanticRouter';
import { adaptSemanticUnderstanding } from '../src/runtime/semanticLegacyAdapter';
import { prepareTurn } from '../src/runtime/turn';
import { readOnlyPlan } from '../src/runtime/semanticExecution';
import { rehabAnswer } from '../src/rehab/assistant';

const today = '2026-10-15';
function request(text: string): Omit<ElderTurnRequest, 'understanding'> {
  return { text, priorChat: [], findings: [], events: [], familySharing: 'denied', agentContext: undefined,
    sharingAudit: [], llmAdapter: ruleBasedAdapter, today, now: '10-15 12:00',
    receivedAt: today + 'T12:00:00', sourceMessageId: 'SYNTHETIC:semantic:1', idSeed: 100 };
}
function semantic(mentions: SemanticMention[]): SemanticTurn {
  return { version: 1, route: 'health', goal: '理解症状', mentions, events: [], relations: [], uncertain: [], suggested_tool: null };
}
const symptom = (text: string, evidence: string, status: SemanticMention['status'], subject: SemanticMention['subject'] = 'self'): SemanticMention =>
  ({ kind: 'symptom', text, evidence, status, subject });

test('semantic legacy: validated improvement polarity no longer becomes an occurred event', async () => {
  const text = '今天没那么喘了，比昨天好多了';
  const baseline = await prepareTurn(request(text));
  assert.equal(baseline.understanding.claims[0].status, 'occurred');
  assert.equal(baseline.plan.eventsToAppend.length, 1);
  const result = await prepareTurn(request(text), null, semantic([symptom('喘', '今天没那么喘了', 'negated')]));
  assert.equal(result.understanding.claims[0].status, 'negated');
  assert.equal(result.plan.eventsToAppend.length, 0);
  assert.doesNotMatch(result.plan.replyText, /我已经记下/);
  assert.deepEqual(result.understanding.claims[0].tags, baseline.understanding.claims[0].tags);
  assert.equal(result.understanding.claims[0].subject, baseline.understanding.claims[0].subject);
  assert.equal(result.understanding.claims[0].eventDate, baseline.understanding.claims[0].eventDate);
});

test('semantic legacy: full evidence restores the original double-negation merge', async () => {
  const text = '我不是没有喘';
  const result = await prepareTurn(request(text), null, semantic([symptom('喘', text, 'occurred')]));
  assert.equal(result.understanding.claims[0].status, 'occurred');
  assert.equal(result.plan.eventsToAppend.length, 1);
});

test('semantic legacy: separate symptoms preserve negation, hypothesis and uncertainty', async () => {
  const text = '我今天没有头晕，如果我明天胸闷怎么办，我可能有点喘';
  const result = await prepareTurn(request(text), null, semantic([
    symptom('头晕', '我今天没有头晕', 'negated'),
    symptom('胸闷', '如果我明天胸闷怎么办', 'hypothetical'),
    symptom('喘', '我可能有点喘', 'uncertain'),
  ]));
  assert.deepEqual(result.understanding.claims.map(claim => claim.status), ['negated', 'hypothetical', 'uncertain']);
  assert.equal(result.plan.eventsToAppend.length, 0);
});

test('semantic legacy: strong rule signals cannot be promoted to occurred by a model', async () => {
  for (const text of ['如果我头晕怎么办', '我可能有点喘', '我差点摔倒']) {
    const original = understandElderInput(text, today);
    const word = text.includes('头晕') ? '头晕' : text.includes('喘') ? '喘' : '摔倒';
    const result = await prepareTurn(request(text), null, semantic([symptom(word, text, 'occurred')]));
    assert.equal(result.understanding.claims[0].status, original.claims[0].status, text);
    assert.equal(result.plan.eventsToAppend.length, 0, text);
  }
});

test('semantic legacy: family ownership and the original date remain local-rule decisions', async () => {
  const text = '爸爸昨天腿疼';
  const original = await prepareTurn(request(text));
  const result = await prepareTurn(request(text), null, semantic([symptom('腿疼', text, 'occurred', 'father')]));
  assert.equal(result.plan.eventsToAppend.length, 0);
  assert.equal(result.plan.familyEventsToAppend.length, 1);
  assert.equal(result.understanding.claims[0].subject, 'father');
  assert.equal(result.understanding.claims[0].eventDate, '2026-10-14');
  assert.deepEqual(result.plan.familyEventsToAppend, original.plan.familyEventsToAppend);
});

test('semantic legacy: model ownership conflict cannot write to either person', async () => {
  const text = '爸爸昨天腿疼';
  const result = await prepareTurn(request(text), null, semantic([symptom('腿疼', text, 'occurred', 'self')]));
  assert.equal(result.understanding.claims[0].subject, 'father');
  assert.equal(result.plan.eventsToAppend.length, 0);
  assert.equal(result.plan.familyEventsToAppend.length, 0);
  assert.equal(result.plan.sharingAuditEntries.length, 0);
  assert.equal(result.plan.correction, null);
  assert.match(result.plan.replyText, /先不新增或更改健康记录/);
});

test('semantic legacy: mixed or incomplete clause evidence is clarified without factual writes', async () => {
  const text = '我喘而且没劲';
  for (const mentions of [
    [symptom('喘', text, 'occurred'), symptom('没劲', text, 'negated')],
    [symptom('喘', '喘', 'negated')],
    [symptom('喘', text, 'negated')],
  ]) {
    const result = await prepareTurn(request(text), null, semantic(mentions));
    assert.deepEqual(result.understanding.claims[0].tags, understandElderInput(text, today).claims[0].tags);
    assert.equal(result.plan.eventsToAppend.length, 0);
    assert.equal(result.plan.familyEventsToAppend.length, 0);
    assert.match(result.plan.replyText, /先不新增或更改健康记录/);
  }
});

test('semantic legacy: uncertain or hypothetical disagreement outside old merge is not persisted as occurred', async () => {
  const text = '我有点喘';
  for (const status of ['uncertain', 'hypothetical'] as const) {
    const result = await prepareTurn(request(text), null, semantic([symptom('喘', text, status)]));
    assert.equal(result.plan.eventsToAppend.length, 0);
    assert.match(result.plan.replyText, /先不新增或更改健康记录/);
  }
});

test('semantic legacy: urgent rule evidence survives a model negation including future detection', async () => {
  const text = '我胸口痛，喘不过气';
  const baseline = await prepareTurn(request(text));
  assert.ok(runDetection(baseline.plan.eventsToAppend, today).some(finding => finding.severity === 'urgent'));
  const result = await prepareTurn(request(text), null, semantic([
    symptom('胸口痛', '我胸口痛', 'negated'), symptom('喘不过气', '喘不过气', 'negated'),
  ]));
  assert.equal(result.plan.safetyAction, true);
  assert.deepEqual(result.understanding, baseline.understanding);
  assert.deepEqual(result.plan.eventsToAppend, baseline.plan.eventsToAppend);
  assert.match(result.plan.replyText, /急救/);
});

test('semantic legacy: ambiguous nonurgent safety wording is retained without a false save receipt', async () => {
  const text = '我头晕而且喘';
  const result = await prepareTurn(request(text), null, semantic([
    symptom('头晕', text, 'negated'), symptom('喘', text, 'occurred'),
  ]));
  assert.equal(result.plan.safetyAction, true);
  assert.equal(result.plan.eventsToAppend.length, 0);
  assert.match(result.plan.replyText, /先坐稳/);
  assert.match(result.plan.replyText, /先不新增或更改健康记录/);
  assert.doesNotMatch(result.plan.replyText, /我已经记下/);
});

test('semantic legacy: old v1 without status and cross-turn mentions do not alter current clinical understanding', () => {
  const text = '今天没那么喘了';
  const baseline = understandElderInput(text, today);
  for (const mentions of [
    [{ kind: 'symptom' as const, text: '喘' }],
    [{ ...symptom('喘', text, 'negated'), source_message_id: 'past-user-turn' }],
  ]) {
    const result = adaptSemanticUnderstanding(text, today, [], semantic(mentions));
    assert.deepEqual(result.understanding, baseline);
    assert.equal(result.needsClarification, false);
  }
});

test('semantic legacy: flag-off path is unchanged and semantic path never invokes a second LLM', async () => {
  const text = '我有点喘';
  const baseline = await prepareTurn(request(text));
  assert.deepEqual(await prepareTurn(request(text), null, null), baseline);
  let calls = 0;
  await prepareTurn({ ...request(text), llmAdapter: { complete: async () => { calls++; return { text: 'must not call', tags: [] }; } } },
    { baseUrl: 'https://must-not-call.invalid', apiKey: 'SYNTHETIC', model: 'test', timeoutMs: 1 },
    semantic([symptom('喘', text, 'occurred')]));
  assert.equal(calls, 0);
});

test('semantic legacy: read-only family wording does not promise discarded sharing or recording', async () => {
  const planned = await prepareTurn({ ...request('爸爸今天腿疼'), familySharing: 'granted',
    findings: [{ id: 'existing-urgent', date: today, severity: 'urgent', title: 'existing', detail: 'existing', evidence: [] }] });
  assert.match(planned.plan.replyText, /家属可以看到/);
  const result = readOnlyPlan(planned.plan);
  assert.equal(result.safetyAction, true);
  assert.match(result.replyText, /爸爸/);
  assert.match(result.replyText, /不会新增或共享健康记录/);
  assert.doesNotMatch(result.replyText, /家属可以看到|这次会分享/);
  assert.deepEqual(result.familyEventsToAppend, []);
  assert.deepEqual(result.shareFamilyEventIds, []);
  assert.deepEqual(result.sharingAuditEntries, []);
});

test('semantic legacy: read-only correction wording does not promise an unapplied revocation', async () => {
  const planned = await prepareTurn({ ...request('刚才说错了，没有喘'),
    priorChat: [{ id: 'SYNTHETIC:prior', role: 'elder', text: '我有点喘', time: '12:00' }] });
  assert.ok(planned.plan.correction);
  assert.match(planned.plan.replyText, /只会撤销/);
  const result = readOnlyPlan(planned.plan);
  assert.equal(result.correction, null);
  assert.match(result.replyText, /不会撤销或修改已有健康记录/);
  assert.doesNotMatch(result.replyText, /只会撤销|已按您刚才的更正/);
});

test('semantic legacy: record fallback renders actual local fields without raw JSON or a model call', async () => {
  let reads = 0, modelCalls = 0;
  const result = await rehabAnswer('查看我的训练记录', false, 'SYNTHETIC', {
    reply: async () => { modelCalls++; return 'must not transmit records'; },
  }, { read: async ({ name }) => {
    reads++;
    return { tool: name, read_only: true, status: 'found',
      scope: { participant_id: 'SYNTHETIC', source_kind: 'SYNTHETIC', usage_context: 'TEST' },
      records: [{ id: 'test-record', exercise_id: 'shoulder_abduction', exercise_label: '肩外展',
        settings: { INTERNAL_NOT_FOR_CHAT: 'secret' }, summary: { completed: 3 } }] };
  } });
  assert.equal(reads, 1);
  assert.equal(modelCalls, 0);
  assert.match(result.text, /test-record|肩外展/);
  assert.match(result.text, /完成次数：3/);
  assert.doesNotMatch(result.text, /exercise_id|settings|INTERNAL_NOT_FOR_CHAT|[{}]/);
});
