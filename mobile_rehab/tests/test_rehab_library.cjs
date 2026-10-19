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

// Minimal UI fixture; the packaging/browser checks compare the real backend catalogue.
const gym=()=>[['fitness_squat','深蹲','下肢'],['fitness_deadlift','硬拉','下肢'],['fitness_bench_press','卧推','推'],['fitness_row','俯身划船','拉'],['fitness_overhead_press','肩上推举','推'],['fitness_curl','二头弯举','拉'],['fitness_pushup','俯卧撑','推'],['fitness_split_squat','分腿蹲','下肢']].map(([id,label,group])=>({id,label,group}));
test('unified catalogue includes eight actual fitness analyses and retains all 185 cards',()=>{
 const c=read(),g=gym(),before=JSON.stringify({c,g}),all=L.filtered(c,'all','all','',g);
 assert.equal(all.length,193);assert.equal(L.filtered(c,'fitness','all','',g).length,8);
 assert.deepEqual(all.slice(0,8).map(a=>a.id),g.map(a=>a.id));
 assert.equal(L.filtered(c,'assessment','all','',g).length,63);assert.equal(L.filtered(c,'training','all','',g).length,122);
 assert.equal(new Set(all.map(a=>a.id)).size,193);assert.equal(JSON.stringify({c,g}),before);
});
test('common fitness aliases and barbell back-squat wording are searchable',()=>{
 const c=read(),g=gym();
 for(const [q,id] of [['杠铃深蹲','fitness_squat'],['背蹲','fitness_squat'],['杠铃 硬拉','fitness_deadlift'],['杠铃卧推','fitness_bench_press'],['杠铃划船','fitness_row'],['肩推','fitness_overhead_press'],['二头肌弯举','fitness_curl'],['push up','fitness_pushup'],['分腿深蹲','fitness_split_squat'],['BENCH PRESS','fitness_bench_press']])assert(L.filtered(c,'all','all',q,g).some(a=>a.id===id),q);
 assert(L.filtered(c,'training','all','杠铃深蹲',g).some(a=>a.id==='T-LOW-020'));
 assert(L.filtered(c,'fitness','hip','硬拉',g).every(a=>a.category==='hip'));
 assert.equal(L.filtered(c,'assessment','all','杠铃卧推',g).length,0);
});
test('only available, known analyses appear, with no duplicate or guessed contracts',()=>{
 const c=read(),g=gym();assert.equal(L.fitnessEntries(c,[]).length,0);
 assert.equal(L.fitnessEntries(c,[...g,g[0],{id:'fitness_unknown',label:'未知动作'}]).length,8);
 assert.equal(L.fitnessEntries(c,g.map(a=>({...a,available:false}))).length,0);
 assert.equal(L.fitnessTarget('T-LOW-020',g),'fitness_squat');assert.equal(L.fitnessTarget('T-LOW-060',g),'fitness_deadlift');
 for(const id of ['T-LOW-015','T-AXU-027','E-LOW-023','T-AXU-059'])assert.equal(L.fitnessTarget(id,g),null);
 assert.equal(L.fitnessTarget('T-LOW-020',[]),null);assert.equal(L.fitnessTarget('T-LOW-020',[{id:'fitness_squat',available:false}]),null);
 for(const entry of L.fitnessEntries(c,g)){assert(!('start_angle'in entry));assert(!('source_dose'in entry));if(entry.overview)assert(c.images[entry.overview]);}
});
