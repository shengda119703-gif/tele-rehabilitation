import type { ChatMessage, FamilyHealthEvent } from '../types';
import { appendHealthEvents, type HealthEvent } from '../pipeline/events';
import { understandElderInput } from '../engine/understanding';
import {
  canUseLlmUnderstanding,
  understandElderInputWithLlm,
  type UnderstandingLlmConfig,
} from '../engine/llmUnderstanding';
import { parsePrivacyIntent } from '../engine/privacy';
import { planElderTurn, type ElderTurnRequest, type ElderTurnPlan } from '../engine/elderTurn';
import { removeCorrectedChatHealthEvents, removeCorrectedFamilyEvents } from '../engine/correction';
import type { SharingAuditCandidate } from '../engine/sharingAudit';

export async function prepareTurn(
  request: Omit<ElderTurnRequest, 'understanding'>,
  config: UnderstandingLlmConfig | null = null,
) {
  const intent = parsePrivacyIntent(request.text);
  const understanding = canUseLlmUnderstanding(intent, config !== null)
    ? await understandElderInputWithLlm(request.text, request.today, request.priorChat, config!)
    : understandElderInput(request.text, request.today, request.priorChat);
  const plan = await planElderTurn({ ...request, understanding });
  return { understanding, plan };
}

export interface TurnApplication {
  updateFamily: (update: (current: FamilyHealthEvent[]) => FamilyHealthEvent[]) => void;
  recordAudit: (entries: SharingAuditCandidate[]) => void;
  shareFamily: (ids: string[]) => void;
  updateEvents: (update: (current: HealthEvent[]) => HealthEvent[]) => void;
  broadcast: (events: HealthEvent[]) => void;
  shareFindings: (ids: string[]) => void;
  medicationMissed: () => void;
}

/** The original hook's execution order, including its correction-only limitation. */
export function applyTurnPlan(plan: ElderTurnPlan, target: TurnApplication): void {
  const { correction } = plan;
  if (correction) target.updateFamily((current) => removeCorrectedFamilyEvents(current, correction.messageId));
  if (plan.familyEventsToAppend.length > 0)
    target.updateFamily((current) => [...current, ...plan.familyEventsToAppend]);
  if (plan.sharingAuditEntries.length > 0) target.recordAudit(plan.sharingAuditEntries);
  if (plan.shareFamilyEventIds.length > 0) target.shareFamily(plan.shareFamilyEventIds);
  if (plan.eventsToAppend.length > 0) {
    target.updateEvents((current) =>
      appendHealthEvents(
        correction ? removeCorrectedChatHealthEvents(current, correction.messageId, correction.tags) : current,
        plan.eventsToAppend,
      ),
    );
    target.broadcast(plan.eventsToAppend);
    if (plan.shareFindingIds.length > 0) target.shareFindings(plan.shareFindingIds);
  }
  if (plan.medicationMissed) target.medicationMissed();
}

export function settlePendingReply(current: ChatMessage[], pendingId: string, reply: ChatMessage): ChatMessage[] {
  const index = current.findIndex((item) => item.id === pendingId);
  if (index < 0) return [...current, reply];
  const next = [...current];
  next[index] = { ...reply, id: pendingId };
  return next;
}
