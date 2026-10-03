const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const script=fs.readFileSync(path.join(__dirname,'../static/extensions.js'),'utf8');
function sandbox(){
 const c={document:{addEventListener(){}},window:{addEventListener(){}},
  esc:s=>String(s??'').replace(/[<>&]/g,c=>({'<':'&lt;','>':'&gt;','&':'&amp;'}[c])),
  number:(v,u='')=>Number.isFinite(v)?v+u:'未测得',label:x=>x,sideLabel:()=> '左侧',dateLabel:()=> '测试日期'};
 vm.createContext(c);vm.runInContext(script,c);return c;
}
test('posture does not render missing numbers as zero or a diagnosis',()=>{
 const c=sandbox();const html=c.postureMetrics({metrics:[{label:'髋线',valid:false,value:null,reason:'保持站姿',note:'test'}]});
 assert.match(html,/未测得/);assert.doesNotMatch(html,/>0</);assert.doesNotMatch(html,/诊断正常/);
});
test('shared summary uses human label and escapes report fields',()=>{
 const html=sandbox().reportRow({exercise:'id',label:'<肩外展>',side:'left',mode:'assessment',summary:{completed:3,metrics:{angle:{value:20}},motion_range:{range_deg:40}}});
 assert.match(html,/&lt;肩外展&gt;/);assert.match(html,/40°/);
});
test('live camera is explicit, stoppable and never records audio',()=>{
 assert.match(script,/getUserMedia\(\{audio:false/);assert.match(script,/getTracks\(\)\.forEach\(t=>t.stop\(\)\)/);
 assert.match(script,/document.hidden\)stopLive/);assert.match(script,/isSecureContext/);
 assert.match(script,/同意将实时画面传到电脑分析，不保存画面/);
});
test('share identity not verified and views do not auto change plans',()=>{
 assert.match(script,/身份未核验/);assert.match(script,/留言不会自动修改训练计划/);
 assert.match(script,/撤销分享/);assert.match(script,/当前档案不会合并或删除/);
});
test('completed plan can create next round and upload freezes select fields',()=>{
 const app=fs.readFileSync(path.join(__dirname,'../static/app.js'),'utf8');
 assert.match(app,/!record \|\| progress.blocked \|\| !progress.next_key/);
 assert.match(app,/#app select/);assert.match(app,/DOMContentLoaded',init/);
});
