'use strict';
// Every request is intercepted. Provider responses and credentials are fictional; no live calls.
const {test, before, after} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
let playwright;
try { playwright = require('playwright'); }
catch { playwright = require('../../ankang/route1-health-agent/node_modules/playwright'); }
const root = path.resolve(__dirname, '../..');
const assets = new Map([
  ['/cloud-static/portal.js', ['cloud_service/static/portal.js', 'application/javascript']],
  ['/cloud-static/portal.css', ['cloud_service/static/portal.css', 'text/css']],
  ...['unified.css','unified-polish.css','controls.css'].map(name=>['/static/'+name, ['mobile_rehab/static/'+name, 'text/css']])
].map(([url,[file,type]])=>[url,{body:fs.readFileSync(path.join(root,file),'utf8'),contentType:type}]));
const html = fs.readFileSync(path.join(root,'cloud_service/static/index.html'),'utf8');
const origin = 'http://127.0.0.1:19491';
const doctor = {account_id:'fictional-doctor',role:'DOCTOR_ADMIN',csrf_token:'fictional-csrf'};
const defaults = {
  configured:true,model:'deepseek-flash',source:'environment',configuration_writable:true,
  provider_connection:'NOT_VERIFIED',last_checked_at:null,monthly_tokens:200000,monthly_calls:200,max_output_tokens:1200
};
let browser;
before(async()=> { browser = await playwright.chromium.launch({channel:'msedge',headless:true}); });
after(async()=> { await browser?.close(); });

