import type { HealthRecordSnapshot } from '../store/HealthRecordStore';
import type { HealthEvent } from '../pipeline/events';

/** Tasks and sharing audit intentionally remain session-only, as upstream. */
export interface StoredSession {
  revision: number;
  health: HealthRecordSnapshot;
}
export type PersistenceReceipt =
  | { status: 'saved' | 'memory-only' | 'not-configured' | 'not-saved' | 'loaded' | 'pending'; revision: number }
  | { status: 'failed'; revision: number; error: string };

/** Trusted LOCAL storage only (contains private health data). Resolve after actual completion. */
export interface PersistencePort {
  load(sessionId: string): Promise<StoredSession | null>;
  save(sessionId: string, snapshot: StoredSession): Promise<'saved' | 'memory-only'>;
  clear(sessionId: string): Promise<'saved' | 'memory-only'>;
}

export interface DeliveryIntent {
  sessionId: string;
  revision: number;
  events: HealthEvent[];
  shareFindingIds: string[];
  shareFamilyEventIds: string[];
}
export type DeliveryReceipt = {
  status: 'not-requested' | 'not-configured' | 'accepted' | 'delivered' | 'failed';
  error?: string;
};
/** No transport imports in core. Host must enforce recipient consent and visibility. */
export interface DeliveryPort {
  deliver(intent: DeliveryIntent): Promise<Extract<DeliveryReceipt['status'], 'accepted' | 'delivered'>>;
}

/** Useful for embedded hosts/tests; never claims durable disk persistence. */
export class InMemoryPersistence implements PersistencePort {
  private readonly snapshots = new Map<string, StoredSession>();
  async load(id: string): Promise<StoredSession | null> {
    return structuredClone(this.snapshots.get(id) ?? null);
  }
  async save(id: string, snapshot: StoredSession): Promise<'memory-only'> {
    this.snapshots.set(id, structuredClone(snapshot));
    return 'memory-only';
  }
  async clear(id: string): Promise<'memory-only'> {
    this.snapshots.delete(id);
    return 'memory-only';
  }
}
