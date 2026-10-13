const {test}=require('node:test');
const assert=require('node:assert/strict');
const {Store,validateBackup}=require('../web/store.js');
function backup(){
 const map=new Map(),storage={getItem:k=>map.get(k)||null,setItem:(k,v)=>map.set(k,v)};
 const s=new Store(storage);s.write('profile:'+s.value.owner,{profile:{name:'TEST',age:30,conditions:[],medicationRecords:[]}});
 return {kind:'ankang-phone-backup',version:2,data:s.value};
}
test('current backup preserves owner and strips stale grants without changing source',()=>{
 const b=backup();b.data.daily.grants.other=['health'];const before=JSON.stringify(b);
 const v=validateBackup(b);assert.equal(v.owner,b.data.owner);assert.deepEqual(v.daily.grants,{});assert.equal(JSON.stringify(b),before);
});
test('malformed current backup and foreign measurement contract are rejected',()=>{
 const b=backup();b.data.jobs='invalid';assert.throws(()=>validateBackup(b));
 const c=backup();c.data.jobs=[{id:crypto.randomUUID(),mode:'assessment',state:'done',side:'left',created_at:new Date().toISOString(),measurement_version:'desktop-yolo',result:{summary:{},local_report:{contract:'desktop-yolo'}}}];assert.throws(()=>validateBackup(c));
});
test('current backup preserves measured assessment and its bound plan; missing assessment fails',()=>{
 const b=backup(),id=crypto.randomUUID();
 b.data.jobs=[{id,mode:'assessment',state:'done',side:'left',created_at:new Date().toISOString(),measurement_version:'android-local-projection-1',result:{summary:{completed:2},local_report:{contract:'android-local-projection-1'}}}];
 b.data.plans=[{id:crypto.randomUUID(),revision:1,items:[{key:crypto.randomUUID(),side:'left',assessment_id:id,settings:{target_reps:2}}]}];
 const v=validateBackup(b);assert.equal(v.plans[0].items[0].assessment_id,id);assert.equal(v.jobs[0].result.summary.completed,2);
 b.data.plans[0].items[0].assessment_id=crypto.randomUUID();assert.throws(()=>validateBackup(b));
});
