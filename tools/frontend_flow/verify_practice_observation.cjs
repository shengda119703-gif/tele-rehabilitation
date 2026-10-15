// Real prerecorded camera input + real owning /live engine. No API mocks.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path');
async function verifyPracticeObservation(page,out){
 const geometry=()=>page.locator('#practice-back').evaluate(e=>{const r=e.getBoundingClientRect();return{x:r.x+scrollX,y:r.y+scrollY,width:r.width,height:r.height};});
 const before=await geometry();
 await page.evaluate(()=>{
  if(!window.RehabGuidance?.app)throw Error('Original production guidance scheduler missing');
  window.__qaAudioAttempts=[];const speak=RehabGuidance.app.audio.speak.bind(RehabGuidance.app.audio),cancel=RehabGuidance.app.audio.cancel.bind(RehabGuidance.app.audio);
  RehabGuidance.app.audio.speak=(text,done)=>{window.__qaAudioAttempts.push({kind:'speak',text,at:performance.now()});return speak(text,done);};
  RehabGuidance.app.audio.cancel=()=>{window.__qaAudioAttempts.push({kind:'cancel',at:performance.now()});return cancel();};
  window.__qaPreviewTrace=[];window.__qaOcclude=true;const original=api;
  window.api=async(route,opts)=>{const data=await original(route,opts);if(route.startsWith('/live/'))window.__qaPreviewTrace.push({route,method:opts?.method||'GET',received_ms:performance.now(),valid:data.valid,phase:data.summary?.phase||data.cue?.status,count:data.summary?.completed,value:data.summary?.metrics?.[data.summary?.primary_metric]?.value});if(window.__qaPracticeReadFault&&route==='/practice/'+practiceJourney.start.operation_id&&!opts){window.__qaPracticeReadFault=false;throw Error('TEST unreadable response after actual owned GET');}return data;};
  const draw=CanvasRenderingContext2D.prototype.drawImage;
  CanvasRenderingContext2D.prototype.drawImage=function(...args){draw.apply(this,args);if(window.__qaOcclude&&args[0] instanceof HTMLVideoElement){this.fillStyle='#000';this.fillRect(0,0,this.canvas.width,this.canvas.height);}};
 });
 await page.locator('#practice-observation summary').click();await page.locator('#live-consent').check();await page.locator('#live-voice').check();await page.locator('#live-start').click();
 await page.locator('#live-cue').filter({hasText:'先按示范练习'}).waitFor({timeout:20000});
 await page.waitForFunction(()=>window.__qaPreviewTrace.filter(r=>r.route.endsWith('/frame')).length>=3,null,{timeout:45000});
 const preparing=await page.evaluate(()=>({running:practiceJourney.running,count:practiceJourney.receipt.confirmed_count,frames:window.__qaPreviewTrace.filter(r=>r.route.endsWith('/frame'))}));
 assert.equal(preparing.running,true);assert.equal(preparing.count,null);assert(preparing.frames.every(r=>!r.valid));
 await page.screenshot({path:path.join(out,'PRIVATE-practice-soft-wait.png'),fullPage:true});
 await page.evaluate(()=>{window.__qaOcclude=false;});
 // Frames stay actual. A negative readiness result is kept, never coerced.
 await page.waitForFunction(()=>window.__qaPreviewTrace.some(r=>r.valid===true),null,{timeout:60000});
 await page.waitForTimeout(10000);
 const tracked=await page.evaluate(()=>({cue:document.querySelector('#live-cue').textContent,frames:window.__qaPreviewTrace.filter(r=>r.route.endsWith('/frame')),generation:practiceJourney.previewGeneration,preview:practiceJourney.previewCount,segments:practiceJourney.observationSegments||[]}));
 const auto=tracked.segments.some(r=>r.to==='AUTO_ASSISTED');
 const videoSame=await page.evaluate(async()=>{const v=document.querySelector('#live-video'),stream=v.srcObject;await reconcilePractice(practiceJourney,document.querySelector('#practice-area'));return v===document.querySelector('#live-video')&&stream===v.srcObject;});assert.equal(videoSame,true);
 const failedReadSame=await page.evaluate(async()=>{const v=document.querySelector('#live-video'),stream=v.srcObject,input=document.querySelector('#practice-count').value;window.__qaPracticeReadFault=true;await reconcilePractice(practiceJourney,document.querySelector('#practice-area'));return v===document.querySelector('#live-video')&&stream===v.srcObject&&input===document.querySelector('#practice-count').value&&practiceJourney.running;});assert.equal(failedReadSame,true);
 // Short and long visual gaps are controlled black JPEGs to the REAL model.
 await page.evaluate(()=>{window.__qaOcclude=true;});await page.waitForTimeout(750);
 assert.equal(await page.evaluate(()=>practiceJourney.running),true);
 await page.waitForTimeout(7500);
 if(auto)await page.locator('#live-cue').filter({hasText:'已继续陪练'}).waitFor();
 assert.equal(await page.evaluate(()=>practiceJourney.running),true);
 const angle=await page.locator('#live-angle').textContent();assert.equal(angle,'—');
 await page.screenshot({path:path.join(out,'PRIVATE-practice-long-gap.png'),fullPage:true});
 await page.evaluate(()=>{window.__qaOcclude=false;});await page.waitForTimeout(6000);
 await page.locator('#practice-pause').click();await page.waitForFunction(()=>!liveCloseRequest&&!liveCreateRequest&&!liveCameraRequest);
 assert.equal(await page.evaluate(()=>document.querySelector('#live-video').srcObject),null);
 assert.equal(await page.evaluate(()=>RehabGuidance.app.snapshot().pending),0);assert.equal(await page.evaluate(()=>RehabGuidance.app.snapshot().active),false);
 const pauseFrameCount=await page.evaluate(()=>window.__qaPreviewTrace.filter(r=>r.route.endsWith('/frame')).length);
 await page.waitForTimeout(500);assert.equal(await page.evaluate(()=>window.__qaPreviewTrace.filter(r=>r.route.endsWith('/frame')).length),pauseFrameCount);
 await page.locator('#practice-pause').click();await page.waitForFunction(()=>practiceJourney.previewGeneration===2&&document.querySelector('#live-video').srcObject!==null);
 await page.waitForFunction(n=>window.__qaPreviewTrace.filter(r=>r.route.endsWith('/frame')).length>n,pauseFrameCount,{timeout:30000});
 await page.locator('#live-stop').click();await page.waitForFunction(()=>!liveCloseRequest&&!liveCreateRequest&&!liveCameraRequest);
 const afterStop=await page.evaluate(()=>({frames:window.__qaPreviewTrace.filter(r=>r.route.endsWith('/frame')).length,tracksStopped:document.querySelector('#live-video').srcObject===null,segments:practiceJourney.observationSegments||[],count:practiceJourney.receipt.confirmed_count,running:practiceJourney.running}));
 await page.waitForTimeout(500);assert.equal(await page.evaluate(()=>window.__qaPreviewTrace.filter(r=>r.route.endsWith('/frame')).length),afterStop.frames);
 const guidance=await page.evaluate(()=>({stats:RehabGuidance.app.snapshot(),attempts:window.__qaAudioAttempts}));
 assert.equal(guidance.stats.active,false);assert.equal(guidance.stats.pending,0);assert(guidance.stats.max_pending<=1);assert(guidance.attempts.some(v=>v.kind==='speak'));
 const normal=guidance.attempts.filter(v=>v.kind==='speak');for(let n=1;n<normal.length;n++)assert(normal[n].at-normal[n-1].at>=5900);
 assert(normal.filter(v=>v.text==='先按示范练习，自动指导稍后接上').length<=1);assert(normal.filter(v=>v.text==='刚才一小段没看清，继续练习即可').length<=1);
 assert.equal(afterStop.tracksStopped,true);assert.equal(afterStop.running,true);assert.equal(afterStop.count,null);
 await page.locator('#practice-observation summary').click();assert.deepEqual(await geometry(),before);
 await fs.writeFile(path.join(out,'PRIVATE-preview-trace.json'),JSON.stringify(afterStop.segments.length?{frames:await page.evaluate(()=>window.__qaPreviewTrace),segments:afterStop.segments}:{frames:await page.evaluate(()=>window.__qaPreviewTrace)},null,2));
 await fs.writeFile(path.join(out,'PRIVATE-guidance-attempts.json'),JSON.stringify(guidance,null,2));
 const result={kind:'actual-guided-practice-and-owned-preview-browser-flow',real_model:true,real_prerecorded_camera:true,physical_camera:false,physical_android:false,blank_preparation_keeps_practice:true,soft_budget_ms:6000,actual_preview_frames:afterStop.frames,auto_assistance_before_long_gap:auto,auto_assistance_observed:afterStop.segments.some(r=>r.to==='AUTO_ASSISTED'),short_and_long_gaps_keep_practice:true,preview_not_saved_as_visual_fact:true,confirmed_count:null,no_formal_contribution:true,video_dom_and_stream_retained_during_reconcile:true,existing_back_button_geometry_unchanged:true,stop_releases_media_and_stops_frames:true,pause_stops_preview_and_single_continue_restores_opted_in_camera:true,new_preview_boundary_does_not_resume_old_engine:true,guidance_scheduler_original_audio_outlet:true,normal_audio_spacing_checked:true,guidance_pending_capacity:guidance.stats.max_pending,audio_speak_attempts:normal.length,paused_and_stopped_audio_cancelled:true,audible_output_verified:false,mode_segments_source:'frontend-only draft; not body measurements or a canonical receipt'};
 await fs.writeFile(path.join(out,'observation-result.json'),JSON.stringify(result,null,2));return result;
}
module.exports={verifyPracticeObservation};
