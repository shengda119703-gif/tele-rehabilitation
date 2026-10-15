'use strict';
// Isolated browser coverage: all HTTP routes are fulfilled locally, never forwarded.
const {test,before,after} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
let playwright;
try { playwright = require('playwright'); }
catch { playwright = require('../../ankang/route1-health-agent/node_modules/playwright'); }
const root = path.resolve(__dirname,'../..'), origin = 'http://127.0.0.1:19493';
const assets = new Map([
  ['/cloud-static/portal.js',['cloud_service/static/portal.js','application/javascript']],
  ['/cloud-static/portal.css',['cloud_service/static/portal.css','text/css']],
  ...['unified.css','unified-polish.css','controls.css'].map(name=>['/static/'+name,['mobile_rehab/static/'+name,'text/css']])
].map(([url,[file,type]])=>[url,{body:fs.readFileSync(path.join(root,file),'utf8'),contentType:type}]));
const html = fs.readFileSync(path.join(root,'cloud_service/static/index.html'),'utf8');
const doctor = {account_id:'TEST-doctor',role:'DOCTOR_ADMIN',csrf_token:'TEST-csrf'};
const zero = {calls:0,prompt_tokens:0,completion_tokens:0,total_tokens:0,cache_hit_tokens:0,cache_miss_tokens:0,reserved_tokens:0,uncertain_calls:0,unpriced_calls:0,estimated_cost_by_currency:{}};
const measured = {...zero,calls:6,prompt_tokens:900,completion_tokens:300,total_tokens:1200,cache_hit_tokens:700,cache_miss_tokens:200,reserved_tokens:83,uncertain_calls:1,unpriced_calls:2,estimated_cost_by_currency:{CNY:'0.001234',USD:'0.000005'}};
const labels = {CHAT:'普通问答',RESULT_EXPLANATION:'结果解释',CANDIDATE_PLAN:'方案建议',ASSESSMENT_GUIDANCE:'评估指引',REASSESSMENT:'复评建议',LEGACY:'其他'};
const pricing = {version:'TEST-manual-v1',currency:'CNY',cache_hit:'0.5',cache_miss:'2',output:'3'};
function receipt(index = 0) {
  return {id:'TEST-receipt-'+index,operation_id:'TEST-operation-'+index,provider_id:'TEST-provider-'+index,
    purpose:Object.keys(labels)[index%6],model:'TEST-model',state:'SUCCEEDED',created_at:1792022400+index,completed_at:1792022401+index,
    usage:{prompt_tokens:19,completion_tokens:7,total_tokens:26,prompt_cache_hit_tokens:13,prompt_cache_miss_tokens:6},
    pricing,estimated_cost:'0.0000395',answer:'TEST answer <img src=x onerror="window.injected=1">'};
}
function patientUsage(period = '2026-10',offset = 0,budget = {monthly_tokens:200000,monthly_calls:200}) {
  return {period,enabled:true,usage:measured,today:{date:'2026-10-15',usage:period === '2026-10' ? measured : zero},
    days:[{date:period+'-01',usage:measured}],by_purpose:Object.keys(labels).map(purpose=>({purpose,usage:{...zero,calls:1,total_tokens:26}})),
    quota_tokens:budget.monthly_tokens,quota_calls:budget.monthly_calls,remaining_tokens:budget.monthly_tokens-1283,remaining_calls:budget.monthly_calls-6,
    items:offset === 0 ? Array.from({length:30},(_,i)=>receipt(i)) : [receipt(35)],total:31,cost_kind:'ESTIMATE_NOT_INVOICE'};
}
function overview(period = '2026-10',offset = 0) {
  const usage = {...zero,calls:1,prompt_tokens:19,completion_tokens:7,total_tokens:26,cache_hit_tokens:13,cache_miss_tokens:6};
  return {period,usage:measured,items:[{patient_id:offset ? 'TEST-no-grant' : 'TEST-patient',username:'TEST-user-'+offset,
    display_name:offset ? 'TEST 未授权患者' : 'TEST <svg onload="window.injected=1">',usage,
    quota_tokens:200000,quota_calls:200,remaining_tokens:199974,remaining_calls:199}],total:51,offset,limit:50};
}
let browser;
before(async()=> { browser = await playwright.chromium.launch({channel:'msedge',headless:true}); });
after(async()=> { await browser?.close(); });

