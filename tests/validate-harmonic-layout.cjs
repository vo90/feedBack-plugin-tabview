// Exercise the actual pinned alphaTab factories and model, not copied layout logic.
// Usage: node tests/validate-harmonic-layout.cjs /path/to/alphaTab-1.8.2.js
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const a=require(path.resolve(process.argv[2]));
const src=fs.readFileSync(path.join(__dirname,'../screen.js'),'utf8');
const start=src.indexOf('function _tvNeedsHarmonicBands('),end=src.indexOf('function _tvApplyHarmonicMap(',start);
const {needs,separate}=new Function(src.slice(start,end)+';return {needs:_tvNeedsHarmonicBands,separate:_tvSeparateHarmonicBands};')();
function score(kind,pm,otherVoice=false) {
    const importer=new a.importer.AlphaTexImporter();
    importer.initFromString(':4 7.3 8.3 | 9.3 10.3',new a.Settings());
    const result=importer.readScore(),bar=result.tracks[0].staves[0].bars[0],n=bar.voices[0].beats[0].notes[0];
    n.harmonicType=kind;n.harmonicValue=12;
    if(otherVoice) {
        // Same onset, different voice/string: still one visual effect column.
        const v=new a.model.Voice(),b=new a.model.Beat(),other=new a.model.Note();
        bar.addVoice(v);v.addBeat(b);b.addNote(other);b.displayStart=bar.voices[0].beats[0].displayStart;other.isPalmMute=pm;
    } else n.isPalmMute=pm;
    return result;
}
for(const kind of [a.model.HarmonicType.Artificial,a.model.HarmonicType.Tap,a.model.HarmonicType.Pinch,a.model.HarmonicType.Natural]) {
    assert.equal(needs(score(kind,false)),false);
    assert.equal(needs(score(kind,true)),true);
    assert.equal(needs(score(kind,true,true)),true);
}
assert.equal(needs(score(a.model.HarmonicType.None,true)),false);
const effects=a.Environment.defaultRenderers.flatMap(f=>f.effectBands||[]).map(b=>b.effect);
const previous=effects.map(e=>({e,share:e.canShareBand,proto:Object.getPrototypeOf(e)}));
separate(a);separate(a);
for(const {e,share,proto} of previous) {
    assert.equal(Object.getPrototypeOf(e),proto);
    assert.equal(e.canShareBand,[a.NotationElement.EffectHarmonics,a.NotationElement.EffectPalmMute].includes(e.notationElement)?false:share);
}
assert.throws(()=>separate({...a,Environment:{defaultRenderers:[]}}),/Unsupported tablature effect layout/);
console.log('Compound harmonic detection and distinct effect rows passed against pinned alphaTab; unrelated factories unchanged');
