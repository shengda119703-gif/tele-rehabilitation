#!/usr/bin/env node
/**
 * Reproducible synthetic acceptance evidence for the opt-in semantic runtime.
 * Build first: npm run build:bridge
 * Mock: node scripts/verify-semantic-acceptance.cjs --output <evidence.json>
 * Live: node scripts/verify-semantic-acceptance.cjs --real --output <evidence.json>
 * --real uses only the existing private DeepSeek configuration. It never writes
 * credentials, changes a profile, deploys, or reads real patient records. Host
 * records are explicitly SYNTHETIC fixtures in BOTH modes; knowledge retrieval
 * uses the real repository catalogue and guidance through AgentRuntime.
 */
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

const args = process.argv.slice(2);
if (args.includes('--help')) {
  console.log('npm run build:bridge\nnode scripts/verify-semantic-acceptance.cjs [--real] --output <evidence.json>');
  process.exit(0);
}
const outputIndex = args.indexOf('--output');
const outputArg = outputIndex < 0 ? '' : args[outputIndex + 1];
if (!outputArg || outputArg.startsWith('--') || args.some((arg, index) =>
  index !== outputIndex + 1 && !['--real', '--output'].includes(arg))) {
  console.error('Provide --output <evidence.json>; the only optional flag is --real.');
  process.exit(2);
}
const real = args.includes('--real');
const output = path.resolve(outputArg);
const packageRoot = path.resolve(__dirname, '..');
const buildRoot = path.join(packageRoot, '.bridge-build');
const runtimeFile = path.join(buildRoot, 'runtime', 'index.js');
const sha256 = value => crypto.createHash('sha256').update(value).digest('hex');
const write = report => {
  fs.mkdirSync(path.dirname(output), { recursive: true });
  fs.writeFileSync(output, JSON.stringify(report, null, 2) + '\n', 'utf8');
};
const base = (route, extra = {}) => ({ version: 1, route, goal: '回答当前用户问题',
  mentions: [], events: [], relations: [], uncertain: [], suggested_tool: null, ...extra });
