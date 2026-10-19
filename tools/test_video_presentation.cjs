/* Local APK-assets video presentation QA. All media and records stay in isolated storage. */
'use strict';
const assert=require('node:assert/strict'),http=require('node:http'),fs=require('node:fs/promises'),path=require('node:path');
const {spawnSync}=require('node:child_process'),{createHash}=require('node:crypto');
const {chromium}=require('../ankang/route1-health-agent/node_modules/playwright');
const repo=path.resolve(__dirname,'..'),assets=path.join(repo,'android_offline/build/assets');
const out=path.resolve(process.argv[2]||'.runtime/video-presentation-20261019');
const input=path.resolve(process.argv[3]||'E:/game/test video/深蹲.mp4');
const mime={'.html':'text/html; charset=utf-8','.js':'application/javascript','.css':'text/css','.json':'application/json','.webp':'image/webp','.jpg':'image/jpeg','.png':'image/png','.svg':'image/svg+xml','.wasm':'application/wasm','.mp4':'video/mp4','.webm':'video/webm'};
const sha=data=>createHash('sha256').update(data).digest('hex');
const report={checks:[],fixtures:[],errors:[],externalRequests:[],scope:'Isolated browser identity and storage; real APK assets; local CPU analysis; no emulator, cloud, paid model, or real-account writes.'};
function run(command,args,options={}){const r=spawnSync(command,args,{encoding:'utf8',windowsHide:true,maxBuffer:16*1024*1024,...options});assert.equal(r.status,0,(r.error?.message||'')+'\n'+r.stderr);return r;}
function ffmpegPath(){
 if(process.env.FFMPEG_PATH)return process.env.FFMPEG_PATH;
 for(const python of [path.join(repo,'rehab_codex_single_camera_v2_1/.venv/Scripts/python.exe'),'python']){
  const r=spawnSync(python,['-c','import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())'],{encoding:'utf8',windowsHide:true});
  if(r.status===0&&r.stdout.trim())return r.stdout.trim();
 }
 throw Error('Set FFMPEG_PATH or install imageio_ffmpeg in the verified project Python.');
}
async function fixtures(){
 const ffmpeg=ffmpegPath(),dir=path.join(out,'fixtures');await fs.mkdir(dir,{recursive:true});
 const width=160,height=120,colors={red:[255,0,0],green:[0,255,0],blue:[0,0,255]};
 const raw=color=>{const b=Buffer.alloc(width*height*3);for(let i=0;i<b.length;i+=3){b[i]=color[0];b[i+1]=color[1];b[i+2]=color[2];}return b;};
 for(const [name,color]of Object.entries(colors))await fs.writeFile(path.join(dir,name+'.ppm'),Buffer.concat([Buffer.from(`P6\n${width} ${height}\n255\n`),raw(color)]));
 const cfr=path.join(dir,'second-frame-cfr-bframes.mp4');
 run(ffmpeg,['-hide_banner','-loglevel','error','-y','-f','rawvideo','-pixel_format','rgb24','-video_size',`${width}x${height}`,'-framerate','2','-i','pipe:0','-an','-c:v','libx264','-crf','10','-pix_fmt','yuv420p','-g','30','-bf','2','-b_strategy','0','-movflags','+faststart',cfr],{input:Buffer.concat(['red','green','blue','blue','blue','blue','blue','blue'].map(c=>raw(colors[c])))});
 const list=path.join(dir,'vfr.ffconcat');
 await fs.writeFile(list,"ffconcat version 1.0\nfile 'red.ppm'\nduration 0.52\nfile 'green.ppm'\nduration 0.84\nfile 'blue.ppm'\nduration 1.16\nfile 'blue.ppm'\nduration 0.52\nfile 'blue.ppm'\n");
 const vfr=path.join(dir,'second-frame-vfr-bframes.mp4'),webm=path.join(dir,'second-frame-vfr.webm');
 run(ffmpeg,['-hide_banner','-loglevel','error','-y','-safe','0','-f','concat','-i',list,'-fps_mode','vfr','-an','-c:v','libx264','-crf','10','-pix_fmt','yuv420p','-g','30','-bf','2','-b_strategy','0','-movflags','+faststart',vfr]);
 run(ffmpeg,['-hide_banner','-loglevel','error','-y','-safe','0','-f','concat','-i',list,'-fps_mode','vfr','-an','-c:v','libvpx-vp9','-lossless','1','-pix_fmt','yuv420p',webm]);
 for(const [file,kind,second]of [[cfr,'cfr-h264-bframes',.5],[vfr,'vfr-h264-bframes',.52],[webm,'vfr-vp9-webm',.52]]){
  const log=run(ffmpeg,['-hide_banner','-i',file,'-vf','showinfo','-an','-f','null','-']).stderr;
  const frames=[...log.matchAll(/\bn:\s*(\d+)\s+pts:\s*-?\d+\s+pts_time:([\d.-]+)[^\r\n]*?\btype:(\w)/g)].map(m=>({n:Number(m[1]),pts:Number(m[2]),type:m[3]}));
  assert(frames.length>=4,'ffmpeg must expose actual frame timestamps');assert.equal(frames[0].pts,0);assert(Math.abs(frames[1].pts-second)<.001);
  if(kind.includes('vfr'))assert(new Set(frames.slice(1).map((f,i)=>(f.pts-frames[i].pts).toFixed(3))).size>1,'Fixture must really be VFR');
  if(kind.includes('bframes'))assert(frames.some(f=>f.type==='B'),'Fixture must contain B frames');
  const bytes=await fs.readFile(file);if(file.endsWith('.mp4'))assert(bytes.includes(Buffer.from('ctts')),'B-frame MP4 must contain composition offsets');
  report.fixtures.push({file,kind,frames,sha256:sha(bytes),bytes:bytes.length});
 }
 report.checks.push('generated_real_cfr_bframes_ctts_vfr_and_webm_fixtures_with_verified_pts');return report.fixtures;
}
async function pixel(page,url){return page.evaluate(async src=>{const i=new Image();i.src=src;await i.decode();const c=document.createElement('canvas');c.width=i.naturalWidth;c.height=i.naturalHeight;const x=c.getContext('2d');x.drawImage(i,0,0);return Array.from(x.getImageData(Math.floor(c.width*.22),Math.floor(c.height*.22),1,1).data);},url);}
function color(pixel,channel,message){assert(pixel[channel]>200&&pixel[(channel+1)%3]<65&&pixel[(channel+2)%3]<65,message+': '+pixel.join(','));}
async function screenshotPixel(page,locator,file){const png=await locator.screenshot({path:file});return pixel(page,'data:image/png;base64,'+png.toString('base64'));}
async function frameState(page,selector,overlaySelector){
 return page.evaluate(({selector,overlaySelector})=>{
  const v=document.querySelector(selector),c=document.createElement('canvas');c.width=v.videoWidth;c.height=v.videoHeight;c.getContext('2d').drawImage(v,0,0);
  const overlay=overlaySelector?document.querySelector(overlaySelector):null,bytes=overlay?.getContext('2d').getImageData(0,0,overlay.width,overlay.height).data;
  return {paused:v.paused,currentTime:v.currentTime,muted:v.muted,poster:v.getAttribute('poster'),video:c.toDataURL(),overlay:overlay?.toDataURL(),annotatedPixels:bytes?bytes.filter((_,i)=>i%4===3&&bytes[i]>0).length:0};
 },{selector,overlaySelector});
}
function stable(a,b,label){assert.equal(b.paused,true,label+' paused');assert(Math.abs(a.currentTime-b.currentTime)<.001,label+' currentTime changed');assert.equal(sha(a.video),sha(b.video),label+' video pixels changed');if(a.overlay)assert.equal(sha(a.overlay),sha(b.overlay),label+' annotation pixels changed');}
(async()=>{
 await fs.mkdir(out,{recursive:true});let browser,server;
 try{
  const generated=await fixtures();
  if(process.argv.includes('--fixtures-only')){report.passed=true;return;}
  await fs.access(input);
  server=http.createServer(async(req,res)=>{try{
   const url=new URL(req.url,'http://127.0.0.1'),name=url.pathname==='/'?'index.html':url.pathname==='/capture'?'capture.html':decodeURIComponent(url.pathname.slice(1)),file=path.resolve(assets,name);
   if(!file.startsWith(assets+path.sep))throw Error('outside assets');const data=await fs.readFile(file),type=mime[path.extname(file)]||'application/octet-stream';
   const range=/^bytes=(\d+)-(\d*)$/.exec(req.headers.range||'');
   if(range){const start=Number(range[1]),end=Math.min(data.length-1,range[2]?Number(range[2]):data.length-1);res.writeHead(206,{'Content-Type':type,'Content-Range':`bytes ${start}-${end}/${data.length}`,'Accept-Ranges':'bytes','Content-Length':end-start+1});res.end(data.subarray(start,end+1));}
   else{res.writeHead(200,{'Content-Type':type,'Content-Length':data.length,'Accept-Ranges':'bytes'});res.end(data);}
  }catch(e){res.writeHead(404);res.end();}});
  await new Promise(r=>server.listen(0,'127.0.0.1',r));const origin='http://127.0.0.1:'+server.address().port;
  browser=await chromium.launch({channel:'msedge',headless:true,args:['--autoplay-policy=document-user-activation-required']});
  const context=await browser.newContext({viewport:{width:430,height:932},isMobile:true,hasTouch:true,deviceScaleFactor:1});
  await context.addInitScript(()=>{localStorage.setItem('ankang-phone-active-1','ankang-phone-product-2');window.OfflineAndroid={accountIdentity:()=>JSON.stringify({origin:'https://139.224.216.18',role:'PATIENT',patient_id:'00000000-0000-4000-8000-000000000011',account_id:'00000000-0000-4000-8000-000000000012',username:'isolated-video-presentation-qa'}),cloudConfigured:()=>false};});
  await context.route('**/*',route=>{const url=route.request().url();if(url.startsWith(origin)||url.startsWith('blob:')||url.startsWith('data:'))return route.continue();report.externalRequests.push(url);return route.abort();});
  const page=await context.newPage();page.setDefaultTimeout(25000);page.on('pageerror',e=>report.errors.push(e.message));
  await page.goto(origin+'/capture?tab=assess&entry=library');await page.locator('[data-rl-card="fitness_squat"]').click();
  await page.waitForFunction(()=>!!globalThis.RehabVideoPresentation);
  for(const fixture of generated){
   await page.locator('#fit-gallery-input').setInputFiles(fixture.file);
   await page.waitForFunction(()=>{const v=document.querySelector('#file-area video');return v?.readyState>=2&&!!v.getAttribute('poster');});
   const video=page.locator('#file-area video'),initial=await video.evaluate(v=>({paused:v.paused,time:v.currentTime,poster:v.poster}));
   assert.equal(initial.paused,true);assert.equal(initial.time,0,'Poster extraction must not seek the user-visible video');
   fixture.posterPixel=await pixel(page,initial.poster);color(fixture.posterPixel,1,fixture.kind+' poster must be actual second green frame');
   fixture.displayedPixel=await screenshotPixel(page,video,path.join(out,fixture.kind+'-initial-poster.png'));color(fixture.displayedPixel,1,fixture.kind+' initially displayed frame');
   await video.evaluate(v=>v.play());await page.waitForFunction(()=>document.querySelector('#file-area video').currentTime>1.45);
   await video.evaluate(v=>v.pause());const paused=await frameState(page,'#file-area video');await page.waitForTimeout(450);stable(paused,await frameState(page,'#file-area video'),fixture.kind+' preview pause');
   fixture.pausePixel=await screenshotPixel(page,video,path.join(out,fixture.kind+'-pause.png'));color(fixture.pausePixel,2,fixture.kind+' pause must retain current blue frame');
   await video.evaluate(v=>{v.currentTime=.7;});await page.waitForFunction(()=>{const v=document.querySelector('#file-area video');return !v.seeking&&Math.abs(v.currentTime-.7)<.005;});
   fixture.seekPixel=await screenshotPixel(page,video,path.join(out,fixture.kind+'-seek.png'));color(fixture.seekPixel,1,fixture.kind+' manual seek must show actual green frame');
   const sought=await frameState(page,'#file-area video');await page.waitForTimeout(300);stable(sought,await frameState(page,'#file-area video'),fixture.kind+' preview manual seek');
   report.checks.push(fixture.kind+'_second_frame_exact_initial_paused_at_zero_play_pause_and_seek');
  }
  await page.locator('#fit-gallery-input').setInputFiles(input);await page.waitForFunction(()=>!!document.querySelector('#file-area video')?.getAttribute('poster'));
  await page.screenshot({path:path.join(out,'real-squat-preview.png')});
  const previewState=()=>page.locator('#file-area video').evaluate(v=>({readyState:v.readyState,networkState:v.networkState,preload:v.preload,paused:v.paused,currentTime:v.currentTime,poster:!!v.poster,buffered:Array.from({length:v.buffered.length},(_,i)=>[v.buffered.start(i),v.buffered.end(i)])}));
  report.previewTiming=[{afterPosterMs:0,...await previewState()}];
  for(const afterPosterMs of [1000,2000]){await page.waitForTimeout(1000);await page.screenshot({path:path.join(out,'real-squat-preview-after-'+afterPosterMs+'ms.png')});report.previewTiming.push({afterPosterMs,...await previewState()});}
  if(process.argv.includes('--compare-preload')){
   await page.locator('#file-area video').evaluate(v=>{v.preload='auto';v.load();});
   await page.waitForTimeout(1000);await page.screenshot({path:path.join(out,'real-squat-preview-preload-auto-after-1000ms.png')});report.preloadAuto=await previewState();
  }
  if(process.argv.includes('--preview-only')){assert.deepEqual(report.errors,[]);assert.deepEqual(report.externalRequests,[]);report.passed=true;return;}
  await page.evaluate(()=>PhoneLocal.store.change(v=>v.cloudIdentity=JSON.parse(OfflineAndroid.accountIdentity())));
  await page.locator('#consent').check();await page.locator('#upload-btn').click();
  await page.waitForFunction(()=>['done','failed'].includes(PhoneLocal.store.value.jobs.at(-1)?.state),null,{timeout:240000});
  report.job=await page.evaluate(()=>structuredClone(PhoneLocal.store.value.jobs.at(-1)));assert.equal(report.job.state,'done',report.job.message);assert.equal(report.job.exercise,'fitness_squat');assert.equal(report.job.mode,'fitness');
  await page.waitForSelector('#motion-review');await page.waitForFunction(()=>RehabMotionReview.current?.data?.hasTrace);
  await page.waitForFunction(()=>{const v=document.querySelector('.mr-media video');return v?.readyState>=2&&!v.paused&&v.currentTime>.15;});
  assert.equal(await page.locator('.mr-media video').evaluate(v=>v.muted),true,'Report autoplay must be muted');
  await page.waitForFunction(()=>{const c=document.querySelector('.mr-overlay');if(!c?.width)return false;const d=c.getContext('2d').getImageData(0,0,c.width,c.height).data;return d.some((v,i)=>i%4===3&&v>0);});
  await page.locator('.mr-play').click();await page.waitForFunction(()=>document.querySelector('.mr-media video').paused);await page.waitForTimeout(150);
  const paused=await frameState(page,'.mr-media video','.mr-overlay');assert(paused.annotatedPixels>0,'Real analysis must draw actual annotation points');await page.waitForTimeout(650);const held=await frameState(page,'.mr-media video','.mr-overlay');stable(paused,held,'real squat report pause');
  await page.screenshot({path:path.join(out,'real-squat-report-paused.png')});
  const seekTime=await page.locator('.mr-media video').evaluate(v=>Math.min(v.duration*.58,v.duration-.3));
  await page.locator('.mr-progress input').evaluate((slider,t)=>{slider.value=String(t);slider.dispatchEvent(new Event('input',{bubbles:true}));},seekTime);
  await page.waitForFunction(t=>{const v=document.querySelector('.mr-media video');return !v.seeking&&Math.abs(v.currentTime-t)<.015;},seekTime);await page.waitForTimeout(120);
  const sought=await frameState(page,'.mr-media video','.mr-overlay');assert(sought.annotatedPixels>0,'Seek must retain the corresponding annotation overlay');await page.waitForTimeout(650);stable(sought,await frameState(page,'.mr-media video','.mr-overlay'),'real squat report manual seek');
  assert.notEqual(sha(paused.video),sha(sought.video),'Manual seek should change the visible real video frame');
  await page.screenshot({path:path.join(out,'real-squat-report-manual-seek.png')});
  report.playback={pausedTime:paused.currentTime,pausedVideoSha256:sha(paused.video),pausedOverlaySha256:sha(paused.overlay),annotatedPixels:paused.annotatedPixels,seekTime:sought.currentTime,seekVideoSha256:sha(sought.video),seekOverlaySha256:sha(sought.overlay)};
  report.input={path:input,sha256:sha(await fs.readFile(input))};
  report.checks.push('original_squat_actual_cpu_analysis_muted_report_autoplay_pause_pixels_and_manual_seek_stable');
  assert.deepEqual(report.errors,[]);assert.deepEqual(report.externalRequests,[]);report.passed=true;
 }catch(e){report.passed=false;report.failure=e.stack||String(e);throw e;}
 finally{
  await fs.writeFile(path.join(out,'browser-checks.json'),JSON.stringify(report,null,2));
  if(browser)await browser.close();if(server)await new Promise(r=>server.close(r));
  console.log(JSON.stringify({passed:report.passed,checks:report.checks,errors:report.errors,externalRequests:report.externalRequests,output:out}));
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
