/* Same-origin Cookie transport for the unchanged phone-local product. */
(function(root){
'use strict';
const nativeFetch=root.fetch.bind(root),PS=root.PhoneStore;
const initial=JSON.parse(document.getElementById('ankang-web-identity').textContent);
const identity=Object.freeze({...initial,origin:location.origin});
if(identity.role!=='PATIENT'||!PS.cloudKey(PS.CLOUD_PREFIX+identity.patient_id))throw Error('请使用本人账号登录');
const key=PS.CLOUD_PREFIX+identity.patient_id,store=new PS.Store(localStorage,key);
store.change(v=>{if(v.fixture)throw Error('此档案不是本人记录');v.cloudIdentity=structuredClone(identity);});
localStorage.setItem(PS.ACTIVE_KEY,key);
let invalid=false,csrf='',checking=null;
function invalidate(){
 if(invalid)return;invalid=true;root.offlinePause?.();root.PhoneMotion?.pause?.();
 location.replace('/account?next=/');
}
function assertScope(){
 if(invalid||localStorage.getItem(PS.ACTIVE_KEY)!==key){invalidate();throw Error('账号已变化，请重新打开本人档案');}
}
async function api(path,method='GET',body){
 const headers={};
 if(body!==undefined)headers['Content-Type']='application/json';
 if(method!=='GET')headers['X-CSRF-Token']=csrf;
 const response=await nativeFetch('/api/cloud/v1'+path,{method,headers,credentials:'same-origin',cache:'no-store',redirect:'error',signal:AbortSignal.timeout(20000),body:body===undefined?undefined:JSON.stringify(body)});
 const value=await response.json();
 if(!response.ok){if(response.status===401)invalidate();throw Error(value.message||'暂时无法连接，请稍后重试');}
 return value;
}
async function check(){
 assertScope();if(checking)return checking;
 checking=(async()=>{
  const value=await api('/auth/me');
  if(value.patient_id!==identity.patient_id||value.account_id!==identity.account_id||value.role!=='PATIENT'){invalidate();throw Error('登录账号已变化');}
  csrf=value.csrf_token;assertScope();return value;
 })().finally(()=>{checking=null;});return checking;
}
async function request(action,value,body={}){
 assertScope();if(value.patient_id!==identity.patient_id||value.account_id!==identity.account_id)throw Error('记录不属于当前账号');
 await check();const patient='/patients/'+identity.patient_id;
 if(action==='records')return api(patient+'/records?offset=0&limit=10');
 if(action==='append')return api(patient+'/record-events','POST',body.document);
 if(action==='grant'){
  const profile=await api(patient);assertScope();
  return api(patient+'/doctor-access','PUT',{enabled:body.enabled,expected_version:profile.grant_version});
 }
 if(action==='logout'){const result=await api('/auth/logout','POST',{});invalid=true;root.offlinePause?.();return result;}
 throw Error('云操作未开放');
}
async function login(){
 if(root.PhoneMotion?.active){alert('请先结束当前分析');return;}
 try{await root.PhoneLocal?.store.tail;await request('logout',identity);location.assign('/account?next=/');}
 catch(e){if(!invalid)alert(e.message);}
}
root.AnkangBrowserAccount={origin:location.origin,identity:()=>identity,request,login,assertScope,check};
root.AnkangBrowserAccount.ready=check();
// Mark the promise handled; the local adapter also awaits it before any writes.
root.AnkangBrowserAccount.ready.catch(()=>{});
addEventListener('storage',event=>{if(event.key===PS.ACTIVE_KEY&&event.newValue!==key)invalidate();});
addEventListener('pageshow',event=>{if(event.persisted)check().catch(()=>{});});
addEventListener('focus',()=>check().catch(()=>{}));
})(globalThis);
