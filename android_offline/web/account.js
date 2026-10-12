(function(root){
'use strict';
const PS=root.PhoneStore,ORIGIN='https://139.224.216.18',UUID=/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/;
const pending=new Map();let sequence=0,uploading=null;
function identity(){const text=root.OfflineAndroid?.accountIdentity?.();return text?JSON.parse(text):null;}
function validateIdentity(value){if(!value||value.origin!==ORIGIN||value.role!=='PATIENT'||!UUID.test(value.patient_id)||!UUID.test(value.account_id)||typeof value.username!=='string')throw Error('请重新登录云账号');return value;}
async function activate(value){
 validateIdentity(value);const old=root.PhoneLocal?.store;
 if(root.PhoneMotion?.active)throw Error('请先结束当前分析');
 if(old)await old.tail;
 const key=PS.CLOUD_PREFIX+value.patient_id,store=new PS.Store(localStorage,key);
 store.change(v=>{v.cloudIdentity=structuredClone(value);});
 localStorage.setItem(PS.ACTIVE_KEY,key);if(root.location)root.location.href='/';
}
function scope(store){
 const value=validateIdentity(identity());
 if(!PS.cloudKey(store.key)||store.key!==PS.CLOUD_PREFIX+value.patient_id||store.value.owner!==value.patient_id||store.value.fixture)throw Error('请打开当前云账号档案；旧本机和展示记录不自动上传');
 return value;
}
function request(action,value,body={}){
 validateIdentity(value);if(!root.OfflineAndroid?.accountRequest)return Promise.reject(Error('此功能需要新版 APK'));
 return new Promise((resolve,reject)=>{const id=String(++sequence),timer=setTimeout(()=>{pending.delete(id);reject(Error('云回复未收到，记录保留；可以重试'));},45000);
 pending.set(id,{resolve,reject,timer});
 try{root.OfflineAndroid.accountRequest(id,action,JSON.stringify({...body,patient_id:value.patient_id}));}catch(e){clearTimeout(timer);pending.delete(id);reject(e);}
 });
}
function reply(id,status,text){const call=pending.get(id);if(!call)return;pending.delete(id);clearTimeout(call.timer);try{const result=JSON.parse(text);if(status<200||status>=300)throw Error(result.message||'云操作未完成');call.resolve(result);}catch(e){call.reject(e);}}
function jobPayload(job,label=null){
 const report=job.result?.local_report;
 if(job.state!=='done'||job.measurement_version!=='android-local-projection-1'||!report||job.synthetic||job.fixture||job.result.synthetic||job.result.fixture||report.synthetic||report.fixture)throw Error('仅上传已完成的本人分析结果');
 const bar=job.result.barbell;
 return{schema:'ankang-result-1',title:label||job.result.spec?.label||job.exercise,kind:job.mode,measured_at:job.created_at,source:'REPLAY_FILE',
  result:{id:job.id,exercise:job.exercise,side:job.side,measurement_version:job.measurement_version,summary:job.result.summary,conditions:job.result.conditions,
   repetitions:job.result.repetitions?.map(({number,total_s,outbound_s,return_s,range_deg})=>({number,total_s,outbound_s,return_s,range_deg})),feedback:job.feedback||null,
   barbell:bar?{version:bar.version,calibration:bar.calibration,summary:bar.summary,assumptions:bar.assumptions}:null,
   limitations:job.result.limitations}};
}
async function queue(store){
 const value=scope(store);
 const catalog=root.PhoneMotion?.catalog?await root.PhoneMotion.catalog():null;
 const labels=new Map(catalog?[...catalog.rehab,...catalog.fitness,...catalog.posture].map(s=>[s.id,s.label]):[]);
 return store.serial(()=>store.change(v=>{
  if(v.owner!==value.patient_id||v.fixture)throw Error('账号档案已变化');
  const out=v.cloudOutbox??={version:1,patient_id:value.patient_id,installation_id:crypto.randomUUID(),items:[]};
  if(out.version!==1||out.patient_id!==value.patient_id||!Array.isArray(out.items))throw Error('原上传队列无法读取，未覆盖');
  const entries=[];
  for(const job of v.jobs){try{entries.push(['job:'+job.id,jobPayload(job,labels.get(job.exercise))]);}catch{/* Failed, incomplete and fixture reports remain only in their original store. */}}
  for(const p of v.practices||[])if(p.state==='COMMITTED'&&p.context?.participant_id===v.owner)entries.push(['practice:'+p.id,{schema:'ankang-result-1',title:p.exercise_id,kind:'guided_practice',source:p.record_origin,measured_at:p.ended_at,result:structuredClone(p)}]);
  for(const [source_event_id,payload] of entries){
   if(out.items.some(i=>i.document.source_event_id===source_event_id))continue;
   const document=JSON.parse(JSON.stringify({operation_id:crypto.randomUUID(),source_event_id,installation_id:out.installation_id,source_kind:payload.kind==='guided_practice'?'SELF_REPORT':'APK_LOCAL',payload}));
   if(new TextEncoder().encode(JSON.stringify(document)).length>32768)throw Error('单项结果过大，原记录保留，请分项导出');
   if(out.items.length>=1000)throw Error('上传队列已满，请先导出记录');
   out.items.push({document,resource_id:null});
  }
  return out.items.filter(i=>!i.resource_id).length;
 }));
}
async function sync(store){
 const value=scope(store),out=store.value.cloudOutbox;
 if(!out)return{uploaded:0};if(out.version!==1||out.patient_id!==value.patient_id)throw Error('上传队列账号不匹配');
 let uploaded=0;
 for(const item of out.items.filter(i=>!i.resource_id)){
  scope(store);const receipt=await request('append',value,{document:item.document});
  if(receipt.status!=='COMMITTED'||!UUID.test(receipt.resource_id))throw Error('云端尚未确认保存，记录继续保留');
  await store.serial(()=>store.change(v=>{const row=v.cloudOutbox.items.find(i=>i.document.operation_id===item.document.operation_id);if(!row)throw Error('原队列条目不存在');row.resource_id=receipt.resource_id;}));uploaded++;
 }
 return{uploaded};
}
function publish(store,retryOnly=false){
 if(uploading)return uploading;
 uploading=(async()=>{if(!retryOnly)await queue(store);return sync(store);})().finally(()=>{uploading=null;});return uploading;
}
function safe(text){return String(text??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
async function open(){
 try{
  const value=identity();if(!value){root.OfflineAndroid.accountLogin();return;}
  validateIdentity(value);await root.PhoneLocal.ready;
  const dialog=document.createElement('dialog');dialog.innerHTML='<h2>云账号 · '+safe(value.username)+'</h2><p role="status">'+(PS.cloudKey(root.PhoneLocal.store.key)?'本人结果先保存在手机，上传后可在电脑和医生网页查看。':'当前为旧本机档案。请打开云账号档案，旧记录不自动合并。')+'</p><div class="actions"></div><section></section>';
  const status=dialog.querySelector('p'),actions=dialog.querySelector('.actions'),content=dialog.querySelector('section');
  const buttons=[];const add=(title,work)=>{const button=document.createElement('button');button.textContent=title;actions.append(button);buttons.push(button);button.onclick=async()=>{
   buttons.forEach(b=>b.disabled=true);status.textContent='正在处理…';try{status.textContent=await work()||'已完成';}catch(e){status.textContent=e.message;}finally{buttons.forEach(b=>b.disabled=false);}
  };};
  add('打开本人档案',()=>activate(value));
  add('上传已保存结果',async()=>{if(!confirm('上传当前账号的评估、健身、体态和已保存练习结果？不含录像原件。'))return '已取消';const result=await publish(root.PhoneLocal.store);return '本次上传 '+result.uploaded+' 条';});
  add('重试待上传',async()=>{const result=await publish(root.PhoneLocal.store,true);return '本次上传 '+result.uploaded+' 条';});
  add('云记录',async()=>{const records=await request('records',value);content.innerHTML=records.items.map(r=>'<details><summary>'+safe(r.payload.title||'分析记录')+'</summary><pre>'+safe(JSON.stringify(r.payload,null,2))+'</pre></details>').join('')||'<p>暂无云记录。</p>';return '云记录已读取（最近10条）';});
  add('授权医生',async()=>{await request('grant',value,{enabled:true});return '已授权医生查看';});
  add('撤销授权',async()=>{await request('grant',value,{enabled:false});return '医生授权已撤销';});
  add('切换账号',()=>root.OfflineAndroid.accountLogin());
  add('退出账号',async()=>{await request('logout',value);await root.PhoneLocal.store.tail;localStorage.setItem(PS.ACTIVE_KEY,PS.KEY);location.href='/';return '已退出';});
  add('关闭',()=>dialog.close());dialog.addEventListener('close',()=>dialog.remove());document.body.append(dialog);dialog.showModal();
 }catch(e){alert(e.message);}
}
if(root.document)document.addEventListener('DOMContentLoaded',()=>{
 const profile=document.querySelector('#profile');if(!profile||!root.OfflineAndroid?.accountLogin)return;
 const button=document.createElement('button');button.className='quiet';button.textContent='云账号';button.setAttribute('aria-label','云账号与结果上传');button.onclick=open;profile.before(button);
});
root.PhoneAccount={ORIGIN,identity,validateIdentity,activate,scope,request,reply,jobPayload,queue,sync,publish,open};
if(typeof module!=='undefined')module.exports=root.PhoneAccount;
})(globalThis);
