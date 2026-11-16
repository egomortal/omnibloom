// node addons/tests/page-outline.test.cjs   (Page outline add-on: outline finder on mini-dom, then the page glue on a fake page)
'use strict';
const test=require('node:test'),a=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const C=require('../bundled/omni-page-outline/core.js'),{parse}=require('./mini-dom.cjs');
const DIR=path.join(__dirname,'..','bundled','omni-page-outline');
const PAGE=`<html><body>
<nav aria-label="Site menu"><a href="/">Home</a></nav>
<main><article><h1>Harbour   bridge
 reopens</h1><p>Intro.</p>
<h2>What changes <a href="#x" aria-hidden="true">¶</a></h2><p>Text</p>
<h3>For drivers</h3><h4>Tolls</h4><h5>Too deep</h5><h6>Deeper</h6>
<h2 hidden>Hidden attr</h2><div aria-hidden="true"><h2>Ghost</h2></div><div inert><h3>Inert</h3></div>
<h2>   </h2><h3><img src="x.png"></h3><h2 aria-label="Labelled only"></h2>
<section><h2>Unnamed section heading</h2></section>
<section aria-labelledby="c-h"><h2 id="c-h">Comments</h2></section>
<div role="heading" aria-level="2">Div heading</div><div role="heading" aria-level="6">Deep div</div>
<h2 class="css-hidden">Display none</h2>
<template><h2>In template</h2></template><script>"<h2>no</h2>"</script>
<div data-omni-addon="other"><h2>Other add-on UI</h2></div>
</article></main>
<div role="region" title="Related">r</div><div role="navigation"><h3>Footer links</h3></div>
</body></html>`;
const byIdIn=doc=>id=>{const stack=[doc];while(stack.length){const n=stack.pop();if(n.getAttribute&&n.getAttribute('id')===id)return n;stack.push(...(n.childNodes||[]))}return null};

