'use strict';
function mountBarCalibration(){
  if(state.selected==='fitness_pushup')return;
  $('#upload-btn').insertAdjacentHTML('beforebegin',`<section class="bar-calibration"><label class="consent"><input id="bar-enable" type="checkbox"><span>分析器械速度和功率</span></label><div id="bar-setup" hidden><h3>标记器械和参考长度</h3><p class="tip">手机固定侧拍，标尺与器械放在同一平面。</p><p class="camera-note" id="bar-step">正在读取画面…</p><canvas id="bar-frame" aria-label="录像第一帧：按顺序点选长度两端及器械标记" role="img"></canvas><button class="secondary" id="bar-reset" type="button">重新标记</button><label>参考长度（厘米）<input id="bar-length" type="number" inputmode="decimal" min="5" max="300" step="0.1" placeholder="填写实测长度"></label><label>器械总重量（千克，选填）<input id="bar-mass" type="number" inputmode="decimal" min="0.1" max="500" step="0.1" placeholder="杠杆与两侧配重的总重量"></label><p class="tip">不填重量时，只分析运动速度。标记处可贴十字胶带，方便识别。</p><details><summary>拍摄要求</summary><p>固定、水平侧拍，标尺与器械处于同一平面；不要移动镜头、变焦或使用慢动作。建议 60 fps。</p><p>选择器械端部不旋转的标记。使用自由重量，不接触器械架，也不借助绳索、弹力带或他人助力。数据反映器械运动，不是肌肉力量。</p></details><label class="consent"><input id="bar-confirm" type="checkbox"><span>已核对长度和重量，并按拍摄要求录制。</span></label></div></section>`);
  let points=[],frameReady=false;
  const canvas=$('#bar-frame'),ctx=canvas.getContext('2d'),source=document.createElement('video');
  source.muted=true;source.playsInline=true;source.preload='auto';source.src=state.url;
  let still=null;
  const draw=()=>{if(!still)return;ctx.drawImage(still,0,0);const radius=Math.max(6,Math.min(canvas.width,canvas.height)*.025);ctx.lineWidth=Math.max(2,canvas.width/300);ctx.font=`bold ${Math.max(18,canvas.width/35)}px sans-serif`;for(let i=0;i<points.length;i++){const [x,y]=points[i].map((v,k)=>v*(k?canvas.height:canvas.width));ctx.strokeStyle=ctx.fillStyle=i===2?'#ffbf58':'#74f1bf';ctx.beginPath();ctx.arc(x,y,i===2?radius:radius/2,0,Math.PI*2);ctx.stroke();ctx.fillText(String(i+1),x+radius,y);}if(points.length>=2){ctx.strokeStyle='#74f1bf';ctx.beginPath();ctx.moveTo(points[0][0]*canvas.width,points[0][1]*canvas.height);ctx.lineTo(points[1][0]*canvas.width,points[1][1]*canvas.height);ctx.stroke();}$('#bar-step').textContent=['① 点击参考长度的一端','② 点击参考长度的另一端','③ 点击器械端部的标记中心','标记完成，请填写参考长度。'][points.length];};
  source.onloadeddata=()=>{if(!canvas.isConnected)return;canvas.width=source.videoWidth;canvas.height=source.videoHeight;still=document.createElement('canvas');still.width=canvas.width;still.height=canvas.height;still.getContext('2d').drawImage(source,0,0);frameReady=true;draw();};
  source.onerror=()=>{if($('#bar-step'))$('#bar-step').textContent='无法读取画面，请换一段普通录像，或关闭器械分析。';};
  canvas.onpointerdown=e=>{if(!frameReady||points.length===3)return;const r=canvas.getBoundingClientRect();points.push([(e.clientX-r.left)/r.width,(e.clientY-r.top)/r.height]);draw();};
  $('#bar-reset').onclick=()=>{points=[];state.barCalibration=null;draw();};
  $('#bar-enable').onchange=e=>{$('#bar-setup').hidden=!e.target.checked;};
  canvas.barPoints=()=>({points,size:[canvas.width,canvas.height],frameReady});
}
function readBarCalibration(){
  if(!$('#bar-enable')?.checked)return null;
  const {points,size,frameReady}=$('#bar-frame').barPoints();
  if(!frameReady||points.length!==3)throw Error('请先完成画面上的三个标记');
  if(!$('#bar-confirm').checked)throw Error('请确认拍摄要求，或关闭器械分析');
  const length=Number($('#bar-length').value)/100,massText=$('#bar-mass').value,mass=massText?Number(massText):null;
  if(!Number.isFinite(length)||length<.05||length>3)throw Error('请输入 5–300 厘米的实测长度');
  if(mass!==null&&(!Number.isFinite(mass)||mass<.1||mass>500))throw Error('请检查器械重量，不清楚可留空');
  if(Math.hypot((points[1][0]-points[0][0])*size[0],(points[1][1]-points[0][1])*size[1])<30)throw Error('两点太近，请换一段更长的参考距离');
  return {reference_a:points[0],reference_b:points[1],target:points[2],size,length_m:length,mass_kg:mass,confirmed:true};
}
function physicalNumber(v,unit=''){return Number.isFinite(v)?`${Math.abs(v)<10?v.toFixed(2):v.toFixed(1)}${unit}`:'暂无数据';}
function barChart(series,key,unit){
  const values=series.map(s=>s[key]).filter(Number.isFinite);if(!values.length)return '<p class="tip">暂无曲线，请检查画面和重量设置。</p>';
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
function barReport(r){
  const s=r.summary,c=r.calibration;
  return `<section class="bar-report"><div class="card bar-intro"><span class="tag">${r.synthetic?'示例数据':'视频估算'}</span><h2>器械表现</h2><p class="caption">${r.synthetic?'此示例不计入训练记录。':''} 参考长度 ${physicalNumber(c.length_m*100,' cm')} · ${c.mass_kg===null?'未填重量':`器械 ${physicalNumber(c.mass_kg,' kg')}`}</p><div class="stat-grid"><div class="stat"><strong>${physicalNumber(s.peak_velocity_m_s)}</strong><small>最快上升速度 · m/s</small></div><div class="stat"><strong>${physicalNumber(s.peak_force_n)}</strong><small>峰值外力（估算）· N</small></div><div class="stat"><strong>${physicalNumber(s.peak_power_w)}</strong><small>峰值功率（估算）· W</small></div><div class="stat"><strong>${s.bounded_segments}</strong><small>有效上升次数</small></div></div><p class="tip">反映器械运动，不代表肌肉力量。</p>${r.stop_reason?`<p class="warning">${esc(r.stop_reason)}</p>`:''}<p class="tip">${Number.isFinite(s.last_vs_best_velocity_loss_pct)?`最后一段比本组最快速度下降 ${physicalNumber(s.last_vs_best_velocity_loss_pct,'%')}。`:''}</p></div><div class="layout"><div class="card"><h3>上升速度 · m/s</h3>${barChart(r.series,'velocity_m_s','竖直速度 m/s')}<h3>运动轨迹</h3>${barTrajectory(r.series)}<p class="tip">正值为上升，负值为下降。</p></div><div class="card"><h3>每段表现</h3>${r.lifts.map((l,i)=>`<article class="fit-rep"><h3>第 ${l.number} 次上升 · ${l.bounded?'完整':'未录完整'}</h3><p>平均速度 ${physicalNumber(l.mean_velocity_m_s,' m/s')} · 峰速 ${physicalNumber(l.peak_velocity_m_s,' m/s')}<br>达到峰速用时 ${physicalNumber(l.time_to_peak_s,' s')} · 上升距离 ${physicalNumber(l.displacement_m*100,' cm')}<br>峰值功率（估算）${physicalNumber(l.peak_power_w,' W')}</p>${r.synthetic?'':`<button class="secondary" data-bar-peak="${i}">回看最快时刻 ${physicalNumber(l.peak_time_s,'s')}</button>`}</article>`).join('')||'<p class="tip">未识别到完整上升，请拍下完整的抬起过程。</p>'}</div></div><div class="card"><details><summary>更多数据与测量说明</summary><h3>竖直加速度 · m/s²</h3>${barChart(r.series,'acceleration_m_s2','加速度 m/s²')}<h3>竖直外力（估算）· N</h3>${barChart(r.series,'force_n','外力 N')}<h3>竖直功率（估算）· W</h3>${barChart(r.series,'power_w','功率 W')}<p>有效跟踪 ${Math.round(s.tracked_ratio*100)}%。上升次数只统计器械抬起阶段，与完整动作次数分开。</p><p>${r.assumptions.map(esc).join('<br>')}</p><p>规则 ${esc(r.version)}。结果供训练回看参考，请勿据此增加负重。</p></details></div></section>`;
}
function bindBarReport(r){document.querySelectorAll('[data-bar-peak]').forEach(b=>b.onclick=()=>{const video=$('#fit-video');if(!video)return toast('原视频已删除，不能回看');if(video.readyState<1)return toast('原视频尚未就绪或编码不受浏览器支持');video.pause();video.currentTime=r.lifts[Number(b.dataset.barPeak)].peak_time_s;video.scrollIntoView({behavior:'smooth',block:'center'});});}
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
