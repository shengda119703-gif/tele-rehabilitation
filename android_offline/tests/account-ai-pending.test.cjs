// Fictitious accounts, in-memory storage and RPC responses only; no AI/network calls.
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const plain=value=>JSON.parse(JSON.stringify(value));
const noDispatch=['AI_NOT_CONFIGURED','AI_BUSY','AI_QUOTA_EXHAUSTED','AI_REJECTED'];
function failure(code='',status=0){return Object.assign(Error('TEST '+(code||'network/timeout')),{code,status});}
function environment(native=false){
 const rows=new Map(),storage={getItem:key=>rows.get(key)??null,setItem:(key,value)=>rows.set(key,String(value))};
 const cloud={identity:{origin:'https://139.224.216.18',role:'PATIENT',patient_id:crypto.randomUUID(),account_id:crypto.randomUUID(),username:'TEST pending'},calls:[],handler:()=>({state:'SUCCEEDED',answer:'TEST answer'})};
 const c={crypto,structuredClone,setTimeout,clearTimeout,localStorage:storage};
 async function request(action,identity,body){assert(['aiAsk','assistantPreferences','assistantConversation','assistantTurn','candidate','workflow','workflowProfile','assessmentPlans','assessmentPlanCancel'].includes(action));cloud.calls.push(plain(body));return cloud.handler(body,action);}
 c.AnkangBrowserAccount={origin:cloud.identity.origin,identity:()=>cloud.identity,request};
 vm.createContext(c);
 for(const file of ['store.js','account.js'])vm.runInContext(fs.readFileSync(path.resolve(__dirname,'../web/'+file),'utf8'),c);
 c.PhoneAccount.schedule=()=>{};
 const store=new c.PhoneStore.Store(storage,c.PhoneStore.CLOUD_PREFIX+cloud.identity.patient_id);
 store.change(value=>{value.cloudIdentity=plain(cloud.identity);value.cloudBinding={patient_id:cloud.identity.patient_id,owner:value.owner};});
 if(native){
  c.AnkangBrowserAccount=null;
  c.OfflineAndroid={accountIdentity:()=>JSON.stringify(cloud.identity),accountRequest:(id,action,raw)=>{
   request(action,cloud.identity,JSON.parse(raw)).then(result=>c.PhoneAccount.reply(id,200,JSON.stringify(result)),error=>c.PhoneAccount.reply(id,error.status||503,JSON.stringify({code:error.code,message:error.message})));
  }};
 }
 return {account:c.PhoneAccount,cloud,store,context:c,storage,reopen:()=>new c.PhoneStore.Store(storage,store.key)};
}

for(const native of [false,true])for(const code of noDispatch)test(`${native?'native':'browser'} ${code} releases pending and permits a different question`,async()=>{
 const h=environment(native);h.cloud.handler=()=>{throw failure(code,code==='AI_BUSY'||code==='AI_QUOTA_EXHAUSTED'?429:503);};
 await assert.rejects(h.account.askAI(h.store,'TEST first'),error=>error.code===code);
 assert.equal(h.reopen().value.cloudAiPending,undefined);
 h.cloud.handler=()=>({state:'SUCCEEDED',answer:'TEST second answer'});
 assert.equal((await h.account.askAI(h.store,'TEST second')).answer,'TEST second answer');
 assert.notEqual(h.cloud.calls[0].operation_id,h.cloud.calls[1].operation_id);
 assert.equal(h.cloud.calls[1].text,'TEST second');
});

for(const state of ['SUCCEEDED','UNMETERED','UNKNOWN','REJECTED'])test(`${state} remains a terminal receipt`,async()=>{
 const h=environment();h.cloud.handler=()=>({state,answer:null});
 assert.equal((await h.account.askAI(h.store,'TEST question')).state,state);
 assert.equal(h.reopen().value.cloudAiPending,undefined);
});

for(const [code,status] of [['',0],['',504],['AI_UNKNOWN',502],['IDEMPOTENCY_CONFLICT',409],['AUTH_REQUIRED',401],['VALIDATION_ERROR',422]])test(`${code||'network/timeout'} ${status} preserves original operation across reopen`,async()=>{
 const h=environment();h.cloud.handler=()=>{throw failure(code,status);};
 await assert.rejects(h.account.askAI(h.store,'TEST original'));
 const original=plain(h.store.value.cloudAiPending),reopened=h.reopen();
 await assert.rejects(h.account.askAI(reopened,'TEST different'),/原提问/);
 assert.equal(h.cloud.calls.length,1);
 h.cloud.handler=()=>({state:'SUCCEEDED',answer:'TEST recovered'});
 await h.account.askAI(reopened);
 assert.deepEqual(h.cloud.calls[1],{operation_id:original.operation_id,text:original.text});
 assert.equal(h.reopen().value.cloudAiPending,undefined);
});

