const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../screen.js'),'utf8');
const start=source.indexOf('function _tvApplyHarmonicMap('),end=source.indexOf('const ALPHATAB_CDN_BASE',start);
const apply=new Function(source.slice(start,end)+'; return _tvApplyHarmonicMap;')();
const model={HarmonicType:{None:0,Natural:1,Artificial:2,Pinch:3,Tap:4}};
const fallback=()=>({kind:'artificial',node:null,interval:24,policy:'harmonic',basis:'source-playback-fallback'});
function fixture() {
    const note={fret:10,string:2,isPalmMute:true};
    const beat={notes:[note],text:'BAR'};
    const score={tracks:[{staves:[{bars:[{voices:[{beats:[beat]}]}]}]}]};
    const entry={track:0,staff:0,bar:0,voice:0,beat:0,string:2,fret:10,target:fallback()};
    return {note,beat,score,entry};
}
test('unknown contact keeps the held fret and one AH instruction without a false harmonic head',()=>{
    const {score,note,beat,entry}=fixture(),before=structuredClone(entry);
    apply(score,[entry],model);apply(score,[entry],model);
    assert.equal(note.fret,10);assert.equal(note.isPalmMute,true);
    assert.equal(note.harmonicType,model.HarmonicType.None);
    assert.equal(note.harmonicValue,0); // alphaTab inactive value, not a physical node
    assert.equal(beat.text,'BAR AH');assert.equal(beat.notes.length,1);
    assert.deepEqual(note.feedBackHarmonic.target,fallback());
    assert.deepEqual(entry,before);
    note.feedBackHarmonic.target.node=5;assert.equal(entry.target.node,null);
});
test('canonical harmonic contact notation remains exact',()=>{
    const {score,note,beat,entry}=fixture();
    entry.target={kind:'artificial',node:7,interval:19,policy:'harmonic'};
    apply(score,[entry],model);
    assert.equal(note.harmonicType,model.HarmonicType.Artificial);
    assert.equal(note.harmonicValue,7);assert.equal(beat.text,'BAR');
});
test('only the complete approved fallback shape is accepted',()=>{
    const invalid=[...['kind','node','interval','policy','basis'].map(k=>h=>{delete h[k];}),
        ...[{node:0},{node:5},{kind:'pinch'},{kind:'tapped'},{interval:12},{policy:'mixed'},
            {basis:'guessed'},{extra:true}].map(p=>h=>Object.assign(h,p))];
    for(const alter of invalid) {
        const {score,entry}=fixture();alter(entry.target);
        assert.throws(()=>apply(score,[entry],model),/Unsupported harmonic mapping/);
    }
});
