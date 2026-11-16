// Omni add-on "Recipe mode": page glue. MIT, Omnibloom contributors.
// On a page that declares a schema.org Recipe (see core.js) a "Recipe mode" button opens a full-screen, big-text view:
// ingredients to tick off, one step at a time, a servings scaler and step timers. Nothing is fetched.
(()=>{'use strict';const api=window.omniAddon;if(!api||!api.top)return;const core=OmniRecipeCore;
let enabled=false,recipe=null,fab=null,view=null,idle=0,retry=0,saved=null,pushed=false,fsOn=false,wake=null;
let step=0,scale=1,checked=new Set(),cursor=-1,writable=true,stateKey=null,timerTick=0,alertBox=null;
const timers=new Map();   // 'step:index' -> {step,index,seconds,left,endAt,running,done,label}
const memory=new Map();   // private tabs: add-on storage refuses writes, so ticks last only while this page is open
const node=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text!=null&&text!=='')e.textContent=text;return e};
const html=()=>document.documentElement;
const button=(cls,text,label,fn)=>{const b=node('button','omni-recipe-btn '+cls,text);b.type='button';if(label)b.setAttribute('aria-label',label);b.onclick=fn;return b};

// ---- Detection: only the page's own Recipe markup (JSON-LD or microdata) ----
function analyse(){idle=0;if(!enabled)return;try{recipe=core.find(document)}catch(_){recipe=null}
  // Some sites add their JSON-LD after load; one more look a few seconds later, then never again.
  if(!recipe&&!retry)retry=setTimeout(()=>{retry=-1;if(enabled&&!recipe)later()},4000);showFab()}
function later(){if(idle||!enabled)return;idle=window.requestIdleCallback?requestIdleCallback(analyse,{timeout:3000}):setTimeout(analyse,600)}
function showFab(){const want=enabled&&!view&&recipe&&api.settings.get('button')!==false;if(!want){if(fab){fab.remove();fab=null}return}if(fab)return;
  fab=node('button','omni-recipe-fab','Recipe mode');fab.type='button';fab.dataset.omniAddon=api.id;fab.title='Cook from this recipe in large text (Alt+Shift+K)';fab.onclick=()=>open();(document.body||html()).append(fab)}

// ---- Per-page state: add-on storage, or memory in private tabs ----
function load(){stateKey=core.key(location.href);const raw=stateKey?(memory.has(stateKey)?memory.get(stateKey):api.storage.get(stateKey)):undefined;
  const r=core.restore(raw,recipe.ingredients.length,recipe.steps.length);checked=r.checked;scale=r.scale;step=r.step}
function save(){if(!stateKey||!recipe)return;const value=core.entry({checked,n:recipe.ingredients.length,scale,step},Date.now());
  if(!writable){memory.set(stateKey,value);return}const isNew=api.storage.get(stateKey)===undefined;
  api.storage.set(stateKey,value).then(()=>{if(isNew)return prune()}).catch(e=>{if(/private/i.test(String(e&&e.message)))writable=false;memory.set(stateKey,value)})}
async function prune(){const all={};for(const k of api.storage.keys())if(k.startsWith(core.PREFIX))all[k]=api.storage.get(k);for(const k of core.prune(all))await api.storage.remove(k).catch(()=>{})}

// ---- The view ----
let ingList=null,countEl=null,posEl=null,textEl=null,timerRow=null,tray=null,prevBtn=null,nextBtn=null,scaleBtns=[],yieldEl=null,hintEl=null;
function meta(){const r=recipe,bits=[];if(r.prep)bits.push('Prep '+core.human(r.prep));if(r.cook)bits.push('Cook '+core.human(r.cook));if(r.total&&!(r.prep&&r.cook))bits.push('Total '+core.human(r.total));return bits.join(' · ')}
function yieldText(){const y=recipe.yield;if(!y)return scale===1?'':'Amounts '+core.scaleLabel(scale);
  if(scale===1||!y.count)return y.text+(scale===1?'':' · amounts '+core.scaleLabel(scale));return y.text+' → '+core.formatNumber(y.count*scale)}
