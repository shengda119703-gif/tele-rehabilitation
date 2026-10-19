import { catalogue } from './catalogue';
import { localPlan, type PlanInput } from './assistant';
import { searchCards, searchGuidance } from './assistant';
import { readRehabReceipt, describeLocalRehabReceipt, type RehabToolPort, type RehabCall, rehabToolNames } from '../runtime/rehabTools';
import { mapKnowledgeActionToApp, type ExecutableActionMapping } from './exerciseMapping';
import type { ConversationModel } from '../runtime/conversation';
import type { SemanticTurn } from '../runtime/semanticRouter';
import {unavailableEquipment} from './taskState';

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
  app_mappings?: (ExecutableActionMapping | null)[];
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
export function parseRehabToolSelection(raw: string, fallbackQuery = ''): RehabToolSelection | null {
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
    if (args.query !== undefined && args.query !== null && (typeof args.query !== 'string' || args.query.length > 400)) return null;
    if (args.exercise_id !== undefined && !/^[A-Za-z0-9_-]{1,80}$/.test(String(args.exercise_id))) return null;
    if (args.joint !== undefined && (!text(args.joint, 40) || !JOINTS.has(args.joint))) return null;
    if (args.goal !== undefined && !text(args.goal, 300)) return null;
    if (args.region !== undefined && !text(args.region, 100)) return null;
    if (args.equipment !== undefined && !stringArray(args.equipment, 12, 120)) return null;
    if (args.restrictions !== undefined && !stringArray(args.restrictions, 12, 200)) return null;
    if (args.level !== undefined && (typeof args.level !== 'number' || !Number.isInteger(args.level) || args.level < 0 || args.level > 3)) return null;
    if (args.screening_confirmed !== undefined && typeof args.screening_confirmed !== 'boolean') return null;
    const normalizedArgs = { ...args };
    if (item.name === 'rehab.search_knowledge' || item.name === 'rehab.search_guidance') {
      // Real models occasionally omit a search query despite selecting a search tool.
      // Recover deterministically from the current user request instead of rejecting
      // the entire tool plan; never invent a body region or clinical condition.
      if (!text(normalizedArgs.query, 400)) {
        const safeFallback = fallbackQuery.trim().slice(0, 400);
        if (!safeFallback) return null;
        normalizedArgs.query = safeFallback;
      }
    }
    if (item.name === 'rehab.run_plan_algorithm') {
      if (!text(args.goal, 300) || !text(args.region, 100) || !Array.isArray(args.equipment) ||
          !Array.isArray(args.restrictions) || !Number.isInteger(args.level) ||
          typeof args.screening_confirmed !== 'boolean') return null;
    }
    calls.push({
      name: item.name as RehabWorkflowTool,
      arguments: normalizedArgs as RehabToolCall['arguments'],
      reason: item.reason,
    });
  }
  return { version: 1, calls, uncertainties: value.uncertainties };
}

