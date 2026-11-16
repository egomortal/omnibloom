// Omni add-on "YouTube chapters": page glue. MIT, Omnibloom contributors.
// A chapter list panel (D-pad + Cross to jump) and next / previous chapter keys on YouTube watch pages.
// Alt+Shift+C opens the list, Alt+Shift+Right / Left jump to the next / previous chapter. Read only; nothing is sent.
(()=>{'use strict';const api=window.omniAddon;if(!api||!api.top)return;const core=OmniYtChaptersCore;
let enabled=false,list=[],panel=null,prior=null,pill=null,pillTimer=0,timer=0,observer=null,lastUrl='';
const node=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e};
const video=()=>document.querySelector('video.html5-main-video')||document.querySelector('#movie_player video')||document.querySelector('video');
const watching=()=>/^\/(watch|live)\b/.test(location.pathname);
function read(){
  if(!watching())return[];
  const markers=[...document.querySelectorAll('ytd-macro-markers-list-item-renderer')].map(m=>({
    title:(m.querySelector('h4,#details h4,.macro-markers')||m).textContent,time:(m.querySelector('#time,.time')||{}).textContent}));
  const fromM=core.fromMarkers(markers);if(fromM.length)return fromM;
  const d=document.querySelector('#description-inline-expander,ytd-text-inline-expander,#description,ytm-expandable-video-description-body-renderer');
  return core.fromDescription(d?d.innerText||d.textContent:'')}
function refresh(){timer=0;if(!enabled)return;list=read();if(panel)draw()}
function later(){if(!timer)timer=setTimeout(refresh,800)}
function seek(t){const v=video();if(!v||t==null)return false;try{v.currentTime=t;show(core.clock(t)+'  '+(list[core.index(list,t)]||{}).title)}catch(_){return false}return true}
function show(text){if(!pill){pill=node('div','omni-ytc-pill');pill.dataset.omniAddon=api.id;pill.setAttribute('role','status');document.body.append(pill)}
  pill.textContent=text;pill.hidden=false;clearTimeout(pillTimer);pillTimer=setTimeout(()=>{if(pill)pill.hidden=true},1800)}
function draw(){panel.querySelector('.omni-ytc-list').replaceChildren(...(list.length?list.map((c,i)=>{const b=node('button','omni-ytc-item');b.type='button';
    b.append(node('span','omni-ytc-time',core.clock(c.t)),node('span','omni-ytc-title',c.title));b.onclick=()=>{seek(c.t);close()};b.dataset.i=String(i);return b}):
    [node('p','omni-ytc-empty','This video has no chapters.')]));
  const v=video(),cur=v?core.index(list,v.currentTime):-1;const items=panel.querySelectorAll('.omni-ytc-item');
  (items[Math.max(0,cur)]||panel.querySelector('button'))?.focus({preventScroll:false})}
function open(){if(panel)return close();list=read();prior=document.activeElement;panel=node('aside','omni-ytc-panel omni-addon-panel');panel.dataset.omniAddon=api.id;
  panel.setAttribute('aria-label','Chapters');const h=node('h2',null,'Chapters');const x=node('button','omni-ytc-close','Close');x.type='button';x.onclick=close;
  panel.append(h,node('div','omni-ytc-list'),x);document.body.append(panel);
  panel.addEventListener('keydown',e=>{const items=[...panel.querySelectorAll('button')];const i=items.indexOf(document.activeElement);
    if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();e.stopPropagation();items[Math.max(0,Math.min(items.length-1,i+(e.key==='ArrowDown'?1:-1)))]?.focus()}
    else if(e.key==='Escape'){e.preventDefault();e.stopPropagation();close()}},true);draw()}
function close(){if(!panel)return;panel.remove();panel=null;try{prior&&prior.isConnected&&prior.focus({preventScroll:true})}catch(_){}prior=null}
function key(e){if(!enabled||!e.altKey||!e.shiftKey||e.ctrlKey||e.metaKey)return;const v=video();
  if(e.code==='KeyC'){e.preventDefault();e.stopPropagation();open();return}
  if(!v||!list.length)return;
  if(e.key==='ArrowRight'){e.preventDefault();e.stopPropagation();const t=core.next(list,v.currentTime);t==null?show('Last chapter'):seek(t)}
  else if(e.key==='ArrowLeft'){e.preventDefault();e.stopPropagation();seek(core.prev(list,v.currentTime))}}
function nav(){if(location.href===lastUrl)return;lastUrl=location.href;close();later()}
function start(){if(enabled)return;enabled=true;lastUrl=location.href;document.addEventListener('keydown',key,true);
  window.addEventListener('yt-navigate-finish',nav);observer=new MutationObserver(()=>{if(location.href!==lastUrl)nav();else if(!list.length)later()});
  observer.observe(document.body,{childList:true,subtree:true});later()}
function stop(){enabled=false;document.removeEventListener('keydown',key,true);window.removeEventListener('yt-navigate-finish',nav);observer?.disconnect();observer=null;
  clearTimeout(timer);timer=0;close();pill?.remove();pill=null;list=[]}
api.onEnable(start);api.onDisable(stop);if(api.active)start();
window.OmniYtChaptersDiagnostics=()=>({enabled,chapters:list.length})})();
