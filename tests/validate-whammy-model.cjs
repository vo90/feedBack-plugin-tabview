const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const a=require(path.resolve(process.argv[3]));
const source=fs.readFileSync(path.join(__dirname,'../screen.js'),'utf8');
const start=source.indexOf('function _tvApplyWhammyMap('),end=source.indexOf('// Matches rs2gp.py:',start);
const apply=new Function(source.slice(start,end)+'; return _tvApplyWhammyMap;')();
const bundle=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const score=a.importer.ScoreLoader.loadScoreFromBytes(new Uint8Array(Buffer.from(bundle.gp5,'base64')));
const rhythmStart=source.indexOf('function _tvApplyRhythmMap('),rhythmEnd=source.indexOf('function _tvTimeToTick(',rhythmStart);
const rhythm=new Function(source.slice(rhythmStart,rhythmEnd)+';return _tvApplyRhythmMap;')();
if(rhythm(score,bundle.rhythm))score.finish(new a.Settings());
apply(score,bundle.whammy,a.model);
for(const e of bundle.whammy.notes) {
 const note=score.tracks[e.track].staves[e.staff].bars[e.bar].voices[e.voice].beats[e.beat].notes.find(n=>n.string===e.string);
 assert.deepEqual(note.feedBackWhammy,e);
}
for(const e of bundle.whammy.beats) {
 const beat=score.tracks[e.track].staves[e.staff].bars[e.bar].voices[e.voice].beats[e.beat];
 assert.deepEqual((beat.whammyBarPoints||[]).map(p=>[p.offset,p.value]),e.points.map(p=>[p.position,p.semitones*2]));
 assert.deepEqual(beat.feedBackWhammy.members,e.members);
}
const bad=structuredClone(bundle.whammy);bad.notes[0].fret=99;
assert.throws(()=>apply(score,bad,a.model));
const duplicate=structuredClone(bundle.whammy);duplicate.notes.push(duplicate.notes[0]);
assert.throws(()=>apply(score,duplicate,a.model));
const members=structuredClone(bundle.whammy);members.beats[0].members=['wrong'];
assert.throws(()=>apply(score,members,a.model));
console.log(`${bundle.whammy.beats.length} exact beat curves mapped into alphaTab; identity drift rejected`);
