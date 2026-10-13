const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {ProductService} = require('../.bridge-build/product/ProductService.js');
const {ProductLocalStore} = require('../scripts/product-local-store.cjs');
const profile = name => ({name, age:65, conditions:[], medications:[], familyContact:'家属',familyPhone:'',
  mobility:'unknown', usesCane:false, nightVision:'unknown', cognition:'unknown', familySharing:'denied'});
test('report originals stay private; retired image operations cannot create health facts', async t => {
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'ankang-manual-report-'));
  t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
  let providerCalls=0;
  const vision={analyzeImage:async()=>{providerCalls++;throw Error('Retired provider invoked');}};
  const store=new ProductLocalStore(root),service=new ProductService(store,undefined,vision);
  const now=new Date('2026-10-13T09:00:00+08:00');
  const call=(op,owner,input={})=>service.request(op,owner,input,now);
  for(const owner of ['self','other'])await call('profile.save',owner,{profile:profile('TEST '+owner)});
  await call('archive.save','self',{name:'TEST 报告',fileName:'report.png',mediaType:'image/png',bytes:[1,2,3],category:'体检报告',visibility:'private'});
  let snap=await call('snapshot','self');assert.equal(snap.state.events.length,0);
  const id=snap.attachments[0].id;assert.deepEqual((await call('archive.read','self',{id})).bytes,[1,2,3]);
  await assert.rejects(call('archive.read','other',{id}));
  for(const op of ['image.parse','image.confirm'])await assert.rejects(call(op,'self',{bytes:[1],mediaType:'image/png',consent:true,confirmed:true}),/手动录入/);
  assert.equal(providerCalls,0);assert.equal((await call('snapshot','self')).state.events.length,0);
  await call('health.record','self',{metric:'weight',value:63,visibility:'private'});
  const reopened=new ProductService(store);snap=await reopened.request('snapshot','self',{},now);
  const m=snap.history.measurements[0];assert.equal(m.value,63);assert.equal(m.unit,'kg');assert.equal(m.source,'manual');assert.equal(m.visibility,'private');
  assert.equal(snap.capabilities.imageRecognitionAvailable,false);assert.equal(snap.capabilities.healthInput,'manual');
  assert.equal((await call('snapshot','other')).history.measurements.length,0);
});

test('temporary file sharing errors recover without losing the backup', t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'ankang-file-sharing-'));
  t.after(() => fs.rmSync(root, {recursive:true, force:true}));
  const store = new ProductLocalStore(root), key = 'notifications:personal:TEST';
  store.write(key, {revision:1});
  const copy = fs.copyFileSync, rename = fs.renameSync;
  let copyCalls = 0, renameCalls = 0;
  t.mock.method(fs, 'copyFileSync', (...args) => {
    if (copyCalls++ === 0) throw Object.assign(new Error('TEST sharing violation'), {code:'EBUSY'});
    return copy(...args);
  });
  t.mock.method(fs, 'renameSync', (...args) => {
    if (renameCalls++ === 0) throw Object.assign(new Error('TEST sharing violation'), {code:'EPERM'});
    return rename(...args);
  });
  store.write(key, {revision:2});
  assert.deepEqual(store.read(key), {revision:2});
  assert.deepEqual(JSON.parse(fs.readFileSync(store.file(key)+'.bak','utf8')).value, {revision:1});
  assert.equal(fs.readdirSync(path.dirname(store.file(key))).some(f => f.endsWith('.tmp')), false);
});

test('permanent replacement failure stays an error and preserves the old record', t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'ankang-file-failure-'));
  t.after(() => fs.rmSync(root, {recursive:true, force:true}));
  const store = new ProductLocalStore(root), key = 'notifications:personal:TEST';
  store.write(key, {revision:1});
  let attempts = 0;
  t.mock.method(fs, 'renameSync', () => {
    attempts++;
    throw Object.assign(new Error('TEST denied replacement'), {code:'EPERM'});
  });
  assert.throws(() => store.write(key, {revision:2}), {code:'EPERM'});
  assert.ok(attempts > 1 && attempts <= 6);
  assert.deepEqual(store.read(key), {revision:1});
  assert.deepEqual(JSON.parse(fs.readFileSync(store.file(key)+'.bak','utf8')).value, {revision:1});
  assert.equal(fs.readdirSync(path.dirname(store.file(key))).some(f => f.endsWith('.tmp')), false);
});

