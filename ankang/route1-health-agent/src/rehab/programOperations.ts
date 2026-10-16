import type { ConversationModel } from '../runtime/conversation';
import type { RehabToolPort } from '../runtime/rehabTools';
import type { SemanticTurn } from '../runtime/semanticRouter';

export interface RehabOperationPort {
  call(name: string, arguments: Record<string, unknown>): Promise<unknown>;
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
      if (!text(args.plan_id, 80) || !Number.isInteger(args.expected_revision) ||
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
      if (!text(args.plan_id, 80) || !Number.isInteger(args.plan_revision) || args.plan_revision < 1 ||
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

const PROGRAM_SYSTEM = [
  '你是安康应用的康复程序操作规划器。你已经收到 Johnson 第一轮语义和程序只读工具的真实结果。',
  '现在只把用户明确要求转换成候选程序操作，不执行、不回答、不诊断。',
  '允许：rehab.plan.change（修改本人已保存康复计划：名称、已有动作参数、删除动作、添加动作）；',
  'rehab.schedule.upsert（新增或修改本人康复计划的训练安排时间）；',
  'rehab.schedule.remove（删除本人康复安排）。',
  '永远输出 requires_confirmation=true；用户确认前绝不写入。一次只提出一个程序写操作。',
  'plan_id、revision、key 必须来自真实工具结果，禁止猜。',
  '不得修改 participant_id、record_origin、doctor_publication 等系统字段。',
  '训练参数只能使用计划支持的字段；添加动作只能使用已知真实 exercise_id。',
  '康复问题与程序操作同时出现时，只提出待确认的程序修改，不自动执行。',
  '如果无法确定目标，operations=[]，把缺失信息写入 uncertainties。',
  '输出且仅输出 JSON：{"version":1,"operations":[{"name":"rehab.plan.change|rehab.schedule.upsert|rehab.schedule.remove","arguments":{},"evidence":"用户原话片段"}],"requires_confirmation":true,"summary":"给用户看的变更摘要","uncertainties":[]}'
].join('\n');

async function buildPlan(model: ConversationModel, semantic: SemanticTurn, userText: string,
  toolResults: {name:string;data:unknown}[], check: () => void, rehabContext?: unknown): Promise<RehabProgramPlan | null> {
  const payload = JSON.stringify({
    semantic: {route:semantic.route,goal:semantic.goal,intents:semantic.intents??[],mentions:semantic.mentions,events:semantic.events,relations:semantic.relations,uncertain:semantic.uncertain},
    user_text:userText, tool_results:toolResults, rehab_context:rehabContext ?? null,
  });
  if (payload.length > 30000) return null;
  try {
    const raw = await model.reply({purpose:'understanding',messages:[{role:'user',content:PROGRAM_SYSTEM+'\n'+payload}]});
    check();
    return parseRehabProgramPlan(raw);
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
  operations?: RehabOperationPort;
  rehabContext?: unknown;
  check?: () => void;
}): Promise<{plan:RehabProgramPlan|null;previews:unknown[];toolResults:{name:string;data:unknown}[]}> {
  const check=input.check??(()=>{});
  if (!input.operations) return {plan:null,previews:[],toolResults:[]};
  const selection=await selectReads(input.model,input.semantic,input.userText,check);
  if (!selection) return {plan:null,previews:[],toolResults:[]};
  const toolResults:{name:string;data:unknown}[]=[];
  const unique=new Set<string>();
  for(const call of selection.calls){
    if(unique.has(call.name)) continue;
    unique.add(call.name);
    try {
      if(call.name==='rehab.get_training_plan' && input.reads)
        toolResults.push({name:call.name,data:await input.reads.read('rehab.get_training_plan',{})});
      else if(call.name==='rehab.get_schedule')
        toolResults.push({name:call.name,data:await input.operations.call(call.name,{})});
    } catch {
      toolResults.push({name:call.name,data:{status:'failed',reason:'tool_execution_failed'}});
    }
  }
  const plan=await buildPlan(input.model,input.semantic,input.userText,toolResults,check,input.rehabContext);
  if(!plan || !plan.operations.length) return {plan,previews:[],toolResults};
  const previews=[];
  for(const operation of plan.operations){
    try { previews.push({name:operation.name,result:await input.operations.call(operation.name,{...operation.arguments,commit:false})}); }
    catch(error) { previews.push({name:operation.name,result:{status:'rejected',reason:String(error)}}); }
  }
  return {plan,previews,toolResults};
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
  return /康复|训练|锻炼|动作|计划|训练时间|训练安排/.test(evidence);
}

export function isConfirmation(text: string): boolean {
  return /^(?:好|好的|可以|可以的|行|行的|没问题|确认|确认执行|确定|同意|就这样|按这个来|执行吧|改吧|保存吧)[。！!，,\s]*$/i.test(text.trim());
}
export function isCancellation(text: string): boolean {
  return /^(?:不用|不用了|取消|先不要|别改|不要改|算了|不改了)[。！!，,\s]*$/i.test(text.trim());
}

export function renderOperationPreview(plan: RehabProgramPlan | null, previews: unknown[]): string {
  if (!plan || !plan.operations.length) return '我还无法确定要修改哪一项康复计划或安排。请告诉我具体要改哪个动作、次数或时间。';
  if (previews.some(item => record(item) && record(item.result) && item.result.status === 'rejected')) {
    const reason = previews.find(item => record(item) && record(item.result) && item.result.status === 'rejected')?.result?.reason;
    return '这项修改暂时不能执行：'+String(reason ?? '当前计划或安排已经发生变化，请刷新后再试。');
  }
  return '我准备这样修改：\n'+plan.summary+'\n\n如果确认，我才会真正修改你的康复计划或训练安排。';
}

export async function commitRehabProgramOperation(input: {
  pending: PendingRehabOperation;
  operations: RehabOperationPort;
  check?: () => void;
}): Promise<unknown[]> {
  const check=input.check??(()=>{});
  const results: unknown[]=[];
  for (const operation of input.pending.proposal.operations) {
    check();
    results.push(await input.operations.call(operation.name,{...operation.arguments,commit:true}));
    check();
  }
  return results;
}

export function renderOperationResult(result: unknown): string {
  if (record(result) && result.status === 'applied') return '已经按你确认的内容更新了康复计划/训练安排。';
  return '这次修改没有执行成功，当前计划可能已经发生变化，请重新查看后再操作。';
}
