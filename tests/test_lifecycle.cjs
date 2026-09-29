const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const code=fs.readFileSync(path.join(__dirname,'../screen.js'),'utf8');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function harness(){
 function element(){return {style:{visibility:''},dataset:{},children:[],clientHeight:800,
  appendChild(e){e.parentElement=this;this.children.push(e);},setAttribute(){},querySelector(){return null;},
  querySelectorAll(selector){return this.children.filter(e=>'.'+e.className===selector);},
  remove(){if(this.parentElement)this.parentElement.children=this.parentElement.children.filter(e=>e!==this);},
  scrollTo(){}};}
 const player=element(),canvases=[element(),element()],panels=[element(),element()],apis=[],visibility=[],timers=new Map(),imports=[];
 const event=()=>({on(fn){this.fn=fn;},emit(value){this.fn?.(value);}});
 const alphaTab={Settings:class {fillFromJson(s){this.importer=s.importer;}},LayoutMode:{Page:0},
  importer:{ScoreLoader:{loadScoreFromBytes(bytes,settings){const score={tracks:[{name:'GP5 fallback',staves:[]}]};imports.push({settings,score});return score;}}},
  AlphaTabApi:class {
   constructor(){this.scoreLoaded=event();this.renderFinished=event();this.error=event();apis.push(this);}
   load(){} destroy(){this.destroyed=true;}
  }};
 let fetcher=async()=>({ok:true,headers:{get:()=>''},arrayBuffer:async()=>new ArrayBuffer(0)}),timerId=0;
 const sandbox={console:{warn(){},error(){},log(){}},alphaTab,crypto:require('node:crypto').webcrypto,atob,
  document:{getElementById:id=>id==='player'?player:null,createElement:element},
  fetch:(...args)=>fetcher(...args),getComputedStyle:()=>({position:'relative'}),
  setTimeout:fn=>{timers.set(++timerId,fn);return timerId;},clearTimeout:id=>timers.delete(id),
  requestAnimationFrame:()=>1,cancelAnimationFrame(){},addEventListener(){},removeEventListener(){},
  highway:{setVisible:v=>visibility.push(v)}};
 sandbox.window=sandbox;vm.runInNewContext(code,sandbox);
 return {sandbox,apis,player,canvases,panels,visibility,timers,imports,
  renderer:()=>sandbox.feedBackViz_tabview(),fetch:fn=>{fetcher=fn;},
  bundle:{songInfo:{filename:'fixture.feedpak',arrangement_index:0},beats:[]}};
}

