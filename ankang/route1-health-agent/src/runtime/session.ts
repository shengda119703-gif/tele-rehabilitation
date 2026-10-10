import type { CareTask, ChatMessage, ElderProfile } from '../types';
import type { HealthRecordSnapshot } from '../store/HealthRecordStore';
import type { LlmAdapter } from '../engine/agent';
import { ruleBasedAdapter } from '../engine/agent';
import type { UnderstandingLlmConfig } from '../engine/llmUnderstanding';
import { parsePrivacyIntent } from '../engine/privacy';
import { appendSharingAudit, type SharingAuditEntry } from '../engine/sharingAudit';
import { createTurnQueue } from '../engine/turnQueue';
import { buildInitialTasks } from '../engine/tasks';
import { prepareTurn, applyTurnPlan } from './turn';
import { prepareRehabReply, type RehabToolPort } from './rehabTools';
import { deriveHealthState } from './derive';
import { changeTaskStatus, ensureMedicationTask, reconcileCareTasks } from './careTasks';
import type { DeliveryPort, DeliveryReceipt, PersistencePort, PersistenceReceipt, StoredSession } from './ports';
import type { CareCoordinator } from '../care/CareCoordinator';

const copy = <T>(value: T): T => structuredClone(value);
const emptyHealth = (): HealthRecordSnapshot => ({ events: [], familyEvents: [], chat: [] });
function wallClock(now: Date) {
  if (!Number.isFinite(now.getTime())) throw new Error('Invalid turn clock');
  const pad = (n: number, width = 2) => `${n}`.padStart(width, '0');
  const today = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
  return {
    today,
    label: `${today.slice(5)} ${pad(now.getHours())}:${pad(now.getMinutes())}`,
    receivedAt: `${today}T${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}.${pad(now.getMilliseconds(), 3)}`,
  };
}

export interface OpenSessionOptions {
  sessionId: string;
  profile: ElderProfile;
  now: Date;
  initialHealth?: HealthRecordSnapshot;
  persistence?: PersistencePort;
  delivery?: DeliveryPort;
  replyAdapter?: LlmAdapter;
  understandingLlm?: UnderstandingLlmConfig | null;
  rehabTools?: RehabToolPort;
  careTools?: Pick<CareCoordinator, 'replyToText'>;
}
export interface TurnInput {
  text: string;
  now: Date;
  /** Optional optimistic concurrency check, performed when the turn starts. */
  expectedRevision?: number;
}
export interface SessionSnapshot extends HealthRecordSnapshot, ReturnType<typeof deriveHealthState> {
  sessionId: string;
  revision: number;
  generation: number;
  today: string;
  tasks: CareTask[];
  audit: SharingAuditEntry[];
  sharedFindingIds: string[];
  sharedFamilyEventIds: string[];
  persistence: PersistenceReceipt;
  delivery: DeliveryReceipt;
}

export class SessionInvalidatedError extends Error {
  constructor() {
    super('Session closed or reset; turn result discarded');
  }
}

class Session {
  private state!: SessionSnapshot;
  private readonly queue = createTurnQueue();
  private generation = 0;
  private closed = false;
  private sequence = 0;
  private idSeed = 0;
  constructor(private readonly options: OpenSessionOptions) {}

  async initialize() {
    // A failed read rejects open. Never overwrite an unread history with empty state.
    const stored = await this.options.persistence?.load(this.options.sessionId);
    this.state = this.initial(
      copy(stored?.health ?? this.options.initialHealth ?? emptyHealth()),
      this.options.now,
      stored?.revision ?? 0,
    );
    if (stored) this.state.persistence = { status: 'loaded', revision: stored.revision };
    // Continue IDs across reopen (including imported legacy chat), not just within one process.
    this.sequence = this.state.chat.reduce(
      (max, message) => Math.max(max, Number(message.id.match(/:(\d+)$/)?.[1] ?? 0)),
      this.state.chat.length,
    );
    for (const event of this.state.events) {
      const seed = event.id.match(/(?:obs-live-|chat-value-)(\d+)/)?.[1];
      if (seed) this.idSeed = Math.max(this.idSeed, Number(seed));
    }
    return this.read();
  }

  private initial(health: HealthRecordSnapshot, now: Date, revision: number): SessionSnapshot {
    const { today } = wallClock(now);
    const derived = deriveHealthState(this.options.profile, health.events, today);
    let tasks = reconcileCareTasks(buildInitialTasks(today), derived.findings, today);
    if (this.options.profile.medications.length)
      tasks = ensureMedicationTask(tasks, today, this.options.profile.medications);
    return {
      ...health,
      ...derived,
      tasks,
      today,
      revision,
      generation: this.generation,
      sessionId: this.options.sessionId,
      audit: [],
      sharedFindingIds: [],
      sharedFamilyEventIds: [],
      persistence: { status: this.options.persistence ? 'not-saved' : 'not-configured', revision },
      delivery: { status: 'not-requested' },
    };
  }

  private check(generation = this.generation) {
    if (this.closed || generation !== this.generation) throw new SessionInvalidatedError();
  }
  read(): SessionSnapshot {
    this.check();
    if (this.state.generation !== this.generation) throw new SessionInvalidatedError();
    return copy(this.state);
  }

