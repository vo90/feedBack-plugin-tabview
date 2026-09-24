// Run with a generated test bundle and the pinned alphaTab runtime file.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const a=require(path.resolve(process.argv[3]));
const source=fs.readFileSync(path.join(__dirname,'../screen.js'),'utf8');
const start=source.indexOf('function _tvApplyHarmonicMap('),end=source.indexOf('const ALPHATAB_CDN_BASE',start);
const apply=new Function(source.slice(start,end)+'; return _tvApplyHarmonicMap;')();
const bundle=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const score=a.importer.ScoreLoader.loadScoreFromBytes(new Uint8Array(Buffer.from(bundle.gp5,'base64')));
apply(score,bundle.harmonics,a.model);
const kinds={pinch:a.model.HarmonicType.Pinch,artificial:a.model.HarmonicType.Artificial,
    tapped:a.model.HarmonicType.Tap,semi:a.model.HarmonicType.Pinch,feedback:a.model.HarmonicType.None};
for(const e of bundle.harmonics){
    const n=score.tracks[e.track].staves[e.staff].bars[e.bar].voices[e.voice].beats[e.beat].notes.find(n=>n.string===e.string);
    assert.equal(n.fret,e.fret);assert.equal(n.isGhost,true);
    assert.equal(n.harmonicType,e.target?kinds[e.target.kind]:a.model.HarmonicType.Natural);
    assert.equal(n.harmonicValue,e.target?(e.target.kind==='feedback'?0:e.target.node):e.naturalNode);
    assert.equal(n.feedBackHarmonic.sourceId,e.sourceId);
}
assert.throws(()=>apply(score,[{...bundle.harmonics[0],fret:99}],a.model));
assert.throws(()=>apply(score,[bundle.harmonics[0],bundle.harmonics[0]],a.model));
console.log(`${bundle.harmonics.length} harmonic notes mapped in pinned alphaTab; drift and duplicate mappings rejected`);
