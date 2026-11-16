// node --test addons/tests   (Form saver add-on: field eligibility, expiry, size caps, key stability, runtime in a fake page)
'use strict';
const test=require('node:test'),a=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const DIR=path.join(__dirname,'..','bundled','omni-form-saver'),C=require(path.join(DIR,'core.js'));

// ---------------------------------------------------------------- a tiny DOM
class El{constructor(tag,attrs={},doc=null){this.tagName=tag.toUpperCase();this.localName=tag.toLowerCase();this.nodeType=1;this.attrs=new Map(Object.entries(attrs));this.children=[];this.parentNode=null;this.value='';this.textContent='';this.ls={};this.doc=doc;
  this.dataset=new Proxy({},{get:(_,k)=>this.attrs.get('data-'+k.replace(/[A-Z]/g,c=>'-'+c.toLowerCase())),set:(_,k,v)=>(this.attrs.set('data-'+k.replace(/[A-Z]/g,c=>'-'+c.toLowerCase()),String(v)),true)});this.events=[]}
  set className(v){this.attrs.set('class',v)}get className(){return this.attrs.get('class')||''}
  setAttribute(k,v){this.attrs.set(k,String(v))}getAttribute(k){return this.attrs.has(k)?this.attrs.get(k):null}hasAttribute(k){return this.attrs.has(k)}removeAttribute(k){this.attrs.delete(k)}
  append(...cs){for(const c of cs){if(typeof c==='string')continue;c.remove();c.parentNode=this;this.children.push(c)}return this}
  remove(){if(this.parentNode){this.parentNode.children=this.parentNode.children.filter(c=>c!==this);this.parentNode=null}}
  get isConnected(){let e=this;while(e.parentNode)e=e.parentNode;return!!this.doc&&e===this.doc.documentElement}
  contains(n){for(let e=n;e;e=e.parentNode)if(e===this)return true;return false}
  *walk(){for(const c of this.children){yield c;yield*c.walk()}}
  querySelectorAll(sel){if(sel==='button')return[...this.walk()].filter(e=>e.tagName==='BUTTON');if(sel==='input[type=password]')return[...this.walk()].filter(e=>e.tagName==='INPUT'&&String(e.getAttribute('type')).toLowerCase()==='password');throw new Error('selector '+sel)}
  querySelector(sel){return this.querySelectorAll(sel)[0]||null}
  addEventListener(t,f){(this.ls[t]||(this.ls[t]=[])).push(f)}
  dispatchEvent(ev){this.events.push(ev.type)}
  focus(){if(this.doc)this.doc.activeElement=this}click(){if(this.onclick)this.onclick()}
  key(key){const ev={key,preventDefault(){},stopPropagation(){}};for(let e=this;e;e=e.parentNode)for(const f of e.ls.keydown||[])f(ev)}}
const h=(tag,attrs,...kids)=>{const e=new El(tag,attrs||{});e.append(...kids);return e};
function adopt(doc,e){e.doc=doc;for(const c of e.children)adopt(doc,c);return e}

