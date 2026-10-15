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
 for(const name of ['store.js','lin-profile.js','practice.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/'+name),'utf8'),c);
 storage.setItem(c.PhoneStore.ACTIVE_KEY,c.PhoneStore.KEY);c.PhoneStore.files.all=async()=>[];
 c.PhoneMotion={active:false,errors:new Map(),catalog:async()=>({rehab:[],fitness:[],posture:[]}),pause(){}};
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/engine.js'),'utf8'),c);
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

test('retired Agent routes cannot mutate daily facts; manual pages still persist and reopen',async()=>{
 const h=await local();await setupLocal(h);const schedule=h.local.store.value.daily.schedules[0],before=plain(h.local.store.value.daily);
 for(const operation of ['care.prepare','care.confirm','care.cancel','care.status','care.overview','care.next'])await assert.rejects(()=>post(h,'/api/product/'+operation,{}),/Agent 代操作已下架/);
 assert.deepEqual(plain(h.local.store.value.daily),before);
 await post(h,'/api/unified/daily.dose',{medId:'test-med',date:h.today,time:'08:00',status:'taken'});
 await post(h,'/api/unified/daily.schedule',{...schedule,time:'16:00'});
 const reopened=await local(h.storage);assert.equal(reopened.local.store.value.daily.doseAudit.length,1);assert.equal(reopened.local.store.value.daily.schedules[0].time,'16:00');
 assert.equal(reopened.local.store.value.careReceipts,undefined);assert(!Object.keys(reopened.local.store.value.kv).some(k=>k.startsWith('care:')));
});

test('retired care routing rejects unsafe methods and foreign origins without owner writes',async()=>{
 const h=await local();await setupLocal(h);const before=plain(h.local.store.value.daily);
 await assert.rejects(()=>post(h,'/api/product/care.overview',{ownerId:crypto.randomUUID()}),/Agent 代操作已下架/);
 await assert.rejects(()=>post(h,'/api/unified/care.prepare',{requestId:'forged',scope:{participant_id:crypto.randomUUID()},intents:[]}),/Agent 代操作已下架/);
 await assert.rejects(()=>h.local.request('/api/product/care.prepare'),/明确的照护/);
 await assert.rejects(()=>post(h,'https://other.test/api/product/care.overview',{}),/本地档案/);
 await assert.rejects(()=>h.local.request('/api/product/care.overview?ownerId=another'),/查询参数/);
 await assert.rejects(()=>h.local.request('/api/product/care.overview'),/Agent 代操作已下架/);
 assert.deepEqual(plain(h.local.store.value.daily),before);
});

test('rehabilitation chat stays read-only for daily operations and preserves manual training feedback gates',async()=>{
 const h=await local();await setupLocal(h);const before=plain(h.local.store.value.daily);
 const response=await post(h,'/api/product/chat',{text:'帮我把训练改到晚上八点'});
 assert.equal(response.turn.care,undefined);assert.deepEqual(plain(h.local.store.value.daily),before);
 const p=h.local.store.value.plans[0];assert.equal(h.local.planProgress(p).blocked,'');
 h.local.store.change(v=>v.jobs.push({id:crypto.randomUUID(),exercise:'test-exercise',side:'left',mode:'training',state:'done',created_at:new Date().toISOString(),measurement_version:'android-local-projection-1',plan_id:p.id,entry_key:p.items[0].key,result:{summary:{plan_completed:true},local_report:{validRatio:.9,contract:'android-local-projection-1'}}}));
 assert.match(h.local.planProgress(p).blocked,/训练感受/);
 h.local.store.change(v=>v.jobs[0].feedback={pain:1,fatigue:0});assert.match(h.local.planProgress(p).blocked,/不适/);
 assert.equal(h.local.planProgress(p).completed,0);
});

test('original lifecycle clear removes retained legacy approvals while retaining manual daily facts',async()=>{
 const h=await local();await setupLocal(h);h.c.PhoneStore.files.all=async()=>[];
 await post(h,'/api/unified/daily.dose',{medId:'test-med',date:h.today,time:'08:00',status:'taken'});
 h.local.store.write('care:personal:'+h.owner,{workflows:[{confirmationToken:'TEST_LEGACY_TOKEN'}]});
 h.local.store.change(v=>v.careReceipts=[{idempotencyKey:'TEST-legacy'}]);const daily=plain(h.local.store.value.daily);
 await h.local.domain.request('lifecycle.clear',h.owner,{confirmOwner:h.owner},new Date());
 assert.equal(h.local.store.value.careReceipts,undefined);assert(!Object.keys(h.local.store.value.kv).some(k=>k.startsWith('care:')));assert.deepEqual(plain(h.local.store.value.daily),daily);
 await assert.rejects(()=>post(h,'/api/product/care.status',{id:'TEST-legacy'}),/Agent 代操作已下架/);
});