async function fixture(t, options = {}) {
  const context = await browser.newContext({viewport:options.viewport || {width:1280,height:940}});
  t.after(()=>context.close());
  const page = await context.newPage();
  const state = {identity:options.identity === undefined ? {...doctor} : options.identity, settings:{...defaults,...options.settings},calls:[],unexpected:[],errors:[],logs:[]};
  page.on('pageerror',e=>state.errors.push(e.message));
  page.on('console',message=>state.logs.push(message.text()));
  await context.route('**/*',async route=> {
    const request = route.request(), url = new URL(request.url());
    // Fulfill/abort everything, including unexpected requests; never route.continue() or fetch().
    if (url.origin !== origin) { state.unexpected.push(url.href); return route.abort(); }
    if (assets.has(url.pathname)) return route.fulfill(assets.get(url.pathname));
    if (url.pathname === '/static/icon.svg') return route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg"/>'});
    if (url.pathname === '/care' || url.pathname === '/account') return route.fulfill({contentType:'text/html',body:html});
    const call = {path:url.pathname.replace('/api/cloud/v1',''),method:request.method(),headers:request.headers(),data:request.postData() ? request.postDataJSON() : undefined};
    state.calls.push(call);
    const respond = (body,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
    if (options.handler && await options.handler({call,state,respond}) === true) return;
    if (call.path === '/auth/me') return state.identity ? respond(state.identity) : respond({message:'Fictional session expired'},401);
    if (call.path === '/auth/password/login') { state.identity = {...doctor}; return respond(state.identity); }
    if (call.path === '/auth/logout') { state.identity = null; return respond({ok:true}); }
    if (call.path.startsWith('/care/patients?') || call.path === '/care/patients') return respond({items:[{id:'fictional-patient',display_name:'TEST 虚构患者',unread_count:0}],total:1});
    if (call.path === '/care/ai/settings') {
      if (call.method === 'PUT') {
        if (Object.hasOwn(call.data,'key')) state.settings.configured = call.data.key !== '';
        if (call.data.model) state.settings.model = call.data.model;
        state.settings.provider_connection = 'NOT_VERIFIED'; state.settings.source = 'SERVER_FILE';
      }
      return respond(state.settings);
    }
    if (call.path === '/care/ai/check') {
      state.settings.provider_connection = 'MODELS_VERIFIED';
      state.settings.last_checked_at = 1792022400;
      return respond({...state.settings,message:'Fictional model list verified; no chat performed'});
    }
    if (call.path === '/patients/fictional-patient') return respond({display_name:'TEST 虚构患者',doctor_access:false});
    if (call.path === '/care/actions') return respond({items:[]});
    if (call.path.endsWith('/rehab-summary')) return respond({});
    if (call.path.endsWith('/records') || call.path.endsWith('/reports')) return respond({items:[]});
    if (call.path.endsWith('/plans')) return respond({items:[],total:0,current_plan_id:null});
    if (call.path.endsWith('/messages')) return respond({items:[],unread_count:0,has_older:false,next_cursor:0,read_cursor:0});
    if (call.path.endsWith('/ai/usage')) return respond({period:'TEST',enabled:false,usage:{calls:0,prompt_tokens:0,completion_tokens:0,uncertain_calls:0,unpriced_calls:0,estimated_cost_by_currency:{}}});
    state.unexpected.push(call.path); return respond({message:'Unexpected isolated test route'},404);
  });
  await page.goto(origin+(options.entry || '/care'));
  await page.waitForFunction(()=>!document.querySelector('#content')?.textContent.includes('正在读取账号'));
  t.after(()=> { assert.deepEqual(state.errors,[]); assert.deepEqual(state.unexpected,[]); });
  return {page,state,async open() {
    await page.locator('#ai-settings').click();
    await page.waitForFunction(()=>document.querySelector('#ai-refresh')?.disabled === false);
  }};
}
async function settled(page) { await page.waitForFunction(()=>document.querySelector('#ai-refresh')?.disabled === false); }
async function secretAbsent(page,state,secret) {
  assert.equal(await page.locator('#ai-key').inputValue(),'');
  const snapshot = await page.evaluate(()=>({html:document.documentElement.outerHTML,storage:[{...localStorage},{...sessionStorage}],values:[...document.querySelectorAll('input')].map(input=>input.value)}));
  assert(!JSON.stringify(snapshot).includes(secret));
  assert(!state.logs.join('\n').includes(secret));
}

test('header is available only to doctor admins at /care, including after login and logout',async t=> {
  for (const options of [
    {identity:null},
    {identity:{account_id:'fictional-patient',patient_id:'fictional-patient',role:'PATIENT',csrf_token:'fictional-patient-csrf'}},
    {entry:'/account'},
    {entry:'/account',identity:{account_id:'fictional-patient',patient_id:'fictional-patient',role:'PATIENT',csrf_token:'fictional-patient-csrf'}}
  ]) {
    const {page,state} = await fixture(t,options);
    assert.equal(await page.locator('#ai-settings').isVisible(),false);
    assert.equal(state.calls.filter(call=>call.path.startsWith('/care/ai')).length,0);
    if (options.identity === null) {
      await page.getByLabel('账号',{exact:true}).fill('fictional-doctor');
      await page.getByLabel('密码',{exact:true}).fill('fictional-password');
      await page.locator('#account-form button[type=submit]').click();
      await page.locator('#patient-search').waitFor();
      assert.equal(await page.locator('#ai-settings').isVisible(),true);
      await page.locator('#logout').click(); await page.locator('#account-form').waitFor();
      assert.equal(await page.locator('#ai-settings').isVisible(),false);
    }
  }
});

test('settings reuse CSRF requests; saves omit a blank key and never retain a replacement key',async t=> {
  const {page,state,open} = await fixture(t); await open();
  assert.equal(await page.locator('header .brand').getAttribute('href'),'/care');
  assert.equal(await page.locator('#ai-key').getAttribute('type'),'password');
  assert.deepEqual(await page.locator('#ai-model option:not([disabled])').evaluateAll(options=>options.map(option=>option.value)),['deepseek-flash','deepseek-v4-pro']);
  assert((await page.locator('#ai-details').innerText()).includes('200,000'));
  const secret = 'fictional-TEST-key-for-save';
  await page.locator('#ai-key').fill(secret); await page.locator('#ai-model').selectOption('deepseek-v4-pro');
  await page.locator('#ai-save').click(); await settled(page);
  const saved = state.calls.findLast(call=>call.method==='PUT');
  assert.deepEqual(saved.data,{model:'deepseek-v4-pro',key:secret});
  assert.equal(saved.headers['x-csrf-token'],doctor.csrf_token);
  assert.equal(saved.headers['content-type'],'application/json');
  assert((await page.locator('#ai-details').innerText()).includes('服务器配置文件'));
  await secretAbsent(page,state,secret);
  await page.locator('#ai-model').selectOption('deepseek-flash'); await page.locator('#ai-save').click(); await settled(page);
  assert.deepEqual(state.calls.findLast(call=>call.method==='PUT').data,{model:'deepseek-flash'});
  await page.locator('#ai-check').click(); await settled(page);
  assert.deepEqual(state.calls.findLast(call=>call.path==='/care/ai/check').data,{});
  assert.equal(state.calls.findLast(call=>call.path==='/care/ai/check').headers['x-csrf-token'],doctor.csrf_token);
  assert((await page.locator('#ai-status').innerText()).includes('实际问答尚未测试'));
  assert((await page.locator('#ai-details').innerText()).includes('模型列表校验通过'));
});

test('clearing requires confirmation and sends an explicit empty key; canceled clear is inert',async t=> {
  const {page,state,open} = await fixture(t); await open();
  await page.locator('#ai-key').fill('fictional-unsaved-key');
  page.once('dialog',dialog=>dialog.dismiss()); await page.locator('#ai-clear').click();
  assert.equal(state.calls.filter(call=>call.method==='PUT').length,0);
  assert.equal(await page.locator('#ai-key').inputValue(),'');
  page.once('dialog',dialog=>dialog.accept()); await page.locator('#ai-clear').click(); await settled(page);
  assert.deepEqual(state.calls.findLast(call=>call.method==='PUT').data,{key:''});
  assert.equal(await page.locator('#ai-summary').innerText(),'DeepSeek 未启用');
  assert.equal(await page.locator('#ai-check').isDisabled(),true);
  assert.equal(await page.locator('#ai-clear').isDisabled(),true);
});

test('read-only and unconfigured states keep only the permitted controls enabled',async t=> {
  const readonly = await fixture(t,{settings:{configuration_writable:false}}); await readonly.open();
  for (const id of ['ai-key','ai-model','ai-save','ai-clear']) assert.equal(await readonly.page.locator('#'+id).isDisabled(),true);
  assert.equal(await readonly.page.locator('#ai-check').isEnabled(),true);
  assert((await readonly.page.locator('#ai-writable').innerText()).includes('只读'));
  const empty = await fixture(t,{settings:{configured:false,source:'DISABLED',monthly_tokens:0,monthly_calls:null,max_output_tokens:null}}); await empty.open();
  assert.equal(await empty.page.locator('#ai-check').isDisabled(),true);
  assert.equal(await empty.page.locator('#ai-save').isEnabled(),true);
  assert((await empty.page.locator('#ai-details').innerText()).includes('未知'));
  await empty.page.locator('#ai-save').click(); await settled(empty.page);
  assert.deepEqual(empty.state.calls.findLast(call=>call.method==='PUT').data,{model:'deepseek-flash'});
  assert((await empty.page.locator('#ai-status').innerText()).includes('尚未配置密钥'));
});

test('read-only settings without a key expose status only and make no provider requests',async t=> {
  const {page,state,open} = await fixture(t,{settings:{configured:false,configuration_writable:false,source:'DISABLED'}}); await open();
  assert.equal(await page.locator('#ai-key[type="password"]').count(),1);
  assert.equal(await page.locator('#ai-key').inputValue(),'');
  assert.equal(await page.locator('#ai-key').getAttribute('value'),null);
  assert.equal(await page.locator('#ai-summary').innerText(),'DeepSeek 未启用');
  assert((await page.locator('#ai-writable').innerText()).includes('只读'));
  for (const id of ['ai-key','ai-model','ai-save','ai-check','ai-clear']) assert.equal(await page.locator('#'+id).isDisabled(),true);
  assert.equal(await page.locator('#ai-refresh').isEnabled(),true);
  assert.equal(state.calls.filter(call=>call.path.startsWith('/care/ai/')).length,1);
  assert.equal(state.calls.find(call=>call.path.startsWith('/care/ai/')).method,'GET');
});

test('failed saves clear immediately, cannot duplicate pending writes, and suppress reflected error secrets',async t=> {
  let release; const gate = new Promise(resolve=>release=resolve);
  t.after(()=>release());
  const secret = 'fictional-TEST-key-in-error';
  const {page,state,open} = await fixture(t,{handler:async({call,respond})=> {
    if (call.method !== 'PUT') return false;
    await gate; await respond({message:'Rejected <b>'+secret+'</b>',code:secret},422); return true;
  }}); await open();
  await page.locator('#ai-key').fill(secret);
  const synchronous = await page.locator('#ai-form').evaluate(form=> {
    form.requestSubmit();
    return {key:form.elements.key.value,disabled:form.querySelector('button[type="submit"]').disabled,html:form.innerHTML};
  });
  assert.equal(synchronous.key,''); assert.equal(synchronous.disabled,true);
  assert(!synchronous.html.includes(secret));
  await secretAbsent(page,state,secret);
  await page.locator('#ai-form').evaluate(form=>form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));
  release(); await settled(page);
  assert.equal(state.calls.filter(call=>call.method==='PUT').length,1);
  assert((await page.locator('.cloud-error').innerText()).includes('刷新状态'));
  assert.equal(await page.locator('#ai-save').isEnabled(),true);
  await secretAbsent(page,state,secret);
});

