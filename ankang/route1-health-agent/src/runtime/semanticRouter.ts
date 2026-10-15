import type {ConversationModel} from './conversation';

export type SemanticRoute = 'chat' | 'rehab' | 'records' | 'module' | 'health';
export interface SemanticTurn {
  version: 1;
  route: SemanticRoute;
  goal: string;
  mentions: {kind: 'symptom'|'exercise'|'body_region'|'other'; text: string}[];
  uncertain: string[];
  suggested_tool: 'rehab.get_training_plan'|'rehab.get_training_history'|'rehab.get_recent_assessments'|null;
}

const ROUTES = new Set(['chat','rehab','records','module','health']);
const TOOLS = new Set(['rehab.get_training_plan','rehab.get_training_history','rehab.get_recent_assessments']);
const SYSTEM = `你是安康应用的第一轮语义解析器。对每条用户消息输出且仅输出一个 JSON 对象：
{"version":1,"route":"chat|rehab|records|module|health","goal":"用户想做什么","mentions":[{"kind":"symptom|exercise|body_region|other","text":"原文出现的内容"}],"uncertain":["缺失或模糊的信息"],"suggested_tool":null}
route：chat=普通闲聊；rehab=康复知识/动作/训练讨论；records=查询本人康复计划/评估/训练历史；module=界面/其他操作；health=报告症状或健康状况。可用只读工具：rehab.get_training_plan, rehab.get_training_history, rehab.get_recent_assessments；如确有本人康复记录查询意图，在 suggested_tool 中填写其中一个；其余填 null。
不要虚构病情、记录、诊断或权限；不确定写入 uncertain。模型的工具建议只是请求，不代表已执行。不要输出 Markdown。`;

export function parseSemanticTurn(raw: string): SemanticTurn | null {
  try {
    const value: unknown = JSON.parse(raw.trim().replace(/^\`\`\`(?:json)?\s*/i,'').replace(/\s*\`\`\`$/,''));
    if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
    const v = value as Record<string,unknown>;
    if (v.version !== 1 || typeof v.route !== 'string' || !ROUTES.has(v.route) ||
        typeof v.goal !== 'string' || v.goal.length > 400 || !Array.isArray(v.mentions) ||
        v.mentions.length > 12 || !Array.isArray(v.uncertain) || v.uncertain.length > 12 ||
        (v.suggested_tool !== null && (typeof v.suggested_tool !== 'string' || !TOOLS.has(v.suggested_tool)))) return null;
    const mentions: SemanticTurn['mentions'] = [];
    for (const x of v.mentions) {
      if (!x || typeof x !== 'object' || !['symptom','exercise','body_region','other'].includes(x.kind) ||
          typeof x.text !== 'string' || !x.text.trim() || x.text.length > 100) return null;
      mentions.push({kind:x.kind,text:x.text});
    }
    if (!v.uncertain.every(x => typeof x === 'string' && x.length <= 120)) return null;
    return {version:1,route:v.route as SemanticRoute,goal:v.goal,mentions,
      uncertain:v.uncertain as string[],suggested_tool:v.suggested_tool as SemanticTurn['suggested_tool']};
  } catch { return null; }
}

/** Semantics only. No external model call when a turn is private/no-record. */
export async function understandSemanticTurn(model: ConversationModel, text:string): Promise<SemanticTurn|null> {
  try {
    const response = await model.reply({messages:[{role:'user',content:SYSTEM+'\n用户输入：'+JSON.stringify(text)}]});
    return parseSemanticTurn(response);
  } catch { return null; }
}
