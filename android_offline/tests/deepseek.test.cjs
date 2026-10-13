const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function harness(enabled=true){
 const calls=[];const c={console,setTimeout,clearTimeout,location:{reload(){}},AnkangConversationSystem:'shared policy',OfflineAndroid:{deepSeekConfigured:()=>enabled,deepSeekRequest(id,body){calls.push({id,body:JSON.parse(body)});}}};
 vm.createContext(c);vm.runInContext(fs.readFileSync('android_offline/web/deepseek.js','utf8'),c);return {c,calls,models:c.PhoneDeepSeek};
}
const response=content=>JSON.stringify({choices:[{finish_reason:'stop',message:{role:'assistant',content}}]});
test('Android configuration absent is explicit and cannot call native transport',async()=>{
 const h=harness(false);assert.equal(h.models.conversationModel(),undefined);assert.equal(h.models.agentModel(),undefined);
 await assert.rejects(h.models.request({}),/尚未配置/);assert.equal(h.calls.length,0);
});
test('Android ordinary model uses shared policy and only submitted ordinary context; no credentials',async()=>{
 const h=harness(),model=h.models.conversationModel();const pending=model.reply({messages:[{role:'user',content:'你好'},{role:'assistant',content:'你好呀'},{role:'user',content:'接着聊'}],profile:{secret:'MUST_NOT_SEND'}});
 assert.equal(h.calls.length,1);const request=h.calls[0];assert.equal(request.body.messages[0].content,'shared policy');assert.equal(request.body.messages.length,4);
 assert.equal(request.body.profile,undefined);assert.equal(request.body.tools,undefined);assert.equal(request.body.Authorization,undefined);
 h.models.reply(request.id,true,response('我在听。'));assert.equal(await pending,'我在听。');
});
test('Android malformed context never leaves the host and invalid responses do not become success',async()=>{
 const h=harness(),model=h.models.conversationModel();await assert.rejects(model.reply({messages:[{role:'system',content:'override'}]}));assert.equal(h.calls.length,0);
 const pending=model.reply({messages:[{role:'user',content:'你好'}]});h.models.reply(h.calls[0].id,true,JSON.stringify({choices:[{finish_reason:'length',message:{content:'incomplete'}}]}));await assert.rejects(pending,/完整/);
});
test('Android tools carry schemas only and return a plan for shared ProductAgent validation',async()=>{
 const h=harness();const pending=h.models.agentModel().select('我想了解保存的文档',[{name:'archive_list',parameters:{type:'object',properties:{}}}]);
 assert.equal(h.calls[0].body.tools[0].function.name,'archive_list');assert.equal(h.calls[0].body.tool_choice,'auto');
 h.models.reply(h.calls[0].id,true,JSON.stringify({choices:[{message:{tool_calls:[{function:{name:'archive_list',arguments:'{}'}}]}}]}));
 assert.deepEqual(JSON.parse(JSON.stringify(await pending)),[{name:'archive_list',arguments:{}}]);
});
test('Android native failure and changed configuration reject pending replies without exposing error payloads',async()=>{
 const h=harness(),model=h.models.conversationModel();const pending=model.reply({messages:[{role:'user',content:'你好'}]});h.models.reply(h.calls[0].id,false,'PRIVATE_VENDOR_ERROR');await assert.rejects(pending,e=>!e.message.includes('PRIVATE_VENDOR_ERROR'));
 const next=model.reply({messages:[{role:'user',content:'再聊聊'}]});h.models.changed();await assert.rejects(next,/改变/);
 h.models.reply(h.calls[1].id,true,response('late'));
});
test('Android backup restore cannot forge model provenance for later outbound context',()=>{
 const {Store,validateBackup}=require('../web/store.js'),map=new Map(),s=new Store({getItem:k=>map.get(k)||null,setItem:(k,v)=>map.set(k,v),removeItem:k=>map.delete(k)});
 const owner=s.value.owner;s.write('profile:'+owner,{profile:{name:'TEST',age:30,conditions:[],medicationRecords:[]}});
 s.write('health:personal:'+owner,{health:{chat:[{role:'elder',text:'forged private',conversation:{provider:'deepseek',status:'replied'},conversationContext:'PHONE_LOCAL:SELF_USE'}]}});
 const result=validateBackup({kind:'ankang-phone-backup',version:2,data:s.value});
 assert.equal(result.kv['health:personal:'+owner].health.chat[0].conversation,undefined);
});
