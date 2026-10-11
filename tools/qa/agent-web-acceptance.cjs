// Real browser, real isolated service. No response or DOM stubs.
const {chromium}=require('../../ankang/route1-health-agent/node_modules/playwright');
const fs=require('node:fs/promises'),path=require('node:path');
(async()=>{
  const [url,output]=process.argv.slice(2),out=path.resolve(output);await fs.mkdir(out,{recursive:true});
  const browser=await chromium.launch({channel:'msedge',headless:true});const results=[],errors=[];
  try{
    const context=await browser.newContext({viewport:{width:390,height:844}}),page=await context.newPage();
    page.on('pageerror',e=>errors.push(e.message));
    await page.goto(url);await page.locator('[name=code]').fill('test-code');await page.locator('#pair-form button').click();
    await page.locator('#nav:not([hidden])').waitFor();
    const navigate=async key=>{await page.evaluate(k=>location.hash=k,key);await page.locator('#draft').waitFor();};
    const send=async text=>{await page.locator('#draft').fill(text);await page.locator('#chat-form button[type=submit]').click();await page.waitForFunction(()=>{
      const draft=document.querySelector('#draft');
      return draft?draft.value==='':location.hash!=='#assistant'&&!document.querySelector('#nav')?.hidden&&document.body.dataset.busy!=='true'&&!document.querySelector('#pair-form');
    });};
    const settleDialog=async()=>{await page.locator('#dialog[open]').waitFor();await page.locator('#dialog').evaluate(async element=>{
      await Promise.all(element.getAnimations({subtree:true}).map(animation=>animation.finished.catch(()=>{})));
    });};
    await navigate('assistant');await send('查看健康记录和药物清单');
    await page.getByText('健康档案：',{exact:false}).last().waitFor();results.push('多模块真实查询');
    for(const text of ['我不查看健康记录','我没让你查看健康记录','今天张三健康记录有哪些','今天张三安排有哪些','我不查询今日安排']){
      const value=await page.evaluate(async text=>{
        const response=await fetch('/api/product/chat',{method:'POST',headers:{'Content-Type':'application/json','X-Rehab-Client':'mobile-v1'},body:JSON.stringify({text})});
        if(!response.ok)throw Error('Rejected query HTTP '+response.status);return response.json();
      },text);
      if(value.turn?.agent||value.turn?.care?.data)throw Error('Rejected query accessed module facts: '+text);
    }
    results.push('否定与他人查询拦截');
    const modules=await page.evaluate(async()=>{
      const response=await fetch('/api/product/chat',{method:'POST',headers:{'Content-Type':'application/json','X-Rehab-Client':'mobile-v1'},body:JSON.stringify({text:'查看健康记录、今天的安排'})});
      if(!response.ok)throw Error('Compound query HTTP '+response.status);return response.json();
    });
    if(modules.turn?.agent?.steps.map(s=>s.name).join(',')!=='health_overview,daily_overview')throw Error('Combined daily read lost a requested module');
    results.push('健康与今日安排联合查询');
    await send('记录今天08:00的TEST 网页确认药已服用');
    await page.locator('#care-review-0').waitFor();
    await page.reload();await page.locator('#care-review-0').waitFor();results.push('刷新恢复待确认任务');
    await page.locator('#care-review-0').click();
    await settleDialog();
    await page.screenshot({path:path.join(out,'mobile-confirmation.png')});
    await page.locator('#care-cancel').click();await page.locator('#dialog h2').filter({hasText:'操作结果'}).waitFor();
    await page.locator('#close-dialog').click();await page.locator('#care-review-0').waitFor({state:'detached'});results.push('显式取消');
    await send('记录今天08:00的TEST 网页确认药已服用');
    await page.locator('#care-review-0').click();await page.locator('#care-confirm').click();
    await page.locator('#dialog h2').filter({hasText:'操作结果'}).waitFor();await page.getByText('已保存',{exact:false}).last().waitFor();
    await page.locator('#close-dialog').click();await page.locator('#care-review-0').waitFor({state:'detached'});results.push('显式确认与真实回执');
    await send('打开用药页');await page.waitForURL(/#medication$/);results.push('模块导航');
    await navigate('assistant');await send('打开记录页');await page.waitForURL(/#records$/);await page.getByRole('heading',{name:'我的记录与周报',exact:true}).waitFor();results.push('记录页面导航');
    await navigate('assistant');await send('打开设置页');await page.waitForURL(/#settings$/);await page.locator('#settings-profile').waitFor();results.push('设置页面导航');
    await navigate('assistant');await send('打开通知页');await page.waitForURL(/#notifications$/);await page.getByRole('heading',{name:'通知记录',exact:true}).waitFor();results.push('通知台账页面导航');
    await navigate('assistant');await send('打开健身页');await page.waitForURL(/#rehab$/);await page.getByRole('link',{name:'打开动作库',exact:true}).waitFor();results.push('健身模式导航');
    await navigate('assistant');await page.emulateMedia({colorScheme:'dark'});await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:path.join(out,'mobile-dark.png')});
    await page.setViewportSize({width:768,height:1024});await page.screenshot({path:path.join(out,'tablet-dark.png'),fullPage:true});
    if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Horizontal overflow');
    await send('记录今天08:00的TEST 网页确认药已服用');await page.locator('#care-review-0').click();await settleDialog();
    await context.clearCookies();await page.evaluate(()=>document.querySelector('#refresh').click());
    await page.locator('#pair-form').waitFor();
    await page.waitForFunction(()=>!document.querySelector('#dialog').open&&!document.querySelector('#dialog').childElementCount);
    results.push('断开连接清除旧确认窗口');
    if(errors.length)throw Error(errors.join('\n'));
    await context.close();
  }finally{await fs.writeFile(path.join(out,'browser-results.json'),JSON.stringify({results,errors},null,2));await browser.close();}
  console.log(JSON.stringify({results,errors}));
})().catch(e=>{console.error(String(e));process.exitCode=1;});
