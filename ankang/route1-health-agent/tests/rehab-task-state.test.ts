import test from 'node:test';
import assert from 'node:assert/strict';
import {AgentRuntime,InMemoryPersistence} from '../src/runtime';
import {profile as demoProfile} from '../src/data/demo';
import type {ConversationModel} from '../src/runtime/conversation';
import {updateRehabTask,restoreRehabTask,REHAB_TASK_TTL_MS,unavailableEquipment} from '../src/rehab/taskState';

test('equipment constraints use explicit own clauses and later corrections without guessing',()=>{
  assert.deepEqual(unavailableEquipment(['我没有弹力带，只有椅子']),['弹力带']);
  assert.deepEqual(unavailableEquipment(['我没有弹力带','现在有弹力带']),[]);
  assert.deepEqual(unavailableEquipment(['我有弹力带','现在不再有弹力带']),['弹力带']);
  for(const text of ['朋友没有弹力带','如果没有弹力带怎么办？','我不确定有弹力带','我需要弹力带'])
    assert.deepEqual(unavailableEquipment([text]),[]);
  assert.deepEqual(unavailableEquipment(['没有哑铃','如果我有哑铃','朋友有哑铃','我不知道有哑铃']),['哑铃']);
});

const now = new Date(2026,9,19,12);
const owner = 'SYNTHETIC_TEST_GUIDANCE';
const profile = {...demoProfile,name:owner,medications:[],familySharing:'denied' as const};
function semantic(text:string,route='chat',plan=false) {
  return {version:1,route,goal:text,mentions:[],events:[],relations:[],uncertain:[],suggested_tool:null,
    intents:plan?[{type:'plan_generation',route:'rehab',goal:text,evidence:text}]:[]};
}

test('proactive question persists across reopen; equipment correction reuses original request and increments version',async()=>{
  const persistence = new InMemoryPersistence();
  const prompts:string[]=[];
  let phase = 0;
  const model:ConversationModel = {async reply(input){
    prompts.push(input.messages[0].content);
    if(phase++ === 0) return JSON.stringify(semantic('帮我制定居家训练计划','rehab',true));
    if(phase === 2) return JSON.stringify(semantic('没有弹力带，只有椅子'));
    if(phase === 3) return JSON.stringify({version:1,calls:[
      {name:'rehab.search_knowledge',arguments:{query:'T-LOW-003'},reason:'检索动作卡'}],uncertainties:[]});
    return JSON.stringify({version:1,goal:'居家训练',summary:'TEST 草案',
      algorithm_input:{goal:'居家训练',region:'膝',equipment:['椅子'],restrictions:[],level:null,screening_confirmed:false},
      candidate_actions:[{exercise_id:'T-LOW-003',reason:'真实卡片'}],doctor_review_required:true,
      doctor_review_reasons:['需核对'],uncertainties:[]});
  }};
  const runtime = new AgentRuntime();
  const options = {sessionId:owner,participantId:owner,profile,now,persistence,semanticRoutingEnabled:true,conversationModel:model};
  await runtime.openSession(options);
  const first = await runtime.processTurn(owner,{text:'帮我制定居家训练计划',now});
  assert.match(first.reply.text,/哪些器材|徒手/);
  assert.equal(phase,1,'ask one useful question before additional model/tool calls');
  assert.equal(first.snapshot.rehabTask?.revision,1);
  await runtime.closeSession(owner);
  await runtime.openSession(options);
  const second = await runtime.processTurn(owner,{text:'没有弹力带，只有椅子',now});
  assert.equal(second.snapshot.rehabTask?.revision,2);
  assert.match(second.reply.text,/候选|专业审核/);
  assert.match(prompts[2],/帮我制定居家训练计划/);
  assert.match(prompts[2],/没有弹力带，只有椅子/);
  assert.equal(second.snapshot.rehabTask?.status,'draft');
  assert.deepEqual(second.snapshot.events,[]);
  await runtime.closeSession(owner);
});

test('topic change, cancellation and private turns clear the pending rehab task',async()=>{
  for(const next of ['今天天气怎么样','取消','这段不要记录']){
    let calls=0;
    const model:ConversationModel={async reply(){calls++;return JSON.stringify(semantic(
      calls===1?'帮我制定居家训练计划':next,calls===1?'rehab':'chat',calls===1));}};
    const runtime = new AgentRuntime();
    await runtime.openSession({sessionId:owner,profile,now,semanticRoutingEnabled:true,conversationModel:model});
    await runtime.processTurn(owner,{text:'帮我制定居家训练计划',now});
    const result = await runtime.processTurn(owner,{text:next,now});
    assert.equal(result.snapshot.rehabTask,null,next);
    await runtime.closeSession(owner);
  }
});

test('expired, cross-context or corrupt tasks never restore approval or candidate authority',()=>{
  const task=updateRehabTask(null,'TEST original restriction','local',now.getTime());
  assert.equal(restoreRehabTask(task,'remote',now.getTime()),null);
  assert.equal(restoreRehabTask(task,'local',now.getTime()+REHAB_TASK_TTL_MS+1),null);
  assert.equal(restoreRehabTask({...task,messages:[42]},'local',now.getTime()),null);
  const restored=restoreRehabTask({...task,status:'draft',validation:{status:'passed'}},'local',now.getTime());
  assert.equal(restored?.validation,null);
  let revised=task;
  for(let i=0;i<12;i++)revised=updateRehabTask(revised,'TEST correction '+i,'local',now.getTime());
  assert.equal(revised.messages.length,8);
  assert.equal(revised.messages[0],'TEST original restriction');
});

test('restored task cancellation works with no configured model',async()=>{
  const persistence=new InMemoryPersistence();
  await persistence.save(owner,{revision:1,health:{events:[],familyEvents:[],chat:[]},
    rehabTask:updateRehabTask(null,'TEST task','TEST_SOURCE',now.getTime())});
  const runtime=new AgentRuntime();
  await runtime.openSession({sessionId:owner,profile,now,persistence,semanticRoutingEnabled:true});
  const turn=await runtime.processTurn(owner,{text:'取消',now,conversationContext:'TEST_SOURCE'});
  assert.equal(turn.snapshot.rehabTask,null);
  assert.match(turn.reply.text,/取消/);
  await runtime.closeSession(owner);
});
