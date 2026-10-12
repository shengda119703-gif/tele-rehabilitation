// Production feedback controller with controlled transport/DOM, not phone QA.
const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const plain=v=>JSON.parse(JSON.stringify(v)),tick=()=>new Promise(r=>setImmediate(r));
function harness(){
 const nodes=new Map(),panel={id:'practice-feedback',set innerHTML(v){this.html=v;nodes.clear();for(const m of v.matchAll(/id="([^"]+)"/g))nodes.set('#'+m[1],{value:'',textContent:'',disabled:false});},get innerHTML(){return this.html;}};
 const area={},j={context:{provider:'TEST-owned',participant_id:'TEST-person'},start:{operation_id:crypto.randomUUID()},receipt:{state:'COMMITTED'},draftSaved:true};
 let active=true,revision=0,values={pain:null,fatigue:null,note:null},lost=false,failRead=false;const ops=new Map(),writes=[],drafts=[];
 const equal=(a,b)=>JSON.stringify(a)===JSON.stringify(b),snapshot=()=>({practice_id:j.start.operation_id,context:j.context,revision,values,saved_at:revision?'TEST-time':null});
 const c={document:{createElement:()=>panel},$:(id)=>id==='#practice-feedback'?panel:nodes.get(id),esc:String,toast:()=>{},newUploadOperation:()=>crypto.randomUUID(),practiceEqual:equal,currentPractice:()=>active,persistPractice:v=>drafts.push(plain(v)),pausePractice(){},navigate(){},console};
 c.api=async(route,opts)=>{
  if(failRead)throw Error('TEST disconnected');
  if(route.includes('/operations/')){const r=ops.get(route.split('/').at(-1));if(!r)throw Object.assign(Error('TEST missing'),{status:404});return plain(r);}
  if(!opts)return plain(snapshot());
  const p=JSON.parse(opts.body);writes.push(p);
  if(p.expected_revision!==revision)throw Object.assign(Error('TEST revision conflict'),{status:409,reason:{code:'FEEDBACK_REVISION_CONFLICT'}});
  values=p.values;revision++;const r={...snapshot(),...p,revision,status:'COMMITTED'};ops.set(p.operation_id,r);
  if(lost){lost=false;throw Error('TEST unreadable committed reply');}return plain(r);
 };
 vm.createContext(c);vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/practice-feedback.js'),'utf8'),c);
 c.j=j;c.area=area;c.panel=panel;
 return{c,j,area,panel,nodes,writes,drafts,run:s=>vm.runInContext(s,c),setLost:()=>lost=true,setReadFail:()=>failRead=true,deactivate:()=>active=false,external:v=>{values=v;revision++;}};
}
async function mount(h){h.run('drawPracticeFeedback(j,area,panel);reconcilePracticeFeedback(j,area,panel)');await tick();}
test('feedback blanks remain null, explicit zero is distinct, and skip does not write',async()=>{
 const h=harness();await mount(h);assert.equal(h.nodes.get('#practice-pain').value,'');assert.equal(h.nodes.get('#practice-fatigue').value,'');
 assert.deepEqual(plain(h.run("practiceFeedbackValues({pain:'',fatigue:'0',note:'  '})")),{pain:null,fatigue:0,note:null});
 h.nodes.get('#practice-feedback-later').onclick();assert.equal(h.writes.length,0);
});
test('lost feedback reply preserves immutable intent, queries same key, and never posts another write',async()=>{
 const h=harness();await mount(h);h.j.feedbackDraft={pain:'',fatigue:'3',note:'TEST explicit'};h.setLost();h.nodes.get('#practice-feedback-submit').onclick();await tick();
 assert.equal(h.writes.length,1);const original=plain(h.j.feedbackPending);assert.equal(original.values.pain,null);assert.match(h.panel.html,/保存待核对/);
 await h.run('reconcilePracticeFeedback(j,area,panel)');assert.equal(h.writes.length,1);assert.equal(h.j.feedbackPending,null);assert.equal(h.j.feedbackSnapshot.revision,1);assert.match(h.panel.html,/感受已保存/);
 assert(h.drafts.some(d=>d.feedbackPending?.operation_id===original.operation_id));
});
test('genuine revision conflict retains draft and requires explicit latest-version replacement',async()=>{
 const h=harness();await mount(h);h.external({pain:null,fatigue:2,note:'TEST other editor'});h.j.feedbackDraft={pain:'',fatigue:'3',note:'TEST my draft'};
 h.nodes.get('#practice-feedback-submit').onclick();await tick();assert.equal(h.j.feedbackConflict,true);assert.equal(h.writes.length,1);assert.equal(h.j.feedbackPending.expected_revision,0);assert.equal(h.j.feedbackDraft.note,'TEST my draft');
 const oldKey=h.j.feedbackPending.operation_id;h.nodes.get('#practice-feedback-replace').onclick();await tick();assert.equal(h.writes.length,2);assert.equal(h.writes[1].expected_revision,1);assert.notEqual(h.writes[1].operation_id,oldKey);assert.equal(h.j.feedbackSnapshot.revision,2);assert.equal(h.j.feedbackSuperseded[0].operation_id,oldKey);
});
test('same-value revision conflict converges without a new write',async()=>{
 const h=harness();await mount(h);h.external({pain:null,fatigue:3,note:'TEST same'});h.j.feedbackDraft={pain:'',fatigue:'3',note:'TEST same'};
 h.nodes.get('#practice-feedback-submit').onclick();await tick();assert.equal(h.writes.length,1);assert.equal(h.j.feedbackPending,null);assert.equal(h.j.feedbackConflict,false);assert.match(h.panel.html,/相同感受已保存/);
});
test('read failure leaves a retry and stale owner callback cannot submit feedback',async()=>{
 const h=harness();h.setReadFail();await mount(h);assert.equal(h.nodes.get('#practice-feedback-submit').disabled,false);assert.equal(h.nodes.get('#practice-feedback-submit').textContent,'重试读取感受');assert.equal(h.writes.length,0);
 const old=harness();old.j.feedbackPending={operation_id:crypto.randomUUID(),expected_revision:0,values:{pain:null,fatigue:3,note:null}};old.deactivate();await mount(old);assert.equal(old.writes.length,0);
});
test('initial slow read disables only feedback submit before an unknown revision can be used',async()=>{
 const h=harness();let resolve;h.c.api=()=>new Promise(r=>resolve=r);
 const pending=h.run('drawPracticeFeedback(j,area,panel);reconcilePracticeFeedback(j,area,panel)');
 assert.equal(h.nodes.get('#practice-feedback-submit').disabled,true);assert.equal(h.nodes.get('#practice-feedback-later').disabled,false);
 assert.match(h.panel.html,/正在核对感受保存状态/);assert.equal(h.writes.length,0);
 resolve({practice_id:h.j.start.operation_id,context:h.j.context,revision:0,values:{pain:null,fatigue:null,note:null},saved_at:null});await pending;
 assert.equal(h.nodes.get('#practice-feedback-submit').disabled,false);assert.equal(h.nodes.get('#practice-pain').value,'');
});
