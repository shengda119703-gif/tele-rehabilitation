/* Public action cards: read-only browsing, independent of measurement state. */
(function(root){
  'use strict';
  const E=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const plain=v=>String(v??'').replace(/<a\b[^>]*><\/a>/g,'').replace(/\*\*/g,'');
  const base='/static/assets/rehab-library-v1/';
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
  function filtered(value,kind,category,query){
    const q=query.trim().toLowerCase();
    return value.actions.filter(a=>(kind==='all'||a.kind===kind)&&(category==='all'||a.category===category)&&(!q||(a.name+' '+a.id+' '+a.region).toLowerCase().includes(q)));
  }
  function image(slot,cls=''){
    const item=data?.images[slot];if(!item)return '';
    return `<img class="${cls}" src="${E(item.url)}" alt="${E(item.description||'动作概览')}" loading="lazy" decoding="async">`;
  }
  root.RehabLibrary={load,validate,filtered,plain};
  if(typeof module!=='undefined')module.exports=root.RehabLibrary;
  if(!root.document||typeof actionLibrary!=='function')return;
  const originalLibrary=actionLibrary;
  let kind='all',category='all',query='',limit=30,visit=0;
  function frame(view){document.body.dataset.rehabView=view;document.querySelector('.bottom-nav').hidden=true;}
  function field(title,text){return text?`<section class="card rl-field"><h2>${E(title)}</h2><p>${E(plain(text))}</p></section>`:'';}
  function showCard(id){
    const card=data.actions.find(a=>a.id===id);if(!card)return;
    ++visit;
    app.innerHTML=`<div class="rl-public"><header class="rv-page-top"><button class="back" id="rl-back" aria-label="返回动作库">‹</button><h1>动作详情</h1></header><figure class="rl-overview">${image(card.overview)}</figure><div class="rl-name"><h2>${E(card.name)}</h2><p>${E(card.region)} · ${E(card.kind==='assessment'?'评估':'训练')}</p></div>${field('动作介绍',card.introduction)}${field('准备',card.preparation)}${field('怎么做',card.instructions)}${field('动作要领',card.key_points)}<section class="card"><h2>动作图解</h2><p class="caption rl-sequence">${E(plain(card.sequence_reuse))}</p><div class="rl-steps">${card.steps.map(slot=>{const im=data.images[slot];return `<figure><button type="button" data-rl-image="${E(slot)}" aria-label="放大动作图片">${image(slot)}</button><figcaption>${im.group_id!=='base'?`<strong>${E(im.group_label)}</strong>`:''}${E(im.description)}</figcaption></figure>`;}).join('')}</div><p class="caption">图解供查看，不作为测量参考。按动作文字和本人的训练计划执行。</p></section><details class="card rl-more"><summary>适用条件与注意事项</summary>${field('器材',card.equipment)}${field('开始条件',card.start_conditions)}${field('停止或调整',card.stop_conditions)}${field('次数与安排',card.source_dose)}${field('常见错误',card.common_errors)}${field('退阶',card.regression)}${field('进阶',card.progression)}${field('拍摄位置',card.camera)}</details><details class="card rl-more"><summary>完整动作资料与出处</summary><p>${E(plain(card.source_content))}</p></details><div class="rv-detail-foot"><button class="primary" id="rl-assess">选择评估动作</button><button class="secondary" id="rl-plan">我的计划</button></div></div>`;
    frame('detail');
    document.getElementById('rl-back').onclick=showLibrary;
    document.getElementById('rl-assess').onclick=()=>{++visit;state.rehabEntry='assessment';state.detail=false;state.preparing=false;state.search='';state.joint='all';state.viewFilter='all';originalLibrary('assessment');frameRehabV51('library');window.scrollTo(0,0);};
    document.getElementById('rl-plan').onclick=()=>{++visit;navigate('plan');};
    app.querySelectorAll('[data-rl-image]').forEach(b=>b.onclick=()=>{
      const dialog=document.createElement('dialog');dialog.className='rl-dialog';dialog.innerHTML=`<button type="button" aria-label="关闭图片">关闭</button>${image(b.dataset.rlImage)}`;
      document.body.append(dialog);dialog.querySelector('button').onclick=()=>dialog.close();dialog.onclose=()=>{dialog.remove();b.focus();};dialog.showModal();
    });
    window.scrollTo(0,0);
  }
  function showLibrary(){
    const current=++visit;
    app.innerHTML='<div class="rl-public" data-rl-loading><header class="rv-page-top"><button class="back" id="rl-home" aria-label="返回康复">‹</button><h1>动作库</h1></header><p role="status">正在读取动作图文…</p></div>';
    document.getElementById('rl-home').onclick=returnRehabV51;frame('library');
    const draw=value=>{
      if(current!==visit||!app.querySelector('[data-rl-loading]')||state.tab!=='assess'||state.training||state.preparing||state.job)return;
      app.innerHTML=`<div class="rl-public"><header class="rv-page-top"><button class="back" id="rl-home" aria-label="返回康复">‹</button><h1>动作库</h1><span class="caption">185 个动作</span></header><div class="rl-kinds" aria-label="动作类型">${[['all','全部'],['assessment','评估'],['training','训练']].map(([id,name])=>`<button data-rl-kind="${id}" aria-pressed="${kind===id}">${name}</button>`).join('')}</div><div class="library-toolbar"><label class="search-field"><span class="sr-only">搜索动作</span><input type="search" id="rl-search" placeholder="搜索动作或部位" value="${E(query)}"></label></div><div class="action-library"><aside class="body-categories" aria-label="身体部位">${[['all','全部部位'],...Object.entries(value.categories)].map(([id,name])=>`<button data-rl-category="${E(id)}" class="${category===id?'selected':''}" aria-pressed="${category===id}">${E(name)}</button>`).join('')}</aside><section><p id="rl-count" class="caption" role="status"></p><div class="action-list" id="rl-list"></div><button class="secondary rl-load-more" id="rl-more">查看更多动作</button></section></div></div>`;
      document.getElementById('rl-home').onclick=returnRehabV51;
      function rows(){
        const items=filtered(value,kind,category,query);
        document.getElementById('rl-count').textContent=items.length+' 个动作';
        document.getElementById('rl-list').innerHTML=items.slice(0,limit).map(a=>`<button class="action-row" data-rl-card="${E(a.id)}"><span class="rv-thumb rl-thumb-art">${image(a.overview)}</span><span><strong>${E(a.name)}</strong><small>${a.kind==='assessment'?'评估':'训练'} · ${E(a.region)}</small></span></button>`).join('')||'<p class="library-empty">没有找到这个动作，试试其他名称。</p>';
        document.getElementById('rl-more').hidden=items.length<=limit;
        app.querySelectorAll('[data-rl-card]').forEach(b=>b.onclick=()=>showCard(b.dataset.rlCard));
      }
      app.querySelectorAll('[data-rl-kind]').forEach(b=>b.onclick=()=>{kind=b.dataset.rlKind;limit=30;app.querySelectorAll('[data-rl-kind]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));rows();});
      app.querySelectorAll('[data-rl-category]').forEach(b=>b.onclick=()=>{category=b.dataset.rlCategory;limit=30;app.querySelectorAll('[data-rl-category]').forEach(x=>{x.classList.toggle('selected',x===b);x.setAttribute('aria-pressed',String(x===b));});rows();});
      document.getElementById('rl-search').oninput=e=>{query=e.target.value;limit=30;rows();};
      document.getElementById('rl-more').onclick=()=>{limit+=30;rows();};rows();
    };
    load().then(draw).catch(()=>{
      if(current!==visit||!app.querySelector('[data-rl-loading]'))return;
      const box=app.querySelector('[data-rl-loading]');box.querySelector('[role="status"]').textContent='动作图文暂未读取，请重试。';
      const retry=document.createElement('button');retry.className='secondary';retry.textContent='重新读取';retry.onclick=showLibrary;box.append(retry);
      const fallback=document.createElement('button');fallback.className='secondary';fallback.textContent='前往评估';fallback.onclick=()=>{state.rehabEntry='assessment';originalLibrary('assessment');frameRehabV51('library');};box.append(fallback);
    });
  }
  actionLibrary=function(mode){
    const q=new URLSearchParams(location.search);
    if(mode!=='fitness'&&state.shared&&!state.training&&!state.preparing&&!state.job&&q.get('guide')!=='1'&&(state.rehabEntry||q.get('entry'))==='library'){showLibrary();return;}
    ++visit;return originalLibrary(mode);
  };
  document.addEventListener('error',event=>{
    const img=event.target;if(img?.tagName!=='IMG'||!img.getAttribute('src')?.startsWith(base))return;
    img.hidden=true;const note=document.createElement('span');note.className='rl-image-error';note.textContent='图片暂不可用，请查看动作文字';img.after(note);
  },true);
})(typeof window==='undefined'?globalThis:window);