async function fixture(t,options = {}) {
  const context = await browser.newContext({viewport:{width:1280,height:940}});
  t.after(()=>context.close());
  const page = await context.newPage();
  const state = {identity:options.identity === undefined ? {...doctor} : options.identity,calls:[],unexpected:[],errors:[],budget:{monthly_tokens:200000,monthly_calls:200}};
  page.on('pageerror',e=>state.errors.push(e.message));
  await context.route('**/*',async route=> {
    const req = route.request(),url = new URL(req.url());
    if (url.origin !== origin) { state.unexpected.push(url.href); return route.abort(); }
    if (assets.has(url.pathname)) return route.fulfill(assets.get(url.pathname));
    if (url.pathname === '/static/icon.svg') return route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg"/>'});
    if (['/care','/account'].includes(url.pathname)) return route.fulfill({contentType:'text/html',body:html});
    const call = {path:url.pathname.replace('/api/cloud/v1',''),query:Object.fromEntries(url.searchParams),method:req.method(),headers:req.headers(),data:req.postData() ? req.postDataJSON() : undefined};
    state.calls.push(call);
    const respond = (body,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
    if (options.handler && await options.handler({call,state,respond}) === true) return;
    if (call.path === '/auth/me') return state.identity ? respond(state.identity) : respond({message:'TEST session expired'},401);
    if (call.path === '/auth/password/login') { state.identity = {...doctor}; return respond(state.identity); }
    if (call.path === '/auth/logout') { state.identity = null; return respond({ok:true}); }
    if (call.path === '/care/patients') return respond({items:[{id:'TEST-patient',display_name:'TEST 患者',unread_count:0}],total:1});
    if (call.path === '/care/ai/usage') return respond(overview(call.query.period,Number(call.query.offset)));
    if (call.path === '/patients/TEST-patient/ai/usage') return respond(patientUsage(call.query.period,Number(call.query.offset),state.budget));
    if (call.path === '/patients/TEST-patient/ai/budget' && call.method === 'PUT') { state.budget = {...call.data}; return respond(state.budget); }
    if (call.path === '/patients/TEST-patient') return respond({display_name:'TEST 患者',doctor_access:true});
    if (call.path === '/patients/TEST-no-grant') return respond({message:'当前没有这份患者档案的访问权限。'},404);
    if (call.path === '/care/actions') return respond({items:[]});
    if (call.path.endsWith('/rehab-summary')) return respond({});
    if (call.path.endsWith('/records') || call.path.endsWith('/reports')) return respond({items:[]});
    if (call.path.endsWith('/plans')) return respond({items:[],total:0,current_plan_id:null});
    if (call.path.endsWith('/messages')) return respond({items:[],unread_count:0,has_older:false,next_cursor:0,read_cursor:0});
    state.unexpected.push(call.path); return respond({message:'Unexpected isolated test route'},404);
  });
  await page.goto(origin+(options.entry || '/care'));
  await page.waitForFunction(()=>!document.getElementById('content').textContent.includes('正在读取账号'));
  t.after(()=> { assert.deepEqual(state.errors,[]); assert.deepEqual(state.unexpected,[]); });
  return {page,state,async patient() {
    await page.locator('[data-patient="TEST-patient"]').click(); await page.locator('#plans-next').waitFor();
    await page.locator('#tab-usage').click(); await page.locator('#usage-budget-form').waitFor({state:'attached'});
  },async summary() {
    await page.locator('#ai-usage').click(); await page.locator('#usage-users-next').waitFor();
  }};
}
async function month(page,value) {
  await page.locator('#usage-month-form input').fill(value);
  await page.locator('#usage-month-form button').click();
}
async function frames(page) { await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))); }
function gate(t) {
  let release,arrived;
  const ready = new Promise(resolve=>arrived=resolve),waiting = new Promise(resolve=>release=resolve);
  t.after(()=>release());
  return {ready,waiting,release,arrived};
}

