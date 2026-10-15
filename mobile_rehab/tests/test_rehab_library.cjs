const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs');
const L=require('../static/rehab-library.js');
const read=()=>JSON.parse(fs.readFileSync(require('node:path').join(__dirname,'../static/assets/rehab-library-v1/catalogue.json')));
test('public cards have complete read-only content without measurement bindings',()=>{
 const c=L.validate(read());assert.equal(L.filtered(c,'assessment','all','').length,63);assert.equal(L.filtered(c,'training','all','').length,122);
 assert(L.filtered(c,'all','all','硬拉').length>=3);assert.equal(L.filtered(c,'all','all','T-LOW-060')[0].id,'T-LOW-060');
 assert.equal(L.filtered(c,'all','neck','').every(a=>a.category==='neck'),true);
 assert.equal(c.measurement_bindings,false);
});
test('external URLs and cross-card images fail closed',()=>{
 for(const edit of [c=>c.images[c.actions[0].overview].url='https://evil.invalid/x.webp',c=>c.images[c.actions[0].overview].action_id='T-LOW-060',c=>c.actions[1].id=c.actions[0].id,c=>c.measurement_bindings=true]){
  const c=read();edit(c);assert.throws(()=>L.validate(c));
 }
});
test('independent image groups and original cautions are retained',()=>{
 const c=read(),a=c.actions.find(a=>a.id==='T-LOW-038');assert.equal(a.steps.length,8);assert.equal(new Set(a.steps.map(s=>c.images[s].group_id)).size,4);
 const original=JSON.parse(fs.readFileSync(require('node:path').join(__dirname,'../../docs/rehab-library/image-handoff/catalogue.json')));
 for(const a of c.actions){assert.equal(a.source_content,original.actions.find(x=>x.action_id===a.id).source_content);assert(a.source_content.length>100);}
 const deadlift=c.actions.find(a=>a.id==='T-LOW-060');assert(deadlift.start_conditions);assert(deadlift.stop_conditions);assert.equal(deadlift.steps.length,4);
});
