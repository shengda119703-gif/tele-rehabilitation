'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const {ObservationPresenter,POLICY}=require('../static/observation-presenter.js');
const frame=(phase='REST',valid=true,count=6,angle=45)=>({valid,summary:{phase,completed:count,primary_metric:'shoulder',metrics:{shoulder:{value:angle}}},cue:{instruction:'缓慢抬起手臂',status:phase}});
test('six-second budget has a guided exit, not a manufactured READY or count',()=>{
 const changes=[],p=new ObservationPresenter(v=>changes.push(v));p.begin(0);p.receive(frame('WAIT_READY',true,0),500);
 assert.equal(p.view(5999).count,null);const after=p.view(6000);assert.equal(after.mode,'GUIDED');assert.equal(after.voice,false);assert.match(after.cue,/先按示范/);assert.equal(after.count,null);assert.equal(p.phase,'WAIT_READY');assert.equal(p.view(6500).activeNotice,false);assert.equal(changes.length,0);
});
test('both native engine phase schemas require current stable evidence',()=>{
 for(const phase of ['REST','SEATED_READY','outbound','rest']){const p=new ObservationPresenter();p.begin(0);p.receive(frame(phase),0);assert.equal(p.mode,'GUIDED');p.receive(frame(phase),750);p.receive(frame(phase),1500);assert.equal(p.mode,'AUTO_ASSISTED');assert.equal(p.view(1500).voice,true);}
 for(const phase of ['prepare','missing','WAIT_READY','FINISHED','future']){const p=new ObservationPresenter();p.begin(0);p.receive(frame(phase),0);p.receive(frame(phase),1600);assert.equal(p.mode,'GUIDED');assert.equal(p.count,null);}
});
test('short and long gaps never clear confirmed preview count or add unobserved counts',()=>{
 const changes=[],p=new ObservationPresenter(v=>changes.push(v));p.begin(0);for(const t of [0,750,1500])p.receive(frame(),t);
 p.receive(frame('missing',false,99),1750);assert.equal(p.view(2000).count,6);assert.equal(p.view(2000).angle,null);assert.equal(p.view(2000).voice,false);assert.equal(p.view(3000).state,'WEAK');
 const long=p.view(6500);assert.equal(long.mode,'GUIDED');assert.equal(long.state,'LOST');assert.equal(long.count,6);assert.equal(long.activeNotice,true);assert.equal(p.view(6750).activeNotice,false);assert.equal(changes.at(-1).reason,'visual_gap');
});
test('one late valid frame cannot restore automatic assistance across a timing gap',()=>{
 const p=new ObservationPresenter();p.begin(0);p.receive(frame(),0);p.receive(frame(),2000);assert.equal(p.mode,'GUIDED');p.receive(frame(),2750);p.receive(frame(),3500);assert.equal(p.mode,'AUTO_ASSISTED');
 p.view(9000);p.receive(frame('REST',true,7),10000);assert.equal(p.mode,'GUIDED');p.receive(frame('REST',true,7),10750);p.receive(frame('REST',true,7),11500);assert.equal(p.mode,'AUTO_ASSISTED');assert.equal(p.count,7);
});
test('missing/null/NaN values cannot produce a correction, and observed zero is valid',()=>{
 for(const angle of [null,undefined,NaN,Infinity]){const p=new ObservationPresenter();p.begin(0);const missing=frame();missing.summary.metrics.shoulder.value=angle;p.receive(missing,0);p.receive(missing,1500);assert.equal(p.view(1500).voice,false);assert.equal(p.view(1500).angle,null);}
 const p=new ObservationPresenter();p.begin(0);p.receive(frame('REST',true,0,0),0);p.receive(frame('REST',true,0,0),750);p.receive(frame('REST',true,0,0),1500);assert.equal(p.count,0);assert.equal(p.angle,0);
});
test('stop and a new preview boundary discard obsolete readiness, not saved practice facts',()=>{
 const p=new ObservationPresenter();p.begin(0);for(const t of [0,750,1500])p.receive(frame(),t);p.disable(1700);assert.equal(p.view(2000).voice,false);assert.equal(p.view(2000).count,6);assert.equal(p.receive(frame('REST',true,100),2200),undefined);p.begin(3000);assert.equal(p.count,null);assert.equal(p.mode,'GUIDED');assert.equal(POLICY.readySoftWaitMs,6000);
});
test('a lower old snapshot in the same preview cannot clear a known count',()=>{
 const p=new ObservationPresenter();p.begin(0);for(const t of [0,750,1500])p.receive(frame(),t);p.receive(frame('REST',true,0),1700);assert.equal(p.count,6);
});
