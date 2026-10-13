'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const M=require('../static/medication-v121.js');
function fixture(){return {profile:{ownerId:'TEST-owner',dataMode:'personal',profile:{medicationRecords:[
 {id:'TEST-A',name:'TEST 药物 A',dose:'按既有医嘱',status:'active'},
 {id:'TEST-B',name:'TEST 药物 B',dose:'',status:'active'},
 {id:'TEST-stopped',name:'TEST 停用记录',status:'stopped'}]}},dailyProduct:{medSchedules:{
 'TEST-A':{times:['08:00','20:00'],start:'2026-10-01',end:'2026-10-31'},
 'TEST-B':{times:['12:30'],start:'2026-10-01',end:''},
 'TEST-stopped':{times:['09:00'],start:'2026-10-01',end:''}},doses:{},doseAudit:[]}};}
test('approved medication script can load before unified controller without accessing its globals',()=>{
 const c={document:{},window:{addEventListener(){}}};vm.createContext(c);
 vm.runInContext(fs.readFileSync(path.resolve(__dirname,'../static/medication-v121.js'),'utf8'),c);
 assert.equal(typeof c.window.MedicationV121.render,'function');
});
test('arrangements keep active IDs, boundaries, source data and explicit zero-record state',()=>{
 const s=fixture(),before=JSON.stringify(s),rows=M.arrangements(s,'2026-10-13');
 assert.deepEqual(rows.map(r=>[r.medId,r.time,r.status]),[['TEST-A','08:00','unrecorded'],['TEST-B','12:30','unrecorded'],['TEST-A','20:00','unrecorded']]);
 assert.equal(M.arrangements(s,'2026-09-30').length,0);assert.equal(M.arrangements(s,'2026-10-31').length,3);assert.equal(M.arrangements(s,'2026-11-01').length,1);
 assert.equal(JSON.stringify(s),before);
});
test('first unrecorded task is selected; skipped and taken are not silently reinterpreted',()=>{
 const s=fixture();s.dailyProduct.doses['TEST-A|2026-10-13|08:00']={status:'taken'};
 let rows=M.arrangements(s,'2026-10-13');assert.equal(M.initial(rows),1);
 s.dailyProduct.doses['TEST-B|2026-10-13|12:30']={status:'skipped'};
 rows=M.arrangements(s,'2026-10-13');assert.equal(M.initial(rows),2);assert.equal(rows[1].status,'skipped');
 assert.equal(M.initial([]),0);
});
test('gesture advances at most one, clamps endpoints and ignores vertical/subthreshold motion',()=>{
 assert.equal(M.step(1,-5000,0,12),2);assert.equal(M.step(1,5000,0,12),0);
 assert.equal(M.step(0,100,0,12),0);assert.equal(M.step(11,-100,0,12),11);
 assert.equal(M.step(5,-100,150,12),5);assert.equal(M.step(5,-34,0,12),5);assert.equal(M.step(0,-100,0,0),0);
});
test('different drugs at the same time stay distinct, including IDs with delimiter characters',()=>{
 const s=fixture();s.profile.profile.medicationRecords[1].id='TEST|B';s.dailyProduct.medSchedules['TEST|B']={times:['08:00'],start:'2026-10-01',end:''};
 const rows=M.arrangements(s,'2026-10-13');assert.equal(rows.length,3);assert.equal(new Set(rows.map(M.key)).size,3);
});
test('trackpad inertia stays in one gesture even after rendering the new selected card',()=>{
 const g={at:0,sum:0,moved:false};let i=2;
 for(const [dx,at] of [[12,1000],[30,1010],[120,1020],[150,1030]])i=M.wheelStep(g,i,dx,0,12,at);
 assert.equal(i,3);
 i=M.wheelStep(g,i,80,0,12,1400);assert.equal(i,4);
 i=M.wheelStep(g,i,100,200,12,1410);assert.equal(i,4);
});
test('changed schedules and stopped medicines cannot hide recorded history; original empty dose survives correction',()=>{
 const s=fixture(),r={medId:'TEST-A',date:'2026-10-12',time:'08:00',status:'unrecorded',medName:'TEST 当前名',dose:'TEST 当前说明',recordedAt:'2026-10-13T10:00:00Z'};
 s.profile.profile.medicationRecords[0].status='stopped';s.dailyProduct.medSchedules['TEST-A'].times=['09:00'];s.dailyProduct.doses[M.key(r)]=r;
 s.dailyProduct.doseAudit=[{at:r.recordedAt,record:r},{at:'2026-10-12T01:00:00Z',record:{...r,status:'taken',medName:'TEST 原登记名',dose:''}}];
 const before=JSON.stringify(s),records=M.records(s);
 assert.equal(records.length,1);assert.equal(records[0].medName,'TEST 原登记名');assert.equal(records[0].dose,'');assert.equal(records[0].status,'unrecorded');assert.equal(records[0].time,'08:00');
 assert.equal(JSON.stringify(s),before);assert.equal(M.arrangements(s,'2026-10-12').some(r=>r.medId==='TEST-A'),false);
});
test('history orders by planned date/time rather than backfill registration time',()=>{
 const s=fixture();for(const [date,time,recordedAt] of [['2026-10-10','20:00','2026-10-14'],['2026-10-13','20:00','2026-10-13'],['2026-10-13','08:00','2026-10-13']]){
  const r={medId:'TEST-A',date,time,status:'taken',medName:'TEST',dose:'',recordedAt};s.dailyProduct.doses[M.key(r)]=r;
 }
 assert.deepEqual(M.records(s).map(r=>[r.date,r.time]),[['2026-10-13','08:00'],['2026-10-13','20:00'],['2026-10-10','20:00']]);
});
test('without old audit data, history uses actual stored snapshot instead of current profile dose',()=>{
 const s=fixture(),r={medId:'TEST-A',date:'2026-10-13',time:'08:00',status:'taken',medName:'TEST 原记录',dose:'',recordedAt:'2026-10-13'};
 s.dailyProduct.doses[M.key(r)]=r;assert.equal(M.records(s)[0].medName,r.medName);assert.equal(M.records(s)[0].dose,'');
});
test('save-state verification uses authoritative values, no inferred success or zero filling',()=>{
 const s=fixture(),p={medId:'TEST-A',date:'2026-10-13',time:'08:00',status:'taken'};
 assert.equal(M.savedMatches(s,'dose',p),false);s.dailyProduct.doses[M.key(p)]={...p};assert.equal(M.savedMatches(s,'dose',p),true);
 assert.equal(M.savedMatches(s,'dose',{...p,status:'skipped'}),false);
 assert.equal(M.savedMatches(s,'medSchedule',{medId:'TEST-A',times:['20:00','08:00','08:00'],start:'2026-10-01',end:'2026-10-31'}),true);
 assert.equal(M.savedMatches(s,'medSchedule',{medId:'TEST-A',times:['08:00'],start:'2026-10-01',end:'2026-10-31'}),false);
 assert.equal(M.savedMatches(s,'medication.status',{id:'TEST-stopped',status:'stopped'}),true);
});
test('date validation preserves real calendar validity and leap years',()=>{
 for(const d of ['2026-10-13','2024-02-29','2026-12-31'])assert.equal(M.validDate(d),true,d);
 for(const d of ['2026-02-29','2026-13-01','2026-10-32','2026-1-1','0000-01-01','',null])assert.equal(M.validDate(d),false,String(d));
});
test('AI questions add no drug identity, dose or full medication history and request no prescription',()=>{
 assert.match(M.question('drug'),/不.*处方|不给出处方/);assert.doesNotMatch(M.question('drug'),/TEST|mg|1片|病历|示例/);
 assert.match(M.question('home'),/未记录/);
});
