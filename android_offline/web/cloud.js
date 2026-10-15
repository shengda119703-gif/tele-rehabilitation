/* Optional companion transport; personal data never waits for a cloud connection. */
(function(root){
'use strict';
const pending=new Map();let sequence=0;
function configured(){if(root.PhoneLocal?.store.key===PhoneStore.LIN_KEY)return false;return !!root.OfflineAndroid?.cloudConfigured();}
function accountFamily(){
 const local=root.PhoneLocal,store=local?.store;
 if(!store||!root.PhoneStore.cloudKey(store.key)||store.value.fixture)return null;
 try{const value=root.PhoneAccount.aiScope(store);if(store.value.owner!==value.patient_id)return null;return{value,store};}catch{return null;}
}
function familyConfigured(){return !!accountFamily()||(!root.PhoneStore.cloudKey(root.PhoneLocal?.store.key)&&configured());}
function request(path,method='GET',data=null){
 const family=accountFamily(),accountProfile=root.PhoneStore.cloudKey(root.PhoneLocal?.store.key);
 if(family||accountProfile){
  if(!family)return Promise.reject(Error('请先登录当前本人账号，再管理家人关联'));
  const action=path==='/v1/family'&&method==='GET'?'family':path==='/v1/summary'&&method==='PUT'?'familySummary':method==='POST'?({'/v1/family/invite':'familyInvite','/v1/family/bind':'familyBind','/v1/family/grant':'familyGrant','/v1/family/unbind':'familyUnbind'})[path]:null;
  if(!action)return Promise.reject(Error('此操作不属于账号家庭服务；原设备备份通道保持独立'));
  return root.PhoneAccount.request(action,family.value,data||{}).then(result=>{const current=accountFamily();if(!current||current.value.account_id!==family.value.account_id||current.value.patient_id!==family.value.patient_id)throw Error('账号已变化，请刷新后查看家人');return result;});
 }
 if(!configured())return Promise.reject(Error('尚未连接云端。长按右上角“我的档案”设置；个人功能仍可离线使用。'));
 return new Promise((resolve,reject)=>{const id=String(++sequence),timer=setTimeout(()=>{pending.delete(id);reject(Error('云端暂时无法连接，本机记录保留'));},15000);pending.set(id,{resolve,reject,timer});OfflineAndroid.cloudRequest(id,path,method,data===null?'':JSON.stringify(data));});
}
function reply(id,status,body){const p=pending.get(id);if(!p)return;pending.delete(id);clearTimeout(p.timer);try{const result=JSON.parse(body);if(status>=200&&status<300)p.resolve(result);else p.reject(Error(result.detail||'云端请求失败'));}catch{p.reject(Error('云端返回格式不正确'));}}
async function publish(local){
 const snap=await local.domain.request('snapshot',local.store.value.owner,{},new Date()),b=await local.body();
 // Only independently marked family_ok measurements. Never chat or originals.
 const permitted=new Set(Object.values(local.cloudState.grants).flat());
 const health=permitted.has('health')?snap.state.events.filter(e=>e.measurement?.visibility==='family_ok').slice(-10).map(e=>({timestamp:e.timestamp,text:(e.measurement.metric+'：'+e.measurement.value+' '+e.measurement.unit).slice(0,300)})):[];
 const rehab=permitted.has('rehab')?b.records.slice(-10).map(r=>({timestamp:r.created_at,text:(r.label+' · '+(r.summary.completed??0)+' 次'+(r.summary.plan_completed?' · 完成目标':'')).slice(0,300)})):[];
 const doses=permitted.has('medication')?Object.values(local.store.value.daily.doses).slice(-10).map(({medName,date,time,status})=>({medName,date,time,status})):[];
 return request('/v1/summary','PUT',{name:snap.profile.profile.name,health,rehab,doses});
}
root.PhoneCloud={configured,familyConfigured,request,reply,publish};
})(globalThis);
