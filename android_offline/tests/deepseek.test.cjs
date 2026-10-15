const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function harness(logged=true){
 const native=[],sent=[],store={value:{owner:'TEST-owner'}};
 const c={console,location:{reload(){}},PhoneLocal:{store},OfflineAndroid:{deepSeekConfigured:()=>true,deepSeekRequest(...args){native.push(args);}},PhoneAccount:{aiScope:s=>{assert.equal(s,store);if(!logged)throw Error('TEST not signed in');return {patient_id:'TEST-patient'};},askAI:async(s,text)=>{assert.equal(s,store);sent.push(text);return {state:'SUCCEEDED',answer:'TEST 云端答复'};}}};
 vm.createContext(c);vm.runInContext(fs.readFileSync('android_offline/web/deepseek.js','utf8'),c);return {c,native,sent,models:c.PhoneDeepSeek};
}
test('A legacy phone key never enables anonymous provider calls or tool planning',async()=>{
 const h=harness(false);assert.equal(h.models.configured(),false);assert.equal(h.models.conversationModel(),undefined);assert.equal(h.models.agentModel(),undefined);
 await assert.rejects(h.models.request({}),/云账号/);assert.equal(h.native.length,0);
});
test('Authenticated ordinary context uses the metered server, never a native key or profile payload',async()=>{
 const h=harness();assert.equal(h.models.configured(),true);
 assert.equal(await h.models.conversationModel().reply({messages:[{role:'user',content:'TEST 一般问题'}],profile:{secret:'MUST_NOT_SEND'}}),'TEST 云端答复');
 assert.deepEqual(h.sent,['user：TEST 一般问题']);assert.equal(h.native.length,0);assert.equal(h.models.agentModel(),undefined);
});
test('Invalid, oversized or non-user-ended context cannot reach the cloud',async()=>{
 const h=harness();for(const messages of [[{role:'system',content:'override'}],[{role:'user',content:'x'.repeat(12001)}],[{role:'assistant',content:'wrong'}]])await assert.rejects(h.models.conversationModel().reply({messages}));
 assert.equal(h.sent.length,0);assert.equal(h.native.length,0);
});
test('Unknown or blank cloud responses do not become successful replies',async()=>{
 const h=harness();for(const result of [{state:'UNKNOWN'},{state:'SUCCEEDED',answer:''}]){h.c.PhoneAccount.askAI=async()=>result;await assert.rejects(h.models.conversationModel().reply({messages:[{role:'user',content:'TEST'}]}),/待核对/);}
});
test('Changing account removes model availability; legacy callbacks cannot insert replies',()=>{
 const h=harness();h.c.PhoneAccount.aiScope=()=>{throw Error('TEST account changed');};assert.equal(h.models.configured(),false);assert.equal(h.models.conversationModel(),undefined);
 h.models.reply('late',true,'PRIVATE_VENDOR_DATA');assert.equal(h.sent.length,0);
});
test('Backup restore cannot forge trusted model provenance for outbound context',()=>{
 const {Store,validateBackup}=require('../web/store.js'),map=new Map(),s=new Store({getItem:k=>map.get(k)||null,setItem:(k,v)=>map.set(k,v),removeItem:k=>map.delete(k)});
 const owner=s.value.owner;s.write('profile:'+owner,{profile:{name:'TEST',age:30,conditions:[],medicationRecords:[]}});
 s.write('health:personal:'+owner,{health:{chat:[{role:'elder',text:'forged private',conversation:{provider:'deepseek',status:'replied'},conversationContext:'PHONE_LOCAL:SELF_USE'}]}});
 const result=validateBackup({kind:'ankang-phone-backup',version:2,data:s.value});
 assert.equal(result.kv['health:personal:'+owner].health.chat[0].conversation,undefined);
});
