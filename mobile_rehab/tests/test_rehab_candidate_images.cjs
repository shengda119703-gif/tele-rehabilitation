const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.join(__dirname,'../static'),base=path.join(root,'assets/rehab-candidates-v10');
const index=JSON.parse(fs.readFileSync(path.join(base,'resource-index.json'))),mapping=JSON.parse(fs.readFileSync(path.join(base,'exercise-mapping.json'))),catalog=JSON.parse(fs.readFileSync(path.join(base,'catalog-display.json')));
function context(host='127.0.0.1',flag=true,query='?rehabImagePreview=1',failure=false){
 const w={location:{hostname:host,search:query},__ANKANG_INTERNAL_IMAGE_PREVIEW__:flag,fetch:async url=>({ok:!failure,json:async()=>url.includes('resource-index')?index:url.includes('exercise-mapping')?mapping:catalog})};
 const c={window:w,URLSearchParams};vm.createContext(c);vm.runInContext(fs.readFileSync(path.join(root,'rehab-candidate-images.js'),'utf8'),c);return w;
}
test('ordinary catalogue shows declared pictures without an internal marker or query',async()=>{
 for(const args of [['127.0.0.1',false,''],['example.com',false,''],['example.com',true,'?rehabImagePreview=1'],['localhost',false,'?rehabImagePreview=0']]){
  const w=context(...args),P=w.RehabCandidateImages;assert.equal(P.enabled(),false);assert.equal(await P.load(),true);
  assert.match(P.thumb('shoulder_abduction'),/049_E-AXU-013_s02/);
  assert.equal(Object.keys(mapping).filter(id=>P.thumb(id)).length,18);
  assert.equal(P.picture('elbow_flexion',true),'');assert.equal(P.thumb('index_mcp_flexion'),'');
 }
});
test('catalogue covers are explicitly selected from exact candidates, not clinical bindings',()=>{
 assert.equal(Object.keys(catalog.covers).length,18);
 for(const [id,slot] of Object.entries(catalog.covers)){
  assert.equal(mapping[id].preview_scope,'internal_candidate');
  assert.ok(mapping[id].candidate_images.some(b=>b.slot_id===slot&&b.public_action_id===index.images[slot].action_id));
  assert.equal(mapping[id].patient_enabled,false);
 }
 assert.equal(catalog.covers.shoulder_flexion,'048_E-AXU-012_s02');
 assert.equal(catalog.covers.shoulder_abduction,'049_E-AXU-013_s02');
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
 assert.match(P.thumb('shoulder_abduction'),/049_E-AXU-013_s02/);assert.doesNotMatch(P.thumb('shoulder_abduction'),/057_E-AXU-017/);
 assert.match(mapping.elbow_extension.issues.join(' '),/阻断直接复用/);assert.equal(P.thumb('elbow_extension'),'');assert.equal(P.picture('elbow_extension',true),'');assert.equal(Object.values(mapping).filter(m=>m.preview_scope==='resource_library_only').length,7);assert.match(P.picture('shoulder_abduction',true),/配图待审核/);
 assert.match(P.picture('shoulder_abduction',true),/loading="lazy"/);assert.match(P.thumb('shoulder_abduction'),/width="959" height="1200"/);assert.equal(P.thumb('index_mcp_flexion'),'');assert.equal(P.picture('__wrong',true), '');
});
test('loading failure leaves the original picture and instruction fallback',async()=>{
 const w=context('127.0.0.1',true,'?rehabImagePreview=1',true);assert.equal(await w.RehabCandidateImages.load(),false);assert.equal(w.RehabCandidateImages.picture('shoulder_abduction',true),'');assert.match(w.RehabCandidateImages.status(),/加载失败/);
});
test('a cover from another action or a conflict pool fails closed to text',async()=>{
 for(const bad of [{...catalog,covers:{shoulder_abduction:'057_E-AXU-017_s01'}},{...catalog,covers:{elbow_flexion:'057_E-AXU-017_s01'}}]){
  const w=context('example.com',false,''),fetch=w.fetch;
  w.fetch=async url=>url.includes('catalog-display')?{ok:true,json:async()=>bad}:fetch(url);
  assert.equal(await w.RehabCandidateImages.load(),false);assert.equal(w.RehabCandidateImages.thumb('shoulder_abduction'),'');
 }
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
 const css=fs.readFileSync(path.join(root,'rehab-candidate-images.css'),'utf8');assert.doesNotMatch(css,/object-fit\s*:\s*cover|scaleX|rotate|!important/);assert.match(css,/object-fit:contain/);assert.match(css,/rv-candidate-thumb img\{width:100%;height:auto/);assert.doesNotMatch(css,/grid-template-rows:minmax\(0,1fr\) 22px/);assert.doesNotMatch(css,/position:absolute/);assert.match(css,/scroll-snap-type:x mandatory/);
});

// Sorting is a catalogue view only: neither the input nor plan execution order changes.
test('pictured actions precede text-only actions without dropping IDs or changing group order',async()=>{
 const w=context('example.com',false,'');await w.RehabCandidateImages.load();
 const c={window:w};vm.createContext(c);vm.runInContext(fs.readFileSync(path.join(root,'rehab-v51.js'),'utf8'),c);
 const items=[{id:'index_mcp_flexion'},{id:'elbow_extension'},{id:'hip_flexion'},{id:'shoulder_abduction'},{id:'ankle_dorsiflexion'}],before=JSON.stringify(items);
 assert.deepEqual(Array.from(w.RehabV51.order(items),x=>x.id),['shoulder_abduction','hip_flexion','ankle_dorsiflexion','index_mcp_flexion','elbow_extension']);
 assert.equal(JSON.stringify(items),before);
 const all=Object.keys(mapping).map(id=>({id})),ordered=Array.from(w.RehabV51.order(all));
 assert.equal(ordered.length,53);assert.equal(new Set(ordered.map(x=>x.id)).size,53);
 assert.ok(ordered.slice(0,18).every(x=>w.RehabV51.thumb(x.id,true).includes('<img')));
 assert.ok(ordered.slice(18).every(x=>!w.RehabV51.thumb(x.id,true).includes('<img')));
});

test('each catalogue cover is the last mapped picture and all 38 pictures live in the main carousel',async()=>{
 const w=context('example.com',false,'');await w.RehabCandidateImages.load();let total=0;
 for(const [id,slot] of Object.entries(catalog.covers)){
  const bindings=mapping[id].candidate_images;
  assert.equal(slot,bindings.at(-1).slot_id);
  const html=w.RehabCandidateImages.picture(id,true);
  assert.deepEqual(Array.from(html.matchAll(/data-candidate-open="([^"]+)"/g),m=>m[1]),bindings.map(b=>b.slot_id));
  assert.match(html,new RegExp('data-photo-start="'+(bindings.length-1)+'"'));
  assert.doesNotMatch(html,/<details|rv-candidate-materials/);
  total+=bindings.length;
 }
 assert.equal(total,38);
 const capture=fs.readFileSync(path.join(root,'rehab-v51-capture.js'),'utf8');
 assert.doesNotMatch(capture,/\.gallery\(/);assert.match(capture,/\.mount\?\.\(app\)/);
});
test('main image navigation starts at the cover, supports boundaries, keyboard and reduced motion',()=>{
 const w=context(),buttons=Array.from({length:3},()=>({tabIndex:0}));let onscroll,lastBehavior;
 const track={clientWidth:320,scrollLeft:0,children:buttons.map(b=>({querySelector:()=>b})),addEventListener:(_name,fn)=>onscroll=fn,
  scrollTo({left,behavior}){this.scrollLeft=left;lastBehavior=behavior;onscroll();}};
 const previous={},next={},output={},parts={'.rv-carousel-track':track,'[data-photo-prev]':previous,'[data-photo-next]':next,output};
 w.RehabCandidateImages.mount({querySelectorAll:()=>[{dataset:{photoStart:'2'},querySelector:key=>parts[key]}]});
 assert.equal(track.scrollLeft,640);assert.equal(output.textContent,'3 / 3');assert.equal(next.disabled,true);
 previous.onclick();assert.equal(track.scrollLeft,320);assert.equal(output.textContent,'2 / 3');assert.equal(next.disabled,false);
 let prevented=0;track.onkeydown({target:track,key:'Home',preventDefault(){prevented++;}});
 assert.equal(output.textContent,'1 / 3');assert.equal(previous.disabled,true);assert.equal(prevented,1);
 next.onclick();assert.equal(output.textContent,'2 / 3');
 w.matchMedia=()=>({matches:true});track.onkeydown({target:track,key:'End',preventDefault(){}});
 assert.equal(output.textContent,'3 / 3');assert.equal(lastBehavior,'auto');
 track.scrollLeft=0;onscroll();assert.equal(output.textContent,'1 / 3');
 assert.deepEqual(buttons.map(b=>b.tabIndex),[0,-1,-1]);
});
