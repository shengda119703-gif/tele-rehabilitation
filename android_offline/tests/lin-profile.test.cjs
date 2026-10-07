const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const asset=name=>fs.readFileSync('android_offline/build/assets/'+name,'utf8');
const original=()=>JSON.parse(asset('lin-profile.json'));
function memory(){const map=new Map();return{getItem:k=>map.get(k)??null,setItem:(k,v)=>map.set(k,String(v)),removeItem:k=>map.delete(k)};}
function context(storage=memory()){
 const c={crypto:globalThis.crypto,structuredClone,Date,console,Blob,File,URL,Headers,Response,TextDecoder,TextEncoder,Uint8Array,setTimeout,clearTimeout,localStorage:storage,
  location:{origin:'https://appassets.androidplatform.net',href:'/'},document:{addEventListener(){}},Element:class{},MutationObserver:class{},XMLHttpRequest:class{},alert:()=>{},confirm:()=>true};
 c.fetch=async url=>new Response(asset(new URL(url,c.location.origin).pathname.slice(1)),{headers:{'Content-Type':'application/json'}});
 vm.createContext(c);
 for(const name of ['product.js','store.js','lin-profile.js','engine.js'])vm.runInContext(fs.readFileSync('android_offline/build/assets/local/'+name,'utf8'),c);
 const files=new Map();c.PhoneStore.files.get=async id=>files.get(id);c.PhoneStore.files.all=async()=>[...files.values()];c.PhoneStore.files.put=async(id,v)=>files.set(id,v);c.PhoneStore.files.remove=async id=>files.delete(id);
 c.PhoneMotion={active:false,errors:new Map(),catalog:async()=>JSON.parse(asset('catalog.json')),pause(){}};
 return{c,storage,files};
}
async function local(storage){const h=context(storage);vm.runInContext(fs.readFileSync('android_offline/web/cloud.js','utf8'),h.c);vm.runInContext(fs.readFileSync('android_offline/web/local-api.js','utf8'),h.c);await h.c.PhoneLocal.ready;return h;}
const plain=v=>JSON.parse(JSON.stringify(v));
test('portable TEST asset contains only generated owner-scoped records and preserves original reports',()=>{
 const {c}=context(),p=original(),v=c.PhoneLin.validate(p);
 assert.equal(v.jobs.length,24);assert.equal(v.plans[0].items.length,4);
 assert.deepEqual(plain(v.jobs.reduce((a,j)=>(a[j.mode]=(a[j.mode]||0)+1,a),{})),{assessment:18,fitness:2,posture:2,training:2});
 assert(v.jobs.every(j=>j.synthetic&&j.fixture==='test-lin-profile-v1'&&!j.video_available&&j.result.local_report.origin==='desktop-TEST-fixture'));
 const fitness=v.jobs.filter(j=>j.mode==='fitness');assert.deepEqual(fitness.map(j=>j.result.summary.completed).sort(),[6,8]);
 assert(fitness.every(j=>j.result.barbell.calibration.mass_kg===20));
 assert(!JSON.stringify(v).includes('shared_database'));assert(!JSON.stringify(p).includes('E:\\'));
 assert(!Object.keys(v.kv).some(k=>k.startsWith('attachments:')));
});
test('fresh install selects Lin; legacy/existing personal account and explicit selection keep their namespace',()=>{
 const {c,storage}=context(),PS=c.PhoneStore;
 assert.equal(PS.selectedKey(storage),PS.LIN_KEY);
 storage.setItem('rehab-offline-state-1','{}');assert.equal(PS.selectedKey(storage),PS.KEY);
 storage.setItem(PS.ACTIVE_KEY,PS.LIN_KEY);assert.equal(PS.selectedKey(storage),PS.LIN_KEY);
 storage.setItem(PS.ACTIVE_KEY,'../../other');assert.equal(PS.selectedKey(storage),PS.KEY);
});
test('first import is idempotent, preserves user edits and leaves personal state/attachments untouched',async()=>{
 const {c,storage,files}=context(),PS=c.PhoneStore;
 const personal=new PS.Store(storage);personal.write('profile:'+personal.value.owner,{profile:{name:'本人',age:31,conditions:[]},dataMode:'real'});
 const before=storage.getItem(PS.KEY);files.set('personal-archive',{ownerId:personal.value.owner,kind:'archive',dataMode:'real',bytes:new Uint8Array([1,2])});
 const lin=new PS.Store(storage,PS.LIN_KEY);assert.equal(await c.PhoneLin.initialize(lin,c.fetch),true);
 lin.change(v=>v.daily.ownNote='本次打开之后新增');const after=storage.getItem(PS.LIN_KEY);
 assert.equal(await c.PhoneLin.initialize(lin,()=>{throw Error('should not refetch')}),false);
 assert.equal(storage.getItem(PS.LIN_KEY),after);assert.equal(storage.getItem(PS.KEY),before);assert.equal(files.size,4);
 assert.equal(files.get('personal-archive').bytes[1],2);
});
test('conflicting namespace or attachment never overwrites another account',async()=>{
 const {c,storage,files}=context(),PS=c.PhoneStore;
 const lin=new PS.Store(storage,PS.LIN_KEY),p=original();files.set(p.attachments[0].id,{ownerId:crypto.randomUUID(),kind:'archive',dataMode:'real'});
 await assert.rejects(()=>c.PhoneLin.initialize(lin,c.fetch),/编号已占用/);assert.equal(storage.getItem(PS.LIN_KEY),null);
 lin.write('profile:'+lin.value.owner,{dataMode:'real',profile:{name:'本人'}});const before=storage.getItem(PS.LIN_KEY);
 await assert.rejects(()=>c.PhoneLin.initialize(lin,c.fetch),/已有其他档案/);assert.equal(storage.getItem(PS.LIN_KEY),before);
});
test('first-open dates shift consistently to supplied time and do not pre-fill future doses',()=>{
 const {c}=context(),p=original(),at=new Date('2031-04-15T10:00:00+08:00'),shifted=c.PhoneLin.rebase(p,at);
 assert.equal(shifted.data.fixture.importedAt,at.toISOString());assert.equal(shifted.data.fixture.originalAnchor,p.data.fixture.anchor);
 assert.equal(new Date(shifted.data.jobs[0].created_at)-new Date(p.data.jobs[0].created_at),at-new Date(p.data.fixture.anchor));
 assert(Object.values(shifted.data.daily.doses).every(d=>new Date(d.date+'T'+d.time+':00')<=at));
 assert(Object.entries(shifted.data.daily.doses).every(([key,d])=>key.includes('|'+d.date+'|')));
 assert.equal(c.PhoneLin.validate(shifted).jobs.length,24);
});
test('backup accepts only the named fixture family, refuses foreign owners/contracts and leaves real grants cleared',()=>{
 const {c}=context(),p=original();assert(c.PhoneStore.validateBackup({kind:'ankang-phone-backup',version:2,data:p.data}).fixture.synthetic);
 p.data.kv['health:real:'+crypto.randomUUID()]={};assert.throws(()=>c.PhoneLin.validate(p));
 const wrong=original();wrong.data.jobs[0].measurement_version='desktop-yolo';assert.throws(()=>c.PhoneLin.validate(wrong));
 const identity=original();identity.data.kv['profile:'+identity.data.fixture.members[0]].dataMode='real';assert.throws(()=>c.PhoneLin.validate(identity));
});
test('original ProductService loads all major areas; native plan is linked to two completed training records',async()=>{
 const {c}=await local(),s=await c.PhoneLocal.snapshot();
 assert.equal(s.profile.profile.name,'TEST 林女士');assert.equal(s.state.events.filter(e=>e.measurement).length,140);
 assert.equal(s.profile.profile.medicationRecords.length,3);assert.equal(s.attachments.length,3);assert(s.state.chat.length>=8);
 assert(s.history.report.sections.length>=3);assert.equal(s.familyMembers[0].name,'TEST 林晓');
 const plan=await c.PhoneLocal.request('/api/plan');assert.equal(plan.progress.completed,2);assert.equal(plan.progress.total,4);assert.equal(plan.plan.items.find(i=>i.key===plan.progress.next_key).exercise_id,'shoulder_flexion');
 const body=await c.PhoneLocal.body();assert.equal(body.total,24);assert.equal(body.training_count,2);
 const archive=await c.PhoneLocal.domain.request('archive.read',c.PhoneLocal.store.value.owner,{id:s.attachments[0].id},new Date());assert(archive.bytes.length>0);
});
test('attachment writes use imported owner rather than the pre-import placeholder',async()=>{
 const {c}=await local(),L=c.PhoneLocal,owner=L.store.value.owner;
 await L.domain.request('archive.save',owner,{name:'本机新增资料',category:'其他资料',fileName:'new.txt',mediaType:'text/plain',visibility:'private',bytes:[65,66]},new Date());
 const saved=(await L.snapshot()).attachments.find(a=>a.name==='本机新增资料');assert(saved);
 await L.domain.request('archive.trash',owner,{id:saved.id},new Date());assert(!(await L.snapshot()).attachments.some(a=>a.id===saved.id));
 await L.domain.request('archive.restore',owner,{id:saved.id},new Date());assert((await L.snapshot()).attachments.some(a=>a.id===saved.id));
});
test('Lin family permissions and backup are local only; existing personal cloud credentials are not used/disconnected',async()=>{
 const {c}=await local(),L=c.PhoneLocal;let calls=0,disconnects=0;c.OfflineAndroid={cloudConfigured:()=>true,cloudRequest:()=>calls++,cloudDisconnect:()=>disconnects++};
 assert.equal(c.PhoneCloud.configured(),false);await assert.rejects(()=>c.PhoneCloud.request('/v1/family'));
 const member=L.store.value.fixture.members[0];c.PhoneLin.familyOperation(L.store,'familyGrant',{member,categories:['health','rehab']});
 const backup=await L.backup();assert.equal(c.PhoneStore.validateBackup(backup).daily.grants[member].length,2);
 await L.restore(JSON.stringify(backup));assert.equal(L.store.value.daily.grants[member].length,2);assert.equal(disconnects,0);assert.equal(calls,0);
 await assert.rejects(()=>L.request('/api/unified/daily.familyInvite',{method:'POST',body:'{}'}),/两台手机/);
});
test('profile switching persists only the selection, rejects active analysis and does not reseed either store',async()=>{
 const {c,storage}=await local(),L=c.PhoneLocal,before=storage.getItem(c.PhoneStore.LIN_KEY);
 c.PhoneMotion.active=true;await assert.rejects(()=>L.selectProfile(c.PhoneStore.KEY),/结束/);
 c.PhoneMotion.active=false;await L.selectProfile(c.PhoneStore.KEY);assert.equal(storage.getItem(c.PhoneStore.ACTIVE_KEY),c.PhoneStore.KEY);assert.equal(storage.getItem(c.PhoneStore.LIN_KEY),before);
 assert.equal(storage.getItem(c.PhoneStore.KEY),null);assert.equal(c.location.href,'/');
});
