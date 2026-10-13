// Actual packaged UI + CPU vision + real HTTPS API. Native bridge is emulated
// by a bounded Node transport; this is NOT a physical Android/Keystore test.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),http=require('node:http'),path=require('node:path'),crypto=require('node:crypto');
const {chromium}=require('../../ankang/route1-health-agent/node_modules/playwright');
const ORIGIN='https://139.224.216.18',PREFIX='/api/cloud/v1';
async function main(){
 const [privateArg,videoArg,outArg,exercise='shoulder_abduction']=process.argv.slice(2);if(!privateArg||!videoArg||!outArg)throw Error('Private credentials, authorized video and fresh output directory required');
 if(!['shoulder_abduction','fitness_squat'].includes(exercise))throw Error('Unsupported QA exercise');
 const credentials=JSON.parse(await fs.readFile(privateArg,'utf8')),out=path.resolve(outArg),video=path.resolve(videoArg),assets=path.resolve(__dirname,'../../android_offline/build/assets');await fs.mkdir(out,{recursive:false});
 const inputHash=crypto.createHash('sha256').update(await fs.readFile(video)).digest('hex'),errors=[],wire=[];let browser,page,session;
 async function api(route,method='GET',body,token){
  const response=await fetch(ORIGIN+PREFIX+route,{method,redirect:'error',headers:{'Content-Type':'application/json','X-Ankang-Client':'native',...(token?{Authorization:'Bearer '+token}:{})},body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(15000)});
  return{status:response.status,body:await response.json()};
 }
 const signed=await api('/auth/password/login','POST',{username:credentials.username,password:credentials.password,client_kind:'APK'});assert.equal(signed.status,200);session=signed.body;
 const identity={origin:ORIGIN,account_id:session.account_id,patient_id:session.patient_id,username:session.username,role:session.role};
 const initial=await api('/patients/'+identity.patient_id+'/records?offset=0&limit=10','GET',undefined,session.access_token);assert.equal(initial.status,200);const priorCount=initial.body.items.length;
 let dropped=false,appendCalls=0;
 const server=http.createServer(async(req,res)=>{try{const name=new URL(req.url,'http://localhost').pathname;if(name.startsWith('/api/')){wire.push(name);res.writeHead(503);res.end('No Python API at this isolated origin');return;}const file=name==='/'?path.join(assets,'index.html'):name==='/capture'?path.join(assets,'capture.html'):path.resolve(assets,'.'+decodeURIComponent(name));if(!file.startsWith(assets+path.sep)){res.writeHead(403);res.end();return;}res.setHeader('Content-Type',file.endsWith('.html')?'text/html':file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':file.endsWith('.json')?'application/json':file.endsWith('.wasm')?'application/wasm':'application/octet-stream');res.end(await fs.readFile(file));}catch{res.writeHead(404);res.end();}});
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 try{
  browser=await chromium.launch({channel:'msedge',headless:true});const context=await browser.newContext({viewport:{width:390,height:844}});page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  await page.exposeFunction('qaAccountBridge',async(action,text)=>{
   const value=JSON.parse(text);assert.equal(value.patient_id,identity.patient_id);
   if(action==='append'){
    appendCalls++;const result=await api('/patients/'+identity.patient_id+'/record-events','POST',value.document,session.access_token);
    if(!dropped&&result.status===201){dropped=true;return{status:503,body:{message:'QA: committed reply lost'}};}return result;
   }
   if(action==='records')return api('/patients/'+identity.patient_id+'/records?offset=0&limit=10','GET',undefined,session.access_token);
   if(action==='identity')return{status:200,body:identity};
   throw Error('Unsupported QA bridge action');
  });
  await context.addInitScript(value=>{
   localStorage.setItem('ankang-phone-active-1','ankang-phone-cloud-1:'+value.patient_id);
   window.OfflineAndroid={accountIdentity:()=>JSON.stringify(value),accountLogin:()=>{},accountRequest:(id,action,text)=>window.qaAccountBridge(action,text).then(r=>PhoneAccount.reply(id,r.status,JSON.stringify(r.body))).catch(()=>PhoneAccount.reply(id,503,'{"message":"QA transport failed"}'))};
  },identity);
  const local='http://127.0.0.1:'+server.address().port;
  await page.goto(local+'/');await page.waitForFunction(()=>window.PhoneLocal&&PhoneLocal.store.value.kv['profile:'+PhoneLocal.store.value.owner]);
  await page.goto(local+'/capture?tab='+(exercise==='fitness_squat'?'fitness':'assess'));await page.locator('[data-action="'+exercise+'"]').click();await page.locator(exercise==='fitness_squat'?'#fit-gallery-input':'#gallery-file').setInputFiles(video);await page.locator('#consent').check();await page.locator('#upload-btn').click();
  await page.waitForFunction(()=>PhoneLocal.store.value.jobs.length===1&&['done','failed'].includes(PhoneLocal.store.value.jobs[0].state),null,{timeout:180000});
  const job=await page.evaluate(()=>PhoneLocal.store.value.jobs[0]);await fs.writeFile(path.join(out,'PRIVATE-actual-phone-job.json'),JSON.stringify(job,null,2));assert.equal(job.state,'done',job.message);assert(!job.result.local_report.synthetic);
  const first=await page.evaluate(async()=>{try{await PhoneAccount.publish(PhoneLocal.store);return null;}catch(e){return e.message;}});assert.equal(first,'QA: committed reply lost');
  const before=await page.evaluate(()=>structuredClone(PhoneLocal.store.value.cloudOutbox));assert.equal(before.items[0].resource_id,null);
  const second=await page.evaluate(()=>PhoneAccount.publish(PhoneLocal.store,true));assert.equal(second.uploaded,1);
  assert.equal((await page.evaluate(()=>PhoneAccount.publish(PhoneLocal.store,true))).uploaded,0);
  const cloud=await api('/patients/'+identity.patient_id+'/records?offset=0&limit=10','GET',undefined,session.access_token);assert.equal(cloud.status,200);assert.equal(cloud.body.items.length,priorCount+1);
  const afterUpload=await page.evaluate(()=>PhoneLocal.store.value.cloudOutbox.items[0]);const matching=cloud.body.items.find(r=>r.id===afterUpload.resource_id);assert(matching);assert.deepEqual(matching.payload.result.summary,job.result.summary);
  await page.goto(local+'/');await page.getByRole('button',{name:'云账号与结果上传'}).click();await page.getByRole('button',{name:'云记录',exact:true}).click();await page.getByText('云记录已读取（最近10条）',{exact:true}).waitFor();await page.locator('dialog details summary').first().click();await page.screenshot({path:path.join(out,'PRIVATE-phone-cloud-records.png'),fullPage:true});
  const after=await page.evaluate(()=>PhoneLocal.store.value.cloudOutbox);assert.deepEqual(before.items[0].document,after.items[0].document);assert(after.items[0].resource_id);
  const desktop=await api('/auth/password/login','POST',{username:credentials.username,password:credentials.password,client_kind:'DESKTOP'});assert.equal(desktop.status,200);
  const read=await api('/patients/'+identity.patient_id+'/records?offset=0&limit=10','GET',undefined,desktop.body.access_token);assert.deepEqual(read.body.items,cloud.body.items);await api('/auth/logout','POST',{},desktop.body.access_token);
  const web=await browser.newContext({viewport:{width:1440,height:940}}),webPage=await web.newPage();webPage.on('pageerror',e=>errors.push(e.message));await webPage.goto(ORIGIN+'/');await webPage.locator('[name="username"]').fill(credentials.username);await webPage.locator('[name="password"]').fill(credentials.password);await webPage.locator('#account-form button').click();await webPage.locator('.cloud-record').first().waitFor();
  const webRecords=await webPage.evaluate(async(patient)=>{const r=await fetch('/api/cloud/v1/patients/'+patient+'/records');if(!r.ok)throw Error('WEB read failed');return r.json();},identity.patient_id);assert.deepEqual(webRecords.items,cloud.body.items);await webPage.screenshot({path:path.join(out,'PRIVATE-web-cloud-records.png'),fullPage:true});
  assert.equal(inputHash,crypto.createHash('sha256').update(await fs.readFile(video)).digest('hex'));assert.equal(wire.length,0);assert.deepEqual(errors,[]);
  const result={actual_cpu_worker:true,actual_packaged_assets:true,physical_android_tested:false,native_bridge:'Node emulation of bounded HTTPS contract; Java/Keystore not executed',exercise,visual_count:job.result.summary.completed,valid_ratio:job.result.summary.valid_ratio,source:'REPLAY_FILE',input_sha256:inputHash,prior_server_records:priorCount,new_server_records:1,server_record_count:cloud.body.items.length,append_calls:appendCalls,committed_reply_loss_recovered:true,original_payload_unchanged:true,desktop_native_read:true,web_cookie_read:true,browser_errors:errors,local_python_api_calls:wire.length};await fs.writeFile(path.join(out,'result.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }catch(e){await fs.writeFile(path.join(out,'failure.json'),JSON.stringify({message:e.message,errors,wire},null,2));if(page&&!page.isClosed())await page.screenshot({path:path.join(out,'PRIVATE-failure.png'),fullPage:true}).catch(()=>{});throw e;}
 finally{if(session)await api('/auth/logout','POST',{},session.access_token).catch(()=>{});await browser?.close();await new Promise(r=>server.close(r));}
}
main().catch(e=>{console.error(e.message);process.exitCode=1;});
