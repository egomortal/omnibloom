// Omni add-on "Resume videos": page glue. MIT, Omnibloom contributors.
(()=>{'use strict';const api=window.omniAddon;if(!api)return;const core=OmniResumeCore,seen=new WeakMap();
let enabled=false,writable=true,box=null,boxTimer=null,boxVideo=null,prior=null;
const OPTS={capture:true,passive:true},MEDIA=['loadedmetadata','durationchange','play','playing','timeupdate','pause','ended'];
function info(v){let s=seen.get(v);if(!s){s={src:'',offered:false,pending:false,last:0};seen.set(v,s)}const src=v.currentSrc||v.src||'';if(src!==s.src){s.src=src;s.offered=false;s.last=0}return s}
// One key per page address and per long video on it (ads and previews are short, so they do not shift the index).
function keyFor(v){const url=core.normalize(location.href);if(!url)return null;const long=[...document.getElementsByTagName('video')].filter(x=>core.longEnough(x.duration));const i=long.indexOf(v);return core.key(url,i<0?0:i)}
function write(k,value){if(!writable)return Promise.resolve();return api.storage.set(k,value).catch(e=>{if(/private/.test(String(e&&e.message)))writable=false})}
function forget(k){if(!writable||api.storage.get(k)===undefined)return Promise.resolve();return api.storage.remove(k).catch(()=>{})}
async function prune(){const all={};for(const k of api.storage.keys())if(k.startsWith(core.PREFIX))all[k]=api.storage.get(k);for(const k of core.prune(all))await forget(k)}
function save(v){if(!enabled||!writable)return;const s=info(v);if(s.pending)return;const action=core.saveAction(v.currentTime,v.duration,v.ended);if(action==='skip')return;
const k=keyFor(v);if(!k)return;s.last=Date.now();if(action==='remove'){forget(k);return}
const value=core.entry(v.currentTime,v.duration,Date.now()),old=api.storage.get(k);if(Array.isArray(old)&&old[0]===value[0]&&old[1]===value[1])return;
const isNew=old===undefined;write(k,value).then(()=>{if(isNew)return prune()})}
function saveAll(){for(const v of document.getElementsByTagName('video'))save(v)}
function close(){clearInterval(boxTimer);boxTimer=null;if(boxVideo)info(boxVideo).pending=false;boxVideo=null;if(!box)return;const had=box.contains(document.activeElement);box.remove();box=null;
if(had&&prior&&prior.isConnected)try{prior.focus({preventScroll:true})}catch(_){}prior=null}
function offer(v){if(!enabled||box)return;const s=info(v);if(s.offered)return;const k=keyFor(v);if(!k)return;const target=core.decide(api.storage.get(k),v.duration,v.currentTime);if(target===null)return;
s.offered=true;s.pending=true;boxVideo=v;prior=document.activeElement;
const node=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text)e.textContent=text;return e};
box=node('div','omni-resume');box.dataset.omniAddon=api.id;box.setAttribute('role','dialog');box.setAttribute('aria-label','Resume video');
const q=node('p','omni-resume-q','Resume from '+core.clock(target)+'?'),yes=node('button','omni-resume-yes','Resume'),no=node('button','omni-resume-no','Start over'),left=node('span','omni-resume-left');
yes.type=no.type='button';left.setAttribute('aria-hidden','true');
yes.onclick=()=>{try{v.currentTime=target;if(v.paused)v.play().catch(()=>{})}catch(_){}close()};
no.onclick=()=>{forget(k);close()};
box.addEventListener('keydown',e=>{if(e.key==='Escape'||e.key==='GoBack'){e.preventDefault();e.stopPropagation();close();return}
if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)){e.preventDefault();e.stopPropagation();(document.activeElement===yes?no:yes).focus({preventScroll:true})}
else if(e.key==='Enter'||e.key===' ')e.stopPropagation()});
const row=node('div','omni-resume-row');row.append(yes,no,left);box.append(q,row);
const fs=document.fullscreenElement||document.webkitFullscreenElement;(fs&&fs.tagName!=='VIDEO'?fs:document.body||document.documentElement).append(box);
try{yes.focus({preventScroll:true})}catch(_){}
let n=8;left.textContent=n+' s';boxTimer=setInterval(()=>{if(--n<=0)close();else left.textContent=n+' s'},1000)}
function onMedia(e){const v=e.target;if(!(v instanceof HTMLVideoElement)||v.closest('[data-omni-addon]'))return;
switch(e.type){case'timeupdate':if(!v.paused&&Date.now()-info(v).last>=core.SAVE_EVERY)save(v);break;case'pause':case'ended':save(v);break;default:offer(v)}}
function onHide(){saveAll()}
function onVisibility(){if(document.visibilityState==='hidden')saveAll()}
function start(){if(enabled)return;enabled=true;for(const t of MEDIA)document.addEventListener(t,onMedia,OPTS);addEventListener('pagehide',onHide,OPTS);document.addEventListener('visibilitychange',onVisibility,OPTS);
for(const v of document.getElementsByTagName('video'))if(v.readyState>=1)offer(v)}
function stop(){if(!enabled)return;enabled=false;for(const t of MEDIA)document.removeEventListener(t,onMedia,OPTS);removeEventListener('pagehide',onHide,OPTS);document.removeEventListener('visibilitychange',onVisibility,OPTS);close()}
api.onEnable(start);api.onDisable(stop);window.OmniResumeDiagnostics=()=>({enabled,writable,saved:api.storage.keys().filter(k=>k.startsWith(core.PREFIX)).length,prompt:!!box});if(api.active)start()})();