test('a network failure also clears the key synchronously and never echoes it',async t=> {
  const secret = 'fictional-TEST-key-network-failure';
  const {page,state,open} = await fixture(t); await open();
  await page.route('**/api/cloud/v1/care/ai/settings',route=>route.request().method()==='PUT' ? route.abort('connectionfailed') : route.fallback());
  await page.locator('#ai-key').fill(secret);
  assert.equal(await page.locator('#ai-form').evaluate(form=> {form.requestSubmit(); return form.elements.key.value;}),'');
  await settled(page); await secretAbsent(page,state,secret);
  assert((await page.locator('.cloud-error').innerText()).includes('刷新状态'));
});

test('provider status and message-only failures are handled without echoing untrusted fields',async t=> {
  const secret = 'fictional-TEST-reflected-response'; let checks = 0;
  const {page,state,open} = await fixture(t,{settings:{model:secret,source:secret,last_checked_at:secret,monthly_tokens:secret},handler:async({call,state,respond})=> {
    if (call.path !== '/care/ai/check') return false;
    checks++;
    await respond({...state.settings,key:secret,message:secret,provider_connection:checks===1 ? 'FAILED' : secret}); return true;
  }}); await open(); await secretAbsent(page,state,secret);
  assert.equal(await page.locator('#ai-model').inputValue(),'');
  await page.locator('#ai-check').click(); await settled(page);
  assert((await page.locator('#ai-status').innerText()).includes('校验失败'));
  await secretAbsent(page,state,secret);
  await page.locator('#ai-check').click(); await settled(page);
  assert((await page.locator('#ai-status').innerText()).includes('服务返回了校验提示'));
  await secretAbsent(page,state,secret);
});

