'use strict';
const $ = (s) => document.querySelector(s);
const app = $('#app');
const state = {tab:'assess', catalog:[], joint:'shoulder', selected:'shoulder_abduction', side:'left', jobs:[], file:null, url:null, job:null, upload:null, training:null};
let pollTimer, toastTimer;
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number = (v, unit='') => Number.isFinite(v) ? `${Math.round(v*10)/10}${unit}` : '未测得';
const selected = () => state.catalog.find(x => x.id === state.selected);
const label = (id) => state.catalog.find(x => x.id === id)?.label || state.fitnessCatalog?.find(x => x.id === id)?.label || id;
const sideLabel = (s) => s === 'left' ? '左侧' : '右侧';
const dateLabel = (v) => new Date(v).toLocaleString('zh-CN', {month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'});
const statusLabel = (s) => ({uploading:'上传中',queued:'等待分析',analyzing:'分析中',done:'已完成',failed:'需重试'}[s] || s);
function toast(text) { $('#toast').textContent=text; $('#toast').hidden=false; clearTimeout(toastTimer); toastTimer=setTimeout(()=>$('#toast').hidden=true,6000); }
async function api(path, opts={}) {
  const res=await fetch('/api'+path,{...opts,headers:{'X-Rehab-Client':'mobile-v1',...opts.headers}});
  let body; try {body=await res.json();} catch {throw Error('电脑服务没有正常响应，请稍后重试');}
  if(!res.ok) {if(res.status===401 && path!=='/pair') {pairPage();} throw Error(typeof body.detail==='string'?body.detail:'请求未完成，请稍后重试');}
  return body;
}
function pairPage(){
  state.job=null;
  clearTimeout(pollTimer); $('.bottom-nav').hidden=true; $('#connection').textContent='等待连接';
  app.innerHTML=`<section class="pair"><span class="tag">你的手机 × 你的电脑</span><h1>让康复评估，<br>离你更近一点。</h1><p>手机和电脑连接同一 Wi-Fi，输入电脑启动窗口中的连接码。</p><form id="pair-form"><label class="caption" for="pair-code">电脑连接码</label><input id="pair-code" name="code" autocomplete="off" autocapitalize="none" spellcheck="false" placeholder="输入连接码" required maxlength="32"><button class="primary">连接我的电脑 →</button></form><p class="tip">视频仅发送到这台电脑，不上传公共云。当前为家庭局域网演示版，请勿在公共网络使用。</p></section>`;
  $('#pair-form').onsubmit=async e=>{e.preventDefault();const b=e.currentTarget.querySelector('button');b.disabled=true;try{await api('/pair',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:$('#pair-code').value.trim()})});await init();}catch(e){toast(e.message);b.disabled=false;}};
}
function clearFile(){if(state.url)URL.revokeObjectURL(state.url);state.file=null;state.url=null;state.barCalibration=null;}
function navigate(tab){
  if(state.upload){toast('正在上传，请先完成或取消上传');return;}
  clearTimeout(pollTimer);state.tab=tab;state.job=null;state.training=null;clearFile();
  if(tab==='assess'&&!selected()){state.selected='shoulder_abduction';state.joint='shoulder';}
  document.querySelectorAll('[data-tab]').forEach(b=>b.classList.toggle('active',b.dataset.tab===tab));
  render();window.scrollTo({top:0,behavior:'instant'});
}
function render(){if(state.tab==='assess')assessment();else if(state.tab==='history')history();else if(state.tab==='plan')plan();else if(state.tab==='fitness')fitnessPage();else devices();}
function assessment(){
  const ex=selected(), i=ex.instructions;
  const joints=[...new Map(state.catalog.map(x=>[x.joint,x.joint_label]))];
  app.innerHTML=`<section class="hero"><div class="hero-orbit" aria-hidden="true"></div><div class="eyebrow">A LITTLE MOVEMENT. A BETTER YOU.</div><h1>了解身体，<br>从一次小小的活动开始。</h1><p>手机拍摄 · 电脑分析 · 查看个人活动建议</p></section>
  <div class="steps"><span class="current">01 选择动作</span><span>02 拍摄上传</span><span>03 查看结果</span></div>
  <div class="layout"><section><div class="section-head"><h2>今天想了解哪里？</h2><small>按身体部位选择</small></div><div class="chips" aria-label="身体部位">${joints.map(([id,name])=>`<button class="chip ${id===state.joint?'selected':''}" data-joint="${id}" aria-pressed="${id===state.joint}">${esc(name)}</button>`).join('')}</div>
  <div class="exercise-grid">${state.catalog.filter(x=>x.joint===state.joint).map(x=>`<button class="exercise ${x.id===ex.id?'selected':''}" data-exercise="${x.id}" aria-pressed="${x.id===ex.id}"><strong>${esc(x.label)}</strong><small>${x.view==='frontal'?'正面':'侧面'}拍摄${x.experimental?' · 探索性观察':''}</small></button>`).join('')}</div>
  <div class="card tint"><span class="tag">拍摄小贴士</span><h3>手机放稳，留出活动空间</h3><p class="tip">优先横屏、720p 或 1080p 普通录像。开始先停留约 3 秒，再按提示完成舒适幅度的动作并返回。建议 15–40 秒，最长 2 分钟。</p><p class="tip">不追求极限幅度；疼痛、头晕或不适时立即停止。</p></div></section>
  <section><div class="card" id="guide"><span class="tag">${esc(i.view_label)}</span><h2>${esc(ex.label)}</h2><div class="side" aria-label="本人测试侧"><button data-side="left" class="${state.side==='left'?'selected':''}">本人左侧</button><button data-side="right" class="${state.side==='right'?'selected':''}">本人右侧</button></div>
  <div class="camera-note">${esc(i.camera)}</div>${[['1',i.start],['2',i.move],['3',i.return]].map(([n,t])=>`<div class="instruction"><span class="number">${n}</span><p>${esc(t)}</p></div>`).join('')}
  <details><summary>了解本次测量</summary>${esc(i.boundary)}<br>${esc(i.count)}</details></div>
  <div class="card"><div class="section-head"><h3>准备好就拍一段</h3><small>最长 2 分钟</small></div><button class="primary" id="camera-btn">打开手机相机录像</button><button class="secondary" id="gallery-btn">从相册选择 / 网络相机录像</button><input id="camera-file" type="file" accept="video/*" capture="environment" hidden><input id="gallery-file" type="file" accept="video/*" hidden><div id="file-area"></div><p class="tip">调用手机系统相机，录好后返回本页。如果浏览器未打开相机，请用相机 App 录像，再从相册选择。</p></div></section></div>`;
  document.querySelectorAll('[data-joint]').forEach(b=>b.onclick=()=>{clearFile();state.joint=b.dataset.joint;state.selected=state.catalog.find(x=>x.joint===state.joint).id;assessment();});
  document.querySelectorAll('[data-exercise]').forEach(b=>b.onclick=()=>{clearFile();state.selected=b.dataset.exercise;assessment();if(innerWidth<651)$('#guide').scrollIntoView({behavior:'smooth',block:'start'});});
  document.querySelectorAll('[data-side]').forEach(b=>b.onclick=()=>{if(state.file && !confirm('更改测试侧会清除当前选择的录像，是否继续？'))return;clearFile();state.side=b.dataset.side;assessment();});
  $('#camera-btn').onclick=()=>$('#camera-file').click();$('#gallery-btn').onclick=()=>$('#gallery-file').click();
  for(const id of ['camera-file','gallery-file'])$('#'+id).onchange=e=>chooseFile(e.target.files[0]);
  if(state.training){
    const t=state.training.entry;
    $('.hero h1').textContent='按个人安排，完成今天的活动';
    $('.hero p').textContent='录制训练 · 上传分析 · 查看完成情况';
    $('.steps').innerHTML='<span class="current">01 查看训练安排</span><span>02 录制并上传</span><span>03 反馈与下一项</span>';
    $('.layout > section:first-child').innerHTML=`<div class="card tint"><span class="tag">本次训练安排 · ${sideLabel(t.side)}</span><h2>${esc(label(t.exercise_id))}</h2><div class="stat-grid"><div class="stat"><strong>${t.settings.target_reps}<small> 次</small></strong><small>本次目标</small></div><div class="stat"><strong>${t.settings.target_sets}<small> 组</small></strong><small>按舒适范围进行</small></div></div><p class="caption">${t.settings.target_angle_deg!==null?'个人投影角目标 '+number(t.settings.target_angle_deg,'°')+'，不是正常值。':'本项未设置角度目标。'} 先看右侧或下方动作提示，再录制训练。</p><p class="warning">这是录像后分析，不提供录制时的实时纠错。感到疼痛、头晕或不适，请立即停止。</p><button class="secondary" id="back-plan">返回训练中心</button></div>`;
    $('.side').innerHTML=`<p class="caption">测试侧：本人${sideLabel(t.side)}，由本次计划确定</p>`;
    $('#back-plan').onclick=()=>navigate('plan');
  }
  fileArea();
}
function chooseFile(file){if(!file)return;if(file.size>256*1024*1024){toast('视频超过 256 MB，请缩短视频或降低分辨率');return;}clearFile();state.file=file;state.url=URL.createObjectURL(file);fileArea();}
function fileArea(){
  if(!state.file)return;
  document.querySelectorAll('.steps span').forEach((s,i)=>s.classList.toggle('current',i===1));
  $('#file-area').innerHTML=`<div class="selected-file"><strong>${esc(state.file.name)}</strong><p class="caption">${(state.file.size/1024/1024).toFixed(1)} MB · ${esc(label(state.selected))} · ${sideLabel(state.side)}</p><video controls playsinline preload="metadata" src="${state.url}"></video></div><label class="consent"><input id="consent" type="checkbox"><span>同意将本次录像传到我的电脑进行动作分析，并保存在电脑上。可在记录页删除原始录像。</span></label><button id="upload-btn" class="primary">上传并开始评估 →</button><p id="upload-status" class="status-text" aria-live="polite"></p><progress id="upload-progress" class="progress" max="100" value="0" hidden></progress><button id="cancel-upload" class="secondary" hidden>取消上传</button>`;
  $('#upload-btn').onclick=upload;
  if(state.training)$('#upload-btn').textContent='上传并分析本次训练 →';
  if(state.tab==='fitness')$('#upload-btn').textContent='上传并分析健身动作 →';
  const video=$('#file-area video');video.onloadedmetadata=()=>{if(Number.isFinite(video.duration)&&video.duration>120){toast('这段视频超过 2 分钟，请截取一项动作后再上传');$('#upload-btn').disabled=true;}};
  if(state.tab==='fitness')mountBarCalibration();
}
function upload(){
  if(!$('#consent').checked){toast('请先勾选本次录像分析授权');return;}
  let calibration=null;
  if(state.tab==='fitness'){try{calibration=readBarCalibration();}catch(e){toast(e.message);return;}}
  const xhr=new XMLHttpRequest();state.upload=xhr;
  // Freeze all selectors while the upload metadata is bound to this video.
  document.querySelectorAll('#app button, #app input').forEach(b=>b.disabled=true);
  $('#cancel-upload').hidden=false;$('#cancel-upload').disabled=false;$('#cancel-upload').onclick=()=>xhr.abort();
  $('#upload-progress').hidden=false;$('#upload-status').textContent='正在上传，请保持页面开启…';
  const binding=state.tab==='fitness'?'&mode=fitness':state.training?`&mode=training&plan_id=${state.training.id}&entry_key=${encodeURIComponent(state.training.entry.key)}`:'';
  xhr.open('POST',`/api/jobs?exercise=${encodeURIComponent(state.selected)}&side=${state.side}&consent=yes${binding}`);
  xhr.setRequestHeader('Content-Type',state.file.type||'application/octet-stream');xhr.setRequestHeader('X-Rehab-Client','mobile-v1');xhr.timeout=180000;
  if(calibration)xhr.setRequestHeader('X-Fitness-Calibration',JSON.stringify(calibration));
  xhr.upload.onprogress=e=>{if(e.lengthComputable){$('#upload-progress').value=e.loaded/e.total*100;$('#upload-status').textContent=e.loaded===e.total?'上传完成，等待电脑接收确认…':`正在上传 ${Math.round(e.loaded/e.total*100)}%`;}};
  const reset=(message)=>{state.upload=null;render();toast(message);};
  xhr.onerror=()=>reset('连接中断，请确认手机和电脑仍在同一 Wi-Fi');xhr.ontimeout=()=>reset('上传超时，请尝试更短的视频');xhr.onabort=()=>reset('已取消上传');
  xhr.onload=()=>{state.upload=null;let data;try{data=JSON.parse(xhr.responseText);}catch{reset('电脑响应异常，请重试');return;}if(xhr.status>=300){reset(data.detail||'上传未完成');return;}clearFile();showJob(data.id);};
  xhr.send(state.file);
}
async function refreshJobs(){state.jobs=await api('/jobs?brief=true');}
function history(){
  const filter=state.historyFilter||'all';
  app.innerHTML=`<div class="page-head"><h1>我的活动记录</h1><p>康复与健身分类保存，每一步都留有记录。</p></div><div class="chips">${[['all','全部'],['rehab','康复'],['fitness','健身']].map(([key,name])=>`<button class="chip ${key===filter?'selected':''}" data-history-filter="${key}">${name}</button>`).join('')}</div><div id="records"><p class="loading">正在读取记录…</p></div>`;
  document.querySelectorAll('[data-history-filter]').forEach(b=>b.onclick=()=>{state.historyFilter=b.dataset.historyFilter;history();});
  refreshJobs().then(()=>{
    if(state.tab!=='history'||(state.historyFilter||'all')!==filter)return;
    const rows=state.jobs.filter(j=>filter==='all'||(filter==='fitness'?j.mode==='fitness':j.mode!=='fitness'));
    $('#records').innerHTML=rows.length?rows.map(j=>`<button class="record" data-job="${j.id}"><span><strong>${esc(label(j.exercise))} · ${sideLabel(j.side)}</strong><small>${dateLabel(j.created_at)} · ${j.mode==='fitness'?'健身分析':j.mode==='training'?'康复训练':'康复评估'}</small></span><span class="badge">${statusLabel(j.state)} ›</span></button>`).join(''):`<div class="card empty"><div class="status-orb">◷</div><h3>还没有${filter==='fitness'?'健身':filter==='rehab'?'康复':''}记录</h3><p>上传一次动作录像后，结果会保存在这里。<br>当前浏览器只展示自己的记录。</p><button class="primary" id="start-assess">${filter==='fitness'?'去分析健身动作':'去做一次评估'}</button></div>`;
    document.querySelectorAll('[data-job]').forEach(b=>b.onclick=()=>showJob(b.dataset.job));
    if($('#start-assess'))$('#start-assess').onclick=()=>navigate(filter==='fitness'?'fitness':'assess');
  }).catch(e=>toast(e.message));
}
async function showJob(id){
  clearTimeout(pollTimer);state.job=id;
  try{const j=await api('/jobs/'+id);if(state.job!==id)return;renderJob(j);if(['queued','analyzing','uploading'].includes(j.state))pollTimer=setTimeout(()=>showJob(id),2000);}catch(e){toast(e.message);if(state.job===id){app.innerHTML='<div class="card empty"><h2>暂时没有连上电脑</h2><p>检查 Wi-Fi 与电脑服务，已上传的任务不会因关闭网页而停止。</p><button class="primary" id="retry">重新连接</button></div>';$('#retry').onclick=()=>showJob(id);}}
}
function renderJob(j){
  if(j.mode==='fitness'&&j.state==='done'){renderFitnessReport(j);return;}
  app.innerHTML=`<button class="back" id="back-history">‹ 返回我的记录</button><div class="page-head"><span class="tag">${sideLabel(j.side)} · 视频评估</span><h1>${esc(label(j.exercise))}</h1><p>${dateLabel(j.created_at)}</p></div><div id="job-content"></div>`;
  $('#back-history').onclick=()=>navigate('history');const area=$('#job-content');
  if(j.mode==='fitness')$('.page-head .tag').textContent=sideLabel(j.side)+' · 健身录像分析';
  if(j.state!=='done'){
    area.innerHTML=`<div class="card center"><div class="status-orb">${j.state==='failed'?'!':'◎'}</div><h2>${statusLabel(j.state)}</h2><p class="status-text" role="status">${esc(j.message)}</p>${j.state!=='failed'?`<progress class="progress" aria-label="分析进行中"></progress><p class="caption">${j.progress?`已处理到视频 ${number(j.progress.analyzed_seconds,' 秒')} · ${j.progress.processed_frames} 帧`:'等待电脑启动分析模型…'}</p><p class="tip">上传完成后可离开本页，稍后从“我的记录”回来查看。</p>`:'<button class="primary" id="retake">重新选择录像</button>'}</div>`;
    if($('#retake'))$('#retake').onclick=()=>navigate(j.mode==='fitness'?'fitness':'assess');
  }else{
    const s=j.result.summary,r=s.motion_range, ratio=s.valid_ratio;
    const measured=!!r;const meaningful=measured && s.completed>0;
    area.innerHTML=`<div class="card"><span class="tag">${meaningful?'本次活动观察':'本次观察不足'}</span><h2>${meaningful?'看见你的活动表现':'已分析，没有足够的可用动作'}</h2><div class="stat-grid"><div class="stat"><strong>${s.completed??0}<small> 次</small></strong><small>观察到的完整动作</small></div><div class="stat"><strong>${Number.isFinite(ratio)?Math.round(ratio*100)+'%':'—'}</strong><small>可用观察时长占比</small></div><div class="stat"><strong>${r?number(r.max_deg-r.min_deg,'°'):'—'}</strong><small>二维投影角变化幅度</small></div><div class="stat"><strong>${number(s.observed_span_s,'s')}</strong><small>本次分析时长</small></div></div><p class="result-note">${measured?`本次观察到的${esc(s.primary_metric_label)}为 <strong>${number(r.min_deg,'°')}–${number(r.max_deg,'°')}</strong>。记录到 ${s.completed} 次完整动作。`:'没有得到足够的连续有效测量，不能据此判断活动能力。'}${!meaningful?' 下次让测试部位完整入镜，起点停留后缓慢完成动作并回位。':''}</p><p class="tip">这是视频中的二维活动观察，不等同于临床关节活动度。可用观察比例反映画面可分析程度，不是动作质量评分。</p><button class="primary file-actions" id="view-plan">查看基于评估的活动建议 →</button><details><summary>本次测量的适用范围</summary>${esc(state.catalog.find(x=>x.id===j.exercise).instructions.boundary)}<br>来源：上传录像 / REPLAY_FILE；不是实时监测。</details></div>`;
    $('#view-plan').onclick=()=>navigate('plan');
  }
  if(j.mode==='training'){
    $('.page-head .tag').textContent=sideLabel(j.side)+' · 训练录像分析';
    if(j.state==='done'){
      const quality=j.result.quality, f=j.feedback||{}, box=document.createElement('section');box.className='card';
      box.innerHTML=`<span class="tag">训练完成情况</span><h2>${j.result.summary.plan_completed?'已观察到计划次数':'尚未观察到全部计划次数'}</h2><p class="tip">已设目标达成 ${quality.observed_goals_met} 次 · 需调整 ${quality.needs_adjustment} 次 · 无法完整评价 ${quality.unassessable} 次。这里只评价已设置目标及可见指标，不代表动作整体完全正确。</p><h3 class="rule">练完感觉怎么样？</h3><p class="tip">请选择真实感受，保存后才能继续下一项。0 表示没有，10 表示非常强烈。</p><form id="feedback-form"><label class="consent">疼痛感 <select id="pain" required><option value="">请选择</option>${Array.from({length:11},(_,i)=>`<option value="${i}" ${f.pain===i?'selected':''}>${i} / 10</option>`).join('')}</select></label><label class="consent">疲劳感 <select id="fatigue" required><option value="">请选择</option>${Array.from({length:11},(_,i)=>`<option value="${i}" ${f.fatigue===i?'selected':''}>${i} / 10</option>`).join('')}</select></label><button class="primary">保存感受，查看下一步</button></form>`;
      area.prepend(box);
      $('#feedback-form').onsubmit=async e=>{e.preventDefault();try{const pain=Number($('#pain').value),fatigue=Number($('#fatigue').value);await api('/jobs/'+j.id+'/feedback',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pain,fatigue,reason:pain>0?'discomfort':fatigue>=5?'fatigue':'completed',revision:f.revision||0})});navigate('plan');}catch(e){toast(e.message);}};
    }
  }
  if(j.video_available&&!['uploading','queued','analyzing'].includes(j.state)){
    const box=document.createElement('section');box.className='card';box.innerHTML=`<h3>回看本次录像</h3><video class="report-video" controls playsinline preload="metadata" src="/api/jobs/${j.id}/video"></video><button class="danger" id="delete-video">删除原始录像，保留评估结果</button>`;area.appendChild(box);
    $('#delete-video').onclick=async()=>{if(!confirm('删除电脑上的本次原始录像？评估结果会保留，录像删除后无法恢复。'))return;try{await api('/jobs/'+j.id+'/video',{method:'DELETE'});await showJob(j.id);toast('已删除原始录像，评估结果保留');}catch(e){toast(e.message);}};
  }
}
function devices(){
  app.innerHTML=`<div class="page-head"><h1>让设备协同起来</h1><p>手机负责拍摄与查看，电脑负责分析。</p></div><div class="layout"><div><div class="card"><div class="device-icon">▣</div><div class="section-head"><h2>手机摄像头</h2><span class="device-state">可使用</span></div><p class="caption">适配红米 K60 Ultra 的移动网页布局。使用系统相机拍摄，再上传到电脑。</p><button class="primary file-actions" id="device-assess">去拍摄评估</button></div><div class="card"><div class="section-head"><h2>电脑分析服务</h2><span class="device-state">已连接</span></div><p class="caption">${esc(location.host)}</p><p class="tip">保持电脑服务开启。手机锁屏可能中断正在进行的上传；上传成功后电脑会独立继续分析。</p></div></div><div class="card"><span class="tag">网络摄像头</span><h2>下一步，接入固定机位</h2><p class="status-text">尚未接入视频流</p><p class="caption">网络摄像头通常先与手机、电脑连接同一路由器，由电脑接收视频流，再给手机展示画面。</p><div class="camera-note">请提供摄像头品牌、型号，以及是否支持 RTSP 或 ONVIF。不要在聊天里发送密码。</div><p class="tip">本版可以上传网络摄像头导出的录像。实时预览、远程开始录制、双机位同步还未接入；手机网页不能直接把 RTSP 地址当作普通视频播放。</p></div></div>`;
  $('#device-assess').onclick=()=>navigate('assess');
}
async function init(){try{const data=await api('/catalog');state.catalog=data.exercises;state.fitnessCatalog=data.fitness||[];$('.bottom-nav').hidden=false;$('#connection').textContent='电脑已连接';render();}catch(e){pairPage();}}
function plan(){
  app.innerHTML='<div class="page-head"><span class="tag">来自你的真实评估</span><h1>今天，循序渐进地活动</h1><p>个人安排 → 录制训练 → 分析结果 → 记录感受</p></div><div id="plan-content"><p class="loading">正在汇总评估…</p></div>';
  api('/plan').then(data=>{
    if(state.tab!=='plan')return;
    const {proposal,progress}=data, record=data.plan, items=proposal.candidates.slice(0,4), area=$('#plan-content');
    area.innerHTML='';
    if(record){
      area.innerHTML=`<div class="card"><span class="tag">已确认的个人计划</span><h2>已完成 ${progress.completed} / ${progress.total} 项</h2>${record.items.map((i,n)=>`<div class="plan-item"><strong>${n+1}. ${esc(label(i.exercise_id))} · ${sideLabel(i.side)}</strong><p class="caption">${i.settings.target_reps} 次 × ${i.settings.target_sets} 组 · ${progress.items[n].done?'已达到次数目标':'待完成'}</p></div>`).join('')}${progress.blocked?`<p class="warning">${esc(progress.blocked)}</p><button id="training-records" class="secondary">查看训练记录 / 补充感受</button>`:progress.next_key?'<button class="primary file-actions" id="train-next">开始下一项训练 →</button>':'<p class="warning">本轮计划已完成，不自动追加练习。</p>'}</div>`;
      if($('#train-next'))$('#train-next').onclick=()=>{const entry=record.items.find(i=>i.key===progress.next_key);state.training={id:record.id,entry};state.selected=entry.exercise_id;state.side=entry.side;state.joint=selected().joint;state.tab='assess';clearFile();assessment();window.scrollTo(0,0);};
      if($('#training-records'))$('#training-records').onclick=()=>navigate('history');
    }
    if(!record || progress.blocked){
      area.insertAdjacentHTML('beforeend',items.length?`<div class="card"><div class="section-head"><h2>根据评估生成的建议</h2><small>${items.length} 项</small></div>${items.map(i=>`<div class="plan-item"><strong>${esc(i.label)}</strong><br><span class="dose">${i.settings.target_reps} 次 × ${i.settings.target_sets} 组 · 组间休息 ${i.settings.rest_between_sets_s} 秒</span><p>${esc(i.rationale)}</p><p class="caption">${esc(i.instruction)}</p><details><summary>为什么安排这个动作？</summary>参考：${esc(i.source.title)} / ${esc(i.source.section)}。次数及幅度是本项目按本人评估适配，不是指南直接开出的个人处方。</details></div>`).join('')}<form id="plan-form"><label class="consent"><input id="activity-ok" type="checkbox" required><span>我目前无疼痛、头晕等不适，无疾病、术后或医嘱活动限制，并已获准进行这类基础活动；不确定时先咨询专业人员。</span></label><label class="consent"><input id="support-ok" type="checkbox"><span>站立项目已准备稳固支撑，并具备安全完成的条件（不选则排除站立项目）。</span></label><button class="primary">确认适用，生成本次训练计划</button></form><p class="tip">一般基础活动安排，不是疾病治疗处方。手机端采用录制后分析，不是实时监护。</p></div>`:!record?'<div class="card empty"><div class="status-orb">▤</div><h3>先完成一次有效评估</h3><p>观察到完整动作且可用观察充足后，系统按本人表现生成安排，不使用预置假数据。</p><button class="primary" id="plan-assess">开始身体评估</button></div>':'');
    }
    if(proposal.excluded.length)area.insertAdjacentHTML('beforeend',`<div class="card"><h3>需要再观察的项目</h3>${proposal.excluded.map(x=>`<p class="tip">${esc(x.label)}：${esc(x.reason)}</p>`).join('')}</div>`);
    if($('#plan-assess'))$('#plan-assess').onclick=()=>navigate('assess');
    if($('#plan-form'))$('#plan-form').onsubmit=async e=>{e.preventDefault();const b=e.currentTarget.querySelector('button');b.disabled=true;try{await api('/plan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({general_activity_ok:$('#activity-ok').checked,standing_support_ok:$('#support-ok').checked,companion_present:false})});plan();}catch(e){toast(e.message);b.disabled=false;}};
  }).catch(e=>{if($('#plan-content'))$('#plan-content').innerHTML='<div class="card empty"><h3>暂时没有读取到训练安排</h3><button class="secondary" id="reload-plan">重试</button></div>';if($('#reload-plan'))$('#reload-plan').onclick=plan;toast(e.message);});
}
document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>navigate(b.dataset.tab));
window.addEventListener('beforeunload',e=>{if(state.upload){e.preventDefault();e.returnValue='';}});
init();
