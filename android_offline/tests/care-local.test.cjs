const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const PS=require('../web/store.js');
const plain=v=>JSON.parse(JSON.stringify(v));
const memory=()=>{const m=new Map();return{getItem:k=>m.get(k)??null,setItem:(k,v)=>m.set(k,String(v)),removeItem:k=>m.delete(k)};};
const deadline=()=>new Date(Date.now()+15*60000).toISOString();
function seed(storage=memory()){
 const store=new PS.Store(storage),owner=store.value.owner,today=PS.day();
 const medicine={id:'test-med',name:'合成测试药',dose:'既有安排',purpose:'',times:'',status:'active'};
 store.write('profile:'+owner,{ownerId:owner,dataMode:'real',profile:{name:'TEST',age:30,conditions:[],medications:[],medicationRecords:[medicine],familySharing:'denied'}});
 PS.applyDaily(store,'medSchedule',{medId:medicine.id,times:['08:00'],start:today,end:''},store.read('profile:'+owner).profile);
 store.change(v=>v.plans.push({id:crypto.randomUUID(),revision:1,items:[]}));
 const plan=store.value.plans[0];
 PS.applyDaily(store,'schedule',{id:crypto.randomUUID(),date:today,time:'14:00',kind:'training',name:'已保存的测试训练',planId:plan.id,revision:plan.revision},store.read('profile:'+owner).profile);
 return{store,owner,today,medicine,storage,port:PS.createCarePort(store,owner)};
}
async function doseAction(h){const f=await h.port.read();return{operation:'daily.dose',payload:{medId:h.medicine.id,date:h.today,time:'08:00',status:'taken'},expected:{medicine:f.medications[0],schedule:f.daily.medSchedules[h.medicine.id],dose:null},label:'记录测试服药'};}
async function scheduleAction(h){const f=await h.port.read(),s=f.daily.schedules[0];return{operation:'daily.schedule',payload:{id:s.id,date:s.date,time:'16:00',kind:s.kind,name:s.name,planId:s.planId,revision:s.revision},expected:{schedule:s,plan:{id:f.plans[0].id,revision:f.plans[0].revision}},label:'调整测试训练时间'};}

test('phone care facts bind owner/source/context and return independent copies',async()=>{
 const h=seed(),f=await h.port.read();assert.deepEqual(f.scope,{participant_id:h.owner,source_kind:'PHONE_LOCAL',usage_context:'SELF_USE'});
 f.medications[0].name='changed';f.daily.medSchedules[h.medicine.id].times=[];
 const again=await h.port.read();assert.equal(again.medications[0].name,h.medicine.name);assert.deepEqual(again.daily.medSchedules[h.medicine.id].times,['08:00']);
 await assert.rejects(()=>PS.createCarePort(h.store,crypto.randomUUID()).read(),/档案已变化/);
 h.store.change(v=>v.kv['profile:'+h.owner].ownerId=crypto.randomUUID());await assert.rejects(()=>h.port.read(),/本人用药档案/);
});

test('phone care atomically records one dose and survives concurrent replay and reopen',async()=>{
 const h=seed(),a=await doseAction(h),expires=deadline();
 const [one,two]=await Promise.all([h.port.execute(a,'test-write:0',expires),h.port.execute(a,'test-write:0',expires)]);
 assert.deepEqual(one,two);assert.equal(h.store.value.daily.doseAudit.length,1);assert.equal(h.store.value.careReceipts.length,1);
 const reopened=new PS.Store(h.storage),port=PS.createCarePort(reopened,h.owner);
 assert.deepEqual(await port.execute(a,'test-write:0',expires),one);assert.equal(reopened.value.daily.doseAudit.length,1);
 a.payload.status='skipped';await assert.rejects(()=>port.execute(a,'test-write:0',expires),/不同操作/);assert.equal(reopened.value.daily.doseAudit.length,1);
});

test('changed medicine, medication schedule or dose rejects a stale proposal without a receipt',async()=>{
 for(const mutate of [v=>v.kv['profile:'+v.owner].profile.medicationRecords[0].dose='changed',v=>v.daily.medSchedules['test-med'].times.push('09:00'),v=>v.daily.doses['test-med|'+PS.day()+'|08:00']={status:'skipped'}]){
  const h=seed(),a=await doseAction(h);h.store.change(mutate);const before=plain(h.store.value);
  await assert.rejects(()=>h.port.execute(a,'stale:0',deadline()),/已变化/);assert.deepEqual(h.store.value,before);assert.equal(h.store.value.careReceipts,undefined);
 }
});

