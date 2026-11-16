// Omni add-on "Break reminder": page glue. MIT, Omnibloom contributors.
// Counts minutes you are actually watching or reading (this tab visible, a video playing or input in the last 2 min) and,
// every 30 / 60 / 90 / 120 of them, shows a small card: "You've been on screen for 1 hour. Time for a break?"
// OK / Snooze 15 min. It never pauses or closes anything. The count is shared by all tabs, per calendar day.
(()=>{'use strict';const api=window.omniAddon;if(!api||!api.top)return;const core=OmniBreakCore;
let enabled=false,timer=0,lastInput=Date.now(),card=null;
const playing=()=>[...document.querySelectorAll('video,audio')].some(m=>!m.paused&&!m.ended&&m.readyState>2);
function input(){lastInput=Date.now()}
function load(){try{return api.storage.get('count')}catch(_){return null}}
function save(s){try{api.storage.set('count',s)}catch(_){}}
function minute(){const now=Date.now();let s=core.tick(load(),now,core.active(document.visibilityState==='visible',playing(),lastInput,now));save(s);
  if(!card&&document.visibilityState==='visible'&&core.due(s,api.settings.get('every')||'60',now)){save(core.shown(s));show(s.mins)}}
function show(mins){card=document.createElement('div');card.className='omni-br-card';card.dataset.omniAddon=api.id;card.setAttribute('role','alertdialog');
  card.setAttribute('aria-label','Break reminder');const p=document.createElement('p');p.textContent="You've been on screen for "+core.text(mins)+' today. Time for a break?';
  const ok=document.createElement('button');ok.type='button';ok.textContent='OK';ok.onclick=close;
  const sn=document.createElement('button');sn.type='button';sn.textContent='Snooze 15 min';sn.onclick=()=>{save(core.snooze(load(),Date.now(),15));close()};
  card.append(p,ok,sn);document.body.append(card);ok.focus({preventScroll:true})}
function close(){if(card)card.remove();card=null}
function start(){if(enabled)return;enabled=true;for(const t of['keydown','mousedown','wheel','touchstart'])document.addEventListener(t,input,{capture:true,passive:true});
  timer=setInterval(minute,60e3)}
function stop(){enabled=false;clearInterval(timer);timer=0;for(const t of['keydown','mousedown','wheel','touchstart'])document.removeEventListener(t,input,{capture:true});close()}
api.onEnable(start);api.onDisable(stop);if(api.active)start()})();