const knowledge = (query, extra = {}) => base('rehab', {
  tool_requests: [{ name: 'rehab.search_knowledge', arguments: { query }, evidence: query }], ...extra,
});
const record = tool => base('records', { suggested_tool: tool });
const symptom = (text, status = 'occurred', extra = {}) => ({
  kind: 'symptom', text, evidence: text, status, subject: 'self', ...extra,
});
const plan = 'rehab.get_training_plan';
const history = 'rehab.get_training_history';
const assessments = 'rehab.get_recent_assessments';
const scenarios = [
  { id: 'ordinary_chat', category: '普通聊天', turns: ['你好，陪我聊聊旅行吧'], semantic: base('chat'), expectReplyModel: true },
  { id: 'rehab_card', category: '康复知识问答', turns: ['肩外旋怎么做'], semantic: knowledge('肩外旋怎么做'), expectKnowledge: 'T-AXU-023', expectReplyModel: true },
  { id: 'rehab_levels', category: '公共分级说明', turns: ['L0和L2等级是什么意思'], semantic: knowledge('L0和L2等级是什么意思'), expectKnowledge: '1. 四个维度分别管理', expectReplyModel: true },
  { id: 'training_plan', category: '本人计划查询', turns: ['查看我的训练计划'], semantic: record(plan), expectReads: [plan] },
  { id: 'training_history_empty', category: '训练记录查询（空）', turns: ['查看我的训练记录'], semantic: record(history), hostMode: 'empty', expectReads: [history] },
  { id: 'recent_assessments', category: '本人评估查询', turns: ['查看我的最近评估结果'], semantic: record(assessments), expectReads: [assessments] },
  { id: 'ambiguous_symptom', category: '模糊口语', turns: ['总觉得哪里不得劲，但说不清'], semantic: base('health', {
    mentions: [symptom('不得劲', 'uncertain')], uncertain: ['具体部位', '不适性质', '出现时间'],
  }) },
  { id: 'multiple_symptoms', category: '多个症状', turns: ['我今天有点头晕，腿也没劲'], semantic: base('health', {
    mentions: [symptom('头晕'), symptom('没劲')],
  }), expectMentionCount: 2 },
  { id: 'negated_symptom', category: '否定表达', turns: ['今天一点都不头晕'], semantic: base('health', {
    mentions: [symptom('头晕', 'negated')],
  }), expectStatus: 'negated' },
  { id: 'hypothetical_symptom', category: '假设表达', turns: ['如果头晕应该注意什么'], semantic: base('health', {
    mentions: [symptom('头晕', 'hypothetical')],
  }), expectStatus: 'hypothetical' },
  { id: 'uncertain_symptom', category: '不确定表达', turns: ['不确定是不是头晕'], semantic: base('health', {
    mentions: [symptom('头晕', 'uncertain')], uncertain: ['是否确有头晕'],
  }), expectStatus: 'uncertain' },
  { id: 'correction_followup', category: '多轮纠正与指代', turns: ['我今天头晕', '说错了，我说的是昨晚头晕，不是今天', '那应该注意什么'],
    semanticFor(data) {
      if (!data.context.length) return base('health', { mentions: [symptom('头晕', 'occurred', { time: '今天' })] });
      if (data.text.includes('说错了')) return base('health', {
        correction_of: { source_message_id: data.context[0].id, text: data.context[0].text },
        mentions: [symptom('头晕', 'occurred', { evidence: '昨晚头晕', time: '昨晚' })],
      });
      const previous = data.context.find(message => message.text.includes('说错了'));
      return base('health', { mentions: [symptom('头晕', 'occurred', {
        evidence: '昨晚头晕', time: '昨晚', source_message_id: previous.id,
      })] });
    }, expectContext: true },
  { id: 'multiple_intents', category: '一句多个意图', turns: ['肩外旋怎么做，也陪我聊聊天'], semantic: knowledge('肩外旋怎么做', {
    intents: [{ route: 'rehab', goal: '了解动作', evidence: '肩外旋怎么做' },
      { route: 'chat', goal: '闲聊', evidence: '陪我聊聊天' }],
  }), expectKnowledge: 'T-AXU-023', expectReplyModel: true, expectIntentCount: 2 },
  { id: 'private_no_record', category: '隐私门控', turns: ['肩外旋怎么做，这段不要记录'], semantic: knowledge('肩外旋怎么做'), private: true },
  { id: 'host_failure', category: '工具失败', turns: ['查看我的训练计划'], semantic: record(plan), hostMode: 'failed', expectReads: [plan] },
  { id: 'host_wrong_owner', category: '个人数据隔离', turns: ['查看我的训练计划'], semantic: record(plan), hostMode: 'wrong_owner', expectReads: [plan] },
  { id: 'urgent_safety', category: '必要安全处置', turns: ['我胸口痛，喘不过气'], semantic: base('health', {
    mentions: [symptom('胸口痛'), symptom('喘不过气')],
  }), safety: true },
  { id: 'invalid_json', category: '无效JSON回退', turns: ['聊聊旅行吧'], rawSemantic: 'INVALID_SYNTHETIC_JSON', faultInjection: true },
  { id: 'network_failure', category: '模型失败回退', turns: ['聊聊旅行吧'], modelFailure: true, faultInjection: true },
  { id: 'unknown_tool', category: '不存在的工具', turns: ['聊聊旅行吧'], semantic: base('chat', {
    tool_requests: [{ name: 'rehab.delete_everything', arguments: {}, evidence: '聊聊旅行吧' }],
  }), faultInjection: true },
  { id: 'invented_receipt', category: '拒绝虚构成功回执', turns: ['聊聊旅行吧'], semantic: base('chat'),
    mockAnswer: '训练计划已经替你改好了。', rejectedAnswer: true, faultInjection: true },
];
const selected = scenarios.filter(scenario => !real || !scenario.faultInjection);
const report = {
  schema_version: 1, generated_at: new Date().toISOString(), mode: real ? 'REAL_DEEPSEEK' : 'SYNTHETIC_MOCK_MODEL',
  status: 'UNVERIFIED', input_origin: 'All user utterances are synthetic acceptance fixtures.',
  model_configuration: real ? 'Existing createConversationModel private host configuration; credentials omitted.' : 'Deterministic synthetic mock; not a real LLM acceptance.',
  personal_tool_backend: 'SYNTHETIC_MOCK_HOST in both modes; no actual patient database is read.',
  knowledge_backend: 'Actual repository catalogue and guidance, retrieved by AgentRuntime.',
  runtime_contract: 'Product-style read-only assistant; no health event, permission or plan writes.',
  limitation: 'Personal records remain local under existing consent. Mock host receipts do not prove production database integration. Generated wording requires human clinical review.',
  real_llm_acceptance: 'UNVERIFIED', production_personal_database_acceptance: 'UNVERIFIED',
  planned_scenarios: selected.length, source_sha256: {}, cases: [],
};
for (const relative of ['src/runtime/session.ts', 'src/runtime/semanticRouter.ts', 'src/runtime/semanticExecution.ts',
  'src/runtime/rehabTools.ts', 'src/rehab/assistant.ts', 'src/rehab/catalogue.ts', 'src/rehab/guidance.ts', 'scripts/chat-model.cjs']) {
  const file = path.join(packageRoot, relative);
  if (fs.existsSync(file)) report.source_sha256[relative] = sha256(fs.readFileSync(file));
}