test('care rescheduling preserves schedule identity and cannot bypass a changed plan revision',async()=>{
 const h=seed(),a=await scheduleAction(h),old=plain(h.store.value.daily.schedules[0]);
 await h.port.execute(a,'move:0',deadline());const moved=h.store.value.daily.schedules[0];
 for(const key of ['id','kind','name','planId','revision','date'])assert.equal(moved[key],old[key]);assert.equal(moved.time,'16:00');
 const stale=seed(),b=await scheduleAction(stale);stale.store.change(v=>v.plans[0].revision++);const before=plain(stale.store.value);
 await assert.rejects(()=>stale.port.execute(b,'move:0',deadline()),/版本已变化/);assert.deepEqual(stale.store.value,before);
 const forged=seed(),c=await scheduleAction(forged);c.payload.name='换成另一个任务';await assert.rejects(()=>forged.port.execute(c,'move:0',deadline()),/已变化/);
});

test('failed storage commit rolls back business write and receipt, then the same request can retry',async()=>{
 const h=seed(),a=await doseAction(h),expires=deadline(),before=plain(h.store.value),save=h.storage.setItem;
 h.storage.setItem=()=>{throw Error('storage quota test')};await assert.rejects(()=>h.port.execute(a,'retry:0',expires),/quota/);assert.deepEqual(h.store.value,before);
 h.storage.setItem=save;await h.port.execute(a,'retry:0',expires);assert.equal(h.store.value.daily.doseAudit.length,1);assert.equal(new PS.Store(h.storage).value.careReceipts.length,1);
});

test('expired approval prevents a new write but still recovers an already committed receipt',async()=>{
 const h=seed(),a=await doseAction(h),expires=deadline();const receipt=await h.port.execute(a,'saved:0',expires),originalNow=Date.now;
 try{Date.now=()=>Date.parse(expires)+1;assert.deepEqual(await h.port.execute(a,'saved:0',expires),receipt);await assert.rejects(()=>h.port.execute(a,'new:0',expires),/已过期/);}
 finally{Date.now=originalNow;}
 assert.equal(h.store.value.daily.doseAudit.length,1);
 await assert.rejects(()=>h.port.execute(a,'invalid:0','bad'),/期限无效/);
});

test('execution rejects extra fields, unknown tools and malformed keys before mutation',async()=>{
 const h=seed(),a=await doseAction(h),before=plain(h.store.value);
 await assert.rejects(()=>h.port.execute({...a,scope:{participant_id:h.owner}},'forged:0',deadline()),/字段/);
 await assert.rejects(()=>h.port.execute({...a,payload:{...a.payload,ownerId:h.owner}},'forged:0',deadline()),/字段/);
 await assert.rejects(()=>h.port.execute({...a,operation:'daily.medSchedule'},'forged:0',deadline()),/执行工具/);
 await assert.rejects(()=>h.port.execute(a,'../other',deadline()),/编号/);assert.deepEqual(h.store.value,before);
});

test('backup export and restore exclude pending workflows, tokens and execution receipts',async()=>{
 const h=seed();h.store.write('care:real:'+h.owner,{workflows:[{confirmationToken:'TEST_TOKEN'}]});
 await h.port.execute(await doseAction(h),'saved:0',deadline());
 const data=PS.backupData(h.store.value);assert(!JSON.stringify(data).includes('TEST_TOKEN'));assert.equal(data.careReceipts,undefined);assert.equal(Object.keys(data.kv).filter(k=>k.startsWith('care:')).length,0);
 const restored=PS.validateBackup({kind:'ankang-phone-backup',version:2,data:h.store.value});assert.equal(restored.careReceipts,undefined);assert(!Object.keys(restored.kv).some(k=>k.startsWith('care:')));assert.equal(restored.daily.doseAudit.length,1);
 assert.equal(h.store.value.careReceipts.length,1);assert.equal(h.store.read('care:real:'+h.owner).workflows[0].confirmationToken,'TEST_TOKEN');
});

