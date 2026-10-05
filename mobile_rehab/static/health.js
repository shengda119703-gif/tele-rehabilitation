'use strict';
// Personal health modules reuse Ankang; drafts stay in memory, never localStorage.
let healthData=null, healthGeneration=0, healthDraft='';
const healthTitles={more:'我的',health:'健康指标',medication:'我的用药',assistant:'健康管家',archive:'健康资料',family:'家庭照护'};
const healthPost=(operation,body)=>api('/product/'+operation,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
function resetHealth(){healthData=null;healthDraft='';healthGeneration++;}
function healthLinks(entries){return entries.map(([tab,title,sub])=>`<button class="health-entry" data-health-nav="${tab}"><span><strong>${title}</strong>${sub?`<small>${sub}</small>`:''}</span><span aria-hidden="true">›</span></button>`).join('');}
function bindHealthLinks(){document.querySelectorAll('[data-health-nav]').forEach(b=>b.onclick=()=>navigate(b.dataset.healthNav));}
function healthShell(tab,body){return `${tab==='more'?'':'<button class="back" id="health-back">返回我的</button>'}<div class="page-head"><h1>${healthTitles[tab]}</h1></div>${body}`;}
async function healthPage(){
  const tab=state.tab, generation=++healthGeneration;
  app.innerHTML=healthShell(tab,'<p class="loading" role="status">正在读取…</p>');
  if($('#health-back'))$('#health-back').onclick=()=>navigate('more');
  try{
    const data=await api('/product');
    if(generation!==healthGeneration||state.tab!==tab)return;
    healthData=data;
    if(tab==='more')myHealthPage(data);
    else if(data.needs_profile)profilePage({},'建立健康档案');
    else if(tab==='health')healthMetricsPage(data);
    else if(tab==='medication')medicationPage(data);
    else if(tab==='assistant')assistantPage(data);
    else if(tab==='archive')archivePage(data);
    else familyPage(data);
    if($('#health-back'))$('#health-back').onclick=()=>navigate('more');
    bindHealthLinks();
  }catch(e){
    if(generation!==healthGeneration||state.tab!==tab)return;
    app.innerHTML=healthShell(tab,`<div class="card"><p role="alert">${esc(e.message)}</p><button class="secondary" id="health-retry">重试</button></div>${healthLinks([['device','设备连接'],['body','身体汇总']])}`);
    $('#health-retry').onclick=healthPage;if($('#health-back'))$('#health-back').onclick=()=>navigate('more');bindHealthLinks();
  }
}
function myHealthPage(data){
  const p=data.snapshot?.profile.profile;
  app.innerHTML=healthShell('more',`<section class="card health-profile"><h2>${p?esc(p.name):'我的健康档案'}</h2><p class="caption">${p?`${p.age} 岁`:'添加称呼和年龄，开启健康记录。'}</p><button class="secondary" id="health-profile">${p?'编辑档案':'建立档案'}</button></section><section class="health-menu">${healthLinks([['health','健康指标','血压、血糖、睡眠与活动'],['medication','我的用药','药物与今日安排'],['assistant','健康管家','记录感受，查看下一步'],['archive','健康资料','检查报告与就诊资料'],['family','家庭照护','分享摘要、查看留言'],['body','身体汇总','评估与训练结果'],['device','设备连接','相机与跨设备档案']])}</section>${p?'<a class="secondary health-download" href="/api/product-backup" download>导出健康备份</a>':''}`);
  $('#health-profile').onclick=()=>profilePage(p||{});
}
function profilePage(p={},title='编辑健康档案'){
  app.innerHTML=`<button class="back" id="health-back">返回我的</button><div class="page-head"><h1>${title}</h1></div><form class="card care-form" id="profile-form"><label for="health-name">称呼</label><input id="health-name" required maxlength="40" value="${esc(p.name)}"><label for="health-age">年龄</label><input id="health-age" type="number" required min="0" max="130" step="1" value="${esc(p.age)}"><label for="health-conditions">已知疾病或活动限制（选填，逗号分隔）</label><textarea id="health-conditions" maxlength="1000">${esc((p.conditions||[]).join('，'))}</textarea><details><summary>联系信息（选填）</summary><label for="family-name">家人称呼</label><input id="family-name" maxlength="40" value="${esc(p.familyContact)}"><label for="family-phone">家人电话</label><input id="family-phone" type="tel" maxlength="30" value="${esc(p.familyPhone)}"><label for="doctor-phone">医生电话</label><input id="doctor-phone" type="tel" maxlength="30" value="${esc(p.communityDoctorPhone)}"><label for="my-phone">本人电话</label><input id="my-phone" type="tel" maxlength="30" value="${esc(p.elderPhone)}"></details><button class="primary">保存档案</button><p class="caption">仅保存到当前电脑，不自动同步到桌面患者库。</p></form>`;
  $('#health-back').onclick=()=>navigate('more');
  healthForm('profile-form',()=>healthPost('profile.save',{profile:{name:$('#health-name').value,age:Number($('#health-age').value),conditions:$('#health-conditions').value.split(/[,，\n]/).map(x=>x.trim()).filter(Boolean),familyContact:$('#family-name').value,familyPhone:$('#family-phone').value,communityDoctorPhone:$('#doctor-phone').value,elderPhone:$('#my-phone').value}}));
}
function healthForm(id,action,success=healthPage){
  const form=$('#'+id), tab=state.tab;
  form.onsubmit=async e=>{e.preventDefault();const b=form.querySelector('button.primary');if(b.disabled)return;b.disabled=true;
    try{await action();if(state.tab===tab&&$('#'+id)===form){toast('已保存');success();}}
    catch(err){toast(err.message);}finally{b.disabled=false;}
  };
}
function metricName(metric){return healthData?.metrics.find(m=>m[0]===metric)?.[1]||metric;}
function healthMeasurements(data){return data.snapshot.state.healthData.measurements||[];}
function latestMeasurements(data){const map=new Map();for(const row of [...healthMeasurements(data)].sort((a,b)=>b.timestamp.localeCompare(a.timestamp)))if(!map.has(row.metric))map.set(row.metric,row);return [...map.values()];}
function measurementRows(rows){return rows.map(r=>`<div class="health-value"><span>${esc(metricName(r.metric))}<small>${dateLabel(r.timestamp)}</small></span><strong>${number(r.value)} <small>${esc(r.unit)}</small></strong></div>`).join('');}
function sharedHealthMarkup(health){
  const names={steps:'活动步数',walkSpeed:'步行速度',sleepHours:'睡眠时长',nightWakes:'夜间醒来',restingHr:'静息心率',weight:'体重',spo2:'血氧',systolic:'收缩压',diastolic:'舒张压',bloodGlucose:'血糖'};
  return `<section class="card"><h2>健康指标</h2>${health.measurements.map(r=>`<div class="health-value"><span>${esc(names[r.metric]||r.metric)}</span><strong>${number(r.value)} <small>${esc(r.unit)}</small></strong></div>`).join('')||'<p class="caption">暂无指标</p>'}<h2>在用药物</h2>${health.medications.map(r=>`<p>${esc(r.name)} · ${esc(r.dose)} · ${esc(r.times)}</p>`).join('')||'<p class="caption">暂无药物记录</p>'}</section>`;
}
function healthMetricsPage(data){
  const latest=latestMeasurements(data), all=[...healthMeasurements(data)].sort((a,b)=>b.timestamp.localeCompare(a.timestamp));
  app.innerHTML=healthShell('health',`<section class="card"><h2>最近记录</h2>${measurementRows(latest)||'<p class="caption">还没有指标记录</p>'}</section><form class="card care-form" id="metric-form"><h2>记录指标</h2><label for="metric-key">指标</label><select id="metric-key">${data.metrics.map(([key,name,unit])=>`<option value="${key}">${name} · ${unit}</option>`).join('')}</select><label for="metric-value">数值</label><input id="metric-value" type="number" step="any" min="0" max="100000" required><button class="primary">保存记录</button></form><section class="card"><h2>记录趋势</h2><label for="trend-key" class="caption">选择指标</label><select id="trend-key">${data.metrics.map(([key,name])=>`<option value="${key}">${name}</option>`).join('')}</select><div id="metric-trend"></div></section><details class="card"><summary>全部记录 · ${all.length} 条</summary>${measurementRows(all.slice(0,100))}</details>`);
  healthForm('metric-form',()=>healthPost('health.record',{metric:$('#metric-key').value,value:Number($('#metric-value').value)}));
  const trend=()=>{const key=$('#trend-key').value,delta=data.snapshot.trends?.[key]?.deltaText;$('#metric-trend').innerHTML=(delta?`<p>${esc(delta)}</p>`:'')+metricTrendMarkup(all.filter(r=>r.metric===key).slice(0,14).reverse());};
  $('#trend-key').value=latest[0]?.metric||'steps';$('#trend-key').onchange=trend;trend();
  const report=data.snapshot.history?.report;
  if(report)app.insertAdjacentHTML('beforeend',`<details class="card"><summary>本周健康汇总</summary><p class="caption">${esc(report.rangeText)}</p>${report.sections.map(s=>`<h3>${esc(s.title)}</h3>${s.lines.map(line=>`<p>${esc(line)}</p>`).join('')}`).join('')}<p class="caption">仅汇总已记录内容，不作为诊断。</p></details>`);
}
function metricTrendMarkup(rows){
  if(!rows.length)return '<p class="caption">暂无记录</p>';
  if(rows.length<2)return measurementRows(rows);
  const values=rows.map(r=>r.value), min=Math.min(...values), max=Math.max(...values),span=max-min||1;
  const points=values.map((v,i)=>`${12+i*276/(values.length-1)},${90-(v-min)*70/span}`).join(' ');
  return `<svg class="health-chart" viewBox="0 0 300 110" role="img" aria-label="最近 ${rows.length} 次记录趋势，最低 ${min}，最高 ${max}"><line x1="12" y1="90" x2="288" y2="90" stroke="#e7e7e7"/><polyline points="${points}" fill="none" stroke="#20b985" stroke-width="3"/></svg><p class="caption">${dateLabel(rows[0].timestamp)} — ${dateLabel(rows.at(-1).timestamp)} · ${esc(rows[0].unit)}</p><details><summary>查看数值</summary>${measurementRows(rows)}</details>`;
}
function medicationPage(data){
  const records=data.snapshot.profile.profile.medicationRecords||[], tasks=data.snapshot.state.tasks.filter(t=>t.kind==='medication_check');
  app.innerHTML=healthShell('medication',`<section class="card"><h2>药物清单</h2>${records.map(r=>`<div class="health-drug"><strong>${esc(r.name)}</strong><p class="caption">${esc([r.dose,r.times].filter(Boolean).join(' · '))||'未填写用量与时间'} · ${r.status==='active'?'在用':'已停用'}</p>${r.purpose?`<p>${esc(r.purpose)}</p>`:''}<div class="health-actions"><button class="secondary" data-med-edit="${esc(r.id)}">编辑</button><button class="secondary" data-med-status="${esc(r.id)}" data-status="${r.status==='active'?'stopped':'active'}">${r.status==='active'?'标记停用':'恢复在用'}</button></div></div>`).join('')||'<p class="caption">还没有药物记录</p>'}</section><section class="card"><h2>今日用药安排</h2>${tasks.map(taskMarkup).join('')||'<p class="caption">目前没有用药待办</p>'}<p class="caption">按既有医嘱填写，不自动调整药物或剂量。</p></section><form class="card care-form" id="med-form"><h2 id="med-form-title">添加药物</h2><input id="med-id" type="hidden"><label for="med-name">药物名称</label><input id="med-name" required maxlength="100"><label for="med-dose">医嘱用量（选填）</label><input id="med-dose" maxlength="100"><label for="med-times">服用时间（选填）</label><input id="med-times" maxlength="100" placeholder="如：每天早餐后"><label for="med-purpose">用途（选填）</label><input id="med-purpose" maxlength="200"><button class="primary">保存药物</button><button class="secondary" type="button" id="med-cancel">清空</button></form>`);
  healthForm('med-form',()=>healthPost('medication.save',{record:{id:$('#med-id').value||newLocalId(),name:$('#med-name').value,dose:$('#med-dose').value,times:$('#med-times').value,purpose:$('#med-purpose').value,status:records.find(r=>r.id===$('#med-id').value)?.status||'active'}}));
  $('#med-cancel').onclick=()=>{$('#med-form').reset();$('#med-id').value='';$('#med-form-title').textContent='添加药物';};
  document.querySelectorAll('[data-med-edit]').forEach(b=>b.onclick=()=>{const r=records.find(r=>r.id===b.dataset.medEdit);for(const key of ['id','name','dose','times','purpose'])$('#med-'+key).value=r[key]||'';$('#med-form-title').textContent='编辑药物';$('#med-form').scrollIntoView({behavior:'smooth',block:'start'});});
  document.querySelectorAll('[data-med-status]').forEach(b=>b.onclick=async()=>{b.disabled=true;try{await healthPost('medication.status',{id:b.dataset.medStatus,status:b.dataset.status});if(state.tab==='medication')healthPage();}catch(e){toast(e.message);b.disabled=false;}});
  bindTasks();
}
function newLocalId(){const bytes=new Uint8Array(16);crypto.getRandomValues(bytes);return Array.from(bytes,x=>x.toString(16).padStart(2,'0')).join('');}
function taskMarkup(t){const done=['completed','dismissed'].includes(t.status);return `<div class="health-task"><strong>${esc(t.title)}</strong><p class="caption">${esc(t.description)}</p>${done?`<small>${t.status==='completed'?'已完成':'已跳过'}</small>`:`<button class="secondary" data-health-task="${esc(t.id)}">确认已完成</button>`}</div>`;}
function bindTasks(){document.querySelectorAll('[data-health-task]').forEach(b=>b.onclick=async()=>{b.disabled=true;const tab=state.tab;try{await healthPost('task.status',{id:b.dataset.healthTask,status:'completed'});if(state.tab===tab)healthPage();}catch(e){toast(e.message);b.disabled=false;}});}
function assistantPage(data){
  const s=data.snapshot.state;
  app.innerHTML=healthShell('assistant',`<section class="health-quick">${healthLinks([['body','看评估结果'],['plan','看训练安排']])}</section><section class="card health-chat" aria-label="管家对话">${s.chat.map(m=>`<div class="health-message ${m.role==='elder'?'mine':''}"><small>${m.role==='elder'?'我':'管家'}${m.persisted===false?' · 本次不记录':''}</small><p>${esc(m.text)}</p></div>`).join('')||'<p class="caption">可以记录今天的感受，或询问健康与用药安排。</p>'}</section><form class="card care-form" id="chat-form"><label for="health-chat">说说今天的情况</label><textarea id="health-chat" required maxlength="1900" rows="3">${esc(healthDraft)}</textarea><label class="consent"><input id="chat-private" type="checkbox"><span>本次不记录</span></label><button class="primary">发送</button><p class="caption">本地规则助手。紧急不适请直接求助。</p><button class="secondary" id="phone-voice" type="button" hidden>选择手机录音</button><input type="file" accept="audio/*" capture id="phone-audio" hidden><p id="voice-status" class="caption" role="status"></p></form><details class="card"><summary>今日待办 · ${s.tasks.length} 项</summary>${s.tasks.map(taskMarkup).join('')||'<p class="caption">暂无待办</p>'}</details>`);
  $('#health-chat').oninput=e=>{healthDraft=e.target.value;};
  healthForm('chat-form',()=>healthPost('chat',{text:$('#health-chat').value,private:$('#chat-private').checked}),()=>{healthDraft='';healthPage();});
  bindTasks();bindHealthLinks();mountPhoneVoice();
}
function archivePage(data){
  app.innerHTML=healthShell('archive',`<section class="card"><h2>我的资料</h2>${data.snapshot.attachments.map(a=>`<a class="health-entry" href="/api/product-archive/${encodeURIComponent(a.id)}" download><span><strong>${esc(a.name)}</strong><small>${esc(a.category)} · ${number(a.size/1024,' KB')}</small></span><span>下载</span></a>`).join('')||'<p class="caption">暂无资料</p>'}</section><form class="card care-form" id="archive-form"><h2>添加资料</h2><label for="archive-name">资料名称</label><input id="archive-name" maxlength="100" required><label for="archive-category">分类</label><select id="archive-category">${data.categories.map(c=>`<option>${c}</option>`).join('')}</select><label for="archive-file">文件（最多 8 MB）</label><input id="archive-file" type="file" accept=".pdf,.jpg,.jpeg,.png,.mp4,.txt" required><label class="consent"><input id="archive-consent" type="checkbox" required><span>同意将这份资料保存到电脑，默认仅自己可见。</span></label><button class="primary">保存资料</button></form>`);
  healthForm('archive-form',()=>{const file=$('#archive-file').files[0];if(!file||file.size>8*1024*1024)throw Error('请选择 8 MB 以内的资料');if(!$('#archive-consent').checked)throw Error('请确认保存资料');return api('/product-archive?consent=yes&name='+encodeURIComponent($('#archive-name').value)+'&category='+encodeURIComponent($('#archive-category').value),{method:'POST',headers:{'Content-Type':file.type||'application/octet-stream'},body:file});});
}
function dialLink(phone,title){const clean=String(phone||'').replace(/[\s-]/g,'');return /^\+?\d{3,20}$/.test(clean)?`<a class="secondary health-download" href="tel:${clean}">${esc(title)}</a>`:'';}
function familyPage(data){
  const p=data.snapshot.profile.profile;
  app.innerHTML=healthShell('family',`<section class="card"><h2>联系家人</h2>${dialLink(p.familyPhone,p.familyContact||'拨打家人电话')||'<p class="caption">尚未填写家人电话</p>'}${dialLink(p.communityDoctorPhone,'拨打医生电话')}<button class="secondary" id="family-profile">编辑联系信息</button></section><section class="card"><h2>分享健康摘要</h2><p class="caption">最近指标、在用药物、评估与训练结果。不包含对话、电话、资料或录像。</p><label class="consent"><input id="family-consent" type="checkbox"><span>同意分享这些内容，链接有效 7 天，可随时撤销。</span></label><button class="primary" id="family-share">生成分享链接</button><div id="family-share-result" aria-live="polite"></div><div id="share-list"></div></section><section class="health-menu">${healthLinks([['care','查看别人分享的报告']])}</section>`);
  $('#family-profile').onclick=()=>profilePage(p);
  $('#family-share').onclick=async()=>{if(!$('#family-consent').checked){toast('请先确认分享内容');return;}const b=$('#family-share');b.disabled=true;try{const share=await api('/product-share',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({consent:true})});if(state.tab!=='family'||!$('#family-share-result'))return;$('#family-share-result').innerHTML=`<p class="access-code">${esc(location.origin+'/#care='+encodeURIComponent(share.code))}</p><p class="caption">复制链接发送给对方；对方需能访问这台电脑。</p>`;loadShares();}catch(e){toast(e.message);}finally{b.disabled=false;}};
  loadShares();
}
async function mountPhoneVoice(){
  try{const status=await api('/product-voice');if(state.tab!=='assistant'||!$('#phone-voice'))return;
    if(!status.available){$('#voice-status').textContent='语音可使用手机键盘的语音输入。';return;}
    $('#phone-voice').hidden=false;$('#phone-voice').onclick=()=>$('#phone-audio').click();
    $('#phone-audio').onchange=async e=>{const file=e.target.files[0];if(!file)return;if(file.size>8*1024*1024){toast('请选择 8 MB 以内的短录音');return;}const b=$('#phone-voice');b.disabled=true;$('#voice-status').textContent='识别中…';try{const r=await api('/product-voice',{method:'POST',headers:{'Content-Type':file.type||'application/octet-stream'},body:file});if(state.tab==='assistant'&&$('#health-chat')){$('#health-chat').value=r.text;healthDraft=r.text;$('#voice-status').textContent='核对文字后点击发送。';}}catch(err){toast(err.message);}finally{b.disabled=false;}};
  }catch(e){if($('#voice-status'))$('#voice-status').textContent='语音可使用手机键盘的语音输入。';}
}
