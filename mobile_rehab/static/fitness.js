'use strict';
function fitnessPage(){
  const catalog=state.fitnessCatalog||[];
  if(!catalog.length){app.innerHTML='<div class="card empty"><h2>健身服务尚未加载</h2><p>请更新电脑服务后刷新页面。</p></div>';return;}
  if(!state.detail){actionLibrary('fitness');return;}
  if(!catalog.some(x=>x.id===state.selected))state.selected='fitness_squat';
  const ex=catalog.find(x=>x.id===state.selected);
  app.innerHTML=`<button class="back" id="fitness-library-back">返回动作库</button><section class="hero action-title fitness-hero"><h1>${esc(ex.label)}</h1><p>${esc(ex.group)} · 侧面拍摄</p></section><div class="steps"><span class="current">1 看动作</span><span>2 拍摄</span><span>3 分析回看</span></div><div class="layout detail-layout"><section><div class="card fitness-guidance" id="fitness-guide"><h2>怎么做</h2><div class="side" aria-label="观察侧"><button data-fit-side="left" class="${state.side==='left'?'selected':''}" aria-pressed="${state.side==='left'}">本人左侧</button><button data-fit-side="right" class="${state.side==='right'?'selected':''}" aria-pressed="${state.side==='right'}">本人右侧</button></div>${ex.steps.map((t,i)=>`<div class="instruction"><span class="number">${i+1}</span><p>${esc(t)}</p></div>`).join('')}<details><summary>拍摄与测量说明</summary><p>${esc(ex.camera)}</p><p>固定手机，开始前站稳 2 秒。重物训练做好保护。</p>${esc(ex.note)}<br>主指标：${esc(ex.metric_label)}。</details></div></section><section><div class="card capture-card"><h2>分析一组动作</h2><p class="caption">侧面拍摄 · 建议 15–40 秒</p><button id="fit-camera" class="primary file-actions">拍摄视频</button><button id="fit-gallery" class="secondary">选择已有视频</button><input type="file" id="fit-camera-input" accept="video/*" capture="environment" hidden><input type="file" id="fit-gallery-input" accept="video/*" hidden><div id="file-area"></div><p class="tip">可选：选择视频后标定器械，查看速度和功率。</p></div></section></div>`;
  $('#fitness-library-back').onclick=()=>backToLibrary('fitness');
  document.querySelectorAll('[data-fit-side]').forEach(b=>b.onclick=()=>{if(state.file&&!confirm('切换观察侧会清除已选录像，是否继续？'))return;clearFile();state.side=b.dataset.fitSide;fitnessPage();});
  $('#fit-camera').onclick=()=>$('#fit-camera-input').click();$('#fit-gallery').onclick=()=>$('#fit-gallery-input').click();
  for(const id of ['fit-camera-input','fit-gallery-input'])$('#'+id).onchange=e=>chooseFile(e.target.files[0]);
  fileArea();
}

function fitnessChart(series){
  if(!series.some(s=>Number.isFinite(s.angle)))return '<p class="tip">未识别到清楚的动作，暂无曲线。</p>';
  const first=series[0].t, last=series[series.length-1].t, span=Math.max(.1,last-first);
  let d='', pen=false;
  for(const s of series){if(!Number.isFinite(s.angle)){pen=false;continue;}const x=40+(s.t-first)/span*490,y=175-s.angle/180*150;d+=`${pen?'L':'M'}${x.toFixed(1)},${y.toFixed(1)} `;pen=true;}
  return `<svg class="fit-chart" viewBox="0 0 555 215" role="img" aria-label="主要关节二维角度随视频时间变化，断线表示缺测"><path class="axis" d="M40 25V175H530 M40 100H530"/><text x="4" y="30">180°</text><text x="10" y="105">90°</text><text x="16" y="180">0°</text><text x="40" y="203">${number(first,'s')}</text><text x="480" y="203">${number(last,'s')}</text><path class="curve" d="${d}"/></svg>`;
}

