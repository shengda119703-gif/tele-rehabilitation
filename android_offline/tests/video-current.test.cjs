const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../web/motion.js'),'utf8');
// Exercise the actual packaged decoder helper without running browser/model setup.
const helper=source.slice(source.indexOf('async function bitmap('),source.indexOf('function summary('));
function context(values){const c={...values};vm.createContext(c);vm.runInContext(helper,c);return c;}
test('packaged decoder waits for real video data and draws the decoded frame',async()=>{
 const video={readyState:1,seeking:true,videoWidth:0,videoHeight:1080},draws=[];
 class Canvas{constructor(w,h){this.width=w;this.height=h;}getContext(){return{drawImage:(...a)=>draws.push(a)};}transferToImageBitmap(){return{width:this.width,height:this.height};}}
 const c=context({performance:{now:()=>0},OffscreenCanvas:Canvas,setTimeout:fn=>{video.readyState=2;video.seeking=false;video.videoWidth=1920;fn();}});
 const out=await c.bitmap(video,768,{cancelled:false});assert.equal(draws.length,1);assert.equal(draws[0][0],video);assert.equal(out.w,768);assert.equal(out.h,432);
});
test('packaged decoder timeout, cancellation and video error reject without invented frames',async()=>{
 let n=0;const c=context({performance:{now:()=>n++?10001:0}});
 await assert.rejects(c.bitmap({readyState:0},768,{cancelled:false}),/解码失败/);
 await assert.rejects(c.bitmap({readyState:0},768,{cancelled:true}),/已停止/);
 await assert.rejects(c.bitmap({readyState:0,error:{}},768,{cancelled:false}),/解码失败/);
});
test('packaged worker preloads buffers and native insets remain outside WebView',()=>{
 assert(source.includes('self.exports={}'));assert.match(source,/poseModel:pose,handModel:hand/);
 const java=fs.readFileSync(path.join(__dirname,'../src/cn/tele/rehabilitation/offline/MainActivity.java'),'utf8');assert.match(java,/container.setOnApplyWindowInsetsListener/);
});
