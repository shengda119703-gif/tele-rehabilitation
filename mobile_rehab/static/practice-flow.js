'use strict';
// A practice journey is not the /live preview and never completes a formal
// plan. The owning backend grants the saved arrangement and commits its record.
let practiceJourney=null,practiceGeneration=0,practiceClock;
const practiceCanonical=v=>Array.isArray(v)?v.map(practiceCanonical):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,practiceCanonical(v[k])])):v;
const practiceEqual=(a,b)=>JSON.stringify(practiceCanonical(a))===JSON.stringify(practiceCanonical(b));
const practiceSideLabel=side=>side==='both'?'双侧':sideLabel(side);
// Routing comes from a validated runtime binding, not from a lost request or
// a guess that two authorities have equivalent plans/records.
const practiceBase=j=>j.context.provider==='hosted-rehab-v2-guided-1'?'/rehab/v2/practice':'/practice';
const practiceDraftKey=c=>'ankang-practice-draft-1:'+JSON.stringify([location.origin,c.provider,c.source_context,c.participant_id]);
const practiceRecordDraftKey=(c,id)=>practiceDraftKey(c)+':'+id;
function updateFormalPracticeLink(j){
 if(j.context.provider!=='hosted-rehab-v2-guided-1')return;
 const u=new URL(location.href);u.searchParams.set('formal_plan',j.start.plan_id);u.searchParams.set('formal_practice',j.start.operation_id);u.searchParams.delete('formal_operation');window.history.replaceState(null,'',u.href);
}
function persistPractice(j){
 try{const text=JSON.stringify({version:1,context:j.context,start:j.start,startRejected:j.startRejected===true,finish:j.finish||null,elapsed:j.elapsed,ended:j.ended,committed:j.receipt?.state==='COMMITTED',countDraft:j.countDraft||'',feedbackDraft:j.feedbackDraft||null,feedbackPending:j.feedbackPending||null,feedbackSuperseded:j.feedbackSuperseded||[],observationSegments:j.observationSegments||[],sequenceStage:j.sequenceStage||null,nextPending:j.nextPending||null,closePending:j.closePending||null,sequenceEndRequested:j.sequenceEndRequested===true});localStorage.setItem(practiceRecordDraftKey(j.context,j.start.operation_id),text);j.draftSaved=true;try{localStorage.setItem(practiceDraftKey(j.context),text);}catch{/* The individually scoped draft remains recoverable from its history entry. */}}
 catch{j.draftSaved=false;}
}
function pausePractice(){
 const j=practiceJourney;if(!j)return;clearInterval(practiceClock);
 clearInterval(practiceRestClock);
 if(typeof stopPracticeObservation==='function')stopPracticeObservation(j);
 if(j.running){const dt=performance.now()-j.tick;if(dt>=0&&dt<1500)j.elapsed+=dt;j.running=false;}
 persistPractice(j);if($('#practice-pause'))$('#practice-pause').textContent='继续';
}
function invalidatePracticeScope(){pausePractice();practiceJourney=null;++practiceGeneration;}
function currentPractice(j,area){return practiceJourney===j&&j.ownerGeneration===(state.uploadOwnerGeneration||0)&&$('#practice-area')===area;}
function startPracticeClock(j){
 if(j.ended||j.running||document.hidden||j.receipt?.execution_allowed!==true)return;j.running=true;j.tick=performance.now();
 clearInterval(practiceClock);practiceClock=setInterval(()=>{
  const now=performance.now(),dt=now-j.tick;j.tick=now;
  // Long timer gaps are unknown, never counted as exercise or a valid hold.
  if(dt<1500)j.elapsed+=Math.max(0,dt);
  if($('#practice-time'))$('#practice-time').textContent=Math.floor(j.elapsed/1000)+' 秒 · 跟练页面时间';
  persistPractice(j);
 },1000);
 if($('#practice-pause'))$('#practice-pause').textContent='暂停';
}
function originalPracticeSequence(rows,record,context){
 const owned=rows.filter(r=>practiceEqual(r.context,context)&&r.plan_ref?.id===record.id&&r.plan_ref.revision===record.revision);
 // A pending parent retains the user's end/create intent ahead of its child.
 const pending=owned.find(r=>{try{const d=JSON.parse(localStorage.getItem(practiceRecordDraftKey(context,r.id))||'null');return d?.start?.operation_id===r.id&&practiceEqual(d.context,context)&&(d.nextPending||d.sequenceEndRequested);}catch{return false;}});
 return pending||owned.find(r=>r.state==='PRACTICING')||owned.find(r=>r.schema_version>=2&&r.continuation&&!r.successor_id)||null;
}
async function beginGuidedPractice(record,entry,resume=null,confirmations=null,runtimePath='/practice'){
 pausePractice();const generation=++practiceGeneration,ownerGeneration=state.uploadOwnerGeneration||0;
 // The retained capture router is query-based. Entering from an assessment
 // result must not send a reload back to the assessment library: the existing
 // plan entry is where the owner-bound original practice draft is reconciled.
 const returnUrl=new URL(location.href,location.origin);returnUrl.searchParams.set('tab',resume?.state==='COMMITTED'?'history':'plan');window.history.replaceState(null,'',returnUrl.href);
 app.innerHTML='<div class="page-head"><h1>'+esc(label(entry.exercise_id))+'</h1></div><div class="card" id="practice-area"><p role="status">正在核对本项安排…</p></div>';
 const area=$('#practice-area');
 try{
  const context=await api(runtimePath+'/context');if(generation!==practiceGeneration||$('#practice-area')!==area||ownerGeneration!==(state.uploadOwnerGeneration||0))return;
  if(runtimePath==='/rehab/v2/practice'){
   const cap=formalReadCapability();if(context.provider!=='hosted-rehab-v2-guided-1'||context.policy_version!=='formal-arrangement-guided-1'||context.owner_scope!==cap?.owner_scope||context.participant_id!==cap.participant_id||context.source_context!=='GUIDED_PRACTICE:SELF_USE'||context.arrangement_source_context!==cap.source_context)throw Error('本次跟练的归属暂未能核对。');
  }else if(context.provider==='hosted-rehab-v2-guided-1')throw Error('本次跟练的运行环境不一致。');
  if(!resume&&!confirmations){
   const rows=await api(runtimePath);if(generation!==practiceGeneration||$('#practice-area')!==area||ownerGeneration!==(state.uploadOwnerGeneration||0))return;
   if(!Array.isArray(rows))throw Error('练习记录暂未能核对，请返回后重试。');
   resume=originalPracticeSequence(rows,record,context);
   if(resume)entry={key:resume.plan_ref.entry_key,exercise_id:resume.exercise_id};
  }
  let saved;try{saved=JSON.parse((resume&&localStorage.getItem(practiceRecordDraftKey(context,resume.id)))||localStorage.getItem(practiceDraftKey(context))||'null');}catch{/* Keep the current page available when draft storage is unavailable. */}
  if(!saved&&practiceJourney&&practiceEqual(practiceJourney.context,context))saved={...practiceJourney,version:1};
  const compatible=saved?.version===1&&practiceEqual(saved.context,context)&&typeof saved.start?.operation_id==='string'&&saved.start.plan_id===record.id&&saved.start.entry_key===entry.key&&(resume?saved.start.operation_id===resume.id:!saved.committed&&!saved.startRejected);
  const j={context,ownerGeneration,start:resume?.start_payload||(compatible?saved.start:{operation_id:newUploadOperation(),plan_id:record.id,plan_revision:record.revision,entry_key:entry.key,...(confirmations||{})}),finish:resume?.finish_payload||(compatible?saved.finish:null),elapsed:compatible&&Number.isFinite(saved.elapsed)?Math.max(0,saved.elapsed):(resume?.finish_payload?.elapsed_ms||0),countDraft:compatible?saved.countDraft||'':'',ended:resume?.state==='COMMITTED'||compatible&&saved.ended===true,running:false,busy:false,receipt:null};
  j.previewGeneration=0;
  j.initialRestorePaused=!!resume||compatible;
  if(compatible){j.feedbackDraft=saved.feedbackDraft||null;j.feedbackPending=saved.feedbackPending||null;j.feedbackSuperseded=saved.feedbackSuperseded||[];j.observationSegments=Array.isArray(saved.observationSegments)?saved.observationSegments:[];j.sequenceStage=saved.sequenceStage;j.nextPending=saved.nextPending||null;j.closePending=saved.closePending||null;j.sequenceEndRequested=saved.sequenceEndRequested===true;}
  practiceJourney=j;persistPractice(j);updateFormalPracticeLink(j);await reconcilePractice(j,area,true);
 }catch(e){if($('#practice-area')===area&&ownerGeneration===(state.uploadOwnerGeneration||0)){area.innerHTML='<p>'+esc(e.message)+'</p><button class="secondary" id="practice-back">返回训练安排</button>';$('#practice-back').onclick=()=>navigate('plan');}}
}
async function reconcilePractice(j,area,mayCreate=false){
 if(j.busy)return;j.busy=true;
 let creating=false;
 try{
  let receipt;try{receipt=await api(practiceBase(j)+'/'+j.start.operation_id);}catch(e){if(e.status!==404||!mayCreate)throw e;if(!currentPractice(j,area))return;creating=true;receipt=await api(practiceBase(j),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(j.start)});}
  if(!currentPractice(j,area))return;
  if(j.receipt?.state==='COMMITTED'&&receipt.state!=='COMMITTED')return;
  if(receipt.id!==j.start.operation_id||!practiceEqual(receipt.context,j.context))throw Error('练习记录的归属不一致，请返回核对。');
  j.receipt=receipt;
  if(receipt.execution_allowed!==true)pausePractice();
  if(receipt.state==='COMMITTED'){j.ended=true;j.finish=receipt.finish_payload;persistPractice(j);}
  drawPractice(j,area);
  if(j.nextPending||j.sequenceEndRequested){void reconcilePracticeSequence(j,area,true);return;}
  if(j.ended&&receipt.state!=='COMMITTED'&&j.finish)await submitPracticeFinish(j,area);
  else if(!j.ended){if(j.initialRestorePaused){j.initialRestorePaused=false;persistPractice(j);return;}startPracticeClock(j);if(typeof resumePracticeObservation==='function')void resumePracticeObservation(j,area);}
 }catch(e){
  if(creating&&!j.receipt&&e.status===409&&['MISSING_INPUT','EXECUTION_BLOCK'].includes(e.reason?.category)){j.startRejected=true;persistPractice(j);}
  if(currentPractice(j,area)&&$('#practice-count')&&j.receipt){
   // A failed lookup is local to reconciliation. Keep the existing form,
   // media node and input; it grants no new execution or successful save.
   $('#practice-save').textContent='暂时未能核对原记录，当前内容保持。'+(j.draftSaved?'草稿已保留。':'记录仍在当前页面。');
   return;
  }
  if(currentPractice(j,area)){area.innerHTML='<p>'+esc(e.message)+'</p><p class="caption">'+(j.draftSaved?'草稿已保留在本机。':'记录仍在当前页面，本机恢复草稿未写入。')+'</p><button class="secondary" id="practice-reconcile">核对原练习</button><button class="secondary" id="practice-back">返回训练安排</button>';$('#practice-reconcile').onclick=()=>reconcilePractice(j,area,true);$('#practice-back').onclick=()=>navigate('plan');}
 }finally{j.busy=false;}
}
function drawPractice(j,area){
 clearInterval(practiceRestClock);
 if(j.receipt?.state==='COMMITTED'&&(j.sequenceStage==='REST'||j.nextPending||j.sequenceEndRequested))return drawPracticeRest(j,area);
 const retainedObservation=!j.ended?$('#practice-observation'):null;
 const r=j.receipt,ex=state.catalog.find(x=>x.id===r.exercise_id),i=ex?.instructions||{},done=r.state==='COMMITTED';
 const heading=typeof app!=='undefined'?app.querySelector?.('.page-head h1'):null;if(heading)heading.textContent=label(r.exercise_id);
 const savedLabel=j.context.provider==='phone-local-1'?'练习记录已保存在本机':'练习记录已保存';
 // Eligibility reconciliation does not remount an active preview/video.
 if(retainedObservation&&$('#practice-count')){
  $('#practice-pause').disabled=r.execution_allowed!==true;
  $('#practice-save').textContent=r.execution_allowed===true?(j.draftSaved?'已进入跟练，草稿已保留':'已进入跟练；本机草稿未写入，结束时将向原服务保存'):(r.execution_reason||'安排暂不可继续；可以结束并保存本次记录。');
  return;
 }
 area.innerHTML=`<div class="section-head"><h2>${esc(label(r.exercise_id))} · ${practiceSideLabel(r.side)}</h2></div><p class="caption">本组安排 ${r.settings.target_reps} 次 · 按原安排练习</p>${!j.ended?['start','move','return'].map((k,n)=>`<div class="instruction"><span class="number">${n+1}</span><p>${esc(i[k])}</p></div>`).join(''):''}<p id="practice-time" class="caption">${Math.floor(j.elapsed/1000)} 秒 · 跟练页面时间</p><p id="practice-save" role="status">${done?savedLabel:j.ended?'本次已结束，正在确认保存':j.draftSaved?'已进入跟练，草稿已保留':'已进入跟练；本机草稿未写入，结束时将向原服务保存'}</p>${!j.ended?'<label class="consent">本组总次数（选填）<input id="practice-count" type="number" min="0" max="10000" step="1" placeholder="本人记录"></label><div class="live-controls"><button class="primary" id="practice-pause">继续</button><button class="danger" id="practice-end">结束本组</button></div>':`<p class="result-note">${done&&r.self_reported_count!==null?'本组 '+esc(r.self_reported_count)+' 次 · 本人记录':'本次未填写执行次数。'}${done?' 未计入自动确认或正式计划进度。':''}</p><button class="secondary" id="practice-reconcile">${done?'查看原保存记录':'核对保存状态'}</button>`}<button class="secondary file-actions" id="practice-back">返回训练安排</button><p class="tip">有疼痛、头晕或不适时立即停止。跟练时间不是有效保持时间。</p>`;
 $('#practice-back').onclick=()=>{pausePractice();navigate('plan');};
  if($('#practice-count')){$('#practice-count').value=j.countDraft||'';$('#practice-count').oninput=e=>{j.countDraft=e.target.value;persistPractice(j);};}
 if($('#practice-reconcile'))$('#practice-reconcile').onclick=()=>reconcilePractice(j,area);
 if(!j.ended&&r.execution_allowed!==true){$('#practice-save').textContent=r.execution_reason||'安排暂不可继续；可以结束并保存本次记录。';$('#practice-pause').disabled=true;}
 if($('#practice-pause'))$('#practice-pause').onclick=()=>j.running?pausePractice():reconcilePractice(j,area);
 const endGroup=reason=>{
  if(j.ended)return;const raw=$('#practice-count').value,count=raw===''?null:Number(raw);
  if(count!==null&&(!Number.isInteger(count)||count<0||count>10000)){toast('请填写本组实际总次数，或留空');return;}
  pausePractice();j.ended=true;j.finish={operation_id:newUploadOperation(),count,elapsed_ms:Math.min(86400000,Math.round(j.elapsed)),reason,feedback:{pain:null,fatigue:null}};
  persistPractice(j);drawPractice(j,area);void submitPracticeFinish(j,area);
 };
 if($('#practice-end'))$('#practice-end').onclick=()=>endGroup('ended');
 // Only an authority supporting the sequence contract offers group completion.
 // Older phone records and their packaged frontend retain the existing path.
 if(!j.ended&&r.schema_version>=2&&r.sequence_policy){const complete=document.createElement('button');complete.id='practice-complete-set';complete.className='secondary';complete.textContent='本组已完成';complete.onclick=()=>endGroup('completed_set');$('#practice-end').parentNode.appendChild(complete);}
 if(done&&r.continuation&&automaticUploadReconciliation){const next=document.createElement('button');next.id='practice-next';next.className='primary';next.textContent=r.continuation.kind==='next_action'?'下一动作':'继续下一组';next.onclick=()=>openPracticeRest(j,area);area.appendChild(next);}
 if(!j.ended&&typeof mountPracticeObservation==='function')mountPracticeObservation(j,area,retainedObservation);
 if(j.ended&&typeof mountPracticeFeedback==='function')mountPracticeFeedback(j,area);
}
async function submitPracticeFinish(j,area){
 if(j.finishRequest||j.ownerGeneration!==(state.uploadOwnerGeneration||0))return;j.finishRequest=true;
 try{
  const r=await api(practiceBase(j)+'/'+j.start.operation_id+'/finish',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(j.finish)});
  if(!currentPractice(j,area))return;
  if(r.state!=='COMMITTED'||r.id!==j.start.operation_id||!practiceEqual(r.finish_payload,j.finish))throw Error('结束回执尚未确认，请核对原记录。');
  j.receipt=r;persistPractice(j);drawPractice(j,area);
 }catch(e){if(currentPractice(j,area))$('#practice-save').textContent='本次已结束，保存待核对。'+(j.draftSaved?'草稿已保留。':'记录仍在当前页面。');}
 finally{j.finishRequest=false;}
}
async function mountPracticeHistory(runtimePath='/practice'){
 if(!state.practiceRecording)return;const area=document.createElement('section');area.className='card';area.id='practice-records';app.appendChild(area);
 if(runtimePath==='/rehab/v2/practice')area.id='formal-practice-records';
 const current=()=>document.querySelector('#'+area.id)===area&&ownerGeneration===(state.uploadOwnerGeneration||0);
 area.innerHTML='<p role="status">正在读取跟练记录…</p>';const ownerGeneration=state.uploadOwnerGeneration||0;
 try{const rows=await api(runtimePath);if(!current())return;
  const empty=$('#records')?.querySelector?.('.empty');if(rows.length&&empty){const title=empty.querySelector('h3'),text=empty.querySelector('p');if(title)title.textContent='暂无录像分析记录';if(text)text.textContent='跟练记录在下方查看。';}
  area.innerHTML='<h2>'+(runtimePath==='/rehab/v2/practice'?'实时安排跟练记录':'跟练记录')+'</h2>'+rows.map(r=>`<button class="record" data-practice="${esc(r.id)}"><span><strong>${esc(label(r.exercise_id))} · ${sideLabel(r.side)}${r.schema_version>=2?' · 第'+esc(r.set_index)+'组':''}</strong><small>${dateLabel(r.ended_at||r.created_at)} · ${r.state==='COMMITTED'?(r.self_reported_count===null?'未填写次数':esc(r.self_reported_count)+' 次 · 本人记录'):'尚未结束'}</small></span><span class="badge">${r.state==='COMMITTED'?'已保存':'继续'} ›</span></button>`).join('');
  area.querySelectorAll('[data-practice]').forEach(b=>b.onclick=()=>{const r=rows.find(x=>x.id===b.dataset.practice);state.tab='assess';state.training={id:r.plan_ref.id,entry:{key:r.plan_ref.entry_key}};state.selected=r.exercise_id;state.side=r.side;beginGuidedPractice({id:r.plan_ref.id,revision:r.plan_ref.revision},{key:r.plan_ref.entry_key,exercise_id:r.exercise_id},r,null,runtimePath);});
 }catch(e){if(current()){area.innerHTML='<p>跟练记录暂时未能读取</p><button class="secondary">重试</button>';area.querySelector('button').onclick=()=>{area.remove();mountPracticeHistory(runtimePath);};}}
}
// A separate navigation clock never contributes practice/holding time. The
// owning storage still checks rest and eligibility when a successor is written.
let practiceRestClock;
async function openPracticeRest(j,area){
 if(!currentPractice(j,area)||j.sequenceBusy)return;
 const epoch=j.sequenceReadEpoch=(j.sequenceReadEpoch||0)+1;
 pausePractice();j.sequenceStage='REST';persistPractice(j);drawPracticeRest(j,area);
 try{const r=await api(practiceBase(j)+'/'+j.start.operation_id);if(!currentPractice(j,area)||j.sequenceReadEpoch!==epoch||j.sequenceEndRequested)return;if(r.id!==j.start.operation_id||!practiceEqual(r.context,j.context))throw Error('原记录归属不一致');j.receipt=r;j.restReceiptAt=performance.now();persistPractice(j);drawPracticeRest(j,area);}
 catch{if(currentPractice(j,area))$('#practice-sequence-status').textContent='原记录暂未能核对，可以稍后再试。';}
}
function drawPracticeRest(j,area){
 clearInterval(practiceRestClock);
 const f=j.receipt.continuation,e=f?.entry,ending=j.sequenceEndRequested===true;
 const heading=typeof app!=='undefined'?app.querySelector?.('.page-head h1'):null;if(heading&&e)heading.textContent=label(e.exercise_id);
 const needsSupport=f?.kind==='next_action',required=f?.decision?.companion_required===true;
 j.restReceiptAt??=performance.now();
 area.innerHTML=`<h2>${ending?'正在结束本次跟练':e?esc(label(e.exercise_id))+' · '+sideLabel(e.side):'核对下一组记录'}</h2><p class="caption">${e?'接下来第 '+esc(f.set_index)+' 组 · '+esc(e.settings.target_reps)+' 次':'原组记录保持不变'}</p><p id="practice-rest-time" role="status"></p>${needsSupport&&!ending?'<label class="consent"><input id="practice-next-support" type="checkbox"><span>已按本项安排准备好支撑</span></label>'+(required?'<label class="consent"><input id="practice-next-companion" type="checkbox"><span>陪同者已到场</span></label>':''):''}<p id="practice-sequence-status" role="status">${esc(j.sequenceMessage||'本组记录已保存。')}</p><div class="live-controls"><button class="primary" id="practice-sequence-start">${ending?'核对结束':j.nextPending||f?.successor_id?'核对记录':needsSupport?'下一动作':'下一组'}</button><button class="danger" id="practice-sequence-end">结束跟练</button></div><button class="secondary file-actions" id="practice-back">返回训练安排</button>`;
 const start=$('#practice-sequence-start'),support=$('#practice-next-support'),companion=$('#practice-next-companion');
 if(support){support.checked=j.nextSupport===true;support.disabled=!!j.nextPending;support.onchange=()=>{j.nextSupport=support.checked;update();};}
 if(companion){companion.checked=j.nextCompanion===true;companion.disabled=!!j.nextPending;companion.onchange=()=>{j.nextCompanion=companion.checked;update();};}
 const update=()=>{
  if(!currentPractice(j,area)||!$('#practice-rest-time')){clearInterval(practiceRestClock);return;}
  const remaining=f?.rest_remaining_ms===null?null:Math.max(0,(f?.rest_remaining_ms||0)-(performance.now()-j.restReceiptAt));
  $('#practice-rest-time').textContent=remaining?'按原安排休息，还剩 '+Math.ceil(remaining/1000)+' 秒':'准备好后点继续，不会自动开始。';
  const blocked=f?.decision?.category==='EXECUTION_BLOCK';
  start.disabled=!!j.sequenceBusy||(!ending&&!j.nextPending&&!f?.successor_id&&(!e||remaining>0||blocked||needsSupport&&(!support?.checked||required&&!companion?.checked)));
  if(blocked&&!ending)$('#practice-sequence-status').textContent=f.decision.message;
 };
 start.onclick=()=>void reconcilePracticeSequence(j,area,false);
 $('#practice-sequence-end').onclick=()=>{pausePractice();++j.sequenceReadEpoch;j.sequenceEndRequested=true;persistPractice(j);drawPracticeRest(j,area);if(!j.sequenceBusy)void reconcilePracticeSequence(j,area,false);};
 $('#practice-back').onclick=()=>{pausePractice();navigate('plan');};
 update();if(!document.hidden)practiceRestClock=setInterval(update,250);
}
function acceptPracticeSuccessor(j,area,r,ending,readOnly){
 if(r.predecessor_id!==j.start.operation_id||r.journey_id!==j.receipt.journey_id||!practiceEqual(r.context,j.context)||j.nextPending&&(!practiceEqual(r.continue_payload,j.nextPending)||r.id!==j.nextPending.operation_id))throw Error('下一组回执尚未确认，请核对原记录。');
 j.nextPending=null;j.sequenceStage=null;j.sequenceEndRequested=false;persistPractice(j);
 const n={context:j.context,ownerGeneration:j.ownerGeneration,start:r.start_payload,receipt:r,finish:r.finish_payload,elapsed:r.finish_payload?.elapsed_ms||0,countDraft:'',ended:r.state==='COMMITTED',running:false,busy:false,previewGeneration:0};
 practiceJourney=n;++practiceGeneration;state.selected=r.exercise_id;state.side=r.side;state.training={id:r.plan_ref.id,entry:{key:r.plan_ref.entry_key}};
 if(ending&&r.state!=='COMMITTED'){n.ended=true;n.finish={operation_id:newUploadOperation(),count:null,elapsed_ms:0,reason:'ended',feedback:{pain:null,fatigue:null}};}
 persistPractice(n);updateFormalPracticeLink(n);drawPractice(n,area);
 if(ending&&r.state==='COMMITTED'){n.sequenceEndRequested=true;n.sequenceStage='REST';persistPractice(n);drawPracticeRest(n,area);void reconcilePracticeSequence(n,area,false);}
 else if(ending&&r.state!=='COMMITTED')void submitPracticeFinish(n,area);
 else if(!readOnly&&!n.ended)startPracticeClock(n);
}
async function reconcilePracticeSequence(j,area,queryOnly=false){
 if(j.sequenceBusy||!currentPractice(j,area))return;j.sequenceBusy=true;j.sequenceMessage=null;drawPracticeRest(j,area);
 let followUpEnd=false;
 try{
  const f=j.receipt.continuation;
  if(!j.nextPending&&!j.sequenceEndRequested&&!f?.successor_id&&!queryOnly){
   const same=f?.kind==='next_set';
   j.nextPending={operation_id:newUploadOperation(),manual_arrangement_confirmed:true,support_ready:same?j.start.support_ready===true:j.nextSupport===true,companion_present:same?j.start.companion_present===true:j.nextCompanion===true};persistPractice(j);
  }
  const identity=j.nextPending?.operation_id||f?.successor_id;let r;
  if(identity){
   try{r=await api(practiceBase(j)+'/'+identity);}catch(error){if(error.status!==404)throw error;}
   if(!currentPractice(j,area))return;
   if(!r&&!j.sequenceEndRequested&&!queryOnly){
    r=await api(practiceBase(j)+'/'+j.start.operation_id+'/continue',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(j.nextPending)});
   }
   if(!currentPractice(j,area))return;
   if(r){acceptPracticeSuccessor(j,area,r,j.sequenceEndRequested,queryOnly);return;}
  }
  if(j.sequenceEndRequested){
   j.closePending??={operation_id:newUploadOperation()};persistPractice(j);
   r=await api(practiceBase(j)+'/'+j.start.operation_id);
   if(!currentPractice(j,area))return;
   if(r.id!==j.start.operation_id||!practiceEqual(r.context,j.context))throw Error('原记录归属不一致');
   if(!r.journey_closed)r=await api(practiceBase(j)+'/'+j.start.operation_id+'/close-journey',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(j.closePending)});
   if(!currentPractice(j,area))return;
   if(r.id!==j.start.operation_id||!practiceEqual(r.context,j.context)||!practiceEqual(r.close_payload,j.closePending)||r.journey_closed!==true)throw Error('结束回执尚未确认');
   j.receipt=r;j.sequenceStage=null;j.nextPending=null;j.sequenceEndRequested=false;persistPractice(j);
  }else j.sequenceMessage='下一组尚未开始，准备好后继续核对。';
 }catch(error){
  if(!currentPractice(j,area))return;
  if(error.status===409&&['MISSING_INPUT','EXECUTION_BLOCK'].includes(error.reason?.category)){j.nextPending=null;j.sequenceMessage=error.message;}
  else j.sequenceMessage=j.sequenceEndRequested?'结束待核对，请重试原操作。':'下一组保存待核对，请重试原操作。';
  persistPractice(j);
  // If End was clicked during the one active create, perform one original-ID
  // lookup. A failed lookup stays manual; no recursive/permanent retry loop.
  followUpEnd=j.sequenceEndRequested&&!queryOnly;
 }finally{
  j.sequenceBusy=false;
  if(currentPractice(j,area))drawPractice(j,area);
  if(followUpEnd&&currentPractice(j,area))void reconcilePracticeSequence(j,area,true);
 }
}
document.addEventListener('visibilitychange',()=>{if(document.hidden)pausePractice();});
window.addEventListener('pagehide',pausePractice);
