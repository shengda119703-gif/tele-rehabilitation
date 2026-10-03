'use strict';
let liveSession=null;
function mountAssessmentExtras(){
  const box=document.createElement('div');box.className='feature-links';
  box.innerHTML='<button class="secondary" id="posture-entry">站姿体态评估</button><button class="secondary" id="body-entry">身体汇总</button>';
  $('.hero').after(box);
  $('#posture-entry').onclick=()=>navigate('posture');$('#body-entry').onclick=()=>navigate('body');
  const button=document.createElement('button');button.className='secondary feature-entry';button.textContent='打开实时动作指导';button.onclick=livePage;$('#guide').append(button);
}
function posturePage(){
  if(!state.postureCatalog?.length){toast('请刷新页面加载体态评估');return;}
  const ex=state.postureCatalog.find(x=>x.id===state.selected)||state.postureCatalog[0];state.selected=ex.id;
  app.innerHTML=`<div class="page-head"><h1>站姿体态评估</h1><p>自然站立，分别录制正面和侧面。</p></div><div class="chips">${state.postureCatalog.map(x=>`<button class="chip ${ex.id===x.id?'selected':''}" data-posture="${x.id}">${esc(x.label)}</button>`).join('')}</div><div class="steps"><span class="current">01 摆好机位</span><span>02 拍摄上传</span><span>03 查看结果</span></div><div class="card"><h2>${esc(ex.label)}</h2><label class="consent">靠近镜头的一侧 <select id="posture-side"><option value="left">本人左侧</option><option value="right">本人右侧</option></select></label>${ex.steps.map((x,i)=>`<div class="instruction"><span class="number">${i+1}</span><p>${esc(x)}</p></div>`).join('')}<button class="primary" id="camera-btn">拍摄视频</button><button class="secondary" id="gallery-btn">选择视频</button><input type="file" accept="video/*" capture="environment" id="camera-file" hidden><input type="file" accept="video/*" id="gallery-file" hidden><div id="file-area"></div><details><summary>测量范围</summary>观察肩线、髋线、躯干与耳肩位置。不诊断骨盆前倾、圆肩或脊柱侧弯。</details></div>`;
  document.querySelectorAll('[data-posture]').forEach(b=>b.onclick=()=>{clearFile();state.selected=b.dataset.posture;posturePage();});
  $('#posture-side').value=state.side;$('#posture-side').onchange=e=>{clearFile();state.side=e.target.value;posturePage();};
  $('#camera-btn').onclick=()=>$('#camera-file').click();$('#gallery-btn').onclick=()=>$('#gallery-file').click();
  for(const id of ['camera-file','gallery-file'])$('#'+id).onchange=e=>chooseFile(e.target.files[0]);fileArea();
}
function postureMetrics(summary){return `<div class="stat-grid posture-metrics">${(summary.metrics||[]).map(m=>`<div class="stat"><small>${esc(m.label)}</small><strong>${m.valid?number(m.value,m.unit):'未测得'}</strong><p>${esc(m.valid?m.note:m.reason)}</p></div>`).join('')}</div>`;}
function renderPostureReport(j){
  const r=j.result;app.innerHTML=`<button class="back" id="posture-back">‹ 返回记录</button><div class="page-head"><h1>${esc(label(j.exercise))}报告</h1><p>${dateLabel(j.created_at)} · ${sideLabel(j.side)}</p></div><div class="card">${postureMetrics(r.summary)}<p class="caption">${esc(r.summary.note)}</p><details><summary>测量说明</summary>${r.limitations.map(esc).join('<br>')}</details><button class="secondary report-print" id="print-report">打印 / 存为 PDF</button><button class="secondary" id="posture-body">查看身体汇总</button></div>${j.video_available?`<div class="card"><video class="report-video" controls playsinline src="/api/jobs/${j.id}/video"></video><button class="danger" id="posture-delete">删除录像，保留结果</button></div>`:''}`;
  $('#posture-back').onclick=()=>navigate('history');$('#print-report').onclick=()=>window.print();$('#posture-body').onclick=()=>navigate('body');
  if($('#posture-delete'))$('#posture-delete').onclick=async()=>{if(!confirm('删除本次原始录像？结果会保留，录像无法恢复。'))return;try{await api('/jobs/'+j.id+'/video',{method:'DELETE'});showJob(j.id);}catch(e){toast(e.message);}};
}
function reportRow(r){
  const s=r.summary||{};
  const posture=(Array.isArray(s.metrics)?s.metrics:[]).filter(m=>m.valid).map(m=>`${esc(m.label)} ${number(m.value,esc(m.unit))}`).join('<br>')||'暂无有效体态数据';
  return `<tr><td>${esc(r.label||label(r.exercise))}<br><small>${sideLabel(r.side)} · ${dateLabel(r.created_at)}</small></td><td>${r.mode==='posture'?posture:r.mode==='training'?`${s.completed??0} 次 · ${s.plan_completed?'完成目标':'查看详情'}`:`${s.completed??0} 次${s.motion_range?' · 幅度 '+number(s.motion_range.range_deg,'°'):''}`}</td></tr>`;
}
async function bodyPage(){
  app.innerHTML='<div class="page-head"><h1>身体与训练汇总</h1></div><p class="loading">正在读取…</p>';
  try{const data=await api('/body');if(state.tab!=='body')return;
    app.innerHTML=`<div class="page-head"><h1>身体与训练汇总</h1><p>${data.total} 次记录 · ${data.training_count} 次康复训练</p></div><div class="card"><h2>${esc(data.next_step.title)}</h2><button class="primary" id="body-next">${data.next_step.job_id?'查看上次训练':'前往训练中心'}</button></div><div class="card"><h2>最近评估</h2>${data.latest.length?`<table class="care-table"><thead><tr><th>项目</th><th>结果</th></tr></thead><tbody>${data.latest.map(reportRow).join('')}</tbody></table>`:'<p class="tip">完成评估后自动汇总到这里。</p>'}<p class="tip">${esc(data.note)}</p><button class="secondary" id="body-print">打印 / 存为 PDF</button></div><div class="card"><h2>报告与随访</h2><p class="tip">将本次摘要分享给家人或康复师，不分享原始录像。</p><button class="primary" id="create-share">生成7天分享链接</button><div id="share-result"></div><div id="share-list"></div></div><div class="card"><h2>近期训练</h2>${data.records.filter(r=>r.mode==='training').slice(0,10).map(r=>`<button class="record" data-body-job="${r.id}"><span>${esc(label(r.exercise))}<small>${dateLabel(r.created_at)} · ${r.feedback?'疼痛 '+r.feedback.pain+' / 疲劳 '+r.feedback.fatigue:'待补充感受'}</small></span><span>查看 ›</span></button>`).join('')||'<p class="tip">暂无训练记录</p>'}</div>`;
    $('#body-next').onclick=()=>data.next_step.job_id?showJob(data.next_step.job_id):navigate('plan');$('#body-print').onclick=()=>window.print();
    document.querySelectorAll('[data-body-job]').forEach(b=>b.onclick=()=>showJob(b.dataset.bodyJob));
    $('#create-share').onclick=async()=>{if(!confirm('分享当前评估和训练摘要？持有链接的人可查看并留言，不包含原始录像。'))return;try{const s=await api('/care/shares',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({consent:true})});const url=location.origin+'/#care='+encodeURIComponent(s.code);$('#share-result').innerHTML=`<p class="tip">复制链接发送给对方。目前对方需要能访问这台电脑。</p><p class="access-code">${esc(url)}</p>`;loadShares();}catch(e){toast(e.message);}};
    loadShares();
  }catch(e){toast(e.message);}
}
async function loadShares(){
  try{const rows=await api('/care/shares');if(!$('#share-list'))return;$('#share-list').innerHTML=rows.map(s=>`<div class="plan-item"><p>${s.active?'分享有效':'分享已失效'} · 截止 ${new Date(s.expires*1000).toLocaleDateString()}</p>${s.notes.map(n=>`<p class="share-notes"><strong>${esc(n.author)}（身份未核验）</strong>：${esc(n.text)}</p>`).join('')}${s.active?`<button class="secondary" data-revoke="${s.id}">撤销分享</button>`:''}</div>`).join('');document.querySelectorAll('[data-revoke]').forEach(b=>b.onclick=async()=>{try{await api('/care/shares/'+b.dataset.revoke,{method:'DELETE'});loadShares();}catch(e){toast(e.message);}});}catch(e){toast(e.message);}
}
function carePage(){
  state.tab='care';app.innerHTML='<div class="page-head"><h1>查看分享报告</h1><p>只读摘要，不包含录像。留言不会自动修改训练计划。</p></div><div class="card"><form class="care-form" id="care-open"><label for="care-code">分享码</label><input id="care-code" required maxlength="100" autocomplete="off"><button class="primary">查看报告</button></form></div><div id="care-report"></div>';
  $('#care-code').value=state.shareCode||'';$('#care-open').onsubmit=e=>{e.preventDefault();viewCare($('#care-code').value.trim());};if(state.shareCode)viewCare(state.shareCode);
}
async function viewCare(code){
  try{const data=await api('/care/view',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code})});if(state.tab!=='care')return;const r=data.report;
    $('#care-report').innerHTML=`<div class="card"><h2>分享时的报告摘要</h2><table class="care-table"><tbody>${r.latest.map(reportRow).join('')}</tbody></table><p class="tip">${esc(r.next_step.title)}。此页不是实时监护。</p></div><div class="card"><h2>留言</h2>${data.notes.map(n=>`<p class="share-notes">${esc(n.author)}（身份未核验）：${esc(n.text)}</p>`).join('')}<form class="care-form" id="care-note"><label for="care-author">你的称呼</label><input id="care-author" required maxlength="40"><label for="care-text">留言内容</label><textarea id="care-text" required maxlength="1000"></textarea><button class="primary">发送留言</button></form></div>`;
    $('#care-note').onsubmit=async e=>{e.preventDefault();try{await api('/care/note',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code,author:$('#care-author').value,text:$('#care-text').value})});viewCare(code);}catch(err){toast(err.message);}};
  }catch(e){if($('#care-report'))$('#care-report').innerHTML='<div class="card"><p>'+esc(e.message)+'</p></div>';}
}
function mountDeviceExtras(){
  mountNetwork();
  app.insertAdjacentHTML('beforeend','<div class="card"><h2>在另一台设备继续</h2><p class="tip">手机和电脑浏览器可使用同一份网页档案。不会自动合并桌面软件里的患者资料。</p><button class="primary" id="create-link">生成我的档案连接码</button><div id="link-result"></div><details><summary>接入另一台设备的档案</summary><form class="care-form" id="link-form"><label for="link-code">另一设备生成的档案连接码</label><input id="link-code" required maxlength="100" autocomplete="off"><button class="secondary">接入该档案</button></form></details><button class="secondary" id="device-body">查看身体汇总与随访</button><button class="secondary" id="device-care">查看他人分享的报告</button></div>');
  $('#device-body').onclick=()=>navigate('body');$('#device-care').onclick=()=>navigate('care');
  $('#create-link').onclick=async()=>{try{const data=await api('/account/link-code',{method:'POST'});$('#link-result').innerHTML='<p class="tip">10分钟内在另一设备的“设备连接”中输入。仅给自己的设备使用。</p><p class="access-code">'+esc(data.code)+'</p>';}catch(e){toast(e.message);}};
  $('#link-form').onsubmit=async e=>{e.preventDefault();if(!confirm('切换到该设备的档案？当前档案不会合并或删除。建议先保留当前档案连接码，以便返回。'))return;try{await api('/account/link',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:$('#link-code').value.trim(),confirm_switch:true})});state.jobs=[];navigate('body');}catch(err){toast(err.message);}};
}
function livePage(){
  clearFile();const ex=selected();
  app.innerHTML=`<button class="back" id="live-back">‹ 返回评估</button><div class="page-head"><h1>${esc(ex.label)} · 实时指导</h1><p>${esc(ex.instructions.camera)}</p></div><div class="card"><div class="live-preview mirrored"><video id="live-video" autoplay playsinline muted></video><canvas id="live-overlay"></canvas></div><div class="live-cue" id="live-cue" aria-live="polite">摆好手机，点击开始</div><div class="live-stats"><span id="live-count">0 次</span><span id="live-angle">—</span></div><p class="caption live-status" id="live-status"></p><label class="consent">镜头 <select id="live-facing"><option value="user">前置摄像头</option><option value="environment">后置摄像头</option></select></label><label class="consent"><input id="live-voice" type="checkbox">语音提示</label><label class="consent"><input id="live-consent" type="checkbox">同意将实时画面传到电脑分析，不保存画面。</label><div class="live-controls"><button class="primary" id="live-start">开始指导</button><button class="danger" id="live-stop" disabled>停止</button></div><p class="tip">这是实时练习指导，结束后不保存为评估依据。需要报告时请录制上传；疼痛、头晕或不适时停止。</p></div>`;
  $('#live-back').onclick=()=>navigate('assess');$('#live-start').onclick=startLive;$('#live-stop').onclick=()=>stopLive();
  if(!window.isSecureContext||!navigator.mediaDevices?.getUserMedia){$('#live-start').disabled=true;$('#live-status').textContent='当前 HTTP 地址不能调用实时相机。请使用可信 HTTPS 地址，或返回录制上传。';}
}
async function startLive(){
  if(!$('#live-consent').checked){toast('请先同意本次实时分析');return;}
  const session={cancelled:false,stream:null,id:null,lastVoice:'',lastSpoken:0,request:null};liveSession=session;$('#live-start').disabled=true;$('#live-stop').disabled=false;
  $('#live-status').textContent='正在打开摄像头…';
  try{
    const facing=$('#live-facing').value;
    session.stream=await navigator.mediaDevices.getUserMedia({audio:false,video:{facingMode:{ideal:facing},width:{ideal:640},height:{ideal:480}}});
    if(session.cancelled){session.stream.getTracks().forEach(t=>t.stop());return;}
    const video=$('#live-video');video.srcObject=session.stream;await video.play();$('.live-preview').classList.toggle('mirrored',facing==='user');
    const data=await api('/live',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({exercise:state.selected,side:state.side,consent:true})});session.id=data.id;
    if(session.cancelled){await api('/live/'+session.id,{method:'DELETE'});return;}
    $('#live-facing').disabled=true;$('#live-status').textContent='正在启动分析…';
    const canvas=document.createElement('canvas');session.canvas=canvas;
    await liveLoop(session);
  }catch(e){if(!session.cancelled){toast(e.name==='NotAllowedError'?'请允许浏览器使用摄像头':e.message);stopLive();}}
}
async function liveLoop(session){
  while(!session.cancelled){
    const video=$('#live-video');if(!video||document.hidden){stopLive();return;}
    const scale=Math.min(1,640/video.videoWidth),canvas=session.canvas;
    canvas.width=Math.round(video.videoWidth*scale);canvas.height=Math.round(video.videoHeight*scale);
    canvas.getContext('2d').drawImage(video,0,0,canvas.width,canvas.height);
    const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',.75));
    if(session.cancelled)return;if(!blob)throw Error('摄像头没有返回画面');
    session.request=new AbortController();const timeout=setTimeout(()=>session.request.abort(),30000);
    let data;try{data=await api('/live/'+session.id+'/frame',{method:'POST',headers:{'Content-Type':'image/jpeg'},body:blob,signal:session.request.signal});}finally{clearTimeout(timeout);}
    if(session.cancelled)return;
    $('#live-count').textContent=(data.summary.completed??0)+' 次';$('#live-angle').textContent=data.valid?number(data.summary.metrics?.[data.summary.primary_metric]?.value,'°'):'—';
    const cue=data.cue.instruction;$('#live-cue').textContent=cue;$('#live-status').textContent=data.valid?'正在指导 · '+Math.round(data.inference_ms)+' ms':(data.cue.status||'正在识别');
    const overlay=$('#live-overlay');overlay.width=canvas.width;overlay.height=canvas.height;const ctx=overlay.getContext('2d');ctx.clearRect(0,0,overlay.width,overlay.height);ctx.fillStyle='#b6ffb3';for(const [x,y]of data.points){ctx.beginPath();ctx.arc(x*overlay.width,y*overlay.height,4,0,Math.PI*2);ctx.fill();}
    if($('#live-voice').checked&&'speechSynthesis'in window&&cue!==session.lastVoice&&Date.now()-session.lastSpoken>3500){speechSynthesis.cancel();const utterance=new SpeechSynthesisUtterance(cue);utterance.lang='zh-CN';speechSynthesis.speak(utterance);session.lastVoice=cue;session.lastSpoken=Date.now();}
    await new Promise(resolve=>setTimeout(resolve,80));
  }
}
function stopLive(){
  const session=liveSession;if(!session)return;liveSession=null;session.cancelled=true;session.request?.abort();session.stream?.getTracks().forEach(t=>t.stop());
  if('speechSynthesis'in window)speechSynthesis.cancel();if(session.id)fetch('/api/live/'+session.id,{method:'DELETE',headers:{'X-Rehab-Client':'mobile-v1'},keepalive:true}).catch(()=>{});
  if($('#live-start')){$('#live-start').disabled=false;$('#live-stop').disabled=true;$('#live-facing').disabled=false;$('#live-status').textContent='已停止，摄像头已关闭';$('#live-cue').textContent='本次指导已结束';const canvas=$('#live-overlay');canvas.getContext('2d').clearRect(0,0,canvas.width,canvas.height);}
}
document.addEventListener('visibilitychange',()=>{if(document.hidden)stopLive();});
window.addEventListener('pagehide',stopLive);

