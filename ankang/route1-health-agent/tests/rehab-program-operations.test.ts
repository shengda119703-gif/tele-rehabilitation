import test from 'node:test';
import assert from 'node:assert/strict';
import {
  parseRehabProgramPlan,
  isConfirmation,
  isCancellation,
  isRehabProgramIntent,
  commitRehabProgramOperation,
  previewRehabProgramOperation,
  renderOperationResult,
} from '../src/rehab/programOperations';
import type { RehabResult } from '../src/runtime/rehabTools';

test('local rename previews without model disclosure, commits once and checks persisted revision',async()=>{
  const id='0123456789abcdef0123456789abcdef';
  let saved={id,revision:3,status:'ACTIVE',name:'PRIVATE_OLD_NAME',items:[{exercise_id:'TEST'}]};
  const receipt=():RehabResult=>({tool:'rehab.get_training_plan',status:'found',read_only:true,
    scope:{participant_id:'TEST',source_kind:'SYNTHETIC',usage_context:'TEST'},records:[saved]});
  const writes:boolean[]=[];
  const operations={async call(_name:string,args:Record<string,unknown>){
    writes.push(args.commit===true);
    assert.equal(args.expected_revision,3);
    if(args.commit){saved={...saved,revision:4,name:'晨间训练'};return {status:'applied',plan_id:id,revision:4};}
    return {status:'preview',plan_id:id,expected_revision:3,after:{name:'晨间训练'}};
  }};
  const preview=await previewRehabProgramOperation({
    model:{async reply(){throw Error('External model must not receive stored data');}},
    semantic:{version:1,route:'rehab',goal:'改名',mentions:[],events:[],relations:[],uncertain:[],suggested_tool:null},
    userText:'把我的训练计划改名为晨间训练',participantId:'TEST',reads:{async read(){return receipt();}},operations});
  assert.equal(saved.name,'PRIVATE_OLD_NAME');assert.deepEqual(writes,[false]);
  assert.ok(preview.plan);assert.equal(preview.plan.operations.length,1);
  const result=await commitRehabProgramOperation({pending:{proposal:preview.plan,previews:preview.previews,createdAt:100},
    now:101,participantId:'TEST',reads:{async read(){return receipt();}},operations});
  assert.equal((result[0] as {status:string}).status,'applied');
  assert.equal(saved.name,'晨间训练');assert.equal(saved.revision,4);
  assert.deepEqual(saved.items,[{exercise_id:'TEST'}]);assert.deepEqual(writes,[false,true]);
});

test('rename rejects foreign and ambiguous plans before preview; false readback never reports verified success',async()=>{
  const id='0123456789abcdef0123456789abcdef';
  for(const foreign of [false,true]){
    let calls=0;
    const result=await previewRehabProgramOperation({
      model:{async reply(){throw Error('No external reads');}},
      semantic:{version:1,route:'rehab',goal:'改名',mentions:[],events:[],relations:[],uncertain:[],suggested_tool:null},
      userText:'把我的训练计划改名为晨间训练',participantId:'TEST',
      reads:{async read(){return {tool:'rehab.get_training_plan',status:'found',read_only:true,
        scope:{participant_id:foreign?'OTHER':'TEST',source_kind:'SYNTHETIC',usage_context:'TEST'},
        records:[{id,revision:1,status:'ACTIVE'},{id:'b'.repeat(32),revision:1,status:'ACTIVE'}]};}},
      operations:{async call(){calls++;return {};}}});
    assert.equal(calls,0);assert.equal(result.plan?.operations.length,0);
  }
  const result=await commitRehabProgramOperation({now:101,pending:{createdAt:100,previews:[],proposal:{version:1,
    requires_confirmation:true,summary:'TEST',uncertainties:[],operations:[{name:'rehab.plan.change',
      arguments:{plan_id:id,expected_revision:1,patch:{name:'TEST'}},evidence:'TEST'}]}},
    participantId:'TEST',reads:{async read(){throw Error('Readback failed');}},
    operations:{async call(){return {status:'applied',plan_id:id,revision:2};}}});
  assert.deepEqual(result,[{status:'committed_unverified'}]);
  assert.match(renderOperationResult(result[0]),/暂时无法核对/);
});

test('expired and future confirmation timestamps are rejected before host writes',async()=>{
  for(const createdAt of [0,1_000_001,Number.NaN]){
    let writes=0;
    await assert.rejects(commitRehabProgramOperation({now:1_000_000,
      pending:{createdAt,previews:[],proposal:{version:1,operations:[{name:'rehab.plan.change',
        arguments:{plan_id:'TEST',expected_revision:1,patch:{name:'TEST'}},evidence:'TEST'}],
        requires_confirmation:true,summary:'TEST',uncertainties:[]}},
      operations:{async call(){writes++;return {status:'applied'};}}}));
    assert.equal(writes,0);
  }
});

test('program operation proposal requires explicit confirmation and one operation', () => {
  const valid = parseRehabProgramPlan(JSON.stringify({
    version: 1,
    operations: [{
      name: 'rehab.plan.change',
      arguments: {
        plan_id: '0123456789abcdef0123456789abcdef',
        expected_revision: 2,
        patch: { remove: ['sit_to_stand:left'] },
      },
      evidence: '把左侧坐站删掉',
    }],
    requires_confirmation: true,
    summary: '删除左侧坐站训练',
    uncertainties: [],
  }));
  assert.ok(valid);

  const two = parseRehabProgramPlan(JSON.stringify({
    version: 1,
    operations: [
      {name:'rehab.plan.change',arguments:{plan_id:'0123456789abcdef0123456789abcdef',expected_revision:2,patch:{remove:['sit_to_stand:left']}},evidence:'删除'},
      {name:'rehab.schedule.remove',arguments:{id:'schedule-1'},evidence:'删安排'},
    ],
    requires_confirmation: true,
    summary: '两项修改',
    uncertainties: [],
  }));
  assert.equal(two, null);
});

test('confirmation phrases are narrow and do not match new instructions', () => {
  assert.equal(isConfirmation('确认'), true);
  assert.equal(isConfirmation('好的'), true);
  assert.equal(isConfirmation('确认后把时间改到8点'), false);
  assert.equal(isCancellation('取消'), true);
  assert.equal(isCancellation('先不要'), true);
});

test('rehab program intent is derived from semantic intent, not raw user keyword routing', () => {
  assert.equal(isRehabProgramIntent({
    version:1, route:'rehab', goal:'调整训练',
    mentions:[], events:[], relations:[], uncertain:[],
    suggested_tool:null, intents:[{
      type:'program_operation', route:'rehab', goal:'调整训练', evidence:'把计划改一下'
    }],
  }), true);
  assert.equal(isRehabProgramIntent({
    version:1, route:'chat', goal:'聊天',
    mentions:[], events:[], relations:[], uncertain:[],
    suggested_tool:null, intents:[],
  }), false);
});