function renderFitnessReport(j){
  const r=j.result,s=r.summary,ex=r.spec,reps=r.repetitions;
  app.innerHTML=`<button class="back" id="fit-back">‹ 返回我的记录</button><div class="page-head"><span class="tag">健身分析 · ${sideLabel(j.side)} · 侧面录像</span><h1>${esc(ex.label)} · 训练报告</h1><p>${dateLabel(j.created_at)}</p></div><div class="layout"><section><div class="card"><h2>${s.completed?'本组结果':'未识别到完整动作'}</h2><div class="stat-grid"><div class="stat"><strong>${s.completed}<small> 次</small></strong><small>完整动作</small></div><div class="stat"><strong>${Number.isFinite(s.valid_ratio)?Math.round(s.valid_ratio*100)+'%':'—'}</strong><small>有效画面占比</small></div><div class="stat"><strong>${number(s.mean_cycle_s,'s')}</strong><small>平均每次用时</small></div><div class="stat"><strong>${s.partial}<small> 段</small></strong><small>未完成片段</small></div></div><p class="fit-summary">${s.completed?`识别到 ${s.completed} 次完整动作，可逐次回看。`:'请拍下动作从开始到回位的全过程，并让测试部位保持入镜。'}</p>${Number.isFinite(s.tempo_cv)?`<p class="tip">用时波动：${Math.round(s.tempo_cv*100)}%（越小表示节奏越稳定）。</p>`:''}</div><div class="card"><h3>${esc(s.primary_metric_label)} · 角度变化</h3>${fitnessChart(r.series)}<p class="caption">曲线断开处为未识别到的片段。</p></div><div class="card"><h3>角度范围</h3>${Object.values(s.metrics).map(m=>`<div class="metric-row"><span>${esc(m.label)}<small>有效画面 ${Math.round(m.coverage*100)}% · ${m.samples} 帧</small></span><strong>${number(m.min)}–${number(m.max)}${m.unit==='deg'?'°':''}</strong></div>`).join('')||'<p class="tip">暂无数据，请重新录制。</p>'}</div></section><section><div class="card"><h3>动作回看</h3>${j.video_available?`<div class="fit-video"><video id="fit-video" controls playsinline preload="metadata" src="/api/jobs/${j.id}/video"></video><canvas id="fit-overlay" aria-hidden="true"></canvas></div><p class="fit-key-note" id="fit-key-note">点击下方时间，回看对应动作。</p><button class="danger" id="fit-delete">删除原始录像，保留分析结果</button>`:'<p class="warning">原始录像已删除，角度、时间和分析结果仍保留。</p>'}<div class="fit-reps-scroll">${reps.map((rep,i)=>`<article class="fit-rep"><h3>第 ${rep.number} 次<span>用时 ${number(rep.total_s,'s')}</span></h3><p class="tip">${esc(ex.phases[0])}至峰值 ${number(rep.outbound_s,'s')} · 峰值后${esc(ex.phases[1])} ${number(rep.return_s,'s')}<br>角度变化 ${number(rep.range_deg,'°')} · 平均角速度 ${number(rep.outbound_mean_angular_rate,'°/s')}</p><div class="keyframes">${[['start','起点'],['turn','峰值'],['end','回位']].map(([key,text])=>`<button data-rep="${i}" data-key="${key}" ${j.video_available?'':'disabled'}>${text} ${number(rep[key].t,'s')}</button>`).join('')}</div>${rep.notes.map(t=>`<p class="warning">${esc(t)}</p>`).join('')}</article>`).join('')||'<p class="tip">识别到完整动作后，可在这里逐次回看。</p>'}</div></div><div class="card"><details><summary>测量说明</summary><p>有效画面占比反映画面是否清楚，不是动作评分。动作时间包含停顿。</p><p>${esc(ex.note)}</p>${r.limitations.map(t=>esc(t)).join('<br>')}<br>请使用固定侧面机位。<br>计次角度：${ex.start_angle}° → ${ex.turn_angle}° → ${ex.start_angle}°。仅用于计次，不必刻意达到这些角度。</details><button id="fit-again" class="secondary">再分析一组</button></div></section></div>`;
  $('#fit-back').onclick=()=>navigate('history');$('#fit-again').onclick=()=>navigate('fitness');
  if(r.barbell){$('.page-head').insertAdjacentHTML('afterend',barReport(r.barbell));bindBarReport(r.barbell);}
  if(r.barbell&&j.video_available)$('#fit-key-note').textContent='黄色表示器械轨迹，绿色表示人体关节。';
  if(!j.video_available)return;
  const video=$('#fit-video'), canvas=$('#fit-overlay');let active=null;
  const overlay=()=>{
    const rect=video.getBoundingClientRect();canvas.width=Math.round(rect.width);canvas.height=Math.round(rect.height);
    const ctx=canvas.getContext('2d');ctx.clearRect(0,0,canvas.width,canvas.height);
    if(!video.videoWidth)return;
    const [cw,ch]=r.conditions.size;
    if(Math.abs(video.videoWidth/video.videoHeight-cw/ch)>.04)return;
    const scale=Math.min(canvas.width/video.videoWidth,canvas.height/video.videoHeight);
    const w=video.videoWidth*scale,h=video.videoHeight*scale,dx=(canvas.width-w)/2,dy=(canvas.height-h)/2;
    if(r.barbell&&video.paused)drawBarOverlay(ctx,r.barbell,video.currentTime,w,h,dx,dy);
    if(!active||Math.abs(video.currentTime-active.t)>.2)return;
    const p=active.points;ctx.strokeStyle='#94edb0';ctx.fillStyle='#94edb0';ctx.lineWidth=3;
    for(const [a,b] of [['shoulder','elbow'],['elbow','wrist'],['shoulder','hip'],['hip','knee'],['knee','ankle']])if(p[a]&&p[b]){ctx.beginPath();ctx.moveTo(dx+p[a][0]*w,dy+p[a][1]*h);ctx.lineTo(dx+p[b][0]*w,dy+p[b][1]*h);ctx.stroke();}
    for(const xy of Object.values(p)){ctx.beginPath();ctx.arc(dx+xy[0]*w,dy+xy[1]*h,4,0,Math.PI*2);ctx.fill();}
  };
  video.ontimeupdate=overlay;video.onseeked=overlay;video.onplay=()=>{active=null;overlay();};
  video.onerror=()=>{active=null;overlay();$('#fit-key-note').textContent='视频无法播放，分析结果仍可查看。下次请使用普通 H.264 录像。';};
  document.querySelectorAll('[data-rep]').forEach(b=>b.onclick=()=>{const rep=reps[Number(b.dataset.rep)],sample=rep[b.dataset.key];active=sample;const seek=()=>{video.pause();video.currentTime=Math.min(sample.t,video.duration);overlay();};if(video.readyState<1)video.addEventListener('loadedmetadata',seek,{once:true});else seek();$('#fit-key-note').textContent=`第 ${rep.number} 次 · ${b.textContent} · 主角度 ${number(sample.angle,'°')}`;video.scrollIntoView({behavior:'smooth',block:'center'});});
  $('#fit-delete').onclick=async()=>{if(!confirm('删除本次原始录像？删除后无法回放，分析结果会保留。'))return;try{await api('/jobs/'+j.id+'/video',{method:'DELETE'});await showJob(j.id);toast('原始录像已删除，分析结果保留');}catch(e){toast(e.message);}};
}
