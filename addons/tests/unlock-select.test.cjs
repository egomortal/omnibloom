// node --test addons/tests   (Unlock selection add-on: target kinds, learning, inline blockers, canvas apps, runtime in a fake page)
'use strict';
const test=require('node:test'),a=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const DIR=path.join(__dirname,'..','bundled','omni-unlock-select'),C=require(path.join(DIR,'core.js'));

// ---------------------------------------------------------------- a tiny DOM with capture/bubble events
class Target{constructor(){this.ls=new Map()}
  addEventListener(t,f,o){const capture=o===true||!!(o&&o.capture);if(!this.ls.has(t))this.ls.set(t,[]);const l=this.ls.get(t);if(!l.some(x=>x.f===f&&x.capture===capture))l.push({f,capture})}
  removeEventListener(t,f,o){const capture=o===true||!!(o&&o.capture);const l=this.ls.get(t);if(l)this.ls.set(t,l.filter(x=>!(x.f===f&&x.capture===capture)))}
  dispatchEvent(ev){return dispatch(this,ev)}}
class El extends Target{constructor(tag,attrs={}){super();this.tagName=tag.toUpperCase();this.localName=tag.toLowerCase();this.nodeType=1;this.attrs=new Map(Object.entries(attrs));this.children=[];this.parentNode=null;this.doc=null;
    const self=this;this.classList={add(c){const s=self.cls();s.add(c);self.attrs.set('class',[...s].join(' '))},remove(c){const s=self.cls();s.delete(c);self.attrs.set('class',[...s].join(' '))},contains:c=>self.cls().has(c)}}
  cls(){return new Set(String(this.attrs.get('class')||'').split(/\s+/).filter(Boolean))}
  setAttribute(k,v){this.attrs.set(k,String(v));this.doc&&this.doc.mutated()}getAttribute(k){return this.attrs.has(k)?this.attrs.get(k):null}removeAttribute(k){this.attrs.delete(k)}
  append(...cs){for(const c of cs){c.parentNode=this;this.children.push(c);if(this.doc)adopt(this.doc,c)}this.doc&&this.doc.mutated();return this}
  get isConnected(){let e=this;while(e.parentNode)e=e.parentNode;return!!this.doc&&e===this.doc.documentElement}
  *walk(){for(const c of this.children){yield c;yield*c.walk()}}
  getBoundingClientRect(){const[w,h]=String(this.attrs.get('data-rect')||'0x0').split('x').map(Number);return{width:w,height:h}}}
function adopt(doc,e){e.doc=doc;for(const c of e.children)adopt(doc,c);return e}
function dispatch(target,ev){const p=[];for(let e=target;e;e=e.parentNode)p.unshift(e);const doc=target.doc||(target.win?target:null);if(doc){if(target!==doc)p.unshift(doc);p.unshift(doc.win)}
  ev.target=target;let stop=false;const run=(node,phase)=>{if(stop)return;for(const l of[...(node.ls.get(ev.type)||[])]){if(phase==='capture'&&!l.capture||phase==='bubble'&&l.capture)continue;l.f.call(node,ev);if(ev._imm)return}if(ev._stop)stop=true};
  for(const n of p.slice(0,-1))run(n,'capture');run(target,'target');if(ev.bubbles!==false)for(const n of p.slice(0,-1).reverse())run(n,'bubble');return!ev.defaultPrevented}
class Ev{constructor(type,init={}){this.type=type;this.bubbles=init.bubbles!==false;this.cancelable=init.cancelable!==false;this.isTrusted=false;this.button=init.button??0;this.defaultPrevented=false}
  preventDefault(){if(this.cancelable)this.defaultPrevented=true}stopPropagation(){this._stop=true}stopImmediatePropagation(){this._stop=true;this._imm=true}}
const h=(tag,attrs,...kids)=>{const e=new El(tag,attrs||{});e.append(...kids);return e};

