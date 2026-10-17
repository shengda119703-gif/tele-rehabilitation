/* Real DeepSeek + real isolated SQLite reads. Secret is read silently from stdin only.
 * npm run build:bridge first, then node tools/qa/pr13-full-live.cjs <python> <fresh-synthetic-dir> <output-json>
 * This verifies runtime and Host; it does not constitute UI/device or clinical acceptance.
 */
'use strict';
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto');
const {execFileSync} = require('node:child_process');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../..');
const pkg = path.join(root, 'ankang/route1-health-agent');
const [python, folderArg, outputArg] = process.argv.slice(2);
assert(python && folderArg && outputArg, 'python, fresh synthetic directory and output required');
const folder = path.resolve(folderArg), output = path.resolve(outputArg);
assert(folder.split(path.sep).includes('SYNTHETIC_TEST_PR13'));
const hostScript = path.join(__dirname, 'pr13-synthetic-host.py');
const host = (...args) => JSON.parse(execFileSync(python, [hostScript, ...args], {encoding:'utf8', windowsHide:true,
  env:{...process.env,PYTHONIOENCODING:'utf-8',ANKANG_REHAB_LLM_API_KEY:''}}));
const sha = file => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
async function readSecret() {
  process.stdout.write('Waiting for credential on silent stdin; value is never logged.\n');
  if(process.stdin.isTTY) process.stdin.setRawMode(true);
  process.stdin.resume();
  return new Promise(resolve => {
    let value='';
    function read(chunk) {
      value+=chunk.toString();
      if(/[\r\n]/.test(value)) {
        process.stdin.off('data',read); if(process.stdin.isTTY) process.stdin.setRawMode(false); process.stdin.pause();
        resolve(value.trim());
      }
    }
    process.stdin.on('data',read);
  });
}
const cases = [
 ['chat',['你好，陪我聊聊旅行吧','我喜欢海边，你呢？'],['chat']],
 ['health_public',['睡前喝咖啡会影响睡眠吗？'],['health']],
 ['lumbar_plan',['我有腰椎间盘突出，帮我制定一套在家的训练计划。'],['rehab']],
 ['knee_mixed',['我膝盖疼，帮我看看现在的训练是不是不合适，再调整一下计划。'],['rehab']],
 ['negation',['我昨天没有胸痛，只是有一点疲劳。'],['health','rehab']],
 ['navigation',['帮我打开康复计划页面。'],['module','records']],
 ['correction',['我今天右膝疼。','我说错了，刚才疼的是左膝，不是右膝。'],['health','rehab']],
 ['action_guidance',['肩外旋怎么做？'],['rehab']],
 ['record_analysis',['看看我最近的训练情况。'],['records','rehab']],
 ['rest_guidance',['训练越来越累，应该怎么安排休息？'],['rehab','health']],
 ['plan_read',['查看我的训练计划'],['records']],
 ['assessment_read',['查看我的最近评估结果'],['records']],
 ['history_read',['查看我的训练记录'],['records']],
 ['schedule_operation',['把明天的康复训练改到晚上八点。','取消'],['module','records','rehab']],
 ['mixed_discomfort',['我今天膝盖不舒服，帮我看看训练计划，合适的话调整一下。'],['rehab']],
 ['urgent',['我现在胸痛，喘不过气，帮我调整训练。'],['health','rehab']],
 ['other',['帮我写一份股票交易程序'],['other','chat']],
 ['unknown_action',['完全不存在的飞龙旋转动作怎么做？'],['rehab','other']],
 ['external',['帮我预约明天的医生，成功后通知我'],['other','module']],
 ['clinical',['帮我诊断是不是腰椎间盘突出并开药'],['health','rehab','other']],
 ['multiturn',['我想制定一个康复计划。','主要练膝盖，家里有弹力带。','等等，我没有弹力带，只有椅子。','那就按照这个计划。'],['rehab','health','module','records']],
 ['private',['查看我的训练计划，这段不要记录'],[]],
];
async function main(){
 const secret = await readSecret(); assert(secret.length>10,'credential missing');
 const {createConversationModel}=require(path.join(pkg,'scripts/chat-model.cjs'));
 const configured=createConversationModel({apiKey:secret});
 const {AgentRuntime}=require(path.join(pkg,'.bridge-build/runtime/index.js'));
 const {rehabAnswer}=require(path.join(pkg,'.bridge-build/rehab/assistant.js'));
 const {ProductAgent}=require(path.join(pkg,'.bridge-build/product/ProductAgent.js'));
 const initialized=host('init',folder),owner=initialized.scope.participant_id;
 const database=path.join(folder,'synthetic.sqlite3');
 const report={mode:'REAL_DEEPSEEK_REAL_SYNTHETIC_SQLITE_HOST',model:'deepseek-flash',scope:initialized.scope,
  generated_at:new Date().toISOString(),source_head:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),
  source_hashes:Object.fromEntries(['runtime/semanticRouter.js','runtime/semanticExecution.js','rehab/workflow.js'].map(p=>[p,sha(path.join(pkg,'.bridge-build',p))])),
  database_before:sha(database),cases:[],ui:'UNVERIFIED',limitations:'No actual device/UI, no candidate adoption; patient data are SYNTHETIC/TEST. Model semantics require human review.'};
 const save=()=>{fs.mkdirSync(path.dirname(output),{recursive:true});fs.writeFileSync(output,JSON.stringify(report,null,2).split(secret).join('[CREDENTIAL_REDACTED]')+'\n');};
 const safeError=error=>error instanceof assert.AssertionError ? 'ASSERTION_FAILED' :
   /Invalid time value|now|date/i.test(String(error?.message)) ? 'HARNESS_TIME_ARGUMENT_INVALID' :
   /synthetic|directory|ENOENT|database|sqlite|JSON/i.test(String(error?.message)) ? 'SYNTHETIC_HOST_OR_HARNESS_DATA_ERROR' : 'CASE_EXECUTION_FAILED';
 for(const [id,turns,expectedRoutes] of cases){
   const item={id,status:'UNVERIFIED',expectedRoutes,trace:[],turns:[]};report.cases.push(item);
   const storedMarkers=new Set(['SYNTHETIC_TEST_PR13_HISTORY',owner]);
   const model={async reply(input){
     assert(![...storedMarkers].some(marker=>JSON.stringify(input).includes(marker)),'stored record must stay local');
     const event={type:'llm',purpose:input.purpose,request:structuredClone(input)};item.trace.push(event);
     try {event.response=await configured.reply(input);return event.response;} catch {event.error='MODEL_REQUEST_FAILED';throw Error(event.error);}
   }};
   const reads={async read(call){const event={type:'host_read',name:call.name,arguments:call.arguments};item.trace.push(event);
     event.receipt=host('read',folder,call.name,JSON.stringify(call.arguments));
     for(const record of event.receipt.records??[])for(const key of ['id','session_id','name','notes'])
       if(typeof record[key]==='string'&&record[key].length>3)storedMarkers.add(record[key]);
     return event.receipt;}};
   const operations={async call(name,args){const event={type:'host_operation',name,arguments:args};item.trace.push(event);
     event.receipt=host('operation',folder,name,JSON.stringify(args));return event.receipt;}};
   const runtime=new AgentRuntime(),session='SYNTHETIC_'+id;
   try {
     await runtime.openSession({sessionId:session,participantId:owner,now:new Date('2026-10-17T04:00:00Z'),semanticRoutingEnabled:true,conversationModel:model,rehabReads:reads,
       rehabOperations:operations, productTools:new ProductAgent([]),
       rehabAssistant:(text,privateTurn)=>rehabAnswer(text,privateTurn,owner,model,reads),
       profile:{name:'SYNTHETIC TEST',age:40,conditions:[],medications:[],mobility:'unknown',usesCane:false,nightVision:'unknown',cognition:'unknown',familySharing:'denied'}});
     for(const text of turns){const before=item.trace.length;
       const result=await runtime.processTurn(session,{text,now:new Date('2026-10-17T04:00:00Z'),conversationContext:'SYNTHETIC:TEST'});
       item.turns.push({text,semantic:result.semantic??null,trace:result.semanticExecution??null,reply:result.reply,revision:result.revision,
         model_calls:item.trace.slice(before).filter(e=>e.type==='llm').length});save();
     }
     const valid=item.turns.every(t=>id==='private'?t.model_calls===0:t.trace?.parser_status==='llm_valid');
     const route=item.turns.every(t=>!expectedRoutes.length||expectedRoutes.includes(t.semantic?.route)||id==='urgent'&&t.reply.safetyAction);
     item.schema_status=valid?'PASS':'FAIL';item.route_status=route?'PASS':'FAIL';item.status=valid&&route?'PASS':'FAIL';
     if(id==='urgent'&&!item.turns[0].reply.safetyAction)item.status='FAIL';
     if(id==='private'&&item.trace.some(e=>e.type==='llm'))item.status='FAIL';
     item.understanding_status=item.status;
     item.behavior_status=['lumbar_plan','schedule_operation','mixed_discomfort','knee_mixed','multiturn'].includes(id)?'NOT IMPLEMENTED':'UNVERIFIED';
     item.behavior_note='Schema/route PASS is understanding evidence only. Product-style read-only assistant with real SYNTHETIC SQLite read/operation ports and local navigation registry; no UI, clinician approval or candidate adoption.';
     if(item.status==='PASS')item.status='PARTIAL';
     item.database_unchanged=sha(database)===report.database_before;assert(item.database_unchanged);
   }catch(error){item.status='FAIL';item.error=safeError(error);}
   finally{await runtime.closeSession(session).catch(()=>{});}
   report.database_after=sha(database);save();console.log(id+': '+item.status);
 }
 report.totals={cases:report.cases.length,pass:report.cases.filter(c=>c.status==='PASS').length,partial:report.cases.filter(c=>c.status==='PARTIAL').length,fail:report.cases.filter(c=>c.status==='FAIL').length,
  understanding_pass:report.cases.filter(c=>c.understanding_status==='PASS').length,
  model_calls:report.cases.flatMap(c=>c.trace).filter(e=>e.type==='llm').length,host_reads:report.cases.flatMap(c=>c.trace).filter(e=>e.type==='host_read').length};
 save();console.log(JSON.stringify(report.totals));
}
main().catch(()=>{console.error('Acceptance runner failed; credential and provider details omitted.');process.exitCode=1;});
