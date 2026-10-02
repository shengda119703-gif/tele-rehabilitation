import { scopeKey, type OwnerScope } from '../archive/ArchiveService';
import type { NotificationPort, NotificationRecord } from '../notification/NotificationService';
export const notificationStorageKey = (scope: OwnerScope) => `ankang-route1-notifications-v2:${scopeKey(scope)}`;
export const browserNotificationPort: NotificationPort = {
  load(scope) {
    const raw = window.localStorage.getItem(notificationStorageKey(scope));
    if (!raw) return [];
    const records = JSON.parse(raw) as NotificationRecord[];
    if (
      !Array.isArray(records) ||
      records.some(
        (r) =>
          scopeKey(r) !== scopeKey(scope) ||
          typeof r.findingId !== 'string' ||
          typeof r.relationshipId !== 'string' ||
          !Array.isArray(r.deliveries),
      )
    )
      throw new Error('Invalid notification ledger');
    return records;
  },
  save(scope, records) {
    try {
      if (records.some((r) => scopeKey(r) !== scopeKey(scope))) throw new Error('Notification owner mismatch');
      window.localStorage.setItem(notificationStorageKey(scope), JSON.stringify(records));
      return { ok: true, storage: 'persistent' };
    } catch (error) {
      return { ok: false, error: String(error) };
    }
  },
};
