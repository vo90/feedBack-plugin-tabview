const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../screen.js'),'utf8');
const code=source.slice(source.indexOf('function _tvApplyRhythmMap('),source.indexOf('// alphaTab 1.8.2 truncates'));
const {apply,validate,tick}=new Function('const TICKS_PER_BEAT=960;'+code+';return {apply:_tvApplyRhythmMap,validate:_tvValidatePickupClock,tick:_tvTimeToTick};')();
test('pickup cursor uses exact start and full-bar boundary',()=>{
 const c=validate([{time:.2,tick:0},{time:.95,tick:1440},{time:2.95,tick:5280}]);
 assert.equal(tick(.2,[],c),960);assert.equal(tick(.45,[],c),1440);assert.equal(tick(.95,[],c),2400);
 assert.equal(tick(1.45,[],c),3360);assert.equal(tick(0,[],c),960);
 for(const bad of [[],[{time:0,tick:0},{time:0,tick:960}],[{time:0,tick:0},{time:1,tick:0}]])assert.throws(()=>validate(bad));
});
test('pickup is marked only when written model duration matches',()=>{
 const bar={masterBar:{timeSignatureNumerator:4,timeSignatureDenominator:4},voices:[{beats:[{duration:8},{duration:8},{duration:8}]}]};
 const score={tracks:[{staves:[{bars:[bar]}]}]};
 assert.equal(apply(score,{version:1,shortDurations:[],pickups:[{bar:0,quarters:1.5}]}),true);
 assert.equal(bar.masterBar.isAnacrusis,true);
 assert.throws(()=>apply(score,{version:1,shortDurations:[],pickups:[{bar:0,quarters:2}]}));
});
