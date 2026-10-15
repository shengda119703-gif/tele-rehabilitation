(function(root){
'use strict';
const copy=v=>JSON.parse(JSON.stringify(v));
const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
const scopeKey=(origin,scope)=>'ankang-formal-session-1:'+JSON.stringify([origin,scope.provider,scope.owner_scope,scope.participant_id,scope.source_context]);
function failure(message){return Error(message);}
class SessionAdapter{
 constructor({scope,origin,request,storage,key,create,draft=null,binding=null,isScopeCurrent=()=>true}){
  if(scope?.provider!=='hosted-rehab-v2-1'||scope.source_context!=='LIVE_CAMERA:SELF_USE'||!scope.owner_scope||!scope.participant_id)throw failure('当前环境不支持正式实时测量。');
  this.scope=copy(scope);this.origin=origin;this.request=request;this.storage=storage;this.key=key;this.isScopeCurrent=isScopeCurrent;
  this.storageKey=scopeKey(origin,scope);this.tail=Promise.resolve();this.snapshot=null;this.frameBusy=false;
  this.draft=draft?copy(draft):{version:1,scope:this.scope,origin,create:copy(create),binding:binding?copy(binding):null,session_id:null,revision:0,seq:-1,pending:null,end_requested:false,save_state:'LOCAL_DRAFT',commit:null};
  if(this.draft.version!==1||this.draft.origin!==origin||!same(this.draft.scope,this.scope)||!this.draft.create?.idempotency_key)throw failure('测量草稿的归属不一致。');
  this.persist();
 }
 persist(){try{
  if(this.draft.save_state==='MEMORY_ONLY')this.draft.save_state='LOCAL_DRAFT';
  const previous=JSON.parse(this.storage.getItem(this.storageKey)||'null');
  const records=previous?.version===2?previous.records:previous?.version===1?{[previous.create.idempotency_key]:previous}:{};
  records[this.draft.create.idempotency_key]=copy(this.draft);
  this.storage.setItem(this.storageKey,JSON.stringify({version:2,current:this.draft.create.idempotency_key,records}));this.durable=true;
 }catch{this.durable=false;if(['LOCAL_DRAFT','MEMORY_ONLY'].includes(this.draft.save_state))this.draft.save_state='MEMORY_ONLY';}}
 serial(fn){const operation=this.tail.then(fn);this.tail=operation.catch(()=>{});return operation;}
 send(route,options){
  // A queued old operation must never use the new person's current HTTP auth.
  // Retain its immutable payload and draft, but do not send it across a scope change.
  if(!this.isScopeCurrent())throw failure('本人或连接已变化，请返回原记录核对。');
  return this.request(route,options);
 }
 endpoint(suffix=''){if(!this.draft.session_id)throw failure('正在核对本次测量。');return '/rehab/v2/sessions/'+encodeURIComponent(this.draft.session_id)+suffix;}
 apply(item){
  const p=item?.frozen_plan?.plan,s=item?.source;
  if(!item?.session_id||item.owner!==this.scope.owner_scope||p?.participant_id!==this.scope.participant_id||s?.source_kind!=='LIVE_CAMERA'||s.usage_context!=='SELF_USE'||p?.submode!==this.draft.create.submode)throw failure('测量记录的归属不一致。');
  if(this.draft.session_id&&item.session_id!==this.draft.session_id)throw failure('测量记录的编号不一致。');
  if(this.draft.create.submode==='assessment'&&(p.exercise_id!==this.draft.create.exercise_id||p.side!==this.draft.create.side||p.view!==this.draft.create.view))throw failure('测量动作或机位不一致。');
  if(this.draft.create.submode==='training'&&(item.frozen_plan.plan_id!==this.draft.create.plan_id||item.frozen_plan.plan_revision!==this.draft.create.expected_plan_revision||item.frozen_plan.entry_key!==this.draft.create.entry_key))throw failure('测量安排已变化。');
  if(this.draft.create.submode==='training'){
   if(p.view!==this.draft.create.view)throw failure('测量机位不一致。');
   const b=this.draft.binding;
   if(b&&(p.exercise_id!==b.exercise_id||p.side!==b.side||p.view!==b.view||Object.entries(b.settings||{}).some(([k,v])=>!same(p[k],v))))throw failure('测量动作或原安排内容不一致。');
  }
  if(!Number.isInteger(item.revision)||item.revision<0)throw failure('测量状态暂未能核对。');
  if(item.revision<this.draft.revision)return this.snapshot;
  if(this.snapshot&&item.revision===this.draft.revision&&item.processed_last_seq<this.snapshot.processed_last_seq&&item.persistence_state!=='finalized')return this.snapshot;
  this.draft.session_id=item.session_id;this.draft.revision=item.revision;this.draft.seq=Math.max(this.draft.seq,item.accepted_last_seq??-1);this.snapshot=item;
  if(item.persistence_state==='finalized')this.draft.end_requested=true;
  this.persist();return item;
 }
 async createOrRead(){
  if(this.draft.session_id)return this.read();
  // Repeating this ORIGINAL POST is supported: server lookup precedes grants.
  // Never invent a new key after an unknown creation response.
  const item=await this.send('/rehab/v2/sessions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(this.draft.create)});
  return this.apply(item);
 }
 create(){return this.serial(()=>this.createOrRead());}
 async read(){return this.apply(await this.send(this.endpoint()));}
 async resolvePending(){
  const op=this.draft.pending;if(!op)return;
  const receipt=await this.send(this.endpoint('/'+op.kind),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(op.payload)});
  if(receipt.session_id!==this.draft.session_id)throw failure('测量操作的回执不一致。');
  if(op.kind==='finish'){
   if(!['finishing','finalized'].includes(receipt.status))throw failure('结束回执暂未能核对。');
   this.draft.save_state='ACCEPTED';this.draft.finish_receipt=copy(receipt);
  }else{
   if(receipt.operation!==op.kind||!Number.isInteger(receipt.revision))throw failure('测量控制回执不一致。');
   this.draft.revision=Math.max(this.draft.revision,receipt.revision);
  }
  this.draft.pending=null;this.persist();
 }
 async command(kind){
  await this.createOrRead();
  if(this.snapshot.persistence_state==='finalized'&&this.draft.pending?.kind!=='finish'){
   if(this.draft.pending){this.draft.last_superseded={...this.draft.pending,reason:'original_session_finalized'};this.draft.pending=null;this.persist();}
   return;
  }
  try{await this.resolvePending();}catch(e){
   if(e.status!==409||e.message!=='control_revision_conflict')throw e;
   // Original POST positively rejected this immutable revision. Query, retain
   // the rejected operation, and use a NEW key for the current explicit intent.
   await this.read();this.draft.last_superseded={...this.draft.pending,reason:'original_revision_rejected'};this.draft.pending=null;this.persist();
  }
  await this.read();
  if(this.snapshot.persistence_state==='finalized'||this.snapshot.run_state==='finishing')return;
  if(kind==='pause'&&this.snapshot.run_state==='paused')return;
  if(kind==='resume'&&this.snapshot.run_state!=='paused')return;
  this.draft.pending={kind,payload:{idempotency_key:this.key(),expected_revision:this.draft.revision,...(kind==='finish'?{reason:'user_stopped'}:{})}};this.persist();
  await this.resolvePending();await this.read();
 }
 pause(){return this.serial(()=>this.command('pause'));}
 resume(){return this.serial(async()=>{if(this.draft.end_requested)return;await this.command('resume');return this.read();});}
 finish(){
  // End intent is immediate and durable, independent of camera/native work.
  this.draft.end_requested=true;this.persist();
  return this.serial(async()=>{await this.command('finish');return this.reconcileCommit();});
 }
 async reconcileCommit(){
  const result=await this.send(this.endpoint('/commit'));
  if(result.session_id!==this.draft.session_id)throw failure('保存回执的归属不一致。');
  const receipt=result.receipt;
  if(result.persistence_state!=='finalized'||!receipt){this.draft.save_state='ACCEPTED';this.persist();return result;}
  if(receipt.session_id!==this.draft.session_id||receipt.status!=='finalized'||!receipt.commit_id||!receipt.visual_snapshot_digest||!Number.isInteger(receipt.completed_reps)||receipt.completed_reps<0)throw failure('正式保存回执暂未能核对。');
  await this.read();
  if(this.snapshot.persistence_state!=='finalized'||this.snapshot.canonical_commit?.commit_id!==receipt.commit_id||this.snapshot.canonical_commit?.visual_snapshot_digest!==receipt.visual_snapshot_digest||this.snapshot.snapshot?.completed!==receipt.completed_reps)throw failure('保存回执与最终测量不一致。');
  this.draft.commit=copy(receipt);this.draft.save_state='COMMITTED';this.draft.end_requested=true;this.persist();return result;
 }
 reconcile(){return this.serial(async()=>{await this.createOrRead();if(this.draft.end_requested){await this.command('finish');return this.reconcileCommit();}if(this.draft.pending)await this.command(this.draft.pending.kind);return this.read();});}
 async frame(blob){
  if(this.frameBusy||this.draft.end_requested||!this.draft.session_id||!this.snapshot||!['preparing','active','recovering'].includes(this.snapshot.run_state))return null;
  this.frameBusy=true;const seq=++this.draft.seq;this.persist();
  try{return await this.send(this.endpoint('/frames'),{method:'POST',headers:{'Content-Type':'image/jpeg','X-Rehab-Event-Id':this.key(),'X-Rehab-Seq':String(seq)},body:blob,timeoutMs:12000});}
  finally{this.frameBusy=false;}
 }
 export(){return JSON.stringify({kind:'ankang-formal-recovery-1',...copy(this.draft)},null,2);}
 static drafts(storage,origin,scope){try{const value=JSON.parse(storage.getItem(scopeKey(origin,scope))||'null');const rows=value?.version===2?Object.values(value.records).reverse():value?.version===1?[value]:[];return rows.filter(d=>d?.version===1&&d.origin===origin&&same(d.scope,scope));}catch{return [];}}
 static restore(storage,origin,scope,action=null){return this.drafts(storage,origin,scope).find(d=>{
  if(!action)return true;if(action.idempotency_key&&d.create.idempotency_key!==action.idempotency_key)return false;
  if(action.submode==='training')return d.create.submode==='training'&&(!action.plan_id||d.create.plan_id===action.plan_id)&&(!action.entry_key||d.create.entry_key===action.entry_key)&&(!action.expected_plan_revision||d.create.expected_plan_revision===action.expected_plan_revision);
  return d.create.submode==='assessment'&&d.create.exercise_id===action.exercise_id&&d.create.side===action.side;
 })||null;}
}
root.RehabFormal={SessionAdapter,scopeKey};
})(globalThis);
