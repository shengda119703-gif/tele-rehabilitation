/* Original v2 feedback is separate from the immutable visual commit. */
(function(root){
'use strict';
const copy=v=>JSON.parse(JSON.stringify(v));
const fields=['pain','fatigue','reason','notes'];
const reasons=['not_recorded','completed','discomfort','fatigue','time','technical','other'];
function values(v){
 if(!v||typeof v!=='object'||['pain','fatigue'].some(k=>v[k]!==null&&(!Number.isInteger(v[k])||v[k]<0||v[k]>10))||!reasons.includes(v.reason)||typeof v.notes!=='string'||v.notes.trim().length>1000)throw Error('请填写0–10的整数，或留空。备注最多1000字。');
 return Object.fromEntries(fields.map(k=>[k,k==='notes'?v[k].trim():v[k]]));
}
const equal=(a,b)=>fields.every(k=>a?.[k]===b?.[k]);
const empty=()=>({pain:null,fatigue:null,reason:'not_recorded',notes:''});
class FeedbackAdapter{
 constructor({scope,origin,sessionId,request,storage,key,isScopeCurrent=()=>true}){
  if(scope?.provider!=='hosted-rehab-v2-1'||scope.source_context!=='LIVE_CAMERA:SELF_USE'||!scope.owner_scope||!scope.participant_id||typeof sessionId!=='string'||!sessionId||sessionId.length>128)throw Error('感受记录的归属不一致。');
  this.scope=copy(scope);this.origin=origin;this.sessionId=sessionId;this.request=request;this.storage=storage;this.key=key;this.isScopeCurrent=isScopeCurrent;this.tail=Promise.resolve();this.snapshot=null;this.conflict=false;this.durable=false;
  this.storageKey='ankang-formal-feedback-1:'+JSON.stringify([origin,scope.provider,scope.owner_scope,scope.participant_id,scope.source_context,sessionId]);
  this.draft={version:1,scope:this.scope,origin,session_id:sessionId,values:null,pending:null,superseded:[],acknowledged:null};
  try{this.originalRaw=storage.getItem(this.storageKey);const saved=JSON.parse(this.originalRaw||'null');if(saved&&!(saved.version===1&&saved.origin===origin&&saved.session_id===sessionId&&JSON.stringify(saved.scope)===JSON.stringify(this.scope)))throw Error('incompatible original feedback');if(saved){
   if(saved.values)values(saved.values);
   if(!Array.isArray(saved.superseded)||saved.superseded.length>32)throw Error('invalid rejected feedback operations');
   if(saved.form&&(!['pain','fatigue','reason','notes'].every(k=>typeof saved.form[k]==='string')||!reasons.includes(saved.form.reason)))throw Error('invalid original feedback form');
   if(saved.acknowledged){const r=saved.acknowledged.receipt;values(r);if(typeof saved.acknowledged.idempotency_key!=='string'||!saved.acknowledged.idempotency_key||r.session_id!==sessionId||r.record_origin!=='self_report'||!Number.isInteger(r.revision)||r.revision<1)throw Error('invalid original feedback receipt');}
   if(saved.pending){values(saved.pending.feedback);if(typeof saved.pending.idempotency_key!=='string'||!saved.pending.idempotency_key||!Number.isInteger(saved.pending.expected_revision)||saved.pending.expected_revision<0)throw Error('invalid pending feedback');}
   this.draft=saved;
  }}catch{/* Keep unreadable storage in place; do not silently overwrite it. */this.restoreFailed=true;}
  if(!this.restoreFailed)this.persist();
 }
 persist(){try{if(this.restoreFailed)throw Error('unreadable original draft');this.storage.setItem(this.storageKey,JSON.stringify(this.draft));this.durable=true;}catch{this.durable=false;}}
 send(route,opts){if(!this.isScopeCurrent())throw Error('本人或连接已变化，请返回原记录核对。');return this.request(route,opts);}
 endpoint(){return '/rehab/v2/sessions/'+encodeURIComponent(this.sessionId);}
 async read(){
  const item=await this.send(this.endpoint()),p=item?.frozen_plan?.plan;
  if(item.session_id!==this.sessionId||item.owner!==this.scope.owner_scope||p?.participant_id!==this.scope.participant_id||item.source?.source_kind!=='LIVE_CAMERA'||item.source.usage_context!=='SELF_USE'||!Number.isInteger(item.feedback_revision)||item.feedback_revision<0)throw Error('原测量或感受版本暂未能核对。');
  if(item.persistence_state!=='finalized')throw Object.assign(Error('测量正在保存，感受可以先填写。'),{code:'feedback_waits_for_measurement_commit'});
  if(item.canonical_commit?.session_id!==this.sessionId)throw Error('原测量或感受版本暂未能核对。');
  if(item.feedback_revision>0){const v=item.latest_feedback;if(v?.session_id!==this.sessionId||v.revision!==item.feedback_revision||v.record_origin!=='self_report')throw Error('感受回执暂未能核对。');values(v);}
  const floor=this.draft.acknowledged?.receipt?.revision||0;
  if(item.feedback_revision<floor&&(!this.snapshot||this.snapshot.feedback_revision<floor))throw Error('感受回执已收到，最新记录仍待核对。');
  if(!this.snapshot||item.feedback_revision>=this.snapshot.feedback_revision)this.snapshot=item;
  return this.snapshot;
 }
 currentValues(){return this.snapshot?.feedback_revision>0?values(this.snapshot.latest_feedback):empty();}
 edit(v){if(this.draft.pending)throw Error('请先核对上次感受的保存状态。');this.draft.values=values(v);this.persist();}
 stage(v){
  if(!this.isScopeCurrent())throw Error('本人或连接已变化，请返回原记录核对。');if(this.restoreFailed)throw Error('原感受草稿未能读取，请先导出恢复内容。');if(!this.snapshot)throw Error('请先读取原感受。');if(this.draft.pending)throw Error('请先核对原操作。');
  const next=values(v);if(equal(next,empty())&&this.snapshot.feedback_revision===0)return false;
  if(this.snapshot.feedback_revision>0&&equal(next,this.currentValues()))return false;
  this.draft.values=next;this.draft.pending={idempotency_key:this.key(),expected_revision:this.snapshot.feedback_revision,feedback:copy(next)};this.conflict=false;this.persist();return true;
 }
 reconcile(){const operation=this.tail.then(()=>this.resolve());this.tail=operation.catch(()=>{});return operation;}
 async resolve(){
  await this.read();const pending=this.draft.pending;if(!pending)return this.snapshot;
  try{
   // Original service looks up this immutable operation before revision checks.
   const receipt=await this.send(this.endpoint()+'/feedback',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(pending)});
   if(receipt?.session_id!==this.sessionId||receipt.revision!==pending.expected_revision+1||receipt.record_origin!=='self_report'||!equal(values(receipt),pending.feedback))throw Error('感受保存回执暂未能核对。');
   this.draft.acknowledged={idempotency_key:pending.idempotency_key,receipt:copy(receipt)};this.draft.pending=null;this.draft.values=null;this.draft.form=null;this.conflict=false;this.persist();
   await this.read();return this.snapshot;
  }catch(error){
   if(error.status===409&&error.message==='feedback_revision_conflict'){
    await this.read();
    if(equal(this.currentValues(),pending.feedback)){
     // The current authoritative values match, but this rejected operation did not commit.
     this.rememberRejected();this.draft.pending=null;this.draft.values=null;this.draft.form=null;this.conflict=false;this.persist();return this.snapshot;
    }
    this.conflict=true;this.persist();
   }
   throw error;
  }
 }
 useLatest(){if(!this.conflict)throw Error('请先核对原感受。');this.rememberRejected();this.draft.pending=null;this.draft.values=null;this.draft.form=null;this.conflict=false;this.persist();}
 replace(){if(!this.conflict||!this.draft.pending)throw Error('请先核对原感受。');const next=copy(this.draft.pending.feedback);this.rememberRejected();this.draft.pending=null;this.conflict=false;return this.stage(next);}
 rememberRejected(){if(this.draft.pending){this.draft.superseded.push({...copy(this.draft.pending),reason:'original_revision_rejected'});if(this.draft.superseded.length>32)this.draft.superseded.shift();}}
 export(){return JSON.stringify({kind:'ankang-formal-feedback-recovery-1',...copy(this.draft),...(this.restoreFailed?{unreadable_original_draft:this.originalRaw}:{})},null,2);}
}
root.RehabFormalFeedback={FeedbackAdapter,values,equal,empty};
})(globalThis);

