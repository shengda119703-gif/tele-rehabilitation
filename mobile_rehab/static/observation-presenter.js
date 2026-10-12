/* Presentation-only tolerance. Engine readiness/counts are never rewritten. */
(function(root){
'use strict';
const POLICY=Object.freeze({version:'rehab-smooth-ui-1',readySoftWaitMs:6000,gapSilentMs:1500,gapNoticeMs:4000,gapGuidedMs:5000,recoveryStableMs:1500});
const READY=new Set(['REST','RAISING','PEAK_OR_HOLD','LOWERING','SEATED_READY','RISING','STANDING_REACHED','rest','outbound','turn','return']);
class ObservationPresenter{
 constructor(onTransition=()=>{}){this.transition=onTransition;this.mode='GUIDED';this.state='DISABLED';this.started=null;this.lastFrame=null;this.lastValid=null;this.stableSince=null;this.count=null;this.angle=null;this.cue='';this.phase=null;this.notices=new Set();}
 setMode(mode,reason,now){if(this.mode===mode)return;const previous=this.mode;this.mode=mode;this.transition({from:previous,to:mode,reason,at:now,source:'LIVE_PREVIEW',time_basis:'frontend_monotonic_not_observed_hold'});}
 begin(now){this.started=now;this.lastFrame=null;this.lastValid=null;this.stableSince=null;this.count=null;this.angle=null;this.phase=null;this.cue='';this.state='STARTING';this.setMode('GUIDED','new_preview_boundary',now);}
 receive(data,now){
  if(this.started===null)return;
  const phase=data.summary?.phase||data.cue?.status;
  const angle=data.summary?.metrics?.[data.summary?.primary_metric]?.value;
  const ready=data.valid===true&&READY.has(phase)&&typeof angle==='number'&&Number.isFinite(angle);
  // Frame gaps are not a continuous recovery interval, even when both end
  // frames happen to be valid. This does not extend the engine's 500ms gate.
  if(this.lastFrame!==null&&now-this.lastFrame>=POLICY.gapSilentMs)this.stableSince=null;
  this.lastFrame=now;this.phase=phase||null;
  if(ready){
   this.lastValid=now;this.stableSince??=now;this.angle=angle;this.cue=data.cue?.instruction||'';
   const count=data.summary?.completed;
   if(Number.isInteger(count)&&count>=0&&(this.count===null||count>=this.count))this.count=count;
   if(now-this.stableSince>=POLICY.recoveryStableMs){this.state='TRACKING';this.setMode('AUTO_ASSISTED','current_engine_phase_stable',now);}
  }else{this.stableSince=null;this.angle=null;}
  return this.view(now);
 }
 disable(now,reason='preview_stopped'){this.state='DISABLED';this.started=null;this.angle=null;this.stableSince=null;this.setMode('GUIDED',reason,now);}
 view(now){
  if(this.state==='DISABLED')return{state:this.state,mode:this.mode,count:this.count,angle:null,cue:'自动指导已关闭，仍可按安排练习',voice:false};
  const gap=this.lastValid===null?null:Math.max(0,now-this.lastValid);
  let cue=this.cue||'按动作说明练习，正在连接自动指导';
  if(gap!==null&&gap>=POLICY.gapGuidedMs){this.state='LOST';this.setMode('GUIDED','visual_gap',now);cue='已继续陪练，部分动作未自动记录';}
  else if(gap!==null&&gap>=POLICY.gapSilentMs){this.state='WEAK';cue=gap>=POLICY.gapNoticeMs?'刚才一小段没看清，继续练习即可':'按安排继续练习';}
  else if(this.lastValid===null&&now-this.started>=POLICY.readySoftWaitMs){this.state='STARTING';this.setMode('GUIDED','ready_soft_wait',now);cue='先按示范练习，自动指导稍后接上';}
  else if(this.mode==='GUIDED')cue='按动作说明练习，正在准备自动指导';
  const angle=gap!==null&&gap<POLICY.gapSilentMs?this.angle:null;
  const issue=this.state==='LOST'?'visual_gap':this.state==='WEAK'&&gap>=POLICY.gapNoticeMs?'visual_gap':this.lastValid===null&&now-this.started>=POLICY.readySoftWaitMs?'ready_soft_wait':null;
  const activeNotice=issue!==null&&!this.notices.has(issue);if(issue)this.notices.add(issue);
  return{state:this.state,mode:this.mode,count:this.count,angle,cue,activeNotice,voice:this.mode==='AUTO_ASSISTED'&&this.state==='TRACKING'&&angle!==null};
 }
}
root.RehabObservation={POLICY,ObservationPresenter};
if(typeof module!=='undefined')module.exports=root.RehabObservation;
})(globalThis);
