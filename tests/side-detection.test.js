const assert=require('node:assert/strict'),fs=require('node:fs');
const {chooseSides}=require('../planner/side-detection.js');
for(const c of JSON.parse(fs.readFileSync('tests/side-decisions.json','utf8'))){const result=chooseSides(c.analyses);assert.equal(result?.identifier??null,c.identifier,c.name)}
assert.equal(chooseSides([]),null);
assert.equal(chooseSides([{labelFeatures:NaN},{labelFeatures:0}]),null);
console.log('PASS: side detector parity, legacy projects, opposite ordering, two-label rejection, conflicts and abstention.');