for(const state of [undefined,'RUNNING','PENDING','FAILED'])test(`${state} does not retire an unresolved request`,async()=>{
 const h=environment();h.cloud.handler=()=>({state});await h.account.askAI(h.store,'TEST original');
 assert.equal(h.reopen().value.cloudAiPending.operation_id,h.cloud.calls[0].operation_id);
 await assert.rejects(h.account.askAI(h.store,'TEST different'),/原提问/);
 assert.equal(h.cloud.calls.length,1);
});

for(const outcome of ['AI_NOT_CONFIGURED','REJECTED'])test(`${outcome} cleanup cannot erase a newer operation`,async()=>{
 const h=environment(),newer={patient_id:h.cloud.identity.patient_id,operation_id:crypto.randomUUID(),text:'TEST newer'};
 h.cloud.handler=()=>{h.store.change(value=>value.cloudAiPending=newer);if(outcome==='REJECTED')return {state:outcome};throw failure(outcome,503);};
 if(outcome==='REJECTED')await h.account.askAI(h.store,'TEST original');else await assert.rejects(h.account.askAI(h.store,'TEST original'));
 assert.deepEqual(plain(h.reopen().value.cloudAiPending),newer);
});

test('cleanup matches the pending patient as well as the operation',async()=>{
 const h=environment();let replacement;
 h.cloud.handler=body=>{replacement={patient_id:crypto.randomUUID(),operation_id:body.operation_id,text:'TEST other patient'};h.store.change(value=>value.cloudAiPending=replacement);return {state:'REJECTED'};};
 await h.account.askAI(h.store,'TEST original');
 assert.deepEqual(plain(h.reopen().value.cloudAiPending),replacement);
});

for(const outcome of ['AI_NOT_CONFIGURED','REJECTED'])for(const changePatient of [false,true])test(`${outcome} preserves pending after ${changePatient?'patient/account':'account'} change`,async()=>{
 const h=environment();let original;
 h.cloud.handler=()=>{
  original=plain(h.store.value.cloudAiPending);
  h.cloud.identity={...h.cloud.identity,account_id:crypto.randomUUID(),...(changePatient?{patient_id:crypto.randomUUID()}:{})};
  h.store.change(value=>{value.cloudIdentity=plain(h.cloud.identity);value.cloudBinding.patient_id=h.cloud.identity.patient_id;});
  if(outcome==='REJECTED')return {state:outcome};throw failure(outcome,503);
 };
 await assert.rejects(h.account.askAI(h.store,'TEST original'));
 assert.deepEqual(plain(h.reopen().value.cloudAiPending),original);
});

test('a stale page cannot overwrite pending saved by another page',async()=>{
 const h=environment();let newer;
 h.cloud.handler=()=>{const other=h.reopen();newer={patient_id:h.cloud.identity.patient_id,operation_id:crypto.randomUUID(),text:'TEST other page'};other.change(value=>value.cloudAiPending=newer);throw failure('AI_BUSY',429);};
 await assert.rejects(h.account.askAI(h.store,'TEST original'));
 assert.deepEqual(plain(h.reopen().value.cloudAiPending),newer);
});

test('simultaneous different questions cannot replace the first pending operation',async()=>{
 const h=environment();h.cloud.handler=()=>({state:'RUNNING'});
 const results=await Promise.allSettled([h.account.askAI(h.store,'TEST first'),h.account.askAI(h.store,'TEST second')]);
 assert.equal(results[0].status,'fulfilled');assert.equal(results[1].status,'rejected');
 assert.equal(h.cloud.calls.length,1);assert.equal(h.reopen().value.cloudAiPending.text,'TEST first');
});

