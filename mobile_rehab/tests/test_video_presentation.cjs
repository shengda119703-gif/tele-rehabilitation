'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const P=require('../static/video-presentation.js');
const u32=n=>{const b=Buffer.alloc(4);b.writeUInt32BE(n);return b;};
const i32=n=>{const b=Buffer.alloc(4);b.writeInt32BE(n);return b;};
const box=(type,...body)=>{const data=Buffer.concat(body);return Buffer.concat([u32(data.length+8),Buffer.from(type),data]);};
const full=(version=0)=>Buffer.from([version,0,0,0]);
function movie({durations=[[4,40]],offsets=null,edit=null,scale=1000,movieScale=1000,large=false,mediaType='vide',sampleCount=null}={}){
  const count=durations.reduce((n,r)=>n+r[0],0),stts=box('stts',full(),u32(durations.length),...durations.flatMap(([n,d])=>[u32(n),u32(d)]));
  const ctts=offsets?box('ctts',full(offsets.some(r=>r[1]<0)?1:0),u32(offsets.length),...offsets.flatMap(([n,d])=>[u32(n),d<0?i32(d):u32(d)])):Buffer.alloc(0);
  const stbl=box('stbl',stts,ctts,box('stsz',full(),u32(0),u32(sampleCount??count)));
  const mdia=box('mdia',box('mdhd',full(),u32(0),u32(0),u32(scale),u32(100000)),box('hdlr',full(),u32(0),Buffer.from(mediaType)),box('minf',stbl));
  const edits=edit?box('edts',box('elst',full(),u32(edit.length),...edit.flatMap(([duration,start,rate=1])=>[u32(duration),i32(start),Buffer.from([0,rate,0,0])]))):Buffer.alloc(0);
  let moov=box('moov',box('mvhd',full(),u32(0),u32(0),u32(movieScale),u32(100000)),box('trak',box('tkhd',Buffer.from([0,0,0,1])),edits,mdia));
  if(large){const header=Buffer.alloc(16);header.writeUInt32BE(1);header.write('moov',4);header.writeBigUInt64BE(BigInt(moov.length+8),8);moov=Buffer.concat([header,moov.subarray(8)]);}
  return new Blob([box('ftyp',Buffer.from('isom0000')),box('mdat',Buffer.alloc(64)),moov],{type:'video/mp4'});
}
test('second MP4 display frame uses actual VFR duration rather than a fixed FPS',async()=>{
  const t=await P.secondFrameTiming(movie({durations:[[1,17],[1,83],[2,40]]}));
  assert.equal(t.timestamp,.017);assert.equal(t.endTimestamp,.1);assert.equal(t.seekTime,.018000000000000002);assert.equal(t.method,'mp4');
  const ntsc=await P.secondFrameTiming(movie({durations:[[4,1001]],scale:30000}));
  assert.equal(ntsc.timestamp,1001/30000);
});
test('B frame composition order and signed CTTS determine second displayed frame',async()=>{
  const t=await P.secondFrameTiming(movie({offsets:[[1,0],[1,80],[2,-40]]}));
  // Decode timestamps 0,40,80,120 become composition timestamps 0,120,40,80.
  assert.equal(t.timestamp,.04);assert.equal(t.seekTime,.041);
});
test('edit start trims priming frames and leading empty edits shift movie time',async()=>{
  const t=await P.secondFrameTiming(movie({durations:[[6,40]],edit:[[200,-1],[120,80]]}));
  assert(Math.abs(t.timestamp-.24)<1e-12);assert(Math.abs(t.seekTime-.241)<1e-12);
  const between=await P.secondFrameTiming(movie({durations:[[6,40]],edit:[[100,50]]}));
  assert.equal(between.timestamp,.03);assert.equal(between.seekTime,.031);
});
test('large boxes and a final second frame are supported without reading mdat',async()=>{
  const file=movie({durations:[[2,50]],large:true}),reads=[];
  const wrapped={size:file.size,slice(a,b){reads.push([a,b]);return file.slice(a,b);}};
  const t=await P.secondFrameTiming(wrapped);assert.equal(t.timestamp,.05);assert.equal(t.seekTime,.051000000000000004);
  assert(reads.every(([a,b])=>!(a===24&&b===88)));
});
test('incomplete, inconsistent and unsupported metadata never supplies an invented frame time',async()=>{
  for(const file of [new Blob([Buffer.from('not a video')]),movie({durations:[[1,40]]}),movie({sampleCount:99}),movie({offsets:[[1,0]]}),movie({edit:[[40,0],[40,80]]}),movie({edit:[[100,0,0]]}),movie({mediaType:'soun'}),movie({durations:[[4,0]]})])assert.equal(await P.secondFrameTiming(file),null);
  const malformed=Buffer.alloc(16);malformed.writeUInt32BE(0xffffffff);malformed.write('moov',4);assert.equal(await P.secondFrameTiming(new Blob([malformed])),null);
});
class Video extends EventTarget{
  constructor(){super();this.attrs=new Map();this.paused=true;this.isConnected=true;this.readyState=0;this.videoWidth=640;this.videoHeight=480;this.style={};this.playCalls=0;this.pauseCalls=0;this.time=0;}
  getAttribute(name){return this.attrs.has(name)?this.attrs.get(name):null;}
  setAttribute(name,value){this.attrs.set(name,String(value));}
  removeAttribute(name){this.attrs.delete(name);}
  set src(value){this.setAttribute('src',value);}
  get src(){return this.getAttribute('src')||'';}
  get currentTime(){return this.time;}
  set currentTime(value){this.time=value;this.seekTimes??=[];this.seekTimes.push(value);queueMicrotask(()=>{this.readyState=2;this.dispatchEvent(new Event('seeked'));this.onSeekRequested?.();});}
  load(){if(!this.src)return;queueMicrotask(()=>{this.readyState=2;this.dispatchEvent(new Event('loadedmetadata'));this.dispatchEvent(new Event('loadeddata'));});}
  play(){this.playCalls++;if(this.rejectPlay)return Promise.reject(Error('gesture required'));this.paused=false;this.dispatchEvent(new Event('play'));return Promise.resolve();}
  pause(){this.pauseCalls++;if(!this.paused){this.paused=true;this.dispatchEvent(new Event('pause'));}}
  remove(){this.isConnected=false;}
}
const flush=()=>new Promise(resolve=>setImmediate(resolve));
async function browser(run){
  const originalDocument=global.document,originalURL=global.URL,decoders=[],created=[],revoked=[],draws=[];let blobCallback=null;
  global.document={body:{append(){}},createElement(tag){if(tag==='video'){
    const v=new Video();
    if(browser.frameSequence||browser.seekSequence){
      const sequence=[...(browser.frameSequence||browser.seekSequence)],callbacks=new Map();let id=0;
      v.requestVideoFrameCallback=fn=>{callbacks.set(++id,fn);return id;};v.cancelVideoFrameCallback=n=>{v.cancelledFrames=(v.cancelledFrames||0)+1;callbacks.delete(n);};
      v.deliverFrame=meta=>{const entry=callbacks.entries().next().value;if(!entry)return;callbacks.delete(entry[0]);entry[1](0,meta);};
      const deliver=()=>{const meta=sequence.shift();if(!meta)return;v.deliverFrame(meta);queueMicrotask(deliver);};
      if(browser.seekSequence)v.onSeekRequested=()=>queueMicrotask(deliver);
      else{const originalPlay=v.play.bind(v);v.play=()=>{const playing=originalPlay();queueMicrotask(deliver);return playing;};}
    }
    decoders.push(v);return v;
  }if(tag==='canvas')return{getContext(){return{drawImage:(...args)=>draws.push(args)};},toBlob(callback){if(browser.delayBlob)blobCallback=callback;else queueMicrotask(()=>callback(new Blob(['poster'])));}};throw Error(tag);}};
  global.URL={createObjectURL(blob){const url='blob:qa-'+created.length;created.push({url,blob});return url;},revokeObjectURL:url=>revoked.push(url)};
  try{await run({decoders,created,revoked,draws,finishBlob:()=>blobCallback?.(new Blob(['poster']))});}
  finally{global.document=originalDocument;global.URL=originalURL;browser.delayBlob=false;browser.frameSequence=null;browser.seekSequence=null;}
}
test('preview uses an independent seek decoder and only installs a poster on the visible video',async()=>browser(async env=>{
  const video=new Video();video.src='blob:selected';const cleanup=P.preview(video,movie());
  for(let i=0;i<5;i++)await flush();
  assert.equal(video.currentTime,0);assert.equal(video.playCalls,0);assert.equal(env.decoders.length,1);assert.deepEqual(env.decoders[0].seekTimes,[.041]);
  assert.equal(env.draws.length,1);assert.equal(video.getAttribute('poster'),'blob:qa-1');assert(env.revoked.includes('blob:qa-0'));
  cleanup();assert.equal(video.getAttribute('poster'),null);assert(env.revoked.includes('blob:qa-1'));
}));
test('play or seeking cancels a delayed poster and never resets the user frame',async()=>{
  for(const event of ['play','seeking'])await browser(async env=>{
    browser.delayBlob=true;const video=new Video();video.src='blob:selected';const cleanup=P.preview(video,movie());for(let i=0;i<5;i++)await flush();
    video.time=4.25;video.dispatchEvent(new Event(event));env.finishBlob();await flush();
    assert.equal(video.getAttribute('poster'),null);assert.equal(video.currentTime,4.25);assert.equal(env.created.length,1);cleanup();
  });
});
test('source replacement or owner invalidation rejects late posters and releases the decoder',async()=>{
  for(const change of ['source','owner'])await browser(async env=>{
    browser.delayBlob=true;let owner=true;const video=new Video();video.src='blob:selected';const cleanup=P.preview(video,movie(),{valid:()=>owner});for(let i=0;i<5;i++)await flush();
    if(change==='source')video.src='blob:new-selection';else owner=false;env.finishBlob();await flush();
    assert.equal(video.getAttribute('poster'),null);assert.equal(env.created.length,1);assert(env.revoked.includes('blob:qa-0'));cleanup();
  });
});
test('MP4 poster waits for the second source frame to be submitted after an old-frame callback',async()=>browser(async env=>{
  browser.seekSequence=[{presentedFrames:1,mediaTime:0}];
  const video=new Video();video.src='blob:selected';const cleanup=P.preview(video,movie());for(let i=0;i<5;i++)await flush();
  assert.equal(env.draws.length,0);assert.equal(video.getAttribute('poster'),null);
  env.decoders[0].deliverFrame({presentedFrames:2,mediaTime:.04});for(let i=0;i<3;i++)await flush();
  assert.equal(env.draws.length,1);assert(video.getAttribute('poster'));assert.equal(video.currentTime,0);cleanup();
}));
test('cancellation while waiting for the submitted seek frame rejects late callbacks',async()=>browser(async env=>{
  browser.seekSequence=[{presentedFrames:1,mediaTime:0}];
  const video=new Video();video.src='blob:selected';const cleanup=P.preview(video,movie());for(let i=0;i<5;i++)await flush();
  video.time=3.5;video.dispatchEvent(new Event('seeking'));env.decoders[0].deliverFrame({presentedFrames:2,mediaTime:.04});await flush();
  assert.equal(env.draws.length,0);assert.equal(video.getAttribute('poster'),null);assert.equal(video.currentTime,3.5);assert(env.decoders[0].cancelledFrames>0);assert(env.revoked.includes('blob:qa-0'));cleanup();
}));
test('a committed next frame outside the second-frame interval is never captured',async()=>browser(async env=>{
  browser.seekSequence=[{presentedFrames:1,mediaTime:.08}];
  const video=new Video();video.src='blob:selected';const cleanup=P.preview(video,movie());for(let i=0;i<5;i++)await flush();
  assert.equal(env.draws.length,0);assert.equal(video.getAttribute('poster'),null);cleanup();await flush();
}));
test('unknown containers use two verified submitted source frames in a muted independent decoder',async()=>browser(async env=>{
  browser.frameSequence=[{presentedFrames:1,mediaTime:0},{presentedFrames:2,mediaTime:.083}];
  const video=new Video();video.src='blob:selected';const cleanup=P.preview(video,new Blob(['webm-or-other-container']));for(let i=0;i<5;i++)await flush();
  assert.equal(env.decoders[0].muted,true);assert.equal(env.decoders[0].playbackRate,.1);assert.equal(video.playCalls,0);assert.equal(video.currentTime,0);assert.equal(env.draws.length,1);assert(video.getAttribute('poster'));cleanup();
}));
test('callback skips or duplicate source frames never become a claimed second-frame poster',async()=>{
  for(const sequence of [[{presentedFrames:3,mediaTime:.08}],[{presentedFrames:1,mediaTime:0},{presentedFrames:3,mediaTime:.08}],[{presentedFrames:1,mediaTime:0},{presentedFrames:2,mediaTime:0}]])await browser(async env=>{
    browser.frameSequence=sequence;const video=new Video();video.src='blob:selected';const cleanup=P.preview(video,new Blob(['unknown']));for(let i=0;i<5;i++)await flush();
    assert.equal(video.getAttribute('poster'),null);assert.equal(env.draws.length,0);assert(env.revoked.includes('blob:qa-0'));cleanup();
  });
});
test('autoplay waits for decoded data, mutes once, and never resumes a user pause',async()=>{
  const video=new Video(),cleanup=P.autoPlay(video);await flush();assert.equal(video.playCalls,0);
  video.readyState=2;video.dispatchEvent(new Event('loadeddata'));await flush();assert.equal(video.playCalls,1);assert.equal(video.muted,true);
  video.time=3.25;video.pause();video.dispatchEvent(new Event('loadeddata'));await flush();assert.equal(video.playCalls,1);assert.equal(video.currentTime,3.25);cleanup();
});
test('autoplay rejection is handled once and a stale owner never starts playback',async()=>{
  const video=new Video();video.readyState=2;video.rejectPlay=true;let blocked=0;const cleanup=P.autoPlay(video,{onBlocked:()=>blocked++});await flush();video.dispatchEvent(new Event('loadeddata'));await flush();assert.equal(video.playCalls,1);assert.equal(blocked,1);cleanup();
  const stale=new Video();stale.readyState=2;P.autoPlay(stale,{valid:()=>false});await flush();assert.equal(stale.playCalls,0);
});
