// Fictitious server replies and in-memory DOM only. No network, model or camera.
'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(__dirname+'/../static/assessment-plans.js','utf8');
const planId='11111111-1111-4111-8111-111111111111',patient='22222222-2222-4222-8222-222222222222',account='33333333-3333-4333-8333-333333333333';
const settle=()=>new Promise(resolve=>setImmediate(resolve));
function fixture(side='choose'){
 let html='',nodes=[],areaPresent=true;
 const area={get innerHTML(){return html;},set innerHTML(value){html=value;nodes=[...value.matchAll(/<button\b([^>]*)>/g)].map(m=>{const node={dataset:{}};for(const a of m[1].matchAll(/([\w-]+)="([^"]*)"/g)){if(a[1]==='id')node.id=a[2];if(a[1].startsWith('data-'))node.dataset[a[1].slice(5).replace(/-([a-z])/g,(_,x)=>x.toUpperCase())]=a[2];}return node;});},querySelector(selector){return nodes.find(n=>'#'+n.id===selector)||null;},querySelectorAll(selector){const key=selector.slice(6,-1).replace(/-([a-z])/g,(_,x)=>x.toUpperCase());return nodes.filter(n=>Object.hasOwn(n.dataset,key));}};
 const store={key:'cloud:'+patient,value:{owner:patient}},identity={patient_id:patient,account_id:account},calls=[],destinations=[];
 const state={tab:'plan',catalog:[{id:'shoulder_abduction',available:true}],uploadOwnerGeneration:0};
 const c={state,document:{querySelector:s=>s==='#assessment-plans'&&areaPresent?area:null},navigator:{onLine:true},URLSearchParams,localStorage:{getItem:()=>store.key},location:{search:'?tab=plan&assessmentPlan='+planId,assign:u=>destinations.push(u)},confirm:()=>true,PhoneLocal:{store},PhoneStore:{cloudKey:()=>true,ACTIVE_KEY:'active'},console};c.window=c;
 const server={items:[{id:planId,title:'TEST <肩部评估>',status:'PLANNED',created_at:1,source_turn_id:account,items:[{exercise_id:'shoulder_abduction',name:'TEST 肩外展',side,instruction:'TEST 舒适范围内完成',record_id:null}]}]};
 c.PhoneAccount={identity:()=>identity,aiScope:s=>{if(s!==store)throw Error('账号已变化');return {...identity};},assessmentPlans:async()=>{calls.push('list');return structuredClone(server);},assessmentPlanCancel:async(s,id)=>{calls.push(['cancel',id]);server.items[0].status='CANCELLED';return {status:'CANCELLED'};}};
 vm.runInNewContext(source,c);
 return {c,state,store,identity,server,calls,destinations,area,get html(){return html;},remove:()=>areaPresent=false,open:()=>area.querySelectorAll('[data-assessment-open]')[0]?.onclick(),mount:()=>c.AssessmentPlans.mount()};
}
test('server plan renders beside training, escapes text and never writes completion locally',async()=>{
 const h=fixture();await h.mount();assert.match(h.html,/评估计划/);assert.match(h.html,/TEST &lt;肩部评估&gt;/);assert.match(h.html,/待评估/);assert.match(h.html,/测量前选择侧别/);assert.equal(h.calls.length,1);assert.deepEqual(h.store.value,{owner:patient});
 h.server.items[0].status='COMPLETED';h.server.items[0].items[0].record_id='server-real-record';await h.mount();assert.match(h.html,/已完成/);assert.match(h.html,/已有关联评估/);assert.equal(h.area.querySelectorAll('[data-assessment-open]').length,0);assert.equal(h.area.querySelectorAll('[data-assessment-cancel]').length,0);
 const app=fs.readFileSync(__dirname+'/../static/app.js','utf8');assert.match(app,/id="plan-content"/);assert.match(app,/id="assessment-plans"/);assert.match(app,/AssessmentPlans.mount\(\)/);assert.match(fs.readFileSync(__dirname+'/../static/index.html','utf8'),/assessment-plans.js/);
});
for(const side of ['choose','bilateral'])test(side+' requires an explicit side before navigation and never opens a camera',async()=>{
 const h=fixture(side);await h.mount();await h.open();assert.equal(h.destinations.length,0);assert.match(h.html,/请选择本次测量侧/);
 await h.area.querySelector('#assessment-right').onclick();assert.equal(h.destinations.length,1);
 const url=new URL(h.destinations[0],'https://test.invalid');assert.equal(url.pathname,'/capture');assert.equal(url.searchParams.get('tab'),'assess');assert.equal(url.searchParams.get('entry'),'assistant');assert.equal(url.searchParams.get('exercise'),'shoulder_abduction');assert.equal(url.searchParams.get('side'),'right');assert.equal(url.searchParams.has('guide'),false);
 assert.equal(h.server.items[0].items[0].record_id,null);assert.deepEqual(h.store.value,{owner:patient});
});
test('known side opens the existing detail; unavailable or cancelled items cannot navigate',async()=>{
 const h=fixture('left');await h.mount();await h.open();assert.match(h.destinations[0],/side=left/);
 const unavailable=fixture();await unavailable.mount();unavailable.state.catalog=[];await unavailable.open();assert.equal(unavailable.destinations.length,0);assert.match(unavailable.html,/当前设备不可用/);
 const cancelled=fixture();await cancelled.mount();cancelled.server.items[0].status='CANCELLED';await cancelled.open();assert.equal(cancelled.destinations.length,0);assert.match(cancelled.html,/已变化/);
});
test('cancel requires confirmation, calls only server cancellation, and re-reads server status',async()=>{
 const h=fixture();await h.mount();h.c.confirm=()=>false;await h.area.querySelectorAll('[data-assessment-cancel]')[0].onclick();assert.deepEqual(h.calls,['list']);
 h.c.confirm=()=>true;await h.area.querySelectorAll('[data-assessment-cancel]')[0].onclick();assert.deepEqual(h.calls,['list',['cancel',planId],'list']);assert.match(h.html,/已取消/);assert.deepEqual(h.store.value,{owner:patient});
});
test('offline, logged-out and failing reads do not show cached plans or claim success',async()=>{
 for(const kind of ['offline','logout','failure']){const h=fixture();if(kind==='offline')h.c.navigator.onLine=false;if(kind==='logout')h.c.PhoneAccount.identity=()=>null;if(kind==='failure')h.c.PhoneAccount.assessmentPlans=async()=>{throw Error('TEST network unavailable');};await h.mount();assert.doesNotMatch(h.html,/TEST 肩外展/);assert.match(h.html,/重新读取/);if(kind!=='failure')assert.equal(h.calls.length,0);}
 const h=fixture();h.c.PhoneAccount.assessmentPlans=async()=>({items:[{id:planId,status:'PLANNED'}]});await h.mount();assert.match(h.html,/回复不完整/);
});
test('account or owner switch during reads discards the previous reply',async()=>{
 for(const field of ['account','owner','store']){const h=fixture();let resolve;h.c.PhoneAccount.assessmentPlans=()=>new Promise(r=>resolve=r);const pending=h.mount();await settle();if(field==='account')h.identity.account_id=patient;if(field==='owner')h.store.value.owner=account;if(field==='store')h.c.PhoneLocal.store={key:'other',value:{owner:account}};resolve(structuredClone(h.server));await pending;assert.doesNotMatch(h.html,/TEST 肩外展/);assert.match(h.html,/账号已变化/);}
});
test('late reads from an earlier generation or page cannot replace the current view',async()=>{
 const h=fixture();let resolve;h.c.PhoneAccount.assessmentPlans=()=>new Promise(r=>resolve=r);const pending=h.mount();await settle();h.c.PhoneAccount.assessmentPlans=async()=>({items:[]});await h.mount();resolve(structuredClone(h.server));await pending;assert.match(h.html,/暂无云端/);assert.doesNotMatch(h.html,/TEST 肩外展/);
 const moved=fixture();let finish;moved.c.PhoneAccount.assessmentPlans=()=>new Promise(r=>finish=r);const old=moved.mount();await settle();moved.state.uploadOwnerGeneration++;moved.area.innerHTML='TEST new owner view';finish(moved.server);await old;assert.equal(moved.html,'TEST new owner view');
});
test('switching accounts while choosing a side or cancelling cannot navigate or report success',async()=>{
 const h=fixture();await h.mount();await h.open();h.identity.account_id=patient;await h.area.querySelector('#assessment-left').onclick();assert.equal(h.destinations.length,0);assert.match(h.html,/账号已变化/);
 const cancelled=fixture();await cancelled.mount();cancelled.c.PhoneAccount.assessmentPlanCancel=async()=>{cancelled.identity.account_id=patient;return {};};await cancelled.area.querySelectorAll('[data-assessment-cancel]')[0].onclick();assert.match(cancelled.html,/账号已变化/);assert.doesNotMatch(cancelled.html,/已取消/);
});
test('action URLs accept only UUID plans and target the assessment section',()=>{const h=fixture();assert.equal(h.c.AssessmentPlans.planURL(planId),'/capture?tab=plan&assessmentPlan='+planId+'#assessment-plans');assert.equal(h.c.AssessmentPlans.planURL('../../other'),null);});
test('desktop paired capture forwards explicit account identity through the existing workbench bridge',async()=>{
 const h=fixture('left');delete h.c.PhoneLocal;const calls=[];
 h.c.api=async(path,opts)=>{calls.push({path,opts});if(path==='/product')return {snapshot:{profile:{ownerId:'TEST-desktop'},cloudAssistant:{connected:true,patient_id:patient,account_id:account}}};if(path.endsWith('assessmentPlanCancel'))return {};return structuredClone(h.server);};
 await h.mount();assert.match(h.html,/TEST 肩外展/);
 assert.deepEqual(JSON.parse(calls.find(c=>c.path.endsWith('assessmentPlans')).opts.body),{patient_id:patient,account_id:account});
 await h.area.querySelectorAll('[data-assessment-cancel]')[0].onclick();const cancel=calls.find(c=>c.path.endsWith('assessmentPlanCancel'));assert.deepEqual(JSON.parse(cancel.opts.body),{patient_id:patient,account_id:account,plan_id:planId});
});
test('desktop missing binding and account switch after RPC never expose server plans',async()=>{
 for(const mode of ['unbound','switch']){const h=fixture();delete h.c.PhoneLocal;let snapshots=0,calls=0;
  h.c.api=async path=>{if(path==='/product'){snapshots++;return {snapshot:{profile:{ownerId:'TEST-desktop'},cloudAssistant:{connected:mode!=='unbound',patient_id:patient,account_id:mode==='switch'&&snapshots>1?patient:account}}};}calls++;return structuredClone(h.server);};
  await h.mount();assert.doesNotMatch(h.html,/TEST 肩外展/);assert.equal(calls,mode==='unbound'?0:1);assert.match(h.html,/绑定|账号已变化/);
 }
});