test('an account change while waiting to save cannot write the old pending request',async()=>{
 const h=environment();let release;h.store.tail=new Promise(resolve=>release=resolve);
 const result=h.account.askAI(h.store,'TEST original');
 h.cloud.identity={...h.cloud.identity,account_id:crypto.randomUUID()};
 h.store.change(value=>value.cloudIdentity=plain(h.cloud.identity));release();
 await assert.rejects(result,/账号已变化/);
 assert.equal(h.cloud.calls.length,0);assert.equal(h.reopen().value.cloudAiPending,undefined);
});

for(const native of [false,true])test(`${native?'native':'browser'} authenticated unbound patient can submit ordinary text without record consent`,async()=>{
 const h=environment(native);h.store.change(value=>{delete value.cloudBinding;value.cloudConsent=false;});
 assert.deepEqual(plain(h.account.aiScope(h.store)),h.cloud.identity);
 assert.throws(()=>h.account.scope(h.store),/绑定/);
 assert.throws(()=>h.account.scope(h.store,true),/绑定/);
 assert.equal((await h.account.askAI(h.store,'TEST ordinary submitted text')).answer,'TEST answer');
 assert.deepEqual(Object.keys(h.cloud.calls[0]).sort(),native?['operation_id','patient_id','text']:['operation_id','text']);
 assert.equal(h.store.value.cloudBinding,undefined);assert.equal(h.store.value.cloudConsent,false);
});

for(const code of noDispatch)test(`unbound patient's retry after reopen retires ${code}`,async()=>{
 const h=environment();h.store.change(value=>delete value.cloudBinding);
 h.cloud.handler=()=>{throw failure();};await assert.rejects(h.account.askAI(h.store,'TEST original'));
 const original=h.cloud.calls[0],reopened=h.reopen();
 h.cloud.handler=()=>{throw failure(code,503);};await assert.rejects(h.account.askAI(reopened),error=>error.code===code);
 assert.deepEqual(h.cloud.calls[1],original);assert.equal(h.reopen().value.cloudAiPending,undefined);
});

for(const mode of ['fixture','missing identity','wrong account','wrong patient','wrong cloud key','binding patient','binding owner'])test(`AI scope rejects ${mode} before saving or submitting`,async()=>{
 const h=environment();h.store.change(value=>{
  if(mode==='fixture')value.fixture={synthetic:true};
  if(mode==='missing identity')delete value.cloudIdentity;
  if(mode==='wrong account')value.cloudIdentity.account_id=crypto.randomUUID();
  if(mode==='wrong patient')value.cloudIdentity.patient_id=crypto.randomUUID();
  if(mode==='binding patient')value.cloudBinding.patient_id=crypto.randomUUID();
  if(mode==='binding owner')value.cloudBinding.owner=crypto.randomUUID();
 });
 if(mode==='wrong cloud key'){h.store.key=h.store.key.replace(h.cloud.identity.patient_id,crypto.randomUUID());h.store.storage.setItem(h.store.key,h.store.raw);}
 assert.throws(()=>h.account.aiScope(h.store));await assert.rejects(h.account.askAI(h.store,'TEST text'));
 assert.equal(h.cloud.calls.length,0);assert.equal(h.store.value.cloudAiPending,undefined);
});

test('AI scope checks stale storage and leaves record-sync consent enforcement intact',async()=>{
 const h=environment();h.store.change(value=>value.cloudConsent=false);
 assert.equal(h.account.aiScope(h.store).patient_id,h.cloud.identity.patient_id);
 assert.throws(()=>h.account.scope(h.store,true),/同步尚未开启/);
 const stale=h.reopen();h.store.change(value=>value.cloudConsent=true);
 assert.throws(()=>h.account.aiScope(stale),/另一个页面更新/);
 await assert.rejects(h.account.askAI(stale,'TEST stale page'),/另一个页面更新/);
 assert.equal(h.cloud.calls.length,0);
});

