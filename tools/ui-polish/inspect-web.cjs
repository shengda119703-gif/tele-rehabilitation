// Screenshot an actual web target/reference without modifying or submitting data.
const {chromium}=require('../../ankang/route1-health-agent/node_modules/playwright');
const fs=require('node:fs/promises');const path=require('node:path');
async function main(){
  const url=process.argv[2];if(!url || !/^https?:\/\//.test(url))throw new Error('Usage: node tools/ui-polish/inspect-web.cjs URL [OUTPUT]');
  const out=path.resolve(process.argv[3] || 'qa-output/ui-env/web-review');await fs.mkdir(out,{recursive:true});
  const browser=await chromium.launch({channel:process.env.UI_BROWSER_CHANNEL || 'msedge',headless:true});const results=[];
  try{
    for(const [name,width,height] of [['desktop',1440,940],['tablet',768,1024],['mobile',390,844]]){
      const context=await browser.newContext({viewport:{width,height},reducedMotion:'reduce'});const page=await context.newPage();const errors=[];
      page.on('console',m=>{if(m.type()==='error')errors.push(m.text())});page.on('pageerror',e=>errors.push(e.message));
      const response=await page.goto(url,{waitUntil:'networkidle',timeout:60000});
      await page.screenshot({path:path.join(out,`${name}.png`),fullPage:true});
      await fs.writeFile(path.join(out,`${name}.txt`),await page.locator('body').innerText());
      results.push({name,width,height,status:response?.status(),title:await page.title(),errors,screenshot:`${name}.png`});await context.close();
    }
    await fs.writeFile(path.join(out,'results.json'),JSON.stringify({url,browser:browser.version(),results},null,2));console.log(JSON.stringify({out,results}));
    if(results.some(r=>r.status>=400 || r.errors.length))process.exitCode=1;
  }finally{await browser.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1});
