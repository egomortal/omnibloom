// Omni add-on "Search blocklist": pure logic (no page changes). MIT, Omnibloom contributors.
// Domain list rules, engine detection, redirect unwrapping and finding result blocks on Google / DuckDuckGo / Bing
// search pages. Reads only nodeType, localName/tagName, childNodes (or children) and getAttribute, so it runs on the
// live document and on the tests' small parsed trees.
(function(root,factory){const value=factory();if(typeof module==='object'&&module.exports)module.exports=value;else root.OmniSearchBlockCore=value})(globalThis,()=>{'use strict';
const MAX_DOMAINS=200,MAX_INPUT=2048,MAX_ELEMENTS=60000,MAX_RESULTS=300,MAX_UNWRAP=3,STORAGE_KEY='blocked-v1';
const LABEL=/^(?!-)[a-z0-9-]{1,63}(?<!-)$/;

// ---- Domains ----
// "https://User@WWW.Example.COM:8080/path?q" -> "example.com". Lowercase, IDN to punycode (xn--), no scheme, port,
// path, leading "*." or "www.", or trailing dot. At least two labels; anything else is null.
function normalise(input){let s=String(input==null?'':input).trim();if(!s||s.length>MAX_INPUT)return null;
  s=s.replace(/^[a-z][a-z0-9+.-]*:\/\//i,'').replace(/^\/\//,'').split(/[\/?#\\]/)[0];s=s.slice(s.lastIndexOf('@')+1).replace(/^\*\./,'');
  if(!s||!s.includes('.')||/[\s<>"'`]/.test(s))return null;let host;try{host=new URL('http://'+s+'/').hostname}catch(_){return null}
  host=host.toLowerCase().replace(/\.$/,'');if(host.startsWith('['))return null;
  if(host.startsWith('www.')&&host.split('.').length>2)host=host.slice(4);
  if(host.length>253)return null;const labels=host.split('.');if(labels.length<2||!labels.every(l=>LABEL.test(l)))return null;
  if(/^\d+$/.test(labels[labels.length-1])&&!/^\d{1,3}(\.\d{1,3}){3}$/.test(host))return null;return host}
// Any input (array, newline / comma / space separated text) -> unique normalised list, at most 200, first kept.
function parseList(raw){const parts=Array.isArray(raw)?raw:typeof raw==='string'?raw.split(/[\s,;]+/):[];const out=[],seen=new Set();
  for(const p of parts){if(out.length>=MAX_DOMAINS)break;if(typeof p!=='string')continue;const d=normalise(p);if(d&&!seen.has(d)){seen.add(d);out.push(d)}}return out}
// A host's own name (lowercase, no trailing dot), for matching.
function hostOf(h){return String(h||'').toLowerCase().replace(/\.$/,'')}
// The list entry that blocks host: the host itself or a parent domain; "example.com" never matches "evil-example.com".
function matchOf(host,set){host=hostOf(host);if(!host||!set||!set.size)return null;
  for(let h=host;h;){if(set.has(h))return h;const i=h.indexOf('.');if(i<0)break;h=h.slice(i+1)}return null}
const isBlocked=(host,set)=>matchOf(host,set)!==null;
function add(list,domain){const d=normalise(domain),l=parseList(list);if(!d)return{list:l,added:null,full:false};if(l.includes(d))return{list:l,added:d,full:false};
  if(l.length>=MAX_DOMAINS)return{list:l,added:null,full:true};return{list:[...l,d],added:d,full:false}}
function remove(list,domain){const d=normalise(domain);return parseList(list).filter(x=>x!==d)}
// What "Block this site" stores for a result host: the host without "www.".
const siteOf=host=>normalise(hostOf(host));

// ---- Engines ----
const GOOGLE=/^(?:www\.)?google\.(?:com?\.)?[a-z]{2,3}$/;
function engine(loc){if(!loc)return null;const host=hostOf(loc.hostname),path=String(loc.pathname||'/'),q=String(loc.search||'');
  if(GOOGLE.test(host)&&path==='/search')return'google';
  if((host==='duckduckgo.com'||host==='www.duckduckgo.com')&&(path==='/'||path==='')&&/[?&]q=/.test(q))return'duckduckgo';
  if(host==='html.duckduckgo.com'&&/^\/html\/?$/.test(path))return'duckduckgo';
  if((host==='bing.com'||host==='www.bing.com')&&path==='/search')return'bing';return null}

// ---- Redirect links ----
function b64url(s){s=String(s).replace(/-/g,'+').replace(/_/g,'/');while(s.length%4)s+='=';const dec=globalThis.atob;if(typeof dec!=='function')return null;
  try{const bin=dec(s);try{return decodeURIComponent(bin.split('').map(c=>'%'+c.charCodeAt(0).toString(16).padStart(2,'0')).join(''))}catch(_){return bin}}catch(_){return null}}
// Google /url?q= (or url=), DuckDuckGo /l/?uddg=, Bing /ck/a?u=a1<base64url>; nested up to 3 times. Returns an http(s) URL or null.
function unwrap(href,base){if(href==null||String(href).trim()==='')return null;let u;try{u=new URL(String(href||''),base||undefined)}catch(_){return null}
  for(let i=0;i<=MAX_UNWRAP;i++){if(u.protocol!=='http:'&&u.protocol!=='https:')return null;const h=hostOf(u.hostname),p=u.searchParams;let next=null;
    if(GOOGLE.test(h)&&(u.pathname==='/url'||u.pathname==='/interstitial'))next=p.get('q')||p.get('url');
    else if((h==='duckduckgo.com'||h.endsWith('.duckduckgo.com'))&&/^\/l\/?$/.test(u.pathname))next=p.get('uddg');
    else if((h==='bing.com'||h==='www.bing.com')&&u.pathname==='/ck/a'){const v=p.get('u')||'';next=v.startsWith('a1')?b64url(v.slice(2)):null;if(!next)return null}
    if(!next)return u.href;if(i===MAX_UNWRAP)return null;try{u=new URL(next)}catch(_){return null}}return null}
function targetHost(href,base){const r=unwrap(href,base);if(!r)return null;try{return hostOf(new URL(r).hostname)||null}catch(_){return null}}

// ---- Result blocks ----
const tag=n=>n&&n.nodeType===1?String(n.localName||n.tagName||'').toLowerCase():'';
const attr=(n,k)=>{const v=n.getAttribute?n.getAttribute(k):null;return v==null?'':String(v)};
const cls=(n,c)=>(' '+attr(n,'class').replace(/\s+/g,' ')+' ').includes(' '+c+' ');
const kids=n=>n.children||[...(n.childNodes||[])].filter(c=>c.nodeType===1);
const ours=n=>attr(n,'data-omni-addon')!=='';
function first(n,pred,budget){const stack=[...kids(n)].reverse();while(stack.length&&budget.n-->0){const e=stack.pop();if(ours(e))continue;if(pred(e))return e;const k=kids(e);for(let i=k.length-1;i>=0;i--)stack.push(k[i])}return null}
const hasHref=e=>tag(e)==='a'&&attr(e,'href')!=='';
const ENGINES={
  google:{box:e=>(tag(e)==='div'&&(cls(e,'MjjYud')||cls(e,'g'))),
    link:(e,b)=>first(e,x=>hasHref(x)&&!!first(x,y=>tag(y)==='h3',b),b)},
  duckduckgo:{box:e=>(tag(e)==='article'&&attr(e,'data-testid')==='result')||(tag(e)==='div'&&cls(e,'result')&&(cls(e,'results_links')||cls(e,'web-result'))&&!cls(e,'result--ad')),
    link:(e,b)=>first(e,x=>hasHref(x)&&(attr(x,'data-testid')==='result-title-a'||cls(x,'result__a')),b)||first(e,hasHref,b)},
  bing:{box:e=>tag(e)==='li'&&cls(e,'b_algo'),
    link:(e,b)=>{const h2=first(e,x=>tag(x)==='h2',b);return(h2&&first(h2,hasHref,b))||first(e,hasHref,b)}}};
// [{node, href, host}] for each result block on the page, outermost blocks only, in page order.
function findResults(doc,eng,base){const E=ENGINES[eng],out=[];if(!E||!doc)return out;const start=doc.body||doc.documentElement||doc;if(!start)return out;
  const budget={n:MAX_ELEMENTS},stack=[start];
  while(stack.length&&budget.n-->0&&out.length<MAX_RESULTS){const e=stack.pop();if(e!==start&&ours(e))continue;
    if(e!==start&&E.box(e)){const a=E.link(e,{n:2000});const host=a?targetHost(attr(a,'href'),base):null;if(host){out.push({node:e,href:attr(a,'href'),host});continue}}
    const k=kids(e);for(let i=k.length-1;i>=0;i--)stack.push(k[i])}
  return out}

return Object.freeze({MAX_DOMAINS,STORAGE_KEY,normalise,parseList,matchOf,isBlocked,add,remove,siteOf,engine,unwrap,targetHost,findResults,ENGINES:Object.freeze(Object.keys(ENGINES))})});
