/* Real browser UI against a loopback test server, using fictional accounts only. */
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path'),crypto=require('node:crypto');
const {chromium}=require('../../ankang/route1-health-agent/node_modules/playwright');
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
 async function login(page,name){await page.goto(origin+(name==='doctor'?'/care':'/account'));await page.getByLabel('账号',{exact:true}).fill(name);await page.getByLabel('密码',{exact:true}).fill('1');await page.locator('#account-form button[type=submit]').click();await page.locator('#logout').waitFor({state:'visible'});}
 try{
  const username='qa-contact-'+crypto.randomBytes(5).toString('hex');await api(pc,'/auth/register','POST',{username,password:'1',display_name:'TEST 患者入口验收'});await login(p,username);await p.goto(origin+'/');
  await p.locator('#contact-clinician').click();const dialog=p.locator('#patient-contact');await dialog.getByRole('heading',{name:'首次开通医师沟通'}).waitFor();
  assert.equal(await dialog.locator('.contact-setup [name=owner]').isChecked(),false);assert.equal(await dialog.locator('.contact-setup [name=doctor]').isChecked(),false);assert.equal(await dialog.locator('.contact-setup [name=sync]').isChecked(),false);
  await dialog.locator('.contact-setup [name=owner]').check();await dialog.locator('.contact-setup [name=doctor]').check();await dialog.getByRole('button',{name:'确认并进入对话',exact:true}).click();await dialog.locator('#contact-message').waitFor({state:'visible'});
  assert.equal(await dialog.getByRole('button',{name:'查看本人 AI 用量',exact:true}).count(),0);
  await dialog.locator('#contact-message').fill('TEST 入口验收：请问训练后应注意什么？');await dialog.getByRole('button',{name:'发送给医师',exact:true}).click();await dialog.getByText('TEST 入口验收：请问训练后应注意什么？',{exact:true}).waitFor();
  const actor=await api(pc,'/auth/me'),base='/patients/'+actor.patient_id;
  await login(d,'doctor');await api(dc,base+'/messages','POST',{operation_id:crypto.randomUUID(),text:'TEST 医师回复：这是隔离验收，不是医疗建议。'});
  await p.reload();await p.locator('#contact-clinician').click();await dialog.getByText('TEST 医师回复：这是隔离验收，不是医疗建议。',{exact:true}).waitFor();
  await p.screenshot({path:path.join(out,'patient-chat-phone-TEST.png'),fullPage:true});
  assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  p.on('dialog',v=>v.accept());await dialog.locator('.contact-file').setInputFiles({name:'TEST-报告原件.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF-1.4\nTEST ONLY')});await dialog.getByText('报告已分享。医师可在后台查看原件。',{exact:true}).waitFor();
  assert.equal((await api(dc,base+'/reports')).items.length,1);
  const failSend=route=>route.request().method()==='POST'&&new URL(route.request().url()).pathname===('/api/cloud/v1'+base+'/messages')?route.abort('internetdisconnected'):route.continue();
  await p.route('**/api/cloud/v1/**',failSend);await dialog.locator('#contact-message').fill('TEST 断网后刷新保留的消息');await dialog.getByRole('button',{name:'发送给医师',exact:true}).click();await dialog.getByText('我 · 待发送',{exact:true}).waitFor();
  await p.reload();await p.locator('#contact-clinician').click();await dialog.getByText('TEST 断网后刷新保留的消息',{exact:true}).waitFor();await dialog.getByText('我 · 待发送',{exact:true}).waitFor();
  await p.screenshot({path:path.join(out,'patient-pending-phone-TEST.png'),fullPage:true});
  await p.unroute('**/api/cloud/v1/**',failSend);await dialog.getByRole('button',{name:'重试待发送消息',exact:true}).click();await dialog.getByText('我 · 待发送',{exact:true}).waitFor({state:'hidden'});
  const messages=await api(pc,base+'/messages?latest=true');assert.equal(messages.items.filter(m=>m.text==='TEST 断网后刷新保留的消息').length,1);
  await dialog.getByRole('button',{name:'医生方案',exact:true}).click();await dialog.getByText('康复医师还没有发布方案。你可以先在对话中说明情况。',{exact:true}).waitFor();
  await dialog.getByRole('button',{name:'资料与授权',exact:true}).click();await dialog.getByRole('heading',{name:'资料与授权',exact:true}).waitFor();assert.equal(await dialog.getByRole('button',{name:'查看本人 AI 用量',exact:true}).isVisible(),false);
  await p.screenshot({path:path.join(out,'patient-settings-phone-TEST.png'),fullPage:true});
  await p.setViewportSize({width:1280,height:900});await dialog.getByRole('button',{name:'医师对话',exact:true}).click();await dialog.getByText('TEST 医师回复：这是隔离验收，不是医疗建议。',{exact:true}).waitFor();await p.screenshot({path:path.join(out,'patient-chat-desktop-TEST.png'),fullPage:true});
  assert.deepEqual(errors,[]);await fs.writeFile(path.join(out,'result.json'),JSON.stringify({scope:'ISOLATED_LOOPBACK',synthetic:true,explicit_first_setup:true,chat_is_default:true,report_shared:true,refresh_preserves_identity_and_history:true,offline_message_preserved_and_once_only_retry:true,api_tools_absent_from_chat:true,no_horizontal_overflow_at_390px:true,browser_errors:errors,passed:true},null,2));
 }catch(error){await p.screenshot({path:path.join(out,'failure-patient.png'),fullPage:true}).catch(()=>{});await fs.writeFile(path.join(out,'result.json'),JSON.stringify({passed:false,error:error.message,browser_errors:errors},null,2));throw error;}
 finally{await browser.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
