'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const P=require('../static/library-practice.js'),scope={participant_id:crypto.randomUUID(),provider:'phone-local-1',source_context:'PHONE_LOCAL:SELF_USE'};
const storage=()=>({values:new Map(),getItem(k){return this.values.get(k)??null;},setItem(k,v){this.values.set(k,v);}});
const record=()=>({version:P.VERSION,id:crypto.randomUUID(),context:{...scope},card_id:'T-LOW-046',name:'坐姿踝主动背屈与跖屈：无外阻',state:'IN_PROGRESS',started_at:new Date().toISOString(),elapsed_ms:0,step_index:0,feedback:null});
test('all 122 training cards have their own literal steps and no guessed prescription',()=>{
 const c=JSON.parse(fs.readFileSync(path.join(__dirname,'../static/assets/rehab-library-v1/catalogue.json'))),cards=c.actions.filter(c=>c.kind==='training');assert.equal(cards.length,122);
 for(const c of cards){const list=P.steps(c);assert(list.length>0&&list.length<100,c.id);assert(list.every(s=>!/^\d+\./.test(s)));}
 assert.deepEqual(P.steps({instructions:'1. 准备\n2. 缓慢抬起\n3. 回位'}),['准备','缓慢抬起','回位']);
});
test('records are isolated by participant, provider and source context',()=>{
 const s=storage(),a=new P.Records(s,scope),r=record();a.save(r);
 for(const c of [{...scope,participant_id:crypto.randomUUID()},{...scope,provider:'other'},{...scope,source_context:'REPLAY_FILE:SELF_USE'}]){const b=new P.Records(s,c);assert.equal(b.value.records.length,0);assert.throws(()=>b.save(r));}
 assert.equal(new P.Records(s,scope).value.records.length,1);
});
test('repeated save is idempotent and finished records cannot be silently overwritten',()=>{
 const s=storage(),a=new P.Records(s,scope),r=record();a.save(r);a.save(r);assert.equal(a.value.records.length,1);
 const ended={...r,state:'FINISHED',ended_at:new Date().toISOString(),finish_reason:'completed',elapsed_ms:1234,feedback:{pain:0,fatigue:null}};
 a.save(ended);a.save(ended);assert.throws(()=>a.save({...ended,elapsed_ms:9999}));assert.throws(()=>a.save(r));
 assert.equal(a.value.records[0].elapsed_ms,1234);assert.equal(a.value.records[0].feedback.pain,0);
});
test('concurrent windows preserve the newer original record rather than last-write-wins',()=>{
 const s=storage(),a=new P.Records(s,scope),b=new P.Records(s,scope);a.save(record());assert.throws(()=>b.save(record()),/另一页面/);assert.equal(new P.Records(s,scope).value.records.length,1);
});
test('malformed or foreign saved records are rejected without modifying storage',()=>{
 for(const modify of [r=>r.card_id='shoulder_abduction',r=>r.card_id='E-LOW-001',r=>r.context.participant_id=crypto.randomUUID(),r=>r.elapsed_ms=-1,r=>r.elapsed_ms=Infinity,r=>r.step_index=-1,r=>r.feedback={pain:11,fatigue:0},r=>r.feedback={pain:'0',fatigue:null},r=>r.state='MEASURED']){
  const s=storage(),a=new P.Records(s,scope),r=record();modify(r);assert.throws(()=>a.save(r));assert.equal(s.values.size,0);
 }
 const s=storage(),a=new P.Records(s,scope);s.setItem(a.key,'bad json');assert.throws(()=>new P.Records(s,scope));assert.equal(s.getItem(a.key),'bad json');
});
test('timer counts only short active monotonic intervals, never pauses or hidden gaps',()=>{
 const r=record();assert.equal(P.advance(r,500,0,true).elapsed_ms,500);assert.equal(P.advance(r,500,0,false).elapsed_ms,0);assert.equal(P.advance(r,30000,0,true).elapsed_ms,0);assert.equal(P.advance(r,0,100,true).elapsed_ms,0);assert.equal(r.elapsed_ms,0);assert.equal(P.format(65000),'01:05');
});
test('illustrated training never claims a measured angle or completes a formal plan',()=>{
 const source=fs.readFileSync(path.join(__dirname,'../static/library-practice.js'),'utf8');
 assert(!source.includes("api('/jobs"));assert(!source.includes("api('/plan"));assert(!source.includes('target_angle'));assert(!source.includes('self_reported_count'));assert(!source.includes('state.training='));
 assert(source.includes('本机记录'));assert(source.includes("api('/practice/context')"));
 const html=fs.readFileSync(path.join(__dirname,'../static/index.html'),'utf8');assert(html.indexOf('/static/library-practice.js')>html.indexOf('/static/rehab-library.js'));assert(html.indexOf('/static/library-practice.js')<html.indexOf('/static/motion-review.js'));
});
