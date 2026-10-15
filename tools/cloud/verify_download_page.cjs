'use strict';
// Anonymous real browser checks. Clipboard writes are stubbed to preserve the
// user's system clipboard; the real download stream is checked separately.
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('../../ankang/route1-health-agent/node_modules/playwright');
async function main(){
 const [origin,output]=process.argv.slice(2);if(!origin||!output)throw Error('Origin and fresh output required');
 const out=path.resolve(output);await fs.mkdir(out,{recursive:false});
 const browser=await chromium.launch({channel:'msedge',headless:true}),errors=[],csp=[],results=[];
 const manifest=JSON.parse(await fs.readFile(path.join(__dirname,'../../cloud_service/static/android-downloads.json'),'utf8'));
 const release=manifest.releases.find(r=>r.version===manifest.default),filename='downloaded-ankang-'+release.version+'.apk';
 try{
  for(const [name,width,height] of [['mobile',390,844],['desktop',1440,940],['narrow',320,760]]){
   const context=await browser.newContext({viewport:{width,height}}),page=await context.newPage();
   page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error'&&/Content Security Policy|Refused to/i.test(m.text()))csp.push(m.text());});
   await context.addInitScript(()=>Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async text=>{window.__copiedContact=text;}}}));
   await page.goto(origin+'/download');await page.getByRole('heading',{name:'安康 Android 版',exact:true}).waitFor();
   assert.equal(await page.locator('#wechat').textContent(),'AK2452409');assert((await page.locator('.release-info').textContent()).includes(release.version));
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
   await page.getByRole('button',{name:'复制微信号',exact:true}).click();await page.getByText('已复制，在微信中搜索添加。',{exact:true}).waitFor();
   assert.equal(await page.evaluate(()=>window.__copiedContact),'AK2452409');assert.equal(await page.locator('#copy-wechat').isDisabled(),false);
   await page.screenshot({path:path.join(out,'download-'+name+'.png'),fullPage:true});
   await page.getByText('安装包信息与其他版本',{exact:true}).click();await page.getByRole('link',{name:'Android 0.3.1',exact:true}).waitFor();
   assert((await page.locator('details').textContent()).includes(release.sha256.toLowerCase()));
   // The actual attachment GET is exercised on one browser, not a fake link.
   if(name==='mobile'){
    const filePromise=page.waitForEvent('download');await page.getByRole('link',{name:'下载 Android 安装包',exact:true}).click();
    const download=await filePromise;assert.equal(download.suggestedFilename(),release.file);
    assert.equal(await download.failure(),null);await download.saveAs(path.join(out,filename));
   }
   await page.evaluate(()=>Object.defineProperty(navigator,'clipboard',{value:{writeText:async()=>{throw Error('Clipboard unavailable');}}}));
   await page.getByRole('button',{name:'复制微信号',exact:true}).click();await page.getByText('微信号已选中，请长按或手动复制。',{exact:true}).waitFor();
   assert.equal(await page.evaluate(()=>getSelection().toString()),'AK2452409');
   await page.getByRole('link',{name:'网页版',exact:true}).click();await page.waitForURL(u=>u.pathname==='/account');
   await page.locator('#connect-account').waitFor({state:'visible'});await page.locator('#connect-account').click();
   await page.locator('[name="username"]').waitFor();await page.getByRole('link',{name:'下载App',exact:true}).click();await page.waitForURL(u=>u.pathname==='/download');
   assert.equal((await context.cookies()).length,0);
   results.push({name,width,height,public_without_login:true,no_horizontal_overflow:true,copy_contract:true,copy_fallback:true,web_login_link:true});await context.close();
  }
  assert.deepEqual(errors,[]);assert.deepEqual(csp,[]);
  const crypto=require('node:crypto'),apk=await fs.readFile(path.join(out,filename));
  const sha=crypto.createHash('sha256').update(apk).digest('hex');assert.equal(apk.length,release.bytes);assert.equal(sha,release.sha256.toLowerCase());
  const report={origin,tls_bypass:false,views:results,browser_errors:errors,csp_errors:csp,download:{bytes:apk.length,sha256:sha},clipboard_native_test:false};
  await fs.writeFile(path.join(out,'result.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
 }finally{await browser.close();}
}
main().catch(e=>{console.error(e.message);process.exitCode=1;});
