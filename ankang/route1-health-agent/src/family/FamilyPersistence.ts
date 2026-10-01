import type { FamilyLink, FamilySharing } from '../types';
import type { DataMode, ProfileSaveResult } from '../profile/ProfilePersistence';
import type { LinkConsentPayload } from '../engine/familyLinkHandshake';
import type { SharingAuditEntry, SharingRecipient } from '../engine/sharingAuditRules';

export interface FamilyRecipient {
  id: string;
  type: SharingRecipient;
  displayName: string;
}
export interface OwnedFamilyLink extends FamilyLink {
  ownerId: string;
  recipient: FamilyRecipient;
}
export interface FamilyState {
  version: 2;
  ownerId: string;
  dataMode: DataMode;
  familySharing: FamilySharing;
  consentUpdatedAt: string;
  familyLink: OwnedFamilyLink | null;
  remoteConsent: LinkConsentPayload | null;
  sharedFindingIds: string[];
  sharedFamilyEventIds: string[];
}
export interface SharingRecord extends SharingAuditEntry {
  ownerId: string;
  relationshipId: string | null;
  recipientId: string | null;
  /** Permission/planning evidence only, never a delivery receipt. */
  stage: 'planned';
}
/** Synchronous local port: browser and memory adapters. No network/account contract. */
export interface FamilyPersistence {
  loadFamilyState(ownerId: string): FamilyState | null;
  saveFamilyState(ownerId: string, state: FamilyState): ProfileSaveResult;
}
export function emptyFamilyState(ownerId: string, dataMode: DataMode): FamilyState {
  if (!ownerId.trim()) throw new Error('ownerId is required');
  return {
    version: 2,
    ownerId,
    dataMode,
    familySharing: 'denied',
    consentUpdatedAt: '',
    familyLink: null,
    remoteConsent: null,
    sharedFindingIds: [],
    sharedFamilyEventIds: [],
  };
}
/** Pending invitation credentials and sensitive audit content remain session-only. */
export function durableFamilyState(state: FamilyState): FamilyState {
  return structuredClone({ ...state, familyLink: state.familyLink?.status === 'active' ? state.familyLink : null });
}
export class InMemoryFamilyPersistence implements FamilyPersistence {
  private states = new Map<string, FamilyState>();
  loadFamilyState(ownerId: string) {
    return structuredClone(this.states.get(ownerId) ?? null);
  }
  saveFamilyState(ownerId: string, state: FamilyState): ProfileSaveResult {
    if (
      ownerId !== state.ownerId ||
      (this.states.get(ownerId)?.dataMode && this.states.get(ownerId)!.dataMode !== state.dataMode)
    )
      return { ok: false, error: 'Family owner or mode mismatch' };
    this.states.set(ownerId, durableFamilyState(state));
    return { ok: true, storage: 'memory' };
  }
}
