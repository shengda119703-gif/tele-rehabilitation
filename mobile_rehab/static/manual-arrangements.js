// B01: reuse owned, already-saved manual arrangements. No generated dose,
// assessment, formal session or automatic-plan qualification is created here.
'use strict';
async function mountManualArrangements(){
 if(!state.practiceRecording||!state.manualPracticeArrangements||!automaticUploadReconciliation)return;
 const area=document.createElement('section');area.className='card';area.id='manual-arrangements';area.hidden=true;app.appendChild(area);
 const ownerGeneration=state.uploadOwnerGeneration||0,current=()=>state.tab==='plan'&&$('#manual-arrangements')===area&&ownerGeneration===(state.uploadOwnerGeneration||0);
 try{
  const [records,practices]=await Promise.all([api('/practice/arrangements'),api('/practice')]);if(!current())return;
  if(!records.length){area.remove();return;}
  area.hidden=false;
  area.innerHTML='<h2>已有人工安排</h2>'+records.map((r,n)=>`<details><summary>${esc(r.name)}</summary>${r.items.map((e,k)=>`<div class="plan-item"><strong>${esc(label(e.exercise_id))} · ${sideLabel(e.side)}</strong><p class="caption">${esc(e.settings.target_reps)} 次 × ${esc(e.settings.target_sets)} 组 · ${Number.isFinite(e.settings.rest_between_sets_s)?'休息 '+esc(e.settings.rest_between_sets_s)+' 秒':'休息按原安排'}</p><button class="secondary" data-manual-entry="${n}:${k}">使用已有安排</button></div>`).join('')}</details>`).join('')+'<div id="manual-confirm-area"></div>';
  area.querySelectorAll('[data-manual-entry]').forEach(button=>button.onclick=()=>{
   if(!current())return;const [n,k]=button.dataset.manualEntry.split(':').map(Number),r=records[n],entry=r.items[k],box=area.querySelector('#manual-confirm-area');
   const original=practices.find(p=>{
    if(p.plan_ref.id!==r.id||p.plan_ref.entry_key!==entry.key)return false;
    if(p.state==='PRACTICING')return true;
    try{const draft=JSON.parse(localStorage.getItem(practiceDraftKey(p.context))||'null');return draft?.start?.operation_id===p.id&&!draft.committed;}catch{return false;}
   });
   if(original){state.training={id:r.id,entry};state.selected=entry.exercise_id;state.side=entry.side;state.detail=true;void beginGuidedPractice(r,entry,original);return;}
   if(entry.decision?.category==='EXECUTION_BLOCK'){box.innerHTML='<p role="status">'+esc(entry.decision.message)+'</p>';return;}
   box.innerHTML=`<form class="care-form" id="manual-confirm-form"><h3>${esc(label(entry.exercise_id))} · ${sideLabel(entry.side)}</h3><p class="caption">采用「${esc(r.name)}」原安排 · 本组 ${esc(entry.settings.target_reps)} 次</p><label class="consent"><input id="manual-confirm" type="checkbox" required><span>确认这份已有安排适用于本人，并已按安排准备好支撑；目前没有疼痛、头晕等不适。</span></label><label class="consent"><input id="manual-companion" type="checkbox" ${entry.decision?.companion_required?'required':''}><span>陪同者已到场（安排要求陪同时确认）</span></label><p id="manual-status" role="status"></p><button class="primary">开始跟练</button></form>`;
   box.querySelector('form').onsubmit=async event=>{
    event.preventDefault();if(!current())return;const start=event.currentTarget.querySelector('button');if(start.disabled)return;start.disabled=true;
    const confirmations={manual_arrangement_confirmed:box.querySelector('#manual-confirm').checked,support_ready:box.querySelector('#manual-confirm').checked,companion_present:box.querySelector('#manual-companion').checked};
    state.training={id:r.id,entry};state.selected=entry.exercise_id;state.side=entry.side;state.joint=selected()?.joint||state.joint;state.detail=true;
    await beginGuidedPractice(r,entry,null,confirmations);
   };
  });
 }catch(error){
  if(!current())return;area.hidden=false;area.innerHTML='<p role="status">已有人工安排暂时未能读取。</p><button class="secondary" id="manual-retry">重试</button>';
  area.querySelector('button').onclick=()=>{area.remove();void mountManualArrangements();};
 }
}
