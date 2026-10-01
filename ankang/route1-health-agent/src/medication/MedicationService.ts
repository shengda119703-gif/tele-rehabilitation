import type { MedicationRecord, ElderProfile } from '../types';
import type { ProfilePersistence, ProfileSaveResult, StoredProfile } from '../profile/ProfilePersistence';
import { listMedications, saveMedication, setMedicationStatus } from './medications';

export type MedicationSaveResult =
  | { ok: true; stored: StoredProfile; storage: 'persistent' | 'memory' }
  | { ok: false; error: string };

/** Thin owner-scoped service; persistence is injected, with no browser or React imports. */
export class MedicationService {
  constructor(private readonly persistence: ProfilePersistence) {}

  private async profile(ownerId: string): Promise<StoredProfile> {
    const stored = await this.persistence.loadProfile(ownerId);
    if (!stored || stored.ownerId !== ownerId) throw new Error('未找到当前用户档案，请重新打开档案。');
    return stored;
  }

  async list(ownerId: string): Promise<MedicationRecord[]> {
    return listMedications((await this.profile(ownerId)).profile);
  }

  save(ownerId: string, record: MedicationRecord): Promise<MedicationSaveResult> {
    return this.update(ownerId, (profile) => saveMedication(profile, record));
  }

  setStatus(ownerId: string, medicationId: string, status: MedicationRecord['status']): Promise<MedicationSaveResult> {
    return this.update(ownerId, (profile) => setMedicationStatus(profile, medicationId, status));
  }

  private async update(
    ownerId: string,
    change: (profile: ElderProfile) => ElderProfile,
  ): Promise<MedicationSaveResult> {
    try {
      const current = await this.profile(ownerId);
      const stored = { ...current, profile: change(current.profile) };
      const result: ProfileSaveResult = await this.persistence.saveProfile(ownerId, stored);
      return result.ok ? { ok: true, stored, storage: result.storage } : result;
    } catch (error) {
      return { ok: false, error: error instanceof Error ? error.message : String(error) };
    }
  }
}
