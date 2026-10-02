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

export async function prepareRehabReply(port: RehabToolPort, text: string, check = () => {}) {
  const call = await port.select(text);
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
