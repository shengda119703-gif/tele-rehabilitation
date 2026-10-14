'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path');
const {chromium}=require('../../ankang/route1-health-agent/node_modules/playwright');
(async()=>{
 const origin=new URL(process.argv[2]),output=path.resolve(process.argv[3]);
 assert.equal(origin.protocol,'http:');assert.equal(origin.hostname,'127.0.0.1');
 assert(process.env.ANKANG_LOCAL_DOCTOR_PASSWORD,'Local administrator credential required');
 await fs.mkdir(output,{recursive:false});
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const patient=await browser.newPage({viewport:{width:1280,height:900}});
  await patient.goto(origin.origin+'/account');
  await patient.locator('#contact-welcome').waitFor({state:'visible'});
  assert.equal(await patient.locator('#contact-auth').isVisible(),false);
  assert.equal(await patient.locator('#contact-welcome textarea').isDisabled(),true);
  await patient.screenshot({path:path.join(output,'patient-contact-empty.png'),fullPage:true});
  const doctor=await browser.newPage({viewport:{width:1280,height:900}});
  await doctor.goto(origin.origin+'/care');
  await doctor.getByLabel('账号',{exact:true}).fill('doctor');
  await doctor.getByLabel('密码',{exact:true}).fill(process.env.ANKANG_LOCAL_DOCTOR_PASSWORD);
  await doctor.locator('#account-form button[type=submit]').click();
  await doctor.getByRole('heading',{name:'患者列表',exact:true}).waitFor();
  for(const route of ['/care/patients','/care/beta-users']){
   const response=await doctor.request.get(origin.origin+'/api/cloud/v1'+route);
   assert.equal(response.status(),200);const data=await response.json();
   assert.equal(data.total,0,'Empty preview must not contain patients');assert.deepEqual(data.items,[]);
  }
  await doctor.getByRole('heading',{name:'暂无患者',exact:true}).waitFor();
  assert.equal(await doctor.locator('#beta-dashboard,#calendar-form,#plan-form').count(),0);
  await doctor.screenshot({path:path.join(output,'doctor-patient-list-empty.png'),fullPage:true});
  await fs.writeFile(path.join(output,'result.json'),JSON.stringify({patients:0,provider_receipts:0,patient_chat_first:true,doctor_list_only:true,patient_seeded:false,passed:true},null,2));
  console.log('Empty user-facing workbench verified without creating patients, messages or model receipts.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
