// node --test addons/tests   (article finder of the Reader view add-on on small HTML fixtures; no jsdom)
'use strict';
const test=require('node:test'),a=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const R=require('../bundled/omni-reader-view/core.js'),{parse}=require('./mini-dom.cjs');
const load=(name,base)=>parse(fs.readFileSync(path.join(__dirname,'fixtures',name),'utf8'),base);
const flat=items=>items.map(x=>typeof x==='string'?x:flat(x.kids)).join('');
const find=(items,tag,out=[])=>{for(const x of items)if(typeof x!=='string'){if(x.tag===tag)out.push(x);find(x.kids,tag,out)}return out};

test('news article: story body wins over comments, related links and navigation',()=>{
  const r=R.extract(load('reader-news.html','https://news.example.org/2026/11/bridge'));
  a.ok(r&&r.isArticle);a.equal(r.title,'Harbour bridge reopens after two years of repairs');a.equal(r.byline,'Mara Lindqvist');a.equal(r.site,'The Coastal Times');a.equal(r.lang,'en');
  a.equal(r.best.localName,'article');
  const text=flat(r.content);
  a.match(text,/reopened to traffic on Monday/);a.match(text,/temporary ferry/);a.match(text,/What changes for drivers/);
  for(const bad of[/Related stories/,/Finally, about time/,/All rights reserved/,/Weather/,/must, never, count/,/Share/,/By Mara/])a.doesNotMatch(text,bad);
  a.equal(find(r.content,'h2').filter(h=>/Harbour bridge reopens/.test(flat(h.kids))).length,0,'the title is not repeated');
  const imgs=find(r.content,'img');a.equal(imgs.length,1);a.equal(imgs[0].attrs.src,'https://news.example.org/img/bridge-1600.jpg','lazy data-src wins over the placeholder');a.equal(imgs[0].attrs.alt,'The bridge at dawn');
  a.ok(r.paragraphs>=5&&r.minutes>=1);
});
test('blog laid out with bare divs: text divs count as paragraphs, srcset gives the large image',()=>{
  const r=R.extract(load('reader-blog-divs.html','https://notes.example.net/2026/oslo'));
  a.ok(r&&r.isArticle,JSON.stringify(r&&{p:r.paragraphs,l:r.length}));
  a.equal(r.title,'A slow week in Oslo, by train and on foot');a.equal(r.byline,'Written by Teodor Berg');
  a.match(R.textOf(r.best),/night train north/);
  const text=flat(r.content);a.match(text,/cinnamon buns/);a.doesNotMatch(text,/Lisbon in three days/);a.doesNotMatch(text,/Archive/);a.doesNotMatch(text,/Written by/);
  a.equal(find(r.content,'img')[0].attrs.src,'https://notes.example.net/p/opera-1280.jpg');
});
test('front page of short linked teasers is not an article (no floating button)',()=>{
  const r=R.extract(load('reader-listing.html'));a.ok(!r||!r.isArticle,JSON.stringify(r&&{p:r.paragraphs,l:r.length}));
});
test('only http(s) links and images survive; scripts and handlers never reach the output',()=>{
  const doc=parse('<html><body><article><p>'+'Long enough sentence, with commas, to score as a paragraph. '.repeat(4)+'<a href="javascript:alert(1)">bad</a> <a href="/ok">good</a> <img src="javascript:x" onerror="alert(1)"><img src="/i.png" width="40"></p>'+('<p>'+'More plain text, more commas, more words to read. '.repeat(5)+'</p>').repeat(3)+'<script>alert(1)</script></article></body></html>','https://site.example/a/');
  const r=R.extract(doc),links=find(r.content,'a');
  a.deepEqual(links.map(l=>l.attrs.href),['https://site.example/ok']);a.equal(find(r.content,'img').length,0);
  a.doesNotMatch(JSON.stringify(r.content),/onerror|alert|javascript/);
});
test('hidden and aria-hidden parts are skipped; empty documents give null',()=>{
  const doc=parse('<body><div class="content">'+('<p>'+'Visible words, plenty of them, in a calm sentence. '.repeat(4)+'</p>').repeat(4)+'<p hidden>'+'Secret text, secret text. '.repeat(10)+'</p><div aria-hidden="true"><p>'+'Ghost words, ghost words. '.repeat(10)+'</p></div></div></body>');
  const text=flat(R.extract(doc).content);a.match(text,/Visible words/);a.doesNotMatch(text,/Secret|Ghost/);
  a.equal(R.extract(parse('<html><head></head><body></body></html>')),null);
});