test('summary entry is doctor-only, independent of the simple patient list, and hides on logout or role loss',async t=> {
  for (const options of [{identity:null},{entry:'/account'},{identity:{account_id:'TEST-patient',role:'PATIENT',patient_id:'TEST-patient',csrf_token:'TEST-patient-csrf'}}]) {
    const {page,state} = await fixture(t,options);
    assert.equal(await page.locator('#ai-usage').isVisible(),false);
    assert.equal(state.calls.some(call=>call.path === '/care/ai/usage'),false);
  }
  const {page,state,summary} = await fixture(t);
  await page.locator('#patient-search').waitFor();
  assert.equal(await page.locator('header #ai-usage').isVisible(),true);
  assert.equal(await page.locator('#content .cloud-usage').count(),0);
  assert.equal(await page.locator('#content').getByText('费用估算',{exact:true}).count(),0);
  await summary();
  state.identity = {...doctor,role:'PATIENT',patient_id:'TEST-patient'};
  await page.evaluate(()=>window.dispatchEvent(new Event('focus')));
  await page.getByRole('heading',{name:'这是医生工作台',exact:true}).waitFor();
  assert.equal(await page.locator('#ai-usage').isVisible(),false);
  state.identity = {...doctor}; await page.reload(); await page.locator('#patient-search').waitFor();
  await page.locator('#logout').click(); await page.locator('#account-form').waitFor();
  assert.equal(await page.locator('#ai-usage').isVisible(),false);
});

test('patient tab shows measured month/day/category/cache quotas and paginates all receipts',async t=> {
  const {page,state,patient} = await fixture(t); await patient();
  assert.equal(await page.locator('[data-patient-tab]').count(),3);
  await month(page,'2026-10'); await page.locator('#usage-budget-form').waitFor({state:'attached'});
  const monthly = await page.getByRole('region',{name:'月度用量',exact:true}).innerText();
  for (const value of ['900（已确认部分）','300（已确认部分）','1,200（已确认部分）','700（已确认部分）','200（已确认部分）','198,717','194','83','CNY 0.001234','USD 0.000005']) {
    assert(monthly.includes(value),value);
  }
  for (const label of Object.values(labels)) assert((await page.getByRole('region',{name:'按用途统计',exact:true}).innerText()).includes(label));
  await page.getByText('每日用量',{exact:true}).click();
  assert((await page.locator('#patient-usage').innerText()).includes('2026-10-01'));
  const receipts = page.locator('[aria-label="请求回执"] .cloud-record');
  assert.equal(await receipts.count(),30);
  await receipts.first().locator('details > summary').first().click();
  const detail = await receipts.first().innerText();
  for (const value of ['TEST-receipt-0','TEST-operation-0','TEST-provider-0','TEST-model','已完成','19','7','26','13','6','北京时间','0.0000395']) assert(detail.includes(value),value);
  await receipts.first().getByText('模型单价（每百万 token）',{exact:true}).click();
  assert((await receipts.first().innerText()).includes('TEST-manual-v1'));
  await receipts.first().getByText('完整回执',{exact:true}).click();
  const raw = await receipts.first().locator('pre').innerText();
  assert.deepEqual(JSON.parse(raw),receipt(0));
  assert.equal(await page.evaluate(()=>window.injected),undefined);
  assert.equal(await page.locator('#patient-usage img').count(),0);
  await page.locator('#usage-next').click(); await page.locator('#usage-previous:not([disabled])').waitFor();
  assert.equal(await page.locator('[aria-label="请求回执"] .cloud-record').count(),1);
  assert((await page.locator('[aria-label="请求回执"]').innerText()).includes('其他'));
  assert.equal(await page.locator('#usage-next').isDisabled(),true);
  assert.deepEqual(state.calls.findLast(call=>call.path.endsWith('/ai/usage')).query,{period:'2026-10',offset:'30'});
  await page.locator('#usage-previous').click(); await page.locator('#usage-previous[disabled]').waitFor();
  await month(page,'2026-09'); await page.getByRole('heading',{name:'API 用量 · 2026-09',exact:true}).waitFor();
  const today = await page.getByRole('region',{name:'今日用量',exact:true}).innerText();
  assert(today.includes('2026-10-15')); assert(today.includes('暂无用量')); assert(!today.includes('1,200'));
  assert.deepEqual(state.calls.findLast(call=>call.path.endsWith('/ai/usage')).query,{period:'2026-09',offset:'0'});
});

