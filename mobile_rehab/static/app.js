'use strict';
const $ = (s) => document.querySelector(s);
const app = $('#app');
const state = {tab:'plan', catalog:[], joint:'all', selected:'shoulder_abduction', side:'left', jobs:[], file:null, url:null, job:null, upload:null, training:null, detail:false, search:'', viewFilter:'all', fitnessGroup:'all'};
let pollTimer, toastTimer;
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number = (v, unit='') => Number.isFinite(v) ? `${Math.round(v*10)/10}${unit}` : '未测得';
const selected = () => state.catalog.find(x => x.id === state.selected);
const label = (id) => state.catalog.find(x => x.id === id)?.label || state.fitnessCatalog?.find(x => x.id === id)?.label || state.postureCatalog?.find(x=>x.id===id)?.label || id;
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
  app.innerHTML=`<section class="pair"><span class="tag">连接电脑</span><h1>手机康复评估</h1><p>手机和电脑连接同一 Wi-Fi，输入电脑启动窗口中的连接码。</p><form id="pair-form"><label class="caption" for="pair-code">电脑连接码</label><input id="pair-code" name="code" autocomplete="off" autocapitalize="none" spellcheck="false" placeholder="输入连接码" required maxlength="32"><button class="primary">连接</button></form><p class="tip">视频保存在这台电脑上。请在可信 Wi-Fi 下使用。</p></section>`;
  $('#pair-form').onsubmit=async e=>{e.preventDefault();const b=e.currentTarget.querySelector('button');b.disabled=true;try{await api('/pair',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:$('#pair-code').value.trim()})});await init();}catch(e){toast(e.message);b.disabled=false;}};
}
function clearFile(){if(state.url)URL.revokeObjectURL(state.url);state.file=null;state.url=null;state.barCalibration=null;}
function navigate(tab){
  if(state.upload){toast('正在上传，请先完成或取消上传');return;}
  if(typeof stopLive==='function')stopLive();
  clearTimeout(pollTimer);state.tab=tab;state.job=null;state.training=null;state.detail=false;state.search='';state.viewFilter='all';clearFile();
  if(tab==='assess'&&!selected()){state.selected='shoulder_abduction';state.joint='shoulder';}
  syncNavigation();
  render();window.scrollTo({top:0,behavior:'instant'});
}
function syncNavigation(){
  const active=['posture','body','care'].includes(state.tab)?'assess':state.training?'plan':state.tab;
  document.querySelectorAll('[data-tab]').forEach(b=>{b.classList.toggle('active',b.dataset.tab===active);if(b.dataset.tab===active)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');});
}
function libraryRows(items,mode){
  return items.length?items.map(x=>`<button class="action-row" data-action="${esc(x.id)}"><span><strong>${esc(x.label)}</strong><small>${esc(mode==='fitness'?x.group:x.joint_label)} · ${mode==='fitness'||x.view==='sagittal'?'侧面':'正面'}拍摄</small></span><span class="row-link">查看</span></button>`).join(''):'<p class="library-empty" role="status">没有找到这个动作，试试其他名称或部位。</p>';
}
function filteredActions(items,mode){
  return items.filter(x=>(mode==='fitness'?(state.fitnessGroup==='all'||x.group===state.fitnessGroup):(state.joint==='all'||x.joint===state.joint))&&(state.viewFilter==='all'||(mode==='fitness'?'sagittal':x.view)===state.viewFilter)&&(!state.search||x.label.toLowerCase().includes(state.search.toLowerCase())));
}
function actionLibrary(mode){
  const fitness=mode==='fitness', items=fitness?state.fitnessCatalog:state.catalog;
  const groups=fitness?[...new Set(items.map(x=>x.group))].map(x=>[x,x]):[...new Map(items.map(x=>[x.joint,x.joint_label]))];
  const active=fitness?state.fitnessGroup:state.joint;
  app.innerHTML=`<div class="page-head library-heading"><h1>${fitness?'健身动作库':'康复评估'}</h1><span class="caption">${items.length} 个动作</span></div>${fitness?'<div class="entry-links"><button id="fitness-demo">示例报告<span>模拟数据</span></button></div>':'<div class="entry-links"><button id="posture-entry">站姿体态<span>正面 / 侧面</span></button><button id="body-entry">身体汇总<span>评估与训练</span></button></div>'}<div class="library-toolbar"><label class="search-field"><span class="sr-only">搜索动作</span><input type="search" id="action-search" placeholder="搜索动作" value="${esc(state.search)}" autocomplete="off"></label>${fitness?'':'<label><span class="sr-only">拍摄机位</span><select id="view-filter"><option value="all">全部机位</option><option value="frontal">正面拍摄</option><option value="sagittal">侧面拍摄</option></select></label>'}</div><div class="action-library"><aside class="body-categories" aria-label="${fitness?'动作分类':'身体部位'}">${[['all','全部'],...groups].map(([id,name])=>`<button data-category="${esc(id)}" class="${id===active?'selected':''}" aria-pressed="${id===active}">${esc(name)}</button>`).join('')}</aside><section class="action-list" id="action-list" aria-label="动作列表">${libraryRows(filteredActions(items,mode),mode)}</section></div>`;
  function bindRows(){document.querySelectorAll('[data-action]').forEach(b=>b.onclick=()=>{clearFile();state.selected=b.dataset.action;state.detail=true;fitness?fitnessPage():assessment();window.scrollTo(0,0);});}
  function updateRows(){ $('#action-list').innerHTML=libraryRows(filteredActions(items,mode),mode);bindRows();}
  document.querySelectorAll('[data-category]').forEach(b=>b.onclick=()=>{if(fitness)state.fitnessGroup=b.dataset.category;else state.joint=b.dataset.category;actionLibrary(mode);});
  $('#action-search').oninput=e=>{state.search=e.target.value.trim();updateRows();};
  if(!fitness){$('#view-filter').value=state.viewFilter;$('#view-filter').onchange=e=>{state.viewFilter=e.target.value;updateRows();};$('#posture-entry').onclick=()=>navigate('posture');$('#body-entry').onclick=()=>navigate('body');}
  else $('#fitness-demo').onclick=showBarDemo;
  bindRows();
}
function backToLibrary(mode){if(state.upload)return;clearFile();state.detail=false;mode==='fitness'?fitnessPage():assessment();window.scrollTo(0,0);}
function render(){if(state.tab==='assess')assessment();else if(state.tab==='history')history();else if(state.tab==='plan')plan();else if(state.tab==='fitness')fitnessPage();else if(state.tab==='posture')posturePage();else if(state.tab==='body')bodyPage();else if(state.tab==='care')carePage();else devices();}
function assessment(){
  if(!state.detail&&!state.training){actionLibrary('assessment');return;}
  const ex=selected(), i=ex.instructions;
  app.innerHTML=`<button class="back" id="action-back">返回${state.training?'训练':'动作库'}</button><section class="hero action-title"><h1>${esc(ex.label)}</h1><p>${esc(ex.joint_label)} · ${esc(i.view_label)}</p></section>
  <div class="steps"><span class="current">1 看动作</span><span>2 拍摄</span><span>3 看结果</span></div>
  <div class="layout detail-layout"><section><div class="card" id="guide"><div class="section-head"><h2>怎么做</h2><small>缓慢完成，再回位</small></div><div class="side" aria-label="本人测试侧"><button data-side="left" class="${state.side==='left'?'selected':''}" aria-pressed="${state.side==='left'}">本人左侧</button><button data-side="right" class="${state.side==='right'?'selected':''}" aria-pressed="${state.side==='right'}">本人右侧</button></div>
  ${[['1',i.start],['2',i.move],['3',i.return]].map(([n,t])=>`<div class="instruction"><span class="number">${n}</span><p>${esc(t)}</p></div>`).join('')}
  <details><summary>拍摄与测量说明</summary><p>${esc(i.camera)}</p><p>开始前停留 3 秒，建议录制 15–40 秒。不适时停止。</p>${esc(i.boundary)}<br>${esc(i.count)}</details></div></section>
  <section><div id="training-dose"></div><div class="card capture-card"><div class="section-head"><h2>${state.training?'记录本次训练':'开始评估'}</h2><small>录像上传</small></div><p class="caption">手机放稳，${ex.view==='frontal'?'正面':'侧面'}拍摄。</p><button class="primary file-actions" id="camera-btn">拍摄视频</button><button class="secondary" id="gallery-btn">选择已有视频</button><input id="camera-file" type="file" accept="video/*" capture="environment" hidden><input id="gallery-file" type="file" accept="video/*" hidden><div id="file-area"></div></div></section></div>`;
  $('#action-back').onclick=()=>state.training?navigate('plan'):backToLibrary('assessment');
  document.querySelectorAll('[data-side]').forEach(b=>b.onclick=()=>{if(state.file && !confirm('更改测试侧会清除当前选择的录像，是否继续？'))return;clearFile();state.side=b.dataset.side;assessment();});
  $('#camera-btn').onclick=()=>$('#camera-file').click();$('#gallery-btn').onclick=()=>$('#gallery-file').click();
  for(const id of ['camera-file','gallery-file'])$('#'+id).onchange=e=>chooseFile(e.target.files[0]);
  if(state.training){
    const t=state.training.entry;
    $('.hero p').textContent='本次训练 · '+sideLabel(t.side);
    $('.steps').innerHTML='<span class="current">1 看动作</span><span>2 记录训练</span><span>3 填写感受</span>';
    $('#training-dose').innerHTML=`<div class="card"><h2>本次目标</h2><div class="stat-grid"><div class="stat"><strong>${t.settings.target_reps}<small> 次</small></strong><small>每组次数</small></div><div class="stat"><strong>${t.settings.target_sets}<small> 组</small></strong><small>训练组数</small></div></div>${Number.isFinite(t.settings.target_angle_deg)?'<p class="caption">个人角度目标 '+number(t.settings.target_angle_deg,'°')+'</p>':''}<p class="tip">感到疼痛、头晕或不适，请停止。</p><button class="secondary" id="back-plan">返回训练</button></div>`;
    $('.side').innerHTML=`<p class="caption">测试侧：本人${sideLabel(t.side)}，由本次计划确定</p>`;
    $('#back-plan').onclick=()=>navigate('plan');
  }
  fileArea();
  mountAssessmentExtras();
}
function chooseFile(file){if(!file)return;if(file.size>256*1024*1024){toast('视频超过 256 MB，请缩短视频或降低分辨率');return;}clearFile();state.file=file;state.url=URL.createObjectURL(file);fileArea();}
function fileArea(){
  if(!state.file)return;
  document.querySelectorAll('.steps span').forEach((s,i)=>s.classList.toggle('current',i===1));
  $('#file-area').innerHTML=`<div class="selected-file"><strong>${esc(state.file.name)}</strong><p class="caption">${(state.file.size/1024/1024).toFixed(1)} MB · ${esc(label(state.selected))} · ${sideLabel(state.side)}</p><video controls playsinline preload="metadata" src="${state.url}"></video></div><label class="consent"><input id="consent" type="checkbox"><span>同意将视频上传到电脑分析并保存，可随时删除原视频。</span></label><button id="upload-btn" class="primary">上传并分析</button><p id="upload-status" class="status-text" aria-live="polite"></p><progress id="upload-progress" class="progress" max="100" value="0" hidden></progress><button id="cancel-upload" class="secondary" hidden>取消上传</button>`;
  $('#upload-btn').onclick=upload;
  if(state.training)$('#upload-btn').textContent='上传并分析';
  if(state.tab==='fitness')$('#upload-btn').textContent='上传并分析';
  const video=$('#file-area video');video.onloadedmetadata=()=>{if(Number.isFinite(video.duration)&&video.duration>120){toast('这段视频超过 2 分钟，请截取一项动作后再上传');$('#upload-btn').disabled=true;}};
  if(state.tab==='fitness')mountBarCalibration();
}
function upload(){
  if(!$('#consent').checked){toast('请先勾选本次录像分析授权');return;}
  let calibration=null;
  if(state.tab==='fitness'){try{calibration=readBarCalibration();}catch(e){toast(e.message);return;}}
  const xhr=new XMLHttpRequest();state.upload=xhr;
  // Freeze all selectors while the upload metadata is bound to this video.
  document.querySelectorAll('#app button, #app input, #app select').forEach(b=>b.disabled=true);
  $('#cancel-upload').hidden=false;$('#cancel-upload').disabled=false;$('#cancel-upload').onclick=()=>xhr.abort();
  $('#upload-progress').hidden=false;$('#upload-status').textContent='正在上传，请保持页面开启…';
  const binding=state.tab==='posture'?'&mode=posture':state.tab==='fitness'?'&mode=fitness':state.training?`&mode=training&plan_id=${state.training.id}&entry_key=${encodeURIComponent(state.training.entry.key)}`:'';
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
  app.innerHTML=`<div class="page-head"><h1>我的活动记录</h1><p>查看评估和训练结果。</p></div><div class="chips">${[['all','全部'],['rehab','康复'],['fitness','健身']].map(([key,name])=>`<button class="chip ${key===filter?'selected':''}" data-history-filter="${key}">${name}</button>`).join('')}</div><div id="records"><p class="loading">正在读取记录…</p></div>`;
  document.querySelectorAll('[data-history-filter]').forEach(b=>b.onclick=()=>{state.historyFilter=b.dataset.historyFilter;history();});
  refreshJobs().then(()=>{
    if(state.tab!=='history'||(state.historyFilter||'all')!==filter)return;
    const rows=state.jobs.filter(j=>filter==='all'||(filter==='fitness'?j.mode==='fitness':j.mode!=='fitness'));
    $('#records').innerHTML=rows.length?rows.map(j=>`<button class="record" data-job="${j.id}"><span><strong>${esc(label(j.exercise))} · ${sideLabel(j.side)}</strong><small>${dateLabel(j.created_at)} · ${j.mode==='fitness'?'健身分析':j.mode==='training'?'康复训练':'康复评估'}</small></span><span class="badge">${statusLabel(j.state)} ›</span></button>`).join(''):`<div class="card empty"><div class="status-orb">◷</div><h3>还没有${filter==='fitness'?'健身':filter==='rehab'?'康复':''}记录</h3><p>上传一次动作录像后，结果会保存在这里。<br>记录仅在当前浏览器账号下显示。</p><button class="primary" id="start-assess">${filter==='fitness'?'去分析健身动作':'去做一次评估'}</button></div>`;
    document.querySelectorAll('[data-job]').forEach(b=>b.onclick=()=>showJob(b.dataset.job));
    if($('#start-assess'))$('#start-assess').onclick=()=>navigate(filter==='fitness'?'fitness':'assess');
  }).catch(e=>toast(e.message));
}
async function showJob(id){
  clearTimeout(pollTimer);state.job=id;
  try{const j=await api('/jobs/'+id);if(state.job!==id)return;renderJob(j);if(['queued','analyzing','uploading'].includes(j.state))pollTimer=setTimeout(()=>showJob(id),2000);}catch(e){toast(e.message);if(state.job===id){app.innerHTML='<div class="card empty"><h2>暂时没有连上电脑</h2><p>检查 Wi-Fi 与电脑服务，已上传的任务不会因关闭网页而停止。</p><button class="primary" id="retry">重新连接</button></div>';$('#retry').onclick=()=>showJob(id);}}
}
function renderJob(j){
  if(j.mode==='posture'&&j.state==='done'){renderPostureReport(j);return;}
  if(j.mode==='fitness'&&j.state==='done'){renderFitnessReport(j);return;}
  app.innerHTML=`<button class="back" id="back-history">‹ 返回我的记录</button><div class="page-head"><span class="tag">${sideLabel(j.side)} · 视频评估</span><h1>${esc(label(j.exercise))}</h1><p>${dateLabel(j.created_at)}</p></div><div id="job-content"></div>`;
  $('#back-history').onclick=()=>navigate('history');const area=$('#job-content');
  if(j.mode==='fitness')$('.page-head .tag').textContent=sideLabel(j.side)+' · 健身录像分析';
  if(j.state!=='done'){
    area.innerHTML=`<div class="card center"><div class="status-orb">${j.state==='failed'?'!':'◎'}</div><h2>${statusLabel(j.state)}</h2><p class="status-text" role="status">${esc(j.message)}</p>${j.state!=='failed'?`<progress class="progress" aria-label="分析进行中"></progress><p class="caption">${j.progress?`已处理到视频 ${number(j.progress.analyzed_seconds,' 秒')} · ${j.progress.processed_frames} 帧`:'等待电脑启动分析模型…'}</p><p class="tip">上传完成后可离开本页，稍后从“我的记录”回来查看。</p>`:'<button class="primary" id="retake">重新选择录像</button>'}</div>`;
    if($('#retake'))$('#retake').onclick=()=>navigate(j.mode==='posture'?'posture':j.mode==='fitness'?'fitness':'assess');
  }else{
    const s=j.result.summary,r=s.motion_range, ratio=s.valid_ratio;
    const measured=!!r;const meaningful=measured && s.completed>0;
    area.innerHTML=`<div class="card"><span class="tag">${meaningful?'评估结果':'画面不足'}</span><h2>${meaningful?'本次结果':'未识别到完整动作'}</h2><div class="stat-grid"><div class="stat"><strong>${s.completed??0}<small> 次</small></strong><small>完整动作</small></div><div class="stat"><strong>${Number.isFinite(ratio)?Math.round(ratio*100)+'%':'—'}</strong><small>有效画面占比</small></div><div class="stat"><strong>${r?number(r.max_deg-r.min_deg,'°'):'—'}</strong><small>视频角度变化</small></div><div class="stat"><strong>${number(s.observed_span_s,'s')}</strong><small>本次分析时长</small></div></div><p class="result-note">${measured?`本次观察到的${esc(s.primary_metric_label)}为 <strong>${number(r.min_deg,'°')}–${number(r.max_deg,'°')}</strong>。记录到 ${s.completed} 次完整动作。`:'画面不足，暂时无法评估。'}${!meaningful?' 请让测试部位入镜，缓慢完成动作并回位。':''}</p><button class="primary file-actions" id="view-plan">查看训练建议</button><details><summary>测量说明</summary><p>视频角度不等同于临床关节活动度；有效画面占比不是动作评分。</p>${esc(state.catalog.find(x=>x.id===j.exercise).instructions.boundary)}<br>根据上传录像分析，不是实时监测。</details></div>`;
    $('#view-plan').onclick=()=>navigate('plan');
  }
  if(j.mode==='training'){
    $('.page-head .tag').textContent=sideLabel(j.side)+' · 训练录像分析';
    if(j.state==='done'){
      const quality=j.result.quality, f=j.feedback||{}, box=document.createElement('section');box.className='card';
      box.innerHTML=`<span class="tag">训练完成情况</span><h2>${j.result.summary.plan_completed?'已完成计划次数':'尚未完成计划次数'}</h2><p class="tip">达到目标 ${quality.observed_goals_met} 次 · 需调整 ${quality.needs_adjustment} 次 · 未能判断 ${quality.unassessable} 次。按本次目标和可见动作统计。</p><h3 class="rule">练完感觉怎么样？</h3><p class="tip">请选择真实感受，保存后才能继续下一项。0 表示没有，10 表示非常强烈。</p><form id="feedback-form"><label class="consent">疼痛感 <select id="pain" required><option value="">请选择</option>${Array.from({length:11},(_,i)=>`<option value="${i}" ${f.pain===i?'selected':''}>${i} / 10</option>`).join('')}</select></label><label class="consent">疲劳感 <select id="fatigue" required><option value="">请选择</option>${Array.from({length:11},(_,i)=>`<option value="${i}" ${f.fatigue===i?'selected':''}>${i} / 10</option>`).join('')}</select></label><button class="primary">保存感受，查看下一步</button></form>`;
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
  app.innerHTML=`<div class="page-head"><h1>我的设备</h1></div><div class="layout"><div class="card"><div class="section-head"><h2>手机相机</h2><span class="device-state">录像上传</span></div><p class="caption">拍摄后返回网页，上传分析。</p><button class="primary file-actions" id="device-assess">选择评估动作</button></div><section class="card"><div class="section-head"><h2>分析电脑</h2><span class="device-state">已连接</span></div><p class="caption">${esc(location.host)}</p><details><summary>连接说明</summary>保持电脑服务开启，上传期间不要锁屏。上传成功后，可离开网页等待分析结果。</details></section></div>`;
  $('#device-assess').onclick=()=>navigate('assess');
  mountDeviceExtras();
}
async function init(){if(location.hash.startsWith('#care=')){state.shareCode=decodeURIComponent(location.hash.slice(6));window.history.replaceState(null,'',location.pathname);carePage();return;}let data;try{data=await api('/catalog');}catch(e){pairPage();return;}state.catalog=data.exercises;state.fitnessCatalog=data.fitness||[];state.postureCatalog=data.posture||[];$('.bottom-nav').hidden=false;$('#connection').textContent='已连接';syncNavigation();try{render();}catch(e){console.error('页面未能加载',e);toast('页面未能加载，请刷新重试');}}
function weekStrip(now=new Date()){
  const monday=new Date(now.getFullYear(),now.getMonth(),now.getDate());monday.setDate(monday.getDate()-(monday.getDay()+6)%7);
  return `<div class="week-strip" aria-label="本周日期">${['一','二','三','四','五','六','日'].map((name,i)=>{const day=new Date(monday);day.setDate(day.getDate()+i);const today=day.toDateString()===now.toDateString(),iso=`${day.getFullYear()}-${String(day.getMonth()+1).padStart(2,'0')}-${String(day.getDate()).padStart(2,'0')}`;return `<div class="week-day ${today?'today':''}" ${today?'aria-current="date"':''}><strong>${today?'今':name}</strong><time datetime="${iso}">${day.getDate()}</time></div>`;}).join('')}</div>`;
}
function plan(){
  app.innerHTML=`<div class="page-head"><h1>我的训练</h1></div>${weekStrip()}<div class="schedule-tools"><button id="schedule-assess">康复动作库</button><button id="schedule-body">身体汇总</button><button id="schedule-history">训练记录</button></div><div id="plan-content"><p class="loading" role="status">正在读取训练安排…</p></div>`;
  $('#schedule-assess').onclick=()=>navigate('assess');$('#schedule-body').onclick=()=>navigate('body');$('#schedule-history').onclick=()=>{state.historyFilter='rehab';navigate('history');};
  api('/plan').then(data=>{
    if(state.tab!=='plan')return;
    const {proposal,progress}=data, record=data.plan, items=proposal.candidates.slice(0,4), area=$('#plan-content');
    area.innerHTML='';
    if(record){
      const next=record.items.find(i=>i.key===progress.next_key);
      area.innerHTML=`<div class="card"><div class="schedule-header"><h2>${progress.next_key?'本轮安排':'本轮完成'}</h2><p>${progress.completed} / ${progress.total} 项</p></div>${next?`<h1>${esc(label(next.exercise_id))}</h1><p class="caption">${sideLabel(next.side)} · ${next.settings.target_reps} 次 × ${next.settings.target_sets} 组</p>`:''}<progress class="schedule-progress" max="${Math.max(1,progress.total)}" value="${progress.completed}" aria-label="本轮训练完成项数"></progress>${progress.blocked?`<p class="warning">${esc(progress.blocked)}</p><button id="training-records" class="secondary">补充训练感受</button>`:progress.next_key?'<button class="primary file-actions" id="train-next">开始训练</button>':'<p class="tip">本轮训练已完成。</p>'}</div><div class="card"><h2>训练清单</h2>${record.items.map((i,n)=>`<div class="plan-item"><strong>${esc(label(i.exercise_id))}</strong><p class="caption">${sideLabel(i.side)} · ${i.settings.target_reps} 次 × ${i.settings.target_sets} 组 <span class="${progress.items[n].done?'plan-done':''}">· ${progress.items[n].done?'已完成':'待完成'}</span></p></div>`).join('')}</div>`;
      if($('#train-next'))$('#train-next').onclick=()=>{const entry=record.items.find(i=>i.key===progress.next_key);state.training={id:record.id,entry};state.selected=entry.exercise_id;state.side=entry.side;state.joint=selected().joint;state.tab='assess';state.detail=true;syncNavigation();clearFile();assessment();window.scrollTo(0,0);};
      if($('#training-records'))$('#training-records').onclick=()=>navigate('history');
    }
    if(!record || progress.blocked || !progress.next_key){
      area.insertAdjacentHTML('beforeend',items.length?`<div class="card"><div class="section-head"><h2>${record?'下一轮计划':'你的训练建议'}</h2><small>${items.length} 项</small></div>${items.map(i=>`<div class="plan-item"><strong>${esc(i.label)}</strong><span class="dose">${i.settings.target_reps} 次 × ${i.settings.target_sets} 组 · 休息 ${i.settings.rest_between_sets_s} 秒</span><details><summary>动作安排与依据</summary><p>${esc(i.instruction)}</p><p>${esc(i.rationale)}</p>参考：${esc(i.source.title)} / ${esc(i.source.section)}。次数及幅度按本人评估适配，不是疾病治疗处方。</details></div>`).join('')}<form id="plan-form"><label class="consent"><input id="activity-ok" type="checkbox" required><span>目前无疼痛、头晕等不适，无疾病、术后或医嘱活动限制，并已获准进行基础活动。不确定时先咨询专业人员。</span></label><label class="consent"><input id="support-ok" type="checkbox"><span>站立项目已准备稳固支撑，可安全完成。</span></label><button class="primary">使用这份计划</button></form></div>`:!record?'<div class="card empty"><h2>从一次评估开始</h2><p>完成动作评估后，自动生成本轮训练建议。</p><button class="primary" id="plan-assess">开始评估</button></div>':'');
    }
    if(proposal.excluded.length)area.insertAdjacentHTML('beforeend',`<div class="card"><details><summary>待补充评估 · ${proposal.excluded.length} 项</summary>${proposal.excluded.map(x=>`<p class="tip">${esc(x.label)}：${esc(x.reason)}</p>`).join('')}</details></div>`);
    if($('#plan-assess'))$('#plan-assess').onclick=()=>navigate('assess');
    if($('#plan-form'))$('#plan-form').onsubmit=async e=>{e.preventDefault();const b=e.currentTarget.querySelector('button');b.disabled=true;try{await api('/plan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({general_activity_ok:$('#activity-ok').checked,standing_support_ok:$('#support-ok').checked,companion_present:false})});plan();}catch(e){toast(e.message);b.disabled=false;}};
  }).catch(e=>{if($('#plan-content'))$('#plan-content').innerHTML='<div class="card empty"><h3>暂时没有读取到训练安排</h3><button class="secondary" id="reload-plan">重试</button></div>';if($('#reload-plan'))$('#reload-plan').onclick=plan;toast(e.message);});
}
document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>navigate(b.dataset.tab));
window.addEventListener('beforeunload',e=>{if(state.upload){e.preventDefault();e.returnValue='';}});
window.addEventListener('DOMContentLoaded',init);
