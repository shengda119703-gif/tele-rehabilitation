import test from 'node:test';
import assert from 'node:assert/strict';
import { ArchiveService, InMemoryAttachmentPort, scopeKey } from '../src/archive/ArchiveService';
import { readHealthHistory } from '../src/archive/healthHistory';
import { FamilyService } from '../src/family/FamilyService';
import { InMemoryFamilyPersistence } from '../src/family/FamilyPersistence';
import {
  InMemoryNotificationPort,
  NotificationService,
  type NotificationPort,
} from '../src/notification/NotificationService';
import { readPersonTwinProduct } from '../src/personTwin/readPersonTwinProduct';
import { deriveHealthState } from '../src/runtime/derive';
import { PersistentHealthRecordStore } from '../src/store/PersistentHealthRecordStore';
import { observationToEvent } from '../src/pipeline/events';
import type { ElderProfile, Finding } from '../src/types';
const today = '2026-10-01',
  now = today + 'T12:00:00Z';
const scope = { ownerId: 'a', dataMode: 'personal' as const };
function family(owner = 'a', mode: 'personal' | 'demo' = 'personal') {
  return new FamilyService(owner, mode, new InMemoryFamilyPersistence());
}
function grant(f: FamilyService) {
  f.confirmLinkRequest(f.generateInvite(today));
  f.grant();
}
const file = {
  name: '报告',
  category: '体检报告',
  fileName: 'a.pdf',
  mediaType: 'application/pdf',
  bytes: new Uint8Array([1, 2]),
  visibility: 'family_ok' as const,
};
const finding: Finding = {
  id: 'f1',
  date: today,
  severity: 'urgent',
  title: '安全信号',
  detail: '本人信息',
  evidence: [],
  familyMessage: '请联系老人',
  familyEligible: true,
};
const profile: ElderProfile = {
  name: '同名',
  age: 72,
  conditions: [],
  medications: [],
  familyContact: '',
  familyPhone: '',
  mobility: 'independent',
  usesCane: false,
  nightVision: 'normal',
  cognition: 'stable',
  familySharing: 'granted',
};
const events = [
  observationToEvent({
    id: 'public',
    date: today,
    source: 'chat',
    text: '头晕',
    tags: ['dizziness'],
    visibility: 'family_ok',
  }),
  observationToEvent({
    id: 'private',
    date: today,
    source: 'chat',
    text: 'private secret',
    tags: ['pain'],
    visibility: 'private',
  }),
];
const accepted = () => [{ channel: 'browser_push' as const, status: 'accepted' as const, detail: 'adapter accepted' }];

