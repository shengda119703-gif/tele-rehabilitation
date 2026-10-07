/* A named TEST account, isolated from the existing personal store and cloud. */
(function(root){
'use strict';
const SCHEMA='test-lin-apk-v1',PS=PhoneStore;
function isLin(store){const v=store.value;return store.key===PS.LIN_KEY&&v.fixture?.schema===SCHEMA&&v.fixture.synthetic===true&&v.fixture.primaryOwner===v.owner&&v.kv['profile:'+v.owner]?.profile.name==='TEST 林女士';}
function rebase(payload,at=new Date()){
 const p=structuredClone(payload),anchor=new Date(p.data.fixture.anchor),localDate=d=>new Date(d.getFullYear(),d.getMonth(),d.getDate(),12),days=Math.round((localDate(at)-localDate(anchor))/86400000),delta=at-anchor;
 const move=v=>{
  if(Array.isArray(v))return v.map(move);
  if(v&&typeof v==='object')return Object.fromEntries(Object.entries(v).map(([k,x])=>[k.replace(/\|\d{4}-\d{2}-\d{2}\|/,m=>'|'+move(m.slice(1,-1))+'|'),move(x)]));
  if(typeof v!=='string')return v;
  if(/^\d{4}-\d{2}-\d{2}T/.test(v)&&Number.isFinite(Date.parse(v)))return new Date(Date.parse(v)+delta).toISOString();
  if(/^\d{4}-\d{2}-\d{2}$/.test(v)){const d=new Date(v+'T12:00:00');d.setDate(d.getDate()+days);return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;}
  return v;
 };
 const shifted=move(p);
 shifted.data.fixture.importedAt=at.toISOString();
 shifted.data.fixture.originalAnchor=payload.data.fixture.anchor;
 for(const [key,dose]of Object.entries(shifted.data.daily.doses))if(new Date(dose.date+'T'+dose.time+':00')>at)delete shifted.data.daily.doses[key];
 return shifted;
}
function validate(payload){
 if(payload?.schema!==SCHEMA||payload.synthetic!==true||payload.name!=='TEST 林女士'||payload.data.fixture?.schema!==SCHEMA||!Array.isArray(payload.attachments)||payload.attachments.length!==3)throw Error('林女士档案资源不完整');
 const value=PS.validateBackup({kind:'ankang-phone-backup',version:2,data:payload.data});
 if(value.jobs.length!==24||value.plans.length!==1||value.plans[0].items.length!==4||value.jobs.some(j=>j.synthetic!==true||j.fixture!=='test-lin-profile-v1'||j.video_available!==false))throw Error('林女士记录资源不完整');
 if(payload.attachments.some(a=>a.ownerId!==value.owner||a.dataMode!=='demo'||a.mediaType!=='text/plain'||!Array.isArray(a.bytes)||a.bytes.length>32768))throw Error('林女士资料来源不正确');
 return value;
}
async function initialize(store,fetchAsset=root.fetch.bind(root),at=new Date()){
 if(store.key!==PS.LIN_KEY)return false;
 if(store.profiles().length){if(!isLin(store))throw Error('该位置已有其他档案，未覆盖');return false;}
 if(store.value.jobs.length||Object.keys(store.value.kv).length)throw Error('该位置已有记录，未覆盖');
 const response=await fetchAsset('/lin-profile.json');if(!response.ok)throw Error('无法读取林女士档案资源');
 const original=await response.json();validate(original);
 const p=rebase(original,at),value=validate(p),port=PS.attachments(value.owner);
 // Originals first, main state atomically last. Retry never overwrites a different owner.
 for(const a of p.attachments){const existing=await PS.files.get(a.id);if(existing&&(existing.ownerId!==a.ownerId||existing.dataMode!=='demo'||existing.kind!=='archive'))throw Error('资料编号已占用，未覆盖');await port.put({ownerId:value.owner,dataMode:'demo'},{...a,bytes:new Uint8Array(a.bytes)});}
 store.commit(value);return true;
}
function family(store){return isLin(store)?structuredClone(store.value.fixture.familyMembers||[]):[];}
function familyOperation(store,operation,p){
 if(!isLin(store))throw Error('请先连接云端');
 if(!['familyGrant','familyUnbind'].includes(operation))throw Error('新关联需要两台手机连接同一云端；已有家庭记录可直接查看。');
 return store.change(v=>{
  if(!v.fixture.familyMembers.some(m=>m.ownerId===p.member))throw Error('找不到当前家庭关联');
  if(operation==='familyGrant'){
   if(!Array.isArray(p.categories)||p.categories.some(c=>!['health','rehab','medication'].includes(c)))throw Error('共享范围无效');
   v.daily.grants[p.member]=[...new Set(p.categories)];
  }else{v.fixture.familyMembers=v.fixture.familyMembers.filter(m=>m.ownerId!==p.member);delete v.daily.grants[p.member];}
  return{dailyReceipt:true};
 });
}
async function select(store,key){
 if(![PS.KEY,PS.LIN_KEY].includes(key))throw Error('档案位置无效');
 if(root.PhoneMotion?.active)throw Error('请先结束当前分析');
 await store.tail;
 store.storage.setItem(PS.ACTIVE_KEY,key);
 if(root.location)root.location.href='/';
}
root.PhoneLin={isLin,rebase,validate,initialize,family,familyOperation,select};
if(typeof module!=='undefined')module.exports=root.PhoneLin;
})(globalThis);
