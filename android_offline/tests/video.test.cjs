const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const app=fs.readFileSync(require('node:path').join(__dirname,'../web/app.js'),'utf8');
const helper=app.slice(app.indexOf('async function decodedVideoBitmap'),app.indexOf('async function frame('));
test('Android video capture waits for decoded data and draws that video, not a blank placeholder',async()=>{
 const video={readyState:1,seeking:true,videoWidth:0,videoHeight:1080},draws=[];
 class Canvas{constructor(w,h){this.width=w;this.height=h;}getContext(){return {drawImage:(...args)=>draws.push(args)};}transferToImageBitmap(){return {width:this.width,height:this.height};}}
 const ctx={performance:{now:()=>0},session:{cancelled:false},OffscreenCanvas:Canvas,setTimeout:fn=>{video.readyState=2;video.seeking=false;video.videoWidth=1920;fn();}};
 vm.createContext(ctx);vm.runInContext(helper,ctx);const out=await ctx.decodedVideoBitmap(video);assert.equal(draws.length,1);assert.equal(draws[0][0],video);assert.equal(out.width,768);assert.equal(out.height,432);
});
test('decoder timeout and cancellation reject instead of adding invented frames',async()=>{
 let calls=0;const ctx={performance:{now:()=>calls++?10001:0},session:{cancelled:false}};vm.createContext(ctx);vm.runInContext(helper,ctx);
 await assert.rejects(ctx.decodedVideoBitmap({readyState:0}),/超时/);ctx.session.cancelled=true;await assert.rejects(ctx.decodedVideoBitmap({readyState:0}),/已停止/);
});
test('APK worker preloads bundled buffers and native insets are applied outside WebView',()=>{
 assert.match(app,/self.exports=\{\}/);assert.match(app,/poseModel,handModel/);
 const java=fs.readFileSync(require('node:path').join(__dirname,'../src/cn/tele/rehabilitation/offline/MainActivity.java'),'utf8');assert.match(java,/container.setOnApplyWindowInsetsListener/);
});