test('account activation never reassigns the old local identity, chat, plans or pending operations',async()=>{
 const h=environment(),PS=h.context.PhoneStore,old=new PS.Store(h.storage,PS.KEY);
 old.change(v=>{v.cloudIdentity=plain(h.cloud.identity);v.cloudBinding={patient_id:h.cloud.identity.patient_id,owner:v.owner};v.plans=[{id:'TEST old plan'}];v.cloudAssistantPending={text:'TEST old pending'};v.kv['chat:TEST']=['TEST old private conversation'];});
 h.context.PhoneLocal={store:old};const before=h.storage.getItem(PS.KEY),priorCloud=h.storage.getItem(h.store.key);
 h.cloud.identity={...h.cloud.identity,patient_id:crypto.randomUUID(),account_id:crypto.randomUUID()};
 await h.account.activate(h.cloud.identity);
 assert.equal(h.storage.getItem(PS.KEY),before);assert.equal(h.storage.getItem(h.store.key),priorCloud);
 const key=PS.CLOUD_PREFIX+h.cloud.identity.patient_id,fresh=new PS.Store(h.storage,key);
 assert.equal(h.storage.getItem(PS.ACTIVE_KEY),key);assert.deepEqual(plain(fresh.value.plans),[]);
 assert.equal(fresh.value.cloudAssistantPending,undefined);assert(!JSON.stringify(fresh.value).includes('TEST old'));
});

function assistantReply(body,sequence=1){return {turn:{id:crypto.randomUUID(),operation_id:body.operation_id,state:'LOCAL',sequence,text:body.text,answer:'TEST server answer',actions:[],created_at:1,source:'local'},summary:{text:'TEST'},source:'local',health_context_enabled:false};}
for(const native of [false,true])test(`${native?'native':'browser'} assistant sends original text without record binding or upload consent`,async()=>{
 const h=environment(native);h.store.change(v=>{delete v.cloudBinding;v.cloudConsent=false;});
 h.cloud.handler=(body,action)=>{assert.equal(action,'assistantTurn');return assistantReply(body);};
 await h.account.assistantTurn(h.store,'查看我已有的肩部康复记录');
 assert.equal(h.cloud.calls[0].text,'查看我已有的肩部康复记录');assert.equal(h.cloud.calls[0].private,undefined);
 assert.equal(h.store.value.cloudConsent,false);assert.equal(h.store.value.cloudBinding,undefined);assert.equal(h.reopen().value.cloudAssistantPending,undefined);
});
test('assistant preferences are explicit, versioned and independent of sharing consent',async()=>{
 const h=environment();h.store.change(v=>{delete v.cloudBinding;v.cloudConsent=false;});
 h.cloud.handler=(body,action)=>{assert.equal(action,'assistantPreferences');return body.health_context===undefined?{version:0,health_context:false}:{version:1,health_context:body.health_context};};
 assert.equal((await h.account.assistantPreferences(h.store)).health_context,false);
 await h.account.assistantPreferences(h.store,{expected_version:0,health_context:true});
 assert.deepEqual(h.cloud.calls[1],{expected_version:0,health_context:true});assert.equal(h.store.value.cloudConsent,false);
 assert.throws(()=>h.account.assistantPreferences(h.store,{expected_version:0,health_context:'yes'}));
});
for(const text of ['不要记录我的肩部结果','别保存这次对话','不要告诉家人我的训练情况'])test(`private input stays out of assistant RPC: ${text}`,async()=>{
 const h=environment();await assert.rejects(h.account.assistantTurn(h.store,text),/仅在本机/);assert.equal(h.cloud.calls.length,0);
});
test('assistant lost reply keeps the original while a different question can complete',async()=>{
 const h=environment();h.cloud.handler=()=>{throw failure();};await assert.rejects(h.account.assistantTurn(h.store,'TEST original'));
 const original=plain(h.cloud.calls[0]),reopened=h.reopen();
 h.cloud.handler=body=>assistantReply(body);await h.account.assistantTurn(reopened,'TEST different');
 assert.notEqual(h.cloud.calls[1].operation_id,original.operation_id);
 assert.equal(h.reopen().value.cloudAssistantPending.operation_id,original.operation_id);
 await h.account.assistantTurn(reopened);
 assert.deepEqual(h.cloud.calls[2],original);assert.equal(h.reopen().value.cloudAssistantPending,undefined);
});

for(const native of [false,true])test(`${native?'native':'browser'} reads recover an old completed reply without provider dispatch`,async()=>{
 const h=environment(native);h.cloud.handler=()=>{throw failure();};await assert.rejects(h.account.assistantTurn(h.store,'TEST original'));
 const intent=plain(h.store.value.cloudAssistantPending),reopened=h.reopen();
 h.cloud.handler=(body,action)=>{assert.equal(action,'assistantConversation');return {items:[assistantReply(intent).turn],has_more:false,next_after:1};};
 assert.equal((await h.account.assistantConversation(reopened)).items.length,1);
 assert.equal(h.reopen().value.cloudAssistantPending,undefined);assert.equal(h.cloud.calls.length,2);
});

