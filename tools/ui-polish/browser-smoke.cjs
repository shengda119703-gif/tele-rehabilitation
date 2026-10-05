// Tests browser capability against a local QA fixture; this is not the Qt product.
const { chromium } = require('../../ankang/route1-health-agent/node_modules/playwright');
const http = require('node:http');
const fs = require('node:fs/promises');
const path = require('node:path');
async function main() {
  const out = path.resolve(process.argv[2] || 'qa-output/ui-env/browser');
  await fs.mkdir(out,{recursive:true});
  const server=http.createServer((req,res)=>{
    res.writeHead(200,{'Content-Type':'text/html; charset=utf-8'});
    res.end('<!doctype html><html lang="zh"><meta name="viewport" content="width=device-width,initial-scale=1"><title>UI Environment Smoke Test</title><body><h1>UI 环境能力测试</h1><p>QA fixture；不是 Qt 正式产品页面。</p><button id="test">测试交互</button><output id="result"></output><script>test.onclick=()=>{result.textContent="PASS"}</script></body></html>');
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  let browser;
  try {
    browser=await chromium.launch({channel:process.env.UI_BROWSER_CHANNEL || 'msedge',headless:true});
    const results=[];
    for(const [name,width,height] of [['desktop',1440,940],['tablet',768,1024],['mobile',390,844]]) {
      const context=await browser.newContext({viewport:{width,height},reducedMotion:'reduce'});
      const page=await context.newPage();const errors=[];
      page.on('pageerror',e=>errors.push(e.message));page.on('console',msg=>{if(msg.type()==='error')errors.push(msg.text())});
      await page.goto(`http://127.0.0.1:${server.address().port}`,{waitUntil:'networkidle'});
      await page.locator('#test').click();
      if(await page.locator('#result').textContent() !== 'PASS')throw new Error('Interaction failed');
      await page.screenshot({path:path.join(out,`${name}.png`),fullPage:true});
      results.push({name,width,height,consoleErrors:errors,screenshot:`${name}.png`,interaction:'PASS'});
      await context.close();
    }
    await fs.writeFile(path.join(out,'results.json'),JSON.stringify({target:'local QA fixture, NOT Qt product',browser:browser.version(),results},null,2));
    if(results.some(r=>r.consoleErrors.length))throw new Error('Console errors; inspect results.json');
    console.log(JSON.stringify({status:'PASS',out,browser:browser.version(),results}));
  } finally {await browser?.close();await new Promise(resolve=>server.close(resolve));}
}
main().catch(e=>{console.error(e);process.exitCode=1});
