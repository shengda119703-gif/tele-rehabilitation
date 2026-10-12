// Actual hosted original manual-library -> independent practice -> real SQLite.
// This is an explicitly labelled TEST arrangement, not professional clearance.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path'),crypto=require('node:crypto'),{spawn}=require('node:child_process');
const {chromium}=require('../../ankang/route1-health-agent/node_modules/playwright');
async function main(){
 const out=path.resolve(process.argv[2]||'');if(!process.argv[2])throw Error('A fresh isolated QA output directory is required');await fs.mkdir(out,{recursive:false});
 const root=path.resolve(__dirname,'../..'),data=path.join(out,'host-data');
 const host=spawn(path.join(root,'rehab_codex_single_camera_v2_1/.venv/Scripts/python.exe'),[path.join(__dirname,'run_capture_host.py'),'--data',data,'--saved-manual-arrangement-fixture','--unreadable-practice-finish-reply'],{cwd:root,windowsHide:true,stdio:['ignore','pipe','pipe']});
 let log='',exited=false,browser,page;host.stderr.on('data',v=>log+=v);const terminal=new Promise(resolve=>host.once('exit',(code,signal)=>{exited=true;resolve({code,signal});}));
 try{
  const ready=await new Promise((resolve,reject)=>{let buffer='';const timer=setTimeout(()=>reject(Error('Isolated host start timeout')),30000);host.stdout.on('data',v=>{buffer+=v;try{const r=JSON.parse(buffer.split('\n')[0]);clearTimeout(timer);resolve(r);}catch{}});host.once('exit',()=>{clearTimeout(timer);reject(Error('Isolated host exited: '+log));});});
  const base='http://127.0.0.1:'+ready.port;browser=await chromium.launch({channel:'msedge',headless:true});const context=await browser.newContext({viewport:{width:390,height:844}});
  const cookie=ready.seed_owner+'.'+crypto.createHmac('sha256','TEST-frontend-isolated-host').update(ready.seed_owner).digest('hex');await context.addCookies([{name:'rehab_device',value:cookie,url:base,httpOnly:true,sameSite:'Strict'}]);
  const before=await(await context.request.get(base+'/api/plan')).json();assert.equal(before.proposal.candidates.length,0);assert.equal(before.plan.record_origin,'manual');
  page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));await page.goto(base+'/capture?tab=plan');
  await page.locator('#manual-arrangements').waitFor({state:'visible'});await page.locator('#manual-arrangements summary').click();await page.locator('[data-manual-entry]').click();
  assert.equal(await page.locator('#manual-confirm').isChecked(),false);assert.equal(await page.locator('#manual-companion').isChecked(),false);assert.equal(await page.getByText('自动计划规则版本无效，请重新生成',{exact:true}).count(),0);
  await page.screenshot({path:path.join(out,'PRIVATE-manual-arrangement.png'),fullPage:true});
  await page.locator('#manual-confirm').check();await page.locator('#manual-confirm-form button').click();await page.locator('#practice-pause').waitFor();
  assert.equal(await page.evaluate(()=>practiceJourney.running),true);const identity=await page.evaluate(()=>practiceJourney.start.operation_id);
  await page.locator('#practice-count').fill('3');await page.locator('#practice-back').click();await page.locator('#manual-arrangements summary').click();await page.locator('[data-manual-entry]').click();await page.locator('#practice-pause').waitFor();
  assert.equal(await page.locator('#practice-count').inputValue(),'3');assert.equal(await page.evaluate(()=>practiceJourney.start.operation_id),identity);assert.equal(await page.locator('#manual-confirm-form').count(),0);
  await page.locator('#practice-end').click();await page.locator('#practice-save').filter({hasText:'保存待核对'}).waitFor();await page.reload();
  await page.locator('#manual-arrangements summary').click();await page.locator('[data-manual-entry]').click();await page.locator('#practice-save').filter({hasText:'练习记录已保存'}).waitFor();
  await page.screenshot({path:path.join(out,'PRIVATE-manual-saved.png'),fullPage:true});
  const rows=await(await context.request.get(base+'/api/practice')).json();assert.equal(rows.length,1);assert.equal(rows[0].id,identity);assert.equal(rows[0].state,'COMMITTED');assert.equal(rows[0].self_reported_count,3);assert.equal(rows[0].confirmed_count,null);assert.equal(rows[0].formal_plan_ref,null);assert.equal(rows[0].assessment_ref,null);
  const after=await(await context.request.get(base+'/api/plan')).json();assert.deepEqual(after.plan,before.plan);assert.equal(after.progress.completed,0);assert.equal(after.proposal.candidates.length,0);
  await page.locator('[data-tab="history"]').click();await page.locator('[data-practice]').click();await page.locator('#practice-save').filter({hasText:'练习记录已保存'}).waitFor();assert.equal(await page.evaluate(()=>practiceJourney.start.operation_id),identity);
  await page.goto(base+'/capture?tab=plan&experience=legacy');await page.locator('#plan-content .card').first().waitFor();assert.equal(await page.locator('#manual-arrangements').count(),0);assert.equal(errors.length,0);
  const result={kind:'actual-hosted-saved-manual-arrangement-browser-flow',arrangement_source:'original owned manual library; explicit TEST dose 7 reps x 2 sets, not a generated prescription',no_qualified_assessment_created:true,no_automatic_candidate_created:true,one_original_practice_record:true,confirmed_count:null,self_reported_count:3,count_source:'explicit QA entry, not body motion',formal_plan_contribution:null,original_arrangement_unchanged:true,explicit_confirmation_initially_unchecked:true,navigation_and_finish_reply_fault_keep_original_identity:true,return_does_not_repeat_original_confirmation:true,history_reads_original:true,legacy_disables_new_entry_without_deleting_fact:true,browser_errors:errors,physical_phone_tested:false};
  await fs.writeFile(path.join(out,'result.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }catch(error){await fs.writeFile(path.join(out,'failure.json'),JSON.stringify({message:error.message},null,2));if(page&&!page.isClosed())await page.screenshot({path:path.join(out,'PRIVATE-failed-page.png'),fullPage:true}).catch(()=>{});throw error;}
 finally{await browser?.close();if(!exited)await fs.writeFile(path.join(data,'stop-request'),'QA shutdown');let timer;await Promise.race([terminal,new Promise(resolve=>{timer=setTimeout(resolve,15000);})]);clearTimeout(timer);if(!exited)host.kill();await fs.writeFile(path.join(out,'host.log'),log);}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
