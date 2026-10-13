import test from 'node:test';
import assert from 'node:assert/strict';
import {AgentRuntime, InMemoryPersistence, SessionInvalidatedError} from '../src/runtime';
import {conversationMessages, isOperationalConversation, type ConversationModel} from '../src/runtime/conversation';
import type {ChatMessage, ElderProfile} from '../src/types';

const profile:ElderProfile={name:'SYNTHETIC/TEST',age:72,conditions:[],medications:[],
  familyContact:'TEST',familyPhone:'',mobility:'independent',usesCane:false,
  nightVision:'normal',cognition:'stable',familySharing:'denied'};
const now=()=>new Date(2026,9,11,19,0,0);
type Messages=Parameters<ConversationModel['reply']>[0]['messages'];
function recordingModel(reply='TEST_MODEL_REPLY') {
  const calls:Messages[]=[];
  const model:ConversationModel={async reply(input){calls.push(structuredClone(input.messages));return reply;}};
  return {calls,model};
}
async function open(options:Partial<Parameters<AgentRuntime['openSession']>[0]>={}) {
  const runtime=new AgentRuntime();
  await runtime.openSession({sessionId:'TEST_A',profile,now:now(),...options});
  return runtime;
}
function deferred<T>() {
  let resolve!:(value:T)=>void;
  const promise=new Promise<T>(r=>{resolve=r;});
  return {promise,resolve};
}

test('conversation runtime: the exact screenshot prompts reach DeepSeek without adding health facts or tools',async()=>{
  const {model,calls}=recordingModel('我是 AI，可以陪你聊聊。');
  let toolCalls=0;
  const runtime=await open({conversationModel:model,
    productTools:{async replyToText(){toolCalls++;return null;}},
    careTools:{async replyToText(){return null;}}});
  const baseline=runtime.readSnapshot('TEST_A');
  for(const text of ['你可以做我对象吗','你喜欢我吗']) {
    const turn=await runtime.processTurn('TEST_A',{text,now:now(),conversationContext:'SYNTHETIC:TEST'});
    assert.equal(turn.reply.text,'我是 AI，可以陪你聊聊。');
    assert.deepEqual(turn.reply.conversation,{provider:'deepseek',status:'replied'});
    assert.equal(turn.reply.conversationContext,'SYNTHETIC:TEST');
    assert.deepEqual(turn.snapshot.events,baseline.events);
    assert.deepEqual(turn.snapshot.familyEvents,baseline.familyEvents);
    assert.deepEqual(turn.tasks,baseline.tasks);
    assert.deepEqual(turn.appliedChanges.eventsToAppend,[]);
    assert.deepEqual(turn.appliedChanges.familyEventsToAppend,[]);
    assert.deepEqual(turn.appliedChanges.sharingAuditEntries,[]);
    assert.equal(turn.delivery.status,'not-requested');
    assert.equal(turn.agent,undefined);
    assert.equal(turn.care,undefined);
    assert.equal(turn.rehab,undefined);
  }
  assert.equal(calls.length,2);
  assert.equal(calls[0].at(-1)?.content,'你可以做我对象吗');
  assert.equal(calls[1].at(-1)?.content,'你喜欢我吗');
  assert.equal(toolCalls,0);
});

