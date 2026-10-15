const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
async function local(personal=true,native=true){
 const values=new Map(),bindings=[],reads=[];
 const storage={getItem:k=>values.get(k)??null,setItem:(k,v)=>values.set(k,String(v)),removeItem:k=>values.delete(k)};
 const c={crypto:globalThis.crypto,structuredClone,Date,console,Blob,File,URL,Headers,Response,TextDecoder,TextEncoder,Uint8Array,setTimeout,clearTimeout,localStorage:storage,
  location:{origin:'https://appassets.androidplatform.net',href:'/'},document:{addEventListener(){}},Element:class{},MutationObserver:class{},XMLHttpRequest:class{},alert:()=>{},confirm:()=>true};
 c.fetch=async url=>{const name=new URL(url,c.location.origin).pathname.slice(1);return new Response(fs.readFileSync(name==='lin-profile.json'&&process.env.ANKANG_TEST_PROFILE_FIXTURE?process.env.ANKANG_TEST_PROFILE_FIXTURE:'android_offline/build/assets/'+name),{headers:{'Content-Type':'application/json'}});};
 vm.createContext(c);
 for(const name of ['product.js','store.js','lin-profile.js','engine.js','practice.js'])vm.runInContext(fs.readFileSync('android_offline/build/assets/local/'+name,'utf8'),c);
 storage.setItem(c.PhoneStore.ACTIVE_KEY,personal?c.PhoneStore.KEY:c.PhoneStore.LIN_KEY);
 const files=new Map();c.PhoneStore.files.get=async id=>files.get(id);c.PhoneStore.files.all=async()=>[...files.values()];c.PhoneStore.files.put=async(id,v)=>files.set(id,v);
 c.PhoneMotion={active:false,errors:new Map(),catalog:async()=>JSON.parse(fs.readFileSync('android_offline/build/assets/catalog.json')),pause(){}};
 if(native)c.OfflineAndroid={motionBind:(owner,personal)=>bindings.push({owner,personal}),motionRead:owner=>{reads.push(owner);return JSON.stringify({available:true,current:{recording:false},today:{heart_mean:null},records:[]});}};
 for(const name of ['cloud.js','local-api.js'])vm.runInContext(fs.readFileSync('android_offline/web/'+name,'utf8'),c);
 await c.PhoneLocal.ready;return{c,bindings,reads};
}
test('native collection binds actual personal owner after initialization, not placeholder/test owner',async()=>{
 const {c,bindings}=await local();assert.deepEqual(bindings,[{owner:c.PhoneLocal.store.value.owner,personal:true}]);
 const fixture=await local(false);assert.equal(fixture.bindings.at(0).personal,false);assert.equal(fixture.bindings.at(0).owner,fixture.c.PhoneLocal.store.value.owner);
});
test('read-only motion route preserves clinical, medicine and training records',async()=>{
 const {c,reads}=await local();const before=JSON.stringify(c.PhoneLocal.store.value),reply=await c.PhoneLocal.request('/api/device-motion');
 assert.equal(reply.available,true);assert.equal(reply.today.heart_mean,null);assert.deepEqual(reads,[c.PhoneLocal.store.value.owner]);assert.equal(JSON.stringify(c.PhoneLocal.store.value),before);
 await assert.rejects(()=>c.PhoneLocal.request('/api/device-motion?owner=other'),/当前手机档案/);
 await assert.rejects(()=>c.PhoneLocal.request('https://other.test/api/device-motion'),/当前手机档案/);
});
test('existing browser mode without Android bridge remains usable and does not invent heart data',async()=>{
 const {c}=await local(true,false);assert.equal((await c.PhoneLocal.request('/api/device-motion')).available,false);assert.equal((await c.PhoneLocal.snapshot()).profile.profile.name,'本机用户');
});
test('profile switching explicitly invalidates recording before navigation; active analysis still refuses switch',async()=>{
 const {c,bindings}=await local();c.PhoneMotion.active=true;await assert.rejects(()=>c.PhoneLocal.selectProfile(c.PhoneStore.LIN_KEY),/先结束/);assert.equal(bindings.length,1);
 c.PhoneMotion.active=false;await assert.rejects(()=>c.PhoneLocal.selectProfile('other'),/无效/);assert.equal(bindings.length,1);
 await c.PhoneLocal.selectProfile(c.PhoneStore.LIN_KEY);assert.deepEqual(bindings.at(-1),{owner:'',personal:false});assert.equal(c.localStorage.getItem(c.PhoneStore.ACTIVE_KEY),c.PhoneStore.LIN_KEY);
});
test('backup restore invalidates native owner and never includes native location or heart samples',async()=>{
 const {c,bindings}=await local();const data=await c.PhoneLocal.backup();assert(!JSON.stringify(data).includes('PHONE_SENSORS_BLE_HRS'));await c.PhoneLocal.restore(JSON.stringify(data));assert.deepEqual(bindings.at(-1),{owner:'',personal:false});
});
