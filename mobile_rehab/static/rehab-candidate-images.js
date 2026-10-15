/* Internal preview only. These pictures never enter clinical guides or calculations. */
(function(root){
  'use strict';
  const escape=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let index=null,mappings=null,error='';
  function enabled(){
    return root.__ANKANG_INTERNAL_IMAGE_PREVIEW__===true &&
      ['127.0.0.1','localhost','[::1]'].includes(root.location?.hostname) &&
      new URLSearchParams(root.location.search).get('rehabImagePreview')==='1';
  }
  function candidates(id){
    if(!enabled()||!index||!mappings)return [];
    return (mappings[id]?.candidate_images||[]).map(binding=>({binding,image:index.images[binding.slot_id]}))
      .filter(({binding,image})=>image&&image.action_id===binding.public_action_id&&
        /^\/static\/assets\/rehab-candidates-v10\/[A-Za-z0-9_-]+\.webp$/.test(image.url));
  }
  function status(){return !enabled()?'':error?'候选素材加载失败，继续使用原文字说明。':!index?'候选素材正在读取…':'内部候选预览 · 待审核，不作为跟练指导';}
  function imageTag(image,cls=''){
    return `<img class="${cls}" src="${escape(image.url)}" alt="${escape(image.action_name)} · 待审核素材" loading="lazy" decoding="async">`;
  }
  function thumb(id){
    const first=candidates(id)[0];if(!first||mappings[id].preview_scope==='resource_library_only')return '';
    return `<span class="rv-thumb rv-candidate-thumb">${imageTag(first.image)}<small>待审核</small></span>`;
  }
  function picture(id,large){
    const first=candidates(id)[0];if(!first||mappings[id].preview_scope==='resource_library_only')return '';
    return `<figure class="rv-photo ${large?'rv-photo-large':''} rv-candidate-photo">${imageTag(first.image)}<figcaption>待审核 · 侧别、阶段未确认</figcaption></figure>`;
  }
  function gallery(id){
    const rows=candidates(id);if(!rows.length)return '';
    const entry=mappings[id];
    return `<section class="rv-candidate-materials"><details><summary>待审核素材（${rows.length}张）</summary><p>${entry.preview_scope==='resource_library_only'?'存在明确映射冲突，仅作资源审阅。':''}不作为准确动作步骤或患者教学依据。本人侧别、动作阶段和适用条件须独立核验。</p><details class="rv-candidate-issues"><summary>映射限制</summary>${entry.issues.map(t=>`<p>${escape(t)}</p>`).join('')}</details>${rows.map(({binding,image})=>{
      const confirmed=binding.review_status==='approved'&&['left','right'].includes(binding.side)&&['start','move','return'].includes(binding.phase);
      const label=confirmed?`${binding.side==='left'?'本人左侧':'本人右侧'} · ${({start:'准备',move:'动作',return:'回位'})[binding.phase]}`:'侧别、阶段未确认';
      return `<figure><button type="button" data-candidate-open="${escape(image.slot_id)}" aria-label="放大 ${escape(image.slot_id)} 待审核图片">${imageTag(image)}</button><figcaption><strong>${escape(label)} · 待审核</strong><span>${escape(image.slot_id)} · ${escape(image.group_id||'overview')}</span><span>${escape(image.frame_description||'公共卡概览，非动作起点')}</span></figcaption></figure>`;
    }).join('')}</details></section>`;
  }
  async function load(){
    if(!enabled())return false;
    try{
      const responses=await Promise.all(['resource-index.json','exercise-mapping.json'].map(n=>root.fetch('/static/assets/rehab-candidates-v10/'+n)));
      if(responses.some(r=>!r.ok))throw Error('resource unavailable');
      [index,mappings]=await Promise.all(responses.map(r=>r.json()));
      if(index.schema_version!==1||index.public_actions.length!==185||Object.keys(index.images).length!==656)throw Error('invalid index');
      error='';return true;
    }catch(e){index=null;mappings=null;error='unavailable';return false;}
    finally{root.document?.dispatchEvent(new Event('rehab-candidate-images-ready'));}
  }
  root.RehabCandidateImages={enabled,candidates,thumb,picture,gallery,status,load,getIndex:()=>index,getMappings:()=>mappings};
  if(typeof module!=='undefined')module.exports=root.RehabCandidateImages;
  if(root.document){
    root.document.addEventListener('error',e=>{
      const img=e.target;if(img?.tagName!=='IMG'||!img.src?.includes('/rehab-candidates-v10/'))return;
      const holder=img.closest('figure,.rv-candidate-thumb');if(!holder)return;
      img.hidden=true;const note=root.document.createElement('p');note.className='rv-candidate-failed';note.textContent='图片暂不可用，请查看原文字说明。';holder.append(note);
    },true);
    root.document.addEventListener('click',e=>{
      const trigger=e.target.closest?.('[data-candidate-open]');if(!trigger||!enabled())return;
      const image=index?.images[trigger.dataset.candidateOpen];if(!image)return;
      const dialog=root.document.createElement('dialog');dialog.className='rv-candidate-dialog';
      dialog.innerHTML=`<button type="button" aria-label="关闭图片">关闭</button>${imageTag(image)}<p>${escape(image.slot_id)} · 待审核，不作为示教</p>`;
      root.document.body.append(dialog);dialog.querySelector('button').onclick=()=>dialog.close();
      dialog.onclose=()=>{dialog.remove();trigger.focus();};dialog.showModal();
    });
    load();
  }
})(typeof window==='undefined'?globalThis:window);