test('GET failures remain recoverable and 401 uses the existing authentication flow',async t=> {
  let unavailable = true;
  const {page,state,open} = await fixture(t,{handler:async({call,state,respond})=> {
    if (call.path.startsWith('/care/ai/') && !state.identity) {
      await respond({message:'fictional-secret-expired'},401); return true;
    }
    if (call.path !== '/care/ai/settings' || call.method !== 'GET' || !unavailable) return false;
    await respond({message:'fictional-secret-provider-error'},503); return true;
  }}); await open();
  assert((await page.locator('.cloud-error').innerText()).includes('无法读取'));
  assert.equal(await page.locator('#ai-save').isDisabled(),true);
  assert(!(await page.locator('#content').innerText()).includes('fictional-secret-provider-error'));
  unavailable = false; await page.locator('#ai-refresh').click(); await settled(page);
  assert.equal(await page.locator('#ai-save').isEnabled(),true);
  state.identity = null;
  await page.locator('#ai-key').fill('fictional-unsent-expired-key');
  await page.locator('#ai-save').click();
  await page.locator('#account-form').waitFor();
  assert.equal(await page.locator('#ai-settings').isVisible(),false);
  assert.equal(await page.locator('#ai-key').count(),0);
  assert((await page.locator('.cloud-error').innerText()).includes('登录'));
});

test('401 from settings GET, save PUT, or check POST hides the header and clears even the detached input',async t=> {
  for (const method of ['GET','PUT','POST']) {
    let expired = false;
    const secret = 'fictional-TEST-key-401-'+method;
    const {page,state,open} = await fixture(t,{handler:async({call,respond})=> {
      if (!expired || !call.path.startsWith('/care/ai/') || call.method !== method) return false;
      await respond({message:secret,code:secret},401); return true;
    }}); await open();
    await page.locator('#ai-key').fill(secret);
    await page.evaluate(()=> {window.__detachedAIKey = document.getElementById('ai-key');});
    expired = true;
    await page.locator(method === 'GET' ? '#ai-refresh' : method === 'PUT' ? '#ai-save' : '#ai-check').click();
    await page.locator('#account-form').waitFor();
    assert.equal(await page.locator('#ai-settings').isHidden(),true);
    assert.equal(await page.locator('#ai-settings').evaluate(button=>button.hidden),true);
    assert.equal(await page.locator('#ai-key').count(),0);
    assert.equal(await page.evaluate(()=>window.__detachedAIKey.value),'');
    assert(!(await page.locator('body').innerHTML()).includes(secret));
    assert(!state.logs.join('\n').includes(secret));
  }
});