test('actual local upload route queries its durable operation after lost reply and refuses duplicate writes',async()=>{
 const h=await local(),operation=crypto.randomUUID(),files=new Map(),inference=[];
 h.c.PhoneStore.files.put=async(id,value)=>files.set(id,value);h.c.PhoneStore.files.remove=async id=>files.delete(id);
 h.c.PhoneMotion.spec=async id=>({id});h.c.PhoneMotion.analyze=async(store,job)=>inference.push(job.id);
 const route='/api/jobs?exercise=shoulder_abduction&side=left&consent=yes',opts={method:'POST',headers:{'X-Rehab-Upload-Operation':operation},body:new Blob(['TEST video bytes'])};
 const created=await h.local.request(route,opts);const receipt=await h.local.request('/api/uploads/'+operation);
 assert.equal(receipt.id,created.id);assert.equal(receipt.upload_operation,operation);assert.equal(receipt.mode,'assessment');assert.equal(files.size,1);
 await assert.rejects(()=>h.local.request(route,opts),e=>e.status===409);
 await new Promise(resolve=>setTimeout(resolve,5));assert.deepEqual(inference,[created.id]);assert.equal(h.local.store.value.jobs.length,1);
 const reopened=await local(h.storage),after=await reopened.local.request('/api/uploads/'+operation);
 assert.equal(after.id,created.id);assert.equal(after.state,'failed');assert.equal(after.upload_operation,operation);
});
test('local upload queries keep malformed, missing and foreign-owner receipts separate',async()=>{
 const h=await local(),other=await local(),operation=crypto.randomUUID();
 h.local.store.change(v=>v.jobs.push({id:crypto.randomUUID(),upload_operation:operation,exercise:'shoulder_abduction',side:'left',mode:'assessment',state:'failed',created_at:new Date().toISOString(),video_available:false}));
 assert.equal((await h.local.request('/api/uploads/'+operation)).upload_operation,operation);
 await assert.rejects(()=>other.local.request('/api/uploads/'+operation),e=>e.status===404);
 await assert.rejects(()=>h.local.request('/api/uploads/not-a-key'),e=>e.status===400);
});
test('failed phone storage does not manufacture an upload receipt or start analysis',async()=>{
 const h=await local(),operation=crypto.randomUUID();let analysis=0;
 h.c.PhoneMotion.spec=async id=>({id});h.c.PhoneMotion.analyze=async()=>analysis++;
 h.c.PhoneStore.files.put=async()=>{throw Error('TEST quota failure');};
 await assert.rejects(()=>h.local.request('/api/jobs?exercise=shoulder_abduction&side=left&consent=yes',{method:'POST',headers:{'X-Rehab-Upload-Operation':operation},body:new Blob(['TEST video bytes'])}),/quota/);
 assert.equal(h.local.store.value.jobs.length,0);assert.equal(analysis,0);
 await assert.rejects(()=>h.local.request('/api/uploads/'+operation),e=>e.status===404);
});

async function allowedPractice(h,exercise='shoulder_abduction'){
 const catalog=JSON.parse(fs.readFileSync(path.join(__dirname,'../build/assets/catalog.json'),'utf8'));
 h.c.PhoneMotion.catalog=async()=>catalog;
 const spec=catalog.rehab.find(s=>s.id===exercise),baseline=spec.target_direction==='decrease'?90:0,sign=spec.target_direction==='decrease'?-1:1;
 const values=[...Array(15).fill(baseline),...Array(2).fill([10,25,45,50,50,25,0,0,0,0]).flat().map(v=>baseline+sign*v)];
 const report=h.c.LocalEngine.analyzeReplay(spec,'left',values.map((v,i)=>[i*.12,v]));
 assert.equal(report.reps.length,2,'synthetic metric fixture must pass the ORIGINAL engine');
 const id=crypto.randomUUID();h.local.store.change(v=>v.jobs.push({id,exercise,side:'left',mode:'assessment',state:'done',created_at:new Date().toISOString(),measurement_version:h.c.LocalEngine.VERSION,result:{summary:{completed:2},local_report:report}}));
 const {plan}=await post(h,'/api/plan',{general_activity_ok:true,standing_support_ok:true});
 return{operation_id:crypto.randomUUID(),plan_id:plan.id,plan_revision:plan.revision,entry_key:plan.items[0].key};
}
const endPractice=(count=null)=>({operation_id:crypto.randomUUID(),count,elapsed_ms:1200,reason:'ended',feedback:{pain:null,fatigue:null}});
const nextPractice=(companion=false)=>({operation_id:crypto.randomUUID(),manual_arrangement_confirmed:true,support_ready:true,companion_present:companion});
const completedPractice=(h,a,count=null)=>post(h,'/api/practice/'+a.id+'/finish',{...endPractice(count),reason:'completed_set'});

test('phone sequence keeps two original manual sets as separate facts and atomic links',async()=>{
 const h=await local(),{record}=await manualArrangement(h),original=plain(record),a=await post(h,'/api/practice',manualStart(record));
 assert.equal(a.schema_version,2);assert.equal(a.sequence_policy,'phone-guided-sequence-1');
 const one=await completedPractice(h,a,3);assert.equal(one.continuation.kind,'next_set');assert.equal(one.continuation.rest_remaining_ms,null);
 const value=nextPractice(),two=await post(h,'/api/practice/'+a.id+'/continue',value);assert.equal(two.set_index,2);assert.equal(two.journey_id,a.id);assert.equal(two.finish_payload,null);
 assert.equal(two.confirmed_count,null);assert.equal(two.formal_plan_contribution,null);assert.equal(two.predecessor_id,a.id);
 assert.equal((await h.local.request('/api/practice/'+a.id)).successor_id,two.id);
 const done=await completedPractice(h,two);assert.equal(done.self_reported_count,null);assert.equal(done.continuation,null);assert.equal(done.mode_segments[0].set_index,2);
 const rows=await h.local.request('/api/practice');assert.equal(rows.length,2);assert.deepEqual(plain(rows.map(r=>r.self_reported_count)),[null,3]);assert.deepEqual(plain(h.local.store.value.manualArrangements[0]),original);
 const b=h.c.PhoneStore.validateBackup(await h.local.backup());assert.equal(b.practices.length,2);assert.equal(h.local.store.value.jobs.length,0);assert.equal(h.local.store.value.plans.length,0);
});

