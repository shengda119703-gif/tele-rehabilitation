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
test('partial card is never retrievable; grounded Q&A uses one model call and private turns use none',async()=>{
 assert.equal(catalogue.length,24);assert.equal(catalogue.filter(c=>c.complete).length,23);assert.equal(searchCards('E-LOW-010 怎么做').length,0);
 let calls=0;const model={reply:async({messages})=>{calls++;assert.match(messages[0].content,/E-LOW-009/);return '按资料小幅移动，出现不适停止。';}};
 const result=await rehabAnswer('E-LOW-009 怎么做',false,'TEST',model);assert.match(result.text,/E-LOW-009/);assert.equal(calls,1);
 await rehabAnswer('E-LOW-009 怎么做',true,'TEST',model);assert.equal(calls,1);
 const fallback=await rehabAnswer('E-LOW-009 怎么做',false,'TEST',{reply:async()=>{throw Error('TEST offline');}});assert.match(fallback.text,/依据动作库/);
});
test('local plan filters structured training cards, never adopts, and refuses incomplete library',()=>{
 const input={goal:'TEST goal',region:'TEST region',equipment:['TEST chair'],restrictions:[],level:1,screeningConfirmed:true};
 assert.equal(localPlan(input).status,'needs_library');
 const c={id:'T-TEST-001',name:'TEST ONLY',kind:'training',complete:true,dose:{reps:2,sets:1,restSeconds:30},eligibility:{regions:['TEST region'],equipment:['TEST chair'],restrictions:['TEST blocked'],level:1}};
 const a=localPlan(input,[c]);assert.equal(a.status,'draft');assert.equal(a.adopted,false);assert.equal(a.items.length,1);
 assert.deepEqual(localPlan(input,[c]),a);assert.equal(localPlan({...input,equipment:[]},[c]).items.length,0);
 assert.equal(localPlan({...input,restrictions:['TEST blocked']},[c]).items.length,0);
 assert.equal(localPlan(input,[{...c,complete:false}]).items.length,0);
 assert.throws(()=>localPlan({...input,screeningConfirmed:false}));
});
