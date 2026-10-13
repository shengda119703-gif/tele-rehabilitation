const {test}=require('node:test');
const assert=require('node:assert/strict');
const {ProductService}=require('../.bridge-build/product/ProductService.js');
const {localPlan,rehabAnswer,searchCards}=require('../.bridge-build/rehab/assistant.js');
const {catalogue}=require('../.bridge-build/rehab/catalogue.js');
function port(){const values=new Map();return {read:k=>structuredClone(values.get(k)??null),write:(k,v)=>values.set(k,structuredClone(v)),remove:k=>values.delete(k),profiles:()=>[...values].filter(([k])=>k.startsWith('profile:')).map(([,v])=>v),attachments:{list:async()=>[],clear:async()=>{}}};}
const profile={name:'TEST',age:40,conditions:[],medications:[],mobility:'unknown',usesCane:false,nightVision:'unknown',cognition:'unknown',familySharing:'denied'};
test('chat never changes health, consent or care even when text asks to record/confirm',async()=>{
 let hostWrites=0,modelCalls=0;const service=new ProductService(port(),undefined,undefined,{},()=>({read:async()=>{},execute:async()=>{hostWrites++;}}),undefined,undefined,()=>({reply:async()=>{modelCalls++;return 'TEST';}}));
 const owner='TEST',now=new Date('2026-10-13T09:00:00Z');const call=(op,input={})=>service.request(op,owner,input,now);
 await call('profile.save',{profile});await call('health.record',{metric:'weight',value:63});const before=await call('snapshot');
 for(const text of ['记录血压180','我今天血压180','我吃药了','把训练改到八点','分享给家属','确认执行','撤回上一条记录'])await call('chat',{text});
 const after=await call('snapshot');assert.deepEqual(after.state.events,before.state.events);assert.deepEqual(after.state.familyEvents,before.state.familyEvents);
 assert.equal(after.careAvailable,false);assert.deepEqual(after.agentTools,[]);assert.deepEqual(after.carePending,[]);assert.equal(hostWrites,0);assert.equal(modelCalls,0);
 await assert.rejects(call('care.confirm',{confirmed:true}),/下架/);
});
test('full library and short names are searchable; grounded Q&A uses one model call and private turns use none',async()=>{
 assert.equal(catalogue.length,185);assert.equal(catalogue.filter(c=>c.complete).length,185);
 assert.equal(catalogue.filter(c=>c.kind==='assessment').length,63);assert.equal(catalogue.filter(c=>c.kind==='training').length,122);
 assert.equal(new Set(catalogue.map(c=>c.id)).size,185);assert.equal(searchCards('e-low-010 怎么做')[0].id,'E-LOW-010');
 assert.ok(searchCards('我想了解肩外旋怎么做').some(c=>c.id==='T-AXU-023'));
 assert.ok(searchCards('肩外旋有哪些注意事项').some(c=>c.id==='T-AXU-023'));
 for(const c of catalogue){assert.ok(c.startConditions&&c.stopConditions&&c.sourceDose&&c.equipment);assert.doesNotMatch(c.content,/^## /m);}
 let calls=0;const model={reply:async({messages})=>{calls++;assert.match(messages[0].content,/E-LOW-009/);return '按资料小幅移动，出现不适停止。';}};
 const result=await rehabAnswer('E-LOW-009 怎么做',false,'TEST',model);assert.match(result.text,/E-LOW-009/);assert.equal(calls,1);
 await rehabAnswer('E-LOW-009 怎么做',true,'TEST',model);assert.equal(calls,1);
 const fallback=await rehabAnswer('E-LOW-009 怎么做',false,'TEST',{reply:async()=>{throw Error('TEST offline');}});assert.match(fallback.text,/依据动作库/);
});
test('local plan retains exact source ranges and conditions, never adopts or interprets medical restrictions',()=>{
 const input={goal:'TEST goal',region:'踝',equipment:['稳固椅'],restrictions:[],level:0,screeningConfirmed:true};
 const c=catalogue.find(c=>c.id==='T-LOW-046');
 const a=localPlan(input);assert.equal(a.status,'draft');assert.equal(a.adopted,false);assert.equal(a.reviewRequired,true);assert.equal(a.items.length,1);
 assert.equal(a.items[0].sourceDose,c.sourceDose);assert.equal(a.items[0].startConditions,c.startConditions);assert.equal(a.items[0].stopConditions,c.stopConditions);
 assert.match(a.items[0].sourceDose,/首轮每个允许方向3次/);assert.match(a.items[0].sourceDose,/1—3组×5—10次/);assert.equal(a.items[0].dose,undefined);
 assert.deepEqual(localPlan(input),a);assert.equal(localPlan({...input,equipment:[]}).status,'no_match');
 assert.equal(localPlan({...input,restrictions:['禁止踝活动']}).status,'needs_review');
 assert.equal(localPlan(input,[{...c,complete:false}]).items.length,0);
 assert.equal(localPlan({...input,level:3}).items[0].sourceDose,a.items[0].sourceDose);
 assert.equal(localPlan({...input,region:'髋',equipment:['硬床']}).items.length,0);
 assert.ok(localPlan({...input,region:'髋',equipment:['硬床','滑布']}).items.some(c=>c.id==='T-LOW-002'));
 assert.equal(localPlan({...input,region:'肩',equipment:['稳定桌面']}).items[0].id,'T-AXU-022');
 assert.throws(()=>localPlan({...input,screeningConfirmed:false}));
});

test('general explanations use source sections; existing plans use owner-scoped local records',async()=>{
 assert.match((await rehabAnswer('L0和L2等级是什么意思',true,'TEST')).text,/不是临床肌力分级/);
 let calls=0;const result=await rehabAnswer('我的训练计划',false,'TEST',{reply:async()=>{throw Error('Personal records must stay local');}},
 {read:async({name})=>{calls++;return {tool:name,read_only:true,status:'found',scope:{participant_id:'TEST',source_kind:'TEST',usage_context:'TEST'},records:[{id:'TEST record'}]};}});
 assert.equal(calls,1);assert.match(result.text,/TEST record/);
 const missing=await rehabAnswer('不存在的动作编号T-FAKE-001',false,'TEST',{reply:async()=>{throw Error('Must not call');}});
 assert.match(missing.text,/没有对应资料/);
});
