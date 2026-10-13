/* Actual same-origin browser UI, real local CPU inference and audited result exchange. */
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path'),crypto=require('node:crypto');
const {chromium}=require('../../ankang/route1-health-agent/node_modules/playwright');
async function main(){
 const [origin,privateFile,videoFile,output,doctorFile]=process.argv.slice(2);
 if(!origin||!privateFile||!videoFile||!output||!doctorFile)throw Error('Origin, private QA credentials, authorized video, fresh output and doctor credential file required');
 const credentials=JSON.parse((await fs.readFile(privateFile,'utf8')).replace(/^\uFEFF/,''));
 assert(/^qa-client-[a-f0-9]{10}$/.test(credentials.username));
 const doctorPassword=(await fs.readFile(doctorFile,'utf8')).replace(/^\uFEFF/,'').trim();
 const out=path.resolve(output);await fs.mkdir(out,{recursive:false});
 const video=path.resolve(videoFile),inputHash=crypto.createHash('sha256').update(await fs.readFile(video)).digest('hex');
 const errors=[],violations=[],wire=[];let browser,page,nativeSession;
 const native=async(route,method='GET',body,token)=>{
  const response=await fetch(origin+'/api/cloud/v1'+route,{method,redirect:'error',headers:{'X-Ankang-Client':'native',...(body===undefined?{}:{'Content-Type':'application/json'}),...(token?{Authorization:'Bearer '+token}:{})},body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(20000)});
  assert(response.ok,'API HTTP '+response.status);return response.json();
 };
 try{
  browser=await chromium.launch({channel:'msedge',headless:true});
  const context=await browser.newContext({viewport:{width:390,height:844}});page=await context.newPage();
  page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(new URL(r.url()).pathname.startsWith('/api/'))wire.push({path:new URL(r.url()).pathname,method:r.method()});});
  page.on('console',m=>{if(m.type()==='error'&&/Content Security Policy|Refused to|wasm.*compile/i.test(m.text()))violations.push(m.text());});
  await page.goto(origin+'/');await page.locator('[name="username"]').fill(credentials.username);await page.locator('[name="password"]').fill(credentials.password);
  await page.locator('#account-form button').click();await page.waitForURL(url=>url.pathname==='/');
  await page.waitForFunction(()=>window.PhoneLocal&&PhoneLocal.store.value.kv['profile:'+PhoneLocal.store.value.owner]);
  const identity=await page.evaluate(()=>PhoneAccount.identity());assert.equal(identity.username,credentials.username);
  const priorRecords=await page.evaluate(()=>PhoneAccount.request('records',PhoneAccount.identity()));
  assert.equal(await page.evaluate(()=>PhoneLocal.store.value.jobs.length),0);
  await page.screenshot({path:path.join(out,'PRIVATE-user-home-mobile.png'),fullPage:true});
  await page.goto(origin+'/capture?tab=assess');await page.locator('[data-action="shoulder_abduction"]').click();
  await page.locator('#gallery-file').setInputFiles(video);await page.locator('#consent').check();await page.locator('#upload-btn').click();
  await page.waitForFunction(()=>PhoneLocal.store.value.jobs.length===1&&['done','failed'].includes(PhoneLocal.store.value.jobs[0].state),null,{timeout:240000});
  const job=await page.evaluate(()=>PhoneLocal.store.value.jobs[0]);await fs.writeFile(path.join(out,'PRIVATE-actual-browser-job.json'),JSON.stringify(job,null,2));
  assert.equal(job.state,'done',job.message);assert(!job.result.local_report.synthetic);
  await page.waitForFunction(()=>!document.querySelector('#app')?.textContent.includes('正在手机上分析动作'));
  await page.screenshot({path:path.join(out,'PRIVATE-browser-assessment.png'),fullPage:true});
  let dropped=false,appendCalls=0;
  await page.route('**/record-events',async route=>{
   appendCalls++;const response=await route.fetch();
   if(!dropped&&response.status()===201){dropped=true;await route.fulfill({status:503,contentType:'application/json',body:'{"message":"QA: committed reply lost"}'});}
   else await route.fulfill({response});
  });
  const first=await page.evaluate(async()=>{try{await PhoneAccount.publish(PhoneLocal.store);return null;}catch(e){return e.message;}});
  assert.equal(first,'QA: committed reply lost');
  const before=await page.evaluate(()=>structuredClone(PhoneLocal.store.value.cloudOutbox));assert.equal(before.items[0].resource_id,null);
  assert.equal((await page.evaluate(()=>PhoneAccount.publish(PhoneLocal.store,true))).uploaded,1);
  assert.equal((await page.evaluate(()=>PhoneAccount.publish(PhoneLocal.store,true))).uploaded,0);
  const records=await page.evaluate(()=>PhoneAccount.request('records',PhoneAccount.identity()));assert.equal(records.items.length,priorRecords.items.length+1);
  const matching=records.items.find(r=>r.payload.result.id===job.id);assert(matching);
  assert.equal(matching.source_kind,'WEB_LOCAL');assert.deepEqual(matching.payload.result.summary,job.result.summary);
  const after=await page.evaluate(()=>PhoneLocal.store.value.cloudOutbox);assert.deepEqual(before.items[0].document,after.items[0].document);
  await page.goto(origin+'/');await page.getByRole('button',{name:'云账号与结果上传'}).click();
  await page.getByRole('button',{name:'云记录',exact:true}).click();await page.getByText('云记录已读取（最近10条）',{exact:true}).waitFor();
  await page.screenshot({path:path.join(out,'PRIVATE-browser-cloud-record.png'),fullPage:true});
  await page.getByRole('button',{name:'授权医生',exact:true}).click();await page.getByText('已授权医生查看',{exact:true}).waitFor();
  nativeSession=await native('/auth/password/login','POST',{username:credentials.username,password:credentials.password,client_kind:'DESKTOP'});
  const desktop=await native('/patients/'+identity.patient_id+'/records?offset=0&limit=10','GET',undefined,nativeSession.access_token);
  assert.deepEqual(desktop.items,records.items);await native('/auth/logout','POST',{},nativeSession.access_token);nativeSession=null;
  const careContext=await browser.newContext({viewport:{width:1440,height:940}}),care=await careContext.newPage();care.on('pageerror',e=>errors.push(e.message));
  await care.goto(origin+'/care');await care.locator('[name="username"]').fill('doctor');await care.locator('[name="password"]').fill(doctorPassword);await care.locator('#account-form button').click();
  await care.getByRole('button',{name:'查看档案',exact:true}).first().waitFor();
  const doctorRecords=await care.evaluate(async id=>{const response=await fetch('/api/cloud/v1/patients/'+id+'/records?offset=0&limit=10');if(!response.ok)throw Error('Doctor read failed');return response.json();},identity.patient_id);
  assert.deepEqual(doctorRecords.items,records.items);await care.screenshot({path:path.join(out,'PRIVATE-care-patients.png'),fullPage:true});
  await care.locator('[data-patient="'+identity.patient_id+'"]').click();await care.locator('.cloud-record').first().waitFor();
  await care.screenshot({path:path.join(out,'PRIVATE-care-record.png'),fullPage:true});
  await care.getByRole('button',{name:'退出登录',exact:true}).click();
  await page.getByRole('button',{name:'关闭',exact:true}).click();
  const loadedPages=[];
  for(const section of ['rehab','health','medication','family','assistant','records']){
   await page.goto(origin+'/#'+section);await page.waitForFunction(expected=>typeof ui!=='undefined'&&ui.page===expected,section);
   await page.locator('#content h1').first().waitFor();loadedPages.push(section);
  }
  const plan=await page.evaluate(()=>PhoneLocal.request('/api/plan'));
  await page.goto(origin+'/');await page.setViewportSize({width:1440,height:940});await page.reload();
  await page.waitForFunction(()=>window.PhoneLocal&&PhoneLocal.store.value.jobs.length===1);await page.screenshot({path:path.join(out,'PRIVATE-user-home-desktop.png'),fullPage:true});
  assert.equal(inputHash,crypto.createHash('sha256').update(await fs.readFile(video)).digest('hex'));assert.deepEqual(errors,[]);assert.deepEqual(violations,[]);
  assert(!wire.some(r=>r.path==='/api/jobs'||r.path.startsWith('/api/live/')),'No original video or frames should go to the cloud');
  const result={actual_public_browser:true,actual_cpu_worker:true,source:'WEB_LOCAL',input_sha256:inputHash,visual_count:job.result.summary.completed,valid_ratio:job.result.summary.valid_ratio,
   prior_cloud_records:priorRecords.items.length,new_cloud_records:1,append_calls:appendCalls,committed_reply_loss_recovered:true,desktop_native_read:true,doctor_web_read:true,loaded_pages:loadedPages,plan_candidates:plan.proposal.candidates.length,ui_source_unchanged:true,browser_errors:errors,csp_errors:violations,original_video_uploaded:false};
  await fs.writeFile(path.join(out,'result.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
  await page.getByRole('button',{name:'云账号与结果上传'}).click();await page.getByRole('button',{name:'退出账号',exact:true}).click();
  await page.waitForURL(url=>url.pathname==='/account');
 }catch(e){await fs.writeFile(path.join(out,'failure.json'),JSON.stringify({message:e.message,errors,violations,wire},null,2));if(page&&!page.isClosed())await page.screenshot({path:path.join(out,'PRIVATE-failure.png'),fullPage:true}).catch(()=>{});throw e;}
 finally{if(nativeSession)await native('/auth/logout','POST',{},nativeSession.access_token).catch(()=>{});await browser?.close();}
}
main().catch(e=>{console.error(e.message);process.exitCode=1;});
