const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {spawn}=require('node:child_process');
const {createInterface}=require('node:readline');
const {ProductService}=require('../.bridge-build/product/ProductService.js');
const profile={name:'SYNTHETIC TEST',age:40,conditions:[],medications:[],mobility:'unknown',usesCane:false,nightVision:'unknown',cognition:'unknown',familySharing:'denied'};
const parsed={version:1,route:'chat',goal:'普通聊天',mentions:[],events:[],relations:[],uncertain:[],suggested_tool:null};
function port(){const values=new Map();return {read:k=>structuredClone(values.get(k)??null),write:(k,v)=>values.set(k,structuredClone(v)),remove:k=>values.delete(k),profiles:()=>[],attachments:{list:async()=>[],clear:async()=>{}}};}

test('ProductService opt-in reaches understanding then reply, preserves owner and private boundary',async()=>{
 const calls=[];let configured=true;
 const service=new ProductService(port(),undefined,undefined,{},undefined,undefined,undefined,
   owner=>configured?{reply:async input=>{calls.push({owner,...input});return input.purpose==='understanding'?JSON.stringify(parsed):'今天想聊些什么？';}}:undefined,
   undefined,{semanticRoutingEnabled:true});
 const now=new Date('2026-10-15T12:00:00+08:00');
 await service.request('profile.save','TEST_SELF',{profile},now);
 const result=await service.request('chat','TEST_SELF',{text:'你好，想聊聊天'},now);
 assert.deepEqual(calls.map(c=>c.purpose??'reply'),['understanding','reply']);
 assert.ok(calls.every(c=>c.owner==='TEST_SELF'));assert.match(result.turn.reply.text,/今天想聊/);
 const count=calls.length;await service.request('chat','TEST_SELF',{text:'不要记录：PRIVATE_TEST'},now);assert.equal(calls.length,count);
 configured=false;await service.request('chat','TEST_SELF',{text:'你好'},now);assert.equal(calls.length,count);
 configured=true;await service.request('chat','TEST_SELF',{text:'你好'},now);assert.equal(calls.length,count+2);
});

test('ProductService default-off never invokes new understanding even with a model',async()=>{
 const calls=[];const service=new ProductService(port(),undefined,undefined,{},undefined,undefined,undefined,
 ()=>({reply:async input=>{calls.push(input);return 'TEST';}}));
 const now=new Date('2026-10-15T12:00:00+08:00');await service.request('profile.save','TEST_SELF',{profile},now);
 await service.request('chat','TEST_SELF',{text:'你好'},now);
 assert.equal(calls.some(c=>c.purpose==='understanding'),false);
});

test('opt-in navigation returns the existing patient UI navigation receipt',async()=>{
 const calls=[];
 const service=new ProductService(port(),undefined,undefined,{},undefined,undefined,undefined,
 ()=>({reply:async input=>{calls.push(input);return JSON.stringify({...parsed,route:'module',goal:'打开康复计划页面',tool_requests:[],intents:[{type:'program_operation',route:'module',goal:'打开康复计划页面',evidence:'打开康复计划页面'}]});}}),
 undefined,{semanticRoutingEnabled:true});
 const now=new Date('2026-10-15T12:00:00+08:00');await service.request('profile.save','TEST_SELF',{profile},now);
 for(const text of ['帮我打开康复计划页面','帮我打开康复计划页面。']) {
  const result=await service.request('chat','TEST_SELF',{text},now);
  assert.equal(result.turn.agent.navigation,'rehab');
  assert.deepEqual(result.turn.agent.steps.map(step=>step.name),['open_module']);
  assert.deepEqual(result.turn.snapshot.events,[]);
 }
 assert.equal(calls.length,2);
});

