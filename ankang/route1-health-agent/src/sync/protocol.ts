import type { UserRole } from '../types';
export type CrossTabMessage =
  | { type: 'medication.update'; payload: unknown }
  | { type: 'dispatch.acknowledge'; findingId: string }
  | { type: 'dispatch.append'; record: unknown }
  | { type: 'family.link'; link: unknown; sharing: UserRole | null }
  | { type: 'chat.append'; message: unknown }
  | { type: 'chat.share'; sharedFindingIds: string[]; sharedFamilyEventIds: string[] }
  /**
   * P0-1 配套：健康事件在**同浏览器**各 tab 间保持一致（与 IndexedDB 持久化同一信任域，
   * 只走 BroadcastChannel，不进 PeerJS——私密事件不能落到另一台设备的存储里）。
   * payload: { events: HealthEvent[] }
   */
  | { type: 'events.append'; events: unknown[] }
  /**
   * P0-1 配套：隐私安全的"今日信号量"摘要（只有数量，没有内容），同浏览器与
   * 跨设备（PeerJS）都发——让另一台设备上的家属端也能如实显示
   * "有 N 条信号被隐私挡住"，而不是"今天还没有任何健康信号"。
   * payload: { today: string; signalCount: number; gatedAlertCount: number }
   */
  | { type: 'signals.summary'; today: string; signalCount: number; gatedAlertCount: number }
  /**
   * 评审 P0-1 修复：老人端的共享授权是全系统唯一的权威状态。授权变化必须广播到
   * 同浏览器其它 tab 与跨设备（PeerJS）家属端，否则家属端自己的 familySharing
   * 恒为 'denied'，collectFamilyNotifications 永远算出空数组——家属端永远收不到通知。
   * 载荷只有授权位与时间戳，没有任何健康内容，走 PeerJS 也安全。
   * payload: { sharing: 'denied' | 'granted'; updatedAt: string }
   */
  | { type: 'family.consent'; sharing: 'denied' | 'granted'; updatedAt: string };

export interface CrossTabMessageEnvelope {
  tabId: string;
  fromRole: UserRole | null;
  type: CrossTabMessage['type'];
  payload: unknown;
  at: string;
  /**
   * P1（评审安全项）：消息来自哪条通道。BroadcastChannel 与本浏览器 IndexedDB
   * 同一信任域；PeerJS 对端在绑定握手完成前是"陌生人"。接收端据此执行门控：
   * 陌生人发来的确认/台账消息一律忽略。
   */
  via?: 'local' | 'peer';
}

import { measurementToEvent, observationToEvent, labResultToEvent, type HealthEvent } from '../pipeline/events';
import { normalizeMeasurement } from '../adapters/HealthKitDeviceAdapter';
import { SYMPTOM_LABELS, type LabResult, type Observation, type DataSource } from '../types';
const sources = ['demo','device','photo','manual','import','chat','healthkit'];
/** Validate untyped local envelopes before the existing event merge. Peer never imports raw events. */
export function normalizeSyncEvents(input:unknown, dataMode:'personal'|'demo'):HealthEvent[] {
  if (!Array.isArray(input) || input.length > 10000) throw new Error('Invalid events batch');
  return input.map((e:any) => {
    if (!e || !sources.includes(e.source) || (e.source === 'demo' && dataMode !== 'demo')) throw new Error('Invalid event source');
    const source=e.source as DataSource;
    let result:HealthEvent;
    if (e.type === 'measurement') result=measurementToEvent(normalizeMeasurement(e.measurement,0,source));
    else if(e.type === 'labResult') result=labResultToEvent(lab(e.labResult,source));
    else if(e.type === 'observation') {
      const o=e.observation;
      if(!o || typeof o.id !== 'string' || !o.id || o.source !== source || typeof o.text !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(o.date) || !Number.isFinite(Date.parse(o.date)) || !Array.isArray(o.tags) || o.tags.some((t:any) => !Object.prototype.hasOwnProperty.call(SYMPTOM_LABELS,t)) || (o.status !== undefined && !['occurred','negated','hypothetical','uncertain','near_miss'].includes(o.status))) throw new Error('Invalid observation');
      result=observationToEvent({...o,measurements:o.measurements?.map((m:any,i:number) => normalizeMeasurement(m,i,m.source)),labResults:o.labResults?.map((v:any) => lab(v,v.source))} as Observation);
    } else throw new Error('Invalid event type');
    if(e.id !== result.id || e.timestamp !== result.timestamp || e.source !== result.source) throw new Error('Event wrapper mismatch');
    return result;
  });
}
function lab(v:any, source:DataSource):LabResult {
  if(!v || typeof v.id !== 'string' || !v.id || v.source !== source || !sources.includes(source) || typeof v.timestamp !== 'string' || !Number.isFinite(Date.parse(v.timestamp)) || typeof v.name !== 'string' || typeof v.value !== 'number' || !Number.isFinite(v.value) || typeof v.unit !== 'string') throw new Error('Invalid lab result');
  return {...v,visibility:v.visibility === 'family_ok'?'family_ok':'private'};
}
