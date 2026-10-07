(function(root){
'use strict';
const KEY='ankang-phone-product-2',OLD='rehab-offline-state-1';
const clone=v=>structuredClone(v),now=()=>new Date().toISOString();
function blank(){return{version:2,owner:crypto.randomUUID(),kv:{},jobs:[],plans:[],daily:{schedules:[],medSchedules:{},doses:{},doseAudit:[],grants:{}},migration:null};}
class Store{
 constructor(storage=localStorage){this.storage=storage;const raw=storage.getItem(KEY);this.value=raw?JSON.parse(raw):blank();if(this.value.version!==2||!this.value.owner||!Array.isArray(this.value.jobs)||!this.value.kv)throw Error('本地档案格式不正确，原数据没有覆盖');this.tail=Promise.resolve();}
 commit(value){const text=JSON.stringify(value);if(text.length>12*1024*1024)throw Error('记录空间已满，请先导出备份');this.storage.setItem(KEY,text);this.value=value;}
 change(fn){const next=clone(this.value),result=fn(next);this.commit(next);return result;}
 read(key){return clone(this.value.kv[key]??null);}
 write(key,value){this.change(v=>v.kv[key]=clone(value));}
 remove(key){this.change(v=>delete v.kv[key]);}
 profiles(){return Object.entries(this.value.kv).filter(([k])=>k.startsWith('profile:')).map(([,v])=>clone(v));}
 serial(fn){const result=this.tail.then(fn);this.tail=result.catch(()=>{});return result;}
 async migrate(service){
  if(this.value.migration||this.profiles().length)return;
  const raw=this.storage.getItem(OLD);if(!raw)return;const legacy=JSON.parse(raw);
  if(legacy.version!==1||!Array.isArray(legacy.records)||!legacy.profile)throw Error('旧版档案无法读取，未删除旧数据');
  await service.request('profile.save',this.value.owner,{profile:{name:legacy.profile.name||'本机用户',age:0,conditions:legacy.profile.restrictions?[legacy.profile.restrictions]:[],medications:[],familySharing:'denied',mobility:'unknown',usesCane:false,nightVision:'unknown',cognition:'unknown'}},new Date());
  for(const m of legacy.medicines||[])await service.request('medication.save',this.value.owner,{record:{id:m.id||crypto.randomUUID(),name:m.name,dose:m.dose||'',times:m.times||'',purpose:'',status:'active'}},new Date());
  const jobs=[];
  for(const r of legacy.records){
   if(r.report?.contract!==LocalEngine.VERSION||!Number.isFinite(r.created)||!['left','right'].includes(r.side))continue;
   try{const s=await PhoneMotion.spec(r.exercise);jobs.push({id:r.id,exercise:r.exercise,side:r.side,mode:r.kind||'assessment',state:'done',created_at:new Date(r.created).toISOString(),video_available:false,message:'旧版手机记录',feedback:r.feedback||null,result:PhoneMotion.result(s,r.report,[0,0]),measurement_version:LocalEngine.VERSION});}catch{/* Raw legacy entry is preserved below, not relabelled as a different contract. */}
  }
  const healthMap={'血压（收缩压）':'systolic','血压（舒张压）':'diastolic','血糖':'bloodGlucose','心率':'restingHr','体重':'weight','血氧':'spo2','睡眠':'sleepHours','步数':'steps'};
  for(const h of legacy.health||[]){const metric=healthMap[String(h.name).split(' · ')[0]];if(metric&&Number.isFinite(h.value)&&Number.isFinite(h.created))await service.request('health.record',this.value.owner,{metric,value:h.value,visibility:'private'},new Date(h.created));}
  this.change(v=>{v.jobs.push(...jobs);v.migration={at:now(),source:OLD,raw:legacy,legacyRecords:legacy.records,legacyPlan:legacy.plan,legacyArchive:legacy.archive||[],note:'旧版计划保留原件，不自动计入新版完成量；感受记录与未适配指标保留原始副本。'};});
 }
}
let dbPromise;
function database(){if(!dbPromise)dbPromise=new Promise((resolve,reject)=>{const r=indexedDB.open('ankang-phone-files-2',1);r.onupgradeneeded=()=>r.result.createObjectStore('files');r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);r.onblocked=()=>reject(Error('资料库被占用，请重新打开应用'));});return dbPromise;}
async function fileOp(mode,operation){const db=await database();return new Promise((resolve,reject)=>{const tx=db.transaction('files',mode),r=operation(tx.objectStore('files'));tx.oncomplete=()=>resolve(r.result);tx.onabort=()=>reject(tx.error||Error('资料未保存'));tx.onerror=()=>reject(tx.error||Error('资料库错误'));});}
const files={get:id=>fileOp('readonly',s=>s.get(id)),all:()=>fileOp('readonly',s=>s.getAll()),put:(id,v)=>fileOp('readwrite',s=>s.put(v,id)),remove:id=>fileOp('readwrite',s=>s.delete(id))};
function attachments(owner){return{
 list:async scope=>(await files.all()).filter(x=>x.kind==='archive'&&x.ownerId===scope.ownerId&&x.dataMode===scope.dataMode).map(x=>({...x,bytes:new Uint8Array(x.bytes)})),
 put:async(scope,a)=>{if(scope.ownerId!==owner||a.ownerId!==owner)throw Error('资料不属于本人');if(a.bytes.byteLength>8*1048576)throw Error('资料超过 8 MB');const all=(await files.all()).filter(x=>x.kind==='archive'&&x.ownerId===owner&&x.id!==a.id);if(all.length>=50||all.reduce((n,x)=>n+x.bytes.byteLength,0)+a.bytes.byteLength>64*1048576)throw Error('资料存储已满');await files.put(a.id,{...a,kind:'archive',bytes:new Uint8Array(a.bytes)});},
 clear:async scope=>{for(const a of await files.all())if(a.kind==='archive'&&a.ownerId===scope.ownerId)await files.remove(a.id);},
 setTrash:async(scope,id,at)=>{const a=await files.get(id);if(!a||a.ownerId!==scope.ownerId)throw Error('找不到本人资料');await files.put(id,{...a,trashedAt:at||undefined});}
};}
const DATE=/^\d{4}-\d{2}-\d{2}$/,TIME=/^(?:[01]\d|2[0-3]):[0-5]\d$/;
function day(){const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;}
function validDate(value){if(typeof value!=='string'||!DATE.test(value))return false;const time=Date.parse(value+'T12:00:00');return Number.isFinite(time)&&new Date(time).toISOString().slice(0,10)===value;}
function validateBackup(b){
 const bad=()=>{throw Error('备份结构或测量版本无效');};
 if(b?.kind!=='ankang-phone-backup'||b.version!==2||!b.data||JSON.stringify(b).length>12*1048576)bad();
 const v=clone(b.data),uuid=/^[a-f0-9-]{36}$/;
 if(v.version!==2||!uuid.test(v.owner)||!v.kv||Array.isArray(v.kv)||!Array.isArray(v.jobs)||v.jobs.length>250||!Array.isArray(v.plans)||v.plans.length>250||!v.daily||!Array.isArray(v.daily.schedules)||!v.daily.medSchedules||!v.daily.doses||!Array.isArray(v.daily.doseAudit)||!v.kv['profile:'+v.owner]?.profile)bad();
 const p=v.kv['profile:'+v.owner].profile;if(typeof p.name!=='string'||p.name.length>40||!Number.isInteger(p.age)||p.age<0||p.age>130||!Array.isArray(p.conditions)||!Array.isArray(p.medicationRecords||[]))bad();
 for(const key of Object.keys(v.kv))if(!/^(profile|health|tasks|audit|notifications|family|healthkit-revision|sync-consent|sync-summary):/.test(key)||!key.includes(v.owner)||key.includes('__proto__'))bad();
 for(const j of v.jobs){if(!uuid.test(j.id)||!['assessment','training','fitness','posture'].includes(j.mode)||!['done','failed'].includes(j.state)||!['left','right'].includes(j.side)||!Number.isFinite(Date.parse(j.created_at)))bad();if(j.state==='done'&&(j.measurement_version!=='android-local-projection-1'||j.result?.local_report?.contract!=='android-local-projection-1'||!j.result.summary))bad();}
 const ids=new Set(v.jobs.map(j=>j.id));if(ids.size!==v.jobs.length)bad();
 for(const plan of v.plans){if(!uuid.test(plan.id)||!Number.isInteger(plan.revision)||!Array.isArray(plan.items)||plan.items.length>53)bad();for(const i of plan.items)if(!uuid.test(i.key)||!['left','right'].includes(i.side)||!Number.isInteger(i.settings?.target_reps)||i.settings.target_reps<1||i.settings.target_reps>5||!ids.has(i.assessment_id))bad();}
 // Permissions are server-authoritative and never revived from a stale backup.
 v.daily.grants={};return v;
}
function applyDaily(store,operation,p,profile){return store.change(v=>{
 const d=v.daily,med=(profile.medicationRecords||[]).find(m=>m.id===p.medId);
 if(operation==='medSchedule'){
  if(!med||!Array.isArray(p.times)||p.times.length<1||p.times.length>12||p.times.some(t=>!TIME.test(t))||!validDate(p.start)||(p.end&&(!validDate(p.end)||p.end<p.start)))throw Error('请核对药物、日期和 HH:mm 时间');
  d.medSchedules[p.medId]={times:[...new Set(p.times)].sort(),start:p.start,end:p.end||'',savedAt:now()};
 }else if(operation==='dose'){
  if(!med||!validDate(p.date)||p.date>day()||!TIME.test(p.time)||!['taken','skipped','unrecorded'].includes(p.status))throw Error('用药记录无效');
  const key=p.medId+'|'+p.date+'|'+p.time,s=d.medSchedules[p.medId];if(!d.doses[key]&&(!s||!s.times.includes(p.time)||p.date<s.start||(s.end&&p.date>s.end)))throw Error('该次服药不在已保存的安排中');
  const record={...p,medName:med.name,recordedAt:now()},previous=d.doses[key]?.status||'unrecorded';d.doses[key]=record;d.doseAudit.unshift({at:now(),record:{...record,previous}});d.doseAudit=d.doseAudit.slice(0,300);
 }else if(operation==='schedule'){
  if(!validDate(p.date)||p.date<day()||!TIME.test(p.time)||!['assessment','training'].includes(p.kind)||typeof p.name!=='string'||p.name.length>100)throw Error('请核对安排日期和时间');
  if(p.kind==='training'&&!v.plans.some(x=>x.id===p.planId&&x.revision===p.revision))throw Error('请选择已保存的计划');
  if(d.schedules.some(x=>x.date===p.date&&x.time===p.time&&x.planId===p.planId&&x.id!==p.id))throw Error('该时间已经安排同一计划');
  const item={...p,id:p.id||crypto.randomUUID(),createdAt:now()};d.schedules=d.schedules.filter(x=>x.id!==item.id).concat(item);
 }else if(operation==='unschedule'){
  if(!d.schedules.some(x=>x.id===p.id))throw Error('安排已变化，请刷新');d.schedules=d.schedules.filter(x=>x.id!==p.id);
 }else throw Error('此操作需要连接演示云端');
 return{dailyReceipt:true};
});}
root.PhoneStore={Store,files,attachments,applyDaily,day,validDate,validateBackup,KEY};
if(typeof module!=='undefined')module.exports=root.PhoneStore;
})(globalThis);
