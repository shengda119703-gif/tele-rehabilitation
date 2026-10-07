/* Independent mobile projection contract. Never silently substitute for desktop YOLO. */
(function(root){
'use strict';
const VERSION='android-local-projection-1', finite=v=>typeof v==='number'&&Number.isFinite(v);
const rad=180/Math.PI, distance=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1]);
const vector=(a,b)=>[b[0]-a[0],b[1]-a[1]];
const delta=(a,b)=>((a-b+540)%360)-180;
const median=values=>{if(!values.length)return null;const a=[...values].sort((x,y)=>x-y),i=Math.floor(a.length/2);return a.length%2?a[i]:(a[i-1]+a[i])/2;};
function signed(u,v,minU=8,minV=8){if(Math.hypot(...u)<minU||Math.hypot(...v)<minV)return null;return Math.atan2(u[0]*v[1]-u[1]*v[0],u[0]*v[0]+u[1]*v[1])*rad;}
function angle(a,b,c,min=8){if(!a||!b||!c)return null;const u=vector(b,a),v=vector(b,c),d=Math.hypot(...u)*Math.hypot(...v);if(distance(a,b)<min||distance(b,c)<min)return null;return Math.acos(Math.max(-1,Math.min(1,(u[0]*v[0]+u[1]*v[1])/d)))*rad;}
const MAP={left_eye:2,right_eye:5,left_ear:7,right_ear:8,left_shoulder:11,right_shoulder:12,left_elbow:13,right_elbow:14,left_wrist:15,right_wrist:16,left_hip:23,right_hip:24,left_knee:25,right_knee:26,left_ankle:27,right_ankle:28,left_heel:29,right_heel:30,left_foot_index:31,right_foot_index:32};
function points(result,width,height){
 const out={};if(!result?.pose)return out;
 for(const [name,i] of Object.entries(MAP)){const p=result.pose[i];if(p&&finite(p.x)&&finite(p.y)&&p.x>=0&&p.x<1&&p.y>=0&&p.y<1&&finite(p.visibility)&&p.visibility>=.5&&(p.presence===undefined||p.presence>=.5))out[name]=[p.x*width,p.y*height];}
 return out;
}
function measure(spec,side,result,width,height){
 const p=points(result,width,height),at=n=>p[side+'_'+n], s=at('shoulder'),e=at('elbow'),w=at('wrist'),h=at('hip'),k=at('knee'),a=at('ankle');
 const flex=(x,y,z)=>{const v=angle(x,y,z);return v===null?null:180-v;};
 const pair=(x,y,f)=>x&&y?f(x,y):null;
 const both=(x,y,z,f)=>x&&y&&z?f(x,y,z):null;
 const arm=pair(s,e,(s,e)=>angle([s[0],s[1]+100],s,e));
 const hipAbd=both(h,p[(side==='left'?'right':'left')+'_hip'],k,(h,other,k)=>{const outward=vector(other,h),width=Math.hypot(...outward),thigh=vector(h,k);if(width<30||Math.hypot(...thigh)<20)return null;const across=outward.map(x=>x/width),down=[-across[1],across[0]];if(down[1]<0){down[0]*=-1;down[1]*=-1;}return Math.atan2(thigh[0]*across[0]+thigh[1]*across[1],thigh[0]*down[0]+thigh[1]*down[1])*rad;});
 const m={raise_deg:arm,elbow_flexion_deg:flex(s,e,w),knee_flexion_deg:flex(h,k,a),hip_abduction_deg:hipAbd,
 shoulder_sagittal_raw_deg:pair(s,e,(s,e)=>signed([0,1],vector(s,e),1,20)),hip_sagittal_raw_deg:both(s,h,k,(s,h,k)=>signed(vector(s,h),vector(h,k),30,20)),
 head_pitch_raw_deg:pair(at('ear'),at('eye'),(ear,eye)=>signed([1,0],vector(ear,eye),1,12)),
 trunk_sagittal_raw_deg:pair(h,s,(h,s)=>signed([0,-1],vector(h,s),1,50)),
 knee:angle(h,k,a),hip:angle(s,h,k),elbow:angle(s,e,w),body_line:angle(s,h,a),
 torso:pair(h,s,(h,s)=>Math.atan2(Math.abs(s[0]-h[0]),h[1]-s[1])*rad),
 upper_arm:pair(e,s,(e,s)=>Math.atan2(Math.abs(s[0]-e[0]),e[1]-s[1])*rad)};
 if(p.left_shoulder&&p.right_shoulder&&p.left_eye&&p.right_eye)m.head_roll_raw_deg=signed(vector(p.left_shoulder,p.right_shoulder),vector(p.left_eye,p.right_eye),40,12);
 if(p.left_hip&&p.right_hip&&p.left_shoulder&&p.right_shoulder){const mid=(a,b)=>[(a[0]+b[0])/2,(a[1]+b[1])/2];m.trunk_frontal_raw_deg=distance(p.left_shoulder,p.right_shoulder)<40?null:signed(vector(p.left_hip,p.right_hip),vector(mid(p.left_hip,p.right_hip),mid(p.left_shoulder,p.right_shoulder)),30,50);}
 if(k&&a&&at('heel')&&at('foot_index'))m.ankle_raw_deg=signed(vector(a,k),vector(at('heel'),at('foot_index')),20,15);
 if(result?.hand){
  const hand=result.hand.map(x=>x&&finite(x.x)&&finite(x.y)&&x.x>=0&&x.x<1&&x.y>=0&&x.y<1?[x.x*width,x.y*height]:null);
  // Hand SDK has handedness, but NO per-point visibility scores. Do not invent them.
  const match=result.handedness?.categoryName?.toLowerCase()===side&&result.handedness?.score>=.5;
  if(match){
   for(const [finger,base] of [['thumb',1],['index',5],['middle',9],['ring',13],['pinky',17]]){
    const joints=finger==='thumb'?[['mcp',2],['ip',3]]:[['mcp',base],['pip',base+1],['dip',base+2]];
    for(const [joint,i] of joints){const v=angle(hand[joint==='mcp'&&finger!=='thumb'?0:i-1],hand[i],hand[i+1],4);m[`${finger}_${joint}_flexion_deg`]=v===null?null:180-v;}
   }
   if(e&&w&&hand[0]&&hand[9]&&distance(w,hand[0])<=.08*Math.hypot(width,height))m.wrist_raw_deg=signed(vector(e,w),vector(hand[0],hand[9]),20,20);
  }
 }
 if(spec.id.startsWith('posture_')){
  const line=(x,y,horizontal)=>pair(x,y,(x,y)=>distance(x,y)>=8?Math.atan2(horizontal?Math.abs(x[1]-y[1]):Math.abs(x[0]-y[0]),horizontal?Math.abs(x[0]-y[0]):Math.abs(x[1]-y[1]))*rad:null);
  const mid=(x,y)=>x&&y?[(x[0]+y[0])/2,(x[1]+y[1])/2]:null;
  if(spec.view==='frontal')return {shoulder_level:line(p.left_shoulder,p.right_shoulder,true),hip_level:line(p.left_hip,p.right_hip,true),trunk_lean:line(mid(p.left_shoulder,p.right_shoulder),mid(p.left_hip,p.right_hip),false)};
  return {trunk_lean:line(s,h,false),head_offset:s&&h&&at('ear')&&distance(s,h)>=30?100*Math.abs(at('ear')[0]-s[0])/distance(s,h):null,knee_angle:angle(h,k,a)};
 }
 if(spec.joint==='finger')return m[spec.metric]??null;
 return m[spec.raw_metric||spec.metric]??null;
}
function stableReference(samples,spec){
 for(let start=0;start<=samples.length-5;start++){
  const run=samples.slice(start);if(run.at(-1)[0]-run[0][0]<.8)continue;
  const ref=run[0][1],vals=run.map(x=>spec.directional_calibration?ref+delta(x[1],ref):x[1]);
  if(Math.max(...vals)-Math.min(...vals)<=6)return {value:median(vals),start:run[0][0],end:run.at(-1)[0]};
 }
 return null;
}
function analyzeReplay(spec,side,samples,goal=null){
 // A recording can contain a stationary starting/return posture later in the clip.
 // Reuse that observed reference, then evaluate the original timeline once more.
 // This is not available in live guidance and never fills a missing measurement.
 const engine=new Engine(spec,side,goal);let run=[],candidates=[],last=null;
 if(!spec.id.startsWith('fitness_')&&!spec.id.startsWith('posture_'))for(const [t,raw]of samples){
  if(!finite(raw)||last!==null&&t-last>.5)run=[];
  if(finite(raw)){run.push([t,raw]);run=run.filter(x=>t-x[0]<=1.2);const ref=stableReference(run,spec);if(ref)candidates.push(ref);}
  last=t;
 }
 let reference=null;
 if(candidates.length){reference=spec.directional_calibration?candidates[0]:candidates.reduce((a,b)=>spec.target_direction==='decrease'?(b.value>a.value?b:a):(b.value<a.value?b:a));engine.baseline=reference.value;}
 for(const [t,raw]of samples)engine.consume(t,raw);
 const report=engine.report();report.calibration=reference?{method:'observed-stationary-replay',...reference}:{method:'online-start'};return report;
}
class Engine {
 constructor(spec,side,goal=null){this.spec=spec;this.side=side;this.goal=goal;this.baseline=null;this.sign=null;this.samples=[];this.values=[];this.reps=[];this.series=[];this.frames=0;this.validFrames=0;this.validSeconds=0;this.last=null;this.first=null;this.previousValid=false;this.phase='prepare';this.restSince=null;this.turnSince=null;this.cycleStart=null;this.peak=null;this.current=null;this.partial=0;this.posture={};this.postureRun={};this.lastRaw=null;}
 resetCycle(){if(this.cycleStart!==null)this.partial++;this.phase='prepare';this.restSince=this.turnSince=this.cycleStart=this.peak=null;}
 consume(t,raw){
  if(!finite(t)||t<0||(this.last!==null&&t<=this.last))throw Error('录像时间无效，请换一段录像');
  const gap=this.last===null?0:t-this.last;this.last=t;this.first??=t;this.frames++;
  if(this.spec.id.startsWith('posture_')){
   for(const [key,value]of Object.entries(raw||{})){this.posture[key]??=[];this.postureRun[key]??=[];if(!finite(value)){this.postureRun[key]=[];continue;}if(gap>.5)this.postureRun[key]=[];this.postureRun[key].push([t,value]);if(this.postureRun[key].length>=(this.posture[key]?.length||0))this.posture[key]=[...this.postureRun[key]];}
   return {value:null,reps:0,hint:'自然站立，保持平时的站姿',phase:'posture'};
  }
  if(!finite(raw)||gap>.5){this.previousValid=false;this.samples=[];this.current=null;this.resetCycle();if(!finite(raw))return{value:null,reps:this.reps.length,hint:'继续按动作步骤练习',phase:'missing'};}
  this.validFrames++;if(this.previousValid&&gap<=.5)this.validSeconds+=gap;this.previousValid=true;this.lastRaw=raw;
  const fitness=this.spec.id.startsWith('fitness_');
  if(!fitness&&this.baseline===null){
   this.samples.push([t,raw]);this.samples=this.samples.filter(x=>t-x[0]<=1.2);const ref=stableReference(this.samples,this.spec);
   if(ref){this.baseline=ref.value;this.values.push(this.spec.directional_calibration?0:this.baseline);}
   return{value:raw,reps:this.reps.length,hint:this.spec.ready_hint||'保持起始姿势约 1 秒',phase:'prepare'};
  }
  let value=raw;
  if(this.spec.directional_calibration){const d=delta(raw,this.baseline);if(this.sign===null&&Math.abs(d)>=5)this.sign=d>0?1:-1;value=this.sign===null?0:this.sign*d;}
  this.current=value;this.values.push(value);if(this.values.length>10000)this.values.shift();
  if(!this.series.length||t-this.series[this.series.length-1][0]>=.15)this.series.push([t,value]);
  let excursion,rest,turned;
  if(fitness){const increasing=this.spec.turn_angle>this.spec.start_angle;excursion=increasing?value-this.spec.start_angle:this.spec.start_angle-value;rest=increasing?value<=this.spec.start_angle:value>=this.spec.start_angle;turned=increasing?value>=this.spec.turn_angle:value<=this.spec.turn_angle;}
  else {const increasing=this.spec.target_direction!=='decrease';excursion=this.spec.directional_calibration?value:(increasing?value-this.baseline:this.baseline-value);rest=excursion<=5;turned=excursion>=15;}
  const outbound=this.spec.outbound_hint||this.spec.phases?.[0]||'缓慢完成动作';const returning=this.spec.return_hint||this.spec.phases?.[1]||'缓慢回到起点';
  if(this.phase==='prepare'){
   if(rest){this.restSince??=t;if(t-this.restSince>=.2){this.phase='outbound';this.restSince=null;}}else this.restSince=null;
  } else if(this.phase==='outbound'){
   if(excursion>5&&this.cycleStart===null)this.cycleStart=t;
   if(this.cycleStart!==null)this.peak=this.peak===null?value:(this.spec.target_direction==='decrease'||fitness&&this.spec.turn_angle<this.spec.start_angle?Math.min(this.peak,value):Math.max(this.peak,value));
   if(turned){this.turnSince??=t;if(t-this.turnSince>=.18){this.phase='return';this.turnAt=t;}}else this.turnSince=null;
  } else if(this.phase==='return'){
   this.peak=this.spec.target_direction==='decrease'||fitness&&this.spec.turn_angle<this.spec.start_angle?Math.min(this.peak,value):Math.max(this.peak,value);
   if(rest){this.restSince??=t;if(t-this.restSince>=.2){
    const peak=this.peak,direction=this.spec.target_direction|| (this.spec.turn_angle<this.spec.start_angle?'decrease':'increase');
    const met=this.goal===null?null:(direction==='decrease'?peak<=this.goal:peak>=this.goal);
    this.reps.push({peak,duration:t-this.cycleStart,outbound:this.turnAt-this.cycleStart,return:t-this.turnAt,targetMet:met,time:t});
    this.phase='outbound';this.cycleStart=this.peak=this.restSince=this.turnSince=null;
   }}else this.restSince=null;
  }
  return{value,reps:this.reps.length,hint:this.phase==='return'?returning:this.phase==='prepare'?(this.spec.ready_hint||'回到起始姿势'):outbound,phase:this.phase};
 }
 report(){
  const total=this.last!==null?this.last-this.first:0;
  if(this.spec.id.startsWith('posture_'))return{contract:VERSION,metrics:Object.fromEntries(Object.entries(this.posture).map(([key,run])=>[key,run.length>=10&&run[run.length-1][0]-run[0][0]>=2?median(run.map(x=>x[1])):null])),frames:this.frames,duration:total};
 return{contract:VERSION,frames:this.frames,validFrames:this.validFrames,validRatio:total>0?Math.min(1,this.validSeconds/total):0,duration:total,reps:[...this.reps],partial:this.partial+(this.cycleStart!==null?1:0),min:this.values.length?Math.min(...this.values):null,max:this.values.length?Math.max(...this.values):null,baseline:this.baseline,series:this.series,meanDuration:this.reps.length?this.reps.reduce((s,r)=>s+r.duration,0)/this.reps.length:null};
 }
}
function propose(records,catalog,now=Date.now(),profile={}){
 if(profile.restrictions)return {items:[],excluded:['档案有活动限制，请先由专业人员安排。']};
 const latest=new Map(),excluded=[],items=[];
 for(const r of records.filter(x=>x.kind==='assessment'&&x.report.contract===VERSION).sort((a,b)=>a.created-b.created))latest.set(r.exercise+':'+r.side,r);
 for(const r of latest.values()){
  const spec=catalog.rehab.find(x=>x.id===r.exercise),recipe=catalog.recipes[r.exercise];if(!spec||!recipe)continue;
  const history=records.filter(x=>x.kind==='training'&&x.exercise===r.exercise&&x.side===r.side).sort((a,b)=>b.created-a.created);
  if(history[0]&&(history[0].feedback?.pain>0||history[0].feedback?.fatigue>=5)){excluded.push(spec.label+'：上次有不适，暂不续练');continue;}
  const report=r.report;if(r.created>now||now-r.created>7*86400000||report.validRatio<.8||!report.reps.length){excluded.push(spec.label+'：最近评估不足，请补测');continue;}
  let target=spec.target_direction==='decrease'?report.max-.8*(report.max-report.min):report.min+.8*(report.max-report.min);
  if(recipe[3]!==null)target=Math.min(target,recipe[3]);if(r.exercise==='sit_to_stand'||!finite(target)||target<report.min||target>report.max||report.max-report.min<15)target=null;
  // Leave one observed repetition in reserve when capacity is >= 3.
  // A short assessment is a starting dose, not a maximal-effort prescription.
  const reps=Math.min(5,Math.max(1,report.reps.length-(report.reps.length>=3?1:0)));
  items.push({exercise:r.exercise,side:r.side,assessment:r.id,reps,sets:1,target,standing:recipe[2],source:catalog.sources[recipe[0]],evidenceKind:recipe[4]||'personal-adaptation',complete:false});
 }
 return{items:items.slice(0,4),excluded};
}
const api={VERSION,finite,angle,signed,delta,median,points,measure,Engine,analyzeReplay,propose};
if(typeof module!=='undefined')module.exports=api;else root.LocalEngine=api;
})(typeof self!=='undefined'?self:globalThis);