function renderIngredients(){ingList.textContent='';recipe.ingredients.forEach((t,i)=>{const li=node('li','omni-recipe-li');
  const b=button('omni-recipe-ing',core.scaleIngredient(t,scale),'',()=>toggle(i));b.setAttribute('role','checkbox');b.setAttribute('aria-checked',String(checked.has(i)));b.dataset.i=String(i);
  if(i===cursor)b.classList.add('omni-recipe-cursor');li.append(b);ingList.append(li)});
  countEl.textContent=recipe.ingredients.length?checked.size+' of '+recipe.ingredients.length+' ready':'';
  for(const b of scaleBtns)b.setAttribute('aria-pressed',String(Number(b.dataset.scale)===scale));yieldEl.textContent=yieldText()}
function renderStep(){const n=recipe.steps.length;if(!n){posEl.textContent='No steps on this page';textEl.textContent='';timerRow.textContent='';prevBtn.disabled=nextBtn.disabled=true;return}
  const s=recipe.steps[step];posEl.textContent='Step '+(step+1)+' of '+n+(s.section?' · '+s.section:'')+(s.tip?' · Tip':'');
  textEl.textContent=s.text;timerRow.textContent='';s.timers.forEach((t,i)=>{const b=button('omni-recipe-timer','','',()=>timerPress(step,i));b.dataset.timer=step+':'+i;timerRow.append(b);paintTimer(b)});
  prevBtn.disabled=step<=0;nextBtn.disabled=step>=n-1;paintTray()}
function paintTimer(b){const[si,ti]=b.dataset.timer.split(':').map(Number),t=recipe.steps[si].timers[ti],live=timers.get(b.dataset.timer);
  if(!live){b.textContent='Start '+core.human(t.seconds)+' timer';b.setAttribute('aria-label','Start a '+core.human(t.seconds)+' timer ('+t.label+')');b.className='omni-recipe-btn omni-recipe-timer';return}
  b.textContent=live.done?'Done: '+t.label:core.clock(live.left)+(live.running?' ❚❚':' ▶');b.setAttribute('aria-label',live.done?'Timer finished, press to clear':live.running?'Pause timer':'Resume timer');
  b.className='omni-recipe-btn omni-recipe-timer'+(live.running?' omni-recipe-running':'')+(live.done?' omni-recipe-done':'')}
// Timers of other steps stay visible in a small tray, so leaving a step does not hide its countdown.
function paintTray(){if(!tray)return;tray.textContent='';for(const[k,t]of timers){if(t.step===step)continue;const b=button('omni-recipe-chip','Step '+(t.step+1)+': '+(t.done?'done':core.clock(t.left)),'Go to step '+(t.step+1),()=>go(t.step));
  if(t.done)b.classList.add('omni-recipe-done');tray.append(b)}tray.hidden=!tray.childNodes.length}
