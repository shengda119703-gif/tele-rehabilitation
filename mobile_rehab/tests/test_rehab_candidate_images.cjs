const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.join(__dirname,'../static'),base=path.join(root,'assets/rehab-candidates-v10');
const index=JSON.parse(fs.readFileSync(path.join(base,'resource-index.json'))),mapping=JSON.parse(fs.readFileSync(path.join(base,'exercise-mapping.json')));
function context(host='127.0.0.1',flag=true,query='?rehabImagePreview=1',failure=false){
 const w={location:{hostname:host,search:query},__ANKANG_INTERNAL_IMAGE_PREVIEW__:flag,fetch:async url=>({ok:!failure,json:async()=>url.includes('resource-index')?index:mapping})};
 const c={window:w,URLSearchParams};vm.createContext(c);vm.runInContext(fs.readFileSync(path.join(root,'rehab-candidate-images.js'),'utf8'),c);return w;
}
test('internal marker, loopback and explicit opt-in are all required',async()=>{
 for(const args of [['127.0.0.1',false],['example.com',true],['127.0.0.1',true,''],['localhost',true,'?rehabImagePreview=0']]){
  const w=context(...args);assert.equal(w.RehabCandidateImages.enabled(),false);assert.equal(await w.RehabCandidateImages.load(),false);assert.equal(w.RehabCandidateImages.thumb('shoulder_abduction'),'');
 }
});
test('185 cards and 656 explicit selected slots, no archive/reference URL',()=>{
 assert.equal(index.public_actions.length,185);assert.equal(Object.keys(index.images).length,656);
 for(const [slot,img] of Object.entries(index.images)){
  assert.equal(slot,img.slot_id);assert.equal(img.review_status,'pending');assert.equal(img.side,null);assert.equal(img.phase,null);
  assert.doesNotMatch(img.original_path,/archive|references/);assert.match(img.url,/^\/static\/assets\/rehab-candidates-v10\/[\w-]+\.webp$/);
  assert.ok(fs.existsSync(path.join(root,img.url.replace('/static/',''))));
 }
});
test('53 IDs preserve sides and phases with 25 candidate and 28 empty entries',()=>{
 assert.equal(Object.keys(mapping).length,53);assert.equal(Object.values(mapping).filter(m=>m.candidate_images.length).length,25);
 for(const [id,m] of Object.entries(mapping)){
  assert.equal(m.exercise_id,id);assert.equal(m.patient_enabled,false);assert.equal(m.review_status,'pending');
  for(const side of ['left','right'])for(const phase of ['start','move','return'])assert.equal(m.phase_slots[side][phase],null);
  for(const b of m.candidate_images){assert.equal(b.side,null);assert.equal(b.phase,null);assert.equal(b.review_status,'pending');assert.equal(index.images[b.slot_id].action_id,b.public_action_id);}
  if(/^(thumb|index|middle|ring|pinky)_/.test(id))assert.equal(m.candidate_images.length,0);
 }
});
test('candidate HTML is exact ID scoped, lazy, visibly pending and unknown',async()=>{
 const w=context();await w.RehabCandidateImages.load();const P=w.RehabCandidateImages;
 assert.match(P.thumb('shoulder_abduction'),/049_E-AXU-013_s01/);assert.doesNotMatch(P.thumb('shoulder_abduction'),/057_E-AXU-017/);
 assert.match(P.gallery('elbow_extension'),/阻断直接复用/);assert.equal(P.thumb('elbow_extension'),'');assert.equal(P.picture('elbow_extension',true),'');assert.equal(Object.values(mapping).filter(m=>m.preview_scope==='resource_library_only').length,7);assert.match(P.picture('shoulder_abduction',true),/侧别、阶段未确认/);
 assert.match(P.gallery('shoulder_abduction'),/loading="lazy"/);assert.equal(P.thumb('index_mcp_flexion'),'');assert.equal(P.gallery('__wrong'), '');
});
test('loading failure leaves the original picture and instruction fallback',async()=>{
 const w=context('127.0.0.1',true,'?rehabImagePreview=1',true);assert.equal(await w.RehabCandidateImages.load(),false);assert.equal(w.RehabCandidateImages.picture('shoulder_abduction',true),'');assert.match(w.RehabCandidateImages.status(),/加载失败/);
});
test('explicit selected versions survive, never highest version guessing',()=>{
 assert.match(index.images['116_T-LOW-038_s06'].selected_source,/_v2\.png$/);
 assert.doesNotMatch(index.images['052_E-AXU-016_s02'].selected_source,/_v2/);
});
test('existing presentation defaults, plan and preparation do not opt into candidates',async()=>{
 const w=context();await w.RehabCandidateImages.load();const c={window:w};vm.createContext(c);vm.runInContext(fs.readFileSync(path.join(root,'rehab-v51.js'),'utf8'),c);
 assert.doesNotMatch(w.RehabV51.picture('shoulder_abduction',true),/rehab-candidates/);
 assert.doesNotMatch(w.RehabV51.thumb('shoulder_abduction'),/rehab-candidates/);
 assert.match(w.RehabV51.thumb('shoulder_abduction',true),/rehab-candidates/);
 const app=fs.readFileSync(path.join(root,'app.js'),'utf8');assert.match(app,/picture\(ex.id,true\)/);assert.match(app,/thumb\(i.exercise_id\)/);
 const capture=fs.readFileSync(path.join(root,'rehab-v51-capture.js'),'utf8');assert.match(capture,/picture\(entry.exercise_id,true\)/);
 assert.doesNotMatch(fs.readFileSync(path.join(root,'index.html'),'utf8'),/__ANKANG_INTERNAL_IMAGE_PREVIEW__\s*=/);
});
test('candidate images are contained and overlays cannot cover anatomy',()=>{
 const css=fs.readFileSync(path.join(root,'rehab-candidate-images.css'),'utf8');assert.doesNotMatch(css,/object-fit\s*:\s*cover|scaleX|rotate|!important/);assert.match(css,/object-fit:contain/);assert.match(css,/figcaption\{position:static/);
});
