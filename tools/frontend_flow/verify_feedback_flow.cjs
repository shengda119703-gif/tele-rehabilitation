// Shared real-browser journey. request must call the actual owning runtime.
'use strict';
const fs=require('node:fs/promises'),path=require('node:path'),crypto=require('node:crypto'),assert=require('node:assert/strict');
async function verifyFeedbackFlow(page,request,base,out){
 const rows=await request('/practice'),id=rows[0].id,p='/practice/'+id+'/feedback';
 assert.equal(rows.length,1);assert.equal(rows[0].state,'COMMITTED');
 await page.locator('#practice-feedback-submit').waitFor({state:'visible'});
 await page.waitForFunction(()=>{const b=document.querySelector('#practice-feedback-submit');return b&&!b.disabled;});
 assert.equal(await page.locator('#practice-pain').inputValue(),'');assert.equal(await page.locator('#practice-fatigue').inputValue(),'');
 const buttonGeometry=()=>page.locator('#practice-back').evaluate(el=>{const r=el.getBoundingClientRect();return{x:r.x+window.scrollX,y:r.y+window.scrollY,width:r.width,height:r.height};});
 const originalGeometry=await buttonGeometry();
 await page.locator('#practice-fatigue').fill('3');await page.locator('#practice-note').fill('TEST QA 后补感受，不是人体观察');
 await page.locator('#practice-feedback-later').click();
 await page.goto(base+'/capture?tab=history');await page.locator('[data-practice]').click();
 await page.waitForFunction(()=>{const b=document.querySelector('#practice-feedback-submit');return b&&!b.disabled;});
 assert.equal(await page.locator('#practice-note').inputValue(),'TEST QA 后补感受，不是人体观察');
 // Lose one reply only AFTER the actual authority has committed the feedback.
 await page.evaluate(()=>{const original=window.fetch;let fault=true;window.__qaFeedbackPosts=0;window.fetch=async(...args)=>{const r=await original(...args);if(String(args[0]).endsWith('/feedback')&&args[1]?.method==='POST'){window.__qaFeedbackPosts++;if(fault&&r.ok){fault=false;return new Response('{TEST unreadable committed feedback',{status:200});}}return r;};});
 await page.locator('#practice-feedback-submit').click();await page.waitForFunction(()=>{const b=document.querySelector('#practice-feedback-submit');return b&&!b.disabled;});await page.locator('#practice-feedback-status').filter({hasText:'保存待核对'}).waitFor();
 assert.equal(await page.evaluate(()=>window.__qaFeedbackPosts),1);
 const committed=await request(p);assert.equal(committed.revision,1);assert.equal(committed.values.pain,null);assert.equal(committed.values.fatigue,3);
 const rowAfter=await request('/practice/'+id),operation=rowAfter.practice_feedback.operations[0].operation_id;
 assert.equal(rowAfter.practice_feedback.operations.length,1);
 await page.reload();await page.locator('[data-practice]').click();await page.locator('#practice-feedback-status').filter({hasText:'感受已保存'}).waitFor();
 assert.equal((await request('/practice/'+id)).practice_feedback.operations.length,1);
 assert.equal((await request(p+'/operations/'+operation)).status,'COMMITTED');
 // One real external edit gives a genuine stale-revision conflict; the UI
 // reads it without overwriting, and the user explicitly adopts its contents.
 await request(p,{method:'POST',body:{operation_id:crypto.randomUUID(),expected_revision:1,values:{pain:null,fatigue:2,note:'TEST QA 另一处填写'}}});
 await page.locator('#practice-note').fill('TEST QA 当前页填写');await page.locator('#practice-feedback-submit').click();
 await page.locator('#practice-feedback-status').filter({hasText:'另一处更新'}).waitFor();
 assert.equal((await request(p)).revision,2);assert.equal((await request(p)).values.note,'TEST QA 另一处填写');
 assert.equal(await page.locator('#practice-note').inputValue(),'TEST QA 当前页填写');
 await page.screenshot({path:path.join(out,'feedback-conflict.png'),fullPage:true});
 await page.locator('#practice-feedback-use-latest').click();assert.equal(await page.locator('#practice-note').inputValue(),'TEST QA 另一处填写');
 await page.locator('#practice-note').fill('TEST QA 最终补充');await page.locator('#practice-feedback-submit').click();
 await page.locator('#practice-feedback-status').filter({hasText:'感受已保存'}).waitFor();
 const final=await request('/practice/'+id);assert.equal(final.practice_feedback.revision,3);assert.equal(final.practice_feedback.operations.length,3);
 assert.equal(final.self_reported_count,10);assert.equal(final.confirmed_count,null);assert.equal(final.formal_plan_contribution,null);
 assert.deepEqual(final.finish_payload.feedback,{pain:null,fatigue:null});assert.equal(final.practice_feedback.values.pain,null);
 const finalGeometry=await buttonGeometry();assert.deepEqual(finalGeometry,originalGeometry);
 await page.screenshot({path:path.join(out,'feedback-saved-mobile.png'),fullPage:true});
 await page.setViewportSize({width:1440,height:940});await page.screenshot({path:path.join(out,'feedback-saved-desktop.png'),fullPage:true});await page.setViewportSize({width:390,height:844});
 // Starting a later allowed journey must not overwrite the earlier draft.
 const originalDraft=await page.evaluate(id=>{const key=Array.from({length:localStorage.length},(_,i)=>localStorage.key(i)).find(k=>k.startsWith('ankang-practice-draft-1:')&&k.endsWith(':'+id));return key&&localStorage.getItem(key);},id);
 assert(originalDraft);assert.equal(JSON.parse(originalDraft).feedbackPending,null);
 const result={kind:'actual-runtime-independent-feedback-browser-flow',revision:3,feedback_operations:3,practice_records:1,original_finish_null_feedback_preserved:true,pain_null_preserved:true,qa_fatigue_input:2,values_source:'explicit QA entries, not observed patient feelings',lost_reply_reconciles_original:true,late_draft_survives_navigation_and_reload:true,genuine_conflict_no_silent_overwrite:true,original_button_geometry_unchanged:true,per_practice_draft_retained:true,formal_plan_contribution:null,physical_phone_tested:false};
 await fs.writeFile(path.join(out,'feedback-result.json'),JSON.stringify(result,null,2));return result;
}
module.exports={verifyFeedbackFlow};
