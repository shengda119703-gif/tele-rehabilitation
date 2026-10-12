const {test}=require('node:test'),assert=require('node:assert/strict');
global.crypto=require('node:crypto').webcrypto;
const PS=require('../web/store.js');global.PhoneStore=PS;
let current;global.OfflineAndroid={accountIdentity:()=>JSON.stringify(current)};
const Account=require('../web/account.js');
function memory(){const m=new Map();return{getItem:k=>m.get(k)||null,setItem:(k,v)=>m.set(k,v),removeItem:k=>m.delete(k)};}
function identity(){return{patient_id:crypto.randomUUID(),account_id:crypto.randomUUID(),username:'owner',role:'PATIENT',origin:Account.ORIGIN};}
function job(){return{id:crypto.randomUUID(),state:'done',mode:'assessment',exercise:'shoulder_abduction',side:'left',created_at:new Date().toISOString(),measurement_version:'android-local-projection-1',result:{local_report:{synthetic:false},summary:{completed:3,min:null},limitations:['二维投影'],series:[[1,2]]}};}
test('cloud namespaces isolate original, fixture and other users',()=>{
 const s=memory(),one=identity(),two=identity();
 const a=new PS.Store(s,PS.CLOUD_PREFIX+one.patient_id),b=new PS.Store(s,PS.CLOUD_PREFIX+two.patient_id);
 a.change(v=>v.jobs.push(job()));assert.equal(b.value.jobs.length,0);
 assert.equal(a.value.owner,one.patient_id);s.setItem(PS.ACTIVE_KEY,a.key);assert.equal(PS.selectedKey(s),a.key);
 assert.throws(()=>new PS.Store(s,PS.CLOUD_PREFIX+'../bad'));
 s.setItem(b.key,JSON.stringify(a.value));assert.throws(()=>new PS.Store(s,b.key));
 current=one;assert.throws(()=>Account.scope(new PS.Store(s,PS.LIN_KEY)));assert.throws(()=>Account.scope(new PS.Store(s,PS.KEY)));
});
test('stable outbox and lost ack retry preserve one server record',async()=>{
 current=identity();const store=new PS.Store(memory(),PS.CLOUD_PREFIX+current.patient_id);store.change(v=>v.jobs.push(job()));
 await Account.queue(store);const document=structuredClone(store.value.cloudOutbox.items[0].document);await Account.queue(store);
 assert.equal(store.value.cloudOutbox.items.length,1);let drop=true;const remote=new Map();
 assert.deepEqual(new PS.Store(store.storage,store.key).value.cloudOutbox.items[0].document,document);
 OfflineAndroid.accountRequest=(id,action,text)=>{const value=JSON.parse(text);assert.equal(value.patient_id,current.patient_id);
  if(!remote.has(value.document.operation_id))remote.set(value.document.operation_id,crypto.randomUUID());
  const result=drop?{message:'回复丢失'}:{status:'COMMITTED',resource_id:remote.get(value.document.operation_id)};queueMicrotask(()=>Account.reply(id,drop?503:201,JSON.stringify(result)));drop=false;
 };
 // Capture status before the asynchronous callback; simulate a committed write with no ACK.
 let first=true;OfflineAndroid.accountRequest=(id,action,text)=>{const value=JSON.parse(text);assert.equal(value.patient_id,current.patient_id);
  if(!remote.has(value.document.operation_id))remote.set(value.document.operation_id,crypto.randomUUID());
  const status=first?503:201,result=first?{message:'回复丢失'}:{status:'COMMITTED',resource_id:remote.get(value.document.operation_id)};first=false;queueMicrotask(()=>Account.reply(id,status,JSON.stringify(result)));
 };
 await assert.rejects(()=>Account.sync(store),/回复丢失/);assert.equal(store.value.cloudOutbox.items[0].resource_id,null);
 assert.equal((await Account.sync(store)).uploaded,1);assert.equal((await Account.sync(store)).uploaded,0);
 assert.equal(remote.size,1);assert.deepEqual(store.value.cloudOutbox.items[0].document,document);
 assert.equal(document.payload.result.summary.min,null);assert.equal(document.payload.result.series,undefined);
});
test('switch account cannot upload previous queue; credentials excluded from backups',async()=>{
 current=identity();const store=new PS.Store(memory(),PS.CLOUD_PREFIX+current.patient_id);store.change(v=>v.jobs.push(job()));await Account.queue(store);
 current=identity();await assert.rejects(()=>Account.sync(store),/当前云账号/);
 store.change(v=>v.cloudIdentity=current);const backup=PS.backupData(store.value);assert.equal(backup.cloudOutbox,undefined);assert.equal(backup.cloudIdentity,undefined);
});
test('only actual completed analysis jobs enter queue; no fixture relabeling',async()=>{
 current=identity();const store=new PS.Store(memory(),PS.CLOUD_PREFIX+current.patient_id),real=job(),synthetic=job(),failed=job();synthetic.result.local_report.synthetic=true;failed.state='failed';
 store.change(v=>v.jobs.push(real,synthetic,failed));await Account.queue(store);assert.equal(store.value.cloudOutbox.items.length,1);
 assert.equal(store.value.cloudOutbox.items[0].document.payload.source,'REPLAY_FILE');
 store.change(v=>v.cloudOutbox.version=9);await assert.rejects(()=>Account.queue(store),/未覆盖/);assert.equal(store.value.cloudOutbox.version,9);
});
