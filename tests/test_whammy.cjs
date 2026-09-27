const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../screen.js'),'utf8');
const apply=new Function(source.slice(source.indexOf('function _tvApplyWhammyMap('),source.indexOf('function _tvBarPitchLabel('))+';return _tvApplyWhammyMap;')();
const model={WhammyType:{None:0},VibratoType:{Wide:2,Slight:1},BendPoint:class {constructor(offset,value){Object.assign(this,{offset,value});}}};
function fixture(){
 const notes=Array.from({length:4},()=>({string:6,fret:12,isTieDestination:false}));
 notes[1].isTieDestination=notes[2].isTieDestination=true;
 notes[1].tieOrigin=notes[0];notes[2].tieOrigin=notes[1];
 const beats=notes.map(n=>({notes:[n],addWhammyBarPoint(p){(this.whammyBarPoints ||= []).push(p);}}));
 const score={tracks:[{staves:[{bars:[{voices:[{beats}]}]}]}]};
 const entry=i=>({track:0,staff:0,bar:0,voice:0,beat:i,string:6,fret:12,sourceId:'source:0',time:0,sustain:2,
  expression:{version:1,policy:'optional',segments:[{start:0,end:2,curve:[{t:0,v:0},{t:2,v:-2}]}]}});
 const mapping={version:1,notes:[0,1,2].map(entry),beats:[0,1,2].map(beat=>({track:0,staff:0,bar:0,voice:0,beat,
  members:['source:0'],points:[{position:0,semitones:0},{position:60,semitones:-2}],vibrato:null}))};
 return {score,mapping,notes,beats,entry};
}
test('one source maps to an attack and multiple connected ties, independent of order',()=>{
 const {score,mapping,notes,beats}=fixture();mapping.notes.reverse();
 const original=JSON.stringify(mapping);apply(score,mapping,model);
 assert.equal(JSON.stringify(mapping),original);
 for(let i=0;i<3;i++){
  assert.equal(notes[i].feedBackWhammy.sourceId,'source:0');
  assert.deepEqual(beats[i].whammyBarPoints.map(p=>[p.offset,p.value]),[[0,0],[60,-4]]);
 }
 assert.equal(notes[3].feedBackWhammy,undefined);
});
for(const [name,mutate] of Object.entries({
 'duplicate address':f=>f.mapping.notes.push(f.mapping.notes[0]),
 'unrelated same-fret attack':f=>f.mapping.notes.push(f.entry(3)),
 'disconnected tie':f=>{f.notes[2].tieOrigin=f.notes[3];},
 'missing intermediate tie':f=>f.mapping.notes.splice(1,1),
 'missing owning attack':f=>f.mapping.notes.shift(),
 'tie cycle':f=>{f.notes[1].tieOrigin=f.notes[2];},
 'source time changed':f=>{f.mapping.notes[1].time=.01;},
 'source sustain changed':f=>{f.mapping.notes[1].sustain=3;},
 'source expression changed':f=>{f.mapping.notes[1].expression.segments[0].curve[1].v=-3;},
 'fret changed':f=>{f.mapping.notes[1].fret=13;},
 'unknown beat member':f=>{f.mapping.beats[2].members=['other'];},
 'invalid last beat curve':f=>{f.mapping.beats[2].points[1].semitones=99;},
 'duplicate display beat':f=>f.mapping.beats.push(f.mapping.beats[0]),
}))test(name+' is rejected before any score mutation',()=>{
 const f=fixture();mutate(f);assert.throws(()=>apply(f.score,f.mapping,model));
 for(const n of f.notes)assert.equal(n.feedBackWhammy,undefined);
 for(const b of f.beats){assert.equal(b.feedBackWhammy,undefined);assert.equal(b.whammyBarPoints,undefined);}
});
test('ordinary single-source mapping and absent mapping still work',()=>{
 const f=fixture();f.mapping.notes.length=1;f.mapping.beats.length=1;
 assert.equal(apply(f.score,null,model),f.score);apply(f.score,f.mapping,model);
 assert.equal(f.notes[0].feedBackWhammy.sourceId,'source:0');
});
