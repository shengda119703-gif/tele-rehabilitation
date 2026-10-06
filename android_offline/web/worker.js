// Preloaded local blob URLs / model buffers keep worker loading independent of
// native asset interceptors. No network requests or runtime model downloads.
let pose, hands, mode, modelInfo,tracker,canvas;
self.onmessage = async ({data}) => {
  const {id,type} = data;
  try {
    if(type === 'init') {
      if(pose) pose.close(); if(hands) hands.close(); pose=hands=null;
      mode=data.mode;
      tracker=data.calibration?new LocalBarbell.Tracker(data.calibration):null;
      canvas=tracker?new OffscreenCanvas(1,1):null;
      const files=await exports.FilesetResolver.isSimdSupported()?data.simd:data.noSimd;
      const common={runningMode:'VIDEO',baseOptions:{delegate:'CPU'},minTrackingConfidence:.5};
      if(mode!=='hand') pose=await exports.PoseLandmarker.createFromOptions(files,{...common,baseOptions:{delegate:'CPU',modelAssetBuffer:new Uint8Array(data.poseModel)},numPoses:1,minPoseDetectionConfidence:.5,minPosePresenceConfidence:.5});
      if(mode==='hand'||mode==='wrist') hands=await exports.HandLandmarker.createFromOptions(files,{...common,baseOptions:{delegate:'CPU',modelAssetBuffer:new Uint8Array(data.handModel)},numHands:1,minHandDetectionConfidence:.5,minHandPresenceConfidence:.5});
      modelInfo=data.modelInfo;
      postMessage({id,ok:true,models:modelInfo}); return;
    }
    if(type==='frame') {
      let result;
      try {
        const p=pose?pose.detectForVideo(data.image,data.timestamp):null;
        const h=hands?hands.detectForVideo(data.image,data.timestamp):null;
        result={pose:p?.landmarks?.[0]||null,hand:h?.landmarks?.[0]||null,handedness:h?.handedness?.[0]?.[0]||null};
        if(tracker){canvas.width=data.image.width;canvas.height=data.image.height;const ctx=canvas.getContext('2d',{willReadFrequently:true});ctx.drawImage(data.image,0,0);result.barbell=tracker.frame(data.timestamp/1000,ctx.getImageData(0,0,canvas.width,canvas.height).data,canvas.width,canvas.height);}
      } finally {data.image.close();}
      postMessage({id,ok:true,result}); return;
    }
    if(type==='barbell-report'){postMessage({id,ok:true,report:tracker?.report()||null});return;}
    throw Error('Unknown worker request');
  } catch(error) {postMessage({id,ok:false,error:String(error?.message||error)});}
};
