import test from 'node:test';
import assert from 'node:assert/strict';
import { AgentRuntime, InMemoryPersistence, SessionInvalidatedError, type PersistencePort } from '../src/runtime';
import { ruleBasedAdapter, type LlmAdapter } from '../src/engine/agent';
import type { ElderProfile } from '../src/types';
import { clearSharingAudit, recordSharingAudit } from '../src/engine/sharingAudit';
import { legacyReactTurn, type LegacyState } from './fixtures/legacyReactOrchestration';

const profile: ElderProfile = {
  name: '测试老人',
  age: 72,
  conditions: [],
  medications: [],
  familyContact: '测试家属',
  familyPhone: '',
  mobility: 'independent',
  usesCane: false,
  nightVision: 'normal',
  cognition: 'stable',
  familySharing: 'denied',
};
const date = (day = 12, hour = 10) => new Date(2026, 8, day, hour, 0, 0, 0);
async function open(options: Partial<Parameters<AgentRuntime['openSession']>[0]> = {}) {
  const runtime = new AgentRuntime();
  await runtime.openSession({ sessionId: 'a', profile, now: date(), ...options });
  return runtime;
}
function deferred() {
  let resolve!: () => void;
  const promise = new Promise<void>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}
function blockingAdapter() {
  const started = deferred();
  const release = deferred();
  const adapter: LlmAdapter = {
    async complete(...args) {
      started.resolve();
      await release.promise;
      return ruleBasedAdapter.complete(...args);
    },
  };
  return { adapter, started, release };
}

test('runtime: sequential turns retain sources, append facts, detect, recompute twins and tasks', async () => {
  const r = await open();
  const first = await r.processTurn('a', { text: '我今天早上在厕所摔了一跤', now: date() });
  assert.ok(first.snapshot.events.length);
  assert.ok(first.findings.some((f) => f.severity === 'urgent'));
  assert.ok(first.tasks.length);
  assert.deepEqual(first.personTwin, first.snapshot.agentContext.personTwin);
  assert.equal(first.revision, 1);
  const second = await r.processTurn('a', { text: '我今天量了血压150/95', now: date() });
  assert.equal(second.revision, 2);
  assert.equal(second.snapshot.chat.length, 4);
  assert.notEqual(first.sourceMessageId, second.sourceMessageId);
  assert.ok(second.snapshot.events.length > first.snapshot.events.length);
  const detached = r.readSnapshot('a');
  detached.events.length = 0;
  assert.ok(r.readSnapshot('a').events.length);
});

test('runtime parity: legacy React business path matches complete runtime across 12 turns', async () => {
  const r = await open();
  const state: LegacyState = {
    events: [],
    familyEvents: [],
    chat: [],
    tasks: [],
    audit: [],
    sharedFamilyEventIds: [],
    sharedFindingIds: [],
  };
  const inputs = [
    '我今天头晕',
    '说错了，我今天是胸口疼',
    '我爸今天血压150/95',
    '说错了，不是我爸，是我老公',
    '我今天血压150/95',
    '我今天忘了吃降压药',
    '我头晕，这段不要记录',
    '我今天头晕，不要告诉家人',
    '把我今天头晕告诉女儿',
    '之前告诉女儿什么',
    '刚才说了什么',
    '我今天早上在厕所摔了一跤',
  ];
  for (const [index, text] of inputs.entries()) {
    const now = date(12, 10 + index);
    const result = await r.processTurn('a', { text, now });
    const reference = await legacyReactTurn(
      state,
      profile,
      text,
      '2026-09-12',
      `09-12 ${10 + index}:00`,
      `2026-09-12T${10 + index}:00:00.000`,
      result.sourceMessageId,
      result.reply.id,
      now.getTime(),
    );
    assert.deepEqual(result.reply, reference.reply, text);
    assert.deepEqual(result.understanding, reference.understanding, text);
    assert.deepEqual(result.appliedChanges, reference.plan, text);
    for (const key of [
      'events',
      'familyEvents',
      'chat',
      'tasks',
      'audit',
      'sharedFamilyEventIds',
      'sharedFindingIds',
    ] as const) {
      assert.deepEqual(result.snapshot[key], reference.state[key], `${text}: ${key}`);
    }
    assert.deepEqual(result.findings, reference.findings, text);
    assert.deepEqual(result.snapshot.healthData, reference.healthData, text);
    assert.deepEqual(result.snapshot.agentContext, reference.agentContext, text);
  }
});

