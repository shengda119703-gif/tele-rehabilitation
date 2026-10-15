// Presentation regression: no browser, production data or hardware access.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const dir=path.resolve(__dirname,'../static');
function page(){
  const fixed=new Map();let nodes=[];
  const make=()=>{const classes=new Set();return {dataset:{},value:'',textContent:'',hidden:false,open:false,
    querySelector:()=>null,querySelectorAll:()=>[],setAttribute(){},removeAttribute(){},
    showModal(){this.open=true;},close(){this.open=false;},replaceChildren(){this.innerHTML='';},
    classList:{toggle(){},add(x){classes.add(x);},remove(x){classes.delete(x);},contains(x){return classes.has(x);}}};};
  const content=make();let html='';
  Object.defineProperty(content,'innerHTML',{get:()=>html,set:v=>{
    html=v;nodes=[...v.matchAll(/<(?:button|input|select|textarea|form)\b([^>]*)>/g)].map(m=>{
      const n=make();for(const a of m[1].matchAll(/([\w-]+)="([^"]*)"/g)){
        n[a[1]]=a[2];if(a[1].startsWith('data-'))n.dataset[a[1].slice(5).replace(/-([a-z])/g,(_,x)=>x.toUpperCase())]=a[2];
      }return n;
    });
  }});
  fixed.set('#content',content);
  const query=s=>nodes.find(n=>s==='#'+n.id)||fixed.get(s)||(()=>{const n=make();fixed.set(s,n);return n;})();
  const c={document:{body:{dataset:{}},querySelector:query,querySelectorAll:s=>s.startsWith('[data-')?nodes.filter(n=>n.dataset[s.slice(6,-1).replace(/-([a-z])/g,(_,x)=>x.toUpperCase())]!==undefined):[],addEventListener(){}},
    window:{addEventListener(){},scrollTo(){}},location:{hash:'#home'},setTimeout:()=>0,clearTimeout(){},console,URLSearchParams,AbortController,crypto,structuredClone};
  vm.createContext(c);
  vm.runInContext(fs.readFileSync(path.join(dir,'home-v36.js'),'utf8'),c);
  vm.runInContext(fs.readFileSync(path.join(dir,'unified.js'),'utf8').replace(/\nroute\(\);\s*$/,''),c);
  c.fixture={profile:{profile:{name:'TEST <img>',age:68,conditions:[],medicationRecords:[]}},dailyProduct:{schedules:[]},state:{events:[],chat:[]},history:{report:{rangeText:'TEST 本周',sections:[{title:'TEST 摘要',lines:['TEST 原始记录']}]}}};
  const run=code=>vm.runInContext(code,c);run("ui.snapshot=fixture;ui.homeConnection='ready'");
  return {run,c,get:query,get html(){return html;}};
}

test('assessment-plan actions target My Plans without starting measurement',()=>{
 const p=page(),id='11111111-1111-4111-8111-111111111111';p.c.planId=id;
 const html=p.run("assistantActions([{kind:'assessment_plan',plan_id:planId}])");
 assert.match(html,/查看评估计划/);assert(html.includes('/capture?tab=plan&assessmentPlan='+id+'#assessment-plans'));
 assert.doesNotMatch(html,/tab=assess|guide=1/);assert.equal(p.run("assistantActions([{kind:'assessment_plan',plan_id:'../../other'}])"),'');
});