test('phone continuation lost reply and concurrent replay keep one original child across reopen',async()=>{
 const h=await local(),{record}=await manualArrangement(h),a=await post(h,'/api/practice',manualStart(record));await completedPractice(h,a);
 const value=nextPractice(),route='/api/practice/'+a.id+'/continue';const [one,two]=await Promise.all([post(h,route,value),post(h,route,value)]);assert.equal(one.id,two.id);
 const reopened=await local(h.storage),same=await post(reopened,route,value);assert.equal(same.id,one.id);assert.equal(reopened.local.store.value.practices.length,2);
 await assert.rejects(()=>post(h,route,{...value,support_ready:false}),e=>e.reason.code==='CONTINUE_KEY_CONFLICT');
 await assert.rejects(()=>post(h,route,nextPractice()),e=>e.reason.code==='NO_NEXT_GROUP');
});

test('phone original rest authority rejects early writes and grants no exercise time',async()=>{
 const h=await local(),{record}=await manualArrangement(h,{settings:{target_reps:7,target_sets:2,rest_between_sets_s:30,target_angle_deg:null,needs_companion:false}}),a=await post(h,'/api/practice',manualStart(record));
 h.c.Date=class extends Date{constructor(...args){super(...(args.length?args:['2026-10-12T08:00:00Z']));}static now(){return Date.parse('2026-10-12T08:00:00Z');}};
 const one=await completedPractice(h,a),value=nextPractice();assert.equal(one.continuation.rest_remaining_ms,30000);assert.equal(one.continuation.rest_time_basis,'owning_device_receipt_utc');
 await assert.rejects(()=>post(h,'/api/practice/'+a.id+'/continue',value),e=>e.reason.code==='REST_PENDING');assert.equal(h.local.store.value.practices.length,1);
 h.c.Date=class extends Date{constructor(...args){super(...(args.length?args:['2026-10-12T08:00:31Z']));}static now(){return Date.parse('2026-10-12T08:00:31Z');}};
 assert.equal((await post(h,'/api/practice/'+a.id+'/continue',value)).set_index,2);assert.equal(h.local.store.value.practices[0].finish_payload.elapsed_ms,1200);
});

test('phone next automatic action uses the original proposal and never advances formal progress',async()=>{
 const h=await local();await allowedPractice(h);h.local.store.change(v=>v.jobs.push({...plain(v.jobs[0]),id:crypto.randomUUID(),side:'right'}));
 const {plan}=await post(h,'/api/plan',{general_activity_ok:true,standing_support_ok:true});assert.equal(plan.items.length,2);
 const before=plain(plan),a=await post(h,'/api/practice',{operation_id:crypto.randomUUID(),plan_id:plan.id,plan_revision:plan.revision,entry_key:plan.items[0].key});
 const one=await completedPractice(h,a,2);assert.equal(one.continuation.kind,'next_action');const two=await post(h,'/api/practice/'+a.id+'/continue',nextPractice());
 assert.equal(two.plan_ref.entry_key,plan.items[1].key);assert.equal(two.side,plan.items[1].side);assert.equal(two.set_index,1);assert.equal(two.execution_allowed,true);
 assert.deepEqual(plain(h.local.store.value.plans.at(-1)),before);assert.equal(h.local.planProgress(plan).completed,0);
 h.local.store.change(v=>v.kv['profile:'+v.owner].profile.conditions=['活动限制']);assert.equal((await h.local.request('/api/practice/'+two.id)).execution_allowed,false);
 assert.equal((await completedPractice(h,two)).state,'COMMITTED');
});

test('phone continuation commit failure does not split parent/child and can retry same key',async()=>{
 const h=await local(),{record}=await manualArrangement(h),a=await post(h,'/api/practice',manualStart(record));await completedPractice(h,a);
 const value=nextPractice(),write=h.storage.setItem;h.storage.setItem=()=>{throw Error('TEST sequence quota');};
 await assert.rejects(()=>post(h,'/api/practice/'+a.id+'/continue',value),/quota/);assert.equal(h.local.store.value.practices.length,1);assert.equal(h.local.store.value.practices[0].successor_id,null);
 h.storage.setItem=write;assert.equal((await post(h,'/api/practice/'+a.id+'/continue',value)).id,value.operation_id);assert.equal(h.local.store.value.practices.length,2);
});

