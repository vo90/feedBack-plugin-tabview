// Run with a generated test bundle and the pinned alphaTab runtime file.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
// Expose the pinned library's real worker serializer inside this test module
// only; alphaTab does not export it publicly. No vendor file is changed.
const vendorPath=path.resolve(process.argv[3]),vendorSource=fs.readFileSync(vendorPath,'utf8');
const marker='exports.json = _jsonbarrel;';assert.ok(vendorSource.includes(marker));
const vendor=new (require('node:module'))(vendorPath,module);
vendor.filename=vendorPath;vendor.paths=module.paths;
vendor._compile(vendorSource.replace(marker,marker+' exports.testJsonConverter = JsonConverter;'),vendorPath);
const a=vendor.exports;
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
    const fallback=e.target?.basis==='source-playback-fallback';
    assert.equal(n.harmonicType,fallback?a.model.HarmonicType.None:e.target?kinds[e.target.kind]:a.model.HarmonicType.Natural);
    assert.equal(n.harmonicValue,e.target?(fallback||e.target.kind==='feedback'?0:e.target.node):e.naturalNode);
    if(fallback) {
        assert.equal(n.feedBackHarmonic.target.node,null);
        assert.equal(n.feedBackHarmonic.target.interval,24);
        assert.ok(n.beat.text.split(/\s+/).includes('AH'));
        // This is alphaTab's worker serialization path: the instruction must
        // survive even though our diagnostic sidecar is not native notation.
        const cloned=a.testJsonConverter.jsObjectToScore(a.testJsonConverter.scoreToJsObject(score),new a.Settings());
        const copy=cloned.tracks[e.track].staves[e.staff].bars[e.bar].voices[e.voice].beats[e.beat];
        assert.ok(copy.text.split(/\s+/).includes('AH'));
        assert.equal(copy.notes.find(n=>n.string===e.string).fret,e.fret);
    }
    assert.equal(n.feedBackHarmonic.sourceId,e.sourceId);
}
assert.throws(()=>apply(score,[{...bundle.harmonics[0],fret:99}],a.model));
assert.throws(()=>apply(score,[bundle.harmonics[0],bundle.harmonics[0]],a.model));
console.log(`${bundle.harmonics.length} harmonic notes mapped in pinned alphaTab; drift and duplicate mappings rejected`);
