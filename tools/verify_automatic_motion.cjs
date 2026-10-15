// Private QA: original APK assets, real CPU worker, original video and Store.
// No Android phone/clinical accuracy is inferred from this browser run.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),http=require('node:http'),path=require('node:path'),crypto=require('node:crypto');
const {chromium}=require('../ankang/route1-health-agent/node_modules/playwright');
async function main(){
 const video=path.resolve(process.argv[2]||''),out=path.resolve(process.argv[3]||'');
 if(!process.argv[2]||!process.argv[3])throw Error('VIDEO and fresh private OUTPUT required');
 const original=await fs.readFile(video),sha=crypto.createHash('sha256').update(original).digest('hex');await fs.mkdir(out,{recursive:false});
 const assets=path.resolve(__dirname,'../android_offline/build/assets'),wire=[],errors=[];let browser,page;
 const server=http.createServer(async(req,res)=>{try{
  const p=new URL(req.url,'http://localhost').pathname;if(p.startsWith('/api/')){wire.push(p);res.writeHead(503);return res.end('PRIVATE QA: no Python/cloud API');}
  const file=p==='/capture'?path.join(assets,'capture.html'):p==='/'?path.join(assets,'index.html'):path.resolve(assets,'.'+decodeURIComponent(p));
  if(!file.startsWith(assets+path.sep)){res.writeHead(403);return res.end();}
  const mime={'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.wasm':'application/wasm'};
  res.setHeader('Content-Type',mime[path.extname(file)]||'application/octet-stream');res.end(await fs.readFile(file));
 }catch(e){res.writeHead(404);res.end(String(e));}});
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 try{
  browser=await chromium.launch({channel:'msedge',headless:true});const context=await browser.newContext({viewport:{width:390,height:844}});
  await context.addInitScript(()=>localStorage.setItem('ankang-phone-active-1','ankang-phone-product-2'));
  page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:'+server.address().port+'/capture?tab=fitness');
  await page.waitForFunction(()=>typeof state!=='undefined'&&state.catalog.length===53);await page.evaluate(async()=>{await PhoneLocal.ready;state.tab='fitness';state.selected='fitness_squat';state.detail=true;fitnessPage();});
  assert.equal(await page.locator('#bar-frame,#bar-confirm,#bar-length,#bar-enable').count(),0);
  await page.screenshot({path:path.join(out,'PRIVATE-mobile-before.png'),fullPage:true});
  await page.locator('#fit-gallery-input').setInputFiles(video);
  assert.equal(await page.locator('#bar-frame,#bar-confirm,#bar-length,#bar-enable').count(),0);
  await page.screenshot({path:path.join(out,'PRIVATE-mobile-selected.png'),fullPage:true});
  await page.locator('#consent').check();await page.locator('#upload-btn').click();
  await page.waitForFunction(()=>state.job,{timeout:30000});
  const id=await page.evaluate(()=>state.job);
  await page.waitForFunction(id=>PhoneLocal.store.value.jobs.some(j=>j.id===id&&['done','failed'].includes(j.state)),id,{timeout:240000});
  const job=await page.evaluate(id=>structuredClone(PhoneLocal.store.value.jobs.find(j=>j.id===id)),id);assert.equal(job.state,'done',job.message);
  assert.equal(job.result.equipment_analysis.mode,'automatic');assert.equal(job.result.barbell.automatic,true);assert.equal(job.result.barbell.calibration.mass_kg,null);
  assert.equal(job.result.barbell.measurement.target_kind,'wrist');assert(job.result.barbell.summary.peak_relative_velocity>0);
  await page.evaluate(id=>showJob(id),id);await page.locator('.bar-report').waitFor();
  await page.waitForFunction(()=>document.querySelector('#fit-video')?.readyState>=2,{timeout:30000});
  await page.locator('[data-bar-peak]').first().click();
  await page.waitForFunction(()=>document.querySelector('#fit-video')?.currentTime>0);
  await page.waitForFunction(()=>!document.querySelector('#fit-video')?.seeking&&document.querySelector('#fit-video')?.readyState>=2);
  await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
  assert((await page.locator('#fit-video').getAttribute('src')).startsWith('blob:'));
  await page.screenshot({path:path.join(out,'PRIVATE-mobile-report.png'),fullPage:true});
  await page.setViewportSize({width:1440,height:940});await page.screenshot({path:path.join(out,'PRIVATE-desktop-report.png'),fullPage:true});
  await page.reload();await page.waitForFunction(()=>typeof PhoneLocal!=='undefined');await page.evaluate(async()=>{await PhoneLocal.ready;});
  const persisted=await page.evaluate(id=>PhoneLocal.store.value.jobs.find(j=>j.id===id),id);assert.equal(persisted.state,'done');assert.equal(persisted.result.barbell.version,'automatic-motion-1');
  const backup=await page.evaluate(async()=>PhoneStore.validateBackup(await PhoneLocal.backup()));assert(backup.jobs.some(j=>j.id===id));
  assert.equal(crypto.createHash('sha256').update(await fs.readFile(video)).digest('hex'),sha);assert.deepEqual(wire,[]);assert.deepEqual(errors,[]);
  const result={kind:'actual-apk-assets-cpu-worker',source_sha256:sha,manual_calibration_steps:0,actual_video:true,actual_cpu_vision_worker:true,physical_phone_tested:false,python_cloud_requests:wire.length,browser_errors:errors,history_survives_reload:true,backup_contains_job:true,processed_frames:job.progress?.processed_frames,summary:job.result.summary,trajectory:job.result.barbell.summary,measurement:job.result.barbell.measurement,performance:job.performance};
  await fs.writeFile(path.join(out,'PRIVATE-job.json'),JSON.stringify(job,null,2));await fs.writeFile(path.join(out,'result.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }catch(e){await fs.writeFile(path.join(out,'failure.json'),JSON.stringify({message:e.message,wire,errors},null,2));if(page&&!page.isClosed())await page.screenshot({path:path.join(out,'PRIVATE-failed.png'),fullPage:true}).catch(()=>{});throw e;}
 finally{await browser?.close();await new Promise(r=>server.close(r));}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
