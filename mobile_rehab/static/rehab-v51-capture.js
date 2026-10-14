/* Presentation/navigation adapter around the original capture controllers. */
'use strict';
function returnRehabV51(){
  const q=new URLSearchParams(location.search),ctx=RehabV51.context(state.captureSource||q.get('rehabSource'),q.get('rehabDay'));
  location.assign('/'+(ctx?'?'+ctx:'')+'#rehab');
}
function rehabLibraryTitleV51(){
  const q=new URLSearchParams(location.search);
  return q.get('guide')==='1'?'实时指导':(state.rehabEntry||q.get('entry'))==='assessment'?'活动度评估':'康复动作库';
}
function actionDetailV51(){
  const ex=selected();
  app.innerHTML=`<header class="rv-page-top"><button class="back" id="rv-library-back" aria-label="返回${esc(rehabLibraryTitleV51())}">‹</button><h1>动作详情</h1></header>${RehabV51.picture(ex.id,true)}<div class="rv-detail-name"><h2>${esc(ex.label)}</h2><span>${esc(ex.instructions.view_label)}</span></div><section class="card rv-intro"><h2>动作介绍</h2><p>专业介绍待完善</p><details><summary>已有动作文字与测量范围</summary><p>${esc(ex.instructions.start)}</p><p>${esc(ex.instructions.move)}</p><p>${esc(ex.instructions.return)}</p><p>${esc(ex.instructions.camera)}</p><p>${esc(ex.instructions.boundary)}</p><p>${esc(ex.instructions.count)}</p></details></section><div class="rv-detail-foot"><button class="primary" id="rv-detail-start">${new URLSearchParams(location.search).get('guide')==='1'?'开始实时指导':'开始评估'}</button></div>`;
  $('#rv-library-back').onclick=()=>backToLibrary('assessment');
  $('#rv-detail-start').onclick=()=>{state.preparing=true;if(new URLSearchParams(location.search).get('guide')==='1')livePage();else{state.captureSource='REPLAY_FILE';assessment();}window.scrollTo(0,0);};
  frameRehabV51('detail');
}
function feedbackScoresV51(box){
  for(const [key,label] of [['pain','疼痛'],['fatigue','疲劳']]){
    const select=$('#'+key),field=select.closest('label');if(field.querySelector('.rv-score-range'))continue;
    field.classList.add('rv-score-field');select.classList.add('rv-score-select');select.setAttribute('aria-hidden','true');select.tabIndex=-1;
    field.firstChild.textContent=label+'程度 ';
    const output=document.createElement('output');output.className='rv-score-output';output.id='rv-'+key+'-value';
    const range=document.createElement('input');range.type='range';range.className='rv-score-range';range.id='rv-'+key;range.min='0';range.max='10';range.step='1';range.setAttribute('aria-label',label+'程度');range.setAttribute('aria-describedby','rv-'+key+'-hint');
    const initial=RehabV52.score(select.value);range.value=String(initial??0);
    const update=()=>{const score=RehabV52.score(select.value);output.textContent=score===null?'未选择':score+' / 10';range.setAttribute('aria-valuetext',score===null?'未选择，请主动选择 0至10 分':score+' / 10');range.classList.toggle('unselected',score===null);range.style.setProperty('--rv-score',(score??0)*10+'%');};
    const choose=()=>{select.value=range.value;update();};range.oninput=choose;range.onclick=choose;
    range.onkeydown=e=>{if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End','PageUp','PageDown'].includes(e.key))choose();};
    select.onchange=()=>{const score=RehabV52.score(select.value);range.value=String(score??0);update();};
    select.addEventListener('invalid',e=>{e.preventDefault();toast('请选择真实'+label+'程度');range.focus();});
    const marks=document.createElement('div');marks.className='rv-score-marks';marks.setAttribute('aria-hidden','true');marks.innerHTML='<span>0</span><span>5</span><span>10</span>';
    const hint=document.createElement('p');hint.id='rv-'+key+'-hint';hint.className='rv-score-hint';hint.textContent='0 '+(key==='pain'?'无疼痛':'无疲劳')+' · 5 中等 · 10 很强';
    field.append(output,range,marks,hint);update();
  }
}
function feedbackViewV51(box,entry){
  const back=$('#back-history'),title=$('.page-head'),originalBack=back.onclick,originalText=back.textContent;
  const siblings=Array.from(box.parentElement.children).filter(n=>n!==box).map(n=>[n,n.hidden]);
  siblings.forEach(([n])=>n.hidden=true);box.hidden=false;if(title)title.hidden=true;
  feedbackScoresV51(box);
  box.querySelector('form button.primary').textContent='保存反馈';
  const keep=box.querySelectorAll('.tip')[1];Array.from(box.children).forEach(n=>{if(n.tagName!=='FORM'&&n!==keep)n.hidden=true;});
  const heading=document.createElement('h1');heading.className='rv-page-title';heading.textContent='训练反馈';box.before(heading);
  back.textContent='‹ 返回结果';back.onclick=()=>{heading.remove();siblings.forEach(([n,hidden])=>n.hidden=hidden);box.hidden=true;entry.hidden=false;if(title)title.hidden=false;back.onclick=originalBack;back.textContent=originalText;frameRehabV51('result');window.scrollTo(0,0);};
  frameRehabV51('feedback');window.scrollTo(0,0);box.querySelector('.rv-score-range').focus();
}
function planEntryV51(record,progress,index){
  const entry=record.items[index],isNext=entry.key===progress.next_key&&!progress.blocked;
  app.innerHTML=`<header class="rv-page-top"><button class="back" id="rv-plan-back" aria-label="返回我的计划">‹</button><h1>计划详情</h1></header>${RehabV51.picture(entry.exercise_id,true)}<div class="rv-detail-name"><h2>${esc(label(entry.exercise_id))}</h2><span>本人${sideLabel(entry.side)}</span></div><section class="card"><h2>本次目标</h2><p>${entry.settings.target_reps}次 × ${entry.settings.target_sets}组</p>${Number.isFinite(entry.settings.target_angle_deg)?`<p>个人角度目标 ${number(entry.settings.target_angle_deg,'°')}</p>`:''}<p class="caption">版本 ${record.revision} · 来自已保存计划</p><p>${progress.items[index].done?'已完成':isNext?'下一项':progress.blocked||'按计划顺序进行'}</p></section>${isNext?'<button class="primary" id="rv-entry-start">开始训练</button>':''}`;
  $('#rv-plan-back').onclick=()=>navigate('plan');
  if($('#rv-entry-start'))$('#rv-entry-start').onclick=()=>{state.captureSource='REPLAY_FILE';state.preparing=true;state.training={id:record.id,entry};state.selected=entry.exercise_id;state.side=entry.side;state.joint=selected().joint;state.tab='assess';state.detail=true;clearFile();assessment();window.scrollTo(0,0);};
  frameRehabV51('detail');
}
function extrasRehabV51(){
  state.tab='extras';state.job=null;state.detail=false;
  app.innerHTML='<button class="back" id="rv-extras-back">‹ 返回康复</button><h1 class="rv-page-title">健身 · 体态</h1><div class="rv-extra-grid"><button id="rv-fitness"><strong>健身录像</strong><span>独立健身分析 →</span></button><button id="rv-posture"><strong>体态分析</strong><span>正面与侧面站姿 →</span></button></div><p class="caption">辅助记录，不作为康复计划完成依据。</p>';
  $('#rv-extras-back').onclick=returnRehabV51;$('#rv-fitness').onclick=()=>navigate('fitness');$('#rv-posture').onclick=()=>navigate('posture');frameRehabV51('extras');
}
function frameRehabV51(view){
  if(!state.shared||!state.catalog.length||$('#pair-form')){delete document.body.dataset.rehabView;return;}
  const related=['assess','plan','history','fitness','posture','body','device','extras'].includes(state.tab)||!!state.job;
  if(!related){delete document.body.dataset.rehabView;$('.bottom-nav').hidden=false;return;}
  document.body.dataset.rehabView=view||(state.job?'result':state.training?'prepare':state.tab==='assess'?(state.detail?(state.preparing?'prepare':'detail'):'library'):state.tab);
  $('.bottom-nav').hidden=true;
  if(document.body.dataset.rehabView==='library'){const title=app.querySelector('.library-heading h1');if(title)title.textContent=rehabLibraryTitleV51();}
  if(document.body.dataset.rehabView==='library'&&!app.querySelector('.rv-unverified')){const note=document.createElement('p');note.className='caption rv-unverified';note.textContent='配图未核验，仅作视觉封面；动作文字与机位以现有说明为准。';app.querySelector('.library-toolbar')?.before(note);}
  const isFocused=['prepare','detail','result','guidance'].includes(document.body.dataset.rehabView);
  if(!app.querySelector('.back')&&!isFocused){const back=document.createElement('button');back.className='back rv-back';back.textContent='‹ 返回康复';back.onclick=returnRehabV51;app.prepend(back);}
}
// Wrap rendered pages, retaining the original camera, upload, plan and result handlers.
for(const name of ['assessment','actionLibrary','plan','history','fitnessPage','posturePage','bodyPage','devices','renderPostureReport','renderFitnessReport']){
  const original=window[name];window[name]=function(...args){const result=original(...args);frameRehabV51();if(state.shared&&name==='plan')app.querySelector('.page-head h1').textContent='我的计划';if(result&&typeof result.then==='function')result.then(()=>frameRehabV51(),()=>frameRehabV51());return result;};
}
const originalLivePageV51=livePage;
livePage=function(){const origin=document.body.dataset.rehabView;originalLivePageV51();if(origin==='prepare')$('#live-back').textContent=state.training?'‹ 返回训练准备':'‹ 返回评估准备';if(origin==='detail'){$('#live-back').textContent='‹ 返回动作详情';$('#live-back').onclick=()=>{stopLive();state.preparing=false;assessment();};}frameRehabV51('guidance');};
const originalRenderV51=render;
render=function(){if(state.tab==='extras'){extrasRehabV51();return;}originalRenderV51();frameRehabV51();};
const originalNavigationV51=syncNavigation;
syncNavigation=function(){originalNavigationV51();frameRehabV51();};
const originalShowJobV51=showJob;
showJob=async function(id,retry=0){
  if(state.job!==id)state.resultOrigin=state.tab==='history'?'history':state.training?'plan':state.tab==='body'?'body':'assessment';
  await originalShowJobV51(id,retry);if(state.job===id)frameRehabV51('result');
};
const originalRenderJobV51=renderJob;
renderJob=function(j){
  originalRenderJobV51(j);if(!state.shared)return;frameRehabV51('result');
  const back=$('#back-history');if(back){back.textContent=state.resultOrigin==='plan'?'‹ 返回我的计划':state.resultOrigin==='assessment'?'‹ 返回动作详情':state.resultOrigin==='body'?'‹ 返回身体汇总':'‹ 返回历史记录';back.onclick=()=>{if(state.resultOrigin==='assessment'){state.job=null;state.preparing=false;state.detail=true;state.training=null;state.tab='assess';assessment();window.scrollTo(0,0);}else navigate(state.resultOrigin==='body'?'body':state.resultOrigin==='plan'?'plan':'history');};}
  if(j.mode==='training'&&$('#retake'))$('#retake').onclick=()=>navigate('plan');
  if(j.state==='done'&&j.mode!=='fitness'&&j.mode!=='posture'){
    const card=$('#job-content>.card'),tag=card?.querySelector('.tag');if(tag){if(j.mode==='training')card.querySelector('h2').textContent=j.result.summary.plan_completed?'已达计划次数':'未达计划次数';const planButton=$('#view-plan');if(j.mode==='training'&&planButton){planButton.className='secondary';card.querySelector('details').append(planButton);const quality=document.createElement('p');quality.className='rv-result-quality';quality.textContent=$('#rv-feedback .tip').textContent;card.querySelector('.stat-grid').after(quality);}const saved=document.createElement('p');saved.className='rv-saved';saved.textContent='分析结果已保存';card.prepend(saved);}
  }
};
function initRehabV51Tools(){
  if(!state.shared||!state.catalog.length||$('#pair-form'))return;
  const tool=new URLSearchParams(location.search).get('tool');
  if(tool==='computer'){state.tab='device';devices();const guide=document.createElement('section');guide.className='card';guide.innerHTML='<h2>电脑端训练</h2><p class="caption">正式实时评估与训练在电脑康复页开始。手机可查看计划、安排日期；手机录像分析单独保存。</p>';app.querySelector('.page-head').after(guide);}
  else if(tool==='extras')extrasRehabV51();
  else if(tool==='body')navigate('body');
  frameRehabV51();
}