// Evaluate today's source service instead of the ignored, previously built APK.
// This keeps new care tests independent of an older release bundle and UI lock.
let sourceBundle;
function bundle(){
 if(sourceBundle)return sourceBundle;
 const root=path.resolve(__dirname,'../../ankang/route1-health-agent'),ts=require(path.join(root,'node_modules/typescript')),modules=new Map();
 function collect(file){const id=path.relative(root,file).replaceAll('\\','/').replace(/\.ts$/,'');if(modules.has(id))return id;modules.set(id,'');let code=ts.transpileModule(fs.readFileSync(file,'utf8'),{fileName:file,compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText;code=code.replace(/require\("([^"\n]+)"\)/g,(_,dep)=>{if(!dep.startsWith('.'))throw Error('Unexpected nonlocal domain dependency');return 'require('+JSON.stringify(collect(path.resolve(path.dirname(file),dep)+'.ts'))+')';});modules.set(id,code);return id;}
 const entry=collect(path.join(root,'src/product/ProductService.ts'));
 sourceBundle='(function(){const factories={'+[...modules].map(([id,code])=>JSON.stringify(id)+':function(module,exports,require){'+code+'}').join(',')+'},cache={};function require(id){if(cache[id])return cache[id].exports;const m=cache[id]={exports:{}};factories[id](m,m.exports,require);return m.exports;}globalThis.AnkangDomain=require('+JSON.stringify(entry)+');})();';return sourceBundle;
}
async function local(storage=memory()){
 const c={crypto:globalThis.crypto,structuredClone,Date,console,Blob,File,URL,Headers,Response,TextDecoder,TextEncoder,Uint8Array,AbortController,DOMException,setTimeout,clearTimeout,localStorage:storage,
  location:{origin:'https://appassets.androidplatform.net',href:'/'},document:{addEventListener(){}},Element:class{},MutationObserver:class{},XMLHttpRequest:class{},alert:()=>{},confirm:()=>true};
 c.fetch=async()=>{throw Error('Network unexpectedly requested')};vm.createContext(c);vm.runInContext(bundle(),c);
 for(const name of ['store.js','lin-profile.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/'+name),'utf8'),c);
 storage.setItem(c.PhoneStore.ACTIVE_KEY,c.PhoneStore.KEY);c.PhoneStore.files.all=async()=>[];
 c.PhoneMotion={active:false,errors:new Map(),catalog:async()=>({rehab:[],fitness:[],posture:[]}),pause(){}};
 c.LocalEngine={VERSION:'android-local-projection-1'};
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/cloud.js'),'utf8'),c);vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/local-api.js'),'utf8'),c);await c.PhoneLocal.ready;
 const local=c.PhoneLocal,owner=local.store.value.owner,today=c.PhoneStore.day();
 return{c,local,owner,today,storage};
}
async function setupLocal(h){
 await h.local.domain.request('medication.save',h.owner,{record:{id:'test-med',name:'合成测试药',dose:'既有安排',times:'',purpose:'',status:'active'}},new Date());
 await h.local.request('/api/unified/daily.medSchedule',{method:'POST',body:JSON.stringify({medId:'test-med',times:['08:00'],start:h.today,end:''})});
 h.local.store.change(v=>v.plans.push({id:crypto.randomUUID(),revision:1,items:[{key:crypto.randomUUID(),exercise_id:'test-exercise',side:'left',settings:{target_reps:1,target_sets:1}}]}));
 const p=h.local.store.value.plans[0];
 await h.local.request('/api/unified/daily.schedule',{method:'POST',body:JSON.stringify({id:crypto.randomUUID(),date:h.today,time:'14:00',kind:'training',name:'已保存的测试训练',planId:p.id,revision:p.revision})});
}
const post=(h,route,p)=>h.local.request(route,{method:'POST',body:JSON.stringify(p)});

