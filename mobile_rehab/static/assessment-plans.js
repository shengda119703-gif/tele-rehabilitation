/* Server-owned assessment arrangements. No local completion or measurement writes. */
(function(root){
'use strict';
const UUID=/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/;
const E=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const statuses={PLANNED:'待评估',COMPLETED:'已完成',CANCELLED:'已取消'};
let generation=0;
function planURL(id){return UUID.test(id)?'/capture?tab=plan&assessmentPlan='+encodeURIComponent(id)+'#assessment-plans':null;}
function actionHTML(actions){return (Array.isArray(actions)?actions:[]).filter(a=>a?.kind==='assessment_plan'&&planURL(a.plan_id)).slice(0,4).map(a=>'<a class="secondary" href="'+E(planURL(a.plan_id))+'">查看评估计划</a>').join('');}
function valid(document){
 if(!document||!Array.isArray(document.items)||document.items.some(p=>!p||!UUID.test(p.id)||typeof p.title!=='string'||!Object.hasOwn(statuses,p.status)||!Array.isArray(p.items)||p.items.some(i=>!i||!/^[a-z][a-z0-9_]{0,79}$/.test(i.exercise_id)||typeof i.name!=='string'||typeof i.instruction!=='string'||!['left','right','bilateral','choose'].includes(i.side)||!(i.record_id===null||typeof i.record_id==='string'))))throw Error('评估计划回复不完整，请重新读取');
 return document.items;
}
function alive(ctx){return ctx.generation===generation&&state.tab==='plan'&&(state.uploadOwnerGeneration||0)===ctx.ownerGeneration&&document.querySelector('#assessment-plans')===ctx.area;}
function assertView(ctx){if(!alive(ctx))throw Error('页面已变化');}
async function identity(){
 if(root.navigator?.onLine===false)throw Error('当前离线，无法读取云端评估计划。请联网后重试。');
 if(root.PhoneLocal){
  const store=root.PhoneLocal.store,account=root.PhoneAccount;
  if(!account?.identity())throw Error('请先登录本人云账号，才能读取评估计划。');
  const value=account.aiScope(store);
  if(root.PhoneStore?.cloudKey(store.key)&&localStorage.getItem(root.PhoneStore.ACTIVE_KEY)!==store.key)throw Error('账号已变化，请重新打开本人档案');
  return {owner:store.value.owner,patient:value.patient_id,account:value.account_id,store,key:store.key};
 }
 const result=await api('/product'),snapshot=result.snapshot,cloud=snapshot?.cloudAssistant;
 const owner=snapshot?.profile?.ownerId||snapshot?.ownerId;
 if(!owner||!cloud?.connected||!UUID.test(cloud.patient_id)||!UUID.test(cloud.account_id))throw Error('请先在电脑工作台登录并绑定本人档案，才能读取评估计划。');
 return {owner,patient:cloud.patient_id,account:cloud.account_id};
}
function same(a,b){return a&&b&&a.owner===b.owner&&a.patient===b.patient&&a.account===b.account&&a.store===b.store&&a.key===b.key;}
async function request(ctx,action,id){
 assertView(ctx);const before=await identity();assertView(ctx);
 if(ctx.scope&&!same(ctx.scope,before))throw Error('账号已变化，请重新读取评估计划');
 ctx.scope=before;
 let result;
 if(before.store){
  const account=root.PhoneAccount;
  result=await (action==='cancel'?account.assessmentPlanCancel(before.store,id):account.assessmentPlans(before.store));
 }else{
  result=await api('/unified/workbench.'+(action==='cancel'?'assessmentPlanCancel':'assessmentPlans'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({patient_id:before.patient,account_id:before.account,...(action==='cancel'?{plan_id:id}:{})})});
 }
 assertView(ctx);const after=await identity();assertView(ctx);
 if(!same(before,after))throw Error('账号已变化，旧评估计划未显示');
 return result;
}
function failed(ctx,error){
 if(!alive(ctx))return;
 ctx.area.innerHTML='<h2>评估计划</h2><p role="status">暂时无法读取评估计划：'+E(error.message||'请联网后重试。')+'</p><button type="button" class="secondary" id="assessment-retry">重新读取</button>';
 ctx.area.querySelector('#assessment-retry').onclick=()=>mount();
}
async function currentItem(ctx,planId,index){
 const rows=valid(await request(ctx,'list')),plan=rows.find(p=>p.id===planId),item=plan?.items[index];
 if(!plan||plan.status!=='PLANNED'||!item||item.record_id!==null)throw Error('这项评估安排已变化，请重新读取');
 if(plan.routing_version==='online-assessment-routing-2'&&plan.items.findIndex(i=>i.record_id===null)!==index)throw Error('请先完成上一项评估并保存结果');
 const original=ctx.rows.find(p=>p.id===planId)?.items[index];
 if(!original||original.exercise_id!==item.exercise_id||original.side!==item.side)throw Error('评估项目已变化，请重新读取');
 if(!state.catalog.some(ex=>ex.id===item.exercise_id&&ex.available!==false))throw Error('此评估动作在当前设备不可用，请查看动作库或联系康复医师。');
 return item;
}
async function openItem(ctx,planId,index,side){
 try{
  const item=await currentItem(ctx,planId,index);assertView(ctx);
  if(!side&&['choose','bilateral'].includes(item.side)){
   ctx.area.innerHTML='<h2>评估计划</h2><h3>'+E(item.name)+'</h3><p>'+E(item.instruction)+'</p><p>请选择本次测量侧'+(item.side==='bilateral'?'，双侧请分别测量':'')+'。</p><button type="button" class="primary" id="assessment-left">本人左侧</button> <button type="button" class="primary" id="assessment-right">本人右侧</button> <button type="button" class="secondary" id="assessment-back">返回评估计划</button>';
   for(const choice of ['left','right'])ctx.area.querySelector('#assessment-'+choice).onclick=()=>openItem(ctx,planId,index,choice);
   ctx.area.querySelector('#assessment-back').onclick=()=>mount();return;
  }
  const selectedSide=['left','right'].includes(item.side)?item.side:side;
  if(!['left','right'].includes(selectedSide))throw Error('请选择本次测量侧');
  const query=new URLSearchParams({tab:'assess',entry:'assistant',exercise:item.exercise_id,side:selectedSide});
  if(ctx.scope.store&&root.PhoneAssessmentRun){
   const plan=ctx.rows.find(p=>p.id===planId);
   if(!root.PhoneAssessmentRun.localStep(ctx.scope.store,planId,index)&&!root.confirm('将本次评估视频的分析结果保存到本人云端档案，并更新这份评估计划？原始视频保留在本机。'))return;
   const run=await root.PhoneAssessmentRun.begin(ctx.scope.store,plan,index,selectedSide,true);assertView(ctx);
   query.set('assessmentRun',run);query.set('assessmentIndex',String(index));
  }
  root.location.assign('/capture?'+query.toString());
 }catch(error){failed(ctx,error);}
}
async function cancel(ctx,id){
 if(!alive(ctx)||!root.confirm('取消这份评估计划？已保存的评估记录会保留。'))return;
 try{await request(ctx,'cancel',id);assertView(ctx);await load(ctx);}catch(error){failed(ctx,error);}
}
function draw(ctx){
 const focus=new URLSearchParams(root.location.search).get('assessmentPlan');
 ctx.area.innerHTML='<h2>评估计划</h2><p class="caption">康复管家保存到本人云账号的评估安排；完成状态以服务器核对的已上传评估为准。</p><button type="button" class="secondary" id="assessment-refresh">刷新评估计划</button>'+ctx.rows.map(p=>'<section class="card" id="assessment-plan-'+E(p.id)+'"><h3>'+E(p.title)+'</h3><p>'+statuses[p.status]+'</p>'+p.items.map((i,index)=>'<div class="plan-item"><strong>'+E(i.name)+'</strong><p class="caption">'+({left:'本人左侧',right:'本人右侧',bilateral:'双侧分别测量',choose:'测量前选择侧别'}[i.side])+(i.record_id!==null?' · 已有关联评估':'')+'</p><p>'+E(i.instruction)+'</p>'+(p.status==='PLANNED'&&i.record_id===null?'<button type="button" class="secondary" data-assessment-open="'+p.id+'" data-assessment-index="'+index+'">查看动作详情</button>':'')+'</div>').join('')+(p.status==='PLANNED'?'<button type="button" class="secondary" data-assessment-cancel="'+p.id+'">取消评估计划</button>':'')+'</section>').join('')+(ctx.rows.length?'':'<p>暂无云端评估计划。</p>');
 ctx.area.querySelector('#assessment-refresh').onclick=()=>mount();
 ctx.area.querySelectorAll('[data-assessment-open]').forEach(b=>b.onclick=()=>openItem(ctx,b.dataset.assessmentOpen,Number(b.dataset.assessmentIndex)));
 ctx.area.querySelectorAll('[data-assessment-cancel]').forEach(b=>b.onclick=()=>cancel(ctx,b.dataset.assessmentCancel));
 if(UUID.test(focus))ctx.area.querySelector('#assessment-plan-'+focus)?.scrollIntoView?.({block:'start'});
}
async function load(ctx){
 assertView(ctx);ctx.area.innerHTML='<h2>评估计划</h2><p role="status">正在读取本人云端评估计划…</p>';
 const rows=valid(await request(ctx,'list'));assertView(ctx);ctx.rows=rows;draw(ctx);
}
async function mount(){
 const area=document.querySelector('#assessment-plans');if(!area||state.tab!=='plan')return;
 const ctx={area,generation:++generation,ownerGeneration:state.uploadOwnerGeneration||0,scope:null,rows:[]};
 try{if(root.PhoneLocal&&root.PhoneAssessmentRun){await root.PhoneLocal.ready;await root.PhoneAssessmentRun.resume(root.PhoneLocal.store);}await load(ctx);}catch(error){failed(ctx,error);}
}
root.AssessmentPlans={mount,planURL,actionHTML};
})(window);