test('outline: h1-h4 and landmarks in document order; hidden, empty, deep, skipped and add-on UI left out',()=>{
  const doc=parse(PAGE),r=C.collect(doc.body,{byId:byIdIn(doc),isHidden:el=>el.getAttribute('class')==='css-hidden'});
  a.equal(r.truncated,false);
  a.deepEqual(r.items.map(i=>[i.kind,i.depth,i.text]),[
    ['landmark',0,'Site menu'],['landmark',0,'Harbour bridge reopens'],['landmark',0,'Harbour bridge reopens'],
    ['heading',0,'Harbour bridge reopens'],['heading',1,'What changes'],['heading',2,'For drivers'],['heading',3,'Tolls'],
    ['heading',1,'Labelled only'],['heading',1,'Unnamed section heading'],['landmark',0,'Comments'],['heading',1,'Comments'],['heading',1,'Div heading'],
    ['landmark',0,'Related'],['landmark',0,'Footer links'],['heading',2,'Footer links']]);
  a.deepEqual(r.items.filter(i=>i.kind==='landmark').map(i=>i.landmark),['nav','main','article','section','section','nav']);
  a.equal(r.items[1].label,'Main content');
  for(const it of r.items)a.ok(it.el&&it.el.nodeType===1);
});
test('outline: landmarks can be switched off; empty or missing roots give nothing',()=>{
  const doc=parse(PAGE),r=C.collect(doc.body,{landmarks:false});a.ok(r.items.every(i=>i.kind==='heading'));
  a.ok(r.items.some(i=>i.text==='Display none'),'without the layout check only markup hiding applies');
  a.deepEqual(C.collect(parse('<body></body>').body).items,[]);a.deepEqual(C.collect(null).items,[]);
});
test('outline: long pages stop at 300 entries and say so; long headings are shortened',()=>{
  const doc=parse('<body>'+Array.from({length:450},(_,i)=>'<h2>Part '+i+'</h2>').join('')+'<h1>'+'word '.repeat(80)+'</h1></body>');
  const r=C.collect(doc.body);a.equal(r.items.length,C.MAX_ENTRIES);a.equal(r.truncated,true);a.equal(r.items.at(-1).text,'Part 299');
  const t=C.clean('word '.repeat(80));a.ok(t.length<=C.MAX_TEXT&&t.endsWith('…'));a.equal(C.clean(' a \n  b '),'a b');
});
test('current section and movement helpers',()=>{
  a.equal(C.pickCurrent([]),-1);a.equal(C.pickCurrent([{band:false,above:false},{band:false,above:false}]),-1);
  a.equal(C.pickCurrent([{above:true},{above:true},{band:true},{band:false}]),2);a.equal(C.pickCurrent([{above:true},{above:true},{},{}]),1);
  a.equal(C.step(0,-1,5),0);a.equal(C.step(4,1,5),4);a.equal(C.step(2,1,5),3);a.equal(C.step(-1,0,5),0);a.equal(C.step(0,1,0),-1);
  a.deepEqual(C.wheelSteps(0,140),{steps:1,acc:0},'one D-pad press, one step');a.deepEqual(C.wheelSteps(0,-140),{steps:-1,acc:0});
  let s={acc:0,steps:0},n=0;for(let i=0;i<10;i++){s=C.wheelSteps(s.acc,25);n+=s.steps}a.equal(n,2,'stick stream is summed (250 px -> 2 steps)');
});
test('manifest: off by default, no network, quick switch on; runtime has no storage, timers or HTML parsing',()=>{
  const m=JSON.parse(fs.readFileSync(path.join(DIR,'manifest.json'),'utf8')),rt=fs.readFileSync(path.join(DIR,'runtime.js'),'utf8'),css=fs.readFileSync(path.join(DIR,'addon.css'),'utf8');
  a.equal(m.default_on,false);a.deepEqual(m.hosts,[]);a.equal(m.quick_switch,true);a.equal(m.live_toggle,true);a.deepEqual(m.js,['core.js','runtime.js']);
  a.doesNotThrow(()=>new Function(rt));a.doesNotMatch(rt,/innerHTML|outerHTML|insertAdjacentHTML|document\.write|fetch\(|XMLHttpRequest|storage\.|setInterval/);
  a.match(rt,/new IntersectionObserver\(/);a.match(rt,/prefers-reduced-motion: reduce/);a.match(css,/prefers-reduced-motion:reduce/);
});

// ---- page glue against a fake page (no jsdom): headings from mini-dom, overlay elements from a tiny element class.
function harness(opts={}){
  const vm=require('node:vm'),doc=parse(opts.html||PAGE),tops=new Map(),scrolled=[];let order=0;
  const proto=Object.getPrototypeOf(doc.body);
  const docRoot=()=>doc;
  Object.assign(proto,{getClientRects(){return this.getAttribute('class')==='css-hidden'?[]:[{}]},getBoundingClientRect(){return{top:tops.has(this)?tops.get(this):(tops.set(this,200+300*order++),tops.get(this))}},
    scrollIntoView(o){scrolled.push([this.textContent.trim(),o&&o.behavior])},focus(){document.activeElement=this}});
  Object.defineProperty(proto,'isConnected',{configurable:true,get(){let n=this;while(n.parentNode)n=n.parentNode;return n===docRoot()}});
  class El{constructor(tag){this.nodeType=1;this.localName=tag;this.tagName=tag.toUpperCase();this.childNodes=[];this.parentNode=null;this.attrs={};this.dataset={};this.className='';this._text='';this.listeners={};this.offsetTop=0;this.offsetHeight=30;this.scrollTop=0;this.clientHeight=600}
    get children(){return this.childNodes}get textContent(){return this._text+this.childNodes.map(c=>c.textContent).join('')}set textContent(v){this._text=String(v);for(const c of this.childNodes)c.parentNode=null;this.childNodes=[]}
    append(...xs){for(const x of xs){x.parentNode=this;this.childNodes.push(x)}}
    remove(){if(this.parentNode){this.parentNode.childNodes=this.parentNode.childNodes.filter(c=>c!==this);this.parentNode=null}}
    setAttribute(k,v){this.attrs[k]=String(v)}getAttribute(k){return k in this.attrs?this.attrs[k]:null}hasAttribute(k){return k in this.attrs||(k==='data-omni-addon'&&'omniAddon' in this.dataset)}removeAttribute(k){delete this.attrs[k]}
    addEventListener(t,f){(this.listeners[t]||(this.listeners[t]=[])).push(f)}focus(){document.activeElement=this}
    all(){const out=[];for(const c of this.childNodes)if(c.all)out.push(c,...c.all());return out}
    querySelector(sel){return this.all().find(e=>e.className.split(' ').includes(sel.slice(1)))||null}
    contains(n){return n===this||this.all().includes(n)}closest(sel){let n=this;while(n&&n.className!==undefined){if(n.className.split(' ').includes(sel.slice(1)))return n;n=n.parentNode}return null}
    get isConnected(){let n=this;while(n.parentNode)n=n.parentNode;return n===doc}
    click(){if(this.onclick)this.onclick();let n=this;const ev={target:this};while(n){(n.listeners&&n.listeners.click||[]).forEach(f=>f(ev));n=n.parentNode}}}
  const document={body:doc.body,documentElement:doc.documentElement,readyState:'complete',visibilityState:'visible',activeElement:doc.body,createElement:t=>new El(t),getElementById:byIdIn(doc)};
  const ios=[];class IntersectionObserver{constructor(cb,o){this.cb=cb;this.o=o;this.els=[];ios.push(this)}observe(e){this.els.push(e)}disconnect(){this.off=true}}
  const L={enable:[],disable:[],settings:[]},toasts=[];let settings=Object.assign({button:true,landmarks:true},opts.settings);
  const api={id:'omni-page-outline',top:true,active:opts.active!==false,onEnable:f=>L.enable.push(f),onDisable:f=>L.disable.push(f),onSettings:f=>L.settings.push(f),
    toast:t=>{toasts.push(t);return Promise.resolve(true)},settings:{get:k=>settings[k]},storage:{get(){throw new Error('no storage')},set(){throw new Error('no storage')}}};
  const win={listeners:{}},hist=[{}];let at=0;
  const go=n=>{at=Math.max(0,at+n);setImmediate(()=>(win.listeners.popstate||[]).slice().forEach(f=>f({})))};
  const history={get state(){return hist[at]},pushState(s){hist.length=at+1;hist.push(JSON.parse(JSON.stringify(s)));at++},back:()=>go(-1),go};
  Object.assign(win,{addEventListener(t,f){(win.listeners[t]||(win.listeners[t]=[])).push(f)},removeEventListener(t,f){win.listeners[t]=(win.listeners[t]||[]).filter(x=>x!==f)},
    document,history,innerHeight:1000,matchMedia:q=>({matches:/reduce/.test(q)&&!!opts.reduced}),getComputedStyle:()=>({visibility:'visible'}),IntersectionObserver,
    requestIdleCallback:f=>{setImmediate(f);return 1},cancelIdleCallback(){},performance:{getEntriesByType:()=>[],now:()=>Date.now()},setTimeout,clearTimeout,setImmediate,omniAddon:api,
    Promise,Object,JSON,String,Number,Array,Math,RegExp,Error,Set,Map,WeakMap});
  win.window=win;win.globalThis=win;vm.createContext(win);
  vm.runInContext(fs.readFileSync(path.join(DIR,'core.js'),'utf8'),win);vm.runInContext(fs.readFileSync(path.join(DIR,'runtime.js'),'utf8'),win);
  const fire=(t,e)=>{const ev=Object.assign({isTrusted:true,altKey:false,shiftKey:false,ctrlKey:false,metaKey:false,repeat:false,defaultPrevented:false,preventDefault(){ev.defaultPrevented=true},stopImmediatePropagation(){}},e);(win.listeners[t]||[]).slice().forEach(f=>f(ev));return ev};
  const overlay=()=>doc.documentElement.childNodes.find(n=>n.className==='omni-outline')||null;
  const rows=()=>overlay()?overlay().querySelector('.omni-outline-list').childNodes:[];
  const tick=()=>new Promise(r=>setImmediate(()=>setImmediate(r)));
  return{doc,win,api,L,toasts,scrolled,tops,ios,overlay,rows,tick,hist:()=>hist.slice(0,at+1),history,fire,
    key:k=>fire('keydown',k),wheel:(dy,mode=0)=>fire('wheel',{deltaY:dy,deltaMode:mode}),open:()=>fire('keydown',{altKey:true,shiftKey:true,code:'KeyO'}),
    fab:()=>doc.body.childNodes.find(n=>n.className==='omni-outline-fab')||null,setSettings(s){settings=Object.assign({},settings,s);L.settings.forEach(f=>f(settings))}};
}
test('glue: Alt+Shift+O opens the panel with indented rows; D-pad (wheel) moves; Cross goes; Circle (Back) closes',async()=>{
  const h=harness({reduced:false});await h.tick();
  a.ok(h.fab(),'Outline button on a page with headings');a.equal(h.overlay(),null);
  h.open();const o=h.overlay();a.ok(o,'open');a.equal(o.dataset.omniAddon,'omni-page-outline');a.equal(h.fab(),null,'button hidden while open');
  const rows=h.rows();a.equal(rows.length,15,'CSS-hidden heading filtered by the layout check');
  a.equal(rows[0].className,'omni-outline-item omni-outline-d0 omni-outline-mark');a.match(rows[6].className,/omni-outline-d3/);a.equal(rows[6].textContent,'H4Tolls');
  a.equal(o.querySelector('.omni-outline-count').textContent,'15');
  a.equal(h.hist().length,2);a.ok(h.history.state.omniOutline);
  const sel=()=>rows.findIndex(r=>r.getAttribute('aria-selected')==='true');
  a.equal(sel(),0,'nothing scrolled past yet: first entry');
  let ev=h.wheel(140);a.ok(ev.defaultPrevented,'page does not scroll');a.equal(sel(),1);h.wheel(140);h.wheel(-140);h.wheel(140);a.equal(sel(),2);
  h.wheel(-3,1);a.equal(sel(),1,'line-mode wheel delta');
  h.wheel(30);h.wheel(30);a.equal(sel(),1);h.wheel(30);h.wheel(30);a.equal(sel(),2,'small stick deltas add up');
  h.key({key:'End'});a.equal(sel(),14);h.key({key:'ArrowDown'});a.equal(sel(),14,'clamped');h.key({key:'Home'});h.key({key:'ArrowDown'});h.key({key:'ArrowDown'});h.key({key:'ArrowDown'});
  // Cross with the pointer anywhere off the panel: go to the selected entry, smooth; the panel stays open.
  o.click();a.deepEqual(h.scrolled.at(-1),['Harbour   bridge\n reopens','smooth']);a.ok(h.overlay());
  rows[6].click();a.deepEqual(h.scrolled.at(-1),['Tolls','smooth']);a.equal(sel(),6);
  h.key({key:'Enter'});a.equal(h.scrolled.length,3);
  h.history.back();await h.tick();a.equal(h.overlay(),null,'Back closes');a.ok(h.fab(),'button returns');
  a.equal(h.win.listeners.wheel.length,0,'wheel released');
});
test('glue: reduced motion jumps instantly; Escape closes and takes its history entry back',async()=>{
  const h=harness({reduced:true});await h.tick();h.open();h.key({key:'ArrowDown'});h.key({key:'Enter'});
  a.equal(h.scrolled.at(-1)[1],'auto');h.key({key:'Escape'});await h.tick();a.equal(h.overlay(),null);a.equal(h.hist().length,1);
});
test('glue: the current section comes from IntersectionObserver and is where the selection starts',async()=>{
  const h=harness();await h.tick();const io=h.ios.at(-1);a.equal(io.o.rootMargin,'0px 0px -65% 0px');a.equal(io.els.length,15);
  h.open();const rows=h.rows(),io2=h.ios.at(-1);a.ok(io.off,'rescan replaced the old observer');
  const ent=(i,band,top)=>({target:io2.els[i],isIntersecting:band,boundingClientRect:{top},rootBounds:{top:0}});
  io2.cb([ent(0,false,-500),ent(1,false,-400),ent(3,false,-200),ent(4,true,100),ent(5,false,700)]);
  a.equal(rows[4].getAttribute('aria-current'),'location');a.equal(rows.filter(r=>r.getAttribute('aria-current')).length,1);
  io2.cb([ent(4,false,-50),ent(5,true,40)]);a.equal(rows[5].getAttribute('aria-current'),'location');a.equal(rows[4].getAttribute('aria-current'),null);
  h.key({key:'Escape'});await h.tick();
  // Scrolled down: the page reports headings above the reading line, so the next opening starts there.
  for(const it of io2.els)h.tops.set(it,-100);h.tops.set(io2.els[9],100);for(let i=10;i<15;i++)h.tops.set(io2.els[i],900);
  h.open();const sel=h.rows().findIndex(r=>r.getAttribute('aria-selected')==='true');a.equal(sel,9);
});
test('glue: quick switch on while the page is open shows the outline; off removes everything; no headings -> toast',async()=>{
  const h=harness({active:false});a.equal(h.overlay(),null);h.L.enable.forEach(f=>f());a.ok(h.overlay(),'live switch opens it');
  h.L.disable.forEach(f=>f());await h.tick();a.equal(h.overlay(),null);a.equal(h.fab(),null);a.ok(h.ios.every(io=>io.off));
  h.open();a.equal(h.overlay(),null,'shortcut does nothing while off');
  const e=harness({html:'<body><p>No headings here.</p></body>'});await e.tick();a.equal(e.fab(),null);e.open();a.equal(e.overlay(),null);a.deepEqual(e.toasts,['No headings found on this page']);
  const s=harness({settings:{button:false,landmarks:false}});await s.tick();a.equal(s.fab(),null);s.open();a.equal(s.rows().length,9);
  s.setSettings({landmarks:true});a.equal(s.rows().length,15,'settings change refreshes the open list');
});
