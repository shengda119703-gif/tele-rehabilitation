/* Explicit plan-run consent and single-job outbox. Never publishes history. */
(function(root){
'use strict';
const POLICY='assessment-run-single-results-1',UUID=/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/;
const copy=v=>structuredClone(v),running=new Map();
function scope(store){
 const value=root.PhoneAccount.aiScope(store),owner=store.value.owner;
 if(root.PhoneLocal&&root.PhoneLocal.store!==store||store.value.fixture||root.PhoneStore.cloudKey(store.key)&&localStorage.getItem(root.PhoneStore.ACTIVE_KEY)!==store.key)throw Error('账号已变化，请返回本人评估计划');
 return {owner,patient_id:value.patient_id,account_id:value.account_id,key:store.key};
}
function equal(a,b){return ['owner','patient_id','account_id','key'].every(k=>a[k]===b[k]);}
function guard(store,expected){if(!equal(scope(store),expected))throw Error('账号已变化，原评估待办保留');}
function run(store,id,expected=scope(store)){
 guard(store,expected);const value=store.value.assessmentPlanRuns?.find(r=>r.id===id);
 if(!value||value.policy!==POLICY||!equal(value.scope,expected)||!UUID.test(value.plan_id)||!Array.isArray(value.items))throw Error('本次保存本人档案的授权不存在，请从评估计划重新进入');
 return value;
}
async function change(store,expected,fn){return store.serial(()=>{guard(store,expected);return store.change(v=>fn(v));});}
async function rpc(store,expected,action,body={}){
 guard(store,expected);if(root.navigator?.onLine===false)throw Error('当前离线，本次结果待联网核对');
 const result=await root.PhoneAccount.request(action,root.PhoneAccount.aiScope(store),{...body,account_id:expected.account_id});guard(store,expected);return result;
}
async function serverPlan(store,expected,id){
 guard(store,expected);const result=await root.PhoneAccount.assessmentPlans(store);guard(store,expected);
 const plan=result.items?.find(p=>p.id===id);if(!plan||!Array.isArray(plan.items))throw Error('原评估计划已变化，请刷新');return plan;
}
function first(plan){return plan.items.findIndex(i=>i.record_id===null);}
function pending(plan,index){if(plan.status!=='PLANNED'||first(plan)!==index)throw Error('请按顺序完成当前评估，待服务器确认后再继续');}
async function begin(store,plan,index,side,consented=false){
 const expected=scope(store);pending(plan,index);
 if(!['left','right'].includes(side))throw Error('请选择本次测量侧');
 const original=store.value.assessmentPlanRuns?.find(r=>r.plan_id===plan.id&&r.policy===POLICY&&equal(r.scope,expected));
 if(!original&&!consented)throw Error('请先确认本次视频分析结果保存本人档案');
 return change(store,expected,v=>{
  const runs=v.assessmentPlanRuns??=[],saved=runs.find(r=>r.plan_id===plan.id&&r.policy===POLICY&&equal(r.scope,expected));
  if(saved){if(saved.items.length!==plan.items.length||saved.items.some((i,n)=>i.exercise_id!==plan.items[n].exercise_id||i.planned_side!==plan.items[n].side))throw Error('原计划项目已变化，请重新核对');return saved.id;}
  if(runs.length>=100)throw Error('本机评估待办已满，请先核对已有结果');
  const value={id:crypto.randomUUID(),policy:POLICY,scope:expected,plan_id:plan.id,consented_at:new Date().toISOString(),installation_id:crypto.randomUUID(),items:plan.items.map(i=>({exercise_id:i.exercise_id,planned_side:i.side,side:null,upload_operation:null,job_id:null,document:null,record_id:null,linked:false,last_error:''}))};
  runs.push(value);return value.id;
 });
}
async function prepareUpload(store,id,index,exercise,side,operation=crypto.randomUUID()){
 if(!UUID.test(operation))throw Error('上传编号无效');
 const expected=scope(store),saved=run(store,id,expected),plan=await serverPlan(store,expected,saved.plan_id);pending(plan,index);
 const item=plan.items[index];if(!item||item.exercise_id!==exercise||!['left','right'].includes(side)||['left','right'].includes(item.side)&&item.side!==side)throw Error('本次录像动作或侧别与计划不符');
 return change(store,expected,v=>{
  const r=v.assessmentPlanRuns.find(r=>r.id===id),step=r?.items[index];if(!step||step.exercise_id!==exercise)throw Error('本次评估授权已变化');
  if(step.document||step.record_id)throw Error('本项已有待核对上传，请先恢复原结果，不能重复录入');
  const previous=v.jobs.find(j=>j.id===step.job_id);
  if(previous&&['queued','analyzing','uploading'].includes(previous.state))throw Error('本项视频仍在分析，请等待结果');
  if(previous?.state==='done'){try{validJob(previous,r,index);throw Error('本项结果已保存，请先核对上传');}catch(error){if(error.message==='本项结果已保存，请先核对上传')throw error;}}
  step.side=side;step.upload_operation=operation;step.job_id=null;step.last_error='';
  return {run_id:id,item_index:index,upload_operation:step.upload_operation};
 });
}
function bindJobValue(store,value,job,binding){
 const expected=scope(store),saved=run(store,binding.run_id,expected),step=saved.items[binding.item_index];
 if(!step||step.upload_operation!==job.upload_operation||step.job_id||job.mode!=='assessment'||job.exercise!==step.exercise_id||job.side!==step.side||!UUID.test(job.id)||Date.parse(job.created_at)<Date.parse(saved.consented_at))throw Error('本次录像未取得匹配的计划保存授权');
 const target=value.assessmentPlanRuns.find(r=>r.id===saved.id).items[binding.item_index];target.job_id=job.id;
 job.assessment_run_id=saved.id;job.assessment_item_index=binding.item_index;
}
function validJob(job,saved,index){
 const step=saved.items[index],result=job?.result,summary=result?.summary,report=result?.local_report;
 if(!step||!job||job.id!==step.job_id||job.upload_operation!==step.upload_operation||job.assessment_run_id!==saved.id||job.assessment_item_index!==index||job.state!=='done'||job.mode!=='assessment'||job.exercise!==step.exercise_id||job.side!==step.side||job.synthetic||job.fixture||result?.synthetic||result?.fixture||report?.synthetic||report?.fixture||job.measurement_version!=='android-local-projection-1'||report?.contract!=='android-local-projection-1'||!Number.isSafeInteger(summary?.completed)||summary.completed<=0||!Number.isFinite(summary.valid_ratio)||summary.valid_ratio<0||summary.valid_ratio>1)throw Error('本项还没有可保存的真实完整评估结果，请重新录制有效视频');
 return root.PhoneAccount.jobPayload(job);
}
function changed(){if(root.Event)root.dispatchEvent?.(new root.Event('assessment-run-updated'));}
async function processOne(store,id,index){
 const expected=scope(store);let saved=run(store,id,expected),step=saved.items[index];if(!step?.job_id)return;
 try{
  const plan=await serverPlan(store,expected,saved.plan_id);saved=run(store,id,expected);step=saved.items[index];
  if(step.record_id&&plan.items[index]?.record_id===step.record_id){await change(store,expected,v=>{const s=v.assessmentPlanRuns.find(r=>r.id===id).items[index];s.linked=true;s.last_error='';});changed();return;}
  pending(plan,index);const job=store.value.jobs.find(j=>j.id===step.job_id),payload=validJob(job,saved,index);
  if(step.document&&JSON.stringify(step.document.payload.result)!==JSON.stringify(payload.result))throw Error('原评估结果已变化，不能替换已准备的上传');
  if(!step.document){
   const source=root.AnkangBrowserAccount?'WEB_LOCAL':'APK_LOCAL',key='assessment:'+id+':'+index;
   const document={operation_id:crypto.randomUUID(),source_event_id:key+':'+job.id,installation_id:saved.installation_id,source_kind:source,payload:{...payload,schema:'ankang-workbench-record-1',source,owner_id:expected.owner,patient_id:expected.patient_id,captured_at:job.finished_at||job.created_at,record_key:key,revision:1}};
   if(new TextEncoder().encode(JSON.stringify(document)).length>32768)throw Error('本项结果过大，已保留本机评估，请联系技术支持');
   await change(store,expected,v=>{const s=v.assessmentPlanRuns.find(r=>r.id===id).items[index];if(s.job_id!==job.id)throw Error('评估项目已变化');s.document??=copy(document);});
  }
  step=run(store,id,expected).items[index];
  if(!step.record_id){
   const receipt=await rpc(store,expected,'append',{document:copy(step.document)});
   if(receipt.status!=='COMMITTED'||!UUID.test(receipt.resource_id))throw Error('本人档案保存回执未确认，原操作保留待重试');
   await change(store,expected,v=>{v.assessmentPlanRuns.find(r=>r.id===id).items[index].record_id=receipt.resource_id;});
  }
  step=run(store,id,expected).items[index];
  const receipt=await root.PhoneAccount.assessmentPlanResult(store,saved.plan_id,index,step.record_id);guard(store,expected);
  if(receipt.status!=='COMMITTED'||receipt.record_id!==step.record_id)throw Error('本项评估完成回执未确认，请核对原操作');
  const checked=await serverPlan(store,expected,saved.plan_id);
  if(checked.items[index]?.record_id!==step.record_id)throw Error('服务器尚未确认本项评估，请重试核对');
  await change(store,expected,v=>{const s=v.assessmentPlanRuns.find(r=>r.id===id).items[index];s.linked=true;s.last_error='';});changed();
 }catch(error){
  try{await change(store,expected,v=>{const s=v.assessmentPlanRuns?.find(r=>r.id===id)?.items[index];if(s)s.last_error=String(error.message).slice(0,200);});}catch{/* Another account never receives this callback. */}
  changed();throw error;
 }
}
function process(store,id,index){
 const key=store.key+':'+id+':'+index;if(running.has(key))return running.get(key);
 const task=processOne(store,id,index).finally(()=>running.delete(key));running.set(key,task);return task;
}
async function onSaved(store,jobId){
 scope(store);const work=[];
 for(const saved of store.value.assessmentPlanRuns||[])for(let index=0;index<saved.items.length;index++){const step=saved.items[index];if(step.job_id===jobId&&!step.linked&&store.value.jobs.find(j=>j.id===jobId)?.state==='done')work.push(process(store,saved.id,index));}
 return Promise.allSettled(work);
}
async function resume(store){
 scope(store);const ids=(store.value.assessmentPlanRuns||[]).flatMap(r=>r.items.filter(i=>i.job_id&&!i.linked).map(i=>i.job_id));
 for(const id of ids)await onSaved(store,id);
}
function localStep(store,planId,index){
 const expected=scope(store),saved=store.value.assessmentPlanRuns?.find(r=>r.plan_id===planId&&r.policy===POLICY&&equal(r.scope,expected));
 return saved?{run_id:saved.id,...copy(saved.items[index])}:null;
}
function forJob(store,jobId){
 const expected=scope(store);
 for(const r of store.value.assessmentPlanRuns||[])if(r.policy===POLICY&&equal(r.scope,expected)){const index=r.items.findIndex(i=>i.job_id===jobId);if(index>=0)return{run_id:r.id,plan_id:r.plan_id,item_index:index,...copy(r.items[index])};}return null;
}
root.PhoneAssessmentRun={POLICY,scope,begin,prepareUpload,bindJobValue,onSaved,resume,process,localStep,forJob};
root.addEventListener?.('online',()=>{const store=root.PhoneLocal?.store;if(store)void resume(store).catch(()=>{});});
})(globalThis);