async function mountNetwork(){
  const old=document.querySelector('.layout > .card');if(old)old.remove();
  const section=document.createElement('section');section.className='card';section.id='network-devices';app.append(section);
  try{const cameras=await api('/cameras');if(!$('#network-devices'))return;
    section.innerHTML=`<h2>网络摄像头</h2>${cameras.length?`<form class="care-form" id="network-form"><label for="network-camera">选择摄像头</label><select id="network-camera">${cameras.map(c=>`<option value="${esc(c.id)}">${esc(c.name)}</option>`).join('')}</select><button class="secondary" type="button" id="network-test">测试画面</button><div id="network-preview"></div><label for="network-action">录制项目</label><select id="network-action">${[['assessment',state.catalog],['posture',state.postureCatalog],['fitness',state.fitnessCatalog]].map(([mode,items])=>`<optgroup label="${{assessment:'康复评估',posture:'体态评估',fitness:'健身分析'}[mode]}">${(items||[]).map(x=>`<option value="${mode}:${x.id}">${esc(x.label)}</option>`).join('')}</optgroup>`).join('')}</select><label for="network-side">测试侧</label><select id="network-side"><option value="left">本人左侧</option><option value="right">本人右侧</option></select><label for="network-seconds">录制秒数</label><input type="number" id="network-seconds" min="5" max="60" value="15" required><label class="consent"><input type="checkbox" required>同意电脑录制并保存摄像头画面，用于本次分析。</label><button class="primary">开始录制并分析</button><p class="tip">请先测试画面并摆好姿势。录制后可从记录页删除视频。</p></form>`:'<p class="status-text">尚未配置摄像头</p><p class="tip">已支持 RTSP 测试画面、定时录制和分析。购买摄像头后，在电脑端添加地址即可使用；地址与密码不会发到手机页面。</p>'}`;
    if(!cameras.length)return;
    $('#network-test').onclick=async()=>{const button=$('#network-test');button.disabled=true;try{const response=await fetch('/api/cameras/'+$('#network-camera').value+'/test',{method:'POST',headers:{'X-Rehab-Client':'mobile-v1'}});if(!response.ok){const err=await response.json();throw Error(err.detail);}const url=URL.createObjectURL(await response.blob());const box=$('#network-preview');if(!box){URL.revokeObjectURL(url);return;}const img=document.createElement('img');img.alt='摄像头当前画面';img.className='report-video';img.onload=()=>URL.revokeObjectURL(url);img.src=url;box.replaceChildren(img);}catch(e){toast(e.message);}finally{button.disabled=false;}};
    $('#network-form').onsubmit=async e=>{e.preventDefault();const [mode,exercise]=$('#network-action').value.split(':');const b=e.currentTarget.querySelector('.primary');b.disabled=true;try{const r=await api('/cameras/'+$('#network-camera').value+'/record',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode,exercise,side:$('#network-side').value,seconds:Number($('#network-seconds').value),consent:true})});showJob(r.id);}catch(err){toast(err.message);b.disabled=false;}};
  }catch(e){section.textContent=e.message;}
}
