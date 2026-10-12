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
