// Controller capability/navigation checks only; real writes are verified by
// verify_manual_practice.cjs against the original SQLite/manual library.
'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
function harness({enabled=true,legacy=false,read=async()=>[]}={}){
 const nodes=[],calls=[],state={tab:'plan',practiceRecording:true,manualPracticeArrangements:enabled,uploadOwnerGeneration:0};
 const document={createElement(){return{innerHTML:'',hidden:false,button:{},remove(){nodes.splice(nodes.indexOf(this),1);},querySelector(){return this.button;}};}};
 const scope={state,automaticUploadReconciliation:!legacy,document,app:{appendChild:e=>nodes.push(e)},$:s=>nodes.find(n=>'#'+n.id===s),api:async p=>{calls.push(p);return read(p);}};
 vm.createContext(scope);vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/manual-arrangements.js'),'utf8'),scope);return{scope,nodes,calls};
}
test('APK/unsupported capability does not request the hosted manual API',async()=>{const h=harness({enabled:false,read:async()=>{throw Error('unsupported');}});await h.scope.mountManualArrangements();assert.equal(h.calls.length,0);assert.equal(h.nodes.length,0);});
test('legacy disables the new entry without reading or deleting facts',async()=>{const h=harness({legacy:true});await h.scope.mountManualArrangements();assert.equal(h.calls.length,0);assert.equal(h.nodes.length,0);});
test('empty original manual library adds no mandatory evaluation or new plan',async()=>{const h=harness();await h.scope.mountManualArrangements();assert.deepEqual(h.calls.sort(),['/practice','/practice/arrangements']);assert.equal(h.nodes.length,0);});
test('manual read error is local with retry, not a replacement for the plan page',async()=>{const h=harness({read:async()=>{throw Error('TEST unavailable');}});await h.scope.mountManualArrangements();assert.equal(h.nodes.length,1);assert.equal(h.nodes[0].hidden,false);assert.match(h.nodes[0].innerHTML,/暂时未能读取/);assert.equal(typeof h.nodes[0].button.onclick,'function');assert.equal(h.scope.state.tab,'plan');});
test('late responses after owner change cannot render the previous manual arrangements',async()=>{let resolve;const wait=new Promise(r=>resolve=r),h=harness({read:async()=>wait});const pending=h.scope.mountManualArrangements();h.scope.state.uploadOwnerGeneration++;resolve([]);await pending;assert.equal(h.nodes[0].innerHTML,'');assert.equal(h.nodes[0].hidden,true);});
