/* Optional companion transport; personal data never waits for a cloud connection. */
(function(root){
'use strict';
const pending=new Map();let sequence=0;
function configured(){if(root.PhoneLocal?.store.key===PhoneStore.LIN_KEY)return false;return !!root.OfflineAndroid?.cloudConfigured();}
function request(path,method='GET',data=null){
 if(!configured())return Promise.reject(Error('尚未连接云端。长按右上角“我的档案”设置；个人功能仍可离线使用。'));
 return new Promise((resolve,reject)=>{const id=String(++sequence),timer=setTimeout(()=>{pending.delete(id);reject(Error('云端暂时无法连接，本机记录保留'));},15000);pending.set(id,{resolve,reject,timer});OfflineAndroid.cloudRequest(id,path,method,data===null?'':JSON.stringify(data));});
}
function reply(id,status,body){const p=pending.get(id);if(!p)return;pending.delete(id);clearTimeout(p.timer);try{const result=JSON.parse(body);if(status>=200&&status<300)p.resolve(result);else p.reject(Error(result.detail||'云端请求失败'));}catch{p.reject(Error('云端返回格式不正确'));}}
async function publish(local){
 const snap=await local.domain.request('snapshot',local.store.value.owner,{},new Date()),b=await local.body();
 // Only independently marked family_ok measurements. Never chat or originals.
 const permitted=new Set(Object.values(local.cloudState.grants).flat());
 const health=permitted.has('health')?snap.state.events.filter(e=>e.measurement?.visibility==='family_ok').slice(-30).map(e=>({timestamp:e.timestamp,text:(e.measurement.metric+'：'+e.measurement.value+' '+e.measurement.unit).slice(0,300)})):[];
 const rehab=permitted.has('rehab')?b.records.slice(-20).map(r=>({timestamp:r.created_at,text:r.label+' · '+(r.summary.completed??0)+' 次'+(r.summary.plan_completed?' · 完成目标':'')})):[];
 const doses=permitted.has('medication')?Object.values(local.store.value.daily.doses).slice(-30).map(({medName,date,time,status})=>({medName,date,time,status})):[];
 return request('/v1/summary','PUT',{name:snap.profile.profile.name,health,rehab,doses});
}
root.PhoneCloud={configured,request,reply,publish};
})(globalThis);
