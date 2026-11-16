// Omni add-on "Video fit": page glue. MIT, Omnibloom contributors.
// Puts data-omni-fit (+ two CSS variables for zoom) on page videos; addon.css does the rest (object-fit, transform).
// No polling: media events, window resize / fullscreen changes and a MutationObserver for added videos (debounced).
(()=>{'use strict';const api=window.omniAddon;if(!api||!api.top)return;const core=OmniVideoFitCore;
let enabled=false,writable=true,privateTab=false,session=null,remember=false,observer=null,timer=0,panel=null,prior=null,pill=null,pillTimer=0,limited=false;
const applied=new Set(),hinted=new WeakSet(),OPTS={capture:true,passive:true},ATTR='data-omni-fit';
const node=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text)e.textContent=text;return e};
const fsEl=()=>document.fullscreenElement||document.webkitFullscreenElement||null;
const ours=e=>!!(e&&e.closest&&e.closest('[data-omni-addon]'));
const siteKey=()=>core.siteKey(location.hostname);
function stored(){const k=siteKey();return k?core.saved(api.storage.get(k)):null}
const mode=()=>core.resolve(session,stored(),api.settings.get('mode'));
// ---- applying ----
function clear(v){applied.delete(v);if(!v.hasAttribute(ATTR))return;v.removeAttribute(ATTR);v.style.removeProperty('--omni-fit-zoom');v.style.removeProperty('--omni-fit-base')}
function apply(v,m){if(ours(v))return;const fs=fsEl(),w=v.clientWidth,h=v.clientHeight;
  if(m==='fit'||!core.worthIt(w,h,fs&&(fs===v||fs.contains(v)))){clear(v);return}
  const p=core.plan(m,{w,h},{w:v.videoWidth,h:v.videoHeight},{scale:window.devicePixelRatio||1,keepHw:api.settings.get('keep_hw')!==false});
  const was=v.getAttribute(ATTR)||'',want=p.fit+(p.zoom!==1?' zoom':'');
  if(p.zoom!==1){
    // The page's own transform (if any) stays in front of the zoom; read once, before ours is on.
    if(!/\bzoom\b/.test(was)){let t='none';try{t=getComputedStyle(v).transform}catch(_){}v.style.setProperty('--omni-fit-base',t&&t!=='none'?t:'translate(0)')}
    v.style.setProperty('--omni-fit-zoom',String(p.zoom))}
  else{v.style.removeProperty('--omni-fit-zoom');v.style.removeProperty('--omni-fit-base')}
  if(was!==want)v.setAttribute(ATTR,want);applied.add(v);if(p.limited)limited=true}
function applyAll(){if(!enabled)return;const m=mode();limited=false;for(const v of[...applied])if(!v.isConnected)applied.delete(v);
  for(const v of document.getElementsByTagName('video'))apply(v,m);refreshPanel()}
function later(){if(!timer)timer=setTimeout(()=>{timer=0;applyAll()},250)}
function onMutations(records){for(const r of records)for(const n of r.addedNodes){if(n.nodeType!==1||ours(n))continue;
  if(n.tagName==='VIDEO'||n.getElementsByTagName('video').length){later();return}}}
function onMedia(e){const v=e.target;if(!v||v.tagName!=='VIDEO'||ours(v))return;if(e.type==='playing'){maybeHint(v);return}apply(v,mode());refreshPanel()}
// ---- remembering: one storage key per site. Omni refuses add-on storage writes from private tabs; there the
// choice (and the remember switch) last for this page only. ----
function failed(e){writable=false;privateTab=/private/i.test(String(e&&e.message||e));refreshPanel()}
async function pruneSites(){const all={};for(const k of api.storage.keys())if(k.startsWith(core.SITE_PREFIX))all[k]=api.storage.get(k);
  for(const k of core.prune(all))await api.storage.remove(k).catch(()=>{})}
function save(m){const k=siteKey();if(!k||!writable)return Promise.resolve();const old=api.storage.get(k);if(core.saved(old)===m)return Promise.resolve();
  return api.storage.set(k,core.entry(m,Date.now())).then(()=>{if(old===undefined)return pruneSites()},failed)}
function forget(){const k=siteKey();if(!k||!writable||api.storage.get(k)===undefined)return Promise.resolve();return api.storage.remove(k).catch(failed)}
function choose(m){if(!core.valid(m))return;session=m;if(remember)save(m);applyAll()}
function toggleRemember(){remember=!remember;if(remember)save(mode());else{session=mode();forget()}refreshPanel()}
// ---- the panel (pointer: left stick + Cross; keyboard: arrows, Enter, Escape) ----
function refreshPanel(){if(!panel)return;const m=mode();for(const b of panel.querySelectorAll('[data-mode]'))b.setAttribute('aria-pressed',String(b.dataset.mode===m));
  const r=panel.querySelector('.omni-fit-remember');r.setAttribute('aria-pressed',String(remember));r.textContent='Remember for this site: '+(remember?'On':'Off');
  const notes=[];if(limited)notes.push('Zoom held back so the video stays on the hardware video plane.');
  if(!writable)notes.push(privateTab?'Private tab: kept for this page only.':'Could not save: kept for this page only.');
  panel.querySelector('.omni-fit-note').textContent=notes.join(' ')}
