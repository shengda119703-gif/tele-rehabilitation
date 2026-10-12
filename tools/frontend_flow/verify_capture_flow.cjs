// Actual browser -> owned FastAPI -> original analyzer -> original SQLite.
// Only the POST reply is made unreadable, after the real upload is accepted.
'use strict';
const fs=require('node:fs/promises'),path=require('node:path'),crypto=require('node:crypto');
const {spawn}=require('node:child_process');
const {chromium}=require('../../ankang/route1-health-agent/node_modules/playwright');
async function main(){
 const [videoArg,outputArg]=process.argv.slice(2);if(!videoArg||!outputArg)throw Error('Supply an authorized original video and a new isolated QA directory.');
 const root=path.resolve(__dirname,'../..'),video=path.resolve(videoArg),output=path.resolve(outputArg),data=path.join(output,'host-data');
 await fs.mkdir(output,{recursive:false});const videoHash=crypto.createHash('sha256').update(await fs.readFile(video)).digest('hex');
 const host=spawn(path.join(root,'rehab_codex_single_camera_v2_1/.venv/Scripts/python.exe'),[path.join(__dirname,'run_capture_host.py'),'--data',data,'--unreadable-upload-reply'],{cwd:root,windowsHide:true,stdio:['ignore','pipe','pipe']});
 let hostLog='',browser;host.stderr.on('data',chunk=>{hostLog+=chunk;});
 const terminal=new Promise(resolve=>host.once('exit',(code,signal)=>resolve({code,signal})));let exited=false;terminal.then(()=>{exited=true;});
 try{
  const port=await new Promise((resolve,reject)=>{let text='';const timer=setTimeout(()=>reject(Error('Isolated host did not start')),30000);host.stdout.on('data',chunk=>{text+=chunk;const line=text.split('\n')[0];try{const ready=JSON.parse(line);clearTimeout(timer);resolve(ready.port);}catch{}});host.once('exit',()=>{clearTimeout(timer);reject(Error('Isolated host exited before ready: '+hostLog));});});
  browser=await chromium.launch({channel:'msedge',headless:true});const context=await browser.newContext({viewport:{width:390,height:844}}),page=await context.newPage(),errors=[],calls=[];
  page.on('pageerror',error=>errors.push(error.message));page.on('request',request=>{const url=new URL(request.url());if(url.pathname.startsWith('/api/'))calls.push({method:request.method(),path:url.pathname,operation:request.headers()['x-rehab-upload-operation']||null});});
  await page.goto('http://127.0.0.1:'+port+'/capture?tab=assess');await page.locator('#pair-code').fill('TEST-frontend-isolated-host');await page.locator('#pair-form button').click();
  await page.locator('[data-action="shoulder_abduction"]').click();await page.locator('#gallery-file').setInputFiles(video);await page.locator('#consent').check();
  await page.locator('#upload-btn').click();
  await page.waitForFunction(()=>state.uploadRecovery===null&&typeof state.job==='string',{},{timeout:30000});
  const jobId=await page.evaluate(()=>state.job),operation=calls.find(c=>c.method==='POST'&&c.path==='/api/jobs')?.operation;
  if(!operation)throw Error('Production upload did not bind its operation key');
  const deadline=Date.now()+180000;let job;
  while(Date.now()<deadline){const reply=await context.request.get('http://127.0.0.1:'+port+'/api/jobs/'+jobId,{headers:{'X-Rehab-Client':'mobile-v1'}});if(!reply.ok())throw Error('Original job query failed: '+reply.status());job=await reply.json();if(['done','failed'].includes(job.state))break;await new Promise(resolve=>setTimeout(resolve,1000));}
  if(job?.state!=='done')throw Error('Actual analysis did not finish: '+JSON.stringify({state:job?.state,message:job?.message}));
  await page.evaluate(id=>showJob(id),jobId);await page.locator('#view-plan').waitFor();await page.screenshot({path:path.join(output,'PRIVATE-result.png'),fullPage:true});
  await page.locator('[data-tab="history"]').click();await page.locator('[data-job="'+jobId+'"]').waitFor();await page.reload();await page.locator('[data-tab="history"]').click();await page.locator('[data-job="'+jobId+'"]').waitFor();
  const rows=await (await context.request.get('http://127.0.0.1:'+port+'/api/jobs?brief=true',{headers:{'X-Rehab-Client':'mobile-v1'}})).json();
  if(rows.length!==1||calls.filter(c=>c.method==='POST'&&c.path==='/api/jobs').length!==1||errors.length)throw Error('Duplicate job, upload or browser exception');
  const afterHash=crypto.createHash('sha256').update(await fs.readFile(video)).digest('hex');if(afterHash!==videoHash)throw Error('Original input changed');
  const result={kind:'actual-hosted-browser-flow',input_sha256:videoHash,reply_fault:'unreadable-post-reply-after-real-upload',post_uploads:1,owned_jobs:rows.length,operation_receipt_queries:calls.filter(c=>c.path.startsWith('/api/uploads/')).length,job_state:job.state,saved_session:typeof job.result?.session_id==='string',summary:job.result?.summary,history_survives_reload:true,browser_errors:errors,physical_camera_used:false,target_phone_tested:false};
  await fs.writeFile(path.join(output,'result.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }finally{
  await browser?.close();if(!exited)await fs.writeFile(path.join(data,'stop-request'),'QA shutdown');
  let stopTimer;const result=await Promise.race([terminal,new Promise(resolve=>{stopTimer=setTimeout(()=>resolve(null),15000);})]);clearTimeout(stopTimer);
  if(!result&&!exited)host.kill();await fs.writeFile(path.join(output,'host.log'),hostLog);
 }
}
main().catch(error=>{console.error(error);process.exitCode=1;});