test('conversation runtime: ordinary followups include only successful ordinary pairs, excluding private, no-record, legacy and tool replies',async()=>{
  const {model,calls}=recordingModel();
  const legacy:ChatMessage[]=[{id:'TEST_A:0:elder:1',role:'elder',text:'LEGACY_PRIVATE_RECORD',time:'10-05 10:00'},
    {id:'TEST_A:0:agent:1',role:'agent',text:'LEGACY_RECORD_REPLY',time:'10-05 10:00'}];
  const runtime=await open({conversationModel:model,initialHealth:{events:[],familyEvents:[],chat:legacy},
    productTools:{async replyToText(){return {reply:'TOOL_HEALTH_SECRET',steps:[]};}}});
  await runtime.processTurn('TEST_A',{text:'我喜欢看海',now:now(),conversationContext:'TEST_SOURCE'});
  await runtime.processTurn('TEST_A',{text:'我喜欢红色，不要告诉家人',now:now(),conversationContext:'TEST_SOURCE'});
  await runtime.processTurn('TEST_A',{text:'我喜欢蓝色，这段不要记录',now:now(),conversationContext:'TEST_SOURCE'});
  await runtime.processTurn('TEST_A',{text:'查看健康记录',now:now(),conversationContext:'TEST_SOURCE'});
  const turn=await runtime.processTurn('TEST_A',{text:'接着聊旅行吧',now:now(),conversationContext:'TEST_SOURCE'});
  assert.equal(calls.length,2);
  assert.deepEqual(calls[1],[{role:'user',content:'我喜欢看海'},
    {role:'assistant',content:'TEST_MODEL_REPLY'},{role:'user',content:'接着聊旅行吧'}]);
  assert.doesNotMatch(JSON.stringify(calls),/LEGACY_|TOOL_HEALTH_SECRET|红色|蓝色/);
  assert.deepEqual(turn.snapshot.events,[]);
});

test('conversation runtime: successful model pairs survive reopen, while unavailable/failed pairs never become external context',async()=>{
  const memory=new InMemoryPersistence();
  const {model,calls}=recordingModel();
  const runtime=await open({persistence:memory,conversationModel:model});
  await runtime.processTurn('TEST_A',{text:'我喜欢秋天',now:now(),conversationContext:'SYNTHETIC:TEST'});
  await runtime.closeSession('TEST_A');
  await runtime.openSession({sessionId:'TEST_A',profile,now:now(),persistence:memory,
    conversationModel:{async reply(){throw Error('SECRET_INTERNAL_FAILURE');}}});
  const failure=await runtime.processTurn('TEST_A',{text:'FAILURE_INPUT',now:now(),conversationContext:'SYNTHETIC:TEST'});
  assert.deepEqual(failure.reply.conversation,{provider:'local',status:'failed',reason:'network'});
  assert.doesNotMatch(JSON.stringify(failure),/SECRET_INTERNAL_FAILURE/);
  await runtime.closeSession('TEST_A');
  await runtime.openSession({sessionId:'TEST_A',profile,now:now(),persistence:memory});
  const local=await runtime.processTurn('TEST_A',{text:'LOCAL_INPUT',now:now(),conversationContext:'SYNTHETIC:TEST'});
  assert.deepEqual(local.reply.conversation,{provider:'local',status:'unavailable',reason:'not_configured'});
  await runtime.closeSession('TEST_A');
  await runtime.openSession({sessionId:'TEST_A',profile,now:now(),persistence:memory,conversationModel:model});
  await runtime.processTurn('TEST_A',{text:'接着说秋天',now:now(),conversationContext:'SYNTHETIC:TEST'});
  assert.deepEqual(calls.at(-1),[{role:'user',content:'我喜欢秋天'},
    {role:'assistant',content:'TEST_MODEL_REPLY'},{role:'user',content:'接着说秋天'}]);
});

test('conversation runtime: privacy, clinical, family-health, recall, correction and sharing keep their original routes',async()=>{
  for(const text of ['我喜欢海边，不要告诉家人','我喜欢海边，这段不要记录',
    '我今天早上在厕所摔了一跤','我今天血压150/95','如果头晕怎么办',
    '我爸今天血压150/95','把我今天头晕告诉女儿','之前告诉女儿什么','刚才说了什么',
    '说错了，不是我本人']) {
    const {model,calls}=recordingModel('MUST_NOT_APPEAR');
    const runtime=await open({conversationModel:model});
    const turn=await runtime.processTurn('TEST_A',{text,now:now()});
    assert.equal(calls.length,0,text);
    assert.equal(turn.reply.conversation,undefined,text);
    assert.doesNotMatch(turn.reply.text,/MUST_NOT_APPEAR/,text);
    if(/不要记录/.test(text))assert.equal(turn.reply.persisted,false);
    await runtime.closeSession('TEST_A');
  }
});

