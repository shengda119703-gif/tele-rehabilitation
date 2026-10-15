/* UI/audio scheduling only. No angle, count, eligibility or dose is produced. */
(function(root){
'use strict';
const POLICY=Object.freeze({version:'rehab-smooth-guidance-1',normalIntervalMs:6000,sameCueIntervalMs:10000,queueCapacity:1,tickMs:100,maxRememberedEvents:256,maxRememberedIssues:64});
const PRIORITY=Object.freeze({EXECUTION_STOP:100,USER_OPERATION:80,FORMAL_CUE:60,LIVE_PREVIEW:60,GUIDED_SCRIPT:40,ENCOURAGEMENT:20});
const bindingKey=b=>JSON.stringify([b.owner_scope,b.journey_id,b.provider,b.source_context,b.exercise_id,b.side]);
class AudioPort{
 constructor(host=root){this.host=host;this.serial=0;this.callback=null;this.nativeId=null;}
 prepare(){try{this.host.OfflineAndroid?.guidancePrepare?.();}catch{/* Text remains usable. */}}
 available(){try{const n=this.host.OfflineAndroid;if(n?.guidanceAvailable)return n.guidanceAvailable()===true;return !!(this.host.speechSynthesis&&this.host.SpeechSynthesisUtterance);}catch{return false;}}
 speak(text,done){
  if(!this.available())return false;
  const serial=++this.serial;this.callback=done;
  const finish=()=>{if(serial!==this.serial)return;this.callback=null;this.nativeId=null;done();};
  try{
   if(this.host.OfflineAndroid?.guidanceAvailable){this.nativeId=String(serial);this.host.OfflineAndroid.guidanceSpeak(this.nativeId,text);}
   else{const utterance=new this.host.SpeechSynthesisUtterance(text);utterance.lang='zh-CN';utterance.onend=finish;utterance.onerror=finish;this.host.speechSynthesis.cancel();this.host.speechSynthesis.speak(utterance);}
   return true;
  }catch{++this.serial;this.callback=null;this.nativeId=null;return false;}
 }
 nativeResult(id){if(String(id)!==this.nativeId)return;const done=this.callback;this.callback=null;this.nativeId=null;done?.();}
 cancel(){++this.serial;this.callback=null;this.nativeId=null;try{this.host.speechSynthesis?.cancel();}catch{}try{this.host.OfflineAndroid?.guidanceCancel?.();}catch{}}
}
class Scheduler{
 constructor({audio=new AudioPort(),now=()=>performance.now(),schedule=(fn,ms)=>setTimeout(fn,ms),unschedule=id=>clearTimeout(id)}={}){this.audio=audio;this.now=now;this.schedule=schedule;this.unschedule=unschedule;this.channel=null;this.active=null;this.pending=null;this.timer=null;this.serial=0;this.lastVoice=-Infinity;this.ledgers=new Map();this.stats={offered:0,spoken:0,expired:0,cancelled:0,max_pending:0};}
 open(binding,{isCurrent=()=>true,voiceEnabled=()=>false,render=()=>{},fallback='按动作说明继续练习'}={}){
  if(!binding||['owner_scope','journey_id','provider','source_context','exercise_id'].some(k=>typeof binding[k]!=='string'||!binding[k]))throw Error('Guidance scope missing');
  this.cancelAll();const key=bindingKey(binding);
  let ledger=this.ledgers.get(key);if(!ledger){ledger={events:new Set(),issues:new Set(),texts:new Map()};this.ledgers.set(key,ledger);if(this.ledgers.size>16)this.ledgers.delete(this.ledgers.keys().next().value);}
  const token=Object.freeze({id:++this.serial});this.channel={token,binding:Object.freeze({...binding}),isCurrent,voiceEnabled,render,fallback,ledger,epoch:null,phase:null,view:null};return token;
 }
 current(token){const c=this.channel;if(!c||c.token!==token)return false;try{return c.isCurrent()===true;}catch{return false;}}
 valid(event){const c=this.channel;if(!c||!this.current(event.token)||this.now()>=event.expiresAt||event.epoch!==c.epoch||event.phase!==c.phase)return false;
  if(event.source==='FORMAL_CUE')return event.session_id===c.binding.journey_id&&event.exercise_id===c.binding.exercise_id&&event.side===c.binding.side&&Array.isArray(event.evidence_refs)&&event.evidence_refs.length>0&&event.valid_phases?.includes(c.phase);
  return true;
 }
 show(text){const c=this.channel;if(c&&this.current(c.token)&&c.view!==text){c.view=text;c.render(text);}}
 stopActive(){if(!this.active)return;this.active=null;++this.serial;this.audio.cancel();this.stats.cancelled++;}
 clear(token,text){if(this.channel?.token!==token)return;this.stopActive();this.pending=null;this.viewEvent=null;this.cancelTimer();if(text!==undefined)this.show(text);}
 close(token){if(this.channel?.token!==token)return;this.cancelAll();}
 cancelTimer(){if(this.timer!==null)this.unschedule(this.timer);this.timer=null;}
 cancelAll(){this.cancelTimer();this.active=null;this.pending=null;this.viewEvent=null;this.channel=null;++this.serial;this.audio.cancel();}
 offer(token,input){
  if(!this.current(token))return false;this.stats.offered++;
  const c=this.channel,source=input?.source,ttl=input?.remaining_ms;
  if(!Object.hasOwn(PRIORITY,source)||typeof input.text!=='string'||!input.text.trim()||input.text.length>500||!Number.isFinite(ttl)||ttl<=0||input.valid!==true){this.clear(token,c.fallback);return false;}
  const epoch=input.epoch??null,phase=input.phase??null;
  if(c.epoch!==epoch||c.phase!==phase){this.stopActive();this.pending=null;c.epoch=epoch;c.phase=phase;}
  const event={...input,token,epoch,phase,priority:PRIORITY[source],text:input.text.trim(),expiresAt:this.now()+Math.min(ttl,source==='USER_OPERATION'||source==='EXECUTION_STOP'?6000:1500)};
  if(typeof event.id!=='string'||!event.id||!this.valid(event)){this.clear(token,c.fallback);return false;}
  if(this.active?.priority>event.priority&&this.valid(this.active))return false;
  this.show(event.text);
  // Re-observing the SAME current preview cue renews its UI lease; a formal
  // event cannot outlive the server's newly supplied remaining lifetime.
  if(this.active&&this.active.id===event.id&&this.active.text===event.text){this.active.expiresAt=event.expiresAt;this.arm();return true;}
  if(this.active&&this.active.text!==event.text)this.stopActive();
  if(!c.voiceEnabled()){this.stopActive();this.pending=null;this.armView(event);return true;}
  if(event.source!=='LIVE_PREVIEW'&&c.ledger.events.has(event.id)){this.pending=null;this.armView(event);return true;}
  if(event.notice===true&&(c.ledger.issues.has(event.issue)||c.ledger.issues.size>=POLICY.maxRememberedIssues)){this.pending=null;this.armView(event);return true;}
  if(this.pending?.priority>event.priority&&this.valid(this.pending))return false;
  this.pending=event;this.stats.max_pending=Math.max(this.stats.max_pending,1);this.audio.prepare();this.pump();return true;
 }
 armView(event){this.viewEvent=event;this.arm();}
 arm(){this.cancelTimer();if(this.channel&&(this.active||this.pending||this.viewEvent)){this.timer=this.schedule(()=>{this.timer=null;this.pump();},POLICY.tickMs);}}
 pump(){
  if(!this.channel)return;
  const c=this.channel;if(!this.current(c.token)){this.cancelAll();return;}
  if(this.active&&(!this.valid(this.active)||!c.voiceEnabled()))this.stopActive();
  if(this.pending&&(!this.valid(this.pending)||!c.voiceEnabled())){this.stats.expired++;this.pending=null;}
  if(this.viewEvent&&!this.valid(this.viewEvent)){this.viewEvent=null;if(!this.pending&&!this.active)this.show(c.fallback);}
  const e=this.pending;
  if(e){this.viewEvent=e;const last=c.ledger.texts.get(e.text)??-Infinity,urgent=e.priority>=PRIORITY.USER_OPERATION;
   if((urgent||this.now()-this.lastVoice>=POLICY.normalIntervalMs)&&this.now()-last>=POLICY.sameCueIntervalMs&&!this.active&&this.audio.available()){
    this.pending=null;const serial=++this.serial;this.active=e;
    const accepted=this.audio.speak(e.text,()=>{if(this.serial!==serial||this.channel!==c||this.active!==e||!this.current(e.token))return;this.active=null;this.pump();});
    if(accepted){this.lastVoice=this.now();this.stats.spoken++;if(e.source!=='LIVE_PREVIEW')c.ledger.events.add(e.id);if(c.ledger.events.size>POLICY.maxRememberedEvents)c.ledger.events.delete(c.ledger.events.values().next().value);c.ledger.texts.set(e.text,this.now());if(c.ledger.texts.size>128)c.ledger.texts.delete(c.ledger.texts.keys().next().value);if(e.notice===true)c.ledger.issues.add(e.issue);}
    else{this.active=null;this.pending=e;}
   }
  }
  this.arm();
 }
 snapshot(){return {policy:POLICY.version,active:!!this.active,pending:this.pending?1:0,scope_current:!!this.channel&&this.current(this.channel.token),...this.stats};}
}
const api={POLICY,PRIORITY,Scheduler,AudioPort};
if(typeof root.document!=='undefined'){
 api.app=new Scheduler();api.nativeResult=id=>api.app.audio.nativeResult(id);
 root.document.addEventListener('visibilitychange',()=>{if(root.document.hidden)api.app.cancelAll();});root.addEventListener?.('pagehide',()=>api.app.cancelAll());
}
root.RehabGuidance=api;if(typeof module!=='undefined')module.exports=api;
})(globalThis);
