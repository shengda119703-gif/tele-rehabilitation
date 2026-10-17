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
import { ruleBasedAdapter } from '../engine/agent';
import { runDetection } from '../engine/detect';
import { adaptSemanticUnderstanding } from './semanticLegacyAdapter';
import type { SemanticTurn } from './semanticRouter';

export async function prepareTurn(
  request: Omit<ElderTurnRequest, 'understanding'>,
  config: UnderstandingLlmConfig | null = null,
  semantic: SemanticTurn | null = null,
) {
  const intent = parsePrivacyIntent(request.text);
  if (semantic && intent === 'none') {
    const adapted = adaptSemanticUnderstanding(request.text, request.today, request.priorChat, semantic);
    // This is a pure local guard: no second model call and no event application.
    const rulePlan = await planElderTurn({ ...request, understanding: adapted.ruleUnderstanding, llmAdapter: ruleBasedAdapter });
    // Reuse the clinical engine itself: untrusted polarity must not erase an
    // urgent fact or its future detection, not merely the current warning text.
    if (runDetection(appendHealthEvents(request.events, rulePlan.eventsToAppend), request.today)
      .some(finding => finding.severity === 'urgent')) return { understanding: adapted.ruleUnderstanding, plan: rulePlan };
    let plan = adapted.understanding === adapted.ruleUnderstanding ? rulePlan
      : await planElderTurn({ ...request, understanding: adapted.understanding, llmAdapter: ruleBasedAdapter });
    if (adapted.needsClarification) {
      plan = { ...plan, correction: null, eventsToAppend: [], familyEventsToAppend: [],
        sharingAuditEntries: [], shareFamilyEventIds: [], shareFindingIds: [], medicationMissed: false, toast: '',
        replyText: adapted.understanding.clarificationQuestion!,
        replyBlocks: [{ kind: 'main', text: adapted.understanding.clarificationQuestion! }] };
    }
    // Existing clinical safety remains independent of untrusted model polarity.
    // Retain only safety wording, never a discarded plan's "saved" receipt.
    if (rulePlan.safetyAction) {
      const safetyText = rulePlan.replyBlocks.filter(block => block.kind === 'main').map(block => block.text).join('\n');
      const main = plan.replyBlocks.filter(block => block.kind === 'main').map(block => block.text).join('\n');
      const text = safetyText === main ? main : [safetyText, main].filter(Boolean).join('\n\n');
      const otherBlocks = plan.replyBlocks.filter(block => block.kind !== 'main');
      plan = { ...plan, safetyAction: true, replyBlocks: [{ kind: 'main', text }, ...otherBlocks],
        replyText: [text, ...otherBlocks.map(block => block.text)].join('\n') };
    }
    return { understanding: adapted.understanding, plan };
  }
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
