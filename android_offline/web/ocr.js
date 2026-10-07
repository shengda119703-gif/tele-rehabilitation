/* Bundled OCR only. Results are editable draft text, never automatic measurements. */
(function(root){
'use strict';
let running=false;
async function recognize(blob){
 if(running)throw Error('已有图片正在识别');if(!['image/jpeg','image/png'].includes(blob.type)||blob.size>8*1048576)throw Error('请选择 8 MB 内的 JPG 或 PNG');
 running=true;let worker,spawned,url,timer,image,stopped=false;
 try{
  image=await createImageBitmap(blob);if(image.width*image.height>30000000)throw Error('图片过大，请先裁剪');
  const scale=Math.min(1,1600/Math.max(image.width,image.height)),canvas=new OffscreenCanvas(Math.round(image.width*scale),Math.round(image.height*scale));canvas.getContext('2d').drawImage(image,0,0,canvas.width,canvas.height);image.close();image=null;
  const simd=WebAssembly.validate(Uint8Array.from([0,97,115,109,1,0,0,0,1,5,1,96,0,1,123,3,2,1,0,10,10,1,8,0,65,0,253,15,253,98,11]));
  const [core,body,chi,eng]=await Promise.all([fetch('/ocr/tesseract-core-'+(simd?'simd-':'')+'lstm.wasm.js').then(r=>r.text()),fetch('/ocr/worker.min.js').then(r=>r.text()),fetch('/ocr/chi_sim.traineddata').then(r=>r.arrayBuffer()),fetch('/ocr/eng.traineddata').then(r=>r.arrayBuffer())]);
  // Preload language bytes in a dedicated worker message. Upstream 6.0.1 cannot
  // initialize correctly with object-valued language identifiers; retain strings.
  const prefix="const phoneOcrData={};const phoneFetch=self.fetch.bind(self);self.addEventListener('message',e=>{if(e.data.phoneOcrWeights){Object.assign(phoneOcrData,e.data.phoneOcrWeights);e.stopImmediatePropagation();}});self.fetch=(url,...args)=>{const key=String(url).split('/').pop();if(phoneOcrData[key])return Promise.resolve(new Response(phoneOcrData[key]));return phoneFetch(url,...args);};\n";
  url=URL.createObjectURL(new Blob([prefix,core,'\n',body],{type:'text/javascript'}));
  const work=(async()=>{
   const OriginalWorker=root.Worker;let start;
   try{root.Worker=class extends OriginalWorker{constructor(path,options){super(path,options);if(path===url){spawned=this;this.postMessage({phoneOcrWeights:{'chi_sim.traineddata':chi,'eng.traineddata':eng}},[chi,eng]);}}};
    start=Tesseract.createWorker('chi_sim+eng',1,{workerPath:url,workerBlobURL:false,cacheMethod:'none',gzip:false,langPath:location.origin+'/ocr'});
   }finally{root.Worker=OriginalWorker;}
   worker=await start;if(stopped)throw Error('图片识别已停止');const result=await worker.recognize(await canvas.convertToBlob({type:'image/png'}));return{text:result.data.text.slice(0,20000),confidence:result.data.confidence,local:true,engine:'tesseract.js@6.0.1'};
  })();
  return await Promise.race([work,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('图片识别超时，请裁剪后重试')),90000);})]);
 }finally{stopped=true;clearTimeout(timer);image?.close();spawned?.terminate();if(url)URL.revokeObjectURL(url);running=false;}
}
root.PhoneOCR={recognize};
})(globalThis);
