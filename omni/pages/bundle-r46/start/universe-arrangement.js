/* Local per-Universe arrangement. No native persistence is implied. */
(function(){
'use strict';
const ids=['bloom','aurora','cosmic','arcade','solstice','metro','sakura','abyss','prism','atlas','cassette','relay','loom','kinetic','tide'];
const slots=['hero','apps','pins','recents'],labels=['Search','Apps','Pinned sites','Recent sites'];
const panels=['.hero','.ob-apps-panel','.ob-pins-panel','.ob-recents-panel'].map(s=>document.querySelector(s));
const header=document.querySelector('.topline'),key='ob.universe.arrangements.v1';
if(!header||panels.some(p=>!p))return;
let current='',active=false,selected=-1,dragged=-1,undo=null,layouts={};
try{const raw=localStorage.getItem(key);if(raw&&raw.length<=4096){const data=JSON.parse(raw);if(data&&data.version===1&&data.layouts&&typeof data.layouts==='object')for(const id of ids){const a=data.layouts[id];if(Array.isArray(a)&&a.length===4&&new Set(a).size===4&&a.every(s=>slots.includes(s)))layouts[id]=a.slice()}}}catch(_){}
const button=text=>{const b=document.createElement('button');b.type='button';b.textContent=text;return b};
const toggle=button('Arrange'),done=button('Done'),reset=button('Reset layout'),back=button('Undo');
toggle.id='ob-arrange-toggle';toggle.setAttribute('aria-expanded','false');
const bar=document.createElement('div');bar.className='ob-arrange-bar';bar.hidden=true;bar.setAttribute('role','region');bar.setAttribute('aria-label','Arrange this Universe');
const status=document.createElement('p');status.setAttribute('role','status');status.className='ob-arrange-status';
bar.append(status,back,reset,done);header.append(toggle);header.append(bar);
const handles=panels.map((panel,i)=>{const b=button('Move '+labels[i]);b.className='ob-arrange-handle';b.hidden=true;b.draggable=true;b.dataset.panel=slots[i];b.setAttribute('aria-pressed','false');panel.prepend(b);b.onclick=()=>choose(i);return b});
function say(t){status.textContent=t}
function map(){return layouts[current]||slots}
function paint(){panels.forEach((p,i)=>{slots.forEach(s=>p.classList.remove('ob-slot-'+s));p.classList.add('ob-slot-'+map()[i])});handles.forEach((h,i)=>h.setAttribute('aria-pressed',String(selected===i)));back.disabled=!undo}
function save(){try{localStorage.setItem(key,JSON.stringify({version:1,layouts}));return true}catch(_){return false}}
function cancel(){selected=-1;dragged=-1;paint()}
function swap(a,b){if(a<0||b<0||a===b){cancel();return}undo=map().slice();const next=map().slice();[next[a],next[b]]=[next[b],next[a]];layouts[current]=next;selected=-1;dragged=-1;paint();say(save()?'Layout saved on this device.':'Layout changed for this visit; device storage is unavailable.');handles[a].focus()}
function choose(i){if(!active)return;if(selected===-1){selected=i;paint();say(labels[i]+' selected. Choose another panel to swap, or press Escape to cancel.')}else swap(selected,i)}
function mode(on){active=on;selected=-1;dragged=-1;bar.hidden=!on;handles.forEach(h=>h.hidden=!on);toggle.setAttribute('aria-expanded',String(on));document.body.classList.toggle('ob-arranging',on);paint();if(on){say('Drag a handle onto another, or select two handles to swap. Changes stay on this device.');handles[0].focus()}else toggle.focus()}
toggle.onclick=()=>mode(!active);done.onclick=()=>mode(false);
reset.onclick=()=>{undo=map().slice();delete layouts[current];cancel();say(save()?'Original layout restored on this device.':'Original layout restored for this visit; device storage is unavailable.')};
back.onclick=()=>{if(!undo)return;layouts[current]=undo;undo=null;cancel();say(save()?'Previous layout restored on this device.':'Previous layout restored for this visit; device storage is unavailable.')};
handles.forEach((h,i)=>{h.addEventListener('dragstart',e=>{if(!active){e.preventDefault();return}dragged=i;selected=i;paint();e.dataTransfer.effectAllowed='move';e.dataTransfer.setData('text/plain','omnibloom-panel:'+slots[i])});h.addEventListener('dragend',cancel);panels[i].addEventListener('dragover',e=>{if(active&&dragged>=0){e.preventDefault();e.dataTransfer.dropEffect='move'}});panels[i].addEventListener('drop',e=>{if(active&&dragged>=0){e.preventDefault();swap(dragged,i)}})});
window.addEventListener('keydown',e=>{if(!active||document.querySelector('dialog[open]'))return;const index=handles.indexOf(document.activeElement);if(e.key==='Escape'){e.preventDefault();e.stopImmediatePropagation();if(selected>=0){cancel();say('Move cancelled.')}else mode(false);return}if(index<0||!['ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(e.key))return;e.preventDefault();e.stopImmediatePropagation();const from=handles[index].getBoundingClientRect(),fx=from.x+from.width/2,fy=from.y+from.height/2;const candidates=handles.map((h,i)=>{const r=h.getBoundingClientRect(),dx=r.x+r.width/2-fx,dy=r.y+r.height/2-fy;const primary=e.key==='ArrowRight'?dx:e.key==='ArrowLeft'?-dx:e.key==='ArrowDown'?dy:-dy;return{i,primary,score:primary+2*Math.abs(e.key==='ArrowLeft'||e.key==='ArrowRight'?dy:dx)}}).filter(p=>p.i!==index&&p.primary>1).sort((a,b)=>a.score-b.score);if(candidates[0])handles[candidates[0].i].focus()},true);
function sync(){const next=document.body.dataset.obUniverse;if(!ids.includes(next)||next===current)return;current=next;undo=null;selected=-1;dragged=-1;paint();if(active)say('Arranging '+next+'. Drag a handle or select two panels to swap.')}
new MutationObserver(sync).observe(document.body,{attributes:true,attributeFilter:['data-ob-universe']});
new MutationObserver(()=>{if(current&&!panels[0].classList.contains('ob-slot-'+map()[0]))paint()}).observe(panels[0],{attributes:true,attributeFilter:['class']});
for(const name of ['omniPadController','omniMediaController']){const previous=window[name];if(typeof previous!=='function')continue;window[name]=function(action){const a=String(action).toLowerCase();if(active&&!document.querySelector('dialog[open]')){if(['circle','back','b'].includes(a)){if(selected>=0){cancel();say('Move cancelled.')}else mode(false);return true}if(handles.includes(document.activeElement)&&['up','down','left','right'].includes(a)){window.dispatchEvent(new KeyboardEvent('keydown',{key:'Arrow'+a[0].toUpperCase()+a.slice(1),cancelable:true}));return true}}return previous.apply(this,arguments)}}
window.addEventListener('pagehide',cancel);sync();
})();


