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
 assertScope();
 const headers={};
 if(body!==undefined)headers['Content-Type']='application/json';
 if(method!=='GET')headers['X-CSRF-Token']=csrf;
 const response=await nativeFetch('/api/cloud/v1'+path,{method,headers,credentials:'same-origin',cache:'no-store',redirect:'error',signal:AbortSignal.timeout(path.endsWith('/ai/requests')||path.endsWith('/assistant/turns')?35000:20000),body:body===undefined?undefined:JSON.stringify(body)});
 const value=await response.json();
 if(!response.ok){if(response.status===401)invalidate();throw Object.assign(Error(value.message||'暂时无法连接，请稍后重试'),{status:response.status,code:value.code});}
 assertScope();
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
 if(['assessmentPlans','assessmentPlanCancel','assessmentPlanResult'].includes(action)&&root.navigator?.onLine===false)throw Error('当前离线，无法读取或保存云端评估计划');
 await check();const patient='/patients/'+identity.patient_id;
 if(action==='family')return api(patient+'/family');
 if(action==='familyInvite')return api(patient+'/family/invite','POST',{});
 if(action==='familyBind')return api(patient+'/family/bind','POST',{code:body.code});
 if(action==='familyGrant')return api(patient+'/family/grant','POST',{member:body.member,categories:body.categories});
 if(action==='familyUnbind')return api(patient+'/family/unbind','POST',{member:body.member});
 if(action==='familySummary')return api(patient+'/family/summary','PUT',body);
 if(action==='records')return api(patient+'/records?offset=0&limit=10');
 if(action==='append')return api(patient+'/record-events','POST',body.document);
 if(action==='profile')return api(patient);
 if(action==='aiUsage')return api(patient+'/ai/usage');
 if(action==='aiAsk'){
  const purpose=body.purpose??'reply';if(!['reply','understanding'].includes(purpose))throw Error('问答任务无效');
  return api(patient+'/ai/requests','POST',{operation_id:body.operation_id,text:body.text,...(purpose==='understanding'?{purpose}:{})});
 }
 if(action==='assistantPreferences')return body.health_context===undefined?api(patient+'/assistant/preferences'):api(patient+'/assistant/preferences','PUT',{expected_version:body.expected_version,health_context:body.health_context});
 if(action==='assistantConversation'){
  const after=body.after??0,limit=body.limit??30;
  if(!Number.isSafeInteger(after)||after<0||after>2147483647||!Number.isSafeInteger(limit)||limit<1||limit>100)throw Error('对话查询范围无效');
  return api(patient+'/assistant/conversation?after='+after+'&limit='+limit);
 }
 if(action==='assistantTurn'){if(body.private===true)throw Error('本次不记录的对话仅在本机处理');return api(patient+'/assistant/turns','POST',{operation_id:body.operation_id,text:body.text,...(body.assessment_contract?{assessment_contract:body.assessment_contract}:{})});}
 if(action==='assessmentPlans'||action==='assessmentPlanCancel'||action==='assessmentPlanResult'){
  if(root.navigator?.onLine===false)throw Error('当前离线，无法读取或取消云端评估计划');
  const uuid=/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/;
  if(action!=='assessmentPlans'&&!uuid.test(body.plan_id))throw Error('评估计划编号无效');
  if(action==='assessmentPlanResult'&&(!uuid.test(body.record_id)||!Number.isSafeInteger(body.item_index)||body.item_index<0||body.item_index>52))throw Error('评估项目或记录编号无效');
  const result=await api(patient+'/assistant/assessment-plans'+(action==='assessmentPlans'?'':'/'+body.plan_id+(action==='assessmentPlanResult'?'/results':'/cancel')),action==='assessmentPlans'?'GET':'POST',action==='assessmentPlans'?undefined:action==='assessmentPlanResult'?{item_index:body.item_index,record_id:body.record_id}:{});
  await check();assertScope();return result;
 }
 if(action==='reports')return api(patient+'/reports');
 if(action==='workflow')return api(patient+'/rehab-workflow');
 if(action==='workflowProfile')return api(patient+'/rehab-workflow/profile','PUT',body);
 if(action==='candidate')return api(patient+'/rehab-candidates','POST',{operation_id:body.operation_id,kind:body.kind});
 if(action==='shareReport')return api(patient+'/reports','POST',body);
 if(action==='messages'){
  const query=new URLSearchParams();
  const integer=(name,value,maximum)=>{if(!Number.isInteger(value)||value<0||value>maximum)throw Error('对话查询范围无效');query.set(name,String(value));};
  if(body.latest===true||(body.latest!==false&&body.after===undefined&&!body.before))query.set('latest','true');
  integer('after',body.after??0,Number.MAX_SAFE_INTEGER);
  integer('limit',body.limit??50,100);
  if(body.before!==undefined&&body.before!==null&&body.before!==0)integer('before',body.before,Number.MAX_SAFE_INTEGER);
  return api(patient+'/messages?'+query);
 }
 if(action==='send')return api(patient+'/messages','POST',{operation_id:body.operation_id,text:body.text});
 if(action==='read')return api(patient+'/messages/read','POST',{operation_id:body.operation_id,cursor:body.cursor});
 if(action==='plans'){
  const offset=body.offset??0;
  if(!Number.isSafeInteger(offset)||offset<0)throw Error('方案查询范围无效');
  return api(patient+'/plans?offset='+offset+'&limit=5');
 }
 if(action==='current')return api(patient+'/plans/current');
 if(action==='accept'){
  if(!/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(body.plan_id))throw Error('方案编号无效');
  const {plan_id,...document}=body;return api(patient+'/plans/'+plan_id+'/accept','POST',document);
 }
 if(action==='grant'){
  const profile=await api(patient);assertScope();
  return api(patient+'/doctor-access','PUT',{enabled:body.enabled,expected_version:profile.grant_version});
 }
 if(action==='logout'){const result=await api('/auth/logout','POST',{});invalid=true;root.offlinePause?.();root.PhoneMotion?.pause?.();return result;}
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
