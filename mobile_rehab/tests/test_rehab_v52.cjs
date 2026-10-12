const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const V=require('../static/rehab-v52-core.js');
test('an untouched score is unknown; saved zero and ten survive without coercing invalid values',()=>{
  for(const x of ['', ' ',null,undefined,false,[],{},NaN,Infinity,-1,11,5.5])assert.equal(V.score(x),null);
  for(let i=0;i<=10;i++){assert.equal(V.score(i),i);assert.equal(V.score(String(i)),i);}
});
test('context whitelist and prefill never forward report values, identity or attachments',()=>{
  const c=V.context('training','shoulder_abduction','肩外展','视频角度变化',{patient:'PRIVATE',job:'SECRET',angle:141});
  assert.deepEqual(Object.keys(c),['page','exerciseId','exerciseName','metric']);
  assert.doesNotMatch(V.question({...c,patient:'PRIVATE',angle:141,report:'SECRET'}),/PRIVATE|141|SECRET/);
  assert.match(V.question(c),/视频角度变化.*临床关节活动度/);
  assert.match(V.question(V.context('action','shoulder_abduction','肩外展')),/肩外展动作需要注意什么/);
  assert.match(V.question(V.context('assessment','shoulder_flexion','肩前屈')),/肩前屈活动度评估/);
});
function lifecycle(){
  const nodes=new Map(),focus={focus(opts){this.restored=opts.preventScroll;}};
  const node=k=>{if(!nodes.has(k))nodes.set(k,{hidden:true,classList:{add(){}},append(b){this.button=b;}});return nodes.get(k);};
  const originals=[{id:'private-original-page'}],app={childNodes:originals,innerHTML:'original',replaceChildren(...xs){this.childNodes=xs;this.innerHTML='restored';}};
  const c={location:{href:'http://localhost/capture'},window:{scrollX:0,scrollY:123,scrollTo(x,y){this.restored=[x,y];},addEventListener(name,fn){this[name]=fn;},history:{state:null,pushState(s){this.state=s;},back(){this.state=null;}}},document:{activeElement:focus,body:{dataset:{rehabView:'result'}},createElement:()=>({setAttribute(){}})},$:node,app,state:{shared:true,tab:'history',job:'original-job',captureSource:'REPLAY_FILE',training:{id:'original-plan'}},healthPage(){},healthGeneration:0,healthDraft:'existing AI draft',healthPrivate:true,healthData:{saved:true},assistantPage(){},actionDetailV51(){},selected:()=>({id:'shoulder_abduction',label:'肩外展'}),renderJob(){},label:()=> '肩外展',esc:v=>v,pairPage(){app.innerHTML='pairing';},navigate(){}};
  let resolve,reject;c.calls=[];c.api=(url,opts)=>{c.calls.push({url,opts});return new Promise((a,b)=>{resolve=a;reject=b;});};
  vm.createContext(c);vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/rehab-v52-core.js'),'utf8'),c);const nativeHistory=c.window.history;c.window.history=function historyPage(){};vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/rehab-v52.js'),'utf8'),c);
  c.actionDetailV51();node('.rv-intro h2').button.onclick();
  return {c,node,originals,focus,nativeHistory,resolve:v=>resolve(v),reject:e=>reject(e),flush:()=>new Promise(r=>setImmediate(r))};
}
test('opening AI is read-only and returning restores original state, DOM, position and prior AI draft',async()=>{
  const h=lifecycle();assert.deepEqual(h.c.calls,[{url:'/product',opts:undefined}]);assert.equal(h.c.state.tab,'assistant');assert.equal(h.c.state.job,null);
  h.node('#rv-ai-back').onclick();assert.equal(h.c.state.tab,'history');assert.equal(h.c.state.job,'original-job');assert.equal(h.c.state.training.id,'original-plan');assert.equal(h.c.state.captureSource,'REPLAY_FILE');assert.equal(h.c.healthDraft,'existing AI draft');assert.equal(h.c.healthPrivate,true);
  assert.equal(h.c.app.childNodes[0],h.originals[0]);assert.deepEqual(h.c.window.restored,[0,123]);assert.equal(h.focus.restored,true);
  h.resolve({});await h.flush();assert.equal(h.c.app.innerHTML,'restored');
});
test('AI load failure keeps an honest error and a working return without sending a question',async()=>{
  const h=lifecycle();h.reject(Error('offline'));await h.flush();assert.match(h.c.app.innerHTML,/会话暂不可用.*offline/);
  h.node('#rv-ai-back').onclick();assert.equal(h.c.app.innerHTML,'restored');assert.equal(h.c.calls.length,1);
});
test('revoked authorization discards the cached page even if the existing API changes generation',async()=>{
  const h=lifecycle();h.c.healthGeneration++;h.c.pairPage();h.reject(Object.assign(Error('revoked'),{status:401}));await h.flush();h.node('#rv-ai-back').onclick();assert.equal(h.c.app.innerHTML,'pairing');
});
test('ranges preserve an empty required field until intentional interaction and recover zero',()=>{
  const fields={},selects={},elements=[];
  function element(tag){const e={tag,value:'',classList:{add(){},toggle(){}},style:{setProperty(){}},setAttribute(k,v){this[k]=v;},focus(){this.focused=true;}};elements.push(e);return e;}
  for(const key of ['pain','fatigue']){fields[key]={firstChild:{textContent:''},classList:{add(){}},querySelector:()=>null,append(...xs){this.controls=xs;}};selects[key]={value:key==='pain'?'':'0',closest:()=>fields[key],classList:{add(){}},setAttribute(){},addEventListener(k,fn){this[k]=fn;}};}
  const c={RehabV52:V,$:s=>selects[s.slice(1)],document:{createElement:element},window:{},location:{search:''},URLSearchParams,livePage(){},render(){},syncNavigation(){},showJob(){},renderJob(){},toast(){}};
  vm.createContext(c);vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/rehab-v51-capture.js'),'utf8'),c);c.feedbackScoresV51({});
  const pain=fields.pain.controls[1],fatigue=fields.fatigue.controls[1];assert.equal(selects.pain.value,'');assert.equal(fields.pain.controls[0].textContent,'未选择');assert.equal(fatigue.value,'0');assert.equal(fields.fatigue.controls[0].textContent,'0 / 10');
  pain.onkeydown({key:'Tab'});assert.equal(selects.pain.value,'');pain.onkeydown({key:'Home'});assert.equal(selects.pain.value,'0');
  fatigue.value='10';fatigue.oninput();assert.equal(selects.fatigue.value,'10');assert.equal(fields.fatigue.controls[0].textContent,'10 / 10');
  let prevented=false;selects.pain.invalid({preventDefault(){prevented=true;}});assert.equal(prevented,true);assert.equal(pain.focused,true);
});

test('browser Back restores the retained page without serializing report data into history',async()=>{
  const h=lifecycle();assert.deepEqual(Object.keys(h.nativeHistory.state),['rehabAi52']);h.c.window.popstate({state:null});assert.equal(h.c.app.innerHTML,'restored');assert.equal(h.c.state.job,'original-job');h.resolve({});await h.flush();assert.equal(h.c.app.innerHTML,'restored');
});
