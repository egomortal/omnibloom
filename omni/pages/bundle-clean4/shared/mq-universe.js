// SPDX-License-Identifier: GPL-3.0-or-later
// Follow the selected Universe for presentation; never write a preference.
(()=>{'use strict';
if(document.body?.classList.contains('mq-start'))return;
const ids=['bloom','aurora','cosmic','arcade','solstice','metro','sakura','abyss','prism','atlas','cassette','relay','loom','kinetic','tide'];
const builtIn=new Set(['bloom','arcade','atlas']);
const scriptBase=document.currentScript?.src||new URL('../shared/mq-universe.js',location.href).href;
let epoch=0,sheet=null;
function apply(value){
 const id=ids.includes(value)?value:'bloom';
 document.documentElement.dataset.mqUniverse=id;
 const art=new URL(id==='atlas'?'art/mq-atlas.webp':'art/universes/'+id+'.webp',scriptBase);
 document.documentElement.style.setProperty('--mq-universe-art',`url("${art.href}")`);
 if(builtIn.has(id)){
  if(sheet){sheet.remove();sheet=null;}
  document.documentElement.dataset.mqLayoutReady=id;
  return;
 }
 const href=new URL('universe-layouts/'+id+'.css',scriptBase).href;
 if(sheet?.href===href)return;
 if(!sheet){sheet=document.createElement('link');sheet.rel='stylesheet';sheet.dataset.mqLayout='';document.head.append(sheet);}
 const current=sheet;
 document.documentElement.dataset.mqLayoutReady='loading';
 current.onload=()=>{if(sheet===current&&document.documentElement.dataset.mqUniverse===id)document.documentElement.dataset.mqLayoutReady=id;};
 current.onerror=()=>{if(sheet===current&&document.documentElement.dataset.mqUniverse===id)document.documentElement.dataset.mqLayoutReady='unavailable';};
 current.href=href;
}
function stored(){try{return localStorage.getItem('ob.universe');}catch{return'bloom';}}
apply(stored());
const token=epoch;
if(window.obUniverses?.read)obUniverses.read().then(value=>{if(epoch===token)apply(value||stored());}).catch(()=>{});
addEventListener('storage',event=>{if(event.key==='ob.universe'){epoch++;apply(event.newValue);}});
addEventListener('ob-universe-change',event=>{epoch++;apply(event.detail);});
})();
