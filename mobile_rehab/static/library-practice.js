/* User-started illustrated practice, deliberately separate from measured jobs/plans. */
(function(root){
 'use strict';
 const VERSION='illustrated-practice-1',UUID=/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/;
 const copy=v=>JSON.parse(JSON.stringify(v)),same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
 function context(value){
  if(!value||!UUID.test(value.participant_id)||typeof value.provider!=='string'||!value.provider||typeof value.source_context!=='string'||!value.source_context)throw Error('训练档案暂未能核对');
  return {participant_id:value.participant_id,provider:value.provider,source_context:value.source_context};
 }
 function steps(card){return String(card.instructions||'').split(/\n+/).map(s=>s.replace(/^\s*\d+[.、)）]\s*/,'').trim()).filter(Boolean);}
 function validate(record,scope){
  if(!record||record.version!==VERSION||!UUID.test(record.id)||!same(record.context,scope)||!/^T-[A-Z]+-\d{3}$/.test(record.card_id)||typeof record.name!=='string'||record.name.length>160||!['IN_PROGRESS','FINISHED'].includes(record.state)||!Number.isFinite(Date.parse(record.started_at))||!Number.isFinite(record.elapsed_ms)||record.elapsed_ms<0||record.elapsed_ms>7*86400000||!Number.isInteger(record.step_index)||record.step_index<0||record.step_index>99)throw Error('原训练记录格式不正确，未覆盖');
  if(record.state==='FINISHED'&&(!Number.isFinite(Date.parse(record.ended_at))||!['completed','stopped','discomfort'].includes(record.finish_reason)))throw Error('训练结束记录不完整');
  if(record.feedback!==null&&(!record.feedback||!['pain','fatigue'].every(k=>record.feedback[k]===null||Number.isInteger(record.feedback[k])&&record.feedback[k]>=0&&record.feedback[k]<=10)))throw Error('练后感受无效');
  return record;
 }
 class Records{
  constructor(storage,scope){this.storage=storage;this.context=context(scope);this.key='ankang-illustrated-practice-1:'+JSON.stringify(Object.values(this.context));this.raw=storage.getItem(this.key);const value=this.raw?JSON.parse(this.raw):{version:VERSION,records:[]};
   if(value.version!==VERSION||!Array.isArray(value.records)||value.records.length>250)throw Error('原训练记录无法读取，未覆盖');
   const ids=new Set();for(const row of value.records){validate(row,this.context);if(ids.has(row.id))throw Error('原训练记录编号重复');ids.add(row.id);}this.value=value;
  }
  save(record){validate(record,this.context);if(this.storage.getItem(this.key)!==this.raw)throw Error('训练记录已在另一页面更新，请重新打开本动作');
   const value=copy(this.value),index=value.records.findIndex(r=>r.id===record.id);if(index>=0&&value.records[index].state==='FINISHED'&&!same(value.records[index],record))throw Error('已结束记录不能改写');
   if(index<0){if(value.records.length>=250)throw Error('训练记录已满，请先导出训练记录');value.records.push(copy(record));}else value.records[index]=copy(record);
   const text=JSON.stringify(value);this.storage.setItem(this.key,text);this.raw=text;this.value=value;return copy(record);
  }
 }
 function advance(record,now,previous,running){const dt=now-previous;return {...record,elapsed_ms:record.elapsed_ms+(running&&dt>=0&&dt<1500?dt:0)};}
 function format(ms){const seconds=Math.floor(ms/1000);return String(Math.floor(seconds/60)).padStart(2,'0')+':'+String(seconds%60).padStart(2,'0');}
 const apiExport={VERSION,Records,context,steps,validate,advance,format};root.RehabLibraryPractice=apiExport;
 if(typeof module!=='undefined')module.exports=apiExport;
 if(!root.document||typeof api!=='function'||typeof app==='undefined')return;
 const E=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 let journey=null,clock=null,generation=0;
 const current=j=>journey===j&&j.ownerGeneration===(state.uploadOwnerGeneration||0)&&document.querySelector('#lp-area')===j.area;
 async function records(){return new Records(localStorage,context(await api('/practice/context')));}
 function tick(j){const now=performance.now();j.record=advance(j.record,now,j.previous,j.running);j.previous=now;if(current(j)){const timer=j.area.querySelector('#lp-time');if(timer)timer.textContent=format(j.record.elapsed_ms);}}
 function persist(j){if(!current(j))return false;try{j.repo.save(j.record);j.unsaved=false;return true;}catch(e){j.unsaved=true;j.running=false;clearInterval(clock);clock=null;const status=j.area.querySelector('#lp-status');if(status)status.textContent=e.message;const button=j.area.querySelector('#lp-pause');if(button)button.textContent='继续训练';return false;}}
 function pause(){const j=journey;if(!j)return;tick(j);j.running=false;clearInterval(clock);clock=null;persist(j);const button=j.area.querySelector('#lp-pause');if(button)button.textContent='继续训练';}
 function leave(){pause();journey=null;++generation;state.libraryPractice=false;document.body.classList.remove('library-practice-open');}
 function resume(j){if(!current(j)||j.record.state==='FINISHED'||document.hidden)return;j.previous=performance.now();j.running=true;clearInterval(clock);clock=setInterval(()=>{if(!current(j)){pause();return;}tick(j);if(performance.now()-j.savedAt>5000){persist(j);j.savedAt=performance.now();}},250);}
 function image(j,slot){const item=j.catalogue.images[slot||j.card.overview];return item?`<img src="${E(item.url)}" alt="${E(item.description)}">`:'';}
 function source(j){return `<details class="lp-source"><summary>动作准备与注意事项</summary><p>${E(j.card.preparation)}</p><p>${E(j.card.start_conditions)}</p><p>${E(j.card.stop_conditions)}</p><p>${E(j.card.source_dose)}</p></details>`;}
 function draw(j){
  if(!current(j))return;document.body.classList.add('library-practice-open');const list=steps(j.card),index=Math.min(j.record.step_index,list.length-1),step=list[index];
  // Illustrations are ordered source material, not live pose or phase observations.
  j.area.innerHTML=`<header class="lp-top"><button id="lp-back" aria-label="返回动作详情">‹</button><h1>${E(j.card.name)}</h1></header><figure class="lp-picture">${image(j)}</figure><section class="lp-panel"><div class="lp-line"><span>图文跟练</span><strong id="lp-time">${format(j.record.elapsed_ms)}</strong></div><p class="lp-progress">步骤 ${index+1} / ${list.length}</p><p class="lp-cue" id="lp-cue">${E(step)}</p><p class="lp-preparation">${E(j.card.preparation)}</p><div class="lp-step-controls"><button id="lp-previous" ${index===0?'disabled':''}>上一步</button><button class="primary" id="lp-next">${index===list.length-1?'结束并记录':'下一步'}</button></div>${source(j)}<p id="lp-status" role="status"></p></section><footer class="lp-controls"><button id="lp-pause">${j.running?'暂停训练':'继续训练'}</button><button id="lp-end">结束训练</button></footer>`;
  j.area.querySelector('#lp-back').onclick=()=>{leave();j.onBack();};
  j.area.querySelector('#lp-pause').onclick=()=>{if(j.running)pause();else resume(j);j.area.querySelector('#lp-pause').textContent=j.running?'暂停训练':'继续训练';};
  j.area.querySelector('#lp-previous').onclick=()=>{tick(j);j.record.step_index=Math.max(0,index-1);persist(j);draw(j);};
  j.area.querySelector('#lp-next').onclick=()=>{if(index===list.length-1){finishForm(j,true);return;}tick(j);j.record.step_index=index+1;persist(j);draw(j);};
  j.area.querySelector('#lp-end').onclick=()=>finishForm(j);
 }
 function feedbackSelect(key,title){return `<label>${title}<select id="lp-${key}"><option value="">暂不填写</option>${Array.from({length:11},(_,n)=>`<option value="${n}">${n} / 10</option>`).join('')}</select></label>`;}
 function finishForm(j,completed=false){
  pause();if(!current(j))return;
  j.area.innerHTML=`<header class="lp-top"><button id="lp-continue" aria-label="继续训练">‹</button><h1>本次训练</h1></header><section class="lp-finish"><h2>${E(j.card.name)}</h2><strong class="lp-total">${format(j.record.elapsed_ms)}</strong><p>训练用时</p><form id="lp-feedback"><label>本次情况<select id="lp-reason" required><option value="completed">已练完</option><option value="stopped">提前结束</option><option value="discomfort">不适停止</option></select></label>${feedbackSelect('pain','疼痛感')}${feedbackSelect('fatigue','疲劳感')}<p id="lp-status" role="status"></p><button class="primary" type="submit">保存训练记录</button></form></section>`;
  j.area.querySelector('#lp-reason').value=completed?'completed':'stopped';
  j.area.querySelector('#lp-continue').onclick=()=>{draw(j);resume(j);j.area.querySelector('#lp-pause').textContent='暂停训练';};
  j.area.querySelector('#lp-feedback').onsubmit=async event=>{
   event.preventDefault();if(!current(j)||j.saving)return;j.saving=true;const button=event.currentTarget.querySelector('button');button.disabled=true;
   try{const scope=context(await api('/practice/context'));if(!current(j)||!same(scope,j.repo.context))throw Error('账号已变化，未把旧训练写入新档案');
    const value=k=>{const text=j.area.querySelector('#lp-'+k).value;return text===''?null:Number(text);};
    const final={...j.record,state:'FINISHED',ended_at:new Date().toISOString(),finish_reason:j.area.querySelector('#lp-reason').value,feedback:{pain:value('pain'),fatigue:value('fatigue')}};
    j.repo.save(final);j.record=final;j.unsaved=false;drawResult(j);
   }catch(e){if(current(j))j.area.querySelector('#lp-status').textContent=e.message;}finally{j.saving=false;if(button.isConnected)button.disabled=false;}
  };
 }
 function drawResult(j){
  if(!current(j))return;document.body.classList.add('library-practice-open');const f=j.record.feedback;
  j.area.innerHTML=`<header class="lp-top"><button id="lp-back" aria-label="返回训练记录">‹</button><h1>训练记录</h1></header><section class="lp-finish"><h2>${E(j.card.name)}</h2><strong class="lp-total">${format(j.record.elapsed_ms)}</strong><p>训练用时 · ${j.record.finish_reason==='discomfort'?'不适停止':j.record.finish_reason==='stopped'?'提前结束':'已练完'}</p>${f?.pain!==null&&f?.pain!==undefined?`<p>疼痛感 ${f.pain} / 10</p>`:''}${f?.fatigue!==null&&f?.fatigue!==undefined?`<p>疲劳感 ${f.fatigue} / 10</p>`:''}<p class="lp-provenance">图文跟练 · 本机记录</p><button class="primary" id="lp-history">查看训练记录</button><button id="lp-again">再练一次</button></section>`;
  const history=()=>{leave();navigate('history');};j.area.querySelector('#lp-back').onclick=history;j.area.querySelector('#lp-history').onclick=history;
  j.area.querySelector('#lp-again').onclick=()=>{const {card,catalogue,onBack}=j;leave();void start(card,catalogue,onBack,true);};
 }
 async function start(card,catalogue,onBack,fresh=false,recordId=null){
  if(card?.kind!=='training'||!steps(card).length)return;
  leave();state.libraryPractice=true;const token=++generation,ownerGeneration=state.uploadOwnerGeneration||0;app.innerHTML='<section id="lp-area"><p role="status">正在打开训练…</p></section>';const area=document.querySelector('#lp-area');
  try{const repo=await records();if(token!==generation||ownerGeneration!==(state.uploadOwnerGeneration||0)||document.querySelector('#lp-area')!==area)return;
   let record=recordId?repo.value.records.find(r=>r.id===recordId&&r.card_id===card.id):!fresh?repo.value.records.find(r=>r.card_id===card.id&&r.state==='IN_PROGRESS'):null;
   if(recordId&&!record)throw Error('未找到本人的这次训练记录');
   if(!record){record={version:VERSION,id:newUploadOperation(),context:repo.context,card_id:card.id,name:card.name,state:'IN_PROGRESS',started_at:new Date().toISOString(),elapsed_ms:0,step_index:0,feedback:null};repo.save(record);}
   journey={card,catalogue,onBack,repo,record:copy(record),area,ownerGeneration,running:false,previous:performance.now(),savedAt:performance.now()};
   if(record.state==='FINISHED')drawResult(journey);else{resume(journey);draw(journey);}
  }catch(e){if(token===generation&&ownerGeneration===(state.uploadOwnerGeneration||0)&&document.querySelector('#lp-area')===area){state.libraryPractice=false;area.innerHTML='<p role="status">'+E(e.message)+'</p><button id="lp-return">返回动作详情</button>';area.querySelector('button').onclick=onBack;}}
 }
 async function history(){
  if(!['all','rehab'].includes(state.historyFilter||'all'))return;const area=document.createElement('section');area.id='library-practice-records';area.className='card';app.appendChild(area);const ownerGeneration=state.uploadOwnerGeneration||0;
  const alive=()=>state.tab==='history'&&ownerGeneration===(state.uploadOwnerGeneration||0)&&document.querySelector('#library-practice-records')===area;
  try{const repo=await records();if(!alive())return;const rows=repo.value.records.slice().reverse();if(!rows.length){area.remove();return;}
   area.dataset.hasRecords='true';area.innerHTML='<h2>动作库训练记录</h2>'+rows.map(r=>`<button class="record" data-library-practice="${E(r.id)}"><span><strong>${E(r.name)}</strong><small>${dateLabel(r.ended_at||r.started_at)} · ${format(r.elapsed_ms)} · 图文跟练</small></span><span class="badge">${r.state==='FINISHED'?'已保存':'继续'} ›</span></button>`).join('')+'<button class="secondary" id="lp-export">导出训练记录</button>';
   area.querySelector('#lp-export').onclick=()=>{if(!alive())return;const text=JSON.stringify({version:VERSION,context:repo.context,records:repo.value.records},null,2);if(root.OfflineAndroid?.saveJson)OfflineAndroid.saveJson(text);else{const url=URL.createObjectURL(new Blob([text],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download='安康-动作库训练记录.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}};
   const empty=document.querySelector('#records .empty');if(empty){const title=empty.querySelector('h3');if(title)title.textContent='暂无录像分析记录';}
   area.querySelectorAll('[data-library-practice]').forEach(b=>b.onclick=async()=>{const row=rows.find(r=>r.id===b.dataset.libraryPractice);try{const catalogue=await root.RehabLibrary.load();if(!alive())return;const card=catalogue.actions.find(a=>a.id===row.card_id&&a.kind==='training');if(!card)throw Error('动作资料暂未读取');await start(card,catalogue,()=>navigate('history'),false,row.id);}catch(e){if(alive())toast(e.message);}});
  }catch(e){if(alive())area.innerHTML='<p role="status">训练记录暂未能读取</p><button id="lp-history-retry">重试</button>';area.querySelector('#lp-history-retry')?.addEventListener('click',()=>{area.remove();void history();});}
 }
 Object.assign(apiExport,{start,history,pause,leave});
 const originalHistory=renderHistory;renderHistory=function(){leave();originalHistory();void history();};
 const originalNavigate=navigate;navigate=function(...args){leave();return originalNavigate(...args);};
 document.addEventListener('visibilitychange',()=>{if(document.hidden)pause();});root.addEventListener('pagehide',pause);
 const originalOfflinePause=root.offlinePause;root.offlinePause=function(){pause();originalOfflinePause?.();};
 const originalOfflineBack=root.offlineBack;root.offlineBack=function(){if(journey){const j=journey;leave();j.onBack();return true;}return originalOfflineBack?.()||false;};
 const observer=new MutationObserver(()=>{if(journey&&!current(journey)){clearInterval(clock);journey.running=false;journey=null;state.libraryPractice=false;document.body.classList.remove('library-practice-open');}});observer.observe(document.body,{childList:true,subtree:true});
})(typeof window==='undefined'?globalThis:window);
