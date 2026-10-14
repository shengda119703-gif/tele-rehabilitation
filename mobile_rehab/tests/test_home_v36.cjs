// Read-only projection tests. Fixtures are synthetic and never open a product database.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const H=require('../static/home-v36.js');
const today='2026-10-11';
const scope=source=>({participant_id:'TEST-owner',source_kind:source,usage_context:'SELF_USE'});
function fixture(source='REPLAY_FILE') {
  return {profile:{ownerId:'TEST-owner',profile:{name:'TEST 档案'}},dailyProduct:{schedules:[]},rehabilitation_ui:{
    'rehab.get_training_plan':{scope:scope(source),records:[{id:'TEST-plan',revision:3,next_available:true,items:[{key:'a',exercise_id:'shoulder_flexion',exercise_label:'肩前屈',side:'left',settings:{target_reps:5,target_sets:2}},{key:'b'}],progress:{next_key:'a',completed:0,total:2,blocked:''}}]},
    'rehab.get_training_history':{scope:scope(source),records:[]}
  }};
}
const project=(s,source='REPLAY_FILE',day=today,connection='ready')=>H.model(s,source,day,today,connection);
test('natural week has exactly seven local dates across month, year and leap-day boundaries',()=>{
  assert.deepEqual(H.week(today),['2026-10-05','2026-10-06','2026-10-07','2026-10-08','2026-10-09','2026-10-10','2026-10-11']);
  assert.deepEqual(H.week('2027-01-01'),['2026-12-28','2026-12-29','2026-12-30','2026-12-31','2027-01-01','2027-01-02','2027-01-03']);
  assert.equal(H.week('2024-02-29')[3],'2024-02-29');assert.deepEqual(H.week('2026-02-29'),[]);assert.equal(H.dateOf('2026-13-01'),null);
});
test('only saved terminal training records count; one local day counts once',()=>{
  const s=fixture(),r=s.rehabilitation_ui['rehab.get_training_history'].records;
  for(const [id,status,end_utc] of [['a','FINISHED','2026-10-11T08:00:00+08:00'],['b','COMPLETED','2026-10-11T09:00:00+08:00'],['c','INTERRUPTED','2026-10-10T08:00:00+08:00'],['d','FAILED','2026-10-09T08:00:00+08:00'],['e','UPLOADING','2026-10-08T08:00:00+08:00'],['f','FINISHED',null],['g','FINISHED','invalid'],['h','FINISHED','2026-10-01T08:00:00+08:00']])r.push({id,status,end_utc});
  assert.equal(project(s).history.length,4);assert.deepEqual(project(s).trained,['2026-10-10','2026-10-11']);
  const at=new Date('2026-10-10T18:00:00Z');r.push({id:'local',status:'FINISHED',end_utc:at.toISOString()});
  assert.ok(project(s).trained.includes(H.localDay(at)));
});
test('current participant, source and usage scope never mix',()=>{
  for(const mismatch of [{participant_id:'OTHER'},{source_kind:'LIVE_CAMERA'},{usage_context:'FAMILY_VIEW'}]) {
    const s=fixture();Object.assign(s.rehabilitation_ui['rehab.get_training_plan'].scope,mismatch);Object.assign(s.rehabilitation_ui['rehab.get_training_history'].scope,mismatch);
    s.rehabilitation_ui['rehab.get_training_history'].records=[{id:'x',status:'FINISHED',end_utc:today+'T10:00:00+08:00'}];
    assert.equal(project(s).plan,undefined);assert.equal(project(s).trained.length,0);
  }
});
test('next item and dose use server values; computer live mode remains read-only on phone',()=>{
  const s=fixture(),m=project(s);assert.equal(m.task.title,'肩前屈');assert.match(m.task.meta,/本人左侧 · 5次×2组/);assert.equal(m.task.action,'train');assert.equal(m.task.index,1);
  assert.equal(project(fixture('LIVE_CAMERA'),'LIVE_CAMERA').task.action,'plan');
  assert.equal(project(fixture('LIVE_CAMERA'),'LIVE_CAMERA').task.button,'查看电脑计划');
  assert.equal(project({}).task.action,'assess');assert.equal(project({},'LIVE_CAMERA').task.action,'rehab');
});
test('blocked feedback, unavailable next item and completed plan never expose a start button',()=>{
  const s=fixture(),p=s.rehabilitation_ui['rehab.get_training_plan'].records[0];p.progress.blocked='疼痛与疲劳反馈待补全';
  assert.equal(project(s).task.action,'history');assert.equal(project(s).task.notice,p.progress.blocked);
  p.progress.blocked='';p.next_available=false;p.availability_reason='测量条件待确认';assert.equal(project(s).task.action,'plan');assert.equal(project(s).task.notice,p.availability_reason);
  p.progress.next_key=null;assert.equal(project(s).task.action,'history');assert.equal(project(s).task.index,null);
});
test('date-specific schedules exclude only the exact main schedule, not repeated plan appointments',()=>{
  const s=fixture();s.dailyProduct.schedules=[{id:'main',date:today,time:'09:00',kind:'training',planId:'TEST-plan',revision:3,name:'训练'},{id:'later',date:today,time:'17:00',kind:'training',planId:'TEST-plan',revision:3,name:'训练'},{id:'other-day',date:'2026-10-12',time:'09:00',kind:'training',name:'其他日'}];
  const m=project(s),d=[{time:'08:00',med:{name:'药物'},status:'taken'},{time:'19:30',med:{name:'药物'},status:'unrecorded'}];
  assert.equal(m.mainSchedule.id,'main');assert.match(m.task.meta,/09:00/);
  const rows=H.arrangements(m,d);assert.deepEqual(rows.map(r=>r.time),['08:00','17:00','19:30']);assert.equal(rows[0].status,'已服用');assert.equal(rows[1].id,'later');assert.equal(rows[2].status,'待记录');
  assert.equal(project(s,'REPLAY_FILE','2026-10-12').task.action,'rehab');
});
test('assessment schedule uses the existing assessment entry',()=>{
  const s=fixture();s.dailyProduct.schedules=[{id:'assessment',kind:'assessment',date:today,time:'10:00',name:'肩部评估'}];
  const m=project(s);assert.equal(m.task.action,'assess');assert.equal(m.task.title,'肩部评估');assert.equal(m.task.index,null);
});
test('loading/offline are unknown, not empty successes; loading cannot be clicked',()=>{
  for(const state of ['loading','offline']) {const m=project({},'REPLAY_FILE',today,state),html=H.markup(m,[],today);assert.match(html,/暂未读取/);assert.match(html,/尚未读取/);assert.doesNotMatch(html,/0 天有记录|当天暂无其他安排|<span>0 项<\/span>/);assert.equal(m.task.action,'retry');}
  assert.match(H.hero(project({},'REPLAY_FILE',today,'loading')),/id="home-primary" disabled/);
  assert.match(H.markup(project({}),[],today),/当天暂无其他安排/);
});
test('independent hero layers and dynamic copy are escaped; projection does not mutate input',()=>{
  const s=fixture();s.profile.profile.name='<img src=x onerror=x>';s.rehabilitation_ui['rehab.get_training_plan'].records[0].items[0].exercise_label='<script>x</script>';
  const before=JSON.stringify(s),m=project(s),html=H.markup(m,[],today);assert.equal(JSON.stringify(s),before);
  for(const token of ['class="home-streaks"','class="home-athlete"','id="home-primary"','&lt;script&gt;','&lt;img'])assert.ok(html.includes(token),token);
  assert.doesNotMatch(html,/data:image|hero_design_reference|<script>/);assert.equal((html.match(/class="home-mark"/g)||[]).length,7);
});
