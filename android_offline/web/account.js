(function(root){
'use strict';
const PS=root.PhoneStore,ORIGIN=root.AnkangBrowserAccount?.origin||'https://139.224.216.18',UUID=/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/;
const pending=new Map(),pageNonce=crypto.randomUUID();let sequence=0,uploading=null,scheduled=null,autoRunning=false;
function identity(){if(root.AnkangBrowserAccount)return root.AnkangBrowserAccount.identity();const text=root.OfflineAndroid?.accountIdentity?.();return text?JSON.parse(text):null;}
function login(){return root.AnkangBrowserAccount?root.AnkangBrowserAccount.login():root.OfflineAndroid.accountLogin();}
function validateIdentity(value){if(!value||value.origin!==ORIGIN||value.role!=='PATIENT'||!UUID.test(value.patient_id)||!UUID.test(value.account_id)||typeof value.username!=='string')throw Error('请重新登录云账号');return value;}
async function activate(value){
 validateIdentity(value);const old=root.PhoneLocal?.store;if(root.PhoneMotion?.active)throw Error('请先结束当前分析');if(old)await old.tail;
 // Existing personal records remain where they are. Binding requires a separate explicit confirmation.
 const key=PS.CLOUD_PREFIX+value.patient_id,store=new PS.Store(localStorage,key);
 store.change(v=>{if(v.fixture||v.owner!==value.patient_id||v.cloudIdentity&&(v.cloudIdentity.patient_id!==value.patient_id||v.cloudIdentity.account_id!==value.account_id))throw Error('原档案归属不一致');v.cloudIdentity=structuredClone(value);});localStorage.setItem(PS.ACTIVE_KEY,key);localStorage.setItem('ankang-contact-open','yes');if(root.location)root.location.href='/';
}
function scope(store,requireConsent=false){
 store.assertCurrent?.();
 const value=validateIdentity(identity()),v=store.value,b=v.cloudBinding;
 if(v.fixture||!b||b.patient_id!==value.patient_id||b.owner!==v.owner||v.cloudIdentity?.account_id!==value.account_id||PS.cloudKey(store.key)&&store.key!==PS.CLOUD_PREFIX+value.patient_id)throw Error('请确认当前本人档案与云账号绑定，展示档案不上传');
 if(requireConsent&&!v.cloudConsent)throw Error('本人康复记录自动同步尚未开启');return value;
}
async function bind(store,enabled=true){const value=validateIdentity(identity());await store.serial(()=>store.change(v=>{if(v.fixture||v.cloudBinding&&v.cloudBinding.patient_id!==value.patient_id)throw Error('该本机档案属于其他云账号，请打开独立本人档案');v.cloudIdentity=structuredClone(value);v.cloudBinding={patient_id:value.patient_id,owner:v.owner};v.cloudConsent=enabled;}));return value;}
function request(action,value,body={}){
 validateIdentity(value);const current=identity();if(!current||current.patient_id!==value.patient_id||current.account_id!==value.account_id)return Promise.reject(Error('账号已变化，请重新打开联系康复医师'));
 if(root.AnkangBrowserAccount)return root.AnkangBrowserAccount.request(action,value,body);
 if(!root.OfflineAndroid?.accountRequest)return Promise.reject(Error('此功能需要新版 APK'));
 return new Promise((resolve,reject)=>{const id=pageNonce+':'+String(++sequence),timer=setTimeout(()=>{pending.delete(id);reject(Error('云回复未收到，记录保留；可以重试'));},45000);pending.set(id,{resolve,reject,timer,patient_id:value.patient_id,account_id:value.account_id,action});try{root.OfflineAndroid.accountRequest(id,action,JSON.stringify({...body,patient_id:value.patient_id}));}catch(e){clearTimeout(timer);pending.delete(id);reject(e);}});
}
function reply(id,status,text){const call=pending.get(id);if(!call)return;pending.delete(id);clearTimeout(call.timer);try{const raw=identity(),loggedOut=call.action==='logout'&&status>=200&&status<300&&raw===null,current=loggedOut?null:validateIdentity(raw);if(!loggedOut&&(current.patient_id!==call.patient_id||current.account_id!==call.account_id))throw Error('账号已变化，旧回复未显示，请重新打开联系康复医师');const result=JSON.parse(text);if(status<200||status>=300){const error=Error(result.message||'云操作未完成');error.status=status;error.code=result.code;throw error;}call.resolve(result);}catch(e){call.reject(e);}}
function canonical(v){if(v===null||typeof v!=='object')return JSON.stringify(v);if(Array.isArray(v))return '['+v.map(canonical).join(',')+']';return '{'+Object.keys(v).sort().filter(k=>v[k]!==undefined).map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}';}
async function hash(text){const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text));return [...new Uint8Array(bytes)].map(x=>x.toString(16).padStart(2,'0')).join('');}
function jobPayload(job,label=null){const report=job.result?.local_report;if(job.state!=='done'||job.measurement_version!=='android-local-projection-1'||!report||job.synthetic||job.fixture||job.result.synthetic||job.result.fixture||report.synthetic||report.fixture)throw Error('仅上传已保存本人评估和训练结果');return {title:label||job.result.spec?.label||job.exercise,kind:job.mode,result:{id:job.id,exercise_id:job.exercise,side:job.side,measurement_version:job.measurement_version,source_kind:'REPLAY_FILE',usage_context:'SELF_USE',end_utc:job.created_at,summary:job.result.summary,conditions:job.result.conditions,feedback:job.feedback||null,plan_id:job.plan_id||null,entry_key:job.entry_key||null,limitations:job.result.limitations,measurement_contract:report.measurement_contract||job.result.spec?.measurement_contract||null}};}
async function queue(store){
 const value=scope(store,true),v=structuredClone(store.value),entries=[];
 const p=v.kv['profile:'+v.owner];if(!p||p.ownerId!==v.owner||p.dataMode!=='personal')throw Error('请选择本人真实康复档案');
 const profile=p.profile;entries.push(['profile:'+v.owner,{title:'康复资料',kind:'profile',result:{name:profile.name,age:profile.age,conditions:profile.conditions,mobility:profile.mobility,usesCane:profile.usesCane,rehabGoal:p.rehabGoal,currentState:p.currentState}}]);
 for(const job of v.jobs)if(['assessment','training'].includes(job.mode)){try{entries.push(['job:'+job.id,jobPayload(job)]);}catch{/* unfinished/test records stay local */}}
 for(const plan of v.plans)entries.push(['plan:'+plan.id,{title:plan.name,kind:'rehab_plan',result:plan}]);
 const prepared=[];for(const [key,payload] of entries)prepared.push({key:'record:'+ (await hash(key)).slice(0,32),digest:await hash(canonical(payload.result)),payload:JSON.parse(JSON.stringify(payload))});
 return store.serial(()=>store.change(next=>{
  scope(store,true);const out=next.cloudOutbox??={version:2,patient_id:value.patient_id,installation_id:crypto.randomUUID(),items:[],versions:{}};
  if(![1,2].includes(out.version)||out.patient_id!==value.patient_id||!Array.isArray(out.items))throw Error('原上传队列无法读取，未覆盖');out.version=2;out.versions??={};
  for(const item of prepared){const prior=out.versions[item.key];if(prior?.digest===item.digest)continue;const revision=(prior?.revision||0)+1,payload={...item.payload,schema:'ankang-workbench-record-1',source:root.AnkangBrowserAccount?'WEB_LOCAL':'APK_LOCAL',owner_id:next.owner,patient_id:value.patient_id,captured_at:new Date().toISOString(),record_key:item.key,revision};
   const document={operation_id:crypto.randomUUID(),source_event_id:item.key+':r'+revision,installation_id:out.installation_id,source_kind:payload.source,payload};if(new TextEncoder().encode(JSON.stringify(document)).length>32768)throw Error('单项康复结果过大，原记录保留');if(out.items.length>=1000)throw Error('上传队列已满，请先导出核对');out.items.push({document,resource_id:null});out.versions[item.key]={revision,digest:item.digest};
  }return out.items.filter(i=>!i.resource_id).length;
 }));
}
async function sync(store){const value=scope(store,true),out=store.value.cloudOutbox;if(!out)return{uploaded:0};let uploaded=0;for(const item of out.items.filter(i=>!i.resource_id)){scope(store,true);const receipt=await request('append',value,{document:item.document});if(receipt.status!=='COMMITTED'||!UUID.test(receipt.resource_id))throw Error('云端尚未确认保存，记录继续保留');await store.serial(()=>store.change(v=>{scope(store,true);const row=v.cloudOutbox.items.find(i=>i.document.operation_id===item.document.operation_id);if(!row)throw Error('原队列条目不存在');row.resource_id=receipt.resource_id;}));uploaded++;}return{uploaded};}
function publish(store,retryOnly=false){if(uploading)return uploading;uploading=(async()=>{if(!retryOnly)await queue(store);return sync(store);})().finally(()=>{uploading=null;});return uploading;}
async function send(store,text,operation_id=null){
 const value=scope(store);text=text.trim();if(!text||text.length>4000)throw Error('请填写 1–4000 字');operation_id??=(store.value.cloudMessageOutbox||[]).find(row=>row.patient_id===value.patient_id&&!row.resource_id&&row.text===text)?.operation_id||crypto.randomUUID();if(!UUID.test(operation_id))throw Error('消息编号无效');
 await store.serial(()=>store.change(v=>{const out=v.cloudMessageOutbox??=[];const old=out.find(m=>m.operation_id===operation_id);if(old&&old.text!==text)throw Error('消息编号已用于其他内容');if(!old)out.push({operation_id,text,patient_id:value.patient_id,resource_id:null});}));return syncMessages(store);
}
async function syncMessages(store){const value=scope(store);for(const row of (store.value.cloudMessageOutbox||[]).filter(m=>m.patient_id===value.patient_id&&!m.resource_id)){scope(store);const r=await request('send',value,{operation_id:row.operation_id,text:row.text});if(r.status!=='COMMITTED'||!UUID.test(r.resource_id))throw Error('消息未确认保存，已保留待发送文字');await store.serial(()=>store.change(v=>{scope(store);v.cloudMessageOutbox.find(m=>m.operation_id===row.operation_id).resource_id=r.resource_id;}));}return messages(store);}
async function messages(store,before=0){const value=scope(store);try{const result=await request('messages',value,{before});await store.serial(()=>store.change(v=>{scope(store);const cache=v.cloudMessages??={items:[]};for(const item of result.items)if(!cache.items.some(m=>m.id===item.id))cache.items.push(item);cache.items.sort((a,b)=>a.sequence-b.sequence);cache.items=cache.items.slice(-500);cache.unread_count=result.unread_count;cache.read_cursor=result.read_cursor;}));return result;}catch(e){const current=scope(store);if(current.patient_id!==value.patient_id||current.account_id!==value.account_id)throw e;const cached=store.value.cloudMessages?.items;if(!cached?.length)throw e;return {items:cached.slice(-50),offline:true,unread_count:null};}}
async function markRead(store,cursor){const value=scope(store),r=await request('read',value,{operation_id:crypto.randomUUID(),cursor});await store.serial(()=>store.change(v=>{scope(store);if(v.cloudMessages){v.cloudMessages.read_cursor=Math.max(v.cloudMessages.read_cursor||0,r.read_cursor??cursor);v.cloudMessages.unread_count=Number.isSafeInteger(r.unread_count)?r.unread_count:v.cloudMessages.items.filter(m=>m.author_role==='DOCTOR_ADMIN'&&m.sequence>v.cloudMessages.read_cursor).length;}}));return r;}
async function validatedItems(store,plan){
 const catalog=await root.PhoneMotion.catalog();
 const jobs=store.value.jobs.filter(j=>j.state==='done'&&!j.synthetic&&!j.fixture&&j.result?.local_report&&!j.result.synthetic&&!j.result.fixture).map(j=>({id:j.id,exercise:j.exercise,side:j.side,kind:j.mode,created:new Date(j.created_at).getTime(),report:j.result.local_report,feedback:j.feedback}));
 const newest=new Map();for(const j of store.value.jobs.filter(j=>j.mode==='assessment').sort((a,b)=>Date.parse(a.created_at)-Date.parse(b.created_at)))newest.set(j.exercise+':'+j.side,j);
 const validJobs=jobs.filter(j=>j.kind!=='assessment'||newest.get(j.exercise+':'+j.side)?.state==='done');
 const personal=store.value.kv['profile:'+store.value.owner];if(!personal||personal.ownerId!==store.value.owner||personal.dataMode!=='personal')throw Error('请先保存本人康复资料');
 const eligible=root.LocalEngine.propose(validJobs,catalog,Date.now(),{restrictions:(personal.profile.conditions||[]).join('；')}).items,refs=[],items=[];
 for(const row of plan.items){const spec=catalog.rehab.find(s=>s.id===row.exercise_id),candidate=eligible.find(i=>i.exercise===row.exercise_id&&i.side===row.side);if(!spec||!candidate||spec.measurement_contract!==row.measurement_contract)throw Error('该动作尚无本机最新有效本人评估，或测量定义不一致，请先补测');
  const s=structuredClone(row.settings);if(!Number.isInteger(s.target_reps)||s.target_reps<1||s.target_reps>5||s.target_sets!==1||s.rest_between_sets_s!==null&&(!Number.isFinite(s.rest_between_sets_s)||s.rest_between_sets_s<0||s.rest_between_sets_s>1800)||s.target_angle_deg!==null&&(!Number.isFinite(s.target_angle_deg)||s.target_angle_deg<0||s.target_angle_deg>180))throw Error('医生方案超出当前手机训练支持范围，请联系医生调整');
  if(['allowed_elbow_flexion_deg','allowed_trunk_tilt_deg','lowering_tempo_min_s','lowering_tempo_max_s'].some(k=>s[k]!=null)||s.needs_companion||s.sound_enabled||s.use_of_hands&&s.use_of_hands!=='not_recorded'||Object.values(s.timing_plan||{}).some(v=>v!=null))throw Error('此方案包含手机尚不支持的训练设置，请在电脑版核对采用，或请医生调整');
  const last=jobs.find(j=>j.id===candidate.assessment);if(s.target_angle_deg!==null&&(s.target_angle_deg<last.report.min||s.target_angle_deg>last.report.max))throw Error('方案目标超出本机已评估活动范围，请核对');
  const key=row.exercise_id+':'+row.side;items.push({key,exercise_id:row.exercise_id,side:row.side,settings:s,assessment_id:candidate.assessment,source:{title:'医生工作台发布方案',section:plan.id}});refs.push({key,session_id:candidate.assessment,measurement_contract:row.measurement_contract});
 }
 return {items,refs};
}
async function validateTrainingStart(store,local){
 if(local.status==='PENDING_DOCTOR')throw Error('医生方案仍待云端确认，不能开始训练');
 if(!local.cloud_plan_id)return;
 const result=await validatedItems(store,{items:local.items.map(i=>({...i,measurement_contract:i.measurement_contract}))});
 if(result.items.some((item,index)=>item.assessment_id!==local.items[index].assessment_id))throw Error('当前本人评估已变化，请重新核对医生方案后再训练');
 const active=await request('current',scope(store));
 if(!active.plan||active.plan.id!==local.cloud_plan_id||active.plan.version!==local.cloud_version||['STOPPED','REST_DAY','MANUAL_ONLY'].includes(active.plan.execution_status)||active.plan.execution_date!==local.cloud_execution_date)throw Error('医生方案已停用、更新或今天安排已变化；请联网打开联系康复医师重新核对，不能继续旧安排');
 const expected=await validatedItems(store,active.plan),shape=i=>({exercise_id:i.exercise_id,side:i.side,settings:i.settings});
 if(canonical(expected.items.map(shape))!==canonical(local.items.map(shape)))throw Error('本机训练项目与医生当天安排不一致，请重新核对，不能忽略阶段或器材设置');
}
async function adopt(store,plan,currentRevision){
 if(['STOPPED','REST_DAY','MANUAL_ONLY'].includes(plan.execution_status))throw Error('当前方案停用、休息或需人工执行，请先联系医生核对');
 const value=scope(store);if(plan.status!=='PUBLISHED'||!Array.isArray(plan.items)||!plan.items.length)throw Error('只能采用医生发布的方案');
 const receiptKey=plan.id+':'+plan.version+(plan.execution_date?':'+plan.execution_date:'');let acceptance=store.value.cloudAcceptances?.[receiptKey];
 if(!acceptance){const {items,refs}=await validatedItems(store,plan);await store.serial(()=>store.change(v=>{scope(store);const local={id:crypto.randomUUID(),revision:1,name:plan.title,status:'PENDING_DOCTOR',created_at:new Date().toISOString(),items:items.map((item,index)=>({...item,key:crypto.randomUUID(),measurement_contract:plan.items[index].measurement_contract})),measurement_version:root.LocalEngine.VERSION,cloud_plan_id:plan.id,cloud_version:plan.version,cloud_execution_date:plan.execution_date};v.plans.push(local);const local_validation={local_plan_id:local.id,local_revision:1,scope:{participant_id:v.owner,source_kind:'PHONE_LOCAL',usage_context:'SELF_USE'},validation_policy:'existing-local-assessment-1',assessment_references:refs,validated_at:new Date().toISOString()};(v.cloudAcceptances??={})[receiptKey]={plan_id:plan.id,operation_id:crypto.randomUUID(),expected_version:plan.version,expected_current_revision:currentRevision,local_validation,receipt:null};}));acceptance=store.value.cloudAcceptances[receiptKey];}
 const local=store.value.plans.find(p=>p.id===acceptance.local_validation.local_plan_id);if(!local||local.revision!==acceptance.local_validation.local_revision)throw Error('本地方案已修改，请重新核对医生发布版本');
 let r=acceptance.receipt;
 if(!r){const {receipt:ignored,...body}=acceptance;try{r=await request('accept',value,body);}catch(error){if([403,404,409,412,422].includes(error.status))await store.serial(()=>store.change(v=>{scope(store);delete v.cloudAcceptances[receiptKey];}));throw error;}if(r.status!=='COMMITTED')throw Error('方案仍待云端确认，不能开始训练');await store.serial(()=>store.change(v=>{scope(store);v.cloudAcceptances[receiptKey].receipt=r;}));}
 const current=await request('current',value);if(!current.plan||current.plan.id!==plan.id||current.current_revision!==r.current_revision||['STOPPED','REST_DAY','MANUAL_ONLY'].includes(current.plan.execution_status)||current.plan.execution_date!==plan.execution_date)return {...r,local_status:'SUPERSEDED'};
 try{const checked=await validatedItems(store,plan);if(canonical(checked.items.map((item,index)=>({...item,key:local.items[index].key,measurement_contract:plan.items[index].measurement_contract})))!==canonical(local.items))throw Error('当前评估已变化');}catch{return {...r,local_status:'NEEDS_REVIEW'};}
 await store.serial(()=>store.change(v=>{scope(store);v.plans.find(p=>p.id===local.id).status='ACTIVE';}));return {...r,local_status:'ACTIVE'};
}
function schedule(store){if(autoRunning||scheduled||!store.value.cloudBinding)return;scheduled=setTimeout(async()=>{scheduled=null;autoRunning=true;try{if(store.value.cloudConsent)await publish(store);await syncMessages(store);root.dispatchEvent?.(new Event('workbench-updated'));}catch{/* queue and original local facts remain durable */}finally{autoRunning=false;}},1500);}
async function askAI(store,text=null){
 const value=scope(store);let pending=store.value.cloudAiPending;
 if(pending&&pending.patient_id!==value.patient_id)throw Error('原提问不属于当前本人账号');
 if(pending&&text!==null&&text.trim()!==pending.text)throw Error('原提问回执仍待核对，请先重试原提问，避免重复付费');
 if(!pending){if(typeof text!=='string'||!text.trim()||text.length>12000)throw Error('请填写问题');pending={patient_id:value.patient_id,operation_id:crypto.randomUUID(),text:text.trim()};await store.serial(()=>store.change(v=>{scope(store);v.cloudAiPending=pending;}));}
 const result=await request('aiAsk',value,{operation_id:pending.operation_id,text:pending.text});
 if(['SUCCEEDED','UNMETERED','UNKNOWN'].includes(result.state))await store.serial(()=>store.change(v=>{scope(store);if(v.cloudAiPending?.operation_id===pending.operation_id)delete v.cloudAiPending;}));
 return result;
}
let contactUI=null;
function contactView(){
 if(root.PhoneContact)return Promise.resolve(root.PhoneContact);
 if(contactUI)return contactUI;
 contactUI=new Promise((resolve,reject)=>{
  if(!document.getElementById('ankang-contact-style')){const style=document.createElement('link');style.id='ankang-contact-style';style.rel='stylesheet';style.href='/local/contact.css';document.head.append(style);}
  const script=document.createElement('script');script.src='/local/patient-contact.js';script.onload=()=>resolve(root.PhoneContact);script.onerror=()=>{contactUI=null;script.remove();reject(Error('联系康复医师页面尚未加载，请联网重试'));};document.head.append(script);
 });return contactUI;
}
async function open(){try{const view=await contactView();return await view.open();}catch(error){alert(error.message);}}
if(root.document)document.addEventListener('DOMContentLoaded',()=>{
 const profile=document.querySelector('#profile');if(!profile||!root.OfflineAndroid?.accountLogin&&!root.AnkangBrowserAccount)return;
 const button=document.createElement('button');button.className='quiet';button.textContent='联系康复医师';button.id='contact-clinician';button.setAttribute('aria-label','联系康复医师：对话、分享报告和医生方案');button.onclick=open;profile.before(button);
 const badge=()=>{try{scope(root.PhoneLocal.store);const count=root.PhoneLocal.store.value.cloudMessages?.unread_count||0;button.textContent=count?'联系康复医师（'+count+'）':'联系康复医师';}catch{button.textContent='联系康复医师';}};
 root.addEventListener?.('workbench-updated',badge);root.PhoneLocal?.ready.then(()=>{badge();schedule(root.PhoneLocal.store);if(localStorage.getItem('ankang-contact-open')==='yes'){localStorage.removeItem('ankang-contact-open');open();}});
 root.addEventListener?.('online',()=>schedule(root.PhoneLocal.store));root.setInterval?.(()=>{if(document.visibilityState!=='hidden'&&root.PhoneLocal?.store)schedule(root.PhoneLocal.store);},20000);
});
root.PhoneAccount={ORIGIN,identity,login,validateIdentity,activate,bind,scope,request,reply,jobPayload,queue,sync,publish,send,syncMessages,messages,markRead,adopt,validateTrainingStart,schedule,open,askAI};if(typeof module!=='undefined')module.exports=root.PhoneAccount;
})(globalThis);