test('missing usage stays unknown, real zero stays zero, and unknown receipts are not priced from another model',async t=> {
  const unknown = {...receipt(),usage:null,pricing:null,estimated_cost:null,state:'UNMETERED',completed_at:null,model:'TEST-other-model',purpose:'<img src=x>'};
  const {page,patient} = await fixture(t,{handler:async({call,respond})=> {
    if (!call.path.endsWith('/ai/usage')) return false;
    await respond({...patientUsage(call.query.period),usage:{...zero,calls:1,uncertain_calls:1,unpriced_calls:1,total_tokens:null,cache_hit_tokens:null,cache_miss_tokens:undefined},today:null,by_purpose:null,days:null,items:[unknown],total:1}); return true;
  }}); await patient();
  assert((await page.getByRole('region',{name:'月度用量',exact:true}).innerText()).includes('0（已确认部分）'));
  assert((await page.getByRole('region',{name:'今日用量',exact:true}).innerText()).includes('未知'));
  assert((await page.getByRole('region',{name:'按用途统计',exact:true}).innerText()).includes('未知'));
  const item = page.locator('[aria-label="请求回执"] .cloud-record');
  await item.locator('summary').first().click();
  assert((await item.innerText()).includes('用量未知'));
  assert((await item.innerText()).includes('未知用途（<img src=x>）'));
  for (const label of ['输入 token','输出 token','总 token','缓存命中 token','缓存未命中 token','费用估算（非账单）','完成时间']) {
    assert.equal(await item.locator('dl > div').filter({has:page.locator('dt').filter({hasText:new RegExp('^'+label.replace(/[()]/g,'\\$&')+'$')})}).locator('dd').first().innerText(),'未知');
  }
  assert.equal(await item.locator('img').count(),0);
});

test('doctor budget validates integer limits, sends CSRF once, consumes budget response, then reloads meters',async t=> {
  const save = gate(t);
  const {page,state,patient} = await fixture(t,{handler:async({call,state,respond})=> {
    if (!call.path.endsWith('/ai/budget')) return false;
    save.arrived(); await save.waiting; state.budget = {...call.data}; await respond(state.budget); return true;
  }}); await patient();
  await page.locator('#usage-budget-slot summary').click();
  for (const [name,value] of [['monthly_tokens','0'],['monthly_tokens','100000001'],['monthly_tokens','1.5'],['monthly_calls','100001'],['monthly_calls','0'],['monthly_calls','2.5']]) {
    await page.locator('[name="monthly_tokens"]').fill('200000'); await page.locator('[name="monthly_calls"]').fill('200');
    await page.locator(`[name="${name}"]`).fill(value);
    await page.locator('#usage-budget-form').evaluate(form=>form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));
    assert((await page.locator('#usage-budget-status').innerText()).includes('正整数'));
  }
  assert.equal(state.calls.filter(call=>call.method==='PUT').length,0);
  await page.locator('[name="monthly_tokens"]').fill('100000000'); await page.locator('[name="monthly_calls"]').fill('100000');
  const priorProfiles = state.calls.filter(call=>call.path==='/patients/TEST-patient').length;
  await page.locator('#usage-budget-form button').click(); await save.ready;
  assert.equal(await page.locator('#usage-budget-form button').isDisabled(),true);
  await page.locator('#usage-budget-form').evaluate(form=>form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));
  assert.equal(state.calls.filter(call=>call.method==='PUT').length,1);
  save.release(); await page.getByText('每月额度已保存。',{exact:true}).waitFor();
  const call = state.calls.find(call=>call.method==='PUT');
  assert.deepEqual(call.data,{monthly_tokens:100000000,monthly_calls:100000});
  assert.equal(call.headers['x-csrf-token'],doctor.csrf_token);
  assert.equal(call.headers['content-type'],'application/json');
  assert((await page.getByRole('region',{name:'月度用量',exact:true}).innerText()).includes('99,998,717'));
  assert.equal(state.calls.filter(call=>call.path==='/patients/TEST-patient').length,priorProfiles);
  assert.equal(await page.locator('#usage-budget-form button').isEnabled(),true);
});

