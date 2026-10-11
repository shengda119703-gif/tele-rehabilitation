import test from 'node:test';
import assert from 'node:assert/strict';
import {ProductAgent, type AgentTool, type ProductAgentModel} from '../src/product/ProductAgent';
const now=new Date('2026-10-11T09:00:00+08:00');
function fixture(model?:ProductAgentModel){
  const invoked:string[]=[];
  const tools:AgentTool[]=['health_overview','medication_list','archive_list','family_status','daily_overview'].map(name=>({name,description:name,available:true,mode:'read',run:async()=>{invoked.push(name);return{reply:'TEST '+name,data:{owner:'TEST'}};}}));
  return {invoked,tools,agent:new ProductAgent(tools,model)};
}
test('compound module read runs real adapters once and retains per-step results',async()=>{
  const f=fixture(),r=await f.agent.replyToText('查看健康记录和药物清单',now,()=>{});
  assert.deepEqual(f.invoked,['health_overview','medication_list']);assert.equal(r?.steps.length,2);
  assert(r?.steps.every(s=>s.status==='succeeded'));assert.equal(r?.steps[0].data!==undefined,true);
});

test('combined health and daily query reads both requested modules',async()=>{
  const f=fixture(),r=await f.agent.replyToText('查看健康记录、今天的安排',now,()=>{});
  assert.deepEqual(f.invoked,['health_overview','daily_overview']);assert.equal(r?.steps.length,2);
});
test('the whole model plan is validated before any host call',async()=>{
  for(const calls of [[{name:'health_overview',arguments:{}},{name:'lifecycle.clear',arguments:{}}],
    [{name:'health_overview',arguments:{ownerId:'OTHER'}}],[{name:'open_module',arguments:{module:'camera'}}],
    [{name:'health_overview',arguments:{}},{name:'health_overview',arguments:{}}]]){
    const f=fixture({select:async()=>calls});await assert.rejects(f.agent.replyToText('我想了解保存的文档',now,()=>{}));assert.deepEqual(f.invoked,[]);
  }
});
test('navigation is an explicit UI result, never a training or camera command',async()=>{
  const f=fixture(),r=await f.agent.replyToText('打开康复页',now,()=>{});
  assert.equal(r?.navigation,'rehab');assert.deepEqual(f.invoked,[]);
  assert.equal((await f.agent.replyToText('打开健身页',now,()=>{}))?.navigation,'fitness');
});
test('a failed read retains successful steps and never claims full completion',async()=>{
  const f=fixture();f.tools[1].run=async()=>{throw Error('TEST unavailable');};
  const r=await f.agent.replyToText('查看健康记录和药物清单',now,()=>{});
  assert.deepEqual(r?.steps.map(s=>s.status),['succeeded','failed']);assert.match(r!.reply,/读取失败/);
});
test('stale generation stops the plan before further reads',async()=>{
  const f=fixture();let checks=0;
  await assert.rejects(f.agent.replyToText('查看健康记录和药物清单',now,()=>{if(++checks>1)throw Error('TEST stale');}));
  assert.deepEqual(f.invoked,['health_overview']);
});
test('model outage leaves local queries usable and gives an honest fallback',async()=>{
  const f=fixture({select:async()=>{throw Error('TEST timeout');}});
  assert.equal((await f.agent.replyToText('我想了解保存的文档',now,()=>{}))?.modelError,true);
  assert.equal((await f.agent.replyToText('查看资料',now,()=>{}))?.steps[0].status,'succeeded');
});

test('negated, hypothetical, quoted and other-person queries never read or call a model',async()=>{
  let selections=0;const f=fixture({select:async()=>{selections++;return [{name:'health_overview',arguments:{}}];}});
  for(const text of ['不要查看健康记录','我不查看健康记录','我没让你查看健康记录','今天张三健康记录有哪些','查看健康记录，然后王五的药物清单',
    '假如查看药物清单','王五的健康记录有哪些','请查看王五今天的健康数据','帮忙查一下她的数据','我想看看朋友的记录',
    '查看我的家属的健康记录','查看家属今天的训练记录','查看你的健康记录','查看家庭的健康记录','撤回上一条记录','“查看资料”']){
    assert.equal(await f.agent.replyToText(text,now,()=>{}),null,text);
  }
  assert.equal(selections,0);assert.deepEqual(f.invoked,[]);
  assert.equal((await f.agent.replyToText('查看我的健康记录',now,()=>{}))?.steps[0].status,'succeeded');
  assert.equal((await f.agent.replyToText('查看家属权限',now,()=>{}))?.steps[0].name,'family_status');
});

test('model cannot turn a query into an unsolicited navigation',async()=>{
  const f=fixture({select:async()=>[{name:'open_module',arguments:{module:'health'}}]});
  await assert.rejects(f.agent.replyToText('我想了解保存的文档',now,()=>{}));assert.deepEqual(f.invoked,[]);
});
