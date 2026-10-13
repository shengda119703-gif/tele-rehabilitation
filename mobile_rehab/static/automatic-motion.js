/* Bounded automatic video tracking. Plate size is a PRIOR, not a measured
 * dimension. Pose fallback is a wrist trajectory, never an invented barbell.
 * No network, user clicks, zero-filled gaps or inferred load mass. */
(function(root){
'use strict';
const VERSION='automatic-motion-1',G=9.80665;
const finite=v=>typeof v==='number'&&Number.isFinite(v);
const median=a=>{const b=a.filter(finite).sort((a,b)=>a-b);return b.length?b[Math.floor(b.length/2)]:null;};
function posePoints(landmarks,w,h){
 const p={};for(const [name,index]of Object.entries({nose:0,left_shoulder:11,right_shoulder:12,left_wrist:15,right_wrist:16,left_hip:23,right_hip:24})){
  const v=landmarks?.[index];if(v&&finite(v.x)&&finite(v.y)&&(v.visibility??1)>=.5&&v.x>=0&&v.x<=1&&v.y>=0&&v.y<=1)p[name]=[v.x*w,v.y*h];
 }return p;
}
function bodyScale(p,w,h){
 for(const side of ['left','right']){const a=p[side+'_shoulder'],b=p[side+'_hip'];if(a&&b&&Math.hypot(a[0]-b[0],a[1]-b[1])>=h*.08)return {pixels:Math.hypot(a[0]-b[0],a[1]-b[1]),source:'torso_length',unit:'躯干长度'};}
 const a=p.left_shoulder,b=p.right_shoulder;if(a&&b&&Math.hypot(a[0]-b[0],a[1]-b[1])>=w*.04)return {pixels:Math.hypot(a[0]-b[0],a[1]-b[1]),source:'shoulder_width',unit:'肩宽'};
 return {pixels:h,source:'image_height',unit:'画面高度'};
}
// Gradient-directed Hough voting at <=240 px: bounded CPU/memory, no model download.
function detectPlate(pixels,w,h,p={}){
 if(!pixels?.data||w<32||h<32||w*h>4096*4096)return null;
 const stride=Math.max(1,Math.ceil(Math.max(w,h)/240)),sw=Math.floor(w/stride),sh=Math.floor(h/stride),gray=new Float32Array(sw*sh),edges=[];
 for(let y=0;y<sh;y++)for(let x=0;x<sw;x++){const i=4*((y*stride)*w+x*stride);gray[y*sw+x]=.299*pixels.data[i]+.587*pixels.data[i+1]+.114*pixels.data[i+2];}
 for(let y=2;y<sh-2;y+=2)for(let x=2;x<sw-2;x+=2){const gx=gray[y*sw+x+1]-gray[y*sw+x-1],gy=gray[(y+1)*sw+x]-gray[(y-1)*sw+x],m=Math.hypot(gx,gy);if(m>45)edges.push([x,y,gx/m,gy/m]);}
 if(edges.length<15)return null;
 const sample=Math.max(1,Math.ceil(edges.length/1600)),rmax=Math.min(55,Math.floor(Math.min(sw,sh)*.25)),wrists=[p.left_wrist,p.right_wrist].filter(Boolean);let best=null;
 for(let r=8;r<=rmax;r+=3){const votes=new Uint16Array(sw*sh);
  for(let i=0;i<edges.length;i+=sample){const [x,y,nx,ny]=edges[i];for(const sign of [-1,1]){const cx=Math.round(x+sign*r*nx),cy=Math.round(y+sign*r*ny);if(cx>r&&cx<sw-r&&cy>r&&cy<sh-r)for(let dy=-1;dy<=1;dy++)for(let dx=-1;dx<=1;dx++)votes[(cy+dy)*sw+cx+dx]++;}}
  let candidates=[];for(let i=0;i<votes.length;i++)if(votes[i]>=4)candidates.push(i);candidates.sort((a,b)=>votes[b]-votes[a]);
  for(const index of candidates.slice(0,8)){const x=index%sw,y=Math.floor(index/sw),cx=x*stride,cy=y*stride,radius=r*stride;
   if(p.nose&&Math.hypot(cx-p.nose[0],cy-p.nose[1])<radius*1.5)continue;
   const distance=wrists.length?Math.min(...wrists.map(v=>Math.hypot(cx-v[0],cy-v[1]))):0;if(wrists.length&&distance>Math.max(radius*3,w*.3))continue;
   let supported=0;for(let j=0;j<24;j++){const a=j*Math.PI/12,ux=Math.cos(a),uy=Math.sin(a);let strength=0;for(let dr=-2;dr<=2;dr++){const ix=Math.round(x+(r+dr)*ux),iy=Math.round(y+(r+dr)*uy);if(ix>1&&ix<sw-2&&iy>1&&iy<sh-2){const gx=gray[iy*sw+ix+1]-gray[iy*sw+ix-1],gy=gray[(iy+1)*sw+ix]-gray[(iy-1)*sw+ix];strength=Math.max(strength,Math.abs(gx*ux+gy*uy));}}if(strength>35)supported++;}
   const coverage=supported/24;if(coverage<.7)continue;const score=coverage-distance/Math.max(w,h)*.6;
   if(!best||score>best.score)best={point:[cx,cy],radius,score,coverage};
  }
 }return best;
}
function quadratic(part,index){
 const row=part[index],neighbors=part.slice(Math.max(0,index-120),index+121),interval=median(neighbors.slice(1).map((p,i)=>p.t-neighbors[i].t)),radius=Math.min(.6,Math.max(.28,2.1*(interval||0))),window=neighbors.filter(p=>Math.abs(p.t-row.t)<=radius);if(window.length<5||window[0]===row||window.at(-1)===row)return null;
 const sums=Array(5).fill(0),rhs=Array(3).fill(0);for(const p of window){const t=p.t-row.t;for(let k=0;k<5;k++)sums[k]+=t**k;for(let k=0;k<3;k++)rhs[k]+=p.height*t**k;}
 const a=Array.from({length:3},(_,i)=>[...Array.from({length:3},(_,j)=>sums[i+j]),rhs[i]]);
 for(let k=0;k<3;k++){let pivot=k;for(let i=k+1;i<3;i++)if(Math.abs(a[i][k])>Math.abs(a[pivot][k]))pivot=i;[a[k],a[pivot]]=[a[pivot],a[k]];if(Math.abs(a[k][k])<1e-10)return null;const d=a[k][k];for(let j=k;j<4;j++)a[k][j]/=d;for(let i=0;i<3;i++)if(i!==k){const f=a[i][k];for(let j=k;j<4;j++)a[i][j]-=f*a[k][j];}}
 const coef=a.map(r=>r[3]),residual=Math.sqrt(window.reduce((s,p)=>s+(p.height-(coef[0]+coef[1]*(p.t-row.t)+coef[2]*(p.t-row.t)**2))**2,0)/window.length);
 return {v:coef[1],a:residual<.025?2*coef[2]:null};
}
function summarize(samples,measurement,total=samples.length){
 const metric=measurement?.length_unit==='m',mass=finite(measurement?.mass_kg)&&measurement.mass_kg>0?measurement.mass_kg:null,series=[],parts=[];let part=[],origin=null,last=null;
 for(const s of samples){const valid=s.point?.every(finite)&&finite(s.scale)&&s.scale>0;
  if(part.length&&(!valid||s.epoch!==last?.epoch||s.t-last.t>.3)){parts.push(part);part=[];origin=null;}
  const row={t:s.t,point:valid?s.point.map((v,i)=>v/s.size[i]):null,height:null,x:null,velocity:null,acceleration:null};
  if(valid){origin??=s.point;row.height=(origin[1]-s.point[1])/s.scale;row.x=(s.point[0]-origin[0])/s.scale;part.push(row);}series.push(row);last=s;
 }if(part.length)parts.push(part);
 for(const p of parts)for(let i=0;i<p.length;i++){const d=quadratic(p,i);if(d){p[i].velocity=d.v;p[i].acceleration=d.a;}}
 const lifts=[];for(const p of parts){let run=[],before=null,known=false;const finish=bounded=>{if(run.length>=3){const first=run[0],end=run.at(-1),duration=end.t-first.t,displacement=end.height-first.height;if(duration>=.15&&displacement>=(metric?.025:.04)){const peak=run.reduce((a,b)=>a.velocity>b.velocity?a:b);lifts.push({number:lifts.length+1,bounded:known&&bounded,duration_s:duration,displacement,mean_velocity:displacement/duration,peak_velocity:peak.velocity,peak_time_s:peak.t,time_to_peak_s:peak.t-first.t,mean_specific_power_w_kg:metric?G*displacement/duration:null});}}run=[];};
  for(const row of p){if(finite(row.velocity)&&row.velocity>(metric?.03:.06)){if(!run.length)known=finite(before?.velocity)&&before.velocity<=(metric?.03:.06);run.push(row);}else finish(finite(row.velocity));before=row;}finish(false);
 }
 const complete=lifts.filter(l=>l.bounded),speeds=complete.map(l=>l.mean_velocity),valid=series.filter(r=>finite(r.velocity)),positive=valid.filter(r=>r.velocity>0),peak=positive.length?Math.max(...positive.map(r=>r.velocity)):null;
 const output=series.map(r=>({t:r.t,point:r.point,x_m:metric?r.x:null,height_m:metric?r.height:null,velocity_m_s:metric?r.velocity:null,acceleration_m_s2:metric?r.acceleration:null,relative_height:metric?null:r.height,relative_velocity:metric?null:r.velocity,force_n:metric&&mass!==null&&finite(r.acceleration)?mass*(G+r.acceleration):null,power_w:metric&&mass!==null&&finite(r.velocity)&&finite(r.acceleration)?mass*(G+r.acceleration)*r.velocity:null,specific_lifting_power_w_kg:metric&&finite(r.velocity)?G*Math.max(0,r.velocity):null}));
 const peakField=key=>{const v=output.map(r=>r[key]).filter(finite);return v.length?Math.max(...v):null;};
 return {version:VERSION,automatic:true,synthetic:false,measurement:measurement||{target_kind:'unavailable',length_unit:'relative',speed_unit:'画面高度/s'},calibration:{mode:'automatic',length_m:measurement?.reference_length_m??null,mass_kg:mass},summary:{bounded_segments:complete.length,tracked_ratio:total?series.filter(r=>r.point).length/total:0,peak_velocity_m_s:metric?peak:null,peak_relative_velocity:metric?null:peak,peak_force_n:peakField('force_n'),peak_power_w:peakField('power_w'),peak_specific_lifting_power_w_kg:peakField('specific_lifting_power_w_kg'),last_vs_best_velocity_loss_pct:speeds.length>=2?100*(1-speeds.at(-1)/Math.max(...speeds)):null},lifts:lifts.map(l=>({...l,displacement_m:metric?l.displacement:null,mean_velocity_m_s:metric?l.mean_velocity:null,peak_velocity_m_s:metric?l.peak_velocity:null})),series:output,stop_reason:valid.length?'':'本段未取得连续轨迹，动作分析已保留。',assumptions:[measurement?.target_kind==='plate'?'自动圆形器械候选，按45厘米直径换算；未确认器械规格，长度与速度为近似值。':'手腕运动轨迹，不代表器械或人体重心。',metric?'单位负重抬升功率=g×上升速度，仅表示竖直重力功率分量。':'相对轨迹按实际可见躯干、肩宽或画面高度归一化，不换算米、牛顿或瓦。','重量未知时不推断重量；遮挡、尺度变化及时间缺口分段，不补轨迹。']};
}
class Tracker{
 constructor(options={}){this.options=options;this.samples=[];this.total=0;this.lock=null;this.pending=null;this.epoch=0;this.previous=null;this.wrist=null;this.measurement=null;this.size=null;this.relativeScale=null;this.lastPlate=null;this.fallback=[];this.fallbackEpoch=0;this.fallbackScale=null;this.wristEpochs={left_wrist:0,right_wrist:0};}
 frame(t,pixels,w,h,landmarks){return this.observe(t,pixels,w,h,posePoints(landmarks,w,h));}
 observe(t,pixels,w,h,p){
  if(!finite(t)||t<0||w<1||h<1||this.previous!==null&&t<=this.previous)return null;
  if(this.size&&(this.size[0]!==w||this.size[1]!==h)){this.epoch++;this.lock=this.pending=this.relativeScale=null;this.fallbackEpoch++;this.fallbackScale=null;}this.size=[w,h];
  this.previous=t;this.total++;
  this.wrist??=p[(this.options.side||'left')+'_wrist']?(this.options.side||'left')+'_wrist':p.right_wrist?'right_wrist':p.left_wrist?'left_wrist':null;
  if((p.left_wrist||p.right_wrist)&&!this.fallbackScale)this.fallbackScale=bodyScale(p,w,h);
  if(this.fallbackScale)for(const wrist of (this.options.side==='right'?['right_wrist','left_wrist']:['left_wrist','right_wrist'])){const s=this.fallbackScale,wristPoint=p[wrist]||null,previous=this.fallback.slice(-2).find(row=>row.measurement.target_source===wrist);if(wristPoint&&previous?.point&&Math.hypot(wristPoint[0]/w-previous.point[0]/previous.size[0],wristPoint[1]/h-previous.point[1]/previous.size[1])>.3)this.wristEpochs[wrist]++;
   if(this.fallback.length<30000)this.fallback.push({t,point:wristPoint,scale:s.pixels,size:[w,h],epoch:this.fallbackEpoch+':'+this.wristEpochs[wrist],measurement:{target_kind:'wrist',target_source:wrist,scale_source:s.source,length_unit:'relative',speed_unit:s.unit+'/s',mass_kg:null,approximate:false}});
  }
  const candidate=detectPlate(pixels,w,h,p);let point=null,scale=null,measurement=null;
  if(candidate){const consistent=this.pending&&Math.hypot(candidate.point[0]/w-this.pending.point[0]/this.pending.size[0],candidate.point[1]/h-this.pending.point[1]/this.pending.size[1])<.15&&Math.abs(candidate.radius/this.pending.radius-1)<.3;
   this.pending={...candidate,size:[w,h],count:consistent?this.pending.count+1:1};if(this.pending.count>=3){this.lastPlate=t;if(!this.lock){this.epoch++;this.lock={radius:candidate.radius/w};}if(Math.abs(candidate.radius/w/this.lock.radius-1)>.3){this.epoch++;this.lock={radius:candidate.radius/w};}point=candidate.point;scale=2*this.lock.radius*w/.45;measurement={target_kind:'plate',target_source:'gradient_circle_candidate',scale_source:'plate_diameter_prior',reference_length_m:.45,length_unit:'m',speed_unit:'m/s',mass_kg:null,approximate:true};}
  }else this.pending=null;
  if(this.lock&&this.lastPlate!==null&&t-this.lastPlate>1.2){this.lock=null;this.relativeScale=null;this.epoch++;}
  if(!this.lock){this.wrist??=p[(this.options.side||'left')+'_wrist']?(this.options.side||'left')+'_wrist':p.right_wrist?'right_wrist':p.left_wrist?'left_wrist':null;point=p[this.wrist]||null;const s=bodyScale(p,w,h);if(!this.relativeScale||this.relativeScale.source!==s.source)this.relativeScale=s;scale=this.relativeScale.pixels;measurement={target_kind:'wrist',target_source:this.wrist,scale_source:s.source,length_unit:'relative',speed_unit:s.unit+'/s',mass_kg:null,approximate:false};}
  if(measurement&&this.measurement&&(measurement.target_kind!==this.measurement.target_kind||measurement.scale_source!==this.measurement.scale_source))this.epoch++;
  const before=this.samples.at(-1);if(point&&before?.point&&measurement?.target_kind==='wrist'&&Math.hypot(point[0]/w-before.point[0]/before.size[0],point[1]/h-before.point[1]/before.size[1])>.3)this.epoch++;
  if(measurement)this.measurement=measurement;
  if(this.samples.length<15000)this.samples.push({t,point,scale,size:[w,h],epoch:this.epoch,measurement:this.measurement});
  return point?{point,measurement}:null;
 }
 missing(t,w,h){if(!finite(t)||this.previous!==null&&t<=this.previous)return;this.epoch++;this.fallbackEpoch++;this.total++;this.previous=t;if(this.samples.length<15000)this.samples.push({t,point:null,scale:null,size:[w,h],epoch:this.epoch,measurement:this.measurement});}
 report(){const groups=new Map();for(const s of [...this.samples.filter(s=>s.measurement?.target_kind==='plate'),...this.fallback]){if(!s.measurement)continue;const k=s.measurement.target_kind+':'+s.measurement.target_source+':'+s.measurement.scale_source;const g=groups.get(k)||{m:s.measurement,samples:[],valid:0};g.samples.push(s);if(s.point)g.valid++;groups.set(k,g);}
  const reports=[...groups.values()].map(g=>({g,r:summarize(g.samples,g.m,this.total)})),plates=reports.filter(({g,r})=>g.m.target_kind==='plate'&&g.valid>=Math.max(5,this.total*.5)&&r.series.filter(s=>finite(s.velocity_m_s)).length>=Math.max(3,this.total*.3)),wrists=reports.filter(({g})=>g.m.target_kind==='wrist');
  return (plates.length?plates:wrists).sort((a,b)=>b.r.summary.tracked_ratio-a.r.summary.tracked_ratio)[0]?.r||summarize([],null,this.total);
 }
}
const api={VERSION,Tracker,detectPlate,bodyScale,posePoints,summarize};if(typeof module!=='undefined')module.exports=api;else root.AutomaticMotion=api;
})(typeof self!=='undefined'?self:globalThis);
