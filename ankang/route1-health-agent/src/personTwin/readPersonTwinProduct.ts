import { METRICS } from '../types';
import { buildPersonTwin } from '../engine/personTwin';
import type { CareTask, ElderProfile, FamilyHealthEvent } from '../types';
import type { HealthEvent } from '../pipeline/events';
import { deriveHealthState } from '../runtime/derive';
import type { FamilyState } from '../family/FamilyPersistence';
import { buildFamilyProjection } from '../family/projection';
import type { OwnerScope, Viewer } from '../archive/ArchiveService';
export interface PersonTwinReadInput extends OwnerScope {
  profile: ElderProfile;
  events: HealthEvent[];
  tasks: CareTask[];
  familyEvents?: FamilyHealthEvent[];
  family: FamilyState;
  today: string;
  asOf: string;
}
/** Read model only: no cache or database; the original algorithms remain the sole implementation. */
export function readPersonTwinProduct(input: PersonTwinReadInput, viewer: Viewer = 'self') {
  if (input.family.ownerId !== input.ownerId || input.family.dataMode !== input.dataMode)
    throw new Error('Person Twin owner/mode mismatch');
  const derived = deriveHealthState(input.profile, input.events, input.today);
  const projection = buildFamilyProjection(input.family, {
    ownerId: input.ownerId,
    findings: derived.findings,
    tasks: input.tasks,
    familyEvents: input.familyEvents ?? [],
    measurements: derived.healthData.measurements,
    selfEvents: input.events,
  });
  const familyAllowed = projection.canViewSharedDetail;
  const familyTwin = familyAllowed
    ? buildPersonTwin(input.profile, projection.selfEvents, projection.findings, input.today)
    : null;
  const events = viewer === 'self' ? input.events : projection.selfEvents;
  const tasks = viewer === 'self' ? input.tasks : projection.tasks;
  return {
    ownerId: input.ownerId,
    asOf: input.asOf,
    dataUpdatedAt:
      events
        .map((e) => e.timestamp)
        .sort()
        .slice(-1)[0] ?? null,
    personTwin: viewer === 'self' ? derived.personTwin : familyTwin,
    publicPersonTwin: viewer === 'self' ? derived.agentContext.personTwinPublic : familyTwin,
    findings: viewer === 'self' ? derived.findings : projection.findings,
    tasksSummary: {
      pending: tasks.filter((t) => t.status === 'pending').length,
      inProgress: tasks.filter((t) => t.status === 'in_progress').length,
      completed: tasks.filter((t) => t.status === 'completed').length,
    },
    recentEvents: [...events]
      .sort((a, b) => b.timestamp.localeCompare(a.timestamp))
      .slice(0, 10)
      .map((e) => ({
        id: e.id,
        type: e.type,
        timestamp: e.timestamp,
        source: e.source,
        summary:
          e.type === 'observation'
            ? e.observation.text
            : e.type === 'measurement'
              ? `${METRICS[e.measurement.metric].label} ${e.measurement.value} ${e.measurement.unit}`
              : `${e.labResult.name} ${e.labResult.value} ${e.labResult.unit}`,
      })),
  };
}
