'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(__dirname+'/browser-account.js','utf8');
const patient='11111111-1111-4111-8111-111111111111',account='22222222-2222-4222-8222-222222222222';
function fixture(){
 const memory=new Map(),listeners={},calls=[],redirects=[];
 const identity={patient_id:patient,account_id:account,username:'alice',role:'PATIENT'};
 const storage={getItem:k=>memory.get(k)||null,setItem:(k,v)=>memory.set(k,v)};
 let current={...identity,csrf_token:'memory-only'},onFetch=()=>{};
 class Store{constructor(s,k){this.value=JSON.parse(s.getItem(k)||JSON.stringify({owner:patient}));this.change=fn=>{fn(this.value);s.setItem(k,JSON.stringify(this.value));};}}
 const context={PhoneStore:{CLOUD_PREFIX:'cloud:',ACTIVE_KEY:'active',Store,cloudKey:k=>k==='cloud:'+patient},localStorage:storage,
  document:{getElementById:()=>({textContent:JSON.stringify(identity)})},location:{origin:'https://139.224.216.18',replace:u=>redirects.push(u),assign:u=>redirects.push(u)},
  fetch:async(url,options)=>{calls.push({url,options});await onFetch(url,options);return{ok:true,status:200,json:async()=>url.endsWith('/auth/me')?structuredClone(current):{items:[],status:'COMMITTED'}};},
  addEventListener:(name,fn)=>listeners[name]=fn,structuredClone,AbortSignal,URLSearchParams,alert:()=>{}};
 vm.runInNewContext(source,context);
 return {context,memory,calls,listeners,redirects,identity,setCurrent:v=>current=v,onFetch:fn=>onFetch=fn};
}
test('browser identity is per-patient and credentials never persist in local storage',async()=>{
 const f=fixture();await f.context.AnkangBrowserAccount.ready;
 const state=[...f.memory.values()].join('');assert(state.includes(patient));assert(!state.includes('memory-only'));assert(!state.includes('access_token'));
 await f.context.AnkangBrowserAccount.request('append',f.identity,{document:{operation_id:'one'}});
 const call=f.calls.at(-1);assert(call.url.includes('/patients/'+patient+'/record-events'));assert.equal(call.options.credentials,'same-origin');
 assert.equal(call.options.headers['X-CSRF-Token'],'memory-only');assert(!call.options.headers.Authorization);
});
test('wrong patient and same-browser account switch refuse cloud writes',async()=>{
 const f=fixture();await f.context.AnkangBrowserAccount.ready;
 await assert.rejects(f.context.AnkangBrowserAccount.request('append',{...f.identity,patient_id:account},{}));
 f.setCurrent({...f.identity,patient_id:account,csrf_token:'new'});
 await assert.rejects(f.context.AnkangBrowserAccount.request('append',f.identity,{}));
 assert(!f.calls.some(c=>c.url.endsWith('/record-events')));assert.equal(f.redirects[0],'/account?next=/');
});
test('other tab selecting another account invalidates this tab immediately',async()=>{
 const f=fixture();await f.context.AnkangBrowserAccount.ready;
 f.listeners.storage({key:'active',newValue:'cloud:'+account});
 assert.throws(()=>f.context.AnkangBrowserAccount.assertScope());assert.equal(f.redirects[0],'/account?next=/');
});
test('workbench requests remain bound to current patient and require CSRF for writes',async()=>{
 const f=fixture();await f.context.AnkangBrowserAccount.ready;const api=f.context.AnkangBrowserAccount;
 await api.request('messages',f.identity,{latest:true,limit:50});assert(f.calls.at(-1).url.includes('/patients/'+patient+'/messages?latest=true&after=0&limit=50'));
 await api.request('messages',f.identity,{before:0});assert(!f.calls.at(-1).url.includes('before='));assert(f.calls.at(-1).url.includes('latest=true'));
 await api.request('read',f.identity,{operation_id:'read-one',cursor:7});const read=f.calls.at(-1);assert.equal(read.options.method,'POST');assert.equal(JSON.parse(read.options.body).cursor,7);assert.equal(read.options.headers['X-CSRF-Token'],'memory-only');
 await api.request('send',f.identity,{operation_id:'send-one',text:'待发送原文'});assert.equal(JSON.parse(f.calls.at(-1).options.body).text,'待发送原文');
 await api.request('plans',f.identity);assert(f.calls.at(-1).url.endsWith('/plans?offset=0&limit=5'));
 await api.request('plans',f.identity,{offset:5});assert(f.calls.at(-1).url.endsWith('/plans?offset=5&limit=5'));
 await assert.rejects(api.request('plans',f.identity,{offset:-1}));
 await api.request('current',f.identity);assert(f.calls.at(-1).url.endsWith('/plans/current'));
 await api.request('accept',f.identity,{plan_id:account,operation_id:'accept-one',expected_version:2,expected_current_revision:0,local_validation:{validation_policy:'existing-local-assessment-1'}});
 const accept=f.calls.at(-1);assert(accept.url.endsWith('/plans/'+account+'/accept'));assert(!Object.hasOwn(JSON.parse(accept.options.body),'plan_id'));assert.equal(JSON.parse(accept.options.body).local_validation.validation_policy,'existing-local-assessment-1');
 await assert.rejects(api.request('messages',f.identity,{before:'../../other'}));await assert.rejects(api.request('accept',f.identity,{plan_id:'../../other'}));
 assert(![...f.memory.values()].join('').includes('待发送原文'),'Transport does not cache private conversation; patient outbox owns persistence');
});