test('old single-slot data migrates losslessly and retry targets the chosen question',async()=>{
 const h=environment(),legacy={patient_id:h.cloud.identity.patient_id,account_id:h.cloud.identity.account_id,operation_id:crypto.randomUUID(),text:'TEST legacy'};
 h.store.change(v=>v.cloudAssistantPending=legacy);h.cloud.handler=()=>{throw failure();};
 await assert.rejects(h.account.assistantTurn(h.store,'TEST second'));
 const rows=plain(h.account.assistantPending(h.store));assert.equal(rows.length,2);assert.deepEqual(rows[0],legacy);
 h.cloud.handler=body=>assistantReply(body);await h.account.assistantTurn(h.store,null,rows[1].operation_id);
 assert.equal(h.cloud.calls[1].text,'TEST second');assert.deepEqual(plain(h.account.assistantPending(h.store)),[legacy]);
});

test('sending the same unresolved text reuses its exact operation instead of charging a new one',async()=>{
 const h=environment();h.cloud.handler=()=>{throw failure();};
 await assert.rejects(h.account.assistantTurn(h.store,'TEST same'));await assert.rejects(h.account.assistantTurn(h.reopen(),'TEST same'));
 assert.deepEqual(h.cloud.calls[1],h.cloud.calls[0]);assert.equal(h.account.assistantPending(h.reopen()).length,1);
});

for(const state of ['PENDING','RUNNING'])test(`${state} stays saved and does not block an unrelated question`,async()=>{
 const h=environment();h.cloud.handler=body=>({turn:{...assistantReply(body).turn,answer:null,state}});
 await assert.rejects(h.account.assistantTurn(h.store,'TEST first'),/可以继续提问/);
 h.cloud.handler=body=>assistantReply(body);await h.account.assistantTurn(h.store,'TEST next');
 assert.equal(h.account.assistantPending(h.store)[0].text,'TEST first');
});

for(const wrong of ['operation','text','answer','state'])test(`conversation with mismatching ${wrong} cannot retire original`,async()=>{
 const h=environment();h.cloud.handler=()=>{throw failure();};await assert.rejects(h.account.assistantTurn(h.store,'TEST first'));
 const row=assistantReply(h.store.value.cloudAssistantPending).turn;
 if(wrong==='operation')row.operation_id=crypto.randomUUID();if(wrong==='text')row.text='TEST other';if(wrong==='answer')row.answer=null;if(wrong==='state')row.state='RUNNING';
 h.cloud.handler=()=>({items:[row],has_more:false,next_after:1});await h.account.assistantConversation(h.store);
 assert.equal(h.account.assistantPending(h.store).length,1);
});

test('recovery clears only the matching operation and preserves other pending and clinical records',async()=>{
 const h=environment();h.store.change(v=>{v.jobs=[{id:'TEST existing'}];v.plans=[{id:'TEST plan'}];});h.cloud.handler=()=>{throw failure();};
 await assert.rejects(h.account.assistantTurn(h.store,'TEST one'));await assert.rejects(h.account.assistantTurn(h.store,'TEST two'));
 const rows=h.account.assistantPending(h.store),before=JSON.stringify([h.store.value.jobs,h.store.value.plans,h.store.value.daily]);
 h.cloud.handler=()=>({items:[assistantReply(rows[1]).turn],has_more:false,next_after:1});await h.account.assistantConversation(h.store);
 assert.equal(h.account.assistantPending(h.store).length,1);assert.equal(h.account.assistantPending(h.store)[0].text,'TEST one');
 assert.equal(JSON.stringify([h.store.value.jobs,h.store.value.plans,h.store.value.daily]),before);
});
test('assistant conversation follows cursors, deduplicates pages and retains a bounded continuation cursor',async()=>{
 const h=environment();let page=0;
 h.cloud.handler=body=>{page++;const row={...assistantReply({text:'TEST '+page}).turn,id:'TEST-'+page,sequence:page};return {items:[row],has_more:true,next_after:body.after+1};};
 const result=await h.account.assistantConversation(h.store);
 assert.equal(page,20);assert.equal(result.items.length,20);assert.equal(result.next_after,20);assert.equal(result.has_more,true);
 h.cloud.handler=body=>({items:[],has_more:false,next_after:body.after});
 assert.equal((await h.account.assistantConversation(h.store,result.next_after)).next_after,20);
});
test('assistant pagination and late replies cannot cross an account change',async()=>{
 const h=environment();h.cloud.handler=body=>{h.cloud.identity={...h.cloud.identity,account_id:crypto.randomUUID()};h.store.change(v=>v.cloudIdentity=plain(h.cloud.identity));return assistantReply(body);};
 await assert.rejects(h.account.assistantTurn(h.store,'TEST original'),/账号已变化/);
 assert.equal(h.reopen().value.cloudAssistantPending.text,'TEST original');
});

