// Actual retained /capture -> original plan rule -> SQLite practice adapter.
// Seeds only a COPY of an earlier isolated native-run database, never user DBs.
'use strict';
const fs=require('node:fs/promises'),path=require('node:path'),crypto=require('node:crypto'),{spawn}=require('node:child_process');
const {chromium}=require('../../ankang/route1-health-agent/node_modules/playwright');
async function main(){
 const [sourceArg,outArg]=process.argv.slice(2);if(!sourceArg||!outArg)throw Error('Supply an earlier isolated native run and a fresh QA directory');
 const root=path.resolve(__dirname,'../..'),out=path.resolve(outArg),data=path.join(out,'host-data');await fs.mkdir(out,{recursive:false});
 const host=spawn(path.join(root,'rehab_codex_single_camera_v2_1/.venv/Scripts/python.exe'),[path.join(__dirname,'run_capture_host.py'),'--data',data,'--seed-from-native-run',path.resolve(sourceArg),'--unreadable-practice-finish-reply'],{cwd:root,windowsHide:true,stdio:['ignore','pipe','pipe']});
 let log='',browser,page,exited=false;host.stderr.on('data',v=>log+=v);const terminal=new Promise(resolve=>host.once('exit',(code,signal)=>{exited=true;resolve({code,signal});}));
 try{
  const ready=await new Promise((resolve,reject)=>{let buffer='';const timeout=setTimeout(()=>reject(Error('Host start timed out')),30000);host.stdout.on('data',v=>{buffer+=v;try{const ready=JSON.parse(buffer.split('\n')[0]);clearTimeout(timeout);resolve(ready);}catch{}});host.once('exit',()=>{clearTimeout(timeout);reject(Error('QA host exited: '+log));});});
  const base='http://127.0.0.1:'+ready.port;
  const preview=process.argv.find(a=>a.startsWith('--preview='))?.slice(10);
  browser=await chromium.launch({channel:'msedge',headless:true,args:preview?['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream','--use-file-for-fake-video-capture='+path.resolve(preview)]:[]});const context=await browser.newContext({viewport:{width:390,height:844}});
  const cookie=ready.seed_owner+'.'+crypto.createHmac('sha256','TEST-frontend-isolated-host').update(ready.seed_owner).digest('hex');
  await context.addCookies([{name:'rehab_device',value:cookie,url:base,httpOnly:true,sameSite:'Strict'}]);
  const before=await (await context.request.get(base+'/api/plan')).json();
  if(!before.proposal.candidates.length)throw Error('The actual saved assessment does not qualify; do not fabricate evidence');
  const planReply=await context.request.post(base+'/api/plan',{headers:{'X-Rehab-Client':'mobile-v1'},data:{general_activity_ok:true,standing_support_ok:true,companion_present:false}});
  if(!planReply.ok())throw Error('The original plan gate rejected the QA confirmation: '+await planReply.text());
  page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'/capture?tab=plan');await page.locator('#train-next').click();await page.locator('#practice-pause').waitFor();
  if(preview)await require('./verify_practice_observation.cjs').verifyPracticeObservation(page,out);
  await page.locator('#practice-count').fill('10');await page.locator('#practice-pause').click();
  await page.locator('#practice-back').click();await page.locator('#train-next').click();await page.locator('#practice-count').waitFor();
  if(await page.locator('#practice-count').inputValue()!=='10')throw Error('Explicit count draft lost on navigation');
  await page.locator('#practice-end').click();await page.locator('#practice-save').filter({hasText:'保存待核对'}).waitFor();
  await page.reload();await page.locator('#train-next').click();await page.locator('#practice-save').filter({hasText:'练习记录已保存'}).waitFor();
  await page.screenshot({path:path.join(out,'practice-saved.png'),fullPage:true});
  const rows=await (await context.request.get(base+'/api/practice')).json();
  if(rows.length!==1||rows[0].state!=='COMMITTED'||rows[0].self_reported_count!==10||rows[0].confirmed_count!==null||rows[0].finish_payload.feedback.pain!==null)throw Error('Record identity, source or null feedback was changed');
  await page.locator('[data-tab="history"]').click();await page.locator('[data-practice]').waitFor();await page.locator('[data-practice]').click();await page.locator('#practice-save').filter({hasText:'练习记录已保存'}).waitFor();
  const after=await (await context.request.get(base+'/api/plan')).json();if(after.progress.completed!==0||errors.length)throw Error('Formal progress was changed or browser failed');
  if(process.argv.includes('--feedback'))await require('./verify_feedback_flow.cjs').verifyFeedbackFlow(page,async(route,opts)=>{
   const response=opts?await context.request.post(base+'/api'+route,{headers:{'X-Rehab-Client':'mobile-v1'},data:opts.body}):await context.request.get(base+'/api'+route);
   if(!response.ok())throw Error('Actual owning runtime rejected QA request: '+response.status());return response.json();
  },base,out);
  await page.goto(base+'/capture?tab=plan&experience=legacy');await page.locator('#train-next').click();await page.locator('#gallery-file').waitFor({state:'attached'});
  const legacyRows=await(await context.request.get(base+'/api/practice')).json();if(legacyRows.length!==1)throw Error('Legacy start created another guided record');
  const result={kind:'actual-owned-guided-browser-flow',seed:'copy of previously committed native shoulder-abduction QA record',self_report_input:'QA entered 10, not a performed movement or automatic measurement',finish_reply:'intentionally unreadable after real commit',practice_rows:rows.length,state:rows[0].state,source:rows[0].record_origin,confirmed_count:rows[0].confirmed_count,null_feedback_preserved:true,formal_progress:after.progress.completed,navigation_preserves_count:true,refresh_reconciles_original:true,history_reads_original:true,legacy_starts_original_recording_without_new_practice:true,browser_errors:errors,physical_camera_used:false,target_phone_tested:false};
  await fs.writeFile(path.join(out,'result.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }catch(e){
  await fs.writeFile(path.join(out,'failure.json'),JSON.stringify({kind:'failed-actual-hosted-practice-qa',message:e.message,target_phone_tested:false},null,2));
  if(page&&!page.isClosed()){await page.screenshot({path:path.join(out,'PRIVATE-failed-page.png'),fullPage:true}).catch(()=>{});await fs.writeFile(path.join(out,'PRIVATE-failed-page.html'),await page.content()).catch(()=>{});}
  throw e;
 }finally{
  await browser?.close();if(!exited)await fs.writeFile(path.join(data,'stop-request'),'QA shutdown');
  let timer;await Promise.race([terminal,new Promise(resolve=>{timer=setTimeout(resolve,15000);})]);clearTimeout(timer);if(!exited)host.kill();await fs.writeFile(path.join(out,'host.log'),log);
 }
}
main().catch(e=>{console.error(e);process.exitCode=1;});
