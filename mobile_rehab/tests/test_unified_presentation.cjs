// Presentation regression: no browser, production data or hardware access.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const dir=path.resolve(__dirname,'../static');
function page(){
  const fixed=new Map();let nodes=[];
  const make=()=>({dataset:{},value:'',textContent:'',hidden:false,open:false,
    querySelector:()=>null,querySelectorAll:()=>[],setAttribute(){},removeAttribute(){},
    showModal(){this.open=true;},close(){this.open=false;},classList:{toggle(){}}});
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
    window:{addEventListener(){},scrollTo(){}},location:{hash:'#home'},setTimeout:()=>0,clearTimeout(){},console,URLSearchParams,AbortController};
  vm.createContext(c);
  vm.runInContext(fs.readFileSync(path.join(dir,'unified.js'),'utf8').replace(/\nroute\(\);\s*$/,''),c);
  c.fixture={profile:{profile:{name:'TEST <img>',age:68,conditions:[],medicationRecords:[]}},dailyProduct:{schedules:[]},state:{events:[],chat:[]},history:{report:{rangeText:'TEST 本周',sections:[{title:'TEST 摘要',lines:['TEST 原始记录']}]}}};
  const run=code=>vm.runInContext(code,c);run('ui.snapshot=fixture');
  return {run,c,get:query,get html(){return html;}};
}
test('home has one concise entry, keeps original routes and folds the unchanged weekly data',()=>{
  const p=page();p.run('home()');assert.match(p.html,/href="#assistant"/);assert.match(p.html,/href="#records"/);
  assert.match(p.html,/<details class="weekly-preview"><summary>本周摘要/);assert.match(p.html,/TEST 原始记录/);
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
