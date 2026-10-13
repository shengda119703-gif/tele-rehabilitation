/* Isolated loopback browser checks. All records/messages are labeled TEST. */
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path'),crypto=require('node:crypto');
let playwright;try{playwright=require('playwright');}catch{playwright=require('../../ankang/route1-health-agent/node_modules/playwright');}
async function main(){
 const origin=process.argv[2]||'http://127.0.0.1:14910',target=process.argv[3];
 const url=new URL(origin);assert.equal(url.hostname,'127.0.0.1');assert.equal(url.protocol,'http:');
 assert(target,'Fresh local output directory required');const output=path.resolve(target);await fs.mkdir(output,{recursive:false});
 const browser=await playwright.chromium.launch({channel:'msedge',headless:true});
 const pctx=await browser.newContext({viewport:{width:390,height:844}}),dctx=await browser.newContext({viewport:{width:1440,height:940}});
 const p=await pctx.newPage(),d=await dctx.newPage(),errors=[];[p,d].forEach(page=>page.on('pageerror',e=>errors.push(e.message)));
 const username='qa-workbench-'+crypto.randomBytes(5).toString('hex'),result={scope:'ISOLATED_LOOPBACK',synthetic:true};
 async function api(ctx,route,method='GET',body){
  const me=await ctx.request.get(origin+'/api/cloud/v1/auth/me');const identity=me.ok()?await me.json():{};
  const response=await ctx.request.fetch(origin+'/api/cloud/v1'+route,{method,headers:{Origin:origin,'X-CSRF-Token':identity.csrf_token||''},...(body===undefined?{}:{data:body})});
  assert(response.ok(),`HTTP ${response.status()} ${route}: ${await response.text()}`);return response.json();
 }
 async function login(page,name){await page.goto(origin+(name==='doctor'?'/care':'/account'));await page.getByLabel('账号',{exact:true}).fill(name);await page.getByLabel('密码',{exact:true}).fill('1');await page.getByRole('button',{name:'登录',exact:true}).click();await page.locator('#logout').waitFor({state:'visible'});}
 try{
  await api(pctx,'/auth/register','POST',{username,password:'1',display_name:'TEST 工作台用户'});await login(p,username);
  const identity=await api(pctx,'/auth/me'),ident=identity.patient_id;
  await api(pctx,`/patients/${ident}/doctor-access`,'PUT',{enabled:true,expected_version:0});
  const entries=[['profile','TEST 本人资料',{name:'TEST 已更新资料',age:0,conditions:['仅用于程序验收，无真实诊断']}],['assessment','TEST 已保存评估',{exercise_id:'shoulder_abduction',side:'left',summary:{completed:0,valid_ratio:0,metrics:[{label:'TEST 膝角',value:null,unit:'deg'}]}}],['training','TEST 训练反馈',{exercise_id:'shoulder_abduction',side:'left',summary:{completed:0},feedback:{pain:0,fatigue:0}}],['rehab_plan','TEST 当前本机计划',{name:'TEST 本机计划一',revision:1,items:[{exercise_id:'shoulder_abduction',side:'left',settings:{target_reps:3,target_sets:1,target_angle_deg:null}}]}]];
  for(const [kind,title,data] of entries){await api(pctx,`/patients/${ident}/record-events`,'POST',{operation_id:crypto.randomUUID(),source_event_id:'test-'+kind+'-1',installation_id:'test-browser-only',source_kind:'WEB_LOCAL',payload:{schema:'ankang-workbench-record-1',title,kind,source:'WEB_LOCAL',owner_id:ident,patient_id:ident,record_key:'test:'+kind,revision:1,captured_at:new Date().toISOString(),synthetic:true,result:data}});}
  await api(pctx,`/patients/${ident}/messages`,'POST',{operation_id:crypto.randomUUID(),text:'TEST 患者反馈：只用于程序验收。<img src=x onerror=alert(1)>'});
  await login(d,'doctor');await d.getByRole('heading',{name:'工作台',exact:true}).waitFor();
  await d.getByLabel('查找患者',{exact:true}).fill('TEST 工作台用户');await d.getByRole('button',{name:'查找',exact:true}).click();
  await d.locator(`[data-patient="${ident}"]`).click();
  await d.locator('[data-saved-kind="rehab_plan"]').getByText('TEST 本机计划一',{exact:true}).waitFor();
  await d.locator('[data-saved-kind="assessment"] > summary').click();await d.getByText('TEST 已保存评估',{exact:true}).first().waitFor();
  await d.locator('[data-saved-kind="training"] > summary').click();await d.getByText('TEST 训练反馈',{exact:true}).first().waitFor();
  await d.screenshot({path:path.join(output,'doctor-saved-records.png'),fullPage:true});result.saved_assessment_training_current_local_plan=true;
  await d.getByRole('button',{name:'读取对话',exact:true}).click();await d.locator('.cloud-chat').first().waitFor();
  assert.equal(await d.locator('.cloud-chat img').count(),0);assert((await d.locator('.cloud-chat').innerText()).includes('<img src=x'));
  assert.equal((await api(dctx,`/patients/${ident}/messages?latest=true`)).unread_count,0);result.read_cursor_and_escaped_text=true;
  const other=await dctx.newPage();other.on('pageerror',e=>errors.push(e.message));await other.goto(origin+'/care');await other.locator(`[data-patient="${ident}"]`).click();await other.getByLabel('发送给患者',{exact:true}).waitFor();
  let lost=false;const sendKeys=[];
  await d.route('**/messages',async route=>{if(route.request().method()!=='POST')return route.continue();sendKeys.push(route.request().postDataJSON().operation_id);const response=await route.fetch();if(!lost&&response.ok()){lost=true;return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({message:'TEST 已提交回执丢失'})});}return route.fulfill({response});});
  await d.getByLabel('发送给患者',{exact:true}).fill('TEST 医生反馈：请核对本人记录。');await d.getByRole('button',{name:'发送消息',exact:true}).click();
  await d.getByText('尚未收到成功回执，原文和操作编号已保留；刷新或重新登录后仍可重试。',{exact:true}).waitFor();
  await other.getByLabel('发送给患者',{exact:true}).fill('TEST 第二页草稿不会覆盖未确认操作');await other.getByRole('button',{name:'发送消息',exact:true}).click();
  await other.getByText('另一个页面已有待核对消息，原文已保留。请返回档案重新打开并重试原消息。当前输入未发送。',{exact:true}).waitFor();assert.equal((await api(dctx,`/patients/${ident}/messages?latest=true`)).items.length,2);await other.close();result.other_tab_cannot_overwrite_pending_send=true;
  await d.getByRole('button',{name:'退出登录',exact:true}).click();await login(d,'doctor');await d.locator(`[data-patient="${ident}"]`).click();
  await d.getByRole('button',{name:'重试待发送消息',exact:true}).waitFor();assert.equal(await d.getByLabel('发送给患者',{exact:true}).inputValue(),'TEST 医生反馈：请核对本人记录。');
  await d.getByRole('button',{name:'重试待发送消息',exact:true}).click();await d.getByText('已发送',{exact:true}).waitFor();
  assert.equal(sendKeys.length,2);assert.equal(sendKeys[0],sendKeys[1]);assert.equal((await api(dctx,`/patients/${ident}/messages?latest=true`)).items.length,2);result.committed_reply_loss_same_id_after_logout_reload=true;
  await d.getByRole('button',{name:'新建草稿',exact:true}).click();await d.getByLabel('方案名称',{exact:true}).fill('TEST 医生方案');
  await d.getByLabel('方案说明',{exact:true}).fill('只用于工作台验收，不是患者医嘱。');await d.getByLabel('动作',{exact:true}).selectOption('shoulder_abduction');await d.getByLabel('侧别',{exact:true}).selectOption('left');
  await d.getByLabel('目标次数',{exact:true}).fill('3');await d.getByLabel('目标组数',{exact:true}).fill('1');await d.getByLabel('组间休息（秒）',{exact:true}).fill('30');await d.getByLabel('注意事项',{exact:true}).fill('TEST：仅验收。');
  let lostDraft=false;const draftKeys=[];
  await d.route('**/plans',async route=>{if(route.request().method()!=='POST')return route.continue();draftKeys.push(route.request().postDataJSON().operation_id);const response=await route.fetch();if(!lostDraft&&response.ok()){lostDraft=true;return route.fulfill({status:503,contentType:'application/json',body:'{"message":"TEST 草稿已提交回执丢失"}'});}return route.fulfill({response});});
  await d.screenshot({path:path.join(output,'doctor-plan-editor.png'),fullPage:true});await d.getByRole('button',{name:'保存草稿',exact:true}).click();await d.getByRole('button',{name:'重试待保存草稿',exact:true}).waitFor();
  await d.reload();await d.locator(`[data-patient="${ident}"]`).click();await d.getByRole('button',{name:'重试待保存草稿',exact:true}).click();await d.getByRole('button',{name:'编辑草稿',exact:true}).waitFor();assert.equal(draftKeys.length,2);assert.equal(draftKeys[0],draftKeys[1]);result.draft_reply_loss_same_id_after_reload=true;
  let plans=await api(dctx,`/patients/${ident}/plans`);assert.equal(plans.items[0].items[0].exercise_id,'shoulder_abduction');assert.equal(plans.items[0].items[0].settings.target_angle_deg,null);
  assert.equal((await api(pctx,`/patients/${ident}/plans`)).items.length,0);result.draft_hidden_from_patient=true;
  await d.getByRole('button',{name:'编辑草稿',exact:true}).click();await d.getByLabel('目标次数',{exact:true}).fill('4');await d.getByRole('button',{name:'保存草稿',exact:true}).click();
  await d.getByRole('button',{name:'核对并发布',exact:true}).waitFor();d.once('dialog',dialog=>dialog.accept());await d.getByRole('button',{name:'核对并发布',exact:true}).click();await d.getByRole('button',{name:'以此创建新版本',exact:true}).waitFor();
  plans=await api(pctx,`/patients/${ident}/plans`);assert.equal(plans.items.length,1);assert.equal(plans.items[0].status,'PUBLISHED');assert.equal(plans.items[0].items[0].settings.target_reps,4);result.structured_plan_edit_publish=true;
  await p.reload();await p.getByRole('heading',{name:'TEST 医生方案',exact:true}).waitFor();assert.equal(await p.getByRole('button',{name:/采用/}).count(),0);
  await p.getByRole('button',{name:'读取对话',exact:true}).click();await p.getByText('TEST 医生反馈：请核对本人记录。',{exact:true}).waitFor();
  assert.equal((await api(pctx,`/patients/${ident}/messages?latest=true`)).unread_count,0);await p.reload();await p.getByRole('heading',{name:'TEST 医生方案',exact:true}).waitFor();assert.equal((await api(pctx,`/patients/${ident}/messages?latest=true`)).unread_count,0);result.read_cursor_survives_reload=true;
  await p.getByRole('button',{name:'读取对话',exact:true}).click();await p.getByText('TEST 医生反馈：请核对本人记录。',{exact:true}).waitFor();
  await p.screenshot({path:path.join(output,'patient-account-mobile.png'),fullPage:true});
  await d.setViewportSize({width:390,height:844});await d.reload();await d.locator(`[data-patient="${ident}"]`).click();await d.getByRole('button',{name:'新建草稿',exact:true}).waitFor();await d.getByRole('button',{name:'新建草稿',exact:true}).click();
  await d.locator('#plan-form').waitFor();assert(await d.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await d.screenshot({path:path.join(output,'doctor-mobile.png'),fullPage:true});result.mobile_no_horizontal_overflow=true;
  // Revoke only this isolated TEST patient's grant; active doctor view is cleared.
  const profile=await api(pctx,`/patients/${ident}`);await api(pctx,`/patients/${ident}/doctor-access`,'PUT',{enabled:false,expected_version:profile.grant_version});
  await d.evaluate(()=>window.dispatchEvent(new Event('focus')));await d.getByRole('heading',{name:'无法打开档案',exact:true}).waitFor();assert.equal(await d.locator('.cloud-record').count(),0);assert.equal(await d.locator('#plan-form').count(),0);result.revocation_clears_loaded_private_view=true;
  assert.deepEqual(errors,[]);result.browser_errors=errors;result.passed=true;
  await fs.writeFile(path.join(output,'result.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }catch(e){result.passed=false;result.error=e.message;result.browser_errors=errors;await fs.writeFile(path.join(output,'result.json'),JSON.stringify(result,null,2));await d.screenshot({path:path.join(output,'failure-doctor.png'),fullPage:true});await p.screenshot({path:path.join(output,'failure-patient.png'),fullPage:true});throw e;}
 finally{for(const page of[p,d])if(await page.locator('#logout').isVisible())await page.getByRole('button',{name:'退出登录',exact:true}).click().catch(()=>{});await browser.close();}
}
main().catch(e=>{console.error(e.message);process.exitCode=1;});
