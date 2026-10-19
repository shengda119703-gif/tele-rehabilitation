import type { ConversationModel } from '../runtime/conversation';
import type { RehabToolPort } from '../runtime/rehabTools';
import {readRehabReceipt} from '../runtime/rehabTools';
import type { SemanticTurn } from '../runtime/semanticRouter';

export interface RehabOperationPort {
  call(name: string, args: Record<string, unknown>): Promise<unknown>;
}

export type RehabProgramOperationName =
  | 'rehab.plan.change'
  | 'rehab.schedule.upsert'
  | 'rehab.schedule.remove';

export interface RehabProgramOperation {
  name: RehabProgramOperationName;
  arguments: Record<string, unknown>;
  evidence: string;
}

export interface RehabProgramPlan {
  version: 1;
  operations: RehabProgramOperation[];
  requires_confirmation: true;
  summary: string;
  uncertainties: string[];
}

export interface PendingRehabOperation {
  proposal: RehabProgramPlan;
  previews: unknown[];
  createdAt: number;
}

const OPERATION_NAMES = new Set<RehabProgramOperationName>([
  'rehab.plan.change',
  'rehab.schedule.upsert',
  'rehab.schedule.remove',
]);

const READ_NAMES = new Set(['rehab.get_training_plan', 'rehab.get_schedule']);
const PLAN_SETTING_FIELDS = new Set([
  'target_reps', 'target_sets', 'rest_between_sets_s', 'target_angle_deg',
  'allowed_elbow_flexion_deg', 'allowed_trunk_tilt_deg',
  'lowering_tempo_min_s', 'lowering_tempo_max_s', 'use_of_hands',
  'needs_companion', 'sound_enabled', 'timing_plan',
]);

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
function text(value: unknown, max = 500): value is string {
  return typeof value === 'string' && value.trim().length > 0 && value.length <= max;
}
function json(raw: string): unknown {
  try { return JSON.parse(raw.trim()); } catch { return null; }
}
function stringArray(value: unknown, maxItems = 20, maxChars = 160): value is string[] {
  return Array.isArray(value) && value.length <= maxItems && value.every(v => text(v, maxChars));
}

export function parseRehabProgramPlan(raw: string): RehabProgramPlan | null {
  const value = json(raw);
  if (!record(value) || value.version !== 1 || value.requires_confirmation !== true ||
      !text(value.summary, 800) || !Array.isArray(value.operations) || value.operations.length > 1 ||
      !stringArray(value.uncertainties, 12, 300)) return null;
  const operations: RehabProgramOperation[] = [];
  for (const item of value.operations) {
    if (!record(item) || !text(item.name, 80) || !OPERATION_NAMES.has(item.name as RehabProgramOperationName) ||
        !record(item.arguments) || !text(item.evidence, 500)) return null;
    const args = item.arguments;
    const allowed = item.name === 'rehab.plan.change'
      ? ['plan_id', 'expected_revision', 'patch']
      : item.name === 'rehab.schedule.upsert'
        ? ['id', 'plan_id', 'plan_revision', 'date', 'time', 'name']
        : ['id'];
    if (Object.keys(args).some(k => !allowed.includes(k))) return null;
    if (item.name === 'rehab.plan.change') {
      if (!text(args.plan_id, 80) || typeof args.expected_revision !== 'number' || !Number.isInteger(args.expected_revision) ||
          args.expected_revision < 0 || !record(args.patch)) return null;
      const patch = args.patch;
      if (Object.keys(patch).some(k => !['name', 'add', 'update', 'remove'].includes(k))) return null;
      if (patch.name !== undefined && !text(patch.name, 80)) return null;
      if (patch.remove !== undefined && !stringArray(patch.remove, 106, 160)) return null;
      for (const field of ['add', 'update'] as const) {
        if (patch[field] === undefined) continue;
        if (!Array.isArray(patch[field]) || patch[field].length > 106) return null;
        for (const change of patch[field]) {
          if (!record(change)) return null;
          if (field === 'add') {
            if (!text(change.exercise_id, 80) || !['left', 'right'].includes(String(change.side))) return null;
            if (change.settings !== undefined && !record(change.settings)) return null;
          } else {
            if (!text(change.key, 160) || !record(change.settings)) return null;
            if (Object.keys(change.settings).some(k => !PLAN_SETTING_FIELDS.has(k))) return null;
          }
        }
      }
    } else if (item.name === 'rehab.schedule.upsert') {
      if (args.id !== undefined && !text(args.id, 160)) return null;
      if (!text(args.plan_id, 80) || typeof args.plan_revision !== 'number' || !Number.isInteger(args.plan_revision) || args.plan_revision < 1 ||
          !text(args.date, 20) || !/^\d{4}-\d{2}-\d{2}$/.test(args.date) ||
          !text(args.time, 10) || !/^\d{2}:\d{2}$/.test(args.time) ||
          (args.name !== undefined && !text(args.name, 100))) return null;
    } else if (!text(args.id, 160)) return null;
    operations.push({name: item.name as RehabProgramOperationName, arguments: args, evidence: item.evidence});
  }
  return {version: 1, operations, requires_confirmation: true, summary: value.summary, uncertainties: value.uncertainties};
}