test('phone close preserves original completed facts, ordinary end has no automatic completion',async()=>{
 const h=await local(),{record}=await manualArrangement(h),a=await post(h,'/api/practice',manualStart(record)),one=await completedPractice(h,a,3),value={operation_id:crypto.randomUUID()};
 const closed=await post(h,'/api/practice/'+a.id+'/close-journey',value);assert.equal(closed.journey_closed,true);assert.equal(closed.continuation,null);assert.deepEqual(closed.finish_payload,one.finish_payload);
 assert.equal((await post(h,'/api/practice/'+a.id+'/close-journey',value)).id,a.id);await assert.rejects(()=>post(h,'/api/practice/'+a.id+'/continue',nextPractice()),e=>e.reason.code==='NO_NEXT_GROUP');
 const b=await post(h,'/api/practice',manualStart(record)),ended=await post(h,'/api/practice/'+b.id+'/finish',endPractice());assert.equal(ended.continuation,null);assert.equal(ended.finish_payload.reason,'ended');assert.equal(ended.self_reported_count,null);
});

test('phone next group keeps definition, discomfort, owner and strict payload gates',async()=>{
 const h=await local(),{record}=await manualArrangement(h),a=await post(h,'/api/practice',manualStart(record));await completedPractice(h,a);
 await assert.rejects(()=>post(h,'https://other.test/api/practice/'+a.id+'/continue',nextPractice()),e=>e.status===403);
 await assert.rejects(()=>post(h,'/api/practice/'+a.id+'/continue',{...nextPractice(),set_index:2}),e=>e.status===400);
 await assert.rejects(()=>post(h,'/api/practice/'+a.id+'/continue',{...nextPractice(),support_ready:'yes'}),e=>e.status===400);
 h.c.PhoneMotion.catalog=async()=>({rehab:[],fitness:[],posture:[]});await assert.rejects(()=>post(h,'/api/practice/'+a.id+'/continue',nextPractice()),e=>e.reason.code==='MANUAL_DEFINITION_CHANGED');
 await manualArrangement(h);await post(h,'/api/practice/'+a.id+'/feedback',practiceFeedback(0,{pain:1,fatigue:null,note:null}));await assert.rejects(()=>post(h,'/api/practice/'+a.id+'/continue',nextPractice()),e=>e.reason.code==='PRACTICE_STOP_RECORDED');
 const other=await local();await assert.rejects(()=>other.local.request('/api/practice/'+a.id),e=>e.status===404);
});

test('phone backup checks sequence structure and links while old schema1 remains readable',async()=>{
 const h=await local(),{record}=await manualArrangement(h),a=await post(h,'/api/practice',manualStart(record));await completedPractice(h,a);
 const two=await post(h,'/api/practice/'+a.id+'/continue',nextPractice());await completedPractice(h,two);const b=plain(await h.local.backup());
 for(const mutate of [v=>v.practices[1].journey_id=crypto.randomUUID(),v=>v.practices[0].successor_id=null,v=>v.practices[1].set_index=1,v=>v.practices[1].arrangement_sequence[0].settings.target_sets=3,v=>v.practices[1].continue_payload.support_ready=false]){
  const forged=plain(b);mutate(forged.data);assert.throws(()=>h.c.PhoneStore.validateBackup(forged),/练习记录|备份结构/);
 }
 h.local.store.change(v=>{v.practices.splice(1);const r=v.practices[0];r.schema_version=1;for(const k of ['journey_id','arrangement_sequence','sequence_index','sequence_policy','journey_closed','successor_id'])delete r[k];});
 const old=await h.local.request('/api/practice/'+a.id);assert.equal(old.continuation,null);assert.equal(old.self_reported_count,null);assert.equal(h.c.PhoneStore.validateBackup(await h.local.backup()).practices.length,1);
});

test('actual PHONE_LOCAL practice route commits once, reopens, and never contributes to visual or plan dose',async()=>{
 const h=await local(),start=await allowedPractice(h),context=await h.local.request('/api/practice/context');
 assert.equal(context.participant_id,h.owner);assert.equal(context.provider,'phone-local-1');assert.equal(context.source_context,'PHONE_LOCAL:SELF_USE');
 const [a,b]=await Promise.all([post(h,'/api/practice',start),post(h,'/api/practice',start)]);
 assert.deepEqual(a,b);assert.equal(a.execution_allowed,true);assert.equal(h.local.store.value.practices.length,1);
 const ended=endPractice(10),first=await post(h,'/api/practice/'+a.id+'/finish',ended),again=await post(h,'/api/practice/'+a.id+'/finish',ended);
 assert.deepEqual(first,again);assert.equal(first.state,'COMMITTED');assert.equal(first.record_origin,'SELF_RECORDED');assert.equal(first.self_reported_count,10);assert.equal(first.confirmed_count,null);assert.equal(first.formal_plan_contribution,null);assert.equal(first.finish_payload.feedback.pain,null);
 const reopened=await local(h.storage),saved=await reopened.local.request('/api/practice/'+a.id);
 assert.deepEqual(saved,first);assert.equal((await reopened.local.request('/api/practice')).length,1);
 assert.equal(reopened.local.planProgress(reopened.local.store.value.plans[0]).completed,0);assert.equal(reopened.local.store.value.jobs.length,1);
 assert.equal(h.c.PhoneStore.validateBackup(await h.local.backup()).practices[0].id,a.id);
 await assert.rejects(()=>post(h,'/api/practice/'+a.id+'/finish',{...ended,count:11}),e=>e.status===409);
 await assert.rejects(()=>post(h,'/api/practice',{...start,entry_key:crypto.randomUUID()}),e=>e.status===409);
});

