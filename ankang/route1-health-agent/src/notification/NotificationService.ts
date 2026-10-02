import { collectFamilyNotifications } from '../engine/escalate';
import type { Finding } from '../types';
import type { FamilyState } from '../family/FamilyPersistence';
import { effectiveFamilySharing, familyPermission } from '../family/projection';
import {
  planFamilyNotifications,
  acknowledgeNotification,
  sortNotificationRecords,
  ledgerRecordToNotification,
  isRecordFromToday,
  type FamilyNotificationRecord,
  type DeliveryOutcome,
  type DeliverFn,
} from '../engine/notify';
import type { OwnerScope, Viewer } from '../archive/ArchiveService';
import { scopeKey } from '../archive/ArchiveService';
import type { ProfileSaveResult } from '../profile/ProfilePersistence';
export interface NotificationRecord extends FamilyNotificationRecord, OwnerScope {
  relationshipId: string;
  sessionId: string;
  shareMode: 'persistent' | 'one_time';
  phase: 'pending' | 'accepted' | 'sent' | 'delivered' | 'failed' | 'unavailable';
}
export interface NotificationPort {
  load(scope: OwnerScope): NotificationRecord[];
  save(scope: OwnerScope, records: NotificationRecord[]): ProfileSaveResult;
}
export class InMemoryNotificationPort implements NotificationPort {
  private data = new Map<string, NotificationRecord[]>();
  load(scope: OwnerScope) {
    return structuredClone(this.data.get(scopeKey(scope)) ?? []);
  }
  save(scope: OwnerScope, records: NotificationRecord[]): ProfileSaveResult {
    if (records.some((r) => scopeKey(r) !== scopeKey(scope)))
      return { ok: false, error: 'Notification owner mismatch' };
    this.data.set(scopeKey(scope), structuredClone(records));
    return { ok: true, storage: 'memory' };
  }
}
function phase(outcomes: DeliveryOutcome[]): NotificationRecord['phase'] {
  for (const status of ['delivered', 'sent', 'accepted', 'failed', 'unavailable'] as const)
    if (outcomes.some((o) => o.status === status)) return status;
  return 'pending';
}
export class NotificationService {
  readonly sessionId = crypto.randomUUID();
  private records: NotificationRecord[];
  private listeners = new Set<() => void>();
  private queue: Promise<unknown> = Promise.resolve();
  private retryDone = new Set<string>();
  private closed = false;
  private loadFailed = false;
  private restoredIds = new Set<string>();
  lastSave: ProfileSaveResult = { ok: true, storage: 'memory' };
  constructor(
    readonly scope: OwnerScope,
    private family: () => FamilyState,
    private port: NotificationPort,
  ) {
    scopeKey(scope);
    this.records = [];
    try {
      this.records = port.load(scope);
    } catch (error) {
      this.loadFailed = true;
      this.lastSave = { ok: false, error: String(error) };
    }
    this.restoredIds = new Set(this.records.map((r) => r.findingId));
    if (this.records.some((r) => scopeKey(r) !== scopeKey(scope))) throw new Error('Notification owner mismatch');
  }
  getSnapshot = () => this.records;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };
  private save(records: NotificationRecord[]) {
    this.records = sortNotificationRecords(records) as NotificationRecord[];
    try {
      this.lastSave = this.port.save(this.scope, this.records);
    } catch (error) {
      this.lastSave = { ok: false, error: String(error) };
    }
    for (const listener of this.listeners) listener();
  }
  private allowed(id: string, relationshipId?: string) {
    const state = this.family();
    return (
      state.dataMode === this.scope.dataMode &&
      (!relationshipId || state.familyLink?.id === relationshipId) &&
      familyPermission(state, { ownerId: this.scope.ownerId, id, scope: 'self', intent: 'none' }).allowed
    );
  }
  read(viewer: Viewer = 'self') {
    return structuredClone(
      this.records.filter((r) => viewer === 'self' || this.allowed(r.findingId, r.relationshipId)),
    );
  }
  async dispatch(findings: Finding[], deliver: DeliverFn, now = new Date().toISOString(), canDispatch = true) {
    const operation = this.queue.then(async () => {
      if (this.closed || this.loadFailed || !canDispatch) return;
      // Re-read persisted IDs before reservation; simultaneous tabs still require an adapter-level lock.
      const stored = this.port.load(this.scope);
      if (stored.some((r) => scopeKey(r) !== scopeKey(this.scope))) throw new Error('Notification owner mismatch');
      this.records = [
        ...this.records,
        ...stored.filter((r) => !this.records.some((known) => known.findingId === r.findingId)),
      ];
      const state = this.family();
      if (state.ownerId !== this.scope.ownerId || state.dataMode !== this.scope.dataMode)
        throw new Error('Notification family mismatch');
      const plans = planFamilyNotifications(
        findings.filter((f) => this.allowed(f.id)),
        effectiveFamilySharing(state),
        state.familyLink?.status === 'active',
        this.records,
        now,
        state.sharedFindingIds,
      );
      for (const { notification, record } of plans) {
        if (this.closed || !this.allowed(record.findingId, state.familyLink?.id)) break;
        const pending: NotificationRecord = {
          ...record,
          ...this.scope,
          sessionId: this.sessionId,
          relationshipId: state.familyLink!.id,
          shareMode: state.sharedFindingIds.includes(record.findingId) ? 'one_time' : 'persistent',
          phase: 'pending',
        };
        this.save([...this.records, pending]);
        // Durable dedup must be reserved before external side effects; failure remains pending, not sent.
        if (!this.lastSave.ok) continue;
        let outcomes: DeliveryOutcome[];
        try {
          outcomes = await deliver(notification);
        } catch (error) {
          outcomes = [{ channel: 'browser_push', status: 'failed', detail: String(error) }];
        }
        if (this.closed) continue;
        this.save(
          this.records.map((r) =>
            r.findingId === pending.findingId
              ? { ...r, phase: phase(outcomes), deliveries: outcomes.map((o) => ({ ...o, at: now })) }
              : r,
          ),
        );
      }
    });
    this.queue = operation.catch(() => {});
    await operation;
    return this.read();
  }
  /** Existing policy: failed/unavailable browser push may retry once per service session; no webhook retry. */
  async retryBrowser(deliver: DeliverFn, now = new Date().toISOString()) {
    const operation = this.queue.then(async () => {
      for (const record of this.records) {
        if (
          this.closed ||
          this.loadFailed ||
          !this.restoredIds.has(record.findingId) ||
          record.lifecycle === 'acknowledged' ||
          this.retryDone.has(record.findingId) ||
          !this.allowed(record.findingId, record.relationshipId)
        )
          continue;
        if (
          !record.deliveries.some((d) => d.channel === 'browser_push' && ['failed', 'unavailable'].includes(d.status))
        )
          continue;
        this.retryDone.add(record.findingId);
        let outcomes: DeliveryOutcome[];
        try {
          outcomes = await deliver(ledgerRecordToNotification(record));
        } catch (error) {
          outcomes = [{ channel: 'browser_push', status: 'failed', detail: String(error) }];
        }
        if (this.closed) continue;
        this.save(
          this.records.map((r) =>
            r.findingId === record.findingId
              ? {
                  ...r,
                  deliveries: [
                    ...r.deliveries.filter((d) => d.channel !== 'browser_push'),
                    ...outcomes.filter((d) => d.channel === 'browser_push').map((d) => ({ ...d, at: now })),
                  ],
                  phase: phase([...r.deliveries.filter((d) => d.channel !== 'browser_push'), ...outcomes]),
                }
              : r,
          ),
        );
      }
    });
    this.queue = operation.catch(() => {});
    await operation;
  }
  acknowledge(findingId: string, now = new Date().toISOString()) {
    const record = this.records.find((r) => r.findingId === findingId);
    if (this.closed || this.loadFailed || !record || !this.allowed(findingId, record.relationshipId)) return;
    this.save(acknowledgeNotification(this.records, findingId, now) as NotificationRecord[]);
  }
  mergeRecord(incoming: NotificationRecord) {
    // Only records already carrying this owner and verified relationship are accepted; no identity remapping.
    if (this.closed || this.loadFailed) return;
    if (
      !incoming?.ownerId ||
      incoming.dataMode !== this.scope.dataMode ||
      scopeKey(incoming) !== scopeKey(this.scope) ||
      !this.allowed(incoming.findingId, incoming.relationshipId)
    )
      return;
    const known = this.records.find((r) => r.findingId === incoming.findingId);
    if (known?.lifecycle === 'acknowledged' && incoming.lifecycle !== 'acknowledged') return;
    this.save([...this.records.filter((r) => r.findingId !== incoming.findingId), structuredClone(incoming)]);
  }
  notifications(today: string) {
    return this.read('family')
      .filter((r) => r.lifecycle === 'new' || isRecordFromToday(r, today))
      .map((r) => ({ ...ledgerRecordToNotification(r), oneTime: r.shareMode === 'one_time' }));
  }
  viewNotifications(findings: Finding[], today: string) {
    const state = this.family();
    const current = collectFamilyNotifications(
      findings.filter((f) => this.allowed(f.id)),
      effectiveFamilySharing(state),
      state.sharedFindingIds,
      today,
    );
    const known = new Set(current.map((n) => n.finding.id));
    return [...current, ...this.notifications(today).filter((n) => !known.has(n.finding.id))];
  }
  resume() {
    this.closed = false;
  }
  close() {
    this.closed = true;
  }
}