function mountFormalFeedback(item,area,capability,generation,isPageCurrent=null){
 const owner=state.uploadOwnerGeneration||0,panel=document.createElement('section');panel.className=area.classList.contains('card')?'care-form':'card care-form';panel.id='formal-feedback';area.appendChild(panel);
 const scopeCurrent=()=>{const c=formalReadCapability();return owner===(state.uploadOwnerGeneration||0)&&c?.provider===capability.provider&&c.owner_scope===capability.owner_scope&&c.participant_id===capability.participant_id&&c.source_context===capability.source_context;};
 const f={panel,area,scopeCurrent,current:()=>scopeCurrent()&&(isPageCurrent?isPageCurrent():generation===formalPageGeneration&&$('#formal-record')===area)&&area.contains(panel)&&$('#formal-feedback')===panel,busy:false,message:null};
 f.adapter=new RehabFormalFeedback.FeedbackAdapter({scope:capability,origin:location.origin,sessionId:item.session_id,request:api,storage:localStorage,key:newUploadOperation,isScopeCurrent:scopeCurrent});
 drawFormalFeedback(f);void reconcileFormalFeedback(f);return f;
}
function drawFormalFeedback(f){
 if(!f.current())return;
 const a=f.adapter,known=!!a.snapshot,saved=known&&a.snapshot.feedback_revision>0,pending=!!a.draft.pending,v=a.draft.values||a.currentValues();
 const d=a.draft.form||{pain:v.pain===null?'':String(v.pain),fatigue:v.fatigue===null?'':String(v.fatigue),reason:v.reason,notes:v.notes};
 f.panel.innerHTML='<h2>本次感受</h2><p id="formal-feedback-status" role="status">'+esc(f.message||(f.busy?'正在核对感受…':pending?'感受保存待核对；测量结果已保存。':saved?'感受已保存。':'选填，可以稍后填写。'))+(!a.durable?' 填写仅在当前页面，请先导出。':'')+'</p>'
  +'<label>疼痛（0–10）<input id="formal-feedback-pain" type="number" min="0" max="10" step="1" placeholder="未填写"></label><label>疲劳（0–10）<input id="formal-feedback-fatigue" type="number" min="0" max="10" step="1" placeholder="未填写"></label>'
  +'<label>结束原因<select id="formal-feedback-reason">'+[['not_recorded','未填写'],['completed','按安排结束'],['discomfort','出现不适'],['fatigue','感到疲劳'],['time','时间安排'],['technical','设备或识别问题'],['other','其他']].map(([k,t])=>'<option value="'+k+'">'+t+'</option>').join('')+'</select></label><label>备注<textarea id="formal-feedback-notes" maxlength="1000" placeholder="选填"></textarea></label>'
  +'<div class="live-controls"><button class="primary" id="formal-feedback-save">'+(pending?'核对保存':!known?'重试读取':saved?'保存修改':'保存感受')+'</button><button class="secondary" id="formal-feedback-later">稍后填写</button></div>'
  +(a.conflict?'<p id="formal-feedback-latest"></p><button class="secondary" id="formal-feedback-use-latest">使用最新内容</button><button class="secondary" id="formal-feedback-replace">保存我的填写</button>':'')
  +(!a.durable?'<button class="secondary" id="formal-feedback-export">导出填写内容</button>':'');
 const raw=()=>Object.fromEntries(['pain','fatigue','reason','notes'].map(k=>[k,$('#formal-feedback-'+k).value]));
 for(const k of ['pain','fatigue','reason','notes']){const input=$('#formal-feedback-'+k);input.value=d[k];input.disabled=pending;input.oninput=()=>{if(!f.current())return;a.draft.form=raw();a.persist();};}
 const submit=$('#formal-feedback-save');submit.disabled=f.busy||a.conflict;
 submit.onclick=()=>{if(!f.current()||f.busy)return;if(pending||!known){void reconcileFormalFeedback(f);return;}try{const r=raw(),v={pain:r.pain===''?null:Number(r.pain),fatigue:r.fatigue===''?null:Number(r.fatigue),reason:r.reason,notes:r.notes};if(!a.stage(v)){f.message=saved?'没有新的修改。':'没有填写感受，可以稍后再填。';drawFormalFeedback(f);return;}void reconcileFormalFeedback(f);}catch(e){f.message=e.message;drawFormalFeedback(f);}};
 $('#formal-feedback-later').onclick=()=>{if(f.current()){a.persist();navigate('plan');}};
 if(a.conflict){const latest=a.currentValues();$('#formal-feedback-latest').textContent='疼痛 '+(latest.pain??'未填')+' · 疲劳 '+(latest.fatigue??'未填')+' · '+(latest.notes||'无备注');$('#formal-feedback-use-latest').onclick=()=>{if(!f.current()||f.busy)return;a.useLatest();f.message='已读取最新感受。';drawFormalFeedback(f);};$('#formal-feedback-replace').onclick=()=>{if(!f.current()||f.busy)return;try{a.replace();void reconcileFormalFeedback(f);}catch(e){f.message=e.message;drawFormalFeedback(f);}};}
 if($('#formal-feedback-export'))$('#formal-feedback-export').onclick=()=>{if(f.current())formalExport({adapter:a});};
}
async function reconcileFormalFeedback(f){
 if(!f.current()||f.busy)return;f.busy=true;f.message=null;drawFormalFeedback(f);
 try{await f.adapter.reconcile();f.message=f.adapter.snapshot.feedback_revision>0?'感受已保存。':'选填，可以稍后填写。';}
 catch(e){f.message=f.adapter.conflict?'另一处更新了感受，你的填写仍保留。':f.adapter.draft.pending?'感受保存待核对；测量结果已保存。':e.message;}
 finally{f.busy=false;drawFormalFeedback(f);}
}
