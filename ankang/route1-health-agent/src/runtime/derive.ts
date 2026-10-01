import type { ElderProfile } from '../types';
import { materializeHealthData, type HealthEvent } from '../pipeline/events';
import { runDetection } from '../engine/detect';
import { buildAgentContext } from '../engine/context';

/** Shared by App and the headless session; context builds both Person Twins. */
export function deriveHealthState(profile: ElderProfile, events: HealthEvent[], today: string) {
  const healthData = materializeHealthData(events);
  const findings = runDetection(events, today);
  const agentContext = buildAgentContext(profile, events, today, findings);
  return { healthData, findings, agentContext, personTwin: agentContext.personTwin };
}
