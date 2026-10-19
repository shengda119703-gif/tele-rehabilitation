/* Isolated browser, actual APK adapters/model, original assessment and training flows.
   User video is only read locally; no cloud, production account or sample history. */
'use strict';
const assert=require('node:assert/strict'),http=require('node:http'),fs=require('node:fs/promises'),path=require('node:path');
const {chromium}=require('../../ankang/route1-health-agent/node_modules/playwright');
const repo=path.resolve(__dirname,'../..'),assets=path.join(repo,'android_offline/build/assets'),out=path.resolve(process.argv[2]||'.runtime/apk-motion-review-20261019');
const input=process.argv[3]||'E:/game/test video/肩外展.mp4';
const mime={'.html':'text/html; charset=utf-8','.js':'application/javascript','.css':'text/css','.json':'application/json','.svg':'image/svg+xml','.webp':'image/webp','.jpg':'image/jpeg','.wasm':'application/wasm','.task':'application/octet-stream'};
const adapters=['engine','product','model-policy','deepseek','store','motion','lin-profile','practice','cloud','account','assessment-run','local-api'].map(n=>'<script src="/local/'+n+'.js"></script>').join('');
(async()=>{
 await fs.mkdir(out,{recursive:true});
 const server=http.createServer(async(req,res)=>{try{
  const url=new URL(req.url,'http://127.0.0.1'),name=url.pathname==='/'?'index.html':url.pathname==='/capture'?'capture.html':url.pathname.slice(1);
  let file=path.resolve(assets,name),data;
  if(!file.startsWith(assets+path.sep))throw Error();
  if(!process.env.ANKANG_REVIEW_PACKAGED){
   if(['index.html','capture.html'].includes(name))data=(await fs.readFile(path.join(repo,'mobile_rehab/static',name==='capture.html'?'index.html':'unified.html'),'utf8')).replace('<head>','<head>'+adapters);
   else if(name.startsWith('static/'))file=path.join(repo,'mobile_rehab',name);
   else if(name.startsWith('local/')&&!['product.js','model-policy.js'].includes(path.basename(name)))file=path.join(repo,'android_offline/web',path.basename(name));
  }
  data??=await fs.readFile(file);res.writeHead(200,{'Content-Type':mime[path.extname(file)]||'application/octet-stream'});res.end(data);
 }catch(e){res.writeHead(404);res.end();}});
 await new Promise(r=>server.listen(0,'127.0.0.1',r));const origin='http://127.0.0.1:'+server.address().port;
 const browser=await chromium.launch({channel:'msedge',headless:true}),errors=[],requests=[],checks=[];
 try{
  const context=await browser.newContext({viewport:{width:430,height:932},deviceScaleFactor:1,isMobile:true,hasTouch:true});
  await context.addInitScript(()=>{localStorage.setItem('ankang-phone-active-1','ankang-phone-product-2');const identity={origin:'https://139.224.216.18',role:'PATIENT',patient_id:'00000000-0000-4000-8000-000000000001',account_id:'00000000-0000-4000-8000-000000000002',username:'isolated-qa-only'};window.OfflineAndroid={accountIdentity:()=>JSON.stringify(identity),cloudConfigured:()=>false};});
  await context.route('**/*',route=>{const u=route.request().url();if(u.startsWith(origin)||u.startsWith('blob:'))return route.continue();requests.push(u);return route.abort();});
  const page=await context.newPage();page.setDefaultTimeout(25000);page.on('pageerror',e=>{errors.push(e.message);console.error('PAGE',e.message);});
  await page.goto(origin+'/capture?tab=assess&entry=assessment');await page.locator('[data-action="shoulder_abduction"]').click();await page.locator('#rv-detail-start').click();
  await page.evaluate(()=>PhoneLocal.store.change(v=>v.cloudIdentity=JSON.parse(OfflineAndroid.accountIdentity())));
  await page.locator('#gallery-file').setInputFiles(input);
  if(process.env.ANKANG_REVIEW_REPLAY){const saved=JSON.parse(await fs.readFile(path.join(out,'qa-assessment.json'),'utf8'));await page.evaluate(async saved=>{PhoneLocal.store.change(v=>v.jobs.push(saved.assessment));await PhoneStore.files.put('video:'+saved.assessment.id,{kind:'video',ownerId:PhoneLocal.store.value.owner,blob:state.file});await PhoneStore.files.put('review:'+saved.assessment.id,{...saved.trace,ownerId:PhoneLocal.store.value.owner});},saved);}
  else{await page.locator('#consent').check();await page.locator('#upload-btn').click();}
  await page.waitForFunction(()=>PhoneLocal.store.value.jobs.at(-1)?.state==='done'||PhoneLocal.store.value.jobs.at(-1)?.state==='failed',null,{timeout:180000});
  let assessment=await page.evaluate(()=>structuredClone(PhoneLocal.store.value.jobs.at(-1)));assert.equal(assessment.state,'done',assessment.message);
  const trace=await page.evaluate(id=>PhoneStore.files.get('review:'+id),assessment.id);await fs.writeFile(path.join(out,'qa-assessment.json'),JSON.stringify({assessment,trace}));
  await page.evaluate(id=>showJob(id),assessment.id);
  await page.waitForSelector('#motion-review');await page.waitForFunction(()=>RehabMotionReview.current?.data?.hasTrace);await page.waitForFunction(()=>document.querySelector('.mr-media video')?.readyState>=2);
  const before=await page.evaluate(()=>JSON.stringify(PhoneLocal.store.value));
  assert(assessment.result.review_trace);if(assessment.result.summary.motion_range)assert.equal(await page.evaluate(()=>RehabMotionReview.current.data.metrics.find(m=>m.key==='angle').value),assessment.result.summary.motion_range.max_deg);
  await page.locator('.mr-media video').evaluate(v=>v.currentTime=4);await page.waitForTimeout(250);await page.screenshot({path:path.join(out,'assessment-collapsed.png')});
  const handle=page.locator('.mr-handle'),box=await handle.boundingBox();await page.mouse.move(box.x+box.width/2,box.y+20);await page.mouse.down();await page.mouse.move(box.x+box.width/2,box.y-230,{steps:12});await page.mouse.up();
  assert.equal(await handle.getAttribute('aria-expanded'),'true');await page.waitForTimeout(300);await page.screenshot({path:path.join(out,'assessment-expanded.png')});
  assert(await page.evaluate(()=>{const v=document.querySelector('.mr-media video'),c=document.querySelector('.mr-overlay');return Math.abs(c.width-v.clientWidth)<1.1&&Math.abs(c.height-v.clientHeight)<1.1;}),'annotation canvas follows expanded video bounds');
  await handle.focus();await page.keyboard.press('Enter');assert.equal(await handle.getAttribute('aria-expanded'),'false');await page.keyboard.press('Enter');assert.equal(await handle.getAttribute('aria-expanded'),'true');
  await page.locator('[data-metric="angle"]').click();assert.equal(await page.locator('.mr-chart').count(),1);
  await page.locator('.mr-play').click();await page.waitForTimeout(500);await page.locator('.mr-play').click();
  await page.locator('.mr-annotation').click();assert.equal(await page.locator('.mr-annotation').getAttribute('aria-pressed'),'false');
  assert.equal(await page.evaluate(()=>JSON.stringify(PhoneLocal.store.value)),before,'presentation does not write records');checks.push('assessment_actual_video_model_trace_replay_swipe_chart_play_overlay_read_only');
  assert(!/完整动作|完成次数|已达计划次数/.test(await page.locator('.mr-view').innerText()));
  await page.locator('.mr-more').evaluate(n=>n.open=true);await page.getByRole('button',{name:'问康复管家',exact:true}).click();await page.locator('#health-back').waitFor();await page.locator('#health-back').click();await page.waitForSelector('#motion-review');assert.equal(await page.locator('.mr-play').count(),1);checks.push('existing_contextual_assistant_return_restores_review_without_paid_request');
  // Per-account, per-job read-only annotation access and missing-cache fallback.
  const apiChecks=await page.evaluate(async id=>{
    const good=await PhoneLocal.request('/jobs/'+id+'/review');const cached=await PhoneStore.files.get('review:'+id);
    await PhoneStore.files.put('review:'+id,{...cached,ownerId:crypto.randomUUID()});let foreign=false;try{await PhoneLocal.request('/jobs/'+id+'/review');}catch(e){foreign=e.status===404;}
    await PhoneStore.files.put('review:'+id,cached);let readOnly=false;try{await PhoneLocal.request('/jobs/'+id+'/review',{method:'POST',body:'{}'});}catch(e){readOnly=e.status===405;}
    return {foreign,readOnly,rows:good.rows.length};
  },assessment.id);assert(apiChecks.foreign&&apiChecks.readOnly&&apiChecks.rows>0);checks.push('annotation_endpoint_owner_and_method_guards');
  await page.locator('.mr-back').click();assert.equal(await page.locator('#motion-review').count(),0);assert.equal(await page.evaluate(()=>document.body.classList.contains('motion-review-open')),false);
  // Generate an actual candidate from this measured assessment; original plan checks apply.
  const plan=await page.evaluate(async()=>(await PhoneLocal.request('/plan',{method:'POST',body:JSON.stringify({general_activity_ok:true,standing_support_ok:true})})).plan);
  assert(plan.items.length);await page.evaluate(p=>startPlanEntry(p,p.items[0]),plan);
  await page.waitForSelector('#motion-review.mr-live');assert(await page.locator('#practice-pause').isVisible());assert(await page.locator('#practice-end').isVisible());assert(await page.locator('#live-start').isVisible());
  await page.locator('.mr-handle').click();await page.getByRole('button',{name:'上传训练录像',exact:true}).click();checks.push('original_guided_training_controls_and_recorded_training_entry');
  await page.locator('#gallery-file').setInputFiles(input);await page.locator('#consent').check();await page.locator('#upload-btn').click();
  await page.waitForFunction(id=>{const j=PhoneLocal.store.value.jobs.at(-1);return j?.id!==id&&['done','failed'].includes(j?.state);},assessment.id,{timeout:180000});
  const training=await page.evaluate(()=>structuredClone(PhoneLocal.store.value.jobs.at(-1)));assert.equal(training.mode,'training');assert.equal(training.state,'done',training.message);
  await page.waitForSelector('#motion-review');await page.waitForFunction(()=>RehabMotionReview.current?.data?.hasTrace);await page.waitForFunction(()=>document.querySelector('.mr-media video')?.readyState>=2);
  await page.locator('.mr-media video').evaluate(v=>v.currentTime=4);await page.waitForTimeout(250);await page.screenshot({path:path.join(out,'training-collapsed.png')});
  assert(await page.evaluate(()=>{const a=document.querySelector('.mr-primary-action').getBoundingClientRect(),s=document.querySelector('.mr-scroll').getBoundingClientRect();return a.top>=s.top&&a.bottom<=s.bottom+1;}),'primary result action fully visible');
  await page.locator('.mr-primary-action').hover();assert.equal(await page.locator('.mr-primary-action').evaluate(n=>getComputedStyle(n).backgroundColor),'rgb(223, 255, 101)');
  await page.getByRole('button',{name:'记录疼痛与疲劳',exact:true}).click();await page.waitForTimeout(300);
  assert(await page.locator('#feedback-form').isVisible());await page.screenshot({path:path.join(out,'training-feedback.png')});
  await page.locator('#pain').evaluate(s=>{s.value='0';s.dispatchEvent(new Event('change'));});await page.locator('#fatigue').evaluate(s=>{s.value='2';s.dispatchEvent(new Event('change'));});
  await page.locator('#feedback-form button').click();await page.waitForFunction(id=>PhoneLocal.store.value.jobs.find(j=>j.id===id)?.feedback?.fatigue===2,training.id);
  await page.waitForFunction(()=>state.tab==='plan'&&state.job===null);
  checks.push('training_actual_bound_plan_video_analysis_and_original_feedback_save');
  await page.evaluate(id=>showJob(id),training.id);await page.waitForSelector('#motion-review');await page.setViewportSize({width:360,height:740});await page.waitForTimeout(200);await page.screenshot({path:path.join(out,'small-phone.png')});
  assert(await page.evaluate(()=>{const a=document.querySelector('.mr-primary-action').getBoundingClientRect(),s=document.querySelector('.mr-scroll').getBoundingClientRect();return a.top>=s.top&&a.bottom<=s.bottom+1;}),'small-screen primary action fully visible');
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.setViewportSize({width:1440,height:1000});await page.waitForTimeout(300);await page.screenshot({path:path.join(out,'desktop.png')});
  // Original preview opens only after explicit consent; moved controls retain IDs/handlers.
  await page.evaluate(()=>{RehabMotionReview.destroy();state.selected='shoulder_abduction';state.training=null;livePage();});await page.waitForSelector('#motion-review.mr-live');
  assert(await page.locator('#live-start').isVisible());assert(await page.locator('#live-consent').isVisible());assert.equal(await page.evaluate(()=>document.querySelector('#live-video').srcObject),null);
  assert.equal(await page.locator('#live-cue').evaluate(n=>getComputedStyle(n).color),'rgb(247, 247, 249)');
  await page.locator('#live-start').click();assert.equal(await page.evaluate(()=>document.querySelector('#live-video').srcObject),null);
  await page.setViewportSize({width:430,height:932});await page.screenshot({path:path.join(out,'live-ready.png')});checks.push('live_original_start_stop_consent_no_automatic_camera');
  await page.evaluate(()=>{state.uploadOwnerGeneration=(state.uploadOwnerGeneration||0)+1;document.body.append(document.createElement('i'));});await page.waitForFunction(()=>!RehabMotionReview.current);checks.push('account_generation_invalidates_view');
  assert.deepEqual(errors,[]);assert.deepEqual(requests,[]);
  const inputSha256=require('node:crypto').createHash('sha256').update(await fs.readFile(input)).digest('hex');
  await fs.writeFile(path.join(out,'browser-checks.json'),JSON.stringify({checks,errors,externalRequests:requests,apiChecks,assessment:{id:assessment.id,summary:assessment.result.summary},training:{id:training.id,summary:training.result.summary},input,inputSha256,packaged:!!process.env.ANKANG_REVIEW_PACKAGED,scope:'isolated browser, QA identity only, no cloud or real account writes'},null,2));
  console.log(JSON.stringify({checks,errors,externalRequests:requests,apiChecks}));
 }finally{await browser.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1;});
