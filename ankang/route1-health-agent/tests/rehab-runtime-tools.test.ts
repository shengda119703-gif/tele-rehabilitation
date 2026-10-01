import test from 'node:test';
import assert from 'node:assert/strict';
import { AgentRuntime } from '../src/runtime';
import type { RehabToolPort } from '../src/runtime/rehabTools';
import { profile as demoProfile } from '../src/data/demo';

const now = new Date(2026, 9, 1, 12);
test('rehab tool turn keeps facts outside HealthEvents, empty receipts cannot be invented', async () => {
  let reads = 0;
  const tools: RehabToolPort = {
    select: async () => ({ name: 'rehab.get_training_plan', arguments: {} }),
    read: async () => {
      reads++;
      return {
        tool: 'rehab.get_training_plan',
        read_only: true,
        status: 'empty',
        records: [],
        scope: { participant_id: 'synthetic', source_kind: 'SYNTHETIC', usage_context: 'TEST' },
      };
    },
    describe: async () => {
      throw new Error('Empty data must not call model');
    },
  };
  const runtime = new AgentRuntime();
  await runtime.openSession({ sessionId: 'test', profile: demoProfile, now, rehabTools: tools });
  const result = await runtime.processTurn('test', { text: '我今天练什么？', now });
  assert.match(result.reply.text, /没有找到/);
  assert.equal(result.revision, 1);
  assert.deepEqual(result.snapshot.events, []);
  assert.equal(reads, 1);
  await runtime.closeSession('test');
});

test('private/no_record, safety and new health facts retain their original Agent path', async () => {
  const forbidden = async (): Promise<never> => {
    throw new Error('Must not call');
  };
  const runtime = new AgentRuntime();
  await runtime.openSession({
    sessionId: 'test',
    profile: demoProfile,
    now,
    rehabTools: { select: forbidden, read: forbidden, describe: forbidden },
  });
  for (const text of [
    '我今天练什么，不要记录',
    '我今天头晕，不要告诉家人',
    '我胸口痛，喘不过气',
    '我今天头晕，我今天练什么？',
  ]) {
    await runtime.processTurn('test', { text, now });
  }
  await runtime.closeSession('test');
});