test('durable owner isolation, medication, tasks, health, reports and privacy', async t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'ankang-product-'));
  t.after(() => fs.rmSync(root, {recursive:true, force:true}));
  let service = new ProductService(new ProductLocalStore(root));
  const now = new Date('2026-10-02T12:00:00+08:00');
  const call = (op, owner, input={}) => service.request(op, owner, input, now);
  await call('profile.save', 'a', {profile:profile('合成用户 A')});
  await call('profile.save', 'b', {profile:profile('合成用户 B')});
  await call('medication.save', 'a', {record:{id:'m1', name:'TEST 药物',dose:'遵医嘱',purpose:'',times:'',status:'active'}});
  const state = await call('snapshot','a');
  const task = state.state.tasks.find(t => t.kind === 'medication_check');
  await call('task.status', 'a', {id:task.id,status:'completed'});
  await call('health.record','a',{metric:'weight', value:60, visibility:'private'});
  const turn = await call('chat','a',{text:'不要记录：今天感觉不错'});
  assert.equal(turn.turn.reply.persisted, false);
  service = new ProductService(new ProductLocalStore(root));
  const loaded = await call('snapshot','a');
  assert.equal(loaded.state.tasks.find(t => t.id === task.id).status, 'completed');
  assert.equal(loaded.state.chat.some(m => m.text.includes('不要记录')), false);
  assert.equal(loaded.history.measurements.length,1);
  assert.ok(loaded.history.report.sections.length);
  assert.equal((await call('snapshot','b')).history.measurements.length,0);
  const family = await call('family.summary','a');
  assert.equal(family.canViewSharedDetail,false);
  assert.equal(family.history,null);
  assert.equal(family.twin.recentEvents.length,0);
});
test('family consent, private attachments, notification honesty and clear isolation', async t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(),'ankang-product-'));
  t.after(() => fs.rmSync(root,{recursive:true,force:true}));
  const port = new ProductLocalStore(root), service = new ProductService(port);
  const now = new Date('2026-10-02T12:00:00+08:00');
  const call = (op,owner,input={}) => service.request(op,owner,input,now);
  for (const owner of ['a','b']) await call('profile.save',owner,{profile:profile('合成用户 '+owner)});
  const {code} = await call('family.invite','a');
  await assert.rejects(call('family.bind','a',{code:'invalid'}));
  await call('family.bind','a',{code});
  assert.equal((await call('family.summary','a')).canViewSharedDetail,false);
  await call('family.grant','a');
  await call('archive.save','a',{name:'测试附件',fileName:'test.txt',category:'其他资料',mediaType:'text/plain',bytes:[65,66],visibility:'private'});
  await call('health.record','a',{metric:'weight',value:61,visibility:'family_ok'});
  const summary = await call('family.summary','a');
  assert.equal(summary.canViewSharedDetail,true);
  assert.equal(summary.history.measurements.length,1);
  assert.equal(summary.attachments.length,0);
  await call('chat','a',{text:'我刚才在卫生间摔了一跤，现在胸口有点疼'});
  const planned = await call('notification.plan','a');
  assert.ok(planned.notifications.length>0);
  assert.ok(planned.notifications.every(n => n.phase==='unavailable'));
  await call('notification.ack','a',{id:planned.notifications[0].findingId});
  const restored = await new ProductService(new ProductLocalStore(root)).request('snapshot','a',{},now);
  assert.ok(restored.notifications[0].acknowledgedAt);
  await call('family.revoke','a');
  assert.equal((await call('family.summary','a')).history,null);
  await call('notification.plan','a');
  await assert.rejects(call('notification.ack','a',{id:'not-authorized'}));
  await assert.rejects(call('image.parse','a',{bytes:[1],mediaType:'image/png',consent:true}));
  await assert.rejects(call('lifecycle.clear','a',{confirmOwner:'b'}));
  const backup = await call('lifecycle.export','a');
  assert.deepEqual(backup.attachments[0].bytes,[65,66]);
  await call('lifecycle.clear','a',{confirmOwner:'a'});
  const empty = await call('snapshot','a');
  assert.equal(empty.attachments.length,0);
  assert.equal(empty.state.events.length,0);
  assert.equal((await call('profile.list','')).length,2);
  assert.ok((await call('snapshot','b')).profile);
});

