/* Static assessment covers only. Never used for angles, sides or motion phases. */
(function(root){
  'use strict';
  const entries=Object.create(null);
  function add(ids,file,alt,source='library'){
    const url='/static/assets/'+(source==='library'?'rehab-library-v1/':'assessment-artwork-v1/')+file+'.webp';
    for(const id of ids.split(' ')){
      if(entries[id])throw Error('Duplicate assessment cover');
      entries[id]=Object.freeze({url,alt,scope:'catalogue_cover'});
    }
  }
  add('shoulder_flexion','048_E-AXU-012_s02','肩前屈动作示意');
  add('shoulder_abduction shoulder_adduction','049_E-AXU-013_s02','肩外展与内收部位示意');
  add('shoulder_extension','048_E-AXU-012_s03','肩后伸动作示意');
  add('sit_to_stand','092_T-LOW-017_s02','椅上起立动作示意');
  add('elbow_flexion elbow_extension','elbow-seated','坐位肘屈伸部位示意','generated');
  add('knee_extension','013_E-LOW-007_s02','坐位伸膝动作示意');
  add('knee_flexion','068_T-LOW-045_s02','扶稳屈膝动作示意');
  add('hip_flexion','006_E-LOW-001_s02','扶稳屈髋动作示意');
  add('hip_extension','007_E-LOW-002_s02','扶稳髋后伸动作示意');
  add('hip_abduction','008_E-LOW-003_s02','扶稳髋外展动作示意');
  add('hip_adduction','008_E-LOW-003_s03','扶稳髋内收动作示意');
  add('wrist_flexion','059_E-AXU-019_s02','前臂支撑腕掌屈部位示意');
  add('wrist_extension','059_E-AXU-019_s03','前臂支撑腕背伸部位示意');
  add('wrist_radial_deviation wrist_ulnar_deviation','wrist-overhead','俯视腕部与手掌部位示意','generated');
  add('ankle_dorsiflexion','122_T-LOW-046_s02','坐位踝背屈动作示意');
  add('ankle_plantarflexion','122_T-LOW-046_s03','坐位踝跖屈动作示意');
  add('neck_lateral_flexion','046_E-AXU-010_s02','坐位头颈侧屈动作示意');
  add('neck_flexion','147_T-AXU-009_s02','坐位头颈前屈动作示意');
  add('neck_extension','148_T-AXU-010_s02','坐位头颈后伸动作示意');
  add('trunk_lateral_flexion','040_E-AXU-007_s02','坐位躯干侧屈动作示意');
  add('trunk_flexion','123_T-AXU-001_s02','坐位躯干前屈动作示意');
  add('trunk_extension','trunk-extension-seated','坐位躯干小幅后移部位示意','generated');
  for(const [finger,name] of [['thumb','拇指'],['index','食指'],['middle','中指'],['ring','无名指'],['pinky','小指']]){
    for(const joint of finger==='thumb'?['mcp','ip']:['mcp','pip','dip']){
      add(`${finger}_${joint}_flexion`,finger+'-flexion',name+'屈曲部位示意','generated');
      add(`${finger}_${joint}_extension`,'hand-extension',name+'伸展部位示意','generated');
    }
  }
  Object.freeze(entries);
  function get(id){return typeof id==='string'&&Object.hasOwn(entries,id)?entries[id]:null;}
  root.RehabAssessmentArtwork=Object.freeze({version:'assessment-artwork-1',entries,get});
  if(typeof module!=='undefined')module.exports=root.RehabAssessmentArtwork;
})(typeof window==='undefined'?globalThis:window);