const PROGRAM_READ_SYSTEM = [
  '你是安康应用的康复程序操作规划器。第一轮 Johnson 已经确认用户的主要意图与原话。',
  '现在只决定为了完成应用操作需要读取什么，不修改任何数据。',
  '可用读取工具：rehab.get_training_plan（当前康复计划及版本）、rehab.get_schedule（当前康复安排时间）。',
  '修改计划通常先读取当前计划；改训练时间通常读取当前计划和安排。',
  '如果目标无法确定，不要猜。',
  '输出且仅输出 JSON：{"version":1,"calls":[{"name":"rehab.get_training_plan|rehab.get_schedule","arguments":{},"reason":"..."}],"uncertainties":[]}'
].join('\n');

function parseReadPlan(raw: string) {
  const value = json(raw);
  if (!record(value) || value.version !== 1 || !Array.isArray(value.calls) || value.calls.length > 3 ||
      !stringArray(value.uncertainties, 12, 300)) return null;
  const calls: {name:string;arguments:Record<string,unknown>;reason:string}[] = [];
  for (const item of value.calls) {
    if (!record(item) || !text(item.name, 100) || !READ_NAMES.has(item.name) ||
        !record(item.arguments) || Object.keys(item.arguments).length || !text(item.reason, 300)) return null;
    calls.push({name:item.name,arguments:{},reason:item.reason});
  }
  return {version:1,calls,uncertainties:value.uncertainties};
}

async function selectReads(model: ConversationModel, semantic: SemanticTurn, userText: string, check: () => void) {
  try {
    const raw = await model.reply({
      purpose: 'understanding',
      messages: [{role:'user',content:PROGRAM_READ_SYSTEM+'\n第一轮语义：'+JSON.stringify({
        route:semantic.route, goal:semantic.goal, intents:semantic.intents??[],
        mentions:semantic.mentions, events:semantic.events, relations:semantic.relations,
        uncertain:semantic.uncertain, user_text:userText,
      })}],
    });
    check();
    return parseReadPlan(raw);
  } catch {
    check();
    return null;
  }
}

