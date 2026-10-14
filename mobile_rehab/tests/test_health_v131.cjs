'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const H=require('../static/health-v131.js');
test('approved order is exactly the existing ten metric IDs',()=>{
 assert.deepEqual(H.metrics.map(m=>m[0]),['steps','restingHr','spo2','sleepHours','walkSpeed','weight','systolic','diastolic','bloodGlucose','nightWakes']);
});
test('missing, null, malformed and non-finite values never become a normal zero',()=>{
 const samples=[null,undefined,'',NaN,Infinity,'62',-1,100001].map(value=>({metric:'weight',value,timestamp:'2026-10-13'}));
 assert.equal(H.rows({state:{healthData:{measurements:samples}}},'weight').length,0);
 assert.equal(H.format(H.metrics[0],null),'未记录');assert.deepEqual(H.rows({},'steps'),[]);
});
test('zero is a valid latest observation; dates and sources survive without mutation',()=>{
 const samples=[{metric:'steps',value:500,timestamp:'2026-10-12T12:00:00Z',source:'device'},{metric:'steps',value:0,timestamp:'2026-10-13T12:00:00Z',source:'manual'},{metric:'weight',value:60,timestamp:'2026-10-14T12:00:00Z'}];
 const before=JSON.stringify(samples),result=H.rows({state:{healthData:{measurements:samples}}},'steps');
 assert.equal(result[0].value,0);assert.equal(result.length,2);assert.equal(H.source(result[0]),'手动记录');assert.equal(JSON.stringify(samples),before);
});
test('a long fast gesture only advances one item, vertical gesture does not, ends are bounded',()=>{
 assert.equal(H.step(0,-900,0),1);assert.equal(H.step(5,800,0),4);assert.equal(H.step(3,-100,200),3);
 assert.equal(H.step(0,500,0),0);assert.equal(H.step(9,-500,0),9);assert.equal(H.step(2,-20,0),2);
});
test('metric precision preserves walk speed; unknown source remains honest',()=>{
 assert.equal(H.format(H.metrics[4],.92),'0.92');assert.equal(H.format(H.metrics[5],62.25),'62.25');assert.equal(H.format(H.metrics[0],0),'0');assert.equal(H.source({}),'来源未记录');assert.equal(H.source({source:'custom-import'}),'custom-import');
});
test('AI prefill contains only a metric name and never sends personal values',()=>{
 assert.equal(H.question(''),'');assert.match(H.question('血糖'),/血糖/);assert.match(H.question('血糖'),/不作诊断/);assert.doesNotMatch(H.question('血糖'),/5\.6|TEST|林女士|报告/);
});