function fakePage(o={}){
  const timers=new Map();let tid=0,clock=1_000_000,mo=null;
  const win=new Target(),doc=new Target();doc.win=win;doc.readyState=o.readyState||'loading';doc.mutated=()=>{if(mo)mo.pending=true};
  doc.documentElement=adopt(doc,new El('html'));doc.body=adopt(doc,new El('body'));doc.documentElement.append(doc.body);
  doc.mutated=()=>{if(mo)mo.pending=true};
  doc.querySelectorAll=sel=>{const all=[doc.documentElement,...doc.documentElement.walk()];if(sel==='canvas')return all.filter(e=>e.localName==='canvas');
    const keys=sel.split(',').map(s=>/^\[([a-z]+)\]$/.exec(s.trim())[1]);return all.filter(e=>keys.some(k=>e.attrs.has(k)))};
  const settings=Object.assign({mousedown:true},o.settings);
  const hooks={},api={id:'omni-unlock-select',top:true,active:o.active!==false,onEnable:f=>hooks.enable=f,onDisable:f=>hooks.disable=f,settings:{get:k=>settings[k]}};
  Object.assign(win,{omniAddon:api,document:doc,innerWidth:1920,innerHeight:1080,Date:{now:()=>clock},Event:Ev,
    MutationObserver:class{constructor(f){this.f=f}observe(t,opt){this.opt=opt;mo=this}disconnect(){if(mo===this)mo=null}},
    setTimeout:(f,ms)=>{timers.set(++tid,{f,at:clock+(ms||0)});return tid},clearTimeout:id=>timers.delete(id),Object,Array,String,Math,Number,Map,Set,JSON,Error,RegExp,console});
  win.addEventListener=win.addEventListener.bind(win);win.removeEventListener=win.removeEventListener.bind(win);
  win.window=win;win.globalThis=win;const ctx=vm.createContext(win);
  vm.runInContext(fs.readFileSync(path.join(DIR,'core.js'),'utf8'),ctx);
  const page={doc,win,hooks,settings,
    add(e,parent=doc.body){parent.append(e);return e},
    run(){vm.runInContext(fs.readFileSync(path.join(DIR,'runtime.js'),'utf8'),ctx)},
    ready(){doc.readyState='interactive';dispatch(doc,new Ev('DOMContentLoaded'))},load(){doc.readyState='complete';dispatch(win,new Ev('load'))},
    tick(ms){clock+=ms;for(const[id,t]of[...timers])if(t.at<=clock){timers.delete(id);t.f()}},
    mutate(){if(mo&&mo.pending){mo.pending=false;mo.f([])}},observing:()=>!!mo,observedAttrs:()=>mo&&mo.opt.attributeFilter,
    // a user action: trusted event, then the next task runs (where the add-on checks defaultPrevented)
    user(el,type,init){const ev=new Ev(type,init);ev.isTrusted=true;dispatch(el,ev);page.tick(0);return ev},
    unlocked:()=>doc.documentElement.classList.contains('omni-unlock-select'),diag:()=>JSON.parse(JSON.stringify(win.OmniUnlockSelectDiagnostics()))};
  return page}
// The page's blocker: a document listener that cancels the event (what "return false" handlers do).
function blocker(p,type){const calls=[];p.doc.addEventListener(type,e=>{calls.push(e.target);e.preventDefault()});return calls}

