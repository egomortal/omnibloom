// Omni add-on "Site redirects": page glue. MIT, Omnibloom contributors.
// Runs only on the hosts and paths in manifest.json, never in private tabs (private_safe false). Each rule is its own
// setting, all off by default. At most one redirect per navigation, always location.replace (no extra history entry),
// never on a reload or back/forward, and an address redirected once in this tab is left alone after that (Back).
(()=>{'use strict';const api=window.omniAddon;if(!api||!api.top)return;const core=OmniRedirectsCore;
let enabled=false,done=false,lastHref='',ampWait=false;
const rules=()=>({reddit:api.settings.get('reddit')===true,shorts:api.settings.get('shorts')===true,amp:api.settings.get('amp')===true});
function navType(){try{const n=performance.getEntriesByType('navigation')[0];if(n)return n.type}catch(_){}try{return performance.navigation.type}catch(_){return undefined}}
function flags(){try{return sessionStorage.getItem(core.FLAG_KEY)}catch(_){return null}}
function remember(href){try{sessionStorage.setItem(core.FLAG_KEY,core.addFlag(flags(),href))}catch(_){}}

// One redirect per navigation: `done` for this document; `lastHref` for YouTube's in-page navigations.
function go(from,to){if(done||!to||to===from)return false;done=true;remember(from);
  try{location.replace(to)}catch(_){done=false;return false}return true}
function allowed(href,spa){if(!enabled||done||href===lastHref)return false;lastHref=href;
  if(!spa&&!core.freshNavigation(navType()))return false;return!core.flagged(flags(),href)}

function byUrl(spa){const href=location.href;if(!allowed(href,spa))return;const hit=core.forUrl(href,rules());if(hit)go(href,hit.to)}

// AMP: the page marks itself (<html amp> or <html ⚡>) and names its canonical in <head>.
function isAmp(){const h=document.documentElement;return!!h&&(h.hasAttribute('amp')||h.hasAttribute('⚡'))}
function byCanonical(){ampWait=false;if(!enabled||done||!rules().amp||!isAmp())return;const href=location.href;
  if(!core.freshNavigation(navType())||core.flagged(flags(),href))return;
  let link=null;try{link=document.querySelector('link[rel~="canonical" i][href]')}catch(_){link=document.querySelector('link[rel~="canonical"][href]')}
  if(!link)return;const to=core.canonical(href,link.getAttribute('href'),document.referrer);if(to)go(href,to)}

// YouTube moves between pages without loading one; its own event says when a new address is showing.
function onYtNav(){byUrl(true)}
function onReady(){if(enabled)byCanonical()}
function start(){if(enabled)return;enabled=true;byUrl(false);if(done)return;
  if(document.readyState==='loading'){ampWait=true;document.addEventListener('DOMContentLoaded',onReady,{once:true})}else byCanonical();
  document.addEventListener('yt-navigate-finish',onYtNav)}
function stop(){if(!enabled)return;enabled=false;document.removeEventListener('yt-navigate-finish',onYtNav);if(ampWait)document.removeEventListener('DOMContentLoaded',onReady);ampWait=false}
api.onEnable(start);api.onDisable(stop);   // a changed setting applies from the next navigation
window.OmniRedirectsDiagnostics=()=>({enabled,redirected:done,rules:rules(),flags:core.readFlags(flags()).length});
if(api.active)start()})();
