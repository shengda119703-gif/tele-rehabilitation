// Production controller boundaries, controlled TEST transport/DOM, not devices.
'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const plain=v=>JSON.parse(JSON.stringify(v)),tick=()=>new Promise(r=>setImmediate(r));
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return{promise,resolve};};
function harness(){
 const nodes=new Map(),intervals=new Map(),storage=new Map(),calls=[];let clock=0,nextInterval=0,transport=async()=>{};
 const node=()=>({value:'',textContent:'',checked:false,disabled:false,appendChild(n){if(n.id)nodes.set('#'+n.id,n);},parentNode:{appendChild(n){if(n.id)nodes.set('#'+n.id,n);}}});
 const area={appendChild(n){if(n.id)nodes.set('#'+n.id,n);},set innerHTML(html){this.html=html;nodes.clear();nodes.set('#practice-area',area);for(const m of html.matchAll(/id="([^"]+)"/g))nodes.set('#'+m[1],node());},get innerHTML(){return this.html;}};nodes.set('#practice-area',area);
 const context={participant_id:'TEST-person',provider:'hosted-legacy-1',source_context:'REPLAY_FILE:SELF_USE',policy_version:'saved-arrangement-guided-1'};
 const start={operation_id:crypto.randomUUID(),plan_id:crypto.randomUUID(),plan_revision:1,entry_key:'TEST-entry',manual_arrangement_confirmed:true,support_ready:true,companion_present:false};
 const settings={target_reps:3,target_sets:2,rest_between_sets_s:0},entry={key:'TEST-entry',exercise_id:'shoulder_abduction',side:'left',settings};
 const receipt={schema_version:2,sequence_policy:'hosted-guided-sequence-1',id:start.operation_id,journey_id:start.operation_id,context,state:'COMMITTED',start_payload:start,plan_ref:{id:start.plan_id,revision:1,entry_key:start.entry_key},exercise_id:entry.exercise_id,side:'left',settings,self_reported_count:3,finish_payload:{reason:'completed_set'},continuation:{kind:'next_set',entry,set_index:2,decision:{allowed:true,category:null},rest_remaining_ms:0}};
 const j={context,start,receipt,ended:true,running:false,ownerGeneration:0,elapsed:1500,sequenceStage:'REST'};
 const c={console,URL,location:{origin:'https://TEST-owned.invalid',href:'https://TEST-owned.invalid/capture'},automaticUploadReconciliation:true,state:{uploadOwnerGeneration:0,catalog:[]},document:{hidden:false,addEventListener(){},createElement:node},window:{addEventListener(){},history:{replaceState(){}}},performance:{now:()=>clock},setInterval(fn){const id=++nextInterval;intervals.set(id,fn);return id;},clearInterval:id=>intervals.delete(id),localStorage:{setItem:(k,v)=>storage.set(k,v),getItem:k=>storage.get(k)},$:(s)=>nodes.get(s),esc:String,label:x=>x,sideLabel:x=>x,dateLabel:String,toast(){},navigate(){},newUploadOperation:()=>crypto.randomUUID(),api:async(route,opts)=>{calls.push({route,payload:opts?.body?JSON.parse(opts.body):null});return transport(route,opts);}};
 vm.createContext(c);vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/practice-flow.js'),'utf8'),c);c.j=j;c.area=area;vm.runInContext('practiceJourney=j;drawPracticeRest(j,area)',c);
 const child=payload=>({...plain(receipt),id:payload.operation_id,predecessor_id:start.operation_id,start_payload:{...start,operation_id:payload.operation_id},state:'PRACTICING',finish_payload:null,self_reported_count:undefined,continuation:null,continue_payload:plain(payload),set_index:2,execution_allowed:true});
 return{c,j,area,nodes,calls,storage,intervals,child,run:s=>vm.runInContext(s,c),transport:fn=>transport=fn,clock:t=>{clock=t;for(const fn of [...intervals.values()])fn();}};
}
test('lost continue queries the original immutable child key without a second creation',async()=>{
 const h=harness();let saved,posts=0;h.transport(async(route,opts)=>{if(!opts){if(saved)return saved;throw Object.assign(Error('TEST not found'),{status:404});}posts++;saved=h.child(JSON.parse(opts.body));throw Error('TEST unreadable committed reply');});
 await h.run('reconcilePracticeSequence(j,area,false)');assert.equal(posts,1);const original=plain(h.j.nextPending);assert(original.operation_id);assert.equal(h.j.running,false);
 assert([...h.storage.values()].some(v=>JSON.parse(v).nextPending?.operation_id===original.operation_id));
 await h.run('reconcilePracticeSequence(j,area,true)');assert.equal(posts,1);assert.equal(h.run('practiceJourney.start.operation_id'),original.operation_id);assert.equal(h.run('practiceJourney.running'),false);
 assert.equal(h.j.nextPending,null); // Consumed only after matching the original receipt.
});
test('late absence lookup after owner change cannot create a practice for the new owner',async()=>{
 const h=harness();let reject;h.j.receipt=null;h.j.ended=false;
 h.transport(()=>new Promise((resolve,fail)=>reject=fail));
 const pending=h.run('reconcilePractice(j,area,true)');await tick();h.c.state.uploadOwnerGeneration=1;
 reject(Object.assign(Error('TEST old lookup absent'),{status:404}));await pending;
 assert.equal(h.calls.length,1);assert.equal(h.calls[0].payload,null);assert.equal(h.j.busy,false);
});
test('an old owner cannot automatically submit a retained finish intent',async()=>{
 const h=harness();h.c.state.uploadOwnerGeneration=1;h.j.finish={operation_id:crypto.randomUUID()};
 await h.run('submitPracticeFinish(j,area)');assert.equal(h.calls.length,0);
});
test('native pagehide events are normalized to a stable resource-stop reason',()=>{const h=harness();let reason;h.c.stopPracticeObservation=(j,value)=>reason=value;h.c.event={type:'pagehide'};h.run('pausePractice(event)');assert.equal(reason,'page_hidden');assert.equal(h.j.running,false);});
test('end during in-flight creation ends actual child and never runs its clock',async()=>{
 const h=harness(),pending=deferred();let payload;h.transport(async(route,opts)=>{if(!opts)throw Object.assign(Error('TEST absent'),{status:404});const value=JSON.parse(opts.body);if(route.endsWith('/continue')){payload=value;return pending.promise;}if(route.endsWith('/finish'))return{...h.child(payload),state:'COMMITTED',finish_payload:value,execution_allowed:false};throw Error('TEST unexpected route');});
 const running=h.run('reconcilePracticeSequence(j,area,false)');await tick();h.nodes.get('#practice-sequence-end').onclick();assert.equal(h.j.sequenceEndRequested,true);
 pending.resolve(h.child(payload));await running;await tick();const finish=h.calls.find(c=>c.route.endsWith('/finish'));assert.equal(finish.payload.reason,'ended');assert.equal(finish.payload.count,null);assert.equal(finish.payload.elapsed_ms,0);assert.equal(h.run('practiceJourney.running'),false);
});
test('unknown end lookup errors are bounded and preserve original identity for manual retry',async()=>{
 const h=harness();h.j.nextPending={operation_id:crypto.randomUUID(),manual_arrangement_confirmed:true,support_ready:true,companion_present:false};h.j.sequenceEndRequested=true;
 h.transport(async()=>{throw Error('TEST persistent read failure');});await h.run('reconcilePracticeSequence(j,area,false)');await tick();await tick();
 assert.equal(h.calls.length,2);assert(h.calls.every(c=>!c.payload&&c.route.endsWith(h.j.nextPending.operation_id)));assert.equal(h.j.sequenceEndRequested,true);assert.equal(h.j.sequenceBusy,false);assert.match(h.area.html,/结束待核对/);
});
test('hidden late successor cannot start background practice or replenish elapsed time',async()=>{
 const h=harness(),pending=deferred();let value;h.transport(async(route,opts)=>{if(!opts)throw Object.assign(Error('TEST absent'),{status:404});value=JSON.parse(opts.body);return pending.promise;});
 const running=h.run('reconcilePracticeSequence(j,area,false)');await tick();h.c.document.hidden=true;pending.resolve(h.child(value));await running;assert.equal(h.run('practiceJourney.running'),false);assert.equal(h.run('practiceJourney.elapsed'),0);
});
test('rest timer does not contribute exercise and does not automatically create a group',()=>{
 const h=harness();h.j.receipt.continuation.rest_remaining_ms=3000;h.run('drawPracticeRest(j,area)');assert.equal(h.nodes.get('#practice-sequence-start').disabled,true);h.clock(3100);assert.equal(h.nodes.get('#practice-sequence-start').disabled,false);assert.equal(h.j.elapsed,1500);assert.equal(h.calls.length,0);assert.equal(h.j.running,false);
});
test('late original rest read cannot reopen a journey after explicit end',async()=>{
 const h=harness(),pending=deferred(),original=plain(h.j.receipt);let reads=0;h.transport(async(route,opts)=>{if(!opts)return ++reads===1?pending.promise:original;return{...original,journey_closed:true,continuation:null,close_payload:JSON.parse(opts.body)};});
 const read=h.run('openPracticeRest(j,area)');await tick();h.nodes.get('#practice-sequence-end').onclick();await tick();assert.equal(h.j.receipt.journey_closed,true);pending.resolve(original);await read;assert.equal(h.j.receipt.journey_closed,true);assert.equal(h.j.receipt.continuation,null);
});
test('ordinary End remains ended with null count, never completed_set',async()=>{
 const h=harness();h.j.sequenceStage=null;h.j.ended=false;h.j.receipt.state='PRACTICING';h.j.receipt.execution_allowed=true;h.j.receipt.continuation=null;
 h.transport(async(route,opts)=>{const p=JSON.parse(opts.body);return{...h.j.receipt,state:'COMMITTED',self_reported_count:p.count,finish_payload:p};});h.run('drawPractice(j,area)');h.nodes.get('#practice-end').onclick();await tick();
 const finish=h.calls.find(c=>c.route.endsWith('/finish'));assert.equal(finish.payload.reason,'ended');assert.equal(finish.payload.count,null);assert.equal(h.j.receipt.self_reported_count,null);assert.equal(h.nodes.has('#practice-next'),false);
});
test('lost close reply is queried before any second close write and preserves original group',async()=>{
 const h=harness();h.j.sequenceEndRequested=true;let saved=null,posts=0;h.transport(async(route,opts)=>{if(!opts)return saved||h.j.receipt;posts++;saved={...plain(h.j.receipt),journey_closed:true,continuation:null,close_payload:JSON.parse(opts.body)};throw Error('TEST unreadable committed close reply');});
 const original=plain(h.j.receipt.finish_payload);await h.run('reconcilePracticeSequence(j,area,false)');await tick();await tick();
 assert.equal(posts,1);assert.equal(h.j.sequenceEndRequested,false);assert.equal(h.j.receipt.journey_closed,true);assert.deepEqual(plain(h.j.receipt.finish_payload),original);assert.equal(h.j.receipt.self_reported_count,3);
});
test('original automatic entry resumes a later action without using unchanged formal next key',()=>{
 const h=harness(),root=plain(h.j.receipt),later={...plain(root),id:crypto.randomUUID(),state:'PRACTICING',successor_id:null,plan_ref:{...root.plan_ref,entry_key:'TEST-later'}};
 h.c.rows=[root,later];h.c.plan={id:root.plan_ref.id,revision:root.plan_ref.revision};h.c.context=root.context;
 assert.equal(h.run('originalPracticeSequence(rows,plan,context).id'),later.id);
 h.storage.set(h.run('practiceRecordDraftKey(context,rows[0].id)'),JSON.stringify({context:root.context,start:root.start_payload,sequenceEndRequested:true}));
 assert.equal(h.run('originalPracticeSequence(rows,plan,context).id'),root.id);
 h.c.context={...root.context,participant_id:'TEST-other'};assert.equal(h.run('originalPracticeSequence(rows,plan,context)'),null);
});
test('return or refresh restores an actual active group paused until explicit continue',async()=>{
 const h=harness();h.j.ended=false;h.j.sequenceStage=null;h.j.initialRestorePaused=true;h.j.receipt={...plain(h.j.receipt),state:'PRACTICING',finish_payload:null,execution_allowed:true};
 h.transport(async()=>h.j.receipt);await h.run('reconcilePractice(j,area)');assert.equal(h.j.running,false);assert.equal(h.j.initialRestorePaused,false);
 await h.run('reconcilePractice(j,area)');assert.equal(h.j.running,true);
});
