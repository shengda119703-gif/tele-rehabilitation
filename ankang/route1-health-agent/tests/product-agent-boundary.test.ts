import test from 'node:test';
import assert from 'node:assert/strict';
import {AgentRuntime} from '../src/runtime/session';
import {canUseModuleTools} from '../src/runtime/operationalIntent';
const now=new Date('2026-10-11T09:00:00+08:00');
const profile={name:'TEST',age:65,conditions:[],medications:[],familyContact:'',familyPhone:'',mobility:'unknown',usesCane:false,nightVision:'unknown',cognition:'unknown',familySharing:'denied'} as const;
test('documented local queries and navigation remain available with the complete grammar',()=>{
  for(const text of ['查看健康记录和药物清单','查看资料','查看家庭状态','查看通知记录','查看设备状态','今天有什么安排？','康复下一步是什么','我今天练什么？','打开健身页','打开记录页','打开设置页','打开通知页','我想了解保存的文档','你能做什么？','查看我的健康记录','查看最新的康复计划'])assert.equal(canUseModuleTools(text),true,text);
  assert.equal(canUseModuleTools('有哪些'.repeat(500)+'王五'),false);
});
test('module tools never intercept privacy, symptoms, corrections or sharing',async()=>{
  for(const text of ['不要记录：查看资料','我今天胸痛','我今天血压是150/90','撤回上一条记录','告诉家人我今天头晕',
    '不要查看健康记录','我不查看健康记录','我没让你查看健康记录','今天张三健康记录有哪些','假如查看资料','王五的健康记录有哪些','帮忙查一下她的数据']){
    const runtime=new AgentRuntime();let calls=0;
    await runtime.openSession({sessionId:'TEST',profile:{...profile,conditions:[],medications:[]},now,productTools:{replyToText:async()=>{calls++;return{reply:'TEST tools',steps:[]};}}});
    const turn=await runtime.processTurn('TEST',{text,now});assert.equal(calls,0,text);assert.equal((turn as any).agent,undefined,text);
  }
});

test('legacy rehab model fallback has the same operational input boundary',async()=>{
  let selections=0;const runtime=new AgentRuntime();
  await runtime.openSession({sessionId:'TEST',profile:{...profile,conditions:[],medications:[]},now,rehabTools:{
    select:async()=>{selections++;return null;},read:async()=>{throw Error('TEST forbidden');},describe:async()=>''}});
  for(const text of ['不要查看训练计划','我不查看训练计划','假设查看评估结果','王五的训练记录有哪些','撤回上一条记录'])await runtime.processTurn('TEST',{text,now});
  assert.equal(selections,0);
});
test('module tool result persists in ordinary chat without inventing a health event',async()=>{
  const runtime=new AgentRuntime();
  await runtime.openSession({sessionId:'TEST',profile:{...profile,conditions:[],medications:[]},now,productTools:{replyToText:async()=>({reply:'TEST actual module facts',steps:[{name:'archive_list',status:'succeeded',reply:'TEST actual module facts'}]})}});
  const turn=await runtime.processTurn('TEST',{text:'查看资料',now});
  assert.equal(turn.reply.text,'TEST actual module facts');assert.equal(turn.snapshot.events.length,0);assert.equal(turn.agent?.steps[0].status,'succeeded');
});
