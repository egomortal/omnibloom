// node --test addons/tests   (Search blocklist add-on: domain rules, subdomain matching, redirect unwrapping, the three engines' markup, page glue)
'use strict';
const test=require('node:test'),a=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const C=require('../bundled/omni-search-blocklist/core.js'),{parse}=require('./mini-dom.cjs');
const DIR=path.join(__dirname,'..','bundled','omni-search-blocklist');
const html=name=>fs.readFileSync(path.join(__dirname,'fixtures',name),'utf8');
const hosts=(name,eng,base)=>C.findResults(parse(html(name),base),eng,base).map(r=>r.host);

test('domain normalisation: lowercase, no scheme / user / port / path, no www., punycode, junk refused',()=>{
  for(const[i,o]of[['Example.COM','example.com'],['https://user:pw@WWW.Example.com:8080/a/b?c#d','example.com'],['http://news.example.com/','news.example.com'],
    ['  *.example.org  ','example.org'],['example.com.','example.com'],['//cdn.example.net/x','cdn.example.net'],['Bücher.example.de','xn--bcher-kva.example.de'],
    ['xn--bcher-kva.example.de','xn--bcher-kva.example.de'],['www.co.uk','co.uk'],['www.example','www.example'],['1.2.3.4','1.2.3.4']])a.equal(C.normalise(i),o,i);
  for(const bad of['','  ','localhost','example','-bad-.com','a..b.com','exa mple.com','<script>.com','http://','[::1]',null,undefined,42,'x'.repeat(64)+'.com','a.'+'b'.repeat(2050)])
    a.equal(C.normalise(bad),null,String(bad));
});
test('list: unique, normalised, any separator, capped at 200 (first kept); add / remove',()=>{
  a.deepEqual(C.parseList('Example.com\nhttps://www.example.com/x, spam.example.net; junk  b.example.org'),['example.com','spam.example.net','b.example.org']);
  a.deepEqual(C.parseList(['A.com',7,null,'a.com','https://b.com']),['a.com','b.com']);a.deepEqual(C.parseList(undefined),[]);a.deepEqual(C.parseList({}),[]);
  const many=Array.from({length:250},(_,i)=>'site'+i+'.example');const l=C.parseList(many);a.equal(l.length,200);a.equal(l[0],'site0.example');a.equal(l[199],'site199.example');
  a.deepEqual(C.add(['a.com'],'https://www.B.com/x'),{list:['a.com','b.com'],added:'b.com',full:false});
  a.deepEqual(C.add(['a.com'],'a.com'),{list:['a.com'],added:'a.com',full:false});a.equal(C.add(['a.com'],'nope').added,null);
  const full=C.add(many,'new.example');a.equal(full.full,true);a.equal(full.list.length,200);a.ok(!full.list.includes('new.example'));
  a.deepEqual(C.remove(['a.com','b.com'],'WWW.A.com'),['b.com']);a.equal(C.MAX_DOMAINS,200);
});
test('matching: the domain and its subdomains only; never evil-example.com or example.com.evil.net for example.com',()=>{
  const s=new Set(['example.com','xn--bcher-kva.example.de']);
  for(const h of['example.com','www.example.com','a.b.example.com','EXAMPLE.COM.','xn--bcher-kva.example.de','shop.xn--bcher-kva.example.de'])a.ok(C.isBlocked(h,s),h);
  for(const h of['evil-example.com','notexample.com','example.com.evil.net','example.co','com','example.de','',null])a.ok(!C.isBlocked(h,s),String(h));
  a.equal(C.matchOf('deep.news.example.com',s),'example.com');a.equal(C.matchOf('example.com',new Set()),null);
  a.equal(C.matchOf('x.news.example.com',new Set(['news.example.com','example.com'])),'news.example.com','closest entry first');
  a.equal(C.siteOf('WWW.Example.com'),'example.com');a.equal(C.siteOf('news.example.com'),'news.example.com');
});
test('redirect links: Google /url?q= and url=, DuckDuckGo uddg=, Bing u=a1 base64, nesting; non-http refused',()=>{
  a.equal(C.unwrap('/url?q=https://www.example.com/a%3Fb%3D1&sa=U','https://www.google.co.uk/search?q=x'),'https://www.example.com/a?b=1');
  a.equal(C.unwrap('https://www.google.com/url?url=https%3A%2F%2Fnews.example.com%2F&q=','https://www.google.com/search'),'https://news.example.com/');
  a.equal(C.targetHost('//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.example.com%2Fsoup%3Fa%3D1&rut=x','https://html.duckduckgo.com/html/'),'www.example.com');
  const b=Buffer.from('https://xn--bcher-kva.example.de/ü?x=1').toString('base64url');
  a.equal(C.targetHost('https://www.bing.com/ck/a?!&&p=1&u=a1'+b+'&ntb=1'),'xn--bcher-kva.example.de');
  a.equal(C.targetHost('https://www.bing.com/ck/a?u=zz'),null,'unknown Bing form: no guess');
  const nest='https://www.google.com/url?q='+encodeURIComponent('https://duckduckgo.com/l/?uddg='+encodeURIComponent('https://deep.example.com/'));
  a.equal(C.targetHost(nest),'deep.example.com');
  let loop='https://real.example.com/';for(let i=0;i<5;i++)loop='https://www.google.com/url?q='+encodeURIComponent(loop);a.equal(C.unwrap(loop),null,'too deep');
  for(const bad of['javascript:alert(1)','/url?q=javascript:alert(1)','data:text/html,x','mailto:a@example.com','',null])a.equal(C.targetHost(bad,'https://www.google.com/search'),null,String(bad));
  a.equal(C.unwrap('https://www.google.com/url'),'https://www.google.com/url','no target: the link itself');
  a.equal(C.targetHost('https://plain.example.com/x'),'plain.example.com');
});
test('engines: only the result pages of Google, DuckDuckGo (and its html version) and Bing',()=>{
  const L=u=>{const x=new URL(u);return{hostname:x.hostname,pathname:x.pathname,search:x.search}};
  for(const[u,e]of[['https://www.google.com/search?q=soup','google'],['https://www.google.co.uk/search?q=a','google'],['https://google.com.br/search?q=a','google'],['https://www.google.de/search','google'],
    ['https://duckduckgo.com/?q=soup&ia=web','duckduckgo'],['https://html.duckduckgo.com/html/?q=soup','duckduckgo'],['https://html.duckduckgo.com/html','duckduckgo'],
    ['https://www.bing.com/search?q=soup','bing'],['https://bing.com/search?q=x','bing']])a.equal(C.engine(L(u)),e,u);
  for(const u of['https://www.google.com/','https://www.google.com/maps/search/x','https://images.google.com/search?q=x','https://google.evil.com/search','https://notgoogle.com/search',
    'https://duckduckgo.com/','https://duckduckgo.com/settings','https://www.bing.com/images/search?q=x','https://example.com/search?q=x','https://bing.com.evil.net/search'])a.equal(C.engine(L(u)),null,u);
  a.equal(C.engine(null),null);
});
test('Google fixture: result blocks with an h3 title link; redirects unwrapped; "People also ask" and script links skipped',()=>{
  const base='https://www.google.com/search?q=soup',r=C.findResults(parse(html('search-google.html'),base),'google',base);
  a.deepEqual(r.map(x=>x.host),['www.example.com','news.example.com','evil-example.com','xn--bcher-kva.example.de']);
  a.ok(r.slice(0,3).every(x=>x.node.getAttribute('class')==='MjjYud'),'outer block, so nothing of the result is left');
  const s=new Set(['example.com']);a.deepEqual(r.filter(x=>C.isBlocked(x.host,s)).map(x=>x.host),['www.example.com','news.example.com']);
});
test('DuckDuckGo fixture: html version (uddg links, ads skipped) and the script version (article data-testid=result)',()=>{
  a.deepEqual(hosts('search-duckduckgo.html','duckduckgo','https://html.duckduckgo.com/html/?q=soup'),['www.example.com','shop.example.net','m.example.com','other.example.org']);
});
test('Bing fixture: li.b_algo, title link in h2, /ck/a base64 targets; answer boxes and broken redirects skipped',()=>{
  a.deepEqual(hosts('search-bing.html','bing','https://www.bing.com/search?q=soup'),['www.spam-recipes.example','www.example.com']);
  a.deepEqual(C.findResults(parse(html('search-bing.html')),'nope'),[]);a.deepEqual(C.findResults(null,'bing'),[]);
});
test('source rules: no network, no HTML parsing into the page, off by default, list stays under the storage size',()=>{
  const m=JSON.parse(fs.readFileSync(path.join(DIR,'manifest.json'),'utf8'));a.equal(m.default_on,false);a.deepEqual(m.hosts,[]);a.equal(m.private_safe,true);
  for(const f of['core.js','runtime.js']){const s=fs.readFileSync(path.join(DIR,f),'utf8');
    a.doesNotMatch(s,/\bfetch\(|XMLHttpRequest|WebSocket|EventSource|sendBeacon|importScripts|\beval\(|new Function/);
    a.doesNotMatch(s,/innerHTML|outerHTML|insertAdjacentHTML|document\.write|DOMParser/);
    a.ok(![...s].some(ch=>ch.charCodeAt(0)===0x2028||ch.charCodeAt(0)===0x2029),'no raw line separators');}
  const worst=Array.from({length:200},(_,i)=>(i+'a'.repeat(60)+'.').repeat(3)+'b'.repeat(55-String(i).length)+'.com');
  const big=C.parseList(worst);a.equal(big.length,200);a.ok(big.every(d=>d.length>=240));a.ok(JSON.stringify(big).length<64*1024);
});

// ---- The page glue on a parsed fixture, with the few DOM methods it uses added ----
function page(fixture,href,opts={}){
  const vm=require('node:vm'),doc=parse(html(fixture),href),probe=parse('<div>x</div>').body.childNodes[0];
  const El=probe.constructor,Tx=probe.childNodes[0].constructor,P=El.prototype;
  if(!P._omniTest){P._omniTest=true;
    Object.defineProperty(P,'textContent',{get(){return this.childNodes.map(c=>c.nodeType===8?'':c.textContent).join('')},set(v){for(const c of this.childNodes)c.parentNode=null;this.childNodes=[];if(v!=='')this.append(new Tx(String(v)))}});
    Object.defineProperty(P,'className',{get(){return this.getAttribute('class')||''},set(v){this.attrs.set('class',String(v))}});
    P.setAttribute=function(k,v){this.attrs.set(k,String(v))};P.appendChild=function(c){if(c.parentNode)c.remove();return this.append(c)};
    const nodeAppend=Object.getPrototypeOf(P).append;P.append=function(...cs){let r;for(const c of cs){if(c.parentNode&&c.parentNode!==this)c.remove();r=nodeAppend.call(this,c)}return r};
    P.insertBefore=function(c,ref){if(c.parentNode)c.remove();const i=this.childNodes.indexOf(ref);c.parentNode=this;if(i<0)this.childNodes.push(c);else this.childNodes.splice(i,0,c);return c};
    P.remove=function(){const p=this.parentNode;if(p){p.childNodes=p.childNodes.filter(x=>x!==this);this.parentNode=null}};
    Object.defineProperty(P,'nextSibling',{get(){const p=this.parentNode;return p?p.childNodes[p.childNodes.indexOf(this)+1]||null:null}});
    Object.defineProperty(P,'classList',{get(){const el=this,list=()=>(el.getAttribute('class')||'').split(/\s+/).filter(Boolean),put=l=>el.attrs.set('class',l.join(' '));
      return{contains:c=>list().includes(c),add:(...cs)=>put([...new Set([...list(),...cs])]),remove:(...cs)=>put(list().filter(x=>!cs.includes(x))),
        toggle:(c,on)=>{const has=list().includes(c);on=on===undefined?!has:!!on;if(on&&!has)put([...list(),c]);if(!on&&has)put(list().filter(x=>x!==c));return on}}}});
    P.focus=function(){this.ownerDoc.activeElement=this};P.click=function(){return this.onclick&&this.onclick()};}
  doc.createElement=t=>{const e=new El(t,new Map());e.ownerDoc=doc;return e};doc.activeElement=null;
  let mo=null,timers=new Map(),tid=0;const u=new URL(href),store=new Map(Object.entries(opts.stored||{})),writes=[],hooks={};
  const api={id:'omni-search-blocklist',top:true,active:opts.active!==false,onEnable:f=>hooks.enable=f,onDisable:f=>hooks.disable=f,onSettings:f=>hooks.settings=f,
    settings:{get:k=>k==='button'?opts.button!==false:undefined},
    storage:{get:k=>store.has(k)?JSON.parse(JSON.stringify(store.get(k))):undefined,
      set(k,v){writes.push([k,v]);if(opts.private)return Promise.reject(new Error('error: private tab'));store.set(k,JSON.parse(JSON.stringify(v)));return Promise.resolve(true)}}};
  const win={omniAddon:api,document:doc,location:{href,hostname:u.hostname,pathname:u.pathname,search:u.search},
    MutationObserver:class{constructor(f){this.f=f}observe(){mo=this}disconnect(){if(mo===this)mo=null}},
    setTimeout:f=>{timers.set(++tid,f);return tid},clearTimeout:i=>timers.delete(i),URL,atob,Promise,Object,Array,String,Number,Math,Map,Set,JSON,Error,RegExp,decodeURIComponent};
  win.window=win;win.globalThis=win;vm.createContext(win);
  vm.runInContext(fs.readFileSync(path.join(DIR,'core.js'),'utf8'),win);vm.runInContext(fs.readFileSync(path.join(DIR,'runtime.js'),'utf8'),win);
  const all=()=>{const out=[],walk=n=>{for(const c of n.childNodes)if(c.nodeType===1){out.push(c);walk(c)}};walk(doc);return out};
  const byCls=c=>all().filter(e=>e.classList.contains(c));
  return{doc,store,writes,hooks,all,byCls,api,win,diag:()=>win.OmniSearchBlockDiagnostics&&JSON.parse(JSON.stringify(win.OmniSearchBlockDiagnostics())),
    notice:()=>byCls('omni-sb-notice')[0]||null,buttons:()=>byCls('omni-sb-btn').filter(b=>!b.classList.contains('omni-sb-show')),
    mutate(records){if(mo)mo.f(records)},observing:()=>!!mo,timers:()=>timers.size,flush(){const fs=[...timers.values()];timers.clear();for(const f of fs)f()},
    tick:()=>new Promise(r=>setImmediate(()=>setImmediate(r)))};
}
const G='https://www.google.com/search?q=soup';
test('page glue: off by default; nothing on other pages; hides blocked results with a count line at the top',()=>{
  const off=page('search-google.html',G,{active:false,stored:{'blocked-v1':['example.com']}});a.equal(off.byCls('omni-sb-hidden').length,0);a.equal(off.buttons().length,0);a.equal(off.notice(),null);
  const other=page('search-google.html','https://www.google.com/maps',{stored:{'blocked-v1':['example.com']}});a.equal(other.diag(),undefined,'not a result page: the runtime stops at once');a.equal(other.byCls('omni-sb-hidden').length,0);
  const p=page('search-google.html',G,{stored:{'blocked-v1':['Example.com','junk']}});
  a.equal(p.byCls('omni-sb-hidden').length,2);a.deepEqual(p.diag(),{enabled:true,engine:'google',results:4,hidden:2,shown:false,blocked:1});
  const n=p.notice();a.ok(n);a.equal(n.textContent,'2 results hiddenShow');a.equal(n.parentNode.getAttribute('id'),'rso');a.equal(n.nextSibling.getAttribute('class').split(' ')[0],'MjjYud','first in the results');
  a.equal(n.getAttribute('data-omni-addon'),'omni-search-blocklist');
  a.equal(p.buttons().length,4,'every result gets a button');a.ok(p.buttons().every(b=>b.localName==='button'&&b.type==='button'),'real buttons: D-pad and pointer reach them');
  const visible=p.buttons().filter(b=>!b.parentNode.classList.contains('omni-sb-hidden'));a.deepEqual(visible.map(b=>b.textContent),['Block this site','Block this site']);
  a.equal(visible[0].getAttribute('aria-label'),'Block evil-example.com from search results');
  n.childNodes[1].click();a.equal(p.byCls('omni-sb-hidden').length,0);a.equal(p.byCls('omni-sb-shown').length,2);a.equal(p.notice().textContent,'2 results from blocked sites shownHide');
  a.deepEqual(p.byCls('omni-sb-shown').map(e=>e.childNodes.at(-1).textContent),['Unblock example.com','Unblock example.com']);
  p.notice().childNodes[1].click();a.equal(p.byCls('omni-sb-hidden').length,2);
  p.hooks.disable();a.equal(p.byCls('omni-sb-hidden').length,0);a.equal(p.buttons().length,0);a.equal(p.notice(),null);a.equal(p.observing(),false);
});
test('page glue: Block this site stores the host without www., hides it and moves focus to Show; Unblock takes it back',async()=>{
  const p=page('search-bing.html','https://www.bing.com/search?q=soup');a.equal(p.notice(),null);a.equal(p.buttons().length,2);
  await p.buttons()[0].click();a.deepEqual(p.store.get('blocked-v1'),['spam-recipes.example']);a.equal(p.byCls('omni-sb-hidden').length,1);
  a.equal(p.notice().textContent,'1 result hiddenShow');a.equal(p.doc.activeElement,p.notice().childNodes[1],'focus stays on screen');
  p.notice().childNodes[1].click();const un=p.byCls('omni-sb-shown')[0].childNodes.at(-1);a.equal(un.textContent,'Unblock spam-recipes.example');
  await un.click();a.deepEqual(p.store.get('blocked-v1'),[]);a.equal(p.byCls('omni-sb-hidden').length+p.byCls('omni-sb-shown').length,0);a.equal(p.notice(),null);
});
test('page glue: list full at 200; private tab keeps a block for the page only; button setting',async()=>{
  const many=Array.from({length:200},(_,i)=>'s'+i+'.example');const f=page('search-duckduckgo.html','https://html.duckduckgo.com/html/?q=soup',{stored:{'blocked-v1':many}});
  await f.buttons()[0].click();a.equal(f.writes.length,0,'nothing written when full');a.equal(f.store.get('blocked-v1').length,200);
  const q=page('search-duckduckgo.html','https://duckduckgo.com/?q=soup',{private:true});await q.buttons()[2].click();
  a.equal(q.byCls('omni-sb-hidden').length,1);a.match(q.notice().textContent,/this page only/);a.equal(q.writes.length,1);
  const nb=page('search-duckduckgo.html','https://duckduckgo.com/?q=soup',{button:false,stored:{'blocked-v1':['example.com']}});
  a.equal(nb.buttons().length,0);a.equal(nb.byCls('omni-sb-hidden').length,2,'www.example.com and m.example.com');
});
test('page glue: results added later are found again, throttled; its own changes do not wake it',()=>{
  const p=page('search-google.html',G,{stored:{'blocked-v1':['spam.example']}});a.equal(p.notice(),null);a.ok(p.observing());
  const rso=p.all().find(e=>e.getAttribute('id')==='rso'),late=parse('<div class="g"><a href="/url?q=https://a.spam.example/"><h3>Late</h3></a></div>').body.childNodes[0];
  rso.appendChild(late);const rec={target:rso,addedNodes:[late],removedNodes:[]};p.mutate([rec]);p.mutate([rec]);p.mutate([rec]);a.equal(p.timers(),1,'one look per 300 ms');
  p.flush();a.ok(late.classList.contains('omni-sb-hidden'));a.equal(p.notice().textContent,'1 result hiddenShow');
  p.mutate([{target:rso,addedNodes:[p.notice()],removedNodes:[]}]);a.equal(p.timers(),0,'own nodes ignored');
});
