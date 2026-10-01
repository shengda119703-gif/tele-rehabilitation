import type { ElderProfile, UserRole } from '../types';

export type DataMode = 'demo' | 'personal';
export interface StoredProfile {
  version: 1;
  /** Local stable identity; never derived from a person's display name. */
  ownerId: string;
  dataMode: DataMode;
  profile: ElderProfile;
  preferredRole?: UserRole;
}
export type ProfileSaveResult = { ok: true; storage: 'persistent' | 'memory' } | { ok: false; error: string };

export interface ProfilePersistence {
  loadProfile(ownerId: string): Promise<StoredProfile | null>;
  saveProfile(ownerId: string, profile: StoredProfile): Promise<ProfileSaveResult>;
}

/** Test/embedded adapter. Memory success is explicitly not durable storage. */
export class InMemoryProfilePersistence implements ProfilePersistence {
  private readonly profiles = new Map<string, StoredProfile>();
  constructor(initial: StoredProfile[] = []) {
    for (const profile of initial) this.profiles.set(profile.ownerId, structuredClone(profile));
  }
  async loadProfile(ownerId: string): Promise<StoredProfile | null> {
    return structuredClone(this.profiles.get(ownerId) ?? null);
  }
  async saveProfile(ownerId: string, profile: StoredProfile): Promise<ProfileSaveResult> {
    const current = this.profiles.get(ownerId);
    if (!ownerId || ownerId !== profile.ownerId || (current && current.dataMode !== profile.dataMode)) {
      return { ok: false, error: 'Profile owner or mode mismatch' };
    }
    this.profiles.set(ownerId, structuredClone(profile));
    return { ok: true, storage: 'memory' };
  }
}
