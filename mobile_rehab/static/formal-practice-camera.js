'use strict';
// Optional original v2 measurement beside an independently granted practice.
// The practice clock, self-reported total and formal contribution stay separate.
let formalPracticePermission=null,formalPracticeControl=null;
function formalPracticeCameraBusy(){return !!(formalPracticePermission||formalPracticeControl?.busy||formalPracticeControl?.stream);}
function formalPracticeScope(g){return formalPlanCurrent(g.capability,g.j.ownerGeneration)&&g.j.context.owner_scope===g.capability.owner_scope&&g.j.context.participant_id===g.capability.participant_id;}
function formalPracticeCurrent(g){return formalPracticeScope(g)&&currentPractice(g.j,g.area)&&g.j.formalCamera===g&&g.panel.isConnected;}
function formalPracticeRemember(g){
 if(g.adapter){g.j.formalVisual={version:1,scope:g.capability,create:g.adapter.draft.create,binding:g.adapter.draft.binding,adapter_draft:JSON.parse(JSON.stringify(g.adapter.draft)),link:g.link||null,link_receipt:g.linkReceipt||null,notice_codes:[...(g.notices||[])]};persistPractice(g.j);}
}
function formalPracticeSaveLabel(j){
 const saved=j.receipt?.state==='COMMITTED',parts=j.receipt?.saved_parts;
 const camera=j.formalCamera?.adapter?.draft,visual=camera?.save_state||parts?.visual_facts||(j.formalVisual?'LOCAL_DRAFT':null);
 const base=saved?'练习记录已保存':j.ended?'本次已结束，练习保存待核对':null;
 if(!base)return null;
 if(camera?.save_state==='COMMITTED'&&!j.formalCamera.linkReceipt)return base+'，测量关联待核对';
 if(visual&&visual!=='COMMITTED')return base+'，自动测量保存待核对';
 return base+(visual==='COMMITTED'?'，自动测量已保存':'');
}
function formalPracticeRelease(g,reason){
 clearInterval(g.viewTimer);clearTimeout(g.commitTimer);
 g.presenter?.disable(performance.now(),reason);releaseFormalCamera(g);
 formalPracticeRemember(g);
}
function stopFormalPracticeObservation(j,reason='practice_paused'){
 const g=j.formalCamera;if(!g)return;
 formalPracticeRelease(g,reason);
 if(reason==='scope_changed'||!formalPracticeScope(g)||!g.adapter)return;
 // Mark End synchronously before any queued resume can be sent.
 if(reason==='practice_ended'){void reconcileFormalPracticeCamera(g,true);return;}
 if(g.adapter.draft.end_requested||g.pauseRequest)return;
 g.pauseRequest=g.adapter.pause().then(()=>{formalPracticeRemember(g);renderFormalPracticeState(g);}).catch(e=>{g.error='相机已关闭，暂停待核对。'+formalMessage(e);renderFormalPracticeState(g);}).finally(()=>{g.pauseRequest=null;});
}
function renderFormalPracticeState(g){
 if(!formalPracticeCurrent(g))return;
 const a=g.adapter,d=a?.draft,item=a?.snapshot,view=g.view;
 const count=item?.snapshot?.completed??d?.commit?.completed_reps;
 g.panel.querySelector('#live-count').textContent=Number.isInteger(count)?count+' 次 · 自动记录':'—';
 g.panel.querySelector('#live-angle').textContent=g.sampling&&view?.angle!==null&&view?.angle!==undefined?number(view.angle,'°'):'—';
 g.panel.querySelector('#live-cue').textContent=g.sampling?view?.cue||'按动作说明练习，自动记录正在连接':g.j.ended?'本次练习已结束':'按安排练习，摄像头可稍后开启';
 const status=g.panel.querySelector('#live-status');
 status.textContent=g.error|| (d?.save_state==='COMMITTED'?'自动测量已保存':d?.end_requested?'自动测量保存待核对':g.busy?'正在连接自动测量，当前练习继续':g.sampling?view?.mode==='AUTO_ASSISTED'?'自动记录中':'按安排继续练习':d?'相机已关闭，测量状态可核对':'摄像头选用，不影响当前跟练');
 if(d&&!a.durable&&d.save_state!=='COMMITTED')status.textContent+='；本机测量恢复记录未写入，请先导出';
 const start=g.panel.querySelector('#live-start');start.textContent=d?.end_requested?'开启新的测量':d?'继续自动测量':'开启自动测量';
 start.disabled=g.j.ended||!g.j.running||g.j.receipt.execution_allowed!==true||g.busy||g.sampling||!formalCapability()||!window.isSecureContext||!navigator.mediaDevices?.getUserMedia;
 g.panel.querySelector('#live-stop').disabled=!g.busy&&!g.sampling&&!d;
 g.panel.querySelector('#live-facing').disabled=g.busy||g.sampling;
 const label=formalPracticeSaveLabel(g.j);if(label&&$('#practice-save'))$('#practice-save').textContent=label;
}
function mountFormalPracticeObservation(j,area,retained=null){
 const cap=formalReadCapability();if(!cap||!formalGuidedCapability())return;
 const spec=cap.protocols.find(p=>p.exercise_id===j.receipt.exercise_id);if(!spec)return;
 const panel=retained||document.createElement('details');panel.id='practice-observation';
 if(!retained){panel.innerHTML='<summary>摄像头自动记录（选用）</summary>'+liveMarkup();}
 area.appendChild(panel);
 const g=j.formalCamera||{j,capability:JSON.parse(JSON.stringify(cap)),cameraGeneration:0,sampling:false,busy:false,adapter:null};
 j.formalCamera=g;g.area=area;g.panel=panel;g.video=panel.querySelector('#live-video');g.spec=spec;g.error=null;
 if(formalPracticeControl!==g&&formalPracticeControl?.stream){const previous=formalPracticeControl;formalPracticeRelease(previous,'new_practice_page');if(formalPracticeScope(previous)&&!previous.adapter?.draft.end_requested)void previous.adapter?.pause().catch(()=>{});}
 formalPracticeControl=g;
 if(!retained){
  panel.querySelector('.tip').textContent='可测到的结果单独保存，不与本人填写的总次数相加。';
  panel.querySelector('#live-facing').value=liveFacing;
  panel.querySelector('#live-stop').textContent='关闭并保存测量';
  panel.querySelector('#live-consent').parentElement.insertAdjacentHTML('afterend','<label class="consent"><input id="practice-camera-view" type="checkbox">已按'+(spec.view==='frontal'?'正面':'侧面')+'摆好手机</label><button class="secondary" id="practice-camera-reconcile">核对自动测量</button><button class="secondary" id="practice-camera-export">导出恢复记录</button>');
 }
 panel.querySelector('#live-start').onclick=()=>void startFormalPracticeCamera(g);
 panel.querySelector('#live-stop').onclick=()=>{formalPracticeRelease(g,'user_disabled_camera');void reconcileFormalPracticeCamera(g,true);};
 panel.querySelector('#live-voice').onchange=()=>{if(!panel.querySelector('#live-voice').checked&&g.guidance)RehabGuidance.app.clear(g.guidance);};
 panel.querySelector('#practice-camera-reconcile').onclick=()=>void reconcileFormalPracticeCamera(g,j.ended);
 panel.querySelector('#practice-camera-export').onclick=()=>{
  if(g.adapter){formalExport(g);return;}
  if(!j.formalVisual)return;
  const url=URL.createObjectURL(new Blob([JSON.stringify({kind:'ankang-guided-visual-recovery-1',context:j.context,practice_id:j.start.operation_id,formal_visual:j.formalVisual},null,2)],{type:'application/json'}));
  const link=document.createElement('a');link.href=url;link.download='本次测量恢复记录.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 };
 if(!g.adapter&&j.formalVisual){
  try{
   const v=j.formalVisual;
   if(v.version!==1||!practiceEqual(v.scope,cap)||v.create.submode!=='training'||v.create.plan_id!==j.start.plan_id||v.create.expected_plan_revision!==j.start.plan_revision||v.create.entry_key!==j.start.entry_key||v.binding.exercise_id!==j.receipt.exercise_id||v.binding.side!==j.receipt.side||!practiceEqual(v.binding.settings,j.receipt.settings))throw Error('原测量归属暂未能核对，请保留记录。');
   const draft=RehabFormal.SessionAdapter.restore(localStorage,location.origin,cap,{submode:'training',idempotency_key:v.create.idempotency_key})||v.adapter_draft;
   if(!draft||!practiceEqual(draft.create,v.create)||!practiceEqual(draft.binding,v.binding))throw Error('原测量恢复记录暂未能读取，请先导出。');
   g.adapter=new RehabFormal.SessionAdapter({scope:cap,origin:location.origin,request:api,storage:localStorage,key:newUploadOperation,draft,isScopeCurrent:()=>formalPracticeScope(g)});g.link=v.link;g.linkReceipt=v.link_receipt;g.notices=new Set(v.notice_codes||[]);
   panel.querySelector('#live-consent').checked=v.create.consent===true;panel.querySelector('#practice-camera-view').checked=v.create.view===spec.view;
   // Reopening reconciles the ORIGINAL identity and pauses, never acquires media.
   void reconcileFormalPracticeCamera(g,j.ended);
  }catch(e){g.restoreError=true;g.error=e.message;}
 }
 const refs=j.receipt.visual_session_refs||[];
 if(refs.length&&!panel.querySelector('[data-practice-visual]')){const details=document.createElement('details');details.innerHTML='<summary>对应自动测量</summary>'+refs.map(r=>'<button class="record" data-practice-visual="'+esc(r.session_id)+'">'+(r.save_state==='COMMITTED'?'查看自动记录':'核对自动记录')+'</button>').join('');panel.appendChild(details);details.querySelectorAll('[data-practice-visual]').forEach(b=>b.onclick=()=>{pausePractice();void showFormalRecord(b.dataset.practiceVisual);});}
 renderFormalPracticeState(g);
}
async function formalPracticeLink(g){
 if(!g.adapter.draft.session_id)return;
 g.link??={operation_id:newUploadOperation(),session_id:g.adapter.draft.session_id};formalPracticeRemember(g);
 if(g.link.session_id!==g.adapter.draft.session_id)throw Error('原关联与测量编号不一致，请保留记录。');
 const valid=r=>r.status==='COMMITTED'&&r.operation_id===g.link.operation_id&&r.session_id===g.link.session_id&&r.practice_id===g.j.start.operation_id&&r.journey_id===g.j.receipt.journey_id&&practiceEqual(r.context,g.j.context)&&r.association_scope==='journey_not_self_reported_set_total'&&r.no_measurement_or_contribution_rewrite===true;
 if(g.linkReceipt){if(!valid(g.linkReceipt))throw Error('原测量关联待核对，请保留记录。');return;}
 if(!formalPracticeScope(g))return;
 const r=await api('/rehab/v2/practice/'+g.j.start.operation_id+'/visual-link',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(g.link)});
 if(!valid(r))throw Error('测量关联待核对，请保留原记录。');
 g.linkReceipt=r;formalPracticeRemember(g);
}
async function reconcileFormalPracticeCamera(g,end=false){
 if(!g.adapter||!formalPracticeScope(g))return;
 if(end){g.adapter.draft.end_requested=true;g.adapter.persist();formalPracticeRemember(g);}
 if(g.reconcileRequest){const pending=g.reconcileRequest;return end?pending.then(()=>reconcileFormalPracticeCamera(g,false)):pending;}
 const request=(async()=>{
  try{
   g.error=null;
   if(g.adapter.draft.end_requested)await g.adapter.finish();
   else await g.adapter.pause();
   await formalPracticeLink(g);formalPracticeRemember(g);if(!formalPracticeScope(g))return;
   const r=await api('/rehab/v2/practice/'+g.j.start.operation_id);
   if(formalPracticeScope(g)&&r.id===g.j.start.operation_id&&practiceEqual(r.context,g.j.context)&&!(g.j.receipt.state==='COMMITTED'&&r.state!=='COMMITTED'))g.j.receipt=r;
   if(g.adapter.draft.end_requested&&g.adapter.draft.save_state!=='COMMITTED'&&formalPracticeCurrent(g))pollFormalPracticeCommit(g,0);
  }catch(e){g.error='自动测量待核对。'+formalMessage(e);}
  finally{formalPracticeRemember(g);renderFormalPracticeState(g);}
 })();g.reconcileRequest=request;
 try{await request;}finally{if(g.reconcileRequest===request)g.reconcileRequest=null;}
}
function pollFormalPracticeCommit(g,attempt){
 if(attempt>=5||!formalPracticeCurrent(g)||g.adapter.draft.save_state==='COMMITTED')return;
 clearTimeout(g.commitTimer);g.commitTimer=setTimeout(async()=>{
  if(!formalPracticeCurrent(g))return;
  try{await g.adapter.reconcileCommit();formalPracticeRemember(g);renderFormalPracticeState(g);if(g.adapter.draft.save_state!=='COMMITTED')pollFormalPracticeCommit(g,attempt+1);}
  catch(e){g.error='自动测量保存待核对。'+formalMessage(e);renderFormalPracticeState(g);}
 },Math.min(8000,500*2**attempt));
}
async function startFormalPracticeCamera(g){
 if(!formalPracticeCurrent(g)||!formalCapability()||g.restoreError||g.busy||g.sampling||g.j.ended||!g.j.running||g.j.receipt.execution_allowed!==true)return;
 if(formalPracticePermission||liveSession||liveCameraRequest||liveCreateRequest||liveCloseRequest||liveClosingSession||formalFlow?.cameraRequest||formalFlow?.stream){g.error='上次相机尚未释放，请稍后开启。';renderFormalPracticeState(g);return;}
 if(!g.panel.querySelector('#live-consent').checked||!g.panel.querySelector('#practice-camera-view').checked){g.error='请同意相机分析并确认拍摄方向。';renderFormalPracticeState(g);return;}
 const generation=++g.cameraGeneration,current=()=>formalPracticeCurrent(g)&&generation===g.cameraGeneration&&g.j.running&&!g.j.ended&&!document.hidden;
 g.busy=true;g.error=null;renderFormalPracticeState(g);
 try{
  await g.pauseRequest;await g.reconcileRequest;if(!current())return;
  if(!g.adapter||g.adapter.draft.end_requested){
   if(g.adapter&&g.adapter.draft.save_state!=='COMMITTED')throw Error('上段测量尚在保存，当前跟练可以继续。');
   const value=await readFormalPlan(g.j.start.plan_id,g.capability);if(!current())return;
   if(value.plan.revision!==g.j.start.plan_revision||value.progress.next_key!==g.j.start.entry_key||!formalPlanAllowed(value))throw Error(formalPlanReason(value));
  }
  const facing=g.panel.querySelector('#live-facing').value;
  const acquire=constraints=>{const p=navigator.mediaDevices.getUserMedia({audio:false,video:constraints});formalPracticePermission=p;g.cameraRequest=p;return p;};
  let stream;
  try{stream=await acquire({facingMode:{ideal:facing},width:{ideal:640},height:{ideal:480}});}catch(e){if(e.name!=='OverconstrainedError'||!current())throw e;stream=await acquire({facingMode:{ideal:facing}});}finally{if(formalPracticePermission===g.cameraRequest)formalPracticePermission=null;g.cameraRequest=null;}
  if(!current()){stream.getTracks().forEach(t=>t.stop());return;}
  g.stream=stream;g.video.srcObject=stream;await g.video.play();if(!current()){formalPracticeRelease(g,'late_camera');return;}
  liveFacing=facing;g.panel.querySelector('.live-preview').classList.toggle('mirrored',facing==='user');
  if(!g.adapter||g.adapter.draft.end_requested){
   const create={idempotency_key:newUploadOperation(),consent:true,submode:'training',plan_id:g.j.start.plan_id,expected_plan_revision:g.j.start.plan_revision,entry_key:g.j.start.entry_key,view:g.spec.view,training_plan_confirmed:true,...(g.j.receipt.settings.needs_companion?{companion_confirmed:g.j.start.companion_present===true}:{})};
   const binding={plan_name:'',exercise_id:g.j.receipt.exercise_id,side:g.j.receipt.side,view:g.spec.view,settings:JSON.parse(JSON.stringify(g.j.receipt.settings))};
   g.adapter=new RehabFormal.SessionAdapter({scope:g.capability,origin:location.origin,request:api,storage:localStorage,key:newUploadOperation,create,binding,isScopeCurrent:()=>formalPracticeScope(g)});
   g.adapter.draft.practice_binding={practice_id:g.j.start.operation_id,journey_id:g.j.receipt.journey_id,set_index:g.j.receipt.set_index};g.adapter.persist();g.link=null;g.linkReceipt=null;formalPracticeRemember(g);
  }
  await g.adapter.create();await formalPracticeLink(g);
  if(!current()){if(formalPracticeScope(g))await(g.j.ended?g.adapter.finish():g.adapter.pause());formalPracticeRemember(g);return;}
  await g.adapter.resume();if(!current()||g.adapter.draft.end_requested)return;
  if(!['preparing','active','recovering'].includes(g.adapter.snapshot?.run_state))throw Error('原测量已停止，当前跟练仍可继续。');
  g.sampling=true;g.busy=false;
  g.presenter=new RehabObservation.ObservationPresenter(event=>{g.j.observationSegments??=[];if(g.j.observationSegments.length<256){g.j.observationSegments.push({...event,source:'FORMAL_VISUAL_UI',time_basis:'frontend_monotonic_not_observed_hold',frontend_generation:generation,set_index:g.j.receipt.set_index,session_id:g.adapter.draft.session_id,source_epoch:g.adapter.snapshot.source_epoch,calibration_epoch:g.adapter.snapshot.snapshot?.calibration_epoch});persistPractice(g.j);}});
  g.notices??=new Set();g.presenter.notices=g.notices;
  g.presenter.begin(performance.now());g.view=g.presenter.view(performance.now());
  if(typeof RehabGuidance!=='undefined')g.guidance=RehabGuidance.app.open({owner_scope:g.capability.owner_scope,journey_id:g.j.receipt.journey_id,provider:g.capability.provider,source_context:g.capability.source_context,exercise_id:g.j.receipt.exercise_id,side:g.j.receipt.side,frontend_generation:generation},{isCurrent:()=>current()&&g.sampling,voiceEnabled:()=>g.panel.querySelector('#live-voice').checked,render:text=>{if(current())g.panel.querySelector('#live-cue').textContent=text;}});
 g.viewTimer=setInterval(()=>{if(current()&&g.sampling){g.view=g.presenter.view(performance.now());renderFormalPracticeState(g);if(!g.view.voice&&g.guidance)RehabGuidance.app.clear(g.guidance);}},250);
  await pumpFormalFrames(g.video,g.adapter,()=>current()&&g.sampling,async(item,roundtrip)=>{
   const s=item.snapshot,m=s?.metric?.metrics?.[s.protocol?.metric],cue=item.current_cue;
   if(item.persistence_state==='finalized'||item.run_state==='finishing'||item.run_state==='paused'||s?.training?.stage==='RESTING'||s?.training?.plan_complete===true){formalPracticeRelease(g,'original_measurement_boundary');void reconcileFormalPracticeCamera(g,item.run_state==='finishing'||item.persistence_state==='finalized');return false;}
   const usable=cue&&s&&cue.session_id===item.session_id&&cue.exercise_id===g.j.receipt.exercise_id&&cue.side===g.j.receipt.side&&cue.calibration_epoch===s.calibration_epoch&&cue.valid_phases?.includes(s.phase)&&cue.evidence_refs?.length&&cue.remaining_ttl_ms>roundtrip;
   g.view=g.presenter.receive({valid:m?.valid===true,summary:{phase:s?.phase,primary_metric:s?.protocol?.metric,metrics:s?.metric?.metrics,completed:s?.completed},cue:usable?cue:null},performance.now());renderFormalPracticeState(g);
   if(g.guidance){if(!usable||!g.view.voice)RehabGuidance.app.clear(g.guidance);else RehabGuidance.app.offer(g.guidance,{id:cue.cue_id,source:'FORMAL_CUE',text:cue.instruction,valid:true,remaining_ms:cue.remaining_ttl_ms-roundtrip,session_id:cue.session_id,exercise_id:cue.exercise_id,side:cue.side,epoch:s.calibration_epoch,phase:s.phase,evidence_refs:cue.evidence_refs,valid_phases:cue.valid_phases});}
   return true;
  });
 }catch(e){formalPracticeRelease(g,'camera_error');g.error=({NotAllowedError:'未获得相机授权，按动作说明继续即可。',NotFoundError:'未找到摄像头，当前跟练可以继续。',NotReadableError:'摄像头被占用，当前跟练可以继续。'})[e.name]||formalMessage(e);if(g.adapter&&formalPracticeScope(g)&&!g.adapter.draft.end_requested)void g.adapter.pause().catch(()=>{});}
 finally{g.busy=false;if(!g.sampling&&g.stream)formalPracticeRelease(g,'camera_stopped');formalPracticeRemember(g);renderFormalPracticeState(g);}
}
