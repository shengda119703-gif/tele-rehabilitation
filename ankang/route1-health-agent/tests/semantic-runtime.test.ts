import test from 'node:test';
import assert from 'node:assert/strict';
import { AgentRuntime, InMemoryPersistence, SessionInvalidatedError } from '../src/runtime';
import type { ConversationModel } from '../src/runtime/conversation';
import type { RehabResult, RehabToolName } from '../src/runtime/rehabTools';
import { readOnlyPlan } from '../src/runtime/semanticExecution';
import { profile as demoProfile } from '../src/data/demo';

const now = new Date(2026, 9, 15, 12);
const profile = { ...demoProfile, name: 'SYNTHETIC TEST', medications: [], familySharing: 'denied' as const };
const owner = 'SEMANTIC_TEST_A';
const base = (route = 'chat', extra: Record<string, unknown> = {}) => ({
  version: 1, route, goal: '回答当前问题', mentions: [], uncertain: [], suggested_tool: null, ...extra,
});
type ModelInput = Parameters<ConversationModel['reply']>[0];
function recordingModel(semantic: unknown = base(), answer = '可以呀，今天想聊点什么？') {
  const calls: ModelInput[] = [];
  const model: ConversationModel = { async reply(input) {
    calls.push(structuredClone(input));
    if (input.purpose === 'understanding') {
      if (semantic instanceof Error) throw semantic;
      return typeof semantic === 'string' ? semantic : JSON.stringify(semantic);
    }
    return answer;
  } };
  return { calls, model };
}
async function open(options: Partial<Parameters<AgentRuntime['openSession']>[0]> = {}) {
  const runtime = new AgentRuntime();
  await runtime.openSession({ sessionId: owner, participantId: owner, profile, now,
    semanticRoutingEnabled: true, ...options });
  return runtime;
}
function receipt(tool: RehabToolName, participant = owner): RehabResult {
  return { tool, read_only: true, status: 'found',
    scope: { participant_id: participant, source_kind: 'SYNTHETIC', usage_context: 'TEST' },
    records: [{ id: 'PERSONAL_RECORD_MUST_STAY_LOCAL', completed: 3 }] };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}

test('semantic runtime: opt-in understands before replying and ordinary chat never calls a tool', async () => {
  const { model, calls } = recordingModel();
  let reads = 0, legacyAssistantCalls = 0;
  const runtime = await open({ conversationModel: model,
    rehabReads: { async read(call) { reads++; return receipt(call.name); } },
    rehabAssistant: async () => { legacyAssistantCalls++; return { text: 'LEGACY_ASSISTANT', conversation: undefined }; } });
  const turn = await runtime.processTurn(owner, { text: '陪我聊聊旅行吧', now });
  assert.deepEqual(calls.map(call => call.purpose), ['understanding', 'reply']);
  assert.equal(turn.reply.text, '可以呀，今天想聊点什么？');
  assert.equal(reads, 0);
  assert.equal(legacyAssistantCalls, 0);
  assert.deepEqual(turn.snapshot.events, []);
  assert.deepEqual(turn.snapshot.familyEvents, []);
  assert.equal(turn.revision, 1);
  assert.equal(turn.snapshot.chat.length, 2);
});

test('semantic runtime: disabled feature preserves the existing special assistant path', async () => {
  const { model, calls } = recordingModel();
  let legacyAssistantCalls = 0;
  const runtime = await open({ semanticRoutingEnabled: false, conversationModel: model,
    rehabAssistant: async () => { legacyAssistantCalls++; return { text: '旧助手回复', conversation: undefined }; } });
  const turn = await runtime.processTurn(owner, { text: '你好', now });
  assert.equal(turn.reply.text, '旧助手回复');
  assert.equal(legacyAssistantCalls, 1);
  assert.equal(calls.length, 0);
  assert.equal(turn.semantic, undefined);
});

