// B01: reuse owned, already-saved manual arrangements. No generated dose,
// assessment, formal session or automatic-plan qualification is created here.
'use strict';
async function mountManualArrangements(){
 if(!state.practiceRecording||!state.manualPracticeArrangements||!automaticUploadReconciliation)return;
 const area=document.createElement('section');area.className='card';area.id='manual-arrangements';area.hidden=true;app.appendChild(area);
 const ownerGeneration=state.uploadOwnerGeneration||0,current=()=>state.tab==='plan'&&$('#manual-arrangements')===area&&ownerGeneration===(state.uploadOwnerGeneration||0);
 try{
  const [records,practices]=await Promise.all([api('/practice/arrangements'),api('/practice')]);if(!current())return;
  if(!records.length&&!state.manualArrangementEntry){area.remove();return;}
  area.hidden=false;
  area.innerHTML='<h2>已有人工安排</h2>'+records.map((r,n)=>`<details><summary>${esc(r.name)}</summary>${r.items.map((e,k)=>`<div class="plan-item"><strong>${esc(label(e.exercise_id))} · ${sideLabel(e.side)}</strong><p class="caption">${esc(e.settings.target_reps)} 次 × ${esc(e.settings.target_sets)} 组 · ${Number.isFinite(e.settings.rest_between_sets_s)?'休息 '+esc(e.settings.rest_between_sets_s)+' 秒':'休息按原安排'}</p><button class="secondary" data-manual-entry="${n}:${k}">使用已有安排</button></div>`).join('')}</details>`).join('')+'<div id="manual-confirm-area"></div>';
  if(state.manualArrangementEntry)mountManualArrangementEntry(area,current);
  area.querySelectorAll('[data-manual-entry]').forEach(button=>button.onclick=()=>{
   if(!current())return;const [n,k]=button.dataset.manualEntry.split(':').map(Number),r=records[n],entry=r.items[k],box=area.querySelector('#manual-confirm-area');
   const pending=practices.find(p=>{
    if(p.plan_ref.id!==r.id||p.plan_ref.revision!==r.revision)return false;
    try{const raw=typeof practiceRecordDraftKey==='function'?localStorage.getItem(practiceRecordDraftKey(p.context,p.id)):null;const d=JSON.parse(raw||localStorage.getItem(practiceDraftKey(p.context))||'null');return d?.start?.operation_id===p.id&&(d.nextPending||d.sequenceEndRequested);}catch{return false;}
   });
   const original=pending||practices.find(p=>{
    if(p.plan_ref.id!==r.id||p.plan_ref.revision!==r.revision)return false;
    if(p.state==='PRACTICING')return true;
    if(p.continuation&&!p.successor_id)return true;
    if(p.plan_ref.entry_key!==entry.key)return false;
    try{const draft=JSON.parse(localStorage.getItem(practiceDraftKey(p.context))||'null');return draft?.start?.operation_id===p.id&&!draft.committed;}catch{return false;}
   });
   if(original){state.training={id:r.id,entry};state.selected=entry.exercise_id;state.side=entry.side;state.detail=true;void beginGuidedPractice(r,entry,original);return;}
   if(entry.decision?.category==='EXECUTION_BLOCK'){box.innerHTML='<p role="status">'+esc(entry.decision.message)+'</p>';return;}
   box.innerHTML=`<form id="manual-confirm-form"><h3>${esc(label(entry.exercise_id))} · ${sideLabel(entry.side)}</h3><p class="caption">采用「${esc(r.name)}」原安排 · 本组 ${esc(entry.settings.target_reps)} 次</p><label class="consent"><input id="manual-confirm" type="checkbox" required><span>确认这份已有安排适用于本人，并已按安排准备好支撑；目前没有疼痛、头晕等不适。</span></label><label class="consent"><input id="manual-companion" type="checkbox" ${entry.decision?.companion_required?'required':''}><span>陪同者已到场（安排要求陪同时确认）</span></label><p id="manual-status" role="status"></p><button class="primary">开始跟练</button></form>`;
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
function mountManualArrangementEntry(area,current){
 // Optional entry of an ALREADY decided arrangement. Never default dose or
 // promote it to an automatic plan/qualified assessment; reuse original form.
 const box=document.createElement('details');box.innerHTML=`<summary>录入已有安排</summary><form id="manual-entry-form"><p class="caption">照已有安排填写，不确定的项目先留空。</p><div class="care-form"><label>安排名称<input id="manual-name" maxlength="80" required></label><label>动作<select id="manual-exercise" required><option value="">选择动作</option>${state.catalog.map(s=>`<option value="${esc(s.id)}">${esc(s.label)}</option>`).join('')}</select></label><label>测试侧<select id="manual-side" required><option value="">选择本人侧别</option><option value="left">左侧</option><option value="right">右侧</option></select></label><label>每组次数<input id="manual-reps" type="number" min="1" max="999" step="1" required></label><label>组数<input id="manual-sets" type="number" min="1" max="20" step="1" required></label><label>组间休息（秒，可留空）<input id="manual-rest" type="number" min="0" max="1800" step="any"></label></div><label class="consent"><input id="manual-needs-companion" type="checkbox"><span>原安排要求陪同</span></label><p id="manual-entry-status" role="status"></p><button class="secondary">保存安排</button></form>`;area.appendChild(box);
 let pending=null,draftKey=null,context=null,touched=false;
 const button=box.querySelector('button'),status=box.querySelector('#manual-entry-status'),fields=['manual-name','manual-exercise','manual-side','manual-reps','manual-sets','manual-rest','manual-needs-companion'];
 const formValues=()=>Object.fromEntries(fields.map(id=>[id,id==='manual-needs-companion'?box.querySelector('#'+id).checked:box.querySelector('#'+id).value]));
 const saveDraft=()=>{if(!draftKey)return false;try{localStorage.setItem(draftKey,JSON.stringify({version:1,context,form:formValues(),pending}));return true;}catch{return false;}};
 box.querySelector('form').oninput=()=>{touched=true;saveDraft();};
 button.disabled=true;button.type='button';
 const initializeContext=()=>api('/practice/context').then(c=>{
  if(!current())return;context=c;draftKey=practiceDraftKey(c)+':manual-entry';let saved;try{saved=JSON.parse(localStorage.getItem(draftKey)||'null');}catch{}
  if(saved?.version===1&&practiceEqual(saved.context,c)&&saved.form&&(saved.pending||!touched)){for(const id of fields){const field=box.querySelector('#'+id);if(id==='manual-needs-companion')field.checked=saved.form[id]===true;else if(typeof saved.form[id]==='string')field.value=saved.form[id];}pending=saved.pending||null;}
  if(pending){box.open=true;box.querySelectorAll('input,select').forEach(x=>x.disabled=true);button.textContent='核对原保存';status.textContent='上次保存尚待核对。';}
  button.type='submit';button.onclick=null;button.disabled=false;
 }).catch(()=>{if(current()){status.textContent='档案暂未能核对，已填内容仍在当前页。';button.type='button';button.textContent='重试核对';button.disabled=false;button.onclick=()=>{button.disabled=true;void initializeContext();};}});
 void initializeContext();
 box.querySelector('form').onsubmit=async event=>{
  event.preventDefault();if(!current())return;const button=box.querySelector('button'),status=box.querySelector('#manual-entry-status');if(button.disabled)return;button.disabled=true;
  if(!pending){const val=id=>box.querySelector(id).value;pending={operation_id:newUploadOperation(),name:val('#manual-name').trim(),exercise_id:val('#manual-exercise'),side:val('#manual-side'),settings:{target_reps:Number(val('#manual-reps')),target_sets:Number(val('#manual-sets')),rest_between_sets_s:val('#manual-rest')===''?null:Number(val('#manual-rest')),target_angle_deg:null,needs_companion:box.querySelector('#manual-needs-companion').checked}};box.querySelectorAll('input,select').forEach(x=>x.disabled=true);}
  saveDraft();
  status.textContent='正在核对保存状态…';
  try{
   let original=(await api('/practice/arrangements')).find(r=>r.id===pending.operation_id);
   if(!original)original=await api('/practice/arrangements',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(pending)});
   if(!current())return;if(original.id!==pending.operation_id||original.name!==pending.name||original.items?.[0]?.exercise_id!==pending.exercise_id||original.items[0].side!==pending.side||!practiceEqual(original.items[0].settings,pending.settings))throw Error('保存回执尚未确认');try{localStorage.removeItem(draftKey);}catch{}area.remove();void mountManualArrangements();
  }catch(error){if(!current())return;status.textContent='安排尚未确认保存，请重试核对。';if([400,403].includes(error.status)){status.textContent=error.message;pending=null;saveDraft();box.querySelectorAll('input,select').forEach(x=>x.disabled=false);}}
  finally{if(current())button.disabled=false;}
 };
}
