const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(__dirname+'/../web/cloud.js','utf8');
function fixture({account=true,legacy=true}={}){
 const calls=[],identity={account_id:crypto.randomUUID(),patient_id:crypto.randomUUID()};
 const store={key:account?'cloud:current':'local',value:{owner:identity.patient_id,cloudIdentity:structuredClone(identity)}};
 let current=identity;
 const c={PhoneStore:{LIN_KEY:'lin',cloudKey:k=>k==='cloud:current'},PhoneLocal:{store},
  PhoneAccount:{identity:()=>current,validateIdentity:v=>{if(!v)throw Error('signed out');return v;},aiScope:s=>{if(!current)throw Error('signed out');return current;},request:async(action,value,body)=>{calls.push({action,value,body});return {ok:true};}},
  OfflineAndroid:{cloudConfigured:()=>legacy,cloudRequest:(id,path,method,body)=>{calls.push({legacy:true,path});c.PhoneCloud.reply(id,200,'{"ok":true}');}},
  setTimeout,clearTimeout,Map,Promise,Error};vm.runInNewContext(source,c);
 return {c,calls,identity,store,setIdentity:x=>current=x};
}
test('logged-in account family does not require or use old device connection code',async()=>{
 const h=fixture({legacy:false});assert.equal(h.c.PhoneCloud.configured(),false);assert.equal(h.c.PhoneCloud.familyConfigured(),true);
 for(const [path,method,data,action] of [['/v1/family','GET',null,'family'],['/v1/family/invite','POST',{},'familyInvite'],['/v1/family/bind','POST',{code:'1234ABCD'},'familyBind'],['/v1/family/grant','POST',{member:'x',categories:[]},'familyGrant'],['/v1/family/unbind','POST',{member:'x'},'familyUnbind'],['/v1/summary','PUT',{name:'TEST'},'familySummary']]){
  await h.c.PhoneCloud.request(path,method,data);assert.equal(h.calls.at(-1).action,action);assert.equal(h.calls.at(-1).value.patient_id,h.identity.patient_id);
 }
 assert(!h.calls.some(c=>c.legacy));await assert.rejects(h.c.PhoneCloud.request('/v1/backup'),/独立/);
});
test('cloud profile cannot silently fall back to someone else legacy device session',async()=>{
 const h=fixture();h.setIdentity(null);assert.equal(h.c.PhoneCloud.familyConfigured(),false);
 await assert.rejects(h.c.PhoneCloud.request('/v1/family/invite','POST',{}),/登录/);assert.equal(h.calls.length,0);
});
test('account change during reply discards old family data',async()=>{
 const h=fixture();h.c.PhoneAccount.request=async()=>{h.setIdentity({...h.identity,account_id:crypto.randomUUID()});return {familyMembers:['TEST_OLD_PRIVATE']};};
 await assert.rejects(h.c.PhoneCloud.request('/v1/family'),/账号已变化/);
});
test('unbound legacy profiles retain original family transport',async()=>{
 const h=fixture({account:false});assert(h.c.PhoneCloud.familyConfigured());await h.c.PhoneCloud.request('/v1/family');assert(h.calls[0].legacy);
});
test('main baseline without assistant scope still validates the current account family identity',async()=>{
 const h=fixture({legacy:false});delete h.c.PhoneAccount.aiScope;assert(h.c.PhoneCloud.familyConfigured());await h.c.PhoneCloud.request('/v1/family');assert.equal(h.calls[0].action,'family');
 h.store.value.cloudIdentity.account_id=crypto.randomUUID();await assert.rejects(h.c.PhoneCloud.request('/v1/family'),/登录/);
});
