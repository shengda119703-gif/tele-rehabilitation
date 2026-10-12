// Actual APK assets, actual PhoneMotion CPU worker, original Store and local
// routes. Served only to an isolated browser origin, never a user's phone DB.
'use strict';
const fs=require('node:fs/promises'),http=require('node:http'),path=require('node:path'),crypto=require('node:crypto');
const {chromium}=require('../../ankang/route1-health-agent/node_modules/playwright');
async function main(){
 const [videoArg,outArg]=process.argv.slice(2);if(!videoArg||!outArg)throw Error('Supply authorized original shoulder video and a fresh ignored QA directory');
 const root=path.resolve(__dirname,'../..'),assets=path.join(root,'android_offline/build/assets'),video=path.resolve(videoArg),out=path.resolve(outArg);
 await fs.mkdir(out,{recursive:false});const inputHash=crypto.createHash('sha256').update(await fs.readFile(video)).digest('hex');
 let browser,page;const wireApis=[],errors=[];
 const server=http.createServer(async(req,res)=>{try{
  const pathname=new URL(req.url,'http://localhost').pathname;
  if(pathname.startsWith('/api/')){wireApis.push(pathname);res.writeHead(503);res.end('TEST: no Python/cloud API exists at this origin');return;}
  const file=pathname==='/'?path.join(assets,'index.html'):pathname==='/capture'?path.join(assets,'capture.html'):path.resolve(assets,'.'+decodeURIComponent(pathname));
  if(!file.startsWith(assets+path.sep)){res.writeHead(403);res.end();return;}
  const type=file.endsWith('.html')?'text/html':file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':file.endsWith('.json')?'application/json':file.endsWith('.wasm')?'application/wasm':'application/octet-stream';
  res.setHeader('Content-Type',type);res.end(await fs.readFile(file));
 }catch(e){res.writeHead(404);res.end(String(e));}});
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 try{
  browser=await chromium.launch({channel:'msedge',headless:true});const context=await browser.newContext({viewport:{width:390,height:844}});page=await context.newPage();
  page.on('pageerror',e=>errors.push(e.message));
  await context.addInitScript(()=>localStorage.setItem('ankang-phone-active-1','ankang-phone-product-2'));
  const base='http://127.0.0.1:'+server.address().port;
  await page.goto(base+'/');await page.locator('a[href="#rehab"]').first().waitFor();
  await page.goto(base+'/capture?tab=assess');await page.locator('[data-action="shoulder_abduction"]').click();
  await page.locator('#gallery-file').setInputFiles(video);await page.locator('#consent').check();await page.locator('#upload-btn').click();
  await page.waitForFunction(()=>PhoneLocal.store.value.jobs.length===1&&['done','failed'].includes(PhoneLocal.store.value.jobs[0].state),null,{timeout:180000});
  const job=await page.evaluate(()=>PhoneLocal.store.value.jobs[0]);
  await fs.writeFile(path.join(out,'PRIVATE-phone-job.json'),JSON.stringify(job,null,2));
  if(job.state!=='done')throw Error('Original local analysis did not finish: '+job.message);
  const proposal=await page.evaluate(()=>PhoneLocal.proposal());
  if(!proposal.candidates.length)throw Error('Actual local replay is not eligible. Preserve its facts; do not fabricate a grant.');
  await page.locator('#view-plan').click();await page.locator('#activity-ok').check();await page.locator('#support-ok').check();await page.locator('#plan-form button').click();
  await page.locator('#train-next').click();await page.locator('#practice-pause').waitFor();await page.locator('#practice-count').fill('10');
  // Native onPause calls the real same handler; no background catch-up.
  await page.evaluate(()=>offlinePause());await page.locator('#practice-pause').filter({hasText:'继续'}).waitFor();
  await page.locator('#practice-back').click();await page.locator('#train-next').click();
  if(await page.locator('#practice-count').inputValue()!=='10')throw Error('Draft input lost after native pause/navigation');
  // Fault is after the LOCAL authoritative commit, not a mock save response.
  await page.evaluate(()=>{const original=fetch;window.fetch=async(...args)=>{const r=await original(...args);if(String(args[0]).endsWith('/finish')&&r.ok)return new Response('{TEST unreadable receipt',{status:200});return r;};});
  await page.locator('#practice-end').click();await page.locator('#practice-save').filter({hasText:'保存待核对'}).waitFor();
  await page.reload();await page.locator('#train-next').click();await page.locator('#practice-save').filter({hasText:'练习记录已保存在本机'}).waitFor();
  const persisted=await page.evaluate(async()=>({rows:await PhoneLocal.request('/api/practice'),progress:PhoneLocal.planProgress(PhoneLocal.store.value.plans[0]),jobs:PhoneLocal.store.value.jobs.length,backup:await PhoneLocal.backup()}));
  if(persisted.rows.length!==1||persisted.rows[0].state!=='COMMITTED'||persisted.rows[0].context.source_context!=='PHONE_LOCAL:SELF_USE'||persisted.rows[0].self_reported_count!==10||persisted.rows[0].confirmed_count!==null||persisted.rows[0].finish_payload.feedback.pain!==null||persisted.progress.completed!==0)throw Error('Practice source, identity, dose or feedback was changed');
  if(persisted.backup.data.practices.length!==1)throw Error('Original backup dropped independent practice facts');
  await page.locator('#practice-back').click();await page.locator('#schedule-history').click();await page.locator('[data-practice]').click();await page.locator('#practice-save').filter({hasText:'练习记录已保存在本机'}).waitFor();
  await page.screenshot({path:path.join(out,'phone-practice-saved.png'),fullPage:true});
  await page.goto(base+'/capture?tab=plan&experience=legacy');await page.locator('#train-next').click();await page.locator('#gallery-file').waitFor({state:'attached'});
  const afterHash=crypto.createHash('sha256').update(await fs.readFile(video)).digest('hex');
  if(afterHash!==inputHash||wireApis.length||errors.length)throw Error('Input changed, Python API used, or browser exception: '+JSON.stringify({wireApis,errors}));
  const result={kind:'actual-phone-assets-local-worker-and-practice-flow',input_sha256:inputHash,source:'PHONE_LOCAL:SELF_USE',actual_worker:true,actual_store:true,original_jobs:persisted.jobs,visual_count:job.result.summary.completed,visual_coverage:job.result.local_report.validRatio,practice_records:1,practice_count_source:'QA-entered set total; not a performed exercise',self_reported_count:10,confirmed_count:null,formal_plan_progress:0,null_feedback_preserved:true,native_pause_handler_tested:true,refresh_after_committed_reply_fault:true,history_and_backup_preserved:true,legacy_path_works:true,wire_api_requests:wireApis.length,browser_errors:errors,physical_phone_tested:false,physical_camera_used:false};
  await fs.writeFile(path.join(out,'result.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }catch(e){
  await fs.writeFile(path.join(out,'failure.json'),JSON.stringify({kind:'failed-phone-flow-qa',message:e.message,wireApis,browser_errors:errors,physical_phone_tested:false},null,2));
  if(page&&!page.isClosed()){
   await page.screenshot({path:path.join(out,'PRIVATE-failed-page.png'),fullPage:true}).catch(()=>{});
   const facts=await page.evaluate(()=>PhoneLocal.store.value).catch(()=>null);if(facts)await fs.writeFile(path.join(out,'PRIVATE-failed-store.json'),JSON.stringify(facts,null,2));
  }
  throw e;
 }finally{await browser?.close();await new Promise(resolve=>server.close(resolve));}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
