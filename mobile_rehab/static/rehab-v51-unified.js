/* Approved rehab overview, over the same authenticated unified readers/writers. */
function renderRehabV51(){
  const V=window.RehabV51,m=window.AnkangHomeV36.model(snapshot(),ui.source,ui.day,today(),ui.homeConnection);
  const capture=(tab,source=ui.source)=>{const ctx=V.context(source,ui.day);return '/capture?tab='+tab+(ctx?'&'+ctx:'');};
  delete document.body.dataset.rehabHistory;
  const browsing=new URLSearchParams(location.search);browsing.set('rehabSource',ui.source);browsing.set('rehabDay',ui.day);window.history?.replaceState(null,'',location.pathname+'?'+browsing.toString()+'#rehab');
  if(ui.source==='LIVE_CAMERA'&&!m.plan&&m.connection==='ready'&&ui.day===today())m.task={...m.task,label:'电脑实时评估',meta:'正式评估在电脑端开始',button:'查看电脑方式',action:'computer'};
  $('#content').innerHTML=`<div class="rehab-v51"><div class="rv-search-row"><a class="rv-search" href="${capture('assess')}&entry=library" aria-label="搜索动作"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10" cy="10" r="6"/><path d="m15 15 5 5"/></svg>搜索动作</a><a class="rv-ai" href="#assistant" aria-label="AI 康复管家">AI<i></i></a></div>${V.weekly(m)}<div class="rv-today"><h1>${ui.day===today()?'今日':'当日'}康复</h1><span>${m.connection!=='ready'?(m.connection==='loading'?'正在核验任务':'任务暂未读取'):m.plan?`本轮 ${m.plan.progress?.completed??0}/${m.plan.progress?.total??m.plan.items.length} 项已完成`:'从一次评估开始'}</span></div>${V.hero(m)}<div class="rv-featured"><button id="rehab-plan"><strong>我的计划</strong><b>→</b><i class="rv-plan-art">${'<i></i>'.repeat(3)}</i></button><a href="${capture('assess')}&entry=library" class="rv-library"><strong>动作库</strong><b>→</b><img src="/static/assets/rehab-v51/flexion.jpg" alt="" aria-hidden="true"></a></div><div class="rv-minor"><h2>其他功能</h2><span class="rv-dots" aria-hidden="true"><i class="current"></i><i></i><i></i></span></div><div class="rv-rail" role="region" tabindex="0" aria-label="其他功能，横向滑动浏览">${V.cards.map(([key,title,sub,tab])=>{const contents=`<strong>${title}</strong><small>${key==='history'?(ui.source==='LIVE_CAMERA'?'电脑实时记录':'录像分析记录'):key==='assessment'?'手机录像分析':sub}</small>${V.art(key)}<b aria-hidden="true">↗</b>`;return key==='history'&&ui.source==='LIVE_CAMERA'?`<button class="rv-feature-card" id="rehab-live-history">${contents}</button>`:`<a class="rv-feature-card" href="${capture(tab,key==='assessment'?'REPLAY_FILE':ui.source)+(key==='assessment'?'&entry=assessment':'')}">${contents}</a>`;}).join('')}</div><div class="rv-context"><span class="rv-owner" title="${E(m.profile.name||'我的档案')}" aria-label="当前档案">${E(m.profile.name||'我的档案')}</span>${sourcePicker()}<button id="rehab-refresh">刷新</button></div>${m.task.notice?`<p class="rv-notice" role="status">${E(m.task.notice)}</p>`:''}<details class="rv-arrangements"><summary>日期安排与全部计划</summary><input type="date" id="day" aria-label="查看康复日期" value="${ui.day}">${m.schedules.map(s=>`<div class="row"><time>${E(s.time)}</time><strong>${E(s.name)}</strong><button data-cancel="${E(s.id)}">取消</button></div>`).join('')||'<p>当天暂无安排。</p>'}${plans().map(p=>`<button data-plan="${E(p.id)}">${E(p.name)} · 版本 ${E(p.revision)}</button>`).join('')}<p>手动编辑及旧版本管理请在电脑端进行。</p></details></div>`;
  bindSource();bind('rehab-refresh',load);bind('rehab-live-history',()=>ui.homeConnection==='ready'?renderLiveHistoryV51():load());
  bind('rehab-plan',()=>ui.source==='LIVE_CAMERA'&&m.plan?planDetail(m.plan):location.assign(capture('plan')));
  bind('rehab-primary',async()=>{
    if(ui.busy)return;
    const source=ui.source,day=ui.day,owner=snapshot().profile?.ownerId,intent=m.task.action,expectedGeneration=ui.generation+1,planId=m.plan?.id,planRevision=m.plan?.revision,nextKey=m.next?.key;
    $('#rehab-primary').disabled=true;
    await load();
    if(ui.page!=='rehab'||ui.source!==source||ui.day!==day||snapshot().profile?.ownerId!==owner||ui.generation!==expectedGeneration)return;
    const now=window.AnkangHomeV36.model(snapshot(),source,day,today(),ui.homeConnection);
    if(now.connection!=='ready'||intent==='retry')return;
    if(now.plan?.id!==planId||now.plan?.revision!==planRevision||now.next?.key!==nextKey){say('任务已更新，请重新选择。');return;}
    if(now.task.action==='plan'){if(source==='LIVE_CAMERA'&&now.plan)planDetail(now.plan);else location.assign(capture('plan'));}
    else if(now.task.action==='train')location.assign(capture('plan'));
    else if(now.task.action==='history')location.assign(capture('history'));
    else if(intent==='computer')location.assign(capture('more&tool=computer'));
    else if(now.task.action==='assess'||!now.plan)location.assign(capture('assess')+'&entry=assessment');
    else {$('#day').focus();$('#day').closest('details').open=true;}
  });
  $('#day').onchange=e=>{if(e.target.value){ui.day=e.target.value;renderRehabV51();}};
  document.querySelectorAll('[data-plan]').forEach(b=>b.onclick=()=>planDetail(plans().find(p=>p.id===b.dataset.plan)));
  document.querySelectorAll('[data-cancel]').forEach(b=>b.onclick=()=>confirmAction('取消这次安排？','训练记录和原计划会保留。',()=>daily('unschedule',{id:b.dataset.cancel})));
  const rail=$('.rv-rail');rail.onscroll=()=>{const max=rail.scrollWidth-rail.clientWidth,index=max>0?Math.min(2,Math.floor(rail.scrollLeft/max*3)):0;document.querySelectorAll('.rv-dots i').forEach((d,i)=>d.classList.toggle('current',i===index));};
}