test('manual health validates input and corrupt stored data fails closed', async t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(),'ankang-manual-test-'));
  t.after(() => fs.rmSync(root,{recursive:true,force:true}));
  const port = new ProductLocalStore(root),service = new ProductService(port);
  const call = (op,input={}) => service.request(op,'a',input,new Date('2026-10-13T12:00:00+08:00'));
  await call('profile.save',{profile:profile('TEST 手动用户')});
  await assert.rejects(call('health.record',{metric:'__proto__',value:1}));
  await assert.rejects(call('health.record',{metric:'weight',value:NaN}));
  await assert.rejects(call('image.parse',{bytes:[1],mediaType:'image/png',consent:true}),/手动录入/);
  await call('health.record',{metric:'weight',value:63});
  assert.equal((await call('snapshot')).history.measurements.length,1);
  const recordDir = path.join(root,'profiles');
  const file = fs.readdirSync(recordDir).find(n => n.endsWith('.json'));
  fs.writeFileSync(path.join(recordDir,file),'{broken');
  assert.throws(() => port.profiles());
});


test('backup excludes no-record turns without changing the live conversation', async t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'ankang-private-backup-'));
  t.after(() => fs.rmSync(root, {recursive:true, force:true}));
  const service = new ProductService(new ProductLocalStore(root));
  const now = new Date('2026-10-03T12:00:00+08:00');
  const call = (op, input={}) => service.request(op, 'TEST-backup-owner', input, now);
  await call('profile.save', {profile:profile('TEST 私密备份')});
  await call('chat', {text:'TEST_DURABLE 今天感觉不错'});
  await call('chat', {text:'不要记录：TEST_PRIVATE 今天感觉很累'});
  const live = await call('snapshot');
  assert.ok(live.state.chat.some(m => m.text.includes('TEST_PRIVATE') && m.persisted === false));
  const exported = await call('lifecycle.export');
  assert.ok(exported.snapshot.state.chat.some(m => m.text.includes('TEST_DURABLE')));
  assert.equal(exported.snapshot.state.chat.some(m => m.persisted === false), false);
  assert.equal(JSON.stringify(exported).includes('TEST_PRIVATE'), false);
  assert.ok((await call('snapshot')).state.chat.some(m => m.text.includes('TEST_PRIVATE')));
});

function syntheticProductPort() {
  const values=new Map();
  return {
    read:key=>structuredClone(values.get(key)??null),
    write:(key,value)=>values.set(key,structuredClone(value)),
    remove:key=>values.delete(key),
    profiles:()=>[...values.entries()].filter(([key])=>key.startsWith('profile:')).map(([,value])=>structuredClone(value)),
    attachments:{list:async()=>[],clear:async()=>{}},
  };
}

test('care backup excludes pending credentials and preconditions while the self view keeps confirmation usable',async()=>{
  const owner='TEST-care-backup',now=new Date('2026-10-11T09:00:00+08:00');
  const facts={scope:{participant_id:owner,source_kind:'SYNTHETIC',usage_context:'TEST'},
    medications:[{id:'TEST-med',name:'TEST 药物',dose:'既有说明',purpose:'',times:'',status:'active'}],
    daily:{medSchedules:{'TEST-med':{times:['08:00'],start:'2026-10-01',end:''}},doses:{},schedules:[]},plans:[],history:[]};
  let writes=0;
  const host={read:async()=>structuredClone(facts),execute:async()=>{writes++;throw Error('TEST must not execute');}};
  const service=new ProductService(syntheticProductPort(),undefined,undefined,{},()=>host);
  const call=(operation,input={})=>service.request(operation,owner,input,now);
  await call('profile.save',{profile:profile('TEST 照护备份')});
  const workflow=await call('care.prepare',{requestId:'TEST-care-export',intents:[
    {kind:'record_dose',medId:'TEST-med',date:'2026-10-11',time:'08:00',status:'taken'}]});
  assert.equal((await call('snapshot')).carePending[0].confirmationToken,workflow.confirmationToken);
  const exported=await call('lifecycle.export'),encoded=JSON.stringify(exported);
  assert.equal(exported.careAudit[0].id,workflow.id);
  assert.equal(Object.hasOwn(exported.snapshot,'carePending'),false);
  assert.equal(Object.hasOwn(exported.snapshot,'carePendingUnavailable'),false);
  for(const key of ['confirmationToken','requestSignature','expected'])assert.equal(encoded.includes('"'+key+'"'),false,key);
  assert.equal(encoded.includes(workflow.confirmationToken),false);
  assert.equal((await call('snapshot')).carePending[0].confirmationToken,workflow.confirmationToken);
  assert.equal(writes,0);
});