  process(input: TurnInput) {
    this.check();
    const generation = this.generation;
    const captured = { ...input, now: new Date(input.now) };
    const clock = wallClock(captured.now);
    const sequence = ++this.sequence;
    const sourceMessageId = `${this.options.sessionId}:${generation}:elder:${sequence}`;
    return this.queue.enqueue(async () => {
      this.check(generation);
      if (captured.expectedRevision !== undefined && captured.expectedRevision !== this.state.revision) {
        throw new Error(`Revision conflict: expected ${captured.expectedRevision}, current ${this.state.revision}`);
      }
      const draft = copy(this.state);
      // Recompute before planning, too: a queued turn crossing midnight must not use yesterday's context.
      Object.assign(draft, deriveHealthState(this.options.profile, draft.events, clock.today));
      const persisted = parsePrivacyIntent(captured.text) !== 'no_record';
      const elder: ChatMessage = {
        id: sourceMessageId,
        role: 'elder',
        text: captured.text,
        time: clock.label,
        persisted,
      };
      this.idSeed = Math.max(this.idSeed + 1, captured.now.getTime());
      let { understanding, plan } = await prepareTurn(
        {
          text: captured.text,
          priorChat: draft.chat,
          events: draft.events,
          findings: draft.findings,
          agentContext: draft.agentContext,
          familySharing: this.options.profile.familySharing,
          sharingAudit: draft.audit,
          llmAdapter: this.options.replyAdapter ?? ruleBasedAdapter,
          today: clock.today,
          now: clock.label,
          receivedAt: clock.receivedAt,
          sourceMessageId,
          idSeed: this.idSeed,
        },
        this.options.understandingLlm,
      );
      this.check(generation);
      const privacyIntent = parsePrivacyIntent(captured.text);
      let rehab: Awaited<ReturnType<typeof prepareRehabReply>> = null;
      let care: Awaited<ReturnType<CareCoordinator['replyToText']>> = null;
      if (this.options.careTools && privacyIntent === 'none' && !plan.safetyAction && !plan.correction &&
        !plan.medicationMissed && !plan.eventsToAppend.length && !plan.familyEventsToAppend.length &&
        !plan.sharingAuditEntries.length && !plan.shareFindingIds.length && !plan.shareFamilyEventIds.length) {
        care = await this.options.careTools.replyToText(captured.text, captured.now, sourceMessageId);
        this.check(generation);
        if (care) plan = { ...plan, replyText: care.reply, replyBlocks: [{kind:'main',text:care.reply}], toast:'' };
      }
      // Keep original safety/correction/sharing paths. Private turns never reach the model or host tool.
      if (
        this.options.rehabTools &&
        !care &&
        privacyIntent === 'none' &&
        !plan.safetyAction &&
        !plan.correction &&
        !plan.medicationMissed &&
        !plan.eventsToAppend.length &&
        !plan.familyEventsToAppend.length &&
        !plan.sharingAuditEntries.length &&
        !plan.shareFindingIds.length &&
        !plan.shareFamilyEventIds.length
      ) {
        rehab = await prepareRehabReply(this.options.rehabTools, captured.text, () => this.check(generation));
        this.check(generation);
        if (rehab) plan = rehab.plan;
      }
      let broadcastEvents: typeof draft.events = [];
      let shareFindingIds: string[] = [];
      let shareFamilyEventIds: string[] = [];
      applyTurnPlan(plan, {
        updateFamily: (update) => {
          draft.familyEvents = update(draft.familyEvents);
        },
        recordAudit: (entries) => {
          draft.audit = appendSharingAudit(draft.audit, entries);
        },
        shareFamily: (ids) => {
          shareFamilyEventIds = ids;
          draft.sharedFamilyEventIds = [...new Set([...draft.sharedFamilyEventIds, ...ids])];
        },
        updateEvents: (update) => {
          draft.events = update(draft.events);
        },
        broadcast: (events) => {
          broadcastEvents = events;
        },
        shareFindings: (ids) => {
          shareFindingIds = ids;
          draft.sharedFindingIds = [...new Set([...draft.sharedFindingIds, ...ids])];
        },
        // App historically ignored the callback timestamp; retain its 08:00 default.
        medicationMissed: () => {
          draft.tasks = ensureMedicationTask(draft.tasks, clock.today, this.options.profile.medications);
        },
      });
      const reply: ChatMessage = {
        id: `${this.options.sessionId}:${generation}:agent:${sequence}`,
        role: 'agent',
        text: plan.replyText,
        time: clock.label,
        persisted,
        safetyAction: plan.safetyAction,
        blocks: plan.replyBlocks,
      };
      draft.chat.push(elder, reply);
      Object.assign(draft, deriveHealthState(this.options.profile, draft.events, clock.today));
      draft.tasks = reconcileCareTasks(draft.tasks, draft.findings, clock.today);
      if (this.options.profile.medications.length)
        draft.tasks = ensureMedicationTask(draft.tasks, clock.today, this.options.profile.medications);
      draft.today = clock.today;
      draft.revision += 1;
      draft.persistence = { status: 'pending', revision: draft.revision };
      draft.delivery = { status: 'not-requested' };
      this.state = draft; // Atomic in-memory commit; side-effect failure does not undo accepted facts.
      draft.persistence = await this.save(draft);
      this.check(generation);
      // Private/no_record never invoke an external delivery port, even if a private event was appended.
      const privacy = parsePrivacyIntent(captured.text);
      if (
        privacy !== 'private' &&
        privacy !== 'no_record' &&
        (broadcastEvents.length || shareFamilyEventIds.length || shareFindingIds.length)
      ) {
        if (!this.options.delivery) draft.delivery = { status: 'not-configured' };
        else {
          try {
            draft.delivery = {
              status: await this.options.delivery.deliver(
                copy({
                  sessionId: draft.sessionId,
                  revision: draft.revision,
                  events: broadcastEvents,
                  shareFindingIds,
                  shareFamilyEventIds,
                }),
              ),
            };
          } catch (error) {
            draft.delivery = { status: 'failed', error: String(error) };
          }
        }
      }
      this.check(generation);
      return copy({
        reply,
        replyBlocks: plan.replyBlocks,
        understanding,
        appliedChanges: plan,
        sourceMessageId,
        snapshot: draft,
        findings: draft.findings,
        personTwin: draft.personTwin,
        tasks: draft.tasks,
        persistence: draft.persistence,
        delivery: draft.delivery,
        revision: draft.revision,
        ...(rehab ? { rehab: { call: rehab.call, data: rehab.data } } : {}),
        ...(care ? { care } : {}),
      });
    });
  }