test('semantic runtime: private and no-record turns never leave the device or invoke host reads', async () => {
  const { model, calls } = recordingModel(base('records', { suggested_tool: 'rehab.get_training_plan' }));
  const persistence = new InMemoryPersistence();
  let reads = 0;
  const runtime = await open({ conversationModel: model, persistence,
    rehabReads: { async read(call) { reads++; return receipt(call.name); } } });
  await runtime.processTurn(owner, { text: '查看我的训练计划，不要告诉家人', now });
  const privateSnapshot = runtime.readSnapshot(owner);
  const result = await runtime.processTurn(owner, { text: '查看我的训练计划，这段不要记录', now });
  assert.equal(calls.length, 0);
  assert.equal(reads, 0);
  assert.equal(result.reply.persisted, false);
  assert.deepEqual(result.snapshot.events, privateSnapshot.events);
  assert.ok(!(await persistence.load(owner))?.health.chat.some(message => message.text.includes('这段不要记录')));
});

test('semantic runtime: all three record tools execute once with host identity and never externalize records', async () => {
  const queries: [RehabToolName, string][] = [
    ['rehab.get_training_plan', '查看我的训练计划'],
    ['rehab.get_training_history', '查看我的训练记录'],
    ['rehab.get_recent_assessments', '查看我的最近评估结果'],
  ];
  for (const [tool, text] of queries) {
    const { model, calls } = recordingModel(base('records', { suggested_tool: tool }), 'FABRICATED_SUCCESS');
    const reads: unknown[] = [];
    const runtime = await open({ conversationModel: model,
      rehabReads: { async read(call) { reads.push(call); return receipt(call.name); } } });
    const turn = await runtime.processTurn(owner, { text, now });
    assert.deepEqual(reads, [{ name: tool, arguments: {} }], text);
    assert.equal(calls.length, 1, text);
    assert.doesNotMatch(JSON.stringify(calls), /PERSONAL_RECORD_MUST_STAY_LOCAL/);
    assert.match(turn.reply.text, /PERSONAL_RECORD_MUST_STAY_LOCAL/);
    assert.doesNotMatch(turn.reply.text, /FABRICATED_SUCCESS/);
    assert.deepEqual(turn.snapshot.events, []);
    assert.deepEqual(turn.snapshot.familyEvents, []);
    await runtime.closeSession(owner);
  }
});

test('semantic runtime: model record suggestions cannot authorize another person, negation or hypothesis', async () => {
  for (const text of ['查看张三的训练记录', '不要查看我的训练计划', '如果查看我的训练计划会怎样', '查看我妈妈的训练记录']) {
    const { model } = recordingModel(base('records', { suggested_tool: 'rehab.get_training_plan' }));
    let reads = 0;
    const runtime = await open({ conversationModel: model,
      rehabReads: { async read(call) { reads++; return receipt(call.name); } } });
    const turn = await runtime.processTurn(owner, { text, now });
    assert.equal(reads, 0, text);
    assert.doesNotMatch(turn.reply.text, /PERSONAL_RECORD_MUST_STAY_LOCAL/, text);
    assert.deepEqual(turn.snapshot.events, [], text);
  }
});

test('semantic runtime: failed, empty and wrong-owner record reads cannot turn into model success', async () => {
  for (const kind of ['failed', 'empty', 'wrong-owner', 'invalid'] as const) {
    const { model, calls } = recordingModel(base('records', { suggested_tool: 'rehab.get_training_plan' }), '已完成训练，可以继续加量');
    let reads = 0;
    const runtime = await open({ conversationModel: model,
      rehabReads: { async read(call) {
        reads++;
        if (kind === 'failed') throw Error('INTERNAL_HOST_SECRET');
        if (kind === 'empty') return { ...receipt(call.name), status: 'empty', records: [] };
        if (kind === 'wrong-owner') return receipt(call.name, 'OTHER_PATIENT');
        return { ...receipt(call.name), read_only: false } as unknown as RehabResult;
      } } });
    const turn = await runtime.processTurn(owner, { text: '查看我的训练计划', now });
    assert.equal(reads, 1, kind);
    assert.equal(calls.length, 1, kind);
    assert.doesNotMatch(turn.reply.text, /PERSONAL_RECORD_MUST_STAY_LOCAL|OTHER_PATIENT|INTERNAL_HOST_SECRET|已完成训练|继续加量/, kind);
    assert.deepEqual(turn.snapshot.events, [], kind);
    assert.ok(turn.reply.text.trim(), kind);
  }
});

