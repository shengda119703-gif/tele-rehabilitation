import test from 'node:test';
import assert from 'node:assert/strict';
import { FamilyService } from '../src/family/FamilyService';
import { InMemoryFamilyPersistence } from '../src/family/FamilyPersistence';
import { familyPermission } from '../src/family/projection';
import { browserFamilyPersistence, familyStateKey } from '../src/store/familyStore';
import { observationToEvent } from '../src/pipeline/events';
import type { FamilyHealthEvent, Finding } from '../src/types';

const today = '2026-10-01';
function setup(ownerId = 'owner-a', port = new InMemoryFamilyPersistence()) {
  return new FamilyService(ownerId, 'personal', port);
}
function bind(service: FamilyService) {
  const code = service.generateInvite(today);
  assert.ok(service.confirmLinkRequest(code));
  return code;
}
const finding: Finding = {
  id: 'self-finding',
  date: today,
  severity: 'alert',
  title: '本人变化',
  detail: '本人详情',
  evidence: [],
  familyEligible: true,
};
const relative: FamilyHealthEvent = {
  id: 'relative',
  timestamp: today + 'T12:00:00',
  source: 'chat',
  subject: 'father',
  text: '父亲头晕',
  tags: ['dizziness'],
  hasHealthValue: false,
  status: 'occurred',
  visibility: 'family_ok',
  shareMode: 'persistent',
};
const input = () => ({
  ownerId: 'owner-a',
  findings: [finding],
  tasks: [],
  familyEvents: [relative],
  measurements: [],
});

void test('invite consumption, replacement, session expiry and unbind preserve distinct binding state', async () => {
  const port = new InMemoryFamilyPersistence();
  const service = setup('owner-a', port);
  const old = service.generateInvite(today);
  const current = service.generateInvite(today);
  assert.equal(service.confirmLinkRequest(old), null);
  assert.equal(service.confirmLinkRequest('wrong'), null);
  assert.equal(service.readState().familyLink?.status, 'pending');
  assert.equal(setup('owner-a', port).confirmLinkRequest(current), null);
  assert.equal((await service.bindFamily(current)).ok, true);
  assert.equal(service.readState().familyLink?.status, 'active');
  assert.equal(service.readState().familySharing, 'denied');
  assert.equal(service.confirmLinkRequest(current), null);
  service.grant();
  service.shareFindingIds([finding.id]);
  service.unbind();
  assert.equal(service.readState().familySharing, 'granted');
  assert.equal(service.readState().familyLink, null);
  assert.deepEqual(service.readState().sharedFindingIds, []);
  assert.deepEqual(service.project(input()).findings, []);
  assert.equal(service.confirmLinkRequest(current), null);
});

void test('grant/revoke and selected one-time permission are not long-term consent or delivery', () => {
  const service = setup();
  bind(service);
  service.shareFindingIds([finding.id]);
  assert.equal(service.readState().familySharing, 'denied');
  assert.equal(service.project(input()).findings.length, 1);
  assert.equal(service.project(input()).status, 'permission');
  assert.equal(service.project(input()).canViewSharedDetail, false);
  service.consumeOneTime('self', [finding.id]);
  assert.equal(service.project(input()).findings.length, 0);
  service.grant('2026-10-01T00:01:00');
  assert.equal(service.project(input()).canViewSharedDetail, true);
  service.revoke();
  assert.equal(service.project(input()).canViewSharedDetail, false);
  assert.equal(service.readState().familySharing, 'denied');
});

void test('private/no_record denied; self and family facts projected to separate ledgers', () => {
  const service = setup();
  bind(service);
  service.grant();
  const base = { ownerId: 'owner-a', id: finding.id, scope: 'self' as const, intent: 'none' as const };
  for (const intent of ['private', 'no_record'] as const)
    assert.equal(familyPermission(service.readState(), { ...base, intent }).allowed, false);
  assert.equal(
    familyPermission(service.readState(), { ...base, visibility: 'private', intent: 'share_family' }).allowed,
    false,
  );
  const self = observationToEvent({
    id: 'self',
    date: today,
    source: 'chat',
    text: '本人头晕',
    tags: ['dizziness'],
    visibility: 'family_ok',
  });
  const projected = service.project({
    ...input(),
    selfEvents: [self],
    familyEvents: [
      relative,
      { ...relative, id: 'private-relative', visibility: 'private' },
      { ...relative, id: 'no-record' },
    ],
    privacyIntents: { 'no-record': 'no_record' },
  });
  assert.deepEqual(
    projected.selfEvents.map((e) => e.id),
    [self.id],
  );
  assert.deepEqual(
    projected.familyEvents.map((e) => e.id),
    ['relative'],
  );
  assert.ok(!('profile' in projected) && !('chat' in projected));
  service.revoke();
  service.shareFamilyEventIds(['relative']);
  assert.equal(
    service.project({ ...input(), familyEvents: [{ ...relative, shareMode: 'one_time' }] }).familyEvents.length,
    1,
  );
  assert.deepEqual(service.project(input()).selfEvents, []);
});

