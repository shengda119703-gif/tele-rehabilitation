const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const staticRoot=path.join(__dirname,'../static');
function load(){
  const root={};const context={window:root};vm.createContext(context);
  for(const name of ['assessment-artwork.js','rehab-v51.js'])vm.runInContext(fs.readFileSync(path.join(staticRoot,name),'utf8'),context);
  return root;
}
test('all 53 existing assessment IDs have an explicit packaged cover',()=>{
  const root=load(),A=root.RehabAssessmentArtwork;
  const ids=Object.keys(JSON.parse(fs.readFileSync(path.join(staticRoot,'assets/rehab-candidates-v10/exercise-mapping.json'))));
  assert.equal(ids.length,53);assert.deepEqual(Object.keys(A.entries).sort(),ids.sort());
  for(const id of ids){
    const item=A.get(id);assert.equal(item.scope,'catalogue_cover');assert.ok(item.alt);
    assert.match(item.url,/^\/static\/assets\/(rehab-library-v1|assessment-artwork-v1)\/[A-Za-z0-9_-]+\.webp$/);
    assert.ok(fs.existsSync(path.join(staticRoot,item.url.replace('/static/',''))),item.url);
    for(const field of ['side','phase','angle','target','measurement'])assert.equal(item[field],undefined);
    assert.ok(Object.isFrozen(item));
    for(const html of [root.RehabV51.thumb(id,true),root.RehabV51.picture(id,true,true),root.RehabV51.picture(id,true)]){
      assert.match(html,/<img/);assert.doesNotMatch(html,/rehab-candidates|图片待核验|rv-placeholder/);
      assert.ok(html.includes(item.url));
    }
  }
});
test('unknown and prototype IDs cannot construct image paths',()=>{
  const root=load();for(const id of ['__proto__','constructor','../secret','shoulder_internal_rotation','<script>']){
    assert.equal(root.RehabAssessmentArtwork.get(id),null);assert.doesNotMatch(root.RehabV51.thumb(id),/<img/);
  }
});
test('new covers do not fetch resources, write user data or enable private candidates',()=>{
  const text=fs.readFileSync(path.join(staticRoot,'assessment-artwork.js'),'utf8');
  assert.doesNotMatch(text,/fetch\(|localStorage|indexedDB|\.post\(|accountRequest|candidate_images|__ANKANG_INTERNAL_IMAGE_PREVIEW__/);
  for(const name of ['index.html','unified.html']){
    const html=fs.readFileSync(path.join(staticRoot,name),'utf8');
    assert.ok(html.indexOf('/static/assessment-artwork.js')<html.indexOf('/static/rehab-v51.js'));
    assert.ok(html.includes('/static/assessment-artwork.css'));
  }
});
test('assessment, details and preparation use the same overview, never a stage image',()=>{
  const root=load(),A=root.RehabAssessmentArtwork;
  assert.equal(A.get('elbow_extension').url,A.get('elbow_flexion').url);
  assert.match(A.get('elbow_extension').url,/elbow-seated/);
  assert.match(A.get('trunk_extension').url,/trunk-extension-seated/);
  assert.match(A.get('wrist_radial_deviation').url,/wrist-overhead/);
  for(const finger of ['thumb','index','middle','ring','pinky'])for(const joint of finger==='thumb'?['mcp','ip']:['mcp','pip','dip']){
    assert.match(A.get(`${finger}_${joint}_flexion`).url,new RegExp(finger+'-flexion'));
    assert.match(A.get(`${finger}_${joint}_extension`).url,/hand-extension/);
  }
});
test('cover layout keeps the complete image visible and does not mirror anatomy',()=>{
  const css=fs.readFileSync(path.join(staticRoot,'assessment-artwork.css'),'utf8');
  assert.match(css,/object-fit:\s*contain/);assert.doesNotMatch(css,/scaleX|rotate\(|object-fit:\s*cover/);
  assert.match(css,/aspect-ratio/);
});
test('catalogue sorting keeps every item, leaves plans and its input untouched',()=>{
  const root=load(),items=Object.keys(root.RehabAssessmentArtwork.entries).map(id=>({id}));
  const before=JSON.stringify(items),result=root.RehabV51.order(items);
  assert.equal(JSON.stringify(items),before);assert.equal(result.length,53);
  assert.equal(new Set(result.map(x=>x.id)).size,53);
});
