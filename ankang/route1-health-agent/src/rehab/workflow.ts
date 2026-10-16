import { catalogue } from './catalogue';
import { localPlan, type PlanInput } from './assistant';
import { searchCards, searchGuidance } from './assistant';
import { readRehabReceipt, type RehabToolPort, type RehabCall, rehabToolNames } from '../runtime/rehabTools';
import type { ConversationModel } from '../runtime/conversation';
import type { SemanticTurn } from '../runtime/semanticRouter';

export type RehabWorkflowTool =
  | 'rehab.get_training_plan'
  | 'rehab.get_training_history'
  | 'rehab.get_recent_assessments'
  | 'rehab.search_knowledge'
  | 'rehab.search_guidance'
  | 'rehab.run_plan_algorithm';

export interface RehabToolCall {
  name: RehabWorkflowTool;
  arguments: {
    query?: string;
    exercise_id?: string;
    joint?: string;
    goal?: string;
    region?: string;
    equipment?: string[];
    restrictions?: string[];
    level?: number;
    screening_confirmed?: boolean;
  };
  reason: string;
}

export interface RehabToolSelection {
  version: 1;
  calls: RehabToolCall[];
  uncertainties: string[];
}

export interface RehabCandidateAction {
  exercise_id: string;
  reason: string;
  dose?: string;
}

export interface RehabCandidatePlan {
  version: 1;
  goal: string;
  summary: string;
  algorithm_input: {
    goal: string;
    region: string;
    equipment: string[];
    restrictions: string[];
    level: number | null;
    screening_confirmed: boolean;
  };
  candidate_actions: RehabCandidateAction[];
  doctor_review_required: boolean;
  doctor_review_reasons: string[];
  uncertainties: string[];
}

export interface RehabPlanValidation {
  status: 'passed' | 'needs_review' | 'rejected';
  reasons: string[];
  plan: RehabCandidatePlan;
  algorithm_result?: ReturnType<typeof localPlan>;
}

const WORKFLOW_TOOLS = new Set<RehabWorkflowTool>([
  ...rehabToolNames,
  'rehab.search_knowledge',
  'rehab.search_guidance',
  'rehab.run_plan_algorithm',
]);

