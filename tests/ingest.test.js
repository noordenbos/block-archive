const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const context={location:{protocol:'http:'},state:{blocks:[],pendingCaptures:[]},render(){},save(){},issues(){return []},$:()=>null,notify(){},structuredClone,uid:()=>require('node:crypto').randomUUID(),footprint:()=>[[0,0],[10,0],[10,10]],fileData:null,ingestFolder:null};
Object.assign(context,{blockId:null,photoZoom:1,draft:[],renderSlides(){}});
context.FileReader=class{readAsDataURL(f){this.result='data:image/jpeg;base64,dGVzdA==';this.onload()}};
context.fetch=async(url,options)=>({ok:true,json:async()=>options.body.analysis});
context.SideDetection=require('../planner/side-detection.js');
vm.createContext(context);vm.runInContext(fs.readFileSync('planner/ingest.js','utf8'),context);vm.runInContext('render=()=>{}',context);
const file=(id,role,hash,conflict=false)=>({name:hash+'.jpg',size:100,analysis:{hash,qrValues:[id],role,labelFeatures:role==='identifier'?30:0,gridFeatures:role==='tissue'?20:70,calibration:{mmPerPx:.05},rotationDegrees:90,markerIds:[0,2,3],photo:'data:image/jpeg;base64,dGVzdA==',canonical:'data:image/jpeg;base64,dGVzdA==',identityConflict:conflict?'Wrong printed QR':undefined}});
(async()=>{
await context.ingestFolder({target:{files:[file('B','identifier','b2'),file('A','tissue','a1'),file('B','tissue','b1'),file('A','identifier','a2'),file('C','tissue','c1')]}});
assert.deepEqual(context.state.blocks.map(b=>b.name).sort(),['A','B']);assert.equal(context.state.pendingCaptures.length,1);
assert.equal(context.state.blocks[0].sources.find(s=>s.role==='tissue').name,'b1.jpg');
await context.ingestFolder({target:{files:[file('A','tissue','a1'),file('A','identifier','a2')]}});assert.equal(context.state.blocks.length,2);
await context.ingestFolder({target:{files:[file('BAD','tissue','d1',true),file('BAD','identifier','d2',true)]}});assert.equal(context.state.blocks.length,2);
const b=context.state.blocks[0];b.regions=[{id:'r',points:[[0,0],[2,0],[2,3]]}];context.save();assert.equal(b.scores.length,3);assert.deepEqual(JSON.parse(JSON.stringify(b.scores[2])),[[2,3],[0,0]]);
vm.runInContext('state.blocks[0].analysis={};state.captureBounds={maxHeight:12,minDistance:350,tolerance:1}',context);
assert.ok(context.boundaryError(b).mm<1);context.state.captureBounds.minDistance=20;assert.ok(context.boundaryError(b).mm>1);
console.log('PASS: shuffled QR grouping, role assignment, unmatched retention, duplicate protection, conflicting-label protection, polygon/scoring identity, and error threshold.');
})();