// ---------------------------------------------------------------- core: eligibility
const d=(tag,o={})=>Object.assign({tag},o);
test('eligible: textarea and text-like inputs only',()=>{
  a.equal(C.eligible(d('textarea')),true);
  for(const t of['text','search','email','url','TEXT',' Search ',null,''])a.equal(C.eligible(d('input',{type:t})),true,String(t));
  for(const t of['password','hidden','number','tel','date','checkbox','radio','file','submit','range','color'])a.equal(C.eligible(d('input',{type:t})),false,t);
  for(const tag of['select','div','button',''])a.equal(C.eligible(d(tag)),false,tag);
  a.equal(C.eligible(d('textarea',{readOnly:true})),false);a.equal(C.eligible(d('input',{disabled:true})),false);a.equal(C.eligible(d('textarea',{ours:true})),false);
  a.equal(C.eligible(null),false);
});
test('eligible: never card, one-time-code or password fields, nor anything in a password form',()=>{
  for(const ac of['cc-number','cc-csc','cc-exp','cc-name','billing cc-number','one-time-code','current-password','new-password','section-x CC-NUMBER'])
    a.equal(C.eligible(d('input',{type:'text',autocomplete:ac})),false,ac);
  for(const ac of['email','name','street-address','off','on','username'])a.equal(C.eligible(d('input',{type:'text',autocomplete:ac})),true,ac);
  for(const n of['password','user_password','userPassword','pwd','passcode','cvv','cvc2','card_number','cardNumber','ccnum','creditCard','otp','totp_code','verification-code','one_time','pin','iban','ssn'])
    a.equal(C.eligible(d('input',{type:'text',name:n})),false,n);
  for(const n of['comment','message','q','search','compass','passenger','spinner','email','title'])a.equal(C.eligible(d('textarea',{name:n})),true,n);
  a.equal(C.eligible(d('input',{type:'text',id:'login-password'})),false);
  a.equal(C.eligible(d('textarea',{passwordForm:true})),false);
});
test('describe reads the element: password form, add-on UI, readonly',()=>{
  const user=h('input',{type:'text',name:'user'}),form=h('form',{},h('div',{},user),h('input',{type:'Password',name:'p'}));
  a.equal(C.describe(user).passwordForm,true);a.equal(C.eligible(C.describe(user)),false);
  const note=h('textarea',{name:'note'});h('form',{},note,h('input',{type:'text'}));a.equal(C.eligible(C.describe(note)),true);
  const mine=h('textarea');h('aside',{'data-omni-addon':'x'},mine);a.equal(C.eligible(C.describe(mine)),false);
  a.equal(C.eligible(C.describe(h('textarea',{readonly:''}))),false);a.equal(C.eligible(C.describe(h('input',{}))),true,'no type = text');
  void form;
});

// ---------------------------------------------------------------- core: keys
test('page key: origin + path, query and fragment ignored; storage key prefixed and stable',()=>{
  const l1={origin:'https://forum.example',pathname:'/t/42/reply',search:'?utm=x',hash:'#a'},l2={origin:'https://forum.example',pathname:'/t/42/reply',search:'',hash:''};
  a.equal(C.pageKey(l1),'https://forum.example/t/42/reply');a.equal(C.storageKey(l1),C.storageKey(l2));
  a.ok(C.storageKey(l1).startsWith('omni-form-saver:'));a.ok(!C.storageKey(l1).includes('forum'),'the address itself is not in the key');
  a.notEqual(C.storageKey(l1),C.storageKey({origin:'https://forum.example',pathname:'/t/43/reply'}));
  a.notEqual(C.storageKey(l1),C.storageKey({origin:'http://forum.example',pathname:'/t/42/reply'}));
  a.equal(C.storageKey(l1),'omni-form-saver:'+C.hash('https://forum.example/t/42/reply'),'same hash every time');
});
test('field key: id, else name + place, else path; each finds the same field again in a fresh copy of the page',()=>{
  const build=()=>{const body=h('body',{},h('header',{},h('input',{type:'search',name:'q'})),
    h('main',{},h('form',{},h('input',{type:'text',id:'subject'}),h('textarea',{name:'body'})),h('form',{},h('input',{type:'text',name:'q'}),h('div',{},h('p'),h('textarea'),h('textarea')))));return body};
  const b1=build(),b2=build();
  const all=b=>[...b.walk()].filter(e=>e.tagName==='INPUT'||e.tagName==='TEXTAREA');
  const keys=all(b1).map(e=>C.fieldKey(e,b1));
  a.deepEqual(keys,['n:input:q#0','i:subject','n:textarea:body#0','n:input:q#1','x:/main[1]/form[2]/div[1]/textarea[1]','x:/main[1]/form[2]/div[1]/textarea[2]']);
  a.equal(new Set(keys).size,keys.length,'unique');
  const twin=all(b2);keys.forEach((k,i)=>a.equal(C.findField(b2,k),twin[i],k));
  a.deepEqual(all(b2).map(e=>C.fieldKey(e,b2)),keys,'same keys on reload');
  for(const bad of['x:/nope[1]','n:input:missing#0','i:none','junk',null,'x:/main[9]'])a.equal(C.findField(b1,bad),null,String(bad));
  // text inserted elsewhere does not move an id or name key
  b2.children[1].children[0].append(h('input',{type:'text',name:'extra'}));a.equal(C.findField(b2,'i:subject'),twin[1]);a.equal(C.findField(b2,'n:input:q#1'),twin[3]);
});

