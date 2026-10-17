// In-memory accounts, computed-result fixtures and transport receipts only.
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function fixture(){
 const id=crypto.randomUUID(),patient=crypto.randomUUID(),account=crypto.randomUUID(),memory=new Map();
 const storage={getItem:k=>memory.get(k)??null,setItem:(k,v)=>memory.set(k,String(v))};
 const c={crypto,structuredClone,localStorage:storage,console,navigator:{onLine:true},TextEncoder,setTimeout,clearTimeout};c.globalThis=c;
 vm.createContext(c);vm.runInContext(fs.readFileSync(__dirname+'/../web/store.js','utf8'),c);
 const store=new c.PhoneStore.Store(storage,c.PhoneStore.CLOUD_PREFIX+patient);storage.setItem(c.PhoneStore.ACTIVE_KEY,store.key);
 const plan={id,status:'PLANNED',items:['knee_extension','knee_flexion'].map(exercise_id=>({exercise_id,side:'left',record_id:null}))};
 const calls=[];let failAppend=false,failLink=false;
 c.PhoneLocal={store};c.PhoneAccount={aiScope:()=>({patient_id:patient,account_id:account}),schedule:()=>{},assessmentPlans:async()=>({items:[structuredClone(plan)]}),jobPayload:j=>({kind:'assessment',result:{...j.result.summary,exercise_id:j.exercise,analysis_state:j.state}}),request:async(action,identity,body)=>{calls.push({action,body:structuredClone(body)});if(failAppend)throw Error('TEST offline');return{status:'COMMITTED',resource_id:id};},assessmentPlanResult:async(s,p,index,record)=>{calls.push({action:'link',index,record});if(failLink)throw Error('TEST reply lost');plan.items[index].record_id=record;return{status:'COMMITTED',record_id:record};}};
 vm.runInContext(fs.readFileSync(__dirname+'/../web/assessment-run.js','utf8'),c);
 const api=c.PhoneAssessmentRun;
 async function job(){const run=await api.begin(store,plan,0,'left',true),operation=crypto.randomUUID(),binding=await api.prepareUpload(store,run,0,'knee_extension','left',operation);
  const j={id:crypto.randomUUID(),created_at:new Date(Date.now()+1).toISOString(),upload_operation:operation,mode:'assessment',exercise:'knee_extension',side:'left',state:'done',measurement_version:'android-local-projection-1',result:{summary:{completed:2,valid_ratio:.9},local_report:{contract:'android-local-projection-1'}}};
  store.change(v=>{api.bindJobValue(store,v,j,binding);v.jobs.push(j);});return{run,j};}
 return{c,api,store,plan,calls,job,set failAppend(v){failAppend=v;},set failLink(v){failLink=v;}};
}
test('ordered run requires consent, current first item and matching result',async()=>{
 const h=fixture();await assert.rejects(h.api.begin(h.store,h.plan,0,'left'),/确认/);
 await assert.rejects(h.api.begin(h.store,h.plan,1,'left',true),/顺序/);
 const {run,j}=await h.job();await h.api.onSaved(h.store,j.id);
 assert.equal(h.api.localStep(h.store,h.plan.id,0).linked,true);assert.deepEqual(h.calls.map(x=>x.action),['append','link']);
 await h.api.onSaved(h.store,j.id);assert.equal(h.calls.length,2);
 await assert.rejects(h.api.prepareUpload(h.store,run,0,j.exercise,'right'),/顺序|不符/);
});
test('lost append response retains identical operation and saved result across reload',async()=>{
 const h=fixture(),{run,j}=await h.job();h.failAppend=true;await h.api.onSaved(h.store,j.id);const first=structuredClone(h.calls[0].body);
 assert.equal(h.api.localStep(h.store,h.plan.id,0).linked,false);h.failAppend=false;await h.api.resume(h.store);
 assert.deepEqual(h.calls[1].body,first);assert.equal(h.api.localStep(h.store,h.plan.id,0).linked,true);
});
test('lost result-link response retries only link, never uploads new record',async()=>{
 const h=fixture(),{j}=await h.job();h.failLink=true;await h.api.onSaved(h.store,j.id);h.failLink=false;await h.api.resume(h.store);
 assert.deepEqual(h.calls.map(x=>x.action),['append','link','link']);
});
for(const kind of ['partial','synthetic','other-action','switched-account'])test(kind+' cannot publish a plan result',async()=>{
 const h=fixture(),{j}=await h.job();h.store.change(v=>{const saved=v.jobs[0];if(kind==='partial')saved.result.summary.completed=0;if(kind==='synthetic')saved.synthetic=true;if(kind==='other-action')saved.exercise='shoulder_abduction';});
 if(kind==='switched-account')h.c.localStorage.setItem(h.c.PhoneStore.ACTIVE_KEY,'other');
 await h.api.onSaved(h.store,j.id).catch(()=>{});assert.equal(h.calls.length,0);
});
