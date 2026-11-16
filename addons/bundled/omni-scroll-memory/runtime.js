// Omni add-on "Remember reading position": page glue. MIT, Omnibloom contributors.
// Long pages come back where you left them: the position (a fraction of the page) is kept for 30 days under a hash of
// the page address. On return a small bar offers "Continue reading" (Cross) - it never jumps by itself.
(()=>{'use strict';const api=window.omniAddon;if(!api||!api.top)return;const core=OmniScrollMemCore;
let enabled=false,key=null,timer=0,bar=null,saved=null;
const se=()=>document.scrollingElement||document.documentElement;
function load(){try{const m=api.storage.get('pos');return m&&typeof m==='object'?m:{}}catch(_){return{}}}
function save(){timer=0;if(!enabled||!key)return;const s=se(),maxY=s.scrollHeight-s.clientHeight,m=load();
  if(core.worth(s.scrollTop,maxY,window.innerHeight))m[key]={f:core.fraction(s.scrollTop,maxY),t:Date.now()};else delete m[key];
  try{api.storage.set('pos',core.trim(m))}catch(_){}}
function onScroll(){if(bar&&se().scrollTop>window.innerHeight)hideBar();if(!timer)timer=setTimeout(save,1500)}
function hideBar(){if(bar)bar.remove();bar=null}
function offer(){const e=load()[key];if(!core.fresh(e,Date.now())||se().scrollTop>window.innerHeight*0.5)return;saved=e;
  bar=document.createElement('div');bar.className='omni-sm-bar';bar.dataset.omniAddon=api.id;bar.setAttribute('role','status');
  const go=document.createElement('button');go.type='button';go.textContent='Continue reading ('+Math.round(e.f*100)+'%)';
  const no=document.createElement('button');no.type='button';no.textContent='Start at the top';
  go.onclick=()=>{const s=se();s.scrollTop=core.restoreY(saved.f,s.scrollHeight-s.clientHeight);hideBar()};no.onclick=hideBar;
  bar.append(go,no);document.body.append(bar);setTimeout(hideBar,12000)}
function start(){if(enabled)return;enabled=true;key=core.keyFor(location.href);if(!key)return;
  window.addEventListener('scroll',onScroll,{passive:true});window.addEventListener('pagehide',save);setTimeout(offer,1200)}
function stop(){enabled=false;window.removeEventListener('scroll',onScroll);window.removeEventListener('pagehide',save);clearTimeout(timer);timer=0;hideBar()}
api.onEnable(start);api.onDisable(stop);if(api.active)start()})();