function build(){const v=node('div','omni-recipe');v.id='omni-recipe-mode';v.dataset.omniAddon=api.id;v.tabIndex=-1;v.setAttribute('role','dialog');v.setAttribute('aria-modal','true');v.setAttribute('aria-label','Recipe mode');
  const head=node('div','omni-recipe-head'),title=node('h1','omni-recipe-title',recipe.name||document.title),info=node('p','omni-recipe-meta',meta());
  const scaler=node('div','omni-recipe-scale');scaler.setAttribute('role','group');scaler.setAttribute('aria-label','Servings');yieldEl=node('span','omni-recipe-yield');scaler.append(yieldEl);
  scaleBtns=core.SCALES.map(s=>{const b=button('omni-recipe-sc',core.scaleLabel(s),'Amounts '+core.scaleLabel(s),()=>setScale(s));b.dataset.scale=String(s);return b});scaler.append(...scaleBtns);
  head.append(title,button('omni-recipe-close','Close','Close recipe mode',()=>close()),info,scaler);
  const cols=node('div','omni-recipe-cols'),left=node('section','omni-recipe-ings'),h2=node('h2','omni-recipe-h2','Ingredients');countEl=node('span','omni-recipe-count');h2.append(' ',countEl);
  ingList=node('ul','omni-recipe-list');left.append(h2,ingList);if(!recipe.ingredients.length)left.hidden=true;
  const right=node('section','omni-recipe-step');posEl=node('p','omni-recipe-pos');textEl=node('p','omni-recipe-text');textEl.setAttribute('aria-live','polite');timerRow=node('div','omni-recipe-timers');
  const nav=node('div','omni-recipe-nav');prevBtn=button('omni-recipe-prev','◀ Previous','Previous step',()=>go(step-1));nextBtn=button('omni-recipe-next','Next ▶','Next step',()=>go(step+1));nav.append(prevBtn,nextBtn);
  tray=node('div','omni-recipe-tray');tray.hidden=true;right.append(posEl,textEl,timerRow,nav,tray);cols.append(left,right);
  hintEl=node('p','omni-recipe-hint');alertBox=node('div','omni-recipe-alert');alertBox.setAttribute('role','alert');alertBox.hidden=true;
  v.append(head,cols,hintEl,alertBox);return v}
function hint(){if(hintEl)hintEl.textContent=fsOn?'L1 / R1 or ◀ ▶: step · ▲ ▼ and Square: tick · Triangle: timer · L3: amounts · Circle: close':'Pointer and Cross on the buttons · Back closes'}

// ---- Actions ----
function go(i){if(!recipe||!recipe.steps.length)return;const n=Math.max(0,Math.min(recipe.steps.length-1,i));if(n===step)return;step=n;renderStep();save()}
function toggle(i){if(checked.has(i))checked.delete(i);else checked.add(i);cursor=i;renderIngredients();focusIng();save()}
function setScale(s){if(s===scale||!core.SCALES.includes(s))return;scale=s;renderIngredients();save()}
function moveCursor(d){const n=recipe.ingredients.length;if(!n)return;cursor=cursor<0?(d>0?0:n-1):Math.max(0,Math.min(n-1,cursor+d));renderIngredients();focusIng()}
function focusIng(){const b=view&&view.querySelector('.omni-recipe-cursor');if(b){try{b.focus({preventScroll:false})}catch(_){}if(b.scrollIntoView)try{b.scrollIntoView({block:'nearest'})}catch(_){}}}
function timerPress(si,ti){const k=si+':'+ti,t=recipe.steps[si].timers[ti];let live=timers.get(k);
  if(!live){live={step:si,index:ti,seconds:t.seconds,left:t.seconds,endAt:Date.now()+t.seconds*1000,running:true,done:false,label:t.label};timers.set(k,live)}
  else if(live.done){timers.delete(k);hideAlert()}
  else if(live.running){live.left=Math.max(0,(live.endAt-Date.now())/1000);live.running=false}
  else{live.endAt=Date.now()+live.left*1000;live.running=true}
  ensureTick();repaintTimers()}
function repaintTimers(){if(!view)return;for(const b of view.querySelectorAll('.omni-recipe-timer'))paintTimer(b);paintTray()}
function ensureTick(){const any=[...timers.values()].some(t=>t.running);if(any&&!timerTick)timerTick=setInterval(tickTimers,250);else if(!any&&timerTick){clearInterval(timerTick);timerTick=0}}
function tickTimers(){const now=Date.now();for(const t of timers.values()){if(!t.running)continue;t.left=Math.max(0,(t.endAt-now)/1000);if(t.left<=0){t.running=false;t.done=true;ring(t)}}repaintTimers();ensureTick()}
// No sound: Omni's WebKit has Web Audio off (omni/webkit/configure-cmd.json), so the alert is on screen only.
function ring(t){const msg='Time is up: step '+(t.step+1)+' ('+t.label+')';
  if(view&&alertBox){alertBox.textContent='';alertBox.append(node('span','omni-recipe-alert-text',msg),button('omni-recipe-ok','OK','Dismiss',()=>{const k=t.step+':'+t.index;timers.delete(k);hideAlert();repaintTimers()}));alertBox.hidden=false;
    try{alertBox.querySelector('.omni-recipe-ok').focus({preventScroll:true})}catch(_){}}
  else if(api.toast)api.toast(msg).catch(()=>{})}