test('runtime: private/no_record never use LLM or delivery; no_record is absent from persistence', async () => {
  const memory = new InMemoryPersistence();
  let calls = 0;
  const priorFetch = globalThis.fetch;
  globalThis.fetch = async () => {
    calls++;
    throw new Error('must not connect');
  };
  try {
    const r = await open({
      persistence: memory,
      understandingLlm: { baseUrl: 'https://invalid.test', apiKey: 'test-only', model: 'test', timeoutMs: 20 },
      replyAdapter: {
        async complete() {
          calls++;
          throw new Error('must not connect');
        },
      },
      delivery: {
        async deliver() {
          calls++;
          return 'delivered';
        },
      },
    });
    const privateTurn = await r.processTurn('a', { text: '我今天头晕，不要告诉家人', now: date() });
    assert.ok(privateTurn.snapshot.events.length);
    const noRecord = await r.processTurn('a', { text: '我头晕，这段不要记录', now: date() });
    assert.deepEqual(noRecord.snapshot.events, privateTurn.snapshot.events);
    assert.equal(noRecord.reply.persisted, false);
    assert.equal((await memory.load('a'))?.health.chat.length, 2);
    assert.equal(noRecord.persistence.status, 'memory-only');
    assert.equal(calls, 0);
  } finally {
    globalThis.fetch = priorFetch;
  }
});

test('runtime: sessions isolate tasks, chat, events and audit from each other and legacy globals', async () => {
  const r = await open();
  await r.openSession({ sessionId: 'b', profile, now: date() });
  recordSharingAudit([
    {
      id: 'legacy',
      createdAt: '2026-09-12T10:00:00',
      scope: 'self',
      recipient: 'daughter',
      shareMode: 'one_time',
      content: 'LEGACY_SECRET',
    },
  ]);
  try {
    await r.processTurn('a', { text: '把我今天头晕告诉女儿', now: date() });
    await r.processTurn('a', { text: '我今天早上在厕所摔了一跤', now: date() });
    const a = r.readSnapshot('a');
    assert.ok(a.audit.length);
    assert.ok(a.events.length);
    assert.ok(a.tasks.length);
    const b = await r.processTurn('b', { text: '之前告诉女儿什么', now: date() });
    assert.equal(b.snapshot.audit.length, 0);
    assert.equal(b.snapshot.events.length, 0);
    assert.equal(b.tasks.length, 0);
    assert.ok(!b.reply.text.includes('LEGACY_SECRET'));
    assert.ok(b.reply.text.includes('没有找到可靠'));
    assert.equal(a.chat.length, 4);
  } finally {
    clearSharingAudit();
  }
});

test('runtime: persistence errors are real receipts; accepted facts stay in memory', async () => {
  const port: PersistencePort = {
    async load() {
      return null;
    },
    async save() {
      throw new Error('disk full');
    },
    async clear() {
      throw new Error('disk locked');
    },
  };
  const r = await open({ persistence: port });
  const result = await r.processTurn('a', { text: '我今天血压150/95', now: date() });
  assert.equal(result.persistence.status, 'failed');
  assert.ok(result.snapshot.events.length);
  const reset = await r.resetSession('a', date());
  assert.equal(reset.persistence.status, 'failed');
  assert.equal(reset.events.length, 0);
  assert.equal(reset.audit.length, 0);
  assert.equal(reset.revision, 2);
});

test('runtime: load failure rejects opening and never writes over unread history', async () => {
  let saved = 0;
  await assert.rejects(
    open({
      persistence: {
        async load() {
          throw new Error('cannot read');
        },
        async save() {
          saved++;
          return 'saved';
        },
        async clear() {
          return 'saved';
        },
      },
    }),
    /cannot read/,
  );
  assert.equal(saved, 0);
});

