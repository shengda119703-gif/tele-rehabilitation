/* Shared assessment/training presentation. Original writers and handlers remain owners. */
(function(root){
'use strict';
if(!root.document||!root.RehabMotionData)return;
const D=root.RehabMotionData,finite=D.finite,el=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;};
const escape=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icon=name=>'<svg aria-hidden="true" class="mr-icon"><use href="/static/assets/motion-review-icons.svg#'+name+'"/></svg>';
const time=t=>String(Math.floor(Math.max(0,t)/60)).padStart(2,'0')+':'+String(Math.floor(Math.max(0,t)%60)).padStart(2,'0');
const format=(v,d=1)=>finite(v)?(Math.abs(v)<.5*10**-d?0:v).toFixed(d):'—';
let current=null,sequence=0,aiRestoreObserver=null;
function specFor(job){return [...(typeof state!=='undefined'?state.catalog:[]),...(typeof state!=='undefined'?state.fitnessCatalog||[]:[]),...(typeof state!=='undefined'?state.postureCatalog||[]:[])].find(s=>s.id===job.exercise)||job.result?.spec||{};}
class Sheet{
 constructor(host,options){
  if(current)current.destroy();aiRestoreObserver?.disconnect();aiRestoreObserver=null;this.host=host;this.options=options;this.generation=++sequence;this.owner=typeof state==='undefined'?0:state.uploadOwnerGeneration||0;this.data=options.data;this.summary=true;this.expanded=false;this.listeners=[];this.moves=[];this.originals=[...host.childNodes];
  this.root=el('section','mr-view'+(options.live?' mr-live':''));this.root.id='motion-review';this.root.setAttribute('aria-label',options.live?'实时动作指导':options.job?.mode==='training'?'训练分析结果':'评估分析结果');
  this.root.innerHTML='<header class="mr-top"><button class="mr-icon-button mr-back" aria-label="返回原页面">'+icon('back')+'</button><div><strong class="mr-title"></strong><span class="mr-mode"></span></div><button class="mr-icon-button mr-annotation" aria-label="切换动作标注" aria-pressed="true">'+icon('body')+'</button></header><section class="mr-stage" aria-label="动作画面"><div class="mr-media"></div><p class="mr-media-note"></p></section><section class="mr-sheet" aria-label="动作数据"><button class="mr-handle" aria-label="展开或收起数据" aria-expanded="false"><span></span><small>上滑查看数据</small>'+icon('up')+'</button><div class="mr-scroll"><div class="mr-featured"><div class="mr-feature-value"></div><div class="mr-feature-copy"><small></small><p></p></div></div><div class="mr-quick"></div><div class="mr-primary-actions"></div><div class="mr-expanded" inert><div class="mr-section-head"><h2>动作数据</h2><div class="mr-tabs"><button data-mode="live">当前</button><button data-mode="summary" class="selected">全段</button></div></div><div class="mr-grid"></div><div class="mr-chart-region"></div><section class="mr-highlights"><h2>重点回看</h2><div></div></section><section class="mr-workflow" aria-label="本次后续操作"></section><details class="mr-more"><summary>数据明细与更多操作</summary><div class="mr-methods"></div><div class="mr-more-actions"></div><button class="mr-export">导出本次分析数据</button></details></div></div><div class="mr-transport"><div class="mr-progress"><span>00:00</span><input type="range" min="0" step="0.01" value="0" aria-label="视频进度"><span>00:00</span></div><div class="mr-play-row"><button class="mr-icon-button mr-rewind" aria-label="后退5秒">'+icon('previous')+'</button><button class="mr-play" aria-label="播放视频">'+icon('play')+'</button><button class="mr-icon-button mr-forward" aria-label="前进5秒">'+icon('next')+'</button></div></div></section>';
  this.saved=el('div','mr-preserved');this.saved.hidden=true;this.saved.inert=true;this.saved.append(...this.originals);host.append(this.saved,this.root);current=this;document.body.classList.add('motion-review-open');
  this.find('.mr-title').textContent=options.title||'';const mode=options.live?'实时指导':options.job?.mode==='training'?'训练结果':options.job?.mode==='fitness'?'健身分析':'评估结果',side=options.job?.side||(typeof state!=='undefined'?state.side:null);this.find('.mr-mode').textContent=mode+(side?' · '+(side==='right'?'右侧':'左侧'):'');
  this.on(this.find('.mr-back'),'click',()=>{const b=options.back;this.destroy();if(b)b.click();});
  this.bindSheet();
  this.video=options.video||null;
  if(this.video){this.move(options.preview||this.video,this.find('.mr-media'));if(!options.live){this.video.controls=false;this.overlay=el('canvas','mr-overlay');this.find('.mr-media').append(this.overlay);this.bindVideo();}}
  else{this.find('.mr-media-note').textContent='录像未保留，可查看已保存数据';this.find('.mr-transport').hidden=true;}
  this.find('.mr-annotation').hidden=options.live||!this.video;
  this.annotations=true;this.on(this.find('.mr-annotation'),'click',()=>{this.annotations=!this.annotations;this.find('.mr-annotation').setAttribute('aria-pressed',String(this.annotations));this.drawOverlay();});
  this.on(this.find('.mr-export'),'click',()=>this.export());
  this.on(this.find('[data-mode="live"]'),'click',()=>{this.summary=false;this.update(true);});this.on(this.find('[data-mode="summary"]'),'click',()=>{this.summary=true;this.update(true);});
  const resize=()=>{this.root.style.setProperty('--mr-base',Math.round(Math.max(305,Math.min(innerHeight*.44,425)))+'px');this.setExpanded(this.expanded);this.drawOverlay();};this.resize=new ResizeObserver(resize);this.resize.observe(host);this.on(root,'resize',resize);
  this.mediaResize=new ResizeObserver(()=>this.drawOverlay());this.mediaResize.observe(this.find('.mr-stage'));
  this.removal=new MutationObserver(()=>{if(!this.root.isConnected||this.owner!==(typeof state==='undefined'?0:state.uploadOwnerGeneration||0))this.destroy(false);});this.removal.observe(document.body,{childList:true,subtree:true});
  if(!options.live)this.renderData();
 }
 find(selector){return this.root.querySelector(selector);}
 valid(){return current===this&&this.root.isConnected&&this.owner===(typeof state==='undefined'?0:state.uploadOwnerGeneration||0);}
 on(target,event,handler,options){target?.addEventListener(event,handler,options);this.listeners.push(()=>target?.removeEventListener(event,handler,options));}
 move(node,parent){if(!node)return;const marker=document.createComment('motion-review-node');node.before(marker);this.moves.push([node,marker]);parent.append(node);}
 setExpanded(value){if(!this.root)return;this.expanded=!!value;this.root.classList.toggle('expanded',this.expanded);this.find('.mr-handle').setAttribute('aria-expanded',String(this.expanded));this.find('.mr-expanded').inert=!this.expanded;this.root.style.setProperty('--mr-sheet',value?'76%':'var(--mr-base,44%)');if(!value)this.find('.mr-scroll').scrollTop=0;}
 bindSheet(){
  const handle=this.find('.mr-handle'),scroll=this.find('.mr-scroll');let drag=null,touch=null;
  this.on(handle,'pointerdown',e=>{if(e.button!==0)return;drag={y:e.clientY,h:this.find('.mr-sheet').offsetHeight,moved:false};handle.setPointerCapture(e.pointerId);this.root.classList.add('dragging');});
  this.on(handle,'pointermove',e=>{if(!drag)return;const dy=drag.y-e.clientY;if(Math.abs(dy)>5)drag.moved=true;const h=Math.max(this.root.clientHeight*.30,Math.min(this.root.clientHeight*.91,drag.h+dy));this.root.style.setProperty('--mr-sheet',h+'px');});
  this.on(handle,'pointerup',()=>{if(!drag)return;const d=drag;drag=null;this.root.classList.remove('dragging');this.setExpanded(d.moved?this.find('.mr-sheet').offsetHeight>this.root.clientHeight*.53:!this.expanded);});
  this.on(handle,'pointercancel',()=>{drag=null;this.root.classList.remove('dragging');this.setExpanded(this.expanded);});
  this.on(handle,'click',e=>{if(e.detail===0)this.setExpanded(!this.expanded);});
  this.on(handle,'wheel',e=>{e.preventDefault();this.setExpanded(e.deltaY>0);},{passive:false});
  this.on(scroll,'wheel',e=>{if(!this.expanded&&e.deltaY>0){e.preventDefault();this.setExpanded(true);}},{passive:false});
  this.on(scroll,'touchstart',e=>{touch={y:e.touches[0].clientY,top:scroll.scrollTop};},{passive:true});
  this.on(scroll,'touchend',e=>{if(!touch)return;const dy=e.changedTouches[0].clientY-touch.y;if(!this.expanded&&dy< -35)this.setExpanded(true);else if(this.expanded&&touch.top<=0&&dy>70)this.setExpanded(false);touch=null;},{passive:true});
 }
 bindVideo(){
  const video=this.video,slider=this.find('.mr-progress input');
  const duration=()=>{const d=finite(video.duration)&&video.duration>0?video.duration:this.data?.duration||0;slider.max=String(d);this.find('.mr-progress span:last-child').textContent=time(d);this.drawOverlay();};
  this.on(video,'loadedmetadata',duration);this.on(video,'loadeddata',()=>{duration();this.update(true);});
  this.on(video,'timeupdate',()=>this.update());this.on(video,'seeked',()=>this.update(true));
  this.on(video,'play',()=>{this.summary=false;this.find('.mr-play').innerHTML=icon('pause');this.find('.mr-play').setAttribute('aria-label','暂停视频');this.update(true);this.tick();});
  this.on(video,'pause',()=>{cancelAnimationFrame(this.raf);this.find('.mr-play').innerHTML=icon('play');this.find('.mr-play').setAttribute('aria-label','播放视频');this.update(true);});
  this.on(video,'error',()=>{this.find('.mr-media-note').textContent='视频暂时无法播放，分析数据仍可查看';});
  this.on(this.find('.mr-play'),'click',()=>{if(video.paused){if(video.ended)video.currentTime=0;video.play().catch(()=>{this.find('.mr-media-note').textContent='点击播放重试';});}else video.pause();});
  this.on(slider,'input',()=>{this.summary=false;video.currentTime=Number(slider.value);this.update(true);});
  for(const [selector,d]of [['.mr-rewind',-5],['.mr-forward',5]])this.on(this.find(selector),'click',()=>{if(!finite(video.duration))return;video.currentTime=Math.max(0,Math.min(video.duration,video.currentTime+d));this.summary=false;this.update(true);});duration();
 }
 tick(){if(!this.valid()||this.video.paused)return;this.drawOverlay();this.raf=requestAnimationFrame(()=>this.tick());}
 value(d){const full=this.summary||d.group==='全段'||d.group==='动作节奏'||!this.video||!this.data.samples.length,s=D.nearest(this.data.samples,this.video?.currentTime||0);return full?{value:d.value,text:d.cue,kind:d.kind}:{value:s?.values[d.key]??null,...(s?.feedback[d.key]||{text:'当前片段未取到数值',kind:'neutral'})};}
 renderData(){
  const data=this.data;if(!data)return;
  this.find('.mr-annotation').hidden=!this.video||!data.samples.some(s=>Object.keys(s.points).length||s.bar_point);
  const grid=this.find('.mr-grid');grid.replaceChildren();
  for(const d of data.metrics){const card=el('button','mr-metric');card.type='button';card.dataset.metric=d.key;card.innerHTML='<span class="mr-label">'+escape(d.label)+(d.group==='全段'||d.group==='动作节奏'?'<small>全段</small>':'')+'</span><strong></strong><span class="mr-evaluation"></span>';this.on(card,'click',()=>this.chart(d));grid.append(card);}
  const primary=data.metrics.filter(d=>d.primary),hero=primary[0]||data.metrics[0];this.hero=hero;
  const quick=[data.metrics.find(d=>d.key==='power'),data.metrics.find(d=>d.key==='speed')].filter(Boolean);
  for(const d of primary)if(d!==hero&&!quick.includes(d)&&quick.length<2)quick.push(d);
  this.quick=quick.slice(0,2);this.find('.mr-quick').replaceChildren(...this.quick.map(d=>{const c=el('div');c.dataset.quick=d.key;c.innerHTML='<strong></strong><span></span><small></small>';return c;}));
  this.find('.mr-highlights>div').replaceChildren(...data.highlights.map(h=>{const b=el('button','mr-highlight');b.innerHTML='<time>'+time(h.t)+'</time><span>'+escape(h.text)+'</span>'+icon('open');this.on(b,'click',()=>{if(this.video){this.summary=false;this.video.currentTime=h.t;this.update(true);}});return b;}));this.find('.mr-highlights').hidden=!data.highlights.length;
  this.find('.mr-methods').replaceChildren(...data.methods.map(t=>el('p','',t)));
  this.update(true);
 }
 update(force=false){
  if(!this.valid()||this.options.live)return;const data=this.data;if(!data)return;
  const t=this.video?.currentTime||0;this.find('.mr-progress input').value=String(t);this.find('.mr-progress span').textContent=time(t);
  for(const b of this.root.querySelectorAll('[data-mode]'))b.classList.toggle('selected',b.dataset.mode===(this.summary?'summary':'live'));
  const set=(node,d)=>{const v=this.value(d);node.replaceChildren(document.createTextNode(format(v.value,d.decimals)),el('small','',d.unit));return v;};
  if(this.hero){const v=set(this.find('.mr-feature-value'),this.hero);this.find('.mr-feature-copy small').textContent=this.hero.label+(this.summary?' · 全段':'');this.find('.mr-feature-copy p').textContent=v.text;this.find('.mr-featured').classList.toggle('attention',v.kind==='attention');}
  else{this.find('.mr-feature-value').textContent='—';this.find('.mr-feature-copy p').textContent='本次分析结果已保留';}
  for(const d of data.metrics){const card=this.find('[data-metric="'+d.key+'"]'),v=set(card.querySelector('strong'),d),cue=card.querySelector('.mr-evaluation');cue.textContent=v.text;cue.dataset.kind=v.kind;}
  for(const d of this.quick){const card=this.find('[data-quick="'+d.key+'"]'),v=set(card.querySelector('strong'),d);card.querySelector(':scope>span').textContent=d.label+(this.summary?' · '+d.statistic:'');card.querySelector(':scope>small').textContent=v.text;card.querySelector(':scope>small').dataset.kind=v.kind;}
  this.drawOverlay();
 }
 drawOverlay(){
  if(!this.overlay||!this.video||!this.valid())return;const c=this.overlay,w=this.video.clientWidth,h=this.video.clientHeight;c.width=w;c.height=h;const ctx=c.getContext('2d');ctx.clearRect(0,0,w,h);if(!this.annotations||!this.video.videoWidth)return;
  const sample=D.nearest(this.data.samples,this.video.currentTime);if(!sample)return;const scale=Math.min(w/this.video.videoWidth,h/this.video.videoHeight),vw=this.video.videoWidth*scale,vh=this.video.videoHeight*scale,x0=(w-vw)/2,y0=(h-vh)/2;
  const xy=p=>[x0+p[0]*vw,y0+p[1]*vh],points=sample.points;
  ctx.lineWidth=2.5;ctx.strokeStyle='#72e5cd';ctx.fillStyle='#72e5cd';
  for(const side of ['left','right'])for(const[a,b]of [['shoulder','elbow'],['elbow','wrist'],['shoulder','hip'],['hip','knee'],['knee','ankle'],['ankle','heel'],['heel','foot_index']]){const p=points[side+'_'+a],q=points[side+'_'+b];if(p&&q){ctx.beginPath();ctx.moveTo(...xy(p));ctx.lineTo(...xy(q));ctx.stroke();}}
  for(const chain of [[0,1,2,3,4],[0,5,6,7,8],[5,9,10,11,12],[9,13,14,15,16],[13,17,18,19,20],[0,17]])for(let i=1;i<chain.length;i++){const p=points['hand_'+chain[i-1]],q=points['hand_'+chain[i]];if(p&&q){ctx.beginPath();ctx.moveTo(...xy(p));ctx.lineTo(...xy(q));ctx.stroke();}}
  for(const p of Object.values(points)){ctx.beginPath();ctx.arc(...xy(p),3,0,Math.PI*2);ctx.fill();}
  if(sample.bar_point){ctx.strokeStyle='#f3b6df';ctx.beginPath();ctx.arc(...xy(sample.bar_point),7,0,Math.PI*2);ctx.stroke();}
 }
 chart(metric){
  const host=this.find('.mr-chart-region');host.replaceChildren();const values=this.data.samples.map(s=>[s.t,s.values[metric.key]]),valid=values.map(p=>p[1]).filter(finite);
  const title=el('h2','',metric.label);host.append(title);if(!valid.length){host.append(el('p','',format(metric.value,metric.decimals)+' '+metric.unit+' · '+metric.cue));this.setExpanded(true);host.scrollIntoView({block:'nearest'});return;}
  const c=el('canvas','mr-chart'),min=Math.min(...valid),max=Math.max(...valid),span=max-min||1;c.width=650;c.height=190;c.setAttribute('role','img');c.setAttribute('aria-label',metric.label+'随时间变化，空值断开，范围'+format(min,metric.decimals)+'至'+format(max,metric.decimals)+metric.unit);const ctx=c.getContext('2d');ctx.strokeStyle='#40e5b5';ctx.lineWidth=3;ctx.beginPath();let last=null;
  for(const[t,v]of values){if(!finite(v)){last=null;continue;}const x=8+t/Math.max(.01,this.data.duration)*634,y=170-(v-min)/span*145;if(last===null||t-last>.32)ctx.moveTo(x,y);else ctx.lineTo(x,y);last=t;}ctx.stroke();host.append(c,el('p','mr-chart-scale',time(0)+'　'+format(min,metric.decimals)+'～'+format(max,metric.decimals)+' '+metric.unit+'　'+time(this.data.duration)));this.setExpanded(true);host.scrollIntoView({block:'nearest'});
 }
 export(){const data=JSON.stringify({kind:'ankang-motion-review',version:1,exercise:this.options.job?.exercise,side:this.options.job?.side,metrics:this.data?.metrics||[],series:this.data?.samples.map(s=>({t:s.t,values:s.values}))||[]},null,2);if(root.OfflineAndroid?.saveJson){root.OfflineAndroid.saveJson(data);return;}const u=URL.createObjectURL(new Blob([data],{type:'application/json'})),a=el('a');a.href=u;a.download='本次动作分析.json';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);}
 destroy(restore=true){if(this.destroyed)return;this.destroyed=true;cancelAnimationFrame(this.raf);this.listeners.forEach(f=>f());this.resize?.disconnect();this.mediaResize?.disconnect();this.removal?.disconnect();this.liveObserver?.disconnect();clearInterval(this.liveTimer);
  if(this.video&&!this.options.live)this.video.pause();
  if(restore&&this.host.isConnected){for(const [node,marker]of this.moves)if(marker.isConnected){marker.before(node);marker.remove();}if(this.saved?.isConnected)this.saved.replaceWith(...this.saved.childNodes);}
  this.root.remove();if(this.saved?.isConnected)this.saved.remove();if(current===this){current=null;document.body.classList.remove('motion-review-open');}
 }
}
function primaryAction(c,node,label){if(!node)return;if(label)node.textContent=label;node.classList.add('mr-primary-action');c.move(node,c.find('.mr-primary-actions'));}
function mountReport(job){
 if(typeof state!=='undefined'&&state.job!==job.id)return;
 const host=document.querySelector('#app');if(!host||job.state!=='done'||!job.result)return;
 const spec=specFor(job),data=D.build(job,spec),video=host.querySelector('#fit-video,.report-video,video'),back=host.querySelector('#back-history,#fit-back,#posture-back,.back');
 const feedback=host.querySelector('#rv-feedback'),oldFeedback=host.querySelector('#feedback-form')?.closest('.card'),plan=host.querySelector('#view-plan');
 const ordered=[...host.querySelectorAll('a')].find(a=>a.href.includes('assessmentRun')||a.textContent.includes('继续下一项'));
 const c=new Sheet(host,{job,data,video,title:data.title,back});
 if(feedback||oldFeedback){const box=feedback||oldFeedback;box.hidden=false;box.classList.add('mr-feedback-box');box.prepend(el('h2','mr-feedback-heading','训练反馈'));c.move(box,c.find('.mr-workflow'));if(typeof feedbackScoresV51==='function')feedbackScoresV51(box);const action=el('button','mr-primary-action','记录疼痛与疲劳');c.find('.mr-primary-actions').append(action);c.on(action,'click',()=>{c.setExpanded(true);box.scrollIntoView({block:'start'});});}
 else if(plan&&!ordered)primaryAction(c,plan,'查看训练安排');
 // Keep the original ordered-assessment navigation and save receipt visible.
 if(ordered){const receipt=ordered.parentElement.querySelector('[role=status]');if(receipt)c.move(receipt,c.find('.mr-workflow'));if(plan)c.move(plan,c.find('.mr-more-actions'));primaryAction(c,ordered,'继续评估计划');}
 const originalAI=c.saved.querySelector('.rv-ask-ai');if(originalAI){const ask=el('button','','问康复管家');c.find('.mr-more-actions').append(ask);c.on(ask,'click',()=>{const owner=c.owner;c.destroy();aiRestoreObserver?.disconnect();aiRestoreObserver=new MutationObserver(()=>{if(owner!==(state.uploadOwnerGeneration||0)||state.tab!=='assistant'&&state.job!==job.id){aiRestoreObserver?.disconnect();aiRestoreObserver=null;return;}if(state.job===job.id&&host.querySelector('#back-history')&&!current){aiRestoreObserver.disconnect();aiRestoreObserver=null;mountReport(job);}});aiRestoreObserver.observe(host,{childList:true,subtree:true});originalAI.click();});}
 for(const selector of ['#delete-video','#fit-delete','#retake','#fit-again']){const n=c.saved.querySelector(selector);if(n)c.move(n,c.find('.mr-more-actions'));}
 const limitations=job.result.limitations||[];for(const message of limitations)c.find('.mr-methods').append(el('p','',message));
 if(root.PhoneLocal&&job.result.review_trace){const owner=c.owner;void api('/jobs/'+job.id+'/review').then(trace=>{if(c.valid()&&c.owner===owner){c.data=D.build(job,spec,trace);c.renderData();}}).catch(()=>{/* Old/remote records still show their original summary. */});}
 return c;
}
function mountLive(host,options={}){
 // Hosted formal practice uses panel-scoped controls; keep its existing view.
 if(options.practice&&options.practice.context.provider!=='phone-local-1')return;
 const video=host.querySelector('#live-video');if(!video||current?.options.live&&current.video===video)return current;
 const preview=video.closest('.live-preview'),back=host.querySelector('#live-back,#formal-back,#practice-back,.back'),ex=options.practice?state.catalog.find(s=>s.id===options.practice.receipt?.exercise_id):typeof selected==='function'?selected():null;
 const angle=host.querySelector('#live-angle'),cue=host.querySelector('#live-cue'),status=host.querySelector('#live-status');
 const controls=host.querySelector('#live-start')?.closest('.live-controls'),practiceControls=host.querySelector('#practice-pause')?.parentElement;
 const consent=host.querySelector('#live-consent')?.closest('label'),facing=host.querySelector('#live-facing')?.closest('label'),voice=host.querySelector('#live-voice')?.closest('label');
 if(root.PhoneLocal&&consent&&consent.lastChild?.nodeType===Node.TEXT_NODE)consent.lastChild.textContent='同意在手机上分析本次画面，不保存画面。';
 const c=new Sheet(host,{live:true,video,preview,back,title:ex?.label||'动作指导'});c.find('.mr-tabs').hidden=true;c.find('.mr-highlights').hidden=true;c.find('.mr-more').hidden=true;c.find('.mr-transport').hidden=true;
 c.find('.mr-feature-value').classList.add('mr-live-number');if(angle)c.move(angle,c.find('.mr-feature-value'));if(cue){c.find('.mr-feature-copy p').remove();c.move(cue,c.find('.mr-feature-copy'));}c.find('.mr-feature-copy small').textContent='当前动作提示';
 const snapshot=el('div','mr-live-feedback');if(status)c.move(status,snapshot);c.find('.mr-primary-actions').append(snapshot);
 if(consent)c.move(consent,c.find('.mr-primary-actions'));if(controls)c.move(controls,c.find('.mr-primary-actions'));
 for(const selector of ['#formal-view','#formal-plan-confirmed','#formal-companion']){const field=host.querySelector(selector);if(field)c.move(field.closest('label'),c.find('.mr-primary-actions'));}
 if(practiceControls&&practiceControls!==controls)c.move(practiceControls,c.find('.mr-primary-actions'));
 const instructions=el('section','mr-live-instructions');instructions.innerHTML='<h2>动作要点</h2>'+(ex?.instructions?['start','move','return'].map(k=>'<p>'+escape(ex.instructions[k])+'</p>').join(''):'');c.find('.mr-workflow').append(instructions);
 if(options.practice){const s=options.practice.receipt.settings,target=el('p','mr-live-target','本组目标 '+s.target_reps+' 次'+(finite(s.target_angle_deg)?' · '+format(s.target_angle_deg,0)+'°':''));c.find('.mr-primary-actions').prepend(target);}
 if(typeof assessment==='function'&&(!options.practice||state.training?.id===options.practice.start.plan_id)){const record=el('button','mr-primary-action',options.practice?'上传训练录像':'拍摄或选择录像');c.find('.mr-workflow').append(record);c.on(record,'click',()=>{if(typeof pausePractice==='function')pausePractice();if(typeof stopLive==='function')stopLive('switch_to_recording');c.destroy();state.preparing=true;assessment();});}
 const settings=el('details','mr-camera-settings');settings.innerHTML='<summary>镜头与语音</summary>';for(const node of [facing,voice])if(node)c.move(node,settings);c.find('.mr-workflow').append(settings);
 const count=host.querySelector('#practice-count');if(count)c.move(count.closest('label'),c.find('.mr-workflow'));
 for(const selector of ['#formal-pause','#formal-reconcile','#formal-export','#formal-history','#practice-save','#practice-time']){const n=host.querySelector(selector);if(n)c.move(n,c.find('.mr-workflow'));}
 c.find('.mr-grid').innerHTML='<div class="mr-live-info">当前角度和动作提示来自实时分析。结束后的结果仍按原流程保存。</div>';
 const sync=()=>{if(!c.valid())return;const observed=angle?.textContent||'—',ready=!!video.srcObject&&video.readyState>=2;video.style.visibility=ready?'visible':'hidden';c.find('.mr-media-note').textContent=ready?'':'准备好后打开摄像头';c.find('.mr-section-head h2').textContent='实时指导 · '+observed;};
 c.on(video,'loadeddata',sync);c.on(video,'emptied',sync);
 c.liveObserver=new MutationObserver(sync);for(const n of [angle,cue,status])if(n)c.liveObserver.observe(n,{childList:true,subtree:true,characterData:true});sync();
 return c;
}
root.RehabMotionReview={Sheet,mountReport,mountLive,destroy:()=>current?.destroy(),get current(){return current;}};
// Load after the existing presentation adapters, at the same real entry points.
if(typeof renderJob==='function'){const previous=renderJob;renderJob=function(job){current?.destroy();const result=previous(job);if(job.state==='done'&&job.result&&['assessment','training','fitness','posture'].includes(job.mode))mountReport(job);return result;};}
if(typeof livePage==='function'){const previous=livePage;livePage=function(...args){current?.destroy();const result=previous(...args);mountLive(document.querySelector('#app'));return result;};}
if(typeof drawPractice==='function'){const previous=drawPractice;drawPractice=function(j,area){if(j.ended||j.sequenceStage==='REST')current?.destroy();const result=previous(j,area);if(!j.ended&&j.receipt?.state==='PRACTICING')mountLive(document.querySelector('#app'),{practice:j});return result;};}
})(globalThis);
