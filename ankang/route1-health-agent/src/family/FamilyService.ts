import type { Finding } from '../types';
import type { DataMode, ProfileSaveResult } from '../profile/ProfilePersistence';
import {
  performLinkHandshake,
  type LinkHandshakeOptions,
  type FamilyLinkPayload,
  type LinkConsentPayload,
} from '../engine/familyLinkHandshake';
import type { PrivacyIntent } from '../engine/privacy';
import { appendSharingAudit, type SharingAuditCandidate } from '../engine/sharingAuditRules';
import { consumeOneTimeShareIds } from '../engine/familyDisclosure';
import {
  emptyFamilyState,
  type FamilyState,
  type FamilyPersistence,
  type SharingRecord,
  type OwnedFamilyLink,
} from './FamilyPersistence';
import { buildFamilyProjection, type FamilyProjectionInput } from './projection';

export type FamilyLinkTransport = Omit<LinkHandshakeOptions, 'code'>;
export type BindFamilyOutcome = { ok: true } | { ok: false; reason: 'rejected' | 'unreachable'; detail?: string };
export type RemoteConsent = LinkConsentPayload;
const MAX_IDS = 50;

export function localConsentTimestamp(now = new Date()): string {
  const p = (v: number, width = 2) => String(v).padStart(width, '0');
  return `${now.getFullYear()}-${p(now.getMonth() + 1)}-${p(now.getDate())}T${p(now.getHours())}:${p(now.getMinutes())}:${p(now.getSeconds())}.${p(now.getMilliseconds(), 3)}`;
}
const INVITE_ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789';
export function createInviteCode(today: string): string {
  const random = new Uint32Array(10);
  if (typeof crypto !== 'undefined' && 'getRandomValues' in crypto) crypto.getRandomValues(random);
  else for (let i = 0; i < random.length; i++) random[i] = Math.floor(Math.random() * 0x100000000);
  let suffix = '';
  for (const value of random) suffix += INVITE_ALPHABET[value % INVITE_ALPHABET.length];
  return `AN-${today.slice(0, 4)}-${suffix}`;
}

