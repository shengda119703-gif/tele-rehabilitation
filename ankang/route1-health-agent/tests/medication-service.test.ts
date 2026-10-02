import test from 'node:test';
import assert from 'node:assert/strict';
import { MedicationService } from '../src/medication/MedicationService';
import {
  createMedicationDraft,
  saveMedication,
  normalizeMedicationProfile,
  withLegacyMedications,
} from '../src/medication/medications';
import { InMemoryProfilePersistence, type StoredProfile } from '../src/profile/ProfilePersistence';
import {
  emptyProfile,
  loadStoredProfile,
  saveStoredProfile,
  browserProfilePersistence,
} from '../src/store/profileStore';

const initial = (): StoredProfile => ({
  version: 1,
  ownerId: 'owner-1',
  dataMode: 'personal',
  profile: { ...emptyProfile(), name: '李奶奶' },
});
const key = 'ankang-route1-profile-v1';

void test('add/edit/stop/resume preserve full fields and stable medication ID', async () => {
  const port = new InMemoryProfilePersistence([initial()]);
  const service = new MedicationService(port);
  const record = { ...createMedicationDraft(), name: ' 药物甲 ', dose: '1 片', purpose: '按医嘱', times: '08:00' };
  assert.equal((await service.save('owner-1', record)).ok, true);
  let records = await service.list('owner-1');
  assert.deepEqual(records, [{ ...record, name: '药物甲' }]);
  assert.equal(
    (await service.save('owner-1', { ...records[0], name: '药物乙', dose: '2 片', purpose: '新医嘱', times: '20:00' }))
      .ok,
    true,
  );
  await service.setStatus('owner-1', record.id, 'stopped');
  assert.deepEqual((await port.loadProfile('owner-1'))?.profile.medications, []);
  await service.setStatus('owner-1', record.id, 'active');
  records = await service.list('owner-1');
  assert.deepEqual(records, [{ ...record, name: '药物乙', dose: '2 片', purpose: '新医嘱', times: '20:00' }]);
  assert.deepEqual((await port.loadProfile('owner-1'))?.profile.medications, ['药物乙']);
});

void test('legacy strings migrate without guessing dose; profile form preserves IDs and stopped details', () => {
  const old = { ...initial().profile, medications: ['药物甲 5mg', '药物乙'] };
  const normalized = normalizeMedicationProfile(old);
  const id = normalized.medicationRecords![0].id;
  const reordered = normalizeMedicationProfile({ ...old, medications: [...old.medications].reverse() });
  assert.equal(reordered.medicationRecords![1].id, id);
  assert.equal(normalized.medicationRecords![0].dose, '');
  const stopped = withLegacyMedications(normalized, ['药物乙', '药物丙']);
  assert.equal(stopped.medicationRecords![0].status, 'stopped');
  assert.deepEqual(stopped.medications, ['药物乙', '药物丙']);
  const resumed = withLegacyMedications(stopped, ['药物甲 5mg', '药物乙']);
  assert.equal(resumed.medicationRecords![0].id, id);
  assert.equal(resumed.medicationRecords![0].status, 'active');
  assert.deepEqual(normalizeMedicationProfile(resumed), resumed);
  const renamed = saveMedication(normalized, { ...normalized.medicationRecords![0], name: '新药名' });
  const readded = withLegacyMedications(renamed, ['新药名', '药物甲 5mg']);
  assert.equal(new Set(readded.medicationRecords!.map((record) => record.id)).size, readded.medicationRecords!.length);
  assert.equal(readded.medicationRecords!.find((record) => record.name === '新药名')!.id, id);
});

void test('owners and demo/personal are separate; display-name changes do not change ownership', async () => {
  const first = initial();
  const second: StoredProfile = { ...initial(), ownerId: 'demo-2', dataMode: 'demo' };
  const port = new InMemoryProfilePersistence([first, second]);
  const service = new MedicationService(port);
  await service.save(first.ownerId, { ...createMedicationDraft(), name: '药物甲' });
  assert.deepEqual(await service.list(second.ownerId), []);
  const loaded = (await port.loadProfile(first.ownerId))!;
  assert.equal(
    (await port.saveProfile(first.ownerId, { ...loaded, profile: { ...loaded.profile, name: '新称呼' } })).ok,
    true,
  );
  assert.equal((await service.list(first.ownerId)).length, 1);
  assert.equal((await port.saveProfile(first.ownerId, second)).ok, false);
  assert.equal((await port.saveProfile(first.ownerId, { ...loaded, dataMode: 'demo' })).ok, false);
});

void test('browser migration is durable; save failure keeps persisted data and returns failure', async () => {
  let raw = JSON.stringify({
    version: 1,
    dataMode: 'personal',
    profile: { ...initial().profile, medications: ['旧药'] },
  });
  let fail = false;
  (globalThis as { window?: unknown }).window = {
    localStorage: {
      getItem: () => raw,
      setItem: (_key: string, value: string) => {
        if (fail) throw new Error('quota exceeded');
        raw = value;
      },
    },
  };
  try {
    const loaded = loadStoredProfile()!;
    assert.ok(loaded.ownerId);
    assert.equal(loadStoredProfile()!.ownerId, loaded.ownerId);
    assert.equal(loadStoredProfile()!.profile.medicationRecords![0].id, loaded.profile.medicationRecords![0].id);
    const before = raw;
    fail = true;
    const result = await new MedicationService(browserProfilePersistence).save(loaded.ownerId, {
      ...createMedicationDraft(),
      name: '新药',
    });
    assert.equal(result.ok, false);
    if (!result.ok) assert.match(result.error, /quota/);
    assert.equal(saveStoredProfile(loaded).ok, false);
    assert.equal(raw, before);
    raw = JSON.stringify({ version: 1, dataMode: 'personal', profile: initial().profile });
    const legacy = raw;
    assert.throws(() => loadStoredProfile(), /quota/);
    assert.equal(raw, legacy);
  } finally {
    delete (globalThis as { window?: unknown }).window;
  }
});
