'use strict';
// Independent, revisioned feedback. Never rewrites the immutable finish payload
// or visual facts; null input stays null, and retry queries its original key.
const practiceFeedbackPath=j=>'/practice/'+j.start.operation_id+'/feedback';
const practiceFeedbackValues=d=>({pain:d.pain===''?null:Number(d.pain),fatigue:d.fatigue===''?null:Number(d.fatigue),note:d.note.trim()||null});
const practiceFeedbackDraft=v=>({pain:v.pain===null?'':String(v.pain),fatigue:v.fatigue===null?'':String(v.fatigue),note:v.note||''});
function currentPracticeFeedback(j,area,panel){return currentPractice(j,area)&&$('#practice-feedback')===panel;}
function acceptPracticeFeedback(j,r){
 if(r.practice_id!==j.start.operation_id||!practiceEqual(r.context,j.context)||!Number.isInteger(r.revision)||r.revision<0)throw Error('感受记录归属或版本不一致。');
 if(!j.feedbackSnapshot||r.revision>=j.feedbackSnapshot.revision)j.feedbackSnapshot=r;
}
function mountPracticeFeedback(j,area){
 const panel=document.createElement('section');panel.id='practice-feedback';panel.className='card care-form';area.appendChild(panel);
 drawPracticeFeedback(j,area,panel);
 if(j.receipt.state==='COMMITTED')void reconcilePracticeFeedback(j,area,panel);
}
function drawPracticeFeedback(j,area,panel){
 const saved=j.feedbackSnapshot?.revision>0,waiting=j.receipt.state!=='COMMITTED',pending=!!j.feedbackPending;
 const d=j.feedbackDraft||practiceFeedbackDraft(j.feedbackSnapshot?.values||{pain:null,fatigue:null,note:null});
 const status=j.feedbackBusy?'正在核对感受保存状态…':j.feedbackMessage||(waiting?'练习保存后可提交，感受可以稍后填写。':pending?'感受保存待核对；练习记录已保存。':saved?'感受已保存。':'选填，未填写的项目保持空白。');
 panel.innerHTML=`<h2>本次感受</h2><p role="status" id="practice-feedback-status">${esc(status)}</p><label>疼痛（0–10）<input id="practice-pain" type="number" min="0" max="10" step="1" placeholder="未填写"></label><label>疲劳（0–10）<input id="practice-fatigue" type="number" min="0" max="10" step="1" placeholder="未填写"></label><label>备注<textarea id="practice-note" maxlength="500" placeholder="选填"></textarea></label><div class="live-controls"><button class="primary" id="practice-feedback-submit">${pending?'核对保存状态':saved?'保存修改':'保存感受'}</button><button class="secondary" id="practice-feedback-later">稍后填写</button></div>${j.feedbackConflict?'<details><summary>另一处保存的感受</summary><p id="practice-feedback-latest"></p></details><button class="secondary" id="practice-feedback-use-latest">使用最新内容</button><button class="secondary" id="practice-feedback-replace">按最新版本提交我的填写</button>':''}`;
 for(const [field,id] of [['pain','practice-pain'],['fatigue','practice-fatigue'],['note','practice-note']]){
  const input=$('#'+id);input.value=d[field];input.disabled=pending;
  input.oninput=()=>{j.feedbackDraft={pain:$('#practice-pain').value,fatigue:$('#practice-fatigue').value,note:$('#practice-note').value};j.feedbackMessage=null;persistPractice(j);};
 }
 const submit=$('#practice-feedback-submit');submit.disabled=waiting||j.feedbackBusy;
 if(!j.feedbackSnapshot&&!waiting)submit.textContent='重试读取感受';
 submit.onclick=()=>{
  if(!j.feedbackSnapshot){void reconcilePracticeFeedback(j,area,panel);return;}
  if(j.feedbackPending){void reconcilePracticeFeedback(j,area,panel);return;}
  const values=practiceFeedbackValues(j.feedbackDraft||d);
  if([values.pain,values.fatigue].some(n=>n!==null&&(!Number.isInteger(n)||n<0||n>10))||values.note?.length>500){toast('请填写 0–10 的整数，或留空');return;}
  if(Object.values(values).every(v=>v===null)){toast('没有填写感受，可以稍后再填');return;}
  if(j.feedbackSnapshot.revision>0&&practiceEqual(values,j.feedbackSnapshot.values)){j.feedbackMessage='感受已保存，没有新的修改。';drawPracticeFeedback(j,area,panel);return;}
  j.feedbackDraft=practiceFeedbackDraft(values);
  j.feedbackPending={operation_id:newUploadOperation(),expected_revision:j.feedbackSnapshot.revision,values};persistPractice(j);
  void reconcilePracticeFeedback(j,area,panel);
 };
 $('#practice-feedback-later').onclick=()=>{persistPractice(j);pausePractice();navigate('plan');};
 if(j.feedbackConflict){
  const v=j.feedbackSnapshot.values;$('#practice-feedback-latest').textContent='疼痛 '+(v.pain??'未填')+' · 疲劳 '+(v.fatigue??'未填')+' · '+(v.note||'无备注');
  $('#practice-feedback-use-latest').onclick=()=>{j.feedbackPending=null;j.feedbackConflict=false;j.feedbackDraft=null;j.feedbackMessage='已读取最新感受。';persistPractice(j);drawPracticeFeedback(j,area,panel);};
  $('#practice-feedback-replace').onclick=()=>{
   const old=j.feedbackPending;if(!old||j.feedbackBusy)return;
   (j.feedbackSuperseded??=[]).push(old);
   j.feedbackPending={...old,operation_id:newUploadOperation(),expected_revision:j.feedbackSnapshot.revision};j.feedbackConflict=false;persistPractice(j);
   void reconcilePracticeFeedback(j,area,panel);
  };
 }
}
async function reconcilePracticeFeedback(j,area,panel){
 if(j.feedbackBusy||j.receipt?.state!=='COMMITTED')return;j.feedbackBusy=true;
 // The first read has no revision yet. Reflect its pending state before the
 // user can click a button bound to an unknown revision and lose that intent.
 drawPracticeFeedback(j,area,panel);
 try{
  const path=practiceFeedbackPath(j),snapshot=await api(path);
  if(!currentPracticeFeedback(j,area,panel))return;acceptPracticeFeedback(j,snapshot);
  const pending=j.feedbackPending;
  if(pending){
   let r;try{r=await api(path+'/operations/'+pending.operation_id);}catch(e){
    if(e.status!==404)throw e;
    r=await api(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(pending)});
   }
   if(!currentPracticeFeedback(j,area,panel)||j.feedbackPending!==pending)return;
   if(r.status!=='COMMITTED'||r.operation_id!==pending.operation_id||r.expected_revision!==pending.expected_revision||!practiceEqual(r.values,pending.values))throw Error('感受保存回执尚未确认。');
   acceptPracticeFeedback(j,r);j.feedbackPending=null;j.feedbackDraft=null;j.feedbackConflict=false;j.feedbackMessage='感受已保存。';persistPractice(j);
  }else j.feedbackMessage=null;
 }catch(e){
  if(!currentPracticeFeedback(j,area,panel))return;
  if(e.status===409&&e.reason?.code==='FEEDBACK_REVISION_CONFLICT'){
   try{
    const latest=await api(practiceFeedbackPath(j));if(!currentPracticeFeedback(j,area,panel))return;acceptPracticeFeedback(j,latest);
    if(practiceEqual(latest.values,j.feedbackPending?.values)){j.feedbackPending=null;j.feedbackDraft=null;j.feedbackConflict=false;j.feedbackMessage='相同感受已保存。';}
    else{j.feedbackConflict=true;j.feedbackMessage='另一处更新了感受，请核对后选择。你的填写仍保留。';}
    persistPractice(j);
   }catch{j.feedbackMessage='感受保存待核对；你的填写仍保留。';}
  }else j.feedbackMessage=j.feedbackPending?'感受保存待核对。'+(j.draftSaved?'填写已保留在本机。':'填写仍在当前页面。'):'感受暂时未能读取，可以稍后再试。';
 }finally{
  j.feedbackBusy=false;
  if(currentPracticeFeedback(j,area,panel))drawPracticeFeedback(j,area,panel);
  else if(currentPractice(j,area)&&$('#practice-feedback'))void reconcilePracticeFeedback(j,area,$('#practice-feedback'));
 }
}
