(function(root){
'use strict';
const E=LocalEngine,F=PhoneStore.files,fetchAsset=(...a)=>fetch(...a);
let catalogPromise,active=null;const errors=new Map();
function catalog(){return catalogPromise??=fetchAsset('/catalog.json').then(r=>{if(!r.ok)throw Error('动作目录不完整');return r.json();});}
async function spec(id){const c=await catalog(),s=[...c.rehab,...c.fitness,...c.posture].find(s=>s.id===id);if(!s)throw Error('动作不存在');return s;}
class Model{
 constructor(){this.urls=[];this.pending=new Map();this.sequence=0;this.stopped=false;}
 async init(s,calibration=null){
  const mode=s.joint==='finger'?'hand':s.joint==='wrist'?'wrist':'pose';
  const load=async(path,binary=false)=>{const r=await fetchAsset(path);if(!r.ok)throw Error('安装包模型资源不完整');return binary?r.arrayBuffer():r.text();};
  const [vision,barbell,workerCode,sj,nj,sw,nw,pose,hand,manifest]=await Promise.all([
   load('/vendor/vision_bundle.js'),load('/local/barbell.js'),load('/local/worker.js'),load('/vendor/wasm/vision_wasm_internal.js'),load('/vendor/wasm/vision_wasm_nosimd_internal.js'),load('/vendor/wasm/vision_wasm_internal.wasm',true),load('/vendor/wasm/vision_wasm_nosimd_internal.wasm',true),mode==='hand'?null:load('/models/pose_landmarker_full.task',true),mode==='pose'?null:load('/models/hand_landmarker.task',true),load('/models/manifest.json')]);
  if(this.stopped)throw Error('已停止');
  const url=(data,type)=>{const u=URL.createObjectURL(new Blob([data],{type}));this.urls.push(u);return u;};
  this.worker=new Worker(url('self.exports={};\n'+vision+'\n'+barbell+'\n'+workerCode,'text/javascript'));
  this.worker.onmessage=({data})=>{const p=this.pending.get(data.id);if(!p)return;clearTimeout(p.timer);this.pending.delete(data.id);data.ok?p.resolve(data):p.reject(Error(data.error));};
  this.worker.onerror=event=>{this.close('本地模型启动失败：'+event.message);};
  const files=(js,wasm)=>({wasmLoaderPath:url(js,'text/javascript'),wasmBinaryPath:url(wasm,'application/wasm')});
  return this.call('init',{mode,calibration,simd:files(sj,sw),noSimd:files(nj,nw),poseModel:pose,handModel:hand,modelInfo:JSON.parse(manifest)},[pose,hand].filter(Boolean));
 }
 call(type,params={},transfer=[]){if(this.stopped||!this.worker)return Promise.reject(Error('模型已停止'));return new Promise((resolve,reject)=>{const id=++this.sequence,timer=setTimeout(()=>{this.pending.delete(id);reject(Error('本地分析超时，请重试'));},type==='init'?90000:30000);this.pending.set(id,{resolve,reject,timer});this.worker.postMessage({id,type,...params},transfer);});}
 close(message='已停止'){this.stopped=true;this.worker?.terminate();for(const p of this.pending.values()){clearTimeout(p.timer);p.reject(Error(message));}this.pending.clear();for(const u of this.urls)URL.revokeObjectURL(u);this.urls=[];}
}
function event(video,name,action){return new Promise((resolve,reject)=>{const clean=()=>{clearTimeout(timer);video.removeEventListener(name,ok);video.removeEventListener('error',bad);};const ok=()=>{clean();resolve();},bad=()=>{clean();reject(Error('这段录像不能解码，请使用普通 MP4'));},timer=setTimeout(()=>{clean();reject(Error('读取录像超时'));},20000);video.addEventListener(name,ok,{once:true});video.addEventListener('error',bad,{once:true});action();});}
async function bitmap(video,maxWidth,token){const deadline=performance.now()+10000;while(video.seeking||video.readyState<2||!video.videoWidth){if(token.cancelled)throw Error('已停止');if(video.error||performance.now()>deadline)throw Error('录像解码失败，请换一段 MP4');await new Promise(r=>setTimeout(r,20));}const scale=Math.min(1,maxWidth/video.videoWidth),w=Math.round(video.videoWidth*scale),h=Math.round(video.videoHeight*scale),canvas=new OffscreenCanvas(w,h);canvas.getContext('2d').drawImage(video,0,0,w,h);return{image:canvas.transferToImageBitmap(),w,h};}
function summary(s,r,goal=null){const range=E.finite(r.min)&&E.finite(r.max)?{min_deg:r.min,max_deg:r.max,range_deg:r.max-r.min}:null,met=r.reps?.filter(x=>x.targetMet!==false).length||0;return{completed:r.reps?.length||0,valid_ratio:r.validRatio??null,observed_span_s:r.duration,primary_metric_label:s.metric_label||s.label,motion_range:range,plan_completed:goal?met>=goal.settings.target_reps*(goal.settings.target_sets||1):false,mean_cycle_s:r.meanDuration,partial:r.partial||0};}
function barReport(b,calibration,synthetic=false){
 const series=(b.rows||[]).map(p=>({t:p.t,velocity_m_s:p.v,acceleration_m_s2:p.a,force_n:p.force,power_w:p.power,x_m:p.x??null,height_m:p.height??null,point:p.point??null})),lifts=[];let run=[],previous=null,known=false;
 const finish=bounded=>{if(run.length>=4){const start=run[0],end=run.at(-1),height=end.height_m-start.height_m,duration=end.t-start.t;if(height>=.04&&duration>=.2){const peak=run.reduce((a,b)=>b.velocity_m_s>a.velocity_m_s?b:a),powers=run.map(r=>r.power_w).filter(E.finite),forces=run.map(r=>r.force_n).filter(E.finite);lifts.push({number:lifts.length+1,bounded:known&&bounded,displacement_m:height,mean_velocity_m_s:height/duration,peak_velocity_m_s:peak.velocity_m_s,peak_time_s:peak.t,time_to_peak_s:peak.t-start.t,peak_power_w:powers.length===run.length?Math.max(...powers):null,peak_force_n:forces.length===run.length?Math.max(...forces):null});}}run=[];};
 for(const row of series){const continuous=previous&&row.t-previous.t<=.3;if(E.finite(row.velocity_m_s)&&row.velocity_m_s>.05){if(!continuous)finish(false);if(!run.length)known=!!(continuous&&E.finite(previous.velocity_m_s)&&previous.velocity_m_s<=.05);run.push(row);}else finish(!!(continuous&&E.finite(row.velocity_m_s)));previous=row;}finish(false);
 const complete=lifts.filter(r=>r.bounded),speeds=complete.map(r=>r.mean_velocity_m_s);
 return{version:b.contract||'android-free-weight-2d-1',synthetic,calibration,summary:{peak_velocity_m_s:complete.length?Math.max(...complete.map(r=>r.peak_velocity_m_s)):b.peakSpeed??null,peak_force_n:b.peakForce??null,peak_power_w:b.peakPower??null,bounded_segments:complete.length,tracked_ratio:b.coverage||0,last_vs_best_velocity_loss_pct:speeds.length>=2?100*(1-speeds.at(-1)/Math.max(...speeds)):null},lifts,series,stop_reason:b.valid?'':b.note,assumptions:[b.note||'二维器械运动估算，不代表肌肉力量。','手机降低采样率时峰值会被平滑；本次为器械表现参考，不是临床力量测试。']};
}
const fitnessNames={knee:'膝关节二维夹角',hip:'髋部二维夹角',elbow:'肘关节二维夹角',torso:'躯干相对竖直倾角',upper_arm:'上臂相对竖直倾角',body_line:'肩—髋—踝二维夹角'};
const observable={fitness_squat:['knee','hip','torso'],fitness_deadlift:['hip','knee','torso'],fitness_bench_press:['elbow','upper_arm'],fitness_row:['elbow','torso'],fitness_overhead_press:['elbow','upper_arm','torso'],fitness_curl:['elbow','upper_arm'],fitness_pushup:['elbow','body_line'],fitness_split_squat:['knee','hip','torso']};
function fitnessResult(s,side,frames,size){
 let used=s,fallback=false;const finiteCount=key=>frames.filter(f=>E.finite(f.metrics[key])).length;
 // Cropped ankle: count by actually observed hip motion, never infer a knee.
 if(s.id==='fitness_squat'&&finiteCount('knee')<frames.length*.5&&finiteCount('hip')>=frames.length*.8){used={...s,metric:'hip',metric_label:'髋部二维夹角（膝部缺测时的深蹲往返观察）',start_angle:145,turn_angle:105};fallback=true;}
 const report=E.analyzeReplay(used,side,frames.map(f=>[f.t,f.metrics[used.metric]??null])),out=result(used,report,size);
 out.conditions.metric_fallback=fallback?'observed-hip-no-knee':null;out.summary.metrics={};
 for(const key of observable[s.id]){const values=frames.map(f=>f.metrics[key]).filter(E.finite);out.summary.metrics[key]={label:fitnessNames[key],coverage:values.length/frames.length,min:values.length?Math.min(...values):null,max:values.length?Math.max(...values):null,samples:values.length,unit:'deg'};}
 const keyframe=t=>{const f=frames.reduce((a,b)=>Math.abs(b.t-t)<Math.abs(a.t-t)?b:a);return{t:f.t,angle:f.metrics[used.metric]??null,points:f.points};};
 out.series=frames.map(f=>({t:f.t,metrics:f.metrics,angle:f.metrics[used.metric]??null}));
 out.repetitions=out.repetitions.map((rep,i)=>({...rep,start:keyframe(report.reps[i].time-report.reps[i].duration),turn:keyframe(report.reps[i].time-report.reps[i].return),end:keyframe(report.reps[i].time)}));
 if(fallback)out.limitations.push('膝部未测得，本次仅用实际可见的髋部往返计次；不评价膝角或深度。');
 return out;
}
function result(s,r,size,goal=null,bar=null,calibration=null){
 const out={contract:E.VERSION,local_report:r,summary:summary(s,r,goal),conditions:{size,source:'phone-local'},limitations:['手机本地二维投影观察，不是临床关节活动度或疾病诊断。']};
 if(s.id.startsWith('posture_'))out.summary={metrics:Object.entries(r.metrics).map(([key,value])=>({key,label:({shoulder_level:'双肩连线倾角',hip_level:'双髋连线倾角',trunk_lean:'躯干偏离竖直',head_offset:'耳肩水平偏移',knee_angle:'膝部侧面夹角'})[key],unit:key==='head_offset'?'%':'°',value,valid:E.finite(value),note:'画面中的二维体态观察',reason:'连续可见画面不足'})),note:'不诊断骨盆前倾、脊柱侧弯或膝过伸。'};
 else if(s.id.startsWith('fitness_')){out.spec=s;out.summary.metrics={[s.metric]:{label:s.metric_label,coverage:r.validRatio,min:r.min,max:r.max,samples:r.validFrames,unit:'deg'}};out.series=r.series.map(([t,value])=>({t,metrics:{[s.metric]:value},angle:value}));out.repetitions=r.reps.map((p,i)=>({number:i+1,total_s:p.duration,outbound_s:p.outbound,return_s:p.return,range_deg:Math.abs(p.peak-s.start_angle),outbound_mean_angular_rate:p.outbound>0?Math.abs(p.peak-s.start_angle)/p.outbound:null,start:{t:p.time-p.duration,angle:s.start_angle,points:{}},turn:{t:p.time-p.return,angle:p.peak,points:{}},end:{t:p.time,angle:s.start_angle,points:{}},notes:[]}));}
 if(goal){const met=r.reps.filter(p=>p.targetMet!==false).length;out.quality={observed_goals_met:met,needs_adjustment:r.reps.length-met,unassessable:r.validRatio<.8?r.partial:0};}
 if(bar)out.barbell=barReport(bar,calibration);return out;
}
function update(store,id,values){store.change(v=>{const j=v.jobs.find(j=>j.id===id);if(!j)throw Error('任务已变化');Object.assign(j,values);});}
async function analyze(store,job,file,calibration=null){
 if(active)throw Error('已有本地分析正在进行');
 const token={cancelled:false},model=new Model();active={token,model,job:job.id};let video,url;
 try{
  const s=await spec(job.exercise),goal=job.entry_key?store.value.plans.find(p=>p.id===job.plan_id)?.items.find(i=>i.key===job.entry_key):null;
  video=document.createElement('video');video.muted=true;video.playsInline=true;video.preload='auto';url=URL.createObjectURL(file);
  await event(video,'loadeddata',()=>{video.src=url;video.load();});if(!E.finite(video.duration)||video.duration<=0||video.duration>120.1)throw Error('请选择 120 秒以内的录像');
  const bar=calibration?{points:[calibration.target,calibration.reference_a,calibration.reference_b],meters:calibration.length_m,kg:calibration.mass_kg}:null;
  const models=await model.init(s,bar);update(store,job.id,{message:'正在手机上分析动作'});
  const samples=[],fitnessFrames=[],engine=new E.Engine(s,job.side,goal?.settings.target_angle_deg??null),end=video.duration;let size=[0,0],width=calibration?480:640,step=.12,slow=0;
  for(let target=0;target<end-.04;target+=step){
   if(token.cancelled)throw Error('分析已停止，原录像保留');
   if(video.readyState<2||Math.abs(video.currentTime-target)>.001)await event(video,'seeked',()=>video.currentTime=target);
   const t=video.currentTime;if(engine.last!==null&&t<=engine.last)continue;
   const began=performance.now(),b=await bitmap(video,width,token),inferred=await model.call('frame',{image:b.image,timestamp:t*1000},[b.image]),raw=E.measure(s,job.side,inferred.result,b.w,b.h);
   size=[b.w,b.h];samples.push([t,raw]);engine.consume(t,raw);
   if(s.id.startsWith('fitness_')){const p=E.points(inferred.result,b.w,b.h);fitnessFrames.push({t,metrics:Object.fromEntries(observable[s.id].map(metric=>[metric,E.measure({id:s.id,metric},job.side,inferred.result,b.w,b.h)])),points:Object.fromEntries(['shoulder','elbow','wrist','hip','knee','ankle'].filter(n=>p[job.side+'_'+n]).map(n=>[n,p[job.side+'_'+n].map((v,i)=>v/(i?b.h:b.w))]))});}
   // Media time remains original even when CPU throughput/resolution is reduced.
   const elapsed=performance.now()-began;if(elapsed>220){slow++;if(slow>=5){if(!calibration)width=480;step=.18;}if(slow>=15){if(!calibration)width=384;step=.24;}}
   update(store,job.id,{progress:{analyzed_seconds:t,processed_frames:samples.length},performance:{width,sample_interval_s:step,inference_ms:elapsed}});
   await new Promise(r=>setTimeout(r,0));
  }
  const report=E.analyzeReplay(s,job.side,samples,goal?.settings.target_angle_deg??null),barbell=calibration?(await model.call('barbell-report')).report:null;
  const final=s.id.startsWith('fitness_')?fitnessResult(s,job.side,fitnessFrames,size):result(s,report,size,goal);
  if(barbell)final.barbell=barReport(barbell,calibration);
  update(store,job.id,{state:'done',message:'分析完成',result:final,model_info:models.models,measurement_version:E.VERSION,finished_at:new Date().toISOString()});
 }catch(e){try{update(store,job.id,{state:'failed',message:e.message,finished_at:new Date().toISOString()});}catch(storageError){errors.set(job.id,'手机存储不足，本次结果未保存。请导出已有记录后清理空间。');}}
 finally{model.close();video?.pause();if(video){video.removeAttribute('src');video.load();}if(url)URL.revokeObjectURL(url);active=null;}
}
let live=null;
async function startLive(s,side){if(active||live)throw Error('请先结束当前分析');const model=new Model(),id=crypto.randomUUID();live={id,model,s,side,engine:new E.Engine(s,side),start:null,previous:-1};try{await model.init(s);return{id};}catch(e){stopLive();throw e;}}
async function liveFrame(id,blob){if(!live||live.id!==id)throw Error('实时指导已结束');const run=live,begin=performance.now();run.start??=begin;const t=(begin-run.start)/1000;if(t<=run.previous)throw Error('重复画面');run.previous=t;const image=await createImageBitmap(blob),w=image.width,h=image.height;const {result:raw}=await run.model.call('frame',{image,timestamp:t*1000},[image]);const value=E.measure(run.s,run.side,raw,w,h),obs=run.engine.consume(t,value);return{valid:value!==null,inference_ms:performance.now()-begin,points:Object.values(E.points(raw,w,h)).map(p=>[p[0]/w,p[1]/h]),cue:{instruction:obs.hint,status:obs.phase},summary:{completed:obs.reps,primary_metric:run.s.metric,metrics:{[run.s.metric]:{value:obs.value}}}};}
function stopLive(){live?.model.close();live=null;}
function pause(){stopLive();if(active){active.token.cancelled=true;active.model.close();}}
root.PhoneMotion={catalog,spec,Model,analyze,summary,result,fitnessResult,barReport,startLive,liveFrame,stopLive,pause,errors,get active(){return active;}};
})(globalThis);
