const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {ProductService}=require('../.bridge-build/product/ProductService.js');
const {ProductLocalStore}=require('../scripts/product-local-store.cjs');
const {HealthKitDeviceAdapter}=require('../.bridge-build/adapters/HealthKitDeviceAdapter.js');
const {webhookFamilyDelivery}=require('../.bridge-build/adapters/FamilyNotificationDelivery.js');
const {BrowserVoicePort}=require('../.bridge-build/adapters/BrowserVoiceAdapter.js');
const now=new Date('2026-10-02T12:00:00+08:00');
const profile={name:'SYNTHETIC TEST',age:65,conditions:[],medications:[],familyContact:'TEST',familyPhone:'',mobility:'unknown',usesCane:false,nightVision:'unknown',cognition:'unknown',familySharing:'denied'};
const sample=(id='device-1',source='device')=>({id,source,timestamp:now.toISOString(),metric:'spo2',value:97,unit:'%',visibility:'private'});
async function setup(t,extensions={}) {
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'ankang-extensions-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
 const store=new ProductLocalStore(dir),service=new ProductService(store,undefined,undefined,extensions);
 const call=(op,input={},owner='a')=>service.request(op,owner,input,now);
 await call('profile.save',{profile});await call('profile.save',{profile},'b');return {store,service,call};
}
test('device ingest validates whole batch, scopes sources, deduplicates and reaches Twin',async t=>{
 const {call}=await setup(t);
 const payload={ownerId:'a',source:'device',measurements:[sample()]};
 await call('device.import',payload);await call('device.import',payload);
 assert.equal((await call('snapshot')).state.events.length,1);
 assert.ok((await call('snapshot')).twin.recentEvents.length);
 assert.equal((await call('snapshot',{},'b')).state.events.length,0);
 for(const change of [{unit:'kg'},{metric:'__proto__'},{value:NaN},{confidence:2},{timestamp:'invalid'},{source:'healthkit'}]) await assert.rejects(call('device.import',{...payload,measurements:[sample('valid-new'),{...sample('invalid'),...change}]}));
 await assert.rejects(call('device.import',{...payload,ownerId:'b'}));
 await assert.rejects(call('device.import',{...payload,source:'demo',measurements:[sample('mock','demo')]}));
 assert.equal((await call('snapshot')).state.events.length,1);
});
test('original HealthKit HTTP adapter, diagnostics and failure codes behind product port',async t=>{
 const old=global.fetch;t.after(()=>{global.fetch=old;});let mode='ok';
 global.fetch=async url=>mode==='stale'?new Response(JSON.stringify({error:'stale_data'}),{status:409}):new Response(JSON.stringify({measurements:[sample('hk','healthkit')],diagnostics:{authorizationStatus:'request-completed',freshness:'fresh',revision:1,receivedAt:now.toISOString()}}));
 const {call}=await setup(t,{healthkit:new HealthKitDeviceAdapter('http://localhost:8787/api/healthkit/measurements','TEST')});
 await call('healthkit.import',{from:'2026-10-02',to:'2026-10-02'});
 const diag=await call('healthkit.diagnostics');assert.equal(diag.permissionPlatform,'iOS companion');assert.match(diag.lastAppliedKey,/^1:/);
 mode='stale';await assert.rejects(call('healthkit.import',{from:'2026-10-02',to:'2026-10-02'}),e=>e.code==='stale');
 assert.equal((await call('snapshot')).state.events.length,1);
});
test('webhook reuses NotificationService reservation, consent and accepted semantics',async t=>{
 const old=global.fetch;t.after(()=>{global.fetch=old;});let sends=0;
 global.fetch=async()=>{sends++;return new Response('{}',{status:200});};
 const {call}=await setup(t,{delivery:webhookFamilyDelivery({provider:'custom',token:'TEST',customUrl:'http://localhost:8788/test'})});
 await call('notification.plan');assert.equal(sends,0);
 const {code}=await call('family.invite');await call('family.bind',{code});await call('family.grant');
 await call('chat',{text:'我刚才摔了一跤，现在胸口疼'});
 const planned=await call('notification.plan');assert.ok(sends>0);assert.ok(planned.notifications.every(n=>n.phase==='accepted'));
 const count=sends;await call('notification.plan');assert.equal(sends,count);
 await call('family.revoke');await call('notification.plan');assert.equal(sends,count);
});
test('sync binding gate, owner gate, local-only events, monotonic acknowledgement and consent',async t=>{
 let listener;const sent=[];const port={via:'peer',role:'elder',status:()=>({mode:'cross-device',detail:'TEST mock',peerId:'TEST'}),broadcast:(type,payload)=>sent.push({type,payload}),subscribe:f=>{listener=f;return()=>{};},close:()=>{}};
 const {call}=await setup(t,{sync:()=>port});await call('sync.start');
 listener({type:'dispatch.acknowledge',payload:{ownerId:'a',dataMode:'personal',findingId:'x'}});assert.equal((await call('sync.poll')).outcomes[0].reason,'unbound-peer');
 const {code}=await call('family.invite');listener({type:'family.link',payload:{kind:'request',code,requestId:'req'}});await call('sync.poll');assert.equal(sent.at(-1).payload.kind,'accepted');
 await call('family.grant');await call('chat',{text:'我刚才摔了一跤，现在胸口疼'});const snapshot=await call('notification.plan');const record=snapshot.notifications[0];assert.ok(record);
 listener({type:'events.append',payload:{ownerId:'a',dataMode:'personal',events:[]}});assert.equal((await call('sync.poll')).outcomes[0].reason,'local-only-data');
 listener({type:'dispatch.append',payload:{...record,ownerId:'b'}});assert.equal((await call('sync.poll')).outcomes[0].reason,'owner-mismatch');
 listener({type:'dispatch.acknowledge',payload:{ownerId:'a',dataMode:'personal',relationshipId:record.relationshipId,findingId:record.findingId}});await call('sync.poll');
 listener({type:'dispatch.append',payload:record});await call('sync.poll');assert.equal((await call('snapshot')).notifications[0].lifecycle,'acknowledged');
 await call('sync.publish');assert.ok(sent.some(v=>v.type==='family.consent'));
 port.role='family';
 listener({type:'family.consent',fromRole:'elder',payload:{relationshipId:record.relationshipId,sharing:'denied',updatedAt:'2026-10-02T05:00:00Z'}});await call('sync.poll');
 listener({type:'family.consent',fromRole:'elder',payload:{relationshipId:record.relationshipId,sharing:'granted',updatedAt:'2026-10-02T04:00:00Z'}});assert.equal((await call('sync.poll')).outcomes[0].reason,'stale-consent');
 assert.equal((await call('family.summary')).canViewSharedDetail,false);
});
test('voice port enters existing chat and TTS reads only main block; unavailable is explicit',async t=>{
 let output;const {call}=await setup(t,{voice:{status:()=>({available:true,phase:'idle'}),recognize:async()=> '今天感觉不错',speak:async(text,config)=>{output={text,config};},cancel:()=>{}}});
 const result=await call('voice.input');const reply=result.turn.reply;
 await call('voice.output',{id:reply.id});assert.equal(output.text,reply.blocks?.find(b=>b.kind==='main')?.text??reply.text);assert.equal(output.config.rate,0.9);
 await assert.rejects(call('voice.output',{id:'missing'}));
 const {call:unavailable}=await setup(t);await assert.rejects(unavailable('voice.input'));assert.equal((await unavailable('extensions.status')).voice.available,false);
});
test('extracted browser ASR keeps language, transcript, errors and cancellation behavior',async t=>{
 const old=global.window;let rec;
 global.window={SpeechRecognition:class {constructor(){rec=this;}start(){this.onstart?.();}stop(){}},speechSynthesis:{cancel(){}}};t.after(()=>{global.window=old;});
 const voice=new BrowserVoicePort();const result=voice.recognize({});assert.equal(rec.lang,'zh-CN');rec.onresult({results:[[{transcript:'测试语音'}]]});rec.onend();assert.equal(await result,'测试语音');
 const cancelled=voice.recognize({});voice.cancel();await assert.rejects(cancelled,/cancelled/);
});
test('capture image/video use existing archive, no inferred health events',async t=>{
 const {call}=await setup(t);const result=await call('media.import',{batchId:'TEST',capturedAt:now.toISOString(),source:'browser-upload',files:[{name:'TEST video',fileName:'test.mp4',category:'影像资料',mediaType:'video/mp4',bytes:[0,1,2],visibility:'private'}]});assert.equal(result.attachments.length,1);assert.equal(result.state.events.length,0);assert.equal((await call('family.summary')).attachments.length,0);
 await assert.rejects(call('media.import',{batchId:'bad',capturedAt:now.toISOString(),files:[{mediaType:'video/mp4',bytes:[256]}]}));
});

