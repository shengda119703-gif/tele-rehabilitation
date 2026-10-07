const {test}=require('node:test');
const assert=require('node:assert/strict');
const {readFileSync}=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const staticDir=path.resolve(__dirname,'../static');
function context(){
  const elements=new Map();
  const app={innerHTML:''};
  const sandbox={app,esc:s=>String(s??''),number:v=>Number.isFinite(v)?String(v):'未测得',
    sideLabel:()=> '左侧',dateLabel:()=> '测试日期',
    $:s=>{if(!elements.has(s))elements.set(s,{});return elements.get(s);}};
  vm.createContext(sandbox);
  for(const file of ['barbell.js','fitness.js'])vm.runInContext(readFileSync(path.join(staticDir,file),'utf8'),sandbox);
  return sandbox;
}
function bar(synthetic){return {synthetic,summary:{bounded_segments:0,tracked_ratio:0},
  calibration:{length_m:.5,mass_kg:40},series:[],lifts:[],assumptions:['测试测量条件'],version:'test-only'};}
test('demo remains clearly labelled and estimates are not renamed as direct measurements',()=>{
  const html=context().barReport(bar(true));
  assert.match(html,/示例数据/);
  assert.match(html,/不计入训练记录/);
  assert.match(html,/峰值外力（估算）/);
  assert.match(html,/峰值功率（估算）/);
  assert.doesNotMatch(html,/工程估算|不填造假|完整边界|SYNTHETIC/);
});
test('empty bar report does not invent a peak and assumptions stay in details',()=>{
  const html=context().barReport(bar(false));
  assert.match(html,/暂无数据/);
  assert.match(html,/未识别到完整上升/);
  assert.match(html,/<details><summary>更多数据与测量说明<\/summary>[\s\S]*测试测量条件[\s\S]*<\/details>/);
});
test('fitness report keeps results prominent and puts measurement explanation in closed details',()=>{
  const c=context();
  c.renderFitnessReport({side:'left',video_available:false,result:{
    summary:{completed:0,partial:0,valid_ratio:0,mean_cycle_s:null,metrics:{},primary_metric_label:'膝角度'},
    spec:{label:'深蹲',note:'测试测量范围',start_angle:155,turn_angle:105},series:[],repetitions:[],limitations:['测试限制']}});
  assert.match(c.app.innerHTML,/深蹲 · 训练报告/);
  assert.match(c.app.innerHTML,/未识别到完整动作/);
  assert.match(c.app.innerHTML,/<details><summary>测量说明<\/summary>[\s\S]*测试限制/);
  assert.doesNotMatch(c.app.innerHTML,/<details open|不填入猜测值|可用观察时长占比/);
});
test('upload consent, calibration acknowledgement and safety information remain available',()=>{
  const app=readFileSync(path.join(staticDir,'app.js'),'utf8');
  const barbell=readFileSync(path.join(staticDir,'barbell.js'),'utf8');
  assert.match(app,/id="consent"/);
  assert.match(app,/同意将视频上传到电脑分析并保存/);
  assert.match(barbell,/id="bar-confirm"/);
  assert.match(barbell,/<details><summary>拍摄要求<\/summary>/);
  assert.match(barbell,/绳索、弹力带或他人助力/);
});
