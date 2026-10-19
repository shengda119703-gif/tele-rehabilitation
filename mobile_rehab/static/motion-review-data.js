/* Read-only presentation data. Does not change measurement or completion rules. */
(function(root){
'use strict';
const VERSION='motion-review-trace-1',finite=v=>typeof v==='number'&&Number.isFinite(v);
const names=['left_eye','right_eye','left_ear','right_ear',...['shoulder','elbow','wrist','hip','knee','ankle','heel','foot_index'].flatMap(n=>['left_'+n,'right_'+n]),...Array.from({length:21},(_,i)=>'hand_'+i)];
function handPoints(raw,w,h,side){const out={};if(!raw?.hand||raw.handedness?.categoryName?.toLowerCase()!==side||!(raw.handedness?.score>=.5))return out;raw.hand.slice(0,21).forEach((p,i)=>{if(p&&finite(p.x)&&finite(p.y)&&p.x>=0&&p.x<1&&p.y>=0&&p.y<1)out['hand_'+i]=[p.x*w,p.y*h];});return out;}
const med=a=>{const v=a.filter(finite).sort((a,b)=>a-b),i=v.length>>1;return v.length?(v.length%2?v[i]:(v[i-1]+v[i])/2):null;};
const range=a=>{const v=a.filter(finite);return v.length?Math.max(...v)-Math.min(...v):null;};
function angle(a,b,c){if(!a||!b||!c)return null;const u=[a[0]-b[0],a[1]-b[1]],v=[c[0]-b[0],c[1]-b[1]],d=Math.hypot(...u)*Math.hypot(...v);return d>1e-8?Math.acos(Math.max(-1,Math.min(1,(u[0]*v[0]+u[1]*v[1])/d)))*180/Math.PI:null;}
const midpoint=(a,b)=>a&&b?[(a[0]+b[0])/2,(a[1]+b[1])/2]:null;
const line=(a,b)=>a&&b?Math.atan2(Math.abs(a[1]-b[1]),Math.abs(a[0]-b[0]))*180/Math.PI:null;
const tilt=(a,b)=>a&&b?Math.atan2(a[0]-b[0],Math.abs(a[1]-b[1]))*180/Math.PI:null;
const round=v=>Math.round(v*100000)/100000;
class TraceCollector{
 constructor(){this.rows=[];this.size=null;}
 add(t,points,width,height){
  if(!finite(t)||t<0||width<=0||height<=0||this.rows.length>=750||this.rows.length&&t-this.rows.at(-1).t<.159)return;
  const p={};for(const key of names){const a=points?.[key];if(a?.length===2&&a.every(finite)&&a[0]>=0&&a[0]<=width&&a[1]>=0&&a[1]<=height)p[key]=[round(a[0]/width),round(a[1]/height)];}
  this.size=[width,height];this.rows.push({t:round(t),points:p});
 }
 export(){return {version:VERSION,size:this.size||[0,0],rows:this.rows};}
}
function validateTrace(trace){
 if(!trace||trace.version!==VERSION||!Array.isArray(trace.rows)||trace.rows.length>750||!Array.isArray(trace.size)||trace.size.length!==2||!trace.size.every(v=>finite(v)&&v>0&&v<=8192))return null;
 let previous=-1;
 for(const s of trace.rows){if(!finite(s.t)||s.t<0||s.t>121||s.t<=previous||!s.points||Array.isArray(s.points))return null;previous=s.t;
  for(const [k,p]of Object.entries(s.points))if(!names.includes(k)||!Array.isArray(p)||p.length!==2||p.some(v=>!finite(v)||v<0||v>1))return null;
 }return trace;
}
function nearest(rows,t,gap=.32){let lo=0,hi=rows.length;while(lo<hi){const m=(lo+hi)>>1;if(rows[m].t<=t+.00001)lo=m+1;else hi=m;}const s=rows[lo-1];return s&&t-s.t<=gap?s:null;}
function recent(rows,i,key,seconds=.32){if(!finite(rows[i]?.[key]))return null;const v=[];for(let j=i;j>=0&&rows[i].t-rows[j].t<=seconds;j--){if(j<i&&rows[j+1].t-rows[j].t>.32||!finite(rows[j][key]))break;v.push(rows[j][key]);}return med(v);}
function geometry(trace,side,front){
 if(!validateTrace(trace))return [];
 const [w,h]=trace.size;let reference=null;
 return trace.rows.map(s=>{
  const p=Object.fromEntries(Object.entries(s.points).map(([k,a])=>[k,[a[0]*w,a[1]*h]]));
  const sh=midpoint(p.left_shoulder,p.right_shoulder),hp=midpoint(p.left_hip,p.right_hip),body=sh&&hp?Math.hypot(sh[0]-hp[0],sh[1]-hp[1]):null;
  if(!reference&&finite(body)&&body>=h*.08&&hp)reference={body,hip:hp};
  const at=n=>p[side+'_'+n],row={t:s.t,shoulder:line(p.left_shoulder,p.right_shoulder),pelvis:line(p.left_hip,p.right_hip),torso:front?tilt(sh,hp):tilt(at('shoulder'),at('hip')),hip:angle(at('shoulder'),at('hip'),at('knee')),knee:angle(at('hip'),at('knee'),at('ankle')),left_knee:angle(p.left_hip,p.left_knee,p.left_ankle),right_knee:angle(p.right_hip,p.right_knee,p.right_ankle)};
  row.symmetry=finite(row.left_knee)&&finite(row.right_knee)?Math.abs(row.left_knee-row.right_knee):null;
  row.pelvis_x=reference&&hp?(hp[0]-reference.hip[0])/reference.body*100:null;
  row.pelvis_y=reference&&hp?(reference.hip[1]-hp[1])/reference.body*100:null;
  row.head=at('ear')&&at('shoulder')&&finite(body)&&body>0?100*Math.abs(at('ear')[0]-at('shoulder')[0])/body:null;
  row.depth=at('hip')&&at('knee')&&reference?(at('knee')[1]-at('hip')[1])/reference.body*100:null;
  row.inward=null;row.outward=null;
  if(front){const deviations=[];for(const sd of ['left','right']){const hip=p[sd+'_hip'],knee=p[sd+'_knee'],ankle=p[sd+'_ankle'],other=p[(sd==='left'?'right':'left')+'_ankle'],heel=p[sd+'_heel'],toe=p[sd+'_foot_index'];if(!hip||!knee||!ankle||!other||!heel||!toe||!reference||ankle[1]-hip[1]<h*.04)continue;const sign=ankle[0]>other[0]?1:-1,ratio=Math.max(0,Math.min(1,(knee[1]-hip[1])/(ankle[1]-hip[1]))),x=hip[0]+ratio*(ankle[0]-hip[0]),edge=Math.max(...[ankle,heel,toe].map(a=>sign*a[0]));deviations.push({inward:100*Math.max(0,sign*(x-knee[0]))/reference.body,outward:100*Math.max(0,sign*knee[0]-edge)/reference.body});}for(const k of ['inward','outward'])row[k]=deviations.length?Math.max(...deviations.map(v=>v[k])):null;}
  return row;
 });
}
function seriesOf(result){
 const rows=Array.isArray(result.series)?result.series:result.local_report?.series||[];
 return rows.map(s=>Array.isArray(s)?{t:s[0],angle:s[1]}:{t:s.t,angle:s.angle??null,metrics:s.metrics||{}}).filter(s=>finite(s.t)&&s.t>=0).sort((a,b)=>a.t-b.t);
}
function build(job,spec={},trace=null){
 const r=job.result||{},summary=r.summary||{},side=job.side==='right'?'right':'left',front=spec.view==='frontal',fitness=job.mode==='fitness',posture=job.mode==='posture';
 const observed=seriesOf(r),tr=validateTrace(trace),geo=geometry(tr,side,front),bar=r.barbell?.series||[];
 const times=[...new Set([...observed.map(s=>s.t),...(tr?.rows||[]).map(s=>s.t),...bar.filter(s=>finite(s.t)).map(s=>s.t)])].sort((a,b)=>a-b).slice(0,6000);
 const defs=[],add=(key,label,unit='°',decimals=1,primary=true,group='动作表现')=>defs.push({key,label,unit,decimals,primary,group});
 const metricName=({neck:'头部活动角度',shoulder:'肩部活动角度',elbow:'肘部活动角度',wrist:'腕部活动角度',hip:'髋部活动角度',knee:'膝部活动角度',ankle:'踝部活动角度',trunk:'躯干活动角度',finger:'手指活动角度'})[spec.joint]||'动作角度';
 if(!posture)add('angle',metricName);
 if(finite(summary.motion_range?.range_deg))add('range','活动角度范围','°',1,true,'全段');
 if(fitness&&job.exercise==='fitness_deadlift')add('hip','髋部夹角');
 if(fitness&&job.exercise==='fitness_squat')add('knee','屈膝角度');
 const lower=posture||['hip','knee','ankle'].includes(spec.joint)||['fitness_squat','fitness_deadlift','fitness_split_squat'].includes(job.exercise);
 if(front){if(lower)add('symmetry','左右屈膝角度差','°',1,fitness);add('shoulder','双肩高低差','°',1,!fitness);add('pelvis','骨盆高低差','°',1,posture);if(fitness&&lower){add('inward','膝部向内偏移','%',1);add('outward','膝部向外偏移','%',1);}}
 add('torso',front?'上身侧倾':'上身前倾','°',1,true);
 if(!front&&posture)add('head','耳肩前移比例','%',1);
 add('sway',front?'骨盆左右幅度':'骨盆前后位移','%',1,false,'轨迹与控制');add('rise','骨盆上下幅度','%',1,posture,'轨迹与控制');
 const target=r.barbell?.measurement?.target_kind==='wrist'?'手腕':r.barbell?.measurement?.target_kind==='plate'?'器械':'器械';
 const has=key=>bar.some(s=>finite(s[key]));
 if(has('power_w'))add('power',target+'功率','W',0,true,'输出表现');
 if(has('velocity_m_s'))add('speed',target+'速度','m/s',2,true,'输出表现');
 if(has('relative_velocity'))add('relative_speed','手腕相对速度',r.barbell.measurement?.speed_unit||'躯干长度/s',2,false,'输出表现');
 if(has('x_m'))add('path',target+'水平偏移','cm',1,false,'轨迹与控制');
 if(has('acceleration_m_s2'))add('acceleration',target+'加速度','m/s²',2,false,'输出表现');
 if(has('specific_lifting_power_w_kg'))add('specific_power','单位负重抬升功率','W/kg',2,false,'输出表现');
 const samples=times.map(t=>{
  const source=nearest(observed,t),g0=nearest(geo,t),gi=g0?geo.indexOf(g0):-1,b=nearest(bar,t),pose=tr?nearest(tr.rows,t):null;
  const values={angle:source?.angle??null,range:summary.motion_range?.range_deg??null},feedback={};
  for(const key of ['hip','knee','shoulder','pelvis','torso','head','symmetry','inward','outward'])values[key]=gi>=0?recent(geo,gi,key):null;
  if(finite(values.knee))values.knee=180-values.knee;
  if(finite(values.torso))values.torso=Math.abs(values.torso);
  if(g0){const window=geo.filter(g=>g.t<=t&&t-g.t<=1.2),continuous=window.length>=4&&window.every((g,i)=>i===0||g.t-window[i-1].t<=.32);for(const [key,sourceKey]of [['sway','pelvis_x'],['rise','pelvis_y']])values[key]=continuous&&window.every(g=>finite(g[sourceKey]))?range(window.map(g=>g[sourceKey])):null;}
  for(const [key,sourceKey]of [['power','power_w'],['speed','velocity_m_s'],['path','x_m'],['acceleration','acceleration_m_s2'],['specific_power','specific_lifting_power_w_kg'],['relative_speed','relative_velocity']])values[key]=finite(b?.[sourceKey])?b[sourceKey]*(key==='path'?100:1):null;
  let smooth=true;if(source){const window=observed.filter(s=>s.t<=t&&t-s.t<=.48).map(s=>s.angle).filter(finite);smooth=window.length<3||!window.slice(1,-1).some((v,i)=>Math.abs(window[i]-2*v+window[i+2])>15);}
  const cue=(key,text,kind='good')=>feedback[key]={text,kind};
  cue('angle',smooth?'动作角度变化较平顺':'局部角度变化偏大',smooth?'good':'attention');cue('range','本段实际活动范围','neutral');
  cue('hip','髋部实际夹角','neutral');cue('knee','膝部实际屈曲角度','neutral');
  const lat=gi>=0?recent(geo,gi,'torso'):null;
  cue('torso',front?(finite(lat)&&Math.abs(lat)>=5?(lat>0?'上身向画面右侧偏多':'上身向画面左侧偏多'):'躯干左右控制较稳'):'躯干前倾角度',front&&finite(lat)&&Math.abs(lat)>=5?'attention':front?'good':'neutral');
  cue('symmetry',finite(values.symmetry)&&values.symmetry>=8?(g0?.left_knee<g0?.right_knee?'左腿屈膝偏多':'右腿屈膝偏多'):'左右屈膝较对称',finite(values.symmetry)&&values.symmetry>=8?'attention':'good');
  for(const [key,noun]of [['shoulder','双肩'],['pelvis','骨盆']])cue(key,finite(values[key])&&values[key]>5?noun+'左右高低差增大':noun+'高度较平稳',finite(values[key])&&values[key]>5?'attention':'good');
  for(const key of ['inward','outward'])cue(key,'膝部'+(key==='inward'?'内移':'外移')+'投影变化','neutral');
  cue('head','耳部相对肩部的位置','neutral');cue('sway',front?'骨盆左右移动幅度':'骨盆前后移动幅度','neutral');cue('rise','骨盆上下移动幅度','neutral');
  cue('power','按本次器械参数计算','neutral');cue('speed','竖直轨迹速度','neutral');cue('path','相对片头的画面水平偏移','neutral');cue('acceleration','竖直轨迹加速度','neutral');cue('specific_power','每公斤负重的抬升输出','neutral');cue('relative_speed','按可见身体尺度归一','neutral');
  for(const d of defs)if(!finite(values[d.key]))feedback[d.key]={text:'当前片段未取到数值',kind:'neutral'};
  return {t,values,feedback,points:pose?.points||{},bar_point:b?.point||null};
 });
 const metrics=[];
 for(const d of defs){const values=samples.filter(s=>finite(s.values[d.key]));let value=null,at=null;
  if(d.key==='range')value=summary.motion_range?.range_deg??null;
  else if(values.length){const amplitude=['path','torso'].includes(d.key),peak=values.reduce((a,b)=>(amplitude?Math.abs(b.values[d.key]):b.values[d.key])>(amplitude?Math.abs(a.values[d.key]):a.values[d.key])?b:a);value=peak.values[d.key];at=peak.t;}
  let savedPeak=false;if(d.key==='angle'&&finite(summary.motion_range?.max_deg)){savedPeak=!finite(value)||Math.abs(value-summary.motion_range.max_deg)>.01;value=summary.motion_range.max_deg;if(savedPeak)at=null;}
  if(!finite(value))continue;
  const cue=at!==null?nearest(samples,at)?.feedback[d.key]:{text:savedPeak?'本段最大活动角度':'本段实际活动范围',kind:'neutral'};
  metrics.push({...d,value,time:at,cue:cue.text,kind:cue.kind,statistic:d.key==='range'?'全段':'最大值'});
 }
 // Legacy results without a saved timeline still expose the actual summary.
 if(!metrics.some(m=>m.key==='angle')&&finite(summary.motion_range?.max_deg))metrics.unshift({key:'angle',label:summary.primary_metric_label||spec.metric_label||'最大活动角度',unit:'°',decimals:1,primary:true,group:'全段',value:summary.motion_range.max_deg,time:null,cue:'已保存的角度结果',kind:'neutral',statistic:'最大值'});
 if(posture)for(const m of Array.isArray(summary.metrics)?summary.metrics:[]){if(!m.valid||!finite(m.value))continue;const map={shoulder_level:'shoulder',hip_level:'pelvis',trunk_lean:'torso',head_offset:'head',knee_angle:'knee'},key=map[m.key];if(key&&!metrics.some(d=>d.key===key))metrics.push({key,label:m.label,unit:m.unit,decimals:1,primary:true,group:'全段',value:m.value,time:null,cue:'已保存的姿态结果',kind:'neutral',statistic:'全段'});}
 const reps=r.local_report?.reps||r.repetitions||[],durations=key=>reps.map(p=>p[key]).filter(v=>finite(v)&&v>0);
 const up=med(durations(r.local_report?'outbound':'outbound_s')),down=med(durations(r.local_report?'return':'return_s'));
 for(const [key,label,value,unit]of [['up_time','动作去程用时',up,'s'],['down_time','动作回程用时',down,'s'],['tempo','回程 / 去程用时',finite(up)&&finite(down)?down/up:null,'倍']])if(finite(value))metrics.push({key,label,value,unit,decimals:2,primary:false,group:'动作节奏',time:null,statistic:'全段',cue:key==='tempo'?(value>.8&&value<1.2?'往返节奏较均匀':value>=1.2?'回程慢于去程':'回程快于去程'):'实际往返时段',kind:'neutral'});
 const highlights=metrics.filter(m=>m.kind==='attention'&&finite(m.time)).map(m=>({t:m.time,text:m.cue,key:m.key}));
 if(!highlights.length){const m=metrics.find(m=>m.primary&&finite(m.time));if(m)highlights.push({t:m.time,text:m.cue,key:m.key});}
 return {version:1,title:spec.label||r.spec?.label||job.exercise,mode:job.mode,side,view:front?'正面':'侧面',duration:summary.observed_span_s||r.local_report?.duration||times.at(-1)||0,metrics,samples,highlights,
  parameters:r.barbell?.calibration||null,hasTrace:!!tr,methods:['角度来自本次已保存分析；当前值与全段统计分别展示。','骨盆位移百分比以本片可见躯干长度归一；左右对称表示动作角度，不表示两腿受力比例。','速度、功率沿用本次器械轨迹与参数；没有重量时不生成总功率。','短缺测保留空值；相机预览不写入评估结果或计划完成情况。']};
}
const api={VERSION,finite,med,range,angle,TraceCollector,validateTrace,nearest,geometry,build,handPoints};
if(typeof module!=='undefined')module.exports=api;root.RehabMotionData=api;
})(typeof globalThis!=='undefined'?globalThis:this);
