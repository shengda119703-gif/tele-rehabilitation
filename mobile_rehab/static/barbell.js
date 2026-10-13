'use strict';
function mountBarCalibration(){
  $('#upload-btn').insertAdjacentHTML('beforebegin','<section class="bar-calibration"><p role="status">轨迹自动分析，无需标点。</p></section>');
}
function readBarCalibration(){return null;}
function physicalNumber(v,unit=''){return Number.isFinite(v)?`${Math.abs(v)<10?v.toFixed(2):v.toFixed(1)}${unit}`:'暂无数据';}
function barChart(series,key,unit){
  const values=series.map(s=>s[key]).filter(Number.isFinite);if(!values.length)return '<p class="tip">本段暂无连续曲线。</p>';
  const lo=Math.min(0,...values),hi=Math.max(.01,...values),range=hi-lo||1,first=series[0].t,span=Math.max(.1,series.at(-1).t-first);let path='',pen=false;
  for(const s of series){if(!Number.isFinite(s[key])){pen=false;continue;}path+=`${pen?'L':'M'}${(48+480*(s.t-first)/span).toFixed(1)},${(180-150*(s[key]-lo)/range).toFixed(1)} `;pen=true;}
  return `<svg class="fit-chart" viewBox="0 0 555 220" role="img" aria-label="${unit} 随录像时间变化"><path class="axis" d="M48 30V180H530"/><text x="3" y="25">${physicalNumber(hi)}</text><text x="3" y="184">${physicalNumber(lo)}</text><text x="48" y="210">${physicalNumber(first,'s')}</text><text x="460" y="210">${physicalNumber(series.at(-1).t,'s')}</text><path class="curve" d="${path}"/></svg>`;
}
function barTrajectory(series){
  const points=series.filter(s=>s.x_m!==null&&s.height_m!==null);if(!points.length)return '';
  const xs=points.map(s=>s.x_m),ys=points.map(s=>s.height_m),xmin=Math.min(...xs),xmax=Math.max(...xs),ymin=Math.min(...ys),ymax=Math.max(...ys),scale=Math.min(270/Math.max(.05,xmax-xmin),180/Math.max(.05,ymax-ymin));let d='',pen=false;
  for(const s of series){if(s.x_m===null){pen=false;continue;}d+=`${pen?'L':'M'}${(160+(s.x_m-(xmin+xmax)/2)*scale).toFixed(1)},${(110-(s.height_m-(ymin+ymax)/2)*scale).toFixed(1)} `;pen=true;}
  return `<svg class="fit-chart bar-trajectory" viewBox="0 0 320 220" role="img" aria-label="器械二维等比例轨迹，上方表示抬高"><path class="curve" d="${d}"/></svg>`;
}
function barReport(r,context={}){
  if(r.automatic)return automaticMotionReport(r);
  const s=r.summary,c=r.calibration;
  // Only the marked TEST account's saved history uses compact labels.
  // Standalone examples and ordinary patient/video reports keep their provenance.
  const testHistory=context.testHistory===true&&r.synthetic===true&&r.fixture==='test-lin-profile-v1'&&r.participant_name==='TEST 林女士';
  const qualifier=testHistory?'':'（估算）';
  return `<section class="bar-report"><div class="card bar-intro"><span class="tag">${testHistory?'器械数据':r.synthetic?'示例数据':'视频估算'}</span><h2>器械表现</h2><p class="caption">${r.synthetic&&!testHistory?'此示例不计入训练记录。':''} 参考长度 ${physicalNumber(c.length_m*100,' cm')} · ${c.mass_kg===null?'未填重量':`负重 ${physicalNumber(c.mass_kg,' kg')}`}</p><div class="stat-grid"><div class="stat"><strong>${physicalNumber(s.peak_velocity_m_s)}</strong><small>最快上升速度 · m/s</small></div><div class="stat"><strong>${physicalNumber(s.peak_force_n)}</strong><small>峰值外力${qualifier} · N</small></div><div class="stat"><strong>${physicalNumber(s.peak_power_w)}</strong><small>峰值功率${qualifier} · W</small></div><div class="stat"><strong>${s.bounded_segments}</strong><small>有效上升次数</small></div></div><p class="tip">反映器械运动，不代表肌肉力量。</p>${r.stop_reason?`<p class="warning">${esc(r.stop_reason)}</p>`:''}<p class="tip">${Number.isFinite(s.last_vs_best_velocity_loss_pct)?`最后一段比本组最快速度下降 ${physicalNumber(s.last_vs_best_velocity_loss_pct,'%')}。`:''}</p></div><div class="layout"><div class="card"><h3>上升速度 · m/s</h3>${barChart(r.series,'velocity_m_s','竖直速度 m/s')}<h3>运动轨迹</h3>${barTrajectory(r.series)}<p class="tip">正值为上升，负值为下降。</p></div><div class="card"><h3>每段表现</h3>${r.lifts.map((l,i)=>`<article class="fit-rep"><h3>第 ${l.number} 次上升 · ${l.bounded?'完整':'未录完整'}</h3><p>平均速度 ${physicalNumber(l.mean_velocity_m_s,' m/s')} · 峰速 ${physicalNumber(l.peak_velocity_m_s,' m/s')}<br>达到峰速用时 ${physicalNumber(l.time_to_peak_s,' s')} · 上升距离 ${physicalNumber(l.displacement_m*100,' cm')}<br>峰值功率${qualifier}${physicalNumber(l.peak_power_w,' W')}</p>${r.synthetic?'':`<button class="secondary" data-bar-peak="${i}">回看最快时刻 ${physicalNumber(l.peak_time_s,'s')}</button>`}</article>`).join('')||'<p class="tip">未识别到完整上升，请拍下完整的抬起过程。</p>'}</div></div><div class="card"><details><summary>更多数据与测量说明</summary><h3>竖直加速度 · m/s²</h3>${barChart(r.series,'acceleration_m_s2','加速度 m/s²')}<h3>竖直外力${qualifier} · N</h3>${barChart(r.series,'force_n','外力 N')}<h3>竖直功率${qualifier} · W</h3>${barChart(r.series,'power_w','功率 W')}<p>有效跟踪 ${Math.round(s.tracked_ratio*100)}%。上升次数只统计器械抬起阶段，与完整动作次数分开。</p><p>${r.assumptions.map(esc).join('<br>')}</p><p>规则 ${esc(r.version)}。结果供训练回看参考，请勿据此增加负重。</p></details></div></section>`;
}
function bindBarReport(r){document.querySelectorAll('[data-bar-peak]').forEach(b=>b.onclick=()=>{const video=$('#fit-video');if(!video)return toast('原视频已删除，不能回看');if(video.readyState<1)return toast('原视频尚未就绪或编码不受浏览器支持');video.pause();video.currentTime=r.lifts[Number(b.dataset.barPeak)].peak_time_s;video.scrollIntoView({behavior:'smooth',block:'center'});});}
function automaticMotionReport(r){
 const m=r.measurement||{},s=r.summary||{},metric=m.length_unit==='m',unit=esc(m.speed_unit||'画面高度/s'),speed=metric?s.peak_velocity_m_s:s.peak_relative_velocity;
 const kind=m.target_kind==='plate'?'器械轨迹':m.target_kind==='wrist'?(m.target_source==='right_wrist'?'右手腕轨迹':m.target_source==='left_wrist'?'左手腕轨迹':'手腕轨迹'):'运动轨迹';
 const velocityKey=metric?'velocity_m_s':'relative_velocity';
 const liftHTML=(r.lifts||[]).map((l,i)=>`<article class="fit-rep"><h3>第 ${esc(l.number)} 段上升${l.bounded?'':' · 未录完整'}</h3><p>平均速度 ${physicalNumber(l.mean_velocity)} ${unit}<br>上升用时 ${physicalNumber(l.duration_s,' s')}</p><button class="secondary" data-bar-peak="${i}">回看最快时刻 ${physicalNumber(l.peak_time_s,'s')}</button></article>`).join('');
 return `<section class="bar-report"><div class="card bar-intro"><h2>${kind}</h2><div class="stat-grid"><div class="stat"><strong>${physicalNumber(speed)}</strong><small>最快上升速度 · ${unit}</small></div><div class="stat"><strong>${esc(s.bounded_segments||0)}</strong><small>完整上升段</small></div>${metric?`<div class="stat"><strong>${physicalNumber(s.peak_specific_lifting_power_w_kg)}</strong><small>单位负重抬升功率 · W/kg</small></div>`:''}</div>${r.stop_reason?`<p class="caption">${esc(r.stop_reason)}</p>`:''}</div><div class="card"><h3>速度变化</h3>${barChart(r.series||[],velocityKey,unit)}${liftHTML}<details><summary>测量说明</summary><p>${(r.assumptions||[]).map(esc).join('<br>')}</p><p>自动跟踪覆盖 ${Math.round((s.tracked_ratio||0)*100)}%。规则 ${esc(r.version)}。</p></details></div></section>`;
}
function drawBarOverlay(ctx,r,time,w,h,dx,dy){
  const nearest=r.series.reduce((best,s)=>Math.abs(s.t-time)<Math.abs(best.t-time)?s:best,r.series[0]);
  if(!nearest?.point||Math.abs(nearest.t-time)>.06)return;
  ctx.strokeStyle='#ffbf58';ctx.lineWidth=3;ctx.beginPath();let pen=false,last=null;
  for(const s of r.series){if(s.t<time-2||s.t>time)continue;if(!s.point){pen=false;continue;}const x=dx+s.point[0]*w,y=dy+s.point[1]*h;if(!pen||s.t-last>.15)ctx.moveTo(x,y);else ctx.lineTo(x,y);pen=true;last=s.t;}ctx.stroke();ctx.beginPath();ctx.arc(dx+nearest.point[0]*w,dy+nearest.point[1]*h,8,0,Math.PI*2);ctx.stroke();
}
async function showBarDemo(){
  if(state.upload)return;clearTimeout(pollTimer);state.job='bar-demo';
  try{const result=await api('/fitness/demo');if(state.job!=='bar-demo')return;clearFile();app.innerHTML='<button id="bar-back" class="back">‹ 返回健身分析</button><div class="page-head"><span class="tag">示例报告</span><h1>40 kg 器械分析</h1><p>示例数据 · 3 次上升</p></div>'+barReport(result);$('#bar-back').onclick=()=>navigate('fitness');window.scrollTo(0,0);}catch(e){toast(e.message);}
}