test('operational summary uses global totals and month/pagination, escapes names, and opens existing granted or ungranted patients honestly',async t=> {
  const {page,state,summary} = await fixture(t); await summary();
  assert((await page.locator('#usage-overview').innerText()).includes('1,200'));
  assert((await page.locator('#usage-patients').innerText()).includes('26'));
  assert.equal(await page.locator('#usage-patients svg').count(),0);
  assert.equal(state.calls.some(call=>call.path.startsWith('/patients/')),false);
  await page.locator('#usage-users-next').click(); await page.locator('[data-usage-patient="TEST-no-grant"]').waitFor();
  assert.equal(await page.locator('#usage-users-next').isDisabled(),true);
  assert.equal(state.calls.findLast(call=>call.path==='/care/ai/usage').query.offset,'50');
  await month(page,'2026-09'); await page.locator('[data-usage-patient="TEST-patient"]').waitFor();
  assert.deepEqual(state.calls.findLast(call=>call.path==='/care/ai/usage').query,{period:'2026-09',offset:'0',limit:'50'});
  await page.locator('[data-usage-patient="TEST-patient"]').click(); await page.locator('#plans-next').waitFor();
  assert.equal(await page.locator('[data-patient-tab]').count(),3);
  await summary(); await page.locator('#usage-users-next').click(); await page.locator('[data-usage-patient="TEST-no-grant"]').click();
  await page.getByRole('heading',{name:'无法打开档案',exact:true}).waitFor();
  assert((await page.locator('#content').innerText()).includes('当前没有这份患者档案的访问权限'));
  await page.locator('#back').click(); await page.locator('#patient-search').waitFor();
});

test('a late patient month response cannot overwrite a newer month or another screen',async t=> {
  for (const leave of ['month','back']) {
    const delayed = gate(t);
    const {page,patient} = await fixture(t,{handler:async({call,respond})=> {
      if (!call.path.endsWith('/ai/usage') || call.query.period !== '2026-08') return false;
      delayed.arrived(); await delayed.waiting; await respond(patientUsage('2026-08')); return true;
    }}); await patient();
    await month(page,'2026-08'); await delayed.ready;
    if (leave === 'month') { await month(page,'2026-09'); await page.getByRole('heading',{name:'API 用量 · 2026-09',exact:true}).waitFor(); }
    else { await page.locator('#back').click(); await page.locator('#patient-search').waitFor(); }
    const response = page.waitForResponse(r=>r.url().includes('period=2026-08'));
    delayed.release(); await response; await frames(page);
    assert.equal(await page.getByRole('heading',{name:'API 用量 · 2026-08',exact:true}).count(),0);
    assert.equal(await page.locator(leave==='month' ? '#usage-budget-form' : '#patient-search').count(),1);
  }
});

