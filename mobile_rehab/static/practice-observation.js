'use strict';
// The original /live adapter is a PREVIEW, never a measured training commit.
// Keep its identity and ephemeral count outside the saved practice/dose fields.
function mountPracticeObservation(j,area,retained=null){
 if(j.ended||typeof RehabObservation==='undefined')return;
 const panel=retained||document.createElement('details');panel.id='practice-observation';
 if(!retained){panel.innerHTML='<summary>摄像头自动指导（选用）</summary>'+liveMarkup();}
 area.appendChild(panel);
 $('#live-count').textContent=j.previewCount===undefined?'—':'预览识别 '+j.previewCount+' 次 · 未保存';
 $('#live-facing').value=liveFacing;
 if(j.context.provider==='phone-local-1')$('#live-consent').parentElement.lastChild.textContent='同意在手机上分析实时画面，不上传、不保存画面。';
 $('#live-start').onclick=()=>{
  if(!currentPractice(j,area)||!j.running||j.ended||j.receipt?.execution_allowed!==true){$('#live-status').textContent='请先继续当前允许的练习。';return;}
  if($('#live-consent').checked)j.previewWanted=true;
  const consumer=practiceObservationConsumer(j,area,panel);void startLive(consumer);
 };
 $('#live-stop').onclick=()=>{j.previewWanted=false;stopLive('user_disabled_preview');};
 if(!window.isSecureContext||!navigator.mediaDevices?.getUserMedia){$('#live-start').disabled=true;$('#live-status').textContent='当前地址不能使用实时相机，可按动作说明继续练习。';}
}
function practiceObservationConsumer(j,area,panel){
 const isCurrent=()=>currentPractice(j,area)&&j.running&&!j.ended&&$('#practice-observation')===panel;
 let timer=null,presenter=null;
 const render=view=>{
  if(!isCurrent())return view;
  j.observationView=view;
  $('#live-cue').textContent=view.cue;$('#live-angle').textContent=view.angle===null?'—':number(view.angle,'°');
  if(view.count!==null){j.previewCount=view.count;$('#live-count').textContent='预览识别 '+view.count+' 次 · 未保存';}
  $('#live-status').textContent=view.mode==='AUTO_ASSISTED'?'实时指导中 · 测量预览不计入计划':'按安排继续练习';
  if(!view.voice&&'speechSynthesis'in window)speechSynthesis.cancel();
  return view;
 };
 const consumer={journey:j,isCurrent,
  connected(session){
   ++j.previewGeneration;j.previewCount=undefined;j.observationView=null;
   $('#live-count').textContent='—';
   const context={provider:j.context.provider,source_context:j.context.provider==='phone-local-1'?'PHONE_LOCAL:SELF_USE':'LIVE_CAMERA:SELF_USE',frontend_generation:j.previewGeneration};
   presenter=new RehabObservation.ObservationPresenter(change=>{
    // Small client metadata only; not evidence of effective observed time.
    j.observationSegments??=[];
    if(j.observationSegments.length>=256){stopLive('client_segment_budget');return;}
    j.observationSegments.push({...change,at:j.elapsed,time_basis:'frontend_active_page_time_not_observed_hold',set_index:1,context,preview_id:session.id||null});persistPractice(j);
   });
   presenter.begin(performance.now());
   timer=setInterval(()=>{if(isCurrent())render(presenter.view(performance.now()));else{clearInterval(timer);}},250);
  },
  receive(data){return render(presenter.receive(data,performance.now()));},
  stopped(reason){
   clearInterval(timer);presenter?.disable(performance.now(),reason);persistPractice(j);
   if($('#practice-observation')===panel&&!j.ended){$('#live-cue').textContent='自动指导已关闭，仍可按安排练习';$('#live-angle').textContent='—';}
  },
  error(message){j.previewWanted=false;if($('#practice-observation')===panel)$('#live-status').textContent=message+' 可按动作说明继续练习。';}
 };
 return consumer;
}
function stopPracticeObservation(j){if(liveSession?.consumer?.journey===j)stopLive('practice_paused');}
async function resumePracticeObservation(j,area){
 if(!j.previewWanted||j.previewResumeRequest)return;
 // One explicit Continue intent may restore this journey's opted-in preview.
 // Wait for its original release/permission, never bypass an uncertain close.
 const waits=[liveCameraRequest,liveCreateRequest,liveCloseRequest].filter(Boolean);
 const pending=Promise.allSettled(waits);j.previewResumeRequest=pending;
 try{await pending;if(!currentPractice(j,area)||!j.running||j.ended||!j.previewWanted||liveSession||liveClosingSession)return;
  const start=$('#live-start');if(start&&!start.disabled)start.onclick();
 }finally{if(j.previewResumeRequest===pending)j.previewResumeRequest=null;}
}
