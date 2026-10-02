import type { ElderProfile, MedicationRecord } from '../types';

/** Existing structured records win over same-name legacy entries, including stopped ones. */
export function listMedications(profile: ElderProfile): MedicationRecord[] {
  const saved = (profile.medicationRecords ?? []).map((record) => ({ ...record }));
  const occurrences = new Map<string, number>();
  const usedIds = new Set(saved.map((record) => record.id));
  const legacy = (profile.medications ?? [])
    .filter((name) => !saved.some((record) => record.name === name))
    .map((name) => {
      let occurrence = occurrences.get(name) ?? 0;
      let id = `legacy:${encodeURIComponent(name)}:${occurrence}`;
      // A renamed record still owns its old ID; re-adding the old name must not reuse it.
      while (usedIds.has(id)) id = `legacy:${encodeURIComponent(name)}:${++occurrence}`;
      usedIds.add(id);
      occurrences.set(name, occurrence + 1);
      return {
        // Stable even when unrelated legacy entries are reordered or removed.
        id,
        name,
        dose: '',
        purpose: '',
        times: '',
        status: 'active' as const,
      };
    });
  return [...saved, ...legacy];
}

export function withMedicationRecords(profile: ElderProfile, records: MedicationRecord[]): ElderProfile {
  return {
    ...profile,
    medicationRecords: records.map((record) => ({ ...record })),
    medications: records.filter((record) => record.status === 'active').map((record) => record.name),
  };
}

export function normalizeMedicationProfile(profile: ElderProfile): ElderProfile {
  return withMedicationRecords(profile, listMedications(profile));
}

export function createMedicationDraft(): MedicationRecord {
  return { id: crypto.randomUUID(), name: '', dose: '', purpose: '', times: '', status: 'active' };
}

/** Same add/edit semantics as the original page: replace by ID, append the saved record. */
export function saveMedication(profile: ElderProfile, draft: MedicationRecord): ElderProfile {
  if (!draft.id || !draft.name.trim()) throw new Error('请填写药物名称。');
  if (draft.status !== 'active' && draft.status !== 'stopped') throw new Error('药物状态无效。');
  const records = listMedications(profile).filter((record) => record.id !== draft.id);
  return withMedicationRecords(profile, [...records, { ...draft, name: draft.name.trim() }]);
}

export function setMedicationStatus(
  profile: ElderProfile,
  id: string,
  status: MedicationRecord['status'],
): ElderProfile {
  const record = listMedications(profile).find((item) => item.id === id);
  if (!record) throw new Error('药物记录不存在。');
  return saveMedication(profile, { ...record, status });
}

/** Profile form's existing string-list semantics: omitted records stop; included records resume. */
export function withLegacyMedications(profile: ElderProfile, names: string[]): ElderProfile {
  return normalizeMedicationProfile({
    ...profile,
    medications: names,
    medicationRecords: listMedications(profile).map((record) => ({
      ...record,
      status: names.includes(record.name) ? 'active' : 'stopped',
    })),
  });
}
