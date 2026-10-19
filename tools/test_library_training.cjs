/* Isolated APK-assets illustrated practice QA; no real patient/cloud writes. */
'use strict';
const assert=require('node:assert/strict'),http=require('node:http'),fs=require('node:fs/promises'),path=require('node:path');
const {chromium}=require('../ankang/route1-health-agent/node_modules/playwright');
const repo=path.resolve(__dirname,'..'),assets=path.join(repo,'android_offline/build/assets'),out=path.resolve(process.argv[2]||'.runtime/library-training-20261019');
const mime={'.html':'text/html; charset=utf-8','.js':'application/javascript','.css':'text/css','.json':'application/json','.webp':'image/webp','.jpg':'image/jpeg','.png':'image/png','.svg':'image/svg+xml'};
(async()=>{
 await fs.mkdir(out,{recursive:true});const server=http.createServer(async(req,res)=>{try{const url=new URL(req.url,'http://127.0.0.1'),name=url.pathname==='/capture'?'capture.html':url.pathname.slice(1),file=path.resolve(assets,name);if(!file.startsWith(assets+path.sep))throw Error();res.writeHead(200,{'Content-Type':mime[path.extname(file)]||'application/octet-stream'});res.end(await fs.readFile(file));}catch(e){res.writeHead(404);res.end();}});
 await new Promise(r=>server.listen(0,'127.0.0.1',r));const origin='http://127.0.0.1:'+server.address().port,browser=await chromium.launch({channel:'msedge',headless:true}),errors=[],external=[],checks=[];
 try{
  const context=await browser.newContext({viewport:{width:430,height:932},isMobile:true,hasTouch:true});
  await context.addInitScript(()=>{localStorage.setItem('ankang-phone-active-1','ankang-phone-product-2');window.OfflineAndroid={accountIdentity:()=>JSON.stringify({origin:'https://139.224.216.18',role:'PATIENT',patient_id:'00000000-0000-4000-8000-000000000001',account_id:'00000000-0000-4000-8000-000000000002',username:'isolated-training-qa'}),cloudConfigured:()=>false};});
  await context.route('**/*',r=>{const url=r.request().url();if(url.startsWith(origin)||url.startsWith('blob:'))return r.continue();external.push(url);return r.abort();});
  const page=await context.newPage();page.setDefaultTimeout(20000);page.on('pageerror',e=>errors.push(e.message));
  const snapshot=()=>page.evaluate(()=>{const v=PhoneLocal.store.value;return JSON.stringify({owner:v.owner,kv:v.kv,jobs:v.jobs,plans:v.plans,daily:v.daily,practices:v.practices});});
  const stored=()=>page.evaluate(()=>Object.entries(localStorage).filter(([key])=>key.startsWith('ankang-illustrated-practice-1:')).flatMap(([,v])=>JSON.parse(v).records));
  await page.goto(origin+'/capture?tab=assess&entry=library');await page.locator('#rl-search').waitFor();const clinicalBefore=await snapshot();
  const catalogue=JSON.parse(await fs.readFile(path.join(assets,'static/assets/rehab-library-v1/catalogue.json'),'utf8'));
  await page.locator('[data-rl-kind="training"]').click();
  // Every training card has an executable button; none redirects to the assessment picker.
  for(const card of catalogue.actions.filter(a=>a.kind==='training')){
   await page.locator('#rl-search').fill(card.id);await page.locator('[data-rl-card="'+card.id+'"]').click();assert(await page.locator('#rl-train').isVisible(),card.id);assert.equal(await page.locator('#rl-assess').count(),0,card.id);await page.locator('#rl-back').click();
  }checks.push('all_122_training_details_start_training_not_assessment_picker');
  await page.locator('#rl-search').fill('T-LOW-046');await page.locator('[data-rl-card="T-LOW-046"]').click();await page.locator('#rl-train').scrollIntoViewIfNeeded();await page.waitForFunction(()=>document.querySelector('.rl-steps img')?.naturalWidth>0);await page.screenshot({path:path.join(out,'training-detail-button.png')});
  await page.locator('#rl-train').click();await page.locator('#lp-cue').waitFor();assert((await page.locator('.lp-top h1').innerText()).includes('坐姿踝主动背屈'));assert((await page.locator('#lp-cue').innerText()).includes('稳定坐好'));
  await page.waitForFunction(()=>document.querySelector('.lp-picture img')?.naturalWidth>0);await page.waitForTimeout(1100);assert.notEqual(await page.locator('#lp-time').innerText(),'00:00');
  await page.locator('#lp-next').click();assert((await page.locator('#lp-cue').innerText()).includes('向小腿方向'));await page.locator('#lp-previous').click();assert((await page.locator('#lp-cue').innerText()).includes('稳定坐好'));
  await page.locator('#lp-pause').click();const paused=await stored();await page.waitForTimeout(600);assert.deepEqual(await stored(),paused);
  await page.screenshot({path:path.join(out,'ankle-training-paused.png')});await page.locator('#lp-pause').click();await page.waitForTimeout(500);
  // Resource-ready callbacks must never replace an active practice with an evaluation page.
  await page.evaluate(()=>document.dispatchEvent(new Event('rehab-candidate-images-ready')));assert(await page.locator('#lp-cue').isVisible());
  await page.locator('#lp-back').click();await page.locator('#rl-train').waitFor();const draft=(await stored())[0];assert.equal(draft.state,'IN_PROGRESS');assert(draft.elapsed_ms>1000);
  await page.reload();await page.locator('#rl-search').fill('T-LOW-046');await page.locator('[data-rl-card="T-LOW-046"]').click();await page.locator('#rl-train').click();await page.locator('#lp-cue').waitFor();assert.equal((await stored())[0].id,draft.id);
  await page.locator('#lp-end').click();await page.locator('#lp-pain').selectOption('0');await page.locator('#lp-fatigue').selectOption('2');await page.screenshot({path:path.join(out,'training-feedback.png')});
  await page.getByRole('button',{name:'保存训练记录',exact:true}).click();await page.locator('#lp-history').waitFor();const finished=(await stored())[0];assert.equal(finished.state,'FINISHED');assert.equal(finished.feedback.pain,0);assert.equal(finished.feedback.fatigue,2);
  await page.locator('#lp-history').click();await page.locator('[data-library-practice="'+draft.id+'"]').click();await page.locator('#lp-history').waitFor();assert.equal((await stored())[0].elapsed_ms,finished.elapsed_ms);
  checks.push('literal_steps_image_timer_pause_resume_reload_original_id_explicit_feedback_history');
  await page.locator('#lp-again').click();await page.locator('#lp-cue').waitFor();assert.equal((await stored()).length,2);assert.notEqual((await stored())[1].id,draft.id);
  await page.locator('#lp-pause').click();await page.setViewportSize({width:360,height:740});await page.screenshot({path:path.join(out,'small-phone-training.png')});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert(await page.locator('#lp-end').isVisible());assert(await page.locator('#lp-next').isVisible());
  await page.setViewportSize({width:1440,height:1000});await page.screenshot({path:path.join(out,'desktop-training.png')});assert(await page.locator('#lp-cue').isVisible());
  await page.setViewportSize({width:430,height:932});await page.locator('#lp-end').click();
  // Revalidation failure preserves the unfinished draft, never writes into a new owner.
  await page.evaluate(()=>{window.qaOriginalApi=api;api=async function(p,...args){const result=await qaOriginalApi(p,...args);return p==='/practice/context'?{...result,participant_id:'00000000-0000-4000-8000-000000000099'}:result;};});
  await page.getByRole('button',{name:'保存训练记录',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#lp-status')?.textContent.includes('账号已变化'));assert.equal((await stored())[1].state,'IN_PROGRESS');
  await page.evaluate(()=>api=qaOriginalApi);await page.locator('#lp-reason').selectOption('stopped');await page.getByRole('button',{name:'保存训练记录',exact:true}).click();await page.locator('#lp-history').waitFor();
  assert.equal((await stored())[1].finish_reason,'stopped');assert.equal((await stored())[1].feedback.pain,null);
  assert.equal(await snapshot(),clinicalBefore);checks.push('responsive_controls_finished_immutable_new_session_owner_recheck_no_measured_or_plan_writes');
  await page.locator('#lp-history').click();await page.locator('#library-practice-records').waitFor();await page.waitForTimeout(300);await page.screenshot({path:path.join(out,'training-history.png')});
  assert.deepEqual(errors,[]);assert.deepEqual(external,[]);await fs.writeFile(path.join(out,'browser-checks.json'),JSON.stringify({checks,errors,externalRequests:external,records:await stored(),clinicalUnchanged:true,scope:'isolated QA only, no production records, no model/cloud calls'},null,2));console.log(JSON.stringify({checks,errors,externalRequests:external}));
 }finally{await browser.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1;});
