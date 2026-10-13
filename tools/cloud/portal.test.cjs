'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../../cloud_service/static/portal.js'),'utf8'),context={};
vm.runInNewContext(source.slice(source.indexOf('  const escape ='),source.indexOf('  async function api'))+'globalThis.renderResult=resultDetails;',context);
test('cloud presentation does not turn unnamed desktop metadata into angles',()=>{
 const html=context.renderResult({schema:'ankang-result-1',result:{summary:{completed:0,valid_ratio:0,metrics:{duration:{value:314.55},knee:{label:'膝关节二维夹角',max:null},hip:{label:'髋部二维夹角',max:179.54,unit:'deg'}}}}});
 const visible=html.split('<details>')[0];assert(visible.includes('髋部二维夹角最大值'));assert(visible.includes('179.54 °'));
 assert(!visible.includes('314.55'));assert(!visible.includes('膝关节二维夹角'));assert(visible.includes('0 次'));assert(visible.includes('0 %'));
});
test('record source and named metric labels remain escaped',()=>{
 const html=context.renderResult({schema:'ankang-result-1',source:'<img src=x>',result:{summary:{metrics:[{label:'<script>',value:3,unit:'<b>'}]}}});
 assert(!html.includes('<script>'));assert(!html.includes('<img src=x>'));assert(html.includes('&lt;script&gt;'));
 assert.equal(context.renderResult({schema:'older-payload'}),'');
});
test('acceptance dossier is labeled, read-only and escapes every field',()=>{
 const payload={schema:'ankang-sync-acceptance-1',source:'SYNC_ACCEPTANCE',synthetic:true,read_only:true,clinical_use:false,execution_enabled:false,
  sections:[{key:'profile',title:'<script>身体档案',summary:'<img src=x>',rows:[{label:'<b>姓名',value:'<svg onload=bad>'}]}]};
 const html=context.renderResult(payload);
 assert(html.includes('不是实测结果或医嘱'));assert(html.includes('不启用服药提醒和自动训练'));
 assert(html.includes('&lt;script&gt;'));assert(html.includes('&lt;svg onload=bad&gt;'));
 assert(!html.includes('<script>'));assert(!html.includes('<img src=x>'));assert(!html.includes('<svg'));
 for(const flag of ['synthetic','read_only','clinical_use','execution_enabled']){
  const invalid={...payload,[flag]:!payload[flag]};const view=context.renderResult(invalid);
  assert(view.includes('档案来源需核对'));assert(!view.includes('身体档案'));
 }
});
