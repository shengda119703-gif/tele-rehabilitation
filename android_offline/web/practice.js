/* Independent PHONE_LOCAL practice facts; not a visual session or dose ledger. */
(function(root){
'use strict';
const POLICY='phone-saved-arrangement-guided-1',UUID=/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/;
const MANUAL_POLICY='phone-explicit-manual-practice-1',START_FIELDS=['operation_id','plan_id','plan_revision','entry_key'],MANUAL_FIELDS=['manual_arrangement_confirmed','support_ready','companion_present'];
const copy=v=>structuredClone(v),canonical=v=>Array.isArray(v)?v.map(canonical):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])])):v;
const equal=(a,b)=>JSON.stringify(canonical(a))===JSON.stringify(canonical(b));
function fail(message,status=400,code='INVALID_PRACTICE',category='MISSING_INPUT'){
 const error=Error(message);error.status=status;error.reason={code,category,applies_to:'GUIDED_PRACTICE',message};throw error;
}
function exact(v,keys){if(!v||typeof v!=='object'||Array.isArray(v)||!equal(Object.keys(v).sort(),[...keys].sort()))fail('练习记录含未知或缺失字段');}
function key(v){if(typeof v!=='string'||!UUID.test(v))fail('练习编号无效');}
const stopped=p=>p.finish_payload&&(p.finish_payload.reason==='discomfort'||[p.finish_payload.feedback,...(p.practice_feedback?.operations||[]).map(r=>r.values)].some(f=>f.pain>0||f.fatigue>=5));
function createPort(store,owner,arrangement,manualCatalog=async()=>({rehab:[]})){
 const scope=()=>{
  if(store.value.owner!==owner||store.read('profile:'+owner)?.ownerId!==owner)fail('请使用原本人的手机档案',403,'OWNER_CHANGED','AUTHORIZATION');
  PhoneStore.validatePractices(store.value.practices,owner);
  PhoneStore.validateManualArrangements(store.value.manualArrangements,owner);
  return{participant_id:owner,provider:'phone-local-1',source_context:'PHONE_LOCAL:SELF_USE',policy_version:POLICY};
 };
 const find=id=>{key(id);scope();const r=(store.value.practices||[]).find(r=>r.id===id);if(!r)fail('未找到本人的这次练习记录',404,'PRACTICE_NOT_FOUND','TECHNICAL');return r;};
 const relatedStop=(p,ref,entry)=>stopped(p)&&(p.plan_ref.id===ref.id||p.exercise_id===entry.exercise_id&&p.side===entry.side);
 async function saveArrangement(value){
  exact(value,['operation_id','name','exercise_id','side','settings']);key(value.operation_id);const context=scope();
  const old=(store.value.manualArrangements||[]).find(r=>r.id===value.operation_id);
  if(old){if(!equal(old.original_payload,value))fail('此保存编号已用于另一份安排',409,'MANUAL_KEY_CONFLICT','TECHNICAL');return copy(old);}
  const spec=(await manualCatalog()).rehab.find(s=>s.id===value.exercise_id);scope();
  if(!spec)fail('请使用当前康复动作库中的项目');
  const item={schema_version:1,id:value.operation_id,revision:1,context,created_at:new Date().toISOString(),name:value.name,record_origin:'manual_saved',measurement_version:null,assessment_ref:null,original_payload:copy(value),items:[{key:value.operation_id,exercise_id:value.exercise_id,side:value.side,measurement_contract:spec.measurement_contract,settings:copy(value.settings)}]};
  PhoneStore.validateManualArrangements([item],owner);
  if((store.value.manualArrangements||[]).length>=250)fail('已有安排空间已满，请先导出备份',507,'MANUAL_STORAGE_FULL','TECHNICAL');
  store.change(v=>(v.manualArrangements??=[]).push(item));return copy(item);
 }
 async function manualDecision(ref,confirmations={}){
  scope();const r=(store.value.manualArrangements||[]).find(r=>r.id===ref.id),entry=r?.items.find(e=>e.key===ref.entry_key),required=entry?.settings.needs_companion===true;
  const denied=(code,message,category='EXECUTION_BLOCK')=>({allowed:false,code,category,applies_to:'GUIDED_PRACTICE',message,reason:message,policy_version:MANUAL_POLICY,companion_required:required});
  if(!r||r.revision!==ref.revision||!entry)return denied('MANUAL_ARRANGEMENT_CHANGED','原安排已变化，可以结束并保存已发生的练习。');
  const spec=(await manualCatalog()).rehab.find(s=>s.id===entry.exercise_id);scope();
  if(!spec||spec.measurement_contract!==entry.measurement_contract)return denied('MANUAL_DEFINITION_CHANGED','本项动作定义需要重新核对。');
  if((store.value.practices||[]).some(p=>relatedStop(p,ref,entry)))return denied('PRACTICE_STOP_RECORDED','本项已记录不适，请先停止并核对安排。');
  const latest=store.value.jobs.filter(j=>j.mode==='training'&&j.state==='done'&&j.exercise===entry.exercise_id&&j.side===entry.side).sort((a,b)=>Date.parse(b.created_at)-Date.parse(a.created_at))[0];
  if(latest&&(latest.feedback?.pain>0||latest.feedback?.fatigue>=5))return denied('TRAINING_STOP_RECORDED','最近训练记录了不适，请先核对安排。');
  if(confirmations.manual_arrangement_confirmed!==true)return denied('MANUAL_CONFIRMATION_REQUIRED','请确认采用本人的这份已有安排。','MISSING_INPUT');
  if(confirmations.support_ready!==true)return denied('SUPPORT_CONFIRMATION_REQUIRED','请按原安排准备好支撑。','MISSING_INPUT');
  if(required&&confirmations.companion_present!==true)return denied('COMPANION_REQUIRED','本项安排需要陪同者在场。','MISSING_INPUT');
  return{allowed:true,code:'EXPLICIT_MANUAL_PRACTICE_ALLOWED',category:null,applies_to:'GUIDED_PRACTICE',message:null,reason:null,policy_version:MANUAL_POLICY,companion_required:required,formal_measurement_allowed:null,entry:copy(entry)};
 }
 async function arrangements(){scope();const result=[];for(const r of store.value.manualArrangements||[]){const entries=[];for(const e of r.items){const decision=await manualDecision({id:r.id,revision:r.revision,entry_key:e.key});const {entry,...publicDecision}=decision;entries.push({...copy(e),decision:publicDecision});}result.push({id:r.id,revision:r.revision,name:r.name,record_origin:r.record_origin,items:entries});}return result.reverse();}
 async function projection(item){
  scope();const r=copy(item);r.execution_allowed=false;r.execution_reason=null;
  if(item.state==='PRACTICING'){
   let allowed=item.guidance_policy===MANUAL_POLICY?await manualDecision(item.plan_ref,item.start_payload):await arrangement(item.plan_ref);
   if(item.guidance_policy===MANUAL_POLICY&&allowed.allowed&&(!equal(item.settings,allowed.entry.settings)||item.exercise_id!==allowed.entry.exercise_id||item.side!==allowed.entry.side))allowed={...allowed,allowed:false,code:'MANUAL_SNAPSHOT_CHANGED',category:'EXECUTION_BLOCK',message:'原安排与本次记录需要重新核对。',reason:'原安排与本次记录需要重新核对。'};
   const hasStop=(store.value.practices||[]).some(p=>relatedStop(p,item.plan_ref,item));
   r.execution_allowed=allowed.allowed===true&&!hasStop;
   r.execution_reason=hasStop?'本轮已记录不适，请先停止并核对安排。':allowed.reason||null;
   if(item.guidance_policy===MANUAL_POLICY){const {entry,...decision}=allowed;r.execution_decision=decision;}
  }
  return r;
 }
 async function start(value){
  const manual=value&&typeof value==='object'&&!Array.isArray(value)&&MANUAL_FIELDS.some(k=>k in value);
  exact(value,manual?[...START_FIELDS,...MANUAL_FIELDS]:START_FIELDS);key(value.operation_id);key(value.plan_id);key(value.entry_key);
  if(manual&&MANUAL_FIELDS.some(k=>typeof value[k]!=='boolean'))fail('请明确确认已有安排、支撑与陪同情况');
  if(!Number.isInteger(value.plan_revision)||value.plan_revision<1)fail('请使用本人的已保存安排');
  const context=scope(),previous=store.value.practices||[],old=previous.find(p=>p.id===value.operation_id);
  // Reconcile a committed original BEFORE checking eligibility for new work.
  if(old){if(!equal(old.start_payload,value))fail('该练习编号已用于另一项安排',409,'PRACTICE_KEY_CONFLICT','TECHNICAL');return projection(old);}
  const ref={id:value.plan_id,revision:value.plan_revision,entry_key:value.entry_key},allowed=manual?await manualDecision(ref,value):await arrangement(ref);
  if(!allowed.allowed)fail(allowed.reason||'本项安排暂不可执行',409,allowed.code||'ARRANGEMENT_NOT_ALLOWED',allowed.category||'EXECUTION_BLOCK');
  if(previous.some(p=>relatedStop(p,ref,allowed.entry)))fail('本轮已记录不适，请先停止并核对安排。',409,'PRACTICE_STOP_RECORDED','EXECUTION_BLOCK');
  if(previous.some(p=>p.state==='PRACTICING'))fail('上次练习尚未结束，请先返回原记录。',409,'ORIGINAL_PRACTICE_OPEN','TECHNICAL');
  if(previous.length>=250)fail('练习记录空间已满，请先导出备份',507,'PRACTICE_STORAGE_FULL','TECHNICAL');
  const e=allowed.entry,item={schema_version:1,id:value.operation_id,context,state:'PRACTICING',start_payload:copy(value),created_at:new Date().toISOString(),plan_ref:ref,exercise_id:e.exercise_id,side:e.side,settings:copy(e.settings),record_origin:'GUIDED_PRACTICE',visual_session_ref:null,confirmed_count:null,formal_plan_contribution:null,finish_payload:null};
  if(manual){const {entry,...decision}=allowed;Object.assign(item,{guidance_policy:MANUAL_POLICY,arrangement_ref:{...copy(ref),kind:'MANUAL_SAVED'},formal_plan_ref:null,assessment_ref:null,execution_grant:decision});}
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
  ended.mode_segments=[{mode:'GUIDED',start:item.created_at,end:ended.ended_at,reason:item.guidance_policy===MANUAL_POLICY?'explicit_saved_manual_arrangement':'allowed_saved_arrangement',time_basis:'device_receipt_time',source:'GUIDED_PRACTICE',set_index:1}];
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
 return{context:scope,start,finish,feedback,feedbackOperation,saveFeedback,arrangements,saveArrangement,get:id=>projection(find(id)),list:async()=>{scope();return Promise.all([...(store.value.practices||[])].reverse().map(projection));}};
}
root.PhonePractice={createPort,POLICY,MANUAL_POLICY};
if(typeof module!=='undefined')module.exports=root.PhonePractice;
})(globalThis);