// ---- 1.1.0: reading options (prefs.js), the toolbar's wiring and its CSS -------------------------------------------
const Pr=require('../bundled/omni-reader-view/prefs.js'),DIR=path.join(__dirname,'..','bundled','omni-reader-view');
const manifest=()=>JSON.parse(fs.readFileSync(path.join(DIR,'manifest.json'),'utf8'));
const css=fs.readFileSync(path.join(DIR,'addon.css'),'utf8'),runtime=fs.readFileSync(path.join(DIR,'runtime.js'),'utf8');

test('reading time comes from the article words and is shown up top, then counts down',()=>{
  const r=R.extract(load('reader-news.html','https://news.example.org/2026/11/bridge'));
  a.ok(r.words>50);a.equal(r.minutes,Math.max(1,Math.round(r.words/230)));
  a.equal(Pr.timeLabel(4,0),'4 min read');a.equal(Pr.timeLabel(4,.5),'2 min left');a.equal(Pr.timeLabel(4,.9),'1 min left');a.equal(Pr.timeLabel(4,1),'Finished');
  a.equal(Pr.timeLabel(0,0),'1 min read');a.equal(Pr.timeLabel(3,NaN),'3 min read');a.equal(Pr.timeLabel(3,-1),'3 min read');
  a.match(runtime,/omni-reader-time/);a.match(runtime,/timeLabel\(minutes,room>0\?view\.scrollTop\/room:0\)/);
});
test('the options: 5 text sizes, 3 widths, 3 fonts, 4 colours (black for OLED), line spacing',()=>{
  const v=k=>[...Pr.BY_KEY[k].values];
  a.deepEqual(v('size'),['small','medium','large','huge','giant']);a.deepEqual(v('width'),['narrow','medium','wide']);
  a.deepEqual(v('font'),['serif','sans','readable']);a.deepEqual(v('theme'),['light','sepia','dark','black']);a.ok(v('spacing').length>=3);
  for(const o of Pr.OPTIONS){a.equal(o.labels.length,o.values.length);a.ok(Object.isFrozen(o)&&Object.isFrozen(o.values));a.ok(o.values.includes(Pr.DEFAULTS[o.key])||Pr.DEFAULTS[o.key]==='auto')}
  a.deepEqual(Object.keys(Pr.DEFAULTS).sort(),Pr.OPTIONS.map(o=>o.key).sort());
});
test('saved choices win over the settings page, which wins over the defaults; junk is dropped',()=>{
  a.deepEqual(Pr.resolve(null,null),{size:'large',width:'medium',font:'serif',theme:'auto',spacing:'normal'});
  a.deepEqual(Pr.resolve({size:'giant'},{size:'medium',theme:'sepia'}),{size:'giant',width:'medium',font:'serif',theme:'sepia',spacing:'normal'});
  a.deepEqual(Pr.resolve({size:'enormous',font:'comic',width:7,theme:'<b>'},{size:'nope'}),Pr.resolve(null,null));
  a.deepEqual(Pr.clean(JSON.parse('{"size":"small","extra":1,"font":"readable","spacing":"loose","__proto__":{"x":1}}')),{size:'small',font:'readable'});
  a.deepEqual(Pr.clean('text'),{});a.deepEqual(Pr.clean(null),{});
});
test('stored value round-trips; a later settings-page change of size or colours replaces that saved choice only',()=>{
  const base={size:'large',theme:'auto'},stored=JSON.parse(JSON.stringify(Pr.pack({size:'huge',theme:'black',width:'wide',bogus:1},base)));
  a.ok(JSON.stringify(stored).length<300,'small value');a.deepEqual(stored.base,base);a.equal(stored.choices.bogus,undefined);
  let r=Pr.load(stored,base);a.deepEqual(r.prefs,{size:'huge',width:'wide',font:'serif',theme:'black',spacing:'normal'});
  r=Pr.load(stored,{size:'small',theme:'auto'});a.equal(r.prefs.size,'small');a.equal(r.prefs.theme,'black');a.equal(r.prefs.width,'wide');a.equal(r.choices.size,undefined);
  r=Pr.load(stored,{size:'large',theme:'sepia'});a.equal(r.prefs.theme,'sepia');a.equal(r.prefs.size,'huge');
  a.deepEqual(Pr.load(undefined,base).prefs,Pr.resolve(null,base));a.deepEqual(Pr.load({choices:'x',base:3},base).choices,{});
  a.equal(Pr.load({choices:{size:'small'}},{size:'giant'}).prefs.size,'small','a value without base keeps the choice');
});
test('A- / A+ step through the five sizes and stop at the ends',()=>{
  a.equal(Pr.step('size','large',1),'huge');a.equal(Pr.step('size','huge',1),'giant');a.equal(Pr.step('size','giant',1),'giant');
  a.equal(Pr.step('size','medium',-1),'small');a.equal(Pr.step('size','small',-1),'small');a.equal(Pr.step('size','bad',1),'large');
  a.ok(Pr.atEnd('size','small',-1)&&Pr.atEnd('size','giant',1)&&!Pr.atEnd('size','large',1)&&!Pr.atEnd('size','large',-1));
});
test('class names: auto colours follow Omni dark pages; every non-default choice has its CSS',()=>{
  const p=Pr.resolve({width:'wide',font:'readable',spacing:'relaxed'},{size:'huge',theme:'auto'});
  a.equal(Pr.classes(p,true),'omni-reader omni-reader-dark omni-reader-huge omni-reader-w-wide omni-reader-f-readable omni-reader-l-relaxed');
  a.match(Pr.classes(p,false),/omni-reader-light /);a.match(Pr.classes(Pr.resolve({theme:'black'}),true),/omni-reader-black /);
  const sel={size:v=>'.omni-reader.omni-reader-'+v+'{',theme:v=>'.omni-reader.omni-reader-'+v+'{',width:v=>'.omni-reader-w-'+v+' .omni-reader-article{',font:v=>'.omni-reader.omni-reader-f-'+v+'{',spacing:v=>'.omni-reader.omni-reader-l-'+v+'{'};
  const rootDefault={size:'large',theme:'light',width:'medium',font:'serif',spacing:'normal'};   // drawn by the plain .omni-reader rules
  for(const o of Pr.OPTIONS)for(const v of o.values)if(v!==rootDefault[o.key])a.ok(css.includes(sel[o.key](v)),'CSS for '+o.key+'='+v);
  a.match(css,/\.omni-reader-panel\[hidden\]\{display:none!important\}/);
  a.match(css,/\.omni-reader-black\{--rv-bg:#000;/);
});
test('fonts: only what Omni ships (plus named optional faces), nothing downloaded',()=>{
  a.doesNotMatch(css,/@font-face|@import|url\(/i);
  const allowed=new Set(['Noto Serif','DejaVu Serif','DejaVu Sans','DejaVu Sans Mono','Noto Sans JP','Georgia','Arial','OpenDyslexic','Atkinson Hyperlegible','Lexend','Verdana']);
  for(const m of css.matchAll(/'([^']+)'/g))a.ok(allowed.has(m[1]),'font '+m[1]);
  a.match(css,/omni-reader-f-readable\{font-family:[^}]*'DejaVu Sans',sans-serif!important;letter-spacing:[^;]+;word-spacing:/);
  a.match(css,/letter-spacing:inherit!important;word-spacing:inherit!important/,'spacing reaches the article text');
});
test('manifest 1.1: prefs.js loads before runtime.js; settings-page choices match the toolbar',()=>{
  const m=manifest();a.deepEqual(m.js,['core.js','prefs.js','runtime.js']);
  const [maj,min]=m.version.split('.').map(Number);a.ok(maj>1||(maj===1&&min>=1),m.version);
  const s=Object.fromEntries(m.settings.map(x=>[x.key,x]));
  a.deepEqual(s.size.choices,[...Pr.BY_KEY.size.values]);a.equal(s.size.default,Pr.DEFAULTS.size);
  a.deepEqual([...s.theme.choices].sort(),['auto',...Pr.BY_KEY.theme.values].sort());a.equal(s.theme.default,Pr.DEFAULTS.theme);
  a.equal(m.private_safe,true,'still runs in private tabs');
});
test('runtime: options go to the add-on storage only, built without HTML parsing, no Read aloud in this build',()=>{
  a.doesNotThrow(()=>new Function(runtime));
  a.match(runtime,/api\.storage\.set\(P\.STORAGE_KEY,P\.pack\(choices,lastBase\)\)\.catch\(/,'a refused write (private tab) is not an error');
  a.doesNotMatch(runtime,/settings\.set\(/);a.doesNotMatch(runtime,/innerHTML|outerHTML|insertAdjacentHTML|document\.write/);
  a.doesNotMatch(runtime,/speechSynthesis/);
  a.match(fs.readFileSync(path.join(__dirname,'..','..','omni','webkit','configure-cmd.json'),'utf8'),/ENABLE_SPEECH_SYNTHESIS:BOOL=OFF/,'if this turns ON, add Read aloud');
  for(const o of Pr.OPTIONS)a.ok(o.labels.every(l=>l.length<=12),'labels fit a TV button');
});

// The page glue against a small fake page (no jsdom): toolbar, saved options, Back closing the panel then the reader.
function readerHarness(opts={}){
  const vm=require('node:vm');
  class El{constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.parentNode=null;this.attrs={};this.dataset={};this.className='';this.id='';this.hidden=false;this.disabled=false;this.textContent='';this.listeners={};
    this.scrollTop=0;this.scrollHeight=4000;this.clientHeight=1000;this.style={p:{},getPropertyValue:k=>this.style.p[k]||'',getPropertyPriority:()=>'',setProperty:(k,v)=>{this.style.p[k]=v},removeProperty:k=>{delete this.style.p[k]}}}
    append(...xs){for(const x of xs)if(typeof x!=='string'){x.parentNode=this;this.children.push(x)}else this.textContent+=x}
    remove(){if(this.parentNode){this.parentNode.children=this.parentNode.children.filter(c=>c!==this);this.parentNode=null}}
    get isConnected(){let n=this;while(n.parentNode)n=n.parentNode;return n===html}
    setAttribute(k,v){this.attrs[k]=String(v)}getAttribute(k){return k in this.attrs?this.attrs[k]:null}hasAttribute(k){return k in this.attrs}removeAttribute(k){delete this.attrs[k]}
    addEventListener(t,f){(this.listeners[t]||(this.listeners[t]=[])).push(f)}
    focus(){document.activeElement=this}getBoundingClientRect(){return{left:0,width:10,top:0,height:10}}
    all(){const out=[];for(const c of this.children)out.push(c,...c.all());return out}
    matches(sel){if(sel.startsWith('.'))return this.className.split(' ').includes(sel.slice(1));const m=/^\[([\w-]+)="([^"]*)"\]$/.exec(sel);if(m)return this.getAttribute(m[1])===m[2];return this.tagName===sel.toUpperCase()}
    querySelectorAll(sel){return this.all().filter(e=>e.matches(sel))}querySelector(sel){return this.querySelectorAll(sel)[0]||null}
    contains(n){return n===this||this.all().includes(n)}
    click(){if(this.onclick)this.onclick()}}
  const html=new El('html'),body=new El('body');html.append(body);
  const document={documentElement:html,body,readyState:'complete',visibilityState:'visible',baseURI:'https://news.example.org/a',title:'T',activeElement:body,createElement:t=>new El(t)};
  const store=new Map(),writes=[],L={settings:[],enable:[]};let settings={size:'large',theme:'auto',button:true};
  if(opts.stored)store.set('prefs',JSON.stringify(opts.stored));
  const api={id:'omni-reader-view',top:true,active:true,onEnable:f=>L.enable.push(f),onDisable(){},onSettings:f=>L.settings.push(f),toast:()=>Promise.resolve(true),
    settings:{get:k=>settings[k]},storage:{get:k=>store.has(k)?JSON.parse(store.get(k)):undefined,
    set(k,v){writes.push(JSON.parse(JSON.stringify(v)));if(opts.private)return Promise.reject(new Error('error: private tab'));store.set(k,JSON.stringify(v));return Promise.resolve(true)}}};
  const win={listeners:{}},hist=[{}];let at=0;
  const go=n=>{at=Math.max(0,at+n);setImmediate(()=>(win.listeners.popstate||[]).slice().forEach(f=>f({})))};
  const history={get state(){return hist[at]},pushState(s){hist.length=at+1;hist.push(JSON.parse(JSON.stringify(s)));at++},back:()=>go(-1),go};
  const found={title:'Bridge',byline:'',site:'Coastal',lang:'en',dir:'',content:['Some text.'],length:2000,paragraphs:6,words:920,minutes:4,isArticle:true};
  Object.assign(win,{addEventListener(t,f){(win.listeners[t]||(win.listeners[t]=[])).push(f)},removeEventListener(t,f){win.listeners[t]=(win.listeners[t]||[]).filter(x=>x!==f)},
    document,history,location:{hostname:'news.example.org'},scrollY:0,scrollTo(){},matchMedia:()=>({matches:!!opts.dark}),requestAnimationFrame:f=>setImmediate(f),cancelAnimationFrame(){},
    requestIdleCallback:()=>1,cancelIdleCallback(){},performance:{getEntriesByType:()=>[],now:()=>0},setTimeout,clearTimeout,setImmediate,omniAddon:api,
    OmniReaderCore:{extract:()=>found},Promise,Object,JSON,String,Number,Array,Math,RegExp,Error,Set,Map});
  win.window=win;win.globalThis=win;vm.createContext(win);
  vm.runInContext(fs.readFileSync(path.join(DIR,'prefs.js'),'utf8'),win);vm.runInContext(fs.readFileSync(path.join(DIR,'runtime.js'),'utf8'),win);
  const key=k=>(win.listeners.keydown||[]).slice().forEach(f=>f(Object.assign({isTrusted:true,altKey:false,shiftKey:false,ctrlKey:false,metaKey:false,repeat:false,target:document.activeElement,preventDefault(){},stopImmediatePropagation(){}},k)));
  const view=()=>html.querySelector('.omni-reader');
  const tick=()=>new Promise(r=>setImmediate(()=>setImmediate(r)));
  return{store,writes,view,btn:cls=>view().querySelector('.'+cls),key,tick,history,hist:()=>hist.slice(0,at+1),open:()=>key({altKey:true,shiftKey:true,code:'KeyR'}),
    setSettings(s){settings=Object.assign({},settings,s);L.settings.forEach(f=>f(settings))}};
}
test('toolbar: saved options apply on open; A+, choices and the panel restyle in place and are saved',async()=>{
  const h=readerHarness({stored:Pr.pack({font:'sans',width:'narrow'},{size:'large',theme:'auto'})});h.open();
  const v=h.view();a.ok(v,'reader open');a.match(v.className,/omni-reader-light omni-reader-large omni-reader-w-narrow omni-reader-f-sans omni-reader-l-normal/);
  a.equal(h.btn('omni-reader-left').textContent,'4 min read');a.match(h.btn('omni-reader-time').textContent,/About 4 min read · 920 words/);
  h.btn('omni-reader-larger').click();await h.tick();a.match(v.className,/omni-reader-huge/);a.deepEqual(h.writes.at(-1).choices,{font:'sans',width:'narrow',size:'huge'});
  h.btn('omni-reader-larger').click();a.match(v.className,/omni-reader-giant/);a.equal(h.btn('omni-reader-larger').disabled,true);
  const panel=h.btn('omni-reader-panel');a.equal(panel.hidden,true);h.btn('omni-reader-opts').click();a.equal(panel.hidden,false);
  a.equal(h.btn('omni-reader-opts').getAttribute('aria-expanded'),'true');a.equal(v.querySelectorAll('.omni-reader-choice').length,5+3+3+4+3);
  h.btn('omni-reader-c-theme-black').click();a.match(v.className,/omni-reader-black/);a.equal(h.btn('omni-reader-c-theme-black').getAttribute('aria-pressed'),'true');
  a.equal(h.btn('omni-reader-c-theme-light').getAttribute('aria-pressed'),'false');
  h.btn('omni-reader-c-spacing-relaxed').click();h.btn('omni-reader-c-font-readable').click();a.match(v.className,/omni-reader-f-readable omni-reader-l-relaxed/);
  await h.tick();a.deepEqual(JSON.parse(h.store.get('prefs')),{choices:{font:'readable',width:'narrow',size:'giant',theme:'black',spacing:'relaxed'},base:{size:'large',theme:'auto'}});
  v.scrollTop=1500;v.listeners.scroll[0]();await h.tick();a.equal(h.btn('omni-reader-left').textContent,'2 min left');
});
test('Back (Circle) closes the options panel first, then the reader; Escape does the same',async()=>{
  const h=readerHarness();h.open();h.btn('omni-reader-opts').click();a.equal(h.hist().length,3);a.ok(h.history.state.omniReaderPanel);
  h.history.back();await h.tick();a.ok(h.view(),'still reading');a.equal(h.btn('omni-reader-panel').hidden,true);
  h.history.back();await h.tick();a.equal(h.view(),null,'reader closed');
  const k=readerHarness();k.open();k.btn('omni-reader-opts').click();k.key({key:'Escape'});await k.tick();a.ok(k.view());a.equal(k.btn('omni-reader-panel').hidden,true);
  a.equal(k.hist().length,2,'the panel entry was taken back');k.key({key:'Escape'});await k.tick();a.equal(k.view(),null);a.equal(k.hist().length,1);
  const c=readerHarness();c.open();c.btn('omni-reader-opts').click();c.btn('omni-reader-close').click();await c.tick();a.equal(c.view(),null);a.equal(c.hist().length,1,'closing with the panel open leaves no extra history');
});
test('private tab: storage refused, the choice still applies on this page and nothing throws',async()=>{
  const h=readerHarness({private:true});h.open();h.btn('omni-reader-smaller').click();await h.tick();
  a.match(h.view().className,/omni-reader-medium/);a.equal(h.store.size,0);a.equal(h.writes.length,1);
});
test('the settings page wins: changing Text size there drops the toolbar size, keeps the rest',async()=>{
  const h=readerHarness({stored:Pr.pack({size:'giant',font:'sans'},{size:'large',theme:'auto'}),dark:true});h.open();
  a.match(h.view().className,/omni-reader-dark omni-reader-giant/);
  h.setSettings({size:'small'});await h.tick();a.match(h.view().className,/omni-reader-small .*omni-reader-f-sans/);
  a.deepEqual(JSON.parse(h.store.get('prefs')),{choices:{font:'sans'},base:{size:'small',theme:'auto'}});
});