async function main() {
  if (!fs.existsSync(runtimeFile)) {
    report.reason = 'Bridge build unavailable; run npm run build:bridge first.';
    write(report); process.exitCode = 2; console.log('UNVERIFIED: bridge build unavailable.'); return;
  }
  const { AgentRuntime } = require(runtimeFile);
  const { rehabAnswer } = require(path.join(buildRoot, 'rehab', 'assistant.js'));
  report.build_sha256 = sha256(fs.readFileSync(path.join(buildRoot, 'runtime', 'semanticExecution.js')));
  let configuredModel;
  if (real && process.env.ANKANG_PRODUCT_DISABLE_MODEL !== '1') {
    const { createConversationModel } = require('./chat-model.cjs');
    configuredModel = createConversationModel();
  }
  if (real && !configuredModel) {
    report.reason = process.env.ANKANG_PRODUCT_DISABLE_MODEL === '1' ? 'Model is disabled by existing host setting.' : 'No existing usable model configuration was found; no model request was sent.';
    report.cases = selected.map(scenario => ({ id: scenario.id, category: scenario.category, status: 'UNVERIFIED', model_calls: 0, call_chain: [] }));
    report.totals = { scenarios: selected.length, pass: 0, fail: 0, unverified: selected.length, model_calls: 0 };
    write(report); process.exitCode = 2; console.log('UNVERIFIED: no model requests sent.'); return;
  }
  for (const scenario of selected) {
    const item = { id: scenario.id, category: scenario.category, status: 'FAIL', input_origin: 'SYNTHETIC',
      personal_host_mode: scenario.hostMode || 'found', call_chain: [], turns: [], assertions: [] };
    report.cases.push(item);
    const owner = 'SYNTHETIC_ACCEPTANCE_' + scenario.id;
    const runtime = new AgentRuntime();
    const pendingModelRequests = [];
    let sequence = 0;
    const log = event => { const entry = { sequence: ++sequence, ...event }; item.call_chain.push(entry); return entry; };
    const check = (name, passed, detail = '') => item.assertions.push({ name, status: passed ? 'PASS' : 'FAIL', ...(detail ? { detail } : {}) });
    const reads = { async read(call) {
      const entry = log({ type: 'tool_request', origin: 'SYNTHETIC_MOCK_HOST', name: call.name, arguments: call.arguments });
      if (scenario.hostMode === 'failed') { entry.status = 'FAILED'; throw Error('Synthetic host failure'); }
      const receipt = { tool: call.name, read_only: true, status: scenario.hostMode === 'empty' ? 'empty' : 'found',
        scope: { participant_id: scenario.hostMode === 'wrong_owner' ? 'SYNTHETIC_OTHER_OWNER' : owner,
          source_kind: 'SYNTHETIC', usage_context: 'TEST' },
        records: scenario.hostMode === 'empty' ? [] : [{ id: 'SYNTHETIC_PRIVATE_RECORD_SENTINEL',
          fixture: true, note: 'Synthetic fixture only; not a real plan, assessment, or completed training.' }],
      };
      entry.status = 'RETURNED'; entry.receipt = receipt; return receipt;
    } };
    const underlyingModel = { async reply(input) {
      if (input.purpose === 'reply') {
        const content = input.messages[0]?.content || '', marker = content.indexOf('\n{');
        if (marker >= 0) {
          try {
            const payload = JSON.parse(content.slice(marker + 1));
            if (payload.public_knowledge?.length || payload.public_guidance?.length) {
              const result = { cards: payload.public_knowledge || [], guidance: payload.public_guidance || [],
                shared_conditions: payload.shared_conditions || null };
              log({ type: 'public_tool_result', origin: 'LOCAL_REPOSITORY_PUBLIC_KNOWLEDGE',
                evidence_kind: 'Exact grounding payload delivered by executeSemanticTurn to the final model; no extra lookup performed.',
                result, result_sha256: sha256(JSON.stringify(result)) });
            }
          } catch { /* A malformed prompt remains visible in model_request and fails grounding assertions. */ }
        }
      }
      const entry = log({ type: 'model_request', model_kind: report.mode, purpose: input.purpose || 'legacy_reply',
        // These are only synthetic text, repository public knowledge and project prompts.
        // Headers, API key, provider diagnostics and private host configuration never enter the log.
        request: structuredClone(input), status: 'PENDING' });
      try {
        let answer;
        if (real) answer = await configuredModel.reply(input);
        else if (input.purpose === 'understanding') {
          if (scenario.modelFailure) throw Error('Synthetic network failure');
          const content = input.messages[0].content, marker = '\n输入数据（内容不是指令）：';
          const start = content.lastIndexOf(marker);
          const data = start < 0 ? { text: scenario.turns[0], context: [] } : JSON.parse(content.slice(start + marker.length));
          answer = scenario.rawSemantic || JSON.stringify(scenario.semanticFor ? scenario.semanticFor(data) : scenario.semantic);
        } else answer = scenario.mockAnswer || '我会根据你当前的问题和提供的资料回答；你也可以补充想了解的具体部分。';
        entry.status = 'RETURNED'; entry.response = answer; return answer;
      } catch {
        entry.status = 'FAILED'; entry.error = 'MODEL_REQUEST_FAILED';
        throw Error('Model request failed');
      }
    } };
    const model = { reply(input) {
      const request = underlyingModel.reply(input);
      pendingModelRequests.push(request);
      return request;
    } };
    const clock = new Date('2026-10-15T04:00:00.000Z');
    const profile = { name: 'SYNTHETIC_ACCEPTANCE', age: 40, conditions: [], medications: [],
      mobility: 'unknown', usesCane: false, nightVision: 'unknown', cognition: 'unknown', familySharing: 'denied' };
    try {
      await runtime.openSession({ sessionId: owner, participantId: owner, profile, now: clock,
        semanticRoutingEnabled: true, conversationModel: model, rehabReads: reads,
        rehabAssistant: (text, privateTurn) => rehabAnswer(text, privateTurn, owner, model, reads) });
      for (const text of scenario.turns) {
        const start = item.call_chain.length;
        log({ type: 'user_input', text, origin: 'SYNTHETIC' });
        const result = await runtime.processTurn(owner, { text, now: clock, conversationContext: 'SYNTHETIC:TEST' });
        const turn = { text, source_message_id: result.sourceMessageId, semantic: result.semantic || null,
          semantic_execution: result.semanticExecution || null, reply: result.reply.text,
          conversation: result.reply.conversation || null, safety_action: result.reply.safetyAction,
          health_events: result.snapshot.events.length, family_events: result.snapshot.familyEvents.length,
          revision: result.revision };
        item.turns.push(turn);
        log({ type: 'runtime_trace', trace: result.semanticExecution || null });
        log({ type: 'user_reply', text: result.reply.text, conversation: result.reply.conversation || null });
        check('read_only_state_turn_' + item.turns.length, result.snapshot.events.length === 0 && result.snapshot.familyEvents.length === 0);
        check('no_internal_fields_in_reply_turn_' + item.turns.length, !/suggested_tool|tool_requests|source_message_id|exercise_id|participant_id/.test(result.reply.text));
        const modelCalls = item.call_chain.slice(start).filter(event => event.type === 'model_request');
        if (scenario.private) check('private_turn_zero_model_calls', modelCalls.length === 0);
        else if (!scenario.faultInjection) check('validated_llm_understanding_turn_' + item.turns.length,
          result.semanticExecution?.parser_status === 'llm_valid' && modelCalls[0]?.purpose === 'understanding');
        else if (!scenario.rejectedAnswer) check('invalid_model_falls_back', result.semanticExecution?.parser_status === 'local_fallback');
        if (scenario.expectMentionCount) check('all_symptoms_preserved', result.semantic?.mentions.length >= scenario.expectMentionCount);
        if (scenario.expectStatus) check('expression_status_preserved', result.semantic?.mentions.some(mention => mention.status === scenario.expectStatus));
        if (scenario.expectIntentCount) check('multiple_intents_preserved', result.semantic?.intents?.length >= scenario.expectIntentCount);
        if (scenario.safety) check('existing_safety_preserved', result.reply.safetyAction === true && modelCalls.filter(call => call.purpose !== 'understanding').length === 0);
      }
      const toolCalls = item.call_chain.filter(event => event.type === 'tool_request');
      const modelCalls = item.call_chain.filter(event => event.type === 'model_request');
      item.model_calls = modelCalls.length;
      item.personal_tool_calls = toolCalls.length;
      check('record_results_never_sent_to_model', !JSON.stringify(modelCalls.map(event => event.request)).includes('SYNTHETIC_PRIVATE_RECORD_SENTINEL'));
      if (scenario.expectReads) {
        check('expected_host_tools_once', JSON.stringify(toolCalls.map(call => call.name)) === JSON.stringify(scenario.expectReads));
        check('personal_results_use_local_reply', item.turns.every(turn => turn.conversation?.provider === 'local'));
        check('no_final_model_for_personal_records', modelCalls.every(call => call.purpose === 'understanding'));
      } else check('no_unrequested_personal_reads', toolCalls.length === 0);
      if (scenario.expectReplyModel) {
        check('final_model_was_called', modelCalls.some(call => call.purpose === 'reply' && call.status === 'RETURNED'));
        check('final_model_reply_accepted', item.turns.some(turn => turn.conversation?.provider === 'deepseek' &&
          turn.conversation?.status === 'replied' && turn.semantic_execution?.stages.some(stage => stage.stage === 'reply' && stage.status === 'passed')));
      }
      if (scenario.expectKnowledge) {
        check('real_public_knowledge_in_final_request', modelCalls.some(call => call.purpose === 'reply' && JSON.stringify(call.request).includes(scenario.expectKnowledge)));
        check('knowledge_tool_ran', item.turns.some(turn => turn.semantic_execution?.stages.some(stage => stage.tool === 'rehab.search_knowledge' && stage.status === 'passed')));
      }
      if (scenario.expectContext) {
        check('correction_source_id_valid', item.turns[1]?.semantic?.correction_of?.source_message_id === item.turns[0]?.source_message_id);
        check('followup_source_id_valid', item.turns[2]?.semantic?.mentions.some(mention => mention.source_message_id === item.turns[1]?.source_message_id));
      }
      if (scenario.hostMode === 'wrong_owner' || scenario.hostMode === 'failed') check('failed_record_not_displayed',
        item.turns.every(turn => !turn.reply.includes('SYNTHETIC_PRIVATE_RECORD_SENTINEL')));
      if (scenario.rejectedAnswer) check('invented_execution_rejected', item.turns.every(turn => !turn.reply.includes('改好了') && turn.conversation?.provider === 'local'));
      item.status = item.assertions.every(assertion => assertion.status === 'PASS') ? 'PASS' : 'FAIL';
    } catch {
      item.assertions.push({ name: 'runtime_completed', status: 'FAIL', detail: 'RUNTIME_ERROR; raw diagnostics omitted.' });
      item.status = 'FAIL';
    } finally {
      await runtime.closeSession(owner).catch(() => {});
      // Runtime's bounded understanding can stop waiting before the adapter's
      // own deadline. Preserve its eventual failure/response in evidence rather
      // than leaving a completed scenario with a falsely successful pending call.
      await Promise.allSettled(pendingModelRequests);
    }
    console.log(JSON.stringify({ case: item.id, status: item.status, model_calls: item.model_calls ?? item.call_chain.filter(event => event.type === 'model_request').length }));
    // Save after every scenario so an interrupted real run retains honest partial evidence.
    write(report);
  }
  report.totals = { scenarios: report.cases.length,
    pass: report.cases.filter(item => item.status === 'PASS').length,
    fail: report.cases.filter(item => item.status === 'FAIL').length, unverified: 0,
    model_calls: report.cases.reduce((total, item) => total + (item.model_calls || 0), 0) };
  report.status = report.totals.fail ? 'FAIL' : 'PASS';
  report.real_llm_acceptance = real ? report.status : 'UNVERIFIED';
  report.production_personal_database_acceptance = 'UNVERIFIED';
  write(report);
  console.log(JSON.stringify({ status: report.status, totals: report.totals, real_llm_acceptance: report.real_llm_acceptance }));
  if (report.totals.fail) process.exitCode = 1;
}
main().catch(() => {
  report.status = 'FAIL'; report.reason = 'Acceptance harness failed; raw diagnostics omitted.';
  write(report); console.error('FAIL: acceptance harness failed.'); process.exitCode = 1;
});