test('conversation runtime: unknown-owner, negated, hypothetical and unsupported operations never become model execution claims',async()=>{
  const {model,calls}=recordingModel('已经完成所有操作');
  let reads=0;
  const runtime=await open({conversationModel:model,
    productTools:{async replyToText(){reads++;return null;}}});
  for(const text of ['查看张三健康记录','不打开康复页','如果打开健康页',
    '导出健康数据','删除附件','启动相机','开始训练','分享健康报告给家属',
    '帮我把药删掉','把张三的资料清空','开启摄像头','帮我停止录像','打开网页','我的药物有哪些']) {
    const turn=await runtime.processTurn('TEST_A',{text,now:now()});
    assert.equal(turn.reply.conversation,undefined,text);
    assert.doesNotMatch(turn.reply.text,/已经完成所有操作/,text);
    assert.deepEqual(turn.appliedChanges.eventsToAppend,[],text);
    assert.deepEqual(turn.appliedChanges.familyEventsToAppend,[],text);
    assert.equal(turn.agent,undefined,text);
    assert.equal(turn.rehab,undefined,text);
  }
  assert.equal(calls.length,0);
  assert.equal(reads,1); // Last self query can reach the trusted module registry, which declined it.
});

test('conversation runtime: registered care and module results take priority and are excluded from ordinary context',async()=>{
  const {model,calls}=recordingModel();
  const runtime=await open({conversationModel:model,
    careTools:{async replyToText(text){return text==='核对这项安排'?{reply:'CARE_RECEIPT_SECRET'}:null;}},
    productTools:{async replyToText(){return {reply:'MODULE_RECORD_SECRET',steps:[]};}}});
  const care=await runtime.processTurn('TEST_A',{text:'核对这项安排',now:now()});
  assert.equal(care.reply.text,'CARE_RECEIPT_SECRET');
  const module=await runtime.processTurn('TEST_A',{text:'查看健康记录',now:now()});
  assert.equal(module.reply.text,'MODULE_RECORD_SECRET');
  await runtime.processTurn('TEST_A',{text:'聊聊大海吧',now:now()});
  assert.equal(calls.length,1);
  assert.deepEqual(calls[0],[{role:'user',content:'聊聊大海吧'}]);
});

test('conversation runtime: owner and trusted source/context partitions cannot exchange conversation pairs',async()=>{
  const {model,calls}=recordingModel();
  const runtime=await open({conversationModel:model});
  await runtime.openSession({sessionId:'TEST_B',profile:{...profile,name:'SYNTHETIC/TEST_B'},now:now(),conversationModel:model});
  await runtime.processTurn('TEST_A',{text:'A_ONLY_SECRET',now:now(),conversationContext:'LIVE_CAMERA:SELF_USE'});
  await runtime.processTurn('TEST_B',{text:'B_ONLY_INPUT',now:now(),conversationContext:'LIVE_CAMERA:SELF_USE'});
  assert.deepEqual(calls[1],[{role:'user',content:'B_ONLY_INPUT'}]);
  await runtime.processTurn('TEST_A',{text:'REPLAY_ONLY_INPUT',now:now(),conversationContext:'REPLAY_FILE:SELF_USE'});
  assert.deepEqual(calls[2],[{role:'user',content:'REPLAY_ONLY_INPUT'}]);
  await runtime.processTurn('TEST_A',{text:'REPLAY_FOLLOWUP',now:now(),conversationContext:'REPLAY_FILE:SELF_USE'});
  assert.deepEqual(calls[3],[{role:'user',content:'REPLAY_ONLY_INPUT'},
    {role:'assistant',content:'TEST_MODEL_REPLY'},{role:'user',content:'REPLAY_FOLLOWUP'}]);
  await runtime.processTurn('TEST_A',{text:'TEST_ONLY_INPUT',now:now(),conversationContext:'REPLAY_FILE:TEST'});
  assert.deepEqual(calls[4],[{role:'user',content:'TEST_ONLY_INPUT'}]);
});

