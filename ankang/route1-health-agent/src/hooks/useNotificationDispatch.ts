import { useCallback, useEffect, useMemo, useSyncExternalStore } from 'react';
import type { Finding } from '../types';
import type { DeliverFn } from '../engine/notify';
import type { FamilyService } from '../family/FamilyService';
import type { OwnerScope } from '../archive/ArchiveService';
import { NotificationService, type NotificationRecord } from '../notification/NotificationService';
import { browserNotificationPort } from '../store/BrowserNotificationPort';
import { browserFamilyDelivery, browserOnlyDelivery } from '../adapters/FamilyNotificationDelivery';
interface Options extends OwnerScope {
  findings: Finding[];
  familyService: FamilyService;
  canDispatch?: boolean;
  deliver?: DeliverFn;
}
/** React subscribes and schedules; permission, dedup, retry and ledger belong to the service. */
export function useNotificationDispatch({
  ownerId,
  dataMode,
  findings,
  familyService,
  canDispatch = true,
  deliver,
}: Options) {
  const service = useMemo(
    () => new NotificationService({ ownerId, dataMode }, () => familyService.readState(), browserNotificationPort),
    [ownerId, dataMode, familyService],
  );
  const snapshot = useSyncExternalStore(service.subscribe, service.getSnapshot, service.getSnapshot);
  const family = useSyncExternalStore(familyService.subscribe, familyService.getSnapshot, familyService.getSnapshot);
  useEffect(() => {
    service.resume();
    return () => service.close();
  }, [service]);
  useEffect(() => {
    if (canDispatch) {
      void service
        .retryBrowser(browserOnlyDelivery)
        .then(() => service.dispatch(findings, deliver ?? browserFamilyDelivery))
        .catch((error) => console.warn('[notification]', error));
    }
  }, [service, findings, deliver, canDispatch, family]);
  const acknowledge = useCallback((id: string) => service.acknowledge(id), [service]);
  const mergeRecord = useCallback((record: NotificationRecord) => service.mergeRecord(record), [service]);
  const records = useMemo(() => service.read('family'), [service, snapshot, family]);
  return {
    records,
    service,
    persistence: service.lastSave,
    pendingUnacknowledged: records.filter((r) => r.lifecycle === 'new').length,
    acknowledge,
    mergeRecord,
    mergeAcknowledge: acknowledge,
  };
}
