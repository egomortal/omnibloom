// Omni add-on "Site redirects": pure URL mapping (no page changes). MIT, Omnibloom contributors.
// Three opt-in rules: www/new.reddit.com -> old.reddit.com, YouTube /shorts/<id> -> /watch?v=<id>, AMP -> canonical
// (the page's own <link rel=canonical> on the same registrable domain, and google.com/amp/s/<url> -> https://<url>).
// Every function takes strings and returns a string or null; hosts are compared exactly, never by substring.
(function(root,factory){const value=factory();if(typeof module==='object'&&module.exports)module.exports=value;else root.OmniRedirectsCore=value})(globalThis,()=>{'use strict';
const MAX_URL=8192,FLAG_KEY='omni-site-redirects:v1',MAX_FLAGS=40;
const RULES=Object.freeze(['reddit','shorts','amp']);
const REDDIT=new Set(['reddit.com','www.reddit.com','new.reddit.com']);
const YOUTUBE=new Set(['youtube.com','www.youtube.com','m.youtube.com']);
const GOOGLE=new Set(['google.com','www.google.com']);
// Pages old.reddit.com cannot show, and the account / form pages whose results come from a POST: left alone.
const REDDIT_SKIP=/^\/(media|settings|chat|notifications|login|register|logout|password|account|api|svc|submit|verification|poll|answers|appeal|premium|coins|user\/me)(\/|$)/i;
// Google's own AMP viewer parameters (never part of the publisher's address).
const GOOGLE_PARAMS=new Set(['usqp','amp_js_v','amp_gsa','amp_ct','amp_tf','_gsa','ampshare','aoh','csi','referrer','outputType']);
const VIDEO_ID=/^[A-Za-z0-9_-]{11}$/;

function parse(s,base){if(typeof s!=='string'||!s||s.length>MAX_URL)return null;let u;try{u=base?new URL(s,base):new URL(s)}catch(_){return null}
  if(u.protocol!=='https:'&&u.protocol!=='http:')return null;if(u.username||u.password)return null;return u}
// Exact host, lower case, default port only. A trailing dot or any port means "not this site".
const hostOf=u=>u.port?'':u.hostname.toLowerCase();

// (a) Reddit: same path, query and fragment on old.reddit.com.
function reddit(href){const u=parse(href);if(!u||!REDDIT.has(hostOf(u)))return null;if(REDDIT_SKIP.test(u.pathname))return null;
  return 'https://old.reddit.com'+u.pathname+u.search+u.hash}

// (b) YouTube Shorts: /shorts/<11-char id>[/] -> /watch?v=<id>, other query parameters kept after v (a stray v dropped).
function shorts(href){const u=parse(href);if(!u||!YOUTUBE.has(hostOf(u)))return null;const m=/^\/shorts\/([^/]+)\/?$/.exec(u.pathname);if(!m||!VIDEO_ID.test(m[1]))return null;
  const q=new URLSearchParams(u.search);q.delete('v');const rest=q.toString();return 'https://'+hostOf(u)+'/watch?v='+m[1]+(rest?'&'+rest:'')+u.hash}

// ---- registrable domain (eTLD+1), conservative: an unknown multi-part suffix gives a shorter match, never a wider one ----
const SUFFIX2=new Set(['github.io','gitlab.io','blogspot.com','herokuapp.com','appspot.com','netlify.app','vercel.app','pages.dev','workers.dev','web.app',
  'firebaseapp.com','azurewebsites.net','cloudfront.net','wordpress.com','tumblr.com','substack.com','medium.com','wixsite.com','weebly.com','glitch.me',
  'onrender.com','fly.dev','repl.co','neocities.org','amazonaws.com','s3.amazonaws.com','ngrok.io','ngrok-free.app','duckdns.org','no-ip.org','dyndns.org']);
const CC_SLD=/^(co|com|net|org|gov|edu|ac|or|ne|go|mil|ltd|plc|me|nic|sch|nom|gob|gen|biz|info|in|lg|ad|ed|gr|mod|police|nhs)$/;
const IPV4=/^\d{1,3}(\.\d{1,3}){3}$/;
function registrable(host){if(typeof host!=='string')return null;const h=host.toLowerCase();if(!h||h.endsWith('.')||h.length>253)return null;
  if(IPV4.test(h)||h.includes(':')||h.startsWith('['))return h;   // an IP address only matches itself
  if(!/^[a-z0-9.-]+$/.test(h)||h.includes('..'))return null;const p=h.split('.');if(p.length<2)return null;
  const two=p.slice(-2).join('.'),three=p.slice(-3).join('.');
  let n=2;if(SUFFIX2.has(two)||SUFFIX2.has(three)||(p[p.length-1].length===2&&CC_SLD.test(p[p.length-2])))n=SUFFIX2.has(three)?4:3;
  return p.length>=n?p.slice(-n).join('.'):null}
const sameSite=(a,b)=>{const x=registrable(a),y=registrable(b);return!!x&&x===y};
const noHash=u=>u.origin+u.pathname+u.search;

// (c1) google.com/amp/s/<url> -> https://<url>. Google's viewer parameters dropped, the rest of the query and the fragment kept.
function googleAmp(href){const u=parse(href);if(!u||!GOOGLE.has(hostOf(u)))return null;if(!u.pathname.startsWith('/amp/s/'))return null;
  let inner=u.pathname.slice(7);if(!inner)return null;
  // Some links encode the whole publisher address (example.com%2Fstory%3Fid%3D1): decoded once, only then.
  if(!inner.includes('/')&&/%2f|%3f/i.test(inner)){try{inner=decodeURIComponent(inner)}catch(_){return null}}
  if(/^[\/\\]|[\\@\s]|^[^/?#]*%/.test(inner))return null;   // no scheme-relative, backslash, userinfo, spaces or encoded host
  const t=parse('https://'+inner);if(!t)return null;const h=hostOf(t);
  if(!h||!h.includes('.')||IPV4.test(h)||h.startsWith('[')||h==='localhost'||h.endsWith('.localhost')||GOOGLE.has(h)||/(^|\.)google\.[a-z.]+$/.test(h))return null;
  if(inner.slice(0,h.length).toLowerCase()!==h)return null;   // the host must be the first thing, exactly
  const q=new URLSearchParams(t.search);for(const[k,v]of new URLSearchParams(u.search))if(!GOOGLE_PARAMS.has(k))q.append(k,v);
  const s=q.toString();return 'https://'+h+t.pathname+(s?'?'+s:'')+(t.hash||u.hash)}

// (c2) An AMP page's own canonical: same registrable domain, no downgrade to http, not the page itself, and not the page we
// just came from (an AMP page reached from its canonical stays: that is the user's choice, and it breaks any A<->B loop).
function canonical(pageHref,canonicalHref,referrer){const p=parse(pageHref);if(!p||typeof canonicalHref!=='string')return null;const c=parse(canonicalHref.trim(),p.href);if(!c)return null;
  if(c.protocol==='http:'&&p.protocol==='https:')return null;if(c.port!==p.port)return null;
  if(!sameSite(c.hostname,p.hostname))return null;if(noHash(c)===noHash(p))return null;
  // A cross-origin referrer is cut to its origin by the default referrer policy: then the canonical's origin is enough to stay.
  const r=parse(referrer||'');if(r&&(noHash(r)===noHash(c)||(r.pathname==='/'&&!r.search&&r.origin===c.origin&&r.origin!==p.origin)))return null;
  return c.origin+c.pathname+c.search+(c.hash||p.hash)}

// The address-only rules in order; the first that applies wins. settings: {reddit, shorts, amp} booleans.
function forUrl(href,settings){const s=settings||{};
  if(s.reddit){const to=reddit(href);if(to)return{rule:'reddit',to}}
  if(s.shorts){const to=shorts(href);if(to)return{rule:'shorts',to}}
  if(s.amp){const to=googleAmp(href);if(to)return{rule:'amp',to}}
  return null}

// Navigation guard: only fresh navigations ('navigate'), never a reload or back/forward.
const freshNavigation=type=>type===undefined||type===null||type==='navigate'||type===0;

// Per-tab flags (sessionStorage of the page we redirected from): the addresses already redirected once in this tab.
// Coming back to one (Back, or the same link again) leaves it alone for the rest of the session.
function readFlags(raw){let v;try{v=JSON.parse(raw||'[]')}catch(_){return[]}return Array.isArray(v)?v.filter(x=>typeof x==='string'&&x.length<=MAX_URL).slice(-MAX_FLAGS):[]}
function addFlag(raw,href){const list=readFlags(raw).filter(x=>x!==flagOf(href));list.push(flagOf(href));return JSON.stringify(list.slice(-MAX_FLAGS))}
const flagOf=href=>{const u=parse(href);return u?noHash(u):String(href).slice(0,MAX_URL)};
const flagged=(raw,href)=>readFlags(raw).includes(flagOf(href));

return Object.freeze({RULES,FLAG_KEY,MAX_FLAGS,reddit,shorts,googleAmp,canonical,registrable,sameSite,forUrl,freshNavigation,readFlags,addFlag,flagged,flagOf});
});
