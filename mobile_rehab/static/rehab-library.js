/* Unified browsing; explicit fitness links reuse the existing analysis contracts. */
(function(root){
  'use strict';
  const E=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const plain=v=>String(v??'').replace(/<a\b[^>]*><\/a>/g,'').replace(/\*\*/g,'');
  const base='/static/assets/rehab-library-v1/';
  // Deliberate aliases/artwork, never inferred measurement bindings for 185 cards.
  const fitness = Object.freeze({
    fitness_squat:{category:'knee',aliases:['杠铃深蹲','杠铃背蹲','背蹲','徒手深蹲','squat'],art:'T-LOW-020'},
    fitness_deadlift:{category:'hip',aliases:['杠铃硬拉','常规硬拉','deadlift'],art:'T-LOW-060'},
    fitness_bench_press:{category:'shoulder',aliases:['杠铃卧推','平板卧推','bench press']},
    fitness_row:{category:'shoulder',aliases:['杠铃划船','俯身杠铃划船','划船','barbell row']},
    fitness_overhead_press:{category:'shoulder',aliases:['推举','过头推举','肩推','overhead press'],art:'T-AXU-030'},
    fitness_curl:{category:'elbow_forearm',aliases:['弯举','肱二头肌弯举','二头肌弯举','curl']},
    fitness_pushup:{category:'shoulder',aliases:['俯卧撑','push up','pushup']},
    fitness_split_squat:{category:'knee',aliases:['分腿深蹲','split squat'],art:'T-LOW-021'}
  });
  const cardLinks=Object.freeze({'T-LOW-020':'fitness_squat','T-LOW-060':'fitness_deadlift'});
  const cardAliases=Object.freeze({'T-LOW-020':['杠铃深蹲','深蹲','背蹲'],'T-LOW-060':['杠铃硬拉','常规硬拉']});
  const normalize=v=>String(v??'').normalize('NFKC').toLowerCase().replace(/[\s·/（）()_-]+/g,'');
  let data=null, pending=null;
  function validate(value){
    if(value?.version!=='public-action-library-1'||value.measurement_bindings!==false||value.actions?.length!==185||Object.keys(value.images||{}).length!==656)throw Error('动作资料不完整');
    const ids=new Set();
    for(const card of value.actions){
      if(!/^[ET]-[A-Z]+-\d{3}$/.test(card.id)||ids.has(card.id)||!card.name||!card.introduction||!Array.isArray(card.steps))throw Error('动作资料无效');
      ids.add(card.id);
      for(const slot of [card.overview,...card.steps]){
        const image=value.images[slot];
        if(!image||image.action_id!==card.id||!/^\/static\/assets\/rehab-library-v1\/\d{3}_[ET]-[A-Z]+-\d{3}_(overview|s\d{2})\.webp$/.test(image.url))throw Error('动作图片不匹配');
      }
    }
    return value;
  }
  async function load(){
    if(data)return data;
    if(!pending)pending=root.fetch(base+'catalogue.json').then(r=>{if(!r.ok)throw Error('动作资料暂未读取');return r.json();}).then(validate).then(v=>(data=v)).catch(e=>{pending=null;throw e;});
    return pending;
  }
  function fitnessEntries(value,catalog=[]){
    const seen=new Set();
    return catalog.filter(ex=>fitness[ex.id]&&ex.available!==false&&!seen.has(ex.id)&&seen.add(ex.id)).map(ex=>{
      const meta=fitness[ex.id],art=value.actions.find(a=>a.id===meta.art);
      return {id:ex.id,name:ex.label,kind:'fitness',category:meta.category,region:ex.group,aliases:meta.aliases,overview:art?.overview};
    });
  }
  function fitnessTarget(cardId,catalog=[]){
    const id=cardLinks[cardId];return catalog.some(ex=>ex.id===id&&ex.available!==false)?id:null;
  }
  function filtered(value,kind,category,query,catalog=[]){
    const q=normalize(query);
    return [...fitnessEntries(value,catalog),...value.actions].filter(a=>(kind==='all'||a.kind===kind)&&(category==='all'||a.category===category)&&(!q||[a.name,a.id,a.region,...(a.aliases||cardAliases[a.id]||[])].some(text=>normalize(text).includes(q))));
  }
  function image(slot,cls=''){
    const item=data?.images[slot];if(!item)return '';
    return `<img class="${cls}" src="${E(item.url)}" alt="${E(item.description||'动作概览')}" loading="lazy" decoding="async">`;
  }
  root.RehabLibrary={load,validate,filtered,plain,fitnessEntries,fitnessTarget};
  if(typeof module!=='undefined')module.exports=root.RehabLibrary;
  if(!root.document||typeof actionLibrary!=='function')return;
  const originalLibrary=actionLibrary;
  let kind='all',category='all',query='',limit=30,visit=0;
  function frame(view){document.body.dataset.rehabView=view;document.querySelector('.bottom-nav').hidden=true;}
  function field(title,text){return text?`<section class="card rl-field"><h2>${E(title)}</h2><p>${E(plain(text))}</p></section>`:'';}
  function openFitness(id){
    if(!fitnessEntries(data,state.fitnessCatalog).some(ex=>ex.id===id)){toast('该动作暂未加载，请刷新动作库');return;}
    const browsing={kind,category,query,limit};
    navigate('fitness');++visit;({kind,category,query,limit}=browsing);state.selected=id;state.detail=true;fitnessPage();window.scrollTo(0,0);
  }
  function returnLibrary(){
    clearFile();state.tab='assess';state.detail=false;state.preparing=false;state.rehabEntry='library';syncNavigation();showLibrary();window.scrollTo(0,0);
  }
  function showCard(id){
    const card=data.actions.find(a=>a.id===id);if(!card)return;
    ++visit;
    app.innerHTML=`<div class="rl-public"><header class="rv-page-top"><button class="back" id="rl-back" aria-label="返回动作库">‹</button><h1>动作详情</h1></header><figure class="rl-overview">${image(card.overview)}</figure><div class="rl-name"><h2>${E(card.name)}</h2><p>${E(card.region)} · ${E(card.kind==='assessment'?'评估':'训练')}</p></div>${field('动作介绍',card.introduction)}${field('准备',card.preparation)}${field('怎么做',card.instructions)}${field('动作要领',card.key_points)}<section class="card"><h2>动作图解</h2><p class="caption rl-sequence">${E(plain(card.sequence_reuse))}</p><div class="rl-steps">${card.steps.map(slot=>{const im=data.images[slot];return `<figure><button type="button" data-rl-image="${E(slot)}" aria-label="放大动作图片">${image(slot)}</button><figcaption>${im.group_id!=='base'?`<strong>${E(im.group_label)}</strong>`:''}${E(im.description)}</figcaption></figure>`;}).join('')}</div><p class="caption">图解供查看，不作为测量参考。按动作文字和本人的训练计划执行。</p></section><details class="card rl-more"><summary>适用条件与注意事项</summary>${field('器材',card.equipment)}${field('开始条件',card.start_conditions)}${field('停止或调整',card.stop_conditions)}${field('次数与安排',card.source_dose)}${field('常见错误',card.common_errors)}${field('退阶',card.regression)}${field('进阶',card.progression)}${field('拍摄位置',card.camera)}</details><details class="card rl-more"><summary>完整动作资料与出处</summary><p>${E(plain(card.source_content))}</p></details><div class="rv-detail-foot"><button class="primary" id="rl-assess">选择评估动作</button><button class="secondary" id="rl-plan">我的计划</button></div></div>`;
    frame('detail');
    document.getElementById('rl-back').onclick=showLibrary;
    document.getElementById('rl-assess').onclick=()=>{++visit;state.rehabEntry='assessment';state.detail=false;state.preparing=false;state.search='';state.joint='all';state.viewFilter='all';originalLibrary('assessment');frameRehabV51('library');window.scrollTo(0,0);};
    document.getElementById('rl-plan').onclick=()=>{++visit;navigate('plan');};
    const target=fitnessTarget(id,state.fitnessCatalog);
    if(target){const button=document.createElement('button');button.type='button';button.id='rl-analyse';button.className='primary rl-analyse';button.textContent='拍摄 / 上传分析';button.onclick=()=>openFitness(target);app.querySelector('.rv-detail-foot').before(button);}
    app.querySelectorAll('[data-rl-image]').forEach(b=>b.onclick=()=>{
      const dialog=document.createElement('dialog');dialog.className='rl-dialog';dialog.innerHTML=`<button type="button" aria-label="关闭图片">关闭</button>${image(b.dataset.rlImage)}`;
      document.body.append(dialog);dialog.querySelector('button').onclick=()=>dialog.close();dialog.onclose=()=>{dialog.remove();b.focus();};dialog.showModal();
    });
    window.scrollTo(0,0);
  }
  function showLibrary(){
    const current=++visit,ownerGeneration=state.uploadOwnerGeneration||0;
    app.innerHTML='<div class="rl-public" data-rl-loading><header class="rv-page-top"><button class="back" id="rl-home" aria-label="返回康复">‹</button><h1>动作库</h1></header><p role="status">正在读取动作图文…</p></div>';
    document.getElementById('rl-home').onclick=returnRehabV51;frame('library');
    const draw=value=>{
      if(current!==visit||ownerGeneration!==(state.uploadOwnerGeneration||0)||!app.querySelector('[data-rl-loading]')||!['assess','fitness'].includes(state.tab)||state.training||state.preparing||state.job)return;
      const entries=fitnessEntries(value,state.fitnessCatalog),kinds=[['all','全部'],['assessment','评估'],['training','训练'],...(entries.length?[['fitness','健身']]:[])];
      if(kind==='fitness'&&!entries.length)kind='all';
      app.innerHTML=`<div class="rl-public"><header class="rv-page-top"><button class="back" id="rl-home" aria-label="返回康复">‹</button><h1>动作库</h1><span class="caption">${value.actions.length+entries.length} 个动作</span></header><div class="rl-kinds" aria-label="动作类型">${kinds.map(([id,name])=>`<button data-rl-kind="${id}" aria-pressed="${kind===id}">${name}</button>`).join('')}</div><div class="library-toolbar"><label class="search-field"><span class="sr-only">搜索动作</span><input type="search" id="rl-search" placeholder="搜索动作或部位" value="${E(query)}"></label></div><div class="action-library"><aside class="body-categories" aria-label="身体部位">${[['all','全部部位'],...Object.entries(value.categories)].map(([id,name])=>`<button data-rl-category="${E(id)}" class="${category===id?'selected':''}" aria-pressed="${category===id}">${E(name)}</button>`).join('')}</aside><section><p id="rl-count" class="caption" role="status"></p><div class="action-list" id="rl-list"></div><button class="secondary rl-load-more" id="rl-more">查看更多动作</button></section></div></div>`;
      document.getElementById('rl-home').onclick=returnRehabV51;
      function rows(){
        const items=filtered(value,kind,category,query,state.fitnessCatalog);
        document.getElementById('rl-count').textContent=items.length+' 个动作';
        document.getElementById('rl-list').innerHTML=items.slice(0,limit).map(a=>`<button class="action-row" data-rl-card="${E(a.id)}"><span class="rv-thumb rl-thumb-art">${a.overview?image(a.overview):`<span class="rl-fitness-symbol" aria-hidden="true">${root.RehabV51?.art('extras')||E(a.name)}</span>`}</span><span><strong>${E(a.name)}</strong><small>${a.kind==='fitness'?'健身分析':a.kind==='assessment'?'评估':'训练'} · ${E(a.region)}</small></span></button>`).join('')||'<p class="library-empty">没有找到这个动作，试试其他名称。</p>';
        document.getElementById('rl-more').hidden=items.length<=limit;
        app.querySelectorAll('[data-rl-card]').forEach(b=>b.onclick=()=>fitness[b.dataset.rlCard]?openFitness(b.dataset.rlCard):showCard(b.dataset.rlCard));
      }
      app.querySelectorAll('[data-rl-kind]').forEach(b=>b.onclick=()=>{kind=b.dataset.rlKind;limit=30;app.querySelectorAll('[data-rl-kind]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));rows();});
      app.querySelectorAll('[data-rl-category]').forEach(b=>b.onclick=()=>{category=b.dataset.rlCategory;limit=30;app.querySelectorAll('[data-rl-category]').forEach(x=>{x.classList.toggle('selected',x===b);x.setAttribute('aria-pressed',String(x===b));});rows();});
      document.getElementById('rl-search').oninput=e=>{query=e.target.value;limit=30;rows();};
      document.getElementById('rl-more').onclick=()=>{limit+=30;rows();};rows();
    };
    load().then(draw).catch(()=>{
      if(current!==visit||ownerGeneration!==(state.uploadOwnerGeneration||0)||!app.querySelector('[data-rl-loading]'))return;
      const box=app.querySelector('[data-rl-loading]');box.querySelector('[role="status"]').textContent='动作图文暂未读取，请重试。';
      const retry=document.createElement('button');retry.className='secondary';retry.textContent='重新读取';retry.onclick=showLibrary;box.append(retry);
      const fallback=document.createElement('button');fallback.className='secondary';fallback.textContent='前往评估';fallback.onclick=()=>{state.rehabEntry='assessment';originalLibrary('assessment');frameRehabV51('library');};box.append(fallback);
      if((state.fitnessCatalog||[]).some(ex=>fitness[ex.id]&&ex.available!==false)){const direct=document.createElement('button');direct.className='secondary';direct.textContent='前往健身分析';direct.onclick=()=>{++visit;originalLibrary('fitness');};box.append(direct);}
    });
  }
  actionLibrary=function(mode){
    const q=new URLSearchParams(location.search);
    if(mode==='fitness'&&state.shared&&!state.training&&!state.preparing&&!state.job){kind='fitness';category='all';query='';showLibrary();return;}
    if(mode!=='fitness'&&state.shared&&!state.training&&!state.preparing&&!state.job&&q.get('guide')!=='1'&&(state.rehabEntry||q.get('entry'))==='library'){showLibrary();return;}
    ++visit;return originalLibrary(mode);
  };
  const originalFitnessPage=fitnessPage;
  fitnessPage=function(){
    originalFitnessPage();if(!state.shared||!state.detail||state.tab!=='fitness'||state.job)return;
    const back=document.getElementById('fitness-library-back');if(!back)return;
    back.onclick=returnLibrary;
    const entry=data&&fitnessEntries(data,state.fitnessCatalog).find(ex=>ex.id===state.selected);
    if(entry?.overview){const cover=document.createElement('figure');cover.className='rl-overview rl-fitness-cover';cover.innerHTML=image(entry.overview);app.querySelector('.fitness-guidance')?.before(cover);}
    frame('detail');
  };
  document.addEventListener('error',event=>{
    const img=event.target;if(img?.tagName!=='IMG'||!img.getAttribute('src')?.startsWith(base))return;
    img.hidden=true;const note=document.createElement('span');note.className='rl-image-error';note.textContent='图片暂不可用，请查看动作文字';img.after(note);
  },true);
})(typeof window==='undefined'?globalThis:window);