test('owner-bound local route prepares, confirms compound actions and reopens without duplicate writes',async()=>{
 const h=await local();await setupLocal(h);const schedule=h.local.store.value.daily.schedules[0];
 const w=await post(h,'/api/product/care.prepare',{requestId:'local:compound',intents:[{kind:'record_dose',medId:'test-med',date:h.today,time:'08:00',status:'taken'},{kind:'reschedule_rehab',scheduleId:schedule.id,date:h.today,time:'16:00'}]});
 assert.equal(w.status,'awaiting_confirmation');assert.equal(h.local.store.value.daily.doseAudit.length,0);assert.equal(h.local.store.value.daily.schedules[0].time,'14:00');
 const done=await post(h,'/api/unified/care.confirm',{id:w.id,confirmationToken:w.confirmationToken,confirmed:true});assert.equal(done.status,'succeeded');assert.equal(h.local.store.value.daily.doseAudit.length,1);assert.equal(h.local.store.value.daily.schedules[0].time,'16:00');
 const reopened=await local(h.storage);const again=await post(reopened,'/api/product/care.confirm',{id:w.id,confirmationToken:w.confirmationToken,confirmed:true});assert.equal(again.status,'succeeded');assert.equal(reopened.local.store.value.daily.doseAudit.length,1);
 const status=await post(h,'/api/product/care.status',{id:w.id});assert.equal(status.confirmationToken,undefined);
 const b=await h.local.backup();assert.equal(b.data.careReceipts,undefined);assert(!JSON.stringify(b).includes(w.confirmationToken));assert(!Object.keys(b.data.kv).some(k=>k.startsWith('care:')));
});

test('phone care routing rejects owner/scope overrides, unsafe methods and foreign origins',async()=>{
 const h=await local();await setupLocal(h);
 await assert.rejects(()=>post(h,'/api/product/care.overview',{ownerId:crypto.randomUUID()}),/字段/);
 await assert.rejects(()=>post(h,'/api/unified/care.prepare',{requestId:'forged',scope:{participant_id:crypto.randomUUID()},intents:[]}),/字段/);
 await assert.rejects(()=>h.local.request('/api/product/care.prepare'),/明确的照护/);
 await assert.rejects(()=>post(h,'https://other.test/api/product/care.overview',{}),/本地档案/);
 await assert.rejects(()=>h.local.request('/api/product/care.overview?ownerId=another'),/查询参数/);
 const overview=await h.local.request('/api/product/care.overview');assert.equal(overview.scope.participant_id,h.owner);assert.equal(overview.doses[0].status,'unrecorded');assert.equal(h.local.store.value.daily.doseAudit.length,0);
});

test('source chat carries care workflow and retains original next-training feedback gates',async()=>{
 const h=await local();await setupLocal(h);
 const response=await post(h,'/api/product/chat',{text:'记录今天08:00的合成测试药已服用'});
 assert.equal(response.turn.care.workflow.status,'awaiting_confirmation');assert.equal(h.local.store.value.daily.doseAudit.length,0);assert.match(response.turn.reply.text,/尚未执行/);
 let next=await h.local.request('/api/product/care.next');assert.equal(next.available,true);
 const p=h.local.store.value.plans[0];h.local.store.change(v=>v.jobs.push({id:crypto.randomUUID(),exercise:'test-exercise',side:'left',mode:'training',state:'done',created_at:new Date().toISOString(),measurement_version:'android-local-projection-1',plan_id:p.id,entry_key:p.items[0].key,result:{summary:{plan_completed:true},local_report:{validRatio:.9,contract:'android-local-projection-1'}}}));
 next=await h.local.request('/api/product/care.next');assert.equal(next.available,false);assert.match(next.reason,/训练感受/);
 h.local.store.change(v=>v.jobs[0].feedback={pain:1,fatigue:0});next=await h.local.request('/api/product/care.next');assert.equal(next.available,false);assert.match(next.reason,/不适/);
});

test('original lifecycle clear removes local care approvals/receipts while retaining daily facts',async()=>{
 const h=await local();await setupLocal(h);h.c.PhoneStore.files.all=async()=>[];
 const w=await post(h,'/api/product/care.prepare',{requestId:'clear:test',intents:[{kind:'record_dose',medId:'test-med',date:h.today,time:'08:00',status:'taken'}]});
 await post(h,'/api/product/care.confirm',{id:w.id,confirmationToken:w.confirmationToken,confirmed:true});const daily=plain(h.local.store.value.daily);
 await h.local.domain.request('lifecycle.clear',h.owner,{confirmOwner:h.owner},new Date());
 assert.equal(h.local.store.value.careReceipts,undefined);assert(!Object.keys(h.local.store.value.kv).some(k=>k.startsWith('care:')));assert.deepEqual(plain(h.local.store.value.daily),daily);
 await assert.rejects(()=>post(h,'/api/product/care.status',{id:w.id}),/照护任务/);
});