export class FamilyService {
  private state: FamilyState;
  private invite: string | null = null;
  private bindingVersion = 0;
  private audit: SharingRecord[] = [];
  private listeners = new Set<() => void>();
  private prompted = new Set<string>();
  lastSave: ProfileSaveResult = { ok: true, storage: 'memory' };
  constructor(
    readonly ownerId: string,
    dataMode: DataMode,
    private port: FamilyPersistence,
  ) {
    if (!ownerId.trim()) throw new Error('ownerId is required');
    let loaded: FamilyState | null = null;
    try {
      loaded = port.loadFamilyState(ownerId);
    } catch (error) {
      this.lastSave = { ok: false, error: String(error) };
    }
    if (
      loaded &&
      (loaded.ownerId !== ownerId ||
        loaded.dataMode !== dataMode ||
        (loaded.familyLink && loaded.familyLink.ownerId !== ownerId))
    )
      throw new Error('Family owner or mode mismatch');
    this.state = loaded ?? emptyFamilyState(ownerId, dataMode);
  }
  /** Stable immutable-by-contract snapshot for useSyncExternalStore; public reads return copies. */
  getSnapshot = () => this.state;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };
  readState() {
    return structuredClone(this.state);
  }
  private update(patch: Partial<FamilyState>): ProfileSaveResult {
    const next = { ...this.state, ...patch };
    try {
      this.lastSave = this.port.saveFamilyState(this.ownerId, next);
    } catch (error) {
      this.lastSave = { ok: false, error: String(error) };
    }
    // Revocation remains effective in this session even if durable storage fails.
    this.state = next;
    for (const listener of this.listeners) listener();
    return this.lastSave;
  }
  grant(now = localConsentTimestamp()) {
    return this.update({ familySharing: 'granted', consentUpdatedAt: now, remoteConsent: null });
  }
  revoke() {
    return this.update({
      familySharing: 'denied',
      consentUpdatedAt: '',
      remoteConsent: null,
      sharedFindingIds: [],
      sharedFamilyEventIds: [],
    });
  }
  promptFamilyShare() {
    if (this.state.familySharing === 'denied') this.update({ familySharing: 'ask' });
  }
  promptForFindings(findings: Finding[]) {
    if (this.state.familySharing !== 'denied') return;
    const incoming = findings.filter(
      (f) => f.familyEligible === true && ['alert', 'urgent'].includes(f.severity) && !this.prompted.has(f.id),
    );
    if (!incoming.length) return;
    for (const f of incoming) this.prompted.add(f.id);
    this.promptFamilyShare();
  }
  generateInvite(today: string): string {
    this.bindingVersion++;
    const code = createInviteCode(today);
    this.invite = code;
    const id = `family-${crypto.randomUUID()}`;
    this.update({
      familyLink: {
        id,
        ownerId: this.ownerId,
        relation: '家属',
        displayName: '待绑定',
        maskedContact: '未绑定',
        inviteCode: code,
        status: 'pending',
        recipient: { id: `recipient:${id}`, type: 'family', displayName: '待绑定' },
      },
      remoteConsent: null,
      sharedFindingIds: [],
      sharedFamilyEventIds: [],
    });
    return code;
  }
  private ownedLink(link: FamilyLinkPayload): OwnedFamilyLink {
    return {
      ...link,
      ownerId: this.ownerId,
      recipient: {
        id: `recipient:${link.id}`,
        type: link.relation === '女儿' ? 'daughter' : link.relation === '儿子' ? 'son' : 'family',
        displayName: link.displayName,
      },
    };
  }
  confirmLinkRequest(code: string): FamilyLinkPayload | null {
    if (!code || code !== this.invite || this.state.familyLink?.status !== 'pending') return null;
    const link = this.ownedLink({
      ...this.state.familyLink,
      displayName: '已通过邀请码绑定的家属',
      maskedContact: '已验证邀请码',
      status: 'active',
    });
    this.invite = null;
    this.bindingVersion++;
    this.update({ familyLink: link });
    return structuredClone(link);
  }
  async bindFamily(inviteCode: string, transport?: FamilyLinkTransport): Promise<BindFamilyOutcome> {
    const code = inviteCode.trim();
    if (!code) return { ok: false, reason: 'rejected', detail: 'empty_code' };
    if (code === this.invite && this.confirmLinkRequest(code)) return { ok: true };
    if (!transport) return { ok: false, reason: 'rejected', detail: 'code_mismatch' };
    const version = ++this.bindingVersion;
    const result = await performLinkHandshake({ code, ...transport });
    if (version !== this.bindingVersion) return { ok: false, reason: 'rejected', detail: 'stale_binding' };
    if (!result.ok) return result;
    if (result.link.status !== 'active' || result.link.inviteCode !== code)
      return { ok: false, reason: 'rejected', detail: 'code_mismatch' };
    this.invite = null;
    this.update({
      familyLink: this.ownedLink(result.link),
      remoteConsent: result.consent ?? null,
      familySharing: result.consent?.sharing ?? 'denied',
      consentUpdatedAt: result.consent?.updatedAt ?? '',
      sharedFindingIds: [],
      sharedFamilyEventIds: [],
    });
    return { ok: true };
  }
  unbind() {
    this.bindingVersion++;
    this.invite = null;
    return this.update({ familyLink: null, remoteConsent: null, sharedFindingIds: [], sharedFamilyEventIds: [] });
  }
  applyRemoteConsent(next: RemoteConsent, relationshipId: string) {
    if (this.state.familyLink?.status !== 'active' || relationshipId !== this.state.familyLink.id) return;
    if ((next.sharing !== 'granted' && next.sharing !== 'denied') || typeof next.updatedAt !== 'string') return;
    if (this.state.remoteConsent?.sharing === next.sharing && this.state.remoteConsent.updatedAt === next.updatedAt)
      return;
    this.update({
      remoteConsent: { ...next },
      familySharing: next.sharing,
      consentUpdatedAt: next.updatedAt,
      ...(next.sharing === 'denied' ? { sharedFindingIds: [], sharedFamilyEventIds: [] } : {}),
    });
  }
  shareFindingIds(ids: string[]) {
    this.shareIds('sharedFindingIds', ids);
  }
  shareFamilyEventIds(ids: string[]) {
    this.shareIds('sharedFamilyEventIds', ids);
  }
  private shareIds(key: 'sharedFindingIds' | 'sharedFamilyEventIds', ids: string[]) {
    if (!ids.length || this.state.familyLink?.status !== 'active') return;
    this.update({ [key]: [...new Set([...this.state[key], ...ids])].slice(-MAX_IDS) });
  }
  consumeOneTime(scope: 'self' | 'family', ids: string[]) {
    const key = scope === 'self' ? 'sharedFindingIds' : 'sharedFamilyEventIds';
    return this.update({ [key]: consumeOneTimeShareIds(this.state[key], ids) });
  }
  appendSharingRecords(entries: SharingAuditCandidate[], intent: PrivacyIntent = 'none') {
    if (intent === 'private' || intent === 'no_record') return;
    const link = this.state.familyLink;
    const valid = appendSharingAudit([], entries).filter((e) => e.shareMode !== 'private');
    this.audit = [
      ...this.audit,
      ...valid.map((e) => ({
        ...e,
        ownerId: this.ownerId,
        relationshipId: link?.status === 'active' ? link.id : null,
        recipientId: link?.status === 'active' ? link.recipient.id : null,
        stage: 'planned' as const,
      })),
    ].slice(-100);
  }
  readSharingRecords() {
    return structuredClone(this.audit);
  }
  project(input: FamilyProjectionInput) {
    return buildFamilyProjection(this.state, input);
  }
  close() {
    this.bindingVersion++;
    this.invite = null;
    this.audit = [];
    this.listeners.clear();
  }
}