test('local practice has no fake grant when assessments, side, version or original feedback are not eligible',async()=>{
 for(const mutate of [v=>{v.jobs[0].result.local_report.validRatio=0;},v=>{v.plans[0].revision++;},v=>{v.plans[0].items[0].side='right';},v=>{v.kv['profile:'+v.owner].profile.conditions=['活动限制'];},v=>{v.jobs[0].created_at=new Date(Date.now()-8*86400000).toISOString();},v=>{v.jobs.push({...v.jobs[0],id:crypto.randomUUID(),mode:'training',plan_id:v.plans[0].id,entry_key:v.plans[0].items[0].key,feedback:null});}]){
  const h=await local(),start=await allowedPractice(h);h.local.store.change(mutate);
  await assert.rejects(()=>post(h,'/api/practice',start),e=>e.status===409);assert.equal(h.local.store.value.practices,undefined);
 }
});

test('practice finish still saves after eligibility changes, and plain end keeps null count and null feelings',async()=>{
 const h=await local(),start=await allowedPractice(h),a=await post(h,'/api/practice',start);
 h.local.store.change(v=>v.plans[0].revision++);
 assert.equal((await h.local.request('/api/practice/'+a.id)).execution_allowed,false);
 const saved=await post(h,'/api/practice/'+a.id+'/finish',endPractice());
 assert.equal(saved.self_reported_count,null);assert.equal(saved.record_origin,'GUIDED_PRACTICE');assert.equal(saved.execution_allowed,false);
 assert.equal((await post(h,'/api/practice',start)).state,'COMMITTED');
});

test('one open local practice and explicit discomfort stop remain real execution gates',async()=>{
 const h=await local(),start=await allowedPractice(h),a=await post(h,'/api/practice',start);
 await assert.rejects(()=>post(h,'/api/practice',{...start,operation_id:crypto.randomUUID()}),e=>e.status===409);
 const end={...endPractice(),reason:'discomfort',feedback:{pain:2,fatigue:null}};
 await post(h,'/api/practice/'+a.id+'/finish',end);
 await assert.rejects(()=>post(h,'/api/practice',{...start,operation_id:crypto.randomUUID()}),e=>e.reason?.code==='PRACTICE_STOP_RECORDED');
 assert.equal(h.local.store.value.practices.length,1);
});

test('failed original Store commit creates no practice receipt and same immutable operation can retry',async()=>{
 const h=await local(),start=await allowedPractice(h),save=h.storage.setItem;
 h.storage.setItem=()=>{throw Error('TEST storage quota')};await assert.rejects(()=>post(h,'/api/practice',start),/quota/);assert.equal(h.local.store.value.practices,undefined);
 h.storage.setItem=save;const a=await post(h,'/api/practice',start),end=endPractice(0);
 h.storage.setItem=()=>{throw Error('TEST storage quota')};await assert.rejects(()=>post(h,'/api/practice/'+a.id+'/finish',end),/quota/);
 assert.equal((await h.local.request('/api/practice/'+a.id)).state,'PRACTICING');
 h.storage.setItem=save;assert.equal((await post(h,'/api/practice/'+a.id+'/finish',end)).state,'COMMITTED');
});

test('practice routes reject scope overrides, foreign origins, unsafe methods and invalid feedback before mutation',async()=>{
 const h=await local(),start=await allowedPractice(h);
 await assert.rejects(()=>post(h,'https://other.test/api/practice',start),e=>e.status===403);
 await assert.rejects(()=>post(h,'/api/practice',{...start,owner:h.owner}),e=>e.status===400);
 await assert.rejects(()=>h.local.request('/api/practice/context?owner=other'),e=>e.status===403);
 await assert.rejects(()=>h.local.request('/api/practice',{method:'DELETE'}),e=>e.status===405);
 const a=await post(h,'/api/practice',start);
 for(const feedback of [{pain:-1,fatigue:null},{pain:null},{pain:false,fatigue:null},{pain:null,fatigue:11}])await assert.rejects(()=>post(h,'/api/practice/'+a.id+'/finish',{...endPractice(),feedback}),e=>e.status===400);
 const other=await local();await assert.rejects(()=>other.local.request('/api/practice/'+a.id),e=>e.status===404);
 assert.equal(h.local.store.value.practices[0].state,'PRACTICING');
});

test('practice backup validates ownership and source instead of reviving visual results from self reports',async()=>{
 const h=await local(),start=await allowedPractice(h),a=await post(h,'/api/practice',start);await post(h,'/api/practice/'+a.id+'/finish',endPractice(10));
 const b=await h.local.backup();assert.equal(h.c.PhoneStore.validateBackup(b).practices[0].self_reported_count,10);
 for(const mutate of [r=>r.context.participant_id=crypto.randomUUID(),r=>r.confirmed_count=10,r=>r.formal_plan_contribution=1,r=>r.record_origin='AUTOMATIC',r=>r.finish_payload.feedback.pain=undefined]){
  const forged=plain(b);mutate(forged.data.practices[0]);assert.throws(()=>h.c.PhoneStore.validateBackup(forged),/练习记录/);
 }
});

