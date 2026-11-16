// Omni add-on "Reading ruler": page glue. MIT, Omnibloom contributors.
// A clear band across the middle of the screen with the rest gently dimmed, sized to the text there; scroll the page
// through it. Alt+Shift+R shows / hides it. Pointer events pass through (it never blocks a click).
(()=>{'use strict';const api=window.omniAddon;if(!api||!api.top)return;const core=OmniRulerCore;
let enabled=false,shown=false,top=null,bottom=null,frame=0;
const node=cls=>{const e=document.createElement('div');e.className=cls;e.dataset.omniAddon=api.id;e.setAttribute('aria-hidden','true');return e};
function textAtMiddle(){const x=window.innerWidth/2,y=window.innerHeight/2;let el=document.elementFromPoint?document.elementFromPoint(x,y):null;
  if(!el||el.closest('[data-omni-addon]'))el=document.body;let cs;try{cs=getComputedStyle(el)}catch(_){return{size:16,lh:0}}
  return{size:parseFloat(cs.fontSize),lh:parseFloat(cs.lineHeight)}}
function layout(){frame=0;if(!shown)return;const t=textAtMiddle();const band=core.bandPx(t.size,t.lh,api.settings.get('height')||'medium');
  const y=core.bandTop(window.innerHeight,band);top.style.height=y+'px';bottom.style.top=(y+band)+'px'}
function later(){if(!frame)frame=requestAnimationFrame(layout)}
function show(on){shown=on;if(on){if(!top){top=node('omni-ruler-shade omni-ruler-top');bottom=node('omni-ruler-shade omni-ruler-bottom');document.body.append(top,bottom)}layout()}
  else{if(top)top.remove();if(bottom)bottom.remove();top=bottom=null}}
function key(e){if(enabled&&e.altKey&&e.shiftKey&&!e.ctrlKey&&!e.metaKey&&e.code==='KeyR'){e.preventDefault();e.stopPropagation();show(!shown)}}
function start(){if(enabled)return;enabled=true;document.addEventListener('keydown',key,true);window.addEventListener('scroll',later,{passive:true});window.addEventListener('resize',later);
  show(api.settings.get('start_on')===true)}
function stop(){enabled=false;document.removeEventListener('keydown',key,true);window.removeEventListener('scroll',later);window.removeEventListener('resize',later);show(false)}
api.onEnable(start);api.onDisable(stop);api.onSettings(()=>{if(shown)layout()});if(api.active)start()})();
