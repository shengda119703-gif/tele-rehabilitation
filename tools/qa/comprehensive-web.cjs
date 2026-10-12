// Real Edge, visible form actions and public HTTP readback; no DOM/service stubs.
const {chromium}=require('../../ankang/route1-health-agent/node_modules/playwright');
const fs=require('node:fs/promises'),path=require('node:path');
(async()=>{
 const [url,output]=process.argv.slice(2),out=path.resolve(output);await fs.mkdir(out,{recursive:true});
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const context=await browser.newContext({viewport:{width:390,height:844}}),page=await context.newPage();
 page.setDefaultTimeout(12000);const cases=[],errors=[];page.on('pageerror',e=>errors.push(e.message));
 const check=(condition,message)=>{if(!condition)throw Error(message);};
 const nav=async key=>{await page.evaluate(k=>location.hash=k,key);await page.waitForFunction(k=>document.querySelector('#content')&&location.hash==='#'+k&&document.body.dataset.busy!=='true',key);};
 const close=async()=>{if(await page.locator('#dialog[open]').count())await page.locator('#close-dialog').click();};
 const snap=async()=>{const r=await context.request.get(url+'/api/unified');check(r.ok(),'snapshot '+r.status());return (await r.json()).snapshot;};
 const run=async(name,fn)=>{try{await fn();cases.push({name,status:'PASS'});}catch(e){cases.push({name,status:'FAIL',detail:String(e)});}finally{await page.screenshot({path:path.join(out,String(cases.length).padStart(2,'0')+'.png')}).catch(()=>{});await close().catch(()=>{});await fs.writeFile(path.join(out,'results.json'),JSON.stringify({completed:false,cases,errors},null,2));}console.log(JSON.stringify(cases.at(-1)));};
 try{
  await page.goto(url);await page.locator('[name=code]').fill('test-code');await page.locator('#pair-form button').click();await page.locator('#nav:not([hidden])').waitFor();
  for(const [width,height]of [[390,844],[768,1024],[1440,900]])for(const scheme of ['light','dark'])for(const key of ['home','rehab','health','medication','family']){
   await run(`布局 ${key} ${width} ${scheme}`,async()=>{await close();await page.setViewportSize({width,height});await page.emulateMedia({colorScheme:scheme});await nav(key);await page.locator('#content h1').first().waitFor();check(await page.locator('#nav a').count()===5,'five navigation entries');check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2),'horizontal overflow');});
  }
  await page.setViewportSize({width:390,height:844});await page.emulateMedia({colorScheme:'light'});
  await run('档案表单编辑并刷新持久化',async()=>{
   await nav('health');await page.locator('#edit-profile').click();await page.locator('#profile-form [name=name]').fill('TEST Web QA');await page.locator('#profile-form [name=age]').fill('66');await page.locator('#profile-form [name=conditions]').fill('TEST 已知情况');await page.locator('#profile-form button[type=submit]').click();await page.locator('#dialog[open]').waitFor({state:'hidden'});await page.reload();await page.getByText('TEST Web QA · 66 岁',{exact:false}).waitFor();const s=await snap();check(s.profile.profile.name==='TEST Web QA'&&s.profile.profile.age===66,'saved profile mismatch');
  });
  await run('新增药物真实保存',async()=>{
   await nav('medication');await page.locator('#add-med').click();await page.locator('#med-form [name=name]').fill('TEST Browser Medicine');await page.locator('#med-form [name=dose]').fill('TEST existing instruction');await page.locator('#med-form [name=times]').fill('08:00');await page.locator('#med-form button[type=submit]').click();await page.locator('#content strong').filter({hasText:'TEST Browser Medicine'}).waitFor();check((await snap()).profile.profile.medicationRecords.some(m=>m.name==='TEST Browser Medicine'),'medicine not stored');
  });
  await run('服用时间设置与今日安排',async()=>{
   const med=(await snap()).profile.profile.medicationRecords.find(m=>m.name==='TEST Browser Medicine');check(med,'previous medicine missing');await nav('medication');await page.locator(`[data-med="${med.id}"]`).click();await page.locator('#med-times').click();await page.locator('#times-form [name=times]').fill('08:00, 12:00');await page.locator('#times-form button[type=submit]').click();await page.locator('#dialog[open]').waitFor({state:'hidden'});await page.locator('[data-dose]').first().waitFor();check((await snap()).dailyProduct.medSchedules[med.id].times.length===2,'times not saved');
  });
  for(const [key,label]of [['taken','已服用'],['skipped','已跳过'],['unrecorded','未记录']])await run('逐次服药与更正 '+label,async()=>{
   await nav('medication');await page.locator('[data-dose]').first().click();await page.locator('#'+key).click();await page.locator('#dialog[open]').waitFor({state:'hidden'});await page.reload();await page.locator('[data-dose]').first().waitFor();const values=Object.values((await snap()).dailyProduct.doses);check(values.some(v=>v.status===key),'dose status not persisted '+key);
  });
  await run('未来日期禁用服药记录',async()=>{
   await nav('medication');const future=new Date(Date.now()+86400000);const day=[future.getFullYear(),String(future.getMonth()+1).padStart(2,'0'),String(future.getDate()).padStart(2,'0')].join('-');await page.locator('#day').fill(day);await page.locator('#day').dispatchEvent('change');check(await page.locator('[data-dose]').count()>0,'no future dose entries');for(const b of await page.locator('[data-dose]').all())check(await b.isDisabled(),'future dose enabled');
  });
  await run('上传文本资料与原件读取',async()=>{
   await nav('health');await page.locator('#upload').click();await page.locator('#upload-form [name=name]').fill('TEST Web Original');await page.locator('#file').setInputFiles({name:'TEST 中文原件.txt',mimeType:'text/plain',buffer:Buffer.from('TEST ONLY 原始内容')});await page.locator('#upload-form button[type=submit]').click();await page.locator('#dialog[open]').waitFor({state:'hidden'});await page.getByText('TEST Web Original',{exact:true}).waitFor();const a=(await snap()).attachments.find(a=>a.name==='TEST Web Original');check(a,'attachment missing');const r=await context.request.get(url+'/api/product-archive/'+a.id);check((await r.body()).toString()==='TEST ONLY 原始内容','original bytes differ');await page.locator(`[data-archive="${a.id}"]`).click();check(await page.locator('#dialog a[href^="/api/product-archive/"]').count()===1,'original link missing');
  });
  await run('家庭未关联空状态与邀请码弹窗',async()=>{await nav('family');await page.locator('#invite').click();await page.locator('#dialog[open]').waitFor();check((await page.locator('#dialog').innerText()).includes('邀请码'),'invite not visible');check((await snap()).familyMembers.length===0,'invite falsely created relationship');});
  await run('私密聊天标记与备份排除',async()=>{
   await nav('assistant');await page.locator('#private').check();await page.locator('#draft').fill('TEST_WEB_PRIVATE_SENTINEL_20261012');await page.locator('#chat-form button[type=submit]').click();await page.waitForFunction(()=>document.querySelector('#draft')?.value==='');await page.getByText('本次不记录',{exact:false}).first().waitFor();const r=await context.request.get(url+'/api/product-backup');check(!(await r.text()).includes('TEST_WEB_PRIVATE_SENTINEL_20261012'),'private chat leaked in backup');
  });
  await run('刷新后五页与记录入口仍可访问',async()=>{await page.reload();await page.locator('#nav:not([hidden])').waitFor();for(const key of ['home','rehab','health','medication','family','records']){await nav(key);await page.locator('#content h1').first().waitFor();}});
  await run('页面无JavaScript异常',async()=>check(errors.length===0,errors.join('\n')));
  await fs.writeFile(path.join(out,'results.json'),JSON.stringify({completed:true,cases,errors,counts:{PASS:cases.filter(c=>c.status==='PASS').length,FAIL:cases.filter(c=>c.status==='FAIL').length}},null,2));
 }finally{await context.close();await browser.close();}
 process.exitCode=cases.some(c=>c.status==='FAIL')?1:0;
})().catch(e=>{console.error(String(e));process.exitCode=1;});
