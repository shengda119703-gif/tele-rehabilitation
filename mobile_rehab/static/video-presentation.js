/* Local video presentation only: no upload, analysis or record writes. */
(function(root){
'use strict';
const MAX_MOOV=16*1024*1024,MAX_SAMPLES=2000000;
const safe=fn=>{try{return fn();}catch{return false;}};
const abort=()=>Object.assign(new Error('Video preview cancelled'),{name:'AbortError'});
function number64(view,at,signed=false){
  const n=signed?view.getBigInt64(at):view.getBigUint64(at);
  if(n>BigInt(Number.MAX_SAFE_INTEGER)||n<BigInt(Number.MIN_SAFE_INTEGER))throw Error('Unsafe video timestamp');
  return Number(n);
}
function type(view,at){return String.fromCharCode(...new Uint8Array(view.buffer,view.byteOffset+at,4));}
function boxes(view,start=0,end=view.byteLength){
  const result=[];
  for(let at=start;at<end;){
    if(at+8>end)throw Error('Incomplete video box');
    let size=view.getUint32(at),header=8;
    if(size===1){if(at+16>end)throw Error('Incomplete large video box');size=number64(view,at+8);header=16;}
    if(size===0)size=end-at;
    if(size<header||at+size>end)throw Error('Invalid video box size');
    result.push({type:type(view,at+4),start:at+header,end:at+size});at+=size;
    if(result.length>100000)throw Error('Too many video boxes');
  }
  return result;
}
const child=(view,box,name)=>boxes(view,box.start,box.end).find(b=>b.type===name);
function requireBytes(box,at,length){if(at<box.start||at+length>box.end)throw Error('Incomplete video table');}
function table(view,box,signed=false){
  requireBytes(box,box.start,8);const version=view.getUint8(box.start),count=view.getUint32(box.start+4);
  if(version>1||count>MAX_SAMPLES)throw Error('Unsupported video table');
  requireBytes(box,box.start+8,count*8);
  const rows=[];let total=0;
  for(let i=0;i<count;i++){
    const at=box.start+8+i*8,n=view.getUint32(at),value=signed&&version===1?view.getInt32(at+4):view.getUint32(at+4);
    if(!n||(total+=n)>MAX_SAMPLES)throw Error('Invalid sample count');rows.push([n,value]);
  }
  return{rows,total};
}
function timescale(view,box){
  if(!box)throw Error('Missing media timescale');requireBytes(box,box.start,4);
  const version=view.getUint8(box.start),at=box.start+(version===1?20:12);
  if(version>1)throw Error('Unsupported media header');requireBytes(box,at,4);
  const value=view.getUint32(at);if(!value)throw Error('Invalid media timescale');return value;
}
function editStart(view,track,movieScale){
  const edts=child(view,track,'edts');if(!edts)return{media:0,offset:0,length:Infinity,hasEdit:false};
  const elst=child(view,edts,'elst');if(!elst)return{media:0,offset:0,length:Infinity,hasEdit:false};
  requireBytes(elst,elst.start,8);const version=view.getUint8(elst.start),count=view.getUint32(elst.start+4),size=version===1?20:12;
  if(version>1||count>1024)throw Error('Unsupported edit list');requireBytes(elst,elst.start+8,count*size);
  let offset=0,edit=null;
  for(let i=0;i<count;i++){
    const at=elst.start+8+i*size,duration=version===1?number64(view,at):view.getUint32(at),media=version===1?number64(view,at+8,true):view.getInt32(at+4),rate=at+(version===1?16:8);
    if(view.getInt16(rate)!==1||view.getInt16(rate+2)!==0)throw Error('Unsupported edit rate');
    if(media===-1&&!edit){offset+=duration/movieScale;continue;}
    if(media<0||edit)throw Error('Multiple media edits require decoder fallback');
    edit={media,offset,length:duration?duration/movieScale:Infinity,hasEdit:true};
  }
  if(!edit)throw Error('Video has no visible edit');return edit;
}
function mp4Timing(view){
  const moov={start:0,end:view.byteLength},movieScale=timescale(view,child(view,moov,'mvhd'));
  const tracks=boxes(view).filter(b=>b.type==='trak').map(track=>{
    const media=child(view,track,'mdia'),handler=media&&child(view,media,'hdlr');
    if(!handler)return null;requireBytes(handler,handler.start+8,4);if(type(view,handler.start+8)!=='vide')return null;
    const tkhd=child(view,track,'tkhd');let enabled=true;if(tkhd){requireBytes(tkhd,tkhd.start,4);enabled=!!(view.getUint32(tkhd.start)&1);}
    return{track,media,enabled};
  }).filter(Boolean);
  const enabled=tracks.filter(t=>t.enabled),selected=tracks.length===1?tracks[0]:enabled.length===1?enabled[0]:null;
  if(!selected)return null;
  const {track,media}=selected,scale=timescale(view,child(view,media,'mdhd')),minf=child(view,media,'minf'),stbl=minf&&child(view,minf,'stbl'),stts=stbl&&child(view,stbl,'stts');
  if(!stts)return null;
  const decode=table(view,stts);if(decode.total<2)return null;
  const ctts=child(view,stbl,'ctts'),composition=ctts?table(view,ctts,true):{rows:[[decode.total,0]],total:decode.total};
  if(composition.total!==decode.total)throw Error('Inconsistent composition table');
  const stsz=child(view,stbl,'stsz');if(stsz){requireBytes(stsz,stsz.start+8,4);if(view.getUint32(stsz.start+8)!==decode.total)throw Error('Inconsistent sample table');}
  const edit=editStart(view,track,movieScale),first=[],insert=sample=>{first.push(sample);first.sort((a,b)=>a.t-b.t);if(first.length>3)first.pop();};
  let dts=0,ci=0,remaining=composition.rows[0][0],previous=null;
  for(const [count,delta]of decode.rows){
    if(!delta)throw Error('Zero frame duration');
    for(let n=0;n<count;n++){
      const pts=dts+composition.rows[ci][1],sample={t:pts,duration:delta};
      if(edit.hasEdit&&pts<=edit.media){if(!previous||pts>previous.t)previous=sample;}
      else if(!edit.hasEdit||pts>edit.media)insert(sample);
      dts+=delta;if(!Number.isSafeInteger(dts))throw Error('Unsafe decode time');
      if(--remaining===0&&ci+1<composition.rows.length)remaining=composition.rows[++ci][0];
    }
  }
  if(previous)insert({...previous,t:edit.media});
  const visible=first.map(s=>({timestamp:edit.offset+(s.t-(edit.hasEdit?edit.media:0))/scale,duration:s.duration/scale})).filter(s=>s.timestamp>=0&&s.timestamp<edit.offset+edit.length);
  if(visible.length<2||visible[0].timestamp===visible[1].timestamp||visible[2]?.timestamp===visible[1].timestamp)return null;
  const second=visible[1],end=Math.min(visible[2]?.timestamp??second.timestamp+second.duration,edit.offset+edit.length);
  if(!(end>second.timestamp))return null;
  // Some Android decoders choose the nearest timestamp when seeking. Stay
  // just inside this frame, away from both its boundary and the next frame.
  return{timestamp:second.timestamp,endTimestamp:end,previousTimestamp:visible[0].timestamp,seekTime:second.timestamp+Math.min((end-second.timestamp)/4,.001),method:'mp4'};
}
async function secondFrameTiming(file){
  try{
    if(!file||typeof file.slice!=='function')return null;
    for(let at=0,count=0;at+8<=file.size&&count<1024;count++){
      const header=new DataView(await file.slice(at,Math.min(at+16,file.size)).arrayBuffer());
      let size=header.getUint32(0),head=8;if(size===1){if(header.byteLength<16)return null;size=number64(header,8);head=16;}if(size===0)size=file.size-at;
      if(size<head||at+size>file.size)return null;
      if(type(header,4)==='moov'){
        if(size-head>MAX_MOOV)return null;
        return mp4Timing(new DataView(await file.slice(at+head,at+size).arrayBuffer()));
      }
      at+=size;
    }
  }catch{/* Unsupported or malformed metadata uses a bounded decoder fallback. */}
  return null;
}
function preview(video,file,options={}){
  if(!root.document||!video||!file)return()=>{};
  let cancelled=false,decoder=null,decoderURL=null,posterURL=null,frameCallback=null;
  const waiters=new Set(),source=video.getAttribute('src'),previousPoster=video.getAttribute('poster');
  const valid=()=>!cancelled&&video.isConnected&&video.paused&&video.getAttribute('src')===source&&safe(()=>!options.valid||options.valid());
  const releaseDecoder=()=>{if(!decoder)return;if(frameCallback!==null&&decoder.cancelVideoFrameCallback)decoder.cancelVideoFrameCallback(frameCallback);decoder.pause();decoder.removeAttribute('src');decoder.load();decoder.remove();decoder=null;if(decoderURL){root.URL.revokeObjectURL(decoderURL);decoderURL=null;}};
  const cleanup=()=>{
    if(cancelled)return;cancelled=true;clearTimeout(timer);video.removeEventListener('play',cleanup);video.removeEventListener('seeking',cleanup);
    for(const reject of [...waiters])reject(abort());waiters.clear();releaseDecoder();
    if(posterURL){if(video.getAttribute('poster')===posterURL){if(previousPoster===null)video.removeAttribute('poster');else video.setAttribute('poster',previousPoster);}root.URL.revokeObjectURL(posterURL);posterURL=null;}
  };
  const timer=setTimeout(cleanup,15000);video.addEventListener('play',cleanup);video.addEventListener('seeking',cleanup);
  const wait=(name,ready)=>new Promise((resolve,reject)=>{
    if(!valid())return reject(abort());if(ready?.())return resolve();
    const target=decoder,done=error=>{target.removeEventListener(name,onEvent);target.removeEventListener('error',onError);waiters.delete(cancel);error?reject(error):resolve();},cancel=error=>done(error),onEvent=()=>done(valid()?null:abort()),onError=()=>done(Error('Video decode failed'));
    waiters.add(cancel);target.addEventListener(name,onEvent,{once:true});target.addEventListener('error',onError,{once:true});
  });
  const capture=()=>new Promise((resolve,reject)=>{
    if(!valid()||!decoder?.videoWidth||decoder.readyState<2)return reject(abort());
    const canvas=root.document.createElement('canvas'),scale=Math.min(1,1280/Math.max(decoder.videoWidth,decoder.videoHeight));canvas.width=Math.max(1,Math.round(decoder.videoWidth*scale));canvas.height=Math.max(1,Math.round(decoder.videoHeight*scale));
    try{canvas.getContext('2d').drawImage(decoder,0,0,canvas.width,canvas.height);canvas.toBlob(blob=>{if(!blob||!valid())return reject(abort());posterURL=root.URL.createObjectURL(blob);video.setAttribute('poster',posterURL);resolve();},'image/jpeg',.88);}catch(error){reject(error);}
  });
  void(async()=>{
    try{
      const timing=await secondFrameTiming(file);if(!valid())return;
      decoder=root.document.createElement('video');decoder.muted=true;decoder.defaultMuted=true;decoder.playsInline=true;decoder.preload='auto';decoder.setAttribute('aria-hidden','true');decoder.tabIndex=-1;
      decoder.style.cssText='position:fixed;left:-10000px;top:0;width:1px;height:1px;opacity:0;pointer-events:none';root.document.body.append(decoder);
      decoderURL=root.URL.createObjectURL(file);
      if(timing){
        const metadata=wait('loadedmetadata',()=>decoder.readyState>=1);decoder.src=decoderURL;decoder.load();await metadata;if(!valid())return;
        const committed=typeof decoder.requestVideoFrameCallback==='function'?new Promise((resolve,reject)=>{
          const cancel=error=>reject(error);waiters.add(cancel);
          // Browser metadata rounds mediaTime to microseconds. Keep the
          // tolerance smaller than either adjacent source-frame interval.
          const epsilon=Math.min(.000001,(timing.timestamp-timing.previousTimestamp)/4,(timing.endTimestamp-timing.timestamp)/4);
          const tick=(_,meta)=>{
            if(!valid()){waiters.delete(cancel);reject(abort());return;}
            if(Number.isFinite(meta.mediaTime)&&meta.mediaTime>=timing.timestamp-epsilon&&meta.mediaTime<timing.endTimestamp-epsilon){waiters.delete(cancel);resolve();return;}
            frameCallback=decoder.requestVideoFrameCallback(tick);
          };frameCallback=decoder.requestVideoFrameCallback(tick);
        }):Promise.resolve();
        const seek=wait('seeked');decoder.currentTime=timing.seekTime;await Promise.all([seek,committed]);
        if(decoder.readyState<2)await wait('loadeddata',()=>decoder.readyState>=2);await capture();
      }else if(typeof decoder.requestVideoFrameCallback==='function'){
        // A callback count alone is not a frame number. Require the first two
        // consecutive submitted frames and distinct source presentation times.
        decoder.playbackRate=.1;
        const frames=new Promise((resolve,reject)=>{
          let first=null;const cancel=error=>reject(error);waiters.add(cancel);
          const tick=(_,meta)=>{
            if(!valid()){waiters.delete(cancel);reject(abort());return;}
            if(meta.presentedFrames===1){first=meta.mediaTime;frameCallback=decoder.requestVideoFrameCallback(tick);return;}
            waiters.delete(cancel);
            if(meta.presentedFrames!==2||first===null||!(meta.mediaTime>first)){reject(Error('Second presented frame was skipped'));return;}
            decoder.pause();resolve();
          };frameCallback=decoder.requestVideoFrameCallback(tick);
        });
        decoder.src=decoderURL;decoder.load();const playing=Promise.resolve(decoder.play());await Promise.all([frames,playing]);await capture();
      }
    }catch{/* Preview failures must never interrupt file selection or analysis. */}
    finally{releaseDecoder();if(!posterURL)cleanup();else clearTimeout(timer);}
  })();
  return cleanup;
}
function autoPlay(video,options={}){
  let stopped=false,attempted=false;
  const valid=()=>!stopped&&video.isConnected&&safe(()=>!options.valid||options.valid());
  const cleanup=()=>{stopped=true;video.removeEventListener('loadeddata',attempt);video.removeEventListener('play',played);video.removeEventListener('pause',cleanup);};
  const played=()=>{attempted=true;video.removeEventListener('loadeddata',attempt);};
  const attempt=()=>{
    if(attempted||!valid()){if(!valid())cleanup();return;}if(video.readyState<2)return;
    attempted=true;video.removeEventListener('loadeddata',attempt);video.muted=true;
    try{Promise.resolve(video.play()).catch(error=>{if(valid())safe(()=>options.onBlocked?.(error));});}catch(error){if(valid())safe(()=>options.onBlocked?.(error));}
  };
  video.addEventListener('loadeddata',attempt);video.addEventListener('play',played);video.addEventListener('pause',cleanup);
  Promise.resolve().then(attempt);
  return cleanup;
}
const api={preview,autoPlay,secondFrameTiming};root.RehabVideoPresentation=api;
if(typeof module!=='undefined'&&module.exports)module.exports=api;
})(globalThis);
