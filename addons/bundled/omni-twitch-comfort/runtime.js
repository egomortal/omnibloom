// Omni add-on "Twitch comfort": page glue. MIT, Omnibloom contributors.
// Theatre mode on channel pages (once per visit), Alt+Shift+H hides / shows chat, optional bonus-points claim.
(()=>{'use strict';const api=window.omniAddon;if(!api||!api.top)return;const core=OmniTwitchCore;
let enabled=false,observer=null,timer=0,lastPath='',theatreDone=false,claims=[];
const lbl=b=>b?(b.getAttribute('aria-label')||b.textContent||''):'';
function tick(){timer=0;if(!enabled)return;
  if(location.pathname!==lastPath){lastPath=location.pathname;theatreDone=false}
  if(api.settings.get('theatre')!==false&&!theatreDone&&core.isChannel(location.pathname)){const b=document.querySelector(core.SEL.theatre);
    if(b){theatreDone=true;if(core.wantTheatre(lbl(b),false))b.click()}}
  if(api.settings.get('claim')===true){const area=document.querySelector(core.SEL.claimArea);
    if(area)for(const b of area.querySelectorAll('button'))if(core.isClaim(lbl(b))){const r=core.limiter(Date.now(),claims);claims=r.log;
      if(r.ok){b.click();if(api.toast)api.toast('Bonus points claimed')}break}}}
function later(){if(!timer)timer=setTimeout(tick,500)}
function key(e){if(!enabled||!e.altKey||!e.shiftKey||e.ctrlKey||e.metaKey||e.code!=='KeyH')return;const b=document.querySelector(core.SEL.chatToggle);
  if(b){e.preventDefault();e.stopPropagation();b.click()}}
function start(){if(enabled)return;enabled=true;document.addEventListener('keydown',key,true);observer=new MutationObserver(later);
  observer.observe(document.body,{childList:true,subtree:true});later()}
function stop(){enabled=false;document.removeEventListener('keydown',key,true);if(observer)observer.disconnect();observer=null;clearTimeout(timer);timer=0}
api.onEnable(start);api.onDisable(stop);if(api.active)start()})();
