'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const family=require('../static/family-v10.js');
test('shared member projection excludes unauthorized payload even if present',()=>{
 const m=family.members({familyMembers:[{ownerId:'B',name:'家人',categories:['medication','all'],health:[{text:'PRIVATE'}],rehab:[{text:'PRIVATE'}],doses:[{medName:'TEST',date:'2026-10-14',time:'08:00',status:'taken'}]}],dailyProduct:{grants:{B:['health']}}})[0];
 assert.deepEqual(m.received,['medication']);assert.deepEqual(m.offered,['health']);assert.deepEqual(m.health,[]);assert.deepEqual(m.rehab,[]);assert.equal(m.doses[0].text,'TEST · 已服用');
});
test('explicit health access keeps 0 values and translates only known metric keys',()=>{
 const m=family.members({familyMembers:[{ownerId:'B',categories:['health'],health:[{text:'weight: 0 kg',timestamp:'2026-10-14T00:00:00Z'},{text:'some observation',timestamp:''}]}]})[0];assert.equal(m.health[0].text,'体重: 0 kg');assert.equal(m.health[1].text,'some observation');assert.equal(m.health[1].time,'时间未记录');
});
test('legacy report hash is decoded and malformed/oversized tokens remain report errors',()=>{
 assert.equal(family.reportCode('#home'),null);assert.equal(family.reportCode('#family/reportOpen'),null);assert.equal(family.reportCode('#care=abc%2D123'),'abc-123');assert.equal(family.reportCode('#care=%GG'),'');assert.equal(family.reportCode('#care='+'a'.repeat(101)),'');
});
test('contact changes preserve existing clinical fields and empty optional fields',()=>{
 const p={name:'TEST',age:60,conditions:['原字段'],medicationRecords:[{id:'existing'}],consent:true,elderPhone:'kept'};
 const next=family.contactPayload(p,{name:'',phone:'',doctor:'TEST'});assert.deepEqual(next.medicationRecords,p.medicationRecords);assert.deepEqual(next.conditions,p.conditions);assert.equal(next.elderPhone,'kept');assert.equal(next.familyPhone,'');assert.equal(next.communityDoctorPhone,'TEST');assert.equal(p.familyContact,undefined);
});
test('AI starter has no person, report value or automatic prescription',()=>{
 for(const origin of ['home','concept'])assert(!/TEST|60|血糖|姓名/.test(family.question(origin)));assert.match(family.question('concept'),/不作诊断/);
});
test('production family reference contains no executable inline/demo handlers or inline styles',()=>{
 const src=fs.readFileSync(path.join(__dirname,'../static/family-v10.js'),'utf8');assert(!/<[^>]*\s(?:onclick|oninput|onchange|style)=/.test(src));assert(!/seedMember|A1B2C3D4|D4C3B2A1|setScenario|本地演示|原型演示/.test(src));assert(!/\beval\(|new Function/.test(src));
});
function uiFixture(){
 const vm=require('node:vm'),nodes=new Map(),content={innerHTML:'',querySelectorAll(selector){if(selector==='[data-fv-call]'){if(this.cachedHtml!==this.innerHTML){this.cachedHtml=this.innerHTML;this.actions=[...this.innerHTML.matchAll(/data-fv-call="([^"]*)"/g)].map(m=>({getAttribute:()=>m[1]}));}return this.actions;}return [];}};
 const generic={focus(){},scrollTop:0,hidden:false,querySelector(){return null;},querySelectorAll(){return[];}};nodes.set('#content',content);
 const c={document:{body:{dataset:{}}},window:{addEventListener(){}},location:{hash:'#family/permission'},history:{},ui:{page:'family',homeConnection:'ready',familyReadAt:1,snapshot:{profile:{ownerId:'A',dataMode:'TEST',profile:{}},familyMembers:[{ownerId:'B',name:'家人B',categories:['health']}],dailyProduct:{grants:{B:['medication']}}}},$:s=>nodes.get(s)||generic,snapshot(){return c.ui.snapshot;},voiceStarting:false,recorder:null,route(){},say(){},api(){throw Error('unexpected API');}};
 vm.createContext(c);vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/family-v10.js'),'utf8'),c);return {c,content,f:c.window.FamilyV10};
}
test('browser adapter loads before unified globals are initialized',()=>{
 const vm=require('node:vm'),c={document:{},window:{addEventListener(){}}};vm.createContext(c);vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/family-v10.js'),'utf8'),c);assert.equal(typeof c.window.FamilyV10.render,'function');
});
test('permission reload restores authoritative grants; unfinished edits survive revalidation',()=>{
 const {c,content,f}=uiFixture();f.render();assert.match(content.innerHTML,/aria-label="用药记录" aria-checked="true"/);
 c.ui.homeConnection='loading';f.beforeLoad();assert(!content.innerHTML.includes('家人B'));
 c.ui.homeConnection='ready';f.render();assert.match(content.innerHTML,/aria-label="用药记录" aria-checked="true"/);
 content.actions.find(n=>n.getAttribute()==="F.toggle('health')").onclick();assert.match(content.innerHTML,/有未保存的更改/);assert.match(content.innerHTML,/aria-label="健康近况" aria-checked="true"/);
 c.ui.homeConnection='loading';f.beforeLoad();c.ui.homeConnection='ready';f.render();assert.match(content.innerHTML,/有未保存的更改/);assert.match(content.innerHTML,/aria-label="健康近况" aria-checked="true"/);
});
test('owner switch clears member privacy summaries, permission edits and contact drafts',()=>{
 const {c,content,f}=uiFixture();f.render();content.actions.find(n=>n.getAttribute()==="F.toggle('health')").onclick();
 c.ui.snapshot={profile:{ownerId:'C',dataMode:'TEST',profile:{}},familyMembers:[],dailyProduct:{grants:{}}};f.render();assert(!content.innerHTML.includes('家人B'));assert(!content.innerHTML.includes('有未保存的更改'));assert(!content.innerHTML.includes('保存权限'));
});
test('report management reads the real array contract and keeps unverified notes',async()=>{
 const {c,content,f}=uiFixture();c.location.hash='#family/reports';c.api=async()=>[{id:'TEST-share',expires:10000000000,active:true,notes:[{author:'TEST',text:'真实接口形状'}]}];f.render();await new Promise(setImmediate);f.render();assert.match(content.innerHTML,/1 份/);assert.match(content.innerHTML,/1 条留言/);assert.match(content.innerHTML,/真实接口形状/);assert(!content.innerHTML.includes('[object Object]'));
});
test('guest report route renders only capability payload, never the paired owner snapshot',async()=>{
 const {c,content,f}=uiFixture();c.location.hash='#care=TEST-code';c.ui.snapshot.profile.profile.name='PRIVATE OWNER';c.api=async()=>({report:{health:{measurements:[{metric:'weight',value:0,unit:'kg',timestamp:''}],medications:[]},records:[]},notes:[]});
 // Use the public rendering path; it observes the legacy capability URL.
 c.nav=()=>{};f.render();await new Promise(setImmediate);f.render();assert.match(content.innerHTML,/体重: 0 kg/);assert(!content.innerHTML.includes('PRIVATE OWNER'));assert(!content.innerHTML.includes('家人B'));
});
test('fresh connection hides cached members and clears a resolved read failure',()=>{
 const {c,content,f}=uiFixture();f.render();c.ui.homeConnection='offline';c.ui.snapshot=null;f.failure('TEST disconnected');assert(!content.innerHTML.includes('家人B'));assert.match(content.innerHTML,/TEST disconnected/);
 c.ui.homeConnection='ready';c.ui.snapshot={profile:{ownerId:'A',dataMode:'TEST',profile:{}},familyMembers:[],dailyProduct:{}};f.render();assert(!content.innerHTML.includes('TEST disconnected'));assert(!content.innerHTML.includes('家人B'));
});
test('contact edit direct navigation initializes saved own fields without clearing them',()=>{
 const {c,content,f}=uiFixture();c.location.hash='#family/contactEdit';c.ui.snapshot.profile.profile={familyContact:'TEST saved',familyPhone:'TEST-field',communityDoctorPhone:''};f.render();assert.match(content.innerHTML,/value="TEST saved"/);assert.match(content.innerHTML,/value="TEST-field"/);assert(!content.innerHTML.includes('undefined'));
});