test('bundle initialization uses Windows-1252 and restores Unicode before rendering',async()=>{
 const h=harness(),r=h.renderer(),metadata={version:1,title:'東京 🎸',artist:'Björk',album:'lĕh',trackName:'Lead — ギター'};
 const bytes=Buffer.from('synthetic GP5'),bundle={version:1,gp5:bytes.toString('base64'),
  sha256:require('node:crypto').createHash('sha256').update(bytes).digest('hex'),metadata};
 h.fetch(async()=>({ok:true,headers:{get:()=> 'application/json'},json:async()=>bundle}));
 r.init(h.canvases[0],h.bundle);
 for(let i=0;i<100&&!h.apis.length;i++)await tick();
 assert.equal(h.apis.length,1);
 assert.equal(h.imports[0].settings.importer.encoding,'windows-1252');
 assert.equal(h.imports[0].score.album,metadata.album);
 assert.equal(h.imports[0].score.title,metadata.title);
 assert.equal(h.imports[0].score.artist,metadata.artist);
 assert.equal(h.imports[0].score.tracks[0].name,metadata.trackName);
 h.apis[0].renderFinished.emit();await r.readyPromise;r.destroy();
});
test('fetch failure rejects readiness, reaches draw fallback and retains a timed notice through destroy',async()=>{
 const h=harness();h.fetch(async()=>{throw Error('test fetch failed');});const r=h.renderer();r.init(h.canvases[0],h.bundle);
 await assert.rejects(r.readyPromise,/test fetch failed/);assert.throws(()=>r.draw(h.bundle),/test fetch failed/);
 r.destroy();assert.equal(h.canvases[0].style.visibility,'');
 assert.ok(h.player.children.some(e=>e.className==='tabview-error-banner'));
 for(const fn of h.timers.values())fn();assert.equal(h.player.children.length,0);
});
test('success resolves readiness; late render error reaches the owning draw fallback',async()=>{
 const h=harness(),r=h.renderer();r.init(h.canvases[0],h.bundle);await tick();
 h.apis[0].renderFinished.emit();await r.readyPromise;
 assert.equal(h.canvases[0].style.visibility,'hidden');
 h.apis[0].error.emit(Error('late layout failure'));
 assert.throws(()=>r.draw(h.bundle),/late layout failure/);assert.equal(h.canvases[0].style.visibility,'');
 h.apis[0].renderFinished.emit();assert.equal(h.canvases[0].style.visibility,'','stale completion cannot cover the fallback');
 r.destroy();
});
test('superseded fetch cannot reject the replacement initialization',async()=>{
 const h=harness(),r=h.renderer();let failOld;h.fetch(()=>new Promise((_,reject)=>{failOld=reject;}));
 r.init(h.canvases[0],h.bundle);const previous=r.readyPromise;await tick();
 h.fetch(async()=>({ok:true,headers:{get:()=>''},arrayBuffer:async()=>new ArrayBuffer(0)}));
 r.init(h.canvases[0],h.bundle);await assert.rejects(previous,/superseded/);failOld(Error('old failure'));await tick();
 h.apis[0].renderFinished.emit();await r.readyPromise;assert.doesNotThrow(()=>r.draw(h.bundle));r.destroy();
});
test('failed renderer can be reselected and initialize successfully',async()=>{
 const h=harness(),r=h.renderer();h.fetch(async()=>{throw Error('failed');});r.init(h.canvases[0],h.bundle);
 await assert.rejects(r.readyPromise);r.destroy();
 h.fetch(async()=>({ok:true,headers:{get:()=>''},arrayBuffer:async()=>new ArrayBuffer(0)}));r.init(h.canvases[0],h.bundle);await tick();
 h.apis[0].renderFinished.emit();await r.readyPromise;assert.doesNotThrow(()=>r.draw(h.bundle));r.destroy();
});
test('new successful instance removes the retired instance notice on its own surface',async()=>{
 const h=harness(),failed=h.renderer();h.fetch(async()=>{throw Error('failed');});failed.init(h.canvases[0],h.bundle);
 await assert.rejects(failed.readyPromise);failed.destroy();assert.equal(h.player.querySelectorAll('.tabview-error-banner').length,1);
 h.fetch(async()=>({ok:true,headers:{get:()=>''},arrayBuffer:async()=>new ArrayBuffer(0)}));
 const replacement=h.renderer();replacement.init(h.canvases[0],h.bundle);await tick();h.apis[0].renderFinished.emit();await replacement.readyPromise;
 assert.equal(h.player.querySelectorAll('.tabview-error-banner').length,0);replacement.destroy();
});
test('failure stays scoped to its panel and does not fail another TabView instance',async()=>{
 const h=harness();h.sandbox.slopsmithSplitscreen={isActive:()=>true,panelChromeFor:c=>h.panels[h.canvases.indexOf(c)]};
 const a=h.renderer(),b=h.renderer();a.init(h.canvases[0],h.bundle);b.init(h.canvases[1],h.bundle);await tick();
 h.apis[0].error.emit(Error('panel one failed'));await assert.rejects(a.readyPromise,/panel one failed/);
 h.apis[1].renderFinished.emit();await b.readyPromise;
 assert.throws(()=>a.draw(h.bundle));assert.doesNotThrow(()=>b.draw(h.bundle));
 assert.equal(h.canvases[1].style.visibility,'hidden');assert.ok(!h.visibility.includes(false));
 a.destroy();b.destroy();
});
