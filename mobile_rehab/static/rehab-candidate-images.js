/* Catalogue pictures stay separate from clinical guides and calculations. */
(function(root){
  'use strict';
  const escape=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let index=null,mappings=null,catalog=null,error='';
  function enabled(){
    return root.__ANKANG_INTERNAL_IMAGE_PREVIEW__===true &&
      ['127.0.0.1','localhost','[::1]'].includes(root.location?.hostname) &&
      new URLSearchParams(root.location.search).get('rehabImagePreview')==='1';
  }
  function candidates(id){
    if(!index||!mappings||(!enabled()&&!catalog?.covers[id]))return [];
    return (mappings[id]?.candidate_images||[]).map(binding=>({binding,image:index.images[binding.slot_id]}))
      .filter(({binding,image})=>image&&image.action_id===binding.public_action_id&&
        /^\/static\/assets\/rehab-candidates-v10\/[A-Za-z0-9_-]+\.webp$/.test(image.url));
  }
  function status(){return error?'配图加载失败，继续使用原文字说明。':!index?'配图正在读取…':'配图待审核，动作文字与机位以现有说明为准。';}
  function imageTag(image,cls=''){
    return `<img class="${cls}" src="${escape(image.url)}" alt="${escape(image.action_name)} · 待审核素材" width="${image.display_width}" height="${image.display_height}" loading="lazy" decoding="async" draggable="false">`;
  }
  function thumb(id){
    const rows=candidates(id),first=rows.find(r=>r.image.slot_id===catalog?.covers[id])||rows[0];if(!first||mappings[id].preview_scope==='resource_library_only')return '';
    return `<span class="rv-thumb rv-candidate-thumb">${imageTag(first.image)}<small>待审核</small></span>`;
  }
  function picture(id,large){
    const rows=candidates(id);if(!rows.length||mappings[id].preview_scope==='resource_library_only')return '';
    const current=Math.max(0,rows.findIndex(r=>r.image.slot_id===catalog?.covers[id]));
    return `<section class="rv-photo ${large?'rv-photo-large':''} rv-candidate-photo rv-carousel" data-photo-start="${current}" role="region" aria-label="动作配图" aria-roledescription="轮播图"><div class="rv-carousel-track" tabindex="0" aria-label="左右滑动查看动作配图">${rows.map(({image},i)=>`<figure class="rv-carousel-slide" role="group" aria-label="图片 ${i+1} / ${rows.length}"><button type="button" data-candidate-open="${escape(image.slot_id)}" aria-label="放大图片 ${i+1}">${imageTag(image)}</button></figure>`).join('')}</div><div class="rv-carousel-controls"><button type="button" data-photo-prev aria-label="上一张图片" ${current===0?'disabled':''}>‹</button><output aria-live="polite">${current+1} / ${rows.length}</output><button type="button" data-photo-next aria-label="下一张图片" ${current===rows.length-1?'disabled':''}>›</button><span>配图待审核</span></div></section>`;
  }
  function mount(scope=root.document){
    scope.querySelectorAll('.rv-carousel').forEach(box=>{
      const track=box.querySelector('.rv-carousel-track'),slides=Array.from(track.children);
      const previous=box.querySelector('[data-photo-prev]'),next=box.querySelector('[data-photo-next]'),counter=box.querySelector('output');
      let current=Number(box.dataset.photoStart)||0;
      const update=()=>{
        current=Math.max(0,Math.min(slides.length-1,Math.round(track.scrollLeft/Math.max(1,track.clientWidth))));
        const label=`${current+1} / ${slides.length}`;if(counter.textContent!==label)counter.textContent=label;
        previous.disabled=current===0;next.disabled=current===slides.length-1;
        slides.forEach((slide,i)=>slide.querySelector('button').tabIndex=i===current?0:-1);
      };
      const go=i=>track.scrollTo({left:Math.max(0,Math.min(slides.length-1,i))*track.clientWidth,behavior:root.matchMedia?.('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});
      track.addEventListener('scroll',update,{passive:true});
      previous.onclick=()=>go(current-1);next.onclick=()=>go(current+1);
      track.onkeydown=e=>{
        if(e.target!==track||!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;
        e.preventDefault();go(e.key==='Home'?0:e.key==='End'?slides.length-1:current+(e.key==='ArrowRight'?1:-1));
      };
      track.scrollLeft=current*track.clientWidth;update();
    });
  }
  async function load(){
    try{
      const responses=await Promise.all(['resource-index.json','exercise-mapping.json','catalog-display.json'].map(n=>root.fetch('/static/assets/rehab-candidates-v10/'+n)));
      if(responses.some(r=>!r.ok))throw Error('resource unavailable');
      [index,mappings,catalog]=await Promise.all(responses.map(r=>r.json()));
      if(index.schema_version!==1||index.public_actions.length!==185||Object.keys(index.images).length!==656||catalog.schema_version!==1)throw Error('invalid index');
      for(const [id,slot] of Object.entries(catalog.covers)){
        if(mappings[id]?.preview_scope!=='internal_candidate'||!mappings[id].candidate_images.some(b=>b.slot_id===slot&&b.public_action_id===index.images[slot]?.action_id))throw Error('invalid catalogue cover');
      }
      error='';return true;
    }catch(e){index=null;mappings=null;catalog=null;error='unavailable';return false;}
    finally{root.document?.dispatchEvent(new Event('rehab-candidate-images-ready'));}
  }
  root.RehabCandidateImages={enabled,candidates,thumb,picture,mount,status,load,getIndex:()=>index,getMappings:()=>mappings};
  if(typeof module!=='undefined')module.exports=root.RehabCandidateImages;
  if(root.document){
    root.document.addEventListener('error',e=>{
      const img=e.target;if(img?.tagName!=='IMG'||!img.src?.includes('/rehab-candidates-v10/'))return;
      const holder=img.closest('figure,.rv-candidate-thumb');if(!holder)return;
      img.hidden=true;const note=root.document.createElement('p');note.className='rv-candidate-failed';note.textContent='图片暂不可用，请查看原文字说明。';holder.append(note);
    },true);
    root.document.addEventListener('click',e=>{
      const trigger=e.target.closest?.('[data-candidate-open]');if(!trigger)return;
      const image=index?.images[trigger.dataset.candidateOpen];if(!image)return;
      const dialog=root.document.createElement('dialog');dialog.className='rv-candidate-dialog';
      dialog.innerHTML=`<button type="button" aria-label="关闭图片">关闭</button>${imageTag(image)}<p>${escape(image.slot_id)} · 待审核，不作为示教</p>`;
      root.document.body.append(dialog);dialog.querySelector('button').onclick=()=>dialog.close();
      dialog.onclose=()=>{dialog.remove();trigger.focus();};dialog.showModal();
    });
    load();
  }
})(typeof window==='undefined'?globalThis:window);
