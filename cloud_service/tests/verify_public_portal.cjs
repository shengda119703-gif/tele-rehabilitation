/* Real HTTPS browser flow, isolated synthetic account, no bypass of certificate checks. */
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const {chromium} = require(process.env.ANKANG_PLAYWRIGHT_MODULE || 'playwright');

(async () => {
  const origin = process.argv[2], output = process.argv[3], credentialFile = process.argv[4];
  if (!origin?.startsWith('https://') || !output || !credentialFile) throw Error('HTTPS origin, private output and local credential file required');
  fs.mkdirSync(output, {recursive: true});
  const password = fs.readFileSync(credentialFile, 'utf8').split(/\r?\n/).find(x => x.startsWith('初始密码：'))?.slice(5);
  if (!password) throw Error('Missing private doctor credential');
  const browser = await chromium.launch({channel: 'msedge', headless: true});
  const patient = await browser.newContext({viewport: {width: 390, height: 844}});
  const doctor = await browser.newContext({viewport: {width: 1440, height: 940}});
  const p = await patient.newPage(), d = await doctor.newPage(), errors = [];
  [p, d].forEach(page => page.on('pageerror', e => errors.push(e.message)));
  const username = 'qa-cloud-' + crypto.randomBytes(5).toString('hex');
  const result = {https_certificate_bypassed: false, synthetic_username: username};
  try {
    await p.goto(origin); await p.getByRole('button', {name: '没有账号，去注册'}).click();
    await p.getByLabel('账号', {exact: true}).fill(username);
    await p.getByLabel('姓名', {exact: true}).fill('云端验收用户');
    await p.getByLabel('密码', {exact: true}).fill('1');
    await p.getByRole('button', {name: '创建账号', exact: true}).click();
    await p.getByRole('button', {name: '授权医生查看', exact: true}).waitFor();
    result.registration_with_simple_password = true;
    const me = await p.evaluate(async () => (await fetch('/api/cloud/v1/auth/me')).json());
    result.patient_id = me.patient_id;
    const record = await p.evaluate(async () => {
      const me = await (await fetch('/api/cloud/v1/auth/me')).json();
      const payload = {operation_id: crypto.randomUUID(), source_event_id: 'synthetic-public-portal-check',
        installation_id: 'synthetic-browser-qa', source_kind: 'SELF_REPORT', payload: {title: '验收记录', text: '合成资料，仅用于验证云端读写'}};
      const send = () => fetch(`/api/cloud/v1/patients/${me.patient_id}/record-events`, {method:'POST',
        headers:{'Content-Type':'application/json','X-CSRF-Token':me.csrf_token}, body:JSON.stringify(payload)}).then(r => r.json());
      const first = await send(), second = await send();
      return {same_id: first.resource_id === second.resource_id, idempotent: second.idempotent, status: first.status};
    });
    assert.equal(record.status, 'COMMITTED'); assert(record.same_id && record.idempotent);
    result.record_retry_one_fact = true;
    await p.reload(); await p.getByText('验收记录', {exact:true}).waitFor();
    result.reload_keeps_session_and_record = true;
    await p.screenshot({path:path.join(output, 'PRIVATE-patient-before-grant.png'), fullPage:true});
    await d.goto(origin + '/care');
    await d.getByLabel('账号', {exact:true}).fill('doctor');
    await d.getByLabel('密码', {exact:true}).fill(password);
    await d.getByRole('button', {name:'登录', exact:true}).click();
    await d.getByRole('heading', {name:'医生工作台', exact:true}).waitFor();
    assert.equal(await d.getByRole('button', {name:'查看档案', exact:true}).count(), 0);
    result.no_patient_before_grant = true;
    await p.getByRole('button', {name:'授权医生查看', exact:true}).click();
    await p.getByRole('button', {name:'停止共享', exact:true}).waitFor();
    await d.reload(); await d.getByRole('button', {name:'查看档案', exact:true}).waitFor();
    await d.getByRole('button', {name:'查看档案', exact:true}).click();
    await d.getByText('验收记录', {exact:true}).waitFor();
    result.authorized_doctor_reads_real_cloud_record = true;
    await d.screenshot({path:path.join(output, 'PRIVATE-doctor-records.png'), fullPage:true});
    await p.getByRole('button', {name:'停止共享', exact:true}).click();
    await p.getByRole('button', {name:'授权医生查看', exact:true}).waitFor();
    const forbidden = await d.evaluate(async id => (await fetch('/api/cloud/v1/patients/' + id)).status, me.patient_id);
    assert.equal(forbidden, 404); result.revocation_blocks_existing_doctor_session = true;
    await d.reload(); await d.getByRole('heading', {name:'医生工作台', exact:true}).waitFor();
    assert.equal(await d.getByRole('button', {name:'查看档案', exact:true}).count(), 0);
    result.revocation_removes_list_entry = true;
    await d.screenshot({path:path.join(output, 'PRIVATE-doctor-after-revoke.png'), fullPage:true});
    await d.getByRole('button', {name:'退出登录', exact:true}).click();
    await p.getByRole('button', {name:'退出登录', exact:true}).click();
    await p.getByRole('button', {name:'登录', exact:true}).waitFor();
    await p.getByLabel('账号', {exact:true}).fill(username); await p.getByLabel('密码', {exact:true}).fill('1');
    await p.getByRole('button', {name:'登录', exact:true}).click();
    await p.getByText('验收记录', {exact:true}).waitFor();
    result.relogin_same_patient = true;
    await p.getByRole('button', {name:'退出登录', exact:true}).click();
    assert.deepEqual(errors, []);
    result.passed = true;
    fs.writeFileSync(path.join(output, 'result.json'), JSON.stringify({...result, errors}, null, 2));
    console.log(JSON.stringify({passed:true, registration:true, grant_revocation:true, idempotency:true, browser_errors:errors.length}));
  } catch(e) {
    fs.writeFileSync(path.join(output, 'result.json'), JSON.stringify({...result, passed:false, error:e.message, errors}, null, 2));
    await p.screenshot({path:path.join(output, 'PRIVATE-failure.png'), fullPage:true});
    throw e;
  } finally { await browser.close(); }
})().catch(e => {console.error(e.message); process.exitCode = 1;});
