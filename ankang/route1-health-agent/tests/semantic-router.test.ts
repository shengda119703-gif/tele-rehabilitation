import {test} from 'node:test';
import {strict as assert} from 'node:assert';
import {parseSemanticTurn,understandSemanticTurn} from '../src/runtime/semanticRouter';

test('ordinary chat has no tools', () => {
  const r=parseSemanticTurn(JSON.stringify({version:1,route:'chat',goal:'闲聊',mentions:[],uncertain:[],suggested_tool:null}));
  assert.equal(r?.route,'chat');
  assert.equal(r?.suggested_tool,null);
});

test('record query selects only a whitelisted read tool', () => {
  const r=parseSemanticTurn(JSON.stringify({version:1,route:'records',goal:'查询训练史',mentions:[],uncertain:[],suggested_tool:'rehab.get_training_history'}));
  assert.equal(r?.suggested_tool,'rehab.get_training_history');
});

test('invented tool and malformed data are rejected', () => {
  const base={version:1,route:'module',goal:'修改计划',mentions:[],uncertain:[]};
  assert.equal(parseSemanticTurn(JSON.stringify({...base,suggested_tool:'rehab.update_training_plan'})),null);
  assert.equal(parseSemanticTurn(JSON.stringify({...base,suggested_tool:null,mentions:[{kind:'symptom',text:3}]})),null);
});

test('model failure returns null for legacy fallback', async () => {
  const r=await understandSemanticTurn({reply:async()=>{throw Error('offline');}},'你好');
  assert.equal(r,null);
});

test('ambiguous symptoms preserve uncertainty instead of inventing a diagnosis', () => {
  const r=parseSemanticTurn(JSON.stringify({version:1,route:'health',goal:'报告不适',mentions:[{kind:'symptom',text:'有点不舒服'}],uncertain:['不适部位','症状性质'],suggested_tool:null}));
  assert.deepEqual(r?.uncertain,['不适部位','症状性质']);
});
