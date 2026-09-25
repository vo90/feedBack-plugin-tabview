// Exercise the pinned renderer's actual bar glyph with precise fractional data.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const a=require(path.resolve(process.argv[2]));
const source=fs.readFileSync(path.join(__dirname,'../screen.js'),'utf8');
const start=source.indexOf('function _tvBarPitchLabel('),end=source.indexOf('// Matches rs2gp.py:',start);
const {configure,label}=new Function(source.slice(start,end)+';return {configure:_tvConfigureBarGlyphs,label:_tvBarPitchLabel};')();
for(const [value,text] of [[0,'0'],[-1,'−¼'],[2,'½'],[3,'¾'],[-4,'−1'],[5,'1¼'],[-32,'−8'],[16,'4'],[4/3,'≈0.33']])
 assert.equal(label(value),text);
const effects=a.Environment.defaultRenderers.flatMap(f=>f.effectBands||[]).map(b=>b.effect);
const before=effects.map(e=>({e,create:e.createNewGlyph,proto:Object.getPrototypeOf(e)}));
configure(a);configure(a);
for(const {e,create,proto} of before) {
 assert.equal(Object.getPrototypeOf(e),proto);
 if(e.notationElement!==a.NotationElement.EffectWhammyBarLine)assert.equal(e.createNewGlyph,create);
}
const effect=effects.find(e=>e.notationElement===a.NotationElement.EffectWhammyBarLine);
function beat(mapped=true) {
 const b=new a.model.Beat();
 for(const [offset,value] of [[0,0],[20,4/3],[40,8/3],[60,4]])b.addWhammyBarPoint(new a.model.BendPoint(offset,value));
 if(mapped)b.feedBackWhammy={version:1};return b;
}
const b=beat(),original=b.whammyBarPoints.map(p=>[p.offset,p.value]),g=effect.createNewGlyph(null,b);
assert.equal(g._renderPoints.length,2);assert.deepEqual(b.whammyBarPoints.map(p=>[p.offset,p.value]),original);
assert.equal(Object.hasOwn(effect.createNewGlyph(null,beat(false)),'_getOffset'),false,'Ordinary GP curves keep upstream behavior');
const text=[],lines=[],canvas={font:null,measureText:()=>({height:12}),fillText:(s,x,y)=>text.push({s,x,y}),
 moveTo:(x,y)=>lines.push([x,y]),lineTo:(x,y)=>lines.push([x,y]),stroke(){}};
g.renderer={scoreRenderer:{canvas},resources:{tablatureFont:{}},smuflMetrics:{tabWhammyPerHalfHeight:8,tabWhammyTextPadding:3,tabWhammyDashSize:2},
 settings:{notation:{isNotationElementVisible:()=>false}}};
g.doLayout();assert.ok(g.height>15);assert.ok(g._getOffset(.2)>0);assert.ok(g._getOffset(-.2)<0);
g._paintWhammy(true,new a.model.BendPoint(0,0),new a.model.BendPoint(60,4/3),0,50,1,canvas,'grad.');
assert.deepEqual(text.map(t=>t.s),['grad.','≈0.33']);assert.ok(lines.flat().every(Number.isFinite));
assert.equal(lines.at(-1)[1],50-g._getOffset(4/3),'Unrounded curve geometry');
assert.equal(Object.hasOwn(canvas,'fillText'),true);assert.equal(canvas.fillText.toString().includes('text.push'),true);
assert.deepEqual(b.whammyBarPoints.map(p=>[p.offset,p.value]),original);
assert.throws(()=>configure({...a,Environment:{defaultRenderers:[]}}),/Unsupported tablature bar layout/);
console.log('Pinned bar glyph: compact labels, signed fractional offsets, reserved height, exact model and unrelated factories verified');
