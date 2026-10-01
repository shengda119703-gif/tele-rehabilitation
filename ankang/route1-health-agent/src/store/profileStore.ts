import type { ElderProfile, UserRole } from '../types';
import { profile as demoProfile } from '../data/demo';

import type { StoredProfile, ProfileSaveResult, ProfilePersistence } from '../profile/ProfilePersistence';
import { normalizeMedicationProfile } from '../medication/medications';
export type { StoredProfile, DataMode } from '../profile/ProfilePersistence';
type LegacyStoredProfile = Omit<StoredProfile, 'ownerId'> & { ownerId?: string };

class ProfileStorageError extends Error {}

const KEY = 'ankang-route1-profile-v1';

function isValidProfile(value: unknown): value is ElderProfile {
  if (typeof value !== 'object' || value === null) return false;
  const candidate = value as Partial<ElderProfile>;
  return typeof candidate.name === 'string' && candidate.name.trim().length > 0;
}

/** 结构校验：旧版本/坏数据一律视为没有档案（与 PersistentHealthRecordStore 的容错一致）。 */
export function isValidStoredProfile(value: unknown): value is LegacyStoredProfile {
  if (typeof value !== 'object' || value === null) return false;
  const candidate = value as Partial<StoredProfile>;
  return candidate.version === 1 && isValidProfile(candidate.profile);
}

/** 读取本机档案；任何缺失/坏数据都按"没有档案"处理，回到首启选择。 */
export function loadStoredProfile(): StoredProfile | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as LegacyStoredProfile;
    if (!isValidStoredProfile(parsed)) return null;
    const stored: StoredProfile = {
      version: 1,
      ownerId: parsed.ownerId?.trim() || crypto.randomUUID(),
      profile:
        parsed.dataMode !== 'personal' && !parsed.profile.medicationRecords
          ? {
              ...parsed.profile,
              sex: parsed.profile.sex ?? 'female',
              medicationRecords: demoProfile.medicationRecords?.filter(
                (record) => record.status === 'stopped' || (parsed.profile.medications ?? []).includes(record.name),
              ),
            }
          : parsed.profile,
      dataMode: parsed.dataMode === 'personal' ? 'personal' : 'demo',
      preferredRole:
        parsed.preferredRole === 'elder' || parsed.preferredRole === 'family' ? parsed.preferredRole : undefined,
    };
    stored.profile = normalizeMedicationProfile(stored.profile);
    if (!parsed.ownerId || JSON.stringify(stored.profile) !== JSON.stringify(parsed.profile)) {
      const result = saveStoredProfile(stored);
      if (!result.ok) throw new ProfileStorageError(result.error);
    }
    return stored;
  } catch (error) {
    if (error instanceof ProfileStorageError) throw error;
    return null;
  }
}

export function saveStoredProfile(stored: StoredProfile): ProfileSaveResult {
  if (typeof window === 'undefined') return { ok: false, error: 'Browser storage unavailable' };
  try {
    window.localStorage.setItem(KEY, JSON.stringify(stored));
    return { ok: true, storage: 'persistent' };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : String(error) };
  }
}

export function clearStoredProfile(): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.removeItem(KEY);
  } catch {
    // 同上
  }
}

/** 演示档案（王秀兰奶奶）作为可选的首启入口，不再是唯一身份。 */
export function demoStoredProfile(preferredRole?: UserRole): StoredProfile {
  return {
    version: 1,
    ownerId: crypto.randomUUID(),
    profile: normalizeMedicationProfile({ ...demoProfile }),
    dataMode: 'demo',
    preferredRole,
  };
}

/** 建档起点：除了 familySharing 默认 ask，其余字段留白/中性默认。 */
export function emptyProfile(): ElderProfile {
  return {
    name: '',
    age: 0,
    conditions: [],
    medications: [],
    familyContact: '',
    familyPhone: '',
    communityDoctorPhone: '',
    mobility: 'independent',
    usesCane: false,
    nightVision: 'normal',
    cognition: 'stable',
    familySharing: 'ask',
  };
}

/** Compatibility adapter: one active local profile, not an account database. */
export const browserProfilePersistence: ProfilePersistence = {
  async loadProfile(ownerId) {
    const stored = loadStoredProfile();
    return stored?.ownerId === ownerId ? stored : null;
  },
  async saveProfile(ownerId, stored) {
    const current = loadStoredProfile();
    if (!current || current.ownerId !== ownerId || stored.ownerId !== ownerId || current.dataMode !== stored.dataMode) {
      return { ok: false, error: 'Profile owner or mode mismatch' };
    }
    return saveStoredProfile(stored);
  },
};
