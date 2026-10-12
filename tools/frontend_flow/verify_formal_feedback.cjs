// Original HTTP/SQLite feedback; every score below is explicit QA input, not a patient finding.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path');
module.exports=async function verify({page,context,base,out,id}){
 const endpoint=base+'/api/rehab/v2/sessions/'+id,read=async()=>{const r=await context.request.get(endpoint);assert.equal(r.status(),200);return r.json();};
 const before=await read(),posts=[];
 page.on('request',r=>{if(r.method()==='POST'&&r.url()===endpoint+'/feedback')posts.push(r.postDataJSON());});
 const open=async()=>{await page.goto(base+'/capture?tab=history');await page.locator('[data-formal-record="'+id+'"]').click();await page.locator('#formal-feedback-save').waitFor();await page.waitForFunction(()=>!document.querySelector('#formal-feedback-save').disabled);};
 await page.waitForFunction(()=>document.querySelector('#formal-feedback-save')&&!document.querySelector('#formal-feedback-save').disabled);
 assert.equal(before.feedback_revision,0);assert.equal(await page.locator('#formal-feedback-pain').inputValue(),'');assert.equal(await page.locator('#formal-feedback-fatigue').inputValue(),'');
 // The end-region scenario deliberately left a note; explicitly clear it for this empty-form case.
 await page.locator('#formal-feedback-notes').fill('');
 await page.locator('#formal-feedback-save').click();assert.equal(posts.length,0);assert.equal((await read()).feedback_revision,0);
 await page.locator('#formal-feedback-notes').fill('TEST explicit QA draft, not a patient statement');await page.locator('#formal-feedback-later').click();await open();
 assert.equal(await page.locator('#formal-feedback-notes').inputValue(),'TEST explicit QA draft, not a patient statement');assert.equal((await read()).feedback_revision,0);
 await page.locator('#formal-feedback-fatigue').fill('2');
 await page.evaluate(()=>{const original=fetch;let lose=true;window.fetch=async(route,opts)=>{const result=await original(route,opts);if(String(route).endsWith('/feedback')&&opts?.method==='POST'&&lose){lose=false;throw Error('TEST feedback reply lost AFTER original commit');}return result;};});
 await page.locator('#formal-feedback-save').click();await page.locator('#formal-feedback-status').filter({hasText:'感受保存待核对'}).waitFor();
 assert.equal((await read()).feedback_revision,1);assert.equal((await read()).latest_feedback.pain,null);assert.equal(posts.length,1);const first=posts[0];
 await open();await page.locator('#formal-feedback-status').filter({hasText:'感受已保存'}).waitFor();assert.equal(posts.length,2);assert.deepEqual(posts[1],first);
 assert.equal(await page.locator('#formal-feedback-pain').inputValue(),'');assert.equal(await page.locator('#formal-feedback-fatigue').inputValue(),'2');
 await page.screenshot({path:path.join(out,'PRIVATE-feedback-recovered.png'),fullPage:true});
 // Actual other-edit transaction between staging and the original attempted POST.
 await page.evaluate(()=>{const original=fetch;let collide=true;window.fetch=async(route,opts)=>{if(String(route).endsWith('/feedback')&&opts?.method==='POST'&&collide){collide=false;const request=JSON.parse(opts.body),result=await original(route,{...opts,body:JSON.stringify({...request,idempotency_key:newUploadOperation(),feedback:{pain:null,fatigue:3,reason:'not_recorded',notes:'TEST explicit QA other edit'}})});if(!result.ok)throw Error('TEST other edit was rejected');}return original(route,opts);};});
 await page.locator('#formal-feedback-fatigue').fill('4');await page.locator('#formal-feedback-notes').fill('TEST explicit QA local edit');await page.locator('#formal-feedback-save').click();
 await page.locator('#formal-feedback-use-latest').waitFor();assert.equal((await read()).feedback_revision,2);assert.equal(await page.locator('#formal-feedback-fatigue').inputValue(),'4');
 await page.screenshot({path:path.join(out,'PRIVATE-feedback-conflict.png'),fullPage:true});
 const rejected=posts.at(-1);await page.locator('#formal-feedback-replace').click();await page.locator('#formal-feedback-status').filter({hasText:'感受已保存'}).waitFor();
 const replaced=posts.at(-1);assert.notEqual(replaced.idempotency_key,rejected.idempotency_key);assert.equal(replaced.expected_revision,2);assert.deepEqual(replaced.feedback,rejected.feedback);
 // Same current values converge against the actual latest record, without an unnecessary conflict card.
 await page.evaluate(()=>{const original=fetch;let collide=true;window.fetch=async(route,opts)=>{if(String(route).endsWith('/feedback')&&opts?.method==='POST'&&collide){collide=false;const request=JSON.parse(opts.body),result=await original(route,{...opts,body:JSON.stringify({...request,idempotency_key:newUploadOperation()})});if(!result.ok)throw Error('TEST matching other edit was rejected');}return original(route,opts);};});
 await page.locator('#formal-feedback-fatigue').fill('5');await page.locator('#formal-feedback-save').click();await page.locator('#formal-feedback-status').filter({hasText:'感受已保存'}).waitFor();assert.equal(await page.locator('#formal-feedback-use-latest').count(),0);
 const after=await read();assert.equal(after.feedback_revision,4);assert.equal(after.latest_feedback.pain,null);assert.equal(after.latest_feedback.fatigue,5);assert.deepEqual(after.canonical_commit,before.canonical_commit);assert.equal(after.snapshot.completed,before.snapshot.completed);
 for(const route of ['/api/practice','/api/practice/arrangements']){const response=await context.request.get(base+route);assert.equal(response.status(),200);assert.deepEqual(await response.json(),[]);}
 await open();assert.equal(await page.locator('#formal-feedback-fatigue').inputValue(),'5');assert.equal(await page.locator('[data-formal-record]').count(),0);
 await page.screenshot({path:path.join(out,'PRIVATE-feedback-final.png'),fullPage:true});
 const result={kind:'actual-original-v2-feedback-browser-flow',session_id:id,explicit_qa_scores_not_patient_findings:true,empty_form_no_write:true,pain_stays_null:true,unsubmitted_draft_restored:true,reply_loss_original_key_restored:true,real_conflict_user_choice:true,same_values_conflict_converged:true,original_visual_commit_unchanged:true,feedback_revision:after.feedback_revision,feedback_posts:posts.length,actual_sqlite_writes:4,physical_phone:false};
 await fs.writeFile(path.join(out,'feedback-result.json'),JSON.stringify(result,null,2));await fs.writeFile(path.join(out,'PRIVATE-feedback-posts.json'),JSON.stringify(posts,null,2));return result;
};