async function manualArrangement(h,changes={}){
 const catalog=JSON.parse(fs.readFileSync(path.join(__dirname,'../build/assets/catalog.json'),'utf8'));h.c.PhoneMotion.catalog=async()=>catalog;
 const payload={operation_id:crypto.randomUUID(),name:'TEST 本人已有安排',exercise_id:'shoulder_abduction',side:'left',settings:{target_reps:7,target_sets:2,rest_between_sets_s:null,target_angle_deg:null,needs_companion:false},...changes};
 const record=await post(h,'/api/practice/arrangements',payload);return{record,payload};
}
const manualStart=r=>({operation_id:crypto.randomUUID(),plan_id:r.id,plan_revision:r.revision,entry_key:r.items[0].key,manual_arrangement_confirmed:true,support_ready:true,companion_present:false});

test('real local manual input has a durable owned receipt without an assessment or automatic plan',async()=>{
 const h=await local(),{record,payload}=await manualArrangement(h);
 assert.equal((await h.local.request('/api/catalog')).manual_arrangement_entry,true);
 assert.deepEqual(await post(h,'/api/practice/arrangements',payload),record);
 assert.equal((await h.local.request('/api/practice/arrangements'))[0].id,record.id);
 assert.equal(h.local.store.value.jobs.length,0);assert.equal(h.local.store.value.plans.length,0);
 const start=manualStart(record),a=await post(h,'/api/practice',start);
 assert.equal(a.execution_allowed,true);assert.equal(a.formal_plan_ref,null);assert.equal(a.assessment_ref,null);assert.equal(a.guidance_policy,'phone-explicit-manual-practice-1');
 assert.equal(a.arrangement_ref.kind,'MANUAL_SAVED');assert.deepEqual(plain(a.settings),payload.settings);
 const end=endPractice(3),saved=await post(h,'/api/practice/'+a.id+'/finish',end);assert.equal(saved.self_reported_count,3);assert.equal(saved.confirmed_count,null);assert.equal(saved.formal_plan_contribution,null);
 const reopened=await local(h.storage);assert.deepEqual(await reopened.local.request('/api/practice/'+a.id),saved);assert.equal(reopened.local.store.value.manualArrangements.length,1);
 const backup=h.c.PhoneStore.validateBackup(await h.local.backup());assert.equal(backup.manualArrangements[0].id,record.id);assert.equal(backup.practices[0].id,a.id);
});

test('manual support and companion are explicit, and manual flags do not grant automatic eligibility',async()=>{
 const h=await local(),{record}=await manualArrangement(h,{settings:{target_reps:7,target_sets:2,rest_between_sets_s:30,target_angle_deg:null,needs_companion:true}}),start=manualStart(record);
 for(const field of ['manual_arrangement_confirmed','support_ready','companion_present']){await assert.rejects(()=>post(h,'/api/practice',{...start,companion_present:true,[field]:false}),e=>e.status===409&&e.reason.category==='MISSING_INPUT');await assert.rejects(()=>post(h,'/api/practice',{...start,[field]:1}),e=>e.status===400);}
 const plainStart={operation_id:start.operation_id,plan_id:start.plan_id,plan_revision:start.plan_revision,entry_key:start.entry_key};await assert.rejects(()=>post(h,'/api/practice',plainStart),e=>e.status===409);
 const auto=await allowedPractice(h);await assert.rejects(()=>post(h,'/api/practice',{...auto,manual_arrangement_confirmed:true,support_ready:true,companion_present:true}),e=>e.status===409);
 assert.equal(h.local.store.value.practices,undefined);assert.equal((await post(h,'/api/practice',{...start,companion_present:true})).execution_allowed,true);
});

test('manual create, practice start and finish preserve original Store quota failures and same-key retry',async()=>{
 const h=await local(),catalog=JSON.parse(fs.readFileSync(path.join(__dirname,'../build/assets/catalog.json'),'utf8'));h.c.PhoneMotion.catalog=async()=>catalog;
 const payload={operation_id:crypto.randomUUID(),name:'TEST 同键安排',exercise_id:'shoulder_abduction',side:'left',settings:{target_reps:7,target_sets:2,rest_between_sets_s:null,target_angle_deg:null,needs_companion:false}},save=h.storage.setItem;
 h.storage.setItem=()=>{throw Error('TEST original Store quota')};await assert.rejects(()=>post(h,'/api/practice/arrangements',payload),/quota/);assert.equal(h.local.store.value.manualArrangements,undefined);
 h.storage.setItem=save;const r=await post(h,'/api/practice/arrangements',payload),start=manualStart(r);
 h.storage.setItem=()=>{throw Error('TEST original Store quota')};await assert.rejects(()=>post(h,'/api/practice',start),/quota/);assert.equal(h.local.store.value.practices,undefined);
 h.storage.setItem=save;const a=await post(h,'/api/practice',start),end=endPractice();h.storage.setItem=()=>{throw Error('TEST original Store quota')};await assert.rejects(()=>post(h,'/api/practice/'+a.id+'/finish',end),/quota/);
 assert.equal((await h.local.request('/api/practice/'+a.id)).state,'PRACTICING');h.storage.setItem=save;assert.equal((await post(h,'/api/practice/'+a.id+'/finish',end)).state,'COMMITTED');
});

