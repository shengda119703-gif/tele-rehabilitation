'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(__dirname+'/browser-account.js','utf8');
const patient='11111111-1111-4111-8111-111111111111',account='22222222-2222-4222-8222-222222222222';
function fixture(){
 const memory=new Map(),listeners={},calls=[],redirects=[];
 const identity={patient_id:patient,account_id:account,username:'alice',role:'PATIENT'};
 const storage={getItem:k=>memory.get(k)||null,setItem:(k,v)=>memory.set(k,v)};
 let current={...identity,csrf_token:'memory-only'};
 class Store{constructor(s,k){this.value=JSON.parse(s.getItem(k)||JSON.stringify({owner:patient}));this.change=fn=>{fn(this.value);s.setItem(k,JSON.stringify(this.value));};}}
 const context={PhoneStore:{CLOUD_PREFIX:'cloud:',ACTIVE_KEY:'active',Store,cloudKey:k=>k==='cloud:'+patient},localStorage:storage,
  document:{getElementById:()=>({textContent:JSON.stringify(identity)})},location:{origin:'https://139.224.216.18',replace:u=>redirects.push(u),assign:u=>redirects.push(u)},
  fetch:async(url,options)=>{calls.push({url,options});return{ok:true,status:200,json:async()=>url.endsWith('/auth/me')?structuredClone(current):{items:[],status:'COMMITTED'}};},
  addEventListener:(name,fn)=>listeners[name]=fn,structuredClone,AbortSignal,alert:()=>{}};
 vm.runInNewContext(source,context);
 return {context,memory,calls,listeners,redirects,identity,setCurrent:v=>current=v};
}
test('browser identity is per-patient and credentials never persist in local storage',async()=>{
 const f=fixture();await f.context.AnkangBrowserAccount.ready;
 const state=[...f.memory.values()].join('');assert(state.includes(patient));assert(!state.includes('memory-only'));assert(!state.includes('access_token'));
 await f.context.AnkangBrowserAccount.request('append',f.identity,{document:{operation_id:'one'}});
 const call=f.calls.at(-1);assert(call.url.includes('/patients/'+patient+'/record-events'));assert.equal(call.options.credentials,'same-origin');
 assert.equal(call.options.headers['X-CSRF-Token'],'memory-only');assert(!call.options.headers.Authorization);
});
test('wrong patient and same-browser account switch refuse cloud writes',async()=>{
 const f=fixture();await f.context.AnkangBrowserAccount.ready;
 await assert.rejects(f.context.AnkangBrowserAccount.request('append',{...f.identity,patient_id:account},{}));
 f.setCurrent({...f.identity,patient_id:account,csrf_token:'new'});
 await assert.rejects(f.context.AnkangBrowserAccount.request('append',f.identity,{}));
 assert(!f.calls.some(c=>c.url.endsWith('/record-events')));assert.equal(f.redirects[0],'/account?next=/');
});
test('other tab selecting another account invalidates this tab immediately',async()=>{
 const f=fixture();await f.context.AnkangBrowserAccount.ready;
 f.listeners.storage({key:'active',newValue:'cloud:'+account});
 assert.throws(()=>f.context.AnkangBrowserAccount.assertScope());assert.equal(f.redirects[0],'/account?next=/');
});
