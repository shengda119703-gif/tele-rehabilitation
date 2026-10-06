// Template/interaction contract tests, not a substitute for browser visual QA.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const staticDir=path.resolve(__dirname,'../static');
function harness(){
  let html='',rendered=[];
  const fixed=new Map();
  function parse(v){return [...v.matchAll(/<(?:button|input|select|textarea|h1|h2|h3|div|form|section|p|a)\b([^>]*)>/g)].map(m=>node(m[1]));}
  function node(attrs=''){
    let content='';
    const e={dataset:{},textContent:'',value:'',hidden:false,disabled:false,
      get innerHTML(){return content;},set innerHTML(v){content=v;rendered.push(...parse(v));},
      insertAdjacentHTML(_,v){this.innerHTML=content+v;},
      classList:{toggle(){}},setAttribute(){},removeAttribute(){},click(){this.clicked=true;},append(){},after(){},scrollIntoView(){},querySelector(){return {disabled:false};}};
    for(const a of attrs.matchAll(/([\w-]+)="([^"]*)"/g)){
      e[a[1]]=a[2];if(a[1].startsWith('data-'))e.dataset[a[1].slice(5).replace(/-([a-z])/g,(_,x)=>x.toUpperCase())]=a[2];
    }return e;
  }
  const root={get innerHTML(){return html;},set innerHTML(v){html=v;rendered=parse(v);},insertAdjacentHTML(_,v){this.innerHTML=html+v;},append(e){html+=e.innerHTML;rendered.push(...parse(e.innerHTML));}};
  const nav=['plan','assess','fitness','history','more'].map(x=>node(`data-tab="${x}"`));
  function query(s){
    if(s==='#app')return root;
    if(s.startsWith('#'))return rendered.find(e=>e.id===s.slice(1))||fixed.get(s)||null;
    if(!fixed.has(s))fixed.set(s,node());return fixed.get(s);
  }
  const all=s=>s==='[data-tab]'?nav:s.startsWith('[data-')?rendered.filter(e=>Object.hasOwn(e.dataset,s.slice(6,-1).replace(/-([a-z])/g,(_,x)=>x.toUpperCase()))):[];
  const c={document:{querySelector:query,querySelectorAll:all,createElement:()=>node(),addEventListener(){}},
    window:{addEventListener(){},scrollTo(){}},location:{hash:'',host:'localhost'},URL:{revokeObjectURL(){}},
    setTimeout,clearTimeout,console,AbortController,TypeError,URLSearchParams,confirm:()=>true};
  vm.createContext(c);
  for(const file of ['app.js','fitness.js','barbell.js','extensions.js','health.js'])vm.runInContext(fs.readFileSync(path.join(staticDir,file),'utf8'),c);
  const instructions={view_label:'正面拍摄',camera:'保持肩肘入镜',start:'双臂自然下垂',move:'缓慢抬起手臂',return:'放下手臂',boundary:'测试说明',count:'回位计一次'};
  const exercises=[{id:'shoulder_abduction',label:'肩外展',joint:'shoulder',joint_label:'肩部',view:'frontal',instructions},
    {id:'elbow_flexion',label:'肘屈曲',joint:'elbow',joint_label:'肘部',view:'sagittal',instructions},
    {id:'neck_flexion',label:'颈前屈',joint:'neck',joint_label:'颈部',view:'sagittal',instructions}];
  const fitness=[{id:'fitness_squat',label:'深蹲',group:'腿部',steps:['站稳','下蹲','起身'],camera:'侧面',note:'测试',metric_label:'膝角'},
    {id:'fitness_bench',label:'卧推',group:'上肢',steps:['准备','下放','推起'],camera:'侧面',note:'测试',metric_label:'肘角'}];
  c.fixture=exercises;c.fitFixture=fitness;
  vm.runInContext('state.catalog=fixture;state.fitnessCatalog=fitFixture;',c);
  const run=code=>vm.runInContext(code,c);
  return {c,run,get html(){return root.innerHTML;},get:query,all};
}
test('landing is training and mobile nav is short text, not decorative symbols',()=>{
  const h=harness();assert.equal(h.run('state.tab'),'plan');
  const html=fs.readFileSync(path.join(staticDir,'index.html'),'utf8');
  assert.match(html,/data-tab="plan" class="active">训练/);assert.doesNotMatch(html,/◎|▤|↗|◷|▣/);
});
test('assessment list, category, search, detail and return are distinct interactive states',()=>{
  const h=harness();h.run("state.tab='assess';assessment()");
  assert.match(h.html,/康复评估/);assert.doesNotMatch(h.html,/id="camera-btn"/);
  h.all('[data-category]').find(b=>b.dataset.category==='elbow').onclick();
  assert.match(h.html,/data-action="elbow_flexion"/);assert.doesNotMatch(h.html,/data-action="shoulder_abduction"/);
  h.all('[data-category]').find(b=>b.dataset.category==='all').onclick();
  h.get('#action-search').oninput({target:{value:'颈'}});
  assert.match(h.get('#action-list').innerHTML,/颈前屈/);assert.doesNotMatch(h.get('#action-list').innerHTML,/肩外展/);
  // State transition independent of fake DOM nesting replacement.
  h.run("state.selected='neck_flexion';state.detail=true;assessment()");
  assert.match(h.html,/id="camera-btn"/);assert.match(h.html,/怎么做/);assert.match(h.html,/实时跟练|id="guide"/);
  h.get('#camera-btn').onclick();assert.equal(h.get('#camera-file').clicked,true);
  h.get('#action-back').onclick();assert.equal(h.run('state.detail'),false);assert.match(h.html,/id="action-search"/);
});
test('camera filter and no-results state apply without changing selected action',()=>{
  const h=harness();h.run("state.tab='assess';state.viewFilter='sagittal';assessment()");
  assert.doesNotMatch(h.html,/data-action="shoulder_abduction"/);assert.match(h.html,/data-action="elbow_flexion"/);
  h.get('#action-search').oninput({target:{value:'不存在'}});assert.match(h.get('#action-list').innerHTML,/没有找到/);
  assert.equal(h.run('state.selected'),'shoulder_abduction');
});
test('fitness opens detail from row, keeps observation side, and goes back to library',()=>{
  const h=harness();h.run("state.tab='fitness';state.side='right';fitnessPage()");
  h.all('[data-action]').find(b=>b.dataset.action==='fitness_squat').onclick();
  assert.equal(h.run('state.detail'),true);assert.equal(h.run('state.side'),'right');assert.match(h.html,/分析一组动作/);
  h.get('#fit-gallery').onclick();assert.equal(h.get('#fit-gallery-input').clicked,true);
  h.get('#fitness-library-back').onclick();assert.match(h.html,/健身动作库/);assert.doesNotMatch(h.html,/id="fit-camera"/);
});
test('training detail keeps instructions, dose, fixed side and training navigation',()=>{
  const h=harness();h.run("state.tab='assess';state.selected='shoulder_abduction';state.training={id:'plan',entry:{exercise_id:'shoulder_abduction',side:'left',settings:{target_reps:3,target_sets:1,target_angle_deg:40}}};assessment()");
  assert.match(h.html,/双臂自然下垂/);assert.match(h.get('#training-dose').innerHTML,/本次目标/);
  assert.match(h.get('#training-dose').innerHTML,/40°/);assert.equal(h.run("state.training.id"),'plan');
  h.run('syncNavigation()');assert.equal(h.run('state.training.entry.side'),'left');
});
test('switching tabs resets detail and search, upload still prevents navigation',()=>{
  const h=harness();h.run("state.tab='assess';state.detail=true;state.search='肩';navigate('fitness')");
  assert.equal(h.run('state.detail'),false);assert.equal(h.run('state.search'),'');
  h.run("toast=()=>{};state.upload={};navigate('assess')");assert.equal(h.run('state.tab'),'fitness');
});
test('week strip uses actual local date across month/year edges',()=>{
  const h=harness();const html=h.run('weekStrip(new Date(2026,0,1))');
  assert.match(html,/2025-12-29/);assert.match(html,/2026-01-04/);assert.equal((html.match(/aria-current="date"/g)||[]).length,1);
  assert.match(html,/aria-current="date"><strong>今<\/strong><time datetime="2026-01-01">1/);
});
test('plan next action still carries plan id and dose into the training upload path',async()=>{
  const h=harness();h.c.data={proposal:{candidates:[],excluded:[]},plan:{id:'p1',items:[{key:'next',exercise_id:'shoulder_abduction',side:'right',settings:{target_reps:3,target_sets:1,target_angle_deg:40}}]},progress:{completed:0,total:1,items:[{done:false}],next_key:'next',blocked:null}};
  h.run("api=async()=>data;state.tab='plan';plan()");await new Promise(resolve=>setImmediate(resolve));
  assert.match(h.get('#plan-content').innerHTML,/开始训练/);h.get('#train-next').onclick();
  assert.equal(h.run('state.training.id'),'p1');assert.equal(h.run('state.side'),'right');assert.equal(h.run('state.detail'),true);
  assert.equal(h.run('state.training.entry.settings.target_reps'),3);assert.match(h.html,/记录本次训练/);
});
test('plan candidate explanations are folded and real consent fields remain',async()=>{
  const h=harness();h.c.data={proposal:{candidates:[{label:'肩外展',settings:{target_reps:3,target_sets:1,rest_between_sets_s:20},rationale:'原评估依据',instruction:'缓慢抬臂',source:{title:'指南',section:'活动'}}],excluded:[]},plan:null,progress:{}};
  h.run("api=async()=>data;state.tab='plan';plan()");await new Promise(resolve=>setImmediate(resolve));
  const html=h.get('#plan-content').innerHTML;assert.match(html,/<details><summary>动作安排与依据/);assert.doesNotMatch(html,/<details open/);
  assert.match(html,/id="activity-ok"/);assert.match(html,/id="support-ok"/);assert.match(html,/使用这份计划/);
});
test('network mounting no longer removes phone card',()=>{
  const script=fs.readFileSync(path.join(staticDir,'extensions.js'),'utf8');assert.doesNotMatch(script,/layout > \.card/);
});