test('local sync keeps observations/labs/chat/medication and rejects damaged events',async t=>{
 let listener;const port={via:'local',role:'elder',status:()=>({mode:'local-only',detail:'TEST',peerId:null}),broadcast:()=>{},subscribe:f=>{listener=f;return()=>{};},close:()=>{}};
 const {call}=await setup(t,{sync:()=>port});await call('sync.start');const scope={ownerId:'a',dataMode:'personal'};
 const {observationToEvent,labResultToEvent}=require('../.bridge-build/pipeline/events.js');
 const events=[observationToEvent({id:'obs',source:'manual',date:'2026-10-02',text:'TEST 自报疲劳',tags:['fatigue'],visibility:'private'}),labResultToEvent({id:'lab',source:'import',timestamp:now.toISOString(),name:'TEST laboratory',value:1,unit:'TEST',visibility:'private'})];
 listener({type:'events.append',payload:{...scope,events}});assert.equal((await call('sync.poll')).outcomes[0].applied,true);assert.equal((await call('snapshot')).state.events.length,2);
 listener({type:'events.append',payload:{...scope,events:[{...events[0],id:'wrong'}]}});assert.equal((await call('sync.poll')).outcomes[0].reason,'invalid-events');
 listener({type:'chat.append',payload:{...scope,message:{id:'local-chat',role:'elder',text:'TEST 今日情况',time:'12:00',persisted:true}}});await call('sync.poll');assert.ok((await call('snapshot')).state.chat.some(m=>m.id==='local-chat'));
 const {code}=await call('family.invite');await call('family.bind',{code});await call('family.grant');
 listener({type:'medication.update',payload:{...scope,medicationRecords:[{id:'med',name:'TEST medication',dose:'TEST',purpose:'',times:'',status:'stopped'}]}});await call('sync.poll');assert.equal((await call('snapshot')).profile.profile.medicationRecords[0].status,'stopped');
});
test('original BroadcastChannel transport sends once and closes without network',async t=>{
 const {openBrowserSync}=require('../.bridge-build/sync/BrowserSyncAdapter.js');
 const a=await openBrowserSync('elder'), b=await openBrowserSync('family');t.after(()=>{a.close();b.close();});
 const received=new Promise(resolve=>b.subscribe(resolve));a.broadcast('signals.summary',{today:'2026-10-02',signalCount:1,gatedAlertCount:0});
 const timeout=new Promise((_,reject)=>{const timer=setTimeout(()=>reject(new Error('Local sync timeout')),2000);timer.unref();});
 const envelope=await Promise.race([received,timeout]);assert.equal(envelope.type,'signals.summary');assert.equal(b.status().mode,'local-only');
});
