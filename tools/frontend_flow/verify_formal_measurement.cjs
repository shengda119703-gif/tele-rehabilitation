// Original opt-in HTTP/SQL/YOLO plus prerecorded camera. No measurement mocks.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path'),crypto=require('node:crypto'),{spawn}=require('node:child_process');
const {chromium}=require('../../ankang/route1-health-agent/node_modules/playwright');
async function main(){
 const out=path.resolve(process.argv[2]||'');if(!process.argv[2])throw Error('Fresh isolated QA directory required');await fs.mkdir(out,{recursive:false});
 const root=path.resolve(__dirname,'../..'),data=path.join(out,'host-data'),video=path.join(root,'.runtime/frontend_flow/20261012-u2-observation/shoulder-camera.y4m');
 const hash=async file=>crypto.createHash('sha256').update(await fs.readFile(file)).digest('hex'),inputHash=await hash(video);
 const host=spawn(path.join(root,'rehab_codex_single_camera_v2_1/.venv/Scripts/python.exe'),[path.join(__dirname,'run_capture_host.py'),'--data',data,'--formal-measurement'],{cwd:root,windowsHide:true,stdio:['ignore','pipe','pipe']});
 let log='',exited=false,browser,page;host.stderr.on('data',v=>log+=v);const terminal=new Promise(resolve=>host.once('exit',(code,signal)=>{exited=true;resolve({code,signal});}));
 try{
  const ready=await new Promise((resolve,reject)=>{let buffer='';const timer=setTimeout(()=>reject(Error('Isolated host start timeout')),30000);host.stdout.on('data',v=>{buffer+=v;try{const r=JSON.parse(buffer.split('\n')[0]);clearTimeout(timer);resolve(r);}catch{}});host.once('exit',()=>{clearTimeout(timer);reject(Error('Isolated host exited: '+log));});});
  const desktop=process.argv.includes('--desktop'),base='http://127.0.0.1:'+ready.port;
  browser=await chromium.launch({channel:'msedge',headless:true,args:['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream','--use-file-for-fake-video-capture='+video]});
  const context=await browser.newContext({viewport:desktop?{width:1440,height:940}:{width:390,height:844}});page=await context.newPage();const errors=[],requests=[],responses=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.url().includes('/api/rehab/v2'))requests.push({method:r.method(),path:new URL(r.url()).pathname,seq:r.headers()['x-rehab-seq']??null});});
  page.on('response',r=>{if(r.url().includes('/api/rehab/v2'))responses.push({status:r.status(),path:new URL(r.url()).pathname});});
  await page.goto(base+'/capture?tab=assess');await page.locator('#pair-code').fill('TEST-frontend-isolated-host');await page.locator('#pair-form button').click();
  await page.locator('[data-action="shoulder_abduction"]').click();await page.locator('#formal-entry').click();await page.locator('#live-start').click();
  assert.equal(requests.filter(r=>r.method==='POST').length,0);await page.locator('#live-consent').check();await page.locator('#formal-view').check();
  // Fault only the reply AFTER the actual original operation returned.
  await page.evaluate(()=>{window.__formalReadTrace=[];window.__loseCreate=true;window.__loseFinish=true;const original=api;window.api=async(route,opts)=>{const data=await original(route,opts);if(route.startsWith('/rehab/v2/sessions'))window.__formalReadTrace.push({route,method:opts?.method||'GET',processed:data.processed_count,run_state:data.run_state,observation:data.observation_state,completed:data.snapshot?.completed});if(route==='/rehab/v2/sessions'&&opts?.method==='POST'&&window.__loseCreate){window.__loseCreate=false;throw Error('TEST unreadable original create reply');}if(route.endsWith('/finish')&&window.__loseFinish){window.__loseFinish=false;throw Error('TEST unreadable original finish reply');}return data;};});
  await page.locator('#live-start').click();await page.locator('#live-status').filter({hasText:'TEST unreadable original create reply'}).waitFor();
  const originalCreate=await page.evaluate(()=>formalFlow.adapter.draft.create.idempotency_key);await page.locator('#formal-reconcile').click();await page.locator('#live-status').filter({hasText:'测量已暂停'}).waitFor();
  assert.equal(await page.evaluate(()=>formalFlow.adapter.draft.create.idempotency_key),originalCreate);await page.locator('#live-start').click();
  await page.waitForFunction(()=>formalFlow.sampling&&formalFlow.adapter.snapshot.processed_count>=5,null,{timeout:90000});
  await page.waitForTimeout(4000);await page.screenshot({path:path.join(out,'PRIVATE-measuring.png'),fullPage:true});
  const id=await page.evaluate(()=>formalFlow.adapter.draft.session_id);await page.locator('#formal-pause').click();await page.waitForFunction(()=>formalFlow.adapter.snapshot.run_state==='paused',null,{timeout:30000});
  assert.equal(await page.evaluate(()=>document.querySelector('#live-video').srcObject),null);
  await page.locator('#formal-back').click();await page.locator('#formal-entry').click();await page.locator('#live-status').filter({hasText:'测量已暂停'}).waitFor();assert.equal(await page.evaluate(()=>formalFlow.adapter.draft.session_id),id);
  assert.equal(await page.evaluate(()=>document.querySelector('#live-video').srcObject),null);await page.locator('#live-consent').check();await page.locator('#formal-view').check();await page.locator('#live-start').click();
  await page.waitForFunction(()=>formalFlow.sampling&&formalFlow.adapter.snapshot.control_epoch>=2,null,{timeout:30000});
  await page.locator('#live-stop').click();await page.locator('#live-status').filter({hasText:'保存待核对'}).waitFor();assert.equal(await page.evaluate(()=>document.querySelector('#live-video').srcObject),null);
  const draft=await page.evaluate(()=>formalFlow.adapter.draft);assert.equal(draft.end_requested,true);assert.notEqual(draft.save_state,'COMMITTED');
  await page.reload();await page.locator('[data-tab="assess"]').click();await page.locator('[data-action="shoulder_abduction"]').click();await page.locator('#formal-entry').click();await page.locator('#live-status').filter({hasText:'测量结果已保存'}).waitFor({timeout:30000});
  assert.equal(await page.evaluate(()=>formalFlow.adapter.draft.session_id),id);await page.screenshot({path:path.join(out,'PRIVATE-saved.png'),fullPage:true});
  await page.locator('#formal-history').click();await page.locator('#formal-record').filter({hasText:'测量结果已保存'}).waitFor();await page.screenshot({path:path.join(out,'PRIVATE-original-record.png'),fullPage:true});
  await page.locator('#formal-record-back').click();await page.locator('[data-formal-record]').waitFor();assert.equal(await page.locator('[data-formal-record]').count(),1);
  const history=await(await context.request.get(base+'/api/rehab/v2/sessions')).json(),facts=await(await context.request.get(base+'/api/rehab/v2/sessions/'+id)).json(),canonical=await(await context.request.get(base+'/api/rehab/v2/sessions/'+id+'/commit')).json();
  assert.equal(history.items.length,1);assert.equal(canonical.persistence_state,'finalized');assert.equal(canonical.receipt.commit_id,facts.canonical_commit.commit_id);assert.equal(canonical.receipt.completed_reps,facts.snapshot.completed);assert.equal(facts.frozen_plan.plan.submode,'assessment');assert.equal(facts.end_reason,'user_stopped');assert(facts.processed_count>=5);assert.equal(errors.length,0);assert.equal(await hash(video),inputHash);
  const jobs=await(await context.request.get(base+'/api/jobs?brief=true')).json();assert.equal(jobs.length,0);
  // Ignore permission, leave, then deliver REAL prerecorded media late.
  await page.locator('[data-tab="assess"]').click();await page.locator('[data-action="shoulder_abduction"]').click();await page.locator('#formal-entry').click();await page.locator('#formal-again').click();
  await page.evaluate(()=>{const original=navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);navigator.mediaDevices.getUserMedia=opts=>new Promise((resolve,reject)=>{window.__formalPermission=()=>original(opts).then(stream=>{window.__formalLateStream=stream;resolve(stream);},reject);});});
  await page.locator('#live-consent').check();await page.locator('#formal-view').check();await page.locator('#live-start').click();await page.locator('#formal-back').click();await page.evaluate(()=>window.__formalPermission());
  await page.waitForFunction(()=>window.__formalLateStream?.getTracks().every(t=>t.readyState==='ended'));assert.equal(await page.locator('#formal-area').count(),0);
  assert.equal((await(await context.request.get(base+'/api/rehab/v2/sessions')).json()).items.length,1);
  await page.goto(base+'/capture?tab=assess&experience=legacy');await page.locator('[data-action="shoulder_abduction"]').click();assert.equal(await page.locator('#formal-entry').count(),0);await page.locator('[data-tab="history"]').click();await page.locator('[data-formal-record]').waitFor();assert.equal(await page.locator('[data-formal-record]').count(),1);await page.locator('[data-formal-record]').click();await page.locator('#formal-record').filter({hasText:'测量结果已保存'}).waitFor();
  const result={kind:'actual-original-v2-measurement-browser-flow',viewport:desktop?[1440,940]:[390,844],prerecorded_camera_sha256:inputHash,actual_original_pose_worker:true,physical_camera:false,physical_phone:false,owned_formal_sessions:history.items.length,legacy_jobs:jobs.length,create_posts:requests.filter(r=>r.method==='POST'&&r.path==='/api/rehab/v2/sessions').length,processed_frames:facts.processed_count,completed_reps:facts.snapshot.completed,baseline_observed:!!facts.snapshot.baseline,terminal_reason:facts.end_reason,canonical_snapshot_agree:true,'202_responses':responses.filter(r=>r.status===202).length,create_finish_reply_loss_recovered:true,original_id_restored_paused:true,no_post_without_consent:true,ignored_permission_late_media_released:true,legacy_history_readable:true,no_legacy_summary_rewrite:true,browser_errors:errors,all_goal_complete:false};
  await fs.writeFile(path.join(out,'result.json'),JSON.stringify(result,null,2));await fs.writeFile(path.join(out,'PRIVATE-original-facts.json'),JSON.stringify(facts,null,2));await fs.writeFile(path.join(out,'PRIVATE-requests.json'),JSON.stringify({requests,responses},null,2));console.log(JSON.stringify(result));
 }catch(error){await fs.writeFile(path.join(out,'failure.json'),JSON.stringify({message:error.message},null,2));if(page&&!page.isClosed())await page.screenshot({path:path.join(out,'PRIVATE-failed.png'),fullPage:true}).catch(()=>{});throw error;}
 finally{await browser?.close();if(!exited)await fs.writeFile(path.join(data,'stop-request'),'QA shutdown');let timer;await Promise.race([terminal,new Promise(r=>{timer=setTimeout(r,15000);})]);clearTimeout(timer);if(!exited)host.kill();await fs.writeFile(path.join(out,'host.log'),log);}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
