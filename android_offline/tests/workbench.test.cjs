// Isolated fictitious TEST records and an in-memory cloud contract. No person,
// camera, AI provider or network is contacted by these regression tests.
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const PS=require('../web/store.js');
const plain=v=>JSON.parse(JSON.stringify(v));
const memory=()=>{const rows=new Map();return {getItem:k=>rows.get(k)??null,setItem:(k,v)=>rows.set(k,String(v)),removeItem:k=>rows.delete(k)};};
const catalogue=JSON.parse(fs.readFileSync(path.resolve(__dirname,'../build/assets/catalog.json'),'utf8'));
const spec=catalogue.rehab.find(s=>s.id==='shoulder_abduction');
function assessment(){return {id:crypto.randomUUID(),exercise:spec.id,side:'left',mode:'assessment',state:'done',created_at:new Date().toISOString(),measurement_version:'android-local-projection-1',result:{spec,summary:{completed:3},local_report:{contract:'android-local-projection-1',measurement_contract:spec.measurement_contract,min:0,max:70,validRatio:1,reps:[{duration:2},{duration:2},{duration:2}]}}};}
function published(){return {id:crypto.randomUUID(),version:2,status:'PUBLISHED',title:'TEST fictitious professional arrangement',summary:'Generated test data, never used for human training',items:[{exercise_id:spec.id,name:spec.label,side:'left',measurement_contract:spec.measurement_contract,settings:{target_reps:2,target_sets:1,target_angle_deg:40,rest_between_sets_s:30,allowed_elbow_flexion_deg:null,allowed_trunk_tilt_deg:null,lowering_tempo_min_s:null,lowering_tempo_max_s:null,use_of_hands:'not_recorded',needs_companion:false,sound_enabled:false,timing_plan:{}},dose:'',caution:'TEST only'}]};}
let sourceBundle;
function productBundle(){
 if(sourceBundle)return sourceBundle;
 const base=path.resolve(__dirname,'../../ankang/route1-health-agent'),ts=require(path.join(base,'node_modules/typescript')),modules=new Map();
 function collect(file){const id=path.relative(base,file).replaceAll('\\','/').replace(/\.ts$/,'');if(modules.has(id))return id;modules.set(id,'');const compiled=ts.transpileModule(fs.readFileSync(file,'utf8'),{fileName:file,compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText;modules.set(id,compiled.replace(/require\("([^"\n]+)"\)/g,(_,dep)=>{if(!dep.startsWith('.'))throw Error('Unexpected dependency');return 'require('+JSON.stringify(collect(path.resolve(path.dirname(file),dep)+'.ts'))+')';}));return id;}
 const entry=collect(path.join(base,'src/product/ProductService.ts'));sourceBundle='(function(){const factories={'+[...modules].map(([id,code])=>JSON.stringify(id)+':function(module,exports,require){'+code+'}').join(',')+'},cache={};function require(id){if(cache[id])return cache[id].exports;const m=cache[id]={exports:{}};factories[id](m,m.exports,require);return m.exports;}globalThis.AnkangDomain=require('+JSON.stringify(entry)+');})();';return sourceBundle;
}
async function environment(){
 const storage=memory(),initial=new PS.Store(storage),owner=initial.value.owner;
 const identity={origin:'https://139.224.216.18',role:'PATIENT',patient_id:crypto.randomUUID(),account_id:crypto.randomUUID(),username:'TEST-browser'};
 initial.write('profile:'+owner,{ownerId:owner,dataMode:'personal',profile:{name:'TEST fictitious local profile',age:30,conditions:[],medications:[],medicationRecords:[],familySharing:'denied'}});
 initial.change(v=>{v.jobs.push(assessment());v.cloudIdentity=identity;v.cloudBinding={patient_id:identity.patient_id,owner};v.cloudConsent=true;});storage.setItem(PS.ACTIVE_KEY,PS.KEY);
 const cloud={identity,offline:false,lose:'',operations:new Map(),messages:[],records:[],current:null,revision:0,acceptCalls:0,read:0,afterReply:null};
 async function request(action,value,body={}){
  if(cloud.offline)throw Error('TEST disconnected');if(value.patient_id!==cloud.identity?.patient_id)throw Error('TEST wrong account');let response;
  if(action==='append'){const doc=body.document;response=cloud.operations.get(doc.operation_id);if(!response){response={status:'COMMITTED',resource_id:crypto.randomUUID()};cloud.records.push(plain(doc));cloud.operations.set(doc.operation_id,response);}}
  else if(action==='send'){response=cloud.operations.get(body.operation_id);if(!response){const item={id:crypto.randomUUID(),sequence:cloud.messages.length+1,author_role:'PATIENT',text:body.text,created_at:new Date().toISOString()};cloud.messages.push(item);response={status:'COMMITTED',resource_id:item.id,item};cloud.operations.set(body.operation_id,response);}}
  else if(action==='messages')response={items:cloud.messages.slice(-50),read_cursor:cloud.read,unread_count:cloud.messages.filter(m=>m.author_role==='DOCTOR_ADMIN'&&m.sequence>cloud.read).length};
  else if(action==='read'){cloud.read=Math.max(cloud.read,body.cursor);response={status:'COMMITTED',read_cursor:cloud.read,unread_count:cloud.messages.filter(m=>m.author_role==='DOCTOR_ADMIN'&&m.sequence>cloud.read).length};}
  else if(action==='accept'){cloud.acceptCalls++;response=cloud.operations.get(body.operation_id);if(response)response={...response,idempotent:true};else{if(body.expected_current_revision!==cloud.revision){const e=Error('TEST stale current revision');e.status=412;throw e;}assert(body.local_validation.assessment_references.length);cloud.current=body.plan_id;cloud.revision++;response={status:'COMMITTED',resource_id:body.plan_id,current_revision:cloud.revision,idempotent:false};cloud.operations.set(body.operation_id,response);}}
  else if(action==='current')response={plan:cloud.current?{id:cloud.current}:null,current_revision:cloud.revision};
  else throw Error('Unexpected TEST operation: '+action);
  if(cloud.afterReply){const work=cloud.afterReply;cloud.afterReply=null;work();}
  if(cloud.lose===action){cloud.lose='';throw Error('TEST committed, reply lost');}return structuredClone(response);
 }
 const c={crypto,structuredClone,Date,console,Blob,File,URL,Headers,Response,TextDecoder,TextEncoder,Uint8Array,AbortController,DOMException,setTimeout,clearTimeout,localStorage:storage,location:{origin:'https://test.invalid',href:'/'},document:{addEventListener(){}},Element:class{},MutationObserver:class{},XMLHttpRequest:class{},alert:()=>{},confirm:()=>true};
 c.fetch=async()=>{throw Error('Network unexpectedly requested')};c.AnkangBrowserAccount={origin:identity.origin,identity:()=>cloud.identity,request};vm.createContext(c);vm.runInContext(productBundle(),c);
 for(const name of ['store.js','lin-profile.js','engine.js','practice.js','cloud.js'])vm.runInContext(fs.readFileSync(path.resolve(__dirname,'../web/'+name),'utf8'),c);
 let videos=0;c.PhoneStore.files.put=async()=>{videos++;};c.PhoneStore.files.all=async()=>[];
 c.PhoneMotion={active:false,errors:new Map(),catalog:async()=>catalogue,spec:async()=>spec,analyze:async()=>{},pause(){}};
 vm.runInContext(fs.readFileSync(path.resolve(__dirname,'../web/local-api.js'),'utf8'),c);await c.PhoneLocal.ready;
 vm.runInContext(fs.readFileSync(path.resolve(__dirname,'../web/account.js'),'utf8'),c);c.PhoneAccount.schedule=()=>{};
 return {c,cloud,storage,store:c.PhoneLocal.store,account:c.PhoneAccount,owner,get videos(){return videos;},reopen:()=>new c.PhoneStore.Store(storage)};
}
function trainingRoute(plan){return '/api/jobs?consent=yes&exercise='+spec.id+'&side=left&mode=training&plan_id='+plan.id+'&entry_key='+plan.items[0].key;}

test('saved local records have stable revisions, restart retry and no fictitious demo uploads',async()=>{
 const h=await environment();await h.account.queue(h.store);h.cloud.lose='append';await assert.rejects(()=>h.account.sync(h.store),/reply lost/);
 const reopened=h.reopen();await h.account.sync(reopened);assert.equal(h.cloud.records.length,2);assert(h.cloud.records.every(r=>r.payload.owner_id===h.owner));assert(!JSON.stringify(h.cloud.records).includes('cloudIdentity'));
 reopened.change(v=>v.jobs[0].feedback={pain:0,fatigue:2,revision:1});await h.account.queue(reopened);await h.account.sync(reopened);
 assert.equal(h.cloud.records.at(-1).payload.revision,2);assert.equal(h.cloud.records.at(-1).payload.result.feedback.fatigue,2);
 await h.account.queue(reopened);assert.equal((await h.account.sync(reopened)).uploaded,0);
 reopened.change(v=>v.fixture={synthetic:true});await assert.rejects(()=>h.account.queue(reopened),/展示档案/);
});

test('durable message survives offline/reopen/lost response and same-input resend once',async()=>{
 const h=await environment();h.cloud.offline=true;await assert.rejects(()=>h.account.send(h.store,'TEST fictitious follow-up'),/disconnected/);const operation=h.store.value.cloudMessageOutbox[0].operation_id;
 const restarted=h.reopen();h.cloud.offline=false;h.cloud.lose='send';await assert.rejects(()=>h.account.send(restarted,'TEST fictitious follow-up'),/reply lost/);await h.account.send(restarted,'TEST fictitious follow-up');
 assert.equal(h.cloud.messages.length,1);assert.equal(restarted.value.cloudMessageOutbox.length,1);assert.equal(restarted.value.cloudMessageOutbox[0].operation_id,operation);
 h.cloud.messages.push({id:crypto.randomUUID(),sequence:2,author_role:'DOCTOR_ADMIN',text:'TEST simulated doctor reply'});
 const read=await h.account.messages(restarted);assert.equal(read.unread_count,1);await h.account.markRead(restarted,1);assert.equal(restarted.value.cloudMessages.unread_count,1);await h.account.markRead(restarted,2);assert.equal((await h.account.messages(restarted)).unread_count,0);
 h.cloud.offline=true;assert.equal((await h.account.messages(restarted)).offline,true);h.cloud.offline=false;
 h.cloud.afterReply=()=>h.cloud.identity={...h.cloud.identity,account_id:crypto.randomUUID(),patient_id:crypto.randomUUID()};await assert.rejects(()=>h.account.messages(restarted),/绑定/);
 h.cloud.identity=null;await assert.rejects(()=>h.account.messages(restarted),/重新登录/);
});

test('local disk failure cannot create an executable plan or submit acceptance',async()=>{
 const h=await environment(),save=h.storage.setItem;h.storage.setItem=()=>{throw Error('TEST storage quota')};await assert.rejects(()=>h.account.adopt(h.store,published(),0),/quota/);h.storage.setItem=save;
 assert.equal(h.store.value.plans.length,0);assert.equal(h.cloud.acceptCalls,0);
});

test('lost acceptance reply restores frozen operation then activates only after current/fresh checks',async()=>{
 const h=await environment(),plan=published();h.cloud.lose='accept';await assert.rejects(()=>h.account.adopt(h.store,plan,0),/reply lost/);
 const pending=h.store.value.plans[0];assert.equal(pending.status,'PENDING_DOCTOR');assert.equal((await h.c.PhoneLocal.request('/api/plan')).plan,null);
 await assert.rejects(()=>h.c.PhoneLocal.request(trainingRoute(pending),{method:'POST',body:new Blob(['TEST'])}),/尚未确认/);assert.equal(h.videos,0);
 const restarted=h.reopen(),result=await h.account.adopt(restarted,plan,0);assert.equal(result.idempotent,true);assert.equal(result.local_status,'ACTIVE');assert.equal(restarted.value.plans.length,1);
 const local=restarted.value.plans[0];assert.match(local.items[0].key,/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/);assert.equal(h.cloud.operations.values().next().value.resource_id,plan.id);
 const backup=h.c.PhoneStore.validateBackup({kind:'ankang-phone-backup',version:2,data:h.c.PhoneStore.backupData(restarted.value)});assert.equal(backup.plans[0].id,local.id);assert.equal(backup.plans[0].items[0].key,local.items[0].key);assert.equal(backup.cloudAcceptances,undefined);
});

test('expired assessment after lost reply recovers receipt without activating; superseded reply also pauses',async()=>{
 for(const mode of ['expired','superseded']){const h=await environment(),plan=published();h.cloud.lose='accept';await assert.rejects(()=>h.account.adopt(h.store,plan,0),/reply lost/);
  if(mode==='expired')h.store.change(v=>v.jobs[0].created_at=new Date(Date.now()-8*86400000).toISOString());else{h.cloud.current=crypto.randomUUID();h.cloud.revision++;}
  const result=await h.account.adopt(h.reopen(),plan,0);assert.equal(result.idempotent,true);assert.equal(result.local_status,mode==='expired'?'NEEDS_REVIEW':'SUPERSEDED');assert.equal(h.reopen().value.plans[0].status,'PENDING_DOCTOR');
 }
});

test('deterministic revision rejection retires intent and fresh manual approval gets new operation',async()=>{
 const h=await environment(),plan=published();h.cloud.revision=1;await assert.rejects(()=>h.account.adopt(h.store,plan,0),/stale/);
 assert.equal(Object.keys(h.store.value.cloudAcceptances).length,0);assert.equal(h.store.value.plans[0].status,'PENDING_DOCTOR');
 assert.equal((await h.account.adopt(h.store,plan,1)).local_status,'ACTIVE');assert.equal(h.store.value.plans.filter(p=>p.status==='ACTIVE').length,1);
});

test('actual training POST rechecks latest own assessment, age and recent training feedback before storing video',async()=>{
 for(const mode of ['expired','failed','pain']){const h=await environment(),plan=published();await h.account.adopt(h.store,plan,0);const local=h.store.value.plans[0];
  h.store.change(v=>{if(mode==='expired')v.jobs[0].created_at=new Date(Date.now()-8*86400000).toISOString();else if(mode==='failed')v.jobs.push({...assessment(),state:'failed',created_at:new Date(Date.now()+1).toISOString()});else v.jobs.push({...assessment(),mode:'training',feedback:{pain:1,fatigue:0},created_at:new Date(Date.now()+1).toISOString()});});
  await assert.rejects(()=>h.c.PhoneLocal.request(trainingRoute(local),{method:'POST',body:new Blob(['TEST'])}),/最新有效本人评估/);assert.equal(h.videos,0);assert.equal(h.store.value.jobs.filter(j=>j.state==='analyzing').length,0);
 }
});

test('unsupported actions/settings and unbound account fail before any plan write',async()=>{
 for(const mode of ['id','settings','contract','binding']){const h=await environment(),plan=published();if(mode==='id')plan.items[0].exercise_id='TEST-unsupported';if(mode==='settings')plan.items[0].settings.timing_plan={hold_min_s:3};if(mode==='contract')plan.items[0].measurement_contract='TEST-other-contract';if(mode==='binding')h.store.change(v=>delete v.cloudBinding);
  await assert.rejects(()=>h.account.adopt(h.store,plan,0));assert.equal(h.store.value.plans.length,0);assert.equal(h.cloud.acceptCalls,0);
 }
});

test('two cloud stores cannot erase a newer offline message or adoption intent through stale whole-state writes',async()=>{
 const h=await environment(),second=h.reopen();h.cloud.offline=true;await assert.rejects(()=>h.account.send(h.store,'TEST A durable offline text'),/disconnected/);
 const raw=h.storage.getItem(h.store.key),operation=h.store.value.cloudMessageOutbox[0].operation_id;
 assert.throws(()=>second.change(v=>v.cloudMessages={items:[],unread_count:0}),/另一个页面更新/);await assert.rejects(()=>second.serial(()=>second.change(v=>v.plans.push({id:crypto.randomUUID()}))),/另一个页面更新/);
 assert.equal(h.storage.getItem(h.store.key),raw);assert.equal(h.reopen().value.cloudMessageOutbox[0].operation_id,operation);
 h.cloud.offline=false;const fresh=h.reopen();const stale=h.reopen();h.cloud.lose='accept';await assert.rejects(()=>h.account.adopt(fresh,published(),0),/reply lost/);const protectedRaw=h.storage.getItem(h.store.key);
 assert.throws(()=>stale.commit(stale.value),/另一个页面更新/);assert.equal(h.storage.getItem(h.store.key),protectedRaw);assert.equal(Object.keys(h.reopen().value.cloudAcceptances).length,1);
});

test('native RPC replies bind random page nonce and actor, so delayed old-page data cannot resolve a new page',async()=>{
 const a=await environment(),b=await environment(),sentA=[],sentB=[];
 b.cloud.identity=structuredClone(a.cloud.identity);
 for(const [h,sent] of [[a,sentA],[b,sentB]]){h.c.AnkangBrowserAccount=null;h.c.OfflineAndroid={accountIdentity:()=>JSON.stringify(h.cloud.identity),accountRequest:(id,action,body)=>sent.push({id,action,body})};}
 const old=a.account.request('plans',a.cloud.identity);let settled=false;const newer=b.account.request('plans',b.cloud.identity).then(v=>{settled=true;return v;});
 assert.notEqual(sentA[0].id,sentB[0].id);assert.match(sentB[0].id,/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}:1$/);
 b.account.reply(sentA[0].id,200,JSON.stringify({items:['TEST old-page private plan']}));await Promise.resolve();assert.equal(settled,false);
 b.account.reply(sentB[0].id,200,JSON.stringify({items:['TEST current-page plan']}));assert.deepEqual(plain(await newer).items,['TEST current-page plan']);
 a.account.reply(sentA[0].id,200,JSON.stringify({items:[]}));await old;
 const changing=b.account.request('plans',b.cloud.identity);b.cloud.identity={...b.cloud.identity,account_id:crypto.randomUUID(),patient_id:crypto.randomUUID()};b.account.reply(sentB[1].id,200,JSON.stringify({items:['TEST other account']}));await assert.rejects(()=>changing,/账号已变化/);
 const logout=b.account.request('logout',b.cloud.identity);b.cloud.identity=null;b.account.reply(sentB[2].id,200,'{"ok":true}');assert.equal((await logout).ok,true);
 const java=fs.readFileSync(path.resolve(__dirname,'../src/cn/tele/rehabilitation/offline/MainActivity.java'),'utf8'),method=java.slice(java.indexOf('public void accountRequest(')),pattern=method.match(/id\.matches\("([^"]+)"\)/)[1];assert(new RegExp('^(?:'+pattern+')$').test(sentB[0].id));assert(!new RegExp('^(?:'+pattern+')$').test('1'));
});