  private async save(state: SessionSnapshot): Promise<PersistenceReceipt> {
    if (!this.options.persistence) return { status: 'not-configured', revision: state.revision };
    const stored: StoredSession = {
      revision: state.revision,
      health: {
        events: state.events,
        familyEvents: state.familyEvents,
        chat: state.chat.filter((item) => item.persisted !== false),
      },
    };
    try {
      return { status: await this.options.persistence.save(state.sessionId, copy(stored)), revision: state.revision };
    } catch (error) {
      return { status: 'failed', revision: state.revision, error: String(error) };
    }
  }

  updateTask(id: string, status: CareTask['status']) {
    this.check();
    const generation = this.generation;
    return this.queue.enqueue(async () => {
      this.check(generation);
      this.state.tasks = changeTaskStatus(this.state.tasks, id, status);
      this.state.revision += 1;
      // Tasks are deliberately session-only; save only the health snapshot/revision.
      this.state.persistence = await this.save(this.state);
      this.check(generation);
      return this.read();
    });
  }

  reset(now: Date) {
    this.check();
    const captured = new Date(now);
    wallClock(captured);
    const generation = ++this.generation; // Immediately invalidate planning and already queued turns.
    return this.queue.enqueue(async () => {
      this.check(generation);
      this.state = this.initial(emptyHealth(), captured, this.state.revision + 1);
      if (this.options.persistence) {
        try {
          this.state.persistence = {
            status: await this.options.persistence.clear(this.options.sessionId),
            revision: this.state.revision,
          };
        } catch (error) {
          this.state.persistence = { status: 'failed', revision: this.state.revision, error: String(error) };
        }
      }
      this.check(generation);
      return this.read();
    });
  }

  close() {
    this.closed = true;
    ++this.generation;
    // Drain already-started port calls before permitting the same ID to reopen.
    return this.queue.enqueue(async () => {
      this.state = undefined!;
    });
  }
}

/** One registry per host; never share a session ID between different users. */
export class AgentRuntime {
  private readonly sessions = new Map<string, Session>();
  private readonly opening = new Set<string>();
  async openSession(options: OpenSessionOptions): Promise<SessionSnapshot> {
    if (!options.sessionId || this.sessions.has(options.sessionId) || this.opening.has(options.sessionId))
      throw new Error('Session already open or invalid ID');
    this.opening.add(options.sessionId);
    const session = new Session({
      ...options,
      profile: copy(options.profile),
      understandingLlm: options.understandingLlm && copy(options.understandingLlm),
      initialHealth: options.initialHealth && copy(options.initialHealth),
      now: new Date(options.now),
    });
    try {
      const snapshot = await session.initialize();
      this.sessions.set(options.sessionId, session);
      return snapshot;
    } finally {
      this.opening.delete(options.sessionId);
    }
  }
  private get(id: string): Session {
    const session = this.sessions.get(id);
    if (!session) throw new Error(`Session not open: ${id}`);
    return session;
  }
  processTurn(id: string, input: TurnInput) {
    return this.get(id).process(input);
  }
  readSnapshot(id: string) {
    return this.get(id).read();
  }
  resetSession(id: string, now: Date) {
    return this.get(id).reset(now);
  }
  updateTaskStatus(id: string, taskId: string, status: CareTask['status']) {
    return this.get(id).updateTask(taskId, status);
  }
  async closeSession(id: string) {
    const session = this.get(id);
    await session.close();
    if (this.sessions.get(id) === session) this.sessions.delete(id);
  }
}
