import { hostAsPeer, connectToPeer, type PeerConfig, type HostHandle, type GuestHandle } from '../adapters/PeerJSCrossDevice';
import type { SyncPort } from '../product/ExtensionPorts';
/** Transport extracted from useCrossDeviceSync. Browser/WebRTC host only; Node cannot impersonate WebRTC. */
export async function openBrowserSync(role:'elder'|'family', inviteCode?:string, config?:PeerConfig): Promise<SyncPort> {
  const tabId = crypto.randomUUID();
  const handlers = new Set<(envelope:{type:string;payload:unknown}) => void>();
  let status:ReturnType<SyncPort['status']> = {mode:'local-only', detail:'仅本地同浏览器协同', peerId:null};
  let peer:HostHandle|GuestHandle|undefined;
  const channel = !inviteCode && typeof BroadcastChannel !== 'undefined' ? new BroadcastChannel('ankang-route1-cross-tab') : undefined;
  const receive = (raw:unknown) => {
    const e = raw as {tabId?:string;type?:string;payload?:unknown};
    if (!e || e.tabId === tabId || typeof e.type !== 'string') return;
    for (const handler of handlers) handler(raw as {type:string;payload:unknown});
  };
  if (channel) channel.onmessage = event => receive(event.data);
  if (inviteCode) {
    status = {mode:'connecting', detail:'正在建立跨设备连接', peerId:inviteCode};
    try {
      peer = role === 'elder' ? await hostAsPeer(inviteCode,undefined,config) : await connectToPeer(inviteCode,undefined,config);
      peer.onMessage(receive);
      peer.onStatus(s => {status = {mode:s.mode === 'connected' ? 'cross-device' : ['failed','closed'].includes(s.mode) ? 'failed':'connecting', detail:s.detail ?? s.mode, peerId:s.peerId};});
    } catch(error) {channel?.close(); throw error;}
  }
  return {via:inviteCode?'peer':'local', role, status:() => ({...status}),
    subscribe:handler => {handlers.add(handler); return () => {handlers.delete(handler);};},
    broadcast:(type,payload) => {const envelope = {tabId,fromRole:role,type,payload,at:new Date().toISOString()}; if(peer) peer.broadcast(envelope); else channel?.postMessage(envelope);},
    close:() => {peer?.destroy();channel?.close();handlers.clear();status={mode:'failed',detail:'已关闭',peerId:null};}};
}
