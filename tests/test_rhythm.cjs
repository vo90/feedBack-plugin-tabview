const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../screen.js'),'utf8');
const helpers=source.slice(source.indexOf('function _tvApplyRhythmMap('),source.indexOf('// Factory —'));
const {apply,timeline}=new Function('const TICKS_PER_BEAT=960;'+helpers+';return {apply:_tvApplyRhythmMap,timeline:_tvBuildRhythmTimeline};')();
function score(beats,start=0){return {tracks:[{staves:[{bars:[{masterBar:{start},voices:[{beats}]}]}]}]}}
const beat=(duration,extra={})=>({duration,dots:0,graceType:0,tupletNumerator:-1,tupletDenominator:-1,notes:[],...extra});

test('ordinary beat positions and identities are unchanged',()=>{
 const beats=[beat(4,{absoluteDisplayStart:0}),beat(8,{absoluteDisplayStart:960})];
 assert.deepEqual(timeline(score(beats)),beats.map(b=>({beat:b,start:b.absoluteDisplayStart})));
});
test('seventuplet cursor boundaries accumulate before rounding',()=>{
 const beats=Array.from({length:56},()=>beat(128,{tupletNumerator:7,tupletDenominator:4}));
 const before=JSON.stringify(beats),entries=timeline(score(beats,3840));
 entries.forEach((e,i)=>assert.ok(Math.abs(e.start-(3840+i*960/56))<=.5));
 assert.equal(JSON.stringify(beats),before,'must not modify alphaTab geometry/model');
});
test('128th mapping is identity checked and leaves other beats alone',()=>{
 const target=beat(4,{notes:[{string:6,fret:7}]}),ordinary=beat(4);
 const s=score([target,ordinary]);
 const entry={bar:0,voice:0,beat:0,value:128,notes:[{string:6,fret:7,dead:false}]};
 assert.equal(apply(s,undefined),false);
 assert.equal(apply(s,{version:1,shortDurations:[entry]}),true);
 assert.equal(target.duration,128);assert.equal(ordinary.duration,4);
 for(const entries of [[{...entry,value:64}],[{...entry,notes:[{string:6,fret:8}]}],[entry,entry]])
  assert.throws(()=>apply(s,{version:1,shortDurations:entries}));
});
test('grace timing uses existing renderer positions',()=>{
 const beats=[beat(32,{graceType:1,absoluteDisplayStart:0}),beat(8,{absoluteDisplayStart:0})];
 assert.deepEqual(timeline(score(beats)).map(e=>e.start),[0,0]);
});
function cursorHarness(){
 const code=source.slice(source.indexOf('    function _tvSyncCursor('),source.indexOf('    // ── Self-driven cursor loop'));
 const run=new Function(`
 const TICKS_PER_BEAT=960,_tvApi={},_tvReady=true,_tvLatestBeats=[];
 let _tvLastTick=-1,_tvLastBeat=null,_tvLastBounds=null,calls=0;
 const beats=[{}, {}, {}];
 const _tvTimeToTick=t=>t;
 const _tvFindBeatAtTick=t=>beats[Math.min(2,Math.floor(t/15))];
 const _tvUpdateMarker=()=>calls++;
 ${code}
 return {run:times=>{times.forEach(_tvSyncCursor);return calls;},bounds:value=>{_tvApi.boundsLookup=value;}};`)();
 return run;
}
test('small paused seeks update marker and same-beat ticks avoid layout work',()=>{
 assert.equal(cursorHarness().run([960,975,976,990,975]),4);
});
test('paused cursor follows replacement layout bounds without repeated layout work',()=>{
 const h=cursorHarness();h.bounds({});assert.equal(h.run([975,975]),1);
 h.bounds(null);assert.equal(h.run([975]),2);
 h.bounds({});assert.equal(h.run([975,975,976]),3);
});
