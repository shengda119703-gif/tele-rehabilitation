// Preserve visual assets separately from allowed control-code/wording changes.
'use strict';
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),{execFileSync}=require('node:child_process');
const root=path.resolve(__dirname,'../..'),output=path.resolve(process.argv[2]);
const afterDirectory=process.argv[3]?path.resolve(process.argv[3]):path.join(root,'.runtime/frontend_flow/20261012-u0/after'),baselineRef=process.argv[4]||'HEAD';
const names=execFileSync('git',['-c','core.quotepath=false','ls-files','mobile_rehab/static','android_offline/res','rehab_codex_single_camera_v2_1/app/ui','rehab_codex_single_camera_v2_1/assets'],{cwd:root,encoding:'utf8'}).trim().split('\n').filter(n=>/\.(css|qss|svg|png|jpg|jpeg|webp|ttf|otf|woff2?|ico|xml)$/.test(n)||/app\/ui\//.test(n));
const digest=v=>crypto.createHash('sha256').update(v).digest('hex');
// Git's LF blobs can have a CRLF working copy. Record both raw digests, and
// normalize ONLY CRLF in known text formats; binary resources stay byte-exact.
const files=names.map(name=>{
 const baseline=execFileSync('git',['show',baselineRef+':'+name],{cwd:root,maxBuffer:32*1024*1024}),current=fs.readFileSync(path.join(root,name));
 const textResource=/\.(css|qss|svg|xml|py)$/.test(name),normalize=v=>Buffer.from(v.toString('utf8').replace(/\r\n/g,'\n'));
 const validUtf8=v=>Buffer.from(v.toString('utf8')).equals(v);
 const byteIdentical=current.equals(baseline),eolOnly=!byteIdentical&&textResource&&validUtf8(current)&&validUtf8(baseline)&&normalize(current).equals(normalize(baseline));
 return{path:name,sha256:digest(current),git_blob_sha256:digest(baseline),byte_identical:byteIdentical,eol_only:eolOnly,unchanged:byteIdentical||eolOnly};
});
const before=JSON.parse(fs.readFileSync(path.join(root,'.runtime/frontend_flow/20261012-u0/before/observations.json'))),after=JSON.parse(fs.readFileSync(path.join(afterDirectory,'observations.json')));
const geometryUnchanged=JSON.stringify(before.results.map(r=>r.observation))===JSON.stringify(after.results.map(r=>r.observation));
const result={kind:'frozen-visual-resource-and-geometry-check',baseline_ref:baselineRef,comparison:'Git baseline: binary byte-exact; known valid UTF-8 text permits CRLF-only differences',files,changed:files.filter(f=>!f.unchanged).map(f=>f.path),geometryUnchanged,presentation_only:true,physical_device_test:false};
fs.writeFileSync(output,JSON.stringify(result,null,2));console.log(JSON.stringify({protected_files:files.length,changed:result.changed,geometryUnchanged}));if(result.changed.length||!geometryUnchanged)process.exitCode=1;
