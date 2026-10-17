/** Optional host-owned read tools. Never grants a write or an owner-selection capability. */
import type { ElderTurnPlan } from '../engine/elderTurn';

export const rehabToolNames = [
  'rehab.get_training_plan',
  'rehab.get_recent_assessments',
  'rehab.get_training_history',
] as const;
export type RehabToolName = (typeof rehabToolNames)[number];
export interface RehabCall {
  name: RehabToolName;
  arguments: { exercise_id?: string; joint?: string };
}
export interface RehabResult {
  tool: RehabToolName;
  status: 'found' | 'empty';
  read_only: true;
  scope: { participant_id: string; source_kind: string; usage_context: string };
  records: unknown[];
}
export interface RehabToolPort {
  /** Model selects a read tool, or null to continue the original Agent turn. */
  select(text: string): Promise<RehabCall | null>;
  read(call: RehabCall): Promise<RehabResult>;
  describe(text: string, result: RehabResult): Promise<string>;
}

export function validateRehabCall(call: RehabCall): void {
  if (!call || !rehabToolNames.includes(call.name) || !call.arguments ||
      typeof call.arguments !== 'object' || Array.isArray(call.arguments) ||
      Object.keys(call.arguments).some(k => !['exercise_id', 'joint'].includes(k)) ||
      Object.values(call.arguments).some(v => typeof v !== 'string' || !v.trim() || v.length > 100) ||
      (call.arguments.exercise_id !== undefined && !/^[a-zA-Z0-9_-]+$/.test(call.arguments.exercise_id)) ||
      (call.arguments.joint !== undefined && !['shoulder','elbow','knee','hip','wrist','ankle','neck','trunk','finger'].includes(call.arguments.joint)))
    throw new Error('Invalid read-only rehab tool selection');
}

/** The participant is supplied by the host; model fields cannot select it. */
export async function readRehabReceipt(port: Pick<RehabToolPort, 'read'>, call: RehabCall, participantId: string, check = () => {}) {
  validateRehabCall(call);
  const data = await port.read(call);
  check();
  if (!data || data.tool !== call.name || data.read_only !== true || !Array.isArray(data.records) ||
      !['empty', 'found'].includes(data.status) || !data.scope || data.scope.participant_id !== participantId ||
      !['source_kind','usage_context'].every(k => typeof data.scope[k as 'source_kind' | 'usage_context'] === 'string' && data.scope[k as 'source_kind' | 'usage_context'].trim()) ||
      (data.status === 'empty' && data.records.length > 0)) throw new Error('Invalid rehab data receipt');
  return data;
}

/** Local rendering never sends saved personal records to a model. */
export function describeLocalRehabReceipt(data: RehabResult): string {
  if (!data.records.length) return '没有找到当前本人、来源和使用情境下的相关记录。';
  const labels: Record<string, string> = {id:'记录编号',name:'名称',exercise_label:'动作',side:'侧别',status:'状态',
    start_utc:'开始时间',end_utc:'结束时间',created_utc:'创建时间',completed:'完成次数',completed_sets:'完成组数',
    partial:'部分完成次数',invalid:'无效次数',reason:'说明',stop_reason:'停止原因',availability_reason:'可用性说明',
    measurement_note:'测量限制',motion_range:'活动范围',pain:'疼痛自述',fatigue:'疲劳自述',notes:'本人备注'};
  const lines = (value: unknown, depth = 0): string[] => {
    if (!value || typeof value !== 'object' || Array.isArray(value) || depth > 2) return [];
    return Object.entries(value).flatMap(([key, v]): string[] => {
      if (v === null || v === undefined || v === '') return [];
      if (labels[key] && ['string','number','boolean'].includes(typeof v)) return [labels[key] + '：' + String(v).slice(0, 500)];
      if (['summary','training_feedback'].includes(key)) return lines(v, depth + 1);
      if (key === 'next_available') return ['当前计划可用性：' + (v === true ? '记录标为可用，仍需核对当次条件' : '当前不可直接执行')];
      if (key === 'items' && Array.isArray(v)) return v.slice(0, 10).flatMap(item => lines(item, depth + 1));
      return [];
    });
  };
  return '本人已有康复记录（来源：' + data.scope.source_kind + '；情境：' + data.scope.usage_context + '）：\n' +
    data.records.slice(0, 5).map((r, i) => `${i + 1}. ` + (lines(r).join('；') || '已找到记录，详细字段请在康复页面查看。')).join('\n') +
    '\n这些是已有记录，不能仅凭次数或二维角度推断肌力或诊断。';
}

export async function prepareRehabReply(port: RehabToolPort, text: string, check = () => {}, suggestedCall: RehabCall | null = null) {
  const call = suggestedCall ?? await port.select(text);
  check();
  if (call === null) return null;
  if (
    !rehabToolNames.includes(call.name) ||
    !call.arguments ||
    Object.keys(call.arguments).some((k) => !['exercise_id', 'joint'].includes(k)) ||
    Object.values(call.arguments).some((value) => typeof value !== 'string')
  ) {
    throw new Error('Invalid read-only rehab tool selection');
  }
  const data = await port.read(call);
  check();
  if (
    data.tool !== call.name ||
    data.read_only !== true ||
    !Array.isArray(data.records) ||
    !['empty', 'found'].includes(data.status)
  )
    throw new Error('Invalid rehab data receipt');
  // Absence is never left for a model to fill in. No new facts enter HealthEvents.
  const replyText =
    data.status === 'empty' || data.records.length === 0
      ? '没有找到当前用户、数据来源和使用情境下的相关记录。'
      : await port.describe(text, data);
  if (!replyText.trim()) throw new Error('Empty rehab reply');
  const plan: ElderTurnPlan = {
    recordIntent: 'record',
    replyText,
    replyBlocks: [{ kind: 'main', text: replyText }],
    safetyAction: false,
    correction: null,
    eventsToAppend: [],
    familyEventsToAppend: [],
    sharingAuditEntries: [],
    shareFamilyEventIds: [],
    shareFindingIds: [],
    medicationMissed: false,
    toast: '',
  };
  return { plan, call, data };
}
