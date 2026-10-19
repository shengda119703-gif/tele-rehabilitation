'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const D=require('../../mobile_rehab/static/motion-review-data.js');
const job=(result,extra={})=>({id:'qa-only',exercise:'shoulder_abduction',side:'left',mode:'assessment',result,...extra});
test('annotation collector keeps only visible normalized points, bounded sample rate and original times',()=>{
 const c=new D.TraceCollector();for(let i=0;i<10000;i++)c.add(i*.01,{left_shoulder:[320,120],left_knee:[NaN,2],nose:[1,1]},640,480);
 const trace=c.export();assert(trace.rows.length<=626);assert.equal(trace.rows[0].points.left_shoulder[0],.5);assert.equal(trace.rows[0].points.nose,undefined);assert.equal(trace.rows[0].points.left_knee,undefined);assert(D.validateTrace(trace));
 c.add(-1,{},640,480);c.add(1,{},640,480);assert.equal(c.rows.length,trace.rows.length);
});
test('invalid or foreign trace fields and duplicate times cannot enter review',()=>{
 const trace={version:D.VERSION,size:[640,480],rows:[{t:0,points:{left_hip:[.5,.6]}}]};assert(D.validateTrace(trace));
 for(const change of [t=>t.size=[0,480],t=>t.rows.push(t.rows[0]),t=>t.rows[0].points.left_hip=[2,.5],t=>t.rows[0].points.secret=[.5,.5],t=>t.rows[0].t=122]){const t=structuredClone(trace);change(t);assert.equal(D.validateTrace(t),null);}
});
test('hand annotation follows the same handedness confidence as the existing measurement',()=>{
 const raw={hand:[{x:.5,y:.2},{x:2,y:.3}],handedness:{categoryName:'Left',score:.8}},p=D.handPoints(raw,640,480,'left');assert.deepEqual(p,{hand_0:[320,96]});assert.deepEqual(D.handPoints(raw,640,480,'right'),{});raw.handedness.score=.2;assert.deepEqual(D.handPoints(raw,640,480,'left'),{});
});
test('saved assessment series and range drive report, input records are never rewritten',()=>{
 const j=job({summary:{motion_range:{min_deg:5,max_deg:90,range_deg:85}},local_report:{series:[[0,5],[.2,90],[.4,null],[1,8]],reps:[{outbound:1,return:2}]}}),before=JSON.stringify(j),d=D.build(j,{label:'肩外展',view:'frontal'});
 assert.equal(d.metrics.find(m=>m.key==='angle').value,90);assert.equal(d.metrics.find(m=>m.key==='range').value,85);assert.equal(d.metrics.find(m=>m.key==='tempo').value,2);assert.equal(JSON.stringify(j),before);assert(!d.metrics.some(m=>/count|completed|reps/.test(m.key)));
 assert.equal(D.nearest(d.samples,.8),null);assert.equal(d.samples.find(s=>s.t===.4).values.angle,null);
});
test('old summary without video or point cache is usable without invented timeline or power',()=>{
 const d=D.build(job({summary:{motion_range:{max_deg:102,range_deg:92}}}));assert.equal(d.metrics.find(m=>m.key==='angle').value,102);assert.equal(d.samples.length,0);assert.equal(d.hasTrace,false);assert(!d.metrics.some(m=>['power','speed','symmetry'].includes(m.key)));
});
test('whole-clip angle keeps the original report peak, not the decimated replay maximum',()=>{
 const d=D.build(job({summary:{motion_range:{max_deg:171.37,range_deg:170.6}},local_report:{series:[[0,2],[.2,171.14]]}}),{joint:'shoulder'});const angle=d.metrics.find(m=>m.key==='angle');assert.equal(angle.value,171.37);assert.equal(angle.time,null);assert.equal(angle.label,'肩部活动角度');assert.equal(d.samples[1].values.angle,171.14);
});
test('trace can add bilateral geometry but does not claim actual force or complete an action',()=>{
 const c=new D.TraceCollector();c.add(0,{left_shoulder:[200,100],right_shoulder:[400,100],left_hip:[240,280],right_hip:[360,280],left_knee:[235,380],right_knee:[365,380],left_ankle:[230,470],right_ankle:[370,470]},640,480);
 const j=job({local_report:{series:[[0,30]]}},{mode:'fitness',exercise:'fitness_squat'}),before=JSON.stringify(j),d=D.build(j,{view:'frontal'},c.export());assert(d.metrics.some(m=>m.key==='symmetry'));assert.equal(d.metrics.find(m=>m.key==='shoulder').value,0);assert(!d.metrics.some(m=>/force|power/.test(m.key)));assert.equal(JSON.stringify(j),before);
});
test('power uses actual saved mass-calibrated series; no sample mass or standard body parameters',()=>{
 const j=job({series:[{t:0,angle:80},{t:.2,angle:100}],barbell:{measurement:{target_kind:'plate'},calibration:{mass_kg:60},series:[{t:0,velocity_m_s:-1,power_w:-800},{t:.2,velocity_m_s:.4,power_w:300}]}},{mode:'fitness',exercise:'fitness_deadlift'}),d=D.build(j,{view:'sagittal'});
 assert.equal(d.metrics.find(m=>m.key==='power').value,300);assert.equal(d.metrics.find(m=>m.key==='speed').value,.4);assert.equal(d.parameters.mass_kg,60);
 delete j.result.barbell.series[0].power_w;delete j.result.barbell.series[1].power_w;assert(!D.build(j).metrics.some(m=>m.key==='power'));
});
test('posture legacy metrics retain actual values and units',()=>{
 const d=D.build(job({summary:{metrics:[{key:'head_offset',label:'耳肩水平偏移',unit:'%',value:14,valid:true},{key:'shoulder_level',value:10,valid:false}]}},{mode:'posture'}));assert.equal(d.metrics.length,1);assert.equal(d.metrics[0].value,14);assert.equal(d.metrics[0].unit,'%');
});
test('packaged capture loads shared viewer after original workflows, without adding source video',()=>{
 const html=fs.readFileSync('mobile_rehab/static/index.html','utf8');assert(html.indexOf('/static/motion-review.js')>html.indexOf('/static/formal-measurement.js'));assert(html.includes('/static/motion-review-data.js'));assert(!html.includes('14929'));
 const source=fs.readFileSync('mobile_rehab/static/motion-review.js','utf8');assert(source.includes('current?.destroy()'));assert(source.includes('state.uploadOwnerGeneration'));assert(!/fetch\([^)]*https?:/.test(source));
});
