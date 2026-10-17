(function(root){
'use strict';
// Provider credentials and every paid request belong to the account gateway.
function cloudConfigured(){try{return !!root.PhoneAccount?.aiScope(root.PhoneLocal?.store);}catch{return false;}}
function configured(){return cloudConfigured();}
function request(){return Promise.reject(Error('智能问答统一通过云账号连接，请先登录'));}
function reply(){} // Ignore late native callbacks from retired personal-key requests.
function conversationModel(){
 if(!cloudConfigured())return undefined;
 return {async reply({messages,purpose='reply'}){
  if(!['reply','understanding'].includes(purpose))throw Error('问答任务无效');
  if(!Array.isArray(messages)||!messages.length||messages.length>16||messages.at(-1).role!=='user'||messages.some(m=>!['user','assistant'].includes(m.role)||typeof m.content!=='string'||!m.content.trim())||messages.reduce((n,m)=>n+m.content.length,0)>12000)throw Error('对话上下文无效');
  const r=await root.PhoneAccount.askAI(root.PhoneLocal.store,messages.map(m=>m.role+'：'+m.content).join('\n'),purpose);
  if(!['SUCCEEDED','UNMETERED'].includes(r.state)||typeof r.answer!=='string'||!r.answer.trim())throw Error('云端问答结果待核对');
  return r.answer;
 }};
}
function agentModel(){return undefined;}
function changed(){
 // Reload reconstructs domain sessions; persisted ordinary history remains owner scoped.
 root.location.reload();
}
root.PhoneDeepSeek={configured,request,reply,conversationModel,agentModel,changed};
})(globalThis);