// ---------------------------------------------------------------- core
test('kind: plain text vs text fields vs controls',()=>{
  const p=h('p',{},),body=h('body',{},p),field=h('input',{type:'text'}),ta=h('textarea'),sel=h('select'),ed=h('div',{contenteditable:'true'},h('span')),notEd=h('div',{contenteditable:'false'});
  h('html',{},body);body.append(field,ta,sel,ed,notEd);
  a.equal(C.kind(p),'text');a.equal(C.kind(body),'text');a.equal(C.kind(notEd),'text');a.equal(C.kind({nodeType:3,parentNode:p}),'text','text node -> its element');
  for(const e of[field,ta,sel,ed,ed.children[0]])a.equal(C.kind(e),'edit');
  const ctl=['button','canvas','video','svg','iframe','img'].map(t=>h(t)),btnText=h('span'),rb=h('div',{role:'button'},btnText),slider=h('div',{role:'slider'}),ui=h('aside',{'data-omni-addon':'x'},h('b')),drag=h('div',{draggable:'true'});
  for(const e of[...ctl,rb,btnText,slider,ui.children[0],drag])a.equal(C.kind(e),'control',e.localName);
  a.equal(C.kind(h('a',{href:'/x'})),'text','link text can be selected');a.equal(C.kind(null),'control');
});
test('shield/learn: only text, only after the page was seen cancelling; mousedown needs two, main button, setting',()=>{
  for(const t of['selectstart','copy','contextmenu','dragstart']){a.equal(C.shield(t,'text',{}),false);a.equal(C.shield(t,'text',{[t]:1}),true,t);a.equal(C.shield(t,'edit',{[t]:9}),false);a.equal(C.shield(t,'control',{[t]:9}),false)}
  a.equal(C.shield('mousedown','text',{mousedown:1}),false);a.equal(C.shield('mousedown','text',{mousedown:2}),true);
  a.equal(C.shield('mousedown','text',{mousedown:2},{mousedown:false}),false);a.equal(C.shield('mousedown','text',{mousedown:2},{button:2}),false);
  a.equal(C.shield('click','text',{click:9}),false);a.equal(C.shield('keydown','text',{keydown:9}),false);
  a.equal(C.learn('copy','text',true),true);a.equal(C.learn('copy','text',false),false);a.equal(C.learn('copy','edit',true),false);a.equal(C.learn('paste','text',true),false);
});
test('inline blockers: only cancelling code is stripped; onmousedown only on text',()=>{
  for(const v of['return false','return false;','return(false)','event.preventDefault()','window.event.returnValue=false','RETURN FALSE'])a.equal(C.blockerCode(v),true,v);
  for(const v of['openMenu(event)','track("copy")','return true','',null])a.equal(C.blockerCode(v),false,String(v));
  const div=h('div',{oncopy:'return false',oncontextmenu:'showMenu()',onselectstart:'return false',ondragstart:'return false',onmousedown:'return false',oncut:'event.preventDefault()'});h('body',{},div);
  a.deepEqual(C.stripList(div).sort(),['oncopy','oncut','ondragstart','onmousedown','onselectstart']);
  a.deepEqual(C.stripList(h('button',{onmousedown:'return false',oncopy:'return false'})),['oncopy']);
  a.equal(C.ATTR_SELECTOR,'[onselectstart],[oncopy],[oncut],[oncontextmenu],[ondragstart],[onmousedown]');
});
test('bigCanvas: half the viewport or more is a canvas app',()=>{
  const v={w:1920,h:1080};a.equal(C.bigCanvas([{w:1920,h:1080}],v),true);a.equal(C.bigCanvas([{w:1400,h:800}],v),true);
  a.equal(C.bigCanvas([{w:300,h:150},{w:600,h:400}],v),false,'charts and ads');a.equal(C.bigCanvas([{w:4000,h:200}],v),false,'clipped to the viewport');
  a.equal(C.bigCanvas([],v),false);a.equal(C.bigCanvas([{w:0,h:0}],v),false);
});
test('stylesheet: scoped under html.omni-unlock-select, never fields, buttons, canvas or Omni UI',()=>{
  const css=fs.readFileSync(path.join(DIR,'addon.css'),'utf8');
  const sels=[];let depth=0,cur='';for(const ch of css.split('{')[0]){if(ch==='(')depth++;if(ch===')')depth--;if(ch===','&&!depth){sels.push(cur);cur=''}else cur+=ch}sels.push(cur);a.equal(sels.length,2);
  for(const sel of sels)a.match(sel.trim(),/^html\.omni-unlock-select body/);
  a.match(css,/user-select:text!important/);a.match(css,/-webkit-user-select:text!important/);
  for(const x of['input','textarea','button','[role=button]','canvas','[contenteditable]','[data-omni-addon]'])a.ok(css.includes(x),x);
  const m=JSON.parse(fs.readFileSync(path.join(DIR,'manifest.json'),'utf8'));a.equal(m.css_level,'user','user sheet: its !important beats the page');a.equal(m.run_at,'document_start');a.equal(m.default_on,false);
});

