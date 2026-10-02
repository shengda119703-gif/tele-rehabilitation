/**
 * Test-only reference transcription of ef5a767d's useElderChat.runElderTurn,
 * useCareTasks effects and App derived state. No imports from src/runtime.
 * IDs/clock/setters are supplied by the harness instead of React/Math.random.
 * Preserve the original correction gate and App's ignored medication timestamp.
 */
import type { CareTask, ChatMessage, ElderProfile } from '../../src/types';
import type { HealthRecordSnapshot } from '../../src/store/HealthRecordStore';
import { understandElderInput } from '../../src/engine/understanding';
import { ruleBasedAdapter } from '../../src/engine/agent';
import { planElderTurn } from '../../src/engine/elderTurn';
import { parsePrivacyIntent } from '../../src/engine/privacy';
import { appendHealthEvents, materializeHealthData } from '../../src/pipeline/events';
import { removeCorrectedChatHealthEvents, removeCorrectedFamilyEvents } from '../../src/engine/correction';
import { appendSharingAudit, type SharingAuditEntry } from '../../src/engine/sharingAudit';
import { runDetection } from '../../src/engine/detect';
import { buildAgentContext } from '../../src/engine/context';
import { createTaskFromFinding } from '../../src/engine/tasks';

export interface LegacyState extends HealthRecordSnapshot {
  tasks: CareTask[];
  audit: SharingAuditEntry[];
  sharedFamilyEventIds: string[];
  sharedFindingIds: string[];
}

export async function legacyReactTurn(
  state: LegacyState,
  profile: ElderProfile,
  text: string,
  today: string,
  now: string,
  receivedAt: string,
  sourceMessageId: string,
  replyId: string,
  idSeed: number,
) {
  const priorChat = state.chat;
  const understanding = understandElderInput(text, today, priorChat);
  const findings = runDetection(state.events, today);
  const plan = await planElderTurn({
    text,
    understanding,
    priorChat,
    findings,
    events: state.events,
    familySharing: profile.familySharing,
    agentContext: buildAgentContext(profile, state.events, today, findings),
    llmAdapter: ruleBasedAdapter,
    today,
    now,
    receivedAt,
    sourceMessageId,
    idSeed,
    sharingAudit: state.audit,
  });
  const { correction } = plan;
  if (correction) state.familyEvents = removeCorrectedFamilyEvents(state.familyEvents, correction.messageId);
  if (plan.familyEventsToAppend.length > 0) state.familyEvents = [...state.familyEvents, ...plan.familyEventsToAppend];
  if (plan.sharingAuditEntries.length > 0) state.audit = appendSharingAudit(state.audit, plan.sharingAuditEntries);
  if (plan.shareFamilyEventIds.length > 0)
    state.sharedFamilyEventIds = [...new Set([...state.sharedFamilyEventIds, ...plan.shareFamilyEventIds])];
  if (plan.eventsToAppend.length > 0) {
    state.events = appendHealthEvents(
      correction ? removeCorrectedChatHealthEvents(state.events, correction.messageId, correction.tags) : state.events,
      plan.eventsToAppend,
    );
    if (plan.shareFindingIds.length > 0)
      state.sharedFindingIds = [...new Set([...state.sharedFindingIds, ...plan.shareFindingIds])];
  }
  function medication() {
    if (state.tasks.some((task) => task.kind === 'medication_check' && task.dueDate === today)) return;
    const medList = profile.medications.length
      ? profile.medications.map((m) => `• ${m}`).join('\n')
      : '• （暂无录入的药物）';
    state.tasks.push({
      id: `task-medication-${today}`,
      title: '💊 今天的药',
      description: `${medList}\n\n按原来的医生方案服用；不要自行加倍或调整药量。`,
      dueDate: today,
      status: 'pending',
      createdAt: `${today}T08:00:00`,
      kind: 'medication_check',
    });
  }
  if (plan.medicationMissed) medication();
  const persisted = parsePrivacyIntent(text) !== 'no_record';
  const reply: ChatMessage = {
    id: replyId,
    role: 'agent',
    text: plan.replyText,
    time: now,
    persisted,
    safetyAction: plan.safetyAction,
    blocks: plan.replyBlocks,
  };
  state.chat = [...state.chat, { id: sourceMessageId, role: 'elder', text, time: now, persisted }, reply];
  const healthData = materializeHealthData(state.events);
  const nextFindings = runDetection(state.events, today);
  const agentContext = buildAgentContext(profile, state.events, today, nextFindings);
  const actionable = nextFindings.filter((finding) => finding.severity === 'alert' || finding.severity === 'urgent');
  const currentFindingIds = new Set(nextFindings.map((finding) => finding.id));
  state.tasks = state.tasks.filter(
    (task) => !task.sourceFindingId || currentFindingIds.has(task.sourceFindingId) || task.status === 'completed',
  );
  for (const finding of actionable.slice(0, 2)) {
    const task = createTaskFromFinding(finding, today);
    if (task && !state.tasks.some((item) => item.id === task.id)) state.tasks.push(task);
  }
  if (profile.medications.length) medication();
  return { state, reply, understanding, plan, healthData, findings: nextFindings, agentContext };
}
