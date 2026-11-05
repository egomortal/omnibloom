// SPDX-License-Identifier: GPL-3.0-or-later
/* Proposed trusted read-only bridge: video.stats. No media URLs or native writes. */
(()=>{'use strict';
const $=id=>document.getElementById(id),dialog=$('video-stats'),menu=$('options');
let epoch=0,visible=true,pending=null,serial=0;
const foreground=()=>![...document.querySelectorAll('dialog[open],[role=dialog]:not([hidden])')].some(e=>e!==dialog&&e.getClientRects().length);
const focus=e=>{if(e?.isConnected&&!e.disabled&&e.getClientRects().length)obUI.focus(e)};
function invalidate(){epoch++;if(pending)clearTimeout(pending.timer);pending=null;$('stats-refresh').removeAttribute('aria-busy');$('stats-values').replaceChildren()}
function parse(v){
 if(!v||typeof v!=='object'||Array.isArray(v))throw Error('INVALID');
 const unknown='Unknown';
 if(v.res!=null&&(typeof v.res!=='string'||!/^\d{2,5}x\d{2,5}$/.test(v.res)))throw Error('INVALID');
 if(v.codec!=null&&(typeof v.codec!=='string'||!v.codec.length||v.codec.length>48))throw Error('INVALID');
 if(v.path!=null&&!['GPU','CPU','SDL'].includes(v.path))throw Error('INVALID');
 if(v.hdr!=null&&typeof v.hdr!=='boolean')throw Error('INVALID');
 for(const k of ['fpsShown','fpsDropped'])if(v[k]!=null&&(!Number.isFinite(v[k])||v[k]<0||v[k]>1000))throw Error('INVALID');
 return [['Video resolution',v.res==null?unknown:v.res.replace('x',' × ')],['Codec',v.codec==null?unknown:v.codec],['Frames shown / second',v.fpsShown==null?unknown:String(v.fpsShown)],['Frames dropped / second',v.fpsDropped==null?unknown:String(v.fpsDropped)],['Presentation path',v.path==null?unknown:v.path],['HDR output',v.hdr==null?unknown:v.hdr?'On':'Off']];
}
async function refresh(){
 if(pending||!visible||document.hidden||!dialog.open)return;
 const request={epoch};pending=request;$('stats-values').replaceChildren();$('stats-status').textContent='Reading player statistics…';$('stats-refresh').setAttribute('aria-busy','true');
 const owns=()=>pending===request&&request.epoch===epoch&&visible&&!document.hidden&&dialog.open;
 try{
  if(typeof window.omnibloomHost?.request!=='function')throw Error('UNAVAILABLE');
  const reply=await Promise.race([window.omnibloomHost.request({version:1,id:`video-stats-${++serial}`,method:'video.stats',params:{}}),new Promise((_,reject)=>{request.timer=setTimeout(()=>reject(Error('TIMEOUT')),5000)})]);
  if(!owns())return;if(reply?.ok!==true)throw Error('UNAVAILABLE');
  const rows=parse(reply.result);for(const [label,value] of rows){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;dd.textContent=value;$('stats-values').append(dt,dd)}
  $('stats-status').textContent='Player-reported rates and output. Refresh to update.';
 }catch(_){if(owns())$('stats-status').textContent='Statistics unavailable. Refresh to try again.'}finally{clearTimeout(request.timer);if(owns()){pending=null;$('stats-refresh').removeAttribute('aria-busy')}}
}
function close(){if(!dialog.open)return;invalidate();dialog.close();if(visible&&!document.hidden&&!document.querySelector('dialog[open]')){menu.showModal();focus($('show-stats'))}}
$('show-stats').onclick=()=>{if(!visible||document.hidden)return;if(menu.open)menu.close();invalidate();dialog.showModal();focus($('stats-close'));refresh()};
$('stats-refresh').onclick=refresh;$('stats-close').onclick=close;
dialog.addEventListener('cancel',e=>{e.preventDefault();e.stopImmediatePropagation();close()},true);
document.addEventListener('keydown',e=>{if(dialog.open&&foreground()&&e.key==='Escape'){e.preventDefault();e.stopImmediatePropagation();close()}},true);
for(const key of ['omniPadController','omniMediaController']){const previous=window[key];window[key]=function(action){if(dialog.open&&foreground()&&['circle','b','back'].includes(String(action).toLowerCase())){close();return true}return previous?.(action)??false}}
function suspend(){visible=false;invalidate();if(dialog.open)dialog.close();$('stats-status').textContent='Open statistics to read the current player.'}
addEventListener('pagehide',suspend);addEventListener('pageshow',()=>{visible=true});document.addEventListener('visibilitychange',()=>{if(document.hidden)suspend();else visible=true});
})();
