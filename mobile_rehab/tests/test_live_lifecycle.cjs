'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../static/extensions.js'),'utf8');
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return{promise,resolve,reject};};
const settle=()=>new Promise(resolve=>setImmediate(resolve));
function harness(){
 const elements=new Map(),calls=[],voices=[],notices=[],cameraCalls=[];let clock=0;
 function node(){return{textContent:'',disabled:false,checked:false,value:'user',videoWidth:640,videoHeight:480,srcObject:null,pauseCalls:0,play:async()=>{},pause(){this.pauseCalls++;},classList:{toggle(){}},getContext:()=>({drawImage(){},clearRect(){},beginPath(){},arc(){},fill(){}})};}
 for(const id of ['live-video','live-start','live-stop','live-facing','live-status','live-cue','live-count','live-angle','live-overlay','live-consent','live-voice'])elements.set('#'+id,node());
 elements.get('#live-consent').checked=true;elements.get('#live-count').textContent='6 次';elements.get('#live-voice').checked=true;
 let camera=async()=>stream(),endpoint=async(route)=>route==='/live'?{id:'original-session'}:{};
 function stream(){const track={stops:0,stop(){this.stops++;}};return{track,getTracks:()=>[track]};}
 const context={console,Map,performance:{now:()=>clock},AbortController,setTimeout,clearTimeout,
  state:{selected:'shoulder_abduction',side:'left'},document:{hidden:false,addEventListener(){},createElement:()=>({...node(),toBlob:resolve=>resolve({type:'image/jpeg'})})},
  window:{isSecureContext:true,addEventListener(){},speechSynthesis:{}},navigator:{mediaDevices:{getUserMedia:(constraints)=>{cameraCalls.push(constraints);return camera(constraints);}}},
  $:selector=>elements.get(selector)||node(),toast:text=>notices.push(text),number:(v,u)=>v+u,
  api:async(route,opts)=>{calls.push({route,opts});return endpoint(route,opts);},speechSynthesis:{cancel(){voices.push({cancel:true});},speak(utterance){voices.push({text:utterance.text});}},SpeechSynthesisUtterance:class{constructor(text){this.text=text;}},
 };
 vm.createContext(context);vm.runInContext(source,context);
 const originalLoop=context.liveLoop;context.liveLoop=async()=>{};
 return{context,elements,calls,cameraCalls,voices,notices,stream,node,originalLoop,run:s=>vm.runInContext(s,context),camera:fn=>{camera=fn;},endpoint:fn=>{endpoint=fn;},clock:t=>{clock=t;}};
}
test('double start has one actual media request and one immutable preview creation',async()=>{
 const h=harness(),permission=deferred();h.camera(()=>permission.promise);const first=h.context.startLive();await h.context.startLive();
 h.context.state.side='right';permission.resolve(h.stream());await first;
 assert.equal(h.cameraCalls.length,1);assert.equal(h.calls.filter(c=>c.route==='/live').length,1);
 assert.equal(JSON.parse(h.calls[0].opts.body).side,'left');assert.equal(h.cameraCalls[0].audio,false);
 h.context.stopLive();await settle();
});
test('stop during ignored permission prevents another prompt and releases the eventual stream',async()=>{
 const h=harness(),permission=deferred(),stream=h.stream();h.camera(()=>permission.promise);
 const pending=h.context.startLive();h.context.stopLive();await h.context.startLive();assert.equal(h.cameraCalls.length,1);
 permission.resolve(stream);await pending;assert.equal(stream.track.stops,1);assert.equal(h.calls.length,0);assert.equal(h.run('liveSession'),null);
});
test('old camera promise cannot attach to a replacement page with identical element IDs',async()=>{
 const h=harness(),permission=deferred(),stream=h.stream();h.camera(()=>permission.promise);
 const pending=h.context.startLive();const replacement=h.node();h.elements.set('#live-video',replacement);
 permission.resolve(stream);await pending;assert.equal(stream.track.stops,1);assert.equal(replacement.srcObject,null);assert.equal(h.calls.length,0);
 // Simulate the navigation owner's explicit resource cancellation.
 h.context.stopLive();
});
test('stop during preview creation deletes that original preview once after the real ID arrives',async()=>{
 const h=harness(),creation=deferred(),released=deferred();h.endpoint(route=>route==='/live'?creation.promise:released.promise);
 const pending=h.context.startLive();await settle();h.context.stopLive();await h.context.startLive();assert.equal(h.calls.length,1);
 creation.resolve({id:'original-owner-preview'});await settle();assert.equal(h.calls[1].route,'/live/original-owner-preview');assert.equal(h.calls[1].opts.method,'DELETE');
 await h.context.startLive();assert.equal(h.calls.length,2);released.resolve({ok:true});await pending;
 assert.equal(h.elements.get('#live-video').srcObject,null);assert.equal(h.elements.get('#live-start').disabled,false);
});
test('failed release stays visible and one explicit retry addresses the original preview',async()=>{
 const h=harness();let deletes=0;h.endpoint(async route=>{if(route==='/live')return{id:'same-id'};if(++deletes===1)throw Error('503');return{ok:true};});
 await h.context.startLive();h.context.stopLive();await settle();assert.match(h.elements.get('#live-status').textContent,/待确认/);
 assert.equal(h.elements.get('#live-start').disabled,true);assert.equal(h.elements.get('#live-stop').disabled,false);
 h.context.stopLive();await settle();assert.equal(deletes,2);assert.equal(h.elements.get('#live-start').disabled,false);
 assert.equal(h.calls.filter(c=>c.route==='/live').length,1);
});
test('only an unsupported optional constraint receives one relaxed retry',async()=>{
 const h=harness();let tries=0;h.camera(async()=>{if(++tries===1)throw Object.assign(Error('constraint'),{name:'OverconstrainedError'});return h.stream();});
 await h.context.startLive();assert.equal(h.cameraCalls.length,2);assert.equal(h.cameraCalls[1].video.width,undefined);h.context.stopLive();await settle();
});
test('permission denial never loops or allocates a preview',async()=>{
 const h=harness();h.camera(async()=>{throw Object.assign(Error('denied'),{name:'NotAllowedError'});});
 await h.context.startLive();assert.equal(h.cameraCalls.length,1);assert.equal(h.calls.length,0);assert.match(h.notices[0],/原视频/);
 assert.equal(h.elements.get('#live-start').disabled,false);
});
const frame=(valid=true,completed=6,cue='缓慢抬起手臂')=>({valid,inference_ms:25,points:[],cue:{instruction:cue,status:'WAIT_READY'},summary:{completed,primary_metric:'shoulder',metrics:{shoulder:{value:45}}}});
test('missing values preserve known count, clear angle, and cannot trigger visual correction speech',async()=>{
 const h=harness();await h.context.startLive();const s=h.run('liveSession');h.endpoint(async route=>{if(route.endsWith('/frame'))return frame(false,null);return{};});
 const running=h.originalLoop(s);await new Promise(resolve=>setTimeout(resolve,20));h.context.stopLive();await running;await settle();
 assert.equal(h.elements.get('#live-count').textContent,'6 次');assert.equal(h.elements.get('#live-angle').textContent,'—');assert.equal(h.voices.filter(v=>v.text).length,0);
});
test('normal voice has a six-second interval and repeated cue has a ten-second interval',async()=>{
 const h=harness();await h.context.startLive();const s=h.run('liveSession'),sequence=[[0,'A'],[1000,'B'],[6000,'B'],[9000,'A'],[12000,'A']];let index=0;
 h.endpoint(async route=>{if(!route.endsWith('/frame'))return{};if(index===sequence.length){h.context.stopLive();return frame();}const[t,cue]=sequence[index++];h.clock(t);return frame(true,6,cue);});
 await h.originalLoop(s);await settle();assert.deepEqual(h.voices.filter(v=>v.text).map(v=>v.text),['A','B','A']);
});
test('one in-flight frame, immediate stop, and a late result cannot overwrite the stopped UI',async()=>{
 const h=harness();await h.context.startLive();const s=h.run('liveSession'),response=deferred();let frames=0;
 h.endpoint(route=>route.endsWith('/frame')?(frames++,response.promise):{});
 const running=h.originalLoop(s);await settle();await settle();assert.equal(frames,1);h.context.stopLive();
 response.resolve(frame(true,99,'迟到口令'));await running;await settle();assert.equal(h.elements.get('#live-count').textContent,'6 次');
 assert.equal(h.voices.filter(v=>v.text).length,0);assert.equal(s.request.signal.aborted,true);assert.equal(s.stream.track.stops,1);
});