const TOOL_SYSTEM = `你是安康康复分析阶段的工具规划器。你已经收到第一轮语义 JSON。你的任务不是回答用户，也不是生成康复方案，只决定为了分析当前问题需要读取哪些已注册工具。
可用工具：
- rehab.get_training_plan：读取本人当前康复计划，arguments为{}
- rehab.get_training_history：读取本人训练历史，arguments可为{}，只按明确来源提供exercise_id或joint
- rehab.get_recent_assessments：读取本人近期评估，arguments可为{}，只按明确来源提供exercise_id或joint
- rehab.search_knowledge：查询动作知识库；只能查询已存在动作/动作条件/停止条件，arguments必须为{"query":"非空搜索词"}，query最长400字
- rehab.search_guidance：查询康复指导资料；用于训练原则、剂量/进阶、单人执行等，arguments必须为{"query":"非空搜索词"}，query最长400字
- rehab.run_plan_algorithm：运行确定性本地计划筛选算法；只有在目标、部位、器材、限制、等级和 screening_confirmed 都有明确来源时才能调用
规则：
1. 只选择真正需要的工具，可以一次选择多个；最多8个。
2. 不创造动作ID，不创造个人记录，不把“建议调用工具”当成工具执行结果。
3. 不诊断，不判断医学安全许可；如果信息不足写入 uncertainties。
4. run_plan_algorithm 的 screening_confirmed 不得根据“看起来安全”猜测；没有明确数据时不要调用。
5. 个人工具只能读取当前本人数据，不能选择 participant_id。
6. 搜索工具不可省略query或给arguments:{}；不能确定搜索词时省略该调用并写入uncertainties。
7. 输出且仅输出 JSON。格式示例（仅展示参数契约，不要求每轮照抄这些调用）：{"version":1,"calls":[{"name":"rehab.get_training_plan","arguments":{},"reason":"读取本人当前计划"},{"name":"rehab.search_guidance","arguments":{"query":"居家训练原则与休息"},"reason":"查询公共训练原则"}],"uncertainties":[]}`;

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
    const fallbackQuery = [
      semantic.goal,
      ...((semantic.intents ?? []).map(intent => intent.goal)),
      ...semantic.mentions.map(mention => mention.text),
      userText,
    ].filter(Boolean).join(' ').slice(0, 400);
    const parsed = parseRehabToolSelection(raw, fallbackQuery);
    if (!parsed) return null;

    // Plan generation has minimum data dependencies. The LLM may request extra
    // tools, but omission of the knowledge/guidance search must not abort the flow.
    const planGeneration = (semantic.intents ?? []).some(intent => intent.type === 'plan_generation');
    if (!planGeneration) return parsed;
    const required: RehabToolCall[] = [
      {name:'rehab.search_knowledge',arguments:{query:fallbackQuery},reason:'计划生成必须检索真实动作卡'},
      {name:'rehab.search_guidance',arguments:{query:fallbackQuery},reason:'计划生成必须检索适用原则与停止条件'},
    ];
    const selectedSearches = parsed.calls.filter(call =>
      call.name === 'rehab.search_knowledge' || call.name === 'rehab.search_guidance');
    const requiredMissing = required.filter(requiredCall =>
      !selectedSearches.some(call => call.name === requiredCall.name));
    const otherCalls = parsed.calls.filter(call =>
      call.name !== 'rehab.search_knowledge' && call.name !== 'rehab.search_guidance');
    const calls = [...selectedSearches, ...requiredMissing, ...otherCalls].slice(0, MAX_TOOL_CALLS);
    return {...parsed,calls};
  } catch {
    check();
    return null;
  }
}

