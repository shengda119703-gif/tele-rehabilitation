/* Real Edge playback + responsive sheet checks against a generated local review. */
const {chromium}=require('../../ankang/route1-health-agent/node_modules/playwright');
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const url=process.argv[2]||'http://127.0.0.1:14929/';
const output=process.argv[3];
if(!output)throw Error('Pass an audit output directory outside source control');
(async()=>{
 await fs.mkdir(output,{recursive:true});
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const context=await browser.newContext({viewport:{width:430,height:932},deviceScaleFactor:1,isMobile:true,hasTouch:true});
 const page=await context.newPage(),errors=[],writes=[];
 page.on('pageerror',e=>errors.push(e.message));
 page.on('request',r=>{if(!['GET','HEAD'].includes(r.method()))writes.push(r.method()+' '+r.url());});
 const manifest=await(await context.request.get(url+'manifest.json')).json(),checks=[];
 async function ready(id){await page.waitForFunction(id=>document.querySelector('video').getAttribute('src')===id+'/video.mp4'&&document.querySelector('video').readyState>=2,id,{timeout:30000});}
 async function seek(t){await page.locator('video').evaluate(async(v,t)=>{v.pause();if(Math.abs(v.currentTime-t)<.001)return;await new Promise(resolve=>{v.addEventListener('seeked',resolve,{once:true});v.currentTime=t;});},t);}
 async function noOverflow(){assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'document horizontal overflow');}
 try{
  for(const c of manifest.clips){
   await page.goto(url+'?clip='+c.id);await ready(c.id);await seek(4);
   const data=await(await context.request.get(url+c.data)).json();
   const before=await page.locator('video').evaluate(v=>v.getVideoPlaybackQuality().totalVideoFrames);
   await page.getByRole('button',{name:'播放视频',exact:true}).click();
   await page.waitForFunction(before=>{const v=document.querySelector('video');return v.currentTime>4.1&&v.getVideoPlaybackQuality().totalVideoFrames>before;},before,{timeout:15000});
   await page.getByRole('button',{name:'暂停视频',exact:true}).click();await seek(4);
   assert.equal(await page.locator('#clip-title').textContent(),c.title);await noOverflow();
   const values=await page.locator('.metric').evaluateAll(nodes=>nodes.map(el=>({key:el.dataset.key,value:el.querySelector('.metric-value').textContent,cue:el.querySelector('.metric-cue').textContent})));
   const sample=data.samples.filter(s=>s.t<=4).at(-1);
   for(const v of values){
    const m=data.metrics.find(m=>m.key===v.key);const whole=m.group==='动作节奏'||m.key==='mean_power';const actual=whole?m.value:sample.values[m.key];
    const formatted=typeof actual==='number'?(Math.abs(actual)<.5*10**(-m.decimals)?0:actual).toFixed(m.decimals):'—';
    assert.equal(v.value,formatted+m.unit,c.id+' '+v.key+' numeric provenance');
   }
   if(c.id==='01'){
    await page.screenshot({path:path.join(output,'phone-collapsed.png')});
    const box=await page.locator('#sheet-handle').boundingBox();
    await page.mouse.move(box.x+box.width/2,box.y+20);await page.mouse.down();await page.mouse.move(box.x+box.width/2,box.y-240,{steps:15});await page.mouse.up();
    assert.equal(await page.locator('#sheet-handle').getAttribute('aria-expanded'),'true','drag expands');
    await page.waitForTimeout(350);await page.screenshot({path:path.join(output,'phone-expanded.png')});
    await page.getByRole('tab',{name:'全段',exact:true}).click();
    assert.equal(await page.getByRole('tab',{name:'全段',exact:true}).getAttribute('aria-selected'),'true');
    await page.locator('.metric[data-key="power"]').click();assert(await page.locator('.metric-chart svg').count());
    await page.screenshot({path:path.join(output,'phone-chart.png')});
    await page.locator('#sheet-handle').focus();await page.keyboard.press('Enter');
    assert.equal(await page.locator('#sheet-handle').getAttribute('aria-expanded'),'false','keyboard collapses');
    await page.getByRole('button',{name:'选择视频',exact:true}).click();assert(await page.locator('#chooser').evaluate(el=>el.open));await page.getByRole('button',{name:'关闭选择',exact:true}).click();
   }
   await page.locator('#sheet-handle').click();await page.waitForTimeout(350);
   assert.equal(await page.locator('#sheet-handle').getAttribute('aria-expanded'),'true');
   await page.getByRole('tab',{name:'全段',exact:true}).click();
   assert(!/完成次数|重复次数|正在下蹲|正在抬起/.test(await page.locator('body').innerText()),'excluded narration/counts');
   if(c.id==='06'){
    await page.screenshot({path:path.join(output,'deadlift-expanded.png')});
    await page.locator('#trajectory-section').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(output,'deadlift-trajectory.png')});
    const h=data.highlights[0];await page.locator('.highlight').first().click();
    assert(Math.abs(await page.locator('video').evaluate(v=>v.currentTime)-h.t)<.04,'feedback timestamp seek');
   }
   const range=await context.request.get(url+c.id+'/video.mp4',{headers:{Range:'bytes=0-1023'}});assert.equal(range.status(),206);assert.equal((await range.body()).length,1024);
   const csv=await context.request.get(url+c.id+'/metrics.csv');assert.equal(csv.status(),200);
   const decode=await page.locator('video').evaluate(v=>({width:v.videoWidth,height:v.videoHeight,duration:v.duration,decoded:v.getVideoPlaybackQuality().totalVideoFrames,error:v.error?.message||null}));
   assert.equal(decode.width,1280);assert.equal(decode.height,720);assert.equal(decode.error,null);
   checks.push({id:c.id,metrics:values.length,...decode});
  }
  await page.goto(url+'?clip=01');await ready('01');await page.getByRole('button',{name:'查看侧面 ↗',exact:true}).click();await ready('02');
  await page.locator('#next').click();await ready('03');await page.locator('#previous').click();await ready('02');
  await page.getByRole('button',{name:'隐藏动作标注',exact:true}).click();assert.equal(await page.locator('#annotations').getAttribute('aria-pressed'),'false');
  await page.setViewportSize({width:360,height:740});await seek(5);await noOverflow();await page.screenshot({path:path.join(output,'small-phone.png')});
  const desktop=await browser.newPage({viewport:{width:1440,height:1000}});desktop.on('pageerror',e=>errors.push(e.message));await desktop.goto(url+'?clip=06');await desktop.waitForFunction(()=>document.querySelector('video').readyState>=2);await desktop.locator('video').evaluate(v=>v.currentTime=8.08);await desktop.waitForTimeout(400);await desktop.screenshot({path:path.join(output,'desktop.png')});await desktop.close();
  assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);
  await fs.writeFile(path.join(output,'browser-checks.json'),JSON.stringify({checks,errors,writes,drag:true,keyboard:true,seek:true,range206:true,mobile_sizes:[[430,932],[360,740]],desktop_size:[1440,1000]},null,2));
  console.log(JSON.stringify({videos:checks.length,metrics:checks.reduce((s,c)=>s+c.metrics,0),errors:errors.length,writes:writes.length,gestures:'passed'}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
