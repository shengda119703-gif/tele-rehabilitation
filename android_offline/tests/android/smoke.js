// QA-only script. Real fixture videos exist solely in the separate ignored QA APK.
window.__qa={status:'running'};
(async()=>{try{
 await PhoneLocal.ready;
 const phase=QaFixtures.phase();
 const wait=async fn=>{for(let n=0;n<1200;n++){const out=fn();if(out)return out;await new Promise(r=>setTimeout(r,500));}throw Error('Timed out: '+document.body.innerText);};
 if(phase==='health'){
  await wait(()=>document.querySelector('#nav a'));
  if(document.querySelectorAll('#nav a').length!==5)throw Error('Five-page UI missing');
  document.querySelector('#profile').click();const form=document.querySelector('#profile-form');form.elements.name.value='TEST 手机';form.elements.age.value=30;form.requestSubmit();await wait(()=>!document.querySelector('dialog[open]'));
  location.hash='#assistant';await wait(()=>document.querySelector('#chat-form'));
  const textarea=document.querySelector('#draft');textarea.value='我今天体重65公斤';textarea.dispatchEvent(new Event('input',{bubbles:true}));document.querySelector('#chat-form').requestSubmit();await wait(()=>!ui.busy&&ui.draft==='');
  const snapshot=await PhoneLocal.snapshot();if(!snapshot.state.events.some(e=>e.measurement?.metric==='weight'))throw Error('Actual agent did not record weight');
  location.hash='#medication';await wait(()=>document.querySelector('#add-med'));document.querySelector('#add-med').click();const mf=document.querySelector('#med-form');mf.elements.name.value='TEST 药物';mf.elements.dose.value='按既有医嘱';mf.requestSubmit();await wait(()=>document.querySelector('#times-form'));const tf=document.querySelector('#times-form');tf.elements.times.value='08:00';tf.requestSubmit();await wait(()=>!document.querySelector('dialog[open]'));
  await wait(()=>document.querySelector('[data-dose]'));document.querySelector('[data-dose]').click();document.querySelector('#taken').click();await wait(()=>!ui.busy&&document.body.innerText.includes('已服用'));
  const p=PhoneLocal.store.value.daily;if(!Object.values(p.doses).some(x=>x.status==='taken')||!p.doseAudit.length)throw Error('Dose persistence failed');
  location.hash='#health';await wait(()=>document.querySelector('#upload'));document.querySelector('#upload').click();const uf=document.querySelector('#upload-form');uf.elements.name.value='TEST 文本资料';const textFile=new File(['TEST ONLY'],'test.txt',{type:'text/plain'}),dt=new DataTransfer();dt.items.add(textFile);document.querySelector('#file').files=dt.files;document.querySelector('#file').dispatchEvent(new Event('change'));uf.requestSubmit();await wait(()=>!document.querySelector('dialog[open]'));
  const s=await PhoneLocal.snapshot();if(!s.attachments.some(a=>a.name==='TEST 文本资料'))throw Error('Attachment failed');location.hash='#home';
  const canvas=new OffscreenCanvas(1000,220),ctx=canvas.getContext('2d');ctx.fillStyle='white';ctx.fillRect(0,0,1000,220);ctx.fillStyle='black';ctx.font='60px sans-serif';ctx.fillText('TEST 65.0 kg',50,140);const ocr=await PhoneOCR.recognize(await canvas.convertToBlob({type:'image/png'}));if(!ocr.text.includes('65.0'))throw Error('Actual OCR failed: '+JSON.stringify(ocr));
  const backup=await PhoneLocal.backup();PhoneStore.validateBackup(backup);
  window.__qa={status:'passed',phase,events:s.state.events.length,attachments:s.attachments.length,doses:Object.values(p.doses).length,ocr};
 }else{
  await wait(()=>state.catalog.length===53);
  const make=name=>new File([Uint8Array.from(atob(QaFixtures.video(name)),c=>c.charCodeAt(0))],name+'.mp4',{type:'video/mp4'});
  state.tab='assess';state.selected='shoulder_abduction';state.detail=true;assessment();chooseFile(make('shoulder'));document.querySelector('#consent').checked=true;upload();
  const sid=await wait(()=>state.job);const shoulder=await wait(()=>PhoneLocal.store.value.jobs.find(j=>j.id===sid&&['done','failed'].includes(j.state)));if(shoulder.state!=='done')throw Error(shoulder.message);
  await wait(()=>document.querySelector('#view-plan'));document.querySelector('#view-plan').click();await wait(()=>document.querySelector('#plan-form'));document.querySelector('#activity-ok').checked=true;document.querySelector('#support-ok').checked=true;document.querySelector('#plan-form').requestSubmit();await wait(()=>document.querySelector('#train-next'));document.querySelector('#train-next').click();chooseFile(make('shoulder'));document.querySelector('#consent').checked=true;upload();
  const tid=await wait(()=>state.job);const training=await wait(()=>PhoneLocal.store.value.jobs.find(j=>j.id===tid&&['done','failed'].includes(j.state)));if(training.state!=='done')throw Error(training.message);
  await wait(()=>document.querySelector('#feedback-form'));document.querySelector('#pain').value=0;document.querySelector('#fatigue').value=0;document.querySelector('#feedback-form').requestSubmit();await wait(()=>!state.job&&state.tab==='plan');
  const plan=await PhoneLocal.request('/api/plan');if(plan.progress.completed!==plan.progress.total)throw Error('Training incomplete, no fake completion: '+JSON.stringify(training.result.summary));
  state.tab='fitness';state.selected='fitness_squat';state.detail=true;fitnessPage();chooseFile(make('squat'));document.querySelector('#consent').checked=true;upload();const fid=await wait(()=>state.job);const squat=await wait(()=>PhoneLocal.store.value.jobs.find(j=>j.id===fid&&['done','failed'].includes(j.state)));if(squat.state!=='done')throw Error(squat.message);
  await showJob(squat.id);if(!document.body.innerText.includes('训练报告'))throw Error('Fitness report did not render');
  const b=await PhoneLocal.body();if(b.training_count<1||b.total<3)throw Error('Body/history missing');
  // Model availability tests are not real hand/posture accuracy tests.
  const model=new PhoneMotion.Model();await model.init(await PhoneMotion.spec('index_pip_flexion'));const canvas=new OffscreenCanvas(320,240);canvas.getContext('2d').fillRect(0,0,320,240);const image=canvas.transferToImageBitmap();await model.call('frame',{image,timestamp:0},[image]);model.close();
  const backup=await PhoneLocal.request('/api/product-backup');if(backup.version!==2||!backup.domain.attachments.length)throw Error('Backup failed');
  PhoneStore.validateBackup(backup);
  window.__qa={status:'passed',phase,shoulder:shoulder.result.summary,training:training.result.summary,squat:squat.result.summary,plan:plan.progress,total:b.total};
 }
}catch(e){PhoneMotion.pause();window.__qa={status:'failed',error:String(e.stack||e),text:document.body.innerText};}})();
