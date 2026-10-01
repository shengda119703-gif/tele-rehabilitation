import type { CareTask, FamilyHealthEvent, Finding, HealthMeasurement, PrivacyScope } from '../types';
import type { HealthEvent } from '../pipeline/events';
import { isPublicHealthEvent } from '../pipeline/events';
import { measurementsToDayRecords } from '../data/normalize';
import { canShareWithFamily, type PrivacyIntent } from '../engine/privacy';
import { familyVisibleFindings, familyVisibleTasksForSharing } from '../engine/familyDisclosure';
import { visibleFamilyEvents } from '../engine/familyLedger';
import type { FamilyState } from './FamilyPersistence';

export function effectiveFamilySharing(state: FamilyState) {
  return state.remoteConsent?.sharing ?? state.familySharing;
}
export interface FactPermissionInput {
  ownerId: string;
  id: string;
  scope: 'self' | 'family';
  visibility?: PrivacyScope;
  intent: PrivacyIntent;
  shareMode?: 'private' | 'persistent' | 'one_time';
}
/** A permission is not a plan, transport receipt or acknowledgement. */
export function familyPermission(state: FamilyState, fact: FactPermissionInput) {
  const link = state.familyLink;
  const ids = fact.scope === 'self' ? state.sharedFindingIds : state.sharedFamilyEventIds;
  const explicit = fact.intent === 'share_family' || ids.includes(fact.id);
  const allowed =
    fact.ownerId === state.ownerId &&
    link?.ownerId === state.ownerId &&
    link.status === 'active' &&
    fact.visibility !== 'private' &&
    fact.shareMode !== 'private' &&
    fact.intent !== 'private' &&
    fact.intent !== 'no_record' &&
    (fact.shareMode !== 'one_time' || explicit) &&
    canShareWithFamily(effectiveFamilySharing(state), explicit ? 'share_family' : fact.intent);
  return {
    allowed: Boolean(allowed),
    recipient: allowed ? structuredClone(link!.recipient) : null,
    status: 'permission' as const,
  };
}
export interface FamilyProjectionInput {
  ownerId: string;
  findings: Finding[];
  tasks: CareTask[];
  familyEvents: FamilyHealthEvent[];
  measurements: HealthMeasurement[];
  /** Upstream omits no_record facts entirely. Optional ingress intents enforce that gate too. */
  selfEvents?: HealthEvent[];
  privacyIntents?: Record<string, PrivacyIntent>;
}
export function buildFamilyProjection(state: FamilyState, input: FamilyProjectionInput) {
  if (state.ownerId !== input.ownerId) throw new Error('Family projection owner mismatch');
  const bound = state.familyLink?.ownerId === state.ownerId && state.familyLink.status === 'active';
  const sharing = bound ? effectiveFamilySharing(state) : 'denied';
  const canViewSharedDetail = Boolean(bound && sharing === 'granted');
  const intent = (id: string) => input.privacyIntents?.[id] ?? 'none';
  const findings = familyVisibleFindings(input.findings).filter(
    (f) => familyPermission(state, { ownerId: input.ownerId, id: f.id, scope: 'self', intent: intent(f.id) }).allowed,
  );
  const familyEvents = bound
    ? visibleFamilyEvents(input.familyEvents, sharing, state.sharedFamilyEventIds).filter(
        (e) =>
          ['spouse', 'father', 'mother', 'family_other'].includes(e.subject) &&
          familyPermission(state, {
            ownerId: input.ownerId,
            id: e.id,
            scope: 'family',
            visibility: e.visibility,
            shareMode: e.shareMode,
            intent: intent(e.id),
          }).allowed,
      )
    : [];
  const measurements = canViewSharedDetail
    ? input.measurements.filter((m) => m.visibility !== 'private' && !['private', 'no_record'].includes(intent(m.id)))
    : [];
  const selfEvents = canViewSharedDetail
    ? (input.selfEvents ?? []).filter(
        (e) =>
          ['measurement', 'observation', 'labResult'].includes(e.type) &&
          isPublicHealthEvent(e) &&
          !['private', 'no_record'].includes(intent(e.id)),
      )
    : [];
  return structuredClone({
    ownerId: state.ownerId,
    recipient: bound ? state.familyLink!.recipient : null,
    canViewSharedDetail,
    findings,
    familyEvents,
    selfEvents,
    tasks: familyVisibleTasksForSharing(input.tasks, findings, sharing),
    records: measurementsToDayRecords(measurements),
    status: 'permission' as const,
  });
}
export type FamilyProjection = ReturnType<typeof buildFamilyProjection>;
