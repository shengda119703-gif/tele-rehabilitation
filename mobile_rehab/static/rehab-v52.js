/* Contextual AI adapter over the existing capture chat renderer. */
'use strict';
if(typeof window!=='undefined'){
  let visit=null, visitNumber=0;
  const originalHealthPage=healthPage;
  function restoreAI(){
    const saved=visit;if(!saved)return;visit=null;healthGeneration++;
    Object.assign(state,saved.state);healthDraft=saved.healthDraft;healthPrivate=saved.healthPrivate;healthData=saved.healthData;
    app.replaceChildren(...saved.nodes);document.body.dataset.rehabView=saved.view;
    $('.bottom-nav').hidden=saved.navHidden;window.scrollTo(saved.x,saved.y);saved.focus?.focus({preventScroll:true});
  }
  function returnFromAI(){const current=visit;if(!current)return;restoreAI();if(RehabHistoryV52.state?.rehabAi52===current.historyKey)RehabHistoryV52.back();}
  window.addEventListener('popstate',e=>{if(visit&&e.state?.rehabAi52!==visit.historyKey)restoreAI();});
  async function loadAI(){
    const current=visit;if(!current)return;const generation=++healthGeneration;
    app.innerHTML='<button class="back" id="rv-ai-back">‹ 返回原页面</button><h1>康复管家</h1><p role="status">正在读取现有会话…</p>';
    $('#rv-ai-back').onclick=returnFromAI;
    try{
      const data=await api('/product');if(visit!==current||generation!==healthGeneration)return;
      if(data.needs_profile)throw Error('请先在现有档案入口建立本人档案。');
      healthData=data;assistantPage(data);
      const back=$('#health-back');back.textContent='‹ 返回原页面';back.onclick=returnFromAI;
      $('.page-head h1').textContent='康复管家';
      const notice=document.createElement('p');notice.className='rv-ai-notice';notice.textContent='仅预填问题，未附报告数值。辅助理解，不作为标准动作指导。';$('.page-head').after(notice);
      const conversation=$('.health-chat'),past=document.createElement('details');past.className='rv-ai-past';past.innerHTML='<summary>已有对话</summary>';conversation.before(past);past.append(conversation);past.open=!healthDraft;
      document.querySelector('[for="health-chat"]').textContent='确认要问的问题';
      document.querySelectorAll('[data-health-nav]').forEach(b=>b.onclick=()=>{const tab=b.dataset.healthNav;returnFromAI();navigate(tab);});
    }catch(e){
      if(visit!==current)return;
      // Authentication revocation must never restore a cached private report.
      if(e.status===401){visit=null;return;}
      if(generation!==healthGeneration)return;
      app.innerHTML=`<button class="back" id="rv-ai-back">‹ 返回原页面</button><h1>会话暂不可用</h1><p role="alert">${esc(e.message)}</p><button class="secondary" id="rv-ai-retry">重试</button>`;
      $('#rv-ai-back').onclick=returnFromAI;$('#rv-ai-retry').onclick=loadAI;
    }
  }
  function openAI(context){
    if(visit||state.upload)return;
    visit={nodes:Array.from(app.childNodes),state:{...state},view:document.body.dataset.rehabView,x:window.scrollX,y:window.scrollY,focus:document.activeElement,navHidden:$('.bottom-nav').hidden,healthDraft,healthPrivate,healthData,historyKey:++visitNumber};
    RehabHistoryV52.pushState({rehabAi52:visit.historyKey},'',location.href);
    healthDraft=RehabV52.question(context);state.tab='assistant';state.job=null;document.body.dataset.rehabView='ai';$('.bottom-nav').hidden=true;
    window.scrollTo(0,0);loadAI();
  }
  // Reuse the existing chat renderer and writer, including its privacy checkbox and submit lock.
  healthPage=function(){return visit?loadAI():originalHealthPage();};
  function attach(target,context){
    if(!target)return;const button=document.createElement('button');button.type='button';button.className='rv-ask-ai';button.textContent='问 AI';button.setAttribute('aria-label','问 AI：'+(context.metric||'动作介绍'));button.onclick=()=>openAI(context);target.classList.add('rv-ai-anchor');target.append(button);
  }
  const originalDetail=actionDetailV51;
  actionDetailV51=function(){originalDetail();const ex=selected();attach($('.rv-intro h2'),RehabV52.context('action',ex.id,ex.label));};
  const originalResult=renderJob;
  renderJob=function(j){
    originalResult(j);if(!state.shared||j.state!=='done'||!['assessment','training',undefined].includes(j.mode)||!j.result)return;
    const page=j.mode==='training'?'training':'assessment',card=$('#job-content>.card'),name=label(j.exercise);
    attach(card?.querySelector('h2'),RehabV52.context(page,j.exercise,name,'结果概览'));
    card?.querySelectorAll('.stat').forEach((stat,i)=>{if(i===2||(page==='training'&&i===0))attach(stat.querySelector(':scope > small'),RehabV52.context(page,j.exercise,name,i===2?'视频角度变化':'完整动作'));});
  };
}