test('archive add/edit/read/clear preserve ID and isolate owner, mode, bytes', async () => {
  const port = new InMemoryAttachmentPort(),
    f = family();
  const a = new ArchiveService(scope, port, () => f.readState());
  const entry = await a.save(file, now);
  await a.save({ ...file, id: entry.id, name: '改名' }, now);
  assert.equal((await a.list()).length, 1);
  assert.equal((await a.read(entry.id)).name, '改名');
  const read = await a.read(entry.id);
  read.bytes[0] = 9;
  assert.equal((await a.read(entry.id)).bytes[0], 1);
  for (const other of [
    { ownerId: 'b', dataMode: 'personal' as const },
    { ownerId: 'a', dataMode: 'demo' as const },
  ]) {
    const of = family(other.ownerId, other.dataMode);
    const service = new ArchiveService(other, port, () => of.readState());
    assert.deepEqual(await service.list(), []);
    await service.save(file, now);
    await a.clear();
    assert.equal((await service.list()).length, 1);
  }
  assert.deepEqual(await a.list(), []);
});
test('family archives require binding and long consent; private attachments remain private', async () => {
  const port = new InMemoryAttachmentPort(),
    f = family();
  const self = new ArchiveService(scope, port, () => f.readState());
  const entry = await self.save(file);
  await self.save({ ...file, name: '私密', visibility: 'private' });
  const relative = new ArchiveService(scope, port, () => f.readState(), 'family');
  await assert.rejects(relative.list());
  f.confirmLinkRequest(f.generateInvite(today));
  f.shareFindingIds(['f1']);
  await assert.rejects(relative.list());
  f.grant();
  assert.deepEqual(
    (await relative.list()).map((a) => a.id),
    [entry.id],
  );
  f.revoke();
  await assert.rejects(relative.read(entry.id));
});
test('scoped health snapshot storage never hydrates another owner or demo history', async () => {
  const map = new Map<string, unknown>();
  const kv = {
    get: async (k: string) => map.get(k),
    set: async (k: string, v: unknown) => {
      map.set(k, v);
    },
    delete: async (k: string) => {
      map.delete(k);
    },
  };
  const a = new PersistentHealthRecordStore(kv, scopeKey(scope));
  a.save({ events, familyEvents: [], chat: [] });
  const restored = new PersistentHealthRecordStore(kv, scopeKey(scope));
  assert.equal(await restored.hydrate(), true);
  assert.deepEqual(restored.load().events, events);
  for (const key of ['personal:b', 'demo:a'])
    assert.equal(await new PersistentHealthRecordStore(kv, key).hydrate(), false);
});
test('notification permission, one-time, private finding and duplicate gates use existing family rules', async () => {
  const f = family(),
    port = new InMemoryNotificationPort(),
    n = new NotificationService(scope, () => f.readState(), port);
  let calls = 0;
  const deliver = () => {
    calls++;
    return accepted();
  };
  await n.dispatch([finding], deliver, now);
  assert.equal(calls, 0);
  f.confirmLinkRequest(f.generateInvite(today));
  await n.dispatch([finding], deliver, now);
  assert.equal(calls, 0);
  f.shareFindingIds(['f1']);
  await n.dispatch([finding, finding, { ...finding, id: 'private', familyEligible: false }], deliver, now);
  await n.dispatch([finding], deliver, now);
  assert.equal(calls, 1);
  assert.equal(n.read()[0].shareMode, 'one_time');
  assert.equal(f.readState().familySharing, 'denied');
  assert.equal(n.read()[0].phase, 'accepted');
  assert.equal(n.read()[0].lifecycle, 'new');
  f.consumeOneTime('self', ['f1']);
  assert.deepEqual(n.read('family'), []);
  f.grant();
  await n.dispatch([{ ...finding, id: 'f2' }], deliver, now);
  assert.equal(n.read().find((r) => r.findingId === 'f2')?.shareMode, 'persistent');
});
test('notification reservation precedes delivery; failed, delivered and acknowledged stay distinct', async () => {
  const f = family();
  grant(f);
  const n = new NotificationService(scope, () => f.readState(), new InMemoryNotificationPort());
  await n.dispatch(
    [finding],
    () => {
      assert.equal(n.read()[0].phase, 'pending');
      return [{ channel: 'browser_push', status: 'failed', detail: 'denied' }];
    },
    now,
  );
  n.acknowledge('f1', now);
  assert.equal(n.read()[0].phase, 'failed');
  assert.equal(n.read()[0].lifecycle, 'acknowledged');
  await n.dispatch(
    [{ ...finding, id: 'receipt' }],
    () => [{ channel: 'webhook_push', status: 'delivered', detail: 'explicit receipt' }],
    now,
  );
  const receipt = n.read().find((r) => r.findingId === 'receipt')!;
  assert.equal(receipt.phase, 'delivered');
  assert.equal(receipt.lifecycle, 'new');
});
test('notification owners, mode, recipient and reload dedup stay isolated', async () => {
  const port = new InMemoryNotificationPort(),
    f = family();
  grant(f);
  const n = new NotificationService(scope, () => f.readState(), port);
  await n.dispatch([finding], accepted, now);
  const f2 = family('b');
  grant(f2);
  const other = new NotificationService({ ownerId: 'b', dataMode: 'personal' }, () => f2.readState(), port);
  other.mergeRecord(n.read()[0]);
  assert.deepEqual(other.read(), []);
  const demoFamily = family('a', 'demo');
  grant(demoFamily);
  assert.deepEqual(
    new NotificationService({ ownerId: 'a', dataMode: 'demo' }, () => demoFamily.readState(), port).read(),
    [],
  );
  const restored = new NotificationService(scope, () => f.readState(), port);
  let calls = 0;
  await restored.dispatch(
    [finding],
    () => {
      calls++;
      return accepted();
    },
    now,
  );
  assert.equal(calls, 0);
  assert.notEqual(restored.sessionId, n.sessionId);
  f.unbind();
  assert.deepEqual(n.read('family'), []);
  grant(f);
  assert.deepEqual(n.read('family'), []);
});
test('notification storage failure does not claim delivery or invoke channels', async () => {
  const f = family();
  grant(f);
  const bad: NotificationPort = { load: () => [], save: () => ({ ok: false, error: 'disk full' }) };
  const n = new NotificationService(scope, () => f.readState(), bad);
  let calls = 0;
  await n.dispatch(
    [finding],
    () => {
      calls++;
      return accepted();
    },
    now,
  );
  assert.equal(calls, 0);
  assert.equal(n.lastSave.ok, false);
  assert.equal(n.read()[0].phase, 'pending');
});
test('only restored failed browser pushes retry once, never webhook and never after revoke', async () => {
  const f = family();
  grant(f);
  const port = new InMemoryNotificationPort(),
    n = new NotificationService(scope, () => f.readState(), port);
  await n.dispatch([finding], () => [{ channel: 'browser_push', status: 'failed', detail: 'offline' }], now);
  let calls = 0;
  const send = () => {
    calls++;
    return accepted();
  };
  await n.retryBrowser(send);
  assert.equal(calls, 0);
  f.revoke();
  const blocked = new NotificationService(scope, () => f.readState(), port);
  await blocked.retryBrowser(send);
  assert.equal(calls, 0);
  f.grant();
  const next = new NotificationService(scope, () => f.readState(), port);
  await next.retryBrowser(send);
  await next.retryBrowser(send);
  assert.equal(calls, 1);
  assert.equal(next.read()[0].phase, 'accepted');
});
test('Person Twin read model matches runtime/context and family projection excludes private evidence', () => {
  const f = family();
  grant(f);
  const input = { ...scope, profile, events, tasks: [], family: f.readState(), today, asOf: now };
  const derived = deriveHealthState(profile, events, today),
    self = readPersonTwinProduct(input);
  assert.deepEqual(self.personTwin, derived.personTwin);
  assert.deepEqual(self.publicPersonTwin, derived.agentContext.personTwinPublic);
  assert.deepEqual(self.findings, derived.findings);
  assert.equal(self.asOf, now);
  const relative = readPersonTwinProduct(input, 'family');
  assert.ok(!relative.personTwin?.recentSymptoms.includes('pain'));
  assert.ok(!JSON.stringify(relative).includes('private secret'));
  assert.equal(relative.recentEvents.length, 1);
  const history = readHealthHistory(scope, profile, events, [], derived.findings, [], f.readState(), today, 'family');
  assert.equal(history.observations.length, 1);
  f.revoke();
  const revoked = readPersonTwinProduct({ ...input, family: f.readState() }, 'family');
  assert.equal(revoked.personTwin, null);
  assert.deepEqual(revoked.recentEvents, []);
  self.personTwin!.recentSymptoms.push('pain');
  assert.deepEqual(readPersonTwinProduct(input).personTwin, derived.personTwin);
});
