// Omni add-on "Sticky bar hider": page glue. MIT, Omnibloom contributors.
// Fixed / sticky header and footer bars slide away while you scroll down and come back when you scroll up.
(()=>{'use strict';const api=window.omniAddon;if(!api||!api.top)return;const core=OmniStickyCore;
let enabled=false,state={hidden:false,anchor:0},bars=new Map(),scanTimer=0,frame=0;
const ATTR='data-omni-sticky';
function scan(){scanTimer=0;if(!enabled)return;const win={w:window.innerWidth,h:window.innerHeight},want=api.settings.get('which')||'both';
  for(const [el] of bars)if(!el.isConnected)bars.delete(el);
  for(const el of document.body?document.body.querySelectorAll('*'):[]){if(el.closest('[data-omni-addon]'))continue;
    let cs;try{cs=getComputedStyle(el)}catch(_){continue}
    if(cs.position!=='fixed'&&cs.position!=='sticky')continue;
    const edge=core.isBar(el.getBoundingClientRect(),win,cs.position,el.tagName,el.getAttribute('role'));
    if(!edge||(want!=='both'&&want!==edge)){if(bars.has(el)){el.removeAttribute(ATTR);bars.delete(el)}continue}
    if(!bars.has(el)){bars.set(el,edge);el.setAttribute(ATTR,edge)}}
  apply()}
function apply(){for(const [el,edge] of bars)el.setAttribute(ATTR,state.hidden?edge+' hidden':edge)}
function onScroll(){if(frame)return;frame=requestAnimationFrame(()=>{frame=0;const next=core.decide(state,window.scrollY||0);
  if(next.hidden!==state.hidden){state=next;apply()}else state=next})}
function later(){if(!scanTimer)scanTimer=setTimeout(scan,600)}
let observer=null;
function start(){if(enabled)return;enabled=true;state={hidden:false,anchor:window.scrollY||0};window.addEventListener('scroll',onScroll,{passive:true});
  window.addEventListener('resize',later);observer=new MutationObserver(later);observer.observe(document.documentElement,{childList:true,subtree:true});scan()}
function stop(){enabled=false;window.removeEventListener('scroll',onScroll);window.removeEventListener('resize',later);if(observer)observer.disconnect();observer=null;
  clearTimeout(scanTimer);scanTimer=0;for(const [el] of bars)el.removeAttribute(ATTR);bars.clear()}
api.onEnable(start);api.onDisable(stop);api.onSettings(()=>{if(enabled){for(const [el] of bars)el.removeAttribute(ATTR);bars.clear();scan()}});if(api.active)start()})();