test('conversation runtime: external context is bounded to recent ordinary pairs, with caller text preserved',()=>{
  const chat:ChatMessage[]=[];
  for(let i=0;i<20;i++) {
    const common={time:'10-11 19:00',persisted:true,conversationContext:'TEST',
      conversation:{provider:'deepseek' as const,status:'replied' as const}};
    chat.push({...common,id:`TEST_A:0:elder:${i}`,role:'elder',text:`TEST_USER_${i}`},
      {...common,id:`TEST_A:0:agent:${i}`,role:'agent',text:`TEST_REPLY_${i}`});
  }
  const messages=conversationMessages(chat,'CURRENT_INPUT','TEST_A','TEST');
  assert.equal(messages.length,13);
  assert.equal(messages[0].content,'TEST_USER_14');
  assert.equal(messages.at(-1)?.content,'CURRENT_INPUT');
  const long=chat.map(m=>({...m,text:m.text+'x'.repeat(2000)}));
  const bounded=conversationMessages(long,'CURRENT_INPUT','TEST_A','TEST');
  assert.ok(bounded.reduce((sum,m)=>sum+m.content.length,0)<=10000);
  assert.equal(bounded.at(-1)?.content,'CURRENT_INPUT');
});

test('conversation runtime: common ordinary negation and non-health family dialogue are not blanket-rejected',async()=>{
  const {model,calls}=recordingModel();
  const runtime=await open({conversationModel:model});
  for(const text of ['你不喜欢我吗','我不想出门','我妈妈喜欢园艺','我想听你讲个故事']) {
    assert.equal(isOperationalConversation(text),false,text);
    const turn=await runtime.processTurn('TEST_A',{text,now:now()});
    assert.equal(turn.reply.conversation?.provider,'deepseek',text);
    assert.deepEqual(turn.appliedChanges.eventsToAppend,[],text);
    assert.deepEqual(turn.appliedChanges.familyEventsToAppend,[],text);
  }
  assert.equal(calls.length,4);
});

test('conversation runtime: empty, overlong and rejected model replies fail safely with no raw diagnostics',async()=>{
  for(const result of ['', 'x'.repeat(6001), Error('SECRET_KEY_AND_PROVIDER_DETAIL')]) {
    const model:ConversationModel={async reply(){if(result instanceof Error)throw result;return result;}};
    const runtime=await open({conversationModel:model});
    const turn=await runtime.processTurn('TEST_A',{text:'你好呀',now:now()});
    assert.deepEqual(turn.reply.conversation,{provider:'local',status:'failed',reason:'network'});
    assert.match(turn.reply.text,/DeepSeek 这次没有正常返回/);
    assert.doesNotMatch(JSON.stringify(turn),/SECRET_KEY_AND_PROVIDER_DETAIL/);
    assert.deepEqual(turn.appliedChanges.eventsToAppend,[]);
    assert.deepEqual(turn.appliedChanges.familyEventsToAppend,[]);
  }
});

test('conversation runtime: closing during model generation discards late text and allows a clean reopen',async()=>{
  const started=deferred<void>(),release=deferred<string>();
  const runtime=await open({conversationModel:{async reply(){started.resolve();return release.promise;}}});
  const pending=runtime.processTurn('TEST_A',{text:'聊聊旅行吧',now:now()});
  await started.promise;
  const rejection=assert.rejects(pending,SessionInvalidatedError);
  const closing=runtime.closeSession('TEST_A');
  release.resolve('LATE_MODEL_REPLY');
  await rejection;
  await closing;
  await runtime.openSession({sessionId:'TEST_A',profile,now:now()});
  assert.deepEqual(runtime.readSnapshot('TEST_A').chat,[]);
});

test('conversation runtime: reset invalidates an in-flight model reply before any chat or health commit',async()=>{
  const started=deferred<void>(),release=deferred<string>();
  const memory=new InMemoryPersistence();
  const runtime=await open({persistence:memory,conversationModel:{async reply(){started.resolve();return release.promise;}}});
  const pending=runtime.processTurn('TEST_A',{text:'聊聊旅行吧',now:now()});
  await started.promise;
  const rejection=assert.rejects(pending,SessionInvalidatedError);
  const resetting=runtime.resetSession('TEST_A',now());
  release.resolve('LATE_MODEL_REPLY');
  await rejection;
  const reset=await resetting;
  assert.deepEqual(reset.chat,[]);
  assert.deepEqual(reset.events,[]);
  assert.equal(await memory.load('TEST_A'),null);
});
