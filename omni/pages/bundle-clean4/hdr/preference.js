// SPDX-License-Identifier: GPL-3.0-or-later
(()=>{'use strict';
 const $=id=>document.getElementById(id),mode=$('pref-mode'),read=$('pref-read'),save=$('pref-save'),status=$('pref-status');
 let revision=null,epoch=0,pending=null,active=true;
 function ready(){return active&&!document.hidden}
 function render(){mode.disabled=!!pending||revision===null||!ready();save.disabled=mode.disabled;read.disabled=!!pending||!ready()}
 function valid(v){return v&&['off','auto','on'].includes(v.mode)&&Number.isInteger(v.revision)&&v.revision>0&&v.revision<=2147483646&&v.autoSupported===false&&v.hdr10Passthrough===false}
 async function run(write){
  if(pending||!ready()||(write&&revision===null))return;
  const request={epoch,mode:mode.value,revision,focus:document.activeElement};pending=request;
  const owns=()=>pending===request&&epoch===request.epoch&&ready();
  if([mode,save,read].includes(request.focus))status.focus();render();status.textContent=write?'Saving preference…':'Reading preference…';
  try{
   if(typeof window.omnibloomHost?.request!=='function')throw Error('UNAVAILABLE');
   const result=await Promise.race([window.omnibloomHost.request({version:1,method:write?'video.hdr.preference.write':'video.hdr.preference.read',params:write?{mode:request.mode,revision:request.revision}:{}}),new Promise((_,reject)=>request.timer=setTimeout(()=>reject(Error('TIMEOUT')),5000))]);
   if(!owns())return;
   if(result?.ok!==true||!valid(result.result))throw Error(result?.code||'INVALID');
   revision=result.result.revision;mode.value=result.result.mode;status.textContent=write?'Preference saved for the next app start. HDR output still depends on engine and display support.':'Saved preference loaded. Automatic HDR is not available yet.';
  }catch(e){if(owns()){revision=null;status.textContent=e.message==='STALE_STATE'?'Preference changed elsewhere. Read it again before saving.':'Preference unavailable. Read again to retry.'}}
  finally{clearTimeout(request.timer);if(owns()){pending=null;render();if(document.activeElement===status&&!document.querySelector('dialog[open]')){const target=request.focus; if(target?.isConnected&&!target.disabled&&target.getClientRects().length)target.focus()}}}
 }
 read.onclick=()=>run(false);save.onclick=()=>run(true);
 function invalidate(){epoch++;if(pending)clearTimeout(pending.timer);pending=null;revision=null;status.textContent='Read the engine preference to begin.';render()}
 addEventListener('pagehide',()=>{active=false;invalidate()});addEventListener('pageshow',()=>{active=true;render()});document.addEventListener('visibilitychange',()=>{if(document.hidden)invalidate();else render()});render();
})();