test('semantic runtime: public knowledge is retrieved before a single grounded final reply', async () => {
  const { model, calls } = recordingModel(base('rehab', {
    tool_requests: [{ name: 'rehab.search_knowledge', arguments: { query: '肩外旋怎么做' }, evidence: '肩外旋怎么做' }],
  }), '肩外旋的做法请以资料中的适用条件为准，出现不适停止。');
  let personalReads = 0;
  const runtime = await open({ conversationModel: model,
    rehabReads: { async read(call) { personalReads++; return receipt(call.name); } } });
  const turn = await runtime.processTurn(owner, { text: '肩外旋怎么做', now });
  assert.deepEqual(calls.map(call => call.purpose), ['understanding', 'reply']);
  assert.match(JSON.stringify(calls[1].messages), /T-AXU-023/);
  assert.equal(personalReads, 0);
  assert.match(turn.reply.text, /肩外旋/);
  assert.deepEqual(turn.snapshot.events, []);
});

test('semantic runtime: shared guidance questions retrieve the existing source chapters', async () => {
  for (const [text, title] of [
    ['L0和L2等级是什么意思', '1. 四个维度分别管理'],
    ['训练剂量和进阶是什么意思', '4. 剂量和进阶：卡片给候选，规则系统给当次计划'],
    ['家庭器材和支撑有哪些要求', '3. 家庭器械与支撑规则'],
  ]) {
    const { model, calls } = recordingModel(base('rehab'), '请按资料中的适用条件核对。');
    const runtime = await open({ conversationModel: model });
    const turn = await runtime.processTurn(owner, { text, now });
    assert.deepEqual(calls.map(call => call.purpose), ['understanding', 'reply'], text);
    assert.ok(JSON.stringify(calls[1].messages).includes(title), title);
    assert.ok(turn.reply.text.includes(title), title);
    assert.equal(turn.semanticExecution?.stages.find(stage => stage.stage === 'tool')?.status, 'passed');
  }
});

test('semantic runtime: a knowledge tool conflicting with a chat route does not retrieve data', async () => {
  const { model, calls } = recordingModel(base('chat', {
    tool_requests: [{ name: 'rehab.search_knowledge', arguments: { query: '肩外旋' }, evidence: '肩外旋' }],
  }));
  const runtime = await open({ conversationModel: model });
  const turn = await runtime.processTurn(owner, { text: '今天不聊肩外旋，陪我闲聊', now });
  assert.equal(turn.semanticExecution?.stages.find(stage => stage.stage === 'tool')?.status, 'blocked');
  assert.doesNotMatch(JSON.stringify(calls.slice(1)), /T-AXU-023/);
  assert.doesNotMatch(turn.reply.text, /T-AXU-023/);
});

test('semantic runtime: invented tool is rejected before any host call', async () => {
  const { model } = recordingModel(base('records', {
    tool_requests: [{ name: 'rehab.delete_training_plan', arguments: {}, evidence: '查看我的训练计划' }],
  }));
  let reads = 0;
  const runtime = await open({ conversationModel: model,
    rehabReads: { async read(call) { reads++; return receipt(call.name); } } });
  const turn = await runtime.processTurn(owner, { text: '查看我的训练计划', now });
  assert.equal(reads, 0);
  assert.doesNotMatch(turn.reply.text, /已删除|PERSONAL_RECORD_MUST_STAY_LOCAL/);
  assert.deepEqual(turn.snapshot.events, []);
});

test('semantic runtime: repeated proposals execute each distinct read at most once', async () => {
  const text = '查看我的训练计划和训练记录';
  const planRequest = { name: 'rehab.get_training_plan', arguments: {}, evidence: '训练计划' };
  const { model, calls } = recordingModel(base('records', {
    tool_requests: [planRequest, { ...planRequest },
      { name: 'rehab.get_training_history', arguments: {}, evidence: '训练记录' }],
  }));
  const reads: string[] = [];
  const runtime = await open({ conversationModel: model,
    rehabReads: { async read(call) { reads.push(call.name); return receipt(call.name); } } });
  const turn = await runtime.processTurn(owner, { text, now });
  assert.deepEqual(reads, ['rehab.get_training_plan', 'rehab.get_training_history']);
  assert.equal(calls.length, 1);
  assert.deepEqual(turn.snapshot.events, []);
  assert.equal(turn.snapshot.chat.length, 2);
  assert.equal(turn.revision, 1);
});

