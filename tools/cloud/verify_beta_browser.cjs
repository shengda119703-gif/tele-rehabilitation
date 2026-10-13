/* Loopback-only, fictional actor UI checks. No production requests. */
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path'),crypto=require('node:crypto');
const {chromium}=require('../../ankang/route1-health-agent/node_modules/playwright');
async function main(){
 const origin=process.argv[2],out=path.resolve(process.argv[3]);
 assert.equal(new URL(origin).hostname,'127.0.0.1');assert.equal(new URL(origin).protocol,'http:');
 await fs.mkdir(out,{recursive:false});
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const pc=await browser.newContext(),dc=await browser.newContext({viewport:{width:1440,height:940}});
 const p=await pc.newPage(),d=await dc.newPage(),errors=[];
 for(const page of [p,d])page.on('pageerror',e=>errors.push(e.message));
 async function api(ctx,route,method='GET',data){
  const me=await ctx.request.get(origin+'/api/cloud/v1/auth/me'),identity=me.ok()?await me.json():{};
  const r=await ctx.request.fetch(origin+'/api/cloud/v1'+route,{method,headers:{Origin:origin,'X-CSRF-Token':identity.csrf_token||''},...(data===undefined?{}:{data})});
  assert(r.ok(),`${route}: ${r.status()} ${await r.text()}`);return r.json();
 }
 async function login(page,name){await page.goto(origin+'/account');await page.getByLabel('账号',{exact:true}).fill(name);await page.getByLabel('密码',{exact:true}).fill('1');await page.locator('#account-form button[type=submit]').click();await page.locator('#logout').waitFor();}
 try{
  const username='qa-beta-'+crypto.randomBytes(5).toString('hex');
  await api(pc,'/auth/register','POST',{username,password:'1',display_name:'TEST 新增功能验收'});
  await login(p,username);const identity=await api(pc,'/auth/me'),id=identity.patient_id,base='/patients/'+id;
  await api(pc,base+'/doctor-access','PUT',{enabled:true,expected_version:0});
  await api(pc,base+'/rehab-workflow/profile','PUT',{expected_version:0,goal:'TEST 无人体流程',region:'膝',level:0,equipment:['稳固椅'],restrictions:[],screening_confirmed:true});
  const now=new Date().toISOString();
  await api(pc,base+'/record-events','POST',{operation_id:crypto.randomUUID(),source_event_id:'TEST-assessment',installation_id:'TEST-browser-beta',source_kind:'DESKTOP_LOCAL',payload:{schema:'ankang-workbench-record-1',source:'DESKTOP_LOCAL',patient_id:id,kind:'assessment',record_key:'TEST-result',revision:1,owner_id:'TEST-local-owner',captured_at:now,title:'TEST 无人体评估结构',result:{exercise_id:'knee_extension',side:'left',end_utc:now,status:'FINISHED'}}});
  const candidate=await api(pc,base+'/rehab-candidates','POST',{operation_id:crypto.randomUUID(),kind:'STARTER'});
  assert.equal(candidate.state,'PENDING_REVIEW');assert.equal(candidate.document.model_calls,0);
  await api(pc,base+'/reports','POST',{operation_id:crypto.randomUUID(),filename:'TEST-不是病历.pdf',mime:'application/pdf',data:Buffer.from('%PDF-1.4\nTEST-ONLY').toString('base64'),shared:true});
  await login(d,'doctor');await d.goto(origin+'/care');
  await d.locator('#beta-dashboard').getByText('内测用户与 API 用量',{exact:false}).waitFor();
  await d.getByText('配置工作时段与假日（北京时间）',{exact:true}).click();
  await d.locator('#calendar-form [name=intervals]').fill(JSON.stringify({'1':[[540,720],[840,1080]],'2':[[540,720],[840,1080]]}));
  await d.locator('#calendar-form button').click();
  await d.screenshot({path:path.join(out,'doctor-beta-usage-calendar-TEST.png'),fullPage:true});
  await d.locator(`[data-patient="${id}"]`).click();
  await d.getByRole('heading',{name:'报告原件',exact:true}).waitFor();
  assert(await d.getByText('TEST-不是病历.pdf',{exact:true}).isVisible());
  await d.screenshot({path:path.join(out,'doctor-candidate-report-TEST.png'),fullPage:true});
  await api(dc,base+'/rehab-candidates/'+candidate.id+'/review','POST',{decision:'REVIEWED'});
  assert.equal((await api(pc,base+'/plans/current')).plan,null);
  await d.reload();await d.locator(`[data-patient="${id}"]`).click();
  await d.locator('#new-plan').click();
  await d.getByRole('button',{name:'添加阶段',exact:true}).click();
  await d.locator('.programme-phases .phase-name').fill('TEST 第一阶段');
  await d.screenshot({path:path.join(out,'doctor-phase-editor-TEST.png'),fullPage:true});
  assert.deepEqual(errors,[]);
  await fs.writeFile(path.join(out,'result.json'),JSON.stringify({scope:'ISOLATED_LOOPBACK',synthetic:true,calendar_and_usage_ui:true,report_and_candidate_ui:true,review_does_not_activate_plan:true,phase_editor_ui:true,browser_errors:errors,passed:true},null,2));
 }finally{await browser.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
