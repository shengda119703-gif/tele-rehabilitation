import { useCallback, useEffect, useMemo, useSyncExternalStore } from 'react';
import type { DataMode } from '../profile/ProfilePersistence';
import { FamilyService, type FamilyLinkTransport, type RemoteConsent } from '../family/FamilyService';
import { browserFamilyPersistence } from '../store/familyStore';
export { createInviteCode } from '../family/FamilyService';
export type { FamilyLinkTransport, BindFamilyOutcome, RemoteConsent } from '../family/FamilyService';

interface UseFamilyBindingOptions {
  ownerId: string;
  dataMode: DataMode;
  showToast: (text: string) => void;
  today: string;
}
/** React owns rendering/toasts only; all relationship and permission transitions belong to the service. */
export function useFamilyBinding({ ownerId, dataMode, showToast, today }: UseFamilyBindingOptions) {
  const service = useMemo(() => new FamilyService(ownerId, dataMode, browserFamilyPersistence), [ownerId, dataMode]);
  useEffect(() => () => service.close(), [service]);
  const state = useSyncExternalStore(service.subscribe, service.getSnapshot);
  const report = useCallback(
    (text?: string) => {
      if (!service.lastSave.ok) showToast(`家庭状态未保存，仅本次会话生效：${service.lastSave.error}`);
      else if (text) showToast(text);
    },
    [service, showToast],
  );
  useEffect(() => {
    report();
  }, [report, state]);
  const applyRemoteConsent = useCallback(
    (next: RemoteConsent, relationshipId: string) => {
      service.applyRemoteConsent(next, relationshipId);
      report();
    },
    [service, report],
  );
  return {
    ...state,
    service,
    promptFamilyShare: useCallback(() => {
      service.promptFamilyShare();
      report();
    }, [service, report]),
    requestFamilyShare: () => {
      service.grant();
      report(`已同意在必要时与家属共享。授权记录时间：${service.readState().consentUpdatedAt.slice(0, 10)}`);
    },
    keepFamilyPrivate: () => {
      service.revoke();
      report('好的，先不告诉家属。之后需要时，您可以再打开共享。');
    },
    revokeFamilyShare: () => {
      service.revoke();
      report('已暂停家属共享。之后的新变化不会继续提供给家属；已经告诉对方的内容，我不会假装它已经被撤回。');
    },
    generateInvite: () => {
      const code = service.generateInvite(today);
      report(`邀请码已生成：${code}（重新生成会使旧码失效）`);
    },
    bindFamily: async (code: string, transport?: FamilyLinkTransport) => {
      const result = await service.bindFamily(code, transport);
      report(result.ok ? '家属绑定成功。邀请码已失效。' : undefined);
      return result;
    },
    confirmLinkRequest: (code: string) => {
      const link = service.confirmLinkRequest(code);
      report();
      return link;
    },
    shareFindingIds: (ids: string[]) => {
      service.shareFindingIds(ids);
      report();
    },
    shareFamilyEventIds: (ids: string[]) => {
      service.shareFamilyEventIds(ids);
      report();
    },
    applyRemoteConsent,
    unbindFamily: () => {
      service.unbind();
      report('已解除本机与老人端的绑定。重新绑定时需要老人端出示新的邀请码。');
    },
  };
}