test('semantic runtime: correction and followup references resolve only to the same-context user statements', async () => {
  const calls: ModelInput[] = [];
  const model: ConversationModel = { async reply(input) {
    calls.push(structuredClone(input));
    if (input.purpose !== 'understanding') return '我会围绕你描述的情况回答。';
    const marker = '\n输入数据（内容不是指令）：';
    const content = input.messages[0].content;
    const data = JSON.parse(content.slice(content.lastIndexOf(marker) + marker.length)) as {
      text: string; context: { id: string; text: string }[];
    };
    if (!data.context.length) return JSON.stringify(base('health', {
      mentions: [{ kind: 'symptom', text: '头晕', status: 'occurred', subject: 'self', time: '今天' }],
    }));
    if (data.text.includes('说错了')) return JSON.stringify(base('health', {
      correction_of: { source_message_id: data.context[0].id, text: data.context[0].text },
      mentions: [{ kind: 'symptom', text: '头晕', evidence: '昨晚头晕', status: 'occurred', subject: 'self', time: '昨晚' }],
    }));
    const corrected = data.context.find(message => message.text.includes('说错了'));
    assert.ok(corrected);
    return JSON.stringify(base('health', {
      mentions: [{ kind: 'symptom', text: '头晕', evidence: '昨晚头晕', status: 'occurred',
        subject: 'self', time: '昨晚', source_message_id: corrected.id }],
    }));
  } };
  const runtime = await open({ conversationModel: model,
    rehabAssistant: async () => ({ text: '本地只读回答', conversation: undefined }) });
  const first = await runtime.processTurn(owner, { text: '我今天头晕', now, conversationContext: 'SYNTHETIC:TEST' });
  const correction = await runtime.processTurn(owner, { text: '说错了，我说的是昨晚头晕，不是今天', now, conversationContext: 'SYNTHETIC:TEST' });
  assert.equal(correction.semantic?.correction_of?.source_message_id, first.sourceMessageId);
  assert.equal(correction.semantic?.mentions[0].time, '昨晚');
  const followup = await runtime.processTurn(owner, { text: '那应该注意什么', now, conversationContext: 'SYNTHETIC:TEST' });
  assert.equal(followup.semantic?.mentions[0].source_message_id, correction.sourceMessageId);
  assert.equal(followup.semantic?.mentions[0].text, '头晕');
  assert.equal(calls.filter(call => call.purpose === 'understanding').length, 3);
  assert.deepEqual(followup.snapshot.events, []);
  assert.deepEqual(followup.snapshot.familyEvents, []);
});

test('semantic runtime: local personal results and private turns never become later parser or reply context', async () => {
  const calls: ModelInput[] = [];
  let understandingCount = 0;
  const model: ConversationModel = { async reply(input) {
    calls.push(structuredClone(input));
    if (input.purpose !== 'understanding') return '我们可以接着聊花园。';
    understandingCount++;
    return JSON.stringify(understandingCount === 1
      ? base('records', { suggested_tool: 'rehab.get_training_history' }) : base());
  } };
  const runtime = await open({ conversationModel: model,
    rehabReads: { async read(call) { return receipt(call.name); } } });
  const record = await runtime.processTurn(owner, { text: '查看我的训练记录', now, conversationContext: 'SYNTHETIC:TEST' });
  assert.match(record.reply.text, /PERSONAL_RECORD_MUST_STAY_LOCAL/);
  await runtime.processTurn(owner, { text: 'PRIVATE_MARKER，这段不要记录', now, conversationContext: 'SYNTHETIC:TEST' });
  const count = calls.length;
  await runtime.processTurn(owner, { text: '我们聊聊花园吧', now, conversationContext: 'SYNTHETIC:TEST' });
  assert.equal(understandingCount, 2);
  assert.doesNotMatch(JSON.stringify(calls.slice(count)), /PERSONAL_RECORD_MUST_STAY_LOCAL|PRIVATE_MARKER/);
});