// The existing desktop reader exposes scoped summaries, not phone video jobs.
function renderLiveHistoryV51(){
  const H=window.AnkangHomeV36, rows=[...H.records(snapshot(),ui.source,'rehab.get_training_history').map(r=>({...r,kind:'training'})),...H.records(snapshot(),ui.source,'rehab.get_recent_assessments').map(r=>({...r,kind:'assessment'}))].sort((a,b)=>new Date(b.end_utc||0)-new Date(a.end_utc||0));
  document.body.dataset.rehabHistory='true';
  $('#content').innerHTML=`<section class="rehab-v51 rv-live-history"><header class="rv-page-top"><button class="back" id="rv-live-history-back" aria-label="返回康复">‹</button><h1>历史记录</h1></header><p class="rv-notice">电脑实时 · 已保存摘要；完整报告请在电脑端查看。</p>${rows.map((r,i)=>`<button class="rv-live-record" data-live-record="${i}"><strong>${E(r.exercise_label||'动作记录')} · ${r.side==='left'?'本人左侧':r.side==='right'?'本人右侧':'侧别未记录'}</strong><span>${stamp(r.end_utc)} · ${r.kind==='training'?'康复训练':'康复评估'}</span><small>${r.kind==='training'?(r.status==='INTERRUPTED'?'已中断':'已结束'):r.status==='ASSESSED'?'有评估依据':'查看依据状态'} ›</small></button>`).join('')||'<p class="empty">当前本人、电脑实时范围暂无记录。</p>'}</section>`;
  bind('rv-live-history-back',renderRehabV51);
  document.querySelectorAll('[data-live-record]').forEach(b=>b.onclick=()=>{
    const r=rows[Number(b.dataset.liveRecord)],s=r.summary||r,count=s.completed;
    modal('已保存记录摘要',`<p>${E(r.exercise_label)} · ${r.side==='left'?'本人左侧':r.side==='right'?'本人右侧':'侧别未记录'}</p><p>${stamp(r.end_utc)} · 电脑实时</p><p>完整动作：${Number.isFinite(count)?count+' 次':'未记录'}</p>${r.kind==='assessment'?`<p>${E(r.status==='ASSESSED'?'有评估依据':r.reason||'没有有效评估依据')}</p><p>${E(r.measurement_note||'请核对原测量条件')}</p>`:`<p>计划次数：${s.plan_completed===true?'已达标':s.plan_completed===false?'未达标':'未记录'}</p><p>${Number.isFinite(r.training_feedback?.pain)?'疼痛 '+E(r.training_feedback.pain)+' / 10':'疼痛未记录'} · ${Number.isFinite(r.training_feedback?.fatigue)?'疲劳 '+E(r.training_feedback.fatigue)+' / 10':'疲劳未记录'}</p>`}<p>只读摘要，完整报告及原始附件请在电脑端查看。</p>`);
  });
}
