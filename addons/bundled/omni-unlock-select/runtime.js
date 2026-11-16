// Omni add-on "Unlock selection": page glue. MIT, Omnibloom contributors.
// Omni runs add-ons in their own isolated JavaScript world (OmniBlocker.cpp addonWorld), so the page's
// EventTarget.prototype.addEventListener cannot be wrapped from here, and injecting a page-world <script> would
// break on strict CSP sites and expose Omni to the page. Instead, sharing the DOM is enough:
//  1. addon.css (a user-level sheet, so its !important beats the page's) gives page text user-select:text again,
//     only under <html class="omni-unlock-select">, never on buttons, fields, media or Omni UI;
//  2. a window capture listener, registered at document_start before any page script, sees selectstart / copy /
//     contextmenu / dragstart / mousedown first. It never touches text fields or controls. On plain text it stops the
//     event (stopImmediatePropagation) only for event types this page has been seen cancelling on text: after each
//     event it checks defaultPrevented (also set by inline "return false" / returnValue=false), and a harmless
//     synthetic selectstart probe finds document-wide selection blockers before the first press;
//  3. on* attributes whose code cancels (oncopy="return false" etc.) are removed on load and on DOM changes
//     (throttled), and put back if the add-on is switched off.
// A page whose main content is a big <canvas> (games, maps, editors) is left completely alone.
(()=>{'use strict';const api=window.omniAddon;if(!api||!api.top)return;const core=OmniUnlockSelectCore;
let enabled=false,canvasApp=false,observer=null,scanTimer=0,lastScan=-1e9,probing=false,shielded=0;
const seen={},stripped=[];const CAP={capture:true};
const now=()=>Date.now();
const opts=e=>({mousedown:api.settings.get('mousedown')!==false,button:e&&typeof e.button==='number'?e.button:null});
const html=()=>document.documentElement;
function applyClass(){const h=html();if(!h||!h.classList)return;if(enabled&&!canvasApp)h.classList.add(core.ROOT_CLASS);else h.classList.remove(core.ROOT_CLASS)}
// ---- events ----
function onEvent(e){if(!enabled||canvasApp||probing||!e||!e.isTrusted)return;const k=core.kind(e.target);
  if(core.shield(e.type,k,seen,opts(e))){e.stopImmediatePropagation();shielded++;return}
  if(k!=='text')return;
  // Let the page handle it, then see whether it cancelled the default (selection, copy, menu, drag).
  setTimeout(()=>{if(enabled&&core.learn(e.type,k,e.defaultPrevented))seen[e.type]=(seen[e.type]||0)+1},0)}
// A synthetic selectstart on <body>: page handlers that cancel every selection (document.onselectstart=()=>false)
// show themselves without the user losing a first attempt. Nothing else is probed (copy / contextmenu probes could
// make pages show alerts or menus).
function probe(){const b=document.body;if(!enabled||canvasApp||!b||(seen.selectstart||0)>=core.THRESHOLD.selectstart)return;
  let ev=null;probing=true;try{ev=new Event('selectstart',{bubbles:true,cancelable:true});b.dispatchEvent(ev)}catch(_){ev=null}probing=false;
  if(ev&&ev.defaultPrevented)seen.selectstart=core.THRESHOLD.selectstart}
// ---- canvas apps ----
function checkCanvas(){let rects=[];try{rects=[...document.querySelectorAll('canvas')].map(c=>{const r=c.getBoundingClientRect();return{w:r.width,h:r.height}})}catch(_){}
  const big=core.bigCanvas(rects,{w:window.innerWidth||0,h:window.innerHeight||0});if(big!==canvasApp){canvasApp=big;if(big)restore();applyClass()}}
// ---- inline blockers ----
function scan(){lastScan=now();checkCanvas();if(!enabled||canvasApp)return;let list=[];try{list=document.querySelectorAll(core.ATTR_SELECTOR)}catch(_){}
  for(const el of list)for(const a of core.stripList(el)){stripped.push([el,a,el.getAttribute(a)]);el.removeAttribute(a)}}
function restore(){for(const[el,a,v]of stripped.splice(0))if(el.isConnected!==false&&el.getAttribute(a)==null)try{el.setAttribute(a,v)}catch(_){}}
function onMutate(){if(!enabled||scanTimer)return;scanTimer=setTimeout(()=>{scanTimer=0;scan()},Math.max(0,lastScan+core.SCAN_MS-now()))}
function watch(){if(observer||typeof MutationObserver!=='function'||!html())return;observer=new MutationObserver(onMutate);
  observer.observe(html(),{childList:true,subtree:true,attributes:true,attributeFilter:core.ATTRS.slice()})}
function onReady(){if(!enabled)return;scan();probe();watch()}
function onLoad(){if(!enabled)return;checkCanvas();probe()}
// ---- life cycle ----
function start(){if(enabled)return;enabled=true;for(const t of core.TYPES)window.addEventListener(t,onEvent,CAP);applyClass();
  addEventListener('load',onLoad);if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',onReady);else onReady()}
function stop(){if(!enabled)return;enabled=false;for(const t of core.TYPES)window.removeEventListener(t,onEvent,CAP);
  removeEventListener('load',onLoad);document.removeEventListener('DOMContentLoaded',onReady);
  if(observer){observer.disconnect();observer=null}clearTimeout(scanTimer);scanTimer=0;restore();applyClass()}
api.onEnable(start);api.onDisable(stop);
window.OmniUnlockSelectDiagnostics=()=>({enabled,canvasApp,seen:Object.assign({},seen),shielded,stripped:stripped.length,observing:!!observer});
if(api.active)start()})();
