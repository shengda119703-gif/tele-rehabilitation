const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const E=require('../web/engine.js'),B=require('../web/barbell.js');
const c={LocalEngine:E,PhoneStore:{files:{}},fetch:async()=>{},structuredClone,setTimeout,clearTimeout};vm.createContext(c);vm.runInContext(fs.readFileSync('android_offline/web/motion.js','utf8'),c);
const catalog=JSON.parse(fs.readFileSync('android_offline/build/assets/catalog.json','utf8'));
test('cropped knee never becomes an inferred measurement; observed hip is explicitly labelled',()=>{
 const s=catalog.fitness.find(s=>s.id==='fitness_squat'),values=[160,160,160,140,120,100,90,90,120,150,160,160,160];
 const frames=values.map((v,i)=>({t:i*.12,metrics:{knee:null,hip:v,torso:10},points:{}}));
 const r=c.PhoneMotion.fitnessResult(s,'left',frames,[640,480]);assert.equal(r.summary.completed,1);assert.equal(r.summary.metrics.knee.min,null);assert.equal(r.conditions.metric_fallback,'observed-hip-no-knee');assert.match(r.summary.primary_metric_label,/髋部/);assert.equal(r.repetitions.length,1);
 frames.forEach(f=>f.metrics.hip=null);assert.equal(c.PhoneMotion.fitnessResult(s,'left',frames,[640,480]).summary.completed,0);
});
test('real trajectory retains XY and normalized marker, computes bounded upward phases',()=>{
 const samples=Array.from({length:601},(_,i)=>{const t=i/60;let y=0;for(const [start,duration]of [[1,1],[4,1.25],[7,1.5]])if(t>=start&&t<=start+2*duration){y=.25*(1-Math.cos(Math.PI*(t-start)/duration));break;}return[t,y,1,0,[.5,.7-y]];});
 const report=c.PhoneMotion.barReport(B.summarize(samples,40),{mass_kg:40,length_m:.5});assert.equal(report.summary.bounded_segments,3);assert(report.summary.peak_velocity_m_s>0);assert(report.summary.peak_power_w>0);assert(report.series.some(r=>r.point&&r.height_m>.1));assert.equal(report.synthetic,false);
});
test('existing fitness example remains explicitly synthetic and outside personal jobs',()=>{const demo=JSON.parse(fs.readFileSync('android_offline/build/assets/fitness-demo.json'));assert.equal(demo.synthetic,true);assert.equal(demo.summary.bounded_segments,3);});
