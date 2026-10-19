/* V5.1 presentation primitives. No API, clinical calculations or persistent writes. */
(function(root){
  'use strict';
  const escape=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const artwork=Object.freeze({shoulder_flexion:'flexion',shoulder_abduction:'abduction',shoulder_extension:'extension'});
  function picture(id,large=false,candidatePreview=false){
    const cover=root.RehabAssessmentArtwork?.get(id);
    if(cover)return `<figure class="rv-photo rv-assessment-photo ${large?'rv-photo-large':''}"><img src="${escape(cover.url)}" alt="${escape(cover.alt)}" loading="lazy" decoding="async"><figcaption>动作示意</figcaption></figure>`;
    const preview=candidatePreview&&root.RehabCandidateImages?.picture(id,large);if(preview)return preview;
    return artwork[id]?`<figure class="rv-photo ${large?'rv-photo-large':''}"><img src="/static/assets/rehab-v51/${artwork[id]}.jpg" alt="待审核视觉封面" loading="lazy"><figcaption>视觉示例 · 未核验，不作为示教</figcaption></figure>`:`<div class="rv-photo rv-no-photo ${large?'rv-photo-large':''}">动作图片待核验</div>`;
  }
  function thumb(id,candidatePreview=false){const cover=root.RehabAssessmentArtwork?.get(id);if(cover)return `<img class="rv-thumb rv-assessment-thumb" src="${escape(cover.url)}" alt="${escape(cover.alt)}" loading="lazy" decoding="async">`;const preview=candidatePreview&&root.RehabCandidateImages?.thumb(id);if(preview)return preview;return Object.hasOwn(artwork,id)?`<img class="rv-thumb" src="/static/assets/rehab-v51/${artwork[id]}.jpg" alt="未核验视觉封面" loading="lazy">`:'<span class="rv-thumb rv-placeholder" aria-hidden="true">—</span>';}
  function order(items){
    const ids=Object.keys(artwork),rank=id=>ids.includes(id)?ids.indexOf(id):ids.length;
    const pictured=new Set(items.filter(x=>root.RehabAssessmentArtwork?.get(x.id)||artwork[x.id]||root.RehabCandidateImages?.thumb(x.id)).map(x=>x.id));
    return items.slice().sort((a,b)=>Number(pictured.has(b.id))-Number(pictured.has(a.id))||rank(a.id)-rank(b.id));
  }
  function context(source,day){return ['LIVE_CAMERA','REPLAY_FILE'].includes(source)&&/^\d{4}-\d{2}-\d{2}$/.test(day||'')?`rehabSource=${source}&rehabDay=${day}`:'';}
  function hero(m){const t=m.task;
    return `<section class="rv-hero" aria-label="当前康复任务"><svg class="rv-streaks" viewBox="0 0 350 205" preserveAspectRatio="none" aria-hidden="true"><polygon points="185,150 196,128 350,5 350,21 205,139 190,153" class="sport-band"/><path d="M173 206 350 87" class="sport-line"/></svg><img class="rv-athlete" src="/static/assets/home-v36/athlete-cutout.png" alt="" aria-hidden="true"><svg class="rv-streak-front" viewBox="0 0 350 205" preserveAspectRatio="none" aria-hidden="true"><polygon points="240,185 254,169 350,99 350,103 263,169" class="sport-cut"/></svg><div class="rv-task-copy"><span>${escape(t.label)}</span><h2 class="${t.title.length>4?'rv-long':''}">${escape(t.title)}</h2><p>${escape(t.meta)}</p><button id="rehab-primary" ${t.disabled?'disabled':''}>${escape(t.button)} <b aria-hidden="true">→</b></button></div>${t.index?`<small class="rv-task-index">${String(t.index).padStart(2,'0')} / ${String(t.total).padStart(2,'0')}</small>`:''}</section>`;
  }
  function weekly(m){return `<section class="rv-week" aria-label="本周已保存训练记录"><div><strong>本周训练</strong><span>${m.connection==='ready'?`<b>${m.trained.length}</b> 天有记录`:'尚未读取'}</span></div><div class="rv-days">${m.days.map((d,i)=>`<div aria-label="星期${'一二三四五六日'[i]} ${m.connection!=='ready'?'尚未读取':m.trained.includes(d)?'有训练记录':'暂无记录'}"><span>${'一二三四五六日'[i]}</span><i class="${m.trained.includes(d)?'logged':''} ${d===m.day?'current':''}"></i></div>`).join('')}</div></section>`;}
  const cards=[['assessment','活动度评估','关节活动范围','assess'],['history','历史记录','训练与评估','history'],['guidance','实时指导','不计正式进度','assess&guide=1'],['computer','电脑端训练','查看设备能力','more&tool=computer'],['extras','健身 · 体态','辅助功能','assess&tool=extras'],['body','身体汇总','报告与随访','assess&tool=body']];
function art(key){
const id=key==='extras'?'fitness':key==='body'?'history':key;
const all={
assessment:`<svg class="feature-svg" viewBox="0 0 130 112" fill="none" aria-hidden="true"><circle cx="80" cy="64" r="45" stroke="#e6eddb" stroke-width="7"/><path d="M37 64A43 43 0 0 1 113 27" stroke="#c5f619" stroke-width="7" stroke-linecap="round"/><circle cx="80" cy="64" r="8" fill="#d7fa2a"/><path d="M80 64 103 34" stroke="#242b22" stroke-width="5" stroke-linecap="round"/><circle cx="103" cy="34" r="4" fill="#242b22"/><path d="M37 64h9M80 19v9M122 64h-9" stroke="#adb5ab" stroke-width="2" stroke-linecap="round"/></svg>`,
history:`<svg class="feature-svg" viewBox="0 0 130 112" fill="none" aria-hidden="true"><rect x="38" y="18" width="82" height="80" rx="11" fill="#f0f5e9"/><path d="M49 80h59" stroke="#aab6a7" stroke-width="2" stroke-linecap="round"/><rect x="51" y="57" width="11" height="22" rx="4" fill="#d0debf"/><rect x="69" y="40" width="11" height="39" rx="4" fill="#d1fc20"/><rect x="87" y="48" width="11" height="31" rx="4" fill="#b5ca9d"/><path d="M48 37 66 29 79 35 104 22" stroke="#40483c" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><circle cx="104" cy="22" r="3" fill="#d1fc20"/></svg>`,
guidance:`<svg class="feature-svg" viewBox="0 0 130 112" fill="none" aria-hidden="true"><rect x="40" y="21" width="80" height="68" rx="11" fill="#edf3e9" stroke="#c8d3c3"/><rect x="48" y="29" width="64" height="52" rx="5" fill="#252d29"/><circle cx="80" cy="55" r="15" stroke="#d1fd28" stroke-width="2.5" stroke-dasharray="3 5"/><circle cx="80" cy="49" r="5" fill="#d5fc36"/><path d="M69 67c0-8 22-8 22 0" stroke="#d5fc36" stroke-width="2.5" stroke-linecap="round"/><circle cx="108" cy="33" r="4" fill="#f8705c"/></svg>`,
computer:`<svg class="feature-svg" viewBox="0 0 130 112" fill="none" aria-hidden="true"><rect x="29" y="28" width="94" height="58" rx="7" fill="#dae4d7"/><rect x="34" y="33" width="84" height="47" rx="3" fill="#202922"/><circle cx="77" cy="54" r="13" stroke="#d7fb39" stroke-width="2.5"/><path d="M77 46v16M69 54h16" stroke="#d7fb39" stroke-width="2.5" stroke-linecap="round"/><path d="M17 88h117l-11 8H29z" fill="#c2ccc0"/><path d="M51 89h48" stroke="#68766b" stroke-width="2"/></svg>`,
fitness:`<svg class="feature-svg" viewBox="0 0 130 112" fill="none" aria-hidden="true"><circle cx="89" cy="53" r="32" fill="#f0f5e5"/><path d="M52 55h60" stroke="#444f3f" stroke-width="8" stroke-linecap="round"/><path d="M59 40v30M69 46v18M95 46v18M105 40v30" stroke="#b4e71a" stroke-width="10" stroke-linecap="round"/><path d="M59 40v30M105 40v30" stroke="#303b30" stroke-width="3" stroke-linecap="round"/></svg>`}
return all[id]||''}
  root.RehabV51={escape,artwork,picture,thumb,order,context,hero,weekly,cards,art};
  if(typeof module!=='undefined')module.exports=root.RehabV51;
})(typeof window==='undefined'?globalThis:window);