test('backup redacts nested execution credentials without dropping ordinary business expected fields',async()=>{
  const owner='TEST-backup-metadata',now=new Date('2026-10-11T09:00:00+08:00');
  const service=new ProductService(syntheticProductPort());
  await service.request('profile.save',owner,{profile:{...profile('TEST 备份字段'),metadata:{
    expected:'TEST-business-value',confirmationToken:'TEST-nested-token',requestSignature:'TEST-nested-signature'}}},now);
  const exported=await service.request('lifecycle.export',owner,{},now),encoded=JSON.stringify(exported);
  assert.equal(exported.snapshot.profile.profile.metadata.expected,'TEST-business-value');
  assert.equal(encoded.includes('TEST-nested-token'),false);
  assert.equal(encoded.includes('TEST-nested-signature'),false);
  assert.equal(encoded.includes('"confirmationToken"'),false);
  assert.equal(encoded.includes('"requestSignature"'),false);
});

test('module rehab reads reject malformed or another owner receipts before exposing records',async()=>{
  const owner='TEST-rehab-receipt',now=new Date('2026-10-11T09:00:00+08:00');
  const queries=[['查看训练计划','rehab_plan'],['查看最近评估结果','rehab_assessments'],['查看训练记录','rehab_history']];
  const invalid=[
    value=>({...value,tool:'rehab.get_other'}),
    value=>({...value,read_only:false}),
    value=>({...value,status:'succeeded'}),
    value=>({...value,records:{id:'TEST_UNTRUSTED'}}),
    value=>({...value,scope:null}),
    value=>({...value,scope:{...value.scope,participant_id:'OTHER'}}),
    value=>({...value,scope:{...value.scope,source_kind:''}}),
    value=>({...value,scope:{...value.scope,usage_context:undefined}}),
  ];
  for(const [text,name] of queries)for(const damage of invalid){
    const host={read:async call=>damage({tool:call.name,read_only:true,status:'found',
      scope:{participant_id:owner,source_kind:'SYNTHETIC',usage_context:'TEST'},records:[{id:'TEST_UNTRUSTED'}]})};
    const service=new ProductService(syntheticProductPort(),undefined,undefined,{},undefined,undefined,()=>host);
    await service.request('profile.save',owner,{profile:profile('TEST 康复回执')},now);
    const result=await service.request('chat',owner,{text},now),step=result.turn.agent.steps[0];
    assert.equal(step.name,name);
    assert.equal(step.status,'failed',text);
    assert.equal(step.data,undefined);
    assert.equal(result.turn.reply.text.includes('TEST_UNTRUSTED'),false);
  }
});

test('module rehab reads keep valid host source and usage context facts',async()=>{
  const owner='TEST-rehab-valid',now=new Date('2026-10-11T09:00:00+08:00');
  const queries=['查看训练计划','查看最近评估结果','查看训练记录'];
  const host={read:async call=>({tool:call.name,read_only:true,status:'empty',
    scope:{participant_id:owner,source_kind:'REPLAY_FILE',usage_context:'SELF_USE'},records:[]})};
  const service=new ProductService(syntheticProductPort(),undefined,undefined,{},undefined,undefined,()=>host);
  await service.request('profile.save',owner,{profile:profile('TEST 康复来源')},now);
  for(const text of queries){
    const result=await service.request('chat',owner,{text},now),step=result.turn.agent.steps[0];
    assert.equal(step.status,'succeeded');
    assert.deepEqual(step.data.scope,{participant_id:owner,source_kind:'REPLAY_FILE',usage_context:'SELF_USE'});
    assert.deepEqual(step.data.records,[]);
  }
});
