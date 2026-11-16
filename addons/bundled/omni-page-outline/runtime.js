// Omni add-on "Page outline": page glue. MIT, Omnibloom contributors.
// Controller path in Omni: D-pad up/down and the right stick reach the page as wheel events, Cross is a click at the
// pointer and Circle is history Back. So while the outline is open it takes wheel events (move the selection), fills
// the screen with a see-through catcher (Cross anywhere = go to the selected entry; Cross on an entry = go there) and
// holds one history entry (Circle closes it). A keyboard works too: arrows, Enter, Escape, Alt+Shift+O.
(()=>{'use strict';const api=window.omniAddon;if(!api||!api.top)return;const core=OmniOutlineCore;
let enabled=false,items=[],index=new WeakMap(),states=[],io=null,cur=-1,sel=0,root=null,panel=null,list=null,fab=null,pushed=false,prior=null,acc=0,accAt=0,idle=0;
const WHEEL={capture:true,passive:false};
const node=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text)e.textContent=text;return e};
const reduced=()=>{try{return matchMedia('(prefers-reduced-motion: reduce)').matches}catch(_){return false}};
// Laid-out check for candidates only (display:none anywhere above leaves no boxes; visibility is inherited).
function isHidden(el){try{if(!el.getClientRects().length)return true;const s=getComputedStyle(el);return s.visibility==='hidden'||s.visibility==='collapse'}catch(_){return false}}
function scan(){let r={items:[]};try{r=core.collect(document.body,{isHidden,byId:id=>document.getElementById(id),landmarks:api.settings.get('landmarks')!==false})}catch(_){}
items=r.items;index=new WeakMap();items.forEach((it,i)=>{if(!index.has(it.el))index.set(it.el,i)});observe();showFab()}
// Current section without polling: one IntersectionObserver whose root box is the top 35 % of the viewport.
function observe(){if(io){io.disconnect();io=null}states=items.map(()=>({band:false,above:false}));cur=-1;
if(!items.length||typeof IntersectionObserver!=='function')return;
io=new IntersectionObserver(onIntersect,{rootMargin:'0px 0px -65% 0px',threshold:0});for(const it of items)io.observe(it.el)}
function onIntersect(entries){for(const e of entries){const i=index.get(e.target);if(i===undefined)continue;const top=e.rootBounds?e.rootBounds.top:0;
states[i]={band:e.isIntersecting,above:!e.isIntersecting&&e.boundingClientRect.top<top}}
const now=core.pickCurrent(states);if(now!==cur){cur=now;markCurrent()}}
// Once, when the outline opens (the observer's first report is asynchronous): the same rule as pickCurrent.
function currentNow(){const line=innerHeight*0.35;let c=-1;for(let i=0;i<items.length;i++){try{if(items[i].el.getBoundingClientRect().top<=line)c=i}catch(_){}}return c}
function markCurrent(){if(!list)return;for(const b of list.children){const on=+b.dataset.i===cur;if(on)b.setAttribute('aria-current','location');else b.removeAttribute('aria-current')}}
function showFab(){const want=enabled&&!root&&items.length>=3&&api.settings.get('button')!==false;if(!want){if(fab){fab.remove();fab=null}return}if(fab)return;
fab=node('button','omni-outline-fab','Outline');fab.type='button';fab.dataset.omniAddon=api.id;fab.title='Headings on this page (Alt+Shift+O)';fab.onclick=()=>open();(document.body||document.documentElement).append(fab)}
function select(i){if(!list||!items.length)return;sel=core.step(i,0,items.length);for(const b of list.children)b.setAttribute('aria-selected',String(+b.dataset.i===sel));
const b=list.children[sel];if(!b)return;try{b.focus({preventScroll:true})}catch(_){}
// Keep the selected row in view inside the list only (scrollIntoView could move the page as well).
const top=b.offsetTop,bottom=top+b.offsetHeight;if(top<list.scrollTop)list.scrollTop=top;else if(bottom>list.scrollTop+list.clientHeight)list.scrollTop=bottom-list.clientHeight}
function go(i){if(i!==undefined)select(i);const it=items[sel];if(!it)return;
if(!it.el.isConnected){api.toast('That part of the page has gone; outline refreshed').catch(()=>{});rebuild();return}
try{it.el.scrollIntoView({behavior:reduced()?'auto':'smooth',block:'start'})}catch(_){try{it.el.scrollIntoView(true)}catch(_){}}}
function fill(){list.textContent='';items.forEach((it,i)=>{const b=node('button','omni-outline-item omni-outline-d'+it.depth+(it.kind==='landmark'?' omni-outline-mark':''));b.type='button';b.dataset.i=String(i);
b.setAttribute('role','option');b.tabIndex=-1;if(it.kind==='landmark')b.append(node('span','omni-outline-tag',it.label));else b.append(node('span','omni-outline-lv','H'+it.level));
b.append(node('span','omni-outline-text',it.text));list.append(b)});
const count=panel.querySelector('.omni-outline-count');if(count)count.textContent=items.length+(items.length>=core.MAX_ENTRIES?'+':'');markCurrent()}
function rebuild(){scan();if(!root)return;if(!items.length){close();return}fill();select(Math.min(sel,items.length-1))}
function open(){if(root||!enabled)return;scan();if(!items.length){api.toast('No headings found on this page').catch(()=>{});return}
cur=currentNow();prior=document.activeElement;root=node('div','omni-outline');root.dataset.omniAddon=api.id;
panel=node('div','omni-outline-panel');panel.setAttribute('role','dialog');panel.setAttribute('aria-label','Page outline');
const head=node('div','omni-outline-head');head.append(node('span','omni-outline-title','Outline'),node('span','omni-outline-count'));
list=node('div','omni-outline-list');list.setAttribute('role','listbox');list.setAttribute('aria-label','Headings and page regions');
const hint=node('div','omni-outline-hint','D-pad: move · Cross: go · Circle: close');hint.setAttribute('aria-hidden','true');
panel.append(head,list,hint);root.append(panel);fill();
root.addEventListener('click',onClick);if(fab){fab.remove();fab=null}document.documentElement.append(root);select(cur>=0?cur:0);
try{const st=history.state&&typeof history.state==='object'?Object.assign({},history.state):{};st.omniOutline=1;history.pushState(st,'');pushed=true}catch(_){pushed=false}
addEventListener('popstate',onPop);addEventListener('wheel',onWheel,WHEEL);addEventListener('keydown',onPanelKey,true)}
function close(fromPop){if(!root)return;removeEventListener('popstate',onPop);removeEventListener('wheel',onWheel,WHEEL);removeEventListener('keydown',onPanelKey,true);
root.remove();root=panel=list=null;acc=0;
if(pushed&&!fromPop){try{if(history.state&&history.state.omniOutline)history.back()}catch(_){}}pushed=false;
if(prior&&prior.isConnected)try{prior.focus({preventScroll:true})}catch(_){}prior=null;showFab()}
function onPop(){if(root&&!(history.state&&history.state.omniOutline))close(true)}
function onClick(e){const t=e.target,b=t&&t.closest?t.closest('.omni-outline-item'):null;if(b){go(+b.dataset.i);return}if(!panel.contains(t))go()}
function onWheel(e){if(!root)return;e.preventDefault();e.stopImmediatePropagation();const dy=e.deltaMode===1?e.deltaY*40:e.deltaMode===2?e.deltaY*400:e.deltaY;
const now=performance.now();if(now-accAt>300)acc=0;accAt=now;const r=core.wheelSteps(acc,dy);acc=r.acc;if(r.steps)select(sel+r.steps)}
function onPanelKey(e){if(!root||e.ctrlKey||e.metaKey||(e.altKey&&!(e.shiftKey&&e.code==='KeyO')))return;let handled=true;
switch(e.key){case'ArrowDown':case'ArrowRight':select(sel+1);break;case'ArrowUp':case'ArrowLeft':select(sel-1);break;
case'PageDown':select(sel+10);break;case'PageUp':select(sel-10);break;case'Home':select(0);break;case'End':select(items.length-1);break;
case'Enter':case' ':go();break;case'Escape':case'GoBack':case'Backspace':close();break;default:handled=e.altKey&&e.shiftKey&&e.code==='KeyO';if(handled&&!e.repeat)close()}
if(handled){e.preventDefault();e.stopImmediatePropagation()}}
function onKey(e){if(!enabled||root||!e.isTrusted||!e.altKey||!e.shiftKey||e.code!=='KeyO'||e.repeat)return;e.preventDefault();e.stopImmediatePropagation();open()}
function later(){if(idle||!enabled)return;const run=()=>{idle=0;if(enabled&&!root)scan()};idle=window.requestIdleCallback?requestIdleCallback(run,{timeout:3000}):setTimeout(run,800)}
function onLoad(){later()}
function start(live){if(enabled)return;enabled=true;addEventListener('keydown',onKey,true);
if(document.readyState==='complete')later();else addEventListener('load',onLoad,{once:true});
if(live&&document.visibilityState!=='hidden')open()}
function stop(){if(!enabled)return;enabled=false;removeEventListener('keydown',onKey,true);removeEventListener('load',onLoad);
if(idle){(window.cancelIdleCallback||clearTimeout)(idle);idle=0}close();if(io){io.disconnect();io=null}if(fab){fab.remove();fab=null}items=[];states=[];cur=-1}
// Switched on from the quick switch while this page is open: the switch itself is the request to show the outline.
function injectedLate(){try{const nav=performance.getEntriesByType('navigation')[0];return document.readyState==='complete'&&nav&&nav.loadEventEnd>0&&performance.now()-nav.loadEventEnd>1500}catch(_){return false}}
api.onEnable(()=>start(true));api.onDisable(stop);api.onSettings(()=>{if(!enabled)return;if(root)rebuild();else scan()});
window.OmniOutlineDiagnostics=()=>({enabled,open:!!root,entries:items.length,current:cur,selected:sel,observing:!!io});
if(api.active)start(injectedLate())})();
