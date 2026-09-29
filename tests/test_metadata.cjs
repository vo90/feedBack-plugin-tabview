const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../screen.js'),'utf8');
const apply=new Function(source.slice(source.indexOf('function _tvApplyMetadata('),source.indexOf('function _tvLoadScript('))+'; return _tvApplyMetadata;')();
function score(){return {title:'Proxy',artist:'Artist',album:'Album',tracks:[{name:'Lead',staves:[{notes:[{fret:7,time:1}]}]}]};}
function metadata(){return {version:1,title:'東京 🎸',artist:'Björk — Привет',album:'’lĕh-’nérd',trackName:'長い名前'.repeat(40)};}

test('restores complete Unicode and long names without touching score data',()=>{
 const s=score(),m=metadata(),staves=s.tracks[0].staves,before=structuredClone(staves),original=structuredClone(m);
 apply(s,m);
 for(const k of ['title','artist','album'])assert.equal(s[k],m[k]);
 assert.equal(s.tracks[0].name,m.trackName);assert.equal(s.tracks[0].staves,staves);
 assert.equal(s.tracks[0].shortName,Array.from(m.trackName).slice(0,10).join(''));
 assert.deepEqual(staves,before);assert.deepEqual(m,original);
});
test('abbreviated Unicode labels do not retain the GP5 fallback or split emoji',()=>{
 const s=score(),m={...metadata(),trackName:'123456789🎸 Lead'};
 s.tracks[0].shortName='old fallback';apply(s,m);assert.equal(s.tracks[0].shortName,'123456789🎸');
});
test('absent sidecars preserve legacy labels',()=>{
 const s=score(),before=structuredClone(s);apply(s);apply(s,null);assert.deepEqual(s,before);
});
test('validates all fields and single-track identity before any metadata mutation',()=>{
 for(const m of [{...metadata(),version:2},{...metadata(),trackName:null},{...metadata(),title:{}},{},'text']){
  const s=score(),before=structuredClone(s);assert.throws(()=>apply(s,m),/metadata/);assert.deepEqual(s,before);
 }
 for(const tracks of [[],[{},{}]]){const s={...score(),tracks};const before=structuredClone(s);assert.throws(()=>apply(s,metadata()));assert.deepEqual(s,before);}
});
