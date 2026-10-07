/* Template-tracked 2-D free-weight estimates, never muscle force or joint torque. */
(function(root){
'use strict';
const finite=v=>typeof v==='number'&&Number.isFinite(v), median=a=>{const b=[...a].sort((x,y)=>x-y);return b[Math.floor(b.length/2)];};
class Tracker {
 constructor(calibration){this.c=calibration;this.template=null;this.last=null;this.samples=[];this.failed=0;}
 frame(t,pixels,w,h){
  const gray=new Float32Array(w*h);for(let i=0;i<gray.length;i++)gray[i]=.299*pixels[i*4]+.587*pixels[i*4+1]+.114*pixels[i*4+2];
  const size=10;
  const patch=(x,y)=>{if(x<size||y<size||x>=w-size||y>=h-size)return null;const v=[];for(let j=-size;j<=size;j+=2)for(let i=-size;i<=size;i+=2)v.push(gray[(Math.round(y)+j)*w+Math.round(x)+i]);const avg=v.reduce((s,v)=>s+v,0)/v.length;const centered=v.map(x=>x-avg),norm=Math.sqrt(centered.reduce((s,x)=>s+x*x,0));return norm>=20?{centered,norm}:null;};
  if(!this.template){
   this.last=[Math.round(this.c.points[0][0]*w),Math.round(this.c.points[0][1]*h)];this.template=patch(...this.last);if(!this.template){this.failed++;return null;}this.origin=this.last[1];
   const a=this.c.points[1],b=this.c.points[2];this.pixelsPerMeter=Math.hypot((a[0]-b[0])*w,(a[1]-b[1])*h)/this.c.meters;if(this.pixelsPerMeter<5){this.template=null;this.failed++;return null;}
   this.samples.push([t,0,1,0,[this.last[0]/w,this.last[1]/h]]);this.originX=this.last[0];return {y:0,confidence:1};
  }
  let best=null;
  for(let y=this.last[1]-44;y<=this.last[1]+44;y+=2)for(let x=this.last[0]-36;x<=this.last[0]+36;x+=2){const p=patch(x,y);if(!p)continue;const score=p.centered.reduce((s,v,i)=>s+v*this.template.centered[i],0)/(p.norm*this.template.norm);if(!best||score>best.score)best={x,y,score};}
  if(!best||best.score<.75){this.failed++;return null;}
  this.last=[best.x,best.y];const height=(this.origin-best.y)/this.pixelsPerMeter;this.samples.push([t,height,best.score,(best.x-this.originX)/this.pixelsPerMeter,[best.x/w,best.y/h]]);return {y:height,confidence:best.score};
 }
 report(){return summarize(this.samples,this.c.kg,this.failed);}
}
function derivative(series){return series.map((p,i)=>{const window=series.slice(Math.max(0,i-3),Math.min(series.length,i+4));if(window.length<5||window.at(-1)[0]-window[0][0]>.95)return [p[0],null];const mt=window.reduce((s,x)=>s+x[0],0)/window.length,my=window.reduce((s,x)=>s+x[1],0)/window.length;const denom=window.reduce((s,x)=>s+(x[0]-mt)**2,0);return [p[0],denom>0?window.reduce((s,x)=>s+(x[0]-mt)*(x[1]-my),0)/denom:null];});}
function summarize(samples,kg=null,failed=0){
 if(samples.length<8)return {valid:false,note:'跟踪数据不足，请重新选择器械上的清晰位置',samples:samples.length};
 let best=[],run=[];for(const p of samples){if(run.length&&p[0]-run.at(-1)[0]>.3){if(run.length>best.length)best=run;run=[];}run.push(p);}if(run.length>best.length)best=run;
 if(best.length<8)return {valid:false,note:'连续跟踪不足',samples:samples.length};
 const smoothed=best.map((p,i)=>[p[0],median(best.slice(Math.max(0,i-2),i+3).map(x=>x[1]))]);const speed=derivative(smoothed),validSpeed=speed.filter(p=>finite(p[1])),acc=derivative(validSpeed),mass=finite(kg)&&kg>0?kg:null;
 const rows=validSpeed.map(([t,v])=>{const a=acc.find(x=>x[0]===t)?.[1];const force=mass!==null&&finite(a)?mass*(9.80665+a):null;const point=best.find(x=>x[0]===t);return {t,v,a:finite(a)?a:null,force,power:force!==null?force*v:null,height:point?.[1]??null,x:point?.[3]??null,point:point?.[4]??null};});
 return {valid:true,contract:'android-free-weight-2d-1',samples:samples.length,coverage:samples.length/(samples.length+failed),peakSpeed:rows.length?Math.max(...rows.map(x=>Math.abs(x.v))):null,peakAcceleration:rows.some(x=>x.a!==null)?Math.max(...rows.filter(x=>x.a!==null).map(x=>Math.abs(x.a))):null,peakForce:mass!==null&&rows.some(x=>x.force!==null)?Math.max(...rows.filter(x=>x.force!==null).map(x=>x.force)):null,peakPower:mass!==null&&rows.some(x=>x.power!==null)?Math.max(0,...rows.filter(x=>x.power!==null&&x.v>0).map(x=>x.power)):null,mass,displacement:Math.max(...best.map(x=>x[1]))-Math.min(...best.map(x=>x[1])),rows,note:'二维器械运动估算；自由重量外力 F=m(g+a)，功率 P=Fv。不是肌肉力量、关节力矩或人体爆发力实测。'};
}
const api={Tracker,derivative,summarize};if(typeof module!=='undefined')module.exports=api;else root.LocalBarbell=api;
})(typeof self!=='undefined'?self:globalThis);
