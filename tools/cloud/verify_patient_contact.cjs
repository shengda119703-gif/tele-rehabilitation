/* Real browser UI against a loopback test server, using fictional accounts only. */
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path'),crypto=require('node:crypto');
const {chromium}=require('../../ankang/route1-health-agent/node_modules/playwright');
async function verifyPairedRetry(browser){
 const page=await browser.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message));
 try{
  const source=await fs.readFile(path.resolve(__dirname,'../../mobile_rehab/static/unified.js'),'utf8'),start=source.indexOf('async function pairedClinicianContact()'),end=source.indexOf('\nmountPairedClinicianContact();',start);
  assert(start>=0&&end>start);
  await page.route('https://paired-ui.test.invalid/**',route=>route.fulfill({contentType:'text/html',body:'<dialog id="dialog"></dialog>'}));
  await page.goto('https://paired-ui.test.invalid/');
  await page.evaluate(async source=>{
   Object.assign(window,{ui:{busy:false},voiceStarting:false,recorder:null,modalGeneration:0,$:s=>document.querySelector(s),E:v=>String(v??''),stamp:v=>String(v),say:()=>{}});
   window.bind=(id,fn)=>{const button=document.getElementById(id);if(button)button.onclick=fn;};
   window.modal=(title,body)=>{modalGeneration++;const dialog=$('#dialog');dialog.innerHTML='<div class="heading"><h2 id="dialog-title">'+title+'</h2><button id="close-dialog">关闭</button></div>'+body;dialog.showModal();return dialog;};
   window.pairedTest={messages:[],operations:new Map(),sendCalls:0,retryCalls:0,read:0};
   window.api=async(route,body={})=>{
    const action=route.split('.').at(-1),state=window.pairedTest;
    if(action==='identity')return {connected:true,username:'TEST',upload_enabled:false};
    if(action==='messages')return {items:state.messages,next_cursor:state.messages.length,read_cursor:state.read};
    if(action==='read'){state.read=body.cursor;return {};}
    if(action==='retry'){state.retryCalls++;return {};}
    if(action==='send'){
     state.sendCalls++;
     if(!state.operations.has(body.operation_id)){const row={sequence:state.messages.length+1,author_role:'PATIENT',text:body.text,created_at:Date.now()/1000};state.operations.set(body.operation_id,row);state.messages.push(row);}
     if(state.sendCalls===1)throw Error('TEST 已保存，但回执丢失');
     return {};
    }
    throw Error('Unexpected isolated paired operation');
   };
   window.setInterval=callback=>{window.pairedRefresh=callback;return 1;};
   (0,eval)(source);await pairedClinicianContact();
  },source.slice(start,end));
  await page.locator('#paired-message').fill('TEST 原消息');await page.locator('#paired-send-form button[type=submit]').click();await page.getByText('TEST 已保存，但回执丢失',{exact:true}).waitFor();
  await page.locator('#paired-message').fill('TEST 重试期间编辑的新消息');await page.evaluate(()=>pairedRefresh());
  await page.waitForFunction(()=>pairedTest.retryCalls===1&&!document.querySelector('#paired-send-form button[type=submit]').disabled);
  assert.equal(await page.locator('#paired-message').inputValue(),'TEST 重试期间编辑的新消息');
  await page.locator('#paired-send-form button[type=submit]').click();await page.locator('.paired-message').filter({hasText:'TEST 重试期间编辑的新消息'}).waitFor();
  assert.deepEqual(await page.evaluate(()=>({calls:pairedTest.sendCalls,texts:pairedTest.messages.map(m=>m.text)})),{calls:2,texts:['TEST 原消息','TEST 重试期间编辑的新消息']});
 }catch(error){error.message+='\nPaired regression state: '+JSON.stringify(await page.evaluate(()=>({status:document.querySelector('#paired-status')?.textContent,calls:window.pairedTest?.sendCalls,open:document.querySelector('#dialog')?.open,input:document.querySelector('#paired-message')?.value})))+'; errors: '+JSON.stringify(errors);throw error;}
 finally{await page.close();}
}
async function main(){
 const origin=process.argv[2],out=path.resolve(process.argv[3]);
 assert(['127.0.0.1','localhost'].includes(new URL(origin).hostname));assert.equal(new URL(origin).protocol,'http:');
 await fs.mkdir(out,{recursive:false});
 const browser=await chromium.launch({channel:'msedge',headless:true}),pc=await browser.newContext({viewport:{width:390,height:844}}),dc=await browser.newContext();
 const p=await pc.newPage(),d=await dc.newPage(),errors=[];for(const page of[p,d])page.on('pageerror',e=>errors.push(e.message));
 async function api(ctx,route,method='GET',data){
  const me=await ctx.request.get(origin+'/api/cloud/v1/auth/me'),actor=me.ok()?await me.json():{};
  const r=await ctx.request.fetch(origin+'/api/cloud/v1'+route,{method,headers:{Origin:origin,'X-CSRF-Token':actor.csrf_token||''},...(data===undefined?{}:{data})});
  assert(r.ok(),`${route}: ${r.status()} ${await r.text()}`);return r.json();
 }
 async function login(page,name){await page.goto(origin+(name==='doctor'?'/care':'/account'));if(name!=='doctor')await page.locator('#connect-account').click();await page.getByLabel('账号',{exact:true}).fill(name);await page.getByLabel('密码',{exact:true}).fill('1');await page.locator('#account-form button[type=submit]').click();await page.locator('#logout').waitFor({state:'visible'});}
 try{
  const username='qa-contact-'+crypto.randomBytes(5).toString('hex');await api(pc,'/auth/register','POST',{username,password:'1',display_name:'TEST 患者入口验收'});await login(p,username);await p.goto(origin+'/');
  await p.locator('#contact-clinician').click();const dialog=p.locator('#patient-contact');await dialog.getByRole('heading',{name:'首次开通医师沟通'}).waitFor();
  assert.equal(await dialog.locator('.contact-setup [name=owner]').isChecked(),false);assert.equal(await dialog.locator('.contact-setup [name=doctor]').isChecked(),false);assert.equal(await dialog.locator('.contact-setup [name=sync]').isChecked(),false);
  await dialog.locator('.contact-setup [name=owner]').check();await dialog.locator('.contact-setup [name=doctor]').check();await dialog.getByRole('button',{name:'确认并进入对话',exact:true}).click();await dialog.locator('#contact-message').waitFor({state:'visible'});
  assert.equal(await dialog.getByRole('button',{name:'查看本人 AI 用量',exact:true}).count(),0);
  await dialog.getByText('暂无消息',{exact:true}).waitFor();assert.equal(await dialog.locator('.contact-tabs').count(),0);assert.equal(await dialog.getByRole('button',{name:'医生方案',exact:true}).isVisible(),false);
  const composer=await dialog.locator('.contact-composer').boundingBox();assert(composer&&composer.y+composer.height<=844);
  await p.screenshot({path:path.join(out,'patient-empty-chat-phone-TEST.png'),fullPage:true});
  await dialog.locator('#contact-message').fill('TEST 入口验收：请问训练后应注意什么？');await dialog.getByRole('button',{name:'发送',exact:true}).click();await dialog.getByText('TEST 入口验收：请问训练后应注意什么？',{exact:true}).waitFor();
  const actor=await api(pc,'/auth/me'),base='/patients/'+actor.patient_id;
  await login(d,'doctor');await api(dc,base+'/messages','POST',{operation_id:crypto.randomUUID(),text:'TEST 医师回复：这是隔离验收，不是医疗建议。'});
  await p.reload();await p.locator('#contact-clinician').click();await dialog.getByText('TEST 医师回复：这是隔离验收，不是医疗建议。',{exact:true}).waitFor();
  await p.screenshot({path:path.join(out,'patient-chat-phone-TEST.png'),fullPage:true});
  assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await p.waitForFunction(()=>!document.querySelector('#patient-contact .contact-composer button[type=submit]').disabled);
  p.on('dialog',v=>v.accept());await dialog.locator('.contact-file').setInputFiles({name:'TEST-报告原件.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF-1.4\nTEST ONLY')});await dialog.getByText('报告已分享。医师可在后台查看原件。',{exact:true}).waitFor();
  assert.equal((await api(dc,base+'/reports')).items.length,1);
  const failSend=route=>route.request().method()==='POST'&&new URL(route.request().url()).pathname===('/api/cloud/v1'+base+'/messages')?route.abort('internetdisconnected'):route.continue();
  await p.route('**/api/cloud/v1/**',failSend);await dialog.locator('#contact-message').fill('TEST 断网后刷新保留的消息');await dialog.getByRole('button',{name:'发送',exact:true}).click();await dialog.getByText('我 · 待发送',{exact:true}).waitFor();
  await p.reload();await p.locator('#contact-clinician').click();await dialog.getByText('TEST 断网后刷新保留的消息',{exact:true}).waitFor();await dialog.getByText('我 · 待发送',{exact:true}).waitFor();
  await p.screenshot({path:path.join(out,'patient-pending-phone-TEST.png'),fullPage:true});
  await p.unroute('**/api/cloud/v1/**',failSend);await dialog.getByRole('button',{name:'重试待发送消息',exact:true}).click();await dialog.getByText('我 · 待发送',{exact:true}).waitFor({state:'hidden'});
  const messages=await api(pc,base+'/messages?latest=true');assert.equal(messages.items.filter(m=>m.text==='TEST 断网后刷新保留的消息').length,1);
  await dialog.locator('.contact-more summary').click();await dialog.getByRole('button',{name:'医生方案',exact:true}).click();await dialog.getByText('康复医师还没有发布方案。你可以先在对话中说明情况。',{exact:true}).waitFor();assert.equal(await dialog.locator('.contact-composer').isVisible(),false);
  await dialog.locator('.contact-more summary').click();await dialog.getByRole('button',{name:'资料与授权',exact:true}).click();await dialog.getByRole('heading',{name:'资料与授权',exact:true}).waitFor();assert.equal(await dialog.getByRole('button',{name:'查看本人 AI 用量',exact:true}).count(),0);assert.equal(await dialog.getByRole('button',{name:'AI 康复问答',exact:true}).count(),0);
  await p.screenshot({path:path.join(out,'patient-settings-phone-TEST.png'),fullPage:true});
  await p.setViewportSize({width:1280,height:900});await dialog.getByRole('button',{name:'返回医师对话',exact:true}).click();await dialog.getByText('TEST 医师回复：这是隔离验收，不是医疗建议。',{exact:true}).waitFor();await p.waitForFunction(()=>!document.querySelector('#patient-contact .contact-composer button[type=submit]').disabled);await p.screenshot({path:path.join(out,'patient-chat-desktop-TEST.png'),fullPage:true});
  await verifyPairedRetry(browser);
  assert.deepEqual(errors,[]);await fs.writeFile(path.join(out,'result.json'),JSON.stringify({scope:'ISOLATED_LOOPBACK',synthetic:true,explicit_first_setup:true,chat_is_default:true,report_shared:true,refresh_preserves_identity_and_history:true,offline_message_preserved_and_once_only_retry:true,api_tools_absent_from_contact:true,no_management_tabs:true,secondary_actions_in_more:true,composer_visible_at_390px:true,no_horizontal_overflow_at_390px:true,paired_retry_ack_unlocks_next_message_and_preserves_edited_text:true,browser_errors:errors,passed:true},null,2));
 }catch(error){await p.screenshot({path:path.join(out,'failure-patient.png'),fullPage:true}).catch(()=>{});await fs.writeFile(path.join(out,'result.json'),JSON.stringify({passed:false,error:error.message,browser_errors:errors},null,2));throw error;}
 finally{await browser.close();}
}
if(process.argv[2]==='--paired-only'){
 (async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});try{await verifyPairedRetry(browser);console.log('PASS: isolated paired reply recovery keeps edited text and unlocks the next message');}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
}else main().catch(e=>{console.error(e);process.exitCode=1;});
