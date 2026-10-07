const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const E=require('../web/engine.js');
const catalog=JSON.parse(fs.readFileSync(path.join(__dirname,'../build/assets/catalog.json'),'utf8'));
const spec=id=>catalog.rehab.find(x=>x.id===id)||catalog.fitness.find(x=>x.id===id);
function run(engine,values){for(let i=0;i<values.length;i++)engine.consume(i*.12,values[i]);return engine.report();}
test('all 53 existing rehab and 8 fitness contracts included, not hand-maintained',()=>{assert.equal(catalog.rehab.length,53);assert.equal(catalog.fitness.length,8);assert.equal(catalog.posture.length,2);});
test('angle lengths, finite geometry and circular delta',()=>{assert.equal(E.angle([0,20],[0,0],[20,0]),90);assert.equal(E.angle([0,0],[0,0],[20,0]),null);assert.equal(E.delta(-179,179),2);});
test('shoulder can be measured without a hip',()=>{const pose=Array.from({length:33},()=>({x:0,y:0,visibility:0}));pose[11]={x:.5,y:.5,visibility:1};pose[13]={x:.8,y:.5,visibility:1};assert.equal(E.measure(spec('shoulder_abduction'),'left',{pose},640,480),90);});
test('neck flexion only needs same-side eye and ear, no shoulder/hip prerequisite',()=>{const pose=Array.from({length:33},()=>({x:0,y:0,visibility:0}));pose[7]={x:.4,y:.4,visibility:1};pose[2]={x:.5,y:.45,visibility:1};assert.ok(E.finite(E.measure(spec('neck_flexion'),'left',{pose},640,480)));});
test('missing joints remain null, never zero-filled',()=>{assert.equal(E.measure(spec('knee_flexion'),'left',{pose:[]},640,480),null);});
test('baseline, full excursion and return produce one genuine cycle',()=>{const e=new E.Engine(spec('shoulder_abduction'),'left',60),r=run(e,[...Array(15).fill(0),10,25,45,65,80,80,60,40,20,0,0,0,0]);assert.equal(r.reps.length,1);assert.equal(r.reps[0].targetMet,true);assert.ok(r.validRatio>.8);});
test('next-action hint switches to return then next outbound',()=>{const e=new E.Engine(spec('shoulder_abduction'),'left');let t=0,o;for(const v of [...Array(15).fill(0),20,40,50,50])o=e.consume(t+=.12,v);assert.equal(o.hint,spec('shoulder_abduction').return_hint);for(const v of [30,0,0,0,0])o=e.consume(t+=.12,v);assert.equal(o.hint,spec('shoulder_abduction').outbound_hint);});
test('shoulder adduction begins raised, counts lowering and return to raised baseline',()=>{const e=new E.Engine(spec('shoulder_adduction'),'left'),r=run(e,[...Array(15).fill(90),70,50,40,40,60,80,90,90,90]);assert.equal(r.baseline,90);assert.equal(r.reps.length,1);});
test('missing interval cannot connect two half-repetitions',()=>{const e=new E.Engine(spec('shoulder_abduction'),'left'),r=run(e,[...Array(15).fill(0),20,50,60,60,null,40,20,0,0,0,0]);assert.equal(r.reps.length,0);assert.ok(r.partial>=1);});
test('negative, duplicate and non-monotonic media time rejected',()=>{const e=new E.Engine(spec('shoulder_abduction'),'left');assert.throws(()=>e.consume(-1,0));e.consume(0,0);assert.throws(()=>e.consume(0,0));});
test('fitness full squat cycle, no fabricated count on cropped points',()=>{const r=run(new E.Engine(spec('fitness_squat'),'left'),[170,170,170,150,120,100,90,90,120,150,170,170,170]);assert.equal(r.reps.length,1);assert.equal(run(new E.Engine(spec('fitness_squat'),'left'),Array(30).fill(null)).reps.length,0);});
test('all eight fitness actions have an excursion/return path (synthetic geometry, not a human test)',()=>{for(const s of catalog.fitness){const sign=s.turn_angle>s.start_angle?1:-1,start=s.start_angle-sign*5,turn=s.turn_angle+sign*5,mid=(start+turn)/2;const r=run(new E.Engine(s,'left'),[...Array(15).fill(start),mid,mid,...Array(5).fill(turn),mid,mid,...Array(10).fill(start)]);assert.equal(r.reps.length,1,s.id);}});
test('automatic plan is tied to valid recent assessment and observed dose',()=>{const now=1000000000,record={id:'a',kind:'assessment',exercise:'shoulder_abduction',side:'left',created:now-1000,report:{contract:E.VERSION,validRatio:.9,reps:[{},{}],min:0,max:130}};const p=E.propose([record],catalog,now);assert.equal(p.items.length,1);assert.equal(p.items[0].reps,2);assert.equal(p.items[0].target,90);assert.equal(p.items[0].assessment,'a');assert.equal(E.propose([record],catalog,now+8*86400000).items.length,0);});
test('latest failed assessment cannot fall back to old successful one',()=>{const now=Date.now(),valid={id:'a',kind:'assessment',exercise:'shoulder_abduction',side:'left',created:now-1000,report:{contract:E.VERSION,validRatio:1,reps:[{}],min:0,max:100}},failed={...valid,id:'b',created:now,report:{...valid.report,reps:[]}};assert.equal(E.propose([valid,failed],catalog,now).items.length,0);});
test('discomfort and profile restrictions prevent automatic continuation',()=>{const now=Date.now(),assessment={id:'a',kind:'assessment',exercise:'shoulder_abduction',side:'left',created:now,report:{contract:E.VERSION,validRatio:1,reps:[{}],min:0,max:100}},training={kind:'training',exercise:assessment.exercise,side:'left',created:now+10,feedback:{pain:1}};assert.equal(E.propose([assessment,training],catalog,now+20).items.length,0);assert.equal(E.propose([assessment],catalog,now,{restrictions:'术后限制'}).items.length,0);});
test('privileged WebView cannot navigate remotely, bypass TLS or access raw files',()=>{const dir=path.join(__dirname,'..'),manifest=fs.readFileSync(path.join(dir,'AndroidManifest.xml'),'utf8'),java=fs.readFileSync(path.join(dir,'src/cn/tele/rehabilitation/offline/MainActivity.java'),'utf8');assert.match(manifest,/allowBackup="false"/);assert.match(java,/setAllowFileAccess\(false\)/);assert.match(java,/handler.cancel\(\)/);assert.doesNotMatch(java,/handler.proceed\(\)/);assert.match(java,/return !trusted\(request.getUrl\(\)\)/);});
test('initial dose leaves capacity in reserve without fabricating completed repetitions',()=>{const now=Date.now(),r={id:'a',kind:'assessment',exercise:'shoulder_abduction',side:'left',created:now,report:{contract:E.VERSION,validRatio:.9,reps:Array(4).fill({}),min:0,max:130}};assert.equal(E.propose([r],catalog,now).items[0].reps,3);assert.equal(r.report.reps.length,4);});
test('every rehabilitation contract has a concrete mobile metric adapter',()=>{
 const pose=Array.from({length:33},()=>({x:.5,y:.5,visibility:1,presence:1}));
 const coordinates={2:[.48,.12],5:[.52,.12],7:[.44,.15],8:[.56,.15],11:[.35,.25],12:[.65,.25],13:[.25,.4],14:[.75,.4],15:[.15,.55],16:[.85,.55],23:[.4,.5],24:[.6,.5],25:[.38,.7],26:[.62,.7],27:[.36,.9],28:[.64,.9],29:[.35,.92],30:[.63,.92],31:[.48,.92],32:[.76,.92]};
 for(const [i,[x,y]]of Object.entries(coordinates))pose[i]={x,y,visibility:1,presence:1};
 const hand=Array.from({length:21},(_,i)=>({x:.15+i*.016,y:.55+(i%4)*.035}));
 for(const s of catalog.rehab)assert.ok(E.finite(E.measure(s,'left',{pose,hand,handedness:{categoryName:'Left',score:.99}},640,480)),s.id);
});
test('every rehab action has a functioning excursion/return state path (synthetic metric test, not human accuracy)',()=>{
 for(const s of catalog.rehab){const baseline=s.directional_calibration?170:s.target_direction==='decrease'?90:0;const sign=s.target_direction==='decrease'?-1:1;const movement=s.directional_calibration?[175,179,-179,-160,-145,-145,-160,179,170,170,170,170]:[baseline+sign*10,baseline+sign*25,baseline+sign*45,baseline+sign*50,baseline+sign*50,baseline+sign*25,baseline,baseline,baseline,baseline];const r=run(new E.Engine(s,'left'),[...Array(15).fill(baseline),...movement]);assert.equal(r.reps.length,1,s.id);}
});
test('online calibration accepts a stable suffix, not an unnecessary moving prefix',()=>{
 const e=new E.Engine(spec('shoulder_abduction'),'left');
 run(e,[45,35,25,10,10,10,10,10,10,10,10]);assert.equal(e.baseline,10);
});
test('offline replay uses a later observed rest reference and preserves original times',()=>{
 const samples=[0,1,3,8,20,40,60,60,40,20,8,2,2,2,2,2,2,2,2,2].map((v,i)=>[i*.12,v]);
 const r=E.analyzeReplay(spec('shoulder_abduction'),'left',samples,50);
 assert.equal(r.reps.length,1);assert.equal(r.reps[0].targetMet,true);assert.equal(r.calibration.method,'observed-stationary-replay');assert.equal(r.frames,samples.length);assert.equal(r.duration,samples.at(-1)[0]);assert.equal(r.baseline,2);
});
test('replay does not manufacture rest reference or connect missing data',()=>{
 const s=spec('shoulder_abduction'),unstable=Array.from({length:15},(_,i)=>[i*.12,i*12]);assert.equal(E.analyzeReplay(s,'left',unstable).baseline,null);
 const values=[...Array(12).fill(0),20,50,50,null,30,0,0,0,0];const r=E.analyzeReplay(s,'left',values.map((v,i)=>[i*.12,v]));assert.equal(r.reps.length,0);
});
