import test from 'node:test';
import assert from 'node:assert/strict';
import { CareCoordinator, actionEvidence, type CareFacts, type CareAction } from '../src/care/CareCoordinator';

const now = new Date('2026-10-10T09:00:00+08:00');
function fixture() {
  let facts: CareFacts = {scope:{participant_id:'TEST',source_kind:'SYNTHETIC',usage_context:'TEST'},
    medications:[{id:'m',name:'测试药',dose:'既有说明',purpose:'',times:'',status:'active'}],
    daily:{medSchedules:{m:{times:['08:00'],start:'2026-10-01',end:''}},doses:{},
      schedules:[{id:'s',date:'2026-10-10',time:'14:00',kind:'training',name:'测试训练',planId:'p',revision:1}]},
    plans:[{id:'p',revision:1,next_available:true,availability_reason:'',progress:{next_key:'entry',blocked:''}}],history:[]};
  const values = new Map<string, any>(), receipts = new Map<string, any>();
  let executions = 0, fail = false, hostNow=now;
  const port = {read:async()=>structuredClone(facts),execute:async(action:CareAction,key:string,expiresAt:string)=>{
    if(receipts.has(key))return receipts.get(key);
    if(hostNow.getTime()>Date.parse(expiresAt))throw Error('TEST confirmation expired');
    if(fail)throw Error('TEST storage unavailable');
    assert.deepEqual(action.expected, actionEvidence(facts,action));
    executions++;
    if(action.operation==='daily.dose')facts.daily.doses[action.payload.medId+'|'+action.payload.date+'|'+action.payload.time]={...action.payload};
    else facts.daily.schedules=facts.daily.schedules.map(s=>s.id===action.payload.id?{...s,...action.payload}:s);
    const receipt={status:'succeeded' as const,idempotencyKey:key,operation:action.operation};receipts.set(key,receipt);return receipt;
  }};
  const storage={read:<T>(key:string)=>structuredClone(values.get(key)??null) as T|null,write:(key:string,value:unknown)=>{values.set(key,structuredClone(value));}};
  return {get facts(){return facts;},set facts(v){facts=v;},port,storage,values,
    coordinator:()=>new CareCoordinator('personal:TEST',storage,port),get executions(){return executions;},set fail(v:boolean){fail=v;},set hostNow(v:Date){hostNow=v;}};
}
const intents = [{kind:'record_dose',medId:'m',date:'2026-10-10',time:'08:00',status:'taken'},
  {kind:'reschedule_rehab',scheduleId:'s',date:'2026-10-10',time:'16:00'}];
