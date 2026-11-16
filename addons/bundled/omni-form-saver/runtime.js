// Omni add-on "Form saver": page glue. MIT, Omnibloom contributors.
// Keeps typed text in the page's own localStorage (debounced, flushed on pagehide), offers it back in a small bar
// when the same field is empty on the next visit, and clears the page's entry when its form is submitted.
// Never fills anything by itself. Not injected in private tabs (manifest private_safe:false); a page that cannot
// use localStorage (blocked, sandboxed, quota) simply gets nothing.
(()=>{'use strict';const api=window.omniAddon;if(!api||!api.top||api.private===true||api.incognito===true)return;const core=OmniFormSaverCore;
let enabled=false,store=null,pending=new Map(),timer=0,bar=null,prior=null,offered=false,observer=null,watchTimer=0,watchUntil=0;
const OPTS={capture:true,passive:true},now=()=>Date.now();
const node=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text)e.textContent=text;return e};
function ls(){if(store)return store;try{const s=window.localStorage;if(!s)return null;const probe=core.PREFIX+'probe';s.setItem(probe,'1');s.removeItem(probe);store=s}catch(_){store=null}return store}
const key=()=>core.storageKey(location);
function read(){const s=ls();if(!s)return{f:{}};let raw=null;try{raw=s.getItem(key())}catch(_){}return raw==null?{f:{}}:core.parse(raw,now())}
function write(page){const s=ls();if(!s)return;const v=core.serialize(page);try{if(v===null)s.removeItem(key());else s.setItem(key(),v)}catch(_){}}
// Other pages' entries on this site older than 24 h go away (only our prefix is touched).
function sweep(){const s=ls();if(!s)return;const t=now(),drop=[];try{for(let i=0;i<s.length;i++){const k=s.key(i);if(k&&k.startsWith(core.PREFIX)&&core.stale(s.getItem(k),t))drop.push(k)}}catch(_){return}
  for(const k of drop)try{s.removeItem(k)}catch(_){}}
const body=()=>document.body||document.documentElement;
function field(t){return t&&t.nodeType===1&&(t.tagName==='TEXTAREA'||t.tagName==='INPUT')&&core.eligible(core.describe(t))?t:null}
// ---- saving ----
function flush(){clearTimeout(timer);timer=0;if(!pending.size)return;const page=read(),t=now();
  for(const[el,k]of pending)if(el.isConnected!==false)core.put(page,k,String(el.value||''),t);pending.clear();write(page)}
function onInput(e){if(!enabled||!e.isTrusted)return;const el=field(e.target);if(!el)return;pending.set(el,core.fieldKey(el,body()));
  clearTimeout(timer);timer=setTimeout(flush,core.DEBOUNCE_MS)}
function onSubmit(e){if(!enabled)return;pending.clear();clearTimeout(timer);timer=0;const s=ls();if(s)try{s.removeItem(key())}catch(_){}hideBar()}
function onHide(){if(enabled)flush()}
// ---- offering ----
function offer(){if(!enabled||bar||offered)return false;const list=core.restorable(read(),body());if(!list.length)return false;offered=true;stopWatch();
  prior=document.activeElement;bar=node('aside','omni-fs-bar');bar.dataset.omniAddon=api.id;bar.setAttribute('role','dialog');bar.setAttribute('aria-label','Form saver');
  const msg=node('p','omni-fs-text','Restore what you typed?');const n=list.length;
  const sub=node('span','omni-fs-sub',n===1?' (1 box)':' ('+n+' boxes)');msg.append(sub);
  const yes=node('button','omni-fs-btn omni-fs-restore','Restore');yes.type='button';yes.onclick=()=>restore(list);
  const no=node('button','omni-fs-btn omni-fs-dismiss','Dismiss');no.type='button';no.onclick=dismiss;
  const row=node('div','omni-fs-row');row.append(yes,no);bar.append(msg,row);bar.addEventListener('keydown',onBarKey);body().append(bar);
  try{yes.focus({preventScroll:true})}catch(_){}return true}
function restore(list){let first=null;for(const{el,text}of list){if(el.isConnected===false)continue;if(String(el.value||'')!=='')continue;
    el.value=text;for(const t of['input','change'])try{el.dispatchEvent(new Event(t,{bubbles:true}))}catch(_){}if(!first)first=el}
  prior=first||prior;hideBar()}
// Dismiss means "I don't want it": the saved text for this page is deleted.
function dismiss(){const page=read();for(const k of Object.keys(page.f))delete page.f[k];write(page);hideBar()}
function hideBar(){if(!bar)return;const had=bar.contains(document.activeElement);bar.remove();bar=null;
  if(had&&prior&&prior.isConnected!==false)try{prior.focus({preventScroll:true})}catch(_){}prior=null}
function onBarKey(e){if(e.key==='Escape'||e.key==='GoBack'||e.key==='Backspace'){e.preventDefault();e.stopPropagation();hideBar();return}
  if(/^Arrow(Left|Right|Up|Down)$/.test(e.key)){e.preventDefault();e.stopPropagation();const all=[...bar.querySelectorAll('button')],i=all.indexOf(document.activeElement);
    const d=e.key==='ArrowLeft'||e.key==='ArrowUp'?-1:1;all[Math.max(0,Math.min(all.length-1,(i<0?0:i)+d))].focus({preventScroll:true});return}
  if(e.key==='Enter'||e.key===' ')e.stopPropagation()}
// Forms drawn by script after load: look again on DOM changes (debounced) for up to 15 s, then stop.
function stopWatch(){clearTimeout(watchTimer);watchTimer=0;if(observer){observer.disconnect();observer=null}}
function watch(){if(observer||offered||!Object.keys(read().f).length||typeof MutationObserver!=='function')return;watchUntil=now()+15000;
  observer=new MutationObserver(()=>{if(now()>watchUntil){stopWatch();return}if(!watchTimer)watchTimer=setTimeout(()=>{watchTimer=0;offer()},400)});
  observer.observe(document.documentElement,{childList:true,subtree:true})}
// ---- life cycle ----
function start(){if(enabled)return;if(!ls())return;enabled=true;sweep();
  document.addEventListener('input',onInput,OPTS);document.addEventListener('submit',onSubmit,true);addEventListener('pagehide',onHide,OPTS);
  addEventListener('pageshow',onShow,OPTS);if(!offer())watch()}
// Back/forward cache: the page comes back as it was; offer again only if the boxes are empty.
function onShow(e){if(enabled&&e&&e.persisted){offered=false;offer()}}
function stop(){if(!enabled)return;flush();enabled=false;stopWatch();
  document.removeEventListener('input',onInput,OPTS);document.removeEventListener('submit',onSubmit,true);removeEventListener('pagehide',onHide,OPTS);removeEventListener('pageshow',onShow,OPTS);hideBar()}
api.onEnable(start);api.onDisable(stop);
window.OmniFormSaverDiagnostics=()=>({enabled,storage:!!store,pending:pending.size,bar:!!bar,saved:enabled?Object.keys(read().f).length:0});
if(api.active)start()})();
