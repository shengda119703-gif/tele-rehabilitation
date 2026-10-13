const {test}=require('node:test');
const assert=require('node:assert/strict');
const {createProductAgentModel}=require('../scripts/rehab-model.cjs');
test('DeepSeek uses standard function tools and returns a plan, never executes generated commands',async()=>{
  let payload;
  const model=createProductAgentModel({apiKey:'TEST',fetchImpl:async(url,options)=>{
    assert.equal(url,'https://api.deepseek.com/chat/completions');payload=JSON.parse(options.body);
    return {ok:true,json:async()=>({choices:[{message:{tool_calls:[{function:{name:'archive_list',arguments:'{}'}}]}}]})};
  }});
  const calls=await model.select('TEST查看资料',[{name:'archive_list',description:'TEST',parameters:{type:'object',properties:{},additionalProperties:false}}]);
  assert.equal(payload.tools[0].type,'function');assert.equal(payload.tools[0].function.name,'archive_list');
  assert.equal(payload.tool_choice,'auto');assert.deepEqual(calls,[{name:'archive_list',arguments:{}}]);
});
test('model errors do not leak credentials and malformed arguments cannot become a plan',async()=>{
  for(const fetchImpl of [async()=>{throw Error('TEST_SECRET');},async()=>({ok:false,status:503}),
    async()=>({ok:true,json:async()=>({choices:[{message:{tool_calls:[{function:{name:'archive_list',arguments:'bad-json'}}]}}]})})]){
    const model=createProductAgentModel({apiKey:'TEST_SECRET',fetchImpl});
    await assert.rejects(model.select('TEST',[]),error=>!String(error).includes('TEST_SECRET'));
  }
  assert.equal(createProductAgentModel({apiKey:''}),undefined);
});