test('compound care proposal performs no write; exact confirmation executes both and returns receipts',async()=>{
  const f=fixture(),c=f.coordinator(),w=await c.prepare({requestId:'TEST-request-1',intents},now);
  assert.equal(w.status,'awaiting_confirmation');assert.equal(f.executions,0);
  await assert.rejects(c.confirm(w.id,'forged',now));assert.equal(f.executions,0);
  const done=await c.confirm(w.id,w.confirmationToken!,now);assert.equal(done.status,'succeeded');assert.equal(f.executions,2);
  assert.equal(f.facts.daily.schedules[0].time,'16:00');assert.equal(done.steps.every(s=>s.receipt?.status==='succeeded'),true);
  await c.confirm(w.id,w.confirmationToken!,now);assert.equal(f.executions,2);
});
test('request replay returns the same proposal; changed request under the same ID is rejected',async()=>{
  const c=fixture().coordinator(),w=await c.prepare({requestId:'TEST-replay',intents},now);
  assert.equal((await c.prepare({requestId:'TEST-replay',intents},now)).id,w.id);
  await assert.rejects(c.prepare({requestId:'TEST-replay',intents:[intents[0]]},now));
});
test('changed medicine, occurrence, plan or arrangement requires a new proposal',async()=>{
  for(const change of ['medicine','dose','plan','schedule']){
    const f=fixture(),c=f.coordinator(),w=await c.prepare({requestId:'TEST-stale-'+change,intents},now);
    if(change==='medicine')f.facts.medications[0].dose='changed';
    if(change==='dose')f.facts.daily.doses['m|2026-10-10|08:00']={status:'taken'};
    if(change==='plan')f.facts.plans[0].revision=2;
    if(change==='schedule')f.facts.daily.schedules[0].time='15:00';
    const done=await c.confirm(w.id,w.confirmationToken!,now);
    assert.notEqual(done.status,'succeeded');
    assert.equal(f.executions,change==='plan'||change==='schedule'?1:0);
  }
});
test('partial execution is retained and retry only applies unfinished steps',async()=>{
  const f=fixture(),port={...f.port,execute:async(a:CareAction,k:string,e:string)=>{if(a.operation==='daily.schedule')throw Error('TEST unavailable');return f.port.execute(a,k,e);}};
  const c=new CareCoordinator('personal:TEST',f.storage,port),w=await c.prepare({requestId:'TEST-partial',intents},now);
  const partial=await c.confirm(w.id,w.confirmationToken!,now);assert.equal(partial.status,'partially_succeeded');assert.equal(f.executions,1);
  const done=await f.coordinator().confirm(w.id,w.confirmationToken!,now);assert.equal(done.status,'succeeded');assert.equal(f.executions,2);
});
test('host receipt makes recovery idempotent even if coordinator dies after the business write',async()=>{
  const f=fixture();let loseAcknowledgement=true;
  const port={...f.port,execute:async(a:CareAction,k:string,e:string)=>{const r=await f.port.execute(a,k,e);if(loseAcknowledgement){loseAcknowledgement=false;throw Error('TEST receipt lost');}return r;}};
  const c=new CareCoordinator('personal:TEST',f.storage,port),w=await c.prepare({requestId:'TEST-lost',intents:[intents[0]]},now);
  assert.equal((await c.confirm(w.id,w.confirmationToken!,now)).status,'failed');
  f.hostNow=new Date(now.getTime()+16*60000);
  assert.equal((await f.coordinator().confirm(w.id,w.confirmationToken!,now)).status,'succeeded');assert.equal(f.executions,1);
});

test('direct text API rejects negation, hypotheses, examples, quotes and other people',async()=>{
  const f=fixture(),c=f.coordinator();
  for(const text of ['不要把今天训练改到下午四点','如果今天训练改到下午四点会怎么样','假设今天训练改到下午四点',
    '他今天训练改到下午四点','她今天08:00测试药已服用','假设测试药今天08:00已服用','帮我举个例子记录今天08:00的测试药已服用',
    '记录今天08:00的测试药没有服用','“记录今天08:00的测试药已服用”','无需把今天训练改到下午四点','无须把今天训练改到下午四点']){
    const w=await c.prepare({requestId:crypto.randomUUID(),text},now);
    assert.equal(w.status,'needs_clarification',text);assert.equal(w.steps.length,0);
  }
  f.facts.medications[0].name='阿托伐他汀';
  const w=await c.prepare({requestId:'TEST-drug-name',text:'记录今天08:00的阿托伐他汀已服用'},now);
  assert.equal(w.status,'awaiting_confirmation');assert.equal(f.executions,0);
});

test('reschedule parses the original occurrence separately from its new date and time',async()=>{
  const c=fixture().coordinator();
  for(const [text,date,time] of [
    ['今天训练改到明天下午四点','2026-10-11','16:00'],
    ['今天14:00的训练改到16:00','2026-10-10','16:00'],
    ['今天训练改到下午4:00','2026-10-10','16:00'],
  ]){
    const w=await c.prepare({requestId:crypto.randomUUID(),text},now);
    assert.equal(w.status,'awaiting_confirmation');assert.equal(w.steps[0].action.payload.date,date);assert.equal(w.steps[0].action.payload.time,time);
  }
  for(const text of ['今天训练改到下午四点四十五分','今天训练改到今天或明天下午四点','今天训练改到后天下午四点','今天训练改到晚上十二点','今天训练改到晚上零点','今天训练改到晚上0:30'])
    assert.equal((await c.prepare({requestId:crypto.randomUUID(),text},now)).status,'needs_clarification',text);
});

