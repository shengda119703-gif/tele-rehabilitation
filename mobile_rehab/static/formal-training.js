'use strict';
// Original v2 plans are a separate authority, never relabelled /api/plan rows.
let formalPlansGeneration=0;
const formalSideLabel=side=>side==='both'?'双侧':sideLabel(side);
function formalPlanCurrent(capability,owner){
 const c=formalReadCapability();return owner===(state.uploadOwnerGeneration||0)&&c?.provider===capability.provider&&c.owner_scope===capability.owner_scope&&c.participant_id===capability.participant_id&&c.source_context===capability.source_context;
}
function formalPlanRecord(record,capability){
 if(!record||!/^v2plan-[a-f0-9]{32}$/.test(record.id)||record.schema_version!==1||record.policy_version!=='rehab-explicit-plan-1'||record.participant_id!==capability.participant_id||record.source_kind!=='LIVE_CAMERA'||record.usage_context!=='SELF_USE'||!Number.isInteger(record.revision)||record.revision<1||!['ACTIVE','ARCHIVED'].includes(record.status)||!Array.isArray(record.items)||!record.items.length)throw Error('训练安排的归属或版本暂未能核对。');
 const keys=new Set();for(const e of record.items){
  if(!capability.protocols.some(p=>p.exercise_id===e.exercise_id)||!['left','right','both'].includes(e.side)||e.key!==e.exercise_id+':'+e.side||keys.has(e.key)||!e.settings||!Number.isInteger(e.settings.target_reps)||!Number.isInteger(e.settings.target_sets)||typeof e.settings.needs_companion!=='boolean')throw Error('训练条目暂未能核对。');keys.add(e.key);
 }
 return record;
}
function formalPlanView(value,id,capability){
 const p=formalPlanRecord(value?.plan,capability),g=value.progress,s=value.actual_input_required;
 if(p.id!==id||s?.participant_id!==capability.participant_id||s.source_kind!=='LIVE_CAMERA'||s.usage_context!=='SELF_USE'||!g||typeof g.input_compatible!=='boolean'||!Number.isInteger(g.completed)||!Number.isInteger(g.total)||!Array.isArray(g.items)||!(g.blocked===null||typeof g.blocked==='string')||!(g.next_key===null||p.items.some(e=>e.key===g.next_key)))throw Error('训练进度暂未能核对。');
 return value;
}
function formalPlanEntry(value){return value.plan.items.find(e=>e.key===value.progress.next_key)||null;}
function formalPlanAllowed(value){const e=formalPlanEntry(value);return !!(e&&value.plan.status==='ACTIVE'&&value.progress.input_compatible===true&&!value.progress.blocked&&value.entry_support?.[e.key]?.supported===true);}
function formalPlanReason(value){
 const code=value.progress.blocked|| (value.plan.status==='ARCHIVED'?'explicit_plan_archived':null);
 // The original program_progress currently supplies this one exact literal.
 // This is display-only; permission always comes from the complete view above.
 return ({previous_training_feedback_required:'上一项感受尚未填写。已发生的训练仍可保存。','请先在上一项训练结果中记录疼痛和疲劳感受，再继续。':'上一项感受尚未填写。已发生的训练仍可保存。',previous_discomfort_or_fatigue_requires_review:'最近训练记录了不适，请先核对安排。',explicit_plan_archived:'这份安排已归档，已有记录仍可查看。',newer_assessment_requires_plan_review:'已有更新的评估，请先核对这份安排。',assessment_review_window_expired:'评估已超过本项复核期限，请先核对安排。',actual_input_does_not_match_plan_scope:'这份安排不适用于当前输入。',committed_observable_v2_assessment_required:'本项尚无符合要求的测量，可使用已有安排跟练。'})[code]|| (code?'本项需要核对安排，已有记录仍可查看。':!formalPlanEntry(value)?'本轮已完成。':'本项自动测量暂不可用，可查看动作说明。');
}
function formalTrainingBinding(value,entry){
 const spec=formalReadCapability()?.protocols.find(p=>p.exercise_id===entry.exercise_id);
 if(!spec)throw Error('当前环境不支持本项实时测量。');
 return {plan_name:value.plan.name,exercise_id:entry.exercise_id,side:entry.side,view:spec.view,settings:JSON.parse(JSON.stringify(entry.settings))};
}
async function readFormalPlan(id,capability){return formalPlanView(await api('/rehab/v2/plans/'+encodeURIComponent(id)),id,capability);}
function clearFormalTrainingLink(){const u=new URL(location.href);u.searchParams.delete('formal_plan');u.searchParams.delete('formal_operation');u.searchParams.delete('formal_practice');window.history.replaceState(null,'',u.href);}
function invalidateFormalPlanReads(){++formalPlansGeneration;}
function formalGuidedCapability(){const c=formalReadCapability(),g=c?.guided_practice;return g?.provider==='hosted-rehab-v2-guided-1'&&g.policy_version==='formal-arrangement-guided-1'&&g.base_path==='/rehab/v2/practice'?c:null;}
async function openFormalGuidedTraining(id,originalId=null,card=null){
 const capability=formalGuidedCapability();if(!capability||!originalId&&!formalCapability())return;
 const owner=state.uploadOwnerGeneration||0,generation=++formalPlansGeneration,pageNode=app.firstElementChild;
 const current=()=>app.firstElementChild===pageNode&&generation===formalPlansGeneration&&formalPlanCurrent(capability,owner);
 try{
  const base=capability.guided_practice.base_path,context=await api(base+'/context');if(!current())return;
  if(context.provider!=='hosted-rehab-v2-guided-1'||context.owner_scope!==capability.owner_scope||context.participant_id!==capability.participant_id||context.arrangement_source_context!==capability.source_context||context.source_context!=='GUIDED_PRACTICE:SELF_USE')throw Error('跟练的归属暂未能核对。');
  const rows=originalId?[await api(base+'/'+encodeURIComponent(originalId))]:await api(base);if(!current())return;
  const existing=originalId?rows[0]:rows.find(r=>r.plan_ref.id===id&&practiceEqual(r.context,context)&&r.state==='PRACTICING')||rows.find(r=>r.plan_ref.id===id&&practiceEqual(r.context,context)&&r.continuation&&!r.successor_id);
  if(existing){
   if(existing.plan_ref.id!==id||!practiceEqual(existing.context,context))throw Error('原跟练的归属不一致。');
   state.tab='plan';state.training={id,entry:{key:existing.plan_ref.entry_key}};state.selected=existing.exercise_id;state.side=existing.side;syncNavigation();
   await beginGuidedPractice({id,revision:existing.plan_ref.revision},{key:existing.plan_ref.entry_key,exercise_id:existing.exercise_id},existing,null,base);return;
  }
  const value=await readFormalPlan(id,capability);if(!current())return;
  if(!formalPlanAllowed(value))throw Error(formalPlanReason(value));
  const entry=formalPlanEntry(value),box=document.createElement('div');box.id='formal-guided-confirm';box.className='care-form';
  document.querySelector('#formal-guided-confirm')?.remove();(card||document.querySelector('#formal-plans')).appendChild(box);
  box.innerHTML='<form><h3>'+esc(label(entry.exercise_id))+' · '+formalSideLabel(entry.side)+'</h3><p class="caption">'+entry.settings.target_reps+' 次 × '+entry.settings.target_sets+' 组</p><label class="consent"><input id="formal-guided-adopt" type="checkbox" required><span>采用本人的这份安排，支撑已准备好，目前没有疼痛、头晕等不适。</span></label>'+(entry.settings.needs_companion?'<label class="consent"><input id="formal-guided-companion" type="checkbox" required><span>陪同者已到场</span></label>':'')+'<button class="primary">开始跟练</button></form>';
  box.querySelector('form').onsubmit=async event=>{
   event.preventDefault();if(!current()||!box.isConnected)return;const b=event.currentTarget.querySelector('button');if(b.disabled)return;b.disabled=true;
   const adopted=box.querySelector('#formal-guided-adopt').checked,confirmations={manual_arrangement_confirmed:adopted,support_ready:adopted,companion_present:box.querySelector('#formal-guided-companion')?.checked===true};
   state.tab='plan';state.training={id,entry};state.selected=entry.exercise_id;state.side=entry.side;syncNavigation();
   await beginGuidedPractice(value.plan,entry,null,confirmations,base);
  };
 }catch(error){if(current())toast(formalMessage(error));}
}
async function openFormalTraining(id,originalKey=null){
 const capability=originalKey?formalReadCapability():formalCapability();if(!capability)return;
 const owner=state.uploadOwnerGeneration||0,generation=++formalPlansGeneration,pageNode=app.firstElementChild;
 const current=()=>app.firstElementChild===pageNode&&generation===formalPlansGeneration&&formalPlanCurrent(capability,owner);
 try{
  let saved=RehabFormal.SessionAdapter.restore(localStorage,location.origin,capability,{submode:'training',plan_id:id,...(originalKey?{idempotency_key:originalKey}:{})});
  if(!originalKey&&saved?.save_state==='COMMITTED')saved=null;
  if(originalKey&&!saved)throw Error('原训练草稿暂未能读取，请返回核对。');
  let value;
  // A changed/archived plan cannot strand the ORIGINAL end operation.
  if(saved){
   if(!saved.binding||!state.catalog.some(e=>e.id===saved.binding.exercise_id)||saved.create.entry_key!==saved.binding.exercise_id+':'+saved.binding.side||saved.create.view!==saved.binding.view)throw Error('原训练动作暂未能核对，请从记录页查看。');
  }else{
   value=await readFormalPlan(id,capability);if(!current())return;
   if(!formalPlanAllowed(value))throw Error(formalPlanReason(value));
  }
  if(!current())return;
  const entry=saved?{key:saved.create.entry_key,...saved.binding}:formalPlanEntry(value);
  const binding=saved?.binding||formalTrainingBinding(value,entry);
  const training={id,revision:saved?.create.expected_plan_revision||value.plan.revision,entry,binding,saved};
  state.tab='plan';state.training=null;state.selected=binding.exercise_id;state.side=binding.side;syncNavigation();
  await formalMeasurementPage(false,saved?.create.idempotency_key||null,training);
 }catch(e){if(current())toast(formalMessage(e));}
}
function mountFormalPlans(){
 const capability=formalReadCapability();if(!capability)return;
 const owner=state.uploadOwnerGeneration||0,generation=++formalPlansGeneration,area=document.createElement('section');area.id='formal-plans';area.className='card';
 $('#plan-content').insertAdjacentElement('afterend',area);
 const current=()=>$('#formal-plans')===area&&state.tab==='plan'&&generation===formalPlansGeneration&&formalPlanCurrent(capability,owner);
 const drafts=()=>RehabFormal.SessionAdapter.drafts(localStorage,location.origin,capability).filter(d=>d.create.submode==='training'&&d.save_state!=='COMMITTED');
 const pending=()=>{const rows=drafts();if(!rows.length)return;area.insertAdjacentHTML('beforeend','<details><summary>训练待核对 · '+rows.length+'</summary>'+rows.map(d=>'<button class="record" data-formal-training-pending="'+esc(d.create.idempotency_key)+'"><span>'+esc(label(d.binding?.exercise_id||d.create.entry_key))+'</span><span>核对 ›</span></button>').join('')+'</details>');area.querySelectorAll('[data-formal-training-pending]').forEach(b=>b.onclick=()=>{const d=rows.find(r=>r.create.idempotency_key===b.dataset.formalTrainingPending);if(d)void openFormalTraining(d.create.plan_id,d.create.idempotency_key);});};
 area.innerHTML='<h2>实时训练安排</h2><p role="status">正在读取…</p>';pending();
 // Plan, report and legacy arrangement reads have independent subscriptions.
 void (async()=>{
  try{
   const data=await api('/rehab/v2/plans');if(!current())return;
   if(data.policy_version!=='rehab-explicit-plan-1'||!Array.isArray(data.items))throw Error('训练安排暂未能核对。');
   const records=data.items.filter(p=>p.participant_id===capability.participant_id&&p.source_kind==='LIVE_CAMERA'&&p.usage_context==='SELF_USE').map(p=>formalPlanRecord(p,capability));
   area.innerHTML='<h2>实时训练安排</h2>'+(records.length?'':'<p class="caption">尚无实时训练安排，可继续使用已有安排。</p>');pending();
   for(const record of records){const card=document.createElement('div');card.className='plan-item';card.dataset.formalPlan=record.id;card.innerHTML='<strong>'+esc(record.name)+'</strong><p role="status">正在核对本轮进度…</p>';area.appendChild(card);void load(card,record.id);}
  }catch(e){if(current()){area.innerHTML='<h2>实时训练安排</h2><p>暂时未能读取</p><button class="secondary" id="formal-plans-retry">重试</button>';pending();$('#formal-plans-retry').onclick=()=>{area.remove();mountFormalPlans();};}}
 })();
 async function load(card,id){
  try{const value=await readFormalPlan(id,capability);if(!current()||!card.isConnected)return;const p=value.plan,g=value.progress,e=formalPlanEntry(value);
   card.innerHTML='<strong>'+esc(p.name)+'</strong><p class="caption">'+g.completed+' / '+g.total+' 项 · 实时测量记录</p><details><summary>训练清单</summary>'+p.items.map(i=>'<p>'+esc(label(i.exercise_id))+' · '+formalSideLabel(i.side)+' · '+i.settings.target_reps+' 次 × '+i.settings.target_sets+' 组</p>').join('')+'</details>'+(e?'<p>'+esc(label(e.exercise_id))+' · '+formalSideLabel(e.side)+'</p>':'')+(formalPlanAllowed(value)&&formalCapability()?'<button class="primary" data-formal-train>开始实时训练</button>':'<p class="caption">'+esc(formalPlanReason(value))+'</p>');
   const b=card.querySelector('[data-formal-train]');if(b)b.onclick=()=>openFormalTraining(id);
   if(formalGuidedCapability()&&formalCapability()){
    const guided=document.createElement('button');guided.className='secondary';guided.dataset.formalGuided=id;guided.textContent='使用已有安排跟练';guided.onclick=()=>openFormalGuidedTraining(id,null,card);card.appendChild(guided);
   }
   const previous=g.blocked&&g.items.slice().reverse().find(i=>typeof i.session_id==='string'&&i.session_id);
   if(previous){const back=document.createElement('button');back.className='secondary';back.textContent='查看上一项记录';back.onclick=()=>showFormalRecord(previous.session_id);card.appendChild(back);}
  }catch(e){if(current()&&card.isConnected){card.innerHTML='<p>本轮进度暂未能读取</p><button class="secondary">重试</button>';card.querySelector('button').onclick=()=>load(card,id);}}
 }
 const u=new URL(location.href),id=u.searchParams.get('formal_plan'),key=u.searchParams.get('formal_operation');
 const practice=u.searchParams.get('formal_practice');if(id&&practice&&formalGuidedCapability()){void openFormalGuidedTraining(id,practice);return;}
 if(id&&key){const saved=RehabFormal.SessionAdapter.restore(localStorage,location.origin,capability,{submode:'training',plan_id:id,idempotency_key:key});if(saved)void openFormalTraining(id,key);else clearFormalTrainingLink();}
}
