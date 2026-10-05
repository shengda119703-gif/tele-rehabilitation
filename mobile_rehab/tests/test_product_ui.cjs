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
  function parse(v){return [...v.matchAll(/<(?:button|input|select|div|form|section)\b([^>]*)>/g)].map(m=>node(m[1]));}
  function node(attrs=''){
    let content='';
    const e={dataset:{},textContent:'',value:'',hidden:false,disabled:false,
      get innerHTML(){return content;},set innerHTML(v){content=v;rendered.push(...parse(v));},
      insertAdjacentHTML(_,v){this.innerHTML=content+v;},
      classList:{toggle(){}},setAttribute(){},removeAttribute(){},click(){this.clicked=true;},append(){},after(){},scrollIntoView(){}};
    for(const a of attrs.matchAll(/([\w-]+)="([^"]*)"/g)){
      e[a[1]]=a[2];if(a[1].startsWith('data-'))e.dataset[a[1].slice(5).replace(/-([a-z])/g,(_,x)=>x.toUpperCase())]=a[2];
    }return e;
  }
  const root={get innerHTML(){return html;},set innerHTML(v){html=v;rendered=parse(v);},insertAdjacentHTML(_,v){this.innerHTML=html+v;}};
  const nav=['plan','assess','fitness','history','device'].map(x=>node(`data-tab="${x}"`));
  function query(s){
    if(s==='#app')return root;
    if(s.startsWith('#'))return rendered.find(e=>e.id===s.slice(1))||fixed.get(s)||null;
    if(!fixed.has(s))fixed.set(s,node());return fixed.get(s);
  }
  const all=s=>s==='[data-tab]'?nav:s.startsWith('[data-')?rendered.filter(e=>Object.hasOwn(e.dataset,s.slice(6,-1).replace(/-([a-z])/g,(_,x)=>x.toUpperCase()))):[];
  const c={document:{querySelector:query,querySelectorAll:all,createElement:()=>node(),addEventListener(){}},
    window:{addEventListener(){},scrollTo(){}},location:{hash:'',host:'localhost'},URL:{revokeObjectURL(){}},
    setTimeout,clearTimeout,console,confirm:()=>true};
  vm.createContext(c);
  for(const file of ['app.js','fitness.js','barbell.js','extensions.js'])vm.runInContext(fs.readFileSync(path.join(staticDir,file),'utf8'),c);
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