test('explicit local stop is immutable across manual arrangements and later zero feedback',async()=>{
 const h=await local(),{record}=await manualArrangement(h),a=await post(h,'/api/practice',manualStart(record));await post(h,'/api/practice/'+a.id+'/finish',endPractice());
 await post(h,'/api/practice/'+a.id+'/feedback',{operation_id:crypto.randomUUID(),expected_revision:0,values:{pain:1,fatigue:null,note:null}});
 await post(h,'/api/practice/'+a.id+'/feedback',{operation_id:crypto.randomUUID(),expected_revision:1,values:{pain:0,fatigue:null,note:null}});
 const other=await manualArrangement(h);await assert.rejects(()=>post(h,'/api/practice',manualStart(other.record)),e=>e.reason.code==='PRACTICE_STOP_RECORDED');
 const auto=await allowedPractice(h);await assert.rejects(()=>post(h,'/api/practice',auto),e=>e.reason.code==='PRACTICE_STOP_RECORDED');assert.equal(h.local.store.value.practices.length,1);
});

test('local manual input refuses foreign scope, dose rewrites, unsupported action and changed receipt',async()=>{
 const h=await local(),{record,payload}=await manualArrangement(h);
 await assert.rejects(()=>post(h,'https://other.test/api/practice/arrangements',payload),e=>e.status===403);await assert.rejects(()=>post(h,'/api/practice/arrangements',{...payload,owner:h.owner}),e=>e.status===400);
 await assert.rejects(()=>post(h,'/api/practice/arrangements',{...payload,name:'改动'}),e=>e.status===409);await assert.rejects(()=>post(h,'/api/practice/arrangements',{...payload,operation_id:crypto.randomUUID(),exercise_id:'fitness_squat'}));
 await assert.rejects(()=>post(h,'/api/practice',{...manualStart(record),settings:{target_reps:100}}),e=>e.status===400);
 const other=await local();assert.deepEqual(plain(await other.local.request('/api/practice/arrangements')),[]);await assert.rejects(()=>post(other,'/api/practice',manualStart(record)),e=>e.status===409);
 for(const mutate of [b=>b.data.manualArrangements[0].context.participant_id=crypto.randomUUID(),b=>b.data.manualArrangements[0].items[0].settings.target_reps=8,b=>b.data.manualArrangements[0].assessment_ref='fake']){const b=plain(await h.local.backup());mutate(b);assert.throws(()=>h.c.PhoneStore.validateBackup(b),/人工安排/);}
 const a=await post(h,'/api/practice',manualStart(record)),backup=plain(await h.local.backup());backup.data.practices[0].settings.target_reps=8;assert.throws(()=>h.c.PhoneStore.validateBackup(backup),/备份结构/);
 h.local.store.change(v=>v.practices[0].settings.target_reps=8);const rejected=await h.local.request('/api/practice/'+a.id);assert.equal(rejected.execution_allowed,false);assert.equal(rejected.execution_decision.code,'MANUAL_SNAPSHOT_CHANGED');
});

test('changed manual definition blocks further execution but does not block preserving already-ended facts',async()=>{
 const h=await local(),{record}=await manualArrangement(h),start=manualStart(record),a=await post(h,'/api/practice',start);
 h.c.PhoneMotion.catalog=async()=>({rehab:[],fitness:[],posture:[]});assert.equal((await h.local.request('/api/practice/'+a.id)).execution_allowed,false);
 assert.equal((await post(h,'/api/practice/'+a.id+'/finish',endPractice())).state,'COMMITTED');
 const b=await h.local.backup();for(const mutate of [r=>delete r.guidance_policy,r=>r.formal_plan_ref='fake',r=>r.execution_grant.formal_measurement_allowed=true,r=>r.start_payload.support_ready=false]){const forged=plain(b);mutate(forged.data.practices[0]);assert.throws(()=>h.c.PhoneStore.validateBackup(forged),/练习记录/);}
});

test('recent local measured discomfort still blocks manual practice without requiring an assessment',async()=>{
 const h=await local(),{record}=await manualArrangement(h);
 h.local.store.change(v=>v.jobs.push({id:crypto.randomUUID(),exercise:'shoulder_abduction',side:'left',mode:'training',state:'done',created_at:new Date().toISOString(),measurement_version:h.c.LocalEngine.VERSION,result:{summary:{plan_completed:false},local_report:{validRatio:.9,contract:h.c.LocalEngine.VERSION}},feedback:{pain:null,fatigue:5}}));
 await assert.rejects(()=>post(h,'/api/practice',manualStart(record)),e=>e.reason.code==='TRAINING_STOP_RECORDED');assert.equal(h.local.store.value.practices,undefined);
});

