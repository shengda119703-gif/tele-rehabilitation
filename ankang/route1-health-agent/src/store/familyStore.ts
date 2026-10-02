import type { FamilyPersistence, FamilyState } from '../family/FamilyPersistence';
import { durableFamilyState } from '../family/FamilyPersistence';

export const familyStateKey = (ownerId: string) => `ankang-route1-family-state-v2:${encodeURIComponent(ownerId)}`;
/** Old unowned v1 data is deliberately not assigned to whichever profile happens to open it. */
export const browserFamilyPersistence: FamilyPersistence = {
  loadFamilyState(ownerId) {
    if (typeof window === 'undefined') return null;
    const raw = window.localStorage.getItem(familyStateKey(ownerId));
    if (!raw) return null;
    const state = JSON.parse(raw) as FamilyState;
    if (
      state.version !== 2 ||
      state.ownerId !== ownerId ||
      !['demo', 'personal'].includes(state.dataMode) ||
      !['granted', 'denied', 'ask'].includes(state.familySharing) ||
      typeof state.consentUpdatedAt !== 'string' ||
      !Array.isArray(state.sharedFindingIds) ||
      !Array.isArray(state.sharedFamilyEventIds) ||
      !state.sharedFindingIds.every((id) => typeof id === 'string') ||
      !state.sharedFamilyEventIds.every((id) => typeof id === 'string')
    )
      throw new Error('Invalid owner-scoped family state');
    const link = state.familyLink;
    if (
      link &&
      (link.ownerId !== ownerId ||
        link.status !== 'active' ||
        !['id', 'relation', 'displayName', 'maskedContact', 'inviteCode'].every(
          (k) => typeof link[k as keyof typeof link] === 'string',
        ) ||
        !link.recipient ||
        typeof link.recipient.id !== 'string' ||
        !['daughter', 'son', 'family'].includes(link.recipient.type))
    )
      throw new Error('Invalid family relationship');
    if (
      state.remoteConsent &&
      (!['granted', 'denied'].includes(state.remoteConsent.sharing) ||
        typeof state.remoteConsent.updatedAt !== 'string')
    )
      throw new Error('Invalid remote consent');
    return {
      ...state,
      sharedFindingIds: state.sharedFindingIds.slice(-50),
      sharedFamilyEventIds: state.sharedFamilyEventIds.slice(-50),
    };
  },
  saveFamilyState(ownerId, state) {
    if (ownerId !== state.ownerId) return { ok: false, error: 'Family owner mismatch' };
    try {
      if (typeof window === 'undefined') throw new Error('Browser storage unavailable');
      const current = this.loadFamilyState(ownerId);
      if (current && current.dataMode !== state.dataMode) throw new Error('Family mode mismatch');
      window.localStorage.setItem(familyStateKey(ownerId), JSON.stringify(durableFamilyState(state)));
      return { ok: true, storage: 'persistent' };
    } catch (error) {
      return { ok: false, error: String(error) };
    }
  },
};
