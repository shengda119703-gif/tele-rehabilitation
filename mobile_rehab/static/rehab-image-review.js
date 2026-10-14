/* Read-only resource inspector, not a new task/exercise catalogue. */
'use strict';
(function(){
  let scope='candidates';const P=window.RehabCandidateImages,E=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const grid=document.querySelector('#grid'),status=document.querySelector('#status');
  function render(){
    if(!P.enabled()){status.textContent='预览未开启。仅隔离本地 TEST 服务可启用。';return;}
    const index=P.getIndex(),mappings=P.getMappings();if(!index){status.textContent=P.status();return;}
    status.textContent='185张公共卡 · 656张选用图片 · 全部待审核；不作为患者教学依据。';
    const query=document.querySelector('#search').value.trim().toLowerCase();
    const rows=scope==='public'?index.public_actions.map(a=>({id:a.action_id,name:a.name,slots:a.image_slots,card:a.card_path})):Object.values(mappings).filter(m=>m.candidate_images.length).map(m=>({id:m.exercise_id,name:m.label,slots:m.candidate_images.map(i=>i.slot_id),restricted:m.preview_scope==='resource_library_only'}));
    grid.className='grid';grid.innerHTML=rows.filter(r=>(r.name+r.id).toLowerCase().includes(query)).map(r=>{const image=index.images[r.slots.find(s=>index.images[s].role==='overview')||r.slots[0]];return `<article class="tile"><button data-review-id="${E(r.id)}"><img src="${E(image.url)}" alt="${E(r.name)} 待审核候选" loading="lazy" decoding="async"><strong>${E(r.name)}</strong><small>${E(r.id)} · ${r.restricted?'冲突待审，仅资源库':'待审核'}</small><span>${r.slots.length} 张图片</span></button></article>`;}).join('');
    grid.querySelectorAll('[data-review-id]').forEach(b=>b.onclick=()=>{const row=rows.find(r=>r.id===b.dataset.reviewId);grid.className='detail';grid.innerHTML=`<button id="back">返回列表</button>${row.slots.map(s=>{const i=index.images[s];return `<figure><button data-candidate-open="${E(s)}"><img src="${E(i.url)}" alt="${E(row.name)} 待审核" loading="lazy"></button><figcaption>${E(row.name)} · ${E(s)}<br>${E(i.group_id||'overview')} · 侧别、阶段未确认 · 待审核<br>${E(i.frame_description||'概览，非动作起点')}</figcaption></figure>`;}).join('')}`;document.querySelector('#back').onclick=render;window.scrollTo(0,0);});
  }
  document.addEventListener('rehab-candidate-images-ready',render);
  for(const name of ['candidates','public'])document.querySelector('#'+name).onclick=()=>{scope=name;document.querySelectorAll('nav button').forEach(b=>b.setAttribute('aria-pressed',String(b.id===name)));render();};
  document.querySelector('#search').oninput=render;render();
})();
