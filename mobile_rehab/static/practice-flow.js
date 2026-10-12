'use strict';
// A practice journey is not the /live preview and never completes a formal
// plan. The owning backend grants the saved arrangement and commits its record.
let practiceJourney=null,practiceGeneration=0,practiceClock;
const practiceCanonical=v=>Array.isArray(v)?v.map(practiceCanonical):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,practiceCanonical(v[k])])):v;
const practiceEqual=(a,b)=>JSON.stringify(practiceCanonical(a))===JSON.stringify(practiceCanonical(b));
const practiceDraftKey=c=>'ankang-practice-draft-1:'+JSON.stringify([location.origin,c.provider,c.source_context,c.participant_id]);
const practiceRecordDraftKey=(c,id)=>practiceDraftKey(c)+':'+id;
function persistPractice(j){
 try{const text=JSON.stringify({version:1,context:j.context,start:j.start,finish:j.finish||null,elapsed:j.elapsed,ended:j.ended,committed:j.receipt?.state==='COMMITTED',countDraft:j.countDraft||'',feedbackDraft:j.feedbackDraft||null,feedbackPending:j.feedbackPending||null,feedbackSuperseded:j.feedbackSuperseded||[],observationSegments:j.observationSegments||[]});localStorage.setItem(practiceRecordDraftKey(j.context,j.start.operation_id),text);j.draftSaved=true;try{localStorage.setItem(practiceDraftKey(j.context),text);}catch{/* The individually scoped draft remains recoverable from its history entry. */}}
 catch{j.draftSaved=false;}
}
function pausePractice(){
 const j=practiceJourney;if(!j)return;clearInterval(practiceClock);
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
async function beginGuidedPractice(record,entry,resume=null){
 pausePractice();const generation=++practiceGeneration,ownerGeneration=state.uploadOwnerGeneration||0;
 // The retained capture router is query-based. Entering from an assessment
 // result must not send a reload back to the assessment library: the existing
 // plan entry is where the owner-bound original practice draft is reconciled.
 const returnUrl=new URL(location.href,location.origin);returnUrl.searchParams.set('tab',resume?.state==='COMMITTED'?'history':'plan');window.history.replaceState(null,'',returnUrl.href);
 app.innerHTML='<div class="page-head"><h1>'+esc(label(entry.exercise_id))+'</h1></div><div class="card" id="practice-area"><p role="status">正在核对本项安排…</p></div>';
 const area=$('#practice-area');
 try{
  const context=await api('/practice/context');if(generation!==practiceGeneration||$('#practice-area')!==area||ownerGeneration!==(state.uploadOwnerGeneration||0))return;
  let saved;try{saved=JSON.parse((resume&&localStorage.getItem(practiceRecordDraftKey(context,resume.id)))||localStorage.getItem(practiceDraftKey(context))||'null');}catch{/* Keep the current page available when draft storage is unavailable. */}
  if(!saved&&practiceJourney&&practiceEqual(practiceJourney.context,context))saved={...practiceJourney,version:1};
  const compatible=saved?.version===1&&practiceEqual(saved.context,context)&&typeof saved.start?.operation_id==='string'&&saved.start.plan_id===record.id&&saved.start.entry_key===entry.key&&(resume?saved.start.operation_id===resume.id:!saved.committed);
  const j={context,ownerGeneration,start:resume?.start_payload||(compatible?saved.start:{operation_id:newUploadOperation(),plan_id:record.id,plan_revision:record.revision,entry_key:entry.key}),finish:resume?.finish_payload||(compatible?saved.finish:null),elapsed:compatible&&Number.isFinite(saved.elapsed)?Math.max(0,saved.elapsed):(resume?.finish_payload?.elapsed_ms||0),countDraft:compatible?saved.countDraft||'':'',ended:resume?.state==='COMMITTED'||compatible&&saved.ended===true,running:false,busy:false,receipt:null};
  j.previewGeneration=0;
  if(compatible){j.feedbackDraft=saved.feedbackDraft||null;j.feedbackPending=saved.feedbackPending||null;j.feedbackSuperseded=saved.feedbackSuperseded||[];j.observationSegments=Array.isArray(saved.observationSegments)?saved.observationSegments:[];}
  practiceJourney=j;persistPractice(j);await reconcilePractice(j,area,true);
 }catch(e){if($('#practice-area')===area&&ownerGeneration===(state.uploadOwnerGeneration||0)){area.innerHTML='<p>'+esc(e.message)+'</p><button class="secondary" id="practice-back">返回训练安排</button>';$('#practice-back').onclick=()=>navigate('plan');}}
}
async function reconcilePractice(j,area,mayCreate=false){
 if(j.busy)return;j.busy=true;
 try{
  let receipt;try{receipt=await api('/practice/'+j.start.operation_id);}catch(e){if(e.status!==404||!mayCreate)throw e;receipt=await api('/practice',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(j.start)});}
  if(!currentPractice(j,area))return;
  if(j.receipt?.state==='COMMITTED'&&receipt.state!=='COMMITTED')return;
  if(receipt.id!==j.start.operation_id||!practiceEqual(receipt.context,j.context))throw Error('练习记录的归属不一致，请返回核对。');
  j.receipt=receipt;
  if(receipt.execution_allowed!==true)pausePractice();
  if(receipt.state==='COMMITTED'){j.ended=true;j.finish=receipt.finish_payload;persistPractice(j);}
  drawPractice(j,area);
  if(j.ended&&receipt.state!=='COMMITTED'&&j.finish)await submitPracticeFinish(j,area);
  else if(!j.ended){startPracticeClock(j);if(typeof resumePracticeObservation==='function')void resumePracticeObservation(j,area);}
 }catch(e){
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
 const retainedObservation=!j.ended?$('#practice-observation'):null;
 const r=j.receipt,ex=state.catalog.find(x=>x.id===r.exercise_id),i=ex?.instructions||{},done=r.state==='COMMITTED';
 const savedLabel=j.context.provider==='phone-local-1'?'练习记录已保存在本机':'练习记录已保存';
 // Eligibility reconciliation does not remount an active preview/video.
 if(retainedObservation&&$('#practice-count')){
  $('#practice-pause').disabled=r.execution_allowed!==true;
  $('#practice-save').textContent=r.execution_allowed===true?(j.draftSaved?'已进入跟练，草稿已保留':'已进入跟练；本机草稿未写入，结束时将向原服务保存'):(r.execution_reason||'安排暂不可继续；可以结束并保存本次记录。');
  return;
 }
 area.innerHTML=`<div class="section-head"><h2>${esc(label(r.exercise_id))} · ${sideLabel(r.side)}</h2></div><p class="caption">本组安排 ${r.settings.target_reps} 次 · 按原安排练习</p>${!j.ended?['start','move','return'].map((k,n)=>`<div class="instruction"><span class="number">${n+1}</span><p>${esc(i[k])}</p></div>`).join(''):''}<p id="practice-time" class="caption">${Math.floor(j.elapsed/1000)} 秒 · 跟练页面时间</p><p id="practice-save" role="status">${done?savedLabel:j.ended?'本次已结束，正在确认保存':j.draftSaved?'已进入跟练，草稿已保留':'已进入跟练；本机草稿未写入，结束时将向原服务保存'}</p>${!j.ended?'<label class="consent">本组总次数（选填）<input id="practice-count" type="number" min="0" max="10000" step="1" placeholder="本人记录"></label><div class="live-controls"><button class="primary" id="practice-pause">继续</button><button class="danger" id="practice-end">结束本组</button></div>':`<p class="result-note">${done&&r.self_reported_count!==null?'本组 '+esc(r.self_reported_count)+' 次 · 本人记录':'本次未填写执行次数。'}${done?' 未计入自动确认或正式计划进度。':''}</p><button class="secondary" id="practice-reconcile">${done?'查看原保存记录':'核对保存状态'}</button>`}<button class="secondary file-actions" id="practice-back">返回训练安排</button><p class="tip">有疼痛、头晕或不适时立即停止。跟练时间不是有效保持时间。</p>`;
 $('#practice-back').onclick=()=>{pausePractice();navigate('plan');};
  if($('#practice-count')){$('#practice-count').value=j.countDraft||'';$('#practice-count').oninput=e=>{j.countDraft=e.target.value;persistPractice(j);};}
 if($('#practice-reconcile'))$('#practice-reconcile').onclick=()=>reconcilePractice(j,area);
 if(!j.ended&&r.execution_allowed!==true){$('#practice-save').textContent=r.execution_reason||'安排暂不可继续；可以结束并保存本次记录。';$('#practice-pause').disabled=true;}
 if($('#practice-pause'))$('#practice-pause').onclick=()=>j.running?pausePractice():reconcilePractice(j,area);
 if($('#practice-end'))$('#practice-end').onclick=()=>{
  if(j.ended)return;const raw=$('#practice-count').value,count=raw===''?null:Number(raw);
  if(count!==null&&(!Number.isInteger(count)||count<0||count>10000)){toast('请填写本组实际总次数，或留空');return;}
  pausePractice();j.ended=true;j.finish={operation_id:newUploadOperation(),count,elapsed_ms:Math.min(86400000,Math.round(j.elapsed)),reason:'ended',feedback:{pain:null,fatigue:null}};
  persistPractice(j);drawPractice(j,area);void submitPracticeFinish(j,area);
 };
 if(!j.ended&&typeof mountPracticeObservation==='function')mountPracticeObservation(j,area,retainedObservation);
 if(j.ended&&typeof mountPracticeFeedback==='function')mountPracticeFeedback(j,area);
}
async function submitPracticeFinish(j,area){
 if(j.finishRequest)return;j.finishRequest=true;
 try{
  const r=await api('/practice/'+j.start.operation_id+'/finish',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(j.finish)});
  if(!currentPractice(j,area))return;
  if(r.state!=='COMMITTED'||r.id!==j.start.operation_id||!practiceEqual(r.finish_payload,j.finish))throw Error('结束回执尚未确认，请核对原记录。');
  j.receipt=r;persistPractice(j);drawPractice(j,area);
 }catch(e){if(currentPractice(j,area))$('#practice-save').textContent='本次已结束，保存待核对。'+(j.draftSaved?'草稿已保留。':'记录仍在当前页面。');}
 finally{j.finishRequest=false;}
}
async function mountPracticeHistory(){
 if(!state.practiceRecording)return;const area=document.createElement('section');area.className='card';area.id='practice-records';app.appendChild(area);
 area.innerHTML='<p role="status">正在读取跟练记录…</p>';const ownerGeneration=state.uploadOwnerGeneration||0;
 try{const rows=await api('/practice');if($('#practice-records')!==area||ownerGeneration!==(state.uploadOwnerGeneration||0))return;
  area.innerHTML='<h2>跟练记录</h2>'+rows.map(r=>`<button class="record" data-practice="${esc(r.id)}"><span><strong>${esc(label(r.exercise_id))} · ${sideLabel(r.side)}</strong><small>${dateLabel(r.ended_at||r.created_at)} · ${r.state==='COMMITTED'?(r.self_reported_count===null?'未填写次数':esc(r.self_reported_count)+' 次 · 本人记录'):'尚未结束'}</small></span><span class="badge">${r.state==='COMMITTED'?'已保存':'继续'} ›</span></button>`).join('');
  area.querySelectorAll('[data-practice]').forEach(b=>b.onclick=()=>{const r=rows.find(x=>x.id===b.dataset.practice);state.tab='assess';state.training={id:r.plan_ref.id,entry:{key:r.plan_ref.entry_key}};state.selected=r.exercise_id;state.side=r.side;beginGuidedPractice({id:r.plan_ref.id,revision:r.plan_ref.revision},{key:r.plan_ref.entry_key,exercise_id:r.exercise_id},r);});
 }catch(e){if($('#practice-records')===area){area.innerHTML='<p>跟练记录暂时未能读取</p><button class="secondary" id="practice-history-retry">重试</button>';$('#practice-history-retry').onclick=()=>{area.remove();mountPracticeHistory();};}}
}
document.addEventListener('visibilitychange',()=>{if(document.hidden)pausePractice();});
window.addEventListener('pagehide',pausePractice);