export async function previewRehabProgramOperation(input: {
  model: ConversationModel;
  semantic: SemanticTurn;
  userText: string;
  reads?: Pick<RehabToolPort,'read'>;
  participantId?: string;
  operations?: RehabOperationPort;
  rehabContext?: unknown;
  check?: () => void;
}): Promise<{plan:RehabProgramPlan|null;previews:unknown[];toolResults:{name:string;data:unknown}[]}> {
  const check=input.check??(()=>{});
  if (!input.operations) return {plan:null,previews:[],toolResults:[]};
  // Resolve this narrow, non-clinical operation locally. Stored names, IDs and
  // revisions never enter an external-model prompt. Ambiguous targets fail closed.
  const rename = /^(?:请)?(?:帮我)?(?:把)?(?:我的|当前的|当前)?(?:康复|训练)计划(?:改名为|重命名为|改名叫)([\p{L}\p{N} _-]{1,80})[。！!]?$/u.exec(input.userText.trim());
  if (rename && input.reads && input.participantId) {
    const toolResults:{name:string;data:unknown}[]=[];
    try {
      const receipt=await readRehabReceipt(input.reads,{name:'rehab.get_training_plan',arguments:{}},input.participantId,check);
      toolResults.push({name:'rehab.get_training_plan',data:receipt});
      const active=receipt.records.filter(row=>record(row)&&row.status==='ACTIVE');
      if(active.length!==1) return {plan:{version:1,operations:[],requires_confirmation:true,
        summary:'尚未修改计划名称。',uncertainties:['当前没有唯一的有效训练计划，请在康复页选择具体计划。']},previews:[],toolResults};
      const current=active[0];
      if(!record(current)||typeof current.id!=='string'||!/^[0-9a-f]{32}$/.test(current.id)||
        !Number.isInteger(current.revision)||Number(current.revision)<1) throw Error('Invalid local plan revision');
      const operation:RehabProgramOperation={name:'rehab.plan.change',arguments:{plan_id:current.id,
        expected_revision:current.revision,patch:{name:rename[1].trim()}},evidence:input.userText};
      const preview=await input.operations.call(operation.name,{...operation.arguments,commit:false});
      check();
      if(!record(preview)||preview.status!=='preview'||preview.plan_id!==current.id||
        preview.expected_revision!==current.revision||!record(preview.after)||preview.after.name!==rename[1].trim())
        throw Error('Invalid local rename preview');
      return {plan:{version:1,operations:[operation],requires_confirmation:true,
        summary:'将当前训练计划名称改为“'+rename[1].trim()+'”。',uncertainties:[]},
        previews:[{name:operation.name,result:preview}],toolResults};
    } catch {
      check();
      return {plan:{version:1,operations:[],requires_confirmation:true,summary:'尚未修改计划名称。',
        uncertainties:['未能核对本人计划或修改预览，请刷新康复页面后重试。']},previews:[],toolResults};
    }
  }
  const selection=await selectReads(input.model,input.semantic,input.userText,check);
  if (!selection) return {plan:null,previews:[],toolResults:[]};
  const toolResults:{name:string;data:unknown}[]=[];
  const unique=new Set<string>();
  for(const call of selection.calls){
    if(unique.has(call.name)) continue;
    unique.add(call.name);
    try {
      if(call.name==='rehab.get_training_plan' && input.reads)
        toolResults.push({name:call.name,data:await input.reads.read({name:'rehab.get_training_plan',arguments:{}})});
      else if(call.name==='rehab.get_schedule')
        toolResults.push({name:call.name,data:await input.operations.call(call.name,{})});
    } catch {
      toolResults.push({name:call.name,data:{status:'failed',reason:'tool_execution_failed'}});
    }
    check();
  }
  // Stored plan/schedule data has no external-model consent or local intent resolver yet.
  return {plan:{version:1,operations:[],requires_confirmation:true,summary:'这次修改尚未执行。',
    uncertainties:['当前未授权把已保存的个人计划和训练安排发送给外部模型，请在康复页面手动修改。']},previews:[],toolResults};
}