// ---------------------------------------------------------------- core: size caps and expiry
test('size cap: 20 KB of UTF-8 per field; longer or empty text is not kept',()=>{
  a.equal(C.MAX_BYTES,20480);a.equal(C.byteLength('aé€😀'),1+2+3+4);
  const page={f:{}};a.equal(C.put(page,'k','x'.repeat(20480),1000),true);a.equal(page.f.k[0].length,20480);
  a.equal(C.put(page,'k','x'.repeat(20481),2000),false);a.equal('k' in page.f,false,'the older, smaller text goes too: the field changed');
  a.equal(C.put(page,'e','€'.repeat(6826),1),true);a.equal(C.put(page,'e','€'.repeat(6827),1),false,'3-byte characters count as 3');
  a.equal(C.put(page,'z','',1),false);a.equal(C.serialize(page),null,'nothing left = key removed');
  // a stored oversize value (hand-edited, older version) is dropped on read
  const raw=JSON.stringify({f:{a:['x'.repeat(20481),10],b:['ok',10]}});a.deepEqual(Object.keys(C.parse(raw,20).f),['b']);
});
test('field cap: at most 50 per page, oldest dropped',()=>{
  const page={f:{}};for(let i=0;i<55;i++)C.put(page,'k'+i,'t',1000+i);a.equal(Object.keys(page.f).length,50);a.equal('k0' in page.f,false);a.equal('k4' in page.f,false);a.ok('k5' in page.f&&'k54' in page.f);
});
test('expiry: older than 24 h (or from the future, or malformed) is never offered',()=>{
  const now=1_800_000_000_000,H=3600*1000;
  const raw=JSON.stringify({f:{fresh:['a',now-23*H],edge:['b',now-24*H],old:['c',now-24*H-1],future:['d',now+2*H],bad:['e','yesterday'],num:[5,now],arr:'x'}});
  a.deepEqual(Object.keys(C.parse(raw,now).f).sort(),['edge','fresh']);
  a.equal(C.stale(raw,now),false);a.equal(C.stale(JSON.stringify({f:{old:['c',now-25*H]}}),now),true);
  for(const junk of['','{',null,'[]','{"f":3}'])a.deepEqual(C.parse(junk,now),{f:{}},String(junk));
});

// ---------------------------------------------------------------- runtime in a fake page
function fakePage(o={}){
  const timers=new Map(),winL=new Map(),docL=new Map();let tid=0,clock=o.now||1_800_000_000_000;
  const on=(m,t,f)=>{if(!m.has(t))m.set(t,new Set());m.get(t).add(f)},off=(m,t,f)=>m.get(t)?.delete(f),fire=(m,t,ev)=>{for(const f of[...(m.get(t)||[])])f(ev)};
  const doc={activeElement:null,createElement:t=>adopt(doc,new El(t)),addEventListener:(t,f)=>on(docL,t,f),removeEventListener:(t,f)=>off(docL,t,f)};
  doc.documentElement=adopt(doc,new El('html'));doc.body=adopt(doc,new El('body'));doc.documentElement.append(doc.body);
  const data=o.data||new Map();
  const localStorage=o.noStorage?undefined:{get length(){return data.size},key:i=>[...data.keys()][i]??null,getItem:k=>data.has(k)?data.get(k):null,
    setItem:(k,v)=>{if(o.quota)throw new Error('QuotaExceededError');data.set(k,String(v))},removeItem:k=>{data.delete(k)}};
  const hooks={},api={id:'omni-form-saver',top:true,active:o.active!==false,private:o.private,onEnable:f=>hooks.enable=f,onDisable:f=>hooks.disable=f,settings:{get:()=>undefined}};
  let mo=null;
  const win={omniAddon:api,document:doc,localStorage,location:Object.assign({origin:'https://forum.example',pathname:'/t/42/reply'},o.loc),
    Date:{now:()=>clock},Event:class{constructor(type,init){this.type=type;Object.assign(this,init)}},
    MutationObserver:class{constructor(f){this.f=f}observe(){mo=this}disconnect(){if(mo===this)mo=null}},
    setTimeout:f=>{timers.set(++tid,f);return tid},clearTimeout:id=>timers.delete(id),
    addEventListener:(t,f)=>on(winL,t,f),removeEventListener:(t,f)=>off(winL,t,f),Object,Array,String,Math,Number,Map,Set,JSON,Error,RegExp};
  win.window=win;win.globalThis=win;const ctx=vm.createContext(win);
  vm.runInContext(fs.readFileSync(path.join(DIR,'core.js'),'utf8'),ctx);
  const page={doc,data,hooks,api,win,
    add(e,parent=doc.body){adopt(doc,e);parent.append(e);return e},
    run(){vm.runInContext(fs.readFileSync(path.join(DIR,'runtime.js'),'utf8'),ctx)},
    type(el,text,trusted=true){el.value=text;fire(docL,'input',{type:'input',target:el,isTrusted:trusted})},
    submit(form){fire(docL,'submit',{type:'submit',target:form,isTrusted:true})},
    pagehide(){fire(winL,'pagehide',{type:'pagehide'})},pageshow(persisted){fire(winL,'pageshow',{type:'pageshow',persisted})},
    mutate(){if(mo)mo.f([])},observing:()=>!!mo,
    timers:()=>timers.size,flush(){const fs=[...timers.values()];timers.clear();for(const f of fs)f()},
    tick(ms){clock+=ms},bar:()=>[...doc.body.walk()].find(e=>e.className==='omni-fs-bar')||null,
    saved(){const k=C.storageKey(win.location);return data.has(k)?JSON.parse(data.get(k)).f:null},diag:()=>win.OmniFormSaverDiagnostics()};
  return page}
