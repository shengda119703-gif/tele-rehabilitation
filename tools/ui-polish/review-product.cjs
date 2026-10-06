// Real local service + existing routes. TEST data only, including per-dose writes.
const {chromium}=require('../../ankang/route1-health-agent/node_modules/playwright');
const fs=require('node:fs/promises');const path=require('node:path');
(async()=>{
 const out=path.resolve(process.argv[2]||'qa-output/ui-polish-20261006/web');await fs.mkdir(out,{recursive:true});
 const browser=await chromium.launch({channel:'msedge',headless:true});const results=[];
 try {
  for(const [name,width,height,theme] of [['mobile',390,844,'light'],['small',320,740,'light'],['tablet',768,1024,'light'],['desktop',1440,940,'light'],['dark',390,844,'dark']]){
   if(process.argv[3]&&process.argv[3]!==name)continue;
   const ctx=await browser.newContext({viewport:{width,height},colorScheme:theme});const page=await ctx.newPage();const errors=[];
   page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error'&&!m.text().includes('401'))errors.push(m.text())});
   await page.goto('http://127.0.0.1:8876');await page.locator('#pair-form').waitFor();
   await page.screenshot({path:path.join(out,name+'-pair.png'),fullPage:true});
   await page.locator('[name=code]').fill('test-code');await page.locator('#pair-form button').click();await page.locator('#nav:not([hidden])').waitFor();
   await page.locator('#message').waitFor({state:'hidden',timeout:12000});
   await page.locator('#nav a[href="#rehab"]').click();await page.waitForTimeout(70);
   if(!await page.evaluate(()=>document.querySelector('.nav-thumb').getAnimations().length))throw Error('Navigation travel was cancelled');
   await page.screenshot({path:path.join(out,name+'-navigation-travel.png')});await page.waitForTimeout(350);
   const aligned=await page.evaluate(()=>{const a=document.querySelector('#nav [aria-current]').getBoundingClientRect(),b=document.querySelector('.nav-thumb').getBoundingClientRect();return Math.abs(a.left-b.left)<2&&Math.abs(a.top-b.top)<2&&Math.abs(a.width-b.width)<2;});
   if(!aligned)throw Error('Navigation marker does not settle onto selected link');
   for(const key of ['home','rehab','health','medication','family','assistant','records']){
    await page.evaluate(k=>{location.hash=k},key);await page.waitForTimeout(330);
    const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
    if(overflow)throw Error(name+'/'+key+' horizontal overflow');
    await page.screenshot({path:path.join(out,name+'-'+key+'.png'),fullPage:true});
    if(['home','records','assistant'].includes(key)) {
     await page.evaluate(()=>scrollTo(0,document.documentElement.scrollHeight));await page.waitForTimeout(150);
     await page.screenshot({path:path.join(out,name+'-'+key+'-scrolled.png')});
    }
   }
   // Follow the new public entries, including browser Back and persisted data.
   await page.locator('#nav a[href="#home"]').click();
   await page.locator('a[href="#records"]').click();await page.locator('.weekly-report').waitFor();
   await page.locator('summary').filter({hasText:/^健康记录$/}).click();
   if(!await page.locator('#content').innerText().then(t=>t.includes('62')||t.includes('63')))throw Error('Saved metric missing from records');
   await page.getByRole('link',{name:'返回首页',exact:true}).click();
   await page.locator('#nav a[href="#rehab"]').click();
   for(const [mode,tab] of [['assessment','assess'],['fitness','fitness']]) {
    await page.locator(`[data-rehab-mode="${mode}"]`).click();
    await page.screenshot({path:path.join(out,name+'-rehab-'+mode+'.png'),fullPage:true});
    await page.locator(`a[href="/capture?tab=${tab}"]`).click();await page.waitForURL('**/capture?tab='+tab);
    await page.goBack();await page.locator('[data-rehab-mode="training"]').waitFor();
   }
   await page.evaluate(()=>{location.hash='health'});await page.waitForTimeout(200);await page.locator('#edit-profile').click();
   await page.waitForTimeout(330);
   await page.screenshot({path:path.join(out,name+'-profile-dialog.png'),fullPage:true});await page.keyboard.press('Escape');
   if(await page.locator('dialog').isVisible())throw Error('Escape did not close profile dialog');
   await page.evaluate(()=>{location.hash='assistant'});await page.waitForTimeout(200);
   await page.locator('#draft').fill('TEST 今天感觉还好');
   if(await page.locator('.composer').getAttribute('data-charged')!=='true')throw Error('Composer charge feedback missing');
   await page.screenshot({path:path.join(out,name+'-composer-charged.png'),fullPage:true});
   await page.locator('#draft').fill('我今天体重63公斤');await page.locator('#chat-form button[type="submit"]').click();
   await page.waitForFunction(()=>document.querySelector('.conversation')?.textContent.includes('63')&&!document.querySelector('#chat-form button[type="submit"]').disabled);
   await page.locator('#nav a[href="#health"]').click();
   await page.waitForFunction(()=>document.querySelector('.timeline')?.textContent.includes('63'));
   await page.screenshot({path:path.join(out,name+'-chat-record-saved.png'),fullPage:true});
   await page.emulateMedia({reducedMotion:'reduce'});await page.evaluate(()=>{location.hash='family'});await page.waitForTimeout(50);
   if(await page.evaluate(()=>document.querySelector('.nav-thumb').getAnimations().length))throw Error('Reduced motion still travels');
   await page.emulateMedia({reducedMotion:'no-preference'});
   await page.evaluate(()=>{location.hash='medication'});await page.waitForTimeout(200);
   const dose=page.locator('[data-dose]');if(await dose.count()) {
    await dose.first().click();await page.locator('#taken').click();await page.locator('dialog').waitFor({state:'hidden'});
    await page.locator('.status').first().waitFor();await page.screenshot({path:path.join(out,name+'-dose-saved.png'),fullPage:true});
   }
   for(const tab of ['assess','plan','fitness','history']) {
    await page.goto('http://127.0.0.1:8876/capture?tab='+tab);await page.waitForTimeout(550);
    await page.screenshot({path:path.join(out,name+'-capture-'+tab+'.png'),fullPage:true});
    const navBox=await page.locator('.bottom-nav').boundingBox();
    if(navBox.x<0||navBox.x+navBox.width>width+1)throw Error(name+'/capture/'+tab+' navigation clipped');
    if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)) {
     console.error(await page.evaluate(()=>[...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>innerWidth+1).map(e=>({tag:e.tagName,cls:e.className,width:e.getBoundingClientRect().width,text:e.textContent.slice(0,60)}))));
     throw Error(name+'/capture/'+tab+' overflow');
    }
   }
   results.push({name,width,height,theme,errors});await ctx.close();
  }
  await fs.writeFile(path.join(out,process.argv[3]?'results-'+process.argv[3]+'.json':'results.json'),JSON.stringify({browser:browser.version(),results},null,2));console.log(JSON.stringify(results));
  if(results.some(r=>r.errors.length))process.exitCode=1;
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
