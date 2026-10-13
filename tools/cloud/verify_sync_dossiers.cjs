'use strict';
// Read-only actual public UI/API checks. No TLS bypass, clinical writes or grants.
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const {chromium}=require('../../ankang/route1-health-agent/node_modules/playwright');
const ORIGIN='https://139.224.216.18',BASE=ORIGIN+'/api/cloud/v1';
const NAMES=['gh409','ty211','ljy666','wz999','lc783256'];
const KEYS=['profile','health','medications','assessment','rehab_plan','training','fitness','daily_health','followup','family','assistant'];
const canonical=v=>JSON.stringify(v&&typeof v==='object'?Array.isArray(v)?v.map(x=>JSON.parse(canonical(x))):Object.fromEntries(Object.keys(v).sort().map(k=>[k,JSON.parse(canonical(v[k]))])):v);
const sha=v=>crypto.createHash('sha256').update(canonical(v)).digest('hex');
async function api(route,method='GET',body,token){
 const r=await fetch(BASE+route,{method,redirect:'error',signal:AbortSignal.timeout(20000),headers:{'X-Ankang-Client':'native',...(body===undefined?{}:{'Content-Type':'application/json'}),...(token?{Authorization:'Bearer '+token}:{})},body:body===undefined?undefined:JSON.stringify(body)});
 assert(r.ok,'API HTTP '+r.status);return r.json();
}
async function main(){
 const [userFile,doctorFile,output]=process.argv.slice(2);
 if(!userFile||!doctorFile||!output)throw Error('Private credentials and fresh output required');
 const users=JSON.parse((await fs.readFile(userFile,'utf8')).replace(/^\uFEFF/,''));
 assert.equal(users.length,5);assert.deepEqual(users.map(v=>v.username).sort(),[...NAMES].sort());
 const doctorPassword=(await fs.readFile(doctorFile,'utf8')).replace(/^\uFEFF/,'').trim();
 const out=path.resolve(output);await fs.mkdir(out,{recursive:false});
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const errors=[],csp=[],results=[],identities=[],contexts=[],pages=[],cleanupErrors=[];let doctorPage,report,webLogouts=0;
 const watch=p=>{p.on('pageerror',e=>errors.push(e.message));p.on('console',m=>{if(m.type()==='error'&&/Content Security Policy|Refused to/i.test(m.text()))csp.push(m.text());});};
 const login=async(p,url,name,password)=>{await p.goto(ORIGIN+url);await p.locator('[name="username"]').fill(name);await p.locator('[name="password"]').fill(password);await p.locator('#account-form button').click();await p.locator('#logout').waitFor({state:'visible'});};
 try{
  for(const user of users){
   const context=await browser.newContext({viewport:{width:390,height:844}});contexts.push(context);
   const page=await context.newPage();pages.push(page);watch(page);
   await login(page,'/account',user.username,user.password);
   await page.locator('.cloud-dossier-section').first().waitFor();
   const me=await page.evaluate(async()=>{const r=await fetch('/api/cloud/v1/auth/me');return r.json();});
   const records=await page.evaluate(async id=>(await fetch('/api/cloud/v1/patients/'+id+'/records?offset=0&limit=100')).json(),me.patient_id);
   const dossiers=records.items.filter(r=>r.payload.schema==='ankang-sync-acceptance-1');assert.equal(dossiers.length,1);
   const dossier=dossiers[0],payload=dossier.payload;assert.equal(payload.patient_id,me.patient_id);assert.equal(payload.username,user.username);
   assert.equal(dossier.source_kind,'IMPORT');assert.equal(dossier.attribution_state,'DECLARED');assert.equal(payload.synthetic,true);assert.equal(payload.clinical_use,false);assert.equal(payload.execution_enabled,false);
   assert.equal(payload.sections.length,11);assert.equal(payload.sections.reduce((n,s)=>n+s.rows.length,0),85);
   assert.deepEqual(payload.sections.map(s=>s.key),KEYS);
   assert.equal(await page.locator('.cloud-dossier-section').count(),11);
   await page.getByText('同步验收资料：不是实测结果或医嘱，不启用服药提醒和自动训练。',{exact:true}).waitFor();
   assert.equal((await page.locator('#grant').textContent()).trim(),'停止共享');
   if(user.username==='gh409'){
    for(const key of ['profile','health','medications'])await page.locator('[data-section="'+key+'"] > summary').click();
    await page.screenshot({path:path.join(out,'PRIVATE-patient-dossier-mobile.png'),fullPage:true});
   }
   const native=[];
   for(const kind of ['APK','DESKTOP']){
    const signed=await api('/auth/password/login','POST',{...user,client_kind:kind});
    try{
     assert.equal(signed.patient_id,me.patient_id);
     const read=await api('/patients/'+me.patient_id+'/records?offset=0&limit=100','GET',undefined,signed.access_token);
     assert.deepEqual(read.items,records.items);native.push(kind+'_API');
    }finally{await api('/auth/logout','POST',{},signed.access_token);}
   }
   // Full user app opens the very same cloud record, without accepting it as
   // device measurements, local medical eligibility or active prescriptions.
   await page.goto(ORIGIN+'/');await page.waitForFunction(()=>window.PhoneLocal?.store?.value?.cloudIdentity);
   await page.evaluate(()=>PhoneLocal.ready);
   const before=await page.evaluate(()=>({jobs:PhoneLocal.store.value.jobs.length,plans:PhoneLocal.store.value.plans.length}));
   await page.getByRole('button',{name:'云账号与结果上传',exact:true}).click();
   await page.getByRole('button',{name:'云记录',exact:true}).click();
   await page.getByText('云记录已读取（最近10条）',{exact:true}).waitFor();
   await page.locator('dialog section summary').filter({hasText:'完整身体与使用档案'}).click();
   assert((await page.locator('dialog section').textContent()).includes('SYNC_ACCEPTANCE'));
   const fullRead=await page.evaluate(()=>PhoneAccount.request('records',PhoneAccount.identity()));
   assert.deepEqual(fullRead.items,records.items);
   assert.deepEqual(await page.evaluate(()=>({jobs:PhoneLocal.store.value.jobs.length,plans:PhoneLocal.store.value.plans.length})),before);
   await page.getByRole('button',{name:'关闭',exact:true}).click();
   identities.push({page,patient_id:me.patient_id,records:records.items});
   results.push({username:user.username,sections:11,fields:85,payload_sha256:sha(payload),readers:['WEB_PORTAL','WEB_FULL',...native],unchanged_local_jobs_and_plans:true});
  }
  const doctorContext=await browser.newContext({viewport:{width:1440,height:940}});contexts.push(doctorContext);doctorPage=await doctorContext.newPage();pages.push(doctorPage);watch(doctorPage);
  await login(doctorPage,'/care','doctor',doctorPassword);await doctorPage.locator('.cloud-patient').first().waitFor();
  for(let i=0;i<users.length;i++){
   await doctorPage.locator('.cloud-patient').filter({hasText:users[i].username}).getByRole('button',{name:'查看档案',exact:true}).click();
   await doctorPage.locator('.cloud-dossier-section').first().waitFor();assert.equal(await doctorPage.locator('.cloud-dossier-section').count(),11);
   const shared=await doctorPage.evaluate(async id=>(await fetch('/api/cloud/v1/patients/'+id+'/records?offset=0&limit=100')).json(),identities[i].patient_id);
   assert.deepEqual(shared.items,identities[i].records);results[i].readers.push('DOCTOR_WEB');
   if(i===0){for(const key of ['assessment','rehab_plan'])await doctorPage.locator('[data-section="'+key+'"] > summary').click();await doctorPage.screenshot({path:path.join(out,'PRIVATE-doctor-dossier-desktop.png'),fullPage:true});}
   const other=identities[(i+1)%identities.length].patient_id;
   const forbidden=(await identities[i].page.request.get(BASE+'/patients/'+other+'/records')).status();assert.equal(forbidden,404);results[i].other_patient_status=forbidden;
   await doctorPage.getByRole('button',{name:'返回患者列表',exact:true}).click();await doctorPage.locator('.cloud-patient').first().waitFor();
  }
  assert.deepEqual(errors,[]);assert.deepEqual(csp,[]);
  const capabilities=await api('/capabilities');assert.equal(capabilities.version,'0.1.4');assert.equal(capabilities.incremental_sync,false);assert.equal(capabilities.plans,false);
  report={public_https:true,tls_bypass:false,patients:results,browser_errors:errors,csp_errors:csp,clinical_execution:false,full_incremental_sync:false,physical_apk_test:false};
 }finally{
  for(const page of pages){
   try{
    const meResponse=await page.request.get(BASE+'/auth/me');
    if(meResponse.ok()){
     const me=await meResponse.json();
     const logout=await page.request.post(BASE+'/auth/logout',{headers:{'Origin':ORIGIN,'X-CSRF-Token':me.csrf_token},data:{}});
     assert(logout.ok(),'Temporary WEB session logout failed');
     assert.equal((await page.request.get(BASE+'/auth/me')).status(),401);webLogouts++;
    }
   }catch(e){cleanupErrors.push(e.message);}
  }
  for(const c of contexts)await c.close();await browser.close();
 }
 assert.deepEqual(cleanupErrors,[]);assert.equal(webLogouts,6);
 report.temporary_web_sessions_revoked=webLogouts;
 await fs.writeFile(path.join(out,'result.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
}
main().catch(e=>{console.error(e.message);process.exitCode=1;});
