const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {ProductService} = require('../.bridge-build/product/ProductService.js');
const {ProductLocalStore} = require('../scripts/product-local-store.cjs');
const profile = name => ({name, age:65, conditions:[], medications:[], familyContact:'家属',familyPhone:'',
  mobility:'unknown', usesCane:false, nightVision:'unknown', cognition:'unknown', familySharing:'denied'});
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

test('image candidates require consent and confirmation; corrupt data fails closed', async t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(),'ankang-image-test-'));
  t.after(() => fs.rmSync(root,{recursive:true,force:true}));
  const port = new ProductLocalStore(root);
  const vision = {name:'TEST protocol fixture',analyzeImage:async () => ({kind:'weight',
    measurements:[{metric:'weight',value:63,unit:'kg',confidence:0.99}],labResults:[],confidence:0.99})};
  const service = new ProductService(port,undefined,vision);
  const call = (op,input={}) => service.request(op,'a',input,new Date('2026-10-02T12:00:00+08:00'));
  await call('profile.save',{profile:profile('TEST 图片用户')});
  await assert.rejects(call('health.record',{metric:'__proto__',value:1}));
  await assert.rejects(call('health.record',{metric:'weight',value:NaN}));
  await assert.rejects(call('image.parse',{bytes:[1],mediaType:'image/png'}));
  const parsed = await call('image.parse',{bytes:[1],mediaType:'image/png',consent:true});
  assert.equal(parsed.measurements.length,1);
  assert.equal((await call('snapshot')).state.events.length,0);
  await assert.rejects(call('image.confirm',{confirmed:false}));
  await call('image.confirm',{confirmed:true});
  assert.equal((await call('snapshot')).history.measurements.length,1);
  await assert.rejects(call('image.confirm',{confirmed:true}));
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
