// node --test addons/tests   (Video fit add-on: the pure logic, a model of the players' hole rect, and runtime.js in a fake page)
'use strict';
const test=require('node:test'),a=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const DIR=path.join(__dirname,'..','bundled','omni-video-fit'),C=require(path.join(DIR,'core.js'));

// ---------------------------------------------------------------- core
test('modes cycle in panel order and unknown modes fall back to Fit',()=>{
  a.deepEqual(C.MODES,['fit','fill','stretch','zoom110','zoom120','zoom133']);
  a.equal(C.next('fit',1),'fill');a.equal(C.next('zoom133',1),'fit');a.equal(C.next('fit',-1),'zoom133');a.equal(C.next('bogus',1),'fit');
  a.equal(C.resolve(null,null,'zoom120'),'zoom120');a.equal(C.resolve(null,'fill','zoom120'),'fill');a.equal(C.resolve('stretch','fill','zoom120'),'stretch');
  a.equal(C.resolve('x',['fill'],'nope'),'fit');
});
test('plan: Fit applies nothing, Fill is object-fit cover, Stretch is fill, Zoom is contain + scale',()=>{
  const box={w:1920,h:1080},v43={w:1440,h:1080};
  a.deepEqual(C.plan('fit',box,v43).fit,null);a.equal(C.plan('fit',box,v43).zoom,1);
  const f=C.plan('fill',box,v43);a.equal(f.fit,'cover');a.equal(f.zoom,1);a.deepEqual(f.rect,{w:1920,h:1440});
  const s=C.plan('stretch',box,v43);a.equal(s.fit,'fill');a.deepEqual(s.rect,{w:1920,h:1080});
  const z=C.plan('zoom133',box,v43);a.equal(z.fit,'contain');a.ok(Math.abs(z.zoom-4/3)<1e-9);a.deepEqual(z.rect,{w:1920,h:1440});a.equal(z.limited,false);
  // 4:3 in 16:9: Zoom 1.33 fills the width exactly, the same as Fill
  a.deepEqual(C.plan('zoom133',box,v43).rect,C.plan('fill',box,v43).rect);
  // 21:9 in 16:9: cover factor 2.37/1.78
  a.ok(Math.abs(C.coverFactor(1920,1080,2560,1080)-(2560/1080)/(1920/1080))<1e-9);
  // video size not known yet: cover on the box, re-planned on loadedmetadata
  a.deepEqual(C.plan('fill',box,{w:0,h:0}).rect,{w:1920,h:1080});
});
test('plan keeps the picture rect inside the hardware plane limits (4096 a side, 3840x2160 pixels)',()=>{
  // a 4K root view (1920 CSS px at 2 device px per CSS px): any zoom over 4096/3840 would be refused by the shell
  const box={w:1920,h:1080},v169={w:3840,h:2160};
  // full screen there: the contain rect is already 3840x2160 = the pixel cap, so no zoom at all is left
  const z=C.plan('zoom110',box,v169,{scale:2});a.equal(z.limited,true);a.equal(z.fit,'contain');a.equal(z.zoom,1);a.ok(C.fits(z.rect.w,z.rect.h),JSON.stringify(z.rect));
  const f=C.plan('fill',box,{w:1440,h:1080},{scale:2});a.equal(f.limited,true);a.equal(f.fit,'contain','held-back Fill becomes contain + the largest allowed zoom');a.ok(C.fits(f.rect.w,f.rect.h));
  // a smaller (windowed) player there: some zoom is left
  const w=C.plan('zoom133',{w:1600,h:900},v169,{scale:2});a.equal(w.limited,true);a.equal(w.zoom,1.2);a.ok(C.fits(w.rect.w,w.rect.h));
  a.equal(C.plan('zoom110',{w:1600,h:900},v169,{scale:2}).limited,false);
  const free=C.plan('zoom110',box,v169,{scale:2,keepHw:false});a.equal(free.limited,false);a.equal(free.zoom,1.1);a.ok(!C.fits(free.rect.w,free.rect.h));
  // 1080p root view: every mode fits
  for(const m of C.MODES)a.equal(C.plan(m,box,{w:1440,h:1080},{scale:1}).limited,false,m);
  a.equal(C.plan('stretch',box,v169,{scale:2}).limited,false,'stretch never grows the rect');
});
test('hole rect model: object-fit and the zoom transform both change the rect the player reports',()=>{
  // what OmniMSEPlayer/OmniProgressivePlayer::holeGeometry measure: computePaintRectForObjectViewBox(videoBox()) mapped by
  // localToAbsoluteQuad (transforms included), bounding box, rounded. A 4:3 video in a 1920x1080 full-screen element:
  const el={x:0,y:0,w:1920,h:1080},v={w:1440,h:1080};
  a.deepEqual(pick(C.holeRect(el,v,'contain',1,1)),{x:240,y:0,w:1440,h:1080},'Fit: pillarboxed picture');
  a.deepEqual(pick(C.holeRect(el,v,'cover',1,1)),{x:0,y:-180,w:1920,h:1440},'Fill: rect overflows the element (cropped by the page hole, not by the plane)');
  a.deepEqual(pick(C.holeRect(el,v,'contain',4/3,1)),{x:0,y:-180,w:1920,h:1440},'Zoom 1.33: the transform scales the reported rect');
  a.deepEqual(pick(C.holeRect(el,v,'fill',1,1)),{x:0,y:0,w:1920,h:1080},'Stretch: the element box');
  a.equal(C.holeRect(el,v,'contain',4/3,1).accepted,true);
  // a 4K root view: Zoom 1.1 on 16:9 makes a 4224-wide rect -> refused ("video rect out of range"), paint path
  a.equal(C.holeRect(el,{w:3840,h:2160},'contain',1.1,2).accepted,false);
  const p=C.plan('zoom110',el,{w:3840,h:2160},{scale:2});a.equal(C.holeRect(el,{w:3840,h:2160},p.fit,p.zoom,2).accepted,true,'the held-back zoom is accepted');
});
const pick=r=>({x:r.x,y:r.y,w:r.w,h:r.h});
test('small videos are left alone unless full screen',()=>{a.equal(C.worthIt(160,90,false),false);a.equal(C.worthIt(160,90,true),true);a.equal(C.worthIt(640,360,false),true);a.equal(C.worthIt(0,0,false),false)});
test('site keys hash the host (www and case ignored) and pruning keeps the newest 300',()=>{
  const k=C.siteKey('www.Example.com');a.equal(k,C.siteKey('example.com'));a.ok(k.startsWith(C.SITE_PREFIX)&&!k.includes('example'));a.notEqual(k,C.siteKey('example.org'));
  a.equal(C.siteKey(''),null);a.deepEqual(C.entry('fill',1700000000999),['fill',1700000000]);a.equal(C.saved(['zoom120',1]),'zoom120');a.equal(C.saved(['nope',1]),null);a.equal(C.saved('fill'),null);
  const all={other:1};for(let i=0;i<320;i++)all[C.SITE_PREFIX+'s'+i]=['fill',1000+i];all[C.SITE_PREFIX+'bad']='junk';
  const drop=C.prune(all);a.equal(drop.length,21);a.ok(drop.includes(C.SITE_PREFIX+'bad'));a.ok(drop.includes(C.SITE_PREFIX+'s19'));a.ok(!drop.includes(C.SITE_PREFIX+'s20'));a.ok(!drop.includes('other'));
});
test('the stylesheet sets only object-fit / transform on videos (nothing that takes a video off the hardware plane)',()=>{
  const css=fs.readFileSync(path.join(DIR,'addon.css'),'utf8'),videoRules=css.split('}').filter(r=>/^\s*video\[/.test(r));
  a.equal(videoRules.length,4);
  for(const r of videoRules){const body=r.slice(r.indexOf('{')+1);for(const bad of['opacity','filter','mask','clip-path','mix-blend','reflect','rotate','skew','matrix3d'])a.ok(!body.includes(bad),bad+' in '+r)}
});

// ---------------------------------------------------------------- runtime in a fake page
function fakePage(o={}){
  const listeners=new Map(),timers=new Map();let tid=0;
  const on=(t,k,f)=>{const key=t+':'+k;if(!listeners.has(key))listeners.set(key,new Set());listeners.get(key).add(f)};
  const off=(t,k,f)=>listeners.get(t+':'+k)?.delete(f);
  const fire=(t,k,ev)=>{for(const f of[...(listeners.get(t+':'+k)||[])])f(ev)};
  class El{constructor(tag){this.tagName=tag.toUpperCase();this.nodeType=1;this.attrs=new Map();this.children=[];this.parentNode=null;this.textContent='';this.clientWidth=0;this.clientHeight=0;
    const props=new Map();this.style={setProperty:(k,v)=>props.set(k,v),removeProperty:k=>props.delete(k),getPropertyValue:k=>props.get(k)??'',props};
    this.dataset=new Proxy({},{get:(_,k)=>this.attrs.get('data-'+k.replace(/[A-Z]/g,c=>'-'+c.toLowerCase())),set:(_,k,v)=>(this.attrs.set('data-'+k.replace(/[A-Z]/g,c=>'-'+c.toLowerCase()),String(v)),true)});this.ls={}}
    set className(v){this.attrs.set('class',v)}get className(){return this.attrs.get('class')||''}
    setAttribute(k,v){this.attrs.set(k,String(v))}getAttribute(k){return this.attrs.has(k)?this.attrs.get(k):null}hasAttribute(k){return this.attrs.has(k)}removeAttribute(k){this.attrs.delete(k)}
    append(...cs){for(const c of cs){if(typeof c==='string')continue;c.remove();c.parentNode=this;this.children.push(c);if(this.observed)this.observed(c)}}
    remove(){if(this.parentNode){this.parentNode.children=this.parentNode.children.filter(c=>c!==this);this.parentNode=null}}
    get isConnected(){let e=this;while(e.parentNode)e=e.parentNode;return e===doc.documentElement}
    contains(n){for(let e=n;e;e=e.parentNode)if(e===this)return true;return false}
    *walk(){for(const c of this.children){yield c;yield*c.walk()}}
    matches(sel){return sel.split(',').some(s=>match(this,s.trim()))}
    closest(sel){for(let e=this;e&&e.matches;e=e.parentNode)if(e.matches(sel))return e;return null}
    querySelectorAll(sel){return[...this.walk()].filter(e=>e.matches(sel))}querySelector(sel){return this.querySelectorAll(sel)[0]||null}
    getElementsByTagName(t){return[...this.walk()].filter(e=>e.tagName===t.toUpperCase())}
    addEventListener(t,f){(this.ls[t]||(this.ls[t]=[])).push(f)}removeEventListener(){}
    focus(){doc.activeElement=this}click(){if(this.onclick)this.onclick()}
    key(key){const ev={key,preventDefault(){},stopPropagation(){}};for(let e=this;e;e=e.parentNode)for(const f of e.ls?.keydown||[])f(ev)}}
  function match(e,s){const m=/^([a-z]*)((?:\.[\w-]+|\[[^\]]+\])*)$/i.exec(s);if(!m)throw new Error('selector '+s);if(m[1]&&e.tagName!==m[1].toUpperCase())return false;
    for(const p of m[2].match(/\.[\w-]+|\[[^\]]+\]/g)||[]){if(p[0]==='.'){if(!e.className.split(/\s+/).includes(p.slice(1)))return false;continue}
      const q=/^\[([\w-]+)(?:(~?=)"?([^"]*)"?)?\]$/.exec(p),v=e.getAttribute(q[1]);if(v===null)return false;if(q[2]==='='&&v!==q[3])return false;if(q[2]==='~='&&!v.split(/\s+/).includes(q[3]))return false}return true}
  const doc={documentElement:new El('html'),activeElement:null,fullscreenElement:null,visibilityState:'visible',readyState:'complete',
    createElement:t=>new El(t),querySelector:s=>doc.documentElement.querySelector(s),getElementsByTagName:t=>doc.documentElement.getElementsByTagName(t),querySelectorAll:s=>doc.documentElement.querySelectorAll(s),
    addEventListener:(t,f)=>on('doc',t,f),removeEventListener:(t,f)=>off('doc',t,f)};
  doc.body=new El('body');doc.documentElement.append(doc.body);
  const store=new Map(o.store||[]),settings=Object.assign({mode:'fit',keep_hw:true,button:true},o.settings),hooks={},toasts=[],writes=[];
  const api={id:'omni-video-fit',top:true,active:o.active!==false,toast:t=>(toasts.push(t),Promise.resolve()),
    settings:{get:k=>settings[k]},onEnable:f=>hooks.enable=f,onDisable:f=>hooks.disable=f,onSettings:f=>hooks.settings=f,
    storage:{get:k=>store.get(k),keys:()=>[...store.keys()],
      set:(k,v)=>{writes.push(k);if(o.private)return Promise.reject(new Error('error: private tab'));store.set(k,v);return Promise.resolve()},
      remove:k=>{writes.push('-'+k);if(o.private)return Promise.reject(new Error('error: private tab'));store.delete(k);return Promise.resolve()}}};
  let mo=null;
  const win={omniAddon:api,document:doc,location:{hostname:o.host||'www.films.example'},devicePixelRatio:o.dpr||1,
    getComputedStyle:e=>({transform:e.siteTransform||'none'}),performance:{getEntriesByType:()=>[],now:()=>0},
    MutationObserver:class{constructor(f){this.f=f}observe(){mo=this}disconnect(){if(mo===this)mo=null}},
    setTimeout:(f)=>{timers.set(++tid,f);return tid},clearTimeout:id=>timers.delete(id),
    addEventListener:(t,f)=>on('win',t,f),removeEventListener:(t,f)=>off('win',t,f),Promise,Object,Array,String,Math,Number,Set,WeakSet,Map,JSON,Error};
  win.window=win;win.globalThis=win;
  const ctx=vm.createContext(win);
  vm.runInContext(fs.readFileSync(path.join(DIR,'core.js'),'utf8'),ctx);
  const video=(w,h,vw,vh,parent=doc.body)=>{const v=new El('video');v.clientWidth=w;v.clientHeight=h;v.videoWidth=vw;v.videoHeight=vh;parent.append(v);return v};
  const page={doc,api,store,settings,hooks,toasts,writes,video,El,win,
    run(){vm.runInContext(fs.readFileSync(path.join(DIR,'runtime.js'),'utf8'),ctx)},
    timers:()=>timers.size,flush(){const fs=[...timers.values()];timers.clear();for(const f of fs)f()},
    winKey(ev){fire('win','keydown',ev)},mutate(...added){if(mo)mo.f([{addedNodes:added}])},media(type,v){fire('doc',type,{type,target:v})},
    diag:()=>win.OmniVideoFitDiagnostics(),panel:()=>doc.querySelector('aside.omni-fit-panel'),
    async settle(){for(let i=0;i<5;i++)await new Promise(r=>setImmediate(r))}};
  return page;
}
test('runtime: the site default from settings goes on every big video; tiny ones and add-on UI are left alone',()=>{
  const p=fakePage({settings:{mode:'fill'},active:true});const big=p.video(1280,720,1440,1080),tiny=p.video(120,68,640,360);p.run();
  a.equal(big.getAttribute('data-omni-fit'),'cover');a.equal(tiny.getAttribute('data-omni-fit'),null);a.equal(p.diag().videos,1);
  p.settings.mode='zoom120';p.hooks.settings();a.equal(big.getAttribute('data-omni-fit'),'contain zoom');a.equal(big.style.getPropertyValue('--omni-fit-zoom'),'1.2');
  a.equal(big.style.getPropertyValue('--omni-fit-base'),'translate(0)');
  p.settings.mode='fit';p.hooks.settings();a.equal(big.hasAttribute('data-omni-fit'),false);a.equal(big.style.getPropertyValue('--omni-fit-zoom'),'');
});
test('runtime: a page transform is kept in front of the zoom',()=>{
  const p=fakePage({settings:{mode:'zoom110'}});const v=p.video(1280,720,1920,1080);v.siteTransform='matrix(1, 0, 0, 1, 0, -10)';p.run();
  a.equal(v.style.getPropertyValue('--omni-fit-base'),'matrix(1, 0, 0, 1, 0, -10)');
  v.siteTransform='matrix(1.1, 0, 0, 1.1, 0, 0)';p.settings.mode='zoom133';p.hooks.settings();   // ours is on: the base is not re-read (no compounding)
  a.equal(v.style.getPropertyValue('--omni-fit-base'),'matrix(1, 0, 0, 1, 0, -10)');
});
test('runtime: videos added later are picked up once per burst (debounced MutationObserver), sizes on loadedmetadata',()=>{
  const p=fakePage({settings:{mode:'stretch'}});p.run();a.equal(p.timers(),0,'nothing scheduled while idle (no polling)');
  const wrap=new p.El('div');p.doc.body.append(wrap);const v=p.video(1280,720,0,0,wrap);
  p.mutate(wrap);p.mutate(wrap);p.mutate(new p.El('span'));a.equal(p.timers(),1,'one timer for the burst');a.equal(v.getAttribute('data-omni-fit'),null);
  p.flush();a.equal(v.getAttribute('data-omni-fit'),'fill');a.equal(p.timers(),0);
  const s=p.doc.createElement('span');p.mutate(s);a.equal(p.timers(),0,'non-video additions schedule nothing');
  const late=p.video(0,0,0,0);late.clientWidth=1920;late.clientHeight=1080;p.media('loadedmetadata',late);a.equal(late.getAttribute('data-omni-fit'),'fill');
});
test('runtime: the panel picks a mode; Remember for this site saves one hashed key and forgets it',async()=>{
  const p=fakePage();const v=p.video(1920,1080,1440,1080);p.run();a.equal(p.panel(),null);
  p.hooks.disable();p.hooks.enable();await p.settle();   // switched on from the quick switch with a video on the page: the panel opens
  const panel=p.panel();a.ok(panel);a.equal(panel.querySelector('[data-mode="fit"]').getAttribute('aria-pressed'),'true');
  panel.querySelector('[data-mode="zoom133"]').click();a.equal(v.getAttribute('data-omni-fit'),'contain zoom');a.equal(p.store.size,0,'not remembered yet');
  panel.querySelector('.omni-fit-remember').click();await p.settle();const k=C.siteKey('films.example');a.equal(p.store.get(k)[0],'zoom133');
  a.equal(panel.querySelector('.omni-fit-remember').getAttribute('aria-pressed'),'true');
  panel.querySelector('[data-mode="fill"]').click();await p.settle();a.equal(p.store.get(k)[0],'fill');
  // a new page on the same site starts with the saved choice and the switch on
  const q=fakePage({store:p.store});const w=q.video(1920,1080,1440,1080);q.run();a.equal(w.getAttribute('data-omni-fit'),'cover');a.equal(q.diag().remember,true);
  panel.querySelector('.omni-fit-remember').click();await p.settle();a.equal(p.store.has(k),false);a.equal(v.getAttribute('data-omni-fit'),'cover','the page keeps its choice');
  panel.querySelector('.omni-fit-done').click();a.equal(p.panel(),null);
});
test('runtime: private tab - the host refuses the write; the choice lasts for this page only',async()=>{
  const p=fakePage({private:true});const v=p.video(1920,1080,2560,1080);p.run();
  p.doc.body.focus();p.hooks.disable();p.hooks.enable();await p.settle();const panel=p.panel();
  panel.querySelector('[data-mode="zoom120"]').click();panel.querySelector('.omni-fit-remember').click();await p.settle();
  a.equal(p.store.size,0);a.equal(p.diag().writable,false);a.equal(p.diag().privateTab,true);a.equal(p.diag().mode,'zoom120');a.equal(v.getAttribute('data-omni-fit'),'contain zoom');
  a.match(panel.querySelector('.omni-fit-note').textContent,/Private tab: kept for this page only/);
  const n=p.writes.length;panel.querySelector('[data-mode="fill"]').click();await p.settle();a.equal(p.writes.length,n,'no more write attempts once refused');
  a.equal(v.getAttribute('data-omni-fit'),'cover');
});
test('runtime: keys - Alt+Shift+F opens the panel, arrows move, Escape closes; full-screen <video> cycles with a toast',async()=>{
  const p=fakePage();const v=p.video(1920,1080,1440,1080);p.run();
  const key=code=>p.winKey({code,altKey:true,shiftKey:true,isTrusted:true,repeat:false,preventDefault(){},stopImmediatePropagation(){}});
  p.hooks.disable();p.hooks.enable();a.ok(p.panel(),'live switch-on opened it');p.panel().querySelector('.omni-fit-done').click();a.equal(p.panel(),null);
  key('KeyF');const panel=p.panel();a.ok(panel);const first=p.doc.activeElement;a.equal(first.dataset.mode,'fit');
  first.key('ArrowRight');a.equal(p.doc.activeElement.dataset.mode,'fill');p.doc.activeElement.key('Escape');a.equal(p.panel(),null);
  p.doc.fullscreenElement=v;key('KeyF');a.equal(p.panel(),null);a.deepEqual(p.toasts,['Video fit: Fill (crop)']);a.equal(v.getAttribute('data-omni-fit'),'cover');
});
test('runtime: the Fit button shows once per video when a big one starts and goes after 5 s',()=>{
  const p=fakePage();const v=p.video(1920,1080,1440,1080);p.run();p.media('playing',v);
  const pill=p.doc.querySelector('button.omni-fit-pill');a.ok(pill);a.equal(pill.textContent,'Video fit: Fit');p.flush();a.equal(p.doc.querySelector('button.omni-fit-pill'),null);
  p.media('playing',v);a.equal(p.doc.querySelector('button.omni-fit-pill'),null,'once per video');
  const q=fakePage({settings:{button:false}});const w=q.video(1920,1080,1440,1080);q.run();q.media('playing',w);a.equal(q.doc.querySelector('button.omni-fit-pill'),null);
});
test('runtime: switching off removes every trace and the observer',()=>{
  const p=fakePage({settings:{mode:'zoom133'}});const v=p.video(1920,1080,1440,1080);p.run();a.ok(v.hasAttribute('data-omni-fit'));
  p.hooks.disable();a.equal(v.hasAttribute('data-omni-fit'),false);a.equal(v.style.props.size,0);a.equal(p.diag().enabled,false);
  p.mutate(p.video(1920,1080,1,1));a.equal(p.timers(),0);
});
test('runtime: a 4K root view holds the zoom back and says so',async()=>{
  const p=fakePage({dpr:2,settings:{mode:'zoom133'}});const v=p.video(1600,900,3840,2160),full=p.video(1920,1080,3840,2160);p.run();
  a.equal(v.style.getPropertyValue('--omni-fit-zoom'),'1.2');a.equal(p.diag().limited,true);
  a.equal(full.getAttribute('data-omni-fit'),'contain','full screen at 4K: no zoom fits the plane');a.equal(full.style.getPropertyValue('--omni-fit-zoom'),'');
  p.settings.keep_hw=false;p.hooks.settings();a.ok(Math.abs(Number(v.style.getPropertyValue('--omni-fit-zoom'))-4/3)<1e-9);a.equal(p.diag().limited,false);
});