test('semantic runtime: unsupported saved-state claims from final generation fail closed', async () => {
  for (const answer of ['我已经保存了你的训练计划。', '已为你修改训练安排。', '您现在可以开始训练。',
    '已完成十次训练。', '我查到你昨天做了三组训练。', '你的记录显示昨天做了三组训练。',
    '训练计划已经替你改好了。', '您现在可继续训练。', '工具参数为 exercise_id: shoulder_abduction。']) {
    const { model } = recordingModel(base(), answer);
    const runtime = await open({ conversationModel: model });
    const turn = await runtime.processTurn(owner, { text: '聊聊日常生活吧', now });
    assert.notEqual(turn.reply.text, answer);
    assert.doesNotMatch(turn.reply.text, /已经保存|已为你修改|现在可以开始训练|已完成十次|我查到|你的记录显示|改好了|现在可继续训练|exercise_id/);
    assert.deepEqual(turn.snapshot.events, []);
    assert.deepEqual(turn.appliedChanges.sharingAuditEntries, []);
    assert.equal(turn.reply.conversation?.provider, 'local');
  }
});

test('semantic runtime: invalid understanding followed by internal JSON cannot leak through legacy fallback', async () => {
  const internal = JSON.stringify(base('records', { suggested_tool: 'rehab.get_training_plan' }));
  const { model, calls } = recordingModel('INVALID_SEMANTIC_JSON', internal);
  const runtime = await open({ conversationModel: model });
  const turn = await runtime.processTurn(owner, { text: '陪我聊聊天吧', now });
  assert.equal(calls.filter(call => call.purpose === 'understanding').length, 1);
  assert.doesNotMatch(turn.reply.text, /suggested_tool|"route"|"version"|rehab\.get_training_plan|INVALID_SEMANTIC_JSON/);
  assert.ok(turn.reply.text.trim());
  assert.equal(turn.reply.conversation?.provider, 'local');
});

test('semantic runtime: invalid JSON and rejected understanding safely fall back without a second understanding service', async () => {
  const originalFetch = globalThis.fetch;
  let legacyUnderstandingCalls = 0;
  globalThis.fetch = async () => { legacyUnderstandingCalls++; throw Error('MUST_NOT_CALL_LEGACY_LLM'); };
  try {
    for (const semantic of ['not JSON', Error('NETWORK_PROVIDER_SECRET')]) {
      const { model, calls } = recordingModel(semantic, '本地回退后的普通回答');
      const runtime = await open({ conversationModel: model,
        understandingLlm: { baseUrl: 'https://invalid.test', apiKey: 'synthetic-test', model: 'test', timeoutMs: 10 } });
      const turn = await runtime.processTurn(owner, { text: '聊聊旅行吧', now });
      assert.equal(calls.filter(call => call.purpose === 'understanding').length, 1);
      assert.equal(legacyUnderstandingCalls, 0);
      assert.ok(turn.reply.text.trim());
      assert.doesNotMatch(turn.reply.text, /not JSON|NETWORK_PROVIDER_SECRET|MUST_NOT_CALL_LEGACY_LLM/);
      assert.equal(turn.revision, 1);
      assert.deepEqual(turn.snapshot.events, []);
    }
  } finally { globalThis.fetch = originalFetch; }
});

test('semantic runtime: a chat classification cannot suppress existing urgent safety handling', async () => {
  const text = '我胸口痛，喘不过气';
  const reference = await open({ semanticRoutingEnabled: false });
  const baseline = await reference.processTurn(owner, { text, now });
  const { model, calls } = recordingModel(base(), '放心继续训练');
  const runtime = await open({ conversationModel: model });
  const turn = await runtime.processTurn(owner, { text, now });
  assert.equal(baseline.reply.safetyAction, true);
  assert.equal(turn.reply.safetyAction, true);
  assert.equal(turn.reply.text, baseline.reply.text);
  assert.equal(calls.length, 1);
  assert.doesNotMatch(turn.reply.text, /放心继续训练/);
  assert.equal(turn.snapshot.events.length, baseline.snapshot.events.length);
  assert.equal(new Set(turn.snapshot.events.map(event => event.id)).size, turn.snapshot.events.length);
});

