/* Independent PHONE_LOCAL practice facts; not a visual session or dose ledger. */
(function(root){
'use strict';
const POLICY='phone-saved-arrangement-guided-1',UUID=/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/;
const copy=v=>structuredClone(v),canonical=v=>Array.isArray(v)?v.map(canonical):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])])):v;
const equal=(a,b)=>JSON.stringify(canonical(a))===JSON.stringify(canonical(b));
function fail(message,status=400,code='INVALID_PRACTICE',category='MISSING_INPUT'){
 const error=Error(message);error.status=status;error.reason={code,category,applies_to:'GUIDED_PRACTICE',message};throw error;
}
function exact(v,keys){if(!v||typeof v!=='object'||Array.isArray(v)||!equal(Object.keys(v).sort(),[...keys].sort()))fail('练习记录含未知或缺失字段');}
function key(v){if(typeof v!=='string'||!UUID.test(v))fail('练习编号无效');}
const stopped=p=>p.finish_payload&&(p.finish_payload.reason==='discomfort'||[p.finish_payload.feedback,...(p.practice_feedback?.operations||[]).map(r=>r.values)].some(f=>f.pain>0||f.fatigue>=5));
function createPort(store,owner,arrangement){
 const scope=()=>{
  if(store.value.owner!==owner||store.read('profile:'+owner)?.ownerId!==owner)fail('请使用原本人的手机档案',403,'OWNER_CHANGED','AUTHORIZATION');
  PhoneStore.validatePractices(store.value.practices,owner);
  return{participant_id:owner,provider:'phone-local-1',source_context:'PHONE_LOCAL:SELF_USE',policy_version:POLICY};
 };
 const find=id=>{key(id);scope();const r=(store.value.practices||[]).find(r=>r.id===id);if(!r)fail('未找到本人的这次练习记录',404,'PRACTICE_NOT_FOUND','TECHNICAL');return r;};
 async function projection(item){
  scope();const r=copy(item);r.execution_allowed=false;r.execution_reason=null;
  if(item.state==='PRACTICING'){
   const allowed=await arrangement(item.plan_ref);
   const hasStop=(store.value.practices||[]).some(p=>p.plan_ref.id===item.plan_ref.id&&stopped(p));
   r.execution_allowed=allowed.allowed===true&&!hasStop;
   r.execution_reason=hasStop?'本轮已记录不适，请先停止并核对安排。':allowed.reason||null;
  }
  return r;
 }
 async function start(value){
  exact(value,['operation_id','plan_id','plan_revision','entry_key']);key(value.operation_id);key(value.plan_id);key(value.entry_key);
  if(!Number.isInteger(value.plan_revision)||value.plan_revision<1)fail('请使用本人的已保存安排');
  const context=scope(),previous=store.value.practices||[],old=previous.find(p=>p.id===value.operation_id);
  // Reconcile a committed original BEFORE checking eligibility for new work.
  if(old){if(!equal(old.start_payload,value))fail('该练习编号已用于另一项安排',409,'PRACTICE_KEY_CONFLICT','TECHNICAL');return projection(old);}
  const ref={id:value.plan_id,revision:value.plan_revision,entry_key:value.entry_key},allowed=await arrangement(ref);
  if(!allowed.allowed)fail(allowed.reason||'本项安排暂不可执行',409,'ARRANGEMENT_NOT_ALLOWED','EXECUTION_BLOCK');
  if(previous.some(p=>p.plan_ref.id===ref.id&&stopped(p)))fail('本轮已记录不适，请先停止并核对安排。',409,'PRACTICE_STOP_RECORDED','EXECUTION_BLOCK');
  if(previous.some(p=>p.state==='PRACTICING'))fail('上次练习尚未结束，请先返回原记录。',409,'ORIGINAL_PRACTICE_OPEN','TECHNICAL');
  if(previous.length>=250)fail('练习记录空间已满，请先导出备份',507,'PRACTICE_STORAGE_FULL','TECHNICAL');
  const e=allowed.entry,item={schema_version:1,id:value.operation_id,context,state:'PRACTICING',start_payload:copy(value),created_at:new Date().toISOString(),plan_ref:ref,exercise_id:e.exercise_id,side:e.side,settings:copy(e.settings),record_origin:'GUIDED_PRACTICE',visual_session_ref:null,confirmed_count:null,formal_plan_contribution:null,finish_payload:null};
  store.change(v=>(v.practices??=[]).push(item));return projection(item);
 }
 async function finish(id,value){
  exact(value,['operation_id','count','elapsed_ms','reason','feedback']);key(value.operation_id);
  if(value.count!==null&&(!Number.isInteger(value.count)||value.count<0||value.count>10000))fail('请填写本组实际总次数，或留空');
  if(!Number.isInteger(value.elapsed_ms)||value.elapsed_ms<0||value.elapsed_ms>86400000)fail('练习页面时间无效');
  if(!['ended','completed_set','discomfort'].includes(value.reason))fail('结束方式无效');
  exact(value.feedback,['pain','fatigue']);if(Object.values(value.feedback).some(n=>n!==null&&(!Number.isInteger(n)||n<0||n>10)))fail('请填写真实感受，或留空');
  const item=find(id);
  if(item.finish_payload){if(!equal(item.finish_payload,value))fail('本次已保存，请先查看原结束记录',409,'FINISH_KEY_CONFLICT','TECHNICAL');return projection(item);}
  // Save already-ended facts even if the plan/assessment later changes. This
  // grants no further execution, visual confirmation, or formal contribution.
  const ended={...copy(item),state:'COMMITTED',ended_at:new Date().toISOString(),finish_payload:copy(value),self_reported_count:value.count,count_scope:'set_total',set_index:1,elapsed_source:'frontend_active_time_not_observed_hold',record_origin:value.count===null?'GUIDED_PRACTICE':'SELF_RECORDED'};
  ended.mode_segments=[{mode:'GUIDED',start:item.created_at,end:ended.ended_at,reason:'allowed_saved_arrangement',time_basis:'device_receipt_time',source:'GUIDED_PRACTICE',set_index:1}];
  store.change(v=>{v.practices[v.practices.findIndex(p=>p.id===id)]=ended;});return projection(ended);
 }
 function feedback(id){
  const item=find(id),f=item.practice_feedback;
  return{practice_id:id,context:copy(item.context),revision:f?.revision||0,values:copy(f?.values||{...(item.finish_payload?.feedback||{pain:null,fatigue:null}),note:null}),saved_at:f?.saved_at||null};
 }
 function feedbackOperation(id,operation){
  key(operation);const item=find(id),r=item.practice_feedback?.operations.find(r=>r.operation_id===operation);
  if(!r)fail('未找到本次感受填写的保存回执',404,'FEEDBACK_NOT_FOUND','TECHNICAL');
  return{practice_id:id,context:copy(item.context),status:'COMMITTED',...copy(r)};
 }
 function saveFeedback(id,value){
  exact(value,['operation_id','expected_revision','values']);key(value.operation_id);
  if(!Number.isInteger(value.expected_revision)||value.expected_revision<0)fail('感受记录版本无效');
  exact(value.values,['pain','fatigue','note']);const f=value.values;
  if([f.pain,f.fatigue].some(n=>n!==null&&(!Number.isInteger(n)||n<0||n>10))||f.note!==null&&(typeof f.note!=='string'||!f.note.trim()||f.note.length>500)||Object.values(f).every(v=>v===null))fail('请填写真实感受；未填写的项目保持空白');
  const item=find(id);if(item.state!=='COMMITTED')fail('先确认练习保存，再提交感受。',409,'PRACTICE_NOT_COMMITTED','TECHNICAL');
  const previous=item.practice_feedback||{revision:0,operations:[]},old=previous.operations.find(r=>r.operation_id===value.operation_id);
  if(old){if(old.expected_revision!==value.expected_revision||!equal(old.values,f))fail('填写编号已用于另一份内容。',409,'FEEDBACK_KEY_CONFLICT','TECHNICAL');return feedbackOperation(id,value.operation_id);}
  if(previous.revision!==value.expected_revision)fail('感受记录已在另一处更新，请先核对。',409,'FEEDBACK_REVISION_CONFLICT','TECHNICAL');
  if(previous.operations.length>=100)fail('本次感受修改记录空间已满；原内容保留',507,'FEEDBACK_STORAGE_FULL','TECHNICAL');
  const r={operation_id:value.operation_id,expected_revision:value.expected_revision,revision:previous.revision+1,values:copy(f),saved_at:new Date().toISOString()};
  store.change(v=>{v.practices.find(p=>p.id===id).practice_feedback={revision:r.revision,values:copy(f),saved_at:r.saved_at,operations:[...previous.operations,r]};});
  return feedbackOperation(id,value.operation_id);
 }
 // Caller uses the ORIGINAL Store.serial actor. Do not nest another actor or
 // acknowledge a failed Store.commit; all routes stay on this device/provider.
 return{context:scope,start,finish,feedback,feedbackOperation,saveFeedback,get:id=>projection(find(id)),list:async()=>{scope();return Promise.all([...(store.value.practices||[])].reverse().map(projection));}};
}
root.PhonePractice={createPort,POLICY};
if(typeof module!=='undefined')module.exports=root.PhonePractice;
})(globalThis);