test('stale overview successes and 401s cannot overwrite a new month or logged-out session',async t=> {
  for (const leave of ['month','logout']) {
    const delayed = gate(t);
    const {page,summary} = await fixture(t,{handler:async({call,respond})=> {
      if (call.path !== '/care/ai/usage' || call.query.period !== '2026-08') return false;
      delayed.arrived(); await delayed.waiting; await respond(leave==='month' ? {message:'TEST stale expiry'} : overview('2026-08'),leave==='month' ? 401 : 200); return true;
    }}); await summary(); await month(page,'2026-08'); await delayed.ready;
    if (leave==='month') { await month(page,'2026-09'); await page.getByRole('heading',{name:'2026-09 · 月度用量',exact:true}).waitFor(); }
    else { await page.locator('#logout').click(); await page.locator('#account-form').waitFor(); }
    const response = page.waitForResponse(r=>r.url().includes('period=2026-08'));
    delayed.release(); await response; await frames(page);
    assert.equal(await page.locator(leave==='month' ? '#usage-overview' : '#account-form').count(),1);
    assert.equal(await page.locator('#ai-usage').isVisible(),leave==='month');
    assert(!(await page.locator('#content').innerText()).includes('TEST stale expiry'));
  }
});

test('a delayed budget save cannot replace summary navigation or reopen patient details',async t=> {
  const delayed = gate(t);
  const {page,state,patient,summary} = await fixture(t,{handler:async({call,respond})=> {
    if (!call.path.endsWith('/ai/budget')) return false;
    delayed.arrived(); await delayed.waiting; await respond(call.data); return true;
  }}); await patient();
  await page.locator('#usage-budget-slot summary').click(); await page.locator('#usage-budget-form button').click(); await delayed.ready;
  await summary(); const priorReads = state.calls.filter(call=>call.path.endsWith('/ai/usage')).length;
  const response = page.waitForResponse(r=>r.request().method()==='PUT');
  delayed.release(); await response; await frames(page);
  assert.equal(await page.locator('#usage-overview').count(),1);
  assert.equal(await page.locator('#patient-usage').count(),0);
  assert.equal(state.calls.filter(call=>call.path.endsWith('/ai/usage')).length,priorReads);
});

test('summary failure is visible and retryable, budget failure preserves edits, and current 401 clears admin entry',async t=> {
  let summaryStatus = 503,budgetStatus = 403;
  const {page,state,patient} = await fixture(t,{handler:async({call,respond})=> {
    if (call.path === '/care/ai/usage' && summaryStatus) { await respond({message:'TEST 用量汇总暂不可用'},summaryStatus); return true; }
    if (call.path.endsWith('/ai/budget')) { await respond({message:'TEST 没有额度修改权限'},budgetStatus); return true; }
    return false;
  }});
  await page.locator('#ai-usage').click(); await page.getByText('无法读取用量汇总，请重新查询。',{exact:true}).waitFor();
  assert((await page.locator('.cloud-error').innerText()).includes('暂不可用'));
  assert.equal(await page.locator('#usage-users-next').count(),0);
  summaryStatus = 0; await page.locator('#usage-month-form button').click(); await page.locator('#usage-users-next').waitFor();
  await page.locator('#usage-back').click(); await page.locator('#patient-search').waitFor(); await patient();
  await page.locator('#usage-budget-slot summary').click(); await page.locator('[name="monthly_tokens"]').fill('300000');
  await page.locator('#usage-budget-form button').click(); await page.getByText('未能确认额度已保存，请重新读取用量核对后重试。',{exact:true}).waitFor();
  assert.equal(await page.locator('[name="monthly_tokens"]').inputValue(),'300000');
  assert.equal(await page.locator('#usage-budget-form button').isEnabled(),true);
  budgetStatus = 401; state.identity = null; await page.locator('#usage-budget-form button').click(); await page.locator('#account-form').waitFor();
  assert.equal(await page.locator('#ai-usage').isVisible(),false);
});

test('usage and summary fit desktop and mobile widths with existing styles',async t=> {
  const {page,patient,summary} = await fixture(t); await patient();
  for (const view of ['patient','summary']) {
    if (view==='summary') await summary();
    for (const width of [1280,390]) {
      await page.setViewportSize({width,height:940});
      assert(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth),view+' '+width);
      assert.equal(await page.locator('header #ai-usage').isVisible(),true);
      if (process.env.PORTAL_USAGE_SCREENSHOT_DIR) await page.screenshot({path:path.join(process.env.PORTAL_USAGE_SCREENSHOT_DIR,`doctor-usage-${view}-${width}.png`),fullPage:view==='summary'});
    }
  }
});
