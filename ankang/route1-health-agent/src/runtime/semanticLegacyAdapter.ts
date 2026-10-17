import type { ChatMessage } from '../types';
import { parseElderInput } from '../engine/agent';
import { mergeClauseStatus } from '../engine/llmUnderstanding';
import {
  understandElderInput, understandElderInputWithOverrides,
  type ClaimStatus, type StructuredElderInput,
} from '../engine/understanding';
import type { SemanticMention, SemanticTurn } from './semanticRouter';

export interface SemanticLegacyAdaptation {
  ruleUnderstanding: StructuredElderInput;
  understanding: StructuredElderInput;
  /** No durable writes until conflicting or incomplete factual evidence is clarified. */
  needsClarification: boolean;
}

const CLARIFICATION = '这句话里症状是否发生、指的是谁还需要核对。我先不新增或更改健康记录，请把每个人的症状及是否发生分别说清楚。';

/**
 * Reuse the existing polarity merge; never infer a new tag, subject or date.
 * A mention must cover a whole current clause, and every rule tag in that
 * clause must have the same explicit judgment. Partial/mixed evidence cannot
 * safely become one persisted event, so the caller keeps it pending instead.
 */
export function adaptSemanticUnderstanding(
  text: string, today: string, priorChat: ChatMessage[], semantic: SemanticTurn,
): SemanticLegacyAdaptation {
  const ruleUnderstanding = understandElderInput(text, today, priorChat);
  const current = semantic.mentions.filter((mention) => mention.kind === 'symptom' &&
    mention.source_message_id === undefined && mention.status !== undefined);
  if (!current.length) return { ruleUnderstanding, understanding: ruleUnderstanding, needsClarification: false };
  const statusOverrides = new Map<string, ClaimStatus>();
  const matched = new Set<SemanticMention>();
  let needsClarification = false;
  for (const claim of ruleUnderstanding.claims) {
    const candidates = current.filter((mention) => claim.text.includes(mention.text));
    if (!candidates.length) continue;
    candidates.forEach((mention) => matched.add(mention));
    const complete = candidates.every((mention) => mention.evidence === claim.text &&
      text.includes(mention.evidence) && mention.evidence.includes(mention.text) &&
      mention.subject === claim.subject && mention.subject !== 'unknown');
    const statuses = new Set(candidates.map((mention) => mention.status!));
    const coveredTags = new Set(candidates.flatMap((mention) => parseElderInput(mention.text).tags));
    if (!complete || statuses.size !== 1 || !claim.tags.length || claim.hasHealthValue || claim.outcome ||
        !claim.tags.every((tag) => coveredTags.has(tag))) {
      needsClarification = true;
      continue;
    }
    const proposed = candidates[0].status!;
    const merged = mergeClauseStatus(claim.status, proposed);
    // Preserve the old strong-signal priority. If its occurred/non-occurred
    // disagreement is outside that merger's supported polarity pair, clarify.
    if (merged === 'occurred' && proposed !== 'occurred') {
      needsClarification = true;
      continue;
    }
    if (merged !== claim.status) statusOverrides.set(claim.text, merged);
  }
  if (current.some((mention) => !matched.has(mention))) needsClarification = true;
  const understanding = statusOverrides.size
    ? understandElderInputWithOverrides(text, today, priorChat, statusOverrides)
    : ruleUnderstanding;
  return { ruleUnderstanding, understanding: needsClarification
    ? { ...understanding, clarificationQuestion: CLARIFICATION } : understanding, needsClarification };
}
