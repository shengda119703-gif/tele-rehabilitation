import { appendSharingAudit, type SharingAuditEntry, type SharingAuditCandidate } from './sharingAuditRules';
export * from './sharingAuditRules';

const LEGACY_SHARING_AUDIT_KEY = 'ankang-route1-sharing-audit-v1';
const DEFAULT_LIMIT = 100;
let sessionAudit: SharingAuditEntry[] = [];

function cloneEntries(entries: SharingAuditEntry[]): SharingAuditEntry[] {
  return entries.map((entry) => ({ ...entry }));
}

/** Session-only audit. Sensitive sharing content is never restored from browser persistence. */
export function loadSharingAudit(): SharingAuditEntry[] {
  if (typeof window !== 'undefined') {
    window.localStorage.removeItem(LEGACY_SHARING_AUDIT_KEY);
  }
  return cloneEntries(sessionAudit);
}

export function saveSharingAudit(entries: SharingAuditEntry[]): void {
  sessionAudit = cloneEntries(entries.slice(-DEFAULT_LIMIT));
}

export function clearSharingAudit(): void {
  sessionAudit = [];
  if (typeof window !== 'undefined') {
    window.localStorage.removeItem(LEGACY_SHARING_AUDIT_KEY);
  }
}

export function recordSharingAudit(next: SharingAuditCandidate[]): void {
  if (next.length === 0) return;
  saveSharingAudit(appendSharingAudit(sessionAudit, next));
}