test('assistant transport preserves original text, explicit preferences and bounded conversation cursors',async()=>{
 const f=fixture();await f.context.AnkangBrowserAccount.ready;const api=f.context.AnkangBrowserAccount;
 await api.request('assistantPreferences',f.identity);assert(f.calls.at(-1).url.endsWith('/assistant/preferences'));assert.equal(f.calls.at(-1).options.method,'GET');
 await api.request('assistantPreferences',f.identity,{expected_version:0,health_context:true});assert.equal(f.calls.at(-1).options.method,'PUT');assert.equal(f.calls.at(-1).options.headers['X-CSRF-Token'],'memory-only');
 assert.deepEqual(JSON.parse(f.calls.at(-1).options.body),{expected_version:0,health_context:true});
 await api.request('assistantConversation',f.identity,{after:37,limit:30});assert(f.calls.at(-1).url.endsWith('/assistant/conversation?after=37&limit=30'));
 await assert.rejects(api.request('assistantConversation',f.identity,{after:-1}));
 await assert.rejects(api.request('assistantTurn',f.identity,{operation_id:account,text:'TEST incognito',private:true}));
 await api.request('assistantTurn',f.identity,{operation_id:account,text:'查看我已有的肩部结果',owner:'WRONG'});
 assert.deepEqual(JSON.parse(f.calls.at(-1).options.body),{operation_id:account,text:'查看我已有的肩部结果'});
 assert(![...f.memory.values()].join('').includes('查看我已有的肩部结果'));
});

test('family uses self account, CSRF and narrowly shaped mutation bodies',async()=>{
 const f=fixture();await f.context.AnkangBrowserAccount.ready;const api=f.context.AnkangBrowserAccount;
 for(const [action,tail,body,method] of [['family','',{},'GET'],['familyInvite','/invite',{},'POST'],['familyBind','/bind',{code:'1234ABCD'},'POST'],['familyGrant','/grant',{member:account,categories:[]},'POST'],['familyUnbind','/unbind',{member:account},'POST'],['familySummary','/summary',{name:'TEST',health:[],rehab:[],doses:[]},'PUT']]){
  await api.request(action,f.identity,body);const call=f.calls.at(-1);assert(call.url.endsWith('/patients/'+patient+'/family'+tail));assert.equal(call.options.method,method);
  if(method!=='GET'){assert.equal(call.options.headers['X-CSRF-Token'],'memory-only');assert.deepEqual(JSON.parse(call.options.body),body);}
 }
});

test('assessment plan API is account-bound, uncached, and cancels with empty JSON and CSRF',async()=>{
 const f=fixture();await f.context.AnkangBrowserAccount.ready;const api=f.context.AnkangBrowserAccount;
 await api.request('assessmentPlans',f.identity);
 const get=f.calls.findLast(c=>c.url.endsWith('/assistant/assessment-plans'));assert.equal(get.options.method,'GET');assert.equal(get.options.cache,'no-store');assert.equal(get.options.body,undefined);
 await api.request('assessmentPlanCancel',f.identity,{plan_id:account,record_id:'forged',status:'COMPLETED'});
 const cancel=f.calls.findLast(c=>c.url.endsWith('/assistant/assessment-plans/'+account+'/cancel'));assert.equal(cancel.options.method,'POST');assert.deepEqual(JSON.parse(cancel.options.body),{});assert.equal(cancel.options.headers['X-CSRF-Token'],'memory-only');
 await assert.rejects(api.request('assessmentPlanCancel',f.identity,{plan_id:'../../other'}),/编号无效/);
 assert(![...f.memory.values()].join('').includes('PLANNED'));
 f.context.navigator={onLine:false};const count=f.calls.length;await assert.rejects(api.request('assessmentPlans',f.identity),/离线/);assert.equal(f.calls.length,count);
});

test('cookie identity changing while a plan request is in flight discards the old response',async()=>{
 const f=fixture();await f.context.AnkangBrowserAccount.ready;
 f.onFetch(url=>{if(url.endsWith('/assistant/assessment-plans'))f.setCurrent({...f.identity,patient_id:account,csrf_token:'other'});});
 await assert.rejects(f.context.AnkangBrowserAccount.request('assessmentPlans',f.identity),/已变化/);
 assert.equal(f.calls.filter(c=>c.url.endsWith('/assistant/assessment-plans')).length,1);assert.equal(f.redirects[0],'/account?next=/');
});
