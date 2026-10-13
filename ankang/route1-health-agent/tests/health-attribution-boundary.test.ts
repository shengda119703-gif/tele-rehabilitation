import test from 'node:test';
import assert from 'node:assert/strict';
import { acceptedSelfClaims, understandElderInput, understandElderInputWithOverrides } from '../src/engine/understanding';
const today = '2026-10-12';
const prior = [{id:'real-prior',role:'elder' as const,text:'我今天血糖5.5',time:today+'T09:00:00Z'}];
for (const text of ['张三今天血糖9.5','刚才说错了，这个血压180/110不是我的','我血糖9.5，不是我的','我血压180/110，不是我','今天张三血糖9.5','我看到张三血糖9.5','李四今天血压180/110','我朋友今天血糖9.5','王小明的血氧88%',
  '资料里写着血压180/110，不是我的记录','报告示例中血糖9.5，这不是我的结果',
  '例如我血糖9.5','“我今天血压180/110”','我今天血糖9.5，这不是我的数据']) {
  test('untrusted ownership cannot add self facts: '+text,()=>{
    for (const history of [[],prior]) {
      const input=understandElderInput(text,today,history);
      assert.equal(acceptedSelfClaims(input).length,0);
      assert.ok(input.clarificationQuestion);
      assert.equal(input.correction,false);
      assert.equal(input.correctionTargetMessageId,undefined);
    }
    const overridden=understandElderInputWithOverrides(text,today,prior,new Map([[text,'occurred']]));
    assert.equal(acceptedSelfClaims(overridden).length,0);
  });
}
for (const text of ['我今天血糖5.5','我今天静息心率68','今天血压120/80','血糖5.5','告诉女儿我今天血糖5.5','我昨天血压120/80']) {
  test('genuine self report remains accepted: '+text,()=>assert.ok(acceptedSelfClaims(understandElderInput(text,today)).length));
}
test('explicit retraction without a new quoted result still corrects the previous turn',()=>{
  const input=understandElderInput('刚才说错了，不是我',today,prior);
  assert.equal(input.correctionTargetMessageId,'real-prior');
});