function healthFixture(){return {needs_profile:false,metrics:[['weight','体重','kg']],categories:['其他资料'],snapshot:{profile:{profile:{name:'TEST <img>',age:65,conditions:[],medicationRecords:[{id:'m1',name:'TEST medicine',dose:'医嘱剂量',times:'早餐后',status:'active'}]}},state:{healthData:{measurements:[{metric:'weight',value:60,unit:'kg',timestamp:'2026-10-05T01:00:00Z'}]},chat:[{role:'elder',text:'<script>TEST</script>',persisted:false}],tasks:[{id:'t1',title:'核对用药',description:'TEST',kind:'medication_check',status:'pending'}]},attachments:[],history:{report:{sections:[],rangeText:'TEST'}}}};}

test('temporary result sharing lock retries automatically and ignores a page that was left',async()=>{
  const h=harness();let scheduled,calls=0;
  h.c.setTimeout=fn=>{scheduled=fn;return 1;};h.c.clearTimeout=()=>{};
  h.c.fetch=async()=>{calls++;return {ok:calls>1,status:calls>1?200:503,json:async()=>calls>1?{id:'job',state:'done'}:{detail:'结果正在保存'}};};
  h.run("renderJob=j=>{app.innerHTML='<h2>分析完成</h2>'}");
  await h.run("showJob('job')");assert.match(h.html,/正在保存结果/);assert.doesNotMatch(h.html,/没有连上电脑/);
  scheduled();await new Promise(resolve=>setImmediate(resolve));assert.match(h.html,/分析完成/);assert.equal(calls,2);
  calls=0;await h.run("showJob('job')");h.run("state.job=null");scheduled();await new Promise(resolve=>setImmediate(resolve));assert.equal(calls,1);
});
test('my hub exposes health, medication, assistant, archive and family without removing devices',async()=>{
  const h=harness();h.c.healthFixture=healthFixture();h.run("api=async()=>healthFixture;state.tab='more';healthPage()");await new Promise(resolve=>setImmediate(resolve));
  for(const title of ['健康指标','我的用药','健康管家','健康资料','家庭照护','设备连接'])assert.match(h.html,new RegExp(title));
  assert.match(h.html,/TEST &lt;img&gt;/);assert.doesNotMatch(h.html,/<img>/);
  assert.match(fs.readFileSync(path.join(staticDir,'index.html'),'utf8'),/data-tab="more">我的/);
});
test('health loading result never overwrites another tab',async()=>{
  const h=harness();let finish;h.c.deferred=new Promise(resolve=>{finish=resolve;});h.run("api=()=>deferred;state.tab='health';healthPage();navigate('assess')");
  finish(healthFixture());await new Promise(resolve=>setImmediate(resolve));assert.match(h.html,/康复评估/);assert.doesNotMatch(h.html,/id="metric-form"/);
});
test('medication editing binds actual record and task, saves through domain endpoint',async()=>{
  const h=harness();h.c.healthFixture=healthFixture();h.c.calls=[];h.run("api=async(path,opts)=>{calls.push([path,opts]);return healthFixture};state.tab='medication';healthPage()");await new Promise(resolve=>setImmediate(resolve));
  h.all('[data-med-edit]')[0].onclick();assert.equal(h.get('#med-id').value,'m1');assert.equal(h.get('#med-name').value,'TEST medicine');
  h.all('[data-health-task]')[0].onclick();await new Promise(resolve=>setImmediate(resolve));
  assert.equal(h.c.calls[1][0],'/product/task.status');assert.equal(JSON.parse(h.c.calls[1][1].body).id,'t1');
});
test('chat escapes text, exposes local/private state and reset clears draft',async()=>{
  const h=harness();h.c.healthFixture=healthFixture();h.run("api=async()=>healthFixture;state.tab='assistant';healthDraft='私密草稿';healthPage()");await new Promise(resolve=>setImmediate(resolve));
  assert.match(h.html,/&lt;script&gt;TEST&lt;\/script&gt;/);assert.doesNotMatch(h.html,/<script>/);assert.match(h.html,/本次不记录/);assert.match(h.html,/本地规则助手/);
  h.run('resetHealth()');assert.equal(h.run('healthDraft'),'');assert.equal(h.run('healthData'),null);
});
test('shared summary and contacts escape content, never permit javascript telephone targets',()=>{
  const h=harness();h.c.summary={measurements:[],medications:[{name:'<script>',dose:'TEST',times:'TEST'}]};
  const html=h.run('sharedHealthMarkup(summary)');assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>/);
  assert.equal(h.run("dialLink('javascript:alert(1)','TEST')"),'');assert.match(h.run("dialLink('13800138000','家人')"),/href="tel:13800138000"/);
});
test('single point or empty trend does not invent baseline, static scripts have no persistent private draft',()=>{
  const h=harness();assert.match(h.run('metricTrendMarkup([])'),/暂无记录/);h.c.point=[{metric:'weight',value:60,unit:'kg',timestamp:'2026-10-05T01:00:00Z'}];
  assert.doesNotMatch(h.run('metricTrendMarkup(point)'),/<svg/);
  const script=fs.readFileSync(path.join(staticDir,'health.js'),'utf8');assert.doesNotMatch(script,/localStorage\.(setItem|getItem)|speechSynthesis|navigator.mediaDevices/);
});

