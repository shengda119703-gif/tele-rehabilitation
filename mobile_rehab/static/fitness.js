'use strict';
function fitnessPage(){
  const catalog=state.fitnessCatalog||[];
  if(!catalog.length){app.innerHTML='<div class="card empty"><h2>健身服务尚未加载</h2><p>请更新电脑服务后刷新页面。</p></div>';return;}
  if(!catalog.some(x=>x.id===state.selected))state.selected='fitness_squat';
  const ex=catalog.find(x=>x.id===state.selected);
  app.innerHTML=`<section class="hero fitness-hero"><div class="hero-orbit" aria-hidden="true"></div><div class="eyebrow">TRAIN. REVIEW. PROGRESS.</div><h1>每一次训练，<br>看得更明白。</h1><p>拍一组动作，回看次数、角度与节奏。</p></section><div class="steps"><span class="current">01 选择动作</span><span>02 录制上传</span><span>03 分析回看</span></div><div class="layout"><section><div class="section-head"><h2>今天练什么？</h2><small>${catalog.length} 项常见动作</small></div><div class="fitness-grid">${catalog.map(x=>`<button data-fitness="${x.id}" class="${x.id===ex.id?'selected':''}" aria-pressed="${x.id===ex.id}"><strong>${esc(x.label)}</strong><small>${esc(x.group)} · 侧面拍摄</small></button>`).join('')}</div><div class="card tint"><h3>只分析你实际拍到的内容</h3><p class="tip">一段视频只录一种动作、一组训练。使用固定侧面机位，不要移动、变焦或剪接；先保持起点约 2 秒，再开始动作。</p><p class="tip">先用自己已掌握的动作和熟悉的安排演示。不要为测试提高重量或追求极限；重物训练应有合适保护。</p></div></section><section><div class="card fitness-guidance" id="fitness-guide"><span class="tag">健身录像分析 · 非康复处方</span><h2>${esc(ex.label)}</h2><div class="side" aria-label="观察侧"><button data-fit-side="left" class="${state.side==='left'?'selected':''}">本人左侧</button><button data-fit-side="right" class="${state.side==='right'?'selected':''}">本人右侧</button></div><p class="camera-note">${esc(ex.camera)}</p>${ex.steps.map((t,i)=>`<div class="instruction"><span class="number">${i+1}</span><p>${esc(t)}</p></div>`).join('')}<details><summary>这项分析能看什么？</summary>${esc(ex.note)}<br>主指标：${esc(ex.metric_label)}。依据你选择的动作切分往返，不自动辨认动作种类。</details></div><div class="card"><h3>录一组，看看表现</h3><p class="tip">建议 15–40 秒，最长 2 分钟 / 256 MB；普通 720p 或 1080p 录像。</p><button id="fit-camera" class="primary file-actions">打开手机相机录像</button><button id="fit-gallery" class="secondary">选择已有训练录像</button><input type="file" id="fit-camera-input" accept="video/*" capture="environment" hidden><input type="file" id="fit-gallery-input" accept="video/*" hidden><div id="file-area"></div><p class="tip">录制后分析，不在手机系统相机内实时纠错。</p></div></section></div>`;
  document.querySelectorAll('[data-fitness]').forEach(b=>b.onclick=()=>{clearFile();state.selected=b.dataset.fitness;fitnessPage();if(innerWidth<651)$('#fitness-guide').scrollIntoView({behavior:'smooth'});});
  document.querySelectorAll('[data-fit-side]').forEach(b=>b.onclick=()=>{if(state.file&&!confirm('切换观察侧会清除已选录像，是否继续？'))return;clearFile();state.side=b.dataset.fitSide;fitnessPage();});
  $('#fit-camera').onclick=()=>$('#fit-camera-input').click();$('#fit-gallery').onclick=()=>$('#fit-gallery-input').click();
  for(const id of ['fit-camera-input','fit-gallery-input'])$('#'+id).onchange=e=>chooseFile(e.target.files[0]);
  fileArea();
  const demo=document.createElement('button');demo.className='secondary';demo.textContent='体验速度与功率示例（模拟数据）';demo.onclick=showBarDemo;$('.fitness-hero').after(demo);
}

