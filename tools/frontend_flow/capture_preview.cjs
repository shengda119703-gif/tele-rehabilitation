// Real retained capture page rendered in Chromium. Metadata-only TEST responses
// are for visual comparison, not backend, camera, or clinical acceptance.
'use strict';
const http=require('node:http'),fs=require('node:fs/promises'),path=require('node:path');
const {chromium}=require('../../ankang/route1-health-agent/node_modules/playwright');
const root=path.resolve(__dirname,'../..'),staticRoot=path.join(root,'mobile_rehab/static');
async function main(){
 const output=path.resolve(process.argv[2]);await fs.mkdir(output,{recursive:true});
 const catalog=JSON.parse(await fs.readFile(path.join(root,'android_offline/build/assets/catalog.json'),'utf8'));
 const server=http.createServer(async(req,res)=>{try{
  const pathname=new URL(req.url,'http://localhost').pathname;
  if(pathname==='/api/catalog'){res.setHeader('Content-Type','application/json');res.end(JSON.stringify({shared:true,exercises:catalog.rehab,fitness:catalog.fitness,posture:catalog.posture}));return;}
  if(pathname.startsWith('/api/')){res.writeHead(404);res.end(JSON.stringify({detail:'TEST: this presentation harness has no backend write capability'}));return;}
  const filename=pathname==='/capture'?path.join(staticRoot,'index.html'):path.resolve(staticRoot,'.'+pathname.replace(/^\/static/,''));
  if(!filename.startsWith(staticRoot+path.sep)){res.writeHead(403);res.end();return;}
  res.setHeader('Content-Type',filename.endsWith('.js')?'application/javascript':filename.endsWith('.css')?'text/css':filename.endsWith('.html')?'text/html':'application/octet-stream');
  res.end(await fs.readFile(filename));
 }catch(error){res.writeHead(404);res.end(String(error));}});
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 let browser;
 try{
  browser=await chromium.launch({channel:'msedge',headless:true});const results=[];
  for(const [name,width,height] of [['mobile',390,844],['desktop',1440,940]]){
   const context=await browser.newContext({viewport:{width,height},colorScheme:'light'});
   const page=await context.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message));
   await page.goto(`http://127.0.0.1:${server.address().port}/capture?tab=assess`);
   await page.locator('[data-action="shoulder_abduction"]').waitFor();
   await page.locator('[data-action="shoulder_abduction"]').click();
   await page.screenshot({path:path.join(output,name+'-action.png'),fullPage:true});
   await page.getByRole('button',{name:'实时跟练',exact:true}).click();
   await page.screenshot({path:path.join(output,name+'-live.png'),fullPage:true});
   const observation=await page.evaluate(()=>Object.fromEntries(['live-start','live-stop','live-back','live-video','live-facing'].map(id=>{
    const element=document.getElementById(id),r=element.getBoundingClientRect(),style=getComputedStyle(element);
    return[id,{x:r.x,y:r.y,width:r.width,height:r.height,font:style.fontFamily,fontSize:style.fontSize}];
   })));
   if(errors.length)throw Error(JSON.stringify(errors));results.push({name,width,height,observation,errors});await context.close();
  }
  await fs.writeFile(path.join(output,'observations.json'),JSON.stringify({presentation_only:true,backend_writes:false,camera_used:false,results},null,2));
  console.log(JSON.stringify({output,results}));
 }finally{await browser?.close();await new Promise(resolve=>server.close(resolve));}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
