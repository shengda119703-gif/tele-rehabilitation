import type { SemanticTurn } from './semanticRouter';

export type ScopeFallbackKind = 'clinical_handoff' | 'unsupported_operation' | 'out_of_scope';

export interface ScopeFallback {
  kind: ScopeFallbackKind;
  reply: string;
}

/**
 * Explicit terminal route for requests outside the assistant's registered routes.
 *
 * This is not a medical triage engine. Existing clinical/safety handling runs
 * before this function; it never overrides an existing safety action.
 * It also never claims to contact a clinician, book an appointment, or execute
 * an application operation that is not registered with the host.
 */
export function resolveScopeFallback(semantic: SemanticTurn, userText: string): ScopeFallback | null {
  const clauses = userText.split(/[，,。；;！？!?]/).map(value => value.trim()).filter(Boolean);
  const clinicalBoundary = clauses.some(clause => {
    const negated = /(?:不想|不需要|无需|不用|不要|别|不希望|不打算).{0,10}(?:诊断|确诊|开药|处方|调整用药|停药|换药|治疗方案|咨询医生|看医生|转诊)/.test(clause);
    if (negated) return false;
    return /(?:咨询医生|看医生|转诊|就医|检查结果.{0,12}(?:怎么办|怎么处理|严重吗)|(?:帮我|请|能不能|可不可以|替我|给我|想让你|需要你|你能|你帮我).{0,12}(?:诊断|确诊|开药|开处方|调整用药|停药|换药|决定治疗方案|制定治疗方案)|(?:要不要|是否需要|该不该|需不需要).{0,10}(?:咨询医生|看医生|就医|诊断|调整用药|停药|换药))/.test(clause);
  });

  // Explicit requests for diagnosis/treatment decisions are escalated even when
  // the first router labels them as health or rehab rather than "other".
  if (clinicalBoundary && ['other', 'health', 'rehab'].includes(semantic.route)) {
    return {
      kind: 'clinical_handoff',
      reply: '这件事需要医生结合病史、查体和必要检查作出判断。我可以帮你整理症状、既往情况和想问医生的问题，但不能替医生诊断、开药或决定治疗。如果症状正在明显加重，或你觉得情况紧急，请及时联系当地医疗服务；我没有替你联系医生或完成预约。',
    };
  }

  if (semantic.route !== 'other') return null;

  const unsupportedOperation = clauses.some(clause => {
    if (/(?:不要|别|不需要|不用|无需|不想|不打算).{0,10}(?:打开|进入|跳转|设置提醒|发提醒|预约|挂号|联系医生|打电话|呼叫救护车|发送转诊|替我联系|帮我联系)/.test(clause)) return false;
    return /(?:打开|进入|跳转|设置提醒|发提醒|预约|挂号|联系医生|打电话|呼叫救护车|发送转诊|替我联系|帮我联系)/.test(clause);
  });
  if (unsupportedOperation) {
    return {
      kind: 'unsupported_operation',
      reply: '这个请求目前不在已接通的康复助手操作范围内，我还没有执行它，也不会假装已经完成。你可以在应用对应页面手动操作；如果你告诉我想完成的目标，我可以帮你整理下一步。',
    };
  }

  return {
    kind: 'out_of_scope',
    reply: '这个请求暂时超出安康康复助手当前的功能范围。我目前主要支持一般健康信息咨询、康复动作与训练分析、本人康复记录查询，以及已接通的康复计划和训练安排操作。你可以换一种方式描述目标；如果问题需要个体化诊断或治疗决策，请咨询医生。',
  };
}
