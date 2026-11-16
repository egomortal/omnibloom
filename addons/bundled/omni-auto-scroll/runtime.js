// Omni add-on "Auto-scroll": page glue. MIT, Omnibloom contributors.
// Alt+Shift+S starts / stops hands-free scrolling; Alt+Shift+Up / Down change the speed; any other key, a click or the
// end of the page stops it. The chosen speed is remembered.
(()=>{'use strict';const api=window.omniAddon;if(!api||!api.top)return;const core=OmniAutoScrollCore;
let enabled=false,running=false,frame=0,last=0,carry=0,idx=2,pill=null,pillTimer=0;
const node=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e};
function show(text){if(!pill){pill=node('div','omni-as-pill');pill.dataset.omniAddon=api.id;pill.setAttribute('role','status');document.body.append(pill)}
  pill.textContent=text;pill.hidden=false;clearTimeout(pillTimer);pillTimer=setTimeout(()=>{if(pill)pill.hidden=true},1500)}
const label=()=>'Auto-scroll '+core.SPEEDS[idx]+' px/s';
function tick(t){frame=0;if(!running)return;const se=document.scrollingElement||document.documentElement;
  const r=core.advance(carry,core.SPEEDS[idx],last?t-last:16,se.scrollTop,se.scrollHeight-se.clientHeight);last=t;carry=r.carry;
  if(r.move)se.scrollTop+=r.move;if(r.done){stopRun('End of the page');return}frame=requestAnimationFrame(tick)}
function startRun(){if(running)return;running=true;last=0;carry=0;show(label());frame=requestAnimationFrame(tick)}
function stopRun(why){if(!running)return;running=false;if(frame)cancelAnimationFrame(frame);frame=0;show(why||'Auto-scroll off')}
function save(){try{api.storage.set('speed',core.SPEEDS[idx])}catch(_){}}
function key(e){if(!enabled)return;const ours=e.altKey&&e.shiftKey&&!e.ctrlKey&&!e.metaKey;
  if(ours&&e.code==='KeyS'){e.preventDefault();e.stopPropagation();running?stopRun():startRun();return}
  if(ours&&(e.key==='ArrowUp'||e.key==='ArrowDown')){e.preventDefault();e.stopPropagation();idx=core.stepSpeed(idx,e.key==='ArrowUp'?1:-1);save();show(label());return}
  if(running&&!['Shift','Alt','Control','Meta'].includes(e.key))stopRun()}
function click(){if(running)stopRun()}
function start(){if(enabled)return;enabled=true;try{idx=core.speedIndex(api.storage.get('speed'))}catch(_){idx=2}
  document.addEventListener('keydown',key,true);document.addEventListener('mousedown',click,true)}
function stop(){enabled=false;stopRun();document.removeEventListener('keydown',key,true);document.removeEventListener('mousedown',click,true);if(pill)pill.remove();pill=null}
api.onEnable(start);api.onDisable(stop);if(api.active)start()})();
