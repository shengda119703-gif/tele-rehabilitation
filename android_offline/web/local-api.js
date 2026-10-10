(function(root){
'use strict';
const nativeFetch=root.fetch.bind(root),NativeXHR=root.XMLHttpRequest,PS=PhoneStore,PM=PhoneMotion;
const store=new PS.Store(localStorage,PS.selectedKey()),now=()=>new Date(),copy=v=>structuredClone(v);
let owner=store.value.owner;
const metrics=[['steps','活动步数','步'],['walkSpeed','步行速度','m/s'],['sleepHours','睡眠时长','小时'],['nightWakes','夜间醒来','次'],['restingHr','静息心率','bpm'],['weight','体重','kg'],['spo2','血氧','%'],['systolic','收缩压','mmHg'],['diastolic','舒张压','mmHg'],['bloodGlucose','血糖','mmol/L']];
const categories=['体检报告','就诊记录','检验检查','影像资料','病历资料','其他资料'];
const profile=()=>store.read('profile:'+owner)?.profile;
const domain=new AnkangDomain.ProductService({read:k=>store.read(k),write:(k,v)=>store.write(k,v),remove:k=>store.remove(k),profiles:()=>store.profiles(),attachments:{list:s=>PS.attachments(owner).list(s),put:(s,a)=>PS.attachments(owner).put(s,a),clear:s=>PS.attachments(owner).clear(s),setTrash:(s,id,at)=>PS.attachments(owner).setTrash(s,id,at)}},undefined,undefined,{},participant=>PS.createCarePort(store,participant,careRehabFacts));
const ready=store.serial(async()=>{
 await PhoneLin.initialize(store,nativeFetch);
 owner=store.value.owner;
 await store.migrate(domain);
 if(!profile())await domain.request('profile.save',owner,{profile:{name:'本机用户',age:0,conditions:[],medications:[],mobility:'unknown',usesCane:false,nightVision:'unknown',cognition:'unknown',familySharing:'denied'}},now());
 // Interrupted jobs are explicitly failed, not silently counted as successful.
 store.change(v=>v.jobs.forEach(j=>{if(['queued','analyzing','uploading'].includes(j.state)){j.state='failed';j.message='上次分析被中断，原录像保留，请重新分析。';}}));
});
let cloudState={familyMembers:[],grants:{},at:0},cloudBusy=false;
async function cloudRefresh(){
 if(cloudBusy||!PhoneCloud.configured())return;cloudBusy=true;
 try{const state=await PhoneCloud.request('/v1/family');cloudState={...state,at:Date.now()};await PhoneCloud.publish(root.PhoneLocal);if(typeof ui!=='undefined'&&ui.page==='family'&&!ui.busy&&typeof load==='function')load();}
 catch(e){cloudState={familyMembers:[],grants:{},at:Date.now(),unavailable:true};if(typeof ui!=='undefined'&&ui.page==='family'&&!ui.busy&&typeof load==='function')load();}
 finally{cloudBusy=false;}
}
function publicJob(j,brief=false){const out=copy(j);if(PM.errors.has(j.id)){out.state='failed';out.message=PM.errors.get(j.id);}if(brief)delete out.result;return out;}
function findJob(id){const j=store.value.jobs.find(j=>j.id===id);if(!j)throw Error('找不到这项记录');return j;}
function planProgress(p,value=store.value){const items=p?.items||[],statuses=items.map(i=>{
 const job=value.jobs.filter(j=>j.mode==='training'&&j.plan_id===p.id&&j.entry_key===i.key&&j.state==='done').at(-1);
 const f=job?.feedback,done=!!(job?.result.summary.plan_completed&&job.result.local_report.validRatio>=.8&&f&&f.pain===0&&f.fatigue<5);
 return{key:i.key,done,job_id:job?.id||null,blocked:job&&!f?'请补充上次训练感受':f&&(f.pain>0||f.fatigue>=5)?'上次训练有不适，请先停止并咨询专业人员':'',};
 }),next=statuses.find(i=>!i.done);return{completed:statuses.filter(i=>i.done).length,total:items.length,next_key:next?.key||null,items:statuses,blocked:next?.blocked||''};}
async function careRehabFacts(value){
 // Reuse saved plans and the existing progress/feedback gates. No new dose or
 // clinical threshold is introduced by the coordination adapter.
 const p=value.plans.at(-1),progress=p?planProgress(p,value):null;
 const plans=p?[{...p,progress,next_available:!!(progress.next_key&&!progress.blocked),availability_reason:progress.blocked||(progress.next_key?'':'这一轮已完成')}]:[];
 const history=value.jobs.filter(j=>j.mode==='training'&&j.state==='done').reverse().map(j=>({exercise_id:j.exercise,side:j.side,end_utc:j.created_at,plan_id:j.plan_id,entry_key:j.entry_key,summary:j.result?.summary,feedback:j.feedback}));
 return{plans,history};
}
async function proposal(){const c=await PM.catalog(),records=store.value.jobs.filter(j=>j.state==='done'&&j.result.local_report).map(j=>({id:j.id,exercise:j.exercise,side:j.side,created:new Date(j.created_at).getTime(),kind:j.mode||'assessment',report:j.result.local_report,feedback:j.feedback}));
 const p=LocalEngine.propose(records,c,Date.now(),{restrictions:(profile().conditions||[]).join('；')});
 return{candidates:p.items.map(i=>{const s=c.rehab.find(s=>s.id===i.exercise);return{...i,exercise_id:i.exercise,label:s.label,settings:{target_reps:i.reps,target_sets:1,target_angle_deg:i.target,rest_between_sets_s:30},instruction:s.instructions.move+'；'+s.instructions.return,rationale:'按最近本人评估中的可见次数和舒适活动幅度安排。',source:typeof i.source==='string'?{title:i.source,section:''}:i.source};}),excluded:p.excluded.map(reason=>({label:'待补充',reason}))};}
async function body(){const c=await PM.catalog(),records=store.value.jobs.filter(j=>j.state==='done').map(j=>({id:j.id,exercise:j.exercise,label:[...c.rehab,...c.fitness,...c.posture].find(s=>s.id===j.exercise)?.label||j.exercise,side:j.side,mode:j.mode,created_at:j.created_at,summary:j.result.summary,feedback:j.feedback})),latest=[...new Map(records.filter(j=>j.mode!=='training').map(j=>[j.exercise+':'+j.side,j])).values()];return{total:records.length,training_count:records.filter(j=>j.mode==='training').length,records,latest,next_step:{title:store.value.plans.length?'按本轮计划继续训练':'完成评估，查看本轮训练建议'},note:'手机本地二维测量汇总，仅反映本次可见活动，不作疾病诊断。'};}
async function snapshot(){const s=await domain.request('snapshot',owner,{},now()),c=await PM.catalog(),p=store.value.plans.at(-1),progress=p?planProgress(p):null;
 const scope={participant_id:owner,source_kind:'PHONE_LOCAL',usage_context:'SELF_USE'};
 const jobs=store.value.jobs.filter(j=>j.state==='done');
 const plan=p?{...p,progress,items:p.items.map(i=>({...i,exercise_label:c.rehab.find(s=>s.id===i.exercise_id)?.label||i.exercise_id}))}:null;
 s.dailyProduct=copy(store.value.daily);s.familyMembers=PhoneLin.family(store);
 if(PhoneCloud.configured()){
  if(Date.now()-cloudState.at<60000){s.familyMembers=copy(cloudState.familyMembers);s.dailyProduct.grants=copy(cloudState.grants);}
  if(Date.now()-cloudState.at>20000)setTimeout(cloudRefresh,0);
 }
 s.rehabilitation_ui={
 'rehab.get_training_plan':{records:plan?[plan]:[],scope},
 'rehab.get_recent_assessments':{records:jobs.filter(j=>j.mode==='assessment').map(j=>({exercise_id:j.exercise,exercise_label:c.rehab.find(s=>s.id===j.exercise)?.label,side:j.side,end_utc:j.created_at,measurement_version:LocalEngine.VERSION,summary:j.result.summary})),scope},
 'rehab.get_training_history':{records:jobs.filter(j=>j.mode==='training').map(j=>({exercise_id:j.exercise,exercise_label:c.rehab.find(s=>s.id===j.exercise)?.label,side:j.side,end_utc:j.created_at,summary:j.result.summary})),scope}};
 return s;
}
async function jsonBody(opts){if(!opts.body)return{};if(typeof opts.body==='string')return JSON.parse(opts.body);if(opts.body instanceof Blob)return JSON.parse(await opts.body.text());throw Error('请求格式不正确');}
function failure(message,status=400){const e=Error(message);e.status=status;throw e;}
async function request(path,opts={}){
 await ready;if(opts.signal?.aborted)throw new DOMException('已取消','AbortError');const u=new URL(path,location.origin),route=u.pathname.replace(/^\/api/,''),method=opts.method||'GET',q=u.searchParams;
 // Inference and live frames deliberately do not occupy the domain write queue.
 if(route.startsWith('/live/')){
  if(route.endsWith('/frame'))return PM.liveFrame(route.split('/')[2],opts.body);
  PM.stopLive();return{stopped:true};
 }
 if(route==='/live'){const p=await jsonBody(opts);if(p.consent!==true)failure('请确认本次相机分析');return PM.startLive(await PM.spec(p.exercise),p.side);}
 return store.serial(async()=>{
  const payload=opts.body instanceof Blob?null:await jsonBody(opts);
  if(route==='/pair')return{ok:true,local:true};
  if(route==='/unified')return{snapshot:await snapshot(),source:'PHONE_LOCAL',shared:true,local:true};
  if(route==='/product')return{needs_profile:false,snapshot:await snapshot(),metrics,categories,assistant:'local',external_model:false};
  if(route.startsWith('/product/care.')||route.startsWith('/unified/care.')){
   if(u.origin!==location.origin)failure('请使用当前手机本地档案',403);
   const operation=route.slice(9);
   if(!['care.overview','care.next','care.prepare','care.status','care.confirm','care.cancel'].includes(operation))failure('未开放此照护操作',404);
   if(!['GET','POST'].includes(method)||(!['care.overview','care.next'].includes(operation)&&method!=='POST'))failure('请使用明确的照护操作请求',405);
   if(q.toString())failure('照护请求不接受档案或来源查询参数');
   return domain.request(operation,owner,payload,now());
  }
  if(route.startsWith('/product/')){
   const operation=route.slice(9),p=payload;
   if(operation==='profile.save'){const old=profile();if(!p.profile||typeof p.profile.name!=='string'||p.profile.name.length>40||!Number.isInteger(p.profile.age)||p.profile.age<0||p.profile.age>130||!Array.isArray(p.profile.conditions)||p.profile.conditions.length>20)failure('请核对称呼、年龄和健康情况');p.profile={...old,...p.profile,medications:old.medications,medicationRecords:old.medicationRecords,familySharing:old.familySharing};}
   if(operation==='chat'&&p.private===true)p.text='不要记录：'+p.text;
   if(!['profile.save','chat','health.record','medication.save','medication.status','task.status','notification.plan','notification.ack'].includes(operation))failure('未开放此操作',404);
   return domain.request(operation,owner,p,now());
  }
  if(route.startsWith('/unified/daily.')){
   const operation=route.slice(15);
   if(operation.startsWith('family')){
    if(PhoneLin.isLin(store))return PhoneLin.familyOperation(store,operation,payload);
    const action=({familyInvite:'invite',familyBind:'bind',familyGrant:'grant',familyUnbind:'unbind'})[operation];if(!action)failure('家庭操作无效');
    const r=await PhoneCloud.request('/v1/family/'+action,'POST',payload);cloudState={...await PhoneCloud.request('/v1/family'),at:Date.now()};await PhoneCloud.publish(root.PhoneLocal);return r;
   }
   return PS.applyDaily(store,operation,payload,profile());
  }
  if(route==='/catalog'){const c=await PM.catalog();return{shared:true,exercises:c.rehab.map(s=>({...s,available:true,backend:'phone-mediapipe'})),fitness:c.fitness.map(s=>({...s,available:true})),posture:c.posture};}
  if(route==='/plan'){
   const proposed=await proposal();if(method==='POST'){
    if(!payload.general_activity_ok)failure('请确认目前适合进行基础活动');if(!proposed.candidates.length)failure('暂无可用评估，请先完成一次动作评估');if(proposed.candidates.some(i=>i.standing)&&!payload.standing_support_ok)failure('请为站立项目准备稳固支撑');
    const p={id:crypto.randomUUID(),revision:1,name:'本轮康复训练',created_at:now().toISOString(),items:proposed.candidates.map(i=>({key:crypto.randomUUID(),exercise_id:i.exercise,side:i.side,settings:i.settings,assessment_id:i.assessment,source:i.source})),measurement_version:LocalEngine.VERSION};store.change(v=>v.plans.push(p));
   }
   const p=store.value.plans.at(-1);return{proposal:proposed,plan:p||null,progress:planProgress(p)};
  }
  if(route==='/jobs'&&method==='POST'){
   if(q.get('consent')!=='yes')failure('请确认本次分析');if(PM.active)failure('已有本地分析正在进行',409);if(!(opts.body instanceof Blob)||opts.body.size>256*1048576)failure('请选择 256 MB 以内的录像');
   const s=await PM.spec(q.get('exercise')),side=q.get('side');if(!['left','right'].includes(side))failure('请选择测试侧');
   const mode=q.get('mode')||'assessment',p=store.value.plans.find(x=>x.id===q.get('plan_id')),entry=p?.items.find(i=>i.key===q.get('entry_key'));
   if(mode==='training'&&(!entry||entry.exercise_id!==s.id||entry.side!==side))failure('本轮计划已变化，请重新选择动作');
   if(store.value.jobs.length>=250)failure('记录空间已满，请先导出备份');
   const id=crypto.randomUUID(),job={id,exercise:s.id,side,mode,state:'analyzing',created_at:now().toISOString(),message:'正在加载手机模型',video_available:true,plan_id:p?.id||null,entry_key:entry?.key||null};
   await PS.files.put('video:'+id,{kind:'video',ownerId:owner,blob:opts.body});
   try{store.change(v=>v.jobs.push(job));}catch(e){await PS.files.remove('video:'+id);throw e;}
   let calibration=null;const headers=new Headers(opts.headers||{}),raw=headers.get('X-Fitness-Calibration');if(raw)calibration=JSON.parse(raw);
   setTimeout(()=>PM.analyze(store,job,opts.body,calibration).catch(e=>{store.change(v=>{const j=v.jobs.find(x=>x.id===id);j.state='failed';j.message=e.message;});}),0);return{id};
  }
  if(route==='/jobs')return store.value.jobs.map(j=>publicJob(j,q.get('brief')==='true')).reverse();
  if(route.startsWith('/jobs/')){
   const parts=route.split('/'),j=findJob(parts[2]);
   if(parts[3]==='video'){
    if(method==='DELETE'){await PS.files.remove('video:'+j.id);store.change(v=>{v.jobs.find(x=>x.id===j.id).video_available=false;});return{ok:true};}
    const file=await PS.files.get('video:'+j.id);if(!file)failure('原始录像已删除',404);return new Response(file.blob,{headers:{'Content-Type':file.blob.type||'video/mp4'}});
   }
   if(parts[3]==='feedback'){
    if(j.mode!=='training'||j.state!=='done'||![payload.pain,payload.fatigue].every(n=>Number.isInteger(n)&&n>=0&&n<=10))failure('请填写本次训练的真实感受');
    if((j.feedback?.revision||0)!==payload.revision)failure('记录已变化，请刷新',409);store.change(v=>{const job=v.jobs.find(x=>x.id===j.id);job.feedback={...payload,revision:payload.revision+1,at:now().toISOString()};});return{ok:true};
   }return publicJob(j);
  }
  if(['/body','/product-rehab'].includes(route))return body();
  if(route==='/product-archive'&&method==='POST'){
   if(q.get('consent')!=='yes'||!(opts.body instanceof Blob)||opts.body.size>8*1048576)failure('请确认保存 8 MB 以内的本人资料');
   if(!categories.includes(q.get('category'))||!q.get('name')||q.get('name').length>100)failure('请填写资料名称和分类');
   const mediaType=opts.body.type||new Headers(opts.headers).get('Content-Type');if(!['image/png','image/jpeg','application/pdf','text/plain'].includes(mediaType))failure('请选择 JPG、PNG、PDF 或文本资料');
   return domain.request('archive.save',owner,{name:q.get('name'),category:q.get('category'),fileName:opts.body.name||q.get('name'),mediaType,visibility:'private',bytes:new Uint8Array(await opts.body.arrayBuffer())},now());
  }
  if(route.startsWith('/product-archive/')){
   const [,base,id,action]=route.split('/');
   if(action){if(payload.confirm!==true||!['trash','restore'].includes(action))failure('请确认资料操作');return domain.request('archive.'+action,owner,{id},now());}
   const a=await domain.request('archive.read',owner,{id},now());return new Response(new Uint8Array(a.bytes),{headers:{'Content-Type':a.mediaType,'X-File-Name':encodeURIComponent(a.fileName)}});
  }
  if(route==='/product-trash')return domain.request('archive.trash.list',owner,{},now());
  if(route==='/product-backup')return backup();
  if(route==='/product-ocr')return{available:true,local:true,engine:'tesseract.js@6.0.1'};
  if(route.startsWith('/product-ocr/')){const a=await domain.request('archive.read',owner,{id:route.split('/')[2]},now());return PhoneOCR.recognize(new Blob([new Uint8Array(a.bytes)],{type:a.mediaType}));}
  if(route==='/product-voice'&&method==='GET')return{available:!!root.OfflineAndroid?.speechAvailable(),local:true,detail:'本地语音服务，识别文字需本人核对。'};
  if(route==='/product-voice')failure('使用语音输入按钮调用手机本地识别；录音文件转写未接入',503);
  if(route==='/cameras'||route==='/care/shares')return[];
  if(route==='/account/link-code'||route==='/account/link')failure('手机本地档案无需电脑连接；跨设备功能需配置演示云端',503);
  if(route.startsWith('/care/')||route==='/product-share'||route.startsWith('/cameras/'))failure('请先配置演示云端；当前不会上传本人资料',503);
  if(route==='/fitness/demo')return (await nativeFetch('/fitness-demo.json')).json();
  failure('此功能尚未接入手机本地版',404);
 });
}
root.fetch=async function(input,opts={}){const path=typeof input==='string'?input:input.url,u=new URL(path,location.origin);if(u.origin!==location.origin||!u.pathname.startsWith('/api/'))return nativeFetch(input,opts);try{const result=await request(u.href,opts);return result instanceof Response?result:new Response(JSON.stringify(result),{headers:{'Content-Type':'application/json'}});}catch(e){if(e.name==='AbortError')throw e;return new Response(JSON.stringify({detail:e.message}),{status:e.status||400,headers:{'Content-Type':'application/json'}});}};
// Preserve the existing upload form/progress handler without sending a video off-device.
root.XMLHttpRequest=class{
 constructor(){this.upload={};this.headers={};this.status=0;this.responseText='';this.readyState=0;this.controller=new AbortController();}
 open(method,url){this.method=method;this.url=url;this.readyState=1;}
 setRequestHeader(k,v){this.headers[k]=v;}
 abort(){this.controller.abort();this.onabort?.();}
 send(body){const u=new URL(this.url,location.origin);if(!u.pathname.startsWith('/api/'))throw Error('不允许向未配置地址发送资料');this.upload.onprogress?.({lengthComputable:true,loaded:body.size,total:body.size});root.fetch(u.href,{method:this.method,body,headers:this.headers,signal:this.controller.signal}).then(async r=>{this.status=r.status;this.responseText=await r.text();this.readyState=4;if(!this.controller.signal.aborted)this.onload?.();}).catch(()=>{if(!this.controller.signal.aborted)this.onerror?.();});}
};
// Media elements cannot use JavaScript fetch interceptors. Resolve their local blobs.
async function resolveMedia(node){if(!(node instanceof Element))return;const nodes=[node,...node.querySelectorAll('video[src^="/api/jobs/"]')];for(const video of nodes){if(video.tagName!=='VIDEO'||!video.getAttribute('src')?.startsWith('/api/jobs/'))continue;const id=video.getAttribute('src').split('/')[3],file=await PS.files.get('video:'+id);if(file&&video.isConnected){const url=URL.createObjectURL(file.blob);video.src=url;video.addEventListener('emptied',()=>URL.revokeObjectURL(url),{once:true});}}}
document.addEventListener('DOMContentLoaded',()=>{
 new MutationObserver(list=>list.forEach(m=>m.addedNodes.forEach(resolveMedia))).observe(document.body,{childList:true,subtree:true});
 if(typeof ui!=='undefined'){ui.source='REPLAY_FILE';ready.then(()=>{if(typeof load==='function')load();});}
 if(root.OfflineAndroid)root.print=()=>OfflineAndroid.printPage();
});
document.addEventListener('contextmenu',e=>{if(e.target.closest?.('#profile')){e.preventDefault();root.OfflineAndroid?.settings();}});
let speechPending=false;
document.addEventListener('click',e=>{
 if(!root.OfflineAndroid||!e.target.closest?.('#voice,#voice-cancel'))return;
 e.preventDefault();e.stopImmediatePropagation();
 if(speechPending||e.target.closest('#voice-cancel')){OfflineAndroid.speechCancel();return;}
 speechPending=true;const label=document.querySelector('#voice-state');if(label)label.textContent='正在听，请说出要记录的内容';OfflineAndroid.speechStart();
},true);
function speechResult(text,error){speechPending=false;if(text&&typeof ui!=='undefined'){ui.draft=[ui.draft,text].filter(Boolean).join('\n').slice(0,1900);const field=document.querySelector('#draft');if(field)field.value=ui.draft;}const label=document.querySelector('#voice-state');if(label)label.textContent=error||'已填入草稿，核对后发送。';}
async function backup(){
 const exported=await domain.request('lifecycle.export',owner,{},now());
 // Binary originals remain independently exportable; keep JSON restore bounded.
 exported.attachments=exported.attachments.map(({bytes,...a})=>({...a,originalIncluded:false}));
 const data=PS.backupData(store.value);data.jobs.forEach(j=>{if(!['done','failed'].includes(j.state)){j.state='failed';j.message='备份时分析尚未完成，未计入结果。';}});
 return{kind:'ankang-phone-backup',version:2,exportedAt:now().toISOString(),data,domain:exported,note:'仅文字记录、评估结果和计划；录像及资料原件请单独导出。'};
}
async function restore(text){try{
 const value=PS.validateBackup(JSON.parse(text));
 if(PM.active)throw Error('请先结束当前分析');
 // Preserve the previous state before any replacement; quota failure aborts restore.
 if((value.fixture?.schema==='test-lin-apk-v1')!==(store.key===PS.LIN_KEY))throw Error('请先切换到对应档案，再恢复备份');
 store.storage.setItem(store.key+':before-restore',JSON.stringify(store.value));
 value.jobs.forEach(j=>{j.video_available=false;});
 if(store.key!==PS.LIN_KEY)value.daily.grants={};
 store.commit(value);if(store.key!==PS.LIN_KEY&&root.OfflineAndroid?.cloudConfigured())OfflineAndroid.cloudDisconnect?.();location.href='/';
}catch(e){alert(e.message+'；当前数据未覆盖。');}}
async function exportBackup(){try{await ready;OfflineAndroid.saveJson(JSON.stringify(await backup()));}catch(e){alert(e.message);}}
async function cloudBackup(){try{
 if(!confirm('将本人的文字记录、评估结果和计划备份到已配置云端？不包含录像和资料原件。'))return;
 let revision=0;try{revision=(await PhoneCloud.request('/v1/backup')).revision;}catch(e){if(!e.message.includes('没有本人'))throw e;}
 await PhoneCloud.request('/v1/backup','PUT',{consent:true,revision,document:await backup()});alert('云端备份已保存');
}catch(e){alert(e.message);}}
async function cloudRestore(){try{const b=await PhoneCloud.request('/v1/backup');if(confirm('恢复本人云端备份？当前文字记录和计划将保留恢复前副本。录像与资料原件不包含在此备份中。'))await restore(JSON.stringify(b.document));}catch(e){alert(e.message);}}
document.addEventListener('click',async e=>{const a=e.target.closest?.('a[href^="/api/"]');if(!a)return;e.preventDefault();try{const r=await root.fetch(a.href);if(!r.ok)throw Error((await r.json()).detail);const blob=await r.blob();if(root.OfflineAndroid){if(blob.type.includes('json'))OfflineAndroid.saveJson(await blob.text());else{const bytes=new Uint8Array(await blob.arrayBuffer());let text='';for(let i=0;i<bytes.length;i+=8192)text+=String.fromCharCode(...bytes.subarray(i,i+8192));OfflineAndroid.saveDocument(decodeURIComponent(r.headers.get('X-File-Name')||'健康资料'),btoa(text),blob.type);}}else{const u=URL.createObjectURL(blob),link=document.createElement('a');link.href=u;link.download='健康记录';link.click();setTimeout(()=>URL.revokeObjectURL(u),1000);}}catch(err){alert(err.message);}});
root.offlinePause=()=>{speechPending=false;PM.pause();if(typeof stopLive==='function')stopLive();};
root.offlineBack=()=>{const d=document.querySelector('dialog[open]');if(d){d.close();return true;}if(PM.active){if(confirm('结束本次分析？原录像保留。'))PM.pause();return true;}if(location.pathname==='/capture'){location.href='/';return true;}if(location.hash&&location.hash!=='#home'){location.hash='#home';return true;}return false;};
root.PhoneLocal={store,domain,ready,request,snapshot,proposal,body,planProgress,backup,restore,exportBackup,cloudBackup,cloudRestore,cloudRefresh,speechResult,selectProfile:key=>PhoneLin.select(store,key),get cloudState(){return cloudState;}};
})(globalThis);