test('semantic runtime: special assistant health turns remain read-only even after LLM understanding', async () => {
  const { model, calls } = recordingModel(base('health', {
    mentions: [{ kind: 'symptom', text: '头晕', status: 'occurred', subject: 'self' }],
  }));
  const runtime = await open({ conversationModel: model,
    rehabAssistant: async () => ({ text: '已收到描述，请核对具体情况。', conversation: undefined }) });
  const turn = await runtime.processTurn(owner, { text: '我今天头晕', now });
  assert.equal(calls.filter(call => call.purpose === 'understanding').length, 1);
  assert.deepEqual(turn.snapshot.events, []);
  assert.deepEqual(turn.snapshot.familyEvents, []);
  assert.deepEqual(turn.appliedChanges.eventsToAppend, []);
  assert.deepEqual(turn.appliedChanges.sharingAuditEntries, []);
});

test('semantic runtime: read-only urgent replies retain safety without invented recording or sharing receipts', async () => {
  for (const text of ['我胸口痛，喘不过气', '我胸口痛，喘不过气，告诉女儿',
    '我胸口痛，喘不过气，不要告诉家人', '我胸口痛，喘不过气，这段不要记录']) {
    const reference = await open({ semanticRoutingEnabled: false });
    const baseline = await reference.processTurn(owner, { text, now });
    const { model, calls } = recordingModel(base('health'));
    const runtime = await open({ conversationModel: model,
      rehabAssistant: async () => ({ text: 'fallback', conversation: undefined }) });
    const turn = await runtime.processTurn(owner, { text, now });
    // no_record historically has a false safetyAction while retaining urgent
    // wording. Preserve that contract instead of introducing a new decision rule.
    assert.equal(turn.reply.safetyAction, baseline.reply.safetyAction, text);
    assert.match(turn.reply.text, /停止活动|急救/, text);
    for (const block of baseline.replyBlocks.filter(block => block.kind === 'main')) {
      assert.ok(turn.reply.text.includes(block.text), text);
    }
    assert.doesNotMatch(turn.reply.text, /(?:已|已经)(?:记下|记录|保存|共享|分享)|这次分享给家属一次的是|只保存在您这台设备上/, text);
    assert.ok(turn.replyBlocks.every(block => block.kind !== 'privacy' && block.kind !== 'receipt'), text);
    assert.deepEqual(turn.snapshot.events, [], text);
    assert.deepEqual(turn.snapshot.familyEvents, [], text);
    assert.deepEqual(turn.snapshot.audit, [], text);
    assert.equal(turn.delivery.status, 'not-requested', text);
    if (/告诉女儿|不要告诉|不要记录/.test(text)) assert.equal(calls.length, 0, text);
    await runtime.closeSession(owner);
    await reference.closeSession(owner);
  }
});

test('semantic runtime: read-only plan removes pure recording main blocks without removing safety text', async () => {
  const runtime = await open({ semanticRoutingEnabled: false });
  const turn = await runtime.processTurn(owner, { text: '我胸口痛，喘不过气', now });
  const plan = readOnlyPlan({ ...turn.appliedChanges, replyBlocks: [
    { kind: 'main', text: '已记下您刚才说的情况。' },
    { kind: 'main', text: '请先停止活动并保持安全姿势。' },
    { kind: 'privacy', text: '已共享给家属。' },
    { kind: 'receipt', text: '已记录。' },
  ] });
  assert.equal(plan.safetyAction, true);
  assert.match(plan.replyText, /停止活动并保持安全姿势/);
  assert.doesNotMatch(plan.replyText, /已记下|已共享|已记录/);
  assert.deepEqual(plan.eventsToAppend, []);
  assert.deepEqual(plan.familyEventsToAppend, []);
  assert.deepEqual(plan.sharingAuditEntries, []);
});