function hideAlert(){if(alertBox){alertBox.hidden=true;alertBox.textContent=''}}
function firstTimer(){const s=recipe.steps[step];if(s&&s.timers.length){const i=s.timers.findIndex((_,j)=>{const t=timers.get(step+':'+j);return!t||!t.done});timerPress(step,i<0?0:i)}}

// ---- Open / close: full screen when allowed (then Omni sends L1/R1 as j/l and the D-pad as arrow keys), else an overlay ----
function open(){if(view||!enabled)return;try{recipe=core.find(document)||recipe}catch(_){}if(!recipe){api.toast('No recipe found on this page').catch(()=>{});return}
  load();cursor=-1;view=build();renderIngredients();renderStep();
  const h=html();saved={dark:h.getAttribute('data-omni-dark'),overflow:h.style.getPropertyValue('overflow'),prio:h.style.getPropertyPriority('overflow'),focus:document.activeElement,y:window.scrollY||0};
  h.setAttribute('data-omni-dark','off');h.style.setProperty('overflow','hidden','important');if(fab){fab.remove();fab=null}h.append(view);
  addEventListener('keydown',onKey,true);addEventListener('popstate',onPop);document.addEventListener('fullscreenchange',onFs);document.addEventListener('webkitfullscreenchange',onFs);
  // Back (Circle outside full screen, browser back) closes recipe mode instead of leaving the page.
  try{const st=history.state&&typeof history.state==='object'?Object.assign({},history.state):{};st.omniRecipeMode=1;history.pushState(st,'');pushed=true}catch(_){pushed=false}
  // Called from the button press itself, so the page's user gesture is still there for the full-screen request.
  try{const req=view.requestFullscreen||view.webkitRequestFullscreen;const p=req&&req.call(view);if(p&&p.catch)p.catch(()=>{})}catch(_){}
  // Keep the screen on if this WebKit offers the Screen Wake Lock API (Omni's build does not list it; checked, not assumed).
  try{if(navigator.wakeLock&&navigator.wakeLock.request)navigator.wakeLock.request('screen').then(l=>{if(view)wake=l;else l.release().catch(()=>{})},()=>{})}catch(_){}
  hint();try{view.focus({preventScroll:true})}catch(_){}}
function close(fromPop){if(!view)return;removeEventListener('keydown',onKey,true);removeEventListener('popstate',onPop);document.removeEventListener('fullscreenchange',onFs);document.removeEventListener('webkitfullscreenchange',onFs);
  const fsEl=document.fullscreenElement||document.webkitFullscreenElement;if(fsEl===view)try{const x=(document.exitFullscreen||document.webkitExitFullscreen).call(document);if(x&&x.catch)x.catch(()=>{})}catch(_){}
  if(wake){wake.release().catch(()=>{});wake=null}view.remove();view=null;fsOn=false;alertBox=ingList=countEl=posEl=textEl=timerRow=tray=prevBtn=nextBtn=yieldEl=hintEl=null;scaleBtns=[];
  const h=html();if(saved){if(saved.dark===null)h.removeAttribute('data-omni-dark');else h.setAttribute('data-omni-dark',saved.dark);
    if(saved.overflow)h.style.setProperty('overflow',saved.overflow,saved.prio);else h.style.removeProperty('overflow');
    try{scrollTo(0,saved.y)}catch(_){}if(saved.focus&&saved.focus.isConnected)try{saved.focus.focus({preventScroll:true})}catch(_){}saved=null}
  if(pushed&&!fromPop){try{if(history.state&&history.state.omniRecipeMode)history.back()}catch(_){}}pushed=false;showFab()}