const JOINTS = new Set(['shoulder','elbow','knee','hip','wrist','ankle','neck','trunk','finger']);
const MAX_TOOL_CALLS = 8;

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
function text(value: unknown, max = 500): value is string {
  return typeof value === 'string' && value.trim().length > 0 && value.length <= max;
}
function stringArray(value: unknown, maxItems = 20, maxChars = 160): value is string[] {
  return Array.isArray(value) && value.length <= maxItems && value.every(v => text(v, maxChars));
}
function json(raw: string): unknown {
  try {
    const cleaned = raw.trim().replace(/^\`\`\`(?:json)?\s*/i, '').replace(/\s*\`\`\`$/, '');
    return JSON.parse(cleaned);
  } catch { return null; }
}

/**
 * LLM #2 only decides which registered read/search/algorithm tools are useful.
 * The host executes them. Tool names never grant authorization.
 */
export function parseRehabToolSelection(raw: string): RehabToolSelection | null {
  const value = json(raw);
  if (!record(value) || value.version !== 1 || !Array.isArray(value.calls) ||
      value.calls.length > MAX_TOOL_CALLS || !stringArray(value.uncertainties, 12, 200)) return null;
  const calls: RehabToolCall[] = [];
  for (const item of value.calls) {
    if (!record(item) || !text(item.name, 100) || !WORKFLOW_TOOLS.has(item.name as RehabWorkflowTool) ||
        !record(item.arguments) || !text(item.reason, 300)) return null;
    const args = item.arguments;
    const allowed = ['query','exercise_id','joint','goal','region','equipment','restrictions','level','screening_confirmed'];
    if (Object.keys(args).some(k => !allowed.includes(k))) return null;
    if (args.query !== undefined && !text(args.query, 400)) return null;
    if (args.exercise_id !== undefined && !/^[A-Za-z0-9_-]{1,80}$/.test(String(args.exercise_id))) return null;
    if (args.joint !== undefined && (!text(args.joint, 40) || !JOINTS.has(args.joint))) return null;
    if (args.goal !== undefined && !text(args.goal, 300)) return null;
    if (args.region !== undefined && !text(args.region, 100)) return null;
    if (args.equipment !== undefined && !stringArray(args.equipment, 12, 120)) return null;
    if (args.restrictions !== undefined && !stringArray(args.restrictions, 12, 200)) return null;
    if (args.level !== undefined && (!Number.isInteger(args.level) || args.level < 0 || args.level > 3)) return null;
    if (args.screening_confirmed !== undefined && typeof args.screening_confirmed !== 'boolean') return null;
    if (item.name === 'rehab.search_knowledge' || item.name === 'rehab.search_guidance') {
      if (!text(args.query, 400)) return null;
    }
    if (item.name === 'rehab.run_plan_algorithm') {
      if (!text(args.goal, 300) || !text(args.region, 100) || !Array.isArray(args.equipment) ||
          !Array.isArray(args.restrictions) || !Number.isInteger(args.level) ||
          typeof args.screening_confirmed !== 'boolean') return null;
    }
    calls.push({
      name: item.name as RehabWorkflowTool,
      arguments: args as RehabToolCall['arguments'],
      reason: item.reason,
    });
  }
  return { version: 1, calls, uncertainties: value.uncertainties };
}

const TOOL_SYSTEM = `你是安康康复分析阶段的工具规划器。你已经收到第一轮语义 JSON。你的任务不是回答用户，也不是生成康复方案，只决定为了分析当前问题需要读取哪些已注册工具。
可用工具：
- rehab.get_training_plan：读取本人当前康复计划
- rehab.get_training_history：读取本人训练历史
- rehab.get_recent_assessments：读取本人近期评估
- rehab.search_knowledge：查询动作知识库；只能查询已存在动作/动作条件/停止条件
- rehab.search_guidance：查询康复指导资料；用于训练原则、剂量/进阶、单人执行等
- rehab.run_plan_algorithm：运行确定性本地计划筛选算法；只有在目标、部位、器材、限制、等级和 screening_confirmed 都有明确来源时才能调用
规则：
1. 只选择真正需要的工具，可以一次选择多个；最多8个。
2. 不创造动作ID，不创造个人记录，不把“建议调用工具”当成工具执行结果。
3. 不诊断，不判断医学安全许可；如果信息不足写入 uncertainties。
4. run_plan_algorithm 的 screening_confirmed 不得根据“看起来安全”猜测；没有明确数据时不要调用。
5. 个人工具只能读取当前本人数据，不能选择 participant_id。
6. 输出且仅输出 JSON：{"version":1,"calls":[{"name":"...","arguments":{},"reason":"..."}],"uncertainties":[]}`;

export async function selectRehabTools(
  model: ConversationModel,
  semantic: SemanticTurn,
  userText: string,
  check = () => {},
): Promise<RehabToolSelection | null> {
  const prompt = TOOL_SYSTEM + '\n第一轮语义：' + JSON.stringify({
    route: semantic.route, goal: semantic.goal, intents: semantic.intents ?? [],
    mentions: semantic.mentions, events: semantic.events, relations: semantic.relations,
    uncertain: semantic.uncertain, user_text: userText,
  });
  try {
    const raw = await model.reply({ purpose: 'understanding', messages: [{ role: 'user', content: prompt }] });
    check();
    return parseRehabToolSelection(raw);
  } catch {
    check();
    return null;
  }
}

function normalizeRegion(value: string): string {
  const map: Record<string,string> = { 膝盖:'膝', 膝关节:'膝', 肩膀:'肩', 肩关节:'肩', 髋关节:'髋', 脚踝:'踝', 踝关节:'踝', 手腕:'腕', 腕关节:'腕' };
  return map[value.trim()] ?? value.trim();
}

function sourceTextForAction(id: string) {
  return catalogue.find(c => c.id === id && c.kind === 'training' && c.complete);
}

/** Strict validation: every proposed action must exist as a complete training card. */
export function validateRehabPlan(candidate: RehabCandidatePlan, cards = catalogue): RehabPlanValidation {
  const reasons: string[] = [];
  if (!candidate || candidate.version !== 1 || !text(candidate.goal, 300) || !text(candidate.summary, 1200)) {
    return { status: 'rejected', reasons: ['invalid_candidate_shape'], plan: candidate };
  }
  if (!record(candidate.algorithm_input) || !text(candidate.algorithm_input.goal, 300) ||
      !text(candidate.algorithm_input.region, 100) || !stringArray(candidate.algorithm_input.equipment, 12, 120) ||
      !stringArray(candidate.algorithm_input.restrictions, 12, 200) ||
      (candidate.algorithm_input.level !== null && (!Number.isInteger(candidate.algorithm_input.level) || candidate.algorithm_input.level < 0 || candidate.algorithm_input.level > 3)) ||
      typeof candidate.algorithm_input.screening_confirmed !== 'boolean') {
    return { status: 'rejected', reasons: ['invalid_algorithm_input'], plan: candidate };
  }
  if (!Array.isArray(candidate.candidate_actions) || candidate.candidate_actions.length > 6 ||
      !Array.isArray(candidate.doctor_review_reasons) || candidate.doctor_review_reasons.length > 12 ||
      !Array.isArray(candidate.uncertainties) || candidate.uncertainties.length > 12) {
    return { status: 'rejected', reasons: ['invalid_candidate_lists'], plan: candidate };
  }
  const validIds = new Set(cards.filter(c => c.kind === 'training' && c.complete).map(c => c.id));
  for (const item of candidate.candidate_actions) {
    if (!record(item) || !/^[A-Z]-[A-Z0-9]+-\d+$/.test(String(item.exercise_id)) ||
        !validIds.has(item.exercise_id) || !text(item.reason, 500) ||
        (item.dose !== undefined && !text(item.dose, 500))) {
      return { status: 'rejected', reasons: ['unknown_or_incomplete_action'], plan: candidate };
    }
    const card = sourceTextForAction(item.exercise_id);
    if (!card?.sourceDose || !card.startConditions || !card.stopConditions || !card.equipment) {
      return { status: 'rejected', reasons: ['action_card_missing_required_conditions'], plan: candidate };
    }
    if (item.dose !== undefined && !card.sourceDose.includes(item.dose)) {
      reasons.push('dose_not_verbatim_from_action_card:' + item.exercise_id);
    }
  }
  if (candidate.algorithm_input.restrictions.some(v => v.trim())) reasons.push('individual_restrictions_require_review');
  if (!candidate.algorithm_input.screening_confirmed) reasons.push('screening_not_confirmed');
  if (candidate.uncertainties.length) reasons.push('unresolved_uncertainty');
  if (candidate.doctor_review_required) reasons.push(...candidate.doctor_review_reasons.map(v => 'doctor_review:' + v));
  return { status: reasons.length ? 'needs_review' : 'passed', reasons, plan: candidate };
}

function parseCandidate(raw: string): RehabCandidatePlan | null {
  const value = json(raw);
  if (!record(value) || value.version !== 1 || !text(value.goal, 300) || !text(value.summary, 1200) ||
      !record(value.algorithm_input) || !Array.isArray(value.candidate_actions) ||
      typeof value.doctor_review_required !== 'boolean' || !stringArray(value.doctor_review_reasons, 12, 300) ||
      !stringArray(value.uncertainties, 12, 300)) return null;
  const a = value.algorithm_input;
  if (!text(a.goal,300) || !text(a.region,100) || !stringArray(a.equipment,12,120) ||
      !stringArray(a.restrictions,12,200) ||
      (a.level !== null && (!Number.isInteger(a.level)||a.level<0||a.level>3)) ||
      typeof a.screening_confirmed !== 'boolean') return null;
  const actions: RehabCandidateAction[] = [];
  for(const item of value.candidate_actions){
    if(!record(item)||!/^[A-Z]-[A-Z0-9]+-\d+$/.test(String(item.exercise_id))||!text(item.reason,500)||
       (item.dose!==undefined&&!text(item.dose,500))) return null;
    actions.push({exercise_id:String(item.exercise_id),reason:item.reason,...(item.dose!==undefined?{dose:item.dose}: {})});
  }
  return {version:1,goal:value.goal,summary:value.summary,algorithm_input:{
    goal:a.goal,region:a.region,equipment:a.equipment,restrictions:a.restrictions,
    level:a.level,screening_confirmed:a.screening_confirmed
  },candidate_actions:actions,doctor_review_required:value.doctor_review_required,
  doctor_review_reasons:value.doctor_review_reasons,uncertainties:value.uncertainties};
}

async function executeCall(
  call: RehabToolCall,
  reads: Pick<RehabToolPort,'read'> | undefined,
  participantId: string,
  check: () => void,
): Promise<{name:string; data:unknown}> {
  if (call.name === 'rehab.search_knowledge') {
    const cards = searchCards(call.arguments.query ?? '');
    return { name: call.name, data: cards.map(c => ({
      id:c.id,name:c.name,kind:c.kind,region:c.region,level:c.level,equipment:c.equipment,
      startConditions:c.startConditions,stopConditions:c.stopConditions,sourceDose:c.sourceDose,content:c.content
    })) };
  }
  if (call.name === 'rehab.search_guidance') {
    const section = searchGuidance(call.arguments.query ?? '');
    return { name: call.name, data: section ? {title:section.title,content:section.content} : null };
  }
  if (call.name === 'rehab.run_plan_algorithm') {
    const a = call.arguments;
    const input: PlanInput = {
      goal:a.goal!, region:normalizeRegion(a.region!), equipment:a.equipment!, restrictions:a.restrictions!,
      level:a.level!, screeningConfirmed:false,
    };
    try { return {name:call.name,data:localPlan(input)}; }
    catch (error) { return {name:call.name,data:{status:'needs_review',error:String(error)}}; }
  }
  if (!reads) throw new Error('personal_read_tool_unavailable');
  const personal: RehabCall = { name: call.name as RehabCall['name'], arguments: {
    ...(call.arguments.exercise_id ? {exercise_id:call.arguments.exercise_id}:{}),
    ...(call.arguments.joint ? {joint:call.arguments.joint}:{}),
  }};
  const data = await readRehabReceipt(reads, personal, participantId, check);
  return {name:call.name,data};
}

const ANALYSIS_SYSTEM = `你是安康康复分析器。你只根据“第一轮语义”和“已执行工具结果”形成一个候选康复计划 JSON，不直接修改用户计划，不执行程序操作，不诊断，不把模型猜测写成个人事实。
必须输出：
{"version":1,"goal":"...","summary":"...","algorithm_input":{"goal":"...","region":"...","equipment":[],"restrictions":[],"level":null,"screening_confirmed":false},"candidate_actions":[{"exercise_id":"已检索到的动作ID","reason":"...","dose":"仅当动作卡原文可支持时填写"}],"doctor_review_required":false,"doctor_review_reasons":[],"uncertainties":[]}
规则：
1. candidate_actions 只能使用工具返回的完整训练动作 ID，禁止创造 ID。
2. 不把 assessment 卡当 training 动作。
3. 不发明次数、组数、保持时间或负重；dose 只能逐字取自动作卡 sourceDose，否则省略。
4. algorithm_input 只能来自用户明确表达或工具结果；不知道就填 null/空数组，不猜。
5. screening_confirmed 只有工具结果或用户明确资料直接支持时才可为 true；不要因为没有看到危险就填 true。
6. restrictions 有个人限制时，优先 doctor_review_required=true，除非工具结果明确给出可执行的现有专业计划边界。
7. 信息不足时保留 uncertainties；不要为了生成“完整计划”而补数据。
8. doctor_review_required 表示“当前信息不足或存在需要专业核实的因素”，不是泛化的“所有康复问题都必须就医”。
9. 只输出 JSON，不要 Markdown，不要解释。`;

export async function generateRehabCandidate(
  model: ConversationModel,
  semantic: SemanticTurn,
  userText: string,
  toolResults: {name:string;data:unknown}[],
  check = () => {},
): Promise<RehabCandidatePlan | null> {
  const payload = JSON.stringify({
    semantic: {route:semantic.route,goal:semantic.goal,intents:semantic.intents??[],mentions:semantic.mentions,events:semantic.events,relations:semantic.relations,uncertain:semantic.uncertain},
    user_text:userText,
    tool_results:toolResults,
  });
  if (payload.length > 30000) return null;
  try {
    const raw=await model.reply({purpose:'understanding',messages:[{role:'user',content:ANALYSIS_SYSTEM+'\n'+payload}]});
    check();
    return parseCandidate(raw);
  } catch { check(); return null; }
}

export async function runRehabWorkflow(input: {
  model: ConversationModel;
  semantic: SemanticTurn;
  userText: string;
  reads?: Pick<RehabToolPort,'read'>;
  participantId: string;
  check?: () => void;
}): Promise<{candidate: RehabCandidatePlan | null; validation: RehabPlanValidation | null; toolResults:{name:string;data:unknown}[]; selection:RehabToolSelection|null}> {
  const check=input.check??(()=>{});
  const selection=await selectRehabTools(input.model,input.semantic,input.userText,check);
  if(!selection) return {candidate:null,validation:null,toolResults:[],selection:null};
  const toolResults:{name:string;data:unknown}[]=[];
  const unique=new Set<string>();
  for(const call of selection.calls){
    const key=call.name+JSON.stringify(call.arguments);
    if(unique.has(key))continue;
    unique.add(key);
    try { toolResults.push(await executeCall(call,input.reads,input.participantId,check)); }
    catch { toolResults.push({name:call.name,data:{status:'failed',reason:'tool_execution_failed'}}); }
  }
  const candidate=await generateRehabCandidate(input.model,input.semantic,input.userText,toolResults,check);
  if(!candidate) return {candidate:null,validation:null,toolResults,selection};

  // The deterministic algorithm is authoritative when the LLM explicitly requested it.
  // The model may propose inputs, but the host owns execution and the returned result.
  const algorithmResult = toolResults.find(r => r.name === 'rehab.run_plan_algorithm')?.data as ReturnType<typeof localPlan> | undefined;
  let validation=validateRehabPlan(candidate);
  if (algorithmResult) {
    validation = { ...validation, algorithm_result: algorithmResult };
    const algorithmIds = new Set((algorithmResult.items ?? []).map(item => item.id));
    if (candidate.candidate_actions.some(action => !algorithmIds.has(action.exercise_id))) {
      validation = {
        ...validation,
        status: 'rejected',
        reasons: [...validation.reasons, 'candidate_action_not_returned_by_algorithm'],
      };
    }
    if (algorithmResult.status === 'no_match' && candidate.candidate_actions.length) {
      validation = {
        ...validation,
        status: 'rejected',
        reasons: [...validation.reasons, 'algorithm_no_match'],
      };
    }
    if (algorithmResult.status === 'needs_review') {
      validation = {
        ...validation,
        status: validation.status === 'rejected' ? 'rejected' : 'needs_review',
        reasons: [...validation.reasons, 'algorithm_requires_review'],
      };
    }
  }
  return {candidate,validation,toolResults,selection};
}

/** Safe user-facing rendering of a validated draft; it is not persistence. */
export function renderRehabDraft(result: RehabPlanValidation | null): string {
  if(!result) return '康复分析暂时没有形成可验证的候选方案。请补充具体目标、部位或当前训练情况。';
  if(result.status==='rejected') return '这次康复分析没有形成符合系统结构的候选方案，请补充具体情况后再试。';
  const p=result.plan;
  const lines=[p.summary];
  if(p.candidate_actions.length) lines.push('候选动作：'+p.candidate_actions.map(a=>a.exercise_id).join('、'));
  if(result.algorithm_result?.status) lines.push('规则筛选：'+result.algorithm_result.status);
  if(result.status==='needs_review') lines.push('当前方案仍需核对：'+result.reasons.map(r=>r.replace(/^doctor_review:/,'')).join('；'));
  else lines.push('这是一份候选方案，尚未写入你的训练计划。');
  return lines.join('\\n');
}
