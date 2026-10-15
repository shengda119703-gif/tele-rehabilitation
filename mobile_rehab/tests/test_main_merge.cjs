// Integration wiring only: no camera, patient records or invented measurements.
'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const read=name=>fs.readFileSync(path.join(__dirname,'../static',name),'utf8');
function harness(){
  const nodes=new Map(),calls=[];
  const node=()=>({hidden:false,textContent:'',classList:{toggle(){}},setAttribute(){}});
  for(const id of ['#app','.bottom-nav','#toast'])nodes.set(id,node());
  const c={URLSearchParams,URL,console,AbortController,setTimeout,clearTimeout,
    location:{search:'',hash:'',pathname:'/capture'},history:{replaceState(){}},
    document:{body:{dataset:{}},querySelector:s=>nodes.get(s),querySelectorAll:()=>[]},
    addEventListener(){},scrollTo(){},livePage(){},fitnessPage(){},posturePage(){},
    bodyPage(){},renderPostureReport(){},renderFitnessReport(){},
    beginGuidedPractice:(record,entry)=>calls.push(['practice',record.id,entry.key])};
  c.window=c;vm.createContext(c);vm.runInContext(read('app.js'),c);
  vm.runInContext("state.catalog=[{id:'TEST-action',joint:'shoulder'}];",c);
  c.assessment=()=>calls.push(['assessment']);c.syncNavigation=()=>{};c.clearFile=()=>{};
  return{c,calls,nodes,run:code=>vm.runInContext(code,c)};
}
const record={id:'TEST-plan'},entry={key:'TEST-entry',exercise_id:'TEST-action',side:'left'};
test('main plan entry preserves local guided practice when supported',()=>{
  const h=harness();h.run('state.practiceRecording=true');h.c.startPlanEntry(record,entry);
  assert.deepEqual(h.calls,[['practice',record.id,entry.key]]);
  assert.equal(h.run('state.training.entry.key'),entry.key);
});
test('phone-local plan entry retains replay preparation without hosted practice',()=>{
  const h=harness();h.c.startPlanEntry(record,entry);
  assert.deepEqual(h.calls,[['assessment']]);assert.equal(h.run('state.preparing'),true);
  assert.equal(h.run('state.captureSource'),'REPLAY_FILE');
});
test('new presentation wraps local history renderer without replacing native History',()=>{
  const h=harness(),native=h.c.history;let reads=0;
  h.c.renderHistory=()=>{reads++;};vm.runInContext(read('rehab-v51-capture.js'),h.c);
  h.c.renderHistory();assert.equal(reads,1);assert.equal(h.c.history,native);
});