const replyForm=p=>{const t=h('textarea',{name:'body'}),s=h('input',{type:'text',id:'subject'}),f=h('form',{},s,t);p.add(f);return{f,t,s}};

test('runtime: off by default; typing is saved once per burst (debounced) and on pagehide',()=>{
  const m=JSON.parse(fs.readFileSync(path.join(DIR,'manifest.json'),'utf8'));a.equal(m.default_on,false);a.equal(m.private_safe,false);
  const p=fakePage({active:false});const{t}=replyForm(p);p.run();p.type(t,'hello');a.equal(p.timers(),0,'inactive: nothing');a.equal(p.data.size,0);
  p.hooks.enable();p.type(t,'h');p.type(t,'he');p.type(t,'hello world');a.equal(p.timers(),1,'one timer for the burst');a.equal(p.saved(),null);
  p.flush();a.deepEqual(Object.keys(p.saved()),['n:textarea:body#0']);a.equal(p.saved()['n:textarea:body#0'][0],'hello world');
  p.type(t,'hello world!');p.pagehide();a.equal(p.saved()['n:textarea:body#0'][0],'hello world!','flushed on pagehide (reload, Back, navigation)');
  p.type(t,'');p.flush();a.equal(p.saved(),null,'cleared box = entry removed');
  p.type(t,'by script',false);a.equal(p.timers(),0,'untrusted input ignored');
});
test('runtime: password forms, card and code fields are never written',()=>{
  const p=fakePage();const user=h('input',{type:'text',name:'user'}),pw=h('input',{type:'password',name:'pw'});p.add(h('form',{},user,pw));
  const card=p.add(h('input',{type:'text',autocomplete:'cc-number'})),otp=p.add(h('input',{type:'text',autocomplete:'one-time-code'})),hid=p.add(h('input',{type:'hidden',name:'tok'}));
  p.run();for(const el of[user,pw,card,otp,hid])p.type(el,'secret');p.pagehide();a.equal(p.data.size,0);a.equal(p.timers(),0);
});
test('runtime: on return, an empty field with saved text gets the bar; Restore fills only empty fields, never by itself',()=>{
  const data=new Map();const p=fakePage({data});const{t,s}=replyForm(p);p.run();p.type(t,'long reply');p.type(s,'Re: hi');p.pagehide();
  const q=fakePage({data,now:1_800_000_000_000+60000});const r=replyForm(q);r.s.value='typed again';q.run();
  const bar=q.bar();a.ok(bar,'bar shown');a.equal(bar.children[0].textContent,'Restore what you typed?');a.equal(r.t.value,'','not auto-filled');
  a.equal(q.doc.activeElement.className,'omni-fs-btn omni-fs-restore','Restore has focus (controller)');
  q.doc.activeElement.key('ArrowRight');a.equal(q.doc.activeElement.textContent,'Dismiss');q.doc.activeElement.key('ArrowLeft');
  q.doc.activeElement.click();a.equal(r.t.value,'long reply');a.equal(r.s.value,'typed again','a field the user filled is left alone');
  a.deepEqual(r.t.events,['input','change']);a.equal(q.bar(),null);
});
test('runtime: no bar when the field is already filled or nothing is saved; Dismiss deletes; Escape keeps',()=>{
  const data=new Map();const p=fakePage({data});const{t}=replyForm(p);p.run();p.type(t,'draft');p.pagehide();
  const full=fakePage({data});const f=replyForm(full);f.t.value='server draft';full.run();a.equal(full.bar(),null);
  const esc=fakePage({data});replyForm(esc);esc.run();esc.bar().children[1].children[0].key('Escape');a.equal(esc.bar(),null);a.ok(esc.saved(),'Escape keeps the text');
  const dis=fakePage({data});replyForm(dis);dis.run();dis.bar().children[1].children[1].click();a.equal(dis.bar(),null);a.equal(dis.saved(),null,'Dismiss deletes');
  const none=fakePage();replyForm(none);none.run();a.equal(none.bar(),null);a.equal(none.observing(),false,'nothing saved: no observer');
});
test('runtime: submit clears the page entry',()=>{
  const p=fakePage();const{f,t}=replyForm(p);p.run();p.type(t,'sent text');p.flush();a.ok(p.saved());p.type(t,'sent text!');p.submit(f);
  a.equal(p.saved(),null);a.equal(p.timers(),0,'pending write dropped');p.pagehide();a.equal(p.saved(),null);
});
test('runtime: text older than 24 h is not offered and is swept',()=>{
  const data=new Map();const p=fakePage({data});const{t}=replyForm(p);p.run();p.type(t,'old');p.pagehide();
  const other=C.PREFIX+'zzz';data.set(other,JSON.stringify({f:{a:['x',1]}}));data.set('site-own-key','keep');
  const q=fakePage({data,now:1_800_000_000_000+C.MAX_AGE_MS+1});replyForm(q);q.run();a.equal(q.bar(),null);
  a.equal(data.has(other),false,'stale key under our prefix swept');a.equal(data.get('site-own-key'),'keep','the site\'s own keys untouched');a.equal(q.saved(),null);
});
test('runtime: a form drawn later by script is found on DOM changes (debounced, then the watch stops)',()=>{
  const data=new Map();const p=fakePage({data});const{t}=replyForm(p);p.run();p.type(t,'spa text');p.pagehide();
  const q=fakePage({data});q.run();a.equal(q.bar(),null);a.equal(q.observing(),true);q.mutate();q.mutate();a.equal(q.timers(),1);
  replyForm(q);q.flush();a.ok(q.bar());a.equal(q.observing(),false);
});
test('runtime: private tabs and pages without localStorage do nothing',()=>{
  const p=fakePage({private:true});const{t}=replyForm(p);p.run();p.type(t,'x');p.pagehide();a.equal(p.data.size,0);a.equal(p.win.OmniFormSaverDiagnostics,undefined);
  const q=fakePage({noStorage:true});const r=replyForm(q);q.run();q.type(r.t,'x');q.pagehide();a.equal(q.diag().enabled,false);
  const z=fakePage({quota:true});const s=replyForm(z);z.run();z.type(s.t,'x');z.pagehide();a.equal(z.data.size,0);
});
test('runtime: disable flushes and removes the bar and listeners',()=>{
  const data=new Map();const p=fakePage({data});const{t}=replyForm(p);p.run();p.type(t,'abc');p.hooks.disable();a.equal(p.saved()['n:textarea:body#0'][0],'abc');
  p.type(t,'later');p.pagehide();a.equal(p.saved()['n:textarea:body#0'][0],'abc');
  const q=fakePage({data});replyForm(q);q.run();a.ok(q.bar());q.hooks.disable();a.equal(q.bar(),null);
});
test('the bar is add-on UI (data-omni-addon) and the stylesheet only styles it',()=>{
  const data=new Map();const p=fakePage({data});const{t}=replyForm(p);p.run();p.type(t,'x');p.pagehide();
  const q=fakePage({data});replyForm(q);q.run();a.equal(q.bar().getAttribute('data-omni-addon'),'omni-form-saver');
  const css=fs.readFileSync(path.join(DIR,'addon.css'),'utf8');for(const r of css.split('}').filter(r=>r.includes('{')&&!r.trim().startsWith('@')))a.match(r.trim(),/^\.omni-fs-/);
});
