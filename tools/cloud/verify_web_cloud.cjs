'use strict';
// Real HTTPS patient/doctor pages, isolated audited QA identity, no TLS bypass.
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('../../ankang/route1-health-agent/node_modules/playwright');
const ORIGIN='https://139.224.216.18';
async function main(){
 const [credentialFile,doctorFile,outDir]=process.argv.slice(2);
 if(!credentialFile||!doctorFile||!outDir)throw Error('Private inputs and fresh output directory required');
 const qa=JSON.parse(await fs.readFile(credentialFile,'utf8'));
 const lines=(await fs.readFile(doctorFile,'utf8')).replace(/^\uFEFF/,'').split(/\r?\n/);
 const secret=lines.find(s=>s.startsWith('初始密码：'))?.slice(5);
 if(!secret)throw Error('Doctor credentials unavailable');
 const out=path.resolve(outDir);await fs.mkdir(out,{recursive:false});
 const browser=await chromium.launch({channel:'msedge',headless:true}),errors=[];
 const patient=await browser.newPage({viewport:{width:390,height:844}});
 const doctor=await browser.newPage({viewport:{width:1440,height:940}});
 for(const p of [patient,doctor])p.on('pageerror',e=>errors.push(e.message));
 async function login(page,url,username,password){await page.goto(url);await page.locator('[name="username"]').fill(username);await page.locator('[name="password"]').fill(password);await page.locator('#account-form button').click();await page.locator('#logout').waitFor({state:'visible'});}
 try{
  await login(patient,ORIGIN+'/',qa.username,qa.password);
  await patient.locator('.cloud-record').first().waitFor();
  const original=await patient.evaluate(async id=>(await fetch('/api/cloud/v1/patients/'+id+'/records?offset=0&limit=10')).json(),qa.identity.patient_id);
  assert(original.items.some(r=>r.source_kind==='APK_LOCAL'));assert(original.items.some(r=>r.source_kind==='DESKTOP_LOCAL'));
  assert(await patient.locator('.cloud-metrics').count()>0);
  await patient.screenshot({path:path.join(out,'PRIVATE-patient-mobile.png'),fullPage:true});
  await patient.locator('#grant').click();await patient.getByRole('button',{name:'停止共享',exact:true}).waitFor();
  await login(doctor,ORIGIN+'/care','doctor',secret);
  await doctor.locator('.cloud-patient').filter({hasText:qa.username}).getByRole('button',{name:'查看档案'}).click();
  await doctor.locator('.cloud-record').first().waitFor();
  const shared=await doctor.evaluate(async id=>(await fetch('/api/cloud/v1/patients/'+id+'/records?offset=0&limit=10')).json(),qa.identity.patient_id);
  assert.deepEqual(shared.items,original.items);assert(await doctor.locator('.cloud-metrics').count()>0);
  await doctor.screenshot({path:path.join(out,'PRIVATE-doctor-desktop.png'),fullPage:true});
  await patient.locator('#grant').click();await patient.getByRole('button',{name:'授权医生查看',exact:true}).waitFor();
  const revoked=await doctor.evaluate(async id=>(await fetch('/api/cloud/v1/patients/'+id+'/records?offset=0&limit=10')).status,qa.identity.patient_id);
  assert.equal(revoked,404);assert.deepEqual(errors,[]);
  const result={public_https:true,tls_bypass:false,patient_cookie_login:true,doctor_cookie_login:true,records:shared.items.length,exact_same_payloads:true,readable_result_metrics:true,revocation_status:revoked,browser_errors:errors};
  await fs.writeFile(path.join(out,'result.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }finally{for(const p of [patient,doctor]){if(await p.locator('#logout').isVisible())await p.locator('#logout').click().catch(()=>{});}await browser.close();}
}
main().catch(e=>{console.error(e.message);process.exitCode=1;});
