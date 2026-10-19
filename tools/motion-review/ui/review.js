/* Private, dependency-free player. Numbers come only from data.json exports. */
"use strict";
const $ = id => document.getElementById(id);
const app = $("app"), video = $("video"), canvas = $("overlay"), ctx = canvas.getContext("2d");
let manifest, clip, clipIndex = 0, loadVersion = 0, summaryMode = false, expanded = false, annotations = true;
let selectedChart = null, lastSample = -1, dragging = null, baseHeight, raf = null;
const finite = v => typeof v === "number" && Number.isFinite(v);
const time = t => `${String(Math.floor(Math.max(0,t)/60)).padStart(2,"0")}:${String(Math.floor(Math.max(0,t)%60)).padStart(2,"0")}`;
const text = (node, value) => { if (node.textContent !== value) node.textContent = value; };
function fmt(v, d) { return finite(v) ? (Math.abs(v) < .5 * 10**(-d) ? 0 : v).toFixed(d) : "—"; }
function node(tag, cls, content) { const el = document.createElement(tag); if (cls) el.className=cls; if(content!==undefined)el.textContent=content; return el; }
function notice(message) { text($("toast"),message);$("toast").hidden=false;clearTimeout(notice.timer);notice.timer=setTimeout(()=>$("toast").hidden=true,2500); }
function getSample(t) {
  if (!clip) return null;
  let lo=0,hi=clip.samples.length;
  while(lo<hi){const m=(lo+hi)>>1;if(clip.samples[m].t<=t)lo=m+1;else hi=m;}
  const i=lo-1;
  return i>=0 && t-clip.samples[i].t<=.30 ? {sample:clip.samples[i],index:i}:null;
}
function fitVideo(){
  if(!clip)return;
  const [x0,y0,x1,y1]=clip.crop, area=$("visual"), frame=$("video-frame");
  const cw=x1-x0,ch=y1-y0, w=Math.min(area.clientWidth,area.clientHeight*cw/ch),h=w*ch/cw;
  frame.style.width=w+"px";frame.style.height=h+"px";
  video.style.width=clip.source_size[0]/cw*100+"%";video.style.height=clip.source_size[1]/ch*100+"%";
  video.style.left=-x0/cw*100+"%";video.style.top=-y0/ch*100+"%";
  const ratio=Math.min(window.devicePixelRatio||1,2);
  canvas.width=Math.round(w*ratio);canvas.height=Math.round(h*ratio);drawOverlay();
}
const edges=[["left_shoulder","right_shoulder"],["left_shoulder","left_elbow"],["left_elbow","left_wrist"],["right_shoulder","right_elbow"],["right_elbow","right_wrist"],["left_shoulder","left_hip"],["right_shoulder","right_hip"],["left_hip","right_hip"],["left_hip","left_knee"],["left_knee","left_ankle"],["right_hip","right_knee"],["right_knee","right_ankle"],["left_ankle","left_heel"],["left_heel","left_foot_index"],["right_ankle","right_heel"],["right_heel","right_foot_index"]];
function drawOverlay(){
  ctx.clearRect(0,0,canvas.width,canvas.height);
  const found=getSample(video.currentTime);if(!found||!annotations)return;
  const s=found.sample,p=s.points,[x0,y0,x1,y1]=clip.crop;
  const xy=p=>[(p[0]*1280-x0)*canvas.width/(x1-x0),(p[1]*720-y0)*canvas.height/(y1-y0)];
  const line=(a,b,color,dashed=false)=>{if(!a||!b)return;const A=xy(a),B=xy(b);ctx.strokeStyle=color;ctx.lineWidth=2.2*(canvas.width/400);ctx.setLineDash(dashed?[7,6]:[]);ctx.beginPath();ctx.moveTo(...A);ctx.lineTo(...B);ctx.stroke();};
  edges.forEach(([a,b])=>line(p[a],p[b],"#72e5cd"));
  for(const [side,color] of [["left","#8bd7ff"],["right","#ffce90"]]){
    line(p[side+"_hip"],p[side+"_ankle"],color,true);ctx.setLineDash([]);
    for(const n of ["hip","knee","ankle"]){const v=p[side+"_"+n];if(!v)continue;ctx.fillStyle=color;ctx.beginPath();ctx.arc(...xy(v),3.4*canvas.width/400,0,Math.PI*2);ctx.fill();}
  }
  if(s.bar_point){
    const [x,y]=xy([s.bar_point[0]/1280,s.bar_point[1]/720]);ctx.strokeStyle="#f3b6df";ctx.lineWidth=2*canvas.width/400;ctx.setLineDash([]);
    ctx.beginPath();ctx.arc(x,y,6*canvas.width/400,0,Math.PI*2);ctx.stroke();
    const recent=clip.samples.filter(v=>v.t<=s.t&&s.t-v.t<=1.2&&v.bar_point);
    ctx.beginPath();let last=null;for(const r of recent){const q=xy([r.bar_point[0]/1280,r.bar_point[1]/720]);if(last!==null&&r.t-last<=.30)ctx.lineTo(...q);else ctx.moveTo(...q);last=r.t;}ctx.stroke();
  }
}
function shown(metric,sample,forceSummary=false){
  const whole=forceSummary||summaryMode||metric.group==="动作节奏"||metric.key==="mean_power";
  return whole ? {value:metric.value,cue:metric.cue,kind:metric.kind} : {value:sample?.values[metric.key]??null,cue:sample?.feedback[metric.key]?.text||"片段积累中",kind:sample?.feedback[metric.key]?.kind||"neutral"};
}
function valueHTML(host,value,metric){host.replaceChildren(document.createTextNode(fmt(value,metric.decimals)),node("small","",metric.unit));}
function makeMetric(metric){
  const el=node("button","metric");el.type="button";el.dataset.key=metric.key;
  const label=node("div","metric-label",metric.label);
  if(metric.group==="动作节奏"||metric.key==="mean_power")label.append(node("small","","全段"));
  el.append(label,node("div","metric-value"),node("div","metric-cue"));
  el.setAttribute("aria-expanded","false");
  el.addEventListener("click",()=>openChart(metric.key));return el;
}
function renderCards(){
  for(const id of ["primary-metrics","control-metrics","tempo-metrics"])$(id).replaceChildren();
  for(const m of clip.metrics){
    const target=m.primary?"primary-metrics":m.group==="动作节奏"?"tempo-metrics":"control-metrics";
    $(target).append(makeMetric(m));
  }
  $("tempo-section").hidden=!clip.metrics.some(m=>m.group==="动作节奏");
  const prim=clip.metrics.filter(m=>m.primary);
  const chosen=clip.title==="步行"?prim.slice(1,3):[prim.find(m=>m.key==="power"),prim.find(m=>m.key==="speed")||prim.find(m=>m.key==="torso")].filter(Boolean);
  $("quick-metrics").replaceChildren();
  for(const m of chosen){const item=node("div","quick-metric");item.dataset.key=m.key;item.append(node("div","quick-value"),node("p","quick-label",m.label),node("p","quick-cue"));$("quick-metrics").append(item);}
  $("highlights").replaceChildren();
  for(const h of clip.highlights){const b=node("button","highlight");b.append(node("time","",time(h.t)),node("span","",h.text),node("span","","↗"));b.addEventListener("click",()=>{video.currentTime=h.t;summaryMode=false;updateTabs();update(true);});$("highlights").append(b);}
  $("methods").replaceChildren();
  for(const [key,value]of Object.entries(clip.methods))$("methods").append(node("p","",value));
  $("csv-download").href=`${clip.id}/${clip.csv}`;$("summary-download").href=`${clip.id}/summary.csv`;
  $("data-table").replaceChildren();for(const m of clip.metrics){const tr=node("tr");tr.append(node("td","",m.label),node("td","",fmt(m.value,m.decimals)+" "+m.unit),node("td","",m.cue));$("data-table").append(tr);}
  text($("parameters"),`设定 ${clip.body.mass_kg} kg / ${clip.body.height_cm} cm${clip.bar_load_kg?` · 杠铃 ${clip.bar_load_kg} kg`:""}　${clip.source_note}`);
  renderTrajectory();selectedChart=null;
}
function update(force=false){
  if(!clip)return;const found=getSample(video.currentTime),sample=found?.sample;
  text($("elapsed"),time(video.currentTime));$("seek").value=video.currentTime;
  if(force||lastSample!==(found?.index??-1)){
    lastSample=found?.index??-1;
    const hero=clip.metrics.find(m=>m.primary),heroData=shown(hero,sample,false);
    valueHTML($("featured-value"),heroData.value,hero);text($("featured-label"),hero.label+(summaryMode?" · 全段"+hero.statistic:""));text($("featured-cue"),heroData.cue);$("featured").classList.toggle("attention",heroData.kind==="attention");
    for(const el of document.querySelectorAll(".metric,.quick-metric")){
      const m=clip.metrics.find(m=>m.key===el.dataset.key),data=shown(m,sample);
      valueHTML(el.querySelector(".metric-value,.quick-value"),data.value,m);
      const quickLabel=el.querySelector(".quick-label");if(quickLabel)text(quickLabel,m.label+(summaryMode?" · "+m.statistic:""));
      const cue=el.querySelector(".metric-cue,.quick-cue");text(cue,data.cue);cue.classList.toggle("attention",data.kind==="attention");cue.classList.toggle("neutral",data.kind==="neutral");
      el.setAttribute("aria-label",`${m.label} ${fmt(data.value,m.decimals)} ${m.unit}，${data.cue}`);
    }
    if(selectedChart)updateChartCursor();
    updateTrajectoryCursor();
  }
  drawOverlay();
}
function svgEl(name,attributes={}){const e=document.createElementNS("http://www.w3.org/2000/svg",name);for(const [k,v]of Object.entries(attributes))e.setAttribute(k,v);return e;}
function openChart(key){
  const old=document.querySelector(".metric-chart");if(old)old.remove();
  document.querySelectorAll(".metric.active").forEach(el=>{el.classList.remove("active");el.setAttribute("aria-expanded","false");});
  if(selectedChart===key){selectedChart=null;return;}
  selectedChart=key;const m=clip.metrics.find(m=>m.key===key),button=document.querySelector(`.metric[data-key="${key}"]`);
  button.classList.add("active");button.setAttribute("aria-expanded","true");
  const block=node("div","metric-chart"),head=node("div","chart-header"),close=node("button","","×");close.setAttribute("aria-label","关闭数据曲线");close.addEventListener("click",()=>openChart(key));head.append(node("span","",m.label+" · "+m.unit),close);block.append(head);
  const data=clip.samples.map(s=>[s.t,s.values[key]??null]),vs=data.map(d=>d[1]).filter(finite);
  if(vs.length){
    let min=Math.min(...vs),max=Math.max(...vs);if(key==="power"||key==="speed"){min=Math.min(0,min);max=Math.max(0,max);}
    const pad=Math.max((max-min)*.08,.01);min-=pad;max+=pad;
    const x=t=>t/clip.duration*320,y=v=>100-(v-min)/(max-min)*92;
    const svg=svgEl("svg",{viewBox:"0 0 320 110",role:"img","aria-label":`${m.label}随时间变化，纵轴${fmt(min,m.decimals)}到${fmt(max,m.decimals)}${m.unit}。缺测处断开。`});
    if(min<=0&&max>=0)svg.append(svgEl("line",{x1:0,x2:320,y1:y(0),y2:y(0),stroke:"#696171","stroke-width":1}));
    let path="",last=null;
    for(const[t,v]of data){if(!finite(v)){last=null;continue;}path+=(last!==null&&t-last<=.30?"L":"M")+x(t).toFixed(2)+","+y(v).toFixed(2);last=t;}
    svg.append(svgEl("path",{d:path,fill:"none",stroke:"#40e5b5","stroke-width":2}));
    svg.append(svgEl("line",{id:"chart-cursor",x1:x(video.currentTime),x2:x(video.currentTime),y1:0,y2:105,stroke:"#f6f3fa","stroke-width":1,"stroke-dasharray":"3 3"}));block.append(svg);
    const ticks=node("div","chart-ticks");ticks.append(node("span","",`00:00 · ${fmt(min,m.decimals)}～${fmt(max,m.decimals)} ${m.unit}`),node("span","",time(clip.duration)));block.append(ticks);
  }else block.append(node("p","metric-cue neutral",m.cue+" · "+fmt(m.value,m.decimals)+" "+m.unit));
  const parent=button.parentElement;const nodes=[...parent.children].filter(n=>n.classList.contains("metric")),index=nodes.indexOf(button);(nodes[index%2===0?Math.min(index+1,nodes.length-1):index]).after(block);
}
function updateChartCursor(){const cursor=$("chart-cursor");if(cursor){cursor.setAttribute("x1",video.currentTime/clip.duration*320);cursor.setAttribute("x2",video.currentTime/clip.duration*320);}}
function renderTrajectory(){
  const host=$("trajectory");host.replaceChildren();$("trajectory-section").hidden=!clip.trajectory.length;if(!clip.trajectory.length)return;
  const tr=clip.trajectory.filter(v=>finite(v.x)&&finite(v.y)),xs=tr.map(v=>v.x),ys=tr.map(v=>v.y);
  const xmin=Math.min(0,...xs)-2,xmax=Math.max(0,...xs)+2,ymin=Math.min(0,...ys)-2,ymax=Math.max(0,...ys)+2;
  const x=v=>30+(v-xmin)/(xmax-xmin)*260,y=v=>175-(v-ymin)/(ymax-ymin)*165;
  const svg=svgEl("svg",{viewBox:"0 0 320 190",role:"img","aria-label":`杠铃轨迹，横向${xmin.toFixed(1)}到${xmax.toFixed(1)}厘米，竖向${ymin.toFixed(1)}到${ymax.toFixed(1)}厘米。横纵轴分别标尺。`});
  svg.append(svgEl("line",{x1:x(0),x2:x(0),y1:0,y2:180,stroke:"#81788d","stroke-dasharray":"4 4"}));
  let path="",last=null;for(const r of tr){path+=(last!==null&&r.t-last<=.30?"L":"M")+x(r.x)+","+y(r.y);last=r.t;}
  svg.append(svgEl("path",{d:path,fill:"none",stroke:"#c5a6f0","stroke-width":2.5}));
  svg.append(svgEl("circle",{id:"trajectory-cursor",cx:x(tr[0].x),cy:y(tr[0].y),r:4,fill:"#fff"}));host.append(svg);
  const labels=node("div","trajectory-label");labels.append(node("span","",`水平 ${xmin.toFixed(1)}～${xmax.toFixed(1)} cm`),node("span","",`竖向 ${ymin.toFixed(1)}～${ymax.toFixed(1)} cm`));host.append(labels);
  host._map={x,y};
}
function updateTrajectoryCursor(){
  const dot=$("trajectory-cursor"),host=$("trajectory");if(!dot||!host._map)return;
  const t=getSample(video.currentTime)?.sample.t,r=clip.trajectory.find(v=>v.t===t);
  dot.style.display=r&&finite(r.x)&&finite(r.y)?"":"none";if(r){dot.setAttribute("cx",host._map.x(r.x));dot.setAttribute("cy",host._map.y(r.y));}
}
function updateTabs(){
  $("live-tab").setAttribute("aria-selected",String(!summaryMode));$("summary-tab").setAttribute("aria-selected",String(summaryMode));update(true);
}
function setExpanded(value){
  expanded=value;app.classList.toggle("expanded",value);$("sheet-handle").setAttribute("aria-expanded",String(value));$("expanded-content").inert=!value;
  app.style.setProperty("--sheet-height",(value?Math.round(app.clientHeight*.76):baseHeight)+"px");
  if(!value)$("sheet-scroll").scrollTop=0;
}
function layout(){
  const was=expanded;baseHeight=Math.round(Math.max(300,Math.min(425,app.clientHeight*.44)));setExpanded(was);fitVideo();
}
function pickList(){
  for(const id of ["desktop-clips","mobile-clips"]){$(id).replaceChildren();manifest.clips.forEach((c,i)=>{const b=node("button","clip-item"+(i===clipIndex?" selected":""));b.setAttribute("aria-label",c.title+" "+c.view);b.append(node("span","clip-symbol",c.title==="步行"?"步":c.title==="硬拉"?"拉":"蹲"));const names=node("div");names.append(node("strong","",c.title+" · "+c.view),node("p","",c.title==="步行"?"姿态与身体控制":"关节、轨迹与输出"));b.append(names,node("span","clip-arrow","↗"));b.addEventListener("click",()=>{loadClip(i);$("chooser").close();});$(id).append(b);});}
}
async function loadClip(index){
  const version=++loadVersion;video.pause();clip=null;ctx.clearRect(0,0,canvas.width,canvas.height);video.removeAttribute("src");video.load();
  $("video-error").hidden=true;clipIndex=(index+manifest.clips.length)%manifest.clips.length;pickList();
  try{
    const descriptor=manifest.clips[clipIndex],res=await fetch(descriptor.data);if(!res.ok)throw Error("无法读取分析数据");const data=await res.json();if(version!==loadVersion)return;
    clip=data;lastSample=-1;summaryMode=true;renderCards();updateTabs();
    text($("clip-title"),clip.title);text($("clip-view"),clip.view);text($("source-badge"),clip.source_note);
    text($("other-view"),clip.view==="正面"?"查看侧面 ↗":"查看正面 ↗");
    video.src=`${clip.id}/${clip.video}`;video.load();$("seek").max=clip.duration;text($("duration"),time(clip.duration));
    const url=new URL(location.href);url.searchParams.set("clip",clip.id);history.replaceState(null,"",url);fitVideo();update(true);
  }catch(error){if(version!==loadVersion)return;text($("video-error"),error.message);$("video-error").hidden=false;notice("读取失败，请刷新页面");}
}
function frameLoop(){update();if(!video.paused)raf=requestAnimationFrame(frameLoop);}
video.addEventListener("play",()=>{summaryMode=false;updateTabs();$("play").setAttribute("aria-label","暂停视频");$("play").innerHTML='<svg class="icon"><use href="icons.svg#pause"/></svg>';cancelAnimationFrame(raf);frameLoop();});
video.addEventListener("pause",()=>{$("play").setAttribute("aria-label","播放视频");$("play").innerHTML='<svg class="icon"><use href="icons.svg#play"/></svg>';cancelAnimationFrame(raf);update(true);});
video.addEventListener("seeked",()=>update(true));video.addEventListener("loadeddata",()=>{fitVideo();update(true);});video.addEventListener("error",()=>{if(video.getAttribute("src")){text($("video-error"),"视频加载失败，请刷新重试");$("video-error").hidden=false;}});
$("play").addEventListener("click",async()=>{if(!clip)return;try{if(video.paused){if(video.ended)video.currentTime=0;await video.play();}else video.pause();}catch{notice("点击画面后重试播放");}});
$("seek").addEventListener("input",()=>{if(clip){summaryMode=false;updateTabs();video.currentTime=Number($("seek").value);update(true);}});
$("previous").addEventListener("click",()=>loadClip(clipIndex-1));$("next").addEventListener("click",()=>loadClip(clipIndex+1));
$("other-view").addEventListener("click",()=>{if(!clip)return;const other=manifest.clips.findIndex(c=>c.title===clip.title&&c.view!==clip.view);if(other>=0)loadClip(other);});
$("annotations").addEventListener("click",()=>{annotations=!annotations;$("annotations").setAttribute("aria-pressed",String(annotations));$("annotations").setAttribute("aria-label",annotations?"隐藏动作标注":"显示动作标注");drawOverlay();});
$("choose").addEventListener("click",()=>$("chooser").showModal());$("close-chooser").addEventListener("click",()=>$("chooser").close());
$("live-tab").addEventListener("click",()=>{summaryMode=false;updateTabs();});$("summary-tab").addEventListener("click",()=>{summaryMode=true;updateTabs();});
const handle=$("sheet-handle");
handle.addEventListener("pointerdown",e=>{if(e.button!==0)return;dragging={y:e.clientY,height:$("sheet").clientHeight,moved:false};handle.setPointerCapture(e.pointerId);app.classList.add("dragging");});
handle.addEventListener("pointermove",e=>{if(!dragging)return;const delta=dragging.y-e.clientY;if(Math.abs(delta)>5)dragging.moved=true;app.style.setProperty("--sheet-height",Math.min(app.clientHeight*.91,Math.max(baseHeight,dragging.height+delta))+"px");fitVideo();});
function endDrag(e){if(!dragging)return;const d=dragging;dragging=null;app.classList.remove("dragging");setExpanded(d.moved?$("sheet").clientHeight>baseHeight+60:!expanded);}
handle.addEventListener("pointerup",endDrag);handle.addEventListener("pointercancel",()=>{dragging=null;app.classList.remove("dragging");setExpanded(expanded);});
handle.addEventListener("click",e=>{if(e.detail===0)setExpanded(!expanded);});
handle.addEventListener("wheel",e=>{e.preventDefault();setExpanded(e.deltaY>0);},{passive:false});
$("sheet-scroll").addEventListener("wheel",e=>{if(!expanded&&e.deltaY>0){e.preventDefault();setExpanded(true);}},{passive:false});
let touchStart=null;$("sheet-scroll").addEventListener("touchstart",e=>{touchStart={y:e.touches[0].clientY,top:$("sheet-scroll").scrollTop};},{passive:true});
$("sheet-scroll").addEventListener("touchend",e=>{if(!touchStart)return;const dy=e.changedTouches[0].clientY-touchStart.y;if(!expanded&&dy< -35)setExpanded(true);else if(expanded&&touchStart.top<=0&&dy>70)setExpanded(false);touchStart=null;},{passive:true});
document.addEventListener("keydown",e=>{if(["INPUT","BUTTON","SUMMARY","A"].includes(document.activeElement?.tagName)||$("chooser").open)return;if(e.key===" "){e.preventDefault();$("play").click();}if(e.key==="ArrowRight")video.currentTime=Math.min(clip?.duration||0,video.currentTime+.5);if(e.key==="ArrowLeft")video.currentTime=Math.max(0,video.currentTime-.5);if(e.key==="Escape")setExpanded(false);});
new ResizeObserver(fitVideo).observe($("visual"));window.addEventListener("resize",layout);
(async()=>{layout();try{const response=await fetch("manifest.json");if(!response.ok)throw Error("分析目录读取失败");manifest=await response.json();const requested=new URL(location.href).searchParams.get("clip");const index=manifest.clips.findIndex(c=>c.id===requested);await loadClip(index>=0?index:0);}catch(e){notice(e.message);}})();
