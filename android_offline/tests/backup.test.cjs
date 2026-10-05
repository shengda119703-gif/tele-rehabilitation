const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const app=fs.readFileSync(path.join(__dirname,'../web/app.js'),'utf8');
const helper=app.slice(app.indexOf('function validateBackup'),app.indexOf('function healthPage'));
const ctx={E:require('../web/engine.js'),getSpec:id=>id==='shoulder_abduction'?{}:null};vm.createContext(ctx);vm.runInContext(helper,ctx);
function backup(){return {type:'rehab-offline-backup',version:1,data:{version:1,profile:{name:'本人',restrictions:''},records:[],plan:null,health:[],medicines:[],notes:[],archive:[]}};}
test('empty valid backup accepts only known state fields and excludes attachments',()=>{const b=backup();b.data.unknown='discard';b.data.archive=[{id:'attachment'}];const d=ctx.validateBackup(b);assert.equal(d.unknown,undefined);assert.equal(d.archive.length,0);});
test('malformed arrays, unsafe IDs and unsupported measurement contracts cannot overwrite storage',()=>{
 const b=backup();b.data.medicines='bad';assert.throws(()=>ctx.validateBackup(b),/未修改/);
 const c=backup();c.data.medicines=[{id:'" onclick="evil()',name:'x',dose:'x',active:true}];assert.throws(()=>ctx.validateBackup(c),/有效备份/);
 const r=backup();r.data.records=[{id:'r',exercise:'shoulder_abduction',side:'left',kind:'assessment',created:1,report:{contract:'desktop'}}];assert.throws(()=>ctx.validateBackup(r),/有效备份/);
});
test('restore roundtrip keeps genuine assessment and bound plan',()=>{
 const b=backup(),report=ctx.E.analyzeReplay({id:'shoulder_abduction',target_direction:'increase'},'left',Array(12).fill(0).map((v,i)=>[i*.12,v]));
 b.data.records=[{id:'r',exercise:'shoulder_abduction',side:'left',kind:'assessment',created:1,report}];
 b.data.plan={id:'p',created:2,contract:ctx.E.VERSION,items:[{exercise:'shoulder_abduction',side:'left',assessment:'r',reps:1,sets:1,target:null,complete:false,source:{title:'本人活动'}}]};assert.equal(ctx.validateBackup(b).plan.items[0].assessment,'r');b.data.plan.items[0].assessment='missing';assert.throws(()=>ctx.validateBackup(b));
});
test('optional plan adjustment only reduces observed dose and never mutates recommendation',()=>{
 vm.runInContext(app.slice(app.indexOf('function reducedPlan'),app.indexOf('function exportJson')),ctx);
 const items=[{reps:3,exercise:'shoulder_abduction'}];assert.equal(ctx.reducedPlan(items,()=>1)[0].reps,1);assert.equal(items[0].reps,3);for(const v of [0,4,1.5,NaN])assert.throws(()=>ctx.reducedPlan(items,()=>v));
});
