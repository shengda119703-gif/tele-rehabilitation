'use strict';
// Opt-in hosted v2, at the ORIGINAL capture/history entries. Never /live save.
let formalFlow=null,formalPageGeneration=0;
function formalReadCapability(){return state.formalMeasurement?.provider==='hosted-rehab-v2-1'?state.formalMeasurement:null;}
function formalCapability(){return automaticUploadReconciliation?formalReadCapability():null;}
function mountFormalEntry(){
 const capability=formalCapability();if(!capability||state.training||!capability.protocols.some(p=>p.exercise_id===state.selected))return;
 const button=document.createElement('button');button.id='formal-entry';button.className='secondary feature-entry';button.textContent='实时测量并保存';button.onclick=()=>formalMeasurementPage();$('#guide').append(button);
}
function formalCurrent(f){return formalFlow===f&&f.ownerGeneration===(state.uploadOwnerGeneration||0)&&f.pageGeneration===formalPageGeneration&&$('#formal-area')===f.area;}
function formalScopeCurrent(f){const c=state.formalMeasurement;return f.ownerGeneration===(state.uploadOwnerGeneration||0)&&c?.provider===f.capability.provider&&c.owner_scope===f.capability.owner_scope&&c.participant_id===f.capability.participant_id&&c.source_context===f.capability.source_context;}
function formalAdapterOptions(f){return {scope:f.capability,origin:location.origin,request:api,storage:localStorage,key:newUploadOperation,isScopeCurrent:()=>formalScopeCurrent(f)};}
function formalMessage(error){
 return ({camera_analysis_consent_required:'请先同意本次相机分析。',formal_camera_capacity_reached:'还有一项测量未结束，请先核对原记录。',control_revision_conflict:'测量状态已变化，请核对原记录。',session_not_running:'本次测量已停止，请查看已有结果。',formal_inference_worker_unavailable:'自动测量暂不可用，可返回按动作说明练习。',formal_session_store_already_owned:'测量服务正在使用，请稍后核对。',required_companion_confirmation_missing:'本项需要陪同者在场。',readonly_storage:'记录尚未保存，请恢复存储后核对。',camera_view_confirmation_required:'请先确认本次拍摄方向。'})[error.message]||([401,403].includes(error.status)?'连接或权限已变化，请重新核对本人。':error.message);
}
function releaseFormalCamera(f){
 f.sampling=false;++f.cameraGeneration;f.stream?.getTracks().forEach(t=>t.stop());f.stream=null;
 if(f.video){f.video.pause();f.video.srcObject=null;}if(f.guidance){RehabGuidance.app.close(f.guidance);f.guidance=null;}
}
function pauseFormalMeasurement(){
 const f=formalFlow;if(!f)return;releaseFormalCamera(f);
 if(f.adapter&&!f.adapter.draft.end_requested){void f.adapter.pause().then(()=>{if(formalCurrent(f))renderFormalState(f);}).catch(e=>{if(formalCurrent(f))$('#live-status').textContent='暂停待核对。'+formalMessage(e);});}
}
function invalidateFormalMeasurement(){
 // A scope change may NOT automatically write an old person's outbox.
 const f=formalFlow;if(f)releaseFormalCamera(f);formalFlow=null;++formalPageGeneration;
}
function formalExport(f){
 const content=f.adapter?.export();if(!content)return;
 const url=URL.createObjectURL(new Blob([content],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download='本次测量恢复记录.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
async function formalMeasurementPage(forceFresh=false,originalKey=null,training=null){
 const capability=formalCapability()||originalKey&&formalReadCapability(),spec=capability?.protocols.find(p=>p.exercise_id===(training?.binding.exercise_id||state.selected));
 if(!spec)return;
 pausePractice();stopLive();pauseFormalMeasurement();
 const ex=selected(),saved=training?.saved||RehabFormal.SessionAdapter.restore(localStorage,location.origin,capability,{exercise_id:ex.id,side:state.side,idempotency_key:originalKey});
 if(originalKey&&!saved){toast('原草稿暂未能读取，请返回核对。');return;}
 const compatible=!forceFresh&&(training?!!saved:saved?.create.submode==='assessment'&&saved.create.exercise_id===ex.id&&saved.create.side===state.side);
 const f={pageGeneration:++formalPageGeneration,ownerGeneration:state.uploadOwnerGeneration||0,capability,spec,exercise:ex.id,side:state.side,training,adapter:null,cameraGeneration:0,sampling:false,busy:false};formalFlow=f;
 app.innerHTML='<button class="back" id="formal-back">返回'+(training?'训练安排':'动作详情')+'</button><div class="page-head"><h1>'+esc(ex.label)+' · '+(training?'实时训练':'实时测量')+'</h1></div><section id="formal-area">'+liveMarkup()+'</section>';
 f.area=$('#formal-area');f.video=$('#live-video');
 // Existing controls, geometry and original consent. No silent camera request.
 $('#live-count').textContent='—';$('#live-start').textContent=compatible?'继续本次'+(training?'训练':'测量'):training?'开始实时训练':'开始测量';$('#live-stop').textContent='结束并保存';$('#live-facing').value=liveFacing;
 $('.live-controls').insertAdjacentHTML('afterend','<button class="secondary" id="formal-pause" disabled>暂停</button><button class="secondary" id="formal-reconcile">核对保存状态</button><button class="secondary" id="formal-export">导出恢复记录</button>');
 $('#live-consent').parentElement.insertAdjacentHTML('afterend','<label class="consent"><input type="checkbox" id="formal-view">已按'+(spec.view==='frontal'?'正面':'侧面')+'摆好手机</label>');
 $('#formal-area .tip').textContent='结束后保存可测到的结果。疼痛、头晕或不适时停止。';
 $('#formal-back').onclick=()=>{pauseFormalMeasurement();if(training){clearFormalTrainingLink();navigate('plan');}else assessment();};
 if(training){
  const b=training.binding,s=b.settings;
  $('#formal-area').insertAdjacentHTML('afterbegin','<div class="card"><h2>'+esc(b.plan_name)+'</h2><p class="caption">'+formalSideLabel(b.side)+' · '+s.target_reps+' 次 × '+s.target_sets+' 组</p><details><summary>怎么做</summary>'+['start','move','return'].map((key,n)=>'<div class="instruction"><span class="number">'+(n+1)+'</span><p>'+esc(ex.instructions[key])+'</p></div>').join('')+'</details><label class="consent"><input type="checkbox" id="formal-plan-confirmed">采用本人的这份训练安排</label>'+(s.needs_companion?'<label class="consent"><input type="checkbox" id="formal-companion">陪同者已在场</label>':'')+'</div>');
  if(compatible){$('#live-consent').checked=saved.create.consent===true;$('#formal-view').checked=saved.create.view===b.view;$('#formal-plan-confirmed').checked=saved.create.training_plan_confirmed===true;if($('#formal-companion'))$('#formal-companion').checked=saved.create.companion_confirmed===true;}
 }
 $('#live-start').onclick=()=>startFormalCamera(f);$('#formal-pause').onclick=()=>{pauseFormalMeasurement();$('#live-start').disabled=false;};
 $('#live-stop').onclick=()=>endFormalMeasurement(f);$('#formal-export').onclick=()=>formalExport(f);$('#formal-reconcile').onclick=()=>reconcileFormalPage(f);
 if(compatible){
  f.adapter=new RehabFormal.SessionAdapter({...formalAdapterOptions(f),draft:saved});
  $('#live-stop').disabled=false;await reconcileFormalPage(f);
  // Return/reload is paused. The explicit Continue button alone can open camera.
  if(formalCurrent(f)&&!f.adapter.draft.end_requested)pauseFormalMeasurement();
 }
 if(formalCurrent(f)&&!automaticUploadReconciliation){$('#live-start').disabled=true;if(!f.adapter?.draft.end_requested)$('#live-status').textContent='已关闭新测量；可以结束并核对原记录。';}
 else if(formalCurrent(f)&&(!window.isSecureContext||!navigator.mediaDevices?.getUserMedia)){$('#live-start').disabled=true;$('#live-status').textContent='当前地址不能使用实时相机，可返回选择原视频。';}
}
function renderFormalState(f){
 if(!formalCurrent(f)||!f.adapter)return;
 const a=f.adapter,item=a.snapshot,s=item?.snapshot,count=s?.completed??a.draft.commit?.completed_reps;
 $('#live-count').textContent=Number.isInteger(count)?count+' 次 · 自动记录':'—';
 const metric=s?.metric?.metrics?.[s?.protocol?.metric];$('#live-angle').textContent=metric?.valid?number(metric.value,'°'):'—';
 const terminal=a.draft.end_requested;
 const rounds=f.training?s?.training:null,resting=rounds?.stage==='RESTING',planComplete=rounds?.plan_complete===true;
 $('#live-start').disabled=f.busy||f.sampling||terminal||planComplete||!automaticUploadReconciliation;$('#live-stop').disabled=terminal;$('#formal-pause').disabled=!f.sampling;
 if(f.training&&!terminal)$('#live-start').textContent=resting?'继续下一组':a.draft.session_id?'继续本次训练':'开始实时训练';
 $('#live-facing').disabled=f.sampling||f.busy;
 const committed=a.draft.save_state==='COMMITTED';
 $('#live-status').textContent=committed?'测量结果已保存'+(item?.derived_report_state==='ready'?'':'，详细报告稍后补齐'):terminal?'本次已结束，正在确认保存':f.sampling?'正在测量':f.busy?'正在核对本次测量':!item?'本次测量待核对':item.run_state==='paused'?'本次测量已暂停':'相机已停止，测量暂停待核对';
 if(!terminal&&planComplete)$('#live-status').textContent='本项已达到安排，可结束并保存。';
 else if(!terminal&&resting)$('#live-status').textContent='本组已结束，按安排休息'+(Number.isFinite(rounds.prescribed_rest_s)?' '+rounds.prescribed_rest_s+' 秒':'')+'后继续下一组。';
 if(!a.durable&&!committed)$('#live-status').textContent+='；本机恢复草稿未写入，请勿关闭页面';
 if(terminal){$('#live-cue').textContent=committed?'本次测量已结束':'正在整理已有结果';$('#live-angle').textContent='—';}
  else if(!f.sampling){$('#live-cue').textContent=f.busy?'正在核对本次测量':!item?'本次测量待核对':item.run_state==='paused'?'本次测量已暂停':'相机已停止';$('#live-angle').textContent='—';}
 if(committed&&!$('#formal-history')){
  $('.live-controls').insertAdjacentHTML('afterend','<button class="secondary" id="formal-history">查看本次记录</button><button class="secondary" id="formal-again">再测一次</button>');
  $('#formal-history').onclick=()=>showFormalRecord(a.draft.session_id);
  if(f.training){$('#formal-again').textContent='返回训练安排';$('#formal-again').onclick=()=>{clearFormalTrainingLink();navigate('plan');};}
  else{$('#formal-again').disabled=!automaticUploadReconciliation;$('#formal-again').onclick=()=>{if(!formalCurrent(f)||!formalCapability())return;formalFlow=null;formalMeasurementPage(true);};}
 }
 if(terminal&&item?.session_id===a.draft.session_id&&typeof mountFormalFeedback==='function'){
  if(!f.feedback)f.feedback=mountFormalFeedback(item,f.area,f.capability,f.pageGeneration,()=>formalCurrent(f));
  else if(committed&&!f.feedback.adapter.snapshot&&!f.feedback.busy)void reconcileFormalFeedback(f.feedback);
 }
}
async function reconcileFormalPage(f){
 if(!formalCurrent(f)||!f.adapter||f.busy)return;
 f.busy=true;renderFormalState(f);
 try{if(!f.sampling&&!f.adapter.draft.end_requested)await f.adapter.pause();else await f.adapter.reconcile();if(!formalCurrent(f))return;renderFormalState(f);if(f.adapter.draft.end_requested&&f.adapter.draft.save_state!=='COMMITTED')pollFormalCommit(f,0);}
 catch(e){if(formalCurrent(f))$('#live-status').textContent='保存待核对。'+formalMessage(e);}
 finally{f.busy=false;if(formalCurrent(f))renderFormalState(f);}
}
async function pollFormalCommit(f,attempt){
 if(!formalCurrent(f)||f.adapter.draft.save_state==='COMMITTED'||attempt>=5)return;
 clearTimeout(f.commitTimer);f.commitTimer=setTimeout(async()=>{
  if(!formalCurrent(f))return;
  try{await f.adapter.reconcileCommit();if(formalCurrent(f)){renderFormalState(f);if(f.adapter.draft.save_state!=='COMMITTED')pollFormalCommit(f,attempt+1);}}
  catch(e){if(formalCurrent(f))$('#live-status').textContent='保存待核对。'+formalMessage(e);}
 },Math.min(8000,500*2**attempt));
}
async function startFormalCamera(f){
 if(!formalCapability()||!formalCurrent(f)||f.busy||f.sampling||f.cameraRequest||f.adapter?.draft.end_requested)return;
 if(!$('#live-consent').checked||!$('#formal-view').checked){$('#live-status').textContent='请同意相机分析并确认拍摄方向。';return;}
 if(f.training&&(!$('#formal-plan-confirmed').checked||f.training.binding.settings.needs_companion&&!$('#formal-companion')?.checked)){$('#live-status').textContent=f.training.binding.settings.needs_companion?'请确认采用这份安排，且陪同者在场。':'请确认采用本人的这份训练安排。';return;}
 if(liveCameraRequest||liveCreateRequest||liveCloseRequest||liveClosingSession){$('#live-status').textContent='正在释放上次相机，请稍后再开始。';return;}
 f.busy=true;const generation=++f.cameraGeneration;
 $('#live-start').disabled=true;$('#live-stop').disabled=false;$('#live-status').textContent='正在打开摄像头…';
 try{
  if(f.training){
   const value=await readFormalPlan(f.training.id,f.capability);
   if(!formalCurrent(f)||generation!==f.cameraGeneration)return;
   if(value.plan.revision!==f.training.revision)throw Error('训练安排版本已变化，请返回核对。');
   if(value.progress.next_key!==f.training.entry.key)throw Error('本轮训练位置已变化，请返回核对。');
   if(!formalPlanAllowed(value))throw Error(formalPlanReason(value));
  }
  const facing=$('#live-facing').value;
  const acquire=constraints=>{const p=navigator.mediaDevices.getUserMedia({audio:false,video:constraints});f.cameraRequest=p;return p;};
  let stream;
  try{stream=await acquire({facingMode:{ideal:facing},width:{ideal:640},height:{ideal:480}});}catch(e){if(e.name!=='OverconstrainedError'||!formalCurrent(f)||generation!==f.cameraGeneration)throw e;stream=await acquire({facingMode:{ideal:facing}});}finally{f.cameraRequest=null;}
  if(!formalCurrent(f)||generation!==f.cameraGeneration){stream.getTracks().forEach(t=>t.stop());return;}
  f.stream=stream;f.video.srcObject=stream;await f.video.play();if(!formalCurrent(f)||generation!==f.cameraGeneration){releaseFormalCamera(f);return;}
  liveFacing=facing;$('.live-preview').classList.toggle('mirrored',facing==='user');
  if(!f.adapter){
   const create=f.training?{idempotency_key:newUploadOperation(),consent:true,submode:'training',plan_id:f.training.id,expected_plan_revision:f.training.revision,entry_key:f.training.entry.key,view:f.spec.view,training_plan_confirmed:true,...(f.training.binding.settings.needs_companion?{companion_confirmed:true}:{})}:{idempotency_key:newUploadOperation(),consent:true,submode:'assessment',exercise_id:f.exercise,side:f.side,view:f.spec.view};
   f.adapter=new RehabFormal.SessionAdapter({...formalAdapterOptions(f),create,binding:f.training?.binding});
   if(f.training){const u=new URL(location.href);u.searchParams.set('tab','plan');u.searchParams.set('formal_plan',f.training.id);u.searchParams.set('formal_operation',create.idempotency_key);window.history.replaceState(null,'',u.href);}
  }
  await f.adapter.create();
  if(!formalCurrent(f)||generation!==f.cameraGeneration){if(formalScopeCurrent(f))await(f.adapter.draft.end_requested?f.adapter.finish():f.adapter.pause());return;}
  await f.adapter.resume();if(!formalCurrent(f)||generation!==f.cameraGeneration||f.adapter.draft.end_requested){releaseFormalCamera(f);renderFormalState(f);return;}
  f.busy=false;f.sampling=true;
  if(typeof RehabGuidance!=='undefined')f.guidance=RehabGuidance.app.open({owner_scope:f.capability.owner_scope,journey_id:f.adapter.draft.session_id,provider:f.capability.provider,source_context:f.capability.source_context,exercise_id:f.exercise,side:f.side,frontend_generation:generation},{isCurrent:()=>formalCurrent(f)&&f.sampling&&generation===f.cameraGeneration&&!f.adapter.draft.end_requested,voiceEnabled:()=>$('#live-voice')?.checked===true,render:text=>{if(formalCurrent(f))$('#live-cue').textContent=text;}});
  $('#live-voice').onchange=()=>{if(!$('#live-voice').checked&&f.guidance)RehabGuidance.app.clear(f.guidance);};
  renderFormalState(f);await formalFrames(f,generation);
 }catch(e){releaseFormalCamera(f);if(formalCurrent(f)){const cameraMessage={NotAllowedError:'未获得相机授权，可返回选择原视频。',NotFoundError:'未找到可用摄像头。',NotReadableError:'摄像头正在被其他程序使用。'}[e.name];$('#live-status').textContent=cameraMessage||formalMessage(e);$('#live-start').disabled=!!f.adapter?.draft.end_requested;$('#formal-pause').disabled=true;
  if(f.adapter?.draft.session_id&&!f.adapter.draft.pending&&!f.adapter.draft.end_requested&&formalScopeCurrent(f))void f.adapter.pause().catch(()=>{});
 }}
 finally{f.busy=false;if(formalCurrent(f)&&generation===f.cameraGeneration&&!f.adapter?.draft.end_requested){$('#live-start').disabled=false;$('#formal-pause').disabled=true;}}
}
async function formalFrames(f,generation){
 const current=()=>formalCurrent(f)&&f.sampling&&!document.hidden&&generation===f.cameraGeneration&&!f.adapter.draft.end_requested;
 const canvas=document.createElement('canvas');
 while(current()){
  if(!f.video.videoWidth){await new Promise(r=>setTimeout(r,80));continue;}
  const scale=Math.min(1,640/f.video.videoWidth);canvas.width=Math.round(f.video.videoWidth*scale);canvas.height=Math.round(f.video.videoHeight*scale);canvas.getContext('2d').drawImage(f.video,0,0,canvas.width,canvas.height);
  const blob=await new Promise(r=>canvas.toBlob(r,'image/jpeg',.75));if(!current())return;if(!blob)throw Error('相机没有返回画面。');
  await f.adapter.frame(blob);if(!current())return;
  // Accepted != processed. Wait for original consumer, with no frame backlog.
  for(let tries=0;tries<40&&current();tries++){
   const readBegan=performance.now();await f.adapter.read();if(!current())return;renderFormalState(f);
   const roundtrip=performance.now()-readBegan;
   const item=f.adapter.snapshot,s=item.snapshot,cue=item.current_cue;
   if(item.persistence_state==='finalized'||item.run_state==='finishing'){releaseFormalCamera(f);await reconcileFormalPage(f);return;}
   if(f.training&&(s?.training?.stage==='RESTING'||s?.training?.plan_complete===true)){releaseFormalCamera(f);renderFormalState(f);return;}
   const usable=cue&&s&&cue.session_id===item.session_id&&cue.exercise_id===f.exercise&&cue.side===f.side&&cue.calibration_epoch===s.calibration_epoch&&cue.valid_phases?.includes(s.phase)&&cue.evidence_refs?.length&&Number.isFinite(cue.remaining_ttl_ms)&&cue.remaining_ttl_ms>roundtrip;
   // Use backend remaining TTL; never subtract clocks from different processes.
   $('#live-cue').textContent=usable?cue.instruction:'按动作说明继续，部分画面暂未测到';
   if(f.guidance){if(!usable)RehabGuidance.app.clear(f.guidance,'按动作说明继续，部分画面暂未测到');else RehabGuidance.app.offer(f.guidance,{id:cue.cue_id,source:'FORMAL_CUE',text:cue.instruction,valid:true,remaining_ms:cue.remaining_ttl_ms-roundtrip,session_id:cue.session_id,exercise_id:cue.exercise_id,side:cue.side,epoch:s.calibration_epoch,phase:s.phase,evidence_refs:cue.evidence_refs,valid_phases:cue.valid_phases});}
   if(item.processed_last_seq>=item.accepted_last_seq)break;await new Promise(r=>setTimeout(r,100));
  }
  await new Promise(r=>setTimeout(r,120));
 }
}
function endFormalMeasurement(f){
 if(!formalCurrent(f))return;releaseFormalCamera(f);
 if(!f.adapter){$('#live-status').textContent='本次相机已关闭，尚未创建测量记录。';$('#live-start').disabled=false;$('#live-stop').disabled=true;return;}
 const finished=f.adapter.finish();renderFormalState(f);
 void finished.then(()=>{if(formalCurrent(f)){renderFormalState(f);pollFormalCommit(f,0);}}).catch(e=>{if(formalCurrent(f))$('#live-status').textContent='保存待核对。'+formalMessage(e);});
}
function appendFormalDrafts(area,capability){
 const drafts=RehabFormal.SessionAdapter.drafts(localStorage,location.origin,capability).filter(d=>d.save_state!=='COMMITTED');
 if(!drafts.length)return;
 area.insertAdjacentHTML('beforeend','<details><summary>测量待核对 · '+drafts.length+'</summary>'+drafts.map(d=>'<button class="record" data-formal-pending="'+esc(d.create.idempotency_key)+'"><span>'+esc(label(d.binding?.exercise_id||d.create.exercise_id))+' · '+(typeof formalSideLabel==='function'?formalSideLabel(d.binding?.side||d.create.side):sideLabel(d.create.side))+'</span><span>核对 ›</span></button>').join('')+'</details>');
 area.querySelectorAll('[data-formal-pending]').forEach(b=>b.onclick=()=>{const d=drafts.find(r=>r.create.idempotency_key===b.dataset.formalPending);if(!d)return;if(d.create.submode==='training'){void openFormalTraining(d.create.plan_id,d.create.idempotency_key);return;}if(!state.catalog.some(e=>e.id===d.create.exercise_id))return;state.tab='assess';state.training=null;state.selected=d.create.exercise_id;state.side=d.create.side;formalMeasurementPage(false,d.create.idempotency_key);});
}
async function mountFormalHistory(){
 if(!formalReadCapability())return;
 const area=document.createElement('section');area.id='formal-records';area.className='card';app.appendChild(area);const owner=state.uploadOwnerGeneration||0;
 const capability=formalReadCapability();area.innerHTML='<h2>实时测量记录</h2><p role="status">正在读取…</p>';appendFormalDrafts(area,capability);
 try{const data=await api('/rehab/v2/sessions');if($('#formal-records')!==area||owner!==(state.uploadOwnerGeneration||0))return;
  area.innerHTML='<h2>实时测量记录</h2>'+(data.items.length?data.items.map(i=>'<button class="record" data-formal-record="'+esc(i.session_id)+'"><span><strong>'+esc(label(i.contribution.exercise_id))+' · '+sideLabel(i.contribution.side)+'</strong><small>'+dateLabel(i.created_at)+' · '+(i.submode==='training'?'康复训练':'康复评估')+'</small></span><span class="badge">已保存 ›</span></button>').join(''):'<p class="caption">尚无实时测量记录。</p>');
  area.querySelectorAll('[data-formal-record]').forEach(b=>b.onclick=()=>showFormalRecord(b.dataset.formalRecord));
  appendFormalDrafts(area,capability);
 }catch(e){if($('#formal-records')===area&&owner===(state.uploadOwnerGeneration||0)){area.innerHTML='<h2>实时测量记录</h2><p>暂时未能读取</p><button class="secondary" id="formal-history-retry">重试</button>';appendFormalDrafts(area,capability);$('#formal-history-retry').onclick=()=>{area.remove();mountFormalHistory();};}}
}
async function showFormalRecord(id){
 const capability=formalReadCapability();if(!capability)return;
 pauseFormalMeasurement();const generation=++formalPageGeneration,owner=state.uploadOwnerGeneration||0;
 app.innerHTML='<button class="back" id="formal-record-back">返回记录</button><div class="card" id="formal-record"><p>正在读取本次测量…</p></div>';$('#formal-record-back').onclick=()=>navigate('history');const area=$('#formal-record');
 try{const item=await api('/rehab/v2/sessions/'+encodeURIComponent(id));if($('#formal-record')!==area||generation!==formalPageGeneration||owner!==(state.uploadOwnerGeneration||0))return;
  if(item.session_id!==id||item.owner!==capability.owner_scope||item.frozen_plan?.plan?.participant_id!==capability.participant_id||item.source?.source_kind!=='LIVE_CAMERA'||item.source.usage_context!=='SELF_USE')throw Error('本次测量的归属不一致。');
  if(item.persistence_state!=='finalized'||item.canonical_commit?.session_id!==id)throw Error('本次测量仍在保存，请稍后核对。');
  const p=item.frozen_plan.plan,s=item.snapshot,c=item.canonical_commit;
  if(c.completed_reps!==s.completed)throw Error('测量记录暂未能核对。');
  area.innerHTML='<h2>'+esc(label(p.exercise_id))+' · '+(typeof formalSideLabel==='function'?formalSideLabel(p.side):sideLabel(p.side))+'</h2><p class="caption">'+dateLabel(c.committed_at)+' · 测量结果已保存</p><div class="stat-grid"><div class="stat"><strong>'+s.completed+'<small> 次</small></strong><small>自动记录</small></div><div class="stat"><strong>'+esc(s.repetitions?.filter(r=>r.completion_status==='UNASSESSABLE').length??0)+'</strong><small>未完整测到的片段</small></div></div><p class="result-note">本次按实际可观察片段记录；未测到的部分没有补算。</p><p class="caption">'+(item.derived_report_state==='ready'?'详细报告已生成':'详细报告稍后补齐，已有测量结果可以查看。')+'</p><details><summary>测量说明</summary><p>'+esc(s.protocol.metric_version)+' · '+esc(s.measurement_contract.coordinate_space)+'</p><p>二维投影观察，不是疾病诊断。</p></details>';
  if(p.submode==='training'){area.insertAdjacentHTML('beforeend','<p class="caption">本项安排 '+p.target_reps+' 次 × '+p.target_sets+' 组 · 自动完成 '+(s.training?.completed_sets??'—')+' 组</p><details><summary>对应训练安排</summary><p>'+esc(item.frozen_plan.plan_id)+' · 版本 '+item.frozen_plan.plan_revision+'</p><p>'+esc(item.frozen_plan.entry_key)+'</p></details><button class="secondary" id="formal-record-plan">查看训练安排</button>');$('#formal-record-plan').onclick=()=>{clearFormalTrainingLink();navigate('plan');};}
  if(typeof mountFormalFeedback==='function')mountFormalFeedback(item,area,capability,generation);
 }catch(e){if($('#formal-record')===area&&generation===formalPageGeneration&&owner===(state.uploadOwnerGeneration||0)){area.innerHTML='<p>'+esc(formalMessage(e))+'</p><button class="secondary" id="formal-record-retry">重试</button>';$('#formal-record-retry').onclick=()=>showFormalRecord(id);}}
}
document.addEventListener('visibilitychange',()=>{if(document.hidden)pauseFormalMeasurement();});
window.addEventListener('pagehide',()=>pauseFormalMeasurement());
