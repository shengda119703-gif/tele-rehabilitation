window.__linQa={status:'running'};
(async()=>{try{
 await PhoneLocal.ready;
 const wait=async fn=>{for(let n=0;n<160;n++){const value=fn();if(value)return value;await new Promise(r=>setTimeout(r,150));}throw Error('Not ready: '+document.body.innerText);};
 const snap=await PhoneLocal.snapshot(),L=PhoneLocal.store.value;
 if(snap.profile.profile.name!=='TEST 林女士'||L.jobs.length!==24||snap.attachments.length!==3||snap.state.events.filter(e=>e.measurement).length!==140)throw Error('TEST account import incomplete');
 const p=await PhoneLocal.request('/api/plan');if(p.progress.completed!==2||p.progress.total!==4)throw Error('Plan links incorrect');
 if(Object.values(L.daily.doses).some(d=>new Date(d.date+'T'+d.time+':00')>new Date()))throw Error('Future medication completion');
 if(window.__linPhase==='pages'){
  const checks=[];
  for(const [page,title]of [['home','我的记录与周报'],['rehab','日期安排'],['health','资料与图片'],['medication','用药'],['family','TEST 林晓'],['records','本周健康周报'],['assistant','']]){
   location.hash='#'+page;await wait(()=>ui.page===page&&!ui.busy&&document.querySelector('#content'));await wait(()=>document.body.innerText.includes(title));
   if(document.querySelectorAll('#nav a').length!==5)throw Error('Navigation changed');
   if(document.documentElement.scrollWidth>innerWidth+2)throw Error('Horizontal overflow on '+page);checks.push(page);
  }
  location.hash='#health';await wait(()=>ui.page==='health'&&document.querySelector('[data-archive]'));
  document.querySelector('[data-archive]').click();await wait(()=>document.querySelector('dialog[open]'));
  if(!document.querySelector('dialog a[href^="/api/product-archive/"]'))throw Error('Original text download unavailable');document.querySelector('dialog').close();
  for(const a of snap.attachments){const r=await PhoneLocal.request('/api/product-archive/'+a.id);if(!(r instanceof Response)||(await r.blob()).size===0)throw Error('Text original unreadable');}
  const b=await PhoneLocal.backup();PhoneStore.validateBackup(b);
  PhoneLin.familyOperation(PhoneLocal.store,'familyGrant',{member:L.fixture.members[0],categories:['health','rehab']});
  if(PhoneCloud.configured())throw Error('TEST cloud publication enabled');
  window.__linQa={status:'passed',pages:checks,health:140,archives:3,medicines:snap.profile.profile.medicationRecords.length,family:snap.familyMembers[0].name,backup:true};
 }else{
  navigate('history');await wait(()=>document.querySelectorAll('[data-job]').length===24);
  const reports=[];
  for(const job of L.jobs.filter(j=>j.mode==='fitness')){
   await showJob(job.id);await wait(()=>document.body.innerText.includes('训练报告'));const text=document.body.innerText;
   if(!text.includes('TEST 林女士')||!/20(?:\.0)?\s*kg/.test(text)||!text.includes('峰值功率'))throw Error('Fitness report missing data');
   if(text.includes('模拟')||text.includes('估算'))throw Error('TEST history has repeated labels');
   reports.push({exercise:job.exercise,count:job.result.summary.completed,mass:job.result.barbell.calibration.mass_kg,power:job.result.barbell.summary.peak_power_w});
  }
  const rehab=L.jobs.find(j=>j.mode==='assessment'&&j.exercise==='shoulder_abduction');await showJob(rehab.id);await wait(()=>document.body.innerText.includes('视频角度变化'));
  const training=L.jobs.find(j=>j.mode==='training');await showJob(training.id);await wait(()=>document.querySelector('#feedback-form')||document.body.innerText.includes('训练感受'));
  const posture=L.jobs.find(j=>j.mode==='posture');await showJob(posture.id);await wait(()=>document.body.innerText.includes('体态'));
  navigate('body');await wait(()=>document.body.innerText.includes('身体与训练汇总'));
  navigate('plan');await wait(()=>document.querySelector('#train-next'));document.querySelector('#train-next').click();await wait(()=>document.body.innerText.includes('记录本次训练'));
  if(!state.training||state.selected!=='shoulder_flexion')throw Error('Next training step not connected');
  window.__linQa={status:'passed',history:24,assessment:true,training:true,posture:true,body:true,plan:p.progress.completed+'/'+p.progress.total,next:state.selected,fitness:reports};
 }
}catch(e){window.__linQa={status:'failed',error:String(e.stack||e),text:document.body?.innerText};}})();
