/* V5.2 presentation helpers. No report values, identifiers or attachments are forwarded. */
'use strict';
const RehabV52={
  score(value){if(!['number','string'].includes(typeof value)||String(value).trim()==='')return null;const n=Number(value);return Number.isInteger(n)&&n>=0&&n<=10?n:null;},
  context(page,exerciseId,exerciseName,metric=''){
    return {page:['action','assessment','training'].includes(page)?page:'action',exerciseId:String(exerciseId||'').slice(0,80),exerciseName:String(exerciseName||'动作').slice(0,60),metric:String(metric||'').slice(0,80)};
  },
  question(c){
    if(c.page==='action')return `${c.exerciseName}动作需要注意什么？请解释一般注意事项，不代替专业动作指导。`;
    if(c.metric==='视频角度变化')return `${c.exerciseName}的视频角度变化代表什么？与临床关节活动度有什么区别？`;
    if(c.metric==='完整动作')return `如何理解${c.exerciseName}训练中“完整动作”和“已达计划次数”的区别？`;
    return c.page==='training'?`如何理解本次${c.exerciseName}训练的结果？请解释指标含义，不生成康复处方。`:`如何理解${c.exerciseName}活动度评估的指标？`;
  }
};
// Capture the native object before the existing history() page controller shadows it.
const RehabHistoryV52=typeof window!=='undefined'?window.history:null;
if(typeof module!=='undefined'&&module.exports)module.exports=RehabV52;
