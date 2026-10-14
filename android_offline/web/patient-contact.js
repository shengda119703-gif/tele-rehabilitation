/* Patient conversation view. The account adapter owns identity and durable queues. */
(function(root){
'use strict';
const escape=text=>String(text??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const messageTime=value=>{const date=new Date(typeof value==='number'?value*1000:value);return Number.isFinite(date.getTime())?date.toLocaleString():'';};
function planHtml(plan){
 if(!plan)return '<p>康复医师还没有发布方案。你可以先在对话中说明情况。</p>';
 const phase=plan.execution_date?'<p>'+escape(plan.execution_date)+(plan.phase_name?' · '+escape(plan.phase_name):'')+'</p>':'';
 const condition={STOPPED:'该方案已停用，请联系医师核对。',REST_DAY:'今天是休息日。',MANUAL_ONLY:'这一阶段需要医师指导下人工执行。'}[plan.execution_status];
 return '<h3>'+escape(plan.title)+'</h3>'+phase+'<p>'+escape(plan.summary)+'</p>'+(condition?'<p>'+condition+'</p>':'')+(plan.items||[]).map(i=>'<h4>'+escape(i.name)+' · '+(i.side==='left'?'左侧':'右侧')+'</h4><p>'+escape(i.settings.target_reps)+' 次 / 组 · '+escape(i.settings.target_sets)+' 组 · 组间休息 '+escape(i.settings.rest_between_sets_s??0)+' 秒'+(i.settings.target_angle_deg!==null?' · 目标角度 '+escape(i.settings.target_angle_deg)+'°':'')+'</p><p>'+escape(i.dose)+'</p><p>'+escape(i.caution)+'</p>').join('');
}
async function open(){
 const A=root.PhoneAccount,value=A.identity();if(!value){A.login();return;}
 A.validateIdentity(value);await root.PhoneLocal.ready;const store=root.PhoneLocal.store;
 const prior=document.querySelector('#patient-contact');if(prior?.open){prior.focus();return;}
 const dialog=document.createElement('dialog');dialog.id='patient-contact';dialog.setAttribute('aria-labelledby','patient-contact-title');
 dialog.innerHTML='<div class="contact-heading"><div><h2 id="patient-contact-title">联系康复医师</h2><p>安康 · '+escape(value.username)+'</p></div><button type="button" class="quiet contact-close" aria-label="关闭联系康复医师">关闭</button></div><div class="contact-tabs" role="navigation" aria-label="医师服务"><button type="button" data-view="messages">医师对话</button><button type="button" data-view="plans">医生方案</button><button type="button" data-view="settings" class="quiet">资料与授权</button></div><p class="contact-status" role="status" aria-live="polite"></p><section class="contact-content" aria-label="医师服务内容"></section><form class="contact-composer"><label for="contact-message">给康复医师留言</label><textarea id="contact-message" maxlength="4000" rows="3" placeholder="说说你的问题，或告诉医师训练后的感受"></textarea><div class="actions"><button type="submit" class="primary">发送给医师</button><button type="button" class="quiet" data-report>选择报告</button><button type="button" class="quiet" data-refresh>刷新消息</button></div></form><input type="file" class="contact-file" accept="application/pdf,image/png,image/jpeg" aria-label="选择报告原件">';
 const status=dialog.querySelector('.contact-status'),content=dialog.querySelector('.contact-content'),composer=dialog.querySelector('.contact-composer'),input=dialog.querySelector('#contact-message'),fileInput=dialog.querySelector('.contact-file');
 let view='messages',busy=false,oldest=0,planOffset=0,currentRevision=0,plans=[];
 const waiting=()=> (store.value.cloudMessageOutbox||[]).filter(row=>row.patient_id===value.patient_id&&!row.resource_id);
 const bound=()=>{try{A.scope(store);return true;}catch{return false;}};
 const active=()=>dialog.open&&A.identity()?.account_id===value.account_id&&A.identity()?.patient_id===value.patient_id;
 function state(){
  dialog.querySelectorAll('button:not(.contact-close)').forEach(button=>button.disabled=busy);
  composer.hidden=view!=='messages'||!bound();
  dialog.querySelectorAll('[data-view]').forEach(button=>button.setAttribute('aria-current',button.dataset.view===view?'page':'false'));
 }
 async function run(work){
  if(busy||!active())return;busy=true;state();status.textContent='正在连接…';
  try{const note=await work();if(active()&&note)status.textContent=note;}
  catch(error){if(active())status.textContent=waiting().length?'连接未完成，'+waiting().length+' 条消息已保留，联网后会继续发送。':error.message;}
  finally{busy=false;if(active())state();}
 }
 function button(title,work,target=content,quiet=false){const b=document.createElement('button');b.type='button';b.textContent=title;if(quiet)b.className='quiet';b.onclick=()=>run(work);target.append(b);return b;}
 function showPending(){
  for(const row of waiting()){const article=document.createElement('article');article.className='contact-message mine pending';article.innerHTML='<b>我 · 待发送</b><p>'+escape(row.text).replace(/\n/g,'<br>')+'</p>';content.append(article);}
  if(waiting().length)button('重试待发送消息',async()=>{await A.syncMessages(store);return showMessages();});
 }
 async function showMessages(before=0){
  view='messages';state();const r=await A.messages(store,before);if(!active()||view!=='messages')return;
  content.innerHTML=r.items.map(m=>'<article class="contact-message '+(m.author_role==='DOCTOR_ADMIN'?'doctor':'mine')+'"><b>'+(m.author_role==='DOCTOR_ADMIN'?'康复医师':'我')+'</b><p>'+escape(m.text).replace(/\n/g,'<br>')+'</p><small>'+escape(messageTime(m.created_at))+'</small></article>').join('')||'<p class="contact-empty">可以向康复医师描述你的问题，也可以选择分享报告。</p>';
  if(r.items.length){oldest=r.items[0].sequence;if(!r.offline)await A.markRead(store,r.items.at(-1).sequence);button('查看更早的聊天',()=>showMessages(oldest),content,true);}
  showPending();if(!before)content.scrollTop=content.scrollHeight;return r.offline?'正在显示已保存的聊天，联网后可刷新。':waiting().length?'消息已保留，联网后继续发送。':'聊天已更新。医生会在工作时间回复。';
 }
 async function showPlans(offset=0){
  A.scope(store);view='plans';state();const r=await A.request('plans',value,{offset});if(!active()||view!=='plans')return;
  plans=r.items;planOffset=r.offset??offset;currentRevision=r.current_revision;
  content.innerHTML=plans.map((p,index)=>'<article class="contact-plan">'+planHtml(p)+'<button type="button" data-adopt="'+index+'">核对评估并采用'+(r.current_plan_id===p.id?'（当前）':'')+'</button></article>').join('')||'<p>康复医师还没有发布方案。你可以先在对话中说明情况。</p>';
  content.querySelectorAll('[data-adopt]').forEach(b=>b.onclick=()=>run(async()=>{
   const plan=plans[Number(b.dataset.adopt)];if(!confirm('采用「'+plan.title+'」？将核对本机最新本人评估，通过后加入本地训练计划。'))return '未采用';
   const result=await A.adopt(store,plan,currentRevision);currentRevision=result.current_revision;root.load?.();
   return result.local_status==='ACTIVE'?'已加入本地训练计划。开始训练仍需原来的准备确认。':result.local_status==='SUPERSEDED'?'医生方案已更新，请刷新后重新核对。':'请先补做有效评估，再核对采用。';
  }));
  if(plans.length===5)button('查看更早的方案',()=>showPlans(planOffset+5),content,true);
  return '聊天不会改变训练计划。采用方案前会核对评估和手机支持情况。';
 }
 function setup(){
  view='settings';state();content.innerHTML='<h3>首次开通医师沟通</h3><p>账号用于保存聊天和区分你的记录。确认后，以后从“联系康复医师”直接进入。</p><form class="contact-setup"><label><input type="checkbox" name="owner" required>我确认当前本机档案属于这个账号</label><label><input type="checkbox" name="doctor" required>我同意康复医师查看我主动分享的资料并与我沟通</label><label><input type="checkbox" name="sync">同时自动同步已保存的康复评估、训练记录和计划（不含录像）</label><button type="submit">确认并进入对话</button></form>';
  content.querySelector('form').onsubmit=event=>{event.preventDefault();const form=event.currentTarget;if(!form.elements.owner.checked||!form.elements.doctor.checked)return;run(async()=>{await A.bind(store,form.elements.sync.checked);await A.request('grant',value,{enabled:true});if(store.value.cloudConsent)A.schedule(store);return showMessages();});};
 }
 async function chooseReport(){A.scope(store);fileInput.value='';fileInput.click();return '请选择要分享的 PDF、PNG 或 JPEG，单份不超过 2MB。';}
 async function shareReport(){
  const file=fileInput.files[0];if(!file)return;if(file.size>2*1024*1024)throw Error('单份报告不得超过2MB');
  if(!confirm('将「'+file.name+'」分享给已授权的康复医师？不做识字，也不发给 AI。'))return '未分享';
  const bytes=new Uint8Array(await file.arrayBuffer()),digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),x=>x.toString(16).padStart(2,'0')).join(''),operationKey=digest+':'+file.name;
  let operation=store.value.cloudReportOperations?.[operationKey];if(!operation){operation=crypto.randomUUID();await store.serial(()=>store.change(v=>{A.scope(store);(v.cloudReportOperations??={})[operationKey]=operation;}));}
  let binary='';for(const byte of bytes)binary+=String.fromCharCode(byte);
  const r=await A.request('shareReport',A.scope(store),{operation_id:operation,filename:file.name,mime:file.type,data:btoa(binary),shared:true});
  return r.item.shared?'报告已分享。医师可在后台查看原件。':'这份报告曾撤销共享；请在本人网页的报告授权中重新确认。';
 }
 async function workflow(){
  const current=await A.request('workflow',A.scope(store)),p=current.profile||{};
  content.innerHTML='<h3>康复资料与评估</h3><ol>'+current.steps.map(s=>'<li>'+escape(s)+'</li>').join('')+'</ol><p>'+escape(current.assessment_note)+'</p><form class="workflow-profile"><label>康复目标<input name="goal" maxlength="500" value="'+escape(p.goal||'')+'" required></label><label>部位<select name="region">'+['肩','肘','腕','髋','膝','踝','颈','躯干','一般活动'].map(r=>'<option '+(p.region===r?'selected':'')+'>'+r+'</option>').join('')+'</select></label><label>自填能力（不是测量肌力）<select name="level">'+[0,1,2,3].map(n=>'<option value="'+n+'" '+(p.level===n?'selected':'')+'>L'+n+'</option>').join('')+'</select></label><label>器材（每行一项）<textarea name="equipment">'+escape((p.equipment||[]).join('\n'))+'</textarea></label><label>限制（每行一项）<textarea name="restrictions">'+escape((p.restrictions||[]).join('\n'))+'</textarea></label><label><input type="checkbox" name="screening" '+(p.screening_confirmed?'checked':'')+'>已阅读适用与停止条件，有疑问先联系医师</label><button type="submit">保存康复资料</button></form><h4>可选现有评估</h4>'+current.suggested_assessments.map(a=>'<p>'+escape(a.name)+'：'+escape(a.description)+'</p>').join('')+'<p>请回原康复页面开始评估，完成后同步真实结果。</p>';
  const form=content.querySelector('form');form.onsubmit=event=>{event.preventDefault();run(async()=>{await A.request('workflowProfile',A.scope(store),{expected_version:current.profile_version,goal:form.elements.goal.value,region:form.elements.region.value,level:Number(form.elements.level.value),equipment:form.elements.equipment.value.split('\n').map(x=>x.trim()).filter(Boolean),restrictions:form.elements.restrictions.value.split('\n').map(x=>x.trim()).filter(Boolean),screening_confirmed:form.elements.screening.checked});await workflow();return '康复资料已保存。';});};
  for(const [title,kind] of [['提交起始候选供医师审核','STARTER'],['请求医师核对进阶','PROGRESSION']])button(title,async()=>{const r=await A.request('candidate',A.scope(store),{operation_id:crypto.randomUUID(),kind});content.innerHTML='<h3>已提交医师核对</h3><p>'+escape(r.document.note)+'</p>'+r.document.cards.map(c=>'<h4>'+escape(c.name)+'</h4><p>源剂量范围：'+escape(c.sourceDose)+'</p><p>开始条件：'+escape(c.startConditions)+'</p><p>停止条件：'+escape(c.stopConditions)+'</p>').join('');return '候选不调用付费模型，也不会改变当前计划。';});
  return '这些资料供评估与医生审核使用。';
 }
 async function settings(){
  if(!bound()){setup();return '请确认本人档案和医师授权。';}
  view='settings';state();const profile=await A.request('profile',A.scope(store));if(!active()||view!=='settings')return;
  content.innerHTML='<h3>资料与授权</h3><p>医师权限：'+(profile.doctor_access?'已开启':'未开启')+'；康复记录自动同步：'+(store.value.cloudConsent?'已开启':'已暂停')+'</p><div class="contact-settings-actions"></div><details><summary>我的康复资料与 AI 服务</summary><div class="contact-personal-actions"></div></details><details><summary>账号设置</summary><div class="contact-account-actions"></div></details>';
  const actions=content.querySelector('.contact-settings-actions'),personal=content.querySelector('.contact-personal-actions'),accounts=content.querySelector('.contact-account-actions');
  button(profile.doctor_access?'撤销医师授权':'开启医师授权',async()=>{const enabled=!profile.doctor_access;if(!confirm(enabled?'允许康复医师查看你主动分享的资料并与你沟通？':'撤销后医师将不能继续读取你的云端资料和对话。确认撤销？'))return '未修改';await A.request('grant',value,{enabled});return settings();},actions,true);
  button(store.value.cloudConsent?'暂停自动同步':'开启自动同步',async()=>{A.scope(store);const enabled=!store.value.cloudConsent;if(enabled&&!confirm('自动同步已保存的本人康复评估、训练记录、计划和必要资料？不含录像。'))return '未修改';await store.serial(()=>store.change(v=>{A.scope(store);v.cloudConsent=enabled;}));if(enabled)A.schedule(store);return settings();},actions,true);
  button('查看已分享的报告',async()=>{const r=await A.request('reports',A.scope(store));content.innerHTML='<h3>我的报告原件</h3>'+r.items.map(i=>'<p>'+escape(i.filename)+' · '+(i.shared?'已分享给授权医师':'仅本人')+'</p>').join('')+(r.items.length?'':'<p>还没有分享报告。</p>');return '可在本人网页调整原件共享；撤销医师授权会停止医师读取所有资料。';},actions,true);
  button('同步已保存康复资料',async()=>{const r=await A.publish(store);return '本次已同步 '+r.uploaded+' 条真实保存的记录。';},actions,true);
  button('康复目标、器材与评估',workflow,personal,true);
  button('AI 康复问答',async()=>{const text=prompt('AI 与医师对话分开。仅发送你填写的文字，不发送报告或修改计划。');if(!text?.trim())return '未发送';const r=await A.askAI(store,text);content.textContent=r.answer||'结果待核对：'+r.state;return '这是 AI 回复，不是康复医师回复。';},personal,true);
  if(store.value.cloudAiPending)button('核对上次 AI 提问',async()=>{const r=await A.askAI(store);content.textContent=r.answer||'结果待核对：'+r.state;return '已核对原提问回执。';},personal,true);
  button('查看本人 AI 用量',async()=>{const r=await A.request('aiUsage',A.scope(store)),u=r.usage;content.textContent=r.period+'：'+u.calls+' 次；输入 '+u.prompt_tokens+' / 输出 '+u.completion_tokens+' token\n费用估算（不是账单）：'+(Object.entries(u.estimated_cost_by_currency).map(([k,v])=>k+' '+v).join('；')||'尚未计价')+'\n待核对 '+u.uncertain_calls+' 次；未计价 '+u.unpriced_calls+' 次';return '仅显示本人的实际模型回执。';},personal,true);
  button('切换账号',()=>A.login(),accounts,true);
  button('退出账号',async()=>{await A.request('logout',value);await store.tail;localStorage.setItem(root.PhoneStore.ACTIVE_KEY,root.PhoneStore.KEY);location.href='/';},accounts,true);
  button('打开独立本人档案',async()=>{localStorage.setItem(root.PhoneStore.ACTIVE_KEY,root.PhoneStore.CLOUD_PREFIX+value.patient_id);location.href='/';},accounts,true);
  return '你可以随时调整医师授权和同步选择。';
 }
 dialog.querySelector('.contact-close').onclick=()=>dialog.close();
 dialog.querySelector('[data-view="messages"]').onclick=()=>run(()=>bound()?showMessages():(setup(),'请先开通医师沟通。'));
 dialog.querySelector('[data-view="plans"]').onclick=()=>run(()=>bound()?showPlans():(setup(),'请先确认本人档案。'));
 dialog.querySelector('[data-view="settings"]').onclick=()=>run(settings);
 dialog.querySelector('[data-report]').onclick=()=>run(chooseReport);fileInput.onchange=()=>run(shareReport);
 dialog.querySelector('[data-refresh]').onclick=()=>run(showMessages);
 composer.onsubmit=event=>{event.preventDefault();const text=input.value.trim();if(!text)return;run(async()=>{try{await A.send(store,text);}catch(error){if(waiting().some(row=>row.text===text)){if(input.value.trim()===text)input.value='';await showMessages().catch(()=>{content.innerHTML='';showPending();});}throw error;}if(input.value.trim()===text)input.value='';return showMessages();});};
 const updated=()=>{if(active()&&view==='messages'&&!busy&&bound())run(showMessages);};
 root.addEventListener('workbench-updated',updated);
 dialog.addEventListener('close',()=>{root.removeEventListener('workbench-updated',updated);dialog.remove();});
 document.body.append(dialog);dialog.showModal();
 if(bound())await run(async()=>{try{await A.syncMessages(store);}catch{/* Existing queued messages remain visible offline. */}return showMessages();});else setup();
}
root.PhoneContact={open,planHtml};
})(globalThis);