test('semantic runtime: cross-owner and source-context conversations never become shared parser context', async () => {
  const { model, calls } = recordingModel();
  const runtime = await open({ conversationModel: model });
  await runtime.openSession({ sessionId: 'SEMANTIC_TEST_B', participantId: 'SEMANTIC_TEST_B', profile, now,
    semanticRoutingEnabled: true, conversationModel: model });
  await runtime.processTurn(owner, { text: 'A_ONLY_SECRET，我喜欢海边', now, conversationContext: 'SYNTHETIC:TEST' });
  const afterA = calls.length;
  await runtime.processTurn('SEMANTIC_TEST_B', { text: '我们聊聊花园吧', now, conversationContext: 'SYNTHETIC:TEST' });
  assert.doesNotMatch(JSON.stringify(calls.slice(afterA)), /A_ONLY_SECRET/);
  const afterB = calls.length;
  await runtime.processTurn(owner, { text: '聊聊晴天吧', now, conversationContext: 'REPLAY_FILE:SELF_USE' });
  assert.doesNotMatch(JSON.stringify(calls.slice(afterB)), /A_ONLY_SECRET/);
});

test('semantic runtime: raw internal JSON from final generation is not displayed as the answer', async () => {
  const { model } = recordingModel(base(), JSON.stringify(base('records', { suggested_tool: 'rehab.get_training_plan' })));
  const runtime = await open({ conversationModel: model });
  const turn = await runtime.processTurn(owner, { text: '陪我聊聊天吧', now });
  assert.doesNotMatch(turn.reply.text, /suggested_tool|"route"|"version"|rehab\.get_training_plan/);
  assert.ok(turn.reply.text.trim());
});

test('semantic runtime: reset during understanding discards late JSON and does not execute tools', async () => {
  const started = deferred<void>(), release = deferred<string>();
  let reads = 0;
  const model: ConversationModel = { async reply() { started.resolve(); return release.promise; } };
  const runtime = await open({ conversationModel: model,
    rehabReads: { async read(call) { reads++; return receipt(call.name); } } });
  const pending = runtime.processTurn(owner, { text: '查看我的训练计划', now });
  await started.promise;
  const rejected = assert.rejects(pending, SessionInvalidatedError);
  const resetting = runtime.resetSession(owner, now);
  release.resolve(JSON.stringify(base('records', { suggested_tool: 'rehab.get_training_plan' })));
  await rejected;
  const reset = await resetting;
  assert.equal(reads, 0);
  assert.deepEqual(reset.chat, []);
  assert.deepEqual(reset.events, []);
});


test('semantic runtime: explicit other route uses scope fallback instead of generic model claims', async () => {
  for (const [text, expected] of [
    ['我想让你诊断一下这个问题', /需要医生|不能替医生诊断/],
    ['帮我预约医生', /没有执行|不在已接通/],
    ['帮我写一个股票交易机器人', /超出安康康复助手当前的功能范围/],
  ] as const) {
    const { model, calls } = recordingModel(base('other'), '已为你预约成功');
    let reads = 0, writes = 0;
    const runtime = await open({ conversationModel: model,
      rehabReads: { async read(call) { reads++; return receipt(call.name); } },
      rehabOperations: { async call() { writes++; return {status:'applied'}; } },
    });
    const turn = await runtime.processTurn(owner, { text, now });
    assert.match(turn.reply.text, expected, text);
    assert.doesNotMatch(turn.reply.text, /已为你预约成功|已经联系医生|已经执行/, text);
    assert.equal(calls.filter(call => call.purpose === 'reply').length, 0, text);
    assert.equal(reads, 0, text);
    assert.equal(writes, 0, text);
    assert.equal(turn.semanticExecution?.stages.some(stage => stage.reason === 'scope_fallback'), true, text);
    assert.deepEqual(turn.snapshot.events, [], text);
    await runtime.closeSession(owner);
  }
});

test('semantic runtime: other route never claims a real clinician handoff', async () => {
  const { model } = recordingModel(base('other'), '我已经帮你联系医生了');
  let operations = 0;
  const runtime = await open({ conversationModel: model,
    rehabOperations: { async call() { operations++; return {status:'applied'}; } } });
  const turn = await runtime.processTurn(owner, { text: '请帮我联系医生', now });
  assert.match(turn.reply.text, /没有替你联系医生|不能替医生/);
  assert.doesNotMatch(turn.reply.text, /已经帮你联系医生/);
  assert.equal(operations, 0);
  await runtime.closeSession(owner);
});