const practiceFeedback=(revision=0,values={note:'TEST 后补'})=>({operation_id:crypto.randomUUID(),expected_revision:revision,values:{pain:null,fatigue:null,note:null,...values}});
test('local feedback follows committed practice, survives reopen and never mutates finish or formal progress',async()=>{
 const h=await local(),start=await allowedPractice(h),a=await post(h,'/api/practice',start),path='/api/practice/'+a.id;
 const payload=practiceFeedback();await assert.rejects(()=>post(h,path+'/feedback',payload),e=>e.reason?.code==='PRACTICE_NOT_COMMITTED');
 const original=plain(await post(h,path+'/finish',endPractice(10))),r=plain(await post(h,path+'/feedback',payload));
 assert.equal(r.status,'COMMITTED');assert.equal(r.revision,1);assert.equal(r.values.pain,null);assert.equal(r.values.fatigue,null);
 const reopened=await local(h.storage);assert.deepEqual(plain(await reopened.local.request(path+'/feedback/operations/'+payload.operation_id)),r);
 assert.deepEqual(plain(await post(reopened,path+'/feedback',payload)),r);
 const saved=plain(await reopened.local.request(path));for(const k of ['finish_payload','self_reported_count','confirmed_count','mode_segments','formal_plan_contribution'])assert.deepEqual(saved[k],original[k]);
 assert.equal(saved.practice_feedback.operations.length,1);assert.equal((await h.local.request('/api/plan')).progress.completed,0);
 const backup=await reopened.local.backup();assert.equal(h.c.PhoneStore.validateBackup(backup).practices[0].practice_feedback.revision,1);
});
test('local feedback conflict reads latest revision but keeps original immutable operation receipt',async()=>{
 const h=await local(),start=await allowedPractice(h),a=await post(h,'/api/practice',start),path='/api/practice/'+a.id;await post(h,path+'/finish',endPractice());
 const first=practiceFeedback(),r=plain(await post(h,path+'/feedback',first)),second=practiceFeedback(0,{fatigue:2});
 await assert.rejects(()=>post(h,path+'/feedback',second),e=>e.reason?.code==='FEEDBACK_REVISION_CONFLICT');
 assert.deepEqual(plain((await h.local.request(path+'/feedback')).values),first.values);
 await assert.rejects(()=>h.local.request(path+'/feedback/operations/'+second.operation_id),e=>e.status===404);
 const next={...second,operation_id:crypto.randomUUID(),expected_revision:1};assert.equal((await post(h,path+'/feedback',next)).revision,2);
 assert.deepEqual(plain(await post(h,path+'/feedback',first)),r);assert.equal((await h.local.request(path+'/feedback')).revision,2);
 await assert.rejects(()=>post(h,path+'/feedback',{...first,values:next.values}),e=>e.reason?.code==='FEEDBACK_KEY_CONFLICT');
});
test('local feedback storage failure acknowledges nothing and same key saves after quota recovers',async()=>{
 const h=await local(),start=await allowedPractice(h),a=await post(h,'/api/practice',start),path='/api/practice/'+a.id;await post(h,path+'/finish',endPractice());
 const p=practiceFeedback(),save=h.storage.setItem;h.storage.setItem=()=>{throw Error('TEST feedback quota')};await assert.rejects(()=>post(h,path+'/feedback',p),/quota/);
 assert.equal((await h.local.request(path+'/feedback')).revision,0);await assert.rejects(()=>h.local.request(path+'/feedback/operations/'+p.operation_id),e=>e.status===404);
 h.storage.setItem=save;assert.equal((await post(h,path+'/feedback',p)).status,'COMMITTED');
});
test('later local discomfort stops further execution even after editing to zero but facts still save',async()=>{
 const h=await local(),start=await allowedPractice(h),a=await post(h,'/api/practice',start),path='/api/practice/'+a.id;await post(h,path+'/finish',endPractice());
 const b=await post(h,'/api/practice',{...start,operation_id:crypto.randomUUID()});
 await post(h,path+'/feedback',practiceFeedback(0,{pain:1}));await post(h,path+'/feedback',practiceFeedback(1,{pain:0}));
 assert.equal((await h.local.request('/api/practice/'+b.id)).execution_allowed,false);await post(h,'/api/practice/'+b.id+'/finish',endPractice());
 await assert.rejects(()=>post(h,'/api/practice',{...start,operation_id:crypto.randomUUID()}),e=>e.reason?.code==='PRACTICE_STOP_RECORDED');
});
test('feedback rejects malformed values, foreign owners and forged backup revisions',async()=>{
 const h=await local(),start=await allowedPractice(h),a=await post(h,'/api/practice',start),path='/api/practice/'+a.id;await post(h,path+'/finish',endPractice());
 for(const p of [practiceFeedback(0,{}),practiceFeedback(0,{pain:false}),practiceFeedback(0,{note:' '}),practiceFeedback(0,{fatigue:11}),practiceFeedback(0,{note:'x'.repeat(501)}),{...practiceFeedback(),owner:'foreign'}])await assert.rejects(()=>post(h,path+'/feedback',p),e=>e.status===400);
 const other=await local();await assert.rejects(()=>post(other,path+'/feedback',practiceFeedback()),e=>e.status===404);
 await post(h,path+'/feedback',practiceFeedback());const backup=await h.local.backup();
 for(const mutate of [f=>f.revision=2,f=>f.values.pain=0,f=>f.operations[0].expected_revision=2,f=>f.operations[0].values.note=null]){const b=plain(backup);mutate(b.data.practices[0].practice_feedback);assert.throws(()=>h.c.PhoneStore.validateBackup(b),/练习记录/);}
});