test('private draft setting survives rerender but is cleared by identity reset',async()=>{
  const h=harness();h.c.healthFixture=healthFixture();h.run("api=async()=>healthFixture;state.tab='assistant';healthDraft='TEST private';healthPrivate=true;healthPage()");await new Promise(resolve=>setImmediate(resolve));
  assert.equal(h.get('#chat-private').checked,true);h.run('healthPage()');await new Promise(resolve=>setImmediate(resolve));assert.equal(h.get('#chat-private').checked,true);
  h.run('resetHealth()');assert.equal(h.run('healthPrivate'),false);assert.equal(h.run('healthDraft'),'');
});
test('API timeout releases fetch and returns actionable text',async()=>{
  const h=harness();h.c.fetch=(_,opts)=>new Promise((resolve,reject)=>opts.signal.addEventListener('abort',()=>reject(Object.assign(new Error('abort'),{name:'AbortError'}))));
  await assert.rejects(h.run("api('/product',{timeoutMs:5})"),/连接超时/);
});
test('API keeps device header and maps network failure',async()=>{
  const h=harness();h.c.fetch=async(_,opts)=>{assert.equal(opts.headers['X-Rehab-Client'],'mobile-v1');return {ok:true,json:async()=>({TEST:true})};};
  assert.equal((await h.run("api('/product')")).TEST,true);
  h.c.fetch=async()=>{throw new TypeError('Network down');};await assert.rejects(h.run("api('/product')"),/无法连接电脑/);
});
test('restore entry exists only for an empty health profile and states recovery scope',async()=>{
  const h=harness();h.c.healthFixture={needs_profile:true};h.run("api=async()=>healthFixture;state.tab='more';healthPage()");await new Promise(resolve=>setImmediate(resolve));
  assert.match(h.html,/id="restore-form"/);assert.match(h.html,/不包含评估训练录像/);assert.match(h.html,/不恢复家庭授权/);
});
test('archive offers reversible trash and local OCR without automatic medical interpretation',async()=>{
  const h=harness();h.c.healthFixture=healthFixture();h.run("api=async(path)=>path==='/product-trash'?[]:path==='/product-ocr'?{available:false}:healthFixture;state.tab='archive';healthPage()");await new Promise(resolve=>setImmediate(resolve));
  assert.match(h.html,/回收站/);assert.match(h.html,/移入回收站后可恢复/);assert.match(h.html,/不自动填写指标/);
});