test('all current health metric keys have Chinese display labels without changing values',()=>{
  const p=page();
  for(const [key,label] of Object.entries({weight:'体重',steps:'步数',walkSpeed:'步行速度',sleepHours:'睡眠时长',nightWakes:'夜间醒来',restingHr:'静息心率',spo2:'血氧',systolic:'收缩压',diastolic:'舒张压',bloodGlucose:'血糖'})){
    p.c.event={measurement:{metric:key,value:12.3,unit:'unit'}};
    assert.equal(p.run('eventText(event)'),`${label} 12.3 unit`);
  }
});
test('home V3.6 has an independent task and preserves existing plan, history and assistant entries',()=>{
  const p=page();p.run('home()');assert.match(p.html,/href="#assistant"/);assert.match(p.html,/href="#records"/);
  assert.match(p.html,/class="home-task"/);assert.equal((p.html.match(/class="home-mark"/g)||[]).length,7);
  assert.equal(typeof p.get('#home-plan').onclick,'function');assert.equal(typeof p.get('#home-primary').onclick,'function');
  assert.match(p.html,/TEST &lt;img&gt;/);assert.doesNotMatch(p.html,/陪你一步一步|已连接电脑 · 本人资料同步保存/);
});
test('all rehab modes keep original destinations and source option values',()=>{
  const p=page();p.run('rehab()');assert.match(p.html,/value="LIVE_CAMERA"/);assert.match(p.html,/value="REPLAY_FILE"/);
  assert.equal(p.get('#source').value,'LIVE_CAMERA');
  p.run("ui.rehabMode='assessment';rehab()");assert.match(p.html,/href="\/capture\?tab=assess"/);
  p.run("ui.rehabMode='fitness';rehab()");assert.match(p.html,/href="\/capture\?tab=fitness"/);
});
test('existing plan keeps dose, next item, progress and unavailable reason',()=>{
  const p=page();p.c.fixture.rehabilitation_ui={'rehab.get_training_plan':{records:[{id:'TEST-plan',name:'TEST 计划',items:[{key:'a',exercise_label:'TEST 肩外展',side:'left',settings:{target_reps:3,target_sets:2}}],progress:{next_key:'a',completed:0,total:1},availability_reason:'TEST 条件未满足'}]}};
  p.run("ui.source='REPLAY_FILE';rehab()");assert.match(p.html,/3 次 × 2 组/);assert.match(p.html,/TEST 条件未满足/);
  assert.match(p.html,/aria-label="本轮完成进度"/);assert.match(p.html,/开始下一项/);assert.match(p.html,/href="\/capture\?tab=plan"/);
});
test('health and family controls remain bound and permission explanations stay accessible',()=>{
  const p=page();p.run('health()');assert.equal(typeof p.get('#upload').onclick,'function');assert.equal(typeof p.get('#edit-profile').onclick,'function');
  p.run('family()');assert.equal(typeof p.get('#bind').onclick,'function');assert.equal(typeof p.get('#invite').onclick,'function');
  assert.match(p.html,/默认不共享记录/);assert.match(p.html,/不能修改对方档案/);assert.match(p.html,/手机连接码允许操作本人档案/);
});
test('future medication remains disabled, and pending/private conversation labels remain visible',()=>{
  const p=page();p.c.fixture.profile.profile.medicationRecords=[{id:'TEST-med',name:'TEST 药物',status:'active',dose:'TEST 原剂量'}];
  p.c.fixture.dailyProduct.medSchedules={'TEST-med':{times:['08:00'],start:'2026-01-01'}};
  p.run("ui.day='2099-01-01';medication()");assert.match(p.html,/data-dose="0" disabled/);assert.match(p.html,/TEST 原剂量/);assert.match(p.html,/未记录不等于漏服/);
  p.c.fixture.state.chat=[{role:'elder',text:'TEST 对话',pending:true,persisted:false}];p.run('assistant()');
  assert.match(p.html,/本次不记录/);assert.match(p.html,/待确认/);assert.match(p.html,/id="private"/);assert.match(p.html,/maxlength="1900"/);
});
test('button decoration is CSS only with disabled, focus, reduced-motion and contrast modes',()=>{
  const css=fs.readFileSync(path.join(dir,'controls.css'),'utf8');
  for(const token of ['min-height:52px','pointer-events:none',':disabled',':focus-visible','prefers-reduced-motion','forced-colors','--icon-camera','--icon-upload'])assert.ok(css.includes(token),token);
  for(const file of ['unified.html','index.html'])assert.match(fs.readFileSync(path.join(dir,file),'utf8'),/controls\.css\?v=20261007/);
});
test('light and dark button, body and secondary-text tokens maintain readable contrast',()=>{
  const css=fs.readFileSync(path.join(dir,'unified-polish.css'),'utf8');
  const luminance=hex=>{
    if(hex.length===4)hex='#'+[...hex.slice(1)].map(c=>c+c).join('');
    const rgb=[1,3,5].map(i=>parseInt(hex.slice(i,i+2),16)/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);
    return rgb[0]*.2126+rgb[1]*.7152+rgb[2]*.0722;
  };
  const contrast=(a,b)=>{const x=luminance(a),y=luminance(b);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05);};
  const themes=[...css.matchAll(/:root\s*\{([^}]+)\}/g)];assert.equal(themes.length,2);
  for(const theme of themes){
    const tokens=Object.fromEntries([...theme[1].matchAll(/--([\w-]+):\s*(#[\da-f]+)/gi)].map(m=>[m[1],m[2]]));
    for(const [foreground,background] of [['ink','paper'],['muted','paper'],['on-accent','accent']])assert.ok(contrast(tokens[foreground],tokens[background])>=4.5,foreground+' / '+background);
  }
});

test('reconnect refreshes home without starting a newly recovered task',async()=>{
  const p=page();p.run("ui.homeConnection='offline';home();load=async()=>{ui.homeConnection='ready';ui.snapshot=fixture;render()}");
  await p.get('#home-primary').onclick();assert.equal(p.c.location.href,undefined);assert.equal(p.c.location.hash,'#home');
});
test('task click is cancelled if source, selected date, participant or generation changes during revalidation',async()=>{
  for(const changed of ["ui.source='REPLAY_FILE'","ui.day='2099-01-01'","fixture.profile.ownerId='OTHER'","ui.generation++","ui.page='health'"]){
    const p=page();p.run("home();load=async()=>{ui.generation++;"+changed+";ui.homeConnection='ready'}");
    await p.get('#home-primary').onclick();assert.equal(p.c.location.href,undefined);assert.equal(p.c.location.hash,'#home',changed);
  }
});
test('timeline keeps selected medication date and pairing resets home handoff state',()=>{
  const p=page();p.c.fixture.profile.profile.medicationRecords=[{id:'TEST-med',name:'TEST 药物',status:'active'}];
  p.c.fixture.dailyProduct.medSchedules={'TEST-med':{times:['08:00'],start:'2020-01-01'}};
  p.run("ui.day='2026-10-10';home()");p.c.document.querySelectorAll('[data-home-target]')[0].onclick();p.run('route()');
  assert.equal(p.run('ui.day'),'2026-10-10');assert.equal(p.run('ui.page'),'medication');assert.equal(p.run('ui.homeRouteDay'),null);
  p.run("ui.homeRouteDay='2026-10-09';pair()");assert.equal(p.run('ui.snapshot'),null);assert.equal(p.run('ui.homeRouteDay'),null);assert.equal(p.c.document.body.dataset.page,'pair');
});

test('latest main routes coexist with approved subpages and capability report links',()=>{
  for(const [hash,pageName] of [['#history','records'],['#settings','settings'],['#notifications','notifications']]) {
    const p=page();p.c.location.hash=hash;p.run('route()');assert.equal(p.run('ui.page'),pageName);
  }
  for(const [hash,adapter,pageName] of [['#health/detail/steps','HealthV131','health'],['#medication/history','MedicationV121','medication'],['#family/members','FamilyV10','family']]) {
    const p=page();p.c.window[adapter]={reportCode:()=>null};p.c.location.hash=hash;
    p.run(`${pageName}=()=>{};load=()=>{};route()`);assert.equal(p.run('ui.page'),pageName);
  }
  const p=page();let guest=false;p.c.window.FamilyV10={reportCode:()=> 'TEST-CAPABILITY',routeGuest(){guest=true;}};
  p.c.location.hash='#care=TEST-CAPABILITY';p.run('route()');assert.equal(guest,true);assert.equal(p.run('ui.page'),'home');
});
test('fitness alias reaches the real capture flow instead of being swallowed by the rehab home adapter',()=>{
  const p=page();p.c.location.hash='#fitness';p.c.window.RehabV51={context:(source,day)=>`rehabSource=${source}&rehabDay=${day}`};
  p.run("ui.source='REPLAY_FILE';ui.day='2026-10-14';route()");
  assert.equal(p.c.location.href,'/capture?tab=fitness&rehabSource=REPLAY_FILE&rehabDay=2026-10-14');
});
test('profile menu retains clinician, settings and notifications without adding a sixth bottom column',()=>{
  const p=page();let calls=0;p.c.window.PhoneAccount={open(){calls++;}};p.run('editProfile()');
  const html=p.get('#dialog').innerHTML;
  assert.match(html,/id="profile-clinician"/);assert.match(html,/href="#settings"/);assert.match(html,/href="#notifications"/);
  p.get('#profile-clinician').onclick();assert.equal(calls,1);assert.equal(p.get('#dialog').open,false);
  p.run('settings()');assert.equal(typeof p.get('#settings-clinician').onclick,'function');
  assert.match(p.html,/查看通知记录/);assert.equal(p.run('Object.keys(names).length'),5);
});
test('assistant uses main reply provenance and local candidate gate, without promising chat health writes',()=>{
  const p=page();assert.equal(p.run("conversationSource({provider:'deepseek',status:'replied'})"),'DeepSeek 回复');
  assert.match(p.run("conversationSource({provider:'local',status:'unavailable',reason:'not_configured'})"),/本地回复/);
  p.run('assistant()');assert.match(p.html,/id="local-plan"/);assert.doesNotMatch(p.html,/记录身体感受/);
});

test('normal dialogs clear the latest clinician chat layout class',()=>{
  const p=page(),d=p.get('#dialog');d.classList.add('paired-contact');p.run('editProfile()');
  assert.equal(d.classList.contains('paired-contact'),false);assert.match(d.innerHTML,/id="profile-form"/);
});

function cloudAssistantPage(){
 const p=page(),calls=[],turns=[],actor={patient_id:'TEST-patient',account_id:'TEST-account'};
 p.c.fixture.ownerId='TEST-owner';
 p.c.window.PhoneLocal={store:{value:{cloudConsent:false}}};
 let preferences={version:0,health_context:false};
 p.c.window.PhoneAccount={identity:()=>actor,aiScope:()=>actor,
  assistantPreferences:async(store,body)=>{calls.push({action:'preferences',body});if(body)preferences={version:preferences.version+1,health_context:body.health_context};return preferences;},
  assistantConversation:async(store,after)=>{calls.push({action:'conversation',after});return {items:turns.filter(t=>t.sequence>after),has_more:false,next_after:turns.length};},
  assistantTurn:async(store,text)=>{calls.push({action:'turn',text});const turn={id:crypto.randomUUID(),sequence:turns.length+1,text,answer:'TEST server answer',source:'local',created_at:1,actions:[{kind:'assessment',exercise_id:'knee_extension'},{kind:'plan'},{kind:'candidate',candidate_kind:'STARTER'},{kind:'doctor_review'}]};turns.push(turn);return {turn,source:'local'};},
  request:async(action,identity,body)=>{calls.push({action,body});if(action==='workflow')return {profile_version:4,profile:{goal:'TEST old goal'}};return {state:'PENDING_REVIEW'};}
 };
 p.c.localCalls=[];p.run("ui.page='assistant';load=async()=>{};api=async(operation,body)=>{localCalls.push({operation,body});return {turn:{conversation:{provider:'local',status:'replied'}}}};assistant()");
 return Object.assign(p,{calls,turns,actor});
}
const settle=()=>new Promise(resolve=>setImmediate(resolve));

test('logged assistant bypasses local record short-circuits and displays server turns once',async()=>{
 const p=cloudAssistantPage();await settle();p.run("ui.draft='查看我已有的膝部记录'");await p.get('#chat-form').onsubmit({preventDefault(){}});
 assert.equal(p.calls.find(c=>c.action==='turn').text,'查看我已有的膝部记录');assert.equal(p.c.localCalls.length,0);
 p.run('assistant()');await settle();p.run('assistant()');
 assert.equal((p.html.match(/TEST server answer/g)||[]).length,1);assert.match(p.html,/云端管家已连接/);assert.doesNotMatch(p.html,/DeepSeek 已配置/);
 assert.match(p.html,/exercise=knee_extension/);assert.match(p.html,/data-assistant-candidate="STARTER"/);
});

for(const mode of ['checkbox','no_record','privacy'])test(`${mode} turn never calls cloud assistant`,async()=>{
 const p=cloudAssistantPage();await settle();p.c.input=mode==='checkbox'?'TEST private':mode==='no_record'?'不要记录我的训练结果':'不要告诉家人我的训练情况';
 p.run("ui.draft=input;ui.private="+(mode==='checkbox'?'true':'false'));await p.get('#chat-form').onsubmit({preventDefault(){}});
 assert.equal(p.calls.filter(c=>c.action==='turn').length,0);assert.equal(p.c.localCalls.length,1);
});

test('health-context opt-in is unchecked by default and never enables upload',async()=>{
 const p=cloudAssistantPage();await settle();assert.doesNotMatch(p.html,/id="assistant-health-context"[^>]*checked/);
 await p.get('#assistant-health-context').onchange({target:{checked:true}});
 const write=p.calls.find(c=>c.action==='preferences'&&c.body);assert.deepEqual(JSON.parse(JSON.stringify(write.body)),{expected_version:0,health_context:true});
 assert.equal(p.c.window.PhoneLocal.store.value.cloudConsent,false);
});

test('candidate action waits for confirmation and workflow form saves explicit versioned conditions',async()=>{
 const p=cloudAssistantPage();await settle();p.run("ui.draft='TEST candidate'");await p.get('#chat-form').onsubmit({preventDefault(){}});p.run('assistant()');await settle();
 const controls=p.c.document.querySelectorAll('[data-assistant-candidate]');controls[0].onclick();assert(!p.calls.some(c=>c.action==='candidate'));
 await p.get('#assistant-candidate-confirm').onclick();assert.equal(p.calls.filter(c=>c.action==='candidate').length,1);assert.match(p.get('#message').textContent,/等待医生核对/);
 await p.get('#assistant-workflow').onclick();
 for(const [id,value] of [['assistant-goal','TEST new goal'],['assistant-region','膝'],['assistant-equipment','稳固椅，垫'],['assistant-restrictions',''],['assistant-level','1']])p.get('#'+id).value=value;
 p.get('#assistant-screening').checked=true;await p.get('#assistant-workflow-form').onsubmit({preventDefault(){}});
 const save=p.calls.find(c=>c.action==='workflowProfile').body;assert.equal(save.expected_version,4);assert.equal(save.goal,'TEST new goal');assert.equal(save.screening_confirmed,true);assert.equal(p.c.window.PhoneLocal.store.value.cloudConsent,false);
});

test('capture deep link validates selected exercise against actual available catalog without starting a task',()=>{
 const source=fs.readFileSync(path.join(dir,'app.js'),'utf8'),helper=source.slice(source.indexOf('function applyAssistantAssessment(){'),source.indexOf('const automaticUploadReconciliation='));
 for(const id of ['shoulder_abduction','knee_extension','ankle_dorsiflexion','UNKNOWN']){
  const c={state:{catalog:['shoulder_abduction','knee_extension','ankle_dorsiflexion'].map(id=>({id,joint:'TEST',available:true})),selected:'OLD'},location:{search:'?tab=assess&entry=assistant&exercise='+id},URLSearchParams};
  vm.runInNewContext(helper+';applyAssistantAssessment()',c);
  assert.equal(c.state.selected,id==='UNKNOWN'?'OLD':id);assert.equal(c.state.preparing,id==='UNKNOWN'?undefined:false);assert.equal(c.state.training,id==='UNKNOWN'?undefined:null);
 }
});

test('anonymous assistant stays local and settings expose no personal key configuration',async()=>{
 const p=page();p.c.localCalls=[];p.c.window.OfflineAndroid={deepSeekSettings(){throw Error('Legacy key UI must stay unreachable');}};
 p.run("load=async()=>{};api=async(path,body)=>{localCalls.push(body);return {turn:{}}};ui.page='assistant';ui.draft='TEST anonymous';assistant()");
 await p.get('#chat-form').onsubmit({preventDefault(){}});assert.equal(p.c.localCalls.length,1);
 p.run('settings()');assert.doesNotMatch(p.html,/配置 DeepSeek|settings-deepseek/);assert.match(p.html,/登录本人云账号/);
});

test('sync revisits an unfinished earlier turn and updates it without duplicating completed answers',async()=>{
 const p=cloudAssistantPage();await settle();
 p.turns.push({id:'TEST unfinished',sequence:1,text:'TEST pending',answer:null,actions:[],created_at:1},{id:'TEST second',sequence:2,text:'TEST next',answer:'TEST next answer',actions:[],created_at:2});
 await p.get('#assistant-sync').onclick();await settle();assert.equal(p.run('ui.assistantCloud.pending_after'),0);
 p.turns[0].answer='TEST completed first';await p.get('#assistant-sync').onclick();await settle();
 assert.match(p.html,/TEST completed first/);assert.equal((p.html.match(/TEST next answer/g)||[]).length,1);
});
