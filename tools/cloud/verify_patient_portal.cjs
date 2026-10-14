/* Loopback-only checks for the separate patient contact and doctor workbench. */
'use strict';
const assert = require('node:assert/strict'), fs = require('node:fs/promises'), path = require('node:path'), crypto = require('node:crypto');
let playwright; try { playwright = require('playwright'); } catch { playwright = require('../../ankang/route1-health-agent/node_modules/playwright'); }

async function main() {
  const origin = process.argv[2], target = process.argv[3], url = new URL(origin);
  assert.equal(url.hostname, '127.0.0.1'); assert.equal(url.protocol, 'http:');
  assert(target, 'Fresh screenshot directory required'); const output = path.resolve(target); await fs.mkdir(output, {recursive:false});
  const browser = await playwright.chromium.launch({channel:'msedge', headless:true});
  const patientContext = await browser.newContext({viewport:{width:1280,height:940}}), doctorContext = await browser.newContext({viewport:{width:1440,height:940}});
  const patient = await patientContext.newPage(), doctor = await doctorContext.newPage(), errors = [];
  [patient, doctor].forEach(p => p.on('pageerror', e => errors.push(e.message)));
  const result = {scope:'ISOLATED_LOOPBACK', synthetic:true, checks:[]}, username = 'qa-contact-' + crypto.randomBytes(5).toString('hex');
  async function api(context, route, method='GET', data) {
    const me = await context.request.get(origin + '/api/cloud/v1/auth/me'), identity = me.ok() ? await me.json() : {};
    const response = await context.request.fetch(origin + '/api/cloud/v1' + route, {method, headers:{Origin:origin, 'X-CSRF-Token':identity.csrf_token || ''}, ...(data === undefined ? {} : {data})});
    assert(response.ok(), `HTTP ${response.status()} ${route}: ${await response.text()}`); return response.json();
  }
  async function login(page, name, route) {
    await page.goto(origin + route); await page.getByLabel('账号', {exact:true}).fill(name); await page.getByLabel('密码', {exact:true}).fill('1');
    await page.locator('#account-form button[type="submit"]').click(); await page.locator('#logout').waitFor({state:'visible'});
  }
  function check(name) { result.checks.push(name); }
  try {
    await patient.goto(origin + '/account'); await patient.getByRole('heading', {name:'联系康复医师',exact:true}).waitFor();
    assert.equal(await patient.getByRole('heading', {name:'患者登录',exact:true}).count(), 1);
    await doctor.goto(origin + '/care'); await doctor.getByRole('heading', {name:'医生工作台',exact:true}).waitFor(); check('separate_patient_and_doctor_login_pages');
    await api(patientContext, '/auth/register', 'POST', {username, password:'1', display_name:'TEST 患者入口验收'});
    await login(patient, username, '/account'); await patient.locator('#contact-chat').waitFor();
    const identity = await api(patientContext, '/auth/me'), ident = identity.patient_id;
    assert.equal(await patient.getByRole('heading', {name:/工作台|云端记录|候选/}).count(), 0);
    assert.equal(await patient.locator('#records').count(), 0); assert.equal(await patient.locator('#workflow-profile').count(), 0);
    assert.equal(await patient.getByRole('button', {name:'发送给医师',exact:true}).isDisabled(), true);
    assert.equal((await api(patientContext, `/patients/${ident}`)).doctor_access, false); check('patient_chat_is_default_without_management_console_or_implicit_grant');
    await patient.getByRole('button', {name:'同意并联系医师',exact:true}).click(); await patient.waitForFunction(() => document.querySelector('#message-form button')?.disabled === false);
    assert.equal((await api(patientContext, `/patients/${ident}`)).doctor_access, true); check('explicit_consent_enables_contact');
    await patient.getByLabel('给医师留言', {exact:true}).fill('TEST 我想和医师核对训练感受。<img src=x onerror=alert(1)>');
    await patient.getByRole('button', {name:'发送给医师',exact:true}).click(); await patient.getByText('已发送', {exact:true}).waitFor();
    await login(doctor, 'doctor', '/care'); await doctor.locator(`[data-patient="${ident}"]`).click();
    await doctor.getByText('TEST 我想和医师核对训练感受。<img src=x onerror=alert(1)>', {exact:true}).waitFor();
    assert.equal(await doctor.locator('.cloud-chat img').count(), 0); await doctor.locator('#patient-usage').getByRole('heading').waitFor();
    assert((await doctor.locator('#patient-usage').innerText()).includes('0 次请求')); check('doctor_opens_conversation_and_real_per_patient_usage');
    await doctor.getByLabel('发送给患者', {exact:true}).fill('TEST 医师回复：请先告诉我目前的训练感受。');
    await doctor.getByRole('button', {name:'发送消息',exact:true}).click(); await doctor.getByText('已发送', {exact:true}).waitFor();
    await patient.getByRole('button', {name:'刷新对话',exact:true}).click(); await patient.getByText('TEST 医师回复：请先告诉我目前的训练感受。', {exact:true}).waitFor();
    await patient.reload(); await patient.getByText('TEST 医师回复：请先告诉我目前的训练感受。', {exact:true}).waitFor();
    assert.equal(await patient.locator('#account-form').count(), 0); assert.equal((await api(patientContext, `/patients/${ident}/messages?latest=true`)).unread_count, 0); check('two_way_chat_history_login_and_read_cursor_survive_reload');

    let lose = true, clientOffline = false; const sendKeys = [];
    await patient.route('**/messages', async route => {
      if (route.request().method() !== 'POST') return route.continue();
      sendKeys.push(route.request().postDataJSON().operation_id);
      if (clientOffline) return route.abort('internetdisconnected');
      const response = await route.fetch();
      if (lose) { lose=false; return route.fulfill({status:503,contentType:'application/json',body:'{"message":"TEST 回执丢失"}'}); }
      return route.fulfill({response});
    });
    await patient.getByLabel('给医师留言', {exact:true}).fill('TEST 失联重试应只有一条消息。'); await patient.getByRole('button', {name:'发送给医师',exact:true}).click();
    await patient.getByRole('button', {name:'重试待发送消息',exact:true}).waitFor(); await patient.reload();
    await patient.getByRole('button', {name:'重试待发送消息',exact:true}).click(); await patient.getByText('已发送', {exact:true}).waitFor();
    assert.equal(sendKeys.length,2); assert.equal(sendKeys[0],sendKeys[1]);
    assert.equal((await api(patientContext, `/patients/${ident}/messages?latest=true`)).items.filter(x=>x.text==='TEST 失联重试应只有一条消息。').length,1);
    check('patient_stable_message_id_survives_lost_ack_and_reload');
    clientOffline = true; await patientContext.setOffline(true);
    await patient.getByLabel('给医师留言', {exact:true}).fill('TEST 断网后保留并重试。'); await patient.getByRole('button', {name:'发送给医师',exact:true}).click();
    await patient.getByRole('button', {name:'重试待发送消息',exact:true}).waitFor();
    assert(await patient.evaluate(()=>Object.entries(localStorage).some(([key,value])=>key.startsWith('ankang-patient-contact-outbox-1:') && JSON.parse(value).text==='TEST 断网后保留并重试。')));
    clientOffline = false; await patientContext.setOffline(false); await patient.reload(); await patient.getByRole('button', {name:'重试待发送消息',exact:true}).click();
    await patient.getByText('已发送', {exact:true}).waitFor();
    assert.equal((await api(patientContext, `/patients/${ident}/messages?latest=true`)).items.filter(x=>x.text==='TEST 断网后保留并重试。').length,1);
    check('offline_message_is_preserved_and_retryable_after_reload');

    await patient.getByRole('button', {name:'分享报告',exact:true}).click();
    await patient.locator('#report-upload input[type="file"]').setInputFiles({name:'TEST-康复资料.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF-1.4\n%TEST nonclinical original\n%%EOF')});
    assert.equal(await patient.locator('#report-upload [name="shared"]').isChecked(), false);
    await patient.locator('#report-upload [name="shared"]').check(); await patient.locator('#report-upload button').click();
    await patient.getByText('TEST-康复资料.pdf', {exact:true}).waitFor(); const reports=await api(patientContext, `/patients/${ident}/reports`); assert.equal(reports.items[0].shared,true);
    const original=await doctorContext.request.get(origin+'/api/cloud/v1'+`/patients/${ident}/reports/${reports.items[0].id}/original`); assert(original.ok());
    await patient.getByRole('button', {name:'撤销这份原件共享',exact:true}).click(); await patient.getByRole('button', {name:'共享给医生',exact:true}).waitFor();
    assert.equal((await doctorContext.request.get(origin+'/api/cloud/v1'+`/patients/${ident}/reports/${reports.items[0].id}/original`)).status(),404);
    check('selected_report_original_requires_per_file_consent_and_can_be_revoked');

    await doctor.getByRole('button', {name:'新建草稿',exact:true}).click(); await doctor.getByLabel('方案名称', {exact:true}).fill('TEST 医师方案');
    await doctor.getByLabel('方案说明', {exact:true}).fill('仅用于隔离验收，不是医嘱。'); await doctor.getByLabel('动作', {exact:true}).selectOption('shoulder_abduction'); await doctor.getByLabel('侧别', {exact:true}).selectOption('left');
    await doctor.getByLabel('目标次数', {exact:true}).fill('3'); await doctor.getByLabel('目标组数', {exact:true}).fill('1');
    await doctor.getByRole('button', {name:'保存草稿',exact:true}).click(); await doctor.getByRole('button', {name:'核对并发布',exact:true}).waitFor();
    await patient.getByRole('button', {name:'医生方案',exact:true}).click(); assert.equal(await patient.getByRole('heading', {name:'TEST 医师方案',exact:true}).count(),0);
    doctor.once('dialog', dialog=>dialog.accept()); await doctor.getByRole('button', {name:'核对并发布',exact:true}).click(); await doctor.getByRole('button', {name:'以此创建新版本',exact:true}).waitFor();
    await patient.getByRole('button', {name:'医生方案',exact:true}).click(); await patient.getByRole('heading', {name:'TEST 医师方案',exact:true}).waitFor();
    assert.equal(await patient.getByRole('button', {name:/采用|启动/}).count(),0); assert.equal((await api(patientContext, `/patients/${ident}/plans`)).current_plan_id,null);
    check('patient_reads_only_published_plans_and_chat_never_activates_training');

    await patient.getByRole('button', {name:'与医师聊天',exact:false}).click(); await patient.screenshot({path:path.join(output,'patient-contact-desktop.png'),fullPage:true});
    await doctor.locator('#conversation .cloud-chat').first().waitFor(); await doctor.evaluate(()=>scrollTo(0,0)); await doctor.screenshot({path:path.join(output,'doctor-conversation.png'),fullPage:false});
    await doctor.locator('#patient-usage').screenshot({path:path.join(output,'doctor-patient-api-usage.png')});
    await patient.setViewportSize({width:390,height:844}); assert(await patient.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await patient.screenshot({path:path.join(output,'patient-contact-mobile.png'),fullPage:true}); check('patient_mobile_has_no_horizontal_overflow');

    await patient.goto(origin + '/care'); await patient.getByRole('heading',{name:'这是医生工作台',exact:true}).waitFor(); await patient.getByRole('link',{name:'联系康复医师',exact:true}).click(); await patient.locator('#contact-chat').waitFor();
    await doctor.goto(origin + '/account'); await doctor.getByRole('heading',{name:'这是患者沟通入口',exact:true}).waitFor(); await doctor.getByRole('link',{name:'进入医生工作台',exact:true}).click(); await doctor.locator('#patient-search').waitFor();
    assert.equal((await patientContext.request.get(origin+'/api/cloud/v1/care/beta-users')).status(),403); check('wrong_role_entry_has_actionable_navigation_and_server_permissions_remain');
    await patient.locator('.cloud-account-settings > summary').click(); patient.once('dialog',dialog=>dialog.accept()); await patient.getByRole('button',{name:'停止医师共享',exact:true}).click();
    await patient.waitForFunction(()=>document.querySelector('#message-form button')?.disabled); await doctor.reload();
    await doctor.locator('#patient-search').waitFor(); assert.equal(await doctor.locator(`[data-patient="${ident}"]`).count(),0);
    const inaccessible=await doctorContext.request.get(origin+'/api/cloud/v1'+`/patients/${ident}`); assert.equal(inaccessible.status(),404); check('revoking_doctor_access_disables_contact_and_blocks_doctor_record_access');
    assert.deepEqual(errors,[]); result.page_errors=errors; result.passed=result.checks.length;
    await fs.writeFile(path.join(output,'result.json'),JSON.stringify(result,null,2)); process.stdout.write(JSON.stringify(result,null,2)+'\n');
  } finally { await browser.close(); }
}
main().catch(e=>{console.error(e);process.exitCode=1;});