// ---------------------------------------------------------------- runtime
test('runtime: off by default does nothing; on adds the html class, off removes it',()=>{
  const p=fakePage({active:false});const t=p.add(h('p'));const calls=blocker(p,'copy');p.run();p.ready();
  a.equal(p.unlocked(),false);p.user(t,'copy');p.user(t,'copy');a.equal(calls.length,2);a.equal(p.user(t,'copy').defaultPrevented,true,'still blocked');
  p.hooks.enable();a.equal(p.unlocked(),true);p.hooks.disable();a.equal(p.unlocked(),false);a.equal(p.observing(),false);
});
for(const type of['copy','contextmenu','dragstart'])test('runtime: '+type+' blocker on text is undone after the page shows it (first try learns)',()=>{
  const p=fakePage();const t=p.add(h('p'));const calls=blocker(p,type);p.run();p.ready();
  a.equal(p.user(t,type).defaultPrevented,true,'first: the page cancelled it');a.equal(calls.length,1);
  for(let i=0;i<3;i++)a.equal(p.user(t,type).defaultPrevented,false,'then: default happens');a.equal(calls.length,1,'page blocker never ran again');
  a.equal(p.diag().shielded,3);
});
test('runtime: a document-wide selectstart blocker is found by the probe, so the first selection already works',()=>{
  const p=fakePage();const t=p.add(h('p'));const calls=blocker(p,'selectstart');p.run();p.ready();
  a.equal(p.diag().seen.selectstart,1);a.equal(calls.length,1,'only the probe reached it');a.equal(p.user(t,'selectstart').defaultPrevented,false);
  const late=fakePage();const lt=late.add(h('p'));late.run();late.ready();blocker(late,'selectstart');late.load();a.equal(late.diag().seen.selectstart,1,'re-probed at load (late page scripts)');
  a.equal(late.user(lt,'selectstart').defaultPrevented,false);
  const none=fakePage();const nt=none.add(h('p'));const nc=[];none.doc.addEventListener('selectstart',e=>nc.push(e));none.run();none.ready();
  a.equal(none.diag().seen.selectstart,undefined);a.equal(none.user(nt,'selectstart').defaultPrevented,false);a.equal(nc.length,2,'harmless page listeners keep running');
});
test('runtime: pages that do not cancel keep all their listeners (no stopping by default)',()=>{
  const p=fakePage();const t=p.add(h('p'));const seen=[];for(const ty of C.TYPES)p.doc.addEventListener(ty,e=>seen.push(e.type));p.run();p.ready();seen.length=0;
  for(let i=0;i<3;i++)for(const ty of C.TYPES)p.user(t,ty);a.equal(seen.length,15);a.equal(p.diag().shielded,0);
});
test('runtime: mousedown needs two cancels on text, only the main button, and the setting can turn it off',()=>{
  const p=fakePage();const t=p.add(h('p'));const calls=blocker(p,'mousedown');p.run();p.ready();
  p.user(t,'mousedown');a.equal(p.user(t,'mousedown').defaultPrevented,true,'second still the page\'s: threshold 2');
  a.equal(p.user(t,'mousedown').defaultPrevented,false);a.equal(p.user(t,'mousedown',{button:2}).defaultPrevented,true,'other buttons left alone');a.equal(calls.length,3);
  const q=fakePage({settings:{mousedown:false}});const qt=q.add(h('p'));blocker(q,'mousedown');q.run();q.ready();for(let i=0;i<4;i++)a.equal(q.user(qt,'mousedown').defaultPrevented,true);
});
test('runtime: text fields, editable regions, buttons and controls are never shielded',()=>{
  const p=fakePage();const t=p.add(h('p')),inp=p.add(h('input',{type:'text'})),ta=p.add(h('textarea')),ed=p.add(h('div',{contenteditable:''})),btn=p.add(h('button')),rb=p.add(h('div',{role:'button'})),cv=p.add(h('canvas',{'data-rect':'300x150'}));
  const fieldCalls=[];p.doc.addEventListener('copy',e=>fieldCalls.push(e.target));blocker(p,'copy');blocker(p,'contextmenu');p.run();p.ready();
  p.user(t,'copy');p.user(t,'contextmenu');a.deepEqual(p.diag().seen,{copy:1,contextmenu:1});fieldCalls.length=0;
  for(const el of[inp,ta,ed,btn,rb,cv]){a.equal(p.user(el,'copy').defaultPrevented,true,el.localName);a.equal(p.user(el,'contextmenu').defaultPrevented,true,el.localName)}
  a.equal(fieldCalls.length,6,'the page still handles copy in its own fields and controls');
  a.equal(p.user(t,'copy').defaultPrevented,false,'plain text still unlocked');
  // cancels inside fields are not learned
  const q=fakePage();const qi=q.add(h('input'));blocker(q,'copy');q.run();q.ready();q.user(qi,'copy');q.user(qi,'copy');a.deepEqual(q.diag().seen,{});
});
test('runtime: synthetic (page-made) events are neither shielded nor learned from',()=>{
  const p=fakePage();const t=p.add(h('p'));blocker(p,'copy');p.run();p.ready();
  for(let i=0;i<3;i++){const ev=new Ev('copy');t.dispatchEvent(ev);p.tick(0);a.equal(ev.defaultPrevented,true)}a.deepEqual(p.diag().seen,{});
});
test('runtime: cancelling on* attributes are removed at load and after DOM changes (throttled); off puts them back',()=>{
  const p=fakePage();p.doc.body.setAttribute('oncontextmenu','return false');p.doc.body.setAttribute('onselectstart','return false');
  const art=p.add(h('article',{oncopy:'return false;',onclick:'go()'})),menu=p.add(h('div',{oncontextmenu:'openMenu(event)'})),btn=p.add(h('button',{onmousedown:'return false'}));
  p.run();a.equal(p.doc.body.getAttribute('oncontextmenu'),'return false','nothing before DOMContentLoaded');p.ready();
  a.equal(p.doc.body.getAttribute('oncontextmenu'),null);a.equal(p.doc.body.getAttribute('onselectstart'),null);a.equal(art.getAttribute('oncopy'),null);
  a.equal(art.getAttribute('onclick'),'go()');a.equal(menu.getAttribute('oncontextmenu'),'openMenu(event)','own menus kept');a.equal(btn.getAttribute('onmousedown'),'return false','controls kept');
  a.deepEqual([...p.observedAttrs()],['onselectstart','oncopy','oncut','oncontextmenu','ondragstart','onmousedown']);
  const later=p.add(h('section',{oncopy:'return false'}));p.mutate();a.equal(later.getAttribute('oncopy'),'return false','throttled: not yet');
  const more=p.add(h('div',{ondragstart:'return false'}));p.mutate();p.tick(499);a.equal(later.getAttribute('oncopy'),'return false');
  p.tick(1);a.equal(later.getAttribute('oncopy'),null);a.equal(more.getAttribute('ondragstart'),null,'one scan catches the burst');
  a.equal(p.diag().stripped,5);
  p.hooks.disable();a.equal(p.doc.body.getAttribute('oncontextmenu'),'return false');a.equal(later.getAttribute('oncopy'),'return false');a.equal(p.diag().stripped,0);
});
test('runtime: a big canvas (game, map, editor) means hands off; one appearing later undoes everything',()=>{
  const g=fakePage();const t=g.add(h('p'));g.add(h('canvas',{'data-rect':'1920x1080'}));g.doc.body.setAttribute('oncontextmenu','return false');const calls=blocker(g,'contextmenu');
  g.run();g.ready();a.equal(g.diag().canvasApp,true);a.equal(g.unlocked(),false);a.equal(g.doc.body.getAttribute('oncontextmenu'),'return false');
  for(let i=0;i<3;i++)a.equal(g.user(t,'contextmenu').defaultPrevented,true);a.equal(calls.length,3);a.deepEqual(g.diag().seen,{});
  const p=fakePage();const pt=p.add(h('p'));p.doc.body.setAttribute('oncopy','return false');blocker(p,'copy');p.run();p.ready();p.user(pt,'copy');
  a.equal(p.unlocked(),true);a.equal(p.doc.body.getAttribute('oncopy'),null);
  p.add(h('canvas',{'data-rect':'1600x900'}));p.mutate();p.tick(500);
  a.equal(p.diag().canvasApp,true);a.equal(p.unlocked(),false);a.equal(p.doc.body.getAttribute('oncopy'),'return false','attributes put back');
  a.equal(p.user(pt,'copy').defaultPrevented,true,'the page has its events back');
});
test('runtime: listeners are on window in the capture phase and are removed on disable',()=>{
  const p=fakePage();p.run();for(const t of C.TYPES)a.ok((p.win.ls.get(t)||[]).some(l=>l.capture),t);
  p.hooks.disable();for(const t of C.TYPES)a.equal((p.win.ls.get(t)||[]).length,0,t);
  const q=fakePage({readyState:'complete'});q.add(h('p',{oncopy:'return false'}));q.run();a.equal(q.diag().stripped,1,'late injection scans at once');a.equal(q.observing(),true);
});