function fitnessChart(series){
  if(!series.some(s=>Number.isFinite(s.angle)))return '<p class="tip">没有足够的关键点，暂时无法绘制角度曲线。</p>';
  const first=series[0].t, last=series[series.length-1].t, span=Math.max(.1,last-first);
  let d='', pen=false;
  for(const s of series){if(!Number.isFinite(s.angle)){pen=false;continue;}const x=40+(s.t-first)/span*490,y=175-s.angle/180*150;d+=`${pen?'L':'M'}${x.toFixed(1)},${y.toFixed(1)} `;pen=true;}
  return `<svg class="fit-chart" viewBox="0 0 555 215" role="img" aria-label="主要关节二维角度随视频时间变化，断线表示缺测"><path class="axis" d="M40 25V175H530 M40 100H530"/><text x="4" y="30">180°</text><text x="10" y="105">90°</text><text x="16" y="180">0°</text><text x="40" y="203">${number(first,'s')}</text><text x="480" y="203">${number(last,'s')}</text><path class="curve" d="${d}"/></svg>`;
}

function renderFitnessReport(j){
  const r=j.result,s=r.summary,ex=r.spec,reps=r.repetitions;
  app.innerHTML=`<button class="back" id="fit-back">‹ 返回我的记录</button><div class="page-head"><span class="tag">健身分析 · ${sideLabel(j.side)} · 侧面录像</span><h1>${esc(ex.label)} · 本组回顾</h1><p>${dateLabel(j.created_at)} · ${esc(r.rule_version)}</p></div><div class="layout"><section><div class="card"><h2>${s.completed?'看看这一组的表现':'已分析，暂未观察到完整往返'}</h2><div class="stat-grid"><div class="stat"><strong>${s.completed}<small> 次</small></strong><small>观察到的完整往返</small></div><div class="stat"><strong>${Number.isFinite(s.valid_ratio)?Math.round(s.valid_ratio*100)+'%':'—'}</strong><small>可用观察时长占比</small></div><div class="stat"><strong>${number(s.mean_cycle_s,'s')}</strong><small>平均每次往返时间</small></div><div class="stat"><strong>${s.partial}<small> 段</small></strong><small>未形成完整往返的片段</small></div></div><p class="fit-summary">${s.completed?`本段观察到 ${s.completed} 次完整往返。点击下方每次动作的起点、峰值和回位，可以对照原始录像。`:'请确认所选动作与录像一致，观察侧关节完整入镜，并录下起点、动作和回位。没有计数不等于你的动作做错了。'}</p><p class="tip">可用观察占比不是动作质量分数。计次阈值是本版工程规则，不是合格动作标准。</p>${Number.isFinite(s.tempo_cv)?`<p class="tip">往返时间变异系数：${Math.round(s.tempo_cv*100)}%（至少 3 次时提供；数值越小仅代表本组用时越接近，不等于动作更正确）。</p>`:''}</div><div class="card"><h3>${esc(s.primary_metric_label)} · 时间曲线</h3>${fitnessChart(r.series)}<p class="caption">单位为度，横轴为录像时间。平滑后的投影角用于切分动作；缺测处不连线。</p></div><div class="card"><h3>本段可观察指标</h3>${Object.values(s.metrics).map(m=>`<div class="metric-row"><span>${esc(m.label)}<small>有效帧覆盖 ${Math.round(m.coverage*100)}% · ${m.samples} 个样本</small></span><strong>${number(m.min)}–${number(m.max)}${m.unit==='deg'?'°':''}</strong></div>`).join('')||'<p class="tip">没有可用测量，不填入猜测值。</p>'}<p class="tip">${esc(ex.note)} 指标范围来自有效帧，不是推荐或正常范围。</p></div></section><section><div class="card"><h3>关键时刻，回到录像看</h3>${j.video_available?`<div class="fit-video"><video id="fit-video" controls playsinline preload="metadata" src="/api/jobs/${j.id}/video"></video><canvas id="fit-overlay" aria-hidden="true"></canvas></div><p class="fit-key-note" id="fit-key-note">点击关键时刻可暂停回看；彩色线仅标出当时可见的观察侧关节。</p><button class="danger" id="fit-delete">删除原始录像，保留分析结果</button>`:'<p class="warning">原始录像已删除，角度、时间和分析结果仍保留。</p>'}<div class="fit-reps-scroll">${reps.map((rep,i)=>`<article class="fit-rep"><h3>第 ${rep.number} 次<span>本次往返 ${number(rep.total_s,'s')}</span></h3><p class="tip">${esc(ex.phases[0])}至峰值 ${number(rep.outbound_s,'s')} · 峰值后${esc(ex.phases[1])} ${number(rep.return_s,'s')}<br>起点至峰值角变化 ${number(rep.range_deg,'°')} · 平均角变化率 ${number(rep.outbound_mean_angular_rate,'°/s')}</p><div class="keyframes">${[['start','起点'],['turn','峰值'],['end','回位']].map(([key,text])=>`<button data-rep="${i}" data-key="${key}" ${j.video_available?'':'disabled'}>${text} ${number(rep[key].t,'s')}</button>`).join('')}</div>${rep.notes.map(t=>`<p class="warning">${esc(t)}</p>`).join('')}</article>`).join('')||'<p class="tip">观察到完整往返后，这里会出现逐次回看入口。</p>'}</div></div><div class="card"><h3>如何理解这份分析</h3><p class="tip">阶段时间按起点、角度峰值、回位时刻划分，停顿可能包含其中；平均角变化率不是杠铃线速度。</p><details><summary>测量条件与限制</summary>${r.limitations.map(t=>esc(t)).join('<br>')}<br>固定侧面由用户选择，系统未验证机位。<br>切分角：${ex.start_angle}° → ${ex.turn_angle}° → ${ex.start_angle}°。仅为本版计次规则，无需为了计数追求这些角度。</details><button id="fit-again" class="secondary">分析另一组动作</button></div></section></div>`;
  $('#fit-back').onclick=()=>navigate('history');$('#fit-again').onclick=()=>navigate('fitness');
  if(r.barbell){$('.page-head').insertAdjacentHTML('afterend',barReport(r.barbell));bindBarReport(r.barbell);}
  if(r.barbell&&j.video_available)$('#fit-key-note').textContent='可点击峰速或动作关键时刻回看；黄色为器械标记与最近轨迹，绿色为当时可见的人体关键点。';
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
  video.onerror=()=>{active=null;overlay();$('#fit-key-note').textContent='当前浏览器无法播放这段录像，分析数值仍可查看。后续建议使用普通 H.264 / AVC 录像，关闭高效率 HEVC 编码。';};
  document.querySelectorAll('[data-rep]').forEach(b=>b.onclick=()=>{const rep=reps[Number(b.dataset.rep)],sample=rep[b.dataset.key];active=sample;const seek=()=>{video.pause();video.currentTime=Math.min(sample.t,video.duration);overlay();};if(video.readyState<1)video.addEventListener('loadedmetadata',seek,{once:true});else seek();$('#fit-key-note').textContent=`第 ${rep.number} 次 · ${b.textContent} · 主角度 ${number(sample.angle,'°')}`;video.scrollIntoView({behavior:'smooth',block:'center'});});
  $('#fit-delete').onclick=async()=>{if(!confirm('删除本次原始录像？删除后无法回放，分析结果会保留。'))return;try{await api('/jobs/'+j.id+'/video',{method:'DELETE'});await showJob(j.id);toast('原始录像已删除，分析结果保留');}catch(e){toast(e.message);}};
}
