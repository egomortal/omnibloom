// Omni add-on "YouTube captions on": page glue. MIT, Omnibloom contributors.
// Turns YouTube's own captions (CC) on once per video when the video has them. If you switch them off, that video
// stays off. Uses the player's own button; nothing is fetched or sent.
(()=>{'use strict';const api=window.omniAddon;if(!api||!api.top)return;const core=OmniYtCaptionsCore;
let enabled=false,observer=null,timer=0;const handled=new Set();
function check(){timer=0;if(!enabled)return;const vid=core.videoId(location.href);if(!vid)return;
  const b=document.querySelector('.ytp-subtitles-button');if(!b)return;let display='';try{display=getComputedStyle(b).display}catch(_){}
  if(core.shouldPress({hidden:b.hidden,display,pressed:b.getAttribute('aria-pressed')},handled,vid)){handled.add(vid);b.click()}
  else if(b.getAttribute('aria-pressed')==='true')handled.add(vid)}
function later(){if(!timer)timer=setTimeout(check,700)}
function start(){if(enabled)return;enabled=true;window.addEventListener('yt-navigate-finish',later);observer=new MutationObserver(later);
  observer.observe(document.documentElement,{childList:true,subtree:true,attributes:true,attributeFilter:['aria-pressed','style']});later()}
function stop(){enabled=false;window.removeEventListener('yt-navigate-finish',later);if(observer)observer.disconnect();observer=null;clearTimeout(timer);timer=0}
api.onEnable(start);api.onDisable(stop);if(api.active)start()})();