function normalizeRegion(value: string): string {
  const map: Record<string,string> = { 膝盖:'膝', 膝关节:'膝', 肩膀:'肩', 肩关节:'肩', 髋关节:'髋', 脚踝:'踝', 踝关节:'踝', 手腕:'腕', 腕关节:'腕' };
  return map[value.trim()] ?? value.trim();
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
  if (!Array.isArray(candidate.candidate_actions) || !candidate.candidate_actions.length || candidate.candidate_actions.length > 6 ||
      typeof candidate.doctor_review_required !== 'boolean' ||
      !stringArray(candidate.doctor_review_reasons, 12, 300) || !stringArray(candidate.uncertainties, 12, 300)) {
    return { status: 'rejected', reasons: ['invalid_candidate_lists'], plan: candidate };
  }
  const validIds = new Set<string>(cards.filter(c => c.kind === 'training' && c.complete).map(c => c.id));
  const seen = new Set<string>();
  for (const item of candidate.candidate_actions) {
    if (!record(item) || !/^[A-Z]-[A-Z0-9]+-\d+$/.test(String(item.exercise_id)) ||
        !validIds.has(item.exercise_id) || !text(item.reason, 500) ||
        (item.dose !== undefined && !text(item.dose, 500))) {
      return { status: 'rejected', reasons: ['unknown_or_incomplete_action'], plan: candidate };
    }
    if (seen.has(item.exercise_id)) return { status: 'rejected', reasons: ['duplicate_candidate_action'], plan: candidate };
    seen.add(item.exercise_id);
    const card = cards.find(c => c.id === item.exercise_id);
    if (!card?.sourceDose || !card.startConditions || !card.stopConditions || !card.equipment) {
      return { status: 'rejected', reasons: ['action_card_missing_required_conditions'], plan: candidate };
    }
    if (item.dose !== undefined && !card.sourceDose.includes(item.dose)) {
      return {status:'rejected',reasons:['dose_not_verbatim_from_action_card:' + item.exercise_id],plan:candidate};
    }
  }
  if (candidate.algorithm_input.restrictions.some(v => v.trim())) reasons.push('individual_restrictions_require_review');
  if (!candidate.algorithm_input.screening_confirmed) reasons.push('screening_not_confirmed');
  if (candidate.uncertainties.length) reasons.push('unresolved_uncertainty');
  if (candidate.doctor_review_required) reasons.push(...candidate.doctor_review_reasons.map(v => 'doctor_review:' + v));
  // Model flags cannot establish assessment, trial, individual eligibility or clinician approval.
  reasons.push('applicability_and_professional_review_not_verified');
  return { status: 'needs_review', reasons, plan: candidate };
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
      (a.level !== null && (typeof a.level !== 'number'||!Number.isInteger(a.level)||a.level<0||a.level>3)) ||
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
      startConditions:c.startConditions,stopConditions:c.stopConditions,sourceDose:c.sourceDose,
      sourceRefs:c.sourceRefs,content:c.content
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
    catch { return {name:call.name,data:{status:'needs_review',reason:'trusted_screening_not_available',items:[],reviewRequired:true}}; }
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
    // Chat consent does not authorize transmitting stored personal health records.
    tool_results:toolResults.filter(result => ['rehab.search_knowledge','rehab.search_guidance','rehab.run_plan_algorithm'].includes(result.name)),
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
  userStatements?: readonly string[];
  reads?: Pick<RehabToolPort,'read'>;
  participantId: string;
  check?: () => void;
}): Promise<{candidate: RehabCandidatePlan | null; validation: RehabPlanValidation | null; toolResults:{name:string;data:unknown}[]; selection:RehabToolSelection|null}> {
  const check=input.check??(()=>{});
  let selection=await selectRehabTools(input.model,input.semantic,input.userText,check);
  if(!selection) return {candidate:null,validation:null,toolResults:[],selection:null};

  // Plan generation always checks the user's existing plan/history/assessments when
  // the authenticated local read port exists. These receipts remain local and are
  // explicitly excluded from the cloud candidate-generation payload below.
  const planGeneration = (input.semantic.intents ?? []).some(intent => intent.type === 'plan_generation');
  if (planGeneration && input.reads) {
    const requiredReads: RehabToolCall[] = [
      {name:'rehab.get_training_plan',arguments:{},reason:'核对本人当前计划'},
      {name:'rehab.get_training_history',arguments:{},reason:'核对本人训练历史'},
      {name:'rehab.get_recent_assessments',arguments:{},reason:'核对本人近期评估'},
    ];
    const calls = [...requiredReads, ...selection.calls.filter(call =>
      !requiredReads.some(requiredCall => requiredCall.name === call.name))].slice(0, MAX_TOOL_CALLS);
    selection = {...selection,calls};
  }
  const toolResults:{name:string;data:unknown}[]=[];
  const unique=new Set<string>();
  for(const call of selection.calls){
    const key=call.name+JSON.stringify(call.arguments);
    if(unique.has(key))continue;
    unique.add(key);
    try { toolResults.push(await executeCall(call,input.reads,input.participantId,check)); }
    catch { toolResults.push({name:call.name,data:{status:'failed',reason:'tool_execution_failed'}}); }
  }
  if (planGeneration) {
    const knowledge = toolResults.find(result => result.name === 'rehab.search_knowledge');
    const algorithm = toolResults.find(result => result.name === 'rehab.run_plan_algorithm');
    const algorithmData = algorithm?.data;
    const algorithmItems = record(algorithmData) && Array.isArray(algorithmData.items) ? algorithmData.items : [];
    // Do not ask a model to invent a plan when no real action card or algorithm
    // candidate exists. An empty search is a valid result, not a prompt to guess.
    if (!knowledge || !Array.isArray(knowledge.data) || (knowledge.data.length === 0 && algorithmItems.length === 0)) {
      return {candidate:null,validation:null,toolResults,selection};
    }
  }

  const candidate=await generateRehabCandidate(input.model,input.semantic,input.userText,toolResults,check);
  if(!candidate) return {candidate:null,validation:null,toolResults,selection};

  // The deterministic algorithm is authoritative when the LLM explicitly requested it.
  // The model may propose inputs, but the host owns execution and the returned result.
  const algorithmResult = toolResults.find(r => r.name === 'rehab.run_plan_algorithm')?.data as ReturnType<typeof localPlan> | undefined;
  let validation=validateRehabPlan(candidate);
  const unavailable=unavailableEquipment(input.userStatements??[input.userText]);
  if(unavailable.some(equipment=>candidate.algorithm_input.equipment.some(value=>value.includes(equipment)) ||
    candidate.candidate_actions.some(action=>{
      // A card may explicitly offer a no-load version and optional resistance.
      // Optional equipment is not required unless the candidate itself selects it.
      const required=catalogue.find(card=>card.id===action.exercise_id)?.equipment.split('可选')[0]??'';
      return equipment==='椅子'?required.includes('椅'):required.includes(equipment);
    }))){
    validation={...validation,status:'rejected',reasons:[...validation.reasons,'explicit_equipment_conflict']};
  }
  const retrievedIds = new Set(toolResults.flatMap(result =>
    result.name === 'rehab.search_knowledge' && Array.isArray(result.data)
      ? result.data.map(card => card.id as string)
      : result.name === 'rehab.run_plan_algorithm' && record(result.data) && Array.isArray(result.data.items)
        ? result.data.items.map(item => item.id as string) : []));
  if (candidate.candidate_actions.some(action => !retrievedIds.has(action.exercise_id))) {
    validation = {...validation,status:'rejected',reasons:[...validation.reasons,'candidate_action_not_retrieved']};
  }
  const appMappings = candidate.candidate_actions.map(action => mapKnowledgeActionToApp(action.exercise_id));
  validation = {...validation,app_mappings:appMappings};
  if (appMappings.some(mapping => mapping === null)) {
    validation = {
      ...validation,
      status:'rejected',
      reasons:[...validation.reasons,'candidate_action_not_mapped_to_executable_app_movement'],
    };
  }
  if (algorithmResult) {
    validation = { ...validation, algorithm_result: algorithmResult };
    const algorithmIds = new Set((algorithmResult.items ?? []).map(item => item.id));
    if (algorithmResult.status !== 'needs_review' && candidate.candidate_actions.some(action => !algorithmIds.has(action.exercise_id))) {
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
    if (algorithmResult.status === 'needs_review' || algorithmResult.reviewRequired) {
      validation = {
        ...validation,
        status: validation.status === 'rejected' ? 'rejected' : 'needs_review',
        reasons: [...validation.reasons, 'algorithm_requires_review'],
      };
    }
  }
  return {candidate,validation,toolResults,selection};
}

/** Read-only rehabilitation explanations do not need a fake training plan. */
export type RehabAnswerTask = 'exercise_guidance' | 'progress_analysis' | 'rehab_question' | 'plan_generation';

export function rehabAnswerTask(semantic: SemanticTurn): RehabAnswerTask {
  const intents = new Set((semantic.intents ?? []).map(i => i.type));
  if (intents.has('plan_generation')) return 'plan_generation';
  if (intents.has('exercise_guidance')) return 'exercise_guidance';
  if (intents.has('records_query') || intents.has('plan_query')) return 'progress_analysis';
  return 'rehab_question';
}

/** Public exercise/guidance answers use verified local sources; private receipts stay local. */
export async function runRehabReadOnlyAnswer(input: {
  semantic: SemanticTurn;
  userText: string;
  reads?: Pick<RehabToolPort,'read'>;
  participantId: string;
  check?: () => void;
}): Promise<{text: string; source_ids: string[]; status: 'found' | 'missing'}> {
  const check = input.check ?? (() => {});
  const task = rehabAnswerTask(input.semantic);
  if (task === 'progress_analysis') {
    if (!input.reads) return {text:'当前没有连接本人的康复记录，暂时无法分析个人训练变化。',source_ids:[],status:'missing'};
    const outputs: string[] = [];
    let successfulReads = 0;
    for (const name of ['rehab.get_training_plan','rehab.get_training_history','rehab.get_recent_assessments'] as const) {
      try {
        const data = await readRehabReceipt(input.reads,{name,arguments:{}},input.participantId,check);
        // Deliberately no external LLM call: user's health record is not model context.
        successfulReads++;
        outputs.push(describeLocalRehabReceipt(data));
      } catch {
        outputs.push(name + '：读取失败或未授权');
      }
    }
    return {text:(successfulReads ? '已在本地读取以下范围内的本人资料；未将个人记录发送给云端模型。\n' : '本人康复资料读取失败。\n')+outputs.join('\n')+
      '\n目前不能单凭这些记录判断康复是否有效；请对照相同条件下的评估结果。',source_ids:[],status:successfulReads?'found':'missing'};
  }
  const references = searchCards(input.userText);
  const section = searchGuidance(input.userText);
  const ids = references.map(card=>card.id);
  if (!references.length && !section) {
    return {text:'现有动作知识库或指导资料没有找到匹配内容。请告诉我动作名称、编号或具体训练问题；不会编造动作和剂量。',source_ids:[],status:'missing'};
  }
  const blocks = references.map(card =>
    card.id+'｜'+card.name+'\n'+card.content.slice(0,2600)+
    '\n开始条件：'+card.startConditions+'\n停止条件：'+card.stopConditions);
  if (section) blocks.push(section.title+'\n'+section.content.slice(0,2600));
  return {text:blocks.join('\n\n'),source_ids:ids,status:'found'};
}

/** Safe user-facing rendering of a validated draft; it is not persistence. */
export function renderRehabDraft(result: RehabPlanValidation | null): string {
  if(!result) return '康复分析暂时没有形成可验证的候选方案。请补充具体目标、部位或当前训练情况。';
  if(result.status==='rejected') {
    if(result.reasons.includes('explicit_equipment_conflict')){
      return '这份候选仍包含你明确不能使用的器材，已拦下，没有修改计划。可以补充可用器材后重新整理草案。';
    }
    if (result.reasons.includes('candidate_action_not_mapped_to_executable_app_movement')) {
      return '动作库中存在当前康复 App 尚不能执行的动作，因此不能把这份候选直接生成到你的计划里。需要先补齐动作映射；本次没有修改任何计划。';
    }
    return '这次康复分析没有形成符合系统结构的候选方案，请补充具体情况后再试。';
  }
  const p=result.plan;
  const lines=['以下仅为动作库候选，尚未成为个人训练处方。'];
  if(p.candidate_actions.length) lines.push('候选动作：'+p.candidate_actions.map(a=>a.exercise_id).join('、'));
  if(result.algorithm_result?.status === 'no_match') lines.push('当前条件没有匹配的规则方案。');
  else if(result.algorithm_result?.status === 'needs_review') lines.push('现有资料还不足以核对个人适用条件。');
  if(result.status==='needs_review') lines.push('当前方案仍需核对本人评估、动作开始条件、当次试做及必要的专业审核；普通确认不能替代审核。');
  else lines.push('这是一份候选方案，尚未写入你的训练计划。');
  return lines.join('\n');
}