test('session expiry on focus clears the unsent key and hides the entry',async t=> {
  const {page,state,open} = await fixture(t); await open();
  await page.locator('#ai-key').fill('fictional-unsent-expiry-key');
  await page.evaluate(()=> {window.__detachedAIKey = document.getElementById('ai-key');});
  state.identity = null;
  await page.evaluate(()=>window.dispatchEvent(new Event('focus')));
  await page.locator('#account-form').waitFor();
  assert.equal(await page.locator('#ai-settings').evaluate(button=>button.hidden),true);
  assert.equal(await page.evaluate(()=>window.__detachedAIKey.value),'');
});

test('a stale settings 401 cannot sign out a newer settings generation',async t=> {
  let release; const gate = new Promise(resolve=>release=resolve); t.after(()=>release());
  let arrived; const seen = new Promise(resolve=>arrived=resolve);
  const {page,open} = await fixture(t,{handler:async({call,respond})=> {
    if (call.method !== 'PUT') return false;
    arrived(); await gate; await respond({message:'fictional-stale-expiry'},401); return true;
  }}); await open();
  await page.locator('#ai-save').click(); await seen;
  await page.locator('#ai-back').click(); await page.locator('#patient-search').waitFor();
  await open();
  const response = page.waitForResponse(response=>response.url().endsWith('/care/ai/settings') && response.request().method()==='PUT');
  release(); await response;
  await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  assert.equal(await page.locator('#ai-settings').isVisible(),true);
  assert.equal(await page.locator('#ai-form').isVisible(),true);
  assert.equal(await page.locator('#account-form').count(),0);
  assert.equal(await page.locator('.cloud-error').innerText(),'');
});

test('late settings responses cannot replace navigation or a logged-out session',async t=> {
  for (const leave of ['back','logout']) {
    let release; const gate = new Promise(resolve=>release=resolve); t.after(()=>release());
    let arrived; const seen = new Promise(resolve=>arrived=resolve);
    const {page,state,open} = await fixture(t,{handler:async({call,respond})=> {
      if (call.method !== 'PUT') return false;
      arrived(); await gate; await respond({...defaults,model:'deepseek-v4-pro'}); return true;
    }}); await open();
    await page.locator('#ai-key').fill('fictional-race-key'); await page.locator('#ai-save').click(); await seen;
    const response = page.waitForResponse(response=>response.url().endsWith('/care/ai/settings') && response.request().method()==='PUT');
    await page.locator(leave==='back' ? '#ai-back' : '#logout').click();
    await page.locator(leave==='back' ? '#patient-search' : '#account-form').waitFor();
    release(); await response;
    await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
    assert.equal(await page.locator('#ai-form').count(),0);
    assert.equal(await page.locator(leave==='back' ? '#patient-search' : '#account-form').isVisible(),true);
    assert(!state.logs.join('\n').includes('fictional-race-key'));
  }
});

test('role revocation removes settings even when the account id stays the same',async t=> {
  const {page,state,open} = await fixture(t); await open();
  await page.locator('#ai-key').fill('fictional-revoked-key');
  state.identity = {...doctor,role:'PATIENT',patient_id:'fictional-patient'};
  await page.evaluate(()=>window.dispatchEvent(new Event('focus')));
  await page.getByRole('heading',{name:'这是医生工作台',exact:true}).waitFor();
  assert.equal(await page.locator('#ai-settings').isVisible(),false);
  assert.equal(await page.locator('#ai-key').count(),0);
});

test('returning restores patient list and the existing three detail tabs at desktop and mobile widths',async t=> {
  const {page,open} = await fixture(t); await open();
  for (const viewport of [{width:1280,height:940},{width:390,height:844}]) {
    await page.setViewportSize(viewport);
    assert(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth));
    assert.equal(await page.locator('#ai-settings').isVisible(),true);
    assert.equal(await page.locator('#logout').isVisible(),true);
    if (process.env.PORTAL_AI_SCREENSHOT_DIR) await page.screenshot({path:path.join(process.env.PORTAL_AI_SCREENSHOT_DIR,`doctor-ai-settings-${viewport.width}.png`),fullPage:true});
  }
  await page.locator('#ai-back').click(); await page.locator('#patient-search').waitFor();
  await page.locator('[data-patient="fictional-patient"]').click();
  await page.locator('#plans-next').waitFor();
  assert.deepEqual(await page.locator('[data-patient-tab]').allTextContents(),['患者信息','沟通 没有未读','API 用量']);
  await page.locator('[data-patient-tab="usage"]').click(); await page.locator('#patient-usage .cloud-usage').waitFor();
  assert.equal(await page.locator('#patient-info').isVisible(),false);
  assert.equal(await page.locator('#patient-chat').isVisible(),false);
  await open(); await page.locator('#ai-back').click(); await page.locator('#patient-search').waitFor();
});