void test('owner-scoped relationship, grants and session audit do not cross users', () => {
  const port = new InMemoryFamilyPersistence();
  const a = setup('owner-a', port),
    b = setup('owner-b', port);
  bind(a);
  a.grant();
  a.appendSharingRecords([
    {
      id: 'audit',
      createdAt: today,
      scope: 'family',
      recipient: 'daughter',
      shareMode: 'one_time',
      content: '父亲头晕',
    },
  ]);
  a.appendSharingRecords(
    [
      {
        id: 'no-record',
        createdAt: today,
        scope: 'self',
        recipient: 'family',
        shareMode: 'persistent',
        content: '不保存',
      },
    ],
    'no_record',
  );
  assert.equal(a.readSharingRecords().length, 1);
  assert.equal(a.readSharingRecords()[0].stage, 'planned');
  assert.equal(b.readState().familyLink, null);
  assert.equal(b.readState().familySharing, 'denied');
  assert.deepEqual(b.readSharingRecords(), []);
  assert.throws(() => b.project(input()), /owner mismatch/);
  bind(b);
  b.applyRemoteConsent({ sharing: 'granted', updatedAt: today }, a.readState().familyLink!.id);
  assert.equal(b.readState().familySharing, 'denied', 'another relationship cannot overwrite consent');
  const reloaded = setup('owner-a', port);
  assert.equal(reloaded.readState().familyLink?.ownerId, 'owner-a');
  assert.deepEqual(reloaded.readSharingRecords(), []);
  a.close();
  assert.deepEqual(a.readSharingRecords(), []);
});

void test('injected handshake carries consent, rejects mismatches and ignores unbind-stale reply', async () => {
  const elder = setup('elder'),
    family = setup('family');
  const code = elder.generateInvite(today);
  elder.grant();
  let handler: ((event: { type: string; payload: unknown }) => void) | undefined;
  const transport = {
    subscribe(fn: typeof handler) {
      handler = fn;
      return () => {
        handler = undefined;
      };
    },
    broadcast(type: string, payload: unknown) {
      const request = payload as { requestId: string; code: string };
      const link = elder.confirmLinkRequest(request.code);
      handler?.({
        type,
        payload: link
          ? { kind: 'accepted', requestId: request.requestId, link, consent: { sharing: 'granted', updatedAt: today } }
          : { kind: 'rejected', requestId: request.requestId },
      });
    },
  };
  assert.equal((await family.bindFamily('wrong', transport)).ok, false);
  assert.equal((await family.bindFamily(code, transport)).ok, true);
  assert.equal(family.readState().remoteConsent?.sharing, 'granted');
  assert.equal(family.readState().familyLink?.ownerId, 'family');
  const pending = family.bindFamily('late', {
    subscribe(fn) {
      handler = fn;
      return () => {};
    },
    broadcast(_type, payload) {
      family.unbind();
      handler?.({
        type: 'family.link',
        payload: {
          kind: 'accepted',
          requestId: (payload as { requestId: string }).requestId,
          link: { ...elder.readState().familyLink!, inviteCode: 'late' },
        },
      });
    },
  });
  assert.equal((await pending).ok, false);
  assert.equal(family.readState().familyLink, null);
  family.grant();
  assert.equal(
    (
      await family.bindFamily('fresh', {
        subscribe(fn) {
          handler = fn;
          return () => {};
        },
        broadcast(_type, payload) {
          handler?.({
            type: 'family.link',
            payload: {
              kind: 'accepted',
              requestId: (payload as { requestId: string }).requestId,
              link: { ...elder.readState().familyLink!, inviteCode: 'fresh' },
            },
          });
        },
      })
    ).ok,
    true,
  );
  assert.equal(family.readState().familySharing, 'denied', 'new link without consent must not inherit old grant');
});

void test('browser persists by owner; unowned legacy state not inherited; failures remain explicit', () => {
  const map = new Map<string, string>([
    ['ankang-route1-family-state-v1', JSON.stringify({ familySharing: 'granted' })],
  ]);
  let fail = false;
  (globalThis as { window?: unknown }).window = {
    localStorage: {
      getItem: (key: string) => map.get(key) ?? null,
      setItem: (key: string, value: string) => {
        if (fail) throw new Error('quota');
        map.set(key, value);
      },
    },
  };
  try {
    const a = new FamilyService('owner-a', 'personal', browserFamilyPersistence);
    bind(a);
    a.grant();
    assert.ok(map.has(familyStateKey('owner-a')));
    assert.equal(
      new FamilyService('owner-b', 'personal', browserFamilyPersistence).readState().familySharing,
      'denied',
    );
    fail = true;
    assert.equal(a.revoke().ok, false);
    assert.equal(a.readState().familySharing, 'denied');
    assert.equal(a.lastSave.ok, false);
  } finally {
    delete (globalThis as { window?: unknown }).window;
  }
});