function host(){const fs=fsEl();return fs&&fs.tagName!=='VIDEO'?fs:document.body||document.documentElement}
function openPanel(){hidePill();if(panel||!enabled)return;const fs=fsEl();
  if(fs&&fs.tagName==='VIDEO'){cycle();return}   // nothing can be drawn over a video that is itself full screen
  prior=document.activeElement;panel=node('aside','omni-fit-panel');panel.dataset.omniAddon=api.id;panel.setAttribute('role','dialog');panel.setAttribute('aria-label','Video fit');
  panel.append(node('p','omni-fit-title','Video fit'));const row=node('div','omni-fit-modes');row.setAttribute('role','group');row.setAttribute('aria-label','Picture');
  for(const m of core.MODES){const b=node('button','omni-fit-btn',core.LABELS[m]);b.type='button';b.dataset.mode=m;b.onclick=()=>choose(m);row.append(b)}
  const rem=node('button','omni-fit-btn omni-fit-remember');rem.type='button';rem.onclick=toggleRemember;
  const done=node('button','omni-fit-btn omni-fit-done','Done');done.type='button';done.onclick=()=>closePanel();
  const foot=node('div','omni-fit-row');foot.append(rem,done);const note=node('p','omni-fit-note');note.setAttribute('role','status');
  panel.append(row,foot,note);panel.addEventListener('keydown',onPanelKey);host().append(panel);refreshPanel();
  const on=panel.querySelector('[aria-pressed="true"]')||panel.querySelector('button');try{on.focus({preventScroll:true})}catch(_){}}
function closePanel(){if(!panel)return;const had=panel.contains(document.activeElement);panel.remove();panel=null;
  if(had&&prior&&prior.isConnected)try{prior.focus({preventScroll:true})}catch(_){}prior=null}
function onPanelKey(e){if(e.key==='Escape'||e.key==='GoBack'||e.key==='Backspace'){e.preventDefault();e.stopPropagation();closePanel();return}
  if(/^Arrow(Left|Right|Up|Down)$/.test(e.key)){e.preventDefault();e.stopPropagation();const all=[...panel.querySelectorAll('button')],i=all.indexOf(document.activeElement);
    const d=e.key==='ArrowLeft'||e.key==='ArrowUp'?-1:1;all[Math.max(0,Math.min(all.length-1,(i<0?0:i)+d))].focus({preventScroll:true});return}
  if(e.key==='Enter'||e.key===' ')e.stopPropagation()}   // the player's own Space/Enter (play/pause) stays out of it
function cycle(){choose(core.next(mode(),1));api.toast('Video fit: '+core.LABELS[mode()]).catch(()=>{})}
// A small button for a few seconds when a big video starts (once per video), so a controller can reach the panel.
function hidePill(){clearTimeout(pillTimer);pillTimer=0;if(pill){pill.remove();pill=null}}
function maybeHint(v){if(panel||pill||hinted.has(v)||api.settings.get('button')===false)return;const fs=fsEl();
  if(!core.worthIt(v.clientWidth,v.clientHeight,fs&&fs.contains(v))||(fs&&fs.tagName==='VIDEO'))return;hinted.add(v);
  pill=node('button','omni-fit-pill','Video fit: '+core.LABELS[mode()]);pill.type='button';pill.dataset.omniAddon=api.id;pill.title='Video fit (Alt+Shift+F)';pill.onclick=openPanel;
  host().append(pill);pillTimer=setTimeout(hidePill,5000)}
function onKey(e){if(!enabled||!e.isTrusted||!e.altKey||!e.shiftKey||e.code!=='KeyF'||e.repeat)return;e.preventDefault();e.stopImmediatePropagation();panel?closePanel():openPanel()}
// ---- life cycle ----
const MEDIA=['loadedmetadata','resize','playing'];
function start(live){if(enabled)return;enabled=true;remember=stored()!==null;
  for(const t of MEDIA)document.addEventListener(t,onMedia,OPTS);addEventListener('resize',later,OPTS);
  document.addEventListener('fullscreenchange',later,OPTS);document.addEventListener('webkitfullscreenchange',later,OPTS);addEventListener('keydown',onKey,true);
  observer=new MutationObserver(onMutations);observer.observe(document.documentElement,{childList:true,subtree:true});applyAll();
  if(live&&document.visibilityState!=='hidden'&&[...document.getElementsByTagName('video')].some(v=>applied.has(v)||core.worthIt(v.clientWidth,v.clientHeight,false)))openPanel()}
function stop(){if(!enabled)return;enabled=false;clearTimeout(timer);timer=0;if(observer){observer.disconnect();observer=null}
  for(const t of MEDIA)document.removeEventListener(t,onMedia,OPTS);removeEventListener('resize',later,OPTS);
  document.removeEventListener('fullscreenchange',later,OPTS);document.removeEventListener('webkitfullscreenchange',later,OPTS);removeEventListener('keydown',onKey,true);
  closePanel();hidePill();for(const v of[...applied])clear(v);for(const v of document.querySelectorAll('video['+ATTR+']'))clear(v)}
// Switched on from the quick switch while this page is open: the switch itself is the request to pick a fit.
function injectedLate(){try{const nav=performance.getEntriesByType('navigation')[0];return document.readyState==='complete'&&nav&&nav.loadEventEnd>0&&performance.now()-nav.loadEventEnd>1500}catch(_){return false}}
api.onEnable(()=>start(true));api.onDisable(stop);api.onSettings(()=>{if(enabled)applyAll()});
window.OmniVideoFitDiagnostics=()=>({enabled,mode:enabled?mode():null,remember,writable,privateTab,videos:applied.size,limited,panel:!!panel});
if(api.active)start(injectedLate())})();