function onPop(){if(view&&!(history.state&&history.state.omniRecipeMode))close(true)}
// Circle in full screen makes Omni leave full screen; that closes recipe mode too.
function onFs(){if(!view)return;const el=document.fullscreenElement||document.webkitFullscreenElement;if(el===view){fsOn=true;hint()}else if(fsOn)close()}
function editable(t){return t&&(t.isContentEditable||/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName||''))}
// Keys while open. In full screen Omni turns pad buttons into keys: L1 j, R1 l, Square k, Triangle c, L3 m, D-pad arrows.
function onKey(e){if(!view)return;if(e.ctrlKey||e.metaKey||(e.altKey&&!(e.shiftKey&&e.code==='KeyK'))){return}
  const k=e.key,stop=()=>{e.preventDefault();e.stopImmediatePropagation()};
  if(k==='Escape'||k==='GoBack'||(k==='Backspace'&&!editable(e.target))||(e.altKey&&e.shiftKey&&e.code==='KeyK')){stop();if(alertBox&&!alertBox.hidden){hideAlert()}else close();return}
  // A finished timer's alert: Square, Triangle or Enter clears it first.
  if(alertBox&&!alertBox.hidden&&(k==='k'||k==='K'||k==='c'||k==='C'||k==='Enter')){stop();const ok=alertBox.querySelector('.omni-recipe-ok');if(ok)ok.click();return}
  if(k==='ArrowRight'||k==='PageDown'||k==='l'||k==='L'||k==='MediaTrackNext'){stop();go(step+1);return}
  if(k==='ArrowLeft'||k==='PageUp'||k==='j'||k==='J'||k==='MediaTrackPrevious'){stop();go(step-1);return}
  if(k==='ArrowDown'){stop();moveCursor(1);return}if(k==='ArrowUp'){stop();moveCursor(-1);return}
  if(k==='k'||k==='K'){stop();if(cursor<0)moveCursor(1);else toggle(cursor);return}
  if(k==='c'||k==='C'){stop();firstTimer();return}
  if(k==='m'||k==='M'){stop();setScale(core.nextScale(scale));return}
  // Enter / Space press the focused button (default action); the page's own shortcuts stay quiet while open.
  if(!view.contains(e.target))try{view.focus({preventScroll:true})}catch(_){}e.stopImmediatePropagation()}
function onShortcut(e){if(!enabled||view||!e.isTrusted||!e.altKey||!e.shiftKey||e.code!=='KeyK'||e.repeat)return;e.preventDefault();e.stopImmediatePropagation();open()}
function onLoad(){later()}
function start(){if(enabled)return;enabled=true;addEventListener('keydown',onShortcut,true);if(document.readyState==='complete')later();else addEventListener('load',onLoad,{once:true})}
function stop(){if(!enabled)return;enabled=false;removeEventListener('keydown',onShortcut,true);removeEventListener('load',onLoad);if(idle){(window.cancelIdleCallback||clearTimeout)(idle);idle=0}
  if(retry>0)clearTimeout(retry);retry=0;close();if(fab){fab.remove();fab=null}if(timerTick){clearInterval(timerTick);timerTick=0}timers.clear();recipe=null}
api.onEnable(start);api.onDisable(stop);if(api.onSettings)api.onSettings(()=>{if(enabled&&!view)showFab()});
window.OmniRecipeDiagnostics=()=>({enabled,recipe:!!recipe,open:!!view,fullscreen:fsOn,ingredients:recipe?recipe.ingredients.length:0,steps:recipe?recipe.steps.length:0,step,scale,checked:checked.size,timers:timers.size,persistent:writable,wakeLock:!!wake});
if(api.active)start()})();