export function isRehabProgramIntent(semantic: SemanticTurn): boolean {
  const hasProgram = semantic.intents?.some(i => i.type === 'program_operation' || i.type === 'plan_change') ?? false;
  if (!hasProgram) return false;
  if (semantic.route === 'rehab') return true;
  const evidence = [
    semantic.goal,
    ...semantic.mentions.map(m => m.text),
    ...semantic.intents!.filter(i => i.type === 'program_operation' || i.type === 'plan_change').map(i => i.evidence),
  ].join(' ');
  // Navigation/query requests stay on the existing module/records path.
  if (/^(?:打开|进入|查看|看看|跳转|返回|关闭)/.test(semantic.goal.trim())) return false;
  return /修改|更改|调整|增加|删除|移除|减少|暂停|恢复|安排|时间|计划/.test(evidence) &&
    /康复|训练|锻炼|动作|计划/.test(evidence);
}

export function isConfirmation(text: string): boolean {
  return /^(?:好|好的|可以|可以的|行|行的|没问题|确认|确认执行|确定|同意|就这样|按这个来|执行吧|改吧|保存吧)[。！!，,\s]*$/i.test(text.trim());
}
export function isCancellation(text: string): boolean {
  return /^(?:不用|不用了|取消|先不要|别改|不要改|算了|不改了)[。！!，,\s]*$/i.test(text.trim());
}

export function renderOperationPreview(plan: RehabProgramPlan | null, previews: unknown[]): string {
  if (plan?.uncertainties.length) return '这次修改尚未执行：'+plan.uncertainties.join('；');
  if (!plan || !plan.operations.length) return '我还无法确定要修改哪一项康复计划或安排。请告诉我具体要改哪个动作、次数或时间。';
  const rejected = previews.find(item => record(item) && record(item.result) && item.result.status === 'rejected');
  if (rejected) {
    const reason = record(rejected) && record(rejected.result) ? rejected.result.reason : undefined;
    return '这项修改暂时不能执行：'+String(reason ?? '当前计划或安排已经发生变化，请刷新后再试。');
  }
  return '我准备这样修改：\n'+plan.summary+'\n\n如果确认，我才会真正修改你的康复计划或训练安排。';
}

export async function commitRehabProgramOperation(input: {
  pending: PendingRehabOperation;
  operations: RehabOperationPort;
  check?: () => void;
  now?: number;
  reads?: Pick<RehabToolPort,'read'>;
  participantId?: string;
}): Promise<unknown[]> {
  const check=input.check??(()=>{});
  const now=input.now??Date.now();
  if (!Number.isFinite(input.pending.createdAt) || input.pending.createdAt > now ||
      now-input.pending.createdAt > 5*60*1000) throw Error('Rehab operation confirmation expired');
  const results: unknown[]=[];
  for (const operation of input.pending.proposal.operations) {
    check();
    const result=await input.operations.call(operation.name,{...operation.arguments,commit:true});
    check();
    if(operation.name==='rehab.plan.change' && record(result) && result.status==='applied') {
      try {
        if(!input.reads||!input.participantId)throw Error('Readback unavailable');
        const receipt=await readRehabReceipt(input.reads,{name:'rehab.get_training_plan',arguments:{}},input.participantId,check);
        const saved=receipt.records.find(row=>record(row)&&row.id===operation.arguments.plan_id);
        const patch=operation.arguments.patch;
        if(!record(saved)||result.plan_id!==saved.id||result.revision!==saved.revision||
          saved.revision!==Number(operation.arguments.expected_revision)+1||
          (record(patch)&&typeof patch.name==='string'&&saved.name!==patch.name))throw Error('Readback mismatch');
        results.push(result);
      } catch {check();results.push({status:'committed_unverified'});}
    } else results.push(result);
  }
  return results;
}

export function renderOperationResult(result: unknown): string {
  if(record(result)&&result.status==='committed_unverified')return '修改已提交，但暂时无法核对保存结果，请在康复页确认后再操作。';
  if (record(result) && result.status === 'applied') return '已经按你确认的内容更新了康复计划/训练安排。';
  return '这次修改没有执行成功，当前计划可能已经发生变化，请重新查看后再操作。';
}