for(const code of noDispatch)test(`assistant ${code} retires original request but not a newer pending operation`,async()=>{
 const h=environment();h.cloud.handler=()=>{throw failure(code,503);};
 await assert.rejects(h.account.assistantTurn(h.store,'TEST original'));assert.equal(h.reopen().value.cloudAssistantPending,undefined);
 const newer={patient_id:h.cloud.identity.patient_id,account_id:h.cloud.identity.account_id,operation_id:crypto.randomUUID(),text:'TEST newer'};
 h.cloud.handler=()=>{h.store.change(v=>v.cloudAssistantPending=newer);throw failure(code,503);};
 await assert.rejects(h.account.assistantTurn(h.store,'TEST original'));assert.deepEqual(plain(h.reopen().value.cloudAssistantPending),newer);
});
test('assistant pagination keeps one patient identity for the complete page loop',async()=>{
 const h=environment();
 h.cloud.handler=()=>({items:[],next_after:1,get has_more(){h.cloud.identity={...h.cloud.identity,account_id:crypto.randomUUID()};h.store.change(v=>v.cloudIdentity=plain(h.cloud.identity));return true;}});
 await assert.rejects(h.account.assistantConversation(h.store),/账号已变化/);assert.equal(h.cloud.calls.length,1);
});

for(const native of [false,true])test(`${native?'native':'browser'} assessment plan transport uses the account channel and empty cancellation document`,async()=>{
 const h=environment(native),id=crypto.randomUUID(),actions=[];
 h.storage.setItem(h.context.PhoneStore.ACTIVE_KEY,h.store.key);
 h.cloud.handler=(body,action)=>{actions.push(action);return action==='assessmentPlans'?{items:[{id,status:'PLANNED'}]}:{status:'CANCELLED'};};
 assert.equal((await h.account.assessmentPlans(h.store)).items[0].id,id);
 assert.equal((await h.account.assessmentPlanCancel(h.store,id)).status,'CANCELLED');
 assert.deepEqual(actions,['assessmentPlans','assessmentPlanCancel']);
 assert(h.cloud.calls.every(body=>body.account_id===h.cloud.identity.account_id));
 const clean=body=>{const value={...body};delete value.patient_id;delete value.account_id;return value;};
 assert.deepEqual(h.cloud.calls.map(clean),[{}, {plan_id:id}]);
 await assert.rejects(h.account.assessmentPlanCancel(h.store,'../../other'),/编号无效/);assert.equal(h.cloud.calls.length,2);
 assert.equal(h.store.value.plans.length,0);assert.equal(h.store.value.jobs.length,0);
});
for(const native of [false,true])test(`${native?'native':'browser'} assessment plan transport rejects offline and late account or owner changes`,async()=>{
 for(const change of ['offline','account','owner','active']){
  const h=environment(native);h.storage.setItem(h.context.PhoneStore.ACTIVE_KEY,h.store.key);
  if(change==='offline')h.context.navigator={onLine:false};
  h.cloud.handler=()=>{if(change==='account')h.cloud.identity={...h.cloud.identity,account_id:crypto.randomUUID()};if(change==='owner')h.store.value.owner=crypto.randomUUID();if(change==='active')h.storage.setItem(h.context.PhoneStore.ACTIVE_KEY,'other');return {items:[]};};
  await assert.rejects(h.account.assessmentPlans(h.store),/离线|账号|本人档案/);
  assert.equal(h.cloud.calls.length,change==='offline'?0:1);
 }
 const h=environment(native);h.storage.setItem(h.context.PhoneStore.ACTIVE_KEY,h.store.key);h.cloud.identity=null;
 await assert.rejects(h.account.assessmentPlans(h.store),/登录/);assert.equal(h.cloud.calls.length,0);
});
