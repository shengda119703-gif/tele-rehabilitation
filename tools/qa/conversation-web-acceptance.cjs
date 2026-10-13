// Real Edge and TEST server. No DOM, API or model-response stubs.
const {chromium}=require('../../ankang/route1-health-agent/node_modules/playwright');
const fs=require('node:fs/promises'),path=require('node:path');
(async()=>{
  const [url,output]=process.argv.slice(2),out=path.resolve(output);
  const browser=await chromium.launch({channel:'msedge',headless:true}),results=[],errors=[];
  try{
    const context=await browser.newContext({viewport:{width:390,height:844}}),page=await context.newPage();
    page.on('pageerror',e=>errors.push(e.message));
    await page.goto(url);await page.locator('[name=code]').fill('test-code');await page.locator('#pair-form button').click();
    await page.locator('#nav:not([hidden])').waitFor();
    await page.evaluate(()=>location.hash='assistant');await page.locator('#draft').waitFor();
    await page.locator('#draft').fill('你喜欢我吗');await page.locator('#chat-form button[type=submit]').click();
    await page.locator('.bubble small').filter({hasText:'未配置 DeepSeek · 本地回复'}).waitFor();
    const snapshot=await page.evaluate(async()=>{
      const response=await fetch('/api/unified',{headers:{'X-Rehab-Client':'mobile-v1'}});
      if(!response.ok)throw Error('Snapshot '+response.status);return (await response.json()).snapshot;
    });
    const metadata=snapshot.state.chat.at(-1).conversation;
    if(JSON.stringify(metadata)!==JSON.stringify({provider:'local',status:'unavailable',reason:'not_configured'}))throw Error('Incorrect actual reply metadata');
    if(snapshot.state.events.length)throw Error('Ordinary conversation added health facts');
    results.push('普通聊天实际离线路径与来源标签');
    await page.locator('.assistant-capability summary').click();
    await page.getByText('本地模块查询与页面导航可用；DeepSeek 对话尚未配置。',{exact:true}).waitFor();
    results.push('配置状态与回复来源分别显示');
    await page.locator('.assistant-capability summary').click();
    await page.locator('#message').waitFor({state:'hidden'});
    const settle=async()=>page.evaluate(async()=>{
      await Promise.all(document.getAnimations().map(animation=>animation.finished.catch(()=>{})));
    });
    await settle();
    await page.screenshot({path:path.join(out,'mobile-chat-light.png'),fullPage:true});
    await page.emulateMedia({colorScheme:'dark'});await settle();await page.screenshot({path:path.join(out,'mobile-chat-dark.png'),fullPage:true});
    await page.setViewportSize({width:768,height:1024});await settle();await page.screenshot({path:path.join(out,'tablet-chat-dark.png'),fullPage:true});
    if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Horizontal overflow');
    await page.reload();await page.locator('.bubble small').filter({hasText:'未配置 DeepSeek · 本地回复'}).waitFor();
    results.push('刷新保留该条回复的实际来源');
    if(errors.length)throw Error(errors.join('\n'));
    await context.close();
  }finally{
    await fs.writeFile(path.join(out,'browser-results.json'),JSON.stringify({results,errors},null,2));
    await browser.close();
  }
  console.log(JSON.stringify({results,errors}));
})().catch(e=>{console.error(String(e));process.exitCode=1;});