test('expired partial approval can recover a receipt but cannot create another business write',async()=>{
  const f=fixture(),port={...f.port,execute:async(a:CareAction,k:string,e:string)=>{
    if(a.operation==='daily.schedule')throw Error('TEST temporarily unavailable');return f.port.execute(a,k,e);}};
  const c=new CareCoordinator('personal:TEST',f.storage,port),w=await c.prepare({requestId:'TEST-partial-expiry',intents},now);
  assert.equal((await c.confirm(w.id,w.confirmationToken!,now)).status,'partially_succeeded');
  const later=new Date(now.getTime()+16*60000);f.hostNow=later;
  assert.equal((await f.coordinator().confirm(w.id,w.confirmationToken!,later)).status,'partially_succeeded');
  assert.equal(f.executions,1);
  const audit=JSON.stringify(c.audit());assert(!audit.includes('confirmationToken'));assert(!audit.includes('expected'));
});
test('expired, cancelled and another owner/source confirmations never write',async()=>{
  const f=fixture(),c=f.coordinator();
  const expired=await c.prepare({requestId:'TEST-expire',intents},now);
  assert.equal((await c.confirm(expired.id,expired.confirmationToken!,new Date(now.getTime()+16*60000))).status,'expired');
  const cancelled=await c.prepare({requestId:'TEST-cancel',intents},now);await c.cancel(cancelled.id,cancelled.confirmationToken!);
  await assert.rejects(c.confirm(cancelled.id,cancelled.confirmationToken!,now));
  const other=new CareCoordinator('personal:OTHER',f.storage,f.port);await assert.rejects(other.confirm(expired.id,expired.confirmationToken!,now));
  const scope=await c.prepare({requestId:'TEST-scope',intents},now);f.facts.scope.source_kind='REPLAY_FILE';
  await assert.rejects(c.confirm(scope.id,scope.confirmationToken!,now));assert.equal(f.executions,0);
});
test('unknown operations, extra fields, future doses and duplicate targets cannot become actions',async()=>{
  const c=fixture().coordinator();
  for(const invalid of [[{kind:'prescribe',dose:5}],[{...intents[0],owner:'OTHER'}],[{...intents[0],date:'2099-01-01'}],[intents[0],intents[0]]])
    await assert.rejects(c.prepare({requestId:crypto.randomUUID(),intents:invalid},now));
});
test('ambiguous text asks for details; explicit text creates a confirmation, never silently writes',async()=>{
  const f=fixture(),c=f.coordinator();
  assert.equal((await c.prepare({requestId:'TEST-ambiguous',text:'药吃了，帮我记一下'},now)).status,'needs_clarification');
  const w=await c.prepare({requestId:'TEST-explicit',text:'记录今天08:00的测试药已服用；今天训练改到下午四点'},now);
  assert.equal(w.steps.length,2);assert.equal(w.status,'awaiting_confirmation');assert.equal(f.executions,0);
});
test('overview keeps unrecorded distinct from missed and next-step uses existing business gates',async()=>{
  const f=fixture(),c=f.coordinator(),overview=await c.overview(now);
  assert.equal(overview.doses[0].status,'unrecorded');
  f.facts.plans[0].next_available=false;f.facts.plans[0].availability_reason='TEST assessment expired';
  const next=await c.nextStep(now);assert.equal(next.available,false);assert.equal(next.reason,'TEST assessment expired');
});
test('concurrent confirmations serialize; invalid receipt never claims success',async()=>{
  const f=fixture(),c=f.coordinator(),w=await c.prepare({requestId:'TEST-concurrent',intents},now);
  const result=await Promise.all([c.confirm(w.id,w.confirmationToken!,now),c.confirm(w.id,w.confirmationToken!,now)]);
  assert(result.every(r=>r.status==='succeeded'));assert.equal(f.executions,2);
  const bad=new CareCoordinator('personal:TEST',f.storage,{...f.port,execute:async()=>({status:'succeeded',idempotencyKey:'wrong',operation:'daily.dose'})});
  const p=await bad.prepare({requestId:'TEST-bad-receipt',intents:[{...intents[0],status:'skipped'}]},now);
  assert.equal((await bad.confirm(p.id,p.confirmationToken!,now)).status,'failed');
});