test('runtime: concurrent turns are serialized, latest chat is used for recall', async () => {
  const gate = blockingAdapter();
  const r = await open({ replyAdapter: gate.adapter });
  const first = r.processTurn('a', { text: '我今天血压150/95', now: date() });
  await gate.started.promise;
  await r.openSession({ sessionId: 'b', profile, now: date() });
  const independent = await r.processTurn('b', { text: '我今天头晕', now: date() });
  assert.equal(independent.revision, 1);
  const second = r.processTurn('a', { text: '刚才说了什么', now: date() });
  gate.release.resolve();
  const [a, b] = await Promise.all([first, second]);
  assert.equal(a.revision, 1);
  assert.equal(b.revision, 2);
  assert.ok(b.reply.text.includes('血压150/95'));
  assert.deepEqual(
    b.snapshot.chat.map((m) => m.role),
    ['elder', 'agent', 'elder', 'agent'],
  );
});

test('runtime: reset invalidates slow/queued turns without appending late results', async () => {
  const gate = blockingAdapter();
  const r = await open({ replyAdapter: gate.adapter });
  const first = r.processTurn('a', { text: '我今天血压150/95', now: date() });
  await gate.started.promise;
  const second = r.processTurn('a', { text: '我今天头晕', now: date() });
  const rejectedA = assert.rejects(first, SessionInvalidatedError);
  const rejectedB = assert.rejects(second, SessionInvalidatedError);
  const reset = r.resetSession('a', date());
  gate.release.resolve();
  await Promise.all([rejectedA, rejectedB, reset]);
  assert.equal(r.readSnapshot('a').chat.length, 0);
  const next = await r.processTurn('a', { text: '我今天头晕', now: date() });
  assert.equal(next.snapshot.generation, 1);
  assert.equal(next.revision, 2);
});

test('runtime: close invalidates slow results, drains and permits fresh reopen', async () => {
  const gate = blockingAdapter();
  const r = await open({ replyAdapter: gate.adapter });
  const turn = r.processTurn('a', { text: '我今天血压150/95', now: date() });
  await gate.started.promise;
  const rejected = assert.rejects(turn, SessionInvalidatedError);
  const closing = r.closeSession('a');
  assert.throws(() => r.readSnapshot('a'), SessionInvalidatedError);
  gate.release.resolve();
  await Promise.all([rejected, closing]);
  assert.throws(() => r.processTurn('a', { text: '你好', now: date() }), /not open/);
  const reopened = await r.openSession({ sessionId: 'a', profile, now: date() });
  assert.equal(reopened.chat.length, 0);
});

test('runtime: revision conflicts do not break the queue', async () => {
  const r = await open();
  await r.processTurn('a', { text: '我今天头晕', now: date(), expectedRevision: 0 });
  await assert.rejects(r.processTurn('a', { text: '你好', now: date(), expectedRevision: 0 }), /Revision conflict/);
  assert.equal((await r.processTurn('a', { text: '我今天血压150/95', now: date(), expectedRevision: 1 })).revision, 2);
});

test('runtime: midnight updates event dates, context, twins and medication deduplication', async () => {
  const r = await open({ profile: { ...profile, medications: ['测试药物'] } });
  await r.updateTaskStatus('a', 'task-medication-2026-09-12', 'completed');
  await r.processTurn('a', { text: '我今天忘了吃降压药', now: date(12, 23) });
  const result = await r.processTurn('a', { text: '我今天量了血压150/95', now: date(13, 0) });
  assert.equal(result.snapshot.today, '2026-09-13');
  assert.ok(result.appliedChanges.eventsToAppend.every((event) => event.timestamp.startsWith('2026-09-13')));
  assert.equal(result.tasks.filter((task) => task.kind === 'medication_check').length, 2);
  assert.equal(result.tasks.find((task) => task.dueDate === '2026-09-12')?.status, 'completed');
  assert.equal(result.personTwin.asOf, '2026-09-13');
});