// Exercise the shipped process entry, real adapter and ProductService together.
// Fetch is replaced before loading any application code; no live provider call.
test('Node bridge keeps product semantic calls on the account gateway even with a legacy local key',async t=>{
 const scratch=path.resolve(__dirname,'../.runtime');fs.mkdirSync(scratch,{recursive:true});
 const root=fs.mkdtempSync(path.join(scratch,'ankang-unified-host-'));
 const preload=path.join(root,'preload.cjs'),log=path.join(root,'calls.jsonl');
 fs.writeFileSync(preload,`const fs=require('node:fs');global.fetch=async(url,options)=>{const body=JSON.parse(options.body);const understanding=body.response_format?.type==='json_object';fs.appendFileSync(process.env.TEST_CALL_LOG,JSON.stringify({understanding,system:body.messages[0].content})+'\\n');return {ok:true,json:async()=>({choices:[{finish_reason:'stop',message:{role:'assistant',content:understanding?${JSON.stringify(JSON.stringify(parsed))}:'HOST_TEST_REPLY'}}]})};};`);
 const child=spawn(process.execPath,['-r',preload,path.resolve(__dirname,'../scripts/agent-bridge.cjs'),path.join(root,'product')],
   {env:{...process.env,APPDATA:root,ANKANG_REHAB_LLM_API_KEY:'TEST_NOT_REAL',ANKANG_PRODUCT_DISABLE_MODEL:'0',ANKANG_SEMANTIC_ROUTING_ENABLED:'1',TEST_CALL_LOG:log},stdio:['pipe','pipe','pipe'],windowsHide:true});
 t.after(()=>{child.kill();assert.equal(path.dirname(root),scratch);assert.ok(path.basename(root).startsWith('ankang-unified-host-'));fs.rmSync(root,{recursive:true,force:true});});
 const lines=createInterface({input:child.stdout});const waiting=[];const buffered=[];
 const cloudCalls=[];
 lines.on('line',line=>{const value=JSON.parse(line);if(value.toolCall){
   const call=value.toolCall;assert.equal(call.name,'conversation.cloud_reply');cloudCalls.push(call);
   const answer=call.arguments.purpose==='understanding'?JSON.stringify(parsed):'HOST_TEST_REPLY';
   child.stdin.write(JSON.stringify({operation:'tool_result',id:call.id,result:{state:'SUCCEEDED',answer}})+'\n');return;
 }if(waiting.length)waiting.shift()(value);else buffered.push(value);});
 async function request(value){child.stdin.write(JSON.stringify(value)+'\n');const answer=buffered.length?buffered.shift():await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('Host fixture timed out')),10000);waiting.push(v=>{clearTimeout(timer);resolve(v);});});assert.equal(answer.ok,true,JSON.stringify(answer));return answer.result;}
 const now='2026-10-15T12:00:00+08:00';
 await request({operation:'open',sessionId:'TEST_DIRECT',profile,now});
 const direct=await request({operation:'process',sessionId:'TEST_DIRECT',text:'你好',now});
 assert.match(direct.reply.text,/HOST_TEST_REPLY/);
 await request({operation:'product',sessionId:'TEST_SELF',productOperation:'profile.save',payload:{profile},now});
 const offline=await request({operation:'product',sessionId:'TEST_SELF',productOperation:'chat',payload:{text:'你好'},now});
 assert.doesNotMatch(offline.turn.reply.text,/HOST_TEST_REPLY/);assert.equal(cloudCalls.length,0);
 const product=await request({operation:'product',sessionId:'TEST_SELF',cloudConversation:true,productOperation:'chat',payload:{text:'你好'},now});
 assert.match(product.turn.reply.text,/HOST_TEST_REPLY/);
 const calls=fs.readFileSync(log,'utf8').trim().split('\n').map(JSON.parse);
 assert.deepEqual(calls.map(c=>c.understanding),[true,false]);
 assert.deepEqual(cloudCalls.map(c=>c.arguments.purpose??'reply'),['understanding','reply']);
 assert.ok(cloudCalls.every(c=>c.sessionId==='TEST_SELF'));
 assert.ok(calls.filter(c=>c.understanding).every(c=>c.system.includes('语言理解解析器')));
});