test('runtime: failed understanding/reply LLM falls back to original rules', async () => {
  const previous = globalThis.fetch;
  globalThis.fetch = async () => {
    throw new Error('offline');
  };
  try {
    const r = await open({
      understandingLlm: { baseUrl: 'https://invalid.test', apiKey: 'test', model: 'test', timeoutMs: 20 },
      replyAdapter: {
        async complete() {
          throw new Error('offline');
        },
      },
    });
    const result = await r.processTurn('a', { text: '我今天血压150/95', now: date() });
    assert.ok(result.snapshot.events.length);
    assert.ok(result.reply.text);
  } finally {
    globalThis.fetch = previous;
  }
});

test('runtime: delivery is distinct from planned sharing and persistence', async () => {
  const r = await open({
    delivery: {
      async deliver() {
        throw new Error('transport unavailable');
      },
    },
  });
  const result = await r.processTurn('a', { text: '把我今天头晕告诉女儿', now: date() });
  assert.ok(result.snapshot.audit.length);
  assert.equal(result.delivery.status, 'failed');
  assert.equal(result.persistence.status, 'not-configured');
});

test('runtime: close/reopen restores only persisted health, never session-only tasks/audit', async () => {
  const store = new InMemoryPersistence();
  const r = await open({ persistence: store });
  await r.processTurn('a', { text: '把我今天头晕告诉女儿', now: date() });
  await r.closeSession('a');
  const loaded = await r.openSession({ sessionId: 'a', profile, now: date(), persistence: store });
  assert.equal(loaded.chat.length, 2);
  assert.equal(loaded.audit.length, 0);
  assert.equal(loaded.revision, 1);
  await r.resetSession('a', date());
  assert.equal(await store.load('a'), null);
});

test('runtime: reopening with identical clock does not reuse source/event IDs', async () => {
  const persistence = new InMemoryPersistence();
  const r = await open({ persistence });
  const first = await r.processTurn('a', { text: '我今天血压150/95', now: date() });
  await r.closeSession('a');
  await r.openSession({ sessionId: 'a', profile, now: date(), persistence });
  const second = await r.processTurn('a', { text: '我今天血压155/95', now: date() });
  assert.notEqual(first.sourceMessageId, second.sourceMessageId);
  assert.ok(second.snapshot.events.length > first.snapshot.events.length);
  assert.equal(new Set(second.snapshot.events.map((event) => event.id)).size, second.snapshot.events.length);
});

test('runtime: reset waits for in-flight storage before clearing; stale results cannot overwrite reset', async () => {
  const started = deferred();
  const release = deferred();
  const memory = new InMemoryPersistence();
  const order: string[] = [];
  const persistence: PersistencePort = {
    load: (id) => memory.load(id),
    async save(id, snapshot) {
      started.resolve();
      await release.promise;
      order.push('save');
      return memory.save(id, snapshot);
    },
    async clear(id) {
      order.push('clear');
      return memory.clear(id);
    },
  };
  const r = await open({ persistence });
  const turn = r.processTurn('a', { text: '我今天血压150/95', now: date() });
  await started.promise;
  const rejected = assert.rejects(turn, SessionInvalidatedError);
  const reset = r.resetSession('a', date());
  assert.throws(() => r.readSnapshot('a'), SessionInvalidatedError);
  release.resolve();
  await Promise.all([rejected, reset]);
  assert.deepEqual(order, ['save', 'clear']);
  assert.equal(await memory.load('a'), null);
  assert.equal(r.readSnapshot('a').events.length, 0);
});

test('runtime: correction changes exact source facts; original correction-only gate remains', async () => {
  const r = await open();
  await r.processTurn('a', { text: '我今天血压150/95', now: date() });
  const corrected = await r.processTurn('a', { text: '说错了，我今天血压135/85', now: date() });
  assert.ok(corrected.appliedChanges.correction);
  assert.ok(corrected.appliedChanges.eventsToAppend.length);
  assert.ok(!JSON.stringify(corrected.snapshot.healthData.measurements).includes('150'));
  const before = corrected.snapshot.events;
  const only = await r.processTurn('a', { text: '说错了，不是我', now: date() });
  assert.ok(only.appliedChanges.correction);
  assert.equal(only.appliedChanges.eventsToAppend.length, 0);
  assert.deepEqual(only.snapshot.events, before);
});
